"""Application Flask : fabrique `create_app`."""
from __future__ import annotations

import logging
import time
import uuid
from dataclasses import replace
from pathlib import Path
from urllib.parse import urlparse

import psycopg
from flask import Flask, g, jsonify, render_template, request
from werkzeug.middleware.proxy_fix import ProxyFix

from . import db
from .config import Config, load_config
from .routes import bp as web_bp
from .storage import build_storage

ROOT = Path(__file__).resolve().parents[2]
log = logging.getLogger("catalog")


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        force=True,
    )


def _asset_origin(base_url: str) -> str:
    """Origine à autoriser dans la CSP pour les images (vide si chemin relatif)."""
    parsed = urlparse(base_url)
    return f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else ""


def create_app(overrides: dict | None = None) -> Flask:
    config: Config = load_config(overrides)
    configure_logging(config.log_level)

    app = Flask(
        __name__,
        static_folder=str(ROOT / "static"),
        template_folder=str(ROOT / "templates"),
    )
    app.config["APP_CONFIG"] = config
    app.config["SECRET_KEY"] = config.secret_key
    app.config["MAX_CONTENT_LENGTH"] = 64 * 1024  # formulaires uniquement

    if config.trusted_proxy_hops:
        app.wsgi_app = ProxyFix(  # type: ignore[method-assign]
            app.wsgi_app,
            x_for=config.trusted_proxy_hops,
            x_proto=config.trusted_proxy_hops,
            x_host=config.trusted_proxy_hops,
        )

    image_dir = config.local_image_dir
    if not Path(image_dir).is_absolute():
        image_dir = str(ROOT / image_dir)
    storage_cfg = replace(config, local_image_dir=image_dir)
    app.extensions["image_storage"] = build_storage(storage_cfg)

    img_origin = _asset_origin(config.asset_base_url)
    csp = (
        "default-src 'self'; "
        f"img-src 'self' data: {img_origin}; "
        "style-src 'self'; script-src 'self'; "
        "frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    )

    @app.context_processor
    def inject_globals():
        return {
            "app_name": config.app_name,
            "image_url": app.extensions["image_storage"].url_for,
        }

    @app.template_filter("xof")
    def format_xof(value) -> str:
        return f"{int(value):,}".replace(",", " ") + " FCFA"

    # --- Connexion DB par requête (ouverte à la demande, fermée en fin de requête)
    def get_db():
        if "db" not in g:
            g.db = db.connect(config.database_url)
        return g.db

    app.get_db = get_db  # type: ignore[attr-defined]

    @app.teardown_appcontext
    def close_db(_exc):
        conn = g.pop("db", None)
        if conn is not None:
            conn.close()

    # --- Journalisation des requêtes (jamais de corps, d'e-mail ni de message)
    @app.before_request
    def start_timer():
        g.start = time.perf_counter()
        g.request_id = request.headers.get("X-Request-Id") or uuid.uuid4().hex[:12]

    @app.after_request
    def finish(response):
        elapsed_ms = (time.perf_counter() - g.get("start", time.perf_counter())) * 1000
        if not request.path.startswith("/static/"):
            log.info(
                "request_id=%s %s %s -> %s %.1fms",
                g.get("request_id", "-"), request.method, request.path,
                response.status_code, elapsed_ms,
            )
        response.headers["X-Request-Id"] = g.get("request_id", "-")
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Content-Security-Policy"] = csp
        if config.is_production:
            response.headers["Strict-Transport-Security"] = "max-age=31536000"
        return response

    # --- Gestion des erreurs
    def _wants_json() -> bool:
        return request.path.startswith("/health")

    @app.errorhandler(404)
    def not_found(_e):
        if _wants_json():
            return jsonify(status="error", error="not_found"), 404
        return render_template("error.html", code=404, title="Page introuvable",
                               message="La page demandée n'existe pas ou a été déplacée."), 404

    @app.errorhandler(405)
    def method_not_allowed(_e):
        return render_template("error.html", code=405, title="Méthode non autorisée",
                               message="Cette action n'est pas autorisée sur cette page."), 405

    @app.errorhandler(413)
    def too_large(_e):
        return render_template("error.html", code=413, title="Requête trop volumineuse",
                               message="Les données envoyées sont trop volumineuses."), 413

    @app.errorhandler(psycopg.OperationalError)
    def db_unavailable(exc):
        log.error("request_id=%s base de données indisponible : %s",
                  g.get("request_id", "-"), exc.__class__.__name__)
        return render_template("error.html", code=503, title="Service momentanément indisponible",
                               message="Le catalogue est temporairement indisponible. "
                                       "Merci de réessayer dans quelques instants."), 503

    @app.errorhandler(Exception)
    def unexpected(exc):
        from werkzeug.exceptions import HTTPException
        if isinstance(exc, HTTPException):
            return render_template("error.html", code=exc.code, title=exc.name,
                                   message=exc.description), exc.code
        log.exception("request_id=%s erreur inattendue", g.get("request_id", "-"))
        return render_template("error.html", code=500, title="Erreur interne",
                               message="Une erreur est survenue. Notre équipe a été informée."), 500

    app.register_blueprint(web_bp)
    log.info("Application '%s' démarrée (env=%s)", config.app_name, config.app_env)
    return app
