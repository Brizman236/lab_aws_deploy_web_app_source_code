#!/usr/bin/env bash
# Lance l'application en local.
#   ./run.sh              -> serveur de développement Flask
#   ./run.sh prod         -> gunicorn
#   ./run.sh init-db      -> crée le schéma
#   ./run.sh seed-db      -> charge les données de démonstration
#   ./run.sh check-config -> valide la configuration (sans afficher les secrets)
#   ./run.sh test         -> exécute les tests
set -euo pipefail
cd "$(dirname "$0")"

if [ -f .env ]; then set -a; . ./.env; set +a; fi
export PYTHONPATH="src${PYTHONPATH:+:$PYTHONPATH}"
PY="${PYTHON:-python3}"
[ -x .venv/bin/python ] && PY=".venv/bin/python"

case "${1:-dev}" in
  dev)     exec "$PY" -c "from wsgi import app; app.run(host='${HOST:-127.0.0.1}', port=${PORT:-8000}, debug=${FLASK_DEBUG:-False})" ;;
  prod)    exec "$PY" -m gunicorn --bind "${HOST:-0.0.0.0}:${PORT:-8000}" --workers "${WORKERS:-2}" wsgi:app ;;
  init-db) exec "$PY" -m catalog.cli init-db ;;
  seed-db) exec "$PY" -m catalog.cli seed-db ;;
  check-config) exec "$PY" -m catalog.cli check-config ;;
  test)    exec "$PY" -m pytest ;;
  *) echo "Usage: $0 [dev|prod|init-db|seed-db|check-config|test]" >&2; exit 64 ;;
esac
