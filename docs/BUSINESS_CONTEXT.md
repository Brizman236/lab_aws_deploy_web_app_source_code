# Contexte métier

## L'entreprise (fictive)

**TechSahel Solutions** est une société informatique fictive basée à Dakar (Sénégal). Elle vend :

- des ordinateurs portables et de bureau ;
- des équipements réseau (routeurs, switchs, points d'accès, onduleurs) ;
- des écrans ;
- des accessoires, périphériques et supports de stockage.

Ses clients sont des PME, des cabinets, des écoles, des hôtels et des particuliers. Les ventes se concluent après échange avec un conseiller (devis, disponibilité, livraison ou retrait) : **il n'y a pas de vente en ligne**.

## Le problème

Aujourd'hui, les clients doivent appeler ou se déplacer pour connaître l'offre et les prix, et les demandes arrivent de façon dispersée (téléphone, messageries). L'entreprise veut :

1. rendre son offre consultable en permanence ;
2. recevoir des demandes structurées (qui demande quoi, pour quel produit) ;
3. conserver ces demandes dans une base unique pour les traiter.

## La solution

Un **catalogue web public** avec formulaires de demande. Périmètre volontairement limité :

| Dans le périmètre | Hors périmètre |
|---|---|
| Catalogue, détail, recherche, filtres | Panier, commande, paiement en ligne |
| Demande liée à un produit | Comptes clients, authentification |
| Formulaire de contact général | Interface d'administration / back-office |
| Informations sur l'entreprise | Envoi d'e-mails, CRM, facturation |

Le traitement des demandes (`inquiries`) se fait pour l'instant directement en SQL ; une interface de back-office serait une évolution possible mais n'est pas nécessaire au projet Cloud.

## Acteurs

- **Visiteur / client** : utilisateur anonyme du site public.
- **Conseiller commercial** : lit les demandes en base et répond par e-mail/téléphone (hors application).
- **Ingénieur Cloud** : déploie et exploite l'application ; c'est le lecteur principal de cette documentation.

## Règles métier clés

- Les prix sont exprimés en **francs CFA (XOF)**, en entiers.
- Un produit a une disponibilité : `in_stock`, `low_stock`, `out_of_stock`, `on_order`. Un produit en rupture reste visible (le client peut demander à être informé).
- Une demande peut concerner **un produit précis** ou être **générale** (sans produit).
- Une demande a un statut de traitement : `new` → `in_progress` → `closed`.
- Supprimer un produit ne doit **pas** supprimer l'historique des demandes associées.

## Pourquoi cette application sert un projet Cloud

Elle représente une petite charge de travail typique : un serveur web, une base relationnelle, des fichiers statiques et de la configuration. Chaque composant correspond naturellement à un service AWS différent, ce qui permet de se concentrer sur l'infrastructure (réseau, IAM, stockage, haute disponibilité, panne, supervision) sans passer du temps sur le développement logiciel.
