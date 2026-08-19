from __future__ import annotations

import csv
import math
import re
import shutil
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any

from .config import OMR_ROOT, SUBPROCESS_TIMEOUT_SECONDS, TMP_ROOT
from .omr_generation import (
    PAGE_HEIGHT,
    PAGE_WIDTH,
    QR_REGION,
    STUDENT_ID_BLOCK_GAP,
    STUDENT_ID_BLOCK_HEIGHT,
    STUDENT_ID_BLOCK_WIDTH,
    STUDENT_ID_DIGITS,
    STUDENT_ID_ORIGIN,
)

QR_PAYLOAD_PATTERN = re.compile(r"^SIM:(?P<simulado_id>[^|]+)\|ALU:(?P<aluno_id>.+)$")


def _load_page_image(source_path: Path) -> Any:
    """Load the first page of an image/PDF as an OpenCV BGR array."""
    import cv2
    import fitz
    import numpy as np

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
                pixmap.height, pixmap.width, pixmap.n
            )
            if pixmap.n == 4:
                return cv2.cvtColor(array, cv2.COLOR_RGBA2BGR)
            return cv2.cvtColor(array, cv2.COLOR_RGB2BGR)
        finally:
            document.close()

    raise RuntimeError("Formato inválido. Use PDF, PNG, JPG ou JPEG.")


def _detect_marker_centers(image: Any) -> list[tuple[float, float]]:
    """Find the four circular markers and return TL, TR, BL, BR centers."""
    import cv2

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (3, 3), 0)
    _, binary = cv2.threshold(
        blurred, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
    )
    contours, _ = cv2.findContours(binary, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)

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
                and 0.012 * minimum_dimension
                <= contour_height
                <= 0.10 * minimum_dimension
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
                (center_x - anchor_x) / width, (center_y - anchor_y) / height
            )

            if distance > 0.32:
                continue

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


def align_sheet_to_template(source_path: Path) -> Any:
    """Perspective-warp a scanned sheet to the PAGE_WIDTH x PAGE_HEIGHT template."""
    import cv2
    import numpy as np

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


def parse_qr_payload(valor: str) -> tuple[str, str] | None:
    """Extract (simulado_id, aluno_id) from a 'SIM:...|ALU:...' QR payload."""
    match = QR_PAYLOAD_PATTERN.match(valor.strip()) if valor else None
    if not match:
        return None
    return match.group("simulado_id"), match.group("aluno_id")


def read_qr_from_aligned_sheet(aligned_image: Any) -> tuple[str, str] | None:
    """Look for the per-student QR in its known corner and decode it.

    Sheets generated without a QR (older simulados, or the generic blank
    sheet) simply won't have anything there — this returns None and the
    caller falls back to matricula-based matching, unchanged.
    """
    import cv2

    margin = 20
    x0 = max(0, QR_REGION["x"] - margin)
    y0 = max(0, QR_REGION["y"] - margin)
    x1 = min(PAGE_WIDTH, QR_REGION["x"] + QR_REGION["size"] + margin)
    y1 = min(PAGE_HEIGHT, QR_REGION["y"] + QR_REGION["size"] + margin)

    crop = aligned_image[y0:y1, x0:x1]
    if crop.size == 0:
        return None

    detector = cv2.QRCodeDetector()
    valor, _points, _straight = detector.detectAndDecode(crop)
    if not valor:
        return None

    return parse_qr_payload(valor)


def _ocr_single_digit(crop: Any, work_dir: Path, index: int) -> tuple[str, float]:
    """Recognize one handwritten digit with Tesseract and a digit whitelist."""
    import cv2
    import numpy as np

    if shutil.which("tesseract") is None:
        raise RuntimeError("O binário 'tesseract' não está instalado neste serviço.")

    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    height, width = gray.shape

    inner = gray[
        int(height * 0.12) : int(height * 0.88),
        int(width * 0.14) : int(width * 0.86),
    ]
    _, inverted = cv2.threshold(
        inner, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
    )

    ink_ratio = float(np.mean(inverted > 0))
    if ink_ratio < 0.012:
        return "", ink_ratio

    normal = 255 - inverted
    enlarged = cv2.resize(normal, None, fx=6, fy=6, interpolation=cv2.INTER_CUBIC)
    prepared = cv2.copyMakeBorder(
        enlarged, 40, 40, 40, 40, cv2.BORDER_CONSTANT, value=255
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

    digit = max(attempts, key=lambda value: (attempts.count(value), -attempts.index(value)))
    return digit, ink_ratio


def normalize_marked_registration(value: object) -> str:
    compact = re.sub(r"\s+", "", str(value or ""))

    if not re.fullmatch(rf"\d{{1,{STUDENT_ID_DIGITS}}}", compact):
        return ""

    return compact


def recognize_registration_from_blocks(
    aligned: Any,
    work_dir: Path,
) -> dict[str, Any]:
    """Read the ten registration boxes from an already-aligned sheet."""
    block_width = STUDENT_ID_BLOCK_WIDTH
    block_height = STUDENT_ID_BLOCK_HEIGHT
    block_gap = STUDENT_ID_BLOCK_GAP
    origin_x, origin_y = STUDENT_ID_ORIGIN

    digits: list[str] = []
    ink_ratios: list[float] = []

    for index in range(STUDENT_ID_DIGITS):
        block_x = origin_x + index * (block_width + block_gap)
        crop = aligned[
            origin_y : origin_y + block_height, block_x : block_x + block_width
        ]
        digit, ink_ratio = _ocr_single_digit(crop, work_dir, index)
        digits.append(digit)
        ink_ratios.append(round(ink_ratio, 4))

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

    return {
        "registration": registration,
        "digits": digits,
        "ink_ratios": ink_ratios,
        "invalid_gap": invalid_gap,
    }


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
            return {key: (value or "").strip() for key, value in row.items() if key}

    raise RuntimeError("O CSV gerado não contém respostas.")


def parse_omr_csv(results_dir: Path) -> dict[str, str]:
    row = parse_omr_csv_row(results_dir)
    return {key: value for key, value in row.items() if re.fullmatch(r"q\d+", key)}


def run_omrchecker(input_dir: Path, output_dir: Path) -> subprocess.CompletedProcess:
    main_path = OMR_ROOT / "main.py"
    if not main_path.exists():
        raise RuntimeError(
            f"main.py do OMRChecker não foi encontrado em {OMR_ROOT}."
        )

    return subprocess.run(
        [sys.executable, str(main_path), "-i", str(input_dir), "-o", str(output_dir)],
        cwd=OMR_ROOT,
        capture_output=True,
        text=True,
        timeout=SUBPROCESS_TIMEOUT_SECONDS,
    )


def newest_checked_image(output_dir: Path) -> Path | None:
    checked_dir = output_dir / "CheckedOMRs"
    supported = {".png", ".jpg", ".jpeg"}

    if not checked_dir.exists():
        return None

    images = sorted(
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
    return images[0] if images else None


def new_run_dir() -> Path:
    run_dir = TMP_ROOT / uuid.uuid4().hex
    (run_dir / "input").mkdir(parents=True)
    (run_dir / "output").mkdir(parents=True)
    return run_dir
