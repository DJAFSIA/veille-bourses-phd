"""Consignes envoyées au modèle. Toutes reposent sur la même règle : n'utiliser
que des faits écrits dans le profil ou dans l'offre."""

REGLES = """RÈGLES ABSOLUES
- N'utilise QUE des faits écrits dans le PROFIL ou dans l'OFFRE ci-dessous. N'invente RIEN :
  ni projet, ni chiffre, ni résultat, ni lecture d'article, ni nom, ni date.
- Si le profil dit qu'un point est « à ne pas mentionner », « à confirmer » ou « ne pas mettre en avant », respecte-le.
- Respecte le GUIDE (lettre et CV) et la consigne de style du candidat.
- Mots et tournures interdits : {interdits}.
- Pas de tiret cadratin (—)."""

CONTEXTE = """=== PROFIL DU CANDIDAT (seule source de vérité sur lui) ===
{profil}

=== GUIDE LETTRE ET CV ===
{guide}

=== OFFRE ===
{offre}

=== TEXTE DE LA PAGE OFFICIELLE (peut être vide) ===
{page}
"""

NOTES = REGLES + """

Prépare la candidature à cette offre. Réponds en JSON :
{{
 "destinataire": "nom et titre du responsable s'il est écrit dans l'offre, sinon \\"\\"",
 "pieces_demandees": ["pièces demandées par l'annonce, telles qu'écrites"],
 "accroches": [{{"texte": "première phrase de lettre en {langue}, concrète, tirée d'un fait vrai du profil", "fait_du_profil": "le fait du profil utilisé"}}] (exactement 3),
 "points_forts": ["3 à 5 liens précis entre le profil et l'offre"],
 "manques": ["ce que l'offre demande et que le profil n'a pas"],
 "a_confirmer": ["points à vérifier par le candidat avant l'envoi"],
 "preuves": ["les 2 ou 3 preuves les plus fortes à utiliser dans la lettre"]
}}

""" + CONTEXTE

LETTRE = REGLES + """

Écris la lettre de motivation en {langue_nom}, {mots_min} à {mots_max} mots, adressée à : {destinataire}.
- Première phrase : cette accroche (tu peux l'ajuster légèrement) : « {accroche} »
- La 2e ou 3e phrase relie l'accroche au sujet de la thèse, puis nomme le poste.
- Chaque paragraphe commence par une idée forte liée au sujet. 2 ou 3 preuves fortes : {preuves}.
- Une question ou piste de recherche simple que le candidat aimerait explorer, liée au sujet.
- Les manques sont expliqués brièvement et positivement s'il le faut : {manques}.
- Dernière phrase en écho à l'accroche, avec une demande d'entretien polie.
- Phrases simples et de longueur variée, première personne, ton humain.

Réponds en JSON : {{"salutation": "...", "paragraphes": ["...", "..."], "formule_finale": "...", "signature": "nom complet du candidat"}}

""" + CONTEXTE

RELECTURE = """Tu es relecteur. Compare la LETTRE au PROFIL et à l'OFFRE, phrase par phrase.
Signale toute affirmation qui n'est pas appuyée par le profil ou l'offre, toute exagération, toute
erreur sur l'encadrant ou l'établissement, tout ce que le profil demande de ne pas dire, et toute
tournure qui sonne comme une IA ou une brochure. Mots interdits : {interdits}.
Corrige ensuite la lettre en gardant sa structure, sa langue et sa longueur ({mots_min} à {mots_max} mots).

Réponds en JSON : {{"problemes": [{{"phrase": "...", "raison": "..."}}], "lettre": {{"salutation": "...", "paragraphes": ["..."], "formule_finale": "...", "signature": "..."}}}}

=== LETTRE ===
{lettre}

""" + CONTEXTE

CORRECTION = """Corrige cette lettre pour régler UNIQUEMENT les problèmes listés, sans rien ajouter qui ne soit
dans le profil ou l'offre. Garde la langue et une longueur de {mots_min} à {mots_max} mots.
Problèmes : {problemes}

Réponds en JSON : {{"salutation": "...", "paragraphes": ["..."], "formule_finale": "...", "signature": "..."}}

=== LETTRE ===
{lettre}

""" + CONTEXTE

CV = REGLES + """

Construis le CV académique en {langue_nom} pour cette offre, à partir du profil UNIQUEMENT.
Sections, dans cet ordre et avec EXACTEMENT ces titres (en {langue_nom}) : {titres_sections}.
Omets une section vide. Certifications : seulement celles utiles à la recherche. Langues : une ligne par langue, le nom et le
niveau seulement, sans justification ni preuve (ex. « English: working proficiency »).
Antichronologique. Tient sur 2 pages.
Une ligne de profil adaptée à l'offre (ou "" si rien d'utile). Le nom du candidat en gras dans les
publications se marque avec **double astérisque**. Pas de score de langue inventé.

Réponds en JSON :
{{"nom": "...", "titre": "...", "contact": ["email", "téléphone", "ville, pays", "LinkedIn", "GitHub"],
 "profil": "...",
 "sections": [{{"titre": "...", "entrees": [{{"titre": "...", "organisation": "...", "lieu": "...", "dates": "...", "details": ["..."]}}]}}]}}

""" + CONTEXTE

CORRECTION_CV = """Corrige ce CV (JSON) pour régler UNIQUEMENT les problèmes listés, en retirant ce qui
n'est pas dans le profil. Même format JSON en réponse.
Problèmes : {problemes}

=== CV ===
{cv}

""" + CONTEXTE
