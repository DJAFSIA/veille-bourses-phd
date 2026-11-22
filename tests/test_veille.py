import datetime as dt

from veille import rapport, sources
from veille.llm import FauxModele, Reponse
from veille.run_veille import executer
from veille.verification import verifier

INRIA = """<ul><li><h2><a href="/public/classic/fr/offres/2026-99999">PhD Position F/M Privacy for IoT data</a></h2></li>
<li><h2><a href="/public/classic/fr/offres/2026-99998">Ingénieur de recherche F/H</a></h2></li>
<li><h2><a href="/public/classic/fr/offres/2026-10612">Détection des extensions (déjà connue)</a></h2></li></ul>"""

RSS = """<?xml version="1.0"?><rss><channel><title>KTH</title>
<item><title>Doctoral student in wireless networks</title><link>https://kth.varbi.com/en/what:job/jobID:1001/</link><description>PhD &lt;b&gt;edge&lt;/b&gt;</description></item>
<item><title>Administrator</title><link>https://kth.varbi.com/en/what:job/jobID:1002/</link><description>office</description></item>
</channel></rss>"""

VERIF_OK = {"est_offre": True, "finance": True,
            "preuve_financement": "We offer a four-year doctoral contract with a monthly gross salary of 3 100 EUR.",
            "niveau": "Doctorat", "titre": "PhD position in Privacy-Preserving IoT Data Governance",
            "etablissement": "Example University of Technology", "pays": "Pays-Bas", "region": "Europe",
            "domaine": "Gouvernance des données IoT", "financement": "Contrat 4 ans, 3 100 € brut/mois",
            "langue": "Anglais", "date_limite": "2027-01-15",
            "contact": "Prof. Anna Example (anna.example@uni-example.org), faux@invente.org",
            "resume": "Thèse sur la gouvernance des données IoT. Colle à ton profil.", "pertinence": 5}


class Piste:
    def __init__(self, lien, titre="t", source="inria"):
        self.lien, self.titre, self.source = lien, titre, source


def test_sources_inria_et_varbi(faux_http):
    http = faux_http({"jobs.inria.fr": INRIA, "kth.varbi.com": RSS})
    p_inria = sources.inria(["https://jobs.inria.fr/public/classic/fr/offres"], http)
    assert [p.lien for p in p_inria][0] == "https://jobs.inria.fr/public/classic/fr/offres/2026-99999"
    p_varbi = sources.varbi(["kth"], http)
    assert len(p_varbi) == 2 and "edge" in p_varbi[0].extrait
    gardees = sources.noter(p_inria + p_varbi, ["phd", "doctoral"], ["iot", "wireless", "privacy"])
    titres = [p.titre for p in gardees]
    assert "Administrator" not in titres and "Ingénieur de recherche F/H" not in titres
    assert gardees[0].score >= 1


def test_angles_tournent_sur_tout_le_cycle(cfg):
    angles = cfg["angles"]
    assert len(angles) == 30
    vus = set()
    for jour in range(5):
        vus |= set(sources.angles_du_jour(angles, 6, jour))
    assert vus == set(angles)


def test_verification_accepte_et_nettoie(faux_http, page_offre):
    http = faux_http({"uni-example.org": page_offre})
    m = FauxModele({"verification": VERIF_OK})
    offre, raison = verifier(Piste("https://uni-example.org/phd"), m, "profil", dt.date(2026, 11, 22), http)
    assert raison is None
    assert offre["date_limite"] == "2027-01-15" and offre["pertinence"] == 5
    assert "faux@invente.org" not in offre["contact"]  # email absent de la page : retiré
    assert "anna.example@uni-example.org" in offre["contact"]


def test_verification_rejette_sans_preuve_ou_trop_tard(faux_http, page_offre):
    http = faux_http({"uni-example.org": page_offre})
    m = FauxModele({"verification": {**VERIF_OK, "preuve_financement": "Fully funded with a salary of 5000 EUR per month plus housing."}})
    assert verifier(Piste("https://uni-example.org/phd"), m, "", dt.date(2026, 11, 22), http)[1].startswith("preuve")
    m = FauxModele({"verification": {**VERIF_OK, "date_limite": "2026-11-01"}})
    assert verifier(Piste("https://uni-example.org/phd"), m, "", dt.date(2026, 11, 22), http)[1] == "date limite passée"
    m = FauxModele({"verification": {**VERIF_OK, "finance": False}})
    assert "financement" in verifier(Piste("https://uni-example.org/phd"), m, "", dt.date(2026, 11, 22), http)[1]
    assert verifier(Piste("https://autre.org/404"), m, "", dt.date(2026, 11, 22), http)[1].startswith("page illisible")


def test_execution_complete_sans_recherche_web(faux_http, page_offre, base_vide, cfg):
    """La recherche Gemini est coupée : la veille doit continuer avec Inria et Varbi."""
    base_vide.ajouter({"titre": "déjà là", "lien": "https://jobs.inria.fr/public/classic/en/offres/2026-10612"})
    page = page_offre.replace("Deadline: 2027-01-15", "Deadline: 2027-01-15. Ref 2026-99999")
    http = faux_http({"jobs.inria.fr/public/classic/fr/offres/2026-99999": page,
                      "jobs.inria.fr": INRIA, "kth.varbi.com/en/what:rssfeed": RSS})
    cfg = {**cfg, "sources": {"inria": ["https://jobs.inria.fr/public/classic/fr/offres"], "varbi": ["kth"], "pages_liste": []}}
    m = FauxModele({"verification": VERIF_OK}, recherche_ok=False)
    nouvelles = executer(cfg, m, base_vide, http)
    assert len(nouvelles) == 1 and nouvelles[0]["lien"].endswith("2026-99999")
    # la page Varbi n'existe pas dans le faux web : écartée et mémorisée pour ne pas la revérifier
    assert any(k.startswith("varbi:kth:1001") for k in base_vide.vus)
    assert all(not a["recherche"] or a["tache"] == "recherche" for a in m.appels)
    # deuxième passage : plus rien de nouveau, aucune page revérifiée
    m2 = FauxModele({"verification": VERIF_OK}, recherche_ok=False)
    assert executer(cfg, m2, base_vide, http) == []
    assert not [a for a in m2.appels if a["tache"] == "verification"]


def test_recherche_ia_lit_le_json_et_les_sources(faux_http):
    http = faux_http({"__redirection__": "https://vraie-universite.edu/phd"})
    rep = Reponse('```json\n{"offres": [{"titre": "PhD IoT", "lien": "https://u.edu/a", "etablissement": "U"}]}\n```',
                  "gemini-2.5-flash", [{"uri": "https://vertexaisearch.cloud.google.com/grounding-api-redirect/abc", "titre": "u"}])
    m = FauxModele({"recherche": rep})
    pistes = sources.recherche_ia(m, ["angle"], "profil", "2026-11-22", http)
    assert [p.lien for p in pistes] == ["https://u.edu/a", "https://vraie-universite.edu/phd"]


def test_rapport_quotidien():
    auj = dt.date(2026, 11, 22)
    offres = [{"titre": "A", "date_limite": "2026-11-25", "statut": "nouvelle", "pertinence": 4, "etablissement": "X"},
              {"titre": "B", "statut": "postule", "relance_le": "2026-11-20", "postule_le": "2026-11-06"},
              {"titre": "C", "date_limite": "2026-11-25", "statut": "ecartee", "pertinence": 5}]
    nouv = [{"titre": "N <script>", "pertinence": 5, "lien": "https://n.org", "resume": "r"}]
    msg = rapport.contenu(nouv, offres, auj, "https://djafsia.github.io/veille-bourses-phd/")
    assert msg["a_envoyer"] and "1 nouvelle" in msg["sujet"]
    assert "J-3 : A" in msg["texte"] and "C" not in msg["texte"].split("ÉCHÉANCES")[1].split("RELANCES")[0]
    assert "RELANCES" in msg["texte"] and "&lt;script&gt;" in msg["html"] and "<script>" not in msg["telegram"]
