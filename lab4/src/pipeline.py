"""Загрузка, проверка, очистка, split и обучение общего препроцессора."""
import hashlib
import json
from pathlib import Path

import joblib
import mlflow
import numpy as np
import pandas as pd
import yaml
from mlflow.tracking import MlflowClient
from pandera.errors import SchemaError, SchemaErrors
from sklearn.compose import ColumnTransformer
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import FunctionTransformer, OneHotEncoder, StandardScaler

from src.contracts import CATEGORIES, RawTicketsSchema
from src.preprocessing import normalize_text, text_length


def clean_data(raw):
    data = RawTicketsSchema.validate(raw, lazy=True).copy()
    data["text"] = data["text"].fillna("").map(normalize_text)
    empty = data["text"].eq("")
    removed_empty = int(empty.sum())
    data = data.loc[~empty].sort_values(["created_at", "ticket_id"])
    if (data.groupby("text")["category"].nunique() > 1).any():
        raise ValueError("Одинаковым текстам назначены разные категории")
    before = len(data)
    data = data.drop_duplicates(subset=["text"], keep="first").reset_index(drop=True)
    return data, {"raw_rows": len(raw), "empty_rows": removed_empty,
                  "duplicate_rows": before - len(data), "clean_rows": len(data)}


def split_data(clean, train_share):
    if not 0 < train_share < 1:
        raise ValueError("train_share должна находиться между 0 и 1")
    cut = int(len(clean) * train_share)
    if cut == 0 or cut == len(clean):
        raise ValueError("Недостаточно данных для двух выборок")
    # Одинаковое время нельзя разделять между train и test.
    boundary = clean.iloc[cut]["created_at"]
    train = clean.loc[clean["created_at"] < boundary].copy()
    test = clean.loc[clean["created_at"] >= boundary].copy()
    if train.empty or test.empty:
        raise ValueError("Для временного разделения нужны разные даты")
    if set(train["category"]) != set(CATEGORIES):
        raise ValueError("В обучающей выборке должны присутствовать все категории")
    return train, test


def build_preprocessor(max_features, ngram_max):
    return ColumnTransformer([
        ("text", TfidfVectorizer(preprocessor=normalize_text,
                                max_features=max_features, ngram_range=(1, ngram_max)), "text"),
        ("length", Pipeline([
            ("length", FunctionTransformer(text_length, feature_names_out="one-to-one")),
            ("scale", StandardScaler()),
        ]), ["text"]),
        ("channel", Pipeline([
            ("fill", SimpleImputer(strategy="most_frequent")),
            ("encode", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
        ]), ["channel"]),
    ], sparse_threshold=0)


def prepare(root=Path(".")):
    root = Path(root).resolve()
    params = yaml.safe_load((root / "params.yaml").read_text(encoding="utf-8"))["prepare"]
    raw_path = root / "data/raw/tickets.csv"
    raw = pd.read_csv(raw_path, parse_dates=["created_at"])
    clean, report = clean_data(raw)
    train, test = split_data(clean, params["train_share"])
    features = ["text", "channel"]
    preprocessor = build_preprocessor(params["max_features"], params["ngram_max"])
    x_train = preprocessor.fit_transform(train[features])
    x_test = preprocessor.transform(test[features])  # Здесь нет fit.
    out, artifacts = root / "data/processed", root / "artifacts"
    out.mkdir(parents=True, exist_ok=True)
    artifacts.mkdir(parents=True, exist_ok=True)
    for frame, matrix, name in ((train, x_train, "train"), (test, x_test, "test")):
        transformed = pd.DataFrame(matrix, columns=[f"feature_{i:03d}" for i in range(matrix.shape[1])])
        transformed["category"] = frame["category"].to_numpy()
        transformed.to_parquet(out / f"{name}.parquet", index=False)
    joblib.dump(preprocessor, artifacts / "preprocessor.joblib")
    names = preprocessor.get_feature_names_out().tolist()
    (artifacts / "feature_names.json").write_text(json.dumps(names, ensure_ascii=False, indent=2), encoding="utf-8")
    split = {name: frame["ticket_id"].tolist() for name, frame in (("train", train), ("test", test))}
    (out / "split_ids.json").write_text(json.dumps(split, indent=2), encoding="utf-8")
    overlap = len(set(train["text"]) & set(test["text"]))
    report.update(train_rows=len(train), test_rows=len(test), feature_count=x_train.shape[1],
                  text_overlap=overlap, missing_values=int(np.isnan(x_train).sum() + np.isnan(x_test).sum()))
    report_path = out / "validation_report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    if overlap or report["missing_values"]:
        raise ValueError("Нарушена проверка пересечений или пропусков")
    mlflow.set_tracking_uri("sqlite:///" + (root / "mlflow.db").as_posix())
    experiment_name = "lab4-smart-helpdesk"
    client = MlflowClient()
    experiment = client.get_experiment_by_name(experiment_name)
    experiment_id = (experiment.experiment_id if experiment else
                     client.create_experiment(experiment_name, artifact_location=(root / "mlruns").as_uri()))
    with mlflow.start_run(experiment_id=experiment_id) as run:
        logged_params = dict(params, split_strategy="time_ordered", algorithm="tfidf-length-channel",
                             dataset_sha256=hashlib.sha256(raw_path.read_bytes()).hexdigest())
        mlflow.log_params(logged_params)
        mlflow.log_metrics(report)
        for path in (report_path, artifacts / "preprocessor.joblib", artifacts / "feature_names.json",
                     out / "split_ids.json", root / "params.yaml"):
            mlflow.log_artifact(str(path))
    saved = client.get_run(run.info.run_id)
    exported = {"run_id": saved.info.run_id, "experiment": experiment_name,
                    "status": saved.info.status, "params": saved.data.params, "metrics": saved.data.metrics,
                    "artifacts": [item.path for item in client.list_artifacts(saved.info.run_id)]}
    (out / "mlflow_run.json").write_text(json.dumps(exported, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print("MLflow Run:", exported["run_id"])
    return report


if __name__ == "__main__":
    try:
        prepare()
    except (SchemaError, SchemaErrors, ValueError, FileNotFoundError) as error:
        raise SystemExit(f"Ошибка подготовки данных: {error}") from error
