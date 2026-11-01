from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import pytest
from pandera.errors import SchemaErrors

from src.make_sample import make_sample
from src.pipeline import build_preprocessor, clean_data, prepare, split_data
from src.preprocessing import normalize_text


def sample(tmp_path):
    path = make_sample(tmp_path / "tickets.csv")
    return pd.read_csv(path, parse_dates=["created_at"])


def test_cleaning_counts_and_duplicates(tmp_path):
    clean, report = clean_data(sample(tmp_path))
    assert report == {"raw_rows": 64, "empty_rows": 2, "duplicate_rows": 2, "clean_rows": 60}
    assert not clean["text"].duplicated().any()


@pytest.mark.parametrize("column,value", [("category", "UNKNOWN"), ("channel", "sms"),
                                         ("text", "a" * 5001), ("ticket_id", "BAD")])
def test_contract_rejects_invalid_values(tmp_path, column, value):
    raw = sample(tmp_path)
    raw.loc[0, column] = value
    with pytest.raises(SchemaErrors):
        clean_data(raw)


def test_conflicting_labels_are_rejected(tmp_path):
    raw = sample(tmp_path)
    raw.loc[60, "category"] = "PAYMENT"
    with pytest.raises(ValueError, match="разные категории"):
        clean_data(raw)


def test_time_split_has_no_overlap(tmp_path):
    clean, _ = clean_data(sample(tmp_path))
    train, test = split_data(clean, 0.8)
    assert (len(train), len(test)) == (48, 12)
    assert train.created_at.max() < test.created_at.min()
    assert set(train.text).isdisjoint(test.text)


def test_test_vocabulary_does_not_enter_train_and_reload_works(tmp_path):
    train = pd.DataFrame({"text": ["пароль доступ", "оплата квитанция", "экзамен расписание"],
                          "channel": ["web", np.nan, "chat"]})
    test = pd.DataFrame({"text": ["уникальноесловотеста"], "channel": ["new_channel"]})
    transformer = build_preprocessor(500, 2)
    transformer.fit_transform(train)
    before = transformer.named_transformers_["text"].vocabulary_.copy()
    transformed = transformer.transform(test)
    assert "уникальноесловотеста" not in before
    assert transformer.named_transformers_["text"].vocabulary_ == before
    assert not np.isnan(transformed).any()
    # Масштабировщик знает только среднюю длину обучающих текстов.
    assert transformer.named_transformers_["length"].named_steps["scale"].mean_[0] == train.text.str.len().mean()
    noisy = pd.DataFrame({"text": ["  ПАРОЛЬ!!! Доступ?  "], "channel": ["web"]})
    normal = pd.DataFrame({"text": ["пароль доступ"], "channel": ["web"]})
    np.testing.assert_allclose(transformer.transform(noisy), transformer.transform(normal))
    path = tmp_path / "preprocessor.joblib"
    joblib.dump(transformer, path)
    np.testing.assert_allclose(joblib.load(path).transform(test), transformed)


def test_contacts_and_letters_are_normalized():
    assert normalize_text("  Ёж! Пишите demo@example.org  ") == "еж пишите contact"


def test_end_to_end_exports_and_mlflow(tmp_path):
    make_sample(tmp_path / "data/raw/tickets.csv")
    params = Path("params.yaml").read_bytes()
    (tmp_path / "params.yaml").write_bytes(params)
    report = prepare(tmp_path)
    assert report["train_rows"] == 48 and report["text_overlap"] == 0
    assert (tmp_path / "artifacts/preprocessor.joblib").exists()
    train = pd.read_parquet(tmp_path / "data/processed/train.parquet")
    assert len(train) == 48 and not train.isna().any().any()
    import json
    run = json.loads((tmp_path / "data/processed/mlflow_run.json").read_text())
    assert run["status"] == "FINISHED"
    assert run["params"]["split_strategy"] == "time_ordered"
    assert "preprocessor.joblib" in run["artifacts"]
