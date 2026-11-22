from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, UUID4, field_validator

from src.preprocessing import normalize_text


class Category(str, Enum):
    TECHNICAL = "TECHNICAL"
    PAYMENT = "PAYMENT"
    STUDY = "STUDY"


class PredictionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ticket_id: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_-]+$",
                           description="Идентификатор обращения: латиница, цифры, дефис и подчёркивание")
    text: str = Field(min_length=1, max_length=5000, description="Текст обращения, содержащий слова")
    channel: Literal["web", "email", "chat"] = Field(default="web", description="Канал поступления обращения")

    @field_validator("text")
    @classmethod
    def meaningful_text(cls, value: str) -> str:
        if not normalize_text(value):
            raise ValueError("Текст должен содержать слова")
        return value


class PredictionResult(BaseModel):
    trace_id: UUID4 = Field(description="Сквозной UUID4 для поиска запроса в JSON-логах")
    ticket_id: str = Field(description="Идентификатор исходного обращения")
    category: Category | None = Field(description="Предложенная категория или null при неоднозначности")
    confidence: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False,
                                     description="Вероятность модели; null для эвристики и неизвестных слов")
    destination: Literal["IT_SUPPORT", "FINANCE", "STUDENT_OFFICE", "OPERATOR"] = Field(
        description="Предложенный отдел или очередь оператора")
    manual_review_required: bool = Field(description="Нужно ли проверить решение вручную")
    model_version: str = Field(description="Версия комплекта модели и сервиса")
    preprocessor_version: str = Field(description="Версия преобразований из ЛР 4")
    source: Literal["model", "fallback_rule"] = Field(description="Модель или резервная эвристика")
    latency_ms: float = Field(ge=0, allow_inf_nan=False, description="Время подготовки результата в миллисекундах")
    matched_words: list[str] = Field(default_factory=list, description="Ключевые слова резервного правила")
