"""Client Gemini (palier gratuit) avec repli automatique entre modèles.

Chaque appel porte une « tâche » (tri, verification, lettre…). Le faux modèle
des tests s'en sert pour renvoyer une réponse prévue à l'avance.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass, field

import requests

log = logging.getLogger(__name__)

API = "https://generativelanguage.googleapis.com/v1beta"


class LLMError(RuntimeError):
    pass


class RechercheIndisponible(LLMError):
    """La recherche web intégrée n'est pas disponible gratuitement."""


@dataclass
class Reponse:
    texte: str
    modele: str = ""
    sources: list[dict] = field(default_factory=list)

    def json(self):
        return extraire_json(self.texte)


def extraire_json(texte: str):
    """Lit du JSON même entouré de ```json … ``` ou de texte."""
    t = (texte or "").strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t, flags=re.S)
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        pass
    for ouvrant, fermant in (("{", "}"), ("[", "]")):
        debut, fin = t.find(ouvrant), t.rfind(fermant)
        if debut != -1 and fin > debut:
            try:
                return json.loads(t[debut : fin + 1])
            except json.JSONDecodeError:
                continue
    raise LLMError("Réponse du modèle illisible (JSON attendu)")


class Gemini:
    def __init__(self, cle: str, modeles: dict, pause: float = 6.0, session=None):
        if not cle:
            raise LLMError("Clé GEMINI_API_KEY absente")
        self.cle = cle
        self.modeles = modeles
        self.pause = pause
        self.http = session or requests.Session()
        self._disponibles: set[str] | None = None
        self._dernier_appel = 0.0
        self._epuises: set[str] = set()
        self.recherche_ok = True

    # -- modèles disponibles -------------------------------------------------
    def disponibles(self) -> set[str] | None:
        if self._disponibles is None:
            try:
                noms, jeton = set(), None
                while True:
                    params = {"pageSize": 200}
                    if jeton:
                        params["pageToken"] = jeton
                    r = self.http.get(f"{API}/models", params=params,
                                      headers={"x-goog-api-key": self.cle}, timeout=30)
                    r.raise_for_status()
                    d = r.json()
                    noms |= {m["name"].split("/", 1)[-1] for m in d.get("models", [])}
                    jeton = d.get("nextPageToken")
                    if not jeton:
                        break
                self._disponibles = noms
            except Exception as e:  # la liste est une aide, pas une obligation
                log.warning("Liste des modèles indisponible (%s)", type(e).__name__)
                self._disponibles = set()
        return self._disponibles or None

    def candidats(self, niveau: str) -> list[str]:
        liste = list(self.modeles.get(niveau) or [])
        if niveau == "pro":  # repli sur Flash
            liste += [m for m in self.modeles.get("flash", []) if m not in liste]
        dispo = self.disponibles()
        if dispo:
            filtres = [m for m in liste if m in dispo]
            liste = filtres or liste
        return [m for m in liste if m not in self._epuises]

    # -- appel ---------------------------------------------------------------
    def generer(self, prompt: str, *, tache: str = "", niveau: str = "flash",
                json_mode: bool = False, recherche: bool = False,
                systeme: str | None = None) -> Reponse:
        if recherche and not self.recherche_ok:
            raise RechercheIndisponible("Recherche web désactivée pour cette exécution")
        corps = {"contents": [{"role": "user", "parts": [{"text": prompt}]}]}
        if systeme:
            corps["systemInstruction"] = {"parts": [{"text": systeme}]}
        config = {}
        if json_mode and not recherche:
            config["responseMimeType"] = "application/json"
        if config:
            corps["generationConfig"] = config
        if recherche:
            corps["tools"] = [{"google_search": {}}]

        modeles = self.candidats("recherche" if recherche else niveau)
        erreurs = []
        for modele in modeles:
            for essai in range(2):
                self._attendre()
                try:
                    r = self.http.post(f"{API}/models/{modele}:generateContent",
                                       headers={"x-goog-api-key": self.cle,
                                                "Content-Type": "application/json"},
                                       data=json.dumps(corps), timeout=180)
                except requests.RequestException as e:
                    erreurs.append(f"{modele}: réseau ({type(e).__name__})")
                    continue
                if r.status_code == 200:
                    rep = self._lire(r.json(), modele)
                    if rep.texte.strip():
                        log.info("[%s] %s → %s", tache or "appel", niveau, modele)
                        return rep
                    erreurs.append(f"{modele}: réponse vide")
                    break
                message = _message(r)
                erreurs.append(f"{modele}: {r.status_code} {message[:120]}")
                if r.status_code == 429:
                    bas = message.lower()
                    if "per day" in bas or "perday" in bas or essai:
                        self._epuises.add(modele)  # quota du jour épuisé : modèle suivant
                        break
                    time.sleep(min(_retry_after(r), 60))
                    continue
                if r.status_code >= 500:
                    time.sleep(5)
                    continue
                # 400/403/404 : modèle absent, payant, ou outil non disponible
                break
        if recherche:
            self.recherche_ok = False
            raise RechercheIndisponible("; ".join(erreurs) or "aucun modèle de recherche")
        raise LLMError("Aucun modèle n'a répondu : " + "; ".join(erreurs))

    def _attendre(self):
        reste = self.pause - (time.monotonic() - self._dernier_appel)
        if reste > 0:
            time.sleep(reste)
        self._dernier_appel = time.monotonic()

    @staticmethod
    def _lire(d: dict, modele: str) -> Reponse:
        textes, sources = [], []
        for cand in d.get("candidates", [])[:1]:
            for part in (cand.get("content") or {}).get("parts", []):
                if part.get("text") and not part.get("thought"):
                    textes.append(part["text"])
            meta = cand.get("groundingMetadata") or {}
            for chunk in meta.get("groundingChunks", []):
                web = chunk.get("web") or {}
                if web.get("uri"):
                    sources.append({"uri": web["uri"], "titre": web.get("title", "")})
        return Reponse("".join(textes), modele, sources)


def _message(r) -> str:
    try:
        return r.json().get("error", {}).get("message", "") or r.text
    except ValueError:
        return r.text or ""


def _retry_after(r) -> float:
    try:
        return float(r.headers.get("Retry-After", 20))
    except ValueError:
        return 20.0


class FauxModele:
    """Modèle factice pour les tests : réponses choisies selon la tâche."""

    def __init__(self, reponses: dict, recherche_ok: bool = True):
        self.reponses = reponses
        self.recherche_ok = recherche_ok
        self.appels: list[dict] = []

    def generer(self, prompt, *, tache="", niveau="flash", json_mode=False,
                recherche=False, systeme=None) -> Reponse:
        self.appels.append({"tache": tache, "niveau": niveau, "prompt": prompt, "recherche": recherche})
        if recherche and not self.recherche_ok:
            raise RechercheIndisponible("faux modèle : recherche coupée")
        rep = self.reponses.get(tache)
        if rep is None:
            raise LLMError(f"faux modèle : pas de réponse pour « {tache} »")
        if callable(rep):
            rep = rep(prompt)
        if isinstance(rep, Reponse):
            return rep
        texte = rep if isinstance(rep, str) else json.dumps(rep, ensure_ascii=False)
        return Reponse(texte, "faux-modele")


def depuis_env(config: dict):
    """Construit le modèle à partir de l'environnement (secret GEMINI_API_KEY)."""
    if config.get("provider", "gemini") != "gemini":
        raise LLMError("Seul le fournisseur « gemini » est prévu")
    return Gemini(os.environ.get("GEMINI_API_KEY", ""), config.get("modeles", {}),
                  pause=float(config.get("pause_entre_appels", 6)))
