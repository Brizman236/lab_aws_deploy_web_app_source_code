# Architecture applicative

Application **monolithique** de petite taille : un seul processus Python (Flask) servi par gunicorn, une base PostgreSQL, des fichiers statiques.

```text
Navigateur
    │
    ▼
Application Web (Flask)
    │
    ├── Catalogue produits
    ├── Détails produits
    ├── Recherche
    └── Gestion des demandes
             │
             ▼
        PostgreSQL
```

Diagrammes détaillés : [../diagrams/application-architecture.md](../diagrams/application-architecture.md).

## Composants (`src/catalog/`)

| Module | Responsabilité |
|---|---|
| `__init__.py` (`create_app`) | Fabrique de l'application : charge la config, configure les logs, les en-têtes de sécurité, les gestionnaires d'erreurs, la connexion DB par requête |
| `config.py` | Lit et valide les variables d'environnement → objet `Config` immuable |
| `routes.py` | Routes HTTP (blueprint `web`), CSRF, orchestration |
| `validation.py` | Validation/normalisation des saisies (formulaires et paramètres de recherche) |
| `repository.py` | **Toutes** les requêtes SQL (paramétrées) |
| `db.py` | Connexion psycopg, exécution de `schema.sql` / `seed.sql`, `ping()` |
| `storage.py` | Abstraction clé d'image → URL publique |
| `cli.py` | `init-db`, `seed-db`, `check-config` |

Dépendances : `routes → validation, repository, db`, `repository → (SQL)`. La logique n'importe jamais de SDK cloud.

## Flux d'une requête

Exemple : `GET /produits?q=routeur&category=reseau`

1. gunicorn transmet la requête WSGI à Flask (derrière un load balancer, `ProxyFix` lit `X-Forwarded-*` si `TRUSTED_PROXY_HOPS > 0`).
2. `before_request` : démarre un chrono et attribue un `request_id` (réutilise `X-Request-Id` s'il est fourni).
3. `catalog()` → `parse_catalog_filters()` normalise les paramètres (liste blanche pour le tri et la disponibilité, bornes numériques).
4. `repository.search_products()` ouvre (à la demande) une connexion PostgreSQL liée à la requête, exécute `COUNT(*)` puis la requête paginée, **avec paramètres liés**.
5. Jinja2 rend `catalog.html` (échappement HTML automatique). Pour chaque produit, `image_url(image_key)` délègue à `storage.py`.
6. `after_request` : ajoute les en-têtes de sécurité, journalise `request_id méthode chemin → statut durée`.
7. `teardown_appcontext` ferme la connexion.

### Flux d'une demande client (`POST /contact` ou `/produits/<slug>/demande`)

```text
GET formulaire → jeton CSRF signé (valable 2 h) inséré dans la page
POST →  honeypot rempli ?        → redirection silencieuse (rien n'est stocké)
        jeton CSRF invalide ?    → 400 + formulaire réaffiché
        validation échoue ?      → 422 + erreurs par champ, saisie conservée
        sinon INSERT inquiries   → log de l'id seulement → 302 /merci (Post/Redirect/Get)
```

Pour une demande liée à un produit, `product_id` est déterminé par **l'URL**, jamais par un champ du formulaire.

## Interactions avec la base de données

- Une connexion par requête (courte durée de vie, fermée en fin de requête). Simple et suffisant à cette échelle ; un pool (`psycopg_pool`) ou **RDS Proxy** serait une optimisation future documentée, non nécessaire ici.
- SQL écrit à la main dans `repository.py` (pas d'ORM) : le modèle est petit et le SQL lisible par l'ingénieur qui exploitera la base.
- Lectures sans transaction explicite ; l'écriture (`INSERT … RETURNING id`) est validée par `commit()`.
- `schema.sql` est **idempotent** (`IF NOT EXISTS`) ; `seed.sql` vide puis recharge (interdit en production par la CLI).

## Fichiers statiques

- Code applicatif : `static/css`, `static/js` (servis par Flask en local ; en production, nginx/ALB/CDN peut les servir).
- **Images produits** : stockées *hors base*. La base contient `image_key` ; `storage.py` fabrique l'URL :
  - `STORAGE_BACKEND=local` → `/static/images/<clé>` ;
  - `STORAGE_BACKEND=remote` → `<ASSET_BASE_URL>/<clé>` (ex. S3/CloudFront).
- Clé absente ou invalide (`../`, `/`, espaces…) → image `placeholder.svg`, ce qui évite aussi toute traversée de chemin.

## Configuration

Variables d'environnement lues une seule fois au démarrage (`load_config`) ; l'application **refuse de démarrer** si la configuration est invalide (`DATABASE_URL` absente, `APP_ENV` inconnu, `SECRET_KEY` absente en production…). Voir [CONFIGURATION.md](CONFIGURATION.md).

## Gestion des erreurs

| Cas | Réponse |
|---|---|
| Page/produit inconnu | 404, page HTML personnalisée |
| Méthode non autorisée / corps trop gros | 405 / 413, page personnalisée |
| Saisie invalide | 422, formulaire réaffiché avec messages |
| CSRF invalide/expiré | 400, formulaire réaffiché |
| PostgreSQL injoignable | 503, message neutre ; log sans détails sensibles |
| Exception inattendue | 500, page générique ; la trace complète va **dans les logs** seulement |
| `/health*` | Toujours du JSON, jamais de page HTML |

Aucune trace d'exécution ni détail technique n'est renvoyé au client.

## Journalisation

- Module `logging` standard, sortie **stdout/stderr** (format `horodatage niveau logger message`), niveau via `LOG_LEVEL`. Sur un serveur, systemd/journald ou l'agent CloudWatch collectent ce flux : l'application n'écrit pas de fichiers de log.
- Chaque requête : `request_id`, méthode, chemin, statut, durée. Le `request_id` est renvoyé dans l'en-tête `X-Request-Id` pour corréler un incident.
- **Jamais journalisés** : corps de requête, nom, e-mail, téléphone, message, `DATABASE_URL`, `SECRET_KEY`. Une demande créée est tracée par son seul `id`. (Vérifié par un test.)

## Validation des données

Côté serveur uniquement fiable ; les attributs HTML (`required`, `maxlength`) ne sont qu'un confort.

| Champ | Règle |
|---|---|
| `customer_name` | 2–120 caractères après nettoyage |
| `customer_email` | obligatoire, ≤ 254, format e-mail, mis en minuscules |
| `customer_phone` | facultatif, format `+`, chiffres, espaces, `.()-` |
| `message` | 10–2000 caractères |
| `product_id` | entier existant (ou imposé par l'URL) |
| Paramètres de recherche | liste blanche (tri, disponibilité), bornes numériques, `q` tronqué à 100 |

Les caractères de contrôle sont supprimés. La base applique en plus ses propres `CHECK` (défense en profondeur).

## Endpoints

| Méthode | Chemin | Rôle |
|---|---|---|
| GET | `/` | Accueil |
| GET | `/produits` | Catalogue (`q`, `category`, `availability`, `min_price`, `max_price`, `sort`, `page`) |
| GET | `/produits/<slug>` | Détail produit + formulaire |
| POST | `/produits/<slug>/demande` | Demande liée à un produit |
| GET/POST | `/contact` | Contact général |
| GET | `/merci`, `/a-propos` | Pages statiques |
| GET | `/health` | Santé complète : 200 `ok` / 503 `degraded` (base HS) |
| GET | `/health/live` | Liveness : 200 tant que le processus répond |

## Absence d'état (stateless)

Aucune session serveur, aucun fichier écrit localement, aucun cache en mémoire partagé. Le jeton CSRF est signé avec `SECRET_KEY` (pas stocké). Conséquence : n'importe quelle instance peut traiter n'importe quelle requête, ce qui permet plusieurs instances derrière un load balancer, à condition qu'elles partagent la même `SECRET_KEY`.
