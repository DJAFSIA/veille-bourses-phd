"""Veille quotidienne : collecte des pistes, vérification, mise à jour, envoi.

python -m veille.run_veille            # exécution normale (GitHub Actions)
ESSAI=1 python -m veille.run_veille    # rien n'est envoyé, messages dans sortie/
"""
from __future__ import annotations

import argparse
import logging
import os

import requests

from . import llm as llm_mod
from . import notifications, rapport, sources
from .commun import config, journal, url_tableau
from .store import Base, aujourdhui, cle_url
from .verification import verifier

log = logging.getLogger("veille")


def collecter(cfg: dict, modele, http) -> list[sources.Piste]:
    src, v = cfg.get("sources", {}), cfg.get("veille", {})
    auj = aujourdhui()
    pistes = []
    pistes += sources.inria(src.get("inria", []), http)
    pistes += sources.varbi(src.get("varbi", []), http)
    pistes += sources.pages_liste(src.get("pages_liste", []), http)
    angles = sources.angles_du_jour(cfg.get("angles", []), int(v.get("angles_par_jour", 6)), auj.timetuple().tm_yday)
    pistes += sources.recherche_ia(modele, angles, v.get("profil_veille", ""), auj.isoformat(), http)
    log.info("Pistes brutes : %d", len(pistes))
    return pistes


def executer(cfg: dict, modele, base: Base, http=requests) -> list[dict]:
    v = cfg.get("veille", {})
    auj = aujourdhui()
    connues = base.cles_connues()
    pistes, vues = [], set()
    for p in collecter(cfg, modele, http):
        cle = cle_url(p.lien)
        if cle and cle not in connues and cle not in vues:
            vues.add(cle)
            pistes.append(p)
    pistes = sources.noter(pistes, v.get("mots_cles_doctorat", []), v.get("mots_cles_domaine", []))
    pistes = [p for p in pistes if p.score > 0]
    log.info("Pistes nouvelles à vérifier : %d", len(pistes))

    nouvelles = []
    for p in pistes[: int(v.get("max_verifications_par_jour", 14))]:
        offre, raison = verifier(p, modele, v.get("profil_veille", ""), auj, http)
        if offre:
            offre = base.ajouter(offre)
            nouvelles.append({**offre, "statut": "nouvelle"})
            log.info("Ajoutée : %s", offre["id"])
        else:
            base.marquer_vu(p.lien)
            log.info("Écartée : %s (%s)", p.lien[:90], raison)
    base.purger_vus()
    return nouvelles


def main(argv=None):
    journal()
    parser = argparse.ArgumentParser()
    parser.add_argument("--sans-envoi", action="store_true")
    args = parser.parse_args(argv)
    cfg = config()
    base = Base()
    try:
        modele = llm_mod.depuis_env(cfg)
    except llm_mod.LLMError as e:
        raise SystemExit(f"Impossible de démarrer : {e}. Ajoute le secret GEMINI_API_KEY.")
    nouvelles = executer(cfg, modele, base)
    base.sauver()
    log.info("Nouvelles offres : %d (base : %d offres)", len(nouvelles), len(base.offres))

    msg = rapport.contenu(nouvelles, base.fusion(), aujourdhui(), url_tableau())
    if args.sans_envoi or not msg["a_envoyer"]:
        return
    try:
        notifications.email(msg["sujet"], msg["texte"], msg["html"])
    except Exception as e:
        log.error("Email en échec (%s)", type(e).__name__)
    try:
        notifications.telegram(msg["telegram"])
    except Exception as e:
        log.error("Telegram en échec (%s)", type(e).__name__)


if __name__ == "__main__":
    main()
