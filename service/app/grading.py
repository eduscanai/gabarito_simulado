from __future__ import annotations

from typing import Any

from .schemas import DetalheQuestao, NotaCalculada, Questao


def grade_responses(
    detected: dict[str, str],
    questoes: list[Questao],
    valor_maximo: float,
) -> NotaCalculada:
    """Pure post-processing over OMRChecker's detected responses.

    Ported unchanged (in logic) from avaliacao_web/app.py:grade_responses —
    only the field names were translated to Portuguese for this service's
    own response contract.
    """
    details: list[DetalheQuestao] = []
    correct_count = 0
    blank_count = 0
    earned_weight = 0.0

    questao_by_number = {questao.numero: questao for questao in questoes}

    ordered_keys = sorted(
        (key for key in detected if key.removeprefix("q").isdigit()),
        key=lambda key: int(key.removeprefix("q")),
    )
    if not ordered_keys:
        ordered_keys = [f"q{questao.numero}" for questao in questoes]

    weights: dict[int, float] = {}
    for key in ordered_keys:
        number = int(key.removeprefix("q"))
        questao = questao_by_number.get(number)
        weight = questao.peso if questao else 1.0
        weights[number] = weight if weight > 0 else 1.0

    total_weight = sum(weights.values()) or float(len(ordered_keys) or 1)

    for key in ordered_keys:
        question_number = int(key.removeprefix("q"))
        questao = questao_by_number.get(question_number)
        correct_answer = questao.resposta if questao else ""
        selected = detected.get(key, "")
        is_blank = selected == ""
        is_correct = bool(correct_answer) and selected == correct_answer
        weight = weights.get(question_number, 1.0)
        question_value = valor_maximo * weight / total_weight
        earned_score = question_value if is_correct else 0.0

        if is_correct:
            correct_count += 1
            earned_weight += weight

        if is_blank:
            blank_count += 1

        details.append(
            DetalheQuestao(
                questao=question_number,
                selecionada=selected,
                resposta_correta=correct_answer,
                correta=is_correct,
                em_branco=is_blank,
                peso=round(weight, 6),
                valor_questao=round(question_value, 4),
                pontos_obtidos=round(earned_score, 4),
            )
        )

    total = len(ordered_keys)
    error_count = total - correct_count
    weighted_fraction = earned_weight / total_weight if total_weight else 0.0
    score = round(valor_maximo * weighted_fraction, 4)
    percentage = round(weighted_fraction * 100, 2)

    return NotaCalculada(
        acertos=correct_count,
        erros=error_count,
        em_branco=blank_count,
        total=total,
        nota=score,
        nota_maxima=round(valor_maximo, 4),
        percentual=percentage,
        peso_ganho=round(earned_weight, 6),
        peso_total=round(total_weight, 6),
        detalhes=details,
    )
