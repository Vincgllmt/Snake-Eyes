"""Instructions système et mise en forme du contexte (univers + personnages)."""

import hashlib

from . import db

MJ_INSTRUCTIONS = """\
Tu es l'assistant du meneur de jeu (MJ) pour une campagne de jeu de rôle sur table \
se déroulant dans l'univers maison « Snake Eyes ». Le contexte fourni ci-dessous \
(univers, règles, personnages des joueurs, notes du MJ) fait autorité : appuie-toi \
dessus, respecte sa cohérence, et signale quand une idée contredit ou étend un \
élément établi.

Ton rôle :
- Proposer des idées concrètes et jouables : accroches, scènes, PNJ (nom, motivation, \
  manière de parler), rebondissements, complications, récompenses, lieux.
- Exploiter les personnages : leurs historiques, objectifs, failles et liens sont \
  la meilleure matière pour impliquer les joueurs. Cite-les nommément.
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
l'univers maison « Snake Eyes ». Le contexte fourni ci-dessous (univers et règles \
publics, éventuellement la fiche du joueur) fait autorité.

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


def _lore_section(include_secret: bool) -> str:
    parts = []
    for entry in db.list_lore():
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


def build_context(mode: str, character_id: int | None) -> str:
    """Contexte complet envoyé à Claude. Doit être déterministe (sert au cache et au hash)."""
    if mode == "mj":
        characters = db.list_characters()
        chars = "\n\n".join(_character_block(c, with_gm_notes=True) for c in characters)
        return (
            "<univers>\n" + _lore_section(include_secret=True) + "\n</univers>\n\n"
            "<personnages_joueurs>\n" + (chars or "(aucun personnage)") + "\n</personnages_joueurs>"
        )

    context = "<univers_public>\n" + _lore_section(include_secret=False) + "\n</univers_public>"
    others = [c for c in db.list_characters() if c["id"] != character_id]
    if others:
        context += "\n\n<autres_personnages_du_groupe>\n" + "\n".join(
            f'- {c["name"]} (joué par {c["player"] or "?"})' for c in others
        ) + "\n</autres_personnages_du_groupe>"
    if character_id is not None:
        c = db.get_character(character_id)
        if c:
            context += "\n\n<fiche_du_joueur>\n" + _character_block(c, with_gm_notes=False) + "\n</fiche_du_joueur>"
    return context


def instructions(mode: str) -> str:
    return MJ_INSTRUCTIONS if mode == "mj" else JOUEUR_INSTRUCTIONS


def context_hash(context: str) -> str:
    return hashlib.sha256(context.encode("utf-8")).hexdigest()


def context_update_message(context: str) -> str:
    return (
        "[Note automatique de l'application Snake Eyes] Le contexte de la campagne a été modifié. "
        "La version ci-dessous remplace entièrement celle du prompt système et des mises à jour "
        "précédentes :\n\n" + context
    )
