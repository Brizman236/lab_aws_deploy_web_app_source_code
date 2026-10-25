# Diagrammes d'architecture applicative

## Vue d'ensemble

```mermaid
flowchart TD
    B[Navigateur] -->|HTTP| W[Application Web Flask<br/>gunicorn]
    W --> C[Catalogue produits]
    W --> D[Détails produits]
    W --> S[Recherche et filtres]
    W --> I[Gestion des demandes]
    C & D & S & I --> R[repository.py<br/>SQL paramétré]
    R --> P[(PostgreSQL)]
    W -.->|clé image → URL| ST[storage.py]
    ST -.-> L["static/images (local)"]
    ST -.-> O[(Stockage objet<br/>futur S3)]
    CFG[Variables d'environnement] --> W
    W -->|stdout| LOG[Logs]
    H["/health"] --> W
```

Version texte :

```text
Navigateur
    │
    ▼
Application Web (Flask)  ◄── variables d'environnement (config)
    │                    ──► logs (stdout)
    ├── Catalogue produits ─┐
    ├── Détails produits    ├──► repository.py ──► PostgreSQL
    ├── Recherche           │
    └── Gestion des demandes┘
    │
    └── storage.py : image_key ──► /static/images/<clé>   (local)
                                   <ASSET_BASE_URL>/<clé>  (S3 plus tard)
```

## Séquence : consultation du catalogue

```mermaid
sequenceDiagram
    participant U as Navigateur
    participant F as Flask (routes)
    participant V as validation
    participant R as repository
    participant DB as PostgreSQL
    U->>F: GET /produits?q=routeur&category=reseau
    F->>V: parse_catalog_filters(args)
    V-->>F: filtres normalisés
    F->>R: search_products(conn, filtres)
    R->>DB: SELECT … WHERE … (paramètres liés)
    DB-->>R: lignes + total
    R-->>F: produits
    F-->>U: HTML (images : URL depuis image_key)
```

## Séquence : envoi d'une demande client

```mermaid
sequenceDiagram
    participant U as Navigateur
    participant F as Flask
    participant V as validation
    participant DB as PostgreSQL
    U->>F: GET /produits/{slug}
    F-->>U: page + jeton CSRF signé
    U->>F: POST /produits/{slug}/demande
    alt honeypot rempli
        F-->>U: 302 /merci (rien stocké)
    else jeton invalide
        F-->>U: 400 formulaire
    else saisie invalide
        F->>V: validate_inquiry
        F-->>U: 422 erreurs par champ
    else valide
        F->>DB: INSERT INTO inquiries … RETURNING id
        F-->>U: 302 /merci
    end
```

## Santé

```mermaid
flowchart LR
    LB[Load balancer / supervision] -->|GET /health| A[Application]
    A -->|SELECT 1| DB[(PostgreSQL)]
    DB -- OK --> A
    A -- 200 ok --> LB
    DB -. injoignable .-> A
    A -. 503 degraded .-> LB
```
