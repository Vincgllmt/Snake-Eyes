"""Instructions système et mise en forme du contexte (univers + personnages)."""

import hashlib

from . import db

MJ_INSTRUCTIONS = """\
Tu es l'assistant du meneur de jeu (MJ) pour une campagne de jeu de rôle sur table \
se déroulant dans l'univers maison décrit ci-dessous. Ce contexte (univers, règles, \
personnages des joueurs concernés, notes du MJ) fait autorité : appuie-toi dessus, \
respecte sa cohérence, et signale quand une idée contredit ou étend un élément établi.

Ton rôle :
- Proposer des idées concrètes et jouables : accroches, scènes, PNJ (nom, motivation, \
  manière de parler), rebondissements, complications, récompenses, lieux.
- Exploiter les personnages concernés : leurs historiques, objectifs, failles et liens \
  sont la meilleure matière pour impliquer les joueurs. Cite-les nommément. Les \
  personnages listés comme absents ne participent pas : ne construis pas d'idées \
  autour d'eux sauf si le MJ le demande.
- Aider à improviser en cours de partie : quand le MJ décrit une situation, donne \
  plusieurs options courtes plutôt qu'une seule longue réponse.
- Répondre aux questions de règles en t'appuyant sur les règles fournies ; si une \
  règle manque, dis-le et propose un arbitrage cohérent en le présentant comme tel.

Tu parles au MJ : tu peux évoquer librement les secrets de l'univers et les notes \
du MJ. Réponds en français, de façon structurée et directe, sans préambule. \
N'invente pas de faits sur l'univers en les présentant comme établis : distingue \
« établi » de « proposition »."""

JOUEUR_INSTRUCTIONS = """\
Tu aides un joueur d'une campagne de jeu de rôle sur table se déroulant dans \
l'univers maison décrit ci-dessous. Le contexte fourni (univers et règles publics, \
éventuellement la fiche du joueur) fait autorité.

Ton rôle :
- Expliquer les règles de création de personnage et l'univers, à partir du contexte \
  fourni uniquement.
- Aider à construire une fiche : concept, historique, motivations, choix techniques \
  (caractéristiques, compétences, équipement…) en respectant les règles fournies, \
  et vérifier qu'une fiche est conforme quand on te le demande.
- Proposer des idées d'historique et de personnalité qui s'intègrent à l'univers \
  et au groupe, en laissant toujours le dernier mot au joueur.

Limites :
- Tu n'as accès qu'aux informations publiques. Si on te demande des secrets du \
  scénario ou de l'univers, réponds que c'est au MJ d'en décider.
- Si une règle n'est pas dans le contexte, dis-le et conseille de demander au MJ \
  plutôt que d'inventer.

Réponds en français, de façon claire et concise, sans préambule."""


def _lore_section(universe_id: int, include_secret: bool) -> str:
    parts = []
    for entry in db.list_lore(universe_id):
        if entry["secret"] and not include_secret:
            continue
        tag = " [SECRET — MJ uniquement]" if entry["secret"] else ""
        parts.append(f'<section titre="{entry["title"]}{tag}">\n{entry["content"].strip()}\n</section>')
    return "\n\n".join(parts) or "(aucun élément d'univers renseigné pour l'instant)"


def _character_block(c: dict, with_gm_notes: bool) -> str:
    lines = [f'<personnage nom="{c["name"]}" joueur="{c["player"] or "?"}">', c["sheet"].strip() or "(fiche vide)"]
    if with_gm_notes and c["gm_notes"].strip():
        lines += ["<notes_mj>", c["gm_notes"].strip(), "</notes_mj>"]
    lines.append("</personnage>")
    return "\n".join(lines)


def _names(characters: list[dict]) -> str:
    return "\n".join(f'- {c["name"]} (joué par {c["player"] or "?"})' for c in characters)


def build_context(mode: str, universe_id: int, character_id: int | None = None,
                  character_ids: list[int] | None = None) -> str:
    """Contexte complet envoyé à Claude. Doit être déterministe (sert au hash).

    Mode MJ : `character_ids` = personnages concernés (fiches complètes + notes MJ),
    les autres personnages de l'univers sont seulement nommés comme absents.
    Mode joueur : `character_id` = fiche du joueur (sans notes MJ), univers public seulement."""
    universe = db.get_universe(universe_id)
    name = universe["name"] if universe else "?"
    characters = db.list_characters(universe_id)

    if mode == "mj":
        selected = set(character_ids or [])
        involved = [c for c in characters if c["id"] in selected]
        absent = [c for c in characters if c["id"] not in selected]
        blocks = "\n\n".join(_character_block(c, with_gm_notes=True) for c in involved)
        context = (
            f'<univers contexte="{name}">\n' + _lore_section(universe_id, include_secret=True) + "\n</univers>\n\n"
            "<personnages_concernes>\n" + (blocks or "(aucun personnage sélectionné)") + "\n</personnages_concernes>"
        )
        if absent:
            context += "\n\n<personnages_absents>\n" + _names(absent) + "\n</personnages_absents>"
        return context

    context = f'<univers_public contexte="{name}">\n' + _lore_section(universe_id, include_secret=False) + "\n</univers_public>"
    others = [c for c in characters if c["id"] != character_id]
    if others:
        context += "\n\n<autres_personnages_du_groupe>\n" + _names(others) + "\n</autres_personnages_du_groupe>"
    player_character = next((c for c in characters if c["id"] == character_id), None)
    if player_character:
        context += "\n\n<fiche_du_joueur>\n" + _character_block(player_character, with_gm_notes=False) + "\n</fiche_du_joueur>"
    return context


def conversation_context(conv: dict) -> str:
    return build_context(conv["mode"], conv["universe_id"], conv["character_id"], conv["character_ids"])


def instructions(mode: str) -> str:
    return MJ_INSTRUCTIONS if mode == "mj" else JOUEUR_INSTRUCTIONS


def context_hash(context: str) -> str:
    return hashlib.sha256(context.encode("utf-8")).hexdigest()


def context_update_message(context: str) -> str:
    return (
        "[Note automatique de l'application Snake Eyes] Le contexte de la campagne a été modifié "
        "(univers, fiches ou personnages concernés). La version ci-dessous remplace entièrement "
        "celle du prompt système et des mises à jour précédentes :\n\n" + context
    )
