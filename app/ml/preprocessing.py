import re


def tokenize(text: str) -> list[str]:
    """Упрощённая очистка и токенизация; общий модуль для модели и API."""
    text = text.lower().replace("ё", "е")
    text = re.sub(r"[\w.+-]+@[\w.-]+\.[a-zа-я]{2,}", " contact ", text)
    text = re.sub(r"\+?\d[\d ()-]{8,}\d", " contact ", text)
    return re.findall(r"[a-zа-я]+", text)
