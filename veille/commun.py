from __future__ import annotations

import logging
import os
from pathlib import Path

import yaml

RACINE = Path(__file__).resolve().parent.parent


def config() -> dict:
    return yaml.safe_load((RACINE / "config.yaml").read_text(encoding="utf-8"))


def journal():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")


def url_tableau() -> str:
    adresse = (config().get("url_tableau") or "").strip()
    if adresse:
        return adresse
    depot = os.environ.get("GITHUB_REPOSITORY", "")
    if "/" not in depot:
        return ""
    proprio, nom = depot.split("/", 1)
    return f"https://{proprio.lower()}.github.io/{nom}/"
