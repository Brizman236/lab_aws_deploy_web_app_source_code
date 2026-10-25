# Modèle de données (dictionnaire et exemples)

Complément de [DATABASE_DESIGN.md](DATABASE_DESIGN.md) : cette page décrit les **valeurs** et les usages métier des données.

## Entités et volumétrie de démonstration

| Entité | Lignes (seed) | Croissance attendue |
|---|---|---|
| `categories` | 4 | Quasi nulle (quelques lignes) |
| `products` | 16 | Faible (dizaines à centaines) |
| `inquiries` | 8 | La seule table qui grandit en continu (écriture par les visiteurs) |

Conséquence pour l'exploitation : l'application est **majoritairement en lecture** ; seules les demandes génèrent des écritures. La base reste très petite : une instance RDS de petite taille suffit.

## Catégories (données de démonstration)

| slug | Nom | Produits |
|---|---|---|
| `ordinateurs` | Ordinateurs | 4 |
| `reseau` | Équipements réseau | 4 |
| `ecrans` | Écrans | 4 |
| `accessoires` | Accessoires et stockage | 4 |

## Valeurs énumérées

**`products.stock_status`**

| Valeur | Affichage | Signification métier |
|---|---|---|
| `in_stock` | En stock | Disponible immédiatement |
| `low_stock` | Stock limité | Quelques unités restantes |
| `out_of_stock` | Rupture de stock | Indisponible pour le moment |
| `on_order` | Sur commande | Commandé auprès du fournisseur à la demande |

**`inquiries.status`**

| Valeur | Signification |
|---|---|
| `new` | Reçue, non traitée (valeur par défaut) |
| `in_progress` | Prise en charge par un conseiller |
| `closed` | Traitée |

Le site public ne modifie jamais ce statut : il est mis à jour par l'équipe (aujourd'hui en SQL).

## Exemple de produit

```text
id            2
category_id   1                      (Ordinateurs)
name          Nexora Pro 16 - Portable performance
slug          nexora-pro-16            → /produits/nexora-pro-16
brand         Nexora
price_xof     895000                   → affiché « 895 000 FCFA »
stock_status  low_stock                → « Stock limité »
image_key     product-image-002.svg    → /static/images/product-image-002.svg
```

## Exemple de demande

```text
id              5
customer_name   Mariama Faye
customer_email  mariama.faye@example.com
customer_phone  NULL
product_id      NULL                   → demande générale (formulaire /contact)
message         « faites-vous des devis pour équiper une école de 20 postes… »
status          in_progress
```

## Requêtes utiles pour l'équipe commerciale

```sql
-- Demandes à traiter, les plus récentes en premier
SELECT i.id, i.created_at, i.customer_name, i.customer_email, p.name AS produit, i.message
FROM inquiries i LEFT JOIN products p ON p.id = i.product_id
WHERE i.status = 'new' ORDER BY i.created_at DESC;

-- Produits les plus demandés
SELECT p.name, COUNT(*) AS demandes
FROM inquiries i JOIN products p ON p.id = i.product_id
GROUP BY p.name ORDER BY demandes DESC;

-- Passer une demande en cours de traitement
UPDATE inquiries SET status = 'in_progress' WHERE id = 1;
```

## Données personnelles

`inquiries` contient des données personnelles (nom, e-mail, téléphone, message). Les données de démonstration sont fictives (`example.com`, numéros factices). En réel, ces données imposent : accès restreint à la base, chiffrement au repos (RDS), sauvegardes protégées, durée de conservation définie, et aucun affichage de ces champs dans les logs (respecté ici). Voir [SECURITY.md](SECURITY.md).
