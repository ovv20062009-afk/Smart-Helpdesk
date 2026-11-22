"""Сервис инференса. Артефакты читаются только при старте приложения."""
from contextlib import asynccontextmanager
import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
import numpy as np
import pandas as pd

from src.artifacts import load_bundle, MODEL_VERSION, PREPROCESSOR_VERSION
from src.schemas import PredictionRequest, PredictionResult

DEPARTMENTS = {"TECHNICAL": "IT_SUPPORT", "PAYMENT": "FINANCE", "STUDY": "STUDENT_OFFICE"}
logger = logging.getLogger(__name__)


def create_app(root: Path | None = None) -> FastAPI:
    root = Path(root) if root is not None else Path(__file__).resolve().parents[1]

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.ready = False
        try:
            preprocessor, model, manifest = load_bundle(root)
            app.state.preprocessor = preprocessor
            app.state.model = model
            app.state.manifest = manifest
            app.state.ready = True
        except Exception:
            logger.exception("Не удалось загрузить комплект артефактов")
        yield
        app.state.ready = False

    app = FastAPI(title="Smart Helpdesk", version=MODEL_VERSION, lifespan=lifespan)

    @app.get("/health")
    def health():
        ready = app.state.ready
        return JSONResponse(status_code=200 if ready else 503, content={
            "status": "ok" if ready else "unavailable", "model_version": MODEL_VERSION,
            "preprocessor_loaded": ready, "model_loaded": ready,
        })

    @app.post("/predict", response_model=PredictionResult)
    def predict(request: PredictionRequest):
        if not app.state.ready:
            raise HTTPException(status_code=503, detail="Модель или препроцессор недоступны")
        frame = pd.DataFrame([{"text": request.text, "channel": request.channel}])
        try:
            preprocessor = app.state.preprocessor
            features = preprocessor.transform(frame)
            lexical = preprocessor.named_transformers_["text"].transform(frame["text"])
            # Без знакомых слов длина текста и канал не дают основания выбирать отдел.
            if lexical.nnz == 0:
                return PredictionResult(ticket_id=request.ticket_id, category=None, confidence=None,
                    destination="OPERATOR", manual_review_required=True, model_version=MODEL_VERSION,
                    preprocessor_version=PREPROCESSOR_VERSION)
            probabilities = app.state.model.predict_proba(features)[0]
            if not np.isfinite(probabilities).all() or (probabilities < 0).any() or (probabilities > 1).any():
                raise ValueError("Модель вернула некорректные вероятности")
            index = int(np.argmax(probabilities))
            category = str(app.state.model.classes_[index])
            confidence = float(probabilities[index])
            review = confidence < app.state.manifest["review_threshold"]
            return PredictionResult(ticket_id=request.ticket_id, category=category, confidence=confidence,
                destination="OPERATOR" if review else DEPARTMENTS[category], manual_review_required=review,
                model_version=MODEL_VERSION, preprocessor_version=PREPROCESSOR_VERSION)
        except Exception as error:
            logger.exception("Ошибка инференса")
            raise HTTPException(status_code=500, detail="Не удалось обработать обращение") from error

    return app


app = create_app()
