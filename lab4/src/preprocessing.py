"""Общая обработка текста для подготовки и последующего инференса."""
import re


def normalize_text(text: str) -> str:
    text = text.lower().replace("ё", "е")
    text = re.sub(r"[\w.+-]+@[\w.-]+\.[a-zа-я]{2,}", " contact ", text)
    text = re.sub(r"\+?\d[\d ()-]{8,}\d", " contact ", text)
    return " ".join(re.findall(r"[a-zа-я]+", text))


def text_length(values):
    return values.iloc[:, 0].astype(str).map(normalize_text).str.len().to_numpy().reshape(-1, 1)
