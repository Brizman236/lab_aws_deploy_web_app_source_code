"""Démarrage, pages publiques, health, en-têtes de sécurité."""
import pytest

from catalog import create_app
from catalog.config import ConfigError, load_config


def test_app_starts_and_home_renders(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "TechSahel" in r.get_data(as_text=True)


@pytest.mark.parametrize("path", ["/", "/produits", "/contact", "/a-propos", "/merci"])
def test_public_pages_ok(client, path):
    assert client.get(path).status_code == 200


def test_unknown_page_returns_custom_404(client):
    r = client.get("/page-inexistante")
    assert r.status_code == 404
    assert "Page introuvable" in r.get_data(as_text=True)


def test_health_ok(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.is_json
    assert r.get_json()["status"] == "ok"
    assert r.get_json()["database"] == "up"


def test_health_degraded_when_database_down(test_db_url):
    # Port fermé : l'application doit répondre 503 « degraded », sans lever d'exception.
    app = create_app({"DATABASE_URL": "postgresql://nobody@127.0.0.1:1/none",
                      "APP_ENV": "testing", "LOG_LEVEL": "CRITICAL"})
    c = app.test_client()
    r = c.get("/health")
    assert r.status_code == 503
    body = r.get_json()
    assert body["status"] == "degraded" and body["database"] == "down"
    assert c.get("/health/live").status_code == 200  # le processus, lui, est vivant


def test_catalog_shows_friendly_503_when_database_down():
    app = create_app({"DATABASE_URL": "postgresql://nobody@127.0.0.1:1/none",
                      "APP_ENV": "testing", "LOG_LEVEL": "CRITICAL"})
    r = app.test_client().get("/produits")
    assert r.status_code == 503
    assert "indisponible" in r.get_data(as_text=True)


def test_security_headers(client):
    r = client.get("/")
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["X-Frame-Options"] == "DENY"
    assert "default-src 'self'" in r.headers["Content-Security-Policy"]
    assert r.headers["X-Request-Id"]


def test_config_requires_database_url(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(ConfigError):
        load_config()


def test_config_production_requires_secret_key():
    with pytest.raises(ConfigError):
        load_config({"APP_ENV": "production", "DATABASE_URL": "postgresql://x", "SECRET_KEY": ""})


@pytest.mark.parametrize("overrides", [
    {"APP_ENV": "staging-chaos"}, {"ITEMS_PER_PAGE": "abc"}, {"STORAGE_BACKEND": "ftp"},
])
def test_config_rejects_invalid_values(overrides):
    with pytest.raises(ConfigError):
        load_config({"DATABASE_URL": "postgresql://x", **overrides})


def test_config_reads_environment():
    cfg = load_config({"DATABASE_URL": "postgresql://x", "APP_NAME": "Autre", "ASSET_BASE_URL": "https://cdn.example/img/"})
    assert cfg.app_name == "Autre"
    assert cfg.asset_base_url == "https://cdn.example/img"  # slash final retiré
