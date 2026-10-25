"""Fixtures de test. Les tests d'intégration utilisent une VRAIE base PostgreSQL
(TEST_DATABASE_URL), réinitialisée à chaque session : ne jamais la pointer vers
une base contenant des données à conserver."""
import os

import pytest

from catalog import create_app, db


def _test_url() -> str:
    url = os.environ.get("TEST_DATABASE_URL", "").strip()
    if not url:
        pytest.exit("TEST_DATABASE_URL n'est pas définie (voir README, section Tests).", returncode=2)
    return url


@pytest.fixture(scope="session")
def test_db_url():
    url = _test_url()
    if not db.ping(url):
        pytest.exit("PostgreSQL injoignable via TEST_DATABASE_URL.", returncode=2)
    # Repart d'un schéma propre puis charge les données de démonstration.
    with db.connect(url) as conn:
        conn.execute("DROP TABLE IF EXISTS inquiries, products, categories CASCADE")
    db.init_db(url)
    db.seed_db(url)
    return url


@pytest.fixture()
def app(test_db_url):
    db.seed_db(test_db_url)  # état identique avant chaque test
    return create_app({"DATABASE_URL": test_db_url, "APP_ENV": "testing", "LOG_LEVEL": "WARNING"})


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def conn(app, test_db_url):  # dépend de `app` : base réinitialisée avant chaque test
    with db.connect(test_db_url) as c:
        yield c


def get_token(client, path="/contact"):
    html = client.get(path).get_data(as_text=True)
    marker = 'name="csrf_token" value="'
    start = html.index(marker) + len(marker)
    return html[start:html.index('"', start)]
