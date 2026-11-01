"""Применение сохранённого препроцессора к новому обращению без fit."""
from pathlib import Path
import joblib
import numpy as np
import pandas as pd


def main():
    preprocessor = joblib.load(Path("artifacts/preprocessor.joblib"))
    request = pd.DataFrame({"text": ["Не могу войти, забыла пароль"], "channel": ["web"]})
    features = preprocessor.transform(request)
    print("Обращений:", features.shape[0])
    print("Признаков:", features.shape[1])
    print("Все значения конечные:", bool(np.isfinite(features).all()))
    print("Это подготовка признаков. Предсказание категории пока не выполняется.")


if __name__ == "__main__":
    main()
