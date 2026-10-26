"""Mode de configuration CONFIG_SOURCE=aws (Parameter Store + Secrets Manager).

Aucun appel réseau : on injecte de faux clients (comportement) et des clients
boto3 « stubbés » (validation des paramètres d'appel contre le modèle d'API AWS).
"""
import json
import logging
from urllib.parse import urlsplit, unquote

import pytest

from catalog.config import ConfigError, load_config

PREFIX = "/techsahel/production/"
SECRET_ID = "techsahel/rds/catalog_app"
KEY_SECRET_ID = "techsahel/production/secret_key"
KEY_VALUE = "cle-de-test-longue-et-factice"

SSM_VALUES = {
    "APP_ENV": "production",
    "APP_NAME": "TechSahel Catalogue",
    "ASSET_BASE_URL": "https://assets.example.com/images",
    "DB_HOST": "techsahel-postgres.example.eu-west-3.rds.amazonaws.com",
    "DB_NAME": "product_catalog",
}
SECRET = {
    "engine": "postgres",
    "host": "secret-host.example.eu-west-3.rds.amazonaws.com",
    "port": 5432,
    "dbname": "secret_dbname",
    "username": "catalog_app",
    "password": "mot-de-passe-factice",
}
BOOTSTRAP = {"CONFIG_SOURCE": "aws", "SSM_PATH_PREFIX": PREFIX, "DB_SECRET_ID": SECRET_ID,
             "SECRET_KEY_SECRET_ID": KEY_SECRET_ID}


class FakeSSM:
    def __init__(self, values=None, error=None, extra_pages=False):
        self.values, self.error, self.extra_pages = values, error, extra_pages
        self.calls = []

    def get_paginator(self, op):
        assert op == "get_parameters_by_path"
        return self

    def paginate(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        items = [{"Name": PREFIX + k, "Value": v} for k, v in (self.values or {}).items()]
        if self.extra_pages:  # simule la pagination AWS (10 paramètres par page)
            yield {"Parameters": items[:2]}
            yield {"Parameters": items[2:]}
        else:
            yield {"Parameters": items}


class FakeSecrets:
    def __init__(self, secret=None, raw=None, error=None):
        self.secret, self.raw, self.error = secret, raw, error
        self.calls = []

    key_raw = KEY_VALUE      # contenu texte brut du secret SECRET_KEY (None = secret binaire)
    key_error = None

    def get_secret_value(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        if kwargs["SecretId"] == KEY_SECRET_ID:
            if self.key_error:
                raise self.key_error
            return {"SecretString": self.key_raw} if self.key_raw is not None else {"SecretBinary": b"x"}
        return {"SecretString": self.raw if self.raw is not None else json.dumps(self.secret)}


def factory(ssm=None, secrets=None):
    clients = {"ssm": ssm or FakeSSM(SSM_VALUES), "secretsmanager": secrets or FakeSecrets(SECRET)}
    return lambda service: clients[service]


def load(ssm=None, secrets=None, bootstrap=None):
    return load_config(bootstrap or BOOTSTRAP, client_factory=factory(ssm, secrets))


# --- cas nominal
def test_aws_mode_loads_everything():
    cfg = load()
    assert cfg.config_source == "aws"
    assert cfg.app_env == "production" and cfg.is_production
    assert cfg.asset_base_url == "https://assets.example.com/images"
    assert cfg.secret_key == "cle-de-test-longue-et-factice"


def test_database_url_is_built_from_ssm_host_and_secret_credentials():
    url = urlsplit(load().database_url)
    assert url.scheme == "postgresql"
    assert url.hostname == SSM_VALUES["DB_HOST"]          # Parameter Store prime sur le secret
    assert url.path == "/product_catalog"
    assert url.port == 5432
    assert unquote(url.username) == "catalog_app"
    assert unquote(url.password) == "mot-de-passe-factice"
    assert "sslmode=require" in url.query


def test_secret_fields_are_used_when_ssm_has_no_db_parameters():
    ssm = FakeSSM({"APP_ENV": "production"})
    url = urlsplit(load(ssm=ssm).database_url)
    assert url.hostname == SECRET["host"] and url.path == "/secret_dbname"


def test_password_with_special_characters_is_encoded():
    secret = {**SECRET, "password": "p@ss:w/o?r#d%1 é"}
    url = urlsplit(load(secrets=FakeSecrets(secret)).database_url)
    assert unquote(url.password) == "p@ss:w/o?r#d%1 é"
    assert url.hostname == SSM_VALUES["DB_HOST"]  # l'URL n'est pas cassée


def test_ssm_is_read_non_recursively_with_decryption():
    ssm = FakeSSM(SSM_VALUES)
    load(ssm=ssm)
    assert ssm.calls == [{"Path": PREFIX, "Recursive": False, "WithDecryption": True}]


def test_prefix_without_trailing_slash_is_accepted():
    ssm = FakeSSM(SSM_VALUES)
    load(ssm=ssm, bootstrap={**BOOTSTRAP, "SSM_PATH_PREFIX": "/techsahel/production"})
    assert ssm.calls[0]["Path"] == PREFIX


def test_pagination_is_followed():
    assert load(ssm=FakeSSM(SSM_VALUES, extra_pages=True)).app_name == SSM_VALUES["APP_NAME"]


def test_unknown_parameters_are_ignored_and_reported_by_name_only(caplog):
    ssm = FakeSSM({**SSM_VALUES, "SOMETHING_ELSE": "valeur-sensible"})
    with caplog.at_level(logging.INFO):
        cfg = load(ssm=ssm)
    assert "SOMETHING_ELSE" in caplog.text
    assert "valeur-sensible" not in caplog.text
    assert cfg.app_env == "production"


def test_ordinary_environment_variables_are_ignored_in_aws_mode():
    # Pas de contournement : DATABASE_URL / APP_ENV de l'environnement ne comptent pas.
    boot = {**BOOTSTRAP, "DATABASE_URL": "postgresql://evil@elsewhere/x", "APP_ENV": "development",
            "LOG_LEVEL": "DEBUG"}
    cfg = load(bootstrap=boot)
    assert "elsewhere" not in cfg.database_url
    assert cfg.app_env == "production" and cfg.log_level == "INFO"


def test_clients_are_never_built_in_env_mode():
    def boom(_service):
        raise AssertionError("aucun client AWS ne doit être créé en mode env")
    cfg = load_config({"DATABASE_URL": "postgresql://u@h/d", "CONFIG_SOURCE": "env"}, client_factory=boom)
    assert cfg.config_source == "env"


def test_default_mode_is_env():
    assert load_config({"DATABASE_URL": "postgresql://u@h/d"}).config_source == "env"


# --- erreurs : le service doit refuser de démarrer, avec un message clair et sans fuite
def test_invalid_config_source():
    with pytest.raises(ConfigError):
        load_config({"CONFIG_SOURCE": "cloud", "DATABASE_URL": "postgresql://x"})


@pytest.mark.parametrize("missing", ["SSM_PATH_PREFIX", "DB_SECRET_ID", "SECRET_KEY_SECRET_ID"])
def test_bootstrap_variables_are_required(missing):
    boot = {k: v for k, v in BOOTSTRAP.items() if k != missing}
    with pytest.raises(ConfigError, match=missing):
        load(bootstrap=boot)


def test_prefix_must_start_with_slash():
    with pytest.raises(ConfigError, match="commencer par"):
        load(bootstrap={**BOOTSTRAP, "SSM_PATH_PREFIX": "techsahel/production/"})


def test_app_env_is_mandatory_in_aws_mode():
    ssm = FakeSSM({k: v for k, v in SSM_VALUES.items() if k != "APP_ENV"})
    with pytest.raises(ConfigError, match="APP_ENV"):
        load(ssm=ssm)


# --- SECRET_KEY : secret texte brut dans Secrets Manager
def test_secret_key_is_read_from_secrets_manager_as_plain_text():
    secrets = FakeSecrets(SECRET)
    assert load(secrets=secrets).secret_key == KEY_VALUE
    assert {"SecretId": KEY_SECRET_ID} in secrets.calls


@pytest.mark.parametrize("raw,expected", [(KEY_VALUE + "\n", KEY_VALUE), ("  " + KEY_VALUE + " \r\n", KEY_VALUE)])
def test_secret_key_whitespace_is_trimmed(raw, expected):
    secrets = FakeSecrets(SECRET)
    secrets.key_raw = raw
    assert load(secrets=secrets).secret_key == expected


@pytest.mark.parametrize("raw", ["", "   \n", None])
def test_empty_or_binary_secret_key_is_rejected(raw):
    secrets = FakeSecrets(SECRET)
    secrets.key_raw = raw
    with pytest.raises(ConfigError, match="SECRET_KEY"):
        load(secrets=secrets)


def test_secret_key_read_failure_is_reported_without_leaking_details():
    secrets = FakeSecrets(SECRET)
    secrets.key_error = FakeClientError("AccessDeniedException")
    with pytest.raises(ConfigError) as exc:
        load(secrets=secrets)
    assert "SECRET_KEY" in str(exc.value) and "AccessDeniedException" in str(exc.value)
    assert "123456789012" not in str(exc.value)


def test_secret_key_in_parameter_store_is_ignored(caplog):
    # SECRET_KEY ne vient QUE de Secrets Manager, même si un paramètre du même nom existe.
    ssm = FakeSSM({**SSM_VALUES, "SECRET_KEY": "valeur-de-parameter-store"})
    with caplog.at_level(logging.INFO):
        cfg = load(ssm=ssm)
    assert cfg.secret_key == KEY_VALUE
    assert "valeur-de-parameter-store" not in caplog.text


class FakeClientError(Exception):
    def __init__(self, code):
        super().__init__(f"An error occurred ({code}) with ARN arn:aws:ssm:eu-west-3:123456789012:parameter/x")
        self.response = {"Error": {"Code": code, "Message": "détail avec arn:aws:iam::123456789012:role/r"}}


def test_parameter_store_access_denied_is_reported_without_leaking_details():
    with pytest.raises(ConfigError) as exc:
        load(ssm=FakeSSM(error=FakeClientError("AccessDeniedException")))
    msg = str(exc.value)
    assert "AccessDeniedException" in msg and "Parameter Store" in msg
    assert "123456789012" not in msg


def test_secrets_manager_failure_is_reported():
    with pytest.raises(ConfigError, match="Secrets Manager"):
        load(secrets=FakeSecrets(error=FakeClientError("ResourceNotFoundException")))


def test_unreachable_aws_is_reported():
    with pytest.raises(ConfigError, match="Parameter Store"):
        load(ssm=FakeSSM(error=ConnectionError("endpoint injoignable")))


@pytest.mark.parametrize("raw,fragment", [
    ("pas du json", "JSON valide"),
    ("[1, 2]", "objet JSON"),
    (json.dumps({"username": "u"}), "password"),
    (json.dumps({"password": "p"}), "username"),
])
def test_malformed_secret_is_rejected(raw, fragment):
    with pytest.raises(ConfigError, match=fragment):
        load(secrets=FakeSecrets(raw=raw))


def test_missing_host_and_dbname_everywhere_is_rejected():
    ssm = FakeSSM({"APP_ENV": "production"})
    secret = {"username": "u", "password": "p"}
    with pytest.raises(ConfigError, match="Hôte ou nom de base"):
        load(ssm=ssm, secrets=FakeSecrets(secret))


def test_client_creation_failure_is_reported():
    def no_region(_service):
        raise RuntimeError("You must specify a region.")
    with pytest.raises(ConfigError, match="AWS_REGION"):
        load_config(BOOTSTRAP, client_factory=no_region)


def test_password_and_secret_key_never_appear_in_logs_or_errors(caplog):
    with caplog.at_level(logging.DEBUG):
        load()
        with pytest.raises(ConfigError) as exc:
            load(ssm=FakeSSM(error=FakeClientError("ThrottlingException")))
    assert "mot-de-passe-factice" not in caplog.text + str(exc.value)
    assert "cle-de-test-longue-et-factice" not in caplog.text + str(exc.value)


# --- appels réels validés contre le modèle d'API (aucun réseau : Stubber)
def test_calls_match_the_real_aws_api_shapes(monkeypatch):
    boto3 = pytest.importorskip("boto3")
    from botocore.stub import Stubber

    for var in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"):
        monkeypatch.setenv(var, "testing")  # valeurs factices : requises par boto3, aucun appel réseau
    ssm = boto3.client("ssm", region_name="eu-west-3")
    sm = boto3.client("secretsmanager", region_name="eu-west-3")

    with Stubber(ssm) as s1, Stubber(sm) as s2:
        s1.add_response(
            "get_parameters_by_path",
            {"Parameters": [{"Name": PREFIX + k, "Type": "String", "Value": v} for k, v in SSM_VALUES.items()]},
            {"Path": PREFIX, "Recursive": False, "WithDecryption": True},
        )
        s2.add_response("get_secret_value", {"SecretString": json.dumps(SECRET), "Name": SECRET_ID},
                        {"SecretId": SECRET_ID})
        s2.add_response("get_secret_value", {"SecretString": KEY_VALUE + "\n", "Name": KEY_SECRET_ID},
                        {"SecretId": KEY_SECRET_ID})
        cfg = load_config(BOOTSTRAP, client_factory=lambda svc: {"ssm": ssm, "secretsmanager": sm}[svc])
        s1.assert_no_pending_responses()
        s2.assert_no_pending_responses()
    assert cfg.app_env == "production"
