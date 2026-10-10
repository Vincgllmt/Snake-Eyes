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
CONTEXT_NOTICE = "Contexte mis à jour (univers / fiches modifiés)."

app = FastAPI(title="Snake Eyes")
db.init()


# --- Univers ------------------------------------------------------------------

class LoreIn(BaseModel):
    title: str
    content: str = ""
    secret: bool = False
    position: int = 0


@app.get("/api/lore")
def list_lore():
    return db.list_lore()


@app.post("/api/lore")
def create_lore(body: LoreIn):
    return {"id": db.save_lore(None, body.title, body.content, body.secret, body.position)}


@app.put("/api/lore/{lore_id}")
def update_lore(lore_id: int, body: LoreIn):
    db.save_lore(lore_id, body.title, body.content, body.secret, body.position)
    return {"id": lore_id}


@app.delete("/api/lore/{lore_id}")
def delete_lore(lore_id: int):
    db.delete_lore(lore_id)
    return {"ok": True}


# --- Personnages --------------------------------------------------------------

class CharacterIn(BaseModel):
    name: str
    player: str = ""
    sheet: str = ""
    gm_notes: str = ""


@app.get("/api/characters")
def list_characters():
    return db.list_characters()


@app.post("/api/characters")
def create_character(body: CharacterIn):
    return {"id": db.save_character(None, body.name, body.player, body.sheet, body.gm_notes)}


@app.put("/api/characters/{character_id}")
def update_character(character_id: int, body: CharacterIn):
    db.save_character(character_id, body.name, body.player, body.sheet, body.gm_notes)
    return {"id": character_id}


@app.delete("/api/characters/{character_id}")
def delete_character(character_id: int):
    db.delete_character(character_id)
    return {"ok": True}


# --- Conversations ------------------------------------------------------------

class ConversationIn(BaseModel):
    mode: str
    character_id: int | None = None


class RenameIn(BaseModel):
    title: str


class MessageIn(BaseModel):
    content: str


@app.get("/api/conversations")
def list_conversations(mode: str):
    return db.list_conversations(mode)


@app.post("/api/conversations")
def create_conversation(body: ConversationIn):
    if body.mode not in ("mj", "joueur"):
        raise HTTPException(400, "mode invalide")
    character_id = body.character_id if body.mode == "joueur" else None
    if character_id is not None and not db.get_character(character_id):
        raise HTTPException(404, "personnage introuvable")
    context = prompts.build_context(body.mode, character_id)
    system = prompts.instructions(body.mode) + "\n\n" + context
    conversation_id = db.create_conversation(
        body.mode, DEFAULT_TITLE, character_id, system, prompts.context_hash(context)
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
        "title": conv["title"],
        "character_id": conv["character_id"],
        "messages": [{"id": m["id"], "role": m["role"], "text": m["content"]} for m in db.list_messages(conversation_id)],
    }


@app.put("/api/conversations/{conversation_id}")
def rename_conversation(conversation_id: int, body: RenameIn):
    db.rename_conversation(conversation_id, body.title.strip() or DEFAULT_TITLE)
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

    # Si l'univers ou les fiches ont changé depuis le dernier échange, la nouvelle
    # version accompagne le message (le prompt système, lui, reste celui du début).
    context = prompts.build_context(conv["mode"], conv["character_id"])
    new_hash = prompts.context_hash(context)
    context_changed = conv["session_id"] is not None and new_hash != conv["context_hash"]
    prompt = text
    if context_changed:
        prompt = prompts.context_update_message(context) + "\n\n---\n\nMessage :\n" + text

    async def events():
        final: dict = {}
        try:
            if context_changed:
                yield _sse({"type": "notice", "text": CONTEXT_NOTICE})
            async for chunk in claude.stream_reply(conv["mode"], conv["system"], prompt, conv["session_id"], final):
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
