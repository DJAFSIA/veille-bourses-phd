"""Sources de pistes : Inria, flux Varbi, pages de listes, recherche web par IA.

Une piste n'est qu'un titre et un lien. Rien n'entre dans la base sans être
vérifié sur sa page officielle (voir verification.py).
"""
from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from .llm import LLMError, RechercheIndisponible

log = logging.getLogger(__name__)

ENTETES = {"User-Agent": "Mozilla/5.0 (veille-bourses-phd; +https://github.com/DJAFSIA/veille-bourses-phd)",
           "Accept-Language": "fr,en;q=0.8"}


@dataclass
class Piste:
    titre: str
    lien: str
    source: str
    extrait: str = ""
    score: int = 0


def _get(http, url, **kw):
    r = http.get(url, headers=ENTETES, timeout=40, **kw)
    r.raise_for_status()
    return r


def inria(urls: list[str], http=requests) -> list[Piste]:
    pistes = []
    for url in urls:
        try:
            soup = BeautifulSoup(_get(http, url).text, "html.parser")
        except Exception as e:
            log.warning("Inria indisponible (%s)", type(e).__name__)
            continue
        for a in soup.find_all("a", href=True):
            if re.search(r"/offres/\d{4}-\d{4,6}$", a["href"]):
                titre = " ".join(a.get_text(" ").split())
                if titre:
                    pistes.append(Piste(titre, urljoin(url, a["href"]), "inria"))
    return pistes


def varbi(sites: list[str], http=requests) -> list[Piste]:
    pistes = []
    for site in sites:
        url = f"https://{site}.varbi.com/en/what:rssfeed/"
        try:
            racine = ET.fromstring(_get(http, url).content)
        except Exception as e:
            log.warning("Varbi %s indisponible (%s)", site, type(e).__name__)
            continue
        for item in racine.iter("item"):
            titre = (item.findtext("title") or "").strip()
            lien = (item.findtext("link") or "").strip()
            desc = BeautifulSoup(item.findtext("description") or "", "html.parser").get_text(" ")
            if titre and lien:
                pistes.append(Piste(titre, lien, f"varbi:{site}", " ".join(desc.split())[:400]))
    return pistes


def pages_liste(pages: list[dict], http=requests) -> list[Piste]:
    pistes = []
    for page in pages:
        try:
            soup = BeautifulSoup(_get(http, page["url"]).text, "html.parser")
        except Exception as e:
            log.warning("Page %s indisponible (%s)", page["url"], type(e).__name__)
            continue
        motif = re.compile(page["motif"])
        for a in soup.find_all("a", href=True):
            if motif.search(a["href"]):
                titre = " ".join(a.get_text(" ").split())
                if len(titre) > 8:
                    pistes.append(Piste(titre, urljoin(page["url"], a["href"]), "liste"))
    return pistes


PROMPT_RECHERCHE = """Cherche sur le web des offres RÉELLES et OUVERTES (date limite non passée au {date})
de doctorat ou de master FINANCÉS correspondant à : « {angle} ».
Profil du candidat : {profil}
Donne uniquement des annonces dont tu as vu la page officielle (université, institut, portail
de recrutement). N'invente aucun lien. Si tu n'es pas sûr, n'inclus pas l'offre.
Réponds uniquement en JSON : {{"offres": [{{"titre": "...", "lien": "https://...", "etablissement": "..."}}]}}
(au plus 6 offres)."""


def recherche_ia(llm, angles: list[str], profil: str, date: str, http=requests) -> list[Piste]:
    pistes = []
    for angle in angles:
        try:
            rep = llm.generer(PROMPT_RECHERCHE.format(angle=angle, profil=profil, date=date),
                              tache="recherche", recherche=True)
        except RechercheIndisponible as e:
            log.warning("Recherche web par IA indisponible : la veille continue sans elle (%s)", str(e)[:160])
            break
        except LLMError as e:
            log.warning("Recherche « %s » en échec (%s)", angle, str(e)[:120])
            continue
        try:
            trouvees = rep.json().get("offres", [])
        except (LLMError, AttributeError):
            trouvees = []
        for o in trouvees:
            if isinstance(o, dict) and str(o.get("lien", "")).startswith("http"):
                pistes.append(Piste(o.get("titre", ""), o["lien"], "recherche", o.get("etablissement", "")))
        # Les sources citées par Google (liens de redirection) sont aussi des pistes
        for s in rep.sources:
            lien = resoudre(s["uri"], http)
            if lien:
                pistes.append(Piste(s.get("titre", ""), lien, "recherche"))
    return pistes


def resoudre(uri: str, http=requests) -> str:
    """Suit les liens de redirection de Google pour obtenir la vraie adresse."""
    if "grounding-api-redirect" not in uri:
        return uri
    try:
        r = http.head(uri, allow_redirects=True, timeout=20, headers=ENTETES)
        return r.url if r.url and "grounding-api-redirect" not in r.url else ""
    except Exception:
        return ""


def angles_du_jour(angles: list[str], n: int, jour_annee: int) -> list[str]:
    if not angles:
        return []
    debut = (jour_annee * n) % len(angles)
    return [angles[(debut + i) % len(angles)] for i in range(min(n, len(angles)))]


def noter(pistes: list[Piste], mots_doctorat: list[str], mots_domaine: list[str]) -> list[Piste]:
    """Garde les pistes qui ressemblent à un doctorat et les classe par proximité du profil."""
    gardees = []
    for p in pistes:
        texte = f" {p.titre} {p.extrait} ".lower()
        est_doc = p.source == "recherche" or any(m in texte for m in mots_doctorat)
        if not est_doc:
            continue
        p.score = sum(1 for m in mots_domaine if m in texte) + (3 if p.source == "recherche" else 0)
        gardees.append(p)
    return sorted(gardees, key=lambda p: -p.score)
