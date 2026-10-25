"""Abstraction de stockage des images (compatible S3 sans SDK)."""
import os

from catalog.config import load_config
from catalog.storage import LocalImageStorage, RemoteImageStorage, build_storage, is_valid_key

ROOT = os.path.dirname(os.path.dirname(__file__))


def test_local_url_for_key():
    s = LocalImageStorage("static/images", "/static/images")
    assert s.url_for("product-image-001.svg") == "/static/images/product-image-001.svg"


def test_missing_key_falls_back_to_placeholder():
    assert LocalImageStorage("x", "/img").url_for(None).endswith("placeholder.svg")


def test_unsafe_keys_are_rejected():
    for bad in ("../etc/passwd", "a/b.jpg", "", "..", "x y.jpg", "-rf"):
        assert not is_valid_key(bad)
    assert LocalImageStorage("x", "/img").url_for("../secret").endswith("placeholder.svg")


def test_remote_backend_uses_asset_base_url():
    cfg = load_config({"DATABASE_URL": "postgresql://x", "STORAGE_BACKEND": "remote",
                       "ASSET_BASE_URL": "https://bucket.example.com/images/"})
    s = build_storage(cfg)
    assert isinstance(s, RemoteImageStorage)
    assert s.url_for("product-image-007.svg") == "https://bucket.example.com/images/product-image-007.svg"


def test_all_seeded_image_keys_exist_on_disk(conn):
    s = LocalImageStorage(os.path.join(ROOT, "static", "images"), "/static/images")
    for row in conn.execute("SELECT image_key FROM products"):
        assert s.exists(row["image_key"]), row["image_key"]
    assert s.exists("placeholder.svg")
