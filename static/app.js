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
  const isChat = view === "mj" || view === "joueur";
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
    addMessage(m.role, m.text);
  }
  if (!conv.messages.length) {
    addMessage("notice", state.view === "mj"
      ? "Choisis les personnages concernés ci-dessus, puis pose une question, décris une situation de jeu ou demande des idées."
      : "Demande de l'aide pour créer ou vérifier une fiche, ou pose une question sur l'univers et les règles.");
  }
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
      <label>Contenu (Markdown)<textarea name="content" class="big">${escape(it.content)}</textarea></label>`,
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
      <label>Fiche (Markdown : caractéristiques, compétences, historique…)<textarea name="sheet" class="big">${escape(it.sheet)}</textarea></label>
      <label>Notes MJ (secrets, arcs prévus — invisibles en mode joueur)<textarea name="gm_notes" rows="6">${escape(it.gm_notes)}</textarea></label>`,
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
  if (!item) return;
  form.innerHTML = ed.fields(item) + `
    <div class="editor-actions">
      <button type="submit" class="primary">Enregistrer</button>
      ${item.id ? `<button type="button" class="danger" id="delete-item">Supprimer</button>` : ""}
      <span class="saved" id="saved" hidden>Enregistré ✓</span>
    </div>`;
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
  const data = { ...ed.read(e.target), universe_id: state.universeId };
  if (state.itemId) await api("PUT", `${ed.url}/${state.itemId}`, data);
  else state.itemId = (await api("POST", ed.url, data)).id;
  await loadItems();
  showEditor(items.find((it) => it.id === state.itemId));
  $("#saved").hidden = false;
});

loadUniverses().then(() => showView("mj"));
