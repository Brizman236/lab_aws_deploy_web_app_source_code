"""Source de configuration « aws » : Parameter Store + Secrets Manager.

C'est le SEUL module de l'application qui connaît AWS. Il n'est importé que
lorsque CONFIG_SOURCE=aws, et boto3 n'est importé qu'au moment d'ouvrir les
clients : en mode local, ni ce module ni boto3 ne sont nécessaires.

Il produit un simple dictionnaire {NOM_DE_VARIABLE: valeur}, exactement le même
contrat que os.environ : `config.load_config` ne sait pas d'où viennent les valeurs.

Répartition :
  - Parameter Store (chemin SSM_PATH_PREFIX, ex. /techsahel/production/) :
      APP_ENV, APP_NAME, ASSET_BASE_URL, DB_HOST, DB_NAME, ... Le nom du paramètre
      (dernier segment du chemin) est le nom de la variable.
  - Secrets Manager :
      * DB_SECRET_ID : secret JSON de la base, au format RDS :
        {"engine", "host", "port", "dbname", "username", "password"}.
        Le mot de passe n'existe QUE là.
      * SECRET_KEY_SECRET_ID : secret en TEXTE BRUT (pas du JSON) contenant la
        SECRET_KEY de l'application. SECRET_KEY n'est PAS lue dans Parameter Store.

Les credentials AWS ne sont jamais lus par l'application : boto3 utilise la chaîne
standard (rôle IAM de l'instance en production).

Aucune valeur (ni mot de passe, ni DSN) n'est écrite dans les logs ou dans les
messages d'erreur : uniquement des noms de clés et des codes d'erreur.
"""
from __future__ import annotations

import json
import logging
from typing import Callable
from urllib.parse import quote

log = logging.getLogger(__name__)

# Variables que l'on accepte depuis Parameter Store. Tout autre paramètre présent
# sous le même chemin est ignoré (et signalé par son nom dans les logs).
SSM_ALLOWED_KEYS = frozenset({
    "APP_ENV", "APP_NAME", "LOG_LEVEL",
    "STORAGE_BACKEND", "ASSET_BASE_URL", "LOCAL_IMAGE_DIR",
    "ITEMS_PER_PAGE", "TRUSTED_PROXY_HOPS",
    "DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_SSLMODE",
})

# En mode aws, APP_ENV doit être explicite : on ne retombe jamais sur « development ».
REQUIRED_SSM_KEYS = ("APP_ENV",)

DEFAULT_DB_PORT = "5432"
DEFAULT_DB_SSLMODE = "require"  # RDS : connexion chiffrée par défaut

ClientFactory = Callable[[str], object]


class AwsConfigError(RuntimeError):
    """Erreur de lecture de la configuration AWS (le message ne contient aucune valeur)."""


def _default_client_factory(service: str):
    try:
        import boto3  # import tardif : inutile en mode local
    except ImportError as exc:  # pragma: no cover - dépend de l'installation
        raise AwsConfigError(
            "CONFIG_SOURCE=aws nécessite boto3 (pip install -r requirements-aws.txt)."
        ) from exc
    return boto3.client(service)  # région : AWS_REGION / AWS_DEFAULT_REGION


def _describe(exc: Exception) -> str:
    """Résumé sûr d'une exception AWS : classe + code, sans corps de réponse."""
    code = getattr(exc, "response", {}).get("Error", {}).get("Code") if hasattr(exc, "response") else None
    return f"{exc.__class__.__name__}{f' ({code})' if code else ''}"


def _normalize_prefix(prefix: str) -> str:
    prefix = prefix.strip()
    if not prefix.startswith("/"):
        raise AwsConfigError("SSM_PATH_PREFIX doit commencer par '/' (ex. /techsahel/production/).")
    return prefix if prefix.endswith("/") else prefix + "/"


def fetch_parameters(client, prefix: str) -> dict[str, str]:
    """Lit tous les paramètres directement sous `prefix` (SecureString déchiffrés)."""
    prefix = _normalize_prefix(prefix)
    found: dict[str, str] = {}
    ignored: list[str] = []
    try:
        paginator = client.get_paginator("get_parameters_by_path")
        for page in paginator.paginate(Path=prefix, Recursive=False, WithDecryption=True):
            for param in page.get("Parameters", []):
                name = param["Name"][len(prefix):] if param["Name"].startswith(prefix) else param["Name"]
                if name in SSM_ALLOWED_KEYS:
                    found[name] = param["Value"]
                else:
                    ignored.append(name)
    except AwsConfigError:
        raise
    except Exception as exc:  # noqa: BLE001 - ClientError, EndpointConnectionError, NoCredentialsError...
        raise AwsConfigError(
            f"Lecture de Parameter Store impossible sous {prefix} : {_describe(exc)}."
        ) from exc

    if ignored:
        log.warning("Parameter Store : paramètres ignorés (non reconnus) : %s", ", ".join(sorted(ignored)))
    log.info("Parameter Store : %d paramètre(s) chargé(s) sous %s : %s",
             len(found), prefix, ", ".join(sorted(found)))
    return found


def fetch_db_secret(client, secret_id: str) -> dict:
    """Lit le secret JSON de la base (format RDS) et vérifie ses champs obligatoires."""
    try:
        response = client.get_secret_value(SecretId=secret_id)
    except Exception as exc:  # noqa: BLE001
        raise AwsConfigError(f"Lecture de Secrets Manager impossible : {_describe(exc)}.") from exc

    raw = response.get("SecretString")
    if not raw:
        raise AwsConfigError("Le secret de base de données n'a pas de SecretString (secret binaire ?).")
    try:
        data = json.loads(raw)
    except ValueError as exc:
        raise AwsConfigError("Le secret de base de données n'est pas un JSON valide.") from exc
    if not isinstance(data, dict):
        raise AwsConfigError("Le secret de base de données doit être un objet JSON.")

    for field in ("username", "password"):
        if not str(data.get(field, "")).strip():
            raise AwsConfigError(f"Le secret de base de données ne contient pas le champ '{field}'.")
    log.info("Secrets Manager : secret de base de données chargé (champs : %s)", ", ".join(sorted(data)))
    return data


def fetch_secret_key(client, secret_id: str) -> str:
    """Lit la SECRET_KEY : un secret texte brut (SecretString non JSON), espaces de bord retirés."""
    try:
        response = client.get_secret_value(SecretId=secret_id)
    except Exception as exc:  # noqa: BLE001
        raise AwsConfigError(f"Lecture du secret SECRET_KEY impossible : {_describe(exc)}.") from exc

    value = (response.get("SecretString") or "").strip()
    if not value:
        raise AwsConfigError("Le secret SECRET_KEY est vide ou binaire : il doit contenir du texte brut.")
    log.info("Secrets Manager : secret SECRET_KEY chargé")  # jamais la valeur, ni sa longueur
    return value


def build_database_url(secret: dict, ssm: dict[str, str]) -> str:
    """Assemble DATABASE_URL.

    - username / password : toujours du secret (sauf DB_USER explicite dans Parameter Store).
    - host / port / dbname : Parameter Store (DB_HOST, DB_PORT, DB_NAME) s'il y est,
      sinon le secret RDS.
    Les identifiants sont encodés en pourcentage : un mot de passe contenant @ : / ? # % …
    ne casse pas l'URL.
    """
    username = ssm.get("DB_USER") or str(secret["username"])
    password = str(secret["password"])
    host = ssm.get("DB_HOST") or str(secret.get("host", "")).strip()
    port = ssm.get("DB_PORT") or str(secret.get("port", "") or DEFAULT_DB_PORT)
    dbname = ssm.get("DB_NAME") or str(secret.get("dbname", "")).strip()
    sslmode = ssm.get("DB_SSLMODE") or DEFAULT_DB_SSLMODE

    missing = [n for n, v in (("host", host), ("dbname", dbname)) if not v]
    if missing:
        raise AwsConfigError(
            "Hôte ou nom de base introuvable : fournir DB_HOST / DB_NAME dans Parameter Store "
            f"ou les champs {', '.join(missing)} dans le secret."
        )
    if not str(port).isdigit():
        raise AwsConfigError("Le port de la base doit être un entier.")

    return (f"postgresql://{quote(username, safe='')}:{quote(password, safe='')}"
            f"@{host}:{port}/{quote(dbname, safe='')}?sslmode={quote(sslmode, safe='')}")


def load_aws_values(bootstrap: dict, client_factory: ClientFactory | None = None) -> dict[str, str]:
    """Retourne les variables de configuration lues depuis AWS.

    `bootstrap` contient uniquement ce qu'il faut pour savoir OÙ lire :
      SSM_PATH_PREFIX, DB_SECRET_ID, SECRET_KEY_SECRET_ID (+ AWS_REGION, lu par boto3).
    `client_factory(service)` permet d'injecter de faux clients dans les tests.
    """
    prefix = (bootstrap.get("SSM_PATH_PREFIX") or "").strip()
    secret_id = (bootstrap.get("DB_SECRET_ID") or "").strip()
    if not prefix:
        raise AwsConfigError("SSM_PATH_PREFIX est obligatoire avec CONFIG_SOURCE=aws (ex. /techsahel/production/).")
    if not secret_id:
        raise AwsConfigError("DB_SECRET_ID est obligatoire avec CONFIG_SOURCE=aws (nom ou ARN du secret).")
    key_secret_id = (bootstrap.get("SECRET_KEY_SECRET_ID") or "").strip()
    if not key_secret_id:
        raise AwsConfigError("SECRET_KEY_SECRET_ID est obligatoire avec CONFIG_SOURCE=aws (nom ou ARN du secret texte).")

    factory = client_factory or _default_client_factory
    try:
        ssm_client = factory("ssm")
        secrets_client = factory("secretsmanager")
    except AwsConfigError:
        raise
    except Exception as exc:  # noqa: BLE001 - ex. NoRegionError
        raise AwsConfigError(
            f"Initialisation du client AWS impossible : {_describe(exc)} (AWS_REGION définie ?)."
        ) from exc

    params = fetch_parameters(ssm_client, prefix)
    missing = [k for k in REQUIRED_SSM_KEYS if not params.get(k, "").strip()]
    if missing:
        raise AwsConfigError(f"Paramètre(s) obligatoire(s) absent(s) de Parameter Store : {', '.join(missing)}.")

    secret = fetch_db_secret(secrets_client, secret_id)
    secret_key = fetch_secret_key(secrets_client, key_secret_id)

    values = {k: v for k, v in params.items() if not k.startswith("DB_")}
    values["DATABASE_URL"] = build_database_url(secret, params)
    values["SECRET_KEY"] = secret_key
    return values
