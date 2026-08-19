from __future__ import annotations

from pathlib import Path

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg"}


def split_into_pages(filename: str, content: bytes) -> list[tuple[str, bytes]]:
    """Split an uploaded scan into one page-image per physical sheet.

    A single image passes through unchanged (one page). A multi-page PDF
    (e.g. one scanner run covering a whole class) is rendered page-by-page
    into PNGs, ported from avaliacao_web/app.py:expand_batch_upload.
    """
    suffix = Path(filename).suffix.lower()
    stem = Path(filename).stem or "folha"

    if suffix in IMAGE_EXTENSIONS:
        return [(filename, content)]

    if suffix != ".pdf":
        raise ValueError("Formato inválido. Use PDF, PNG, JPG ou JPEG.")

    import fitz

    pages: list[tuple[str, bytes]] = []
    document = fitz.open(stream=content, filetype="pdf")
    try:
        for page_index in range(document.page_count):
            page = document.load_page(page_index)
            pixmap = page.get_pixmap(matrix=fitz.Matrix(3, 3), alpha=False)
            page_name = f"{stem}-pagina-{page_index + 1:03d}.png"
            pages.append((page_name, pixmap.tobytes("png")))
    finally:
        document.close()

    return pages
