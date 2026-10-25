"""Validation côté serveur des données saisies par les utilisateurs.

Les fonctions retournent (valeurs_nettoyées, erreurs). Aucune exception n'est
levée pour une saisie invalide : les erreurs sont renvoyées au formulaire.
"""
from __future__ import annotations

import re

NAME_MIN, NAME_MAX = 2, 120
MESSAGE_MIN, MESSAGE_MAX = 10, 2000
EMAIL_MAX = 254

_EMAIL_RE = re.compile(r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+$")
_PHONE_RE = re.compile(r"^\+?[0-9][0-9 .()-]{5,24}$")
_CTRL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

VALID_STOCK = ("in_stock", "low_stock", "out_of_stock", "on_order")
VALID_SORTS = ("name", "price_asc", "price_desc", "newest")


def _clean(value: str | None) -> str:
    """Supprime les caractères de contrôle et les espaces de bord."""
    return _CTRL_RE.sub("", value or "").strip()


def validate_inquiry(form) -> tuple[dict, dict]:
    """Valide un formulaire de demande (produit ou contact général)."""
    errors: dict[str, str] = {}

    name = _clean(form.get("customer_name"))
    email = _clean(form.get("customer_email")).lower()
    phone = _clean(form.get("customer_phone"))
    message = _clean(form.get("message"))
    raw_product = _clean(form.get("product_id"))

    if not (NAME_MIN <= len(name) <= NAME_MAX):
        errors["customer_name"] = f"Le nom doit contenir entre {NAME_MIN} et {NAME_MAX} caractères."

    if not email:
        errors["customer_email"] = "L'adresse e-mail est obligatoire."
    elif len(email) > EMAIL_MAX or not _EMAIL_RE.match(email):
        errors["customer_email"] = "L'adresse e-mail n'est pas valide."

    if phone and not _PHONE_RE.match(phone):
        errors["customer_phone"] = "Le numéro de téléphone n'est pas valide."

    if not (MESSAGE_MIN <= len(message) <= MESSAGE_MAX):
        errors["message"] = f"Le message doit contenir entre {MESSAGE_MIN} et {MESSAGE_MAX} caractères."

    product_id = None
    if raw_product:
        if raw_product.isdigit() and int(raw_product) < 2**31:
            product_id = int(raw_product)
        else:
            errors["product_id"] = "Produit invalide."

    values = {
        "customer_name": name,
        "customer_email": email,
        "customer_phone": phone or None,
        "message": message,
        "product_id": product_id,
    }
    return values, errors


def parse_catalog_filters(args, per_page_default: int) -> dict:
    """Normalise les paramètres de recherche/filtrage du catalogue."""
    q = _clean(args.get("q"))[:100]
    category = _clean(args.get("category"))[:100]
    availability = _clean(args.get("availability"))
    if availability not in VALID_STOCK:
        availability = ""
    sort = _clean(args.get("sort"))
    if sort not in VALID_SORTS:
        sort = "name"

    def _int(name: str, default: int | None, lo: int, hi: int) -> int | None:
        raw = _clean(args.get(name))
        if not raw.isdigit():
            return default
        return max(lo, min(int(raw), hi))

    return {
        "q": q,
        "category": category,
        "availability": availability,
        "sort": sort,
        "min_price": _int("min_price", None, 0, 100_000_000),
        "max_price": _int("max_price", None, 0, 100_000_000),
        "page": _int("page", 1, 1, 10_000),
        "per_page": per_page_default,
    }
