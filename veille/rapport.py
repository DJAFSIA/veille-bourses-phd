"""Construit le message quotidien : nouvelles offres, échéances proches, relances."""
from __future__ import annotations

import datetime as dt

from .notifications import e


def _jours(iso: str, auj: dt.date):
    try:
        return (dt.date.fromisoformat(iso) - auj).days
    except (TypeError, ValueError):
        return None


def contenu(nouvelles: list[dict], offres: list[dict], auj: dt.date, url_tableau: str = "") -> dict:
    nouvelles = sorted(nouvelles, key=lambda o: (-int(o.get("pertinence") or 0), o.get("date_limite") or "9"))
    proches = []
    for o in offres:
        j = _jours(o.get("date_limite"), auj)
        if j is not None and 0 <= j <= 10 and o.get("statut", "nouvelle") in ("nouvelle", "interesse", "preparation") \
                and int(o.get("pertinence") or 0) >= 3:
            proches.append((j, o))
    proches.sort(key=lambda x: x[0])
    relances = [o for o in offres if o.get("statut") == "postule" and o.get("relance_le")
                and o["relance_le"] <= auj.isoformat()]

    sujet = f"Veille bourses PhD – {auj.strftime('%d/%m/%Y')} : {len(nouvelles)} nouvelle(s) offre(s)"

    def ligne_txt(o):
        dl = o.get("date_limite") or "date à vérifier"
        return f"- [{o.get('pertinence', '?')}/5] {o.get('titre')} – {o.get('etablissement')} ({o.get('pays')}), limite : {dl}\n  {o.get('resume', '')}\n  {o.get('lien', '')}"

    parties_txt = [sujet, ""]
    if nouvelles:
        parties_txt += ["NOUVELLES OFFRES", *map(ligne_txt, nouvelles), ""]
    else:
        parties_txt += ["Aucune nouvelle offre vérifiée aujourd'hui.", ""]
    if proches:
        parties_txt += ["ÉCHÉANCES DANS LES 10 JOURS",
                        *[f"- J-{j} : {o.get('titre')} ({o.get('etablissement')})" for j, o in proches], ""]
    if relances:
        parties_txt += ["RELANCES À FAIRE", *[f"- {o.get('titre')} (postulé le {o.get('postule_le')})" for o in relances], ""]
    if url_tableau:
        parties_txt.append(f"Tableau de bord : {url_tableau}")
    texte = "\n".join(parties_txt)

    def carte(o):
        dl = o.get("date_limite") or "date à vérifier"
        return (f"<li style='margin-bottom:12px'><b>{e(o.get('titre'))}</b><br>"
                f"{e(o.get('etablissement'))} · {e(o.get('pays'))} · limite <b>{e(dl)}</b> · pertinence {e(o.get('pertinence'))}/5<br>"
                f"<span style='color:#444'>{e(o.get('resume'))}</span><br>"
                f"<a href='{e(o.get('lien'))}'>Voir l'offre</a></li>")

    h = [f"<div style='font-family:Arial,sans-serif;max-width:680px'><h2 style='color:#1d4e89'>{e(sujet)}</h2>"]
    h.append(f"<ul>{''.join(map(carte, nouvelles))}</ul>" if nouvelles
             else "<p>Aucune nouvelle offre vérifiée aujourd'hui.</p>")
    if proches:
        h.append("<h3>Échéances dans les 10 jours</h3><ul>" +
                 "".join(f"<li>J-{j} : {e(o.get('titre'))} ({e(o.get('etablissement'))})</li>" for j, o in proches) + "</ul>")
    if relances:
        h.append("<h3>Relances à faire</h3><ul>" +
                 "".join(f"<li>{e(o.get('titre'))} (postulé le {e(o.get('postule_le'))})</li>" for o in relances) + "</ul>")
    if url_tableau:
        h.append(f"<p><a href='{e(url_tableau)}'>Ouvrir le tableau de bord</a></p>")
    h.append("</div>")

    tg = [f"<b>{e(sujet)}</b>", ""]
    for o in nouvelles:
        tg += [f"• <b>{e(o.get('titre'))}</b>",
               f"{e(o.get('etablissement'))} · limite {e(o.get('date_limite') or 'à vérifier')} · {e(o.get('pertinence'))}/5",
               f"<a href=\"{e(o.get('lien'))}\">Voir l'offre</a>", ""]
    if proches:
        tg += ["<b>Échéances proches</b>", *[f"J-{j} : {e(o.get('titre'))}" for j, o in proches], ""]
    if relances:
        tg += ["<b>Relances à faire</b>", *[e(o.get("titre")) for o in relances], ""]
    if url_tableau:
        tg.append(f"<a href=\"{e(url_tableau)}\">Tableau de bord</a>")

    return {"sujet": sujet, "texte": texte, "html": "".join(h), "telegram": "\n".join(tg),
            "a_envoyer": bool(nouvelles or proches or relances)}
