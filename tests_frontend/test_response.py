import pytest
from pydantic import ValidationError

from frontend.response_validation import ApiResponse


@pytest.mark.parametrize("field,value", [("confidence", float("nan")), ("confidence", float("inf")),
    ("confidence", -0.1), ("confidence", 1.1), ("confidence", "0.7"), ("confidence", True),
    ("threshold_used", 0), ("threshold_used", float("nan")), ("manual_review_required", "false"),
    ("destination", "UNKNOWN"), ("category", "OTHER")])
def test_bad_prediction(body, field, value):
    body["prediction"][field] = value
    with pytest.raises(ValidationError):
        ApiResponse.model_validate(body)


@pytest.mark.parametrize("field,value", [("latency_ms", float("inf")), ("latency_ms", -1),
    ("degraded", "false"), ("model_version", ""), ("source", "unknown"),
    ("timestamp_utc", "2026-11-22T08:35:18"), ("timestamp_utc", "2026-11-22T08:35:18+03:00")])
def test_bad_metadata(body, field, value):
    body["metadata"][field] = value
    with pytest.raises(ValidationError):
        ApiResponse.model_validate(body)


def test_model_unknown_words_have_no_score(body):
    body["prediction"].update(category=None, confidence=None)
    result = ApiResponse.model_validate(body)
    assert result.prediction.confidence is None and result.prediction.manual_review_required


@pytest.mark.parametrize("change", [
    {"confidence": None}, {"manual_review_required": False}, {"destination": "IT_SUPPORT"},
    {"matched_words": ["пароль"]},
])
def test_model_must_match_threshold(body, change):
    body["prediction"].update(change)
    with pytest.raises(ValidationError):
        ApiResponse.model_validate(body)


def test_threshold_boundary_can_route(body):
    body["prediction"].update(confidence=0.8, manual_review_required=False, destination="IT_SUPPORT")
    assert not ApiResponse.model_validate(body).prediction.manual_review_required


@pytest.mark.parametrize("change", [
    {"confidence": 0}, {"manual_review_required": True}, {"destination": "OPERATOR"},
    {"matched_words": ["пароль", "пароль"]}, {"matched_words": []},
])
def test_fallback_consistency(fallback, change):
    fallback["prediction"].update(change)
    with pytest.raises(ValidationError):
        ApiResponse.model_validate(fallback)


def test_fallback_cannot_hide_degradation(fallback):
    fallback["metadata"]["degraded"] = False
    with pytest.raises(ValidationError):
        ApiResponse.model_validate(fallback)


def test_single_word_rule_requires_operator(fallback):
    fallback["prediction"].update(matched_words=["пароль"], manual_review_required=True, destination="OPERATOR")
    assert ApiResponse.model_validate(fallback).prediction.confidence is None
