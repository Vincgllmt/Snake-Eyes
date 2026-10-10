"""Stockage SQLite : univers (lore), personnages, conversations et messages."""

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path(os.getenv("SNAKE_EYES_DB", Path(__file__).resolve().parent.parent / "data" / "snake_eyes.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS lore (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    title      TEXT NOT NULL,
    content    TEXT NOT NULL DEFAULT '',
    secret     INTEGER NOT NULL DEFAULT 0,   -- 1 = réservé au MJ, jamais envoyé en mode joueur
    position   INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS characters (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL,
    player     TEXT NOT NULL DEFAULT '',
    sheet      TEXT NOT NULL DEFAULT '',
    gm_notes   TEXT NOT NULL DEFAULT ''      -- notes MJ, jamais envoyées en mode joueur
);
CREATE TABLE IF NOT EXISTS conversations (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    mode         TEXT NOT NULL CHECK (mode IN ('mj', 'joueur')),
    title        TEXT NOT NULL,
    character_id INTEGER REFERENCES characters(id) ON DELETE SET NULL,
    system       TEXT NOT NULL,              -- figé à la création de la conversation
    context_hash TEXT NOT NULL,              -- empreinte du dernier contexte envoyé
    session_id   TEXT,                       -- session Claude Code reprise à chaque message
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS messages (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role            TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'notice')),
    content         TEXT NOT NULL,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def init() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with connect() as db:
        db.executescript(SCHEMA)


@contextmanager
def connect():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    try:
        yield db
        db.commit()
    finally:
        db.close()


def rows(cursor) -> list[dict]:
    return [dict(r) for r in cursor.fetchall()]


# --- Lore -------------------------------------------------------------------

def list_lore() -> list[dict]:
    with connect() as db:
        return rows(db.execute("SELECT * FROM lore ORDER BY position, id"))


def save_lore(lore_id: int | None, title: str, content: str, secret: bool, position: int) -> int:
    with connect() as db:
        if lore_id is None:
            cur = db.execute(
                "INSERT INTO lore (title, content, secret, position) VALUES (?, ?, ?, ?)",
                (title, content, int(secret), position),
            )
            return cur.lastrowid
        db.execute(
            "UPDATE lore SET title = ?, content = ?, secret = ?, position = ? WHERE id = ?",
            (title, content, int(secret), position, lore_id),
        )
        return lore_id


def delete_lore(lore_id: int) -> None:
    with connect() as db:
        db.execute("DELETE FROM lore WHERE id = ?", (lore_id,))


# --- Personnages --------------------------------------------------------------

def list_characters() -> list[dict]:
    with connect() as db:
        return rows(db.execute("SELECT * FROM characters ORDER BY name COLLATE NOCASE"))


def get_character(character_id: int) -> dict | None:
    with connect() as db:
        row = db.execute("SELECT * FROM characters WHERE id = ?", (character_id,)).fetchone()
        return dict(row) if row else None


def save_character(character_id: int | None, name: str, player: str, sheet: str, gm_notes: str) -> int:
    with connect() as db:
        if character_id is None:
            cur = db.execute(
                "INSERT INTO characters (name, player, sheet, gm_notes) VALUES (?, ?, ?, ?)",
                (name, player, sheet, gm_notes),
            )
            return cur.lastrowid
        db.execute(
            "UPDATE characters SET name = ?, player = ?, sheet = ?, gm_notes = ? WHERE id = ?",
            (name, player, sheet, gm_notes, character_id),
        )
        return character_id


def delete_character(character_id: int) -> None:
    with connect() as db:
        db.execute("DELETE FROM characters WHERE id = ?", (character_id,))


# --- Conversations ------------------------------------------------------------

def list_conversations(mode: str) -> list[dict]:
    with connect() as db:
        return rows(db.execute(
            "SELECT id, mode, title, character_id, created_at FROM conversations "
            "WHERE mode = ? ORDER BY id DESC",
            (mode,),
        ))


def get_conversation(conversation_id: int) -> dict | None:
    with connect() as db:
        row = db.execute("SELECT * FROM conversations WHERE id = ?", (conversation_id,)).fetchone()
        return dict(row) if row else None


def create_conversation(mode: str, title: str, character_id: int | None, system: str, context_hash: str) -> int:
    with connect() as db:
        cur = db.execute(
            "INSERT INTO conversations (mode, title, character_id, system, context_hash) VALUES (?, ?, ?, ?, ?)",
            (mode, title, character_id, system, context_hash),
        )
        return cur.lastrowid


def rename_conversation(conversation_id: int, title: str) -> None:
    with connect() as db:
        db.execute("UPDATE conversations SET title = ? WHERE id = ?", (title, conversation_id))


def set_session(conversation_id: int, session_id: str, context_hash: str) -> None:
    with connect() as db:
        db.execute(
            "UPDATE conversations SET session_id = ?, context_hash = ? WHERE id = ?",
            (session_id, context_hash, conversation_id),
        )


def delete_conversation(conversation_id: int) -> None:
    with connect() as db:
        db.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))


def list_messages(conversation_id: int) -> list[dict]:
    with connect() as db:
        return rows(db.execute(
            "SELECT id, role, content, created_at FROM messages WHERE conversation_id = ? ORDER BY id",
            (conversation_id,),
        ))


def add_message(conversation_id: int, role: str, content: str) -> int:
    with connect() as db:
        cur = db.execute(
            "INSERT INTO messages (conversation_id, role, content) VALUES (?, ?, ?)",
            (conversation_id, role, content),
        )
        return cur.lastrowid
