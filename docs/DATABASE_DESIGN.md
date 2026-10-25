# Conception de la base de données

Moteur : **PostgreSQL** (14+). Schéma : [`database/schema.sql`](../database/schema.sql). Données de démonstration : [`database/seed.sql`](../database/seed.sql). Diagramme ER : [../diagrams/database-er.md](../diagrams/database-er.md).

## Vue d'ensemble

```text
Category
   │
   │ 1:N   (une catégorie regroupe plusieurs produits)
   ▼
Product
   │
   │ 1:N   (un produit peut faire l'objet de plusieurs demandes)
   ▼
Inquiry   (product_id NULL = demande générale)
```

Trois tables suffisent : le besoin est un catalogue et une boîte de réception de demandes. Il n'y a volontairement ni table utilisateurs, ni commandes, ni paniers, ni tables d'association.

## Pourquoi ces relations existent

**`categories` 1 — N `products`.** Un produit appartient à exactement une catégorie ; c'est ce qui permet la navigation et le filtre par catégorie. On a retenu une relation 1:N (et non N:N avec des étiquettes) car dans ce catalogue un produit n'a qu'une classification naturelle ; une table d'association serait de la complexité inutile. `category_id` est `NOT NULL` : un produit sans catégorie n'aurait pas de place dans l'interface. `ON DELETE RESTRICT` empêche de supprimer une catégorie encore utilisée.

**`products` 1 — N `inquiries`, optionnelle.** Une demande « pour ce produit » doit pointer vers lui, pour que le commercial sache de quoi on parle et pour mesurer l'intérêt par produit. Mais une demande de contact générale n'a pas de produit : `product_id` est donc **nullable**, ce qui évite deux tables distinctes (demande produit / demande générale). `ON DELETE SET NULL` : si un produit est retiré du catalogue, la demande du client **reste** (elle devient générale) — on ne perd pas l'historique commercial.

## Tables

### `categories`

| Colonne | Type | Rôle |
|---|---|---|
| `id` | `SERIAL` **PK** | Identifiant technique |
| `name` | `VARCHAR(100)` `UNIQUE NOT NULL` | Libellé affiché |
| `slug` | `VARCHAR(100)` `UNIQUE NOT NULL` | Identifiant d'URL / de filtre (`?category=reseau`) |
| `description` | `TEXT` | Texte de présentation |
| `created_at` | `TIMESTAMPTZ` | Date de création |

Contrainte : `slug` ne contient que `[a-z0-9-]` (`categories_slug_format`).

### `products`

| Colonne | Type | Rôle |
|---|---|---|
| `id` | `SERIAL` **PK** | Identifiant technique |
| `category_id` | `INTEGER NOT NULL` **FK → categories(id)** | Catégorie du produit |
| `name` | `VARCHAR(200) NOT NULL` | Nom commercial |
| `slug` | `VARCHAR(200)` `UNIQUE NOT NULL` | URL stable : `/produits/<slug>` |
| `brand` | `VARCHAR(100)` | Marque (fictive) |
| `description` | `TEXT` | Description |
| `price_xof` | `INTEGER NOT NULL` | Prix en FCFA (entier : pas de centimes en XOF, évite les flottants) |
| `stock_status` | `VARCHAR(20) NOT NULL` | Disponibilité (voir contraintes) |
| `image_key` | `VARCHAR(255)` | **Clé d'objet** de l'image (ex. `product-image-001.svg`), nullable → image par défaut |
| `created_at`, `updated_at` | `TIMESTAMPTZ` | Dates ; `updated_at` est tenue à jour par un trigger |

### `inquiries`

| Colonne | Type | Rôle |
|---|---|---|
| `id` | `SERIAL` **PK** | Identifiant technique |
| `customer_name` | `VARCHAR(120) NOT NULL` | Nom saisi |
| `customer_email` | `VARCHAR(254) NOT NULL` | Adresse de réponse (254 = longueur maximale d'une adresse e-mail) |
| `customer_phone` | `VARCHAR(30)` | Facultatif |
| `product_id` | `INTEGER` **FK → products(id)** `ON DELETE SET NULL` | Produit concerné, `NULL` si demande générale |
| `message` | `TEXT NOT NULL` | Contenu de la demande |
| `status` | `VARCHAR(20) NOT NULL DEFAULT 'new'` | Suivi de traitement |
| `created_at` | `TIMESTAMPTZ NOT NULL` | Date de réception |

`customer_phone` a été ajouté au modèle minimal du cahier des charges : pour un commerce local, le téléphone est un canal de réponse courant.

## Clés primaires et étrangères

| Clé | Table | Référence | Suppression |
|---|---|---|---|
| PK `id` | chacune des 3 tables | — | — |
| FK `products.category_id` | products | `categories.id` | `RESTRICT` |
| FK `inquiries.product_id` | inquiries | `products.id` | `SET NULL` |

## Contraintes

| Contrainte | Garantit |
|---|---|
| `categories.name`, `categories.slug`, `products.slug` `UNIQUE` | Pas de doublon, URLs non ambiguës |
| `products_price_positive` : `price_xof >= 0` | Pas de prix négatif |
| `products_stock_status_valid` : ∈ {`in_stock`, `low_stock`, `out_of_stock`, `on_order`} | Statuts maîtrisés |
| `*_slug_format` : `^[a-z0-9]+(-[a-z0-9]+)*$` | Slugs sûrs pour une URL |
| `inquiries_status_valid` : ∈ {`new`, `in_progress`, `closed`} | Cycle de traitement maîtrisé |
| `inquiries_message_not_blank`, `inquiries_name_not_blank` | Pas de demande vide (même si la validation applicative est contournée) |

Des `CHECK` plutôt que des types `ENUM` PostgreSQL : plus simples à faire évoluer (`ALTER TABLE … DROP/ADD CONSTRAINT`) sans migration de type.

## Index

| Index | Justification |
|---|---|
| PK et `UNIQUE` (automatiques) | Recherche par `slug` (page détail), unicité |
| `idx_products_category_id` | Filtre par catégorie, jointure, produits liés ; PostgreSQL n'indexe pas automatiquement les clés étrangères |
| `idx_products_stock_status` | Filtre par disponibilité |
| `idx_products_price` | Filtre par fourchette de prix et tri par prix |
| `idx_inquiries_product_id` | Retrouver les demandes d'un produit ; accélère l'application de `ON DELETE SET NULL` |
| `idx_inquiries_status_created (status, created_at DESC)` | Vue de travail du commercial : demandes `new`, les plus récentes d'abord |

**Non indexé volontairement** : la recherche texte (`ILIKE '%mot%'`). À 16 produits (ou même quelques milliers) un balayage séquentiel est instantané. Si le catalogue devenait très grand, on passerait à `pg_trgm` + index GIN ou à la recherche plein texte PostgreSQL ; c'est de l'over-engineering ici.

## Trigger

`trg_products_updated_at` met à jour `products.updated_at` à chaque `UPDATE`, ce qui évite de dépendre de chaque appelant.

## Fichiers statiques vs données relationnelles

| | Données relationnelles | Fichiers / objets |
|---|---|---|
| Contenu | catégories, produits, demandes | images des produits |
| Stockage | PostgreSQL | disque local (`static/images/`) puis S3 |
| Lien | — | `products.image_key` (texte) |

Stocker les images en `BYTEA` alourdirait les sauvegardes, la réplication et les requêtes, et empêcherait de les servir via un CDN. La base ne contient donc qu'une **clé**.

## Initialisation

```bash
./run.sh init-db     # schema.sql  (idempotent)
./run.sh seed-db     # seed.sql    (4 catégories, 16 produits, 8 demandes ; efface puis recharge)
```

Pas d'outil de migration (Alembic, Flyway…) : un schéma de trois tables n'en justifie pas. Pour une évolution, on ajouterait un fichier SQL daté dans `database/`.
