from app.ml.preprocessing import tokenize


class ModelLoader:
    """Заглушка по ключевым словам, а не обученная ML-модель."""
    version = "stub-1.0.0"
    loaded = True
    keywords = {
        "TECHNICAL": {"пароль", "войти", "доступ", "ошибка", "интернет"},
        "PAYMENT": {"оплата", "оплатить", "платеж", "квитанция", "возврат"},
        "STUDY": {"расписание", "экзамен", "занятие", "справка", "сессия"},
    }

    def predict(self, text: str) -> tuple[str, float]:
        tokens = set(tokenize(text))
        scores = {name: len(tokens & words) for name, words in self.keywords.items()}
        best = max(scores, key=scores.get)
        hits = scores[best]
        if hits == 0:
            return "OTHER", 0.40
        if sum(value == hits for value in scores.values()) > 1:
            return "OTHER", 0.50
        # Условная уверенность нужна только для демонстрации маршрутизации.
        return best, 0.90 if hits >= 2 else 0.70
