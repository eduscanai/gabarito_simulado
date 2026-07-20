from __future__ import annotations

import csv
import io
import logging
import json
import math
import re
import shutil
import subprocess
import sys
import unicodedata
import uuid
import zipfile
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import Body, FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image, ImageDraw
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen.canvas import Canvas

from .config import ASSESSMENTS_DIR, OMR_ROOT, STATIC_DIR
from .database import database_status, initialize_database
from .repository import (
    database_counts,
    find_student_profile,
    sync_all_assessments,
    sync_assessment_directory,
)


DATA_DIR = ASSESSMENTS_DIR
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(application: FastAPI):
    del application
    initialize_database()

    migration = sync_all_assessments(DATA_DIR)

    if migration.get("errors"):
        logger.warning(
            "Algumas avaliações não foram importadas: %s",
            migration["errors"],
        )

    yield


app = FastAPI(
    title="Criador de avaliações OMR",
    lifespan=lifespan,
)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount("/arquivos", StaticFiles(directory=DATA_DIR), name="arquivos")


PAGE_WIDTH = 1200
PAGE_HEIGHT = 1600
CARD_WIDTH_MM = 150
CARD_HEIGHT_MM = 200
BUBBLE_SIZE = 34
MARKER_RATIO = 17
STUDENT_ID_DIGITS = 10
STUDENT_ID_ORIGIN = [352, 220]
STUDENT_ID_BUBBLE_GAP = 34
STUDENT_ID_LABEL_GAP = 46
BATCH_QUESTION_TOP = 390
BATCH_TEMPLATE_VERSION = 4


def slugify(value: str) -> str:
    value = unicodedata.normalize("NFKD", value)
    value = value.encode("ascii", "ignore").decode("ascii")
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9\s-]", "", value)
    value = re.sub(r"[-\s]+", "-", value)
    return value.strip("-") or "avaliacao"


def validate_payload(
    payload: dict[str, Any],
) -> tuple[str, list[dict[str, Any]], float]:
    title = str(payload.get("title", "")).strip()
    questions = payload.get("questions")

    # Compatibilidade com versões antigas.
    raw_total_score = payload.get("total_score")

    if raw_total_score is None:
        legacy_points = payload.get("points_per_question", 1)
        try:
            raw_total_score = float(legacy_points) * len(questions or [])
        except (TypeError, ValueError):
            raw_total_score = 10

    if not title:
        raise HTTPException(400, "Informe o título da avaliação.")

    if not isinstance(questions, list) or not 1 <= len(questions) <= 100:
        raise HTTPException(400, "A avaliação deve ter entre 1 e 100 questões.")

    try:
        total_score = float(raw_total_score)
    except (TypeError, ValueError) as exc:
        raise HTTPException(400, "O valor total da prova é inválido.") from exc

    if total_score <= 0:
        raise HTTPException(400, "O valor total da prova deve ser positivo.")

    normalized: list[dict[str, Any]] = []

    for index, question in enumerate(questions, start=1):
        if not isinstance(question, dict):
            raise HTTPException(400, f"Questão {index} inválida.")

        option_count = question.get("option_count")
        answer = str(question.get("answer", "")).upper().strip()
        raw_weight = question.get("weight", 1)

        if not isinstance(option_count, int) or not 2 <= option_count <= 5:
            raise HTTPException(
                400,
                f"A questão {index} deve ter entre 2 e 5 alternativas.",
            )

        try:
            weight = float(raw_weight)
        except (TypeError, ValueError) as exc:
            raise HTTPException(
                400,
                f"O peso da questão {index} é inválido.",
            ) from exc

        if not 0.1 <= weight <= 1:
            raise HTTPException(
                400,
                (
                    f"O peso da questão {index} deve estar "
                    "entre 0,1 e 1."
                ),
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
                "weight": weight,
            }
        )

    return title, normalized, total_score


def create_marker(path: Path) -> None:
    size = 160
    image = Image.new("RGB", (size, size), "white")
    draw = ImageDraw.Draw(image)

    draw.ellipse((10, 10, size - 10, size - 10), fill="black")
    draw.ellipse((37, 37, size - 37, size - 37), fill="white")
    draw.ellipse((65, 65, size - 65, size - 65), fill="black")

    image.save(path, quality=100)


def calculate_layout(
    questions: list[dict[str, Any]],
    *,
    top: int = 285,
) -> list[dict[str, Any]]:
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


def create_batch_template(
    layout: list[dict[str, Any]],
    *,
    student_id_digits: int = STUDENT_ID_DIGITS,
) -> dict[str, Any]:
    del student_id_digits
    # A matrícula escrita será lida futuramente por OCR. O OMR continua
    # responsável apenas pelas alternativas da prova.
    return create_template(layout)


def create_evaluation(
    questions: list[dict[str, Any]],
) -> dict[str, Any]:
    # O OMRChecker é usado para detectar as respostas. A nota ponderada
    # é calculada por esta aplicação após a leitura do CSV.
    return {
        "source_type": "local",
        "options": {
            "questions_in_order": [f"q1..{len(questions)}"],
            "answers_in_order": [question["answer"] for question in questions],
            "marking_schemes": {
                "DEFAULT": {
                    "correct": "1",
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
    student_id_digits: int = 0,
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
    if show_answers:
        document_kind = "Solução"
    elif student_id_digits:
        document_kind = "Folha de respostas com matrícula em blocos"
    else:
        document_kind = "Folha de respostas"
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
            "SOLUÇÃO - GABARITO MARCADO",
        )
        canvas.setFont("Helvetica", 7)
        canvas.drawCentredString(
            page_width / 2,
            y_pdf(205),
            "As alternativas preenchidas correspondem às respostas corretas.",
        )
    elif student_id_digits:
        canvas.setFont("Helvetica", 8)
        canvas.drawString(x_pdf(110), y_pdf(145), "Nome:")
        canvas.line(x_pdf(190), y_pdf(150), x_pdf(1080), y_pdf(150))

        canvas.setFont("Helvetica-Bold", 8)
        canvas.drawString(x_pdf(110), y_pdf(210), "Matrícula:")
        canvas.setFont("Helvetica", 7)
        canvas.drawString(
            x_pdf(245),
            y_pdf(210),
            "escreva um algarismo em cada bloco",
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

    if student_id_digits and not show_answers:
        block_width = 70
        block_height = 62
        block_gap = 14
        origin_x = 250
        origin_y = 232

        for column in range(student_id_digits):
            block_x = origin_x + column * (block_width + block_gap)
            left_x = x_pdf(block_x)
            bottom_y = y_pdf(origin_y + block_height)
            width = block_width * scale_x
            height = block_height * scale_y

            canvas.setLineWidth(0.9)
            canvas.roundRect(
                left_x,
                bottom_y,
                width,
                height,
                3,
                stroke=1,
                fill=0,
            )

        canvas.setFont("Helvetica", 6.5)
        canvas.drawCentredString(
            page_width / 2,
            y_pdf(325),
            "Escreva os algarismos grandes, centralizados e sem encostar nas bordas.",
        )

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



def ensure_batch_package(assessment_dir: Path) -> dict[str, Path]:
    assessment_path = assessment_dir / "avaliacao.json"
    assessment_data = read_json(assessment_path)
    questions = assessment_data.get("questions", [])

    if not isinstance(questions, list) or not questions:
        raise RuntimeError("A avaliação não possui questões válidas.")

    batch_dir = assessment_dir / "pacote_lote"
    batch_dir.mkdir(parents=True, exist_ok=True)

    paths = {
        "sheet": assessment_dir / "folha_respostas_matricula.pdf",
        "template": batch_dir / "template.json",
        "evaluation": batch_dir / "evaluation.json",
        "config": batch_dir / "config.json",
        "marker": batch_dir / "omr_marker.jpg",
    }

    batch_data = assessment_data.get("batch", {})
    package_is_current = (
        isinstance(batch_data, dict)
        and batch_data.get("template_version") == BATCH_TEMPLATE_VERSION
        and all(path.exists() for path in paths.values())
    )

    if package_is_current:
        return paths

    create_marker(paths["marker"])
    layout = calculate_layout(questions, top=BATCH_QUESTION_TOP)
    write_json(
        paths["template"],
        create_batch_template(
            layout,
            student_id_digits=STUDENT_ID_DIGITS,
        ),
    )
    write_json(paths["evaluation"], create_evaluation(questions))
    write_json(paths["config"], create_config())

    draw_answer_sheet(
        paths["sheet"],
        paths["marker"],
        str(assessment_data.get("title", "Avaliação")),
        str(assessment_data.get("id", assessment_dir.name)),
        layout,
        student_id_digits=STUDENT_ID_DIGITS,
    )

    assessment_data["batch"] = {
        "enabled": True,
        "student_id_digits": STUDENT_ID_DIGITS,
        "mode": "written_blocks",
        "template_version": BATCH_TEMPLATE_VERSION,
        "sheet": "folha_respostas_matricula.pdf",
    }
    write_json(assessment_path, assessment_data)
    return paths


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


def parse_omr_csv_row(results_dir: Path) -> dict[str, str]:
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
                if key
            }

    raise RuntimeError("O CSV gerado não contém respostas.")


def parse_omr_csv(results_dir: Path) -> dict[str, str]:
    row = parse_omr_csv_row(results_dir)
    return {
        key: value
        for key, value in row.items()
        if re.fullmatch(r"q\d+", key)
    }




def _load_page_image(source_path: Path) -> Any:
    """Load the first page of an image/PDF as an OpenCV BGR array."""
    try:
        import cv2
        import fitz
        import numpy as np
    except Exception as exc:
        raise RuntimeError(
            "Dependências de imagem indisponíveis. Confirme OpenCV, NumPy e PyMuPDF."
        ) from exc

    suffix = source_path.suffix.lower()

    if suffix in {".png", ".jpg", ".jpeg"}:
        image = cv2.imread(str(source_path))
        if image is None:
            raise RuntimeError("Não foi possível abrir a imagem enviada.")
        return image

    if suffix == ".pdf":
        document = fitz.open(str(source_path))
        try:
            if document.page_count < 1:
                raise RuntimeError("O PDF enviado não possui páginas.")
            page = document.load_page(0)
            pixmap = page.get_pixmap(matrix=fitz.Matrix(3, 3), alpha=False)
            array = np.frombuffer(pixmap.samples, dtype=np.uint8).reshape(
                pixmap.height,
                pixmap.width,
                pixmap.n,
            )
            if pixmap.n == 4:
                return cv2.cvtColor(array, cv2.COLOR_RGBA2BGR)
            return cv2.cvtColor(array, cv2.COLOR_RGB2BGR)
        finally:
            document.close()

    raise RuntimeError("Formato inválido. Use PDF, PNG, JPG ou JPEG.")


def _detect_marker_centers(image: Any) -> list[tuple[float, float]]:
    """Find the four circular markers and return TL, TR, BL, BR centers."""
    try:
        import cv2
    except Exception as exc:
        raise RuntimeError("OpenCV não está disponível para localizar os marcadores.") from exc

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (3, 3), 0)
    _, binary = cv2.threshold(
        blurred,
        0,
        255,
        cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU,
    )
    contours, _ = cv2.findContours(
        binary,
        cv2.RETR_LIST,
        cv2.CHAIN_APPROX_SIMPLE,
    )

    height, width = gray.shape
    minimum_dimension = min(width, height)
    anchors = [
        (0.14 * width, 0.16 * height),
        (0.86 * width, 0.16 * height),
        (0.14 * width, 0.84 * height),
        (0.86 * width, 0.84 * height),
    ]

    centers: list[tuple[float, float]] = []

    for anchor_x, anchor_y in anchors:
        best: tuple[float, float, float] | None = None

        for contour in contours:
            x, y, contour_width, contour_height = cv2.boundingRect(contour)

            if not (
                0.012 * minimum_dimension <= contour_width <= 0.10 * minimum_dimension
                and 0.012 * minimum_dimension <= contour_height <= 0.10 * minimum_dimension
            ):
                continue

            ratio = contour_width / max(contour_height, 1)
            if not 0.65 <= ratio <= 1.35:
                continue

            area = cv2.contourArea(contour)
            perimeter = cv2.arcLength(contour, True)
            if area <= 0 or perimeter <= 0:
                continue

            circularity = 4 * math.pi * area / (perimeter * perimeter)
            if circularity < 0.25:
                continue

            center_x = x + contour_width / 2
            center_y = y + contour_height / 2
            distance = math.hypot(
                (center_x - anchor_x) / width,
                (center_y - anchor_y) / height,
            )

            if distance > 0.32:
                continue

            # Prefer candidates near the expected corner, circular and larger.
            score = (
                distance
                - 0.03 * circularity
                - 0.001 * min(contour_width, contour_height)
            )

            if best is None or score < best[0]:
                best = (score, center_x, center_y)

        if best is None:
            raise RuntimeError(
                "Não foi possível localizar os quatro marcadores da folha. "
                "Digitalize a página inteira, sem cortar as bordas."
            )

        centers.append((best[1], best[2]))

    return centers


def _align_sheet_to_template(source_path: Path) -> Any:
    """Perspective-warp a scanned sheet to the 1200 x 1600 template."""
    try:
        import cv2
        import numpy as np
    except Exception as exc:
        raise RuntimeError("OpenCV/NumPy indisponíveis para alinhar a folha.") from exc

    image = _load_page_image(source_path)
    marker_centers = _detect_marker_centers(image)
    source_points = np.array(marker_centers, dtype=np.float32)
    target_points = np.array(
        [
            [0, 0],
            [PAGE_WIDTH - 1, 0],
            [0, PAGE_HEIGHT - 1],
            [PAGE_WIDTH - 1, PAGE_HEIGHT - 1],
        ],
        dtype=np.float32,
    )
    transform = cv2.getPerspectiveTransform(source_points, target_points)
    return cv2.warpPerspective(
        image,
        transform,
        (PAGE_WIDTH, PAGE_HEIGHT),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(255, 255, 255),
    )


def _ocr_single_digit(crop: Any, work_dir: Path, index: int) -> tuple[str, float]:
    """Recognize one handwritten digit with Tesseract and a digit whitelist."""
    try:
        import cv2
        import numpy as np
    except Exception as exc:
        raise RuntimeError("OpenCV/NumPy indisponíveis para preparar o OCR.") from exc

    if shutil.which("tesseract") is None:
        raise RuntimeError(
            "O Tesseract OCR não está instalado. No macOS, execute: brew install tesseract"
        )

    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    height, width = gray.shape

    # Ignore the box border and keep only the handwriting area.
    inner = gray[
        int(height * 0.12): int(height * 0.88),
        int(width * 0.14): int(width * 0.86),
    ]
    _, inverted = cv2.threshold(
        inner,
        0,
        255,
        cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU,
    )

    ink_ratio = float(np.mean(inverted > 0))
    if ink_ratio < 0.012:
        return "", ink_ratio

    normal = 255 - inverted
    enlarged = cv2.resize(
        normal,
        None,
        fx=6,
        fy=6,
        interpolation=cv2.INTER_CUBIC,
    )
    prepared = cv2.copyMakeBorder(
        enlarged,
        40,
        40,
        40,
        40,
        cv2.BORDER_CONSTANT,
        value=255,
    )
    image_path = work_dir / f"digito_{index + 1}.png"
    cv2.imwrite(str(image_path), prepared)

    attempts: list[str] = []
    for page_segmentation_mode in (13, 8, 10, 6):
        completed = subprocess.run(
            [
                "tesseract",
                str(image_path),
                "stdout",
                "--oem",
                "1",
                "--psm",
                str(page_segmentation_mode),
                "-l",
                "eng",
                "-c",
                "tessedit_char_whitelist=0123456789",
            ],
            capture_output=True,
            text=True,
            timeout=20,
        )
        recognized = re.sub(r"\D", "", completed.stdout or "")
        if recognized:
            attempts.append(recognized[0])

    if not attempts:
        return "", ink_ratio

    # Majority vote among preprocessing modes. Ties keep the first result.
    digit = max(attempts, key=lambda value: (attempts.count(value), -attempts.index(value)))
    return digit, ink_ratio


def recognize_registration_from_blocks(
    source_path: Path,
    work_dir: Path,
) -> dict[str, Any]:
    """Read the ten registration boxes after marker-based alignment."""
    try:
        import cv2
    except Exception as exc:
        raise RuntimeError("OpenCV não está disponível para reconhecer a matrícula.") from exc

    aligned = _align_sheet_to_template(source_path)
    aligned_path = work_dir / "folha_alinhada.png"
    cv2.imwrite(str(aligned_path), aligned)

    block_width = 70
    block_height = 62
    block_gap = 14
    origin_x = 250
    origin_y = 232

    digits: list[str] = []
    ink_ratios: list[float] = []

    for index in range(STUDENT_ID_DIGITS):
        block_x = origin_x + index * (block_width + block_gap)
        crop = aligned[
            origin_y: origin_y + block_height,
            block_x: block_x + block_width,
        ]
        digit, ink_ratio = _ocr_single_digit(crop, work_dir, index)
        digits.append(digit)
        ink_ratios.append(round(ink_ratio, 4))

    # A valid registration is written contiguously from the first block.
    compact_digits: list[str] = []
    blank_found = False
    invalid_gap = False

    for digit in digits:
        if digit:
            if blank_found:
                invalid_gap = True
            compact_digits.append(digit)
        else:
            blank_found = True

    registration = "" if invalid_gap else "".join(compact_digits)
    registration = normalize_marked_registration(registration)

    registration_crop = aligned[
        max(0, origin_y - 20): min(PAGE_HEIGHT, origin_y + block_height + 20),
        max(0, origin_x - 20): min(
            PAGE_WIDTH,
            origin_x + STUDENT_ID_DIGITS * block_width + (STUDENT_ID_DIGITS - 1) * block_gap + 20,
        ),
    ]
    registration_crop_path = work_dir / "matricula_recortada.png"
    cv2.imwrite(str(registration_crop_path), registration_crop)

    return {
        "registration": registration,
        "digits": digits,
        "ink_ratios": ink_ratios,
        "invalid_gap": invalid_gap,
        "aligned_image_path": aligned_path,
        "registration_crop_path": registration_crop_path,
    }


def expand_batch_upload(source_path: Path, destination_dir: Path) -> list[Path]:
    """Convert an uploaded file into one image per page for batch processing."""
    suffix = source_path.suffix.lower()

    if suffix in {".png", ".jpg", ".jpeg"}:
        destination = destination_dir / source_path.name
        shutil.copy2(source_path, destination)
        return [destination]

    if suffix != ".pdf":
        raise RuntimeError("Formato inválido. Use PDF, PNG, JPG ou JPEG.")

    try:
        import fitz
    except Exception as exc:
        raise RuntimeError("PyMuPDF não está disponível para dividir o PDF.") from exc

    pages: list[Path] = []
    document = fitz.open(str(source_path))
    try:
        for page_index in range(document.page_count):
            page = document.load_page(page_index)
            pixmap = page.get_pixmap(matrix=fitz.Matrix(3, 3), alpha=False)
            destination = destination_dir / (
                f"{source_path.stem}-pagina-{page_index + 1:03d}.png"
            )
            pixmap.save(str(destination))
            pages.append(destination)
    finally:
        document.close()

    return pages

def normalize_marked_registration(value: object) -> str:
    compact = re.sub(r"\s+", "", str(value or ""))

    if not re.fullmatch(rf"\d{{1,{STUDENT_ID_DIGITS}}}", compact):
        return ""

    return compact


def registration_comparison_key(value: object) -> str:
    text = re.sub(r"\s+", "", str(value or ""))

    if text.isdigit():
        return text.lstrip("0") or "0"

    return text.casefold()


def find_student_by_registration(
    students_data: dict[str, Any],
    registration: str,
) -> dict[str, Any] | None:
    students = students_data.get("students", [])

    if not isinstance(students, list):
        return None

    for student in students:
        if isinstance(student, dict) and str(student.get("id", "")) == registration:
            return student

    wanted_key = registration_comparison_key(registration)
    matches = [
        student
        for student in students
        if isinstance(student, dict)
        and registration_comparison_key(student.get("id")) == wanted_key
    ]

    return matches[0] if len(matches) == 1 else None


def grade_responses(
    detected: dict[str, str],
    answer_key: dict[str, str],
    questions: list[dict[str, Any]],
    maximum_score: float,
) -> dict[str, Any]:
    details: list[dict[str, Any]] = []
    correct_count = 0
    blank_count = 0
    earned_weight = 0.0

    question_by_number = {
        int(question.get("number", index)): question
        for index, question in enumerate(questions, start=1)
        if isinstance(question, dict)
    }

    ordered_keys = sorted(
        answer_key,
        key=lambda key: int(key.removeprefix("q")),
    )

    weights: dict[int, float] = {}

    for question_number in range(1, len(ordered_keys) + 1):
        question = question_by_number.get(question_number, {})
        try:
            weight = float(question.get("weight", 1))
        except (TypeError, ValueError):
            weight = 1.0

        weights[question_number] = weight if weight > 0 else 1.0

    total_weight = sum(weights.values()) or float(len(ordered_keys) or 1)

    for key in ordered_keys:
        question_number = int(key.removeprefix("q"))
        selected = detected.get(key, "")
        correct_answer = answer_key[key]
        is_blank = selected == ""
        is_correct = selected == correct_answer
        weight = weights.get(question_number, 1.0)
        question_value = maximum_score * weight / total_weight
        earned_score = question_value if is_correct else 0.0

        if is_correct:
            correct_count += 1
            earned_weight += weight

        if is_blank:
            blank_count += 1

        details.append(
            {
                "question": question_number,
                "selected": selected,
                "correct_answer": correct_answer,
                "is_correct": is_correct,
                "is_blank": is_blank,
                "weight": round(weight, 6),
                "question_value": round(question_value, 4),
                "earned_score": round(earned_score, 4),
            }
        )

    total = len(ordered_keys)
    error_count = total - correct_count
    weighted_fraction = earned_weight / total_weight if total_weight else 0.0
    score = round(maximum_score * weighted_fraction, 4)
    percentage = round(weighted_fraction * 100, 2)

    return {
        "correct": correct_count,
        "errors": error_count,
        "blank": blank_count,
        "total": total,
        "score": score,
        "maximum_score": round(maximum_score, 4),
        "percentage": percentage,
        "earned_weight": round(earned_weight, 6),
        "total_weight": round(total_weight, 6),
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

    maximum_score = float(
        assessment_data.get(
            "maximum_score",
            assessment_data.get("total_score", 10),
        )
    )

    graded = grade_responses(
        detected=detected,
        answer_key=answer_key_data["answers"],
        questions=assessment_data.get("questions", []),
        maximum_score=maximum_score,
    )

    checked_omrs_dir = output_dir / "CheckedOMRs"
    supported_image_extensions = {".png", ".jpg", ".jpeg"}

    checked_images = sorted(
        (
            path
            for path in checked_omrs_dir.rglob("*")
            if path.is_file()
            and path.suffix.lower() in supported_image_extensions
            and "stack" not in path.parts
            and "_MULTI_" not in path.parts
        ),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )

    processed_image_relative = None

    if checked_images:
        student_dir = assessment_dir / "alunos" / student_id
        student_dir.mkdir(parents=True, exist_ok=True)

        processed_destination = (
            student_dir / f"processada{checked_images[0].suffix.lower()}"
        )

        shutil.copy2(
            checked_images[0],
            processed_destination,
        )

        processed_image_relative = str(
            processed_destination.relative_to(assessment_dir)
        )

    graded["processed_image"] = processed_image_relative
    graded["log_excerpt"] = (completed.stdout or "")[-1800:]

    shutil.rmtree(run_root, ignore_errors=True)
    return graded



def process_batch_sheet(
    assessment_dir: Path,
    source_path: Path,
) -> dict[str, Any]:
    package = ensure_batch_package(assessment_dir)
    run_root = assessment_dir / "_batch_processing" / uuid.uuid4().hex
    input_dir = run_root / "input"
    output_dir = run_root / "output"
    ocr_dir = run_root / "ocr"
    input_dir.mkdir(parents=True)
    output_dir.mkdir(parents=True)
    ocr_dir.mkdir(parents=True)

    try:
        ocr_result = recognize_registration_from_blocks(source_path, ocr_dir)

        for filename, source in (
            ("template.json", package["template"]),
            ("config.json", package["config"]),
            ("omr_marker.jpg", package["marker"]),
        ):
            if not source.exists():
                raise RuntimeError(f"Pacote em lote incompleto: {filename}.")
            shutil.copy2(source, input_dir / filename)

        processing_file = input_dir / source_path.name
        shutil.copy2(source_path, processing_file)

        main_path = OMR_ROOT / "main.py"
        if not main_path.exists():
            raise RuntimeError(
                "main.py do OMRChecker não foi encontrado. "
                "A pasta avaliacao_web deve ficar dentro da pasta omrchecker."
            )

        completed = subprocess.run(
            [
                sys.executable,
                str(main_path),
                "-i",
                str(input_dir),
                "-o",
                str(output_dir),
            ],
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
        maximum_score = float(
            assessment_data.get(
                "maximum_score",
                assessment_data.get("total_score", 10),
            )
        )
        graded = grade_responses(
            detected=detected,
            answer_key=answer_key_data["answers"],
            questions=assessment_data.get("questions", []),
            maximum_score=maximum_score,
        )

        checked_dir = output_dir / "CheckedOMRs"
        supported = {".png", ".jpg", ".jpeg"}
        checked_images = sorted(
            (
                path
                for path in checked_dir.rglob("*")
                if path.is_file()
                and path.suffix.lower() in supported
                and "stack" not in path.parts
                and "_MULTI_" not in path.parts
            ),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )

        processed_bytes = None
        processed_suffix = None
        if checked_images:
            processed_bytes = checked_images[0].read_bytes()
            processed_suffix = checked_images[0].suffix.lower()

        graded["marked_registration"] = ocr_result["registration"]
        graded["ocr_digits"] = ocr_result["digits"]
        graded["ocr_ink_ratios"] = ocr_result["ink_ratios"]
        graded["ocr_invalid_gap"] = ocr_result["invalid_gap"]
        graded["registration_crop_bytes"] = (
            ocr_result["registration_crop_path"].read_bytes()
        )
        graded["processed_image_bytes"] = processed_bytes
        graded["processed_image_suffix"] = processed_suffix
        graded["log_excerpt"] = (completed.stdout or "")[-1800:]
        return graded
    finally:
        shutil.rmtree(run_root, ignore_errors=True)

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


@app.get("/avaliacoes/{assessment_id}", response_class=HTMLResponse)
async def assessment_page(assessment_id: str) -> HTMLResponse:
    locate_assessment(assessment_id)

    html = (STATIC_DIR / "avaliacao.html").read_text(encoding="utf-8")
    html = html.replace(
        "__ASSESSMENT_ID_JSON__",
        json.dumps(assessment_id, ensure_ascii=False),
    )

    return HTMLResponse(
        content=html,
        headers={"Cache-Control": "no-store"},
    )




@app.get("/api/health")
async def health_check() -> dict[str, Any]:
    return {
        "status": "ok",
        "storage": "sqlite-local",
        "database": database_status(),
    }


@app.get("/api/database/status")
async def get_database_status() -> dict[str, Any]:
    return {
        "database": database_status(),
        "counts": database_counts(),
    }


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
                "total_weight": assessment.get(
                    "total_weight",
                    assessment.get("question_count", 0),
                ),
                "maximum_score": assessment.get(
                    "maximum_score",
                    assessment.get("total_score", 0),
                ),
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
    title, questions, total_score = validate_payload(payload)

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
    evaluation = create_evaluation(questions)
    config = create_config()

    total_weight = sum(float(question["weight"]) for question in questions)

    assessment_data = {
        "id": assessment_id,
        "title": title,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "question_count": len(questions),
        "total_score": total_score,
        "maximum_score": total_score,
        "total_weight": total_weight,
        # Mantido apenas para compatibilidade com telas ou dados antigos.
        "points_per_question": total_score / len(questions),
        "questions": questions,
    }

    answer_key_data = {
        "assessment_id": assessment_id,
        "title": title,
        "total_score": total_score,
        "total_weight": total_weight,
        "answers": {
            f"q{question['number']}": question["answer"]
            for question in questions
        },
        "weights": {
            f"q{question['number']}": question["weight"]
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

    batch_paths = ensure_batch_package(assessment_dir)

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
        batch_paths["sheet"],
        batch_paths["template"],
        batch_paths["evaluation"],
        batch_paths["config"],
        batch_paths["marker"],
    ]
    create_zip(zip_path, assessment_dir, zip_files)

    base_url = f"/arquivos/{assessment_id}"

    database_sync: dict[str, Any]

    try:
        database_sync = {
            "ok": True,
            "details": sync_assessment_directory(assessment_dir),
        }
    except Exception as exc:
        logger.exception("Falha ao sincronizar avaliação no SQLite.")
        database_sync = {
            "ok": False,
            "error": str(exc),
        }

    return {
        "id": assessment_id,
        "message": "Avaliação criada corretamente.",
        "database_sync": database_sync,
        "details_url": f"/avaliacoes/{assessment_id}",
        "downloads": {
            "answer_sheet": f"{base_url}/folha_respostas_matricula.pdf",
            "batch_answer_sheet": (
                f"{base_url}/folha_respostas_matricula.pdf"
            ),
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
    ensure_batch_package(assessment_dir)
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
            "answer_sheet": f"/arquivos/{assessment_id}/folha_respostas_matricula.pdf",
            "batch_answer_sheet": (
                f"/arquivos/{assessment_id}/folha_respostas_matricula.pdf"
            ),
            "solution": f"/arquivos/{assessment_id}/solucao_gabarito.pdf",
            "zip": f"/arquivos/{assessment_id}/pacote_completo.zip",
        },
    }



@app.post("/api/avaliacoes/{assessment_id}/upload-lote")
async def upload_batch_sheets(
    assessment_id: str,
    files: list[UploadFile] = File(...),
) -> dict[str, Any]:
    assessment_dir = locate_assessment(assessment_id)
    ensure_batch_package(assessment_dir)

    if not files:
        raise HTTPException(400, "Selecione ao menos uma folha.")

    if len(files) > 30:
        raise HTTPException(400, "Envie no máximo 30 arquivos por lote.")

    allowed_extensions = {".pdf", ".png", ".jpg", ".jpeg"}
    students_path = assessment_dir / "alunos.json"
    students_data = read_json(students_path)
    students = students_data.get("students", [])

    if not isinstance(students, list):
        students = []
        students_data["students"] = students

    batch_dir = assessment_dir / "_batch_upload" / uuid.uuid4().hex
    raw_dir = batch_dir / "raw"
    page_dir = batch_dir / "pages"
    raw_dir.mkdir(parents=True, exist_ok=True)
    page_dir.mkdir(parents=True, exist_ok=True)

    page_entries: list[tuple[Path, str]] = []

    try:
        for upload_index, upload in enumerate(files, start=1):
            original_name = Path(upload.filename or f"arquivo-{upload_index}.pdf").name
            extension = Path(original_name).suffix.lower()

            if extension not in allowed_extensions:
                raise HTTPException(
                    400,
                    f"Formato inválido em {original_name}. Use PDF, PNG, JPG ou JPEG.",
                )

            content = await upload.read()
            if not content:
                raise HTTPException(400, f"O arquivo {original_name} está vazio.")
            if len(content) > 80 * 1024 * 1024:
                raise HTTPException(
                    400,
                    f"O arquivo {original_name} deve ter no máximo 80 MB.",
                )

            raw_path = raw_dir / f"{upload_index:03d}-{uuid.uuid4().hex[:8]}{extension}"
            raw_path.write_bytes(content)

            expanded = expand_batch_upload(raw_path, page_dir)
            for page_number, page_path in enumerate(expanded, start=1):
                page_label = original_name
                if len(expanded) > 1:
                    page_label = f"{original_name} - página {page_number}"
                page_entries.append((page_path, page_label))

        if len(page_entries) > 60:
            raise HTTPException(
                400,
                "O lote resultou em mais de 60 páginas. Divida-o em dois envios.",
            )

        processed_students: set[str] = set()
        items: list[dict[str, Any]] = []
        corrected = 0
        review = 0
        errors = 0

        for page_path, page_label in page_entries:
            item: dict[str, Any] = {
                "filename": page_label,
                "status": "review",
            }

            try:
                result = process_batch_sheet(
                    assessment_dir=assessment_dir,
                    source_path=page_path,
                )
                registration = str(result.pop("marked_registration", "")).strip()
                ocr_digits = result.pop("ocr_digits", [])
                crop_bytes = result.pop("registration_crop_bytes", None)
                processed_bytes = result.pop("processed_image_bytes", None)
                processed_suffix = result.pop("processed_image_suffix", None)

                item["registration"] = registration
                item["ocr_digits"] = ocr_digits

                if not registration:
                    review_dir = assessment_dir / "revisao_lote"
                    review_dir.mkdir(parents=True, exist_ok=True)
                    review_name = f"{uuid.uuid4().hex[:10]}-{page_path.name}"
                    shutil.copy2(page_path, review_dir / review_name)
                    if crop_bytes:
                        (review_dir / f"{Path(review_name).stem}-matricula.png").write_bytes(crop_bytes)
                    item["message"] = (
                        "A matrícula não foi reconhecida com segurança. "
                        "A folha foi separada para revisão."
                    )
                    review += 1
                    items.append(item)
                    continue

                student = find_student_by_registration(students_data, registration)

                if student is None:
                    profile = find_student_profile(registration)
                    if profile is not None:
                        student = {
                            "id": profile["registration"],
                            "name": profile["name"],
                            "status": "pending",
                            "result": None,
                            "uploaded_file": None,
                        }
                        students.append(student)

                if student is None:
                    item["message"] = (
                        f"A matrícula {registration} foi lida, mas não existe no cadastro."
                    )
                    review += 1
                    items.append(item)
                    continue

                normalized_id = str(student.get("id", registration))

                if normalized_id in processed_students:
                    item["message"] = (
                        "Já existe outra folha deste aluno no mesmo lote."
                    )
                    review += 1
                    items.append(item)
                    continue

                if (
                    student.get("status") == "corrected"
                    and isinstance(student.get("result"), dict)
                ):
                    item["message"] = (
                        "Este aluno já possui uma correção. A nova folha não substituiu o resultado."
                    )
                    review += 1
                    items.append(item)
                    continue

                processed_students.add(normalized_id)
                student_dir = assessment_dir / "alunos" / safe_student_id(normalized_id)
                student_dir.mkdir(parents=True, exist_ok=True)

                original_destination = student_dir / f"folha_original{page_path.suffix.lower()}"
                shutil.copy2(page_path, original_destination)

                if crop_bytes:
                    crop_destination = student_dir / "matricula_ocr.png"
                    crop_destination.write_bytes(crop_bytes)
                    result["registration_crop"] = str(
                        crop_destination.relative_to(assessment_dir)
                    )

                if processed_bytes and processed_suffix:
                    processed_destination = student_dir / f"processada{processed_suffix}"
                    processed_destination.write_bytes(processed_bytes)
                    result["processed_image"] = str(
                        processed_destination.relative_to(assessment_dir)
                    )

                result_path = student_dir / "resultado.json"
                write_json(result_path, result)

                student["status"] = "corrected"
                student["uploaded_file"] = str(
                    original_destination.relative_to(assessment_dir)
                )
                student["result"] = result

                write_json(students_path, students_data)

                try:
                    sync_assessment_directory(assessment_dir)
                except Exception:
                    logger.exception("Falha ao sincronizar o SQLite após o lote.")

                item.update(
                    {
                        "status": "corrected",
                        "registration": normalized_id,
                        "student_name": str(student.get("name", "Aluno")),
                        "score": result.get("score", 0),
                        "maximum_score": result.get("maximum_score", 0),
                        "message": "Matrícula reconhecida, folha corrigida e nota lançada.",
                    }
                )
                corrected += 1
                items.append(item)
            except subprocess.TimeoutExpired:
                item["status"] = "error"
                item["message"] = "O processamento excedeu o tempo limite."
                errors += 1
                items.append(item)
            except Exception as exc:
                item["status"] = "error"
                item["message"] = str(exc)
                errors += 1
                items.append(item)

        return {
            "message": (
                f"Lote processado: {corrected} corrigida(s), "
                f"{review} para revisão e {errors} com erro."
            ),
            "summary": {
                "corrected": corrected,
                "review": review,
                "errors": errors,
                "total": len(items),
            },
            "items": items,
        }
    finally:
        shutil.rmtree(batch_dir, ignore_errors=True)


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
        shutil.rmtree(
            assessment_dir / "_processing" / safe_id,
            ignore_errors=True,
        )
        raise HTTPException(
            504,
            "O processamento demorou mais que o limite permitido.",
        ) from exc
    except Exception as exc:
        shutil.rmtree(
            assessment_dir / "_processing" / safe_id,
            ignore_errors=True,
        )
        raise HTTPException(
            422,
            f"Falha ao processar a folha: {exc}",
        ) from exc

    result_path = student_dir / "resultado.json"
    write_json(result_path, result)

    student["status"] = "corrected"
    student["uploaded_file"] = str(stored_path.relative_to(assessment_dir))
    student["result"] = result
    write_json(students_path, students_data)

    try:
        database_sync = {
            "ok": True,
            "details": sync_assessment_directory(assessment_dir),
        }
    except Exception as exc:
        logger.exception("Falha ao sincronizar correção no SQLite.")
        database_sync = {
            "ok": False,
            "error": str(exc),
        }

    return {
        "message": f"Folha de {student['name']} corrigida.",
        "student": student,
        "database_sync": database_sync,
    }
