"""Accès PostgreSQL (psycopg 3), uniquement via requêtes paramétrées."""
from __future__ import annotations

import logging
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_FILE = ROOT / "database" / "schema.sql"
SEED_FILE = ROOT / "database" / "seed.sql"


def connect(database_url: str, timeout: int = 5) -> psycopg.Connection:
    return psycopg.connect(database_url, row_factory=dict_row, connect_timeout=timeout)


def run_sql_file(database_url: str, path: Path) -> None:
    sql = path.read_text(encoding="utf-8")
    with connect(database_url) as conn:
        conn.execute(sql)
    log.info("Fichier SQL exécuté : %s", path.name)


def init_db(database_url: str) -> None:
    run_sql_file(database_url, SCHEMA_FILE)


def seed_db(database_url: str) -> None:
    run_sql_file(database_url, SEED_FILE)


def ping(database_url: str) -> bool:
    try:
        with connect(database_url, timeout=2) as conn:
            conn.execute("SELECT 1")
        return True
    except Exception:  # noqa: BLE001 - /health ne doit jamais lever
        return False
