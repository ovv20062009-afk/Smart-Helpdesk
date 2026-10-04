from uuid import uuid4
from app.api.schemas import PredictionRequest, PredictionResponse
from app.ml.inference import ModelLoader

DESTINATIONS = {
    "TECHNICAL": "IT_SUPPORT",
    "PAYMENT": "FINANCE",
    "STUDY": "STUDENT_OFFICE",
    "OTHER": "OPERATOR",
}


def build_prediction(request: PredictionRequest, model: ModelLoader) -> PredictionResponse:
    category, confidence = model.predict(request.text)
    manual_review = confidence < 0.80
    return PredictionResponse(
        request_id=str(uuid4()), ticket_id=request.ticket_id,
        category=category, confidence=confidence,
        destination="OPERATOR" if manual_review else DESTINATIONS[category],
        manual_review_required=manual_review, model_version=model.version,
    )
