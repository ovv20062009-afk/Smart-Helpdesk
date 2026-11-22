"""Предсказание и отдельное резервное правило маршрутизации."""
from dataclasses import dataclass

import numpy as np
import pandas as pd

from src.preprocessing import normalize_text

DEPARTMENTS = {"TECHNICAL": "IT_SUPPORT", "PAYMENT": "FINANCE", "STUDY": "STUDENT_OFFICE"}
KEYWORDS = {
    "TECHNICAL": {"пароль", "войти", "доступ", "ошибка", "интернет"},
    "PAYMENT": {"оплата", "оплатить", "платеж", "квитанция", "возврат"},
    "STUDY": {"расписание", "экзамен", "занятие", "справка", "сессия"},
}
FALLBACK_MIN_MATCHES = 2


@dataclass(frozen=True)
class Decision:
    category: str | None
    confidence: float | None
    destination: str
    manual_review_required: bool
    matched_words: tuple[str, ...] = ()


def fallback_decision(text: str) -> Decision:
    words = set(normalize_text(text).split())
    hits = {category: sorted(words & keywords) for category, keywords in KEYWORDS.items()}
    count = max(map(len, hits.values()))
    winners = [category for category, matched in hits.items() if len(matched) == count]
    if count == 0 or len(winners) != 1:
        return Decision(None, None, "OPERATOR", True)
    category = winners[0]
    manual = count < FALLBACK_MIN_MATCHES
    return Decision(category, None, "OPERATOR" if manual else DEPARTMENTS[category], manual,
                    tuple(hits[category]))


def model_decision(text: str, channel: str, preprocessor, model, threshold: float) -> Decision:
    frame = pd.DataFrame([{"text": text, "channel": channel}])
    features = preprocessor.transform(frame)
    lexical = preprocessor.named_transformers_["text"].transform(frame["text"])
    probabilities = np.asarray(model.predict_proba(features))
    if probabilities.shape != (1, len(model.classes_)):
        raise ValueError("Неверная форма ответа модели")
    row = probabilities[0]
    if (not np.isfinite(row).all() or (row < 0).any() or (row > 1).any()
            or not np.isclose(row.sum(), 1.0)):
        raise ValueError("Некорректные вероятности модели")
    if lexical.nnz == 0:
        return Decision(None, None, "OPERATOR", True)
    index = int(np.argmax(row))
    category = str(model.classes_[index])
    confidence = float(row[index])
    manual = confidence < threshold
    return Decision(category, confidence, "OPERATOR" if manual else DEPARTMENTS[category], manual)
