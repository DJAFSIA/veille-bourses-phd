"""Prépare une candidature : notes.md, lettre (Markdown + PDF), CV (PDF).

Déclenché par un ticket « candidature: <id> » (ou « candidature: <id> accroche=2 »).
Les documents sont envoyés par email et Telegram, jamais publiés dans le dépôt.
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import logging
import os
import re
import sys
from pathlib import Path

from jinja2 import Environment, FileSystemLoader
from markupsafe import Markup

from .. import llm as llm_mod
from .. import notifications
from ..commun import RACINE, config, journal
from ..llm import LLMError
from ..store import Base, aujourdhui, slug
from ..verification import lire_page
from . import controle, prompts

log = logging.getLogger("candidature")
MOIS_FR = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
           "septembre", "octobre", "novembre", "décembre"]


# Titres des sections du CV, dans l'ordre, dans chaque langue. Le modèle les reçoit
# dans le prompt, et normaliser_sections() corrige ceux qu'il aurait laissés dans l'autre langue.
SECTIONS_CV = [
    ("formation", "Formation", "Education"),
    ("publications", "Publications", "Publications"),
    ("recherche", "Expérience de recherche", "Research Experience"),
    ("enseignement", "Enseignement", "Teaching Experience"),
    ("pro", "Expérience professionnelle", "Professional Experience"),
    ("competences", "Compétences", "Skills"),
    ("certifications", "Certifications", "Certifications"),
    ("langues", "Langues", "Languages"),
    ("references", "Références", "References"),
]
# Mots qui reconnaissent une section, quelle que soit sa langue (ordre important :
# « Enseignement et formation » doit être reconnu comme enseignement, pas formation).
_MOTS_SECTIONS = [
    ("publications", ("publication",)),
    ("recherche", ("recherche", "research")),
    ("enseignement", ("enseign", "teach", "tutor", "tutorat")),
    ("pro", ("professionnel", "professional", "work experience", "employment", "emploi")),
    ("competences", ("competence", "skill")),
    ("certifications", ("certif",)),
    ("langues", ("langue", "language")),
    ("references", ("reference", "referee")),
    ("formation", ("formation", "education", "diplome", "degree")),
]


def titres_sections(langue: str) -> str:
    i = 1 if langue == "fr" else 2
    return ", ".join(t[i] for t in SECTIONS_CV)


def normaliser_sections(cv: dict, langue: str) -> dict:
    """Met chaque titre de section connu dans la langue du CV."""
    import unicodedata
    i = 1 if langue == "fr" else 2
    noms = {t[0]: t[i] for t in SECTIONS_CV}
    for s in cv.get("sections", []) or []:
        brut = unicodedata.normalize("NFKD", str(s.get("titre", ""))).encode("ascii", "ignore").decode().lower()
        for cle, mots in _MOTS_SECTIONS:
            if any(m in brut for m in mots):
                s["titre"] = noms[cle]
                break
    return cv


def lire_titre(titre: str):
    m = re.match(r"\s*candidature\s*:\s*(\S+)(?:\s+accroche\s*=\s*([123]))?\s*$", titre or "", re.I)
    if not m:
        raise ValueError("Titre attendu : « candidature: <id> » ou « candidature: <id> accroche=2 »")
    return m.group(1), int(m.group(2) or 1)


def langue_de(offre: dict) -> str:
    return "fr" if re.match(r"\s*fran", offre.get("langue", ""), re.I) else "en"


def charger_profil() -> str:
    profil = os.environ.get("PROFIL_CANDIDAT", "")
    if not profil and os.environ.get("PROFIL_FICHIER"):
        profil = Path(os.environ["PROFIL_FICHIER"]).read_text(encoding="utf-8")
    if len(profil.strip()) < 200:
        raise SystemExit("Profil absent : ajoute le secret PROFIL_CANDIDAT (voir README).")
    return profil


def description_offre(offre: dict) -> str:
    champs = ["titre", "etablissement", "pays", "domaine", "financement", "langue", "date_limite", "contact", "resume", "lien"]
    return "\n".join(f"{c} : {offre.get(c, '')}" for c in champs if offre.get(c))


class Generateur:
    def __init__(self, modele, cfg: dict, profil: str, guide: str):
        self.m = modele
        self.c = cfg.get("candidature", {})
        self.profil, self.guide = profil, guide
        self.interdits = self.c.get("mots_interdits", [])

    def _contexte(self, offre, page):
        return dict(profil=self.profil, guide=self.guide, offre=description_offre(offre), page=page or "(non disponible)",
                    interdits=", ".join(self.interdits), mots_min=self.c.get("mots_min", 350),
                    mots_max=self.c.get("mots_max", 600))

    def _json(self, prompt, tache):
        rep = self.m.generer(prompt, tache=tache, niveau="pro", json_mode=True)
        d = rep.json()
        if not isinstance(d, dict):
            raise LLMError(f"{tache} : réponse inattendue")
        return d

    # -- étapes -----------------------------------------------------------------
    def notes(self, offre, page, langue):
        ctx = self._contexte(offre, page)
        return self._json(prompts.NOTES.format(**ctx, langue="anglais" if langue == "en" else "français"), "notes")

    def lettre(self, offre, page, langue, notes, accroche_n):
        ctx = self._contexte(offre, page)
        accroches = notes.get("accroches") or [{"texte": ""}]
        accroche = accroches[min(accroche_n, len(accroches)) - 1].get("texte", "")
        dest = notes.get("destinataire") or ("the selection committee" if langue == "en" else "le comité de sélection")
        brouillon = self._json(prompts.LETTRE.format(
            **ctx, langue_nom="anglais" if langue == "en" else "français", destinataire=dest, accroche=accroche,
            preuves="; ".join(notes.get("preuves", [])), manques="; ".join(notes.get("manques", [])) or "aucun"), "lettre")
        relu = self._json(prompts.RELECTURE.format(**ctx, lettre=texte_lettre(brouillon)), "relecture")
        lettre = relu.get("lettre") if isinstance(relu.get("lettre"), dict) else brouillon
        remarques_ia = [f"{p.get('phrase', '')} → {p.get('raison', '')}" for p in relu.get("problemes", [])
                        if isinstance(p, dict)]
        sources = self.profil + "\n" + description_offre(offre) + "\n" + (page or "")
        restants = []
        for _ in range(3):
            lettre = nettoyer_lettre(lettre)
            restants = self.controler_lettre(lettre, sources)
            if not restants:
                break
            lettre = self._json(prompts.CORRECTION.format(**ctx, lettre=texte_lettre(lettre),
                                                          problemes="; ".join(restants)), "correction")
        return lettre, remarques_ia, restants

    def controler_lettre(self, lettre, sources):
        corps = "\n".join(lettre.get("paragraphes", []))
        pb = controle.problemes_texte(
            texte_lettre(lettre), sources, self.interdits, ouvertures=self.c.get("ouvertures_interdites", []),
            premier_paragraphe=(lettre.get("paragraphes") or [""])[0], mots_min=0, mots_max=0)
        n = controle.mots(corps)
        if not (self.c.get("mots_min", 350) <= n <= self.c.get("mots_max", 600)):
            pb.append(f"Longueur : {n} mots (attendu {self.c.get('mots_min', 350)} à {self.c.get('mots_max', 600)})")
        pb += controle.noms_salutation(lettre.get("salutation", ""), sources)
        return pb

    def cv(self, offre, page, langue):
        ctx = self._contexte(offre, page)
        cv = self._json(prompts.CV.format(**ctx, langue_nom="anglais" if langue == "en" else "français",
                                          titres_sections=titres_sections(langue)), "cv")
        restants = []
        for _ in range(2):
            restants = controle.problemes_texte(texte_cv(cv), self.profil, self.interdits)
            if not restants:
                break
            cv = self._json(prompts.CORRECTION_CV.format(**ctx, cv=json.dumps(cv, ensure_ascii=False),
                                                         problemes="; ".join(restants)), "correction_cv")
        return normaliser_sections(cv, langue), restants


# -- mise en forme -------------------------------------------------------------
def nettoyer_lettre(l: dict) -> dict:
    return {"salutation": controle.nettoyer(str(l.get("salutation", ""))),
            "paragraphes": [controle.nettoyer(str(p)) for p in l.get("paragraphes", []) if str(p).strip()],
            "formule_finale": controle.nettoyer(str(l.get("formule_finale", ""))),
            "signature": str(l.get("signature", "")).strip()}


def texte_lettre(l: dict) -> str:
    return "\n\n".join([l.get("salutation", ""), *l.get("paragraphes", []), l.get("formule_finale", ""),
                        l.get("signature", "")]).strip()


def texte_cv(cv: dict) -> str:
    morceaux = [cv.get("nom", ""), cv.get("titre", ""), *cv.get("contact", []), cv.get("profil", "")]
    for s in cv.get("sections", []):
        morceaux.append(s.get("titre", ""))
        for e in s.get("entrees", []):
            morceaux += [e.get(k, "") for k in ("titre", "organisation", "lieu", "dates")] + list(e.get("details", []))
    return "\n".join(str(m) for m in morceaux if m).replace("**", "")


def _gras(t) -> Markup:
    t = html.escape(str(t or ""))
    return Markup(re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t))


def date_longue(d: dt.date, langue: str) -> str:
    if langue == "fr":
        return f"Ngaoundéré, le {d.day} {MOIS_FR[d.month - 1]} {d.year}"
    return d.strftime("%d %B %Y").lstrip("0")


def rendre(cv: dict, lettre: dict, offre: dict, langue: str, dossier: Path) -> dict:
    from weasyprint import HTML

    env = Environment(loader=FileSystemLoader(Path(__file__).parent / "modeles"), autoescape=True)
    env.filters["gras"] = _gras
    dossier.mkdir(parents=True, exist_ok=True)
    nom = slug(cv.get("nom") or lettre.get("signature") or "candidat")
    cible = slug(offre.get("etablissement", "offre").split()[0] if offre.get("etablissement") else "offre")
    objet = ("Objet : candidature au poste « {} »" if langue == "fr" else "Application: {}").format(offre.get("titre", ""))

    chemin_cv = dossier / f"CV_{nom}_{cible}.pdf"
    HTML(string=env.get_template("cv.html").render(cv=cv, langue=langue)).write_pdf(chemin_cv)
    chemin_lettre = dossier / f"Lettre_{nom}_{cible}.pdf"
    # Une page si possible (mise en page normale, sinon un peu plus serrée) ; sinon deux pages
    # avec des paragraphes entiers, jamais une phrase seule en haut de la page 2.
    ctx = dict(lettre=lettre, langue=langue, contact=cv.get("contact", [])[:3], objet=objet,
               date=date_longue(aujourdhui(), langue))
    doc = HTML(string=env.get_template("lettre.html").render(**ctx, compact=False)).render()
    if len(doc.pages) > 1:
        serre = HTML(string=env.get_template("lettre.html").render(**ctx, compact=True)).render()
        if len(serre.pages) == 1:
            doc = serre
    doc.write_pdf(chemin_lettre)
    chemin_md = dossier / f"Lettre_{nom}_{cible}.md"
    chemin_md.write_text(f"{objet}\n\n{texte_lettre(lettre)}\n", encoding="utf-8")
    return {"cv": chemin_cv, "lettre_pdf": chemin_lettre, "lettre_md": chemin_md}


def ecrire_notes(offre, notes, accroche_n, remarques_ia, restants_lettre, restants_cv, mots_lettre, dossier: Path) -> Path:
    def liste(xs):
        return "\n".join(f"- {x}" for x in xs) if xs else "- (rien)"
    accroches = "\n".join(
        f"{i}. {'**(utilisée)** ' if i == accroche_n else ''}{a.get('texte', '')}\n   _Fait du profil : {a.get('fait_du_profil', '')}_"
        for i, a in enumerate(notes.get("accroches", []), 1))
    texte = f"""# Candidature : {offre.get('titre', '')}

{offre.get('etablissement', '')} · {offre.get('pays', '')} · date limite : {offre.get('date_limite') or 'à vérifier'}
Offre : {offre.get('lien', '')}
Destinataire : {notes.get('destinataire') or 'non indiqué'}

## Pièces demandées
{liste(notes.get('pieces_demandees', []))}

## Accroches proposées
{accroches}

Pour changer d'accroche, ouvre un ticket « candidature: {offre['id']} accroche=2 » (ou 3).

## Points forts pour cette offre
{liste(notes.get('points_forts', []))}

## Manques
{liste(notes.get('manques', []))}

## Points à confirmer avant l'envoi
{liste(notes.get('a_confirmer', []))}

## Relecture
- Lettre : {mots_lettre} mots.
- Remarques du relecteur IA (déjà corrigées dans la lettre) :
{liste(remarques_ia)}
- Contrôles automatiques encore en échec sur la lettre (à corriger à la main) :
{liste(restants_lettre)}
- Contrôles automatiques encore en échec sur le CV :
{liste(restants_cv)}

Relis tout avant d'envoyer : l'IA peut se tromper, et c'est ton nom qui signe.
"""
    chemin = dossier / "notes.md"
    chemin.write_text(texte, encoding="utf-8")
    return chemin


def preparer(ident: str, accroche_n: int, modele, cfg: dict, profil: str, base: Base, dossier: Path, http=None) -> dict:
    offre = base.offre(ident)
    if not offre:
        raise SystemExit(f"Offre inconnue : {ident}")
    page = ""
    if offre.get("lien"):
        try:
            page = lire_page(offre["lien"], http) if http else lire_page(offre["lien"])
        except Exception as e:
            log.warning("Page de l'offre illisible (%s) : on continue avec la fiche", type(e).__name__)
    guide_path = RACINE / "profil" / "guide-lettre-et-cv.md"
    guide = guide_path.read_text(encoding="utf-8") if guide_path.exists() else ""
    g = Generateur(modele, cfg, profil, guide)
    langue = langue_de(offre)
    notes = g.notes(offre, page, langue)
    lettre, remarques, restants_lettre = g.lettre(offre, page, langue, notes, accroche_n)
    cv, restants_cv = g.cv(offre, page, langue)
    fichiers = rendre(cv, lettre, offre, langue, dossier)
    fichiers["notes"] = ecrire_notes(offre, notes, accroche_n, remarques, restants_lettre, restants_cv,
                                     controle.mots("\n".join(lettre["paragraphes"])), dossier)
    return {"offre": offre, "fichiers": fichiers, "restants": restants_lettre + restants_cv}


def main(argv=None):
    journal()
    p = argparse.ArgumentParser()
    p.add_argument("titre", nargs="?", default=os.environ.get("TITRE_TICKET", ""))
    args = p.parse_args(argv)
    proprio = os.environ.get("GITHUB_REPOSITORY_OWNER", "")
    auteur = os.environ.get("AUTEUR_TICKET", "")
    if proprio and auteur and auteur.lower() != proprio.lower():
        raise SystemExit("Seul le propriétaire du dépôt peut lancer une candidature.")
    ident, accroche_n = lire_titre(args.titre)
    cfg = config()
    modele = llm_mod.depuis_env(cfg)
    dossier = Path(os.environ.get("DOSSIER_SORTIE", "sortie")) / ident
    r = preparer(ident, accroche_n, modele, cfg, charger_profil(), Base(), dossier)
    offre, f = r["offre"], r["fichiers"]
    alerte = f"\n\nAttention : {len(r['restants'])} contrôle(s) à revoir, voir notes.md." if r["restants"] else ""
    pieces = [f["notes"], f["lettre_pdf"], f["lettre_md"], f["cv"]]
    notifications.email(f"Candidature prête : {offre.get('titre', ident)}",
                        f"Voici le dossier préparé pour « {offre.get('titre')} » ({offre.get('etablissement')}).\n"
                        f"Lis d'abord notes.md : pièces demandées, accroches, points à confirmer.{alerte}\n\n{offre.get('lien', '')}",
                        pieces=pieces)
    notifications.telegram(f"<b>Candidature prête</b>\n{notifications.e(offre.get('titre'))}\n"
                           f"Lis d'abord notes.md.{notifications.e(alerte)}", pieces)
    print("Documents envoyés.")


if __name__ == "__main__":
    sys.exit(main())
