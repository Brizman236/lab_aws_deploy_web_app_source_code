"""Point d'entrée WSGI : `gunicorn wsgi:app`."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv()  # sans effet si aucun .env : l'environnement du processus prévaut

from catalog import create_app  # noqa: E402

app = create_app()
