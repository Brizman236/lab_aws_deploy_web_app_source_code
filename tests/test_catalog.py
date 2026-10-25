"""Liste, détail, recherche, filtres, tri, pagination et accès base de données."""
from catalog import repository
from catalog.validation import parse_catalog_filters


def _titles(html):
    import re
    return re.findall(r'card-title"><a[^>]*>([^<]*)', html)


def test_product_list_shows_all_16_products(client):
    html = client.get("/produits?per_page=100").get_data(as_text=True)
    assert "16 produits trouvés" in html
    assert len(_titles(html)) == 12  # première page (12 par page)


def test_pagination_second_page(client):
    html = client.get("/produits?page=2").get_data(as_text=True)
    assert len(_titles(html)) == 4


def test_page_out_of_range_is_clamped(client):
    assert client.get("/produits?page=9999").status_code == 200


def test_product_detail(client):
    r = client.get("/produits/nexora-slim-14")
    html = r.get_data(as_text=True)
    assert r.status_code == 200
    assert "Nexora Slim 14" in html
    assert "485" in html and "FCFA" in html
    assert "product-image-001.svg" in html


def test_product_detail_unknown_slug_404(client):
    assert client.get("/produits/n-existe-pas").status_code == 404


def test_search_by_text(client):
    html = client.get("/produits?q=routeur").get_data(as_text=True)
    assert "1 produit trouvé" in html
    assert "Routeur Wi-Fi 6" in html


def test_search_is_case_insensitive(client):
    assert "1 produit trouvé" in client.get("/produits?q=ROUTEUR").get_data(as_text=True)


def test_search_no_result_shows_empty_state(client):
    html = client.get("/produits?q=zzzzintrouvable").get_data(as_text=True)
    assert "0 produit trouvé" in html
    assert "Aucun produit ne correspond" in html


def test_filter_by_category(client):
    html = client.get("/produits?category=ecrans").get_data(as_text=True)
    assert "4 produits trouvés" in html
    assert all("Lumio" in t for t in _titles(html))


def test_filter_by_availability(client):
    html = client.get("/produits?availability=out_of_stock").get_data(as_text=True)
    assert "1 produit trouvé" in html and "Ultrawide" in html


def test_filter_by_price_range(client):
    html = client.get("/produits?min_price=90000&max_price=200000").get_data(as_text=True)
    assert "3 produits trouvés" in html  # écran 24" (98 000), point d'accès (95 000), switch (185 000)


def test_sort_by_price(client):
    asc = _titles(client.get("/produits?sort=price_asc").get_data(as_text=True))
    desc = _titles(client.get("/produits?sort=price_desc").get_data(as_text=True))
    assert "Clavier" in asc[0] and "Station de travail" in desc[0]


def test_invalid_filters_are_ignored_not_crashing(client):
    r = client.get("/produits?sort=DROP TABLE&availability=x&min_price=abc&page=-3&category=;--")
    assert r.status_code == 200


def test_sql_injection_attempt_is_harmless(client, conn):
    r = client.get("/produits?q=' OR 1=1; DROP TABLE products; --")
    assert r.status_code == 200
    assert "0 produit trouvé" in r.get_data(as_text=True)
    assert conn.execute("SELECT COUNT(*) AS n FROM products").fetchone()["n"] == 16


def test_search_output_is_escaped(client):
    html = client.get("/produits?q=<script>alert(1)</script>").get_data(as_text=True)
    assert "<script>alert(1)</script>" not in html


def test_like_wildcards_are_escaped(client):
    # « _ » ne doit pas jouer le rôle de joker SQL
    assert "0 produit trouvé" in client.get("/produits?q=_____________________").get_data(as_text=True)


# --- couche repository / base de données
def test_repository_search_and_total(conn):
    f = parse_catalog_filters({"q": "écran"}, 12)
    rows, total = repository.search_products(conn, f)
    assert total == len(rows) >= 1


def test_database_content_matches_seed(conn):
    assert conn.execute("SELECT COUNT(*) AS n FROM categories").fetchone()["n"] == 4
    assert conn.execute("SELECT COUNT(*) AS n FROM products").fetchone()["n"] == 16
    assert conn.execute("SELECT COUNT(*) AS n FROM inquiries").fetchone()["n"] >= 5


def test_images_are_references_not_binary(conn):
    keys = [r["image_key"] for r in conn.execute("SELECT image_key FROM products")]
    assert all(isinstance(k, str) and k.startswith("product-image-") for k in keys)


def test_related_products_same_category(conn):
    p = repository.get_product_by_slug(conn, "lumio-pro-27-qhd")
    related = repository.related_products(conn, p)
    assert related and all(r["category_id"] == p["category_id"] and r["id"] != p["id"] for r in related)
