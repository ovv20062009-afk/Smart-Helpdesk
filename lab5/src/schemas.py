from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator
from src.preprocessing import normalize_text


class Category(str, Enum):
    TECHNICAL = "TECHNICAL"
    PAYMENT = "PAYMENT"
    STUDY = "STUDY"


class PredictionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ticket_id: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")
    text: str = Field(min_length=1, max_length=5000)
    channel: Literal["web", "email", "chat"] = "web"

    @field_validator("text")
    @classmethod
    def meaningful_text(cls, value: str) -> str:
        if not normalize_text(value):
            raise ValueError("Текст должен содержать слова")
        return value


class PredictionResult(BaseModel):
    ticket_id: str
    category: Category | None
    confidence: float | None = Field(default=None, ge=0, le=1)
    destination: Literal["IT_SUPPORT", "FINANCE", "STUDENT_OFFICE", "OPERATOR"]
    manual_review_required: bool
    model_version: str
    preprocessor_version: str
