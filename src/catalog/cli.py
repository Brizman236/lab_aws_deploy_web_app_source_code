"""Commandes d'administration : python -m catalog.cli {init-db|seed-db|check-config}."""
from __future__ import annotations

import argparse
import logging
import sys

from . import db
from .config import ConfigError, load_config


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="catalog.cli", description=__doc__)
    parser.add_argument("command", choices=["init-db", "seed-db", "check-config"])
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    try:
        cfg = load_config()
    except ConfigError as exc:
        print(f"Erreur de configuration : {exc}", file=sys.stderr)
        return 2

    if args.command == "check-config":
        print(f"CONFIG_SOURCE={cfg.config_source} APP_ENV={cfg.app_env} APP_NAME={cfg.app_name} LOG_LEVEL={cfg.log_level} "
              f"STORAGE_BACKEND={cfg.storage_backend} ASSET_BASE_URL={cfg.asset_base_url}")
        print("DATABASE_URL : définie (valeur non affichée)")
        return 0

    if cfg.is_production and args.command == "seed-db":
        print("Refus : seed-db efface les données et est interdit en production.", file=sys.stderr)
        return 3

    try:
        if args.command == "init-db":
            db.init_db(cfg.database_url)
            print("Schéma créé / à jour.")
        else:
            db.seed_db(cfg.database_url)
            print("Données de démonstration chargées.")
    except Exception as exc:  # noqa: BLE001
        print(f"Échec ({exc.__class__.__name__}) : vérifiez DATABASE_URL et que PostgreSQL est joignable.",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
