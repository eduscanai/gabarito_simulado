from __future__ import annotations

import json
import re
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen.canvas import Canvas


ROOT = Path(__file__).resolve().parent.parent

TEMPLATE_PATH = (
    ROOT
    / "inputs"
    / "prova_teste_01"
    / "template.json"
)

OUTPUT_PATH = (
    ROOT
    / "formularios"
    / "prova_teste_01"
    / "cartao_resposta_5q.pdf"
)

CARD_WIDTH_MM = 150
CARD_HEIGHT_MM = 200


def expandir_rotulos(rotulos: list[str]) -> list[str]:
    resultado: list[str] = []

    for rotulo in rotulos:
        correspondencia = re.fullmatch(
            r"([A-Za-z_]+)(\d+)\.\.(\d+)",
            rotulo,
        )

        if correspondencia is None:
            resultado.append(rotulo)
            continue

        prefixo = correspondencia.group(1)
        inicio = int(correspondencia.group(2))
        fim = int(correspondencia.group(3))

        for numero in range(inicio, fim + 1):
            resultado.append(f"{prefixo}{numero}")

    return resultado


def obter_alternativas(tipo_campo: str) -> list[str]:
    correspondencia = re.fullmatch(
        r"QTYPE_MCQ(\d+)",
        tipo_campo,
    )

    if correspondencia is None:
        raise ValueError(
            f"Tipo de campo não reconhecido: {tipo_campo}"
        )

    quantidade = int(correspondencia.group(1))

    return [
        chr(ord("A") + indice)
        for indice in range(quantidade)
    ]


def obter_dimensoes(template: dict) -> tuple[float, float]:
    dimensoes = (
        template.get("templateDimensions")
        or template.get("pageDimensions")
    )

    if dimensoes is None:
        raise KeyError(
            "O template não contém templateDimensions "
            "nem pageDimensions."
        )

    return float(dimensoes[0]), float(dimensoes[1])


def main() -> None:
    if not TEMPLATE_PATH.exists():
        raise FileNotFoundError(
            f"Template não encontrado: {TEMPLATE_PATH}"
        )

    template = json.loads(
        TEMPLATE_PATH.read_text(encoding="utf-8")
    )

    largura_template, altura_template = obter_dimensoes(
        template
    )

    largura_bolha, altura_bolha = template[
        "bubbleDimensions"
    ]

    blocos = template.get("fieldBlocks", {})

    if not blocos:
        raise ValueError(
            "O template não possui fieldBlocks."
        )

    _nome_bloco, bloco = next(iter(blocos.items()))

    origem_x, origem_y = bloco["origin"]
    espaco_questoes = bloco["labelsGap"]
    espaco_alternativas = bloco["bubblesGap"]

    questoes = expandir_rotulos(
        bloco["fieldLabels"]
    )

    alternativas = obter_alternativas(
        bloco["fieldType"]
    )

    OUTPUT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    pagina_largura, pagina_altura = A4

    cartao_largura = CARD_WIDTH_MM * mm
    cartao_altura = CARD_HEIGHT_MM * mm

    cartao_esquerda = (
        pagina_largura - cartao_largura
    ) / 2

    cartao_inferior = (
        pagina_altura - cartao_altura
    ) / 2

    escala_x = cartao_largura / largura_template
    escala_y = cartao_altura / altura_template

    def converter_x(x: float) -> float:
        return cartao_esquerda + x * escala_x

    def converter_y(y: float) -> float:
        return (
            cartao_inferior
            + cartao_altura
            - y * escala_y
        )

    canvas = Canvas(
        str(OUTPUT_PATH),
        pagesize=A4,
    )

    canvas.setTitle(
        "Cartão-resposta de cinco questões"
    )

    # Moldura externa utilizada como referência pelo CropPage.
    canvas.setLineWidth(1.5)

    canvas.rect(
        cartao_esquerda,
        cartao_inferior,
        cartao_largura,
        cartao_altura,
        stroke=1,
        fill=0,
    )

    # Cabeçalho.
    canvas.setFont("Helvetica-Bold", 14)

    canvas.drawCentredString(
        pagina_largura / 2,
        converter_y(20),
        "CARTÃO-RESPOSTA",
    )

    canvas.setFont("Helvetica", 8)

    canvas.drawCentredString(
        pagina_largura / 2,
        converter_y(36),
        "Preencha completamente apenas uma alternativa.",
    )

    # Letras A, B, C, D e E.
    canvas.setFont("Helvetica-Bold", 10)

    for indice, alternativa in enumerate(
        alternativas
    ):
        centro_x_template = (
            origem_x
            + indice * espaco_alternativas
            + largura_bolha / 2
        )

        canvas.drawCentredString(
            converter_x(centro_x_template),
            converter_y(origem_y - 6),
            alternativa,
        )

    # Questões e bolhas.
    for indice_questao, _questao in enumerate(
        questoes
    ):
        y_template = (
            origem_y
            + indice_questao * espaco_questoes
        )

        centro_y_template = (
            y_template + altura_bolha / 2
        )

        centro_y_pdf = converter_y(
            centro_y_template
        )

        canvas.setFont("Helvetica-Bold", 10)

        canvas.drawRightString(
            converter_x(origem_x - 9),
            centro_y_pdf - 3,
            str(indice_questao + 1),
        )

        for indice_alternativa, _alternativa in enumerate(
            alternativas
        ):
            x_template = (
                origem_x
                + indice_alternativa
                * espaco_alternativas
            )

            centro_x_template = (
                x_template + largura_bolha / 2
            )

            centro_x_pdf = converter_x(
                centro_x_template
            )

            raio_x = (
                largura_bolha
                * escala_x
                / 2
                - 1.5 * mm
            )

            raio_y = (
                altura_bolha
                * escala_y
                / 2
                - 1.5 * mm
            )

            canvas.setLineWidth(1.2)

            canvas.ellipse(
                centro_x_pdf - raio_x,
                centro_y_pdf - raio_y,
                centro_x_pdf + raio_x,
                centro_y_pdf + raio_y,
                stroke=1,
                fill=0,
            )

    canvas.setFont("Helvetica", 7)

    canvas.drawString(
        cartao_esquerda + 5 * mm,
        cartao_inferior + 5 * mm,
        "Prova teste 01",
    )

    canvas.showPage()
    canvas.save()

    print("PDF criado corretamente.")
    print(f"Arquivo: {OUTPUT_PATH}")
    print(f"Quantidade de questões: {len(questoes)}")
    print(f"Alternativas: {alternativas}")


if __name__ == "__main__":
    main()