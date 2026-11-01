"""Локальный компонент классификации обращений для ЛР 3."""
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.ml.preprocessing import tokenize


class Category(str, Enum):
    TECHNICAL = "TECHNICAL"
    PAYMENT = "PAYMENT"
    STUDY = "STUDY"


class ComponentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ticket_id: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")
    text: str = Field(min_length=1, max_length=5000)

    @field_validator("text")
    @classmethod
    def non_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Текст обращения не должен быть пустым")
        return value


class ComponentResult(BaseModel):
    ticket_id: str
    category: Category | None
    destination: str | None
    needs_human_review: bool
    algorithm_version: str
    matched_words: list[str]


class ModelUnavailableError(RuntimeError):
    """Словарь классификатора недоступен."""


class KeywordClassifier:
    version = "keywords-1.0"
    keywords = {
        Category.TECHNICAL: frozenset({"пароль", "войти", "доступ", "ошибка", "интернет"}),
        Category.PAYMENT: frozenset({"оплата", "оплатить", "платеж", "квитанция", "возврат"}),
        Category.STUDY: frozenset({"расписание", "экзамен", "занятие", "справка", "сессия"}),
    }

    def classify(self, tokens: list[str]) -> tuple[Category | None, list[str]]:
        if not self.keywords:
            raise ModelUnavailableError("Словарь классификатора недоступен")
        words = set(tokens)
        matches = {category: sorted(words & keys) for category, keys in self.keywords.items()}
        count = max(map(len, matches.values()))
        winners = [category for category, hits in matches.items() if len(hits) == count]
        if count == 0 or len(winners) != 1:
            return None, []
        category = winners[0]
        return category, matches[category]


DEPARTMENTS = {
    Category.TECHNICAL: "IT_SUPPORT",
    Category.PAYMENT: "FINANCE",
    Category.STUDY: "STUDENT_OFFICE",
}


class HelpdeskComponent:
    def __init__(self, classifier: KeywordClassifier | None = None):
        self.classifier = classifier if classifier is not None else KeywordClassifier()

    def predict(self, request: ComponentRequest) -> ComponentResult:
        tokens = tokenize(request.text)
        category, matched_words = self.classifier.classify(tokens)
        # Два разных совпадения без ничьей нужны для автоматического маршрута.
        needs_review = category is None or len(matched_words) < 2
        return ComponentResult(
            ticket_id=request.ticket_id,
            category=category,
            destination=None if needs_review else DEPARTMENTS[category],
            needs_human_review=needs_review,
            algorithm_version=self.classifier.version,
            matched_words=matched_words,
        )
