# Configuration

## Principe

Toute valeur qui change d'un environnement à l'autre vient d'une **variable d'environnement**, lue une fois au démarrage par `src/catalog/config.py`. Le code ne contient ni identifiants de base, ni mots de passe, ni clés API, ni credentials AWS, ni secrets.

```text
variables d'environnement ──► load_config() ──► Config (immuable) ──► create_app()
```

L'origine des variables est **indifférente pour l'application** : fichier `.env` en local, `Environment=` / `EnvironmentFile=` de systemd, variables d'un conteneur, ou valeurs récupérées depuis AWS Systems Manager Parameter Store *par l'infrastructure* avant le démarrage.

## Référence des variables

| Variable | Défaut | Obligatoire | Secret | Description |
|---|---|---|---|---|
| `APP_ENV` | `development` | non | non | `development`, `testing` ou `production`. En `production` : `SECRET_KEY` obligatoire, HSTS activé, `seed-db` refusé |
| `APP_NAME` | `TechSahel Catalogue` | non | non | Nom affiché dans les titres de page |
| `DATABASE_URL` | — | **oui** | **oui** | DSN PostgreSQL : `postgresql://user:motdepasse@hote:5432/base`. Peut aussi inclure `?sslmode=require` |
| `SECRET_KEY` | *(vide)* | **oui en production** | **oui** | Signe les jetons de formulaire (CSRF). Même valeur sur toutes les instances. En dev/test, une valeur factice non secrète est utilisée |
| `LOG_LEVEL` | `INFO` | non | non | `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `STORAGE_BACKEND` | `local` | non | non | `local` ou `remote` (voir ci-dessous) |
| `ASSET_BASE_URL` | `/static/images` | non | non | Préfixe des URL d'images. Ex. `https://mon-bucket.s3.eu-west-3.amazonaws.com/images` |
| `LOCAL_IMAGE_DIR` | `static/images` | non | non | Dossier des images pour le backend `local` (relatif à la racine du projet) |
| `ITEMS_PER_PAGE` | `12` | non | non | Taille de page du catalogue (1–100) |
| `TRUSTED_PROXY_HOPS` | `0` | non | non | Nombre de proxys/load balancers de confiance (0–5), pour lire `X-Forwarded-For/Proto/Host` |
| `TEST_DATABASE_URL` | — | tests uniquement | oui | Base **jetable** pour pytest (vidée à chaque session) |

Valeurs invalides → l'application **n'est pas démarrée** et affiche une `ConfigError` explicite (fail fast), ce qui rend les erreurs de déploiement évidentes. `./run.sh` ne charge `.env` que s'il existe ; en production, ce fichier n'est pas utilisé.

Générer une clé secrète :

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Vérifier la configuration sans l'afficher en clair :

```bash
PYTHONPATH=src python -m catalog.cli check-config
```

## Fichiers

| Fichier | Versionné | Contenu |
|---|---|---|
| `.env.example` | oui | Valeurs d'exemple **non secrètes** |
| `.env` | **non** (`.gitignore`) | Valeurs locales réelles du développeur |

## Backends de stockage d'images

- `local` : l'image est servie par Flask à `/static/images/<clé>`.
- `remote` : l'application **n'accède pas** au stockage ; elle construit uniquement `ASSET_BASE_URL/<clé>`. Pas de SDK, pas de credentials côté application. Le téléversement des images relève d'un autre processus (ex. `aws s3 sync` lancé par l'ingénieur ou la CI).

## Compatibilité future avec AWS Systems Manager Parameter Store

L'application **ne dépend pas du SDK AWS** (principe d'indépendance vis-à-vis du fournisseur) : elle ne sait lire que l'environnement. L'infrastructure fournit donc les paramètres, par exemple :

```text
/techsahel/catalog/prod/APP_ENV            (String)
/techsahel/catalog/prod/LOG_LEVEL          (String)
/techsahel/catalog/prod/ASSET_BASE_URL     (String)
/techsahel/catalog/prod/STORAGE_BACKEND    (String)
/techsahel/catalog/prod/DATABASE_URL       (SecureString)
/techsahel/catalog/prod/SECRET_KEY         (SecureString)
```

Mécanisme possible (à réaliser dans le projet d'infrastructure, **pas ici**) : un petit script exécuté au démarrage de l'instance (ou par `ExecStartPre` de systemd) appelle `aws ssm get-parameters-by-path --with-decryption` avec le **rôle IAM de l'instance**, écrit un fichier d'environnement lisible uniquement par l'utilisateur du service (`chmod 600`), puis systemd le charge via `EnvironmentFile=`. Le nom du paramètre correspond au nom de la variable : le script n'a pas de table de correspondance à maintenir.

Si un jour la lecture directe de Parameter Store devenait nécessaire, la seule modification serait dans `load_config()` (une source de plus derrière la même interface `Config`) : le reste du code ne changerait pas.

## Ajouter une variable

1. La lire dans `load_config()` avec une valeur par défaut raisonnable et une validation.
2. L'ajouter à la dataclass `Config`.
3. La documenter dans `.env.example` et dans ce fichier.
