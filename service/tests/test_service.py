from __future__ import annotations

import base64
import io

import fitz
from fastapi.testclient import TestClient

from main import app

client = TestClient(app)

QUESTOES = [
    {"numero": 1, "option_count": 4, "resposta": "B", "peso": 1.0},
    {"numero": 2, "option_count": 4, "resposta": "A", "peso": 1.0},
    {"numero": 3, "option_count": 5, "resposta": "C", "peso": 1.0},
    {"numero": 4, "option_count": 4, "resposta": "D", "peso": 1.0},
    {"numero": 5, "option_count": 4, "resposta": "A", "peso": 1.0},
]


def _pdf_to_png_bytes(pdf_bytes: bytes) -> bytes:
    document = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        page = document.load_page(0)
        pixmap = page.get_pixmap(matrix=fitz.Matrix(3, 3), alpha=False)
        return pixmap.tobytes("png")
    finally:
        document.close()


def _gerar_gabarito(matricula_em_blocos: bool = True) -> dict:
    response = client.post(
        "/v1/gabarito/gerar",
        json={
            "titulo": "Simulado de Teste",
            "identificador": "teste-001",
            "matricula_em_blocos": matricula_em_blocos,
            "questoes": QUESTOES,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_gerar_gabarito_retorna_arquivos_e_gabarito():
    data = _gerar_gabarito()

    assert data["gabarito"] == {"q1": "B", "q2": "A", "q3": "C", "q4": "D", "q5": "A"}
    assert data["pesos"] == {"q1": 1.0, "q2": 1.0, "q3": 1.0, "q4": 1.0, "q5": 1.0}
    assert data["arquivos"]["template_json"]["pageDimensions"] == [1200, 1600]
    assert len(data["arquivos"]["marcador_base64"]) > 0
    assert len(data["arquivos"]["folha_respostas_base64"]) > 0
    assert len(data["arquivos"]["folha_solucao_base64"]) > 0


def test_gerar_com_alunos_produz_uma_folha_personalizada_por_aluno():
    response = client.post(
        "/v1/gabarito/gerar",
        json={
            "titulo": "Simulado de Teste",
            "identificador": "simulado-qr-teste",
            "matricula_em_blocos": True,
            "questoes": QUESTOES,
            "alunos": [
                {"aluno_id": "aluno-1", "nome": "Fulano", "matricula": "1"},
                {"aluno_id": "aluno-2", "nome": "Ciclana", "matricula": "2"},
            ],
        },
    )
    assert response.status_code == 200, response.text
    data = response.json()

    assert [f["aluno_id"] for f in data["folhas_alunos"]] == ["aluno-1", "aluno-2"]
    for folha in data["folhas_alunos"]:
        assert len(folha["folha_base64"]) > 0

    assert data["folha_completa_base64"]
    combinado = fitz.open(
        stream=base64.b64decode(data["folha_completa_base64"]), filetype="pdf"
    )
    try:
        assert combinado.page_count == len(data["folhas_alunos"])
    finally:
        combinado.close()


def test_gerar_sem_alunos_nao_gera_folha_completa():
    data = _gerar_gabarito()
    assert data["folhas_alunos"] == []
    assert data["folha_completa_base64"] is None


def test_corrigir_folha_personalizada_identifica_aluno_pelo_qr():
    response = client.post(
        "/v1/gabarito/gerar",
        json={
            "titulo": "Simulado de Teste",
            "identificador": "simulado-qr-teste",
            "matricula_em_blocos": True,
            "questoes": QUESTOES,
            "alunos": [{"aluno_id": "aluno-qr-1", "nome": "Fulano", "matricula": "1"}],
        },
    )
    assert response.status_code == 200, response.text
    gerado = response.json()
    arquivos = gerado["arquivos"]
    folha_aluno_base64 = gerado["folhas_alunos"][0]["folha_base64"]

    folha_png = _pdf_to_png_bytes(base64.b64decode(folha_aluno_base64))
    marker_bytes = base64.b64decode(arquivos["marcador_base64"])

    correcao = client.post(
        "/v1/folha/corrigir",
        files={
            "sheet": ("folha.png", io.BytesIO(folha_png), "image/png"),
            "template": (
                "template.json",
                io.BytesIO(
                    __import__("json").dumps(arquivos["template_json"]).encode()
                ),
                "application/json",
            ),
            "config": (
                "config.json",
                io.BytesIO(
                    __import__("json").dumps(arquivos["config_json"]).encode()
                ),
                "application/json",
            ),
            "marker": ("marker.jpg", io.BytesIO(marker_bytes), "image/jpeg"),
        },
        data={"matricula_em_blocos": "true"},
    )

    assert correcao.status_code == 200, correcao.text
    data = correcao.json()
    assert data["qr"] == {
        "simulado_id": "simulado-qr-teste",
        "aluno_id": "aluno-qr-1",
    }


def test_corrigir_folha_generica_sem_qr_nao_quebra():
    gerado = _gerar_gabarito(matricula_em_blocos=True)
    arquivos = gerado["arquivos"]

    folha_png = _pdf_to_png_bytes(
        base64.b64decode(arquivos["folha_respostas_base64"])
    )
    marker_bytes = base64.b64decode(arquivos["marcador_base64"])

    correcao = client.post(
        "/v1/folha/corrigir",
        files={
            "sheet": ("folha.png", io.BytesIO(folha_png), "image/png"),
            "template": (
                "template.json",
                io.BytesIO(
                    __import__("json").dumps(arquivos["template_json"]).encode()
                ),
                "application/json",
            ),
            "config": (
                "config.json",
                io.BytesIO(
                    __import__("json").dumps(arquivos["config_json"]).encode()
                ),
                "application/json",
            ),
            "marker": ("marker.jpg", io.BytesIO(marker_bytes), "image/jpeg"),
        },
        data={"matricula_em_blocos": "true"},
    )

    assert correcao.status_code == 200, correcao.text
    assert correcao.json()["qr"] is None


def test_corrigir_folha_solucao_da_nota_maxima():
    gerado = _gerar_gabarito(matricula_em_blocos=False)
    arquivos = gerado["arquivos"]

    solucao_png = _pdf_to_png_bytes(base64.b64decode(arquivos["folha_solucao_base64"]))
    marker_bytes = base64.b64decode(arquivos["marcador_base64"])

    response = client.post(
        "/v1/folha/corrigir",
        files={
            "sheet": ("solucao.png", io.BytesIO(solucao_png), "image/png"),
            "template": (
                "template.json",
                io.BytesIO(
                    __import__("json").dumps(arquivos["template_json"]).encode()
                ),
                "application/json",
            ),
            "config": (
                "config.json",
                io.BytesIO(
                    __import__("json").dumps(arquivos["config_json"]).encode()
                ),
                "application/json",
            ),
            "marker": ("marker.jpg", io.BytesIO(marker_bytes), "image/jpeg"),
        },
        data={
            "matricula_em_blocos": "false",
            "gabarito_json": __import__("json").dumps(
                {"questoes": QUESTOES, "valor_maximo": 10}
            ),
        },
    )

    assert response.status_code == 200, response.text
    data = response.json()

    assert data["respostas_detectadas"] == gerado["gabarito"]
    assert data["nota"]["acertos"] == 5
    assert data["nota"]["erros"] == 0
    assert data["nota"]["nota"] == 10.0
    assert data["nota"]["percentual"] == 100.0
    assert data["imagem_processada_base64"]


def test_corrigir_folha_em_branco_detecta_tudo_vazio_e_sem_matricula():
    gerado = _gerar_gabarito(matricula_em_blocos=True)
    arquivos = gerado["arquivos"]

    folha_png = _pdf_to_png_bytes(
        base64.b64decode(arquivos["folha_respostas_base64"])
    )
    marker_bytes = base64.b64decode(arquivos["marcador_base64"])

    response = client.post(
        "/v1/folha/corrigir",
        files={
            "sheet": ("folha.png", io.BytesIO(folha_png), "image/png"),
            "template": (
                "template.json",
                io.BytesIO(
                    __import__("json").dumps(arquivos["template_json"]).encode()
                ),
                "application/json",
            ),
            "config": (
                "config.json",
                io.BytesIO(
                    __import__("json").dumps(arquivos["config_json"]).encode()
                ),
                "application/json",
            ),
            "marker": ("marker.jpg", io.BytesIO(marker_bytes), "image/jpeg"),
        },
        data={"matricula_em_blocos": "true"},
    )

    assert response.status_code == 200, response.text
    data = response.json()

    assert all(value == "" for value in data["respostas_detectadas"].values())
    assert data["matricula"]["valor"] == ""
    assert data["nota"] is None


def test_dividir_folha_imagem_retorna_uma_pagina():
    gerado = _gerar_gabarito(matricula_em_blocos=False)
    png_bytes = _pdf_to_png_bytes(
        base64.b64decode(gerado["arquivos"]["folha_respostas_base64"])
    )

    response = client.post(
        "/v1/folha/dividir",
        files={"arquivo": ("folha.png", io.BytesIO(png_bytes), "image/png")},
    )

    assert response.status_code == 200, response.text
    paginas = response.json()["paginas"]
    assert len(paginas) == 1
    assert paginas[0]["nome"] == "folha.png"


def test_dividir_folha_pdf_multipagina_retorna_uma_pagina_por_folha():
    gerado = _gerar_gabarito(matricula_em_blocos=False)
    pdf_bytes = base64.b64decode(gerado["arquivos"]["folha_respostas_base64"])

    import fitz

    combinado = fitz.open()
    for _ in range(3):
        origem = fitz.open(stream=pdf_bytes, filetype="pdf")
        combinado.insert_pdf(origem)
        origem.close()
    combinado_bytes = combinado.tobytes()
    combinado.close()

    response = client.post(
        "/v1/folha/dividir",
        files={
            "arquivo": (
                "lote.pdf",
                io.BytesIO(combinado_bytes),
                "application/pdf",
            )
        },
    )

    assert response.status_code == 200, response.text
    paginas = response.json()["paginas"]
    assert len(paginas) == 3
    assert paginas[0]["nome"] == "lote-pagina-001.png"
    assert paginas[2]["nome"] == "lote-pagina-003.png"


def test_token_invalido_e_rejeitado(monkeypatch):
    import app.config as config_module

    monkeypatch.setattr(config_module, "SERVICE_TOKEN", "segredo-teste")
    monkeypatch.setattr("app.auth.SERVICE_TOKEN", "segredo-teste")

    response = client.post(
        "/v1/gabarito/gerar",
        json={"titulo": "x", "questoes": [QUESTOES[0]]},
    )
    assert response.status_code == 401

    response = client.post(
        "/v1/gabarito/gerar",
        json={"titulo": "x", "questoes": [QUESTOES[0]]},
        headers={"Authorization": "Bearer segredo-teste"},
    )
    assert response.status_code == 200
