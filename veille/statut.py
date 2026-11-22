"""Change le statut d'une offre depuis un ticket « statut: <id> <statut> »."""
from __future__ import annotations

import os
import re
import sys

from .store import STATUTS, Base


def lire_titre(titre: str):
    m = re.match(r"\s*statut\s*:\s*(\S+)\s+(\S+)\s*$", titre or "", re.I)
    if not m:
        raise ValueError("Titre attendu : « statut: <id> <statut> »")
    ident, statut = m.group(1), m.group(2).lower()
    statut = {"intéressé": "interesse", "écartée": "ecartee", "postulé": "postule"}.get(statut, statut)
    if statut not in STATUTS:
        raise ValueError(f"Statut inconnu « {statut} » ({', '.join(STATUTS)})")
    return ident, statut


def main(argv=None):
    titre = (argv or sys.argv[1:] or [os.environ.get("TITRE_TICKET", "")])[0]
    ident, statut = lire_titre(titre)
    base = Base()
    base.changer_statut(ident, statut)
    base.sauver()
    print(f"{ident} → {statut}")


if __name__ == "__main__":
    main()
