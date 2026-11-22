"""Envoi par Gmail (mot de passe d'application) et par Telegram (bot).

Sans les secrets correspondants, l'envoi est simplement sauté. Avec ESSAI=1,
rien n'est envoyé : les messages sont écrits dans le dossier sortie/.
"""
from __future__ import annotations

import html
import logging
import mimetypes
import os
import smtplib
import ssl
from email.message import EmailMessage
from pathlib import Path

import requests

log = logging.getLogger(__name__)
SORTIE = Path(os.environ.get("DOSSIER_SORTIE", "sortie"))


def essai() -> bool:
    return os.environ.get("ESSAI", "") not in ("", "0", "false")


def email(sujet: str, texte: str, html_: str | None = None, pieces: list[Path] = ()) -> bool:
    expediteur = os.environ.get("GMAIL_ADRESSE", "")
    mot_de_passe = os.environ.get("GMAIL_MOT_DE_PASSE_APP", "").replace(" ", "")
    destinataire = os.environ.get("EMAIL_DESTINATAIRE", "") or expediteur
    if essai():
        SORTIE.mkdir(parents=True, exist_ok=True)
        (SORTIE / "email.txt").write_text(f"Sujet : {sujet}\n\n{texte}", encoding="utf-8")
        if html_:
            (SORTIE / "email.html").write_text(html_, encoding="utf-8")
        log.info("Essai : email écrit dans %s", SORTIE)
        return True
    if not (expediteur and mot_de_passe):
        log.warning("Email non configuré (secrets GMAIL_ADRESSE / GMAIL_MOT_DE_PASSE_APP)")
        return False
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = sujet, expediteur, destinataire
    msg.set_content(texte)
    if html_:
        msg.add_alternative(html_, subtype="html")
    for p in pieces:
        type_, _ = mimetypes.guess_type(p.name)
        principal, secondaire = (type_ or "application/octet-stream").split("/")
        msg.add_attachment(Path(p).read_bytes(), maintype=principal, subtype=secondaire, filename=p.name)
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ssl.create_default_context(), timeout=60) as s:
        s.login(expediteur, mot_de_passe)
        s.send_message(msg)
    log.info("Email envoyé")
    return True


def telegram(texte_html: str, fichiers: list[Path] = ()) -> bool:
    jeton = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat = os.environ.get("TELEGRAM_CHAT_ID", "")
    if essai():
        SORTIE.mkdir(parents=True, exist_ok=True)
        (SORTIE / "telegram.txt").write_text(texte_html, encoding="utf-8")
        return True
    if not (jeton and chat):
        log.warning("Telegram non configuré (secrets TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID)")
        return False
    api = f"https://api.telegram.org/bot{jeton}"
    ok = True
    for morceau in decouper(texte_html, 3800):
        r = requests.post(f"{api}/sendMessage", timeout=30, data={
            "chat_id": chat, "text": morceau, "parse_mode": "HTML", "disable_web_page_preview": "true"})
        ok &= r.ok
        if not r.ok:
            log.warning("Telegram a refusé le message (%s)", r.status_code)
    for f in fichiers:
        with open(f, "rb") as fh:
            r = requests.post(f"{api}/sendDocument", timeout=60, data={"chat_id": chat},
                              files={"document": (Path(f).name, fh)})
        ok &= r.ok
    return ok


def decouper(texte: str, taille: int) -> list[str]:
    """Coupe un long message aux fins de ligne (Telegram limite à 4096 caractères)."""
    morceaux, courant = [], ""
    for ligne in texte.split("\n"):
        if len(courant) + len(ligne) + 1 > taille and courant:
            morceaux.append(courant)
            courant = ""
        courant += ligne + "\n"
    if courant.strip():
        morceaux.append(courant)
    return morceaux


def e(t) -> str:
    return html.escape(str(t or ""), quote=True)
