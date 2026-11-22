from copy import deepcopy
import pytest

BODY = {
    "trace_id": "2ff952d6-ca63-4b28-b254-8e90fbee96f0", "ticket_id": "T-8",
    "prediction": {"category": "TECHNICAL", "confidence": 0.72, "destination": "OPERATOR",
        "manual_review_required": True, "threshold_used": 0.8, "matched_words": []},
    "metadata": {"model_version": "v1.4.0", "preprocessor_version": "lab4-tfidf-v1",
        "timestamp_utc": "2026-11-22T08:35:18.752230Z", "latency_ms": 16.941,
        "source": "model", "degraded": False}}
PAYLOAD = {"ticket_id": "T-8", "text": "Не могу войти, забыла пароль", "channel": "web"}


@pytest.fixture
def body():
    return deepcopy(BODY)


@pytest.fixture
def payload():
    return dict(PAYLOAD)


@pytest.fixture
def fallback(body):
    body["prediction"].update(confidence=None, destination="IT_SUPPORT", manual_review_required=False,
                              matched_words=["войти", "пароль"])
    body["metadata"].update(source="fallback_rule", degraded=True)
    return body
