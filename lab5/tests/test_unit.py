import pytest

from src.prediction import fallback_decision
from src.preprocessing import normalize_text


@pytest.mark.parametrize("text,category,department,manual", [
    ("Не могу войти, забыла пароль", "TECHNICAL", "IT_SUPPORT", False),
    ("Оплата и квитанция", "PAYMENT", "FINANCE", False),
    ("Экзамен и расписание", "STUDY", "STUDENT_OFFICE", False),
    ("Забыла пароль", "TECHNICAL", "OPERATOR", True),
    ("пароль пароль пароль", "TECHNICAL", "OPERATOR", True),
    ("пароль оплата", None, "OPERATOR", True),
    ("абракадабра", None, "OPERATOR", True),
    ("!!!", None, "OPERATOR", True),
])
def test_fallback_threshold(text, category, department, manual):
    result = fallback_decision(text)
    assert (result.category, result.destination, result.manual_review_required) == (category, department, manual)
    assert result.confidence is None


def test_normalization_is_shared():
    assert normalize_text("  Ёж! demo@example.org ") == "еж contact"
