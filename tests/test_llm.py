import json

import pytest

from veille.llm import Gemini, LLMError, RechercheIndisponible, extraire_json
from conftest import FausseReponse


class SessionGemini:
    """Simule l'API Gemini : un comportement par modèle."""

    def __init__(self, comportements, modeles_listes=("gemini-2.5-flash", "gemini-3.8-flash", "gemini-2.5-pro")):
        self.comportements = comportements
        self.modeles_listes = modeles_listes
        self.appels = []

    def get(self, url, **kw):
        return FausseReponse(json.dumps({"models": [{"name": f"models/{m}"} for m in self.modeles_listes]}))

    def post(self, url, **kw):
        modele = url.split("/models/")[1].split(":")[0]
        corps = json.loads(kw["data"])
        self.appels.append((modele, corps))
        c = self.comportements.get(modele, (404, {"error": {"message": "not found"}}))
        statut, d = c
        return FausseReponse(json.dumps(d), statut)


def ok(texte, sources=()):
    cand = {"content": {"parts": [{"text": "réflexion", "thought": True}, {"text": texte}]}}
    if sources:
        cand["groundingMetadata"] = {"groundingChunks": [{"web": {"uri": u, "title": "t"}} for u in sources]}
    return 200, {"candidates": [cand]}


MODELES = {"flash": ["gemini-2.5-flash", "gemini-3.8-flash"], "pro": ["gemini-2.5-pro"],
           "recherche": ["gemini-2.5-flash"]}


def test_repli_sur_le_modele_suivant():
    s = SessionGemini({"gemini-2.5-flash": (429, {"error": {"message": "Quota exceeded: requests per day"}}),
                       "gemini-3.8-flash": ok('{"a": 1}')})
    g = Gemini("cle", MODELES, pause=0, session=s)
    r = g.generer("x", json_mode=True)
    assert r.modele == "gemini-3.8-flash" and r.json() == {"a": 1}
    assert s.appels[0][1]["generationConfig"]["responseMimeType"] == "application/json"
    # le modèle épuisé n'est plus essayé
    g.generer("y")
    assert [a[0] for a in s.appels].count("gemini-2.5-flash") == 1


def test_pro_se_replie_sur_flash():
    s = SessionGemini({"gemini-2.5-pro": (400, {"error": {"message": "free tier not available"}}),
                       "gemini-2.5-flash": ok("lettre")})
    r = Gemini("cle", MODELES, pause=0, session=s).generer("x", niveau="pro")
    assert r.modele == "gemini-2.5-flash" and r.texte == "lettre"


def test_recherche_web_et_sources():
    s = SessionGemini({"gemini-2.5-flash": ok("{}", ["https://a.org"])})
    r = Gemini("cle", MODELES, pause=0, session=s).generer("x", recherche=True)
    assert r.sources[0]["uri"] == "https://a.org"
    assert s.appels[0][1]["tools"] == [{"google_search": {}}]


def test_recherche_indisponible_coupe_la_recherche_seulement():
    s = SessionGemini({"gemini-2.5-flash": (400, {"error": {"message": "Search grounding is not supported"}}),
                       "gemini-3.8-flash": ok("ok")})
    g = Gemini("cle", MODELES, pause=0, session=s)
    with pytest.raises(RechercheIndisponible):
        g.generer("x", recherche=True)
    with pytest.raises(RechercheIndisponible):
        g.generer("x", recherche=True)
    assert len(s.appels) == 1  # pas de nouvel essai inutile
    assert g.generer("x").texte == "ok"  # le reste fonctionne


def test_erreur_claire_si_aucun_modele():
    with pytest.raises(LLMError):
        Gemini("cle", MODELES, pause=0, session=SessionGemini({})).generer("x")
    with pytest.raises(LLMError):
        Gemini("", MODELES)


def test_extraire_json():
    assert extraire_json('```json\n{"a": [1]}\n```') == {"a": [1]}
    assert extraire_json('Voici : {"b": 2} fin') == {"b": 2}
    with pytest.raises(LLMError):
        extraire_json("pas de json")
