# Veille bourses PhD

Système gratuit qui tourne seul sur GitHub :

- **Veille quotidienne** à 06 h 17 (heure du Cameroun) : Inria, flux Varbi des universités nordiques, offres IACR et Jobbnorge, et une recherche web par Gemini quand elle est disponible gratuitement (30 angles qui tournent). Chaque piste est vérifiée sur sa page officielle : rien n'entre dans la base si la page ne prouve pas que le poste est financé, ou si la date limite est passée.
- **Tableau de bord** GitHub Pages : toutes les offres, filtres, échéances, documents, changement de statut.
- **Générateur de candidature** : bouton « Préparer ma candidature » → notes (pièces demandées, 3 accroches, points forts, manques, points à confirmer), lettre (PDF + Markdown, relue par l'IA et par des contrôles automatiques) et CV PDF (une colonne, cadre bleu double). Envoyés par email et Telegram, jamais publiés.

Tout utilise le palier gratuit de Gemini. Aucun abonnement.

## Mise en route

### 1. Activer GitHub Pages
Settings → Pages → Build and deployment → Source : **GitHub Actions**.
Le tableau de bord sera à l'adresse `https://djafsia.github.io/veille-bourses-phd/`.

### 2. Créer la clé Gemini (gratuite)
1. Va sur https://aistudio.google.com/apikey avec ton compte Google.
2. Accepte les conditions, puis **Create API key** (« Créer une clé API »). Choisis ou crée un projet Google Cloud ; ne relie **aucun** compte de facturation : la clé reste gratuite.
3. Copie la clé (selon le compte, elle commence par `AIza` ou `AQ.`). Ne la partage avec personne.

### 3. Préparer Gmail (mot de passe d'application)
1. Active la validation en deux étapes : https://myaccount.google.com/signinoptions/two-step-verification
2. Crée un mot de passe d'application : https://myaccount.google.com/apppasswords (nom : « veille »). Google affiche 16 lettres : copie-les.

### 4. Préparer Telegram
1. Dans Telegram, écris à **@BotFather** → `/newbot` → donne un nom → il te donne un **jeton** (`123456:ABC…`).
2. Ouvre ton nouveau bot et envoie-lui « bonjour ».
3. Dans un navigateur, ouvre `https://api.telegram.org/bot<JETON>/getUpdates` (remplace `<JETON>`). Repère `"chat":{"id":123456789` : ce nombre est ton **chat id**.

### 5. Ajouter les secrets
Settings → Secrets and variables → Actions → **New repository secret**, un par ligne :

| Nom | Valeur |
|---|---|
| `GEMINI_API_KEY` | la clé Gemini |
| `GMAIL_ADRESSE` | ton adresse Gmail |
| `GMAIL_MOT_DE_PASSE_APP` | les 16 lettres du mot de passe d'application |
| `TELEGRAM_BOT_TOKEN` | le jeton donné par BotFather |
| `TELEGRAM_CHAT_ID` | ton chat id |
| `PROFIL_CANDIDAT` | tout le contenu de ton fichier de profil (voir `profil/profil-exemple.md` pour la forme) |
| `EMAIL_DESTINATAIRE` | facultatif, si les emails doivent aller à une autre adresse |

Le profil reste privé : il n'est jamais écrit dans le dépôt ni dans les journaux.

### 6. Vérifier
Onglet **Actions** → « Diagnostic (clé Gemini, email, Telegram) » → **Run workflow**. Le journal dit quels secrets sont présents, quels modèles Gemini répondent, et tu dois recevoir un email et un message Telegram de test.
Ensuite : « Veille quotidienne » → **Run workflow** pour un premier passage sans attendre 06 h 17.

## Utilisation au quotidien

- **Préparer une candidature** : sur le tableau de bord, bouton « Préparer ma candidature » → GitHub ouvre un ticket `candidature: <id>` → clique **Submit new issue**. Quelques minutes plus tard, les documents arrivent par email et Telegram. Pour une autre accroche : ticket `candidature: <id> accroche=2`.
- **Changer un statut** : choisis le statut dans la liste de l'offre → valide le ticket `statut: <id> <statut>` qui s'ouvre. Statuts : `nouvelle`, `interesse`, `preparation`, `postule`, `ecartee`. Passer à `postule` note la date et prévoit une relance 14 jours plus tard.
- Seul le propriétaire du dépôt peut lancer ces actions ; les tickets des autres sont ignorés.

Relis toujours la lettre et le CV avant d'envoyer : `notes.md` liste ce qui reste à confirmer.

## Bon à savoir

- **Quotas gratuits** : ils changent souvent. Les modèles sont listés dans `config.yaml` et essayés dans l'ordre ; si l'un disparaît ou n'a plus de quota, le suivant prend le relais.
- **Recherche web Gemini** : elle n'est gratuite que sur Gemini 2.5 Flash, qui n'est plus ouvert aux nouveaux comptes (novembre 2026). Elle est donc désactivée (`recherche: []` dans `config.yaml`) et la veille utilise Inria, Varbi, IACR et Jobbnorge.
- **Données envoyées à Google** : sur le palier gratuit, Google peut utiliser les textes envoyés à Gemini pour améliorer ses produits. Ton profil part vers Gemini à chaque candidature préparée : n'y mets rien que tu ne veux pas confier à Google (numéros de pièces d'identité, etc.).
- **Dépôt public** : les offres et les statuts sont visibles de tous ; les lettres, CV et le profil ne le sont jamais.
- GitHub met en pause les tâches planifiées d'un dépôt sans activité pendant 60 jours ; les commits quotidiens de la veille comptent comme activité.

## Structure

```
config.yaml                 modèles, sources, angles, mots interdits
data/offres.json            les offres (125 reprises du tableau Claude au 22/11/2026)
data/statuts.json           ton suivi : statut, dates, documents
data/vus.json               pistes déjà écartées (pour ne pas les revérifier)
site/index.html             tableau de bord
profil/                     guide lettre/CV et exemple de profil (le vrai profil est un secret)
veille/                     code Python (veille, vérification, envois, candidature)
tests/                      tests hors ligne : python -m pytest -q
.github/workflows/          veille, tableau, candidature, statut, tests, diagnostic
```

Test local sans rien envoyer : `ESSAI=1 PROFIL_FICHIER=profil/profil-exemple.md python -m veille.candidature.generer "candidature: <id>"` (les messages sont écrits dans `sortie/`).
