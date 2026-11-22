"""Адаптер сохранённой модели. Не зависит от FastAPI."""
from pathlib import Path

from src.artifacts import MODEL_VERSION, load_bundle
from src.prediction import model_decision


class ModelAdapter:
    version = MODEL_VERSION

    def __init__(self):
        self.model = None
        self.preprocessor = None
        self.threshold = 0.8
        self.last_error = False

    def load(self, root: Path):
        preprocessor, model, manifest = load_bundle(root)
        self.preprocessor = preprocessor
        self.model = model
        self.threshold = manifest["review_threshold"]

    @property
    def ready(self):
        return self.model is not None and self.preprocessor is not None and not self.last_error

    def predict(self, payload):
        if self.model is None or self.preprocessor is None:
            raise RuntimeError("Артефакты недоступны")
        return model_decision(payload.text, payload.channel, self.preprocessor, self.model, self.threshold)
