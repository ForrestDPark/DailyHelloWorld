const $ = (s) => document.querySelector(s),
  W = 2400,
  H = 1800,
  O = { x: 1200, y: 900 },
  MEMO_LAYOUT_KEY = "memo-list-layout-v1";
let memos = [],
  categories = [],
  activeCategory = localStorage.getItem("memo-active-category-v1") || "all",
  current = null,
  dialogMode = null,
  view = { x: 0, y: 0, scale: 1 },
  pan = null,
  pinch = null,
  linkDrag = null,
  nodeDrag = null,
  selectedMapNode = null,
  lastNodeTap = { id: null, at: 0 },
  lastRootTap = 0,
  drawingTargetId = null,
  drawingState = { version: 1, width: 900, height: 600, strokes: [] },
  activeStroke = null;
const pointers = new Map(),
  collapsedNodes = new Set();
async function api(path, options = {}) {
  const r = await fetch(path, {
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        ...(options.headers || {}),
      },
      ...options,
    }),
    data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.detail || "요청을 처리하지 못했습니다");
  return data;
}
function esc(v = "") {
  return String(v).replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
}
function mediaMarkup(node) {
  const image = node.image_data ? `<img class="memo-card-image" data-media-node="${node.id}" alt="이미지 메모">` : "";
  const drawing = node.drawing_data ? `<canvas class="memo-card-drawing" data-drawing-node="${node.id}" width="900" height="600" aria-label="필기 메모"></canvas>` : "";
  return image + drawing;
}
function drawStrokes(canvas, value, responsive = false) {
  if (!canvas) return;
  let data;
  try { data = typeof value === "string" ? JSON.parse(value) : value; } catch { return; }
  const context = canvas.getContext("2d"), sourceWidth = data.width || 900, sourceHeight = data.height || 600;
  if (responsive) {
    const width = Math.max(280, Math.floor(canvas.getBoundingClientRect().width * devicePixelRatio));
    canvas.width = width; canvas.height = Math.floor(width * sourceHeight / sourceWidth);
  }
  context.clearRect(0, 0, canvas.width, canvas.height);
  context.lineCap = "round"; context.lineJoin = "round";
  const sx = canvas.width / sourceWidth, sy = canvas.height / sourceHeight;
  for (const stroke of data.strokes || []) {
    const points = stroke.points || []; if (!points.length) continue;
    context.beginPath(); context.strokeStyle = stroke.color || "#6f42d9";
    context.lineWidth = Math.max(1, (stroke.width || 6) * ((sx + sy) / 2));
    context.moveTo(points[0].x * sx, points[0].y * sy);
    for (let index = 1; index < points.length; index++) context.lineTo(points[index].x * sx, points[index].y * sy);
    if (points.length === 1) context.lineTo(points[0].x * sx + 0.01, points[0].y * sy + 0.01);
    context.stroke();
  }
}
function hydrateCardMedia() {
  for (const node of current?.nodes || []) {
    const image = document.querySelector(`[data-media-node="${node.id}"]`);
    if (image) image.src = node.image_data;
    drawStrokes(document.querySelector(`[data-drawing-node="${node.id}"]`), node.drawing_data, true);
  }
}
function renderColoredText(element, value = "") {
  element.replaceChildren();
  const text = String(value),
    pattern = /\[\[(red|blue|green|orange|purple)\]\]([\s\S]*?)\[\[\/\1\]\]/g;
  let cursor = 0;
  for (const match of text.matchAll(pattern)) {
    if (match.index > cursor)
      element.append(document.createTextNode(text.slice(cursor, match.index)));
    const accent = document.createElement("span");
    accent.className = `memo-accent memo-accent-${match[1]}`;
    accent.textContent = match[2];
    element.append(accent);
    cursor = match.index + match[0].length;
  }
  if (cursor < text.length)
    element.append(document.createTextNode(text.slice(cursor)));
}
const FORMAT_TOKEN_RE = /\[\[(?:\/?(?:b|i|u|s|red|blue|green|orange|purple|color|bg|comment)(?::[^\]]*)?)\]\]/gi;
function richMemoHtml(value = "") {
  const text = String(value);
  let html = "", cursor = 0;
  for (const match of text.matchAll(FORMAT_TOKEN_RE)) {
    html += esc(text.slice(cursor, match.index));
    const token = match[0].slice(2, -2), closing = token.startsWith("/"),
      [rawName, rawValue = ""] = token.replace(/^\//, "").split(":", 2),
      name = rawName.toLowerCase();
    if (closing) html += "</span>";
    else if (["red", "blue", "green", "orange", "purple"].includes(name))
      html += `<span class="memo-accent memo-accent-${name}">`;
    else if (["b", "i", "u", "s"].includes(name)) html += `<span class="memo-format memo-format-${name}">`;
    else if ((name === "color" || name === "bg") && /^#[0-9a-f]{6}$/i.test(rawValue))
      html += `<span class="memo-format" style="${name === "color" ? "color" : "background-color"}:${rawValue}">`;
    else if (name === "comment") {
      let comment = "";
      try { comment = decodeURIComponent(rawValue); } catch {}
      html += `<span class="memo-comment" data-comment="${esc(comment)}" tabindex="0">`;
    }
    cursor = match.index + match[0].length;
  }
  return html + esc(text.slice(cursor));
}
function sourceIndexAtVisibleOffset(source, wanted) {
  let sourceIndex = 0, visible = 0;
  for (const match of String(source).matchAll(FORMAT_TOKEN_RE)) {
    const plainLength = match.index - sourceIndex;
    if (visible + plainLength >= wanted) return sourceIndex + wanted - visible;
    visible += plainLength;
    sourceIndex = match.index + match[0].length;
  }
  return Math.min(String(source).length, sourceIndex + Math.max(0, wanted - visible));
}
const MEMO_NODE_COLORS = [
  "#ef6a78",
  "#ee9b42",
  "#4eae72",
  "#3a9cc0",
  "#5878d8",
  "#9a69cf",
];
function memoNodeColor(node, index = 0) {
  return MEMO_NODE_COLORS[
    Math.abs(Number(node?.id) || index) % MEMO_NODE_COLORS.length
  ];
}
function cardWidthStyle(value) {
  const width = Number(value);
  const resolved = Number.isFinite(width) && width > 0 ? width : 620;
  return `width:${Math.max(220, Math.min(720, resolved))}px;`;
}
function toast(v) {
  const e = $("#toast");
  e.textContent = v;
  e.classList.remove("hidden");
  setTimeout(() => e.classList.add("hidden"), 1800);
}
async function load(id) {
  selectedMapNode = null;
  $("#node-mobile-actions")?.classList.add("hidden");
  [memos, categories] = await Promise.all([
    api("/api/me/memos"),
    api("/api/me/memo-categories"),
  ]);
  if (!(["all", "none"].includes(activeCategory)) && !categories.some((item) => String(item.id) === String(activeCategory))) activeCategory = "all";
  renderCategories();
  renderList();
  const wanted = id || Number(new URLSearchParams(location.search).get("memo"));
  if (wanted) selectMemo(wanted);
  else if (current) selectMemo(current.id);
  else {
    $("#editor").classList.add("hidden");
    $("#empty").classList.remove("hidden");
    $("#empty").innerHTML = memos.length
      ? "<b>메모를 선택하세요</b><p>제목을 누르면 팝오버에서 내용을 확인할 수 있어요.</p>"
      : "<b>첫 메모를 만들어보세요</b><p>채팅 메시지를 저장하거나 새 메모를 직접 작성할 수 있어요.</p>";
  }
}
function memoDate(value) {
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? "날짜 정보 없음"
    : new Intl.DateTimeFormat("ko-KR", {
        year: "numeric",
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      }).format(date);
}
function setMemoLayout(mode) {
  const next = mode === "list" ? "list" : "grid",
    list = $("#memo-list"),
    button = $("#memo-layout");
  list.classList.toggle("list-view", next === "list");
  list.classList.toggle("grid-view", next === "grid");
  button.dataset.layout = next;
  button.textContent = next === "grid" ? "☰ 리스트" : "▦ 격자";
  button.setAttribute(
    "aria-label",
    next === "grid" ? "리스트 보기로 전환" : "격자 보기로 전환",
  );
  try {
    localStorage.setItem(MEMO_LAYOUT_KEY, next);
  } catch {}
}
function renderList() {
  const q = $("#search").value.trim().toLowerCase(),
    list = memos.filter((m) => {
      const categoryIds = memoCategoryIds(m);
      const categoryMatches = activeCategory === "all"
        || (activeCategory === "none" ? categoryIds.length === 0 : categoryIds.some((id) => String(id) === String(activeCategory)));
      return categoryMatches && `${m.title} ${m.note} ${m.source_content}`.toLowerCase().includes(q);
    });
  $("#memo-list").innerHTML = list.length
    ? list
        .map(
          (m) =>
            `<article class="memo-list-item"><button type="button" data-id="${m.id}" class="memo-open ${current?.id === m.id ? "active" : ""}">${memoCategoryIds(m).length ? `<span class="memo-category-badges">${memoCategoryIds(m).map((id) => `<span class="memo-category-badge">${esc(categories.find((item) => item.id === id)?.name || "삭제된 키워드")}</span>`).join("")}</span>` : ""}<strong>${esc((m.title || "제목 없는 메모").split(/\r?\n/, 1)[0])}</strong><span>${esc(memoDate(m.updated_at || m.created_at))}</span></button><button type="button" class="memo-card-delete danger" data-delete-memo="${m.id}" aria-label="${esc((m.title || "제목 없는 메모").split(/\r?\n/, 1)[0])} 삭제">삭제</button></article>`,
        )
        .join("")
    : `<p>${activeCategory === "all" ? "저장된 메모가 없습니다." : "이 키워드에 저장된 메모가 없습니다."}</p>`;
  $("#memo-list")
    .querySelectorAll("[data-id]")
    .forEach((b) => (b.onclick = () => openMemoPreview(+b.dataset.id)));
  $("#memo-list")
    .querySelectorAll("[data-delete-memo]")
    .forEach((button) => (button.onclick = async (event) => {
      event.stopPropagation();
      await removeMemoDocument(+button.dataset.deleteMemo);
    }));
}

async function removeMemoDocument(id) {
  const memo = memos.find((item) => item.id === id);
  if (!memo) return;
  const title = (memo.title || "제목 없는 메모").split(/\r?\n/, 1)[0];
  if (!confirm(`‘${title}’ 메모와 연결된 모든 가지를 삭제할까요?`)) return;
  try {
    await api(`/api/me/memos/${id}`, { method: "DELETE" });
    if (current?.id === id) {
      current = null;
      history.replaceState(null, "", "/memo/");
      $("#editor").classList.add("hidden");
      $("#empty").classList.remove("hidden");
    }
    if ($("#memo-preview-dialog").open) $("#memo-preview-dialog").close();
    await load();
    toast("메모를 삭제했습니다");
  } catch (error) {
    alert(error.message);
  }
}
function renderCategories() {
  const unclassified = memos.filter((memo) => memoCategoryIds(memo).length === 0).length;
  const tabs = [
    {id: "all", name: "전체", count: memos.length},
    {id: "none", name: "미분류", count: unclassified},
    ...categories.map((item) => ({id: String(item.id), name: item.name, count: Number(item.memo_count || 0)})),
  ];
  $("#category-tabs").innerHTML = tabs.map((item) => `<button type="button" data-category="${item.id}" class="${String(activeCategory) === item.id ? "active" : ""}">${esc(item.name)} <small>${item.count}</small></button>`).join("");
  $("#category-tabs").querySelectorAll("button").forEach((button) => button.onclick = () => {
    activeCategory = button.dataset.category;
    localStorage.setItem("memo-active-category-v1", activeCategory);
    renderCategories(); renderList();
  });
}
function renderCategoryManager() {
  $("#category-manager-list").innerHTML = categories.length
    ? categories.map((item) => `<div class="category-manager-row" data-category-row="${item.id}"><input maxlength="40" value="${esc(item.name)}" aria-label="키워드 이름"><button type="button" data-save-category="${item.id}">수정</button><button type="button" class="danger" data-delete-category="${item.id}">삭제</button></div>`).join("")
    : '<p>아직 만든 키워드가 없습니다.</p>';
}
function memoCategoryIds(memo) {
  if (Array.isArray(memo?.category_ids)) return memo.category_ids.map(Number).filter(Number.isFinite);
  return memo?.category_id == null ? [] : [Number(memo.category_id)];
}
function fillMemoCategorySelect(selected = []) {
  const selectedIds = new Set((Array.isArray(selected) ? selected : [selected]).map(Number));
  $("#memo-edit-categories").innerHTML = categories.length
    ? categories.map((item) => `<label class="memo-category-choice"><input type="checkbox" value="${item.id}" ${selectedIds.has(Number(item.id)) ? "checked" : ""}><span>${esc(item.name)}</span></label>`).join("")
    : '<p>키워드 관리에서 먼저 키워드를 만들어보세요.</p>';
}
function openMemoPreview(id) {
  const memo = memos.find((item) => item.id === id);
  if (!memo) return;
  $("#preview-title").textContent = (memo.title || "제목 없는 메모").split(
    /\r?\n/,
    1,
  )[0];
  $("#preview-date").textContent =
    `최근 기록 ${memoDate(memo.updated_at || memo.created_at)}`;
  const sections = [];
  if (memo.source_content) sections.push(`채팅 원문\n${memo.source_content}`);
  if (memo.note)
    sections.push(`${memo.source_content ? "내 메모\n" : ""}${memo.note}`);
  renderColoredText(
    $("#preview-content"),
    sections.join("\n\n") || "기록된 내용이 없습니다.",
  );
  $("#preview-open").dataset.id = String(id);
  $("#preview-edit").dataset.id = String(id);
  $("#memo-preview-dialog").showModal();
}
function openRootEditor(id, focusNote = false) {
  selectMemo(id);
  if (focusNote) openMemoEditDialog();
}
function openMemoEditDialog() {
  if (!current) return;
  syncMemoEditorViewport();
  $("#memo-edit-note").value = current.note || current.source_content || "";
  fillMemoCategorySelect(memoCategoryIds(current));
  $("#memo-edit-dialog").showModal();
  // 제목을 따로 입력하지 않고 내용부터 바로 편집한다. iOS에서는 dialog가
  // 열린 다음 프레임에 포커스해야 visualViewport 높이가 안정적으로 반영된다.
  requestAnimationFrame(() => {
    syncMemoEditorViewport();
    $("#memo-edit-note").focus({ preventScroll: true });
  });
}
function memoTitleFromContent(note, fallback = "새 메모") {
  const firstLine = String(note || "")
    .replace(/\[\[\/?(?:b|i|u|s)\]\]/gi, "")
    .replace(/\[\[(?:color|bg):[^\]]+\]\]|\[\[\/(?:color|bg)\]\]/gi, "")
    .split(/\r?\n/)
    .map((line) => line.trim())
    .find(Boolean);
  return (firstLine || fallback || "새 메모").slice(0, 160);
}
function syncMemoEditorViewport() {
  const viewport = window.visualViewport;
  document.documentElement.style.setProperty(
    "--memo-editor-height",
    `${Math.round(viewport?.height || window.innerHeight)}px`,
  );
  document.documentElement.style.setProperty(
    "--memo-editor-top",
    `${Math.round(viewport?.offsetTop || 0)}px`,
  );
}
async function pasteIntoMemoField(target) {
  if (!target) return;
  try {
    if (!navigator.clipboard?.readText) throw new Error("이 브라우저에서는 클립보드를 직접 읽을 수 없습니다");
    const text = await navigator.clipboard.readText();
    if (!text) return toast("클립보드가 비어 있습니다");
    const start = Number.isFinite(target.selectionStart) ? target.selectionStart : target.value.length;
    const end = Number.isFinite(target.selectionEnd) ? target.selectionEnd : start;
    target.setRangeText(text, start, end, "end");
    target.dispatchEvent(new Event("input", {bubbles: true}));
    target.focus({preventScroll: true});
    toast("클립보드 내용을 붙여넣었습니다");
  } catch (error) {
    target.focus({preventScroll: true});
    alert("붙여넣기 권한을 사용할 수 없습니다. 입력칸을 길게 눌러 ‘붙여넣기’를 선택해 주세요.");
  }
}
document.querySelectorAll("[data-paste-target]").forEach((button) => {
  button.onclick = () => pasteIntoMemoField(document.getElementById(button.dataset.pasteTarget));
});
window.visualViewport?.addEventListener("resize", syncMemoEditorViewport);
window.addEventListener("orientationchange", syncMemoEditorViewport);
function selectMemo(id) {
  current = memos.find((m) => m.id === id);
  if (!current) return;
  history.replaceState(null, "", `?memo=${id}`);
  $("#empty").classList.add("hidden");
  $("#editor").classList.remove("hidden");
  $("#memo-title").value = current.title;
  $("#memo-note").value = current.note;
  const source = !!current.source_message_id;
  $("#source-card").classList.toggle("hidden", !source);
  $("#source-label").textContent = source
    ? `채팅방 ${current.source_room_id || ""}`
    : "직접 작성한 메모";
  $("#source-sender").textContent = current.source_sender;
  renderColoredText($("#source-content"), current.source_content);
  $("#source-content").classList.add("collapsed");
  $("#source-toggle").textContent = "원문 펼치기";
  $("#source-toggle").setAttribute("aria-expanded", "false");
  if (source) {
    $("#source-link").href = `/#room=${encodeURIComponent(current.source_room_id)}&message=${encodeURIComponent(current.source_message_id)}`;
  }
  renderMap();
  renderList();
  requestAnimationFrame(fitMap);
}
function layout() {
  const children = new Map(),
    positions = new Map([[0, { ...O }]]);
  current.nodes.forEach((n) => {
    const k = n.parent_id ?? 0;
    if (!children.has(k)) children.set(k, []);
    children.get(k).push(n);
  });
  const roots = children.get(0) || [];
  roots.forEach((n, i) =>
    place(n, -Math.PI / 2 + (Math.PI * 2 * i) / Math.max(1, roots.length), 1),
  );
  function place(n, a, d) {
    const p = positions.get(n.parent_id ?? 0) || O,
      dist = d === 1 ? 310 : Math.max(205, 265 - d * 12),
      saved =
        Number.isFinite(Number(n.position_x)) &&
        Number.isFinite(Number(n.position_y));
    positions.set(
      n.id,
      saved
        ? { x: Number(n.position_x), y: Number(n.position_y) }
        : { x: p.x + Math.cos(a) * dist, y: p.y + Math.sin(a) * dist },
    );
    const list = children.get(n.id) || [],
      spread = Math.min(1.05, 0.32 + list.length * 0.14);
    list.forEach((c, i) =>
      place(
        c,
        a +
          (list.length === 1
            ? 0
            : -spread / 2 + (spread * i) / (list.length - 1)),
        d + 1,
      ),
    );
  }
  return positions;
}
function renderMap() {
  const pos = layout(),
    rootText = current.note || current.source_content || "";
  $("#memo-tree").innerHTML =
    `<article class="node-card root expanded${selectedMapNode === "root" ? " selected" : ""}" style="--node-accent:#ee9b42;${cardWidthStyle(current.card_width)}left:${O.x}px;top:${O.y}px"><small>ROOT NOTE</small><h3>${esc(current.title)}</h3><textarea class="node-inline-editor root-inline-editor" data-inline-root="1" maxlength="12000" placeholder="내용을 입력하세요">${esc(rootText)}</textarea><div class="node-actions"><button data-toggle-root aria-label="내용 접기">−</button><button class="node-inline-save" data-save-root hidden>변경내용 저장</button><button class="node-resize-handle" data-resize-root aria-label="메모 폭 조절" title="좌우로 밀어 폭 조절">↔</button><button class="node-link-handle" data-link-root aria-label="드래그해 새 메모 연결">＋</button></div></article>` +
    current.nodes
      .map((n, index) => {
        const p = pos.get(n.id),
          collapsed = collapsedNodes.has(n.id),
          color = memoNodeColor(n, index);
        const empty = !String(n.content || "").trim();
        return `<article class="node-card ${collapsed ? "collapsed" : "expanded"}${empty ? " node-empty" : ""}${selectedMapNode === n.id ? " selected" : ""}" data-node-id="${n.id}" style="--node-accent:${color};${cardWidthStyle(n.card_width)}left:${p.x}px;top:${p.y}px">${mediaMarkup(n)}<textarea class="node-inline-editor" data-inline-node="${n.id}" maxlength="6000" placeholder="${n.image_data || n.drawing_data ? "설명을 덧붙이세요" : "내용을 입력하세요"}">${esc(n.content || "")}</textarea><div class="node-actions"><button data-toggle="${n.id}" aria-label="${collapsed ? "내용 펼치기" : "내용 접기"}">${collapsed ? "＋" : "−"}</button><button class="node-inline-save" data-save-node="${n.id}" hidden>변경내용 저장</button>${n.drawing_data ? `<button data-edit-drawing="${n.id}">필기</button>` : ""}<button data-delete="${n.id}" class="danger">삭제</button><button class="node-resize-handle" data-resize="${n.id}" aria-label="메모 폭 조절" title="좌우로 밀어 폭 조절">↔</button><button class="node-link-handle" data-link="${n.id}" aria-label="드래그해 새 메모 연결">＋</button></div></article>`;
      })
      .join("");
  $("#mindmap-lines").innerHTML = current.nodes
    .map((n, index) => {
      const a = pos.get(n.parent_id ?? 0) || O,
        b = pos.get(n.id),
        dx = b.x - a.x;
      return `<path style="--branch-color:${memoNodeColor(n, index)}" d="M ${a.x} ${a.y} C ${a.x + dx * 0.45} ${a.y}, ${b.x - dx * 0.35} ${b.y}, ${b.x} ${b.y}"/>`;
    })
    .join("");
  $("[data-toggle-root]").onclick = (e) => {
    e.currentTarget.closest(".node-card").classList.toggle("root-collapsed");
    e.currentTarget.textContent =
      e.currentTarget.textContent === "−" ? "＋" : "−";
  };
  $("#memo-tree")
    .querySelectorAll("[data-toggle]")
    .forEach(
      (b) =>
        (b.onclick = () => {
          const id = +b.dataset.toggle;
          if (collapsedNodes.has(id)) collapsedNodes.delete(id);
          else collapsedNodes.add(id);
          renderMap();
        }),
    );
  $("#memo-tree")
    .querySelectorAll("[data-delete]")
    .forEach((b) => (b.onclick = () => removeNode(+b.dataset.delete)));
  const rootCard = $("#memo-tree .node-card.root");
  let rootPointerStart = null;
  rootCard.onpointerdown = (event) => {
    if (event.target.closest("button,textarea,input,select")) return;
    rootPointerStart = { x: event.clientX, y: event.clientY };
  };
  rootCard.onpointerup = (event) => {
    if (!rootPointerStart || event.target.closest("button,textarea,input,select")) return;
    const moved = Math.hypot(
      event.clientX - rootPointerStart.x,
      event.clientY - rootPointerStart.y,
    );
    rootPointerStart = null;
    if (moved <= 10) selectMapNode("root");
  };
  bindInlineEditors();
  hydrateCardMedia();
  $("#memo-tree").querySelectorAll("[data-edit-drawing]").forEach((button) => button.onclick = () => openDrawing(Number(button.dataset.editDrawing)));
  $("[data-resize-root]").addEventListener("pointerdown", (event) =>
    startCardResize(event, rootCard, null),
  );
  $("#memo-tree")
    .querySelectorAll("[data-resize]")
    .forEach((button) => {
      const id = Number(button.dataset.resize);
      button.addEventListener("pointerdown", (event) =>
        startCardResize(
          event,
          button.closest(".node-card"),
          current.nodes.find((node) => node.id === id),
        ),
      );
    });
  $("[data-link-root]").addEventListener("pointerdown", (e) =>
    startLinkDrag(e, null, O),
  );
  $("#memo-tree")
    .querySelectorAll("[data-link]")
    .forEach((b) => {
      const id = +b.dataset.link;
      b.addEventListener("pointerdown", (e) =>
        startLinkDrag(e, id, pos.get(id)),
      );
    });
}
function selectMapNode(id) {
  selectedMapNode = id;
  const bar = $("#node-mobile-actions"), root = id === "root",
    node = root ? null : current?.nodes.find((item) => item.id === id);
  if (!root && !node) return;
  $("#memo-tree").querySelectorAll(".node-card.selected").forEach((card) => card.classList.remove("selected"));
  const card = root ? $("#memo-tree .node-card.root") : $(`#memo-tree .node-card[data-node-id="${id}"]`);
  card?.classList.add("selected");
  $("#node-mobile-label").textContent = root ? "기본 메모 선택됨" : "파생 메모 선택됨";
  $("#node-mobile-delete").hidden = root;
  $("#node-mobile-collapse").textContent = root
    ? (card?.classList.contains("root-collapsed") ? "펼치기" : "접기")
    : (collapsedNodes.has(id) ? "펼치기" : "접기");
  bar.classList.remove("hidden");
}
function clearMapNodeSelection() {
  selectedMapNode = null;
  $("#memo-tree")?.querySelectorAll(".node-card.selected").forEach((card) => card.classList.remove("selected"));
  $("#node-mobile-actions").classList.add("hidden");
}
function applyView() {
  $("#mindmap-stage").style.transform =
    `translate(${view.x}px,${view.y}px) scale(${view.scale})`;
  $("#zoom-level").textContent = `${Math.round(view.scale * 100)}%`;
}
function zoom(scale, x, y) {
  const r = $("#mindmap-viewport").getBoundingClientRect(),
    px = (x ?? r.left + r.width / 2) - r.left,
    py = (y ?? r.top + r.height / 2) - r.top,
    wx = (px - view.x) / view.scale,
    wy = (py - view.y) / view.scale;
  view.scale = Math.min(2.4, Math.max(0.28, scale));
  view.x = px - wx * view.scale;
  view.y = py - wy * view.scale;
  applyView();
}
function fitMap() {
  if (!current) return;
  const v = $("#mindmap-viewport"),
    cards = [...$("#memo-tree").querySelectorAll(".node-card")],
    xs = cards.map((c) => parseFloat(c.style.left)),
    ys = cards.map((c) => parseFloat(c.style.top)),
    minX = Math.min(...xs) - 180,
    maxX = Math.max(...xs) + 180,
    minY = Math.min(...ys) - 130,
    maxY = Math.max(...ys) + 130;
  view.scale = Math.max(
    0.28,
    Math.min(
      1,
      (v.clientWidth - 40) / (maxX - minX),
      (v.clientHeight - 40) / (maxY - minY),
    ),
  );
  view.x = v.clientWidth / 2 - ((minX + maxX) / 2) * view.scale;
  view.y = v.clientHeight / 2 - ((minY + maxY) / 2) * view.scale;
  applyView();
}
function setMindmapFullscreen(enabled) {
  const viewport = $("#mindmap-viewport"),
    button = $("#mindmap-fullscreen"),
    active = Boolean(enabled);
  viewport.classList.toggle("fullscreen-mode", active);
  document.body.classList.toggle("mindmap-fullscreen-open", active);
  button.textContent = active ? "×" : "⛶";
  button.setAttribute(
    "aria-label",
    active ? "전체 화면 닫기" : "생각 지도 전체 화면",
  );
  button.title = active ? "전체 화면 닫기" : "전체 화면";
  requestAnimationFrame(() => requestAnimationFrame(fitMap));
}
function pointerWorld(event) {
  const rect = $("#mindmap-viewport").getBoundingClientRect();
  return {
    x: Math.max(
      100,
      Math.min(2300, (event.clientX - rect.left - view.x) / view.scale),
    ),
    y: Math.max(
      80,
      Math.min(1720, (event.clientY - rect.top - view.y) / view.scale),
    ),
  };
}
function redrawMindmapLines() {
  const pos = layout(),
    paths = $("#mindmap-lines").querySelectorAll("path");
  current.nodes.forEach((n, index) => {
    const a = pos.get(n.parent_id ?? 0) || O,
      b = pos.get(n.id),
      dx = b.x - a.x;
    paths[index]?.setAttribute(
      "d",
      `M ${a.x} ${a.y} C ${a.x + dx * 0.45} ${a.y}, ${b.x - dx * 0.35} ${b.y}, ${b.x} ${b.y}`,
    );
  });
}
function resizeInlineEditor(editor) {
  editor.style.height = "auto";
  editor.style.height = `${Math.max(84, editor.scrollHeight + 2)}px`;
}
function bindInlineEditors() {
  const rootEditor = document.querySelector("[data-inline-root]"),
    rootSave = document.querySelector("[data-save-root]"),
    rootInitial = current.note || current.source_content || "";
  if (rootEditor && rootSave) {
    rootEditor.value = rootInitial;
    resizeInlineEditor(rootEditor);
    rootEditor.addEventListener("input", () => {
      resizeInlineEditor(rootEditor);
      rootSave.hidden = rootEditor.value === rootInitial;
    });
    rootEditor.addEventListener("focus", () => selectMapNode("root"));
    rootSave.onclick = async () => {
      const note = rootEditor.value.trim(),
        title = memoTitleFromContent(note, current.title);
      await api(`/api/me/memos/${current.id}`, {
        method: "PUT",
        body: JSON.stringify({ title, note }),
      });
      current.note = note;
      current.title = title;
      const listed = memos.find((memo) => memo.id === current.id);
      if (listed) Object.assign(listed, { note, title });
      renderList();
      renderMap();
      selectMapNode("root");
      toast("변경내용을 저장했습니다");
    };
  }
  document.querySelectorAll("[data-inline-node]").forEach((editor) => {
    const id = Number(editor.dataset.inlineNode),
      node = current.nodes.find((item) => item.id === id),
      save = document.querySelector(`[data-save-node="${id}"]`),
      initial = node?.content || "";
    if (!node || !save) return;
    editor.value = initial;
    resizeInlineEditor(editor);
    editor.addEventListener("input", () => {
      resizeInlineEditor(editor);
      save.hidden = editor.value === initial;
    });
    editor.addEventListener("focus", () => selectMapNode(id));
    save.onclick = async () => {
      const content = editor.value.trim();
      await api(`/api/me/memo-nodes/${id}`, {
        method: "PUT",
        body: JSON.stringify({ content }),
      });
      node.content = content;
      renderMap();
      selectMapNode(id);
      toast("변경내용을 저장했습니다");
    };
  });
}
function prepareNodeDrag(event, card) {
  if (event.target.closest(".memo-comment,textarea,input,select,[contenteditable='true']")) return;
  const id = Number(card.dataset.nodeId),
    node = current.nodes.find((item) => item.id === id);
  if (!node) return;
  clearRichSelectionUI();
  event.preventDefault();
  event.stopPropagation();
  card.setPointerCapture?.(event.pointerId);
  const origin = { x: event.clientX, y: event.clientY },
    saved = layout().get(id),
    state = {
      id,
      node,
      card,
      pointerId: event.pointerId,
      active: false,
      cancelled: false,
      last: saved,
    };
  nodeDrag = state;
  const timer = setTimeout(() => {
    if (nodeDrag !== state || state.cancelled) return;
    state.active = true;
    card.classList.add("dragging");
    navigator.vibrate?.(25);
    toast("메모를 원하는 위치로 옮기세요");
  }, 380);
  const move = (moveEvent) => {
    if (nodeDrag !== state || moveEvent.pointerId !== state.pointerId) return;
    const distance = Math.hypot(
      moveEvent.clientX - origin.x,
      moveEvent.clientY - origin.y,
    );
    if (!state.active) {
      if (distance > 10) {
        state.cancelled = true;
        clearTimeout(timer);
      }
      return;
    }
    moveEvent.preventDefault();
    const point = pointerWorld(moveEvent);
    state.last = point;
    node.position_x = point.x;
    node.position_y = point.y;
    card.style.left = `${point.x}px`;
    card.style.top = `${point.y}px`;
    redrawMindmapLines();
  };
  const end = async (endEvent) => {
    if (nodeDrag !== state || endEvent.pointerId !== state.pointerId) return;
    clearTimeout(timer);
    window.removeEventListener("pointermove", move);
    window.removeEventListener("pointerup", end);
    window.removeEventListener("pointercancel", end);
    card.classList.remove("dragging");
    nodeDrag = null;
    if (!state.active) {
      if (!state.cancelled) {
        selectMapNode(id);
        const now = Date.now();
        if (lastNodeTap.id === id && now - lastNodeTap.at < 430) {
          lastNodeTap = { id: null, at: 0 };
          card.querySelector("[data-inline-node]")?.focus();
        } else {
          lastNodeTap = { id, at: now };
        }
      }
      return;
    }
    try {
      await api(`/api/me/memo-nodes/${id}`, {
        method: "PUT",
        body: JSON.stringify({
          content: node.content,
          position_x: state.last.x,
          position_y: state.last.y,
        }),
      });
      toast("메모 위치를 저장했습니다");
    } catch (error) {
      node.position_x = saved.x;
      node.position_y = saved.y;
      renderMap();
      toast(error.message);
    }
  };
  window.addEventListener("pointermove", move, { passive: false });
  window.addEventListener("pointerup", end);
  window.addEventListener("pointercancel", end);
}

let richSelection = null;
function textOffsetWithin(container, node, offset) {
  const range = document.createRange();
  range.selectNodeContents(container);
  try { range.setEnd(node, offset); } catch { return 0; }
  return range.toString().length;
}
function hideSelectionToolbar() {
  $("#selection-toolbar").classList.add("hidden");
}
function clearRichSelectionUI() {
  richSelection = null;
  hideSelectionToolbar();
  getSelection()?.removeAllRanges();
}
function captureRichSelection() {
  const selection = getSelection();
  if (!selection || selection.rangeCount === 0 || selection.isCollapsed) {
    richSelection = null;
    hideSelectionToolbar();
    return;
  }
  const range = selection.getRangeAt(0),
    content = (range.commonAncestorContainer.nodeType === Node.TEXT_NODE
      ? range.commonAncestorContainer.parentElement
      : range.commonAncestorContainer)?.closest?.("p[data-rich-root],p[data-rich-node]");
  if (!content || !content.contains(range.startContainer) || !content.contains(range.endContainer)) return;
  const start = textOffsetWithin(content, range.startContainer, range.startOffset),
    end = textOffsetWithin(content, range.endContainer, range.endOffset);
  if (end <= start) return;
  const rect = range.getBoundingClientRect(), toolbar = $("#selection-toolbar");
  richSelection = {
    root: content.hasAttribute("data-rich-root"),
    nodeId: Number(content.dataset.richNode || 0), start, end,
  };
  toolbar.classList.remove("hidden");
  const box = toolbar.getBoundingClientRect();
  toolbar.style.left = `${Math.max(8, Math.min(innerWidth - box.width - 8, rect.left + rect.width / 2 - box.width / 2))}px`;
  toolbar.style.top = `${Math.max(8, rect.top - box.height - 10)}px`;
}
async function applyRichFormat(openTag, closeTag, clear = false) {
  if (!richSelection || !current) return;
  const node = richSelection.root ? null : current.nodes.find((item) => item.id === richSelection.nodeId),
    source = richSelection.root ? (current.note || current.source_content || "") : node?.content;
  if (source == null) return;
  const start = sourceIndexAtVisibleOffset(source, richSelection.start),
    end = sourceIndexAtVisibleOffset(source, richSelection.end);
  let selected = source.slice(start, end), updated;
  if (clear) selected = selected.replace(FORMAT_TOKEN_RE, "");
  updated = source.slice(0, start) + (clear ? selected : openTag + selected + closeTag) + source.slice(end);
  try {
    if (richSelection.root) {
      current.note = updated;
      $("#memo-note").value = updated;
      await api(`/api/me/memos/${current.id}`, { method: "PUT", body: JSON.stringify({ title: $("#memo-title").value || current.title, note: updated }) });
    } else {
      node.content = updated;
      await api(`/api/me/memo-nodes/${node.id}`, { method: "PUT", body: JSON.stringify({ content: updated }) });
    }
    getSelection()?.removeAllRanges();
    richSelection = null;
    hideSelectionToolbar();
    renderMap();
    toast("선택한 글자에 서식을 적용했습니다");
  } catch (error) { toast(error.message); }
}
document.addEventListener("selectionchange", () => {
  clearTimeout(captureRichSelection.timer);
  captureRichSelection.timer = setTimeout(() => {
    if (!$("#selection-toolbar").matches(":hover")) captureRichSelection();
  }, 90);
});
document.addEventListener("pointerdown", (event) => {
  if (event.target.closest("#selection-toolbar,.format-color-dialog,.memo-comment")) return;
  // iOS의 textarea 선택 손잡이도 pointerdown을 발생시킨다. 입력 요소에서
  // 전역 Selection을 지우면 기본 오려두기·복사 범위 확장이 중단된다.
  if (event.target.closest("input,textarea,select,[contenteditable='true']")) return;
  if (!event.target.closest("p[data-rich-root],p[data-rich-node]")) clearRichSelectionUI();
});
$("#selection-toolbar").querySelectorAll("[data-format]").forEach((button) => {
  button.onclick = () => applyRichFormat(`[[${button.dataset.format}]]`, `[[/${button.dataset.format}]]`);
});
let pendingColorMode = "color";
function openFormatColorDialog(mode) {
  if (!richSelection) return toast("먼저 색을 바꿀 글자를 선택해주세요");
  pendingColorMode = mode;
  const picker = $("#format-color-picker"), dialog = $("#format-color-dialog");
  picker.value = mode === "color" ? "#e45775" : "#fff19a";
  $("#format-color-title").textContent = mode === "color" ? "글자색" : "배경색";
  updateFormatColorPreview();
  hideSelectionToolbar();
  dialog.showModal();
}
function updateFormatColorPreview() {
  const value = $("#format-color-picker").value, preview = $("#format-color-preview");
  preview.style.color = pendingColorMode === "color" ? value : "";
  preview.style.backgroundColor = pendingColorMode === "background" ? value : "";
}
$("#format-color-button").onclick = () => openFormatColorDialog("color");
$("#format-background-button").onclick = () => openFormatColorDialog("background");
$("#format-color-picker").oninput = updateFormatColorPreview;
$("#format-color-dialog").querySelectorAll("[data-color]").forEach((button) => {
  button.onclick = () => {
    $("#format-color-picker").value = button.dataset.color;
    updateFormatColorPreview();
  };
});
$("#format-color-apply").onclick = async () => {
  const value = $("#format-color-picker").value;
  $("#format-color-dialog").close();
  await applyRichFormat(
    pendingColorMode === "color" ? `[[color:${value}]]` : `[[bg:${value}]]`,
    pendingColorMode === "color" ? "[[/color]]" : "[[/bg]]",
  );
};
$("#format-clear").onclick = () => applyRichFormat("", "", true);
$("#format-comment").onclick = () => {
  const comment = prompt("선택한 문장에 남길 코멘트를 입력하세요.");
  if (comment?.trim()) applyRichFormat(`[[comment:${encodeURIComponent(comment.trim())}]]`, "[[/comment]]");
};
document.addEventListener("click", (event) => {
  const marked = event.target.closest(".memo-comment"), popover = $("#comment-popover");
  if (!marked) {
    if (!event.target.closest("#comment-popover")) popover.classList.add("hidden");
    return;
  }
  event.stopPropagation();
  popover.querySelector("p").textContent = marked.dataset.comment || "코멘트가 없습니다";
  popover.classList.remove("hidden");
  const rect = marked.getBoundingClientRect(), box = popover.getBoundingClientRect();
  popover.style.left = `${Math.max(10, Math.min(innerWidth - box.width - 10, rect.left))}px`;
  popover.style.top = `${Math.min(innerHeight - box.height - 10, rect.bottom + 8)}px`;
});
$("#comment-popover button").onclick = () => $("#comment-popover").classList.add("hidden");
function startCardResize(event, card, node) {
  event.preventDefault();
  event.stopPropagation();
  const startX = event.clientX,
    startWidth = card.getBoundingClientRect().width / view.scale,
    pointerId = event.pointerId;
  card.classList.add("resizing");
  const move = (moveEvent) => {
    if (moveEvent.pointerId !== pointerId) return;
    moveEvent.preventDefault();
    const width = Math.max(
      220,
      Math.min(720, startWidth + (moveEvent.clientX - startX) / view.scale),
    );
    card.style.width = `${width}px`;
    card.dataset.pendingWidth = String(Math.round(width));
  };
  const end = async (endEvent) => {
    if (endEvent.pointerId !== pointerId) return;
    window.removeEventListener("pointermove", move);
    window.removeEventListener("pointerup", end);
    window.removeEventListener("pointercancel", end);
    card.classList.remove("resizing");
    const width = Number(card.dataset.pendingWidth || Math.round(startWidth));
    delete card.dataset.pendingWidth;
    try {
      if (node) {
        node.card_width = width;
        await api(`/api/me/memo-nodes/${node.id}`, {
          method: "PUT",
          body: JSON.stringify({ content: node.content, card_width: width }),
        });
      } else {
        current.card_width = width;
        await api(`/api/me/memos/${current.id}`, {
          method: "PUT",
          body: JSON.stringify({
            title: $("#memo-title").value,
            note: $("#memo-note").value,
            card_width: width,
          }),
        });
      }
      toast(`메모 폭을 ${width}px로 저장했습니다`);
    } catch (error) {
      card.style.width = `${startWidth}px`;
      toast(error.message);
    }
  };
  window.addEventListener("pointermove", move, { passive: false });
  window.addEventListener("pointerup", end);
  window.addEventListener("pointercancel", end);
}
function startLinkDrag(event, parentId, start) {
  event.preventDefault();
  event.stopPropagation();
  const stage = $("#mindmap-stage"),
    ghost = document.createElement("div"),
    path = document.createElementNS("http://www.w3.org/2000/svg", "path");
  ghost.className = "node-card link-ghost";
  ghost.textContent = "새 메모";
  stage.append(ghost);
  path.classList.add("link-preview");
  $("#mindmap-lines").append(path);
  linkDrag = { parentId, start, ghost, path };
  const move = (e) => {
    if (!linkDrag) return;
    const point = pointerWorld(e),
      dx = point.x - start.x;
    ghost.style.left = `${point.x}px`;
    ghost.style.top = `${point.y}px`;
    path.setAttribute(
      "d",
      `M ${start.x} ${start.y} C ${start.x + dx * 0.45} ${start.y}, ${point.x - dx * 0.35} ${point.y}, ${point.x} ${point.y}`,
    );
  };
  const end = (e) => {
    if (!linkDrag) return;
    move(e);
    const point = pointerWorld(e),
      distance = Math.hypot(point.x - start.x, point.y - start.y);
    ghost.remove();
    path.remove();
    linkDrag = null;
    window.removeEventListener("pointermove", move);
    window.removeEventListener("pointerup", end);
    createNodeImmediately(parentId, distance < 70 ? null : point);
  };
  window.addEventListener("pointermove", move);
  window.addEventListener("pointerup", end, { once: true });
  move(event);
}
function gestures() {
  const v = $("#mindmap-viewport");
  v.addEventListener("contextmenu", (e) => {
    if (e.target.closest(".node-card[data-node-id]")) e.preventDefault();
  });
  v.addEventListener(
    "wheel",
    (e) => {
      e.preventDefault();
      zoom(view.scale * Math.exp(-e.deltaY * 0.0015), e.clientX, e.clientY);
    },
    { passive: false },
  );
  v.addEventListener("pointerdown", (e) => {
    const card = e.target.closest(".node-card[data-node-id]");
    if (card && !e.target.closest("button")) {
      prepareNodeDrag(e, card);
      return;
    }
    if (e.target.closest("button,.node-card")) return;
    v.setPointerCapture(e.pointerId);
    pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
    if (pointers.size === 1)
      pan = { x: e.clientX, y: e.clientY, vx: view.x, vy: view.y };
    if (pointers.size === 2) {
      const [a, b] = [...pointers.values()];
      pinch = { d: Math.hypot(a.x - b.x, a.y - b.y), scale: view.scale };
    }
  });
  v.addEventListener("pointermove", (e) => {
    if (!pointers.has(e.pointerId)) return;
    pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
    if (pointers.size === 2 && pinch) {
      const [a, b] = [...pointers.values()];
      zoom(
        (pinch.scale * Math.hypot(a.x - b.x, a.y - b.y)) / Math.max(1, pinch.d),
        (a.x + b.x) / 2,
        (a.y + b.y) / 2,
      );
    } else if (pan) {
      view.x = pan.vx + e.clientX - pan.x;
      view.y = pan.vy + e.clientY - pan.y;
      applyView();
    }
  });
  const end = (e) => {
    pointers.delete(e.pointerId);
    pan = null;
    pinch = null;
  };
  v.addEventListener("pointerup", end);
  v.addEventListener("pointercancel", end);
}
function openNode(mode, id = null, position = null) {
  clearRichSelectionUI();
  dialogMode = { mode, id, position };
  $("#node-dialog-title").textContent =
    mode === "edit" ? "파생 메모 수정" : "새 파생 메모";
  $("#node-content").value =
    mode === "edit"
      ? current.nodes.find((n) => n.id === id)?.content || ""
      : "";
  $("#node-dialog").showModal();
  setTimeout(() => $("#node-content").focus(), 50);
}
async function createNodeImmediately(parentId = null, position = null) {
  if (!current) return;
  try {
    const created = await api(`/api/me/memos/${current.id}/nodes`, {
      method: "POST",
      body: JSON.stringify({
        parent_id: parentId,
        content: "",
        position_x: position?.x ?? null,
        position_y: position?.y ?? null,
        card_width: 620,
      }),
    });
    const memoId = current.id;
    await load(memoId);
    selectMapNode(created.id);
    const editor = document.querySelector(`[data-inline-node="${created.id}"]`);
    editor?.focus({ preventScroll: true });
    editor?.scrollIntoView({ behavior: "smooth", block: "nearest", inline: "nearest" });
    toast("빈 메모를 생각 지도에 만들었습니다");
  } catch (error) {
    alert(error.message);
  }
}
function selectedParentId() {
  return Number.isFinite(Number(selectedMapNode)) ? Number(selectedMapNode) : null;
}
function mapCenterPosition() {
  const rect = $("#mindmap-viewport").getBoundingClientRect();
  return pointerWorld({ clientX: rect.left + rect.width / 2, clientY: rect.top + rect.height / 2 });
}
async function createMediaNode(payload) {
  const center = mapCenterPosition();
  const created = await api(`/api/me/memos/${current.id}/nodes`, {
    method: "POST",
    body: JSON.stringify({ parent_id: selectedParentId(), content: "", position_x: center.x, position_y: center.y, card_width: 620, ...payload }),
  });
  await load(current.id); selectMapNode(created.id); return created;
}
function resizeImage(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = reject;
    reader.onload = () => {
      const image = new Image();
      image.onerror = reject;
      image.onload = () => {
        const scale = Math.min(1, 1600 / Math.max(image.naturalWidth, image.naturalHeight));
        const canvas = document.createElement("canvas");
        canvas.width = Math.max(1, Math.round(image.naturalWidth * scale));
        canvas.height = Math.max(1, Math.round(image.naturalHeight * scale));
        canvas.getContext("2d").drawImage(image, 0, 0, canvas.width, canvas.height);
        resolve(canvas.toDataURL("image/jpeg", 0.84));
      };
      image.src = reader.result;
    };
    reader.readAsDataURL(file);
  });
}
function openDrawing(nodeId = null) {
  drawingTargetId = nodeId;
  const node = nodeId ? current.nodes.find((item) => item.id === nodeId) : null;
  try { drawingState = node?.drawing_data ? JSON.parse(node.drawing_data) : { version: 1, width: 900, height: 600, strokes: [] }; }
  catch { drawingState = { version: 1, width: 900, height: 600, strokes: [] }; }
  $("#drawing-dialog h2").textContent = node ? "필기 이어 쓰기" : "생각 지도에 필기";
  $("#drawing-dialog").showModal();
  requestAnimationFrame(() => drawStrokes($("#drawing-canvas"), drawingState));
}
function drawingPoint(event) {
  const canvas = $("#drawing-canvas"), rect = canvas.getBoundingClientRect();
  return { x: (event.clientX - rect.left) * canvas.width / rect.width, y: (event.clientY - rect.top) * canvas.height / rect.height, p: event.pressure || 0.5 };
}
function bindDrawingCanvas() {
  const canvas = $("#drawing-canvas");
  canvas.addEventListener("pointerdown", (event) => {
    if (event.pointerType === "touch") return;
    event.preventDefault(); canvas.setPointerCapture(event.pointerId);
    activeStroke = { color: $("#drawing-color").value, width: Number($("#drawing-width").value), points: [drawingPoint(event)] };
    drawingState.strokes.push(activeStroke); drawStrokes(canvas, drawingState);
  });
  canvas.addEventListener("pointermove", (event) => {
    if (!activeStroke || !canvas.hasPointerCapture(event.pointerId)) return;
    event.preventDefault(); activeStroke.points.push(drawingPoint(event)); drawStrokes(canvas, drawingState);
  });
  const finish = () => { activeStroke = null; };
  canvas.addEventListener("pointerup", finish); canvas.addEventListener("pointercancel", finish);
}
const activeVoiceInputs = new WeakMap();
function resetVoiceButton(button) {
  button.classList.remove("listening");
  button.textContent = "🎙️ 음성";
  button.setAttribute("aria-label", "음성으로 메모 입력");
}
function startVoiceInput(target, button) {
  const active = activeVoiceInputs.get(button);
  if (active) {
    active.stopping = true;
    button.disabled = true;
    active.recognition.stop();
    return;
  }
  const Recognition =
    window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!Recognition) {
    alert(
      "이 브라우저에서는 음성 입력을 지원하지 않습니다. macOS Safari 또는 Chrome에서 마이크 권한을 허용해주세요.",
    );
    return;
  }
  const recognition = new Recognition(),
    state = { recognition, stopping: false, finalText: "", interimText: "" };
  recognition.lang = "ko-KR";
  recognition.interimResults = true;
  recognition.continuous = true;
  const original = target.value,
    separator = original.trim() ? " " : "";
  activeVoiceInputs.set(button, state);
  button.classList.add("listening");
  button.textContent = "■ 정지";
  button.setAttribute("aria-label", "음성 메모 녹음 정지");
  recognition.onresult = (event) => {
    let interim = "";
    for (let index = event.resultIndex; index < event.results.length; index++) {
      const text = event.results[index][0].transcript;
      if (event.results[index].isFinal) state.finalText += text;
      else interim += text;
    }
    state.interimText = interim;
    target.value = original + separator + state.finalText + state.interimText;
    target.dispatchEvent(new Event("input", { bubbles: true }));
  };
  recognition.onerror = (event) => {
    if (
      event.error === "aborted" ||
      event.error === "no-speech" ||
      state.stopping
    )
      return;
    const message =
      event.error === "not-allowed"
        ? "마이크 권한이 꺼져 있습니다. 브라우저의 사이트 설정에서 마이크를 허용해주세요."
        : `음성 입력 오류: ${event.error}`;
    toast(message);
  };
  recognition.onend = () => {
    if (activeVoiceInputs.get(button) !== state) return;
    activeVoiceInputs.delete(button);
    button.disabled = false;
    resetVoiceButton(button);
    target.focus();
  };
  try {
    recognition.start();
  } catch (error) {
    activeVoiceInputs.delete(button);
    button.disabled = false;
    resetVoiceButton(button);
    if (error.name !== "AbortError")
      toast("음성 입력을 시작하지 못했습니다. 잠시 후 다시 시도해주세요.");
  }
}
async function removeNode(id) {
  if (!confirm("이 가지와 아래에 연결된 메모를 모두 삭제할까요?")) return;
  await api(`/api/me/memo-nodes/${id}`, { method: "DELETE" });
  await load(current.id);
  toast("가지를 삭제했습니다");
}
$("#node-dialog").addEventListener("close", async () => {
  if ($("#node-dialog").returnValue !== "default" || !dialogMode) return;
  const content = $("#node-content").value.trim();
  if (!content) return toast("내용을 입력하세요");
  try {
    if (dialogMode.mode === "edit")
      await api(`/api/me/memo-nodes/${dialogMode.id}`, {
        method: "PUT",
        body: JSON.stringify({ content }),
      });
    else
      await api(`/api/me/memos/${current.id}/nodes`, {
        method: "POST",
        body: JSON.stringify({
          parent_id: dialogMode.id,
          content,
          position_x: dialogMode.position?.x ?? null,
          position_y: dialogMode.position?.y ?? null,
          card_width: 620,
        }),
      });
    await load(current.id);
    toast("메모를 연결했습니다");
  } catch (e) {
    alert(e.message);
  }
});
$("#node-save").onclick = () => $("#node-dialog").close("default");
$("#add-root-node").onclick = () => createNodeImmediately(null);
$("#add-image-node").onclick = () => $("#memo-image-input").click();
$("#memo-image-input").onchange = async (event) => {
  const file = event.target.files?.[0]; if (!file) return;
  try {
    toast("사진을 생각 지도에 맞게 줄이고 있습니다");
    await createMediaNode({ image_data: await resizeImage(file) });
    toast("이미지 메모를 만들었습니다");
  } catch (error) { alert(error.message || "이미지를 처리하지 못했습니다"); }
  event.target.value = "";
};
$("#add-drawing-node").onclick = () => openDrawing();
$("#drawing-undo").onclick = () => { drawingState.strokes.pop(); drawStrokes($("#drawing-canvas"), drawingState); };
$("#drawing-clear").onclick = () => { if (confirm("필기를 모두 지울까요?")) { drawingState.strokes = []; drawStrokes($("#drawing-canvas"), drawingState); } };
$("#drawing-save").onclick = async () => {
  if (!drawingState.strokes.length) return toast("먼저 필기해주세요");
  try {
    const drawing_data = JSON.stringify(drawingState);
    if (drawingTargetId) {
      const node = current.nodes.find((item) => item.id === drawingTargetId);
      await api(`/api/me/memo-nodes/${drawingTargetId}`, { method: "PUT", body: JSON.stringify({ content: node?.content || "", drawing_data }) });
      await load(current.id); selectMapNode(drawingTargetId);
    } else await createMediaNode({ drawing_data });
    $("#drawing-dialog").close(); toast("필기를 생각 지도에 저장했습니다");
  } catch (error) { alert(error.message); }
};
bindDrawingCanvas();
$("#search").oninput = renderList;
$("#manage-categories").onclick = () => {
  renderCategoryManager();
  $("#category-dialog").showModal();
  setTimeout(() => $("#new-category-name").focus(), 50);
};
$("#create-category").onclick = async () => {
  const name = $("#new-category-name").value.trim();
  if (!name) return toast("키워드 이름을 입력하세요");
  try {
    const created = await api("/api/me/memo-categories", {method: "POST", body: JSON.stringify({name})});
    $("#new-category-name").value = "";
    activeCategory = String(created.id);
    localStorage.setItem("memo-active-category-v1", activeCategory);
    await load(current?.id);
    renderCategoryManager();
    toast("키워드를 만들었습니다");
  } catch (error) { alert(error.message); }
};
$("#category-manager-list").onclick = async (event) => {
  const save = event.target.closest("[data-save-category]"), remove = event.target.closest("[data-delete-category]");
  if (!save && !remove) return;
  const id = Number((save || remove).dataset.saveCategory || (save || remove).dataset.deleteCategory);
  try {
    if (save) {
      const name = event.target.closest(".category-manager-row").querySelector("input").value.trim();
      await api(`/api/me/memo-categories/${id}`, {method: "PUT", body: JSON.stringify({name})});
      toast("키워드 이름을 수정했습니다");
    } else {
      const category = categories.find((item) => item.id === id);
      if (!confirm(`‘${category?.name || "이 키워드"}’를 삭제할까요?\n메모는 삭제되지 않고 미분류로 이동합니다.`)) return;
      await api(`/api/me/memo-categories/${id}`, {method: "DELETE"});
      if (String(activeCategory) === String(id)) activeCategory = "none";
      localStorage.setItem("memo-active-category-v1", activeCategory);
      toast("키워드를 삭제하고 메모는 미분류로 옮겼습니다");
    }
    await load(current?.id);
    renderCategoryManager();
  } catch (error) { alert(error.message); }
};
$("#memo-layout").onclick = (event) =>
  setMemoLayout(
    event.currentTarget.dataset.layout === "grid" ? "list" : "grid",
  );
$("#zoom-in").onclick = () => zoom(view.scale * 1.22);
$("#zoom-out").onclick = () => zoom(view.scale / 1.22);
$("#zoom-fit").onclick = fitMap;
$("#mindmap-fullscreen").onclick = () =>
  setMindmapFullscreen(
    !$("#mindmap-viewport").classList.contains("fullscreen-mode"),
  );
$("#node-mobile-edit").onclick = () => {
  if (selectedMapNode === "root") document.querySelector("[data-inline-root]")?.focus();
  else if (Number.isFinite(Number(selectedMapNode)))
    document.querySelector(`[data-inline-node="${Number(selectedMapNode)}"]`)?.focus();
};
$("#node-mobile-collapse").onclick = () => {
  if (selectedMapNode === "root") {
    const card = $("#memo-tree .node-card.root");
    card.classList.toggle("root-collapsed");
    selectMapNode("root");
    return;
  }
  const id = Number(selectedMapNode);
  if (!Number.isFinite(id)) return;
  if (collapsedNodes.has(id)) collapsedNodes.delete(id); else collapsedNodes.add(id);
  renderMap();
  selectMapNode(id);
};
$("#node-mobile-delete").onclick = async () => {
  const id = Number(selectedMapNode);
  if (!Number.isFinite(id)) return;
  await removeNode(id);
  clearMapNodeSelection();
};
$("#node-mobile-close").onclick = clearMapNodeSelection;
document.addEventListener("keydown", (event) => {
  if (
    event.key === "Escape" &&
    $("#mindmap-viewport").classList.contains("fullscreen-mode")
  ) {
    setMindmapFullscreen(false);
  }
});
$("#preview-open").onclick = () => {
  const id = Number($("#preview-open").dataset.id);
  $("#memo-preview-dialog").close();
  openRootEditor(id);
};
$("#preview-edit").onclick = () => {
  const id = Number($("#preview-edit").dataset.id);
  $("#memo-preview-dialog").close();
  openRootEditor(id, true);
};
$("#edit-root").onclick = () => {
  if (!current) return;
  openMemoEditDialog();
};
$("#edit-note-inline").onclick = openMemoEditDialog;
$("#memo-note").onclick = openMemoEditDialog;
$("#source-toggle").onclick = () => {
  const content = $("#source-content");
  const expanded = !content.classList.toggle("collapsed");
  $("#source-toggle").textContent = expanded ? "원문 접기" : "원문 펼치기";
  $("#source-toggle").setAttribute("aria-expanded", String(expanded));
};
$("#node-voice").onclick = (event) =>
  startVoiceInput($("#node-content"), event.currentTarget);
$("#new-memo").onclick = async () => {
  try {
    const r = await api("/api/me/memos", {
      method: "POST",
      body: JSON.stringify({ title: "새 메모", note: "", category_ids: /^\d+$/.test(String(activeCategory)) ? [Number(activeCategory)] : [] }),
    });
    await load(r.id);
    openMemoEditDialog();
  } catch (e) {
    alert(e.message);
  }
};
if (new URLSearchParams(location.search).get("new") === "1") {
  history.replaceState(null, "", location.pathname);
  queueMicrotask(() => $("#new-memo").click());
}
$("#memo-edit-save").onclick = async () => {
  try {
    const note = $("#memo-edit-note").value;
    const title = memoTitleFromContent(note, current.title);
    await api(`/api/me/memos/${current.id}`, {
      method: "PUT",
      body: JSON.stringify({
        title,
        note,
      }),
    });
    await api(`/api/me/memos/${current.id}/category`, {
      method: "PUT",
      body: JSON.stringify({
        category_ids: [...document.querySelectorAll("#memo-edit-categories input:checked")].map((input) => Number(input.value)),
      }),
    });
    $("#memo-edit-dialog").close();
    await load(current.id);
    toast("메모를 수정했습니다");
  } catch (e) {
    alert(e.message);
  }
};
$("#memo-edit-save-top").onclick = () => $("#memo-edit-save").click();
$("#delete-root").onclick = async () => {
  if (current) await removeMemoDocument(current.id);
};
let initialMemoLayout = "grid";
try {
  initialMemoLayout =
    localStorage.getItem(MEMO_LAYOUT_KEY) === "list" ? "list" : "grid";
} catch {}
setMemoLayout(initialMemoLayout);
gestures();
load().catch((e) => {
  $("#empty").innerHTML =
    `<b>메모를 불러오지 못했습니다</b><p>${esc(e.message)}</p>`;
});
