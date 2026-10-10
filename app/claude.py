"""Appel à Claude via le Claude Agent SDK, qui pilote le Claude Code installé
localement : la consommation passe par l'abonnement Claude connecté à Claude
Code (`claude` puis `/login`), pas par une clé API.

Chaque conversation Snake Eyes correspond à une session Claude Code, reprise
à chaque message (`resume`). Claude n'a accès à aucun outil : c'est un simple
dialogue avec le contexte de la campagne en prompt système.
"""

import os
from collections.abc import AsyncIterator
from pathlib import Path

from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, StreamEvent, query

# Une clé API présente dans l'environnement serait prioritaire sur l'abonnement.
os.environ.pop("ANTHROPIC_API_KEY", None)

MODEL = os.getenv("SNAKE_EYES_MODEL") or None  # None = modèle par défaut de Claude Code
EFFORT = {
    "mj": os.getenv("SNAKE_EYES_EFFORT_MJ", "high"),
    "joueur": os.getenv("SNAKE_EYES_EFFORT_JOUEUR", "medium"),
}
# Dossier de travail des sessions, isolé du reste (pas de CLAUDE.md ni de réglages projet).
SESSIONS_DIR = Path(__file__).resolve().parent.parent / "data" / "sessions"


class ClaudeError(Exception):
    pass


async def stream_reply(
    mode: str,
    system: str,
    prompt: str,
    session_id: str | None,
    final: dict,
) -> AsyncIterator[str]:
    """Génère le texte au fil de l'eau ; à la fin, `final` contient `text` (la
    réponse complète) et `session_id` (à réutiliser au message suivant)."""
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    options = ClaudeAgentOptions(
        system_prompt=system,
        tools=[],               # aucun outil : pas d'accès aux fichiers, au shell ni au web
        setting_sources=[],     # n'applique pas tes réglages / hooks / CLAUDE.md personnels
        max_turns=1,
        model=MODEL,
        effort=EFFORT[mode],
        resume=session_id,
        cwd=SESSIONS_DIR,
        include_partial_messages=True,
    )

    text = ""
    async for message in query(prompt=prompt, options=options):
        if isinstance(message, StreamEvent):
            event = message.event
            if event.get("type") == "content_block_delta" and event["delta"].get("type") == "text_delta":
                chunk = event["delta"]["text"]
                text += chunk
                yield chunk
        elif isinstance(message, ResultMessage):
            if message.is_error:
                detail = message.result or ", ".join(map(str, message.errors or [])) or message.subtype
                if "login" in detail.lower():
                    detail += (" — Claude Code n'est pas connecté : sous Docker, renseigne "
                               "CLAUDE_CODE_OAUTH_TOKEN dans .env (obtenu avec `claude setup-token`).")
                raise ClaudeError(f"Claude Code a renvoyé une erreur : {detail}")
            final["text"] = message.result if message.result is not None else text
            final["session_id"] = message.session_id
            final["stop_reason"] = message.stop_reason
            return

    raise ClaudeError("Claude Code s'est arrêté sans renvoyer de réponse.")
