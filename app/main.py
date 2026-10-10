"""Snake Eyes — assistant MJ et aide aux joueurs, propulsé par Claude."""

import json
from pathlib import Path

from claude_agent_sdk import ClaudeSDKError, CLINotFoundError
from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, HTTPException  # noqa: E402
from fastapi.responses import FileResponse, StreamingResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from . import claude, db, prompts  # noqa: E402

STATIC = Path(__file__).resolve().parent.parent / "static"
DEFAULT_TITLE = "Nouvelle conversation"
CONTEXT_NOTICE = "Contexte mis à jour (univers, fiches ou personnages concernés modifiés)."

app = FastAPI(title="Snake Eyes")
db.init()


def _require_universe(universe_id: int) -> None:
    if not db.get_universe(universe_id):
        raise HTTPException(404, "contexte introuvable")


# --- Contextes (« universes » en interne) -------------------------------------

class UniverseIn(BaseModel):
    name: str


@app.get("/api/universes")
def list_universes():
    return db.list_universes()


@app.post("/api/universes")
def create_universe(body: UniverseIn):
    return {"id": db.save_universe(None, body.name.strip() or "Nouveau contexte")}


@app.put("/api/universes/{universe_id}")
def update_universe(universe_id: int, body: UniverseIn):
    _require_universe(universe_id)
    db.save_universe(universe_id, body.name.strip() or "Sans nom")
    return {"id": universe_id}


@app.delete("/api/universes/{universe_id}")
def delete_universe(universe_id: int):
    if len(db.list_universes()) <= 1:
        raise HTTPException(400, "impossible de supprimer le dernier contexte")
    db.delete_universe(universe_id)
    return {"ok": True}


# --- Sections d'univers -------------------------------------------------------

class LoreIn(BaseModel):
    universe_id: int
    title: str
    content: str = ""
    secret: bool = False
    position: int = 0


@app.get("/api/lore")
def list_lore(universe_id: int):
    return db.list_lore(universe_id)


@app.post("/api/lore")
def create_lore(body: LoreIn):
    _require_universe(body.universe_id)
    return {"id": db.save_lore(None, body.universe_id, body.title, body.content, body.secret, body.position)}


@app.put("/api/lore/{lore_id}")
def update_lore(lore_id: int, body: LoreIn):
    db.save_lore(lore_id, body.universe_id, body.title, body.content, body.secret, body.position)
    return {"id": lore_id}


@app.delete("/api/lore/{lore_id}")
def delete_lore(lore_id: int):
    db.delete_lore(lore_id)
    return {"ok": True}


# --- Personnages --------------------------------------------------------------

class CharacterIn(BaseModel):
    universe_id: int
    name: str
    player: str = ""
    sheet: str = ""
    gm_notes: str = ""


@app.get("/api/characters")
def list_characters(universe_id: int):
    return db.list_characters(universe_id)


@app.post("/api/characters")
def create_character(body: CharacterIn):
    _require_universe(body.universe_id)
    return {"id": db.save_character(None, body.universe_id, body.name, body.player, body.sheet, body.gm_notes)}


@app.put("/api/characters/{character_id}")
def update_character(character_id: int, body: CharacterIn):
    db.save_character(character_id, body.universe_id, body.name, body.player, body.sheet, body.gm_notes)
    return {"id": character_id}


@app.delete("/api/characters/{character_id}")
def delete_character(character_id: int):
    db.delete_character(character_id)
    return {"ok": True}


# --- Conversations ------------------------------------------------------------

class ConversationIn(BaseModel):
    mode: str
    universe_id: int
    character_id: int | None = None          # mode joueur : sa fiche
    character_ids: list[int] | None = None   # mode MJ : personnages concernés (défaut : tous)


class ConversationUpdate(BaseModel):
    title: str | None = None
    character_ids: list[int] | None = None


class MessageIn(BaseModel):
    content: str


def _universe_character_ids(universe_id: int, wanted: list[int] | None) -> list[int]:
    """Personnages du contexte parmi `wanted` (tous si None)."""
    ids = [c["id"] for c in db.list_characters(universe_id)]
    return ids if wanted is None else [i for i in ids if i in set(wanted)]


@app.get("/api/conversations")
def list_conversations(mode: str, universe_id: int):
    return db.list_conversations(mode, universe_id)


@app.post("/api/conversations")
def create_conversation(body: ConversationIn):
    if body.mode not in ("mj", "joueur"):
        raise HTTPException(400, "mode invalide")
    _require_universe(body.universe_id)
    character_id, character_ids = None, []
    if body.mode == "joueur" and body.character_id is not None:
        c = db.get_character(body.character_id)
        if not c or c["universe_id"] != body.universe_id:
            raise HTTPException(404, "personnage introuvable dans ce contexte")
        character_id = body.character_id
    if body.mode == "mj":
        character_ids = _universe_character_ids(body.universe_id, body.character_ids)
    context = prompts.build_context(body.mode, body.universe_id, character_id, character_ids)
    system = prompts.instructions(body.mode) + "\n\n" + context
    conversation_id = db.create_conversation(
        body.mode, body.universe_id, DEFAULT_TITLE, character_id, character_ids,
        system, prompts.context_hash(context),
    )
    return {"id": conversation_id}


@app.get("/api/conversations/{conversation_id}")
def get_conversation(conversation_id: int):
    conv = db.get_conversation(conversation_id)
    if not conv:
        raise HTTPException(404)
    return {
        "id": conv["id"],
        "mode": conv["mode"],
        "universe_id": conv["universe_id"],
        "title": conv["title"],
        "character_id": conv["character_id"],
        "character_ids": conv["character_ids"],
        "messages": [{"id": m["id"], "role": m["role"], "text": m["content"]} for m in db.list_messages(conversation_id)],
    }


@app.put("/api/conversations/{conversation_id}")
def update_conversation(conversation_id: int, body: ConversationUpdate):
    conv = db.get_conversation(conversation_id)
    if not conv:
        raise HTTPException(404)
    if body.title is not None:
        db.rename_conversation(conversation_id, body.title.strip() or DEFAULT_TITLE)
    if body.character_ids is not None and conv["mode"] == "mj":
        # Pris en compte par Claude au prochain message (via la mise à jour du contexte).
        db.set_conversation_characters(conversation_id, _universe_character_ids(conv["universe_id"], body.character_ids))
    return {"ok": True}


@app.delete("/api/conversations/{conversation_id}")
def delete_conversation(conversation_id: int):
    db.delete_conversation(conversation_id)
    return {"ok": True}


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


@app.post("/api/conversations/{conversation_id}/messages")
async def send_message(conversation_id: int, body: MessageIn):
    conv = db.get_conversation(conversation_id)
    if not conv:
        raise HTTPException(404)
    text = body.content.strip()
    if not text:
        raise HTTPException(400, "message vide")

    # Si l'univers, les fiches ou la sélection de personnages ont changé depuis le
    # dernier échange, la nouvelle version accompagne le message (le prompt système,
    # lui, reste celui du début).
    context = prompts.conversation_context(conv)
    new_hash = prompts.context_hash(context)
    context_changed = new_hash != conv["context_hash"]
    prompt = text
    if context_changed and conv["session_id"] is not None:
        prompt = prompts.context_update_message(context) + "\n\n---\n\nMessage :\n" + text
    system = conv["system"]
    if conv["session_id"] is None:
        # Premier message : on part directement du contexte à jour.
        system = prompts.instructions(conv["mode"]) + "\n\n" + context
        context_changed = False

    async def events():
        final: dict = {}
        try:
            if context_changed:
                yield _sse({"type": "notice", "text": CONTEXT_NOTICE})
            async for chunk in claude.stream_reply(conv["mode"], system, prompt, conv["session_id"], final):
                yield _sse({"type": "text", "text": chunk})
        except claude.ClaudeError as e:
            yield _sse({"type": "error", "message": str(e)})
            return
        except CLINotFoundError:
            yield _sse({"type": "error", "message": "Claude Code est introuvable : installe-le puis connecte-toi avec `claude`."})
            return
        except ClaudeSDKError as e:
            yield _sse({"type": "error", "message": f"Erreur de Claude Code : {e}"})
            return

        # Rien n'est enregistré tant que Claude n'a pas répondu en entier.
        if context_changed:
            db.add_message(conversation_id, "notice", CONTEXT_NOTICE)
        db.add_message(conversation_id, "user", text)
        db.add_message(conversation_id, "assistant", final["text"])
        if conv["session_id"] is None:
            db.set_system(conversation_id, system)
        db.set_session(conversation_id, final["session_id"], new_hash)
        if conv["title"] == DEFAULT_TITLE:
            title = text if len(text) <= 60 else text[:57].rstrip() + "…"
            db.rename_conversation(conversation_id, title)
        yield _sse({"type": "done", "truncated": final.get("stop_reason") == "max_tokens"})

    return StreamingResponse(events(), media_type="text/event-stream")


# --- Interface ----------------------------------------------------------------

app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")
