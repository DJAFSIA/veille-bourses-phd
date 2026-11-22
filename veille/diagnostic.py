"""Vérifie la configuration : secrets présents, modèles Gemini utilisables,
envoi d'un message de test par email et Telegram. N'affiche aucun secret."""
from __future__ import annotations

import os

from . import llm as llm_mod
from . import notifications
from .commun import config, journal

SECRETS = ["GEMINI_API_KEY", "GMAIL_ADRESSE", "GMAIL_MOT_DE_PASSE_APP", "TELEGRAM_BOT_TOKEN",
           "TELEGRAM_CHAT_ID", "PROFIL_CANDIDAT"]


def main():
    journal()
    cfg = config()
    print("== Secrets ==")
    for s in SECRETS:
        print(f"{s:24} {'présent' if os.environ.get(s) else 'ABSENT'}")
    print(f"{'EMAIL_DESTINATAIRE':24} {'présent' if os.environ.get('EMAIL_DESTINATAIRE') else '(facultatif, absent : envoi à GMAIL_ADRESSE)'}")
    profil = os.environ.get("PROFIL_CANDIDAT", "")
    if profil:
        print(f"Profil : {len(profil)} caractères")

    print("\n== Gemini ==")
    try:
        m = llm_mod.depuis_env(cfg)
    except llm_mod.LLMError as e:
        print("Impossible :", e)
        m = None
    if m:
        dispo = m.disponibles() or set()
        for niveau in ("flash", "pro", "recherche"):
            prevus = cfg["modeles"].get(niveau, [])
            print(f"{niveau:10} prévus : {', '.join(prevus)}")
            print(f"{'':10} visibles avec ta clé : {', '.join(x for x in prevus if x in dispo) or 'aucun'}")
        for niveau in ("flash", "pro"):
            try:
                r = m.generer("Réponds seulement : OK", tache="diagnostic", niveau=niveau)
                print(f"Test {niveau} : réussi avec {r.modele}")
            except llm_mod.LLMError as e:
                print(f"Test {niveau} : ÉCHEC ({str(e)[:300]})")
        try:
            r = m.generer("Quelle est la capitale du Cameroun ? Une ligne.", tache="diagnostic", recherche=True)
            print(f"Test recherche web : réussi avec {r.modele} ({len(r.sources)} source(s))")
        except llm_mod.LLMError as e:
            print(f"Test recherche web : indisponible ({str(e)[:200]}). La veille utilisera les autres sources.")

    print("\n== Envois de test ==")
    try:
        ok = notifications.email("Test veille bourses PhD", "Si tu lis ce message, l'envoi par email fonctionne.")
        print("Email :", "envoyé" if ok else "non configuré")
    except Exception as e:
        print("Email : ÉCHEC", type(e).__name__, str(e)[:200])
    try:
        ok = notifications.telegram("<b>Test veille bourses PhD</b>\nSi tu lis ce message, Telegram fonctionne.")
        print("Telegram :", "envoyé" if ok else "non configuré ou refusé")
    except Exception as e:
        print("Telegram : ÉCHEC", type(e).__name__)


if __name__ == "__main__":
    main()
