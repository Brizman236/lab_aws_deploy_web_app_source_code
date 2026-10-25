"""Configuration de l'application, lue exclusivement depuis l'environnement.

Aucune valeur spécifique à un environnement n'est codée en dur ici. Le seul
contrat avec l'extérieur est l'ensemble des variables d'environnement listées
dans `.env.example`. Que ces variables viennent d'un fichier .env, de systemd,
d'un script de démarrage ou d'AWS Systems Manager Parameter Store (injectées
au démarrage), le code applicatif ne change pas.
"""
from __future__ import annotations

import os
from dataclasses import dataclass


class ConfigError(RuntimeError):
    """Configuration absente ou invalide."""


def _get_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Config:
    app_env: str
    app_name: str
    database_url: str
    log_level: str
    asset_base_url: str
    storage_backend: str
    local_image_dir: str
    secret_key: str
    items_per_page: int
    trusted_proxy_hops: int

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


def load_config(overrides: dict | None = None) -> Config:
    """Construit la configuration depuis os.environ (+ surcharges pour les tests)."""
    env = dict(os.environ)
    if overrides:
        env.update(overrides)

    app_env = env.get("APP_ENV", "development").strip().lower()
    if app_env not in {"development", "testing", "production"}:
        raise ConfigError(f"APP_ENV invalide : {app_env!r}")

    database_url = env.get("DATABASE_URL", "").strip()
    if not database_url:
        raise ConfigError("DATABASE_URL est obligatoire (voir .env.example).")

    secret_key = env.get("SECRET_KEY", "").strip()
    if not secret_key:
        if app_env == "production":
            raise ConfigError("SECRET_KEY est obligatoire en production.")
        # Valeur éphémère non secrète, uniquement pour le développement/les tests.
        secret_key = "dev-only-not-a-secret"

    try:
        items_per_page = int(env.get("ITEMS_PER_PAGE", "12"))
    except ValueError as exc:
        raise ConfigError("ITEMS_PER_PAGE doit être un entier.") from exc
    if items_per_page < 1 or items_per_page > 100:
        raise ConfigError("ITEMS_PER_PAGE doit être compris entre 1 et 100.")

    try:
        trusted_proxy_hops = int(env.get("TRUSTED_PROXY_HOPS", "0"))
    except ValueError as exc:
        raise ConfigError("TRUSTED_PROXY_HOPS doit être un entier.") from exc
    if trusted_proxy_hops < 0 or trusted_proxy_hops > 5:
        raise ConfigError("TRUSTED_PROXY_HOPS doit être compris entre 0 et 5.")

    storage_backend = env.get("STORAGE_BACKEND", "local").strip().lower()
    if storage_backend not in {"local", "remote"}:
        raise ConfigError("STORAGE_BACKEND doit valoir 'local' ou 'remote'.")

    return Config(
        app_env=app_env,
        app_name=env.get("APP_NAME", "TechSahel Catalogue").strip(),
        database_url=database_url,
        log_level=env.get("LOG_LEVEL", "INFO").strip().upper(),
        asset_base_url=env.get("ASSET_BASE_URL", "/static/images").strip().rstrip("/"),
        storage_backend=storage_backend,
        local_image_dir=env.get("LOCAL_IMAGE_DIR", "static/images").strip(),
        secret_key=secret_key,
        items_per_page=items_per_page,
        trusted_proxy_hops=trusted_proxy_hops,
    )
