import json

from veille.store import CHAMPS_SUIVI, DATA, Base, cle_url


def test_offres_importees_du_tableau():
    offres = json.loads((DATA / "offres.json").read_text(encoding="utf-8"))
    statuts = json.loads((DATA / "statuts.json").read_text(encoding="utf-8"))
    assert len(offres) == 125
    ids = [o["id"] for o in offres]
    assert len(set(ids)) == len(ids)
    assert set(statuts) == set(ids)
    for o in offres:
        assert o["titre"] and o["niveau"] in ("Doctorat", "Master")
        assert not set(CHAMPS_SUIVI) & set(o), "le suivi doit être dans statuts.json"
    compte = {}
    for s in statuts.values():
        compte[s["statut"]] = compte.get(s["statut"], 0) + 1
    assert compte == {"nouvelle": 110, "postule": 9, "ecartee": 3, "preparation": 3}
    assert statuts["aalto-trustworthy-ml-2026"]["postule_le"] == "2026-10-31"
    assert statuts["unilu-ml-security-testing-2026"]["documents"][0]["lien"].startswith("https://claude.ai/")


def test_cle_url_reconnait_les_doublons():
    assert cle_url("https://jobs.inria.fr/public/classic/fr/offres/2026-10612") == \
        cle_url("https://jobs.inria.fr/public/classic/en/offres/2026-10612")
    assert cle_url("https://kth.varbi.com/en/what:job/jobID:939588/type:job/where:51/apply:1") == \
        cle_url("https://kth.varbi.com/what:job/jobID:939588/")
    assert cle_url("https://www.example.org/job/12/?utm_source=x") == cle_url("https://example.org/job/12")
    assert cle_url("https://www.aplitrak.com/?adid=AAA") != cle_url("https://www.aplitrak.com/?adid=BBB")


def test_base_connait_toutes_les_offres_importees():
    base = Base()
    connues = base.cles_connues()
    assert cle_url("https://jobs.inria.fr/public/classic/en/offres/2026-10614") in connues


def test_ajout_et_statut(base_vide):
    o = base_vide.ajouter({"titre": "PhD in Edge AI", "etablissement": "TU Exemple – Informatics", "lien": "https://x.org/1"})
    assert o["id"].startswith("tu-exemple-phd-in-edge-ai")
    o2 = base_vide.ajouter({"titre": "PhD in Edge AI", "etablissement": "TU Exemple – Informatics", "lien": "https://x.org/2"})
    assert o2["id"] != o["id"]
    s = base_vide.changer_statut(o["id"], "postule")
    assert s["postule_le"] and s["relance_le"] > s["postule_le"]
    base_vide.sauver()
    relu = Base(base_vide.dossier)
    assert relu.suivi(o["id"])["statut"] == "postule"
    assert len(relu.fusion()) == 2
