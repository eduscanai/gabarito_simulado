from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


# Pasta principal do OMRChecker.
ROOT = Path(__file__).resolve().parent.parent

# Arquivos da prova que já criamos.
TEMPLATE_ORIGEM = (
    ROOT
    / "inputs"
    / "prova_teste_01"
    / "template.json"
)

CONFIG_ORIGEM = (
    ROOT
    / "inputs"
    / "prova_teste_01"
    / "config.json"
)

# Pasta que será processada pelo OMRChecker.
PASTA_DESTINO = (
    ROOT
    / "inputs"
    / "prova_gerada_01"
)

IMAGEM_DESTINO = (
    PASTA_DESTINO
    / "folha_teste_marcada.png"
)

# Respostas que serão preenchidas artificialmente.
RESPOSTAS = {
    "q1": "B",
    "q2": "E",
    "q3": "A",
    "q4": "C",
    "q5": "B",
}


def expandir_rotulos(rotulos: list[str]) -> list[str]:
    """
    Converte, por exemplo:

        ["q1..5"]

    em:

        ["q1", "q2", "q3", "q4", "q5"]
    """
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
    """
    Converte QTYPE_MCQ5 em:

        ["A", "B", "C", "D", "E"]
    """
    correspondencia = re.fullmatch(
        r"QTYPE_MCQ(\d+)",
        tipo_campo,
    )

    if correspondencia is None:
        raise ValueError(
            f"Tipo de campo não suportado: {tipo_campo}"
        )

    quantidade = int(correspondencia.group(1))

    return [
        chr(ord("A") + indice)
        for indice in range(quantidade)
    ]


def obter_dimensoes(template: dict) -> tuple[int, int]:
    """
    Aceita tanto templates antigos, com pageDimensions,
    quanto templates novos, com templateDimensions.
    """
    dimensoes = (
        template.get("templateDimensions")
        or template.get("pageDimensions")
    )

    if dimensoes is None:
        raise KeyError(
            "O template não contém 'templateDimensions' "
            "nem 'pageDimensions'."
        )

    return int(dimensoes[0]), int(dimensoes[1])


def main() -> None:
    if not TEMPLATE_ORIGEM.exists():
        raise FileNotFoundError(
            f"Template não encontrado:\n{TEMPLATE_ORIGEM}"
        )

    if not CONFIG_ORIGEM.exists():
        raise FileNotFoundError(
            f"Configuração não encontrada:\n{CONFIG_ORIGEM}"
        )

    template = json.loads(
        TEMPLATE_ORIGEM.read_text(encoding="utf-8")
    )

    largura_pagina, altura_pagina = obter_dimensoes(
        template
    )

    largura_bolha, altura_bolha = template[
        "bubbleDimensions"
    ]

    blocos = template.get("fieldBlocks", {})

    if not blocos:
        raise ValueError(
            "O template não possui nenhum fieldBlock."
        )

    nome_bloco, bloco = next(iter(blocos.items()))

    origem_x, origem_y = bloco["origin"]
    espaco_questoes = bloco["labelsGap"]
    espaco_alternativas = bloco["bubblesGap"]

    questoes = expandir_rotulos(
        bloco["fieldLabels"]
    )

    alternativas = obter_alternativas(
        bloco["fieldType"]
    )

    imagem = Image.new(
        mode="RGB",
        size=(largura_pagina, altura_pagina),
        color="white",
    )

    desenho = ImageDraw.Draw(imagem)
    fonte = ImageFont.load_default()

    # Moldura externa, usada pelo CropPage.
    desenho.rectangle(
        [
            2,
            2,
            largura_pagina - 3,
            altura_pagina - 3,
        ],
        outline="black",
        width=3,
    )

    desenho.text(
        (largura_pagina / 2, 15),
        "CARTAO-RESPOSTA",
        fill="black",
        font=fonte,
        anchor="mm",
    )

    # Letras A, B, C, D e E.
    for indice, alternativa in enumerate(
        alternativas
    ):
        centro_x = (
            origem_x
            + indice * espaco_alternativas
            + largura_bolha / 2
        )

        desenho.text(
            (centro_x, origem_y - 8),
            alternativa,
            fill="black",
            font=fonte,
            anchor="mm",
        )

    # Desenha as questões e as bolhas.
    for indice_questao, questao in enumerate(
        questoes
    ):
        y = (
            origem_y
            + indice_questao * espaco_questoes
        )

        desenho.text(
            (
                origem_x - 15,
                y + altura_bolha / 2,
            ),
            str(indice_questao + 1),
            fill="black",
            font=fonte,
            anchor="mm",
        )

        for indice_alternativa, alternativa in enumerate(
            alternativas
        ):
            x = (
                origem_x
                + indice_alternativa
                * espaco_alternativas
            )

            caixa = [
                x + 2,
                y + 2,
                x + largura_bolha - 2,
                y + altura_bolha - 2,
            ]

            esta_marcada = (
                RESPOSTAS.get(questao)
                == alternativa
            )

            desenho.ellipse(
                caixa,
                outline="black",
                fill=(
                    "black"
                    if esta_marcada
                    else "white"
                ),
                width=2,
            )

    PASTA_DESTINO.mkdir(
        parents=True,
        exist_ok=True,
    )

    shutil.copy2(
        TEMPLATE_ORIGEM,
        PASTA_DESTINO / "template.json",
    )

    shutil.copy2(
        CONFIG_ORIGEM,
        PASTA_DESTINO / "config.json",
    )

    imagem.save(IMAGEM_DESTINO)

    print("Folha de teste criada corretamente.")
    print(f"Bloco utilizado: {nome_bloco}")
    print(f"Imagem criada em: {IMAGEM_DESTINO}")
    print(f"Respostas esperadas: {RESPOSTAS}")


if __name__ == "__main__":
    main()