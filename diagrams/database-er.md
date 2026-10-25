# Diagramme entité-relation

```mermaid
erDiagram
    CATEGORIES ||--o{ PRODUCTS : "regroupe"
    PRODUCTS   |o--o{ INQUIRIES : "fait l'objet de"

    CATEGORIES {
        int id PK
        varchar name UK
        varchar slug UK
        text description
        timestamptz created_at
    }
    PRODUCTS {
        int id PK
        int category_id FK "NOT NULL, ON DELETE RESTRICT"
        varchar name
        varchar slug UK
        varchar brand
        text description
        int price_xof "CHECK >= 0"
        varchar stock_status "CHECK in_stock, low_stock, out_of_stock, on_order"
        varchar image_key "clé d'objet, pas de binaire"
        timestamptz created_at
        timestamptz updated_at "trigger"
    }
    INQUIRIES {
        int id PK
        varchar customer_name
        varchar customer_email
        varchar customer_phone "facultatif"
        int product_id FK "NULL = demande générale, ON DELETE SET NULL"
        text message
        varchar status "CHECK new, in_progress, closed"
        timestamptz created_at
    }
```

Version texte :

```text
┌────────────┐ 1      N ┌──────────────┐ 1      N ┌─────────────┐
│ categories │─────────<│   products   │─────────<│  inquiries  │
│ id  PK     │          │ id  PK       │          │ id  PK      │
│ name  UK   │          │ category_id  │ FK       │ product_id  │ FK, nullable
│ slug  UK   │          │   FK NOT NULL│          │ customer_*  │
│ description│          │ slug  UK     │          │ message     │
└────────────┘          │ price_xof    │          │ status      │
                        │ stock_status │          │ created_at  │
                        │ image_key ───┼─► objet  └─────────────┘
                        └──────────────┘   (fichier / S3)
```

## Lecture du diagramme

- Une **catégorie** contient de zéro à plusieurs **produits** ; un produit a **exactement une** catégorie.
- Un **produit** peut recevoir zéro à plusieurs **demandes** ; une demande concerne **zéro ou un** produit (`NULL` = contact général).
- `image_key` n'est pas une relation de base de données : c'est une **référence logique** vers un objet stocké hors base.

## Index

| Table | Index | Colonnes |
|---|---|---|
| categories | PK, UK | `id`, `name`, `slug` |
| products | PK, UK | `id`, `slug` |
| products | `idx_products_category_id` | `category_id` |
| products | `idx_products_stock_status` | `stock_status` |
| products | `idx_products_price` | `price_xof` |
| inquiries | PK | `id` |
| inquiries | `idx_inquiries_product_id` | `product_id` |
| inquiries | `idx_inquiries_status_created` | `status, created_at DESC` |
