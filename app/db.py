"""Stockage SQLite : contextes (table `universes`, affichés « Contexte » dans l'interface),
sections d'univers (lore), personnages, conversations et messages."""

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path(os.getenv("SNAKE_EYES_DB", Path(__file__).resolve().parent.parent / "data" / "snake_eyes.db"))
DEFAULT_UNIVERSE = "Snake Eyes"

SCHEMA = """
CREATE TABLE IF NOT EXISTS universes (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS lore (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    universe_id INTEGER REFERENCES universes(id) ON DELETE CASCADE,
    title       TEXT NOT NULL,
    content     TEXT NOT NULL DEFAULT '',
    secret      INTEGER NOT NULL DEFAULT 0,  -- 1 = réservé au MJ, jamais envoyé en mode joueur
    position    INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS characters (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    universe_id INTEGER REFERENCES universes(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    player      TEXT NOT NULL DEFAULT '',
    sheet       TEXT NOT NULL DEFAULT '',
    gm_notes    TEXT NOT NULL DEFAULT ''     -- notes MJ, jamais envoyées en mode joueur
);
CREATE TABLE IF NOT EXISTS conversations (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    universe_id  INTEGER REFERENCES universes(id) ON DELETE CASCADE,
    mode         TEXT NOT NULL CHECK (mode IN ('mj', 'joueur')),
    title        TEXT NOT NULL,
    character_id INTEGER REFERENCES characters(id) ON DELETE SET NULL,  -- mode joueur : sa fiche
    system       TEXT NOT NULL,              -- figé à la création de la conversation
    context_hash TEXT NOT NULL,              -- empreinte du dernier contexte envoyé
    session_id   TEXT,                       -- session Claude Code reprise à chaque message
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);
-- Mode MJ : personnages concernés par la conversation
CREATE TABLE IF NOT EXISTS conversation_characters (
    conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    character_id    INTEGER NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
    PRIMARY KEY (conversation_id, character_id)
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
        _migrate(db)
        if not db.execute("SELECT 1 FROM universes").fetchone():
            db.execute("INSERT INTO universes (name) VALUES (?)", (DEFAULT_UNIVERSE,))


def _migrate(db) -> None:
    """Bases créées avant l'arrivée des contextes multiples : tout est rattaché à un
    contexte par défaut, et les conversations MJ gardent tous les personnages."""
    added = False
    for table in ("lore", "characters", "conversations"):
        columns = {r["name"] for r in db.execute(f"PRAGMA table_info({table})")}
        if "universe_id" not in columns:
            db.execute(f"ALTER TABLE {table} ADD COLUMN universe_id INTEGER REFERENCES universes(id) ON DELETE CASCADE")
            added = True
    if not added:
        return
    orphans = any(
        db.execute(f"SELECT 1 FROM {t} WHERE universe_id IS NULL").fetchone()
        for t in ("lore", "characters", "conversations")
    )
    if not orphans:
        return
    universe_id = db.execute("INSERT INTO universes (name) VALUES (?)", (DEFAULT_UNIVERSE,)).lastrowid
    for table in ("lore", "characters", "conversations"):
        db.execute(f"UPDATE {table} SET universe_id = ? WHERE universe_id IS NULL", (universe_id,))
    db.execute(
        "INSERT OR IGNORE INTO conversation_characters (conversation_id, character_id) "
        "SELECT conv.id, c.id FROM conversations conv JOIN characters c "
        "ON c.universe_id = conv.universe_id WHERE conv.mode = 'mj'"
    )


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


# --- Contextes ----------------------------------------------------------------

def list_universes() -> list[dict]:
    with connect() as db:
        return rows(db.execute("SELECT * FROM universes ORDER BY name COLLATE NOCASE"))


def get_universe(universe_id: int) -> dict | None:
    with connect() as db:
        row = db.execute("SELECT * FROM universes WHERE id = ?", (universe_id,)).fetchone()
        return dict(row) if row else None


def save_universe(universe_id: int | None, name: str) -> int:
    with connect() as db:
        if universe_id is None:
            return db.execute("INSERT INTO universes (name) VALUES (?)", (name,)).lastrowid
        db.execute("UPDATE universes SET name = ? WHERE id = ?", (name, universe_id))
        return universe_id


def delete_universe(universe_id: int) -> None:
    """Supprime aussi ses sections, personnages et conversations."""
    with connect() as db:
        db.execute("DELETE FROM universes WHERE id = ?", (universe_id,))


# --- Lore -------------------------------------------------------------------

def list_lore(universe_id: int) -> list[dict]:
    with connect() as db:
        return rows(db.execute(
            "SELECT * FROM lore WHERE universe_id = ? ORDER BY position, id", (universe_id,)
        ))


def save_lore(lore_id: int | None, universe_id: int, title: str, content: str, secret: bool, position: int) -> int:
    with connect() as db:
        if lore_id is None:
            cur = db.execute(
                "INSERT INTO lore (universe_id, title, content, secret, position) VALUES (?, ?, ?, ?, ?)",
                (universe_id, title, content, int(secret), position),
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

def list_characters(universe_id: int) -> list[dict]:
    with connect() as db:
        return rows(db.execute(
            "SELECT * FROM characters WHERE universe_id = ? ORDER BY name COLLATE NOCASE", (universe_id,)
        ))


def get_character(character_id: int) -> dict | None:
    with connect() as db:
        row = db.execute("SELECT * FROM characters WHERE id = ?", (character_id,)).fetchone()
        return dict(row) if row else None


def save_character(character_id: int | None, universe_id: int, name: str, player: str, sheet: str, gm_notes: str) -> int:
    with connect() as db:
        if character_id is None:
            cur = db.execute(
                "INSERT INTO characters (universe_id, name, player, sheet, gm_notes) VALUES (?, ?, ?, ?, ?)",
                (universe_id, name, player, sheet, gm_notes),
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

def list_conversations(mode: str, universe_id: int) -> list[dict]:
    with connect() as db:
        return rows(db.execute(
            "SELECT id, mode, title, character_id, created_at FROM conversations "
            "WHERE mode = ? AND universe_id = ? ORDER BY id DESC",
            (mode, universe_id),
        ))


def get_conversation(conversation_id: int) -> dict | None:
    with connect() as db:
        row = db.execute("SELECT * FROM conversations WHERE id = ?", (conversation_id,)).fetchone()
        if not row:
            return None
        conv = dict(row)
        conv["character_ids"] = [r[0] for r in db.execute(
            "SELECT character_id FROM conversation_characters WHERE conversation_id = ? ORDER BY character_id",
            (conversation_id,),
        )]
        return conv


def create_conversation(
    mode: str, universe_id: int, title: str, character_id: int | None,
    character_ids: list[int], system: str, context_hash: str,
) -> int:
    with connect() as db:
        conversation_id = db.execute(
            "INSERT INTO conversations (mode, universe_id, title, character_id, system, context_hash) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (mode, universe_id, title, character_id, system, context_hash),
        ).lastrowid
        db.executemany(
            "INSERT INTO conversation_characters (conversation_id, character_id) VALUES (?, ?)",
            [(conversation_id, cid) for cid in character_ids],
        )
        return conversation_id


def rename_conversation(conversation_id: int, title: str) -> None:
    with connect() as db:
        db.execute("UPDATE conversations SET title = ? WHERE id = ?", (title, conversation_id))


def set_conversation_characters(conversation_id: int, character_ids: list[int]) -> None:
    with connect() as db:
        db.execute("DELETE FROM conversation_characters WHERE conversation_id = ?", (conversation_id,))
        db.executemany(
            "INSERT INTO conversation_characters (conversation_id, character_id) VALUES (?, ?)",
            [(conversation_id, cid) for cid in character_ids],
        )


def set_system(conversation_id: int, system: str) -> None:
    with connect() as db:
        db.execute("UPDATE conversations SET system = ? WHERE id = ?", (system, conversation_id))


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
