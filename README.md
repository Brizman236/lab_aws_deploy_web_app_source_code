# TechSahel – Catalogue de produits et demandes clients

Application web monolithique (Flask + PostgreSQL) qui sert de **workload** à un projet de portfolio *Cloud Engineering* : elle est volontairement simple, réaliste, et conçue pour être migrée ensuite vers AWS. **Ce dépôt ne contient aucune infrastructure AWS** : l'infrastructure (réseau, IAM, EC2, RDS, S3, Parameter Store, Terraform, tests de panne) relève d'un projet séparé.

> TechSahel Solutions est une entreprise **fictive**. Toutes les données (produits, marques, clients, e-mails en `example.com`) sont inventées.

---

## 1. Qu'est-ce que cette application ?

Un site vitrine public de la société informatique fictive **TechSahel Solutions** (Dakar, Sénégal) : un catalogue consultable en ligne, avec des formulaires pour demander un devis. **Il n'y a ni panier, ni paiement en ligne, ni comptes utilisateurs.**

## 2. Problème métier résolu

L'entreprise vend des ordinateurs, du réseau, des écrans et des accessoires, mais ses clients doivent aujourd'hui téléphoner pour connaître l'offre et les prix. Le site permet de **consulter l'offre 24 h/24** et de **centraliser les demandes** (produit précis ou question générale) dans une base de données que l'équipe commerciale peut traiter.

## 3. Qui l'utilise ?

| Utilisateur | Usage |
|---|---|
| Visiteur / client (PME, école, particulier) | Parcourt le catalogue, recherche, envoie une demande ou un message |
| Équipe commerciale *(hors périmètre applicatif)* | Lit la table `inquiries` (SQL) pour répondre aux clients |
| Ingénieur Cloud | Déploie, exploite et dépanne l'application sur AWS |

## 4. Fonctionnalités

- Page d'accueil (catégories, nouveautés, recherche rapide)
- Catalogue avec **recherche texte**, filtres (catégorie, disponibilité, fourchette de prix), tri et pagination
- Page de détail d'un produit (image, prix en FCFA, disponibilité, produits liés)
- **Formulaire de demande** lié à un produit, et **formulaire de contact** général
- Pages « À propos », « Merci » et pages d'erreur personnalisées
- `GET /health` (application + base) et `GET /health/live` (processus seul)

## 5. Données manipulées

| Donnée | Où | Nature |
|---|---|---|
| Catégories, produits, demandes clients | **PostgreSQL** | Relationnelle |
| Images des produits | **Fichiers** (`static/images/`, futur S3) | Objets statiques |

La base ne contient **que la clé** de l'image (ex. `product-image-001.svg`), jamais son contenu. Détails : [docs/DATABASE_DESIGN.md](docs/DATABASE_DESIGN.md) et [docs/DATA_MODEL.md](docs/DATA_MODEL.md).

## 6. Architecture

```text
Navigateur
    │  HTTP
    ▼
Application Flask (monolithe, gunicorn)
    ├── routes.py      → catalogue, détail, recherche, demandes, health
    ├── validation.py  → validation côté serveur
    ├── repository.py  → requêtes SQL paramétrées
    ├── storage.py     → clé d'image → URL (local ou ASSET_BASE_URL)
    └── config.py      → configuration par variables d'environnement
             │
             ▼
        PostgreSQL            Images : /static/images/ (local)  →  S3 (cloud)
```

Voir [docs/APPLICATION_ARCHITECTURE.md](docs/APPLICATION_ARCHITECTURE.md) et les diagrammes dans [diagrams/](diagrams/).

## 7. Technologies

Python 3.11+ · Flask 3 · PostgreSQL 14+ · psycopg 3 (SQL paramétré, sans ORM) · gunicorn · HTML/CSS · ~10 lignes de JavaScript (menu mobile) · pytest. Pas de React, Redis, file de messages ni microservices : aucun besoin applicatif ne les justifie.

## 8. Exécuter l'application en local

Prérequis : Python 3.11+ et un serveur PostgreSQL accessible.

```bash
cd product-catalog

# 1. Environnement Python
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. Base de données (exemple local)
createdb product_catalog
cp .env.example .env          # puis adapter DATABASE_URL à votre PostgreSQL

# 3. Schéma + données de démonstration
./run.sh init-db
./run.sh seed-db

# 4. Lancer
./run.sh                      # http://127.0.0.1:8000
```

Autres commandes : `./run.sh prod` (gunicorn), `./run.sh test` (tests). On peut aussi charger le SQL à la main : `psql "$DATABASE_URL" -f database/schema.sql -f database/seed.sql`.

Vérification rapide : `curl http://127.0.0.1:8000/health` → `{"app":"up","database":"up","environment":"development","status":"ok"}`.

### Avec Docker pour PostgreSQL (option)

```bash
docker run --name catalog-pg -e POSTGRES_PASSWORD=devpassword -e POSTGRES_DB=product_catalog -p 5432:5432 -d postgres:16
# DATABASE_URL=postgresql://postgres:devpassword@localhost:5432/product_catalog
```

## 9. Tests

Les tests d'intégration utilisent une **vraie base PostgreSQL dédiée** (jamais celle de développement : elle est vidée) :

```bash
createdb product_catalog_test
export TEST_DATABASE_URL=postgresql://USER:PASSWORD@localhost:5432/product_catalog_test
./run.sh test        # ou : PYTHONPATH=src pytest
```

62 tests couvrent : démarrage, pages, liste, détail, recherche/filtres/tri/pagination, injection SQL, échappement HTML, demandes clients (succès et erreurs), CSRF, anti-spam, contraintes SQL, `/health` avec base disponible et indisponible, configuration, stockage d'images, absence de données personnelles dans les logs.

## 10. Structure de la base de données

```text
categories 1 ──< N products 1 ──< N inquiries (product_id nullable)
```

Trois tables, clés étrangères, contraintes `CHECK`, index justifiés. Le diagramme ER et les explications sont dans [docs/DATABASE_DESIGN.md](docs/DATABASE_DESIGN.md) et [diagrams/database-er.md](diagrams/database-er.md).

## 11. Gestion de la configuration

Toute la configuration vient de **variables d'environnement** (12-factor) ; rien de spécifique à un environnement n'est dans le code. Voir [.env.example](.env.example) et [docs/CONFIGURATION.md](docs/CONFIGURATION.md).

| Variable | Rôle |
|---|---|
| `APP_ENV` | `development`, `testing` ou `production` |
| `APP_NAME` | Nom affiché |
| `DATABASE_URL` | DSN PostgreSQL (**obligatoire**, secret) |
| `SECRET_KEY` | Signature des jetons de formulaire (obligatoire en production, secret) |
| `LOG_LEVEL` | `DEBUG`, `INFO`, `WARNING`… |
| `STORAGE_BACKEND`, `ASSET_BASE_URL`, `LOCAL_IMAGE_DIR` | Origine des images |
| `ITEMS_PER_PAGE`, `TRUSTED_PROXY_HOPS` | Pagination ; proxys de confiance |

Aucun secret n'est versionné : `.env` est ignoré par git, seul `.env.example` (valeurs factices) l'est.

## 12. Contexte de migration Cloud

L'application est **volontairement conçue pour devenir ultérieurement une charge de travail AWS**, organisée conceptuellement ainsi :

```text
Internet
   │
   ▼
EC2
   │
   ├── PostgreSQL → Amazon RDS
   │
   ├── Fichiers statiques → Amazon S3
   │
   └── Configuration → AWS Systems Manager Parameter Store
```

**Cette architecture AWS n'est pas implémentée ici.** L'objectif est uniquement que l'application soit *compatible au niveau architectural* tout en restant indépendante de l'infrastructure :

- **Base** : seule `DATABASE_URL` change pour pointer vers RDS.
- **Images** : `STORAGE_BACKEND=remote` + `ASSET_BASE_URL` pointant vers S3/CloudFront ; la base ne stocke que des clés. L'application **n'utilise pas le SDK AWS**.
- **Configuration** : variables d'environnement, que l'infrastructure peut alimenter depuis Parameter Store sans toucher au code.
- **Sans état** : aucune session ni fichier local écrit ; plusieurs instances derrière un load balancer fonctionnent (jetons CSRF signés, pas de session serveur).
- **Exploitation** : `/health` (readiness, 503 si base HS) et `/health/live`, logs sur stdout, `TRUSTED_PROXY_HOPS` pour un load balancer.

Détail et justification service par service : [docs/DEPLOYMENT_NOTES.md](docs/DEPLOYMENT_NOTES.md).

## 13. Arborescence

```text
product-catalog/
├── README.md
├── docs/            BUSINESS_CONTEXT, APPLICATION_ARCHITECTURE, DATABASE_DESIGN,
│                    DATA_MODEL, CONFIGURATION, SECURITY, DEPLOYMENT_NOTES
├── diagrams/        application-architecture.md, database-er.md  (Mermaid + ASCII)
├── src/catalog/     __init__ (create_app), config, routes, repository,
│                    validation, storage, db, cli
├── templates/       Pages Jinja2
├── static/          css/, js/, images/ (illustrations SVG fictives)
├── database/        schema.sql, seed.sql
├── scripts/         generate_demo_images.py
├── tests/           pytest (62 tests)
├── .env.example  .gitignore  requirements.txt  pytest.ini  wsgi.py  run.sh
```

## 14. Documentation

[Contexte métier](docs/BUSINESS_CONTEXT.md) · [Architecture applicative](docs/APPLICATION_ARCHITECTURE.md) · [Conception de la base](docs/DATABASE_DESIGN.md) · [Modèle de données](docs/DATA_MODEL.md) · [Configuration](docs/CONFIGURATION.md) · [Sécurité](docs/SECURITY.md) · [Notes de déploiement / migration AWS](docs/DEPLOYMENT_NOTES.md)
