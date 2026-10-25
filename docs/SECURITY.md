# Sécurité applicative

Niveau visé : **raisonnable pour un petit site public** sans authentification. Le catalogue est volontairement public ; il n'y a pas de compte utilisateur, donc pas de système de connexion à protéger.

## Mesures implémentées

| Risque | Mesure | Où |
|---|---|---|
| Injection SQL | Requêtes **toujours paramétrées** (`%(nom)s`) ; `ORDER BY` construit depuis une **liste blanche** ; caractères `%` et `_` échappés dans les recherches `ILIKE` | `repository.py` |
| XSS | Échappement automatique Jinja2 ; aucun `|safe` ; **CSP** `script-src 'self'; style-src 'self'` (pas de script ni de style inline) | `templates/`, `__init__.py` |
| CSRF | Jeton signé (`itsdangerous`, sel dédié, durée 2 h), sans état | `routes.py` |
| Spam / robots | Champ piège (honeypot) ; taille de corps limitée à 64 Ko ; longueurs bornées | `routes.py`, `__init__.py` |
| Données invalides | Validation serveur stricte + contraintes `CHECK` en base | `validation.py`, `schema.sql` |
| Détournement d'une demande | `product_id` imposé par l'URL, pas par le formulaire | `routes.py` |
| Traversée de chemin (images) | Les clés d'image doivent respecter `^[A-Za-z0-9][A-Za-z0-9._-]*$` ; sinon image par défaut | `storage.py` |
| Clickjacking | `X-Frame-Options: DENY` et CSP `frame-ancestors 'none'` | `__init__.py` |
| Sniffing MIME / fuite de référent | `X-Content-Type-Options: nosniff`, `Referrer-Policy` | `__init__.py` |
| Downgrade HTTPS | `Strict-Transport-Security` en `APP_ENV=production` | `__init__.py` |
| Fuite d'informations | Pages d'erreur génériques ; traces uniquement dans les logs ; pas de mode debug par défaut | `__init__.py` |
| Fuite de données dans les logs | Aucun nom, e-mail, message ni secret journalisé (testé) | `routes.py`, `tests/` |
| Secrets en dur | Aucun : tout vient de l'environnement ; `.env` ignoré par git ; `check-config` n'affiche pas `DATABASE_URL` | `config.py`, `.gitignore` |
| Configuration dangereuse | Démarrage refusé en production sans `SECRET_KEY` ; `seed-db` refusé en production | `config.py`, `cli.py` |

## Limites connues (volontaires)

- **Pas de limitation de débit** (rate limiting) : à traiter en amont (AWS WAF, load balancer, nginx) plutôt que dans l'application, qui est sans état.
- **Pas d'authentification ni de back-office** : les demandes se lisent en SQL. Un back-office imposerait une vraie authentification (hors périmètre).
- **Pas de CAPTCHA** : le honeypot et le jeton CSRF filtrent les robots simples seulement.
- **TLS** : l'application parle HTTP ; la terminaison HTTPS est de la responsabilité de l'infrastructure (load balancer / reverse proxy). Activer `TRUSTED_PROXY_HOPS` derrière celui-ci.
- **Pas de chiffrement applicatif** des demandes : le chiffrement au repos relève de la base (RDS) ; au transit, de TLS (`sslmode=require` dans `DATABASE_URL`).
- **Les images sont publiques** par nature (catalogue public).

## Recommandations pour le déploiement

1. **Moindre privilège base de données** : l'application utilise un rôle dédié avec `SELECT` sur `categories`/`products` et `SELECT, INSERT` sur `inquiries` (plus `USAGE` sur ses séquences). Les commandes `init-db` / `seed-db` se lancent avec un autre rôle d'administration, jamais celui du service.
2. **Secrets** : `DATABASE_URL` et `SECRET_KEY` fournis par l'environnement (ex. Parameter Store `SecureString`), jamais dans le dépôt, une image ou un log.
3. **Réseau** : base non exposée à Internet, accessible uniquement depuis l'application.
4. **Exécuter le service avec un utilisateur non privilégié**, jamais en root.
5. **Gunicorn derrière un reverse proxy / load balancer** ; ne pas exposer le serveur de développement Flask.
6. **Mettre à jour les dépendances** régulièrement (`pip list --outdated`, audit de vulnérabilités).

## Exemple de rôle PostgreSQL à privilèges limités

```sql
CREATE ROLE catalog_app LOGIN PASSWORD '<fourni-par-lenvironnement>';
GRANT CONNECT ON DATABASE product_catalog TO catalog_app;
GRANT USAGE ON SCHEMA public TO catalog_app;
GRANT SELECT ON categories, products TO catalog_app;
GRANT SELECT, INSERT ON inquiries TO catalog_app;
GRANT USAGE, SELECT ON SEQUENCE inquiries_id_seq TO catalog_app;
```

> Remplacez le mot de passe par une valeur issue de votre gestionnaire de secrets ; ne l'écrivez jamais dans le dépôt.

## Vérification « aucun secret dans le dépôt »

```bash
grep -rniE "(password|secret|api[_-]?key|aws_access|aws_secret|BEGIN .*PRIVATE)" \
  --exclude-dir=.venv --exclude-dir=.git --exclude-dir=__pycache__ .
```

Les seules occurrences attendues sont des **noms** de variables, des commentaires, et la valeur factice `change-me` / `devpassword` dans la documentation et `.env.example`.
