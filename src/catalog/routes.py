"""Routes HTTP publiques : catalogue, détail, demandes, contact, à propos, health."""
from __future__ import annotations

import logging
import math

from flask import (Blueprint, abort, current_app, g, jsonify, redirect,
                   render_template, request, url_for)
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from . import db, repository
from .validation import parse_catalog_filters, validate_inquiry

bp = Blueprint("web", __name__)
log = logging.getLogger("catalog.routes")

CSRF_MAX_AGE = 2 * 60 * 60  # 2 heures


# --- Jeton CSRF sans état : signé avec SECRET_KEY, donc valable sur plusieurs
# instances de l'application derrière un répartiteur de charge.
def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt="inquiry-form")


def _new_csrf_token() -> str:
    return _serializer().dumps("inquiry")


def _csrf_valid(token: str | None) -> bool:
    if not token:
        return False
    try:
        return _serializer().loads(token, max_age=CSRF_MAX_AGE) == "inquiry"
    except (BadSignature, SignatureExpired):
        return False


def _conn():
    return current_app.get_db()  # type: ignore[attr-defined]


@bp.get("/")
def home():
    conn = _conn()
    return render_template(
        "home.html",
        categories=repository.list_categories(conn),
        featured=repository.latest_products(conn, 4),
    )


@bp.get("/produits")
def catalog():
    cfg = current_app.config["APP_CONFIG"]
    filters = parse_catalog_filters(request.args, cfg.items_per_page)
    conn = _conn()
    products, total = repository.search_products(conn, filters)
    pages = max(1, math.ceil(total / filters["per_page"]))
    if filters["page"] > pages:
        filters["page"] = pages
        products, total = repository.search_products(conn, filters)
    return render_template(
        "catalog.html",
        products=products,
        total=total,
        filters=filters,
        pages=pages,
        categories=repository.list_categories(conn),
    )


@bp.get("/produits/<slug>")
def product_detail(slug: str):
    conn = _conn()
    product = repository.get_product_by_slug(conn, slug)
    if product is None:
        abort(404)
    return render_template(
        "product.html",
        product=product,
        related=repository.related_products(conn, product),
        csrf_token=_new_csrf_token(),
        form={}, errors={},
    )


def _handle_inquiry(linked_product: dict | None, template: str, **ctx):
    """Traite le POST d'un formulaire de demande (produit ou contact général)."""
    # Champ piège anti-spam : invisible pour un humain, rempli par certains robots.
    if request.form.get("website"):
        log.info("request_id=%s demande ignorée (honeypot)", g.get("request_id", "-"))
        return redirect(url_for("web.inquiry_thanks"))

    if not _csrf_valid(request.form.get("csrf_token")):
        log.warning("request_id=%s jeton CSRF invalide", g.get("request_id", "-"))
        return render_template(
            template, form=request.form, errors={"_global": "Le formulaire a expiré. Merci de réessayer."},
            csrf_token=_new_csrf_token(), **ctx), 400

    values, errors = validate_inquiry(request.form)
    conn = _conn()

    if linked_product is not None:
        values["product_id"] = linked_product["id"]  # le produit vient de l'URL, pas du formulaire
    elif values["product_id"] is not None and repository.get_product_by_id(conn, values["product_id"]) is None:
        errors["product_id"] = "Produit introuvable."

    if errors:
        return render_template(template, form=request.form, errors=errors,
                               csrf_token=_new_csrf_token(), **ctx), 422

    inquiry_id = repository.create_inquiry(conn, values)
    # On journalise l'identifiant seulement : jamais le nom, l'e-mail ni le message.
    log.info("request_id=%s demande créée id=%s product_id=%s",
             g.get("request_id", "-"), inquiry_id, values["product_id"])
    return redirect(url_for("web.inquiry_thanks"))


@bp.post("/produits/<slug>/demande")
def product_inquiry(slug: str):
    conn = _conn()
    product = repository.get_product_by_slug(conn, slug)
    if product is None:
        abort(404)
    return _handle_inquiry(product, "product.html", product=product,
                           related=repository.related_products(conn, product))


@bp.route("/contact", methods=["GET", "POST"])
def contact():
    if request.method == "POST":
        return _handle_inquiry(None, "contact.html")
    return render_template("contact.html", form={}, errors={}, csrf_token=_new_csrf_token())


@bp.get("/merci")
def inquiry_thanks():
    return render_template("thanks.html")


@bp.get("/a-propos")
def about():
    return render_template("about.html")


# --- Santé -------------------------------------------------------------------
@bp.get("/health")
def health():
    """Santé complète : application + base de données.

    200 {"status": "ok"}        application et base de données opérationnelles
    503 {"status": "degraded"}  application en vie mais base de données injoignable
    """
    cfg = current_app.config["APP_CONFIG"]
    database_up = db.ping(cfg.database_url)
    body = {
        "status": "ok" if database_up else "degraded",
        "app": "up",
        "database": "up" if database_up else "down",
        "environment": cfg.app_env,
    }
    return jsonify(body), (200 if database_up else 503)


@bp.get("/health/live")
def health_live():
    """Liveness : le processus répond, sans toucher à la base de données."""
    return jsonify(status="ok", app="up"), 200
