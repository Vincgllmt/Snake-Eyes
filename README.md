# Snake Eyes

Outil local pour MJ de jeu de rôle, propulsé par Claude. Il passe par **Claude Code
et ton abonnement Claude** (Pro/Max) : pas de clé API, pas de facturation à l'usage.

- **Assistant MJ** : une fenêtre de discussion avec Claude, qui connaît l'univers
  de la campagne et les fiches des personnages, pour trouver des idées (accroches,
  PNJ, rebondissements), improviser en séance ou arbitrer une règle.
- **Aide joueurs** : la même chose, mais limitée aux informations publiques, pour
  aider à créer ou vérifier une fiche de personnage.
- **Univers** et **Personnages** : éditeurs intégrés pour le contexte envoyé à Claude.

Tout est rangé par **contexte** (sélecteur en haut de l'écran, par exemple une campagne) :
chaque contexte a son univers (sections d'histoire, lieux, règles…), ses personnages
et ses conversations.

## Lancement avec Docker (recommandé)

1. Génère un jeton lié à ton abonnement (une seule fois, sur ta machine) :
   ```bash
   claude setup-token
   ```
2. Copie `.env.example` en `.env` et colle le jeton dans `CLAUDE_CODE_OAUTH_TOKEN=`.
3. Lance :
   ```bash
   docker compose up -d --build
   ```
4. Ouvre http://127.0.0.1:8000.

Les données (base SQLite et sessions Claude Code) sont dans `data/`, à côté du projet :
elles survivent aux redémarrages et mises à jour du conteneur. Pour arrêter :
`docker compose down`.

## Lancement sans Docker

Nécessite Python 3.10+ et [Claude Code](https://claude.com/claude-code) connecté à ton
abonnement (`claude` puis `/login`) ; pas besoin de jeton dans ce cas.

```bash
python -m venv .venv
source .venv/Scripts/activate   # Git Bash ; PowerShell : .venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## Ce que voit Claude

| Élément                         | Mode MJ | Mode joueur |
|---------------------------------|:-------:|:-----------:|
| Sections d'univers publiques    | ✅      | ✅          |
| Sections d'univers « secret »   | ✅      | ❌          |
| Fiches des personnages          | celles cochées dans la conversation (les autres : nom seulement, comme absents) | celle choisie à la création de la conversation (les autres : nom + joueur) |
| Notes MJ des personnages        | ✅ (personnages cochés) | ❌          |

Claude ne voit que le contexte de la conversation. Si tu modifies l'univers, une
fiche ou les personnages cochés pendant une conversation, la nouvelle version est
transmise automatiquement au message suivant.

Chaque conversation est une session Claude Code (reprise à chaque message), sans
aucun outil : Claude ne peut ni lire tes fichiers, ni lancer de commandes, ni aller
sur le web. Tes réglages, hooks et CLAUDE.md personnels ne sont pas chargés.
L'usage compte dans les limites de ton abonnement, comme Claude Code.

> ⚠️ Le filtrage des secrets ne concerne que ce qui est envoyé à Claude : les onglets
> Univers / Personnages restent lisibles par quiconque utilise l'appli.

## Structure

```
app/
  main.py     routes FastAPI (CRUD + chat en streaming SSE)
  claude.py   appel à Claude via le Claude Agent SDK (Claude Code local)
  prompts.py  instructions système et construction du contexte
  db.py       stockage SQLite (data/snake_eyes.db)
static/       interface (HTML/CSS/JS, sans build)
Dockerfile, docker-compose.yml
```
