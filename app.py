from __future__ import annotations

import csv
import json
import math
import re
import shutil
import subprocess
import sys
import uuid
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import Body, FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image, ImageDraw
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen.canvas import Canvas


BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
DATA_DIR = BASE_DIR / "data" / "avaliacoes"
OMR_ROOT = BASE_DIR.parent

DATA_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Criador de avaliações OMR")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount("/arquivos", StaticFiles(directory=DATA_DIR), name="arquivos")


PAGE_WIDTH = 1200
PAGE_HEIGHT = 1600
CARD_WIDTH_MM = 150
CARD_HEIGHT_MM = 200
BUBBLE_SIZE = 34
MARKER_RATIO = 17


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^\w\s-]", "", value, flags=re.UNICODE)
    value = re.sub(r"[-\s]+", "-", value)
    return value.strip("-") or "avaliacao"


def validate_payload(payload: dict[str, Any]) -> tuple[str, list[dict[str, Any]], float]:
    title = str(payload.get("title", "")).strip()
    questions = payload.get("questions")
    points = payload.get("points_per_question", 1)

    if not title:
        raise HTTPException(400, "Informe o título da avaliação.")

    if not isinstance(questions, list) or not 1 <= len(questions) <= 100:
        raise HTTPException(400, "A avaliação deve ter entre 1 e 100 questões.")

    try:
        points_float = float(points)
    except (TypeError, ValueError) as exc:
        raise HTTPException(400, "O valor por questão é inválido.") from exc

    if points_float <= 0:
        raise HTTPException(400, "O valor por questão deve ser positivo.")

    normalized: list[dict[str, Any]] = []

    for index, question in enumerate(questions, start=1):
        if not isinstance(question, dict):
            raise HTTPException(400, f"Questão {index} inválida.")

        option_count = question.get("option_count")
        answer = str(question.get("answer", "")).upper().strip()

        if not isinstance(option_count, int) or not 2 <= option_count <= 5:
            raise HTTPException(
                400,
                f"A questão {index} deve ter entre 2 e 5 alternativas.",
            )

        allowed = [chr(ord("A") + i) for i in range(option_count)]

        if answer not in allowed:
            raise HTTPException(
                400,
                f"Marque uma resposta válida na questão {index}.",
            )

        normalized.append(
            {
                "number": index,
                "option_count": option_count,
                "options": allowed,
                "answer": answer,
            }
        )

    return title, normalized, points_float


def create_marker(path: Path) -> None:
    size = 160
    image = Image.new("RGB", (size, size), "white")
    draw = ImageDraw.Draw(image)

    draw.ellipse((10, 10, size - 10, size - 10), fill="black")
    draw.ellipse((37, 37, size - 37, size - 37), fill="white")
    draw.ellipse((65, 65, size - 65, size - 65), fill="black")

    image.save(path, quality=100)


def calculate_layout(questions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    total = len(questions)

    if total <= 25:
        columns = 1
    elif total <= 50:
        columns = 2
    elif total <= 75:
        columns = 3
    else:
        columns = 4

    rows_per_column = math.ceil(total / columns)

    left = 100
    right = 1100
    top = 285
    bottom = 1420
    available_height = bottom - top

    row_gap = 0 if rows_per_column == 1 else available_height / (rows_per_column - 1)
    row_gap = min(48, row_gap)

    column_width = (right - left) / columns
    max_options = max(q["option_count"] for q in questions)

    option_area = column_width - 105
    bubble_gap = 0 if max_options == 1 else min(
        52,
        (option_area - BUBBLE_SIZE) / max(1, max_options - 1),
    )
    bubble_gap = max(38, bubble_gap)

    result: list[dict[str, Any]] = []

    for zero_index, question in enumerate(questions):
        column = zero_index // rows_per_column
        row = zero_index % rows_per_column

        column_left = left + column * column_width
        origin_x = column_left + 62
        origin_y = top + row * row_gap

        result.append(
            {
                **question,
                "column": column,
                "row": row,
                "origin": [round(origin_x), round(origin_y)],
                "bubble_gap": round(bubble_gap, 2),
            }
        )

    return result


def create_template(layout: list[dict[str, Any]]) -> dict[str, Any]:
    field_blocks: dict[str, Any] = {}

    for question in layout:
        field_blocks[f"QUESTION_{question['number']}"] = {
            "origin": question["origin"],
            "direction": "horizontal",
            "bubblesGap": question["bubble_gap"],
            "bubbleValues": question["options"],
            "fieldLabels": [f"q{question['number']}"],
            "labelsGap": 0,
        }

    return {
        "pageDimensions": [PAGE_WIDTH, PAGE_HEIGHT],
        "bubbleDimensions": [BUBBLE_SIZE, BUBBLE_SIZE],
        "preProcessors": [
            {
                "name": "CropOnMarkers",
                "options": {
                    "relativePath": "omr_marker.jpg",
                    "sheetToMarkerWidthRatio": MARKER_RATIO,
                },
            }
        ],
        "customLabels": {},
        "fieldBlocks": field_blocks,
        "outputColumns": [f"q{i}" for i in range(1, len(layout) + 1)],
        "emptyValue": "",
    }


def create_evaluation(
    questions: list[dict[str, Any]],
    points_per_question: float,
) -> dict[str, Any]:
    points_text = f"{points_per_question:g}"

    return {
        "source_type": "local",
        "options": {
            "questions_in_order": [f"q1..{len(questions)}"],
            "answers_in_order": [question["answer"] for question in questions],
            "marking_schemes": {
                "DEFAULT": {
                    "correct": points_text,
                    "incorrect": "0",
                    "unmarked": "0",
                }
            },
        },
    }


def create_config() -> dict[str, Any]:
    return {
        "dimensions": {
            "display_height": 2480,
            "display_width": 1640,
            "processing_height": 820,
            "processing_width": 666,
        },
        "outputs": {
            "show_image_level": 0,
        },
        "pdf_params": {
            "pdf_page": 1,
            "pdf_dpi": 300,
        },
    }


def make_option_labels(count: int) -> list[str]:
    return [chr(ord("A") + index) for index in range(count)]


def draw_answer_sheet(
    output_path: Path,
    marker_path: Path,
    title: str,
    assessment_id: str,
    layout: list[dict[str, Any]],
    *,
    show_answers: bool = False,
) -> None:
    page_width, page_height = A4

    card_width = CARD_WIDTH_MM * mm
    card_height = CARD_HEIGHT_MM * mm
    card_left = (page_width - card_width) / 2
    card_bottom = (page_height - card_height) / 2

    scale_x = card_width / PAGE_WIDTH
    scale_y = card_height / PAGE_HEIGHT

    def x_pdf(x: float) -> float:
        return card_left + x * scale_x

    def y_pdf(y: float) -> float:
        return card_bottom + card_height - y * scale_y

    canvas = Canvas(str(output_path), pagesize=A4)
    document_kind = "Solução" if show_answers else "Folha de respostas"
    canvas.setTitle(f"{document_kind} - {title}")

    marker_side = card_width / MARKER_RATIO
    marker_centers = [
        (card_left, card_bottom + card_height),
        (card_left + card_width, card_bottom + card_height),
        (card_left, card_bottom),
        (card_left + card_width, card_bottom),
    ]

    for center_x, center_y in marker_centers:
        canvas.drawImage(
            str(marker_path),
            center_x - marker_side / 2,
            center_y - marker_side / 2,
            marker_side,
            marker_side,
            preserveAspectRatio=True,
            mask="auto",
        )

    canvas.setLineWidth(0.5)
    canvas.rect(card_left, card_bottom, card_width, card_height)

    canvas.setFont("Helvetica-Bold", 13)
    canvas.drawCentredString(
        page_width / 2,
        y_pdf(92),
        title[:75],
    )

    if show_answers:
        canvas.setFont("Helvetica-Bold", 9)
        canvas.drawCentredString(
            page_width / 2,
            y_pdf(142),
            "SOLUÇÃO — GABARITO MARCADO",
        )
        canvas.setFont("Helvetica", 7)
        canvas.drawCentredString(
            page_width / 2,
            y_pdf(205),
            "As alternativas preenchidas correspondem às respostas corretas.",
        )
    else:
        canvas.setFont("Helvetica", 8)
        canvas.drawString(x_pdf(110), y_pdf(165), "Nome:")
        canvas.line(x_pdf(190), y_pdf(170), x_pdf(720), y_pdf(170))
        canvas.drawString(x_pdf(760), y_pdf(165), "Matrícula:")
        canvas.line(x_pdf(865), y_pdf(170), x_pdf(1080), y_pdf(170))

        canvas.setFont("Helvetica", 7)
        canvas.drawCentredString(
            page_width / 2,
            y_pdf(220),
            "Preencha completamente apenas uma alternativa em cada questão.",
        )

    bubble_radius_x = (BUBBLE_SIZE / 2 - 3) * scale_x
    bubble_radius_y = (BUBBLE_SIZE / 2 - 3) * scale_y

    # Cabeçalho A–E de cada coluna. As letras ficam fora das regiões
    # de leitura para não interferirem na medição das bolhas.
    columns: dict[int, list[dict[str, Any]]] = {}
    for question in layout:
        columns.setdefault(question["column"], []).append(question)

    for column_questions in columns.values():
        first = min(column_questions, key=lambda item: item["row"])
        max_options = max(item["option_count"] for item in column_questions)
        origin_x, origin_y = first["origin"]

        canvas.setFont("Helvetica-Bold", 6.5)
        for option_index, option in enumerate(make_option_labels(max_options)):
            bubble_x = origin_x + option_index * first["bubble_gap"]
            center_x = x_pdf(bubble_x + BUBBLE_SIZE / 2)
            canvas.drawCentredString(center_x, y_pdf(origin_y - 28), option)

    for question in layout:
        origin_x, origin_y = question["origin"]
        center_y = y_pdf(origin_y + BUBBLE_SIZE / 2)

        canvas.setFont("Helvetica-Bold", 7.5)
        canvas.drawRightString(
            x_pdf(origin_x - 15),
            center_y - 2.5,
            str(question["number"]),
        )

        for option_index, option in enumerate(question["options"]):
            bubble_x = origin_x + option_index * question["bubble_gap"]
            center_x = x_pdf(bubble_x + BUBBLE_SIZE / 2)

            is_correct = show_answers and option == question["answer"]

            canvas.setLineWidth(0.8)
            canvas.setFillColorRGB(0, 0, 0)
            canvas.ellipse(
                center_x - bubble_radius_x,
                center_y - bubble_radius_y,
                center_x + bubble_radius_x,
                center_y + bubble_radius_y,
                stroke=1,
                fill=1 if is_correct else 0,
            )

    canvas.setFont("Helvetica", 5.5)
    canvas.drawString(
        x_pdf(90),
        y_pdf(1515),
        f"ID: {assessment_id}",
    )

    canvas.showPage()
    canvas.save()



FICTIONAL_STUDENTS = [
    {"id": "202600001", "name": "Alice Monteiro"},
    {"id": "202600002", "name": "Bruno Tavares"},
    {"id": "202600003", "name": "Camila Nogueira"},
    {"id": "202600004", "name": "Daniel Martins"},
    {"id": "202600005", "name": "Elisa Rocha"},
    {"id": "202600006", "name": "Fernando Campos"},
    {"id": "202600007", "name": "Gabriela Alves"},
    {"id": "202600008", "name": "Henrique Lima"},
    {"id": "202600009", "name": "Isabela Freitas"},
    {"id": "202600010", "name": "João Pedro Ramos"},
    {"id": "202600011", "name": "Larissa Mendes"},
    {"id": "202600012", "name": "Mateus Ribeiro"},
]


def create_students_file(path: Path) -> None:
    students = [
        {
            **student,
            "status": "pending",
            "result": None,
            "uploaded_file": None,
        }
        for student in FICTIONAL_STUDENTS
    ]
    write_json(path, {"students": students})


def read_json(path: Path) -> Any:
    if not path.exists():
        raise HTTPException(404, f"Arquivo não encontrado: {path.name}")
    return json.loads(path.read_text(encoding="utf-8"))


def safe_student_id(student_id: str) -> str:
    normalized = re.sub(r"[^0-9A-Za-z_-]", "", student_id)
    if not normalized:
        raise HTTPException(400, "Identificador de aluno inválido.")
    return normalized


def locate_assessment(assessment_id: str) -> Path:
    safe_id = re.sub(r"[^0-9A-Za-zÀ-ÿ_-]", "", assessment_id)
    assessment_dir = DATA_DIR / safe_id

    if not assessment_dir.exists() or not assessment_dir.is_dir():
        raise HTTPException(404, "Avaliação não encontrada.")

    return assessment_dir


def get_student_record(students_data: dict[str, Any], student_id: str) -> dict[str, Any]:
    for student in students_data.get("students", []):
        if student.get("id") == student_id:
            return student
    raise HTTPException(404, "Aluno não encontrado nesta avaliação.")


def parse_omr_csv(results_dir: Path) -> dict[str, str]:
    csv_files = sorted(
        results_dir.glob("*.csv"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )

    if not csv_files:
        raise RuntimeError("O OMRChecker não gerou arquivo CSV.")

    for csv_path in csv_files:
        with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))

        if rows:
            row = rows[-1]
            return {
                key: (value or "").strip()
                for key, value in row.items()
                if key and re.fullmatch(r"q\d+", key)
            }

    raise RuntimeError("O CSV gerado não contém respostas.")


def grade_responses(
    detected: dict[str, str],
    answer_key: dict[str, str],
    points_per_question: float,
) -> dict[str, Any]:
    details: list[dict[str, Any]] = []
    correct_count = 0
    blank_count = 0

    ordered_keys = sorted(
        answer_key,
        key=lambda key: int(key.removeprefix("q")),
    )

    for key in ordered_keys:
        selected = detected.get(key, "")
        correct_answer = answer_key[key]
        is_blank = selected == ""
        is_correct = selected == correct_answer

        if is_correct:
            correct_count += 1
        if is_blank:
            blank_count += 1

        details.append(
            {
                "question": int(key.removeprefix("q")),
                "selected": selected,
                "correct_answer": correct_answer,
                "is_correct": is_correct,
                "is_blank": is_blank,
            }
        )

    total = len(ordered_keys)
    error_count = total - correct_count
    score = round(correct_count * points_per_question, 4)
    maximum_score = round(total * points_per_question, 4)
    percentage = round((correct_count / total) * 100, 2) if total else 0.0

    return {
        "correct": correct_count,
        "errors": error_count,
        "blank": blank_count,
        "total": total,
        "score": score,
        "maximum_score": maximum_score,
        "percentage": percentage,
        "details": details,
        "detected_answers": detected,
    }


def process_student_sheet(
    assessment_dir: Path,
    student_id: str,
    source_path: Path,
) -> dict[str, Any]:
    omr_package = assessment_dir / "pacote_omr"
    run_root = assessment_dir / "_processing" / student_id / uuid.uuid4().hex
    input_dir = run_root / "input"
    output_dir = run_root / "output"
    input_dir.mkdir(parents=True)
    output_dir.mkdir(parents=True)

    for filename in ("template.json", "config.json", "omr_marker.jpg"):
        source = omr_package / filename
        if not source.exists():
            raise RuntimeError(f"Pacote OMR incompleto: {filename}.")
        shutil.copy2(source, input_dir / filename)

    processing_file = input_dir / source_path.name
    shutil.copy2(source_path, processing_file)

    main_path = OMR_ROOT / "main.py"
    if not main_path.exists():
        raise RuntimeError(
            "main.py do OMRChecker não foi encontrado. "
            "A pasta avaliacao_web deve ficar dentro da pasta omrchecker."
        )

    command = [
        sys.executable,
        str(main_path),
        "-i",
        str(input_dir),
        "-o",
        str(output_dir),
    ]

    completed = subprocess.run(
        command,
        cwd=OMR_ROOT,
        capture_output=True,
        text=True,
        timeout=180,
    )

    if completed.returncode != 0:
        error_tail = (completed.stderr or completed.stdout or "")[-2500:]
        raise RuntimeError(
            "O OMRChecker não conseguiu processar a folha. "
            f"Detalhes: {error_tail}"
        )

    detected = parse_omr_csv(output_dir / "Results")

    answer_key_data = read_json(assessment_dir / "gabarito.json")
    assessment_data = read_json(assessment_dir / "avaliacao.json")

    graded = grade_responses(
        detected=detected,
        answer_key=answer_key_data["answers"],
        points_per_question=float(assessment_data["points_per_question"]),
    )

    checked_images = list((output_dir / "CheckedOMRs").glob("*"))
    processed_image_relative = None

    if checked_images:
        student_dir = assessment_dir / "alunos" / student_id
        student_dir.mkdir(parents=True, exist_ok=True)
        processed_destination = student_dir / f"processada{checked_images[0].suffix}"
        shutil.copy2(checked_images[0], processed_destination)
        processed_image_relative = str(
            processed_destination.relative_to(assessment_dir)
        )

    graded["processed_image"] = processed_image_relative
    graded["log_excerpt"] = (completed.stdout or "")[-1800:]

    shutil.rmtree(run_root, ignore_errors=True)
    return graded

def write_json(path: Path, data: Any) -> None:
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def create_zip(
    zip_path: Path,
    assessment_dir: Path,
    files: list[Path],
) -> None:
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, path.relative_to(assessment_dir))


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/nova")
async def new_assessment_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "nova.html")


@app.get("/avaliacoes/{assessment_id}")
async def assessment_page(assessment_id: str) -> FileResponse:
    locate_assessment(assessment_id)
    return FileResponse(STATIC_DIR / "avaliacao.html")




@app.get("/api/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/avaliacoes")
async def list_assessments() -> dict[str, Any]:
    assessments: list[dict[str, Any]] = []

    if not DATA_DIR.exists():
        return {
            "assessments": [],
            "summary": {
                "total": 0,
                "total_students": 0,
                "corrected": 0,
                "pending": 0,
            },
        }

    try:
        directory_entries = list(DATA_DIR.iterdir())
    except OSError as exc:
        raise HTTPException(
            500,
            f"Não foi possível acessar a pasta de avaliações: {exc}",
        ) from exc

    for assessment_dir in directory_entries:
        if not assessment_dir.is_dir():
            continue

        assessment_path = assessment_dir / "avaliacao.json"
        if not assessment_path.exists():
            continue

        try:
            assessment = read_json(assessment_path)
        except Exception:
            continue

        students_path = assessment_dir / "alunos.json"

        if not students_path.exists():
            create_students_file(students_path)

        try:
            students_data = read_json(students_path)
        except Exception:
            students_data = {"students": []}

        students = students_data.get("students", [])
        corrected_students = [
            student
            for student in students
            if student.get("status") == "corrected"
            and student.get("result")
        ]

        pending = len(students) - len(corrected_students)
        average_score = 0.0
        average_percentage = 0.0

        if corrected_students:
            average_score = round(
                sum(float(student["result"]["score"]) for student in corrected_students)
                / len(corrected_students),
                2,
            )
            average_percentage = round(
                sum(float(student["result"]["percentage"]) for student in corrected_students)
                / len(corrected_students),
                2,
            )

        assessments.append(
            {
                "id": assessment.get("id", assessment_dir.name),
                "title": assessment.get("title", "Avaliação sem título"),
                "created_at": assessment.get("created_at"),
                "question_count": assessment.get("question_count", 0),
                "points_per_question": assessment.get("points_per_question", 0),
                "maximum_score": assessment.get("maximum_score", 0),
                "students": {
                    "total": len(students),
                    "corrected": len(corrected_students),
                    "pending": pending,
                },
                "average_score": average_score,
                "average_percentage": average_percentage,
                "details_url": f"/avaliacoes/{assessment_dir.name}",
                "downloads": {
                    "answer_sheet": f"/arquivos/{assessment_dir.name}/folha_respostas.pdf",
                    "solution": f"/arquivos/{assessment_dir.name}/solucao_gabarito.pdf",
                },
            }
        )

    assessments.sort(
        key=lambda item: item.get("created_at") or "",
        reverse=True,
    )

    return {
        "assessments": assessments,
        "summary": {
            "total": len(assessments),
            "total_students": sum(item["students"]["total"] for item in assessments),
            "corrected": sum(item["students"]["corrected"] for item in assessments),
            "pending": sum(item["students"]["pending"] for item in assessments),
        },
    }


@app.post("/api/avaliacoes")
async def create_assessment(
    payload: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    title, questions, points = validate_payload(payload)

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    assessment_id = f"{slugify(title)}-{timestamp}-{uuid.uuid4().hex[:6]}"

    assessment_dir = DATA_DIR / assessment_id
    omr_dir = assessment_dir / "pacote_omr"
    assessment_dir.mkdir(parents=True)
    omr_dir.mkdir()

    answer_sheet_path = assessment_dir / "folha_respostas.pdf"
    solution_path = assessment_dir / "solucao_gabarito.pdf"
    assessment_json_path = assessment_dir / "avaliacao.json"
    answer_key_path = assessment_dir / "gabarito.json"
    students_path = assessment_dir / "alunos.json"

    template_path = omr_dir / "template.json"
    evaluation_path = omr_dir / "evaluation.json"
    config_path = omr_dir / "config.json"
    marker_path = omr_dir / "omr_marker.jpg"

    create_marker(marker_path)

    layout = calculate_layout(questions)
    template = create_template(layout)
    evaluation = create_evaluation(questions, points)
    config = create_config()

    assessment_data = {
        "id": assessment_id,
        "title": title,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "question_count": len(questions),
        "points_per_question": points,
        "maximum_score": len(questions) * points,
        "questions": questions,
    }

    answer_key_data = {
        "assessment_id": assessment_id,
        "title": title,
        "answers": {
            f"q{question['number']}": question["answer"]
            for question in questions
        },
    }

    write_json(assessment_json_path, assessment_data)
    write_json(answer_key_path, answer_key_data)
    write_json(template_path, template)
    write_json(evaluation_path, evaluation)
    write_json(config_path, config)
    create_students_file(students_path)

    draw_answer_sheet(
        answer_sheet_path,
        marker_path,
        title,
        assessment_id,
        layout,
    )

    draw_answer_sheet(
        solution_path,
        marker_path,
        title,
        assessment_id,
        layout,
        show_answers=True,
    )

    zip_path = assessment_dir / "pacote_completo.zip"

    zip_files = [
        answer_sheet_path,
        solution_path,
        assessment_json_path,
        answer_key_path,
        students_path,
        template_path,
        evaluation_path,
        config_path,
        marker_path,
    ]
    create_zip(zip_path, assessment_dir, zip_files)

    base_url = f"/arquivos/{assessment_id}"

    return {
        "id": assessment_id,
        "message": "Avaliação criada corretamente.",
        "details_url": f"/avaliacoes/{assessment_id}",
        "downloads": {
            "answer_sheet": f"{base_url}/folha_respostas.pdf",
            "solution": f"{base_url}/solucao_gabarito.pdf",
            "answer_key": f"{base_url}/gabarito.json",
            "assessment": f"{base_url}/avaliacao.json",
            "template": f"{base_url}/pacote_omr/template.json",
            "evaluation": f"{base_url}/pacote_omr/evaluation.json",
            "config": f"{base_url}/pacote_omr/config.json",
            "marker": f"{base_url}/pacote_omr/omr_marker.jpg",
            "zip": f"{base_url}/pacote_completo.zip",
        },
    }


@app.get("/api/avaliacoes/{assessment_id}")
async def get_assessment(assessment_id: str) -> dict[str, Any]:
    assessment_dir = locate_assessment(assessment_id)
    assessment = read_json(assessment_dir / "avaliacao.json")
    answer_key = read_json(assessment_dir / "gabarito.json")

    students_path = assessment_dir / "alunos.json"

    # Migração automática para avaliações criadas em versões anteriores.
    if not students_path.exists():
        create_students_file(students_path)

    try:
        students_data = read_json(students_path)
    except Exception:
        create_students_file(students_path)
        students_data = read_json(students_path)

    students = students_data.get("students", [])

    if not isinstance(students, list):
        create_students_file(students_path)
        students_data = read_json(students_path)
        students = students_data.get("students", [])

    normalized_students: list[dict[str, Any]] = []

    for student in students:
        if not isinstance(student, dict):
            continue

        normalized = {
            "id": str(student.get("id", "")),
            "name": str(student.get("name", "Aluno")),
            "status": student.get("status", "pending"),
            "result": student.get("result"),
            "uploaded_file": student.get("uploaded_file"),
        }

        if (
            normalized["status"] == "corrected"
            and not isinstance(normalized["result"], dict)
        ):
            normalized["status"] = "pending"
            normalized["result"] = None

        normalized_students.append(normalized)

    students = normalized_students
    students_data["students"] = students
    write_json(students_path, students_data)

    corrected = [
        student
        for student in students
        if student.get("status") == "corrected"
        and isinstance(student.get("result"), dict)
    ]
    pending = len(students) - len(corrected)

    valid_scores: list[float] = []

    for student in corrected:
        try:
            valid_scores.append(float(student["result"].get("score", 0)))
        except (TypeError, ValueError, AttributeError):
            continue

    average = round(sum(valid_scores) / len(valid_scores), 2) if valid_scores else 0.0

    return {
        "assessment": assessment,
        "answer_key": answer_key,
        "students": students,
        "summary": {
            "total_students": len(students),
            "corrected": len(corrected),
            "pending": pending,
            "average_score": average,
        },
        "downloads": {
            "answer_sheet": f"/arquivos/{assessment_id}/folha_respostas.pdf",
            "solution": f"/arquivos/{assessment_id}/solucao_gabarito.pdf",
            "zip": f"/arquivos/{assessment_id}/pacote_completo.zip",
        },
    }


@app.post("/api/avaliacoes/{assessment_id}/alunos/{student_id}/upload")
async def upload_student_sheet(
    assessment_id: str,
    student_id: str,
    file: UploadFile = File(...),
) -> dict[str, Any]:
    assessment_dir = locate_assessment(assessment_id)
    safe_id = safe_student_id(student_id)

    allowed_extensions = {".pdf", ".png", ".jpg", ".jpeg"}
    original_name = Path(file.filename or "folha.pdf").name
    extension = Path(original_name).suffix.lower()

    if extension not in allowed_extensions:
        raise HTTPException(
            400,
            "Envie uma folha em PDF, PNG, JPG ou JPEG.",
        )

    students_path = assessment_dir / "alunos.json"
    students_data = read_json(students_path)
    student = get_student_record(students_data, safe_id)

    content = await file.read()

    if not content:
        raise HTTPException(400, "O arquivo enviado está vazio.")

    if len(content) > 35 * 1024 * 1024:
        raise HTTPException(400, "O arquivo deve ter no máximo 35 MB.")

    student_dir = assessment_dir / "alunos" / safe_id
    student_dir.mkdir(parents=True, exist_ok=True)

    stored_path = student_dir / f"folha_original{extension}"
    stored_path.write_bytes(content)

    try:
        result = process_student_sheet(
            assessment_dir=assessment_dir,
            student_id=safe_id,
            source_path=stored_path,
        )
    except subprocess.TimeoutExpired as exc:
        raise HTTPException(
            504,
            "O processamento demorou mais que o limite permitido.",
        ) from exc
    except Exception as exc:
        raise HTTPException(422, str(exc)) from exc

    result_path = student_dir / "resultado.json"
    write_json(result_path, result)

    student["status"] = "corrected"
    student["uploaded_file"] = str(stored_path.relative_to(assessment_dir))
    student["result"] = result
    write_json(students_path, students_data)

    return {
        "message": f"Folha de {student['name']} corrigida.",
        "student": student,
    }
