"""Vérifie chaque piste sur sa page officielle avant de l'ajouter à la base.

Règle : le modèle ne lit que le texte de la page. Une offre est rejetée si la
page ne dit pas clairement qu'il s'agit d'un doctorat (ou master) financé, si la
preuve citée n'apparaît pas mot pour mot dans la page, ou si la date limite est
passée. Les emails absents de la page sont retirés.
"""
from __future__ import annotations

import datetime as dt
import io
import logging
import re
import unicodedata

import requests
from bs4 import BeautifulSoup

from .llm import LLMError
from .sources import ENTETES

log = logging.getLogger(__name__)

REGIONS = {"Europe", "Amérique", "Asie", "Autre"}
TAILLE_MAX = 14000


def lire_page(url: str, http=requests) -> str:
    r = http.get(url, headers=ENTETES, timeout=45)
    r.raise_for_status()
    type_ = r.headers.get("Content-Type", "").lower()
    if "pdf" in type_ or url.lower().endswith(".pdf"):
        from pypdf import PdfReader
        lecteur = PdfReader(io.BytesIO(r.content))
        texte = "\n".join((p.extract_text() or "") for p in lecteur.pages[:8])
    else:
        soup = BeautifulSoup(r.text, "html.parser")
        for balise in soup(["script", "style", "nav", "footer", "header", "noscript", "svg"]):
            balise.decompose()
        texte = soup.get_text("\n")
    lignes = [" ".join(l.split()) for l in texte.splitlines()]
    return "\n".join(l for l in lignes if l)[:TAILLE_MAX]


PROMPT = """Tu lis la page officielle d'une annonce. Utilise UNIQUEMENT le texte ci-dessous.
N'invente rien : si une information n'est pas écrite dans la page, laisse le champ vide ("").
Nous sommes le {date}.

Profil du candidat (pour la pertinence et le résumé) : {profil}

Réponds en JSON avec exactement ces clés :
- "est_offre": true seulement si la page annonce un poste de doctorat (PhD, thèse, doctoral researcher…) ou un master, OUVERT aux candidatures
- "finance": true seulement si la page dit que le poste est financé (salaire, contrat, bourse, allocation, frais couverts)
- "preuve_financement": la phrase EXACTE de la page qui montre le financement (copiée mot pour mot, 5 à 30 mots)
- "niveau": "Doctorat" ou "Master"
- "titre": titre de l'annonce
- "etablissement", "pays"
- "region": "Europe", "Amérique", "Asie" ou "Autre"
- "domaine": 2 à 6 mots en français
- "financement": montant et durée tels qu'écrits (en français), sinon "à vérifier"
- "langue": langue de travail ou exigences de langue écrites dans la page
- "date_limite": AAAA-MM-JJ si écrite, sinon ""
- "contact": nom et email écrits dans la page, sinon ""
- "resume": 2 phrases en français, en tutoyant le candidat : de quoi parle la thèse, puis ce qui colle ou bloque avec son profil (ne parle que de ce qui est dans la page et dans le profil)
- "pertinence": entier de 1 à 5 (5 = colle parfaitement au profil)

Adresse de la page : {url}
Texte de la page :
<<<
{texte}
>>>"""


def _norme(t: str) -> str:
    t = unicodedata.normalize("NFKC", t or "").lower()
    t = re.sub(r"[‘’´`]", "'", t)
    t = re.sub(r"[“”«»]", '"', t)
    return re.sub(r"\s+", " ", t).strip()


def present(citation: str, texte: str) -> bool:
    """La citation figure-t-elle dans le texte (à la ponctuation près) ?"""
    c, t = _norme(citation), _norme(texte)
    if len(c) < 12:
        return False
    if c in t:
        return True
    from difflib import SequenceMatcher
    m = SequenceMatcher(None, t, c, autojunk=False).find_longest_match(0, len(t), 0, len(c))
    return m.size >= 0.85 * len(c)


def verifier(piste, llm, profil: str, aujourdhui: dt.date, http=requests):
    """Renvoie (offre, None) si l'offre est valide, sinon (None, raison)."""
    try:
        texte = lire_page(piste.lien, http)
    except Exception as e:
        return None, f"page illisible ({type(e).__name__})"
    if len(texte) < 300:
        return None, "page presque vide"
    try:
        d = llm.generer(PROMPT.format(date=aujourdhui.isoformat(), profil=profil, url=piste.lien, texte=texte),
                        tache="verification", json_mode=True).json()
    except LLMError as e:
        return None, f"modèle : {str(e)[:80]}"
    if not isinstance(d, dict):
        return None, "réponse inattendue"
    if not d.get("est_offre"):
        return None, "pas une offre de doctorat/master ouverte"
    if not d.get("finance"):
        return None, "financement non indiqué"
    if not present(d.get("preuve_financement", ""), texte):
        return None, "preuve de financement introuvable dans la page"
    if d.get("niveau") not in ("Doctorat", "Master"):
        return None, "niveau non reconnu"

    date_limite = str(d.get("date_limite") or "").strip()
    if date_limite:
        try:
            if dt.date.fromisoformat(date_limite) < aujourdhui:
                return None, "date limite passée"
        except ValueError:
            date_limite = ""

    contact = str(d.get("contact") or "")
    page_basse = texte.lower()
    for email in re.findall(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", contact):
        if email.lower() not in page_basse:
            contact = contact.replace(email, "").strip(" ,;–-()")
    try:
        pertinence = max(1, min(5, int(d.get("pertinence", 3))))
    except (TypeError, ValueError):
        pertinence = 3

    offre = {
        "titre": str(d.get("titre") or piste.titre).strip(),
        "etablissement": str(d.get("etablissement") or "").strip(),
        "pays": str(d.get("pays") or "").strip(),
        "region": d.get("region") if d.get("region") in REGIONS else "Autre",
        "domaine": str(d.get("domaine") or "").strip(),
        "financement": str(d.get("financement") or "à vérifier").strip(),
        "langue": str(d.get("langue") or "").strip(),
        "date_limite": date_limite,
        "contact": contact,
        "resume": str(d.get("resume") or "").strip(),
        "pertinence": pertinence,
        "niveau": d["niveau"],
        "lien": piste.lien,
        "source": piste.source,
        "verifie_le": aujourdhui.isoformat(),
    }
    return offre, None
