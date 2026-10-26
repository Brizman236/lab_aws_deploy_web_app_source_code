# Configuration

## Principe

Toute valeur qui change d'un environnement à l'autre est lue **une seule fois au démarrage** par `src/catalog/config.py`, qui produit un objet `Config` immuable. Le code ne contient ni identifiants de base, ni mots de passe, ni clés API, ni credentials AWS, ni secrets.

Deux **modes d'exécution**, choisis par `CONFIG_SOURCE` :

| | Mode `env` (défaut, local) | Mode `aws` (production) |
|---|---|---|
| Activation | `CONFIG_SOURCE=env` ou variable absente | `CONFIG_SOURCE=aws` |
| Source des valeurs | Variables d'environnement, fichier `.env` | **Parameter Store** (valeurs ordinaires) + **Secrets Manager** (identifiants de la base, `SECRET_KEY`) |
| Variables d'environnement ordinaires | Lues | **Ignorées** (AWS est la seule source) |
| boto3 | Jamais importé | Importé à la demande (`requirements-aws.txt`) |
| Credentials AWS | Aucun | Rôle IAM de l'instance (jamais de clé dans le code ni dans `.env`) |

```text
mode env :  .env / environnement ─────────────────────────────┐
                                                              ├─► load_config() ─► Config ─► create_app()
mode aws :  Parameter Store ─┐                                │
            Secrets Manager ─┴─► config_sources.py ───────────┘
```

Le reste de l'application ne sait pas d'où viennent les valeurs. **Tout le code AWS est isolé dans `src/catalog/config_sources.py`**, importé uniquement en mode `aws`.

## Référence des variables

| Variable | Défaut | Obligatoire | Secret | Description |
|---|---|---|---|---|
| `CONFIG_SOURCE` | `env` | non | non | `env` (local) ou `aws` (Parameter Store + Secrets Manager). Valeur autre : l'application ne démarre pas |
| `SSM_PATH_PREFIX` | — | **oui en mode `aws`** | non | Chemin Parameter Store, doit commencer par `/` (ex. `/techsahel/production/`) |
| `DB_SECRET_ID` | — | **oui en mode `aws`** | non | Nom ou ARN du secret Secrets Manager (JSON) contenant les identifiants de la base |
| `SECRET_KEY_SECRET_ID` | — | **oui en mode `aws`** | non | Nom ou ARN du secret Secrets Manager (**texte brut**) contenant la `SECRET_KEY` |
| `AWS_REGION` | — | **oui en mode `aws`** | non | Région des clients AWS (ex. `eu-west-3`), lue par boto3 |
| `APP_ENV` | `development` | non | non | `development`, `testing` ou `production`. En `production` : `SECRET_KEY` obligatoire, HSTS activé, `seed-db` refusé |
| `APP_NAME` | `TechSahel Catalogue` | non | non | Nom affiché dans les titres de page |
| `DATABASE_URL` | — | **oui** | **oui** | DSN PostgreSQL : `postgresql://user:motdepasse@hote:5432/base`. Peut aussi inclure `?sslmode=require` |
| `SECRET_KEY` | *(vide)* | **oui en production** | **oui** | Signe les jetons de formulaire (CSRF). Même valeur sur toutes les instances. En dev/test, une valeur factice non secrète est utilisée. En mode `aws`, elle vient du secret `SECRET_KEY_SECRET_ID` |
| `LOG_LEVEL` | `INFO` | non | non | `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `STORAGE_BACKEND` | `local` | non | non | `local` ou `remote` (voir ci-dessous) |
| `ASSET_BASE_URL` | `/static/images` | non | non | Préfixe des URL d'images. Ex. `https://mon-bucket.s3.eu-west-3.amazonaws.com/images` |
| `LOCAL_IMAGE_DIR` | `static/images` | non | non | Dossier des images pour le backend `local` (relatif à la racine du projet) |
| `ITEMS_PER_PAGE` | `12` | non | non | Taille de page du catalogue (1–100) |
| `TRUSTED_PROXY_HOPS` | `0` | non | non | Nombre de proxys/load balancers de confiance (0–5), pour lire `X-Forwarded-For/Proto/Host` |
| `TEST_DATABASE_URL` | — | tests uniquement | oui | Base **jetable** pour pytest (vidée à chaque session) |

Valeurs invalides → l'application **n'est pas démarrée** et affiche une `ConfigError` explicite (fail fast), ce qui rend les erreurs de déploiement évidentes. `./run.sh` ne charge `.env` que s'il existe ; en mode `aws`, ses valeurs ordinaires sont ignorées.

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

## Mode `aws` : Parameter Store et Secrets Manager

### Variables « bootstrap »

En mode `aws`, seules cinq variables d'environnement sont lues, car elles indiquent **où** aller chercher le reste : `CONFIG_SOURCE=aws`, `SSM_PATH_PREFIX`, `DB_SECRET_ID`, `SECRET_KEY_SECRET_ID`, `AWS_REGION`. Aucune n'est secrète. L'infrastructure les fournit au service (par exemple `Environment=` de systemd).

### Parameter Store

Tous les paramètres situés **directement** sous `SSM_PATH_PREFIX` sont lus (`SecureString` déchiffrés, pagination gérée). Le **nom du paramètre est le nom de la variable** :

```text
/techsahel/production/APP_ENV            String        obligatoire (pas de repli sur « development »)
/techsahel/production/APP_NAME           String
/techsahel/production/ASSET_BASE_URL     String
/techsahel/production/DB_HOST            String        optionnel (sinon : champ host du secret)
/techsahel/production/DB_NAME            String        optionnel (sinon : champ dbname du secret)
```

Noms acceptés : `APP_ENV`, `APP_NAME`, `LOG_LEVEL`, `STORAGE_BACKEND`, `ASSET_BASE_URL`, `LOCAL_IMAGE_DIR`, `ITEMS_PER_PAGE`, `TRUSTED_PROXY_HOPS`, `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_SSLMODE`. Tout autre paramètre du chemin est **ignoré** et signalé dans les logs par son nom (jamais sa valeur). C'est le cas de `SECRET_KEY` : même si un paramètre de ce nom existe, il n'est **pas** utilisé.

### Secrets Manager

`DB_SECRET_ID` désigne un secret JSON au format RDS :

```json
{ "engine": "postgres", "host": "…", "port": 5432, "dbname": "product_catalog",
  "username": "catalog_app", "password": "…" }
```

`username` et `password` sont obligatoires. **Le mot de passe n'existe que dans ce secret.**

`SECRET_KEY_SECRET_ID` désigne un second secret, en **texte brut** (pas de JSON) : son contenu est la clé telle quelle. Les espaces et retours à la ligne en début et fin sont retirés. Un secret vide ou binaire est refusé.

### Construction de `DATABASE_URL`

L'application assemble elle-même l'URL de connexion :

| Élément | Source (par priorité) |
|---|---|
| utilisateur | `DB_USER` (Parameter Store) sinon `username` du secret |
| mot de passe | `password` du secret **uniquement** |
| hôte | `DB_HOST` (Parameter Store) sinon `host` du secret |
| port | `DB_PORT` sinon `port` du secret sinon `5432` |
| base | `DB_NAME` (Parameter Store) sinon `dbname` du secret |
| TLS | `DB_SSLMODE` sinon `require` (connexion chiffrée vers RDS) |

Identifiant et mot de passe sont encodés en pourcentage : un mot de passe contenant `@ : / ? # %` ne casse pas l'URL.

### Comportement en cas de problème

| Situation | Résultat |
|---|---|
| `SSM_PATH_PREFIX` ou `DB_SECRET_ID` absent, préfixe sans `/` initial | Démarrage refusé, message explicite |
| AWS injoignable, accès refusé, région manquante, credentials absents | Démarrage refusé ; le message contient la classe d'erreur et son code (ex. `AccessDeniedException`), **jamais de valeur** |
| `APP_ENV` absent de Parameter Store | Démarrage refusé |
| Secret `SECRET_KEY` illisible, vide ou binaire | Démarrage refusé |
| Secret mal formé (JSON invalide, `username`/`password` manquant) | Démarrage refusé |

**Aucun repli silencieux** vers le mode local : en production, une configuration incomplète doit se voir immédiatement. Les valeurs sont lues une fois par processus : modifier un paramètre demande de **redémarrer** le service.

### Permissions IAM nécessaires (rôle de l'instance)

```text
ssm:GetParametersByPath      sur arn:aws:ssm:<région>:<compte>:parameter/techsahel/production
secretsmanager:GetSecretValue  sur l'ARN du secret de la base ET sur l'ARN du secret SECRET_KEY
kms:Decrypt                  seulement si une clé KMS gérée par vous chiffre les paramètres SecureString ou les secrets
```

Prévoir aussi la **sortie réseau** de l'instance vers les endpoints Systems Manager et Secrets Manager (NAT ou VPC endpoints en sous-réseau privé).

### Vérifier sans afficher de secret

```bash
CONFIG_SOURCE=aws SSM_PATH_PREFIX=/techsahel/production/ DB_SECRET_ID=<secret-db> SECRET_KEY_SECRET_ID=<secret-key> AWS_REGION=eu-west-3 \
  PYTHONPATH=src python -m catalog.cli check-config
```

La commande affiche le mode et les réglages non secrets ; `DATABASE_URL` est seulement indiquée comme « définie ».

## Ajouter une variable

1. La lire dans `load_config()` avec une valeur par défaut raisonnable et une validation.
2. L'ajouter à la dataclass `Config`.
3. La documenter dans `.env.example` et dans ce fichier.
