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

CREATION_INSTRUCTIONS = """\
Tu aides le meneur de jeu (MJ) à préparer une campagne de jeu de rôle sur table \
se déroulant dans l'univers maison décrit ci-dessous (règles, lieux, factions, PNJ, \
intrigues, secrets du MJ). Ce contexte fait autorité : ce que tu crées doit s'y \
intégrer sans le contredire.

Ton rôle : rédiger, à la demande du MJ, des éléments prêts à être ajoutés à \
l'univers de la campagne — quêtes et scénarios, PNJ, lieux, factions, objets, \
créatures, rumeurs, tables aléatoires…
- Sois concret et jouable : noms, motivations, enjeux, indices, obstacles, \
  récompenses, statistiques si les règles fournies en prévoient.
- Rattache tes créations à l'existant : lieux, factions, PNJ et intrigues déjà \
  établis. Tu ne connais pas les personnages des joueurs : n'invente rien à leur \
  sujet ; si le MJ en parle, appuie-toi sur ce qu'il en dit.
- Si la demande est vague, fais des choix et assume-les plutôt que de poser des \
  questions ; le MJ demandera des modifications.
- Quand le MJ demande une modification, renvoie l'élément complet mis à jour, \
  pas seulement le passage modifié.

Format : ta réponse est destinée à être enregistrée telle quelle comme section de \
l'univers. Écris en Markdown, commence directement par un titre de niveau 1 \
(`# Nom de l'élément`), sans préambule ni conclusion, et utilise des intertitres \
de niveau 2 ou plus. Sépare ce que les joueurs peuvent découvrir de ce qui reste \
réservé au MJ (secrets, vérité cachée, plans des PNJ). Réponds en français."""

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


def _lore_block(entry: dict) -> str:
    tag = " [SECRET — MJ uniquement]" if entry["secret"] else ""
    group = f' groupe="{entry["category"]}"' if entry["category"] else ""
    return f'<section titre="{entry["title"]}{tag}"{group}>\n{entry["content"].strip()}\n</section>'


def _character_block(c: dict, with_gm_notes: bool) -> str:
    lines = [f'<personnage nom="{c["name"]}" joueur="{c["player"] or "?"}">', c["sheet"].strip() or "(fiche vide)"]
    if with_gm_notes and c["gm_notes"].strip():
        lines += ["<notes_mj>", c["gm_notes"].strip(), "</notes_mj>"]
    lines.append("</personnage>")
    return "\n".join(lines)


def _names(tag: str, characters: list[dict]) -> str:
    names = "\n".join(f'- {c["name"]} (joué par {c["player"] or "?"})' for c in characters)
    return f"<{tag}>\n{names}\n</{tag}>"


def build_context(mode: str, universe_id: int, character_id: int | None = None,
                  character_ids: list[int] | None = None) -> tuple[str, dict[str, str]]:
    """Contexte envoyé à Claude : le texte complet (prompt système) et ses blocs
    identifiés (`lore:<id>`, `pj:<id>`…), qui permettent de n'envoyer ensuite que
    ce qui a changé. Doit être déterministe (sert au hash).

    Mode MJ : `character_ids` = personnages concernés (fiches complètes + notes MJ),
    les autres personnages de l'univers sont seulement nommés comme absents.
    Mode création (Aide MJ) : tout l'univers, secrets compris, sans les personnages joueurs.
    Mode joueur : `character_id` = fiche du joueur (sans notes MJ), univers public seulement."""
    universe = db.get_universe(universe_id)
    name = universe["name"] if universe else "?"
    characters = db.list_characters(universe_id)
    lore = {
        f"lore:{e['id']}": _lore_block(e)
        for e in db.list_lore(universe_id)
        if mode != "joueur" or not e["secret"]
    }
    lore_text = "\n\n".join(lore.values()) or "(aucun élément d'univers renseigné pour l'instant)"
    blocks = dict(lore)

    if mode == "creation":
        return f'<univers contexte="{name}">\n{lore_text}\n</univers>', blocks

    if mode == "mj":
        selected = set(character_ids or [])
        involved = {f"pj:{c['id']}": _character_block(c, with_gm_notes=True) for c in characters if c["id"] in selected}
        absent = [c for c in characters if c["id"] not in selected]
        blocks.update(involved)
        context = (
            f'<univers contexte="{name}">\n{lore_text}\n</univers>\n\n'
            "<personnages_concernes>\n" + ("\n\n".join(involved.values()) or "(aucun personnage sélectionné)")
            + "\n</personnages_concernes>"
        )
        if absent:
            blocks["absents"] = _names("personnages_absents", absent)
            context += "\n\n" + blocks["absents"]
        return context, blocks

    context = f'<univers_public contexte="{name}">\n{lore_text}\n</univers_public>'
    others = [c for c in characters if c["id"] != character_id]
    if others:
        blocks["autres"] = _names("autres_personnages_du_groupe", others)
        context += "\n\n" + blocks["autres"]
    player_character = next((c for c in characters if c["id"] == character_id), None)
    if player_character:
        blocks["fiche"] = "<fiche_du_joueur>\n" + _character_block(player_character, with_gm_notes=False) + "\n</fiche_du_joueur>"
        context += "\n\n" + blocks["fiche"]
    return context, blocks


def conversation_context(conv: dict) -> tuple[str, dict[str, str]]:
    return build_context(conv["mode"], conv["universe_id"], conv["character_id"], conv["character_ids"])


def instructions(mode: str) -> str:
    return {"mj": MJ_INSTRUCTIONS, "creation": CREATION_INSTRUCTIONS}.get(mode, JOUEUR_INSTRUCTIONS)


def context_hash(context: str) -> str:
    return hashlib.sha256(context.encode("utf-8")).hexdigest()


NOTE = "[Note automatique de l'application Snake Eyes] "


def context_update_message(context: str) -> str:
    return (
        NOTE + "Le contexte de la campagne a été modifié (univers, fiches ou personnages "
        "concernés). La version ci-dessous remplace entièrement celle du prompt système et "
        "des mises à jour précédentes :\n\n" + context
    )


def context_diff_message(old: dict[str, str], new: dict[str, str]) -> str:
    """Seulement les blocs ajoutés, modifiés ou retirés depuis le dernier envoi :
    renvoyer tout le contexte à chaque retouche gonflerait la conversation."""
    changed = [text for key, text in new.items() if old.get(key) != text]
    removed = [text.split("\n", 1)[0] for key, text in old.items() if key not in new]
    parts = [NOTE + "Le contexte de la campagne a été modifié depuis le dernier message. "
             "Le reste du contexte est inchangé."]
    if changed:
        parts.append("Éléments ajoutés ou modifiés (chacun remplace entièrement sa version "
                     "précédente) :\n\n" + "\n\n".join(changed))
    if removed:
        parts.append("Éléments retirés du contexte (n'en tiens plus compte) :\n" + "\n".join(f"- {r}" for r in removed))
    return "\n\n".join(parts)
