"""Обучает небольшой классификатор на готовых признаках из ЛР 4."""
from importlib.metadata import version
import json
from pathlib import Path
import shutil

import joblib
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score

from src.artifacts import digest, code_digest, MODEL_VERSION, PACKAGES, PREPROCESSOR_VERSION


def prepare():
    root = Path(__file__).resolve().parent
    lab4 = root.parent / "lab4"
    required = [lab4 / "data/processed/train.parquet", lab4 / "data/processed/test.parquet",
                lab4 / "artifacts/preprocessor.joblib", lab4 / "src/preprocessing.py"]
    for path in required:
        if not path.exists():
            raise SystemExit(f"Не найден {path}. Сначала выполните конвейер ЛР 4.")
    shared = root / "src/preprocessing.py"
    if code_digest(shared) != code_digest(lab4 / "src/preprocessing.py"):
        raise SystemExit("Обработка текста отличается от ЛР 4. Сначала согласуйте общий модуль.")
    train = pd.read_parquet(required[0])
    test = pd.read_parquet(required[1])
    columns = [name for name in train.columns if name != "category"]
    if columns != [name for name in test.columns if name != "category"]:
        raise SystemExit("Состав признаков train и test отличается")
    classifier = LogisticRegression(C=4.0, max_iter=1000, random_state=42)
    classifier.fit(train[columns].to_numpy(), train["category"])
    predicted = classifier.predict(test[columns].to_numpy())
    source = joblib.load(required[2])
    if len(source.get_feature_names_out()) != len(columns):
        raise SystemExit("Препроцессор не соответствует признакам ЛР 4")
    (root / "artifacts").mkdir(exist_ok=True)
    (root / "models").mkdir(exist_ok=True)
    shutil.copyfile(required[2], root / "artifacts/preprocessor.joblib")
    joblib.dump(classifier, root / "models/model.joblib")
    metrics = {"train_rows": len(train), "test_rows": len(test), "feature_count": len(columns),
               "test_accuracy": float(accuracy_score(test["category"], predicted)),
               "test_macro_f1": float(f1_score(test["category"], predicted, average="macro", zero_division=0))}
    metrics["per_class"] = classification_report(test["category"], predicted, output_dict=True, zero_division=0)
    metrics["classes"] = classifier.classes_.tolist()
    metrics["confusion_matrix"] = confusion_matrix(test["category"], predicted, labels=classifier.classes_).tolist()
    manifest = {"model_version": MODEL_VERSION, "preprocessor_version": PREPROCESSOR_VERSION,
                "algorithm": "LogisticRegression", "C": 4.0, "review_threshold": 0.8,
                "feature_count": len(columns), "packages": {p: version(p) for p in PACKAGES},
                "sha256": {"preprocessor": digest(root / "artifacts/preprocessor.joblib"),
                           "model": digest(root / "models/model.joblib"),
                           "preprocessing_code": code_digest(shared)},
                "training_inputs_sha256": {"train": digest(required[0]), "test": digest(required[1])},
                "source": "lab4", "metrics": metrics}
    (root / "artifacts/manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    (root / "docs").mkdir(exist_ok=True)
    (root / "docs/training_metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    (root / "docs/lab6").mkdir(parents=True, exist_ok=True)
    (root / "docs/lab6/training_metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    print(json.dumps(metrics, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    prepare()
