import os

import pytest
from pypdf import PdfReader

from veille.candidature import controle
from veille.candidature.generer import lire_titre, preparer
from veille.llm import FauxModele
from veille.statut import lire_titre as lire_statut
from veille import notifications

PARAG = ("At Laboratoire Exemple I watched packets vanish between two microcontrollers, and I learned to count "
         "every lost fragment before trusting a result. That habit is what I would bring to your project on "
         "privacy for sensor data. ")

def lettre(paragraphes, salutation="Dear Prof. Example,"):
    return {"salutation": salutation, "paragraphes": paragraphes, "formule_finale": "Yours sincerely,",
            "signature": "Awa EXEMPLE"}


BONNE = lettre([PARAG * 4, PARAG * 3, PARAG * 3, "I would welcome the chance to discuss it with you."])
MAUVAISE = lettre(["I am applying for this cutting-edge position — " + PARAG * 3, PARAG * 3, PARAG * 2,
                   "I improved accuracy by 97 percent."])

NOTES = {"destinataire": "Prof. Anna Example", "pieces_demandees": ["CV", "Lettre"],
         "accroches": [{"texte": "At Laboratoire Exemple I watched packets vanish.", "fait_du_profil": "stage"},
                       {"texte": "Accroche 2", "fait_du_profil": "x"}, {"texte": "Accroche 3", "fait_du_profil": "y"}],
         "points_forts": ["capteurs"], "manques": ["pas de test d'anglais"], "a_confirmer": ["date"],
         "preuves": ["publication"]}

CV = {"nom": "Awa EXEMPLE", "titre": "Computer Engineer", "contact": ["awa.exemple@example.com", "Ville, Pays"],
      "profil": "", "sections": [
          {"titre": "Education", "entrees": [{"titre": "M.Sc. Computer Science", "organisation": "Université Exemple",
                                              "lieu": "", "dates": "2023–2025", "details": ["Mémoire sur les réseaux de capteurs"]}]},
          {"titre": "Publications", "entrees": [{"titre": "**Awa EXEMPLE**, « Titre de l'article », Revue Exemple, 2025",
                                                 "details": ["DOI 10.0000/exemple"]}]}]}


@pytest.fixture
def offre_base(base_vide):
    base_vide.offres.append({"id": "exemple-phd-2026", "titre": "PhD in Privacy for IoT", "etablissement": "Example University",
                             "pays": "Pays-Bas", "langue": "Anglais", "contact": "Prof. Anna Example",
                             "lien": "https://uni-example.org/phd", "date_limite": "2027-01-15"})
    return base_vide


def test_titres_des_tickets():
    assert lire_titre("candidature: kit-kastel-pets-2026") == ("kit-kastel-pets-2026", 1)
    assert lire_titre("Candidature : abc accroche=3") == ("abc", 3)
    with pytest.raises(ValueError):
        lire_titre("candidature")
    assert lire_statut("statut: abc postule") == ("abc", "postule")
    assert lire_statut("statut: abc Intéressé") == ("abc", "interesse")
    with pytest.raises(ValueError):
        lire_statut("statut: abc gagne")


def test_controles_automatiques(cfg):
    c = cfg["candidature"]
    sources = "profil 2025 Laboratoire Exemple awa.exemple@example.com github.com/awa-exemple"
    pb = controle.problemes_texte("I am applying. This cutting-edge lab — 2025, 97 %, bob@x.org, github.com/awa-exemple",
                                  sources, c["mots_interdits"], ouvertures=c["ouvertures_interdites"],
                                  premier_paragraphe="I am applying for")
    texte = " | ".join(pb)
    assert "cutting-edge" in texte and "Ouverture interdite" in texte and "cadratin" in texte
    assert "97" in texte and "bob@x.org" in texte
    assert "2025" not in texte and "awa-exemple" not in texte
    assert controle.noms_salutation("Dear Prof. Smith,", "Prof. Anna Example") == ["Nom du destinataire introuvable dans l'offre : Smith"]
    assert controle.noms_salutation("Dear Prof. Example,", "Prof. Anna Example") == []
    assert controle.noms_salutation("Dear Members of the Selection Committee,", "") == []
    assert controle.nettoyer("a — b") == "a, b"


def test_candidature_complete(faux_http, page_offre, offre_base, cfg, profil, tmp_path):
    http = faux_http({"uni-example.org": page_offre})
    m = FauxModele({"notes": NOTES, "lettre": MAUVAISE,
                    "relecture": {"problemes": [{"phrase": "97 percent", "raison": "chiffre inventé"}], "lettre": MAUVAISE},
                    "correction": BONNE, "cv": CV})
    r = preparer("exemple-phd-2026", 1, m, cfg, profil, offre_base, tmp_path, http)
    f = r["fichiers"]
    taches = [a["tache"] for a in m.appels]
    assert taches[:3] == ["notes", "lettre", "relecture"] and "correction" in taches and taches[-1] == "cv"
    assert all(a["niveau"] == "pro" for a in m.appels)
    assert "Awa EXEMPLE" in m.appels[0]["prompt"]  # le profil est bien fourni au modèle
    assert r["restants"] == []

    cv = PdfReader(f["cv"])
    assert len(cv.pages) <= 2
    texte_cv = cv.pages[0].extract_text()
    assert "Awa EXEMPLE" in texte_cv and "M.Sc. Computer Science" in texte_cv
    lettre_pdf = PdfReader(f["lettre_pdf"]).pages[0].extract_text()
    assert "Dear Prof. Example" in lettre_pdf
    md = f["lettre_md"].read_text(encoding="utf-8")
    assert "cutting-edge" not in md and "—" not in md and md.startswith("Application: PhD in Privacy for IoT")
    notes = f["notes"].read_text(encoding="utf-8")
    assert "**(utilisée)** At Laboratoire Exemple" in notes and "candidature: exemple-phd-2026 accroche=2" in notes
    assert "chiffre inventé" in notes


def test_controles_restants_signales(faux_http, page_offre, offre_base, cfg, profil, tmp_path):
    """Si le modèle n'arrive pas à corriger, les problèmes sont listés dans notes.md."""
    http = faux_http({"uni-example.org": page_offre})
    cv_faux = {**CV, "contact": ["awa.exemple@example.com", "Duolingo 135"]}
    m = FauxModele({"notes": NOTES, "lettre": MAUVAISE, "relecture": {"problemes": [], "lettre": MAUVAISE},
                    "correction": MAUVAISE, "cv": cv_faux, "correction_cv": cv_faux})
    r = preparer("exemple-phd-2026", 2, m, cfg, profil, offre_base, tmp_path, http)
    notes = r["fichiers"]["notes"].read_text(encoding="utf-8")
    assert "Chiffre introuvable dans le profil ou l'offre : 97" in notes
    assert "Chiffre introuvable dans le profil ou l'offre : 135" in notes
    assert "Expression interdite : « cutting-edge »" in notes
    assert "**(utilisée)** Accroche 2" in notes
    assert [a["tache"] for a in m.appels].count("correction") == 3


def test_lettre_en_francais(faux_http, offre_base, cfg, profil, tmp_path):
    offre_base.offres[0]["langue"] = "Français"
    m = FauxModele({"notes": NOTES, "lettre": BONNE, "relecture": {"problemes": [], "lettre": BONNE}, "cv": CV})
    r = preparer("exemple-phd-2026", 1, m, cfg, profil, offre_base, tmp_path, faux_http({}))
    assert "français" in m.appels[1]["prompt"]
    assert r["fichiers"]["lettre_md"].read_text(encoding="utf-8").startswith("Objet : candidature")


def test_envois_en_mode_essai(tmp_path, monkeypatch):
    monkeypatch.setenv("ESSAI", "1")
    monkeypatch.setattr(notifications, "SORTIE", tmp_path)
    assert notifications.email("Sujet", "Texte", "<b>x</b>")
    assert notifications.telegram("<b>bonjour</b>")
    assert (tmp_path / "email.txt").read_text(encoding="utf-8").startswith("Sujet : Sujet")
    morceaux = notifications.decouper("ligne\n" * 2000, 3800)
    assert all(len(m) <= 3800 for m in morceaux) and sum(m.count("ligne") for m in morceaux) == 2000


def test_sans_secrets_rien_ne_part(monkeypatch):
    for v in ("ESSAI", "GMAIL_ADRESSE", "GMAIL_MOT_DE_PASSE_APP", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"):
        monkeypatch.delenv(v, raising=False)
    assert notifications.email("s", "t") is False
    assert notifications.telegram("t") is False


def test_tableau_de_bord_lit_les_bons_fichiers():
    from veille.commun import RACINE
    html = (RACINE / "site" / "index.html").read_text(encoding="utf-8")
    for attendu in ("data/offres.json", "data/statuts.json", "config.json", "candidature: ", "statut: "):
        assert attendu in html


def test_jeton_telegram_nettoye():
    assert notifications.nettoyer_jeton(' bot123456:ABC-def ') == "123456:ABC-def"
    assert notifications.nettoyer_jeton('"123456:ABC"') == "123456:ABC"
    assert notifications.nettoyer_jeton("botanique") == "botanique"
