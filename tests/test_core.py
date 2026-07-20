from avaliacao_web.app import (
    grade_responses,
    normalize_marked_registration,
    registration_comparison_key,
    slugify,
)


def test_slugify_preserves_readable_identifier():
    assert slugify("Cálculo I — P1") == "calculo-i-p1"


def test_registration_normalization():
    assert normalize_marked_registration("2026100963") == "2026100963"
    assert normalize_marked_registration(" 2026100963 ") == "2026100963"
    assert normalize_marked_registration("20A6100963") == ""


def test_registration_comparison_ignores_leading_zeros():
    assert registration_comparison_key("000123") == registration_comparison_key("123")


def test_weighted_score():
    result = grade_responses(
        detected={"q1": "A", "q2": "B"},
        answer_key={"q1": "A", "q2": "C"},
        questions=[
            {"number": 1, "weight": 0.25},
            {"number": 2, "weight": 0.75},
        ],
        maximum_score=10,
    )
    assert result["correct"] == 1
    assert result["score"] == 2.5
    assert result["percentage"] == 25.0
