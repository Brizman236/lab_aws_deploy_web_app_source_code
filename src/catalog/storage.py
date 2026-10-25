"""Abstraction du stockage des fichiers (images produits).

La base de données ne stocke qu'une *clé* d'objet (ex. `product-image-001.svg`).
Ce module transforme une clé en URL publique. Le reste de l'application ne
connaît que l'interface `ImageStorage.url_for(key)`.

Passage à Amazon S3 (voir docs/DEPLOYMENT_NOTES.md) :
  - les objets sont copiés dans un bucket sous les mêmes clés ;
  - on définit ASSET_BASE_URL=https://<bucket-ou-cloudfront>/images ;
  - STORAGE_BACKEND=remote.
Aucune modification de la logique métier ni du schéma n'est nécessaire.
"""
from __future__ import annotations

import os
import re
from abc import ABC, abstractmethod

_KEY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,254}$")


def is_valid_key(key: str | None) -> bool:
    return bool(key) and bool(_KEY_RE.match(key))


class ImageStorage(ABC):
    @abstractmethod
    def url_for(self, key: str | None) -> str:
        """URL publique de l'image associée à `key` (ou un visuel par défaut)."""

    @abstractmethod
    def exists(self, key: str) -> bool:
        """Indique si l'objet est disponible (best effort)."""


class LocalImageStorage(ImageStorage):
    """Fichiers servis par Flask depuis le dossier static/images."""

    def __init__(self, directory: str, base_url: str, placeholder: str = "placeholder.svg"):
        self.directory = directory
        self.base_url = base_url
        self.placeholder = placeholder

    def url_for(self, key: str | None) -> str:
        if not is_valid_key(key):
            key = self.placeholder
        return f"{self.base_url}/{key}"

    def exists(self, key: str) -> bool:
        return is_valid_key(key) and os.path.isfile(os.path.join(self.directory, key))


class RemoteImageStorage(ImageStorage):
    """Objets servis par un hôte externe (S3, CloudFront...) via ASSET_BASE_URL.

    N'utilise volontairement ni boto3 ni aucun SDK : l'application ne fait que
    construire des URLs. Les droits d'écriture/téléversement relèvent du
    processus de publication des assets, pas de l'application web.
    """

    def __init__(self, base_url: str, placeholder: str = "placeholder.svg"):
        self.base_url = base_url
        self.placeholder = placeholder

    def url_for(self, key: str | None) -> str:
        if not is_valid_key(key):
            key = self.placeholder
        return f"{self.base_url}/{key}"

    def exists(self, key: str) -> bool:  # pas de vérification réseau à chaque requête
        return is_valid_key(key)


def build_storage(config) -> ImageStorage:
    if config.storage_backend == "remote":
        return RemoteImageStorage(config.asset_base_url)
    return LocalImageStorage(config.local_image_dir, config.asset_base_url)
