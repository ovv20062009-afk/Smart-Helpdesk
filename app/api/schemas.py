from pydantic import BaseModel, ConfigDict, Field, field_validator


class PredictionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ticket_id: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")
    text: str = Field(min_length=1, max_length=5000)

    @field_validator("text")
    @classmethod
    def text_must_not_be_blank(cls, value):
        if not value.strip():
            raise ValueError("Текст обращения не должен быть пустым")
        return value


class PredictionResponse(BaseModel):
    request_id: str
    ticket_id: str
    category: str
    confidence: float = Field(ge=0, le=1)
    destination: str
    manual_review_required: bool
    model_version: str


class HealthResponse(BaseModel):
    status: str
    model_loaded: bool
    model_version: str
    uptime_seconds: float
