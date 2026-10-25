"""Demandes clients : succès, validation, CSRF, anti-spam, contraintes DB, logs."""
import logging

import psycopg
import pytest

from conftest import get_token

VALID = {
    "customer_name": "Awa Test",
    "customer_email": "Awa.Test@Example.com",
    "customer_phone": "+221 77 000 00 00",
    "message": "Bonjour, je souhaite un devis pour cinq unités.",
}


def _last_inquiry(conn):
    return conn.execute("SELECT * FROM inquiries ORDER BY id DESC LIMIT 1").fetchone()


def test_contact_inquiry_is_stored(client, conn):
    before = conn.execute("SELECT COUNT(*) AS n FROM inquiries").fetchone()["n"]
    r = client.post("/contact", data={**VALID, "csrf_token": get_token(client)})
    assert r.status_code == 302 and r.headers["Location"].endswith("/merci")
    row = _last_inquiry(conn)
    assert conn.execute("SELECT COUNT(*) AS n FROM inquiries").fetchone()["n"] == before + 1
    assert row["product_id"] is None  # demande générale
    assert row["status"] == "new"
    assert row["customer_email"] == "awa.test@example.com"  # normalisé en minuscules


def test_product_inquiry_is_linked_to_product(client, conn):
    token = get_token(client, "/produits/lumio-pro-27-qhd")
    r = client.post("/produits/lumio-pro-27-qhd/demande", data={**VALID, "csrf_token": token})
    assert r.status_code == 302
    row = _last_inquiry(conn)
    slug = conn.execute("SELECT slug FROM products WHERE id = %s", (row["product_id"],)).fetchone()["slug"]
    assert slug == "lumio-pro-27-qhd"


def test_product_id_comes_from_url_not_form(client, conn):
    token = get_token(client, "/produits/lumio-pro-27-qhd")
    client.post("/produits/lumio-pro-27-qhd/demande", data={**VALID, "csrf_token": token, "product_id": "1"})
    row = _last_inquiry(conn)
    assert conn.execute("SELECT slug FROM products WHERE id=%s", (row["product_id"],)).fetchone()["slug"] == "lumio-pro-27-qhd"


def test_inquiry_for_unknown_product_404(client):
    token = get_token(client)
    assert client.post("/produits/inconnu/demande", data={**VALID, "csrf_token": token}).status_code == 404


@pytest.mark.parametrize("field,value,fragment", [
    ("customer_name", "A", "nom"),
    ("customer_name", "   ", "nom"),
    ("customer_email", "pas-un-email", "e-mail"),
    ("customer_email", "", "obligatoire"),
    ("customer_phone", "abc", "téléphone"),
    ("message", "court", "message"),
    ("message", "x" * 2001, "message"),
])
def test_validation_errors_return_422_and_store_nothing(client, conn, field, value, fragment):
    before = conn.execute("SELECT COUNT(*) AS n FROM inquiries").fetchone()["n"]
    data = {**VALID, "csrf_token": get_token(client), field: value}
    r = client.post("/contact", data=data)
    assert r.status_code == 422
    assert fragment in r.get_data(as_text=True).lower()
    assert conn.execute("SELECT COUNT(*) AS n FROM inquiries").fetchone()["n"] == before


def test_form_keeps_user_input_after_error(client):
    r = client.post("/contact", data={**VALID, "customer_email": "mauvais", "csrf_token": get_token(client)})
    assert "Awa Test" in r.get_data(as_text=True)


def test_missing_or_forged_csrf_token_rejected(client, conn):
    before = conn.execute("SELECT COUNT(*) AS n FROM inquiries").fetchone()["n"]
    assert client.post("/contact", data=VALID).status_code == 400
    assert client.post("/contact", data={**VALID, "csrf_token": "forge"}).status_code == 400
    assert conn.execute("SELECT COUNT(*) AS n FROM inquiries").fetchone()["n"] == before


def test_honeypot_silently_discards_bots(client, conn):
    before = conn.execute("SELECT COUNT(*) AS n FROM inquiries").fetchone()["n"]
    r = client.post("/contact", data={**VALID, "csrf_token": get_token(client), "website": "http://spam"})
    assert r.status_code == 302
    assert conn.execute("SELECT COUNT(*) AS n FROM inquiries").fetchone()["n"] == before


def test_html_in_input_is_escaped_on_redisplay(client):
    r = client.post("/contact", data={**VALID, "customer_name": "<b>x</b>", "customer_email": "bad",
                                      "csrf_token": get_token(client)})
    assert "<b>x</b>" not in r.get_data(as_text=True)


def test_personal_data_is_not_logged(client, caplog):
    with caplog.at_level(logging.INFO):
        client.post("/contact", data={**VALID, "csrf_token": get_token(client)})
    logs = caplog.text
    assert "demande créée id=" in logs
    assert "example.com" not in logs and "Awa" not in logs and "devis" not in logs


# --- contraintes au niveau base de données (dernier rempart)
def test_db_rejects_invalid_status(conn):
    with pytest.raises(psycopg.errors.CheckViolation):
        conn.execute("INSERT INTO inquiries (customer_name, customer_email, message, status) "
                     "VALUES ('A B', 'a@b.co', 'message valide', 'bogus')")


def test_db_rejects_unknown_product_fk(conn):
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        conn.execute("INSERT INTO inquiries (customer_name, customer_email, message, product_id) "
                     "VALUES ('A B', 'a@b.co', 'message valide', 99999)")


def test_db_rejects_negative_price(conn):
    with pytest.raises(psycopg.errors.CheckViolation):
        conn.execute("INSERT INTO products (category_id, name, slug, price_xof) VALUES (1, 'x', 'x-neg', -1)")


def test_deleting_product_keeps_inquiry(conn):
    pid = conn.execute("SELECT product_id FROM inquiries WHERE product_id IS NOT NULL LIMIT 1").fetchone()["product_id"]
    conn.execute("DELETE FROM products WHERE id = %s", (pid,))
    assert conn.execute("SELECT COUNT(*) AS n FROM inquiries WHERE product_id = %s", (pid,)).fetchone()["n"] == 0
    assert conn.execute("SELECT COUNT(*) AS n FROM inquiries").fetchone()["n"] == 8  # conservées (SET NULL)
    conn.rollback()
