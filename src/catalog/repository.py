"""Requêtes SQL du catalogue. Toutes les valeurs passent par des paramètres liés."""
from __future__ import annotations

_PRODUCT_COLUMNS = """
    p.id, p.name, p.slug, p.brand, p.description, p.price_xof,
    p.stock_status, p.image_key, p.created_at, p.updated_at,
    c.id AS category_id, c.name AS category_name, c.slug AS category_slug
"""

# Liste blanche : la clause ORDER BY n'est jamais construite depuis la saisie brute.
_SORT_SQL = {
    "name": "p.name ASC, p.id ASC",
    "price_asc": "p.price_xof ASC, p.id ASC",
    "price_desc": "p.price_xof DESC, p.id ASC",
    "newest": "p.created_at DESC, p.id DESC",
}


def _escape_like(term: str) -> str:
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def list_categories(conn) -> list[dict]:
    return conn.execute(
        """
        SELECT c.id, c.name, c.slug, c.description, COUNT(p.id) AS product_count
        FROM categories c
        LEFT JOIN products p ON p.category_id = c.id
        GROUP BY c.id
        ORDER BY c.id
        """
    ).fetchall()


def search_products(conn, filters: dict) -> tuple[list[dict], int]:
    """Retourne (produits de la page, total des résultats)."""
    where, params = [], {}

    if filters["q"]:
        params["q"] = f"%{_escape_like(filters['q'])}%"
        where.append(
            "(p.name ILIKE %(q)s OR p.brand ILIKE %(q)s OR p.description ILIKE %(q)s)"
        )
    if filters["category"]:
        params["category"] = filters["category"]
        where.append("c.slug = %(category)s")
    if filters["availability"]:
        params["availability"] = filters["availability"]
        where.append("p.stock_status = %(availability)s")
    if filters["min_price"] is not None:
        params["min_price"] = filters["min_price"]
        where.append("p.price_xof >= %(min_price)s")
    if filters["max_price"] is not None:
        params["max_price"] = filters["max_price"]
        where.append("p.price_xof <= %(max_price)s")

    where_sql = ("WHERE " + " AND ".join(where)) if where else ""
    base = "FROM products p JOIN categories c ON c.id = p.category_id " + where_sql

    total = conn.execute(f"SELECT COUNT(*) AS n {base}", params).fetchone()["n"]

    params["limit"] = filters["per_page"]
    params["offset"] = (filters["page"] - 1) * filters["per_page"]
    rows = conn.execute(
        f"SELECT {_PRODUCT_COLUMNS} {base} "
        f"ORDER BY {_SORT_SQL[filters['sort']]} LIMIT %(limit)s OFFSET %(offset)s",
        params,
    ).fetchall()
    return rows, total


def get_product_by_slug(conn, slug: str) -> dict | None:
    return conn.execute(
        f"SELECT {_PRODUCT_COLUMNS} FROM products p "
        "JOIN categories c ON c.id = p.category_id WHERE p.slug = %s",
        (slug,),
    ).fetchone()


def get_product_by_id(conn, product_id: int) -> dict | None:
    return conn.execute(
        f"SELECT {_PRODUCT_COLUMNS} FROM products p "
        "JOIN categories c ON c.id = p.category_id WHERE p.id = %s",
        (product_id,),
    ).fetchone()


def latest_products(conn, limit: int = 4) -> list[dict]:
    return conn.execute(
        f"SELECT {_PRODUCT_COLUMNS} FROM products p "
        "JOIN categories c ON c.id = p.category_id "
        "WHERE p.stock_status IN ('in_stock', 'low_stock') "
        "ORDER BY p.created_at DESC, p.id DESC LIMIT %s",
        (limit,),
    ).fetchall()


def related_products(conn, product: dict, limit: int = 4) -> list[dict]:
    return conn.execute(
        f"SELECT {_PRODUCT_COLUMNS} FROM products p "
        "JOIN categories c ON c.id = p.category_id "
        "WHERE p.category_id = %s AND p.id <> %s "
        "ORDER BY p.id LIMIT %s",
        (product["category_id"], product["id"], limit),
    ).fetchall()


def create_inquiry(conn, values: dict) -> int:
    row = conn.execute(
        """
        INSERT INTO inquiries (customer_name, customer_email, customer_phone, product_id, message)
        VALUES (%(customer_name)s, %(customer_email)s, %(customer_phone)s, %(product_id)s, %(message)s)
        RETURNING id
        """,
        values,
    ).fetchone()
    conn.commit()
    return row["id"]
