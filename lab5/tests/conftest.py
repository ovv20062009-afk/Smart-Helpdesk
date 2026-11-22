"""Настройка тестов. Значения здесь не являются рабочими токенами."""
import pytest


@pytest.fixture(autouse=True)
def test_credentials(monkeypatch, request):
    if request.node.path.name == "test_container.py":
        return
    monkeypatch.setenv("APP_DEMO_TOKEN", "unit-test-only")
    monkeypatch.setenv("APP_READONLY_TOKEN", "unit-readonly-only")
    monkeypatch.delenv("HELPDESK_DISABLE_MODEL", raising=False)
