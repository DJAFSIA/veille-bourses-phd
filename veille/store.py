"""Lecture et écriture des données : data/offres.json, data/statuts.json, data/vus.json."""
from __future__ import annotations

import datetime as dt
import json
import re
import unicodedata
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

RACINE = Path(__file__).resolve().parent.parent
DATA = RACINE / "data"

STATUTS = ["nouvelle", "interesse", "preparation", "postule", "ecartee"]
# Champs qui décrivent le suivi personnel (dans statuts.json, pas dans offres.json)
CHAMPS_SUIVI = ["statut", "postule_le", "relance_le", "documents", "dossier", "note"]


def aujourdhui() -> dt.date:
    """Date du jour à l'heure du Cameroun (UTC+1)."""
    return (dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=1)).date()


def _lire(chemin: Path, defaut):
    try:
        return json.loads(chemin.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return defaut


def _ecrire(chemin: Path, donnees):
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(json.dumps(donnees, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
                      encoding="utf-8")


class Base:
    def __init__(self, dossier: Path = DATA):
        self.dossier = Path(dossier)
        self.offres: list[dict] = _lire(self.dossier / "offres.json", [])
        self.statuts: dict[str, dict] = _lire(self.dossier / "statuts.json", {})
        self.vus: dict[str, str] = _lire(self.dossier / "vus.json", {})

    def sauver(self):
        self.offres.sort(key=lambda o: o["id"])
        _ecrire(self.dossier / "offres.json", self.offres)
        _ecrire(self.dossier / "statuts.json", self.statuts)
        _ecrire(self.dossier / "vus.json", self.vus)

    # -- accès ---------------------------------------------------------------
    def offre(self, ident: str) -> dict | None:
        return next((o for o in self.offres if o["id"] == ident), None)

    def suivi(self, ident: str) -> dict:
        return self.statuts.get(ident, {"statut": "nouvelle"})

    def fusion(self) -> list[dict]:
        return [{**o, **self.suivi(o["id"])} for o in self.offres]

    def cles_connues(self) -> set[str]:
        cles = {cle_url(o.get("lien", "")) for o in self.offres if o.get("lien")}
        return cles | set(self.vus)

    # -- modifications ---------------------------------------------------------
    def ajouter(self, offre: dict) -> dict:
        offre = dict(offre)
        offre["id"] = self.nouvel_id(offre)
        offre.setdefault("ajoute_le", aujourdhui().isoformat())
        self.offres.append(offre)
        self.statuts.setdefault(offre["id"], {"statut": "nouvelle"})
        return offre

    def marquer_vu(self, url: str):
        self.vus[cle_url(url)] = aujourdhui().isoformat()

    def purger_vus(self, jours: int = 90):
        limite = (aujourdhui() - dt.timedelta(days=jours)).isoformat()
        self.vus = {k: v for k, v in self.vus.items() if v >= limite}

    def changer_statut(self, ident: str, statut: str, note: str | None = None) -> dict:
        if statut not in STATUTS:
            raise ValueError(f"Statut inconnu : {statut} (attendu : {', '.join(STATUTS)})")
        if not self.offre(ident):
            raise KeyError(f"Offre inconnue : {ident}")
        s = dict(self.suivi(ident))
        s["statut"] = statut
        if statut == "postule" and not s.get("postule_le"):
            s["postule_le"] = aujourdhui().isoformat()
            s["relance_le"] = (aujourdhui() + dt.timedelta(days=14)).isoformat()
        if note:
            s["note"] = note
        self.statuts[ident] = s
        return s

    def nouvel_id(self, offre: dict) -> str:
        base = slug(" ".join(filter(None, [
            (offre.get("etablissement") or "").split("–")[0].split("-")[0].split(",")[0],
            " ".join((offre.get("titre") or "offre").split()[:6]),
        ])))[:60].strip("-") or "offre"
        ident, n = f"{base}-{aujourdhui().year}", 2
        existants = {o["id"] for o in self.offres}
        while ident in existants:
            ident, n = f"{base}-{aujourdhui().year}-{n}", n + 1
        return ident


def slug(texte: str) -> str:
    t = unicodedata.normalize("NFKD", texte).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-")


def cle_url(url: str) -> str:
    """Clé stable d'une offre, pour reconnaître les doublons."""
    if not url:
        return ""
    url = url.strip()
    m = re.search(r"jobs\.inria\.fr/.*/offres/(\d{4}-\d{4,6})", url)
    if m:
        return f"inria:{m.group(1)}"
    m = re.search(r"([a-z0-9-]+)\.varbi\.com/.*jobID:(\d+)", url, re.I)
    if m:
        return f"varbi:{m.group(1).lower()}:{m.group(2)}"
    p = urlsplit(url)
    hote = p.netloc.lower().removeprefix("www.")
    chemin = p.path.rstrip("/") or "/"
    requete = urlencode(sorted((k, v) for k, v in parse_qsl(p.query)
                               if not k.lower().startswith(("utm_", "fbclid", "gclid"))))
    return urlunsplit(("", hote, chemin, requete, "")).lstrip("/")


def importer_brut(lignes: list[dict], dossier: Path = DATA) -> Base:
    """Construit offres.json + statuts.json depuis l'export du tableau Claude."""
    base = Base(dossier)
    base.offres, base.statuts = [], {}
    for r in lignes:
        d = dict(r["data"])
        suivi = {k: d.pop(k) for k in CHAMPS_SUIVI if k in d}
        suivi.setdefault("statut", "nouvelle")
        base.offres.append({"id": r["id"], **d})
        base.statuts[r["id"]] = suivi
    return base
