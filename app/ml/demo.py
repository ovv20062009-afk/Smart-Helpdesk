"""Локальная демонстрация компонента ЛР 3."""
from pydantic import ValidationError

from app.ml.component import ComponentRequest, HelpdeskComponent


def main():
    component = HelpdeskComponent()
    for number, text in enumerate((
        "Не могу войти, забыла пароль",
        "Оплата прошла, нужна квитанция",
        "Забыла пароль",
        "",
    ), 1):
        try:
            result = component.predict(ComponentRequest(ticket_id=f"T-{number}", text=text))
            print(result.model_dump_json())
        except ValidationError:
            print(f"T-{number}: ошибка входа, текст пустой")


if __name__ == "__main__":
    main()
