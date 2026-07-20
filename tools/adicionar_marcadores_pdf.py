from __future__ import annotations

from pathlib import Path

import fitz


ROOT = Path(__file__).resolve().parent.parent

PDF_ORIGINAL = (
    ROOT
    / "formularios"
    / "prova_teste_01"
    / "cartao_resposta_5q.pdf"
)

MARCADOR = (
    ROOT
    / "formularios"
    / "prova_teste_01"
    / "omr_marker.jpg"
)

PDF_DESTINO = (
    ROOT
    / "formularios"
    / "prova_teste_01"
    / "cartao_resposta_5q_marcadores.pdf"
)

# Dimensões do cartão que criamos anteriormente.
LARGURA_CARTAO_MM = 150
ALTURA_CARTAO_MM = 200

# Mesmo valor usado no template CropOnMarkers.
RAZAO_CARTAO_MARCADOR = 17


def mm_para_pontos(valor_mm: float) -> float:
    """Converte milímetros para pontos de PDF."""
    return valor_mm * 72 / 25.4


def criar_retangulo_centralizado(
    centro_x: float,
    centro_y: float,
    lado: float,
) -> fitz.Rect:
    metade = lado / 2

    return fitz.Rect(
        centro_x - metade,
        centro_y - metade,
        centro_x + metade,
        centro_y + metade,
    )


def main() -> None:
    if not PDF_ORIGINAL.exists():
        raise FileNotFoundError(
            f"PDF original não encontrado:\n{PDF_ORIGINAL}"
        )

    if not MARCADOR.exists():
        raise FileNotFoundError(
            f"Imagem do marcador não encontrada:\n{MARCADOR}"
        )

    documento = fitz.open(PDF_ORIGINAL)

    if len(documento) != 1:
        documento.close()
        raise ValueError(
            "O PDF deve possuir exatamente uma página."
        )

    pagina = documento[0]

    largura_pagina = pagina.rect.width
    altura_pagina = pagina.rect.height

    largura_cartao = mm_para_pontos(
        LARGURA_CARTAO_MM
    )

    altura_cartao = mm_para_pontos(
        ALTURA_CARTAO_MM
    )

    esquerda = (
        largura_pagina - largura_cartao
    ) / 2

    direita = esquerda + largura_cartao

    topo = (
        altura_pagina - altura_cartao
    ) / 2

    inferior = topo + altura_cartao

    # O tamanho do marcador mantém a mesma proporção
    # indicada por sheetToMarkerWidthRatio = 17.
    lado_marcador = (
        largura_cartao
        / RAZAO_CARTAO_MARCADOR
    )

    centros = [
        (esquerda, topo),
        (direita, topo),
        (esquerda, inferior),
        (direita, inferior),
    ]

    for centro_x, centro_y in centros:
        area = criar_retangulo_centralizado(
            centro_x,
            centro_y,
            lado_marcador,
        )

        pagina.insert_image(
            area,
            filename=str(MARCADOR),
            keep_proportion=True,
            overlay=True,
        )

    documento.save(
        PDF_DESTINO,
        garbage=4,
        deflate=True,
    )

    documento.close()

    print("PDF com marcadores criado corretamente.")
    print(f"Arquivo: {PDF_DESTINO}")
    print(
        "Lado do marcador: "
        f"{lado_marcador * 25.4 / 72:.2f} mm"
    )


if __name__ == "__main__":
    main()
