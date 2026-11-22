import json
import sys
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))


class FausseReponse:
    def __init__(self, texte="", status=200, type_="text/html", contenu=None, url=""):
        self.text = texte
        self.content = contenu if contenu is not None else texte.encode()
        self.status_code = status
        self.headers = {"Content-Type": type_}
        self.ok = status < 400
        self.url = url

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return json.loads(self.text)


class FauxHTTP:
    """Remplace requests : chaque URL renvoie la page prévue (404 sinon)."""

    def __init__(self, pages: dict):
        self.pages = pages
        self.demandes = []

    def get(self, url, **kw):
        self.demandes.append(url)
        for motif, rep in self.pages.items():
            if motif in url:
                return rep if isinstance(rep, FausseReponse) else FausseReponse(rep, url=url)
        return FausseReponse("introuvable", 404, url=url)

    def head(self, url, **kw):
        return FausseReponse("", 200, url=self.pages.get("__redirection__", url))


@pytest.fixture
def faux_http():
    return FauxHTTP


@pytest.fixture
def base_vide(tmp_path):
    from veille.store import Base
    return Base(tmp_path)


@pytest.fixture
def cfg():
    from veille.commun import config
    return config()


PAGE_OFFRE = """<html><body><nav>menu</nav><h1>PhD position in Privacy-Preserving IoT Data Governance</h1>
<p>The Example University of Technology invites applications for a fully funded PhD position in data governance
for IoT sensor networks in agriculture.</p>
<p>We offer a four-year doctoral contract with a monthly gross salary of 3 100 EUR.</p>
<p>Deadline: 2027-01-15. Contact: Prof. Anna Example (anna.example@uni-example.org).</p>
<p>Requirements: a master's degree in computer science, programming skills in Python, interest in privacy and
wireless sensor networks. The position is open to international candidates. Applications through the portal.</p>
</body></html>"""

PROFIL = (RACINE / "profil" / "profil-exemple.md").read_text(encoding="utf-8")


@pytest.fixture
def page_offre():
    return PAGE_OFFRE


@pytest.fixture
def profil():
    return PROFIL
