# Notes de déploiement et de migration vers AWS

> **Statut : notes de conception uniquement.** Rien d'AWS n'est implémenté dans ce dépôt. Ces notes expliquent comment l'application s'adapte à AWS, afin que le **projet d'infrastructure séparé** (réseau, IAM, EC2, RDS, S3, Parameter Store, Terraform, pannes) puisse l'utiliser comme workload.

## Architecture cible conceptuelle

```text
Internet
   │
   ▼
EC2  (gunicorn + Flask)         ← dans un VPC, protégée par un Security Group
   │
   ├── PostgreSQL → Amazon RDS   (sous-réseau privé)
   │
   ├── Fichiers statiques → Amazon S3
   │
   └── Configuration → AWS Systems Manager Parameter Store
```

Pourquoi ce découpage est naturel : l'application a exactement quatre « besoins » indépendants (calcul, base relationnelle, objets, configuration), et chacun est déjà isolé derrière une interface étroite (processus WSGI, `DATABASE_URL`, `storage.py`, variables d'environnement).

## Correspondance besoins → services AWS

| Besoin applicatif | Service AWS potentiel | Pourquoi ce service est approprié |
|---|---|---|
| Exécution de l'application Web | **Amazon EC2** | Application classique à processus unique (gunicorn) : une machine virtuelle l'exécute telle quelle, sans refonte ni conteneurisation. Le contrôle total de l'OS, du réseau et des logs est précisément ce que le projet Cloud veut exercer (dépannage, pannes simulées). |
| Base de données relationnelle | **Amazon RDS for PostgreSQL** | Le schéma est du PostgreSQL standard (aucune extension) : RDS le fait fonctionner sans changement. RDS prend en charge sauvegardes automatiques, correctifs, chiffrement au repos et option Multi-AZ, ce qu'on ne veut pas administrer à la main pour une si petite base. Seule `DATABASE_URL` change. |
| Images et objets statiques | **Amazon S3** | Les images sont déjà de simples fichiers désignés par une clé. Un stockage objet est durable, peu coûteux, sans serveur à gérer, et libère l'EC2 du service des fichiers. La clé en base devient la clé d'objet S3. CloudFront peut s'y ajouter plus tard sans toucher à l'application. |
| Configuration de l'application | **AWS Systems Manager Parameter Store** | Centralise la configuration par environnement, avec `SecureString` (chiffré par KMS) pour `DATABASE_URL` et `SECRET_KEY`, historique des versions et contrôle d'accès IAM par chemin. Gratuit pour le niveau standard et plus simple que Secrets Manager pour ce besoin. |
| Permissions AWS du workload | **IAM Role** (profil d'instance) | L'instance obtient des credentials **temporaires** automatiquement : aucune clé d'accès dans le code, la configuration ou l'image. Le rôle n'accorde que `ssm:GetParametersByPath` sur le chemin de l'application et la lecture du bucket (si nécessaire) : moindre privilège. |
| Isolation réseau | **Amazon VPC** | Permet de placer la base dans des sous-réseaux **privés** sans route vers Internet, et l'application dans un sous-réseau public (ou derrière un load balancer). C'est la frontière de base de l'architecture. |
| Contrôle des accès réseau | **Security Groups** | Pare-feu avec état, attaché aux ressources : l'EC2 n'accepte que HTTP/HTTPS (et SSH restreint) ; RDS n'accepte `5432` **que depuis le Security Group de l'EC2** (référence de groupe, pas d'IP). Reproduit exactement les flux autorisés par l'application. |

## Ce qu'il faut changer pour déployer (et ce qui ne change pas)

| Élément | Local | AWS | Modification du code |
|---|---|---|---|
| Base | PostgreSQL local | RDS | **Aucune** (`DATABASE_URL`, idéalement `?sslmode=require`) |
| Images | `static/images/` | S3 | **Aucune** (`STORAGE_BACKEND=remote`, `ASSET_BASE_URL=https://…`) |
| Config | `.env` | Parameter Store → environnement du service | **Aucune** |
| Secrets | `.env` local | `SecureString` | **Aucune** |
| Serveur | `./run.sh` (Flask dev) | gunicorn (`./run.sh prod`) derrière nginx/ALB | **Aucune** |
| Logs | stdout | journald → CloudWatch Logs (agent) | **Aucune** |

## Stockage d'images : de local vers S3

1. Créer un bucket et y copier les images **sous les mêmes clés** :
   ```bash
   aws s3 sync static/images/ s3://<bucket>/images/ --exclude "*" --include "*.svg" --include "*.jpg" --include "*.png"
   ```
2. Rendre les objets lisibles (politique du bucket ou, mieux, via CloudFront avec accès restreint au bucket).
3. Définir `STORAGE_BACKEND=remote` et `ASSET_BASE_URL=https://<bucket-ou-distribution>/images`.
4. Redémarrer l'application. Aucune ligne de la base ni du code n'est modifiée : `image_key` reste `product-image-001.svg`.

Pourquoi sans SDK : `storage.py` ne fait que **construire une URL**. L'application n'a donc besoin d'aucune permission S3 ; la lecture est faite par le navigateur du visiteur, pas par le serveur. Si le téléversement par l'application devenait un besoin (ex. un back-office), on ajouterait une nouvelle implémentation de `ImageStorage` (par ex. `S3ImageStorage` avec `boto3`) sans toucher aux routes ni aux templates.

## Configuration depuis Parameter Store

Voir [CONFIGURATION.md](CONFIGURATION.md#compatibilité-future-avec-aws-systems-manager-parameter-store). En résumé : l'infrastructure récupère les paramètres (avec le rôle IAM de l'instance) et les injecte comme variables d'environnement ; l'application ne contient aucun appel AWS.

## Exemple de service systemd (indicatif)

```ini
[Unit]
Description=TechSahel product catalog
After=network.target

[Service]
User=catalog
WorkingDirectory=/opt/product-catalog
EnvironmentFile=/etc/product-catalog/env        # généré au démarrage depuis Parameter Store (chmod 600)
ExecStart=/opt/product-catalog/.venv/bin/gunicorn --bind 127.0.0.1:8000 --workers 2 wsgi:app
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

Derrière nginx ou un load balancer : mettre `TRUSTED_PROXY_HOPS=1`.

## Santé, supervision, pannes

| Endpoint | Réponse | Usage |
|---|---|---|
| `GET /health` | `200 {"status":"ok","database":"up"}` ou `503 {"status":"degraded","database":"down"}` | Vérification de santé d'un load balancer (target group), alarme CloudWatch, contrôle manuel |
| `GET /health/live` | `200 {"status":"ok"}` | Savoir si le **processus** répond, indépendamment de la base |

Scénarios de panne utiles pour le projet Cloud (et symptômes attendus) :

| Panne simulée | Symptôme observable |
|---|---|
| Security Group RDS ferme le port 5432 | `/health` → 503 `database: down` ; pages catalogue → 503 ; `/health/live` → 200 ; la page d'accueil de l'app ne s'affiche pas non plus (elle lit la base) |
| `DATABASE_URL` erronée | L'application démarre (la config est valide) mais `/health` → 503 ; les logs montrent `OperationalError` sans mot de passe |
| `DATABASE_URL` absente | Le service **ne démarre pas** : `ConfigError` dans le journal |
| `ASSET_BASE_URL` / bucket inaccessible | Le site fonctionne, les images n'apparaissent pas (requêtes navigateur en 403/404) |
| `SECRET_KEY` différente entre instances | Certains envois de formulaire échouent en 400 (jeton signé par une autre instance) |
| Rôle IAM sans accès à Parameter Store | Le script de récupération échoue avant le démarrage de l'application |

Les logs utilisent `request_id` (en-tête `X-Request-Id`) pour relier une requête aux lignes de log.

## Pistes d'évolution (hors périmètre actuel)

Application Load Balancer + Auto Scaling (l'application est déjà sans état), RDS Multi-AZ, CloudFront devant S3, RDS Proxy ou pool de connexions, AWS WAF pour la limitation de débit, CloudWatch Logs/alarmes, Secrets Manager avec rotation du mot de passe de la base.
