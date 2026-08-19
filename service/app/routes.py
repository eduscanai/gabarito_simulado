from __future__ import annotations

import base64
import json
import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from . import omr_correction as corr
from . import omr_generation as gen
from .auth import verificar_token
from .grading import grade_responses
from .pdf_split import split_into_pages
from .schemas import (
    ArquivoGerado,
    CorrigirFolhaResponse,
    DividirFolhaResponse,
    FolhaAluno,
    GerarGabaritoRequest,
    GerarGabaritoResponse,
    MatriculaDetectada,
    PaginaDividida,
    QRDetectado,
    Questao,
)

router = APIRouter(prefix="/v1", dependencies=[Depends(verificar_token)])

SUPPORTED_SHEET_EXTENSIONS = {".png", ".jpg", ".jpeg", ".pdf"}


@router.post("/gabarito/gerar", response_model=GerarGabaritoResponse)
async def gerar_gabarito(payload: GerarGabaritoRequest) -> GerarGabaritoResponse:
    top = gen.BATCH_QUESTION_TOP if payload.matricula_em_blocos else gen.PLAIN_QUESTION_TOP
    layout = gen.calculate_layout(payload.questoes, top=top)
    template = gen.create_template(layout)
    config = gen.create_config()
    marker_image = gen.create_marker_image()

    student_id_digits = gen.STUDENT_ID_DIGITS if payload.matricula_em_blocos else 0

    folha_respostas = gen.draw_answer_sheet(
        marker_image,
        payload.titulo,
        payload.identificador,
        layout,
        student_id_digits=student_id_digits,
    )
    folha_solucao = gen.draw_answer_sheet(
        marker_image,
        payload.titulo,
        payload.identificador,
        layout,
        show_answers=True,
        student_id_digits=student_id_digits,
    )

    folhas_alunos_bytes = [
        (
            aluno.aluno_id,
            gen.draw_answer_sheet(
                marker_image,
                payload.titulo,
                payload.identificador,
                layout,
                student_id_digits=student_id_digits,
                qr_image=gen.create_qr_image(
                    f"SIM:{payload.identificador}|ALU:{aluno.aluno_id}"
                ),
                aluno_nome=aluno.nome,
                aluno_matricula=aluno.matricula,
                turma_nome=payload.turma,
            ),
        )
        for aluno in payload.alunos
    ]

    folha_completa_base64 = (
        base64.b64encode(
            gen.merge_pdfs([conteudo for _, conteudo in folhas_alunos_bytes])
        ).decode("ascii")
        if folhas_alunos_bytes
        else None
    )

    return GerarGabaritoResponse(
        gabarito={f"q{q.numero}": q.resposta for q in payload.questoes},
        pesos={f"q{q.numero}": q.peso for q in payload.questoes},
        arquivos=ArquivoGerado(
            template_json=template,
            config_json=config,
            marcador_base64=base64.b64encode(
                gen.image_to_bytes(marker_image)
            ).decode("ascii"),
            folha_respostas_base64=base64.b64encode(folha_respostas).decode("ascii"),
            folha_solucao_base64=base64.b64encode(folha_solucao).decode("ascii"),
        ),
        folhas_alunos=[
            FolhaAluno(
                aluno_id=aluno_id,
                folha_base64=base64.b64encode(conteudo).decode("ascii"),
            )
            for aluno_id, conteudo in folhas_alunos_bytes
        ],
        folha_completa_base64=folha_completa_base64,
    )


@router.post("/folha/dividir", response_model=DividirFolhaResponse)
async def dividir_folha(arquivo: UploadFile = File(...)) -> DividirFolhaResponse:
    """Split one upload into per-page images (a multi-page PDF -> N PNGs).

    Used for batch scans: the caller splits first, then calls
    /v1/folha/corrigir once per returned page.
    """
    suffix = Path(arquivo.filename or "").suffix.lower()
    if suffix not in SUPPORTED_SHEET_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail="Formato inválido. Use PDF, PNG, JPG ou JPEG.",
        )

    content = await arquivo.read()
    try:
        pages = split_into_pages(arquivo.filename or "folha", content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return DividirFolhaResponse(
        paginas=[
            PaginaDividida(
                nome=nome,
                conteudo_base64=base64.b64encode(conteudo).decode("ascii"),
            )
            for nome, conteudo in pages
        ]
    )


async def _save_upload(upload: UploadFile, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    content = await upload.read()
    destination.write_bytes(content)


@router.post("/folha/corrigir", response_model=CorrigirFolhaResponse)
async def corrigir_folha(
    sheet: UploadFile = File(...),
    template: UploadFile = File(...),
    config: UploadFile = File(...),
    marker: UploadFile = File(...),
    matricula_em_blocos: bool = Form(False),
    gabarito_json: str | None = Form(default=None),
) -> CorrigirFolhaResponse:
    sheet_suffix = Path(sheet.filename or "").suffix.lower()
    if sheet_suffix not in SUPPORTED_SHEET_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail="Formato de folha inválido. Use PDF, PNG, JPG ou JPEG.",
        )

    run_dir = corr.new_run_dir()
    input_dir = run_dir / "input"
    output_dir = run_dir / "output"
    sheet_path = input_dir / f"folha{sheet_suffix}"

    try:
        await _save_upload(sheet, sheet_path)
        await _save_upload(template, input_dir / "template.json")
        await _save_upload(config, input_dir / "config.json")
        await _save_upload(marker, input_dir / "omr_marker.jpg")

        completed = corr.run_omrchecker(input_dir, output_dir)

        if completed.returncode != 0:
            error_tail = (completed.stderr or completed.stdout or "")[-2500:]
            raise HTTPException(
                status_code=422,
                detail=f"O OMRChecker não conseguiu processar a folha: {error_tail}",
            )

        detected = corr.parse_omr_csv(output_dir / "Results")

        # Alinha uma vez só (QR e blocos de matrícula usam a mesma folha
        # alinhada, evitando re-alinhar duas vezes). QR é tentado sempre,
        # mesmo em folhas sem matrícula em blocos — se o alinhamento falhar
        # nesse caso, degrada pra "QR não encontrado" em vez de derrubar a
        # correção (que já tinha funcionado até aqui via o OMRChecker).
        aligned_sheet = None
        try:
            aligned_sheet = corr.align_sheet_to_template(sheet_path)
        except Exception:
            if matricula_em_blocos:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        "Não foi possível localizar os quatro marcadores da "
                        "folha para ler a matrícula/QR."
                    ),
                )

        qr_resultado = None
        if aligned_sheet is not None:
            qr_parsed = corr.read_qr_from_aligned_sheet(aligned_sheet)
            if qr_parsed:
                qr_resultado = QRDetectado(simulado_id=qr_parsed[0], aluno_id=qr_parsed[1])

        matricula_resultado = None
        if matricula_em_blocos and aligned_sheet is not None:
            ocr_dir = run_dir / "ocr"
            ocr_dir.mkdir(parents=True, exist_ok=True)
            ocr_result = corr.recognize_registration_from_blocks(aligned_sheet, ocr_dir)
            matricula_resultado = MatriculaDetectada(
                valor=ocr_result["registration"],
                digitos=ocr_result["digits"],
                ink_ratios=ocr_result["ink_ratios"],
                gap_invalido=ocr_result["invalid_gap"],
            )

        nota_resultado = None
        if gabarito_json:
            try:
                gabarito_payload = json.loads(gabarito_json)
                questoes = [Questao(**item) for item in gabarito_payload["questoes"]]
                valor_maximo = float(gabarito_payload.get("valor_maximo", 10))
            except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                raise HTTPException(
                    status_code=400, detail=f"gabarito_json inválido: {exc}"
                ) from exc
            nota_resultado = grade_responses(detected, questoes, valor_maximo)

        imagem_base64 = None
        checked_image = corr.newest_checked_image(output_dir)
        if checked_image:
            imagem_base64 = base64.b64encode(checked_image.read_bytes()).decode("ascii")

        return CorrigirFolhaResponse(
            respostas_detectadas=detected,
            matricula=matricula_resultado,
            qr=qr_resultado,
            nota=nota_resultado,
            imagem_processada_base64=imagem_base64,
            log_excerto=(completed.stdout or "")[-1800:],
        )
    finally:
        shutil.rmtree(run_dir, ignore_errors=True)
