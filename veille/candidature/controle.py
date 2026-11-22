"""Contrôles automatiques des textes générés (sans IA, donc fiables)."""
from __future__ import annotations

import re
import unicodedata

RE_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
RE_URL = re.compile(r"(?:https?://)?(?:www\.)?(?:[a-z0-9-]+\.)+(?:com|org|net|io|fr|cm|edu|ac\.uk|eu|lu|de|nl|be|ch|ca|app|dev)(?:/[^\s,;)]*)?", re.I)
RE_NOMBRE = re.compile(r"\d+(?:[.,\u00a0 ]\d{3})*(?:[.,]\d+)?")
TITRES = r"(?:Prof\.?|Professor|Professeur|Pr\.?|Dr\.?|Doctor|Docteur|Monsieur|Madame|Mr\.?|Mrs\.?|Ms\.?)"


def _plat(t: str) -> str:
    t = unicodedata.normalize("NFKC", t or "").lower()
    return re.sub(r"\s+", "", t)


def _sans_accents(t: str) -> str:
    return unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode().lower()


def nettoyer(texte: str) -> str:
    """Corrections sûres : tirets cadratins remplacés, espaces doublés retirés."""
    t = re.sub(r"\s*—\s*", ", ", texte)
    t = re.sub(r"\s+–\s+", ", ", t)
    return re.sub(r"[ \t]{2,}", " ", t).strip()


def mots(texte: str) -> int:
    return len(re.findall(r"\w+", texte))


def problemes_texte(texte: str, sources: str, interdits: list[str], *, ouvertures: list[str] = (),
                    premier_paragraphe: str = "", mots_min: int = 0, mots_max: int = 0) -> list[str]:
    """Liste lisible des problèmes trouvés. `sources` = profil + offre (la vérité)."""
    pb = []
    bas = texte.lower()
    for m in interdits:
        if re.search(r"(?<!\w)" + re.escape(m.lower().strip()) + r"(?!\w)", bas):
            pb.append(f"Expression interdite : « {m.strip()} »")
    debut = premier_paragraphe.strip().lower()
    for o in ouvertures:
        if debut.startswith(o.lower()):
            pb.append(f"Ouverture interdite : la lettre commence par « {o} »")
    if "—" in texte:
        pb.append("Tiret cadratin présent")

    plat_sources = _plat(sources)
    for email in set(RE_EMAIL.findall(texte)):
        if email.lower() not in sources.lower():
            pb.append(f"Email absent du profil et de l'offre : {email}")
    for url in set(RE_URL.findall(texte)):
        u = re.sub(r"^https?://(www\.)?", "", url.lower()).rstrip("/.")
        if u and u not in sources.lower() and _plat(u) not in plat_sources:
            pb.append(f"Lien absent du profil et de l'offre : {url}")
    for n in set(RE_NOMBRE.findall(RE_EMAIL.sub(" ", texte))):
        brut = n.strip(" .,")
        if len(re.sub(r"\D", "", brut)) < 2:
            continue  # les petits nombres (1 à 9) ne sont pas contrôlés
        if _plat(brut) not in plat_sources and _plat(brut.replace(",", ".")) not in plat_sources:
            pb.append(f"Chiffre introuvable dans le profil ou l'offre : {brut}")
    if mots_min and mots_max:
        n = mots(texte)
        if not (mots_min <= n <= mots_max):
            pb.append(f"Longueur : {n} mots (attendu {mots_min} à {mots_max})")
    return pb


def noms_salutation(salutation: str, sources: str) -> list[str]:
    """Vérifie que le nom du destinataire existe bien dans l'offre."""
    pb = []
    reste = re.sub(r"^\s*(Dear|Cher|Chère|Madame|Monsieur|Bonjour)\s*", "", salutation or "", flags=re.I)
    src = _sans_accents(sources)
    for nom in re.findall(r"(?:" + TITRES + r"\s+)?([A-ZÀ-Ý][\w'’-]{2,})", reste):
        if nom.lower() in {"professor", "professeur", "doctor", "docteur", "madame", "monsieur", "sir", "madam",
                           "members", "committee", "hiring", "selection", "recruitment", "team", "comité"}:
            continue
        if _sans_accents(nom) not in src:
            pb.append(f"Nom du destinataire introuvable dans l'offre : {nom}")
    return pb
