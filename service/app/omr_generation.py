from __future__ import annotations

import io
import math
from typing import Any

import qrcode
from PIL import Image, ImageDraw
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen.canvas import Canvas

from .schemas import Questao

# Layout constants, ported unchanged from avaliacao_web/app.py so that sheets
# generated here stay compatible with the alignment/OCR logic in
# omr_correction.py (which assumes this exact geometry).
PAGE_WIDTH = 1200
PAGE_HEIGHT = 1600
CARD_WIDTH_MM = 150
CARD_HEIGHT_MM = 200
BUBBLE_SIZE = 34
MARKER_RATIO = 17
STUDENT_ID_DIGITS = 10
STUDENT_ID_ORIGIN = [250, 232]
STUDENT_ID_BLOCK_WIDTH = 70
STUDENT_ID_BLOCK_HEIGHT = 62
STUDENT_ID_BLOCK_GAP = 14
BATCH_QUESTION_TOP = 390
PLAIN_QUESTION_TOP = 285

# Canto inferior direito, sempre livre: calculate_layout() nunca posiciona
# bolhas abaixo de y=1420, e o rodapé "ID: ..." fica à esquerda (x=90). Usado
# tanto pra desenhar o QR na folha quanto (por omr_correction.py) pra saber
# onde recortar e decodificar o QR na folha escaneada.
QR_REGION = {"x": 960, "y": 1435, "size": 140}


def make_option_labels(count: int) -> list[str]:
    return [chr(ord("A") + index) for index in range(count)]


def create_qr_image(payload: str) -> Image.Image:
    qr = qrcode.QRCode(border=1)
    qr.add_data(payload)
    qr.make(fit=True)
    return qr.make_image(fill_color="black", back_color="white").get_image()


def create_marker_image() -> Image.Image:
    size = 160
    image = Image.new("RGB", (size, size), "white")
    draw = ImageDraw.Draw(image)

    draw.ellipse((10, 10, size - 10, size - 10), fill="black")
    draw.ellipse((37, 37, size - 37, size - 37), fill="white")
    draw.ellipse((65, 65, size - 65, size - 65), fill="black")

    return image


def calculate_layout(
    questoes: list[Questao],
    *,
    top: int,
) -> list[dict[str, Any]]:
    total = len(questoes)

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
    bottom = 1420
    available_height = bottom - top

    row_gap = 0 if rows_per_column == 1 else available_height / (rows_per_column - 1)
    row_gap = min(48, row_gap)

    column_width = (right - left) / columns
    max_options = max(questao.option_count for questao in questoes)

    option_area = column_width - 105
    bubble_gap = (
        0
        if max_options == 1
        else min(52, (option_area - BUBBLE_SIZE) / max(1, max_options - 1))
    )
    bubble_gap = max(38, bubble_gap)

    result: list[dict[str, Any]] = []

    for zero_index, questao in enumerate(questoes):
        column = zero_index // rows_per_column
        row = zero_index % rows_per_column

        column_left = left + column * column_width
        origin_x = column_left + 62
        origin_y = top + row * row_gap

        result.append(
            {
                "numero": questao.numero,
                "option_count": questao.option_count,
                "options": make_option_labels(questao.option_count),
                "resposta": questao.resposta,
                "peso": questao.peso,
                "column": column,
                "row": row,
                "origin": [round(origin_x), round(origin_y)],
                "bubble_gap": round(bubble_gap, 2),
            }
        )

    return result


def create_template(layout: list[dict[str, Any]]) -> dict[str, Any]:
    field_blocks: dict[str, Any] = {}

    for questao in layout:
        field_blocks[f"QUESTION_{questao['numero']}"] = {
            "origin": questao["origin"],
            "direction": "horizontal",
            "bubblesGap": questao["bubble_gap"],
            "bubbleValues": questao["options"],
            "fieldLabels": [f"q{questao['numero']}"],
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


def draw_answer_sheet(
    marker_image: Image.Image,
    title: str,
    identificador: str,
    layout: list[dict[str, Any]],
    *,
    show_answers: bool = False,
    student_id_digits: int = 0,
    qr_image: Image.Image | None = None,
    aluno_nome: str = "",
    aluno_matricula: str = "",
    turma_nome: str = "",
) -> bytes:
    # Folha personalizada (tem QR): já sabemos de quem é, então nome/turma/
    # matrícula vêm impressos em vez de deixar em branco pra escrever à mão —
    # o QR é a identificação primária, e a matrícula impressa (não mais
    # manuscrita) vira um fallback bem mais confiável pro OCR do que
    # caligrafia, sem exigir nada do aluno. Sem caixas de matrícula aqui — o
    # valor já vem impresso como texto no cabeçalho (ver campos abaixo), então
    # o fallback de identificação por matrícula não se aplica a essa folha
    # (só o QR); a folha genérica (sem QR) continua com as caixas de sempre.
    personalizada = qr_image is not None
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

    buffer = io.BytesIO()
    canvas = Canvas(buffer, pagesize=A4)
    if show_answers:
        document_kind = "Solução"
    elif student_id_digits:
        document_kind = "Folha de respostas com matrícula em blocos"
    else:
        document_kind = "Folha de respostas"
    canvas.setTitle(f"{document_kind} - {title}")

    marker_reader = ImageReader(marker_image)
    marker_side = card_width / MARKER_RATIO
    marker_centers = [
        (card_left, card_bottom + card_height),
        (card_left + card_width, card_bottom + card_height),
        (card_left, card_bottom),
        (card_left + card_width, card_bottom),
    ]

    for center_x, center_y in marker_centers:
        canvas.drawImage(
            marker_reader,
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
    canvas.drawCentredString(page_width / 2, y_pdf(92), title[:75])

    if show_answers:
        canvas.setFont("Helvetica-Bold", 9)
        canvas.drawCentredString(
            page_width / 2, y_pdf(142), "SOLUÇÃO - GABARITO MARCADO"
        )
        canvas.setFont("Helvetica", 7)
        canvas.drawCentredString(
            page_width / 2,
            y_pdf(205),
            "As alternativas preenchidas correspondem às respostas corretas.",
        )
    elif personalizada:
        # Folha personalizada: já sabemos de quem é (QR + matrícula impressa
        # cobrem a identificação), então nada fica em branco pra escrever —
        # rótulos em negrito, valores na mesma fonte/tamanho sem negrito.
        rotulo_fonte = "Helvetica-Bold"
        valor_fonte = "Helvetica"
        tamanho_fonte = 9
        origem_y = 145
        espaco_linha = 34  # ~1.3x o tamanho da fonte, em pontos reais de PDF

        campos = [
            ("Nome", aluno_nome),
            ("Turma", turma_nome),
            ("Matrícula", aluno_matricula),
        ]

        for indice, (rotulo, valor) in enumerate(campos):
            linha_y = origem_y + indice * espaco_linha
            rotulo_texto = f"{rotulo}: "

            canvas.setFont(rotulo_fonte, tamanho_fonte)
            canvas.drawString(x_pdf(110), y_pdf(linha_y), rotulo_texto)
            rotulo_largura = canvas.stringWidth(
                rotulo_texto, rotulo_fonte, tamanho_fonte
            )

            canvas.setFont(valor_fonte, tamanho_fonte)
            canvas.drawString(
                x_pdf(110) + rotulo_largura, y_pdf(linha_y), valor or "—"
            )

        canvas.setFont("Helvetica", 7)
        canvas.drawString(
            x_pdf(110),
            y_pdf(origem_y + len(campos) * espaco_linha + 12),
            "Preencha completamente apenas uma alternativa em cada questão.",
        )
    elif student_id_digits:
        canvas.setFont("Helvetica", 8)
        canvas.drawString(x_pdf(110), y_pdf(145), "Nome:")
        canvas.line(x_pdf(190), y_pdf(150), x_pdf(1080), y_pdf(150))

        canvas.setFont("Helvetica-Bold", 8)
        canvas.drawString(x_pdf(110), y_pdf(210), "Matrícula:")
        canvas.setFont("Helvetica", 7)
        canvas.drawString(
            x_pdf(245), y_pdf(210), "escreva um algarismo em cada bloco"
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

    if student_id_digits and not show_answers and not personalizada:
        block_width = STUDENT_ID_BLOCK_WIDTH
        block_height = STUDENT_ID_BLOCK_HEIGHT
        block_gap = STUDENT_ID_BLOCK_GAP
        origin_x, origin_y = STUDENT_ID_ORIGIN

        for column in range(student_id_digits):
            block_x = origin_x + column * (block_width + block_gap)
            left_x = x_pdf(block_x)
            bottom_y = y_pdf(origin_y + block_height)
            width = block_width * scale_x
            height = block_height * scale_y

            canvas.setLineWidth(0.9)
            canvas.roundRect(
                left_x, bottom_y, width, height, 3, stroke=1, fill=0
            )

        canvas.setFont("Helvetica", 6.5)
        canvas.drawCentredString(
            page_width / 2,
            y_pdf(325),
            "Escreva os algarismos grandes, centralizados e sem encostar nas bordas.",
        )

    columns: dict[int, list[dict[str, Any]]] = {}
    for questao in layout:
        columns.setdefault(questao["column"], []).append(questao)

    for column_questions in columns.values():
        first = min(column_questions, key=lambda item: item["row"])
        max_options = max(item["option_count"] for item in column_questions)
        origin_x, origin_y = first["origin"]

        canvas.setFont("Helvetica-Bold", 6.5)
        for option_index, option in enumerate(make_option_labels(max_options)):
            bubble_x = origin_x + option_index * first["bubble_gap"]
            center_x = x_pdf(bubble_x + BUBBLE_SIZE / 2)
            canvas.drawCentredString(center_x, y_pdf(origin_y - 28), option)

    for questao in layout:
        origin_x, origin_y = questao["origin"]
        center_y = y_pdf(origin_y + BUBBLE_SIZE / 2)

        canvas.setFont("Helvetica-Bold", 7.5)
        canvas.drawRightString(
            x_pdf(origin_x - 15), center_y - 2.5, str(questao["numero"])
        )

        for option_index, option in enumerate(questao["options"]):
            bubble_x = origin_x + option_index * questao["bubble_gap"]
            center_x = x_pdf(bubble_x + BUBBLE_SIZE / 2)

            is_correct = show_answers and option == questao["resposta"]

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
    canvas.drawString(x_pdf(90), y_pdf(1515), f"ID: {identificador}")

    if qr_image is not None:
        qr_reader = ImageReader(qr_image)
        qr_x = x_pdf(QR_REGION["x"])
        qr_size_x = QR_REGION["size"] * scale_x
        qr_size_y = QR_REGION["size"] * scale_y
        qr_bottom_y = y_pdf(QR_REGION["y"] + QR_REGION["size"])
        canvas.drawImage(
            qr_reader,
            qr_x,
            qr_bottom_y,
            qr_size_x,
            qr_size_y,
        )

    canvas.showPage()
    canvas.save()
    return buffer.getvalue()


def image_to_bytes(image: Image.Image, *, fmt: str = "JPEG") -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format=fmt, quality=100)
    return buffer.getvalue()


def merge_pdfs(pdfs: list[bytes]) -> bytes:
    """Combine several single-page PDFs into one multi-page PDF, in order."""
    import fitz

    combinado = fitz.open()
    try:
        for conteudo in pdfs:
            pagina = fitz.open(stream=conteudo, filetype="pdf")
            try:
                combinado.insert_pdf(pagina)
            finally:
                pagina.close()
        return combinado.tobytes()
    finally:
        combinado.close()
