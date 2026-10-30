// Snake Eyes — interface

const $ = (sel) => document.querySelector(sel);

const api = async (method, url, body) => {
  const res = await fetch(url, {
    method,
    headers: body ? { "Content-Type": "application/json" } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
  return res.json();
};

const md = (text) => DOMPurify.sanitize(marked.parse(text || ""));
const escape = (s) => s.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);

const store = {
  get(key) { try { return localStorage.getItem(key); } catch { return null; } },
  set(key, value) { try { localStorage.setItem(key, value); } catch { /* stockage indisponible */ } },
};

const state = { view: "mj", universeId: null, conversationId: null, conversation: null, itemId: null, sending: false };

// --- Contextes (appelés « universes » dans le code et la base) --------------

let universes = [];

async function loadUniverses() {
  universes = await api("GET", "/api/universes");
  const saved = Number(store.get("universeId"));
  if (!universes.some((u) => u.id === state.universeId)) {
    state.universeId = universes.some((u) => u.id === saved) ? saved : universes[0].id;
  }
  $("#universe").innerHTML = universes
    .map((u) => `<option value="${u.id}" ${u.id === state.universeId ? "selected" : ""}>${escape(u.name)}</option>`)
    .join("");
  $("#delete-universe").disabled = universes.length <= 1;
}

async function selectUniverse(id) {
  state.universeId = id;
  store.set("universeId", id);
  await loadUniverses();
  await showView(state.view);
}

$("#universe").addEventListener("change", (e) => selectUniverse(Number(e.target.value)));

$("#rename-universe").addEventListener("click", async () => {
  const current = universes.find((u) => u.id === state.universeId);
  const name = prompt("Nom du contexte :", current.name);
  if (!name?.trim()) return;
  await api("PUT", `/api/universes/${state.universeId}`, { name });
  await loadUniverses();
});

$("#new-universe").addEventListener("click", async () => {
  const name = prompt("Nom du nouveau contexte (ex. une campagne) :");
  if (!name?.trim()) return;
  const { id } = await api("POST", "/api/universes", { name });
  await selectUniverse(id);
});

$("#delete-universe").addEventListener("click", async () => {
  const current = universes.find((u) => u.id === state.universeId);
  if (!confirm(`Supprimer le contexte « ${current.name} » avec tout son univers, ses personnages et ses conversations ?`)) return;
  await api("DELETE", `/api/universes/${state.universeId}`);
  state.universeId = null;
  await selectUniverse(universes.find((u) => u.id !== current.id).id);
});

// --- Navigation ---------------------------------------------------------------

document.querySelectorAll("nav button").forEach((btn) =>
  btn.addEventListener("click", () => showView(btn.dataset.view))
);

async function showView(view) {
  state.view = view;
  document.querySelectorAll("nav button").forEach((b) => b.classList.toggle("active", b.dataset.view === view));
  const isChat = CHAT_MODES.includes(view);
  $("#view-chat").hidden = !isChat;
  $("#view-editor").hidden = isChat;
  if (isChat) {
    state.conversationId = null;
    showChat(null);
    $("#new-character").hidden = view !== "joueur";
    if (view === "joueur") await fillCharacterSelect();
    await loadConversations();
  } else {
    state.itemId = null;
    await loadItems();
    showEditor(null);
  }
}

// --- Conversations ------------------------------------------------------------

const CHAT_MODES = ["mj", "creation", "joueur"];
const WELCOME = {
  mj: "Choisis les personnages concernés ci-dessus, puis pose une question, décris une situation de jeu ou demande des idées.",
  creation: "Demande une quête, un PNJ, un lieu, une faction, un objet… Claude connaît tout l'univers et tous les personnages. Chaque réponse peut être ajoutée à l'univers avec le bouton en dessous.",
  joueur: "Demande de l'aide pour créer ou vérifier une fiche, ou pose une question sur l'univers et les règles.",
};
// Réponses que le MJ peut verser dans l'univers (jamais en mode joueur).
const canSaveToLore = () => state.view !== "joueur";

const charactersOf = () => api("GET", `/api/characters?universe_id=${state.universeId}`);

async function fillCharacterSelect() {
  const chars = await charactersOf();
  $("#new-character").innerHTML =
    `<option value="">Sans fiche (création de perso)</option>` +
    chars.map((c) => `<option value="${c.id}">Fiche : ${escape(c.name)}</option>`).join("");
}

async function loadConversations() {
  const convs = await api("GET", `/api/conversations?mode=${state.view}&universe_id=${state.universeId}`);
  $("#conversations").innerHTML = convs
    .map((c) => `<li data-id="${c.id}" class="${c.id === state.conversationId ? "active" : ""}">${escape(c.title)}<small>${c.created_at}</small></li>`)
    .join("");
  $("#conversations").querySelectorAll("li").forEach((li) =>
    li.addEventListener("click", () => openConversation(Number(li.dataset.id)))
  );
}

$("#new-conversation").addEventListener("click", async () => {
  const charId = state.view === "joueur" ? $("#new-character").value : "";
  const { id } = await api("POST", "/api/conversations", {
    mode: state.view,
    universe_id: state.universeId,
    character_id: charId ? Number(charId) : null,
  });
  await openConversation(id);
  $("#input").focus();
});

function showChat(conv) {
  $("#chat-empty").hidden = !!conv;
  $("#chat-panel").hidden = !conv;
}

async function openConversation(id) {
  state.conversationId = id;
  const conv = await api("GET", `/api/conversations/${id}`);
  state.conversation = conv;
  showChat(conv);
  $("#chat-title").value = conv.title;
  await renderCast();
  $("#messages").innerHTML = "";
  for (const m of conv.messages) {
    const div = addMessage(m.role, m.text);
    if (m.role === "assistant") addLoreButton(div, m.text);
  }
  if (!conv.messages.length) addMessage("notice", WELCOME[state.view]);
  await loadConversations();
}

// Mode MJ : puces des personnages du contexte, cliquables pour les inclure ou non.
async function renderCast() {
  const conv = state.conversation;
  $("#cast").hidden = conv.mode !== "mj";
  if (conv.mode !== "mj") return;
  const chars = await charactersOf();
  const selected = new Set(conv.character_ids);
  $("#cast-chips").innerHTML = chars.length
    ? chars.map((c) => `<button type="button" class="chip ${selected.has(c.id) ? "on" : ""}" data-id="${c.id}" title="${escape(c.player || "")}">${escape(c.name)}</button>`).join(" ")
    : `<span class="hint">aucun personnage dans ce contexte (onglet Personnages)</span>`;
  $("#cast-chips").querySelectorAll(".chip").forEach((chip) =>
    chip.addEventListener("click", async () => {
      const id = Number(chip.dataset.id);
      const ids = selected.has(id) ? conv.character_ids.filter((x) => x !== id) : [...conv.character_ids, id];
      await api("PUT", `/api/conversations/${conv.id}`, { character_ids: ids });
      conv.character_ids = ids;
      await renderCast();
    })
  );
}

function addMessage(role, text) {
  const div = document.createElement("div");
  div.className = `msg ${role}`;
  if (role === "assistant") div.innerHTML = md(text);
  else div.textContent = text;
  $("#messages").appendChild(div);
  $("#messages").scrollTop = $("#messages").scrollHeight;
  return div;
}

// --- Ajout d'une réponse à l'univers ------------------------------------------

function addLoreButton(div, text) {
  if (!canSaveToLore()) return;
  const btn = Object.assign(document.createElement("button"), {
    type: "button", className: "to-lore", textContent: "＋ Ajouter à l'univers",
  });
  btn.addEventListener("click", () => openLoreDialog(text));
  div.appendChild(btn);
}

// Un titre Markdown en première ligne devient le titre de la section.
function splitTitle(text) {
  const match = text.trim().match(/^#{1,6}\s+(.+?)\s*#*\s*(?:\n|$)/);
  return match
    ? { title: match[1].replace(/[*_`]/g, "").trim(), content: text.trim().slice(match[0].length).trim() }
    : { title: "", content: text.trim() };
}

let loreSections = [];

async function openLoreDialog(text) {
  loreSections = await api("GET", `/api/lore?universe_id=${state.universeId}`);
  const f = $("#to-lore-form");
  const { title, content } = splitTitle(text);
  f.destination.innerHTML = `<option value="">Nouvelle section</option>` +
    loreSections.map((l) => `<option value="${l.id}">À la suite de : ${l.secret ? "🔒 " : ""}${escape(l.title)}</option>`).join("");
  f.title.value = title;
  f.content.value = content;
  f.secret.checked = true;
  updateLoreDialog();
  $("#to-lore").showModal();
  f.title.focus();
}

// À la suite d'une section existante : le titre devient un intertitre et le statut secret est celui de la section.
function updateLoreDialog() {
  const f = $("#to-lore-form");
  const section = loreSections.find((l) => l.id === Number(f.destination.value));
  $("#to-lore-title-label").textContent = section ? "Intertitre" : "Titre de la section";
  f.title.required = !section;
  f.secret.disabled = !!section;
  if (section) f.secret.checked = !!section.secret;
}

$("#to-lore-form").destination.addEventListener("change", updateLoreDialog);
$("#to-lore-cancel").addEventListener("click", () => $("#to-lore").close());

$("#to-lore-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = e.target;
  const title = f.title.value.trim();
  const content = f.content.value.trim();
  const section = loreSections.find((l) => l.id === Number(f.destination.value));
  try {
    if (section) {
      const added = (title ? `## ${title}\n\n` : "") + content;
      await api("PUT", `/api/lore/${section.id}`, {
        ...section, content: [section.content.trimEnd(), added].filter(Boolean).join("\n\n"),
      });
    } else {
      const position = Math.max(0, ...loreSections.map((l) => l.position));
      await api("POST", "/api/lore", { universe_id: state.universeId, title, content, secret: f.secret.checked, position });
    }
  } catch (err) {
    alert(`Impossible d'ajouter à l'univers : ${err.message}`);
    return;
  }
  $("#to-lore").close();
  addMessage("notice", `Ajouté à l'univers : « ${section ? section.title : title} ».`);
});

$("#chat-title").addEventListener("change", async () => {
  await api("PUT", `/api/conversations/${state.conversationId}`, { title: $("#chat-title").value });
  await loadConversations();
});

$("#delete-conversation").addEventListener("click", async () => {
  await api("DELETE", `/api/conversations/${state.conversationId}`);
  state.conversationId = null;
  showChat(null);
  await loadConversations();
});

$("#input").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    $("#composer").requestSubmit();
  }
});

$("#composer").addEventListener("submit", async (e) => {
  e.preventDefault();
  const text = $("#input").value.trim();
  if (!text || state.sending) return;
  state.sending = true;
  $("#send").disabled = true;
  $("#input").value = "";

  const convId = state.conversationId;
  const userDiv = addMessage("user", text);
  const replyDiv = addMessage("assistant", "");
  replyDiv.classList.add("pending");
  let reply = "";
  let ok = false;

  try {
    const res = await fetch(`/api/conversations/${convId}/messages`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content: text }),
    });
    if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let sep;
      while ((sep = buffer.indexOf("\n\n")) !== -1) {
        const line = buffer.slice(0, sep);
        buffer = buffer.slice(sep + 2);
        if (!line.startsWith("data: ")) continue;
        const ev = JSON.parse(line.slice(6));
        if (ev.type === "text") {
          reply += ev.text;
          replyDiv.innerHTML = md(reply);
          $("#messages").scrollTop = $("#messages").scrollHeight;
        } else if (ev.type === "notice") {
          $("#messages").insertBefore(Object.assign(document.createElement("div"), { className: "msg notice", textContent: ev.text }), userDiv);
        } else if (ev.type === "error") {
          throw new Error(ev.message);
        } else if (ev.type === "done") {
          ok = true;
          addLoreButton(replyDiv, reply);
          if (ev.truncated) addMessage("notice", "Réponse tronquée (longueur maximale atteinte).");
        }
      }
    }
    if (!ok) throw new Error("La connexion a été interrompue avant la fin de la réponse.");
  } catch (err) {
    // Rien n'a été enregistré côté serveur : on retire l'échange et on remet le texte dans la saisie.
    userDiv.remove();
    replyDiv.remove();
    addMessage("error", `${err.message} — ton message n'a pas été envoyé.`);
    $("#input").value = text;
  } finally {
    replyDiv.classList.remove("pending");
    state.sending = false;
    $("#send").disabled = false;
    if (ok && convId === state.conversationId) await loadConversations();
  }
});

// --- Sections d'univers & personnages -----------------------------------------

// Champ Markdown édité en WYSIWYG : la textarea cachée porte la valeur lue par le formulaire,
// l'éditeur est monté dans le div voisin par mountMarkdownEditors().
const mdField = (name, label, value, size, { docx = false } = {}) => `
  <div class="field">
    <div class="field-head">
      <span>${label}</span>
      ${docx ? `<label class="import-docx" title="Remplace le contenu par celui d'un document Word">
        Importer un .docx<input type="file" accept=".docx" hidden></label>` : ""}
    </div>
    <textarea name="${name}" class="md" data-size="${size}" hidden>${escape(value)}</textarea>
    <div class="md-editor"></div>
  </div>`;

const Editor = typeof window.toastui?.Editor === "function" ? window.toastui.Editor : null;
const colorSyntax = Editor?.plugin?.colorSyntax || Editor?.plugin?.uml; // le plugin s'enregistre sous « uml » (bug upstream)
let mdEditors = [];

function mountMarkdownEditors(form) {
  mdEditors.forEach(({ editor }) => editor.destroy());
  const textareas = [...form.querySelectorAll("textarea.md")];
  if (!Editor) {
    // Éditeur indisponible (CDN injoignable…) : on retombe sur les textareas Markdown.
    textareas.forEach((t) => { t.hidden = false; t.classList.add(t.dataset.size); });
    mdEditors = [];
    return;
  }
  mdEditors = textareas.map((textarea) => {
    const editor = new Editor({
      el: textarea.nextElementSibling,
      initialValue: textarea.value,
      initialEditType: "wysiwyg",
      previewStyle: "tab",
      height: textarea.dataset.size === "big" ? "520px" : "280px",
      language: "fr-FR",
      theme: "dark",
      usageStatistics: false,
      plugins: colorSyntax ? [colorSyntax] : [],
      toolbarItems: [
        ["heading", "bold", "italic", "strike"],
        ["hr", "quote"],
        ["ul", "ol", "task", "indent", "outdent"],
        ["table", "link"],
        ["code", "codeblock"],
      ],
    });
    const importer = textarea.closest(".field").querySelector(".import-docx");
    if (importer) {
      if (window.mammoth) importer.querySelector("input").addEventListener("change", (e) => importDocx(e.target, editor));
      else importer.hidden = true;
    }
    return { textarea, editor };
  });
}

// Un tableau Markdown exige une ligne d'en-tête et des cellules d'une seule ligne :
// on promeut la première ligne en <thead> et on aplatit les paragraphes des cellules.
function normalizeDocxTables(html) {
  const doc = new DOMParser().parseFromString(html, "text/html");
  doc.querySelectorAll("table").forEach((table) => {
    table.querySelectorAll("td, th").forEach((cell) => {
      const parts = [...cell.querySelectorAll("p, li")].map((p) => p.innerHTML.trim()).filter(Boolean);
      if (parts.length) cell.innerHTML = parts.join("<br>");
    });
    if (!table.tHead) {
      const first = table.rows[0];
      if (!first) return;
      const head = table.createTHead();
      const row = head.insertRow();
      [...first.cells].forEach((cell) => {
        const th = doc.createElement("th");
        th.innerHTML = cell.innerHTML;
        row.appendChild(th);
      });
      first.remove();
    }
  });
  return doc.body.innerHTML;
}

async function importDocx(input, editor) {
  const file = input.files[0];
  input.value = ""; // permet de réimporter le même fichier
  if (!file) return;
  if (editor.getMarkdown().trim() && !confirm(`Remplacer le contenu actuel par celui de « ${file.name} » ?`)) return;
  try {
    const { value: html } = await mammoth.convertToHtml({ arrayBuffer: await file.arrayBuffer() });
    // Les images (souvent lourdes, en base64) n'ont rien à faire dans le Markdown envoyé à Claude.
    editor.setHTML(normalizeDocxTables(DOMPurify.sanitize(html, { FORBID_TAGS: ["img"] })));
  } catch (err) {
    alert(`Impossible de lire « ${file.name} » : ${err.message}`);
  }
}

const syncMarkdownEditors = () =>
  mdEditors.forEach(({ textarea, editor }) => (textarea.value = editor.getMarkdown()));

const EDITORS = {
  lore: {
    url: "/api/lore",
    empty: "Ajoute des sections à l'univers de ce contexte : histoire, lieux, factions, règles, ton de la campagne… Les sections marquées « secret » ne sont jamais envoyées en mode joueur.",
    label: (it) => `${it.secret ? "🔒 " : ""}${escape(it.title)}`,
    blank: { title: "", content: "", secret: false, position: 0 },
    fields: (it) => `
      <label>Titre<input name="title" required value="${escape(it.title)}"></label>
      <label>Ordre d'affichage<input name="position" type="number" value="${it.position}"></label>
      <label class="check"><input name="secret" type="checkbox" ${it.secret ? "checked" : ""}> Secret — réservé au MJ</label>
      ${mdField("content", "Contenu", it.content, "big")}`,
    read: (f) => ({
      title: f.title.value, content: f.content.value, secret: f.secret.checked, position: Number(f.position.value) || 0,
    }),
  },
  characters: {
    url: "/api/characters",
    empty: "Ajoute les fiches des personnages joueurs de ce contexte. Les notes MJ ne sont jamais envoyées en mode joueur.",
    label: (it) => `${escape(it.name)}<small>${escape(it.player || "joueur ?")}</small>`,
    blank: { name: "", player: "", sheet: "", gm_notes: "" },
    fields: (it) => `
      <label>Nom du personnage<input name="name" required value="${escape(it.name)}"></label>
      <label>Joueur<input name="player" value="${escape(it.player)}"></label>
      ${mdField("sheet", "Fiche (caractéristiques, compétences, historique…)", it.sheet, "big", { docx: true })}
      ${mdField("gm_notes", "Notes MJ (secrets, arcs prévus — invisibles en mode joueur)", it.gm_notes, "small")}`,
    read: (f) => ({ name: f.name.value, player: f.player.value, sheet: f.sheet.value, gm_notes: f.gm_notes.value }),
  },
};

let items = [];

async function loadItems() {
  const ed = EDITORS[state.view];
  items = await api("GET", `${ed.url}?universe_id=${state.universeId}`);
  $("#items").innerHTML = items
    .map((it) => `<li data-id="${it.id}" class="${it.id === state.itemId ? "active" : ""}">${ed.label(it)}</li>`)
    .join("");
  $("#items").querySelectorAll("li").forEach((li) =>
    li.addEventListener("click", () => {
      state.itemId = Number(li.dataset.id);
      showEditor(items.find((it) => it.id === state.itemId));
      loadItems();
    })
  );
}

function showEditor(item) {
  const ed = EDITORS[state.view];
  const form = $("#editor-form");
  $("#editor-empty").hidden = !!item;
  $("#editor-empty").textContent = ed.empty;
  form.hidden = !item;
  if (!item) {
    form.replaceChildren();
    mountMarkdownEditors(form); // détruit les éditeurs précédents
    return;
  }
  form.innerHTML = ed.fields(item) + `
    <div class="editor-actions">
      <button type="submit" class="primary">Enregistrer</button>
      ${item.id ? `<button type="button" class="danger" id="delete-item">Supprimer</button>` : ""}
      <span class="saved" id="saved" hidden>Enregistré ✓</span>
    </div>`;
  mountMarkdownEditors(form);
  $("#delete-item")?.addEventListener("click", async () => {
    await api("DELETE", `${ed.url}/${item.id}`);
    state.itemId = null;
    showEditor(null);
    await loadItems();
  });
}

$("#new-item").addEventListener("click", () => {
  state.itemId = null;
  showEditor({ ...EDITORS[state.view].blank });
  loadItems();
  $("#editor-form").querySelector("input").focus();
});

$("#editor-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const ed = EDITORS[state.view];
  syncMarkdownEditors();
  const data = { ...ed.read(e.target), universe_id: state.universeId };
  if (state.itemId) await api("PUT", `${ed.url}/${state.itemId}`, data);
  else state.itemId = (await api("POST", ed.url, data)).id;
  await loadItems();
  showEditor(items.find((it) => it.id === state.itemId));
  $("#saved").hidden = false;
});

loadUniverses().then(() => showView("mj"));
