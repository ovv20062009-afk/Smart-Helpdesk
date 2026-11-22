"""Однократная загрузка собственного доверенного комплекта артефактов."""
import hashlib
from importlib.metadata import version
import json
from pathlib import Path

import joblib

MODEL_VERSION = "v1.4.0"
PREPROCESSOR_VERSION = "lab4-tfidf-v1"
PACKAGES = ("scikit-learn", "numpy", "pandas", "joblib")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def code_digest(path: Path) -> str:
    return hashlib.sha256(path.read_text(encoding="utf-8").encode("utf-8")).hexdigest()


def load_bundle(root: Path):
    manifest = json.loads((root / "artifacts/manifest.json").read_text(encoding="utf-8"))
    if manifest["model_version"] != MODEL_VERSION:
        raise ValueError("Версия модели не соответствует сервису")
    if manifest["preprocessor_version"] != PREPROCESSOR_VERSION:
        raise ValueError("Версия препроцессора не соответствует сервису")
    for package in PACKAGES:
        if manifest["packages"][package] != version(package):
            raise ValueError(f"Версия {package} отличается от версии обучения")
    paths = {"preprocessor": root / "artifacts/preprocessor.joblib", "model": root / "models/model.joblib",
             "preprocessing_code": root / "src/preprocessing.py"}
    for name, path in paths.items():
        actual = code_digest(path) if name == "preprocessing_code" else digest(path)
        if actual != manifest["sha256"][name]:
            raise ValueError(f"Контрольная сумма {name} не совпала")
    preprocessor = joblib.load(paths["preprocessor"])
    model = joblib.load(paths["model"])
    if model.n_features_in_ != manifest["feature_count"]:
        raise ValueError("Неверное число признаков модели")
    if len(preprocessor.get_feature_names_out()) != model.n_features_in_:
        raise ValueError("Модель и препроцессор несовместимы")
    if set(model.classes_) != {"TECHNICAL", "PAYMENT", "STUDY"}:
        raise ValueError("Неизвестные классы модели")
    if not 0 < manifest["review_threshold"] <= 1:
        raise ValueError("Неверный порог ручной проверки")
    return preprocessor, model, manifest
