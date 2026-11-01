import pytest
from pydantic import ValidationError

from app.ml.component import (
    ComponentRequest, HelpdeskComponent, KeywordClassifier, ModelUnavailableError,
)


def predict(text):
    return HelpdeskComponent().predict(ComponentRequest(ticket_id="T-1", text=text))


def test_technical_route():
    result = predict("Не могу войти, забыла пароль")
    assert result.category == "TECHNICAL"
    assert result.destination == "IT_SUPPORT"
    assert result.needs_human_review is False
    assert result.algorithm_version == "keywords-1.0"


def test_payment_route():
    result = predict("Оплата прошла, нужна квитанция")
    assert result.category == "PAYMENT" and result.destination == "FINANCE"


def test_one_match_requires_person():
    result = predict("Забыла пароль")
    assert result.category == "TECHNICAL"
    assert result.destination is None and result.needs_human_review


def test_tie_requires_person():
    result = predict("Пароль и оплата")
    assert result.category is None and result.destination is None
    assert result.needs_human_review


@pytest.mark.parametrize("text", ["", "   ", "a" * 5001])
def test_invalid_text(text):
    with pytest.raises(ValidationError):
        ComponentRequest(ticket_id="T-1", text=text)


def test_missing_classifier_is_explicit_error():
    classifier = KeywordClassifier()
    classifier.keywords = {}
    with pytest.raises(ModelUnavailableError, match="недоступен"):
        HelpdeskComponent(classifier).predict(ComponentRequest(ticket_id="T-1", text="пароль"))
