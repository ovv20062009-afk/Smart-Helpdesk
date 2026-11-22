"""REST API Smart Helpdesk: доступ, квота, модель и явный резервный режим."""
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import os
from pathlib import Path
from threading import Lock
import time
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Request, Security
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from src.artifacts import MODEL_VERSION, PREPROCESSOR_VERSION
from src.limiter import MemoryRateLimiter, RateLimitExceeded
from src.logger import get_json_logger, trace_context
from src.model_adapter import ModelAdapter
from src.prediction import fallback_decision
from src.schemas import PredictionMetadata, PredictionOutput, PredictionRequest, PredictionResult, RoutingPrediction
from src.security import Client, TokenConfig, require_predict

logger = get_json_logger()
SAFE_PATHS = {"/health", "/ready", "/api/v1/predict", "/predict", "/docs", "/openapi.json", "/redoc"}
ERROR_RESPONSES = {
    401: {"description": "Отсутствует или неверен Bearer-токен; WWW-Authenticate: Bearer"},
    403: {"description": "Клиент установлен, но прогноз ему запрещён"},
    422: {"description": "Вход не соответствует схеме"},
    429: {"description": "Исчерпана квота клиента; Retry-After в секундах"},
    503: {"description": "Не настроен доступ либо недоступны модель и резервное правило"},
}


def get_limiter(request: Request):
    return request.app.state.limiter


def admitted_client(request: Request, client: Client = Security(require_predict),
                    limiter=Depends(get_limiter)):
    try:
        limiter.check(client.client_id)
    except RateLimitExceeded as error:
        raise HTTPException(429, "Лимит запросов исчерпан", headers={"Retry-After": str(error.retry_after)}) from None
    return client


def create_app(root: Path | None = None) -> FastAPI:
    root = Path(root) if root is not None else Path(__file__).resolve().parents[1]

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.tokens = TokenConfig.from_environment()
        app.state.limiter = MemoryRateLimiter(limit=60, window_seconds=60)
        app.state.inference_lock = Lock()
        app.state.adapter = ModelAdapter()
        try:
            if os.environ.get("HELPDESK_DISABLE_MODEL") == "1":
                raise RuntimeError("Модель отключена для проверки Fallback")
            app.state.adapter.load(root)
            logger.info("artifacts_loaded", extra={"extra_data": {"model_version": MODEL_VERSION}})
        except Exception as error:
            app.state.adapter.last_error = True
            logger.warning("artifacts_unavailable", extra={"extra_data": {
                "error_type": type(error).__name__, "model_version": MODEL_VERSION}})
        yield
        app.state.adapter = None

    app = FastAPI(title="Smart Helpdesk", version=MODEL_VERSION, lifespan=lifespan,
                  description="Учебная маршрутизация обращений. Bearer-доступ, 60 допусков за 60 секунд, явный Fallback.")

    @app.middleware("http")
    async def trace_request(request: Request, call_next):
        trace_id = str(uuid4())
        token = trace_context.set(trace_id)
        request.state.trace_id = trace_id
        request.state.started = time.perf_counter()
        request.state.log_fields = {}
        try:
            try:
                response = await call_next(request)
            except Exception as error:
                request.state.log_fields["error_type"] = type(error).__name__
                response = JSONResponse(status_code=500, content={"detail": "Ошибка сервиса", "trace_id": trace_id})
            response.headers["X-Trace-ID"] = trace_id
            fields = {"trace_id": trace_id, "method": request.method,
                      "path": request.url.path if request.url.path in SAFE_PATHS else "other",
                      "status_code": response.status_code,
                      "latency_ms": round((time.perf_counter() - request.state.started) * 1000, 3),
                      "model_version": MODEL_VERSION}
            fields.update(request.state.log_fields)
            logger.info("request_complete", extra={"extra_data": fields})
            return response
        finally:
            trace_context.reset(token)

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, error: HTTPException):
        return JSONResponse(status_code=error.status_code,
                            content={"detail": error.detail, "trace_id": request.state.trace_id},
                            headers=error.headers)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, error: RequestValidationError):
        details = [{"type": item["type"], "loc": item["loc"], "msg": item["msg"]}
                   for item in error.errors()]
        return JSONResponse(status_code=422, content={"detail": details, "trace_id": request.state.trace_id})

    @app.get("/health", tags=["Monitoring"], summary="Проверить, что процесс отвечает")
    def health(request: Request):
        with app.state.inference_lock:
            adapter = app.state.adapter
            return {"status": "ok" if adapter.ready else "degraded", "process_alive": True,
                    "model_version": MODEL_VERSION, "trace_id": request.state.trace_id,
                    "model_loaded": adapter.model is not None,
                    "preprocessor_loaded": adapter.preprocessor is not None, "fallback_available": True}

    @app.get("/ready", tags=["Monitoring"], summary="Проверить готовность модели и настройки доступа",
             responses={503: {"description": "Модель или настройка доступа не готовы"}})
    def ready(request: Request):
        with app.state.inference_lock:
            adapter = app.state.adapter
            model_ready = adapter.ready
            configured = app.state.tokens.configured
            return JSONResponse(status_code=200 if model_ready and configured else 503, content={
                "status": "ready" if model_ready and configured else "not_ready",
                "model_loaded": adapter.model is not None,
                "preprocessor_loaded": adapter.preprocessor is not None,
                "model_ready": model_ready, "auth_configured": configured,
                "model_version": MODEL_VERSION, "trace_id": request.state.trace_id})

    def calculate(payload: PredictionRequest, request: Request):
        started = time.perf_counter()
        with app.state.inference_lock:
            adapter = app.state.adapter
            source = "model"
            try:
                decision = adapter.predict(payload)
                adapter.last_error = False
            except Exception as error:
                adapter.last_error = True
                source = "fallback_rule"
                logger.warning("fallback_activated", extra={"extra_data": {
                    "trace_id": request.state.trace_id, "ticket_id": payload.ticket_id,
                    "source": source, "error_type": type(error).__name__, "model_version": MODEL_VERSION}})
                try:
                    decision = fallback_decision(payload.text)
                except Exception as fallback_error:
                    logger.error("fallback_unavailable", extra={"extra_data": {
                        "error_type": type(fallback_error).__name__}})
                    raise HTTPException(503, "Оценка недоступна") from None
            elapsed = round((time.perf_counter() - started) * 1000, 3)
            try:
                output = PredictionOutput(
                    trace_id=request.state.trace_id, ticket_id=payload.ticket_id,
                    prediction=RoutingPrediction(category=decision.category, confidence=decision.confidence,
                        destination=decision.destination, manual_review_required=decision.manual_review_required,
                        threshold_used=adapter.threshold, matched_words=list(decision.matched_words)),
                    metadata=PredictionMetadata(model_version=adapter.version, preprocessor_version=PREPROCESSOR_VERSION,
                        timestamp_utc=datetime.now(timezone.utc), latency_ms=elapsed,
                        source=source, degraded=source == "fallback_rule"))
            except (TypeError, ValueError, AttributeError):
                adapter.last_error = True
                raise HTTPException(503, "Некорректный результат обработки") from None
        request.state.log_fields = {"ticket_id": payload.ticket_id, "source": source,
            "category": output.prediction.category, "destination": output.prediction.destination,
            "manual_review_required": output.prediction.manual_review_required,
            "latency_ms": elapsed}
        return output

    @app.post("/api/v1/predict", tags=["Inference"], response_model=PredictionOutput,
              responses=ERROR_RESPONSES, summary="Предложить категорию и отдел")
    def predict(payload: PredictionRequest, request: Request, client=Depends(admitted_client)):
        return calculate(payload, request)

    @app.post("/predict", tags=["Inference"], response_model=PredictionResult,
              responses=ERROR_RESPONSES, deprecated=True,
              summary="Прежний формат ответа, с теми же доступом и квотой")
    def legacy_predict(payload: PredictionRequest, request: Request, client=Depends(admitted_client)):
        output = calculate(payload, request)
        return PredictionResult(trace_id=output.trace_id, ticket_id=output.ticket_id,
            **output.prediction.model_dump(exclude={"threshold_used"}),
            **output.metadata.model_dump(exclude={"timestamp_utc", "degraded"}))

    return app


app = create_app()
