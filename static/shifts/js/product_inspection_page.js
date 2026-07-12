import * as pdfjsLib from "pdfjs-dist";

pdfjsLib.GlobalWorkerOptions.workerSrc =
  "https://cdn.jsdelivr.net/npm/pdfjs-dist@4.0.379/build/pdf.worker.min.mjs";

function getCookie(name) {
  const m = document.cookie.match(
    new RegExp("(?:^|; )" + name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + "=([^;]*)")
  );
  return m ? decodeURIComponent(m[1]) : "";
}

function esc(s) {
  return String(s || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/"/g, "&quot;");
}

function readBootstrap() {
  const el = document.getElementById("insp-bootstrap");
  if (!el) return null;
  try {
    return JSON.parse(el.textContent || "{}");
  } catch (_e) {
    return null;
  }
}

function postForm(action, fields) {
  const fd = new FormData();
  fd.append("action", action);
  const csrf = getCookie("csrftoken");
  if (csrf) fd.append("csrfmiddlewaretoken", csrf);
  Object.entries(fields || {}).forEach(([k, v]) => fd.append(k, v));
  return fetch(window.location.href, {
    method: "POST",
    body: fd,
    headers: { "X-CSRFToken": getCookie("csrftoken"), "X-Requested-With": "XMLHttpRequest" },
    credentials: "same-origin",
  }).then(async (res) => {
    const data = await res.json();
    if (!res.ok || !data?.ok) throw new Error((data && data.error) || "Ошибка сохранения.");
    return data;
  });
}

function uid() {
  return "d" + Math.random().toString(36).slice(2, 10);
}

function dist(x1, y1, x2, y2) {
  return Math.hypot(x1 - x2, y1 - y2);
}

const boot = readBootstrap();
if (!boot) throw new Error("No bootstrap");

const state = {
  canEdit: !!boot.canEdit,
  criticalityChoices: boot.criticalityChoices || [],
  frequencyChoices: boot.frequencyChoices || [],
  inspection: boot.inspection || { dimensions: [], sessions: [], drawing_files: [] },
  planRows: (boot.inspection?.dimensions || []).slice(),
  draft: [],
  selectedEmpCode: "",
  selectedEmpLabel: "",
  pdfDoc: null,
  pdfPage: 1,
  pdfNumPages: 0,
  currentFileUrl: "",
  renderTask: null,
  pickMode: true,
  activeDraftId: null,
  suppressCanvasClick: false,
};

const canvas = document.getElementById("insp-pdf-canvas");
const canvasWrap = document.getElementById("insp-canvas-wrap");
const markersEl = document.getElementById("insp-markers");
const canvasEmpty = document.getElementById("insp-canvas-empty");
const canvasLoading = document.getElementById("insp-canvas-loading");
const drawingSelect = document.getElementById("insp-drawing-select");
const CANVAS_EMPTY_DEFAULT =
  "Чертёж не загружен. Добавьте PDF в карточке наладки.";
const pageLabel = document.getElementById("insp-page-label");
const draftTbody = document.getElementById("insp-draft-tbody");
const draftEmpty = document.getElementById("insp-draft-empty");
const journalEl = document.getElementById("insp-journal");
const journalEmpty = document.getElementById("insp-journal-empty");
const planTbody = document.getElementById("insp-plan-tbody");

function setMsg(id, text, isErr) {
  const el = document.getElementById(id);
  if (!el) return;
  el.textContent = text || "";
  el.classList.toggle("is-error", !!isErr);
}

function setDrawingView(mode, message) {
  const loading = mode === "loading";
  const empty = mode === "empty" || mode === "error";
  const ready = mode === "ready";

  if (canvasWrap) {
    canvasWrap.classList.toggle("is-busy", loading || empty);
  }
  if (canvasLoading) canvasLoading.hidden = !loading;
  if (canvasEmpty) {
    canvasEmpty.hidden = !empty;
    canvasEmpty.classList.toggle("is-error", mode === "error");
    const p = canvasEmpty.querySelector("p");
    if (p) p.textContent = message || CANVAS_EMPTY_DEFAULT;
  }
  if (canvas) canvas.hidden = !ready;
  if (markersEl) markersEl.hidden = !ready;
}

function updateInspTabSlider() {
  const slider = document.getElementById("insp-tab-slider");
  const active = document.querySelector(".insp-tab.is-active");
  if (!slider || !active) return;
  slider.style.width = active.offsetWidth + "px";
  slider.style.left = active.offsetLeft + "px";
}

function optionHtml(choices, selected) {
  return choices
    .map(
      (c) =>
        `<option value="${esc(c.value)}"${c.value === selected ? " selected" : ""}>${esc(c.label)}</option>`
    )
    .join("");
}

function findNearPlanDimension(x, y, page) {
  let best = null;
  let bestD = 5;
  (state.inspection.dimensions || []).forEach((dim) => {
    if (dim.mark_x == null || dim.mark_y == null) return;
    if (dim.pdf_page && Number(dim.pdf_page) !== page) return;
    const d = dist(x, y, Number(dim.mark_x), Number(dim.mark_y));
    if (d < bestD) {
      bestD = d;
      best = dim;
    }
  });
  return best;
}

function draftFromPlanDim(dim, x, y, page) {
  return {
    id: uid(),
    dimension_id: dim.id,
    label: dim.label,
    nominal: dim.nominal || "",
    tolerance_display: dim.tolerance_display || "",
    criticality: dim.criticality || "",
    actual_value: "",
    mark_x: x ?? dim.mark_x,
    mark_y: y ?? dim.mark_y,
    pdf_page: page ?? dim.pdf_page ?? state.pdfPage,
    from_drawing: true,
  };
}

function draftFromClick(x, y, page) {
  const near = findNearPlanDimension(x, y, page);
  if (near) return draftFromPlanDim(near, x, y, page);
  const n = state.draft.length + 1;
  return {
    id: uid(),
    label: "Точка " + n,
    nominal: "",
    tolerance_display: "",
    actual_value: "",
    mark_x: x,
    mark_y: y,
    pdf_page: page,
    from_drawing: true,
  };
}

function addDraft(item) {
  state.draft.push(item);
  state.activeDraftId = item.id;
  renderDraft();
  renderMarkers();
}

function removeDraft(id) {
  state.draft = state.draft.filter((d) => d.id !== id);
  if (state.activeDraftId === id) state.activeDraftId = null;
  renderDraft();
  renderMarkers();
}

function clampPct(v) {
  return Math.min(100, Math.max(0, v));
}

function pointerToCanvasPct(clientX, clientY) {
  if (!canvas) return { x: 0, y: 0 };
  const rect = canvas.getBoundingClientRect();
  if (!rect.width || !rect.height) return { x: 0, y: 0 };
  return {
    x: clampPct(((clientX - rect.left) / rect.width) * 100),
    y: clampPct(((clientY - rect.top) / rect.height) * 100),
  };
}

function draftMarkerBadgeHtml(idx, isActive) {
  const activeClass = isActive ? " is-active" : "";
  return `<span class="insp-marker insp-marker--draft${activeClass}" aria-hidden="true">${idx + 1}</span>`;
}

function attachDraftMarkerDrag(markerEl, rowId) {
  let startX = 0;
  let startY = 0;
  let dragging = false;

  markerEl.addEventListener("pointerdown", (e) => {
    e.stopPropagation();
    e.preventDefault();
    startX = e.clientX;
    startY = e.clientY;
    dragging = false;
    state.activeDraftId = rowId;
    markerEl.setPointerCapture(e.pointerId);
    markerEl.classList.add("is-dragging");
    renderDraft();
  });

  markerEl.addEventListener("pointermove", (e) => {
    if (!markerEl.hasPointerCapture(e.pointerId)) return;
    const dx = e.clientX - startX;
    const dy = e.clientY - startY;
    if (!dragging && Math.hypot(dx, dy) < 4) return;
    dragging = true;
    canvasWrap?.classList.add("is-dragging-marker");
    const { x, y } = pointerToCanvasPct(e.clientX, e.clientY);
    const row = state.draft.find((d) => d.id === rowId);
    if (!row) return;
    row.mark_x = x;
    row.mark_y = y;
    markerEl.style.left = x + "%";
    markerEl.style.top = y + "%";
  });

  markerEl.addEventListener("pointerup", (e) => {
    if (!markerEl.hasPointerCapture(e.pointerId)) return;
    markerEl.releasePointerCapture(e.pointerId);
    markerEl.classList.remove("is-dragging");
    canvasWrap?.classList.remove("is-dragging-marker");
    if (dragging) {
      state.suppressCanvasClick = true;
      setTimeout(() => {
        state.suppressCanvasClick = false;
      }, 0);
      renderDraft();
      renderMarkers();
    } else {
      state.activeDraftId = rowId;
      renderDraft();
      renderMarkers();
    }
    dragging = false;
  });

  markerEl.addEventListener("click", (e) => {
    e.stopPropagation();
  });
}

function renderDraft() {
  if (!draftTbody) return;
  draftTbody.innerHTML = "";
  state.draft.forEach((row, idx) => {
    const tr = document.createElement("tr");
    tr.dataset.draftId = row.id;
    const isActive = row.id === state.activeDraftId;
    tr.classList.toggle("is-active", isActive);
    tr.innerHTML =
      `<td class="insp-draft-num">${draftMarkerBadgeHtml(idx, isActive)}</td>` +
      `<td><input type="text" class="insp-inp" data-f="label" value="${esc(row.label)}" maxlength="120" /></td>` +
      `<td><input type="text" class="insp-inp" data-f="nominal" value="${esc(row.nominal)}" maxlength="80" /></td>` +
      `<td><input type="text" class="insp-inp" data-f="tolerance_display" value="${esc(row.tolerance_display)}" maxlength="80" placeholder="±0.05" /></td>` +
      `<td><input type="text" class="insp-inp insp-inp--actual" data-f="actual_value" value="${esc(row.actual_value)}" maxlength="80" placeholder="факт" required /></td>` +
      `<td><button type="button" class="btn btn-inv-delete btn-inv-delete--s0 js-draft-remove" title="Убрать">×</button></td>`;
    draftTbody.appendChild(tr);
  });
  if (draftEmpty) draftEmpty.hidden = state.draft.length > 0;
}

function collectDraftFromDom() {
  const rows = [];
  draftTbody?.querySelectorAll("tr").forEach((tr, idx) => {
    const base = state.draft[idx] || {};
    const row = { ...base };
    tr.querySelectorAll("[data-f]").forEach((inp) => {
      row[inp.getAttribute("data-f")] = inp.value;
    });
    rows.push(row);
  });
  state.draft = rows;
  return rows;
}

function renderMarkers() {
  if (!markersEl || !canvas) return;
  markersEl.innerHTML = "";
  const showPage = state.pdfPage;

  (state.inspection.dimensions || []).forEach((dim) => {
    if (dim.mark_x == null || dim.mark_y == null) return;
    if (dim.pdf_page && Number(dim.pdf_page) !== showPage) return;
    const m = document.createElement("button");
    m.type = "button";
    m.className = "insp-marker insp-marker--plan";
    m.style.left = dim.mark_x + "%";
    m.style.top = dim.mark_y + "%";
    m.title = dim.label;
    m.textContent = "◆";
    m.addEventListener("click", (e) => {
      e.stopPropagation();
      if (!state.draft.some((d) => d.dimension_id === dim.id)) {
        addDraft(draftFromPlanDim(dim, dim.mark_x, dim.mark_y, showPage));
      }
    });
    markersEl.appendChild(m);
  });

  state.draft.forEach((row, idx) => {
    if (row.mark_x == null || row.mark_y == null) return;
    if (row.pdf_page && Number(row.pdf_page) !== showPage) return;
    const m = document.createElement("button");
    m.type = "button";
    m.className = "insp-marker insp-marker--draft" + (row.id === state.activeDraftId ? " is-active" : "");
    m.style.left = row.mark_x + "%";
    m.style.top = row.mark_y + "%";
    m.title = row.label || "Пункт " + (idx + 1);
    m.textContent = String(idx + 1);
    attachDraftMarkerDrag(m, row.id);
    markersEl.appendChild(m);
  });
}

async function renderPdfPage() {
  if (!state.pdfDoc || !canvas) return;
  if (state.renderTask) {
    try {
      state.renderTask.cancel();
    } catch (_e) {}
  }
  const page = await state.pdfDoc.getPage(state.pdfPage);
  const viewport = page.getViewport({ scale: 1 });
  const wrapW = canvasWrap?.clientWidth || viewport.width;
  const maxScale = wrapW >= 1100 ? 3 : wrapW >= 760 ? 2.5 : 1.75;
  const displayScale = Math.min(maxScale, Math.max(1, wrapW / viewport.width));
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  const renderViewport = page.getViewport({ scale: displayScale * dpr });
  canvas.width = renderViewport.width;
  canvas.height = renderViewport.height;
  canvas.style.width = `${renderViewport.width / dpr}px`;
  canvas.style.height = `${renderViewport.height / dpr}px`;
  const ctx = canvas.getContext("2d");
  state.renderTask = page.render({ canvasContext: ctx, viewport: renderViewport });
  await state.renderTask.promise;
  if (pageLabel) pageLabel.textContent = `Стр. ${state.pdfPage} / ${state.pdfNumPages}`;
  renderMarkers();
}

async function loadPdf(url) {
  if (!url) {
    state.pdfDoc = null;
    setDrawingView("empty");
    return;
  }
  state.currentFileUrl = url;
  const openLink = document.getElementById("insp-pdf-open");
  if (openLink) openLink.href = url;
  setDrawingView("loading");
  try {
    if (state.pdfDoc) {
      try {
        await state.pdfDoc.destroy();
      } catch (_e) {}
      state.pdfDoc = null;
    }
    const loading = pdfjsLib.getDocument({ url, withCredentials: true });
    state.pdfDoc = await loading.promise;
    state.pdfNumPages = state.pdfDoc.numPages;
    state.pdfPage = 1;
    await renderPdfPage();
    setDrawingView("ready");
  } catch (err) {
    console.error("PDF load failed:", err);
    state.pdfDoc = null;
    setDrawingView(
      "error",
      "Не удалось загрузить чертеж. Нажмите PDF или обновите страницу."
    );
  }
}

function initDrawingSelect() {
  const files = state.inspection.drawing_files || [];
  if (!drawingSelect) return;
  drawingSelect.innerHTML = "";
  if (!files.length) {
    const opt = document.createElement("option");
    opt.value = "";
    opt.textContent = "Нет чертежа";
    drawingSelect.appendChild(opt);
    setDrawingView("empty");
    return;
  }
  files.forEach((f, i) => {
    const opt = document.createElement("option");
    opt.value = f.url;
    opt.textContent = f.name || "Чертёж " + (i + 1);
    drawingSelect.appendChild(opt);
  });
  loadPdf(files[0].url);
  drawingSelect.addEventListener("change", () => loadPdf(drawingSelect.value));
}

canvasWrap?.addEventListener("click", (e) => {
  if (!state.pickMode || !canvas || !state.pdfDoc || state.suppressCanvasClick) return;
  if (e.target.closest(".insp-marker")) return;
  const rect = canvas.getBoundingClientRect();
  const x = ((e.clientX - rect.left) / rect.width) * 100;
  const y = ((e.clientY - rect.top) / rect.height) * 100;
  addDraft(draftFromClick(x, y, state.pdfPage));
});

document.getElementById("insp-page-prev")?.addEventListener("click", async () => {
  if (!state.pdfDoc || state.pdfPage <= 1) return;
  state.pdfPage -= 1;
  await renderPdfPage();
});
document.getElementById("insp-page-next")?.addEventListener("click", async () => {
  if (!state.pdfDoc || state.pdfPage >= state.pdfNumPages) return;
  state.pdfPage += 1;
  await renderPdfPage();
});
document.getElementById("insp-pick-mode")?.addEventListener("change", (e) => {
  state.pickMode = e.target.checked;
  canvasWrap?.classList.toggle("is-pick-mode", state.pickMode);
});

draftTbody?.addEventListener("input", () => collectDraftFromDom());
draftTbody?.addEventListener("click", (e) => {
  const rm = e.target.closest(".js-draft-remove");
  if (rm) {
    const tr = rm.closest("tr");
    if (tr?.dataset.draftId) removeDraft(tr.dataset.draftId);
    return;
  }
  const tr = e.target.closest("tr[data-draft-id]");
  if (!tr || e.target.closest("input, button, textarea, select")) return;
  state.activeDraftId = tr.dataset.draftId;
  renderDraft();
  renderMarkers();
});

document.getElementById("insp-clear-draft")?.addEventListener("click", () => {
  state.draft = [];
  state.activeDraftId = null;
  renderDraft();
  renderMarkers();
});

document.getElementById("insp-load-from-plan")?.addEventListener("click", async () => {
  const firstPiece = document.getElementById("insp-first-piece")?.checked ? "1" : "0";
  try {
    const data = await postForm("get_inspection_applicable", { first_piece: firstPiece });
    (data.dimensions || []).forEach((dim) => {
      if (!state.draft.some((d) => d.dimension_id === dim.id)) {
        state.draft.push(draftFromPlanDim(dim, dim.mark_x, dim.mark_y, dim.pdf_page || state.pdfPage));
      }
    });
    renderDraft();
    renderMarkers();
  } catch (err) {
    setMsg("insp-form-msg", err.message, true);
  }
});

function resultLabel(r) {
  if (r === "ok") return "Годна";
  if (r === "nok") return "Брак";
  if (r === "partial") return "Частично";
  return r || "";
}

function renderJournal() {
  if (!journalEl) return;
  const sessions = state.inspection.sessions || [];
  journalEl.innerHTML = "";
  sessions.forEach((s) => {
    const card = document.createElement("article");
    card.className = "insp-session";
    const rows = (s.values || [])
      .map(
        (v) =>
          `<tr><td>${esc(v.dimension_label)}</td><td>${esc(v.nominal)}</td><td>${esc(v.tolerance_display)}</td><td>${esc(v.actual_value)}</td><td>${v.is_ok === true ? "OK" : v.is_ok === false ? "брак" : "—"}</td></tr>`
      )
      .join("");
    card.innerHTML =
      `<header class="insp-session-head"><strong>Акт №${esc(s.session_no)}</strong> · ${esc(s.created_at)} · ${esc(s.inspector_label)}` +
      (s.part_label ? ` · ${esc(s.part_label)}` : "") +
      `<span class="insp-result insp-result--${esc(s.result)}">${esc(resultLabel(s.result))}</span>` +
      (state.canEdit
        ? ` <button type="button" class="btn btn-inv-delete btn-inv-delete--s0 js-del-session" data-id="${esc(s.id)}">×</button>`
        : "") +
      `</header><p class="muted">Записал: ${esc(s.author_username)}${s.notes ? " · " + esc(s.notes) : ""}</p>` +
      `<table class="insp-table insp-table--compact"><thead><tr><th>Размер</th><th>Номинал</th><th>Допуск</th><th>Факт</th><th>OK</th></tr></thead><tbody>${rows}</tbody></table>`;
    journalEl.appendChild(card);
  });
  if (journalEmpty) journalEmpty.hidden = sessions.length > 0;
}

function applyInspection(payload) {
  if (!payload) return;
  state.inspection = payload;
  state.planRows = (payload.dimensions || []).slice();
  renderJournal();
  renderPlan();
  renderMarkers();
}

function renderPlan() {
  if (!planTbody || !state.canEdit) return;
  planTbody.innerHTML = "";
  state.planRows.forEach((row, idx) => {
    const tr = document.createElement("tr");
    tr.dataset.rowIndex = String(idx);
    const tol = row.tolerance_display || "";
    tr.innerHTML =
      `<td><input class="insp-inp" data-f="label" value="${esc(row.label)}" maxlength="120" /></td>` +
      `<td><input class="insp-inp" data-f="nominal" value="${esc(row.nominal)}" maxlength="80" /></td>` +
      `<td><input class="insp-inp" data-f="tolerance_display" value="${esc(tol)}" maxlength="80" /></td>` +
      `<td><select class="insp-inp" data-f="criticality">${optionHtml(state.criticalityChoices, row.criticality || "standard")}</select></td>` +
      `<td><select class="insp-inp" data-f="frequency">${optionHtml(state.frequencyChoices, row.frequency || "always")}</select></td>` +
      `<td><input class="insp-inp" type="number" data-f="frequency_n" min="1" max="999" value="${esc(row.frequency_n || 5)}" style="width:4em" /></td>` +
      `<td><button type="button" class="btn btn-inv-delete btn-inv-delete--s0 js-plan-remove">×</button></td>`;
    planTbody.appendChild(tr);
  });
}

function collectPlanFromDom() {
  const rows = [];
  planTbody?.querySelectorAll("tr").forEach((tr, idx) => {
    const row = { ...(state.planRows[idx] || {}) };
    tr.querySelectorAll("[data-f]").forEach((inp) => {
      row[inp.getAttribute("data-f")] = inp.value;
    });
    if ((row.label || "").trim()) rows.push(row);
  });
  state.planRows = rows;
  return rows;
}

document.getElementById("insp-plan-add-row")?.addEventListener("click", () => {
  state.planRows = collectPlanFromDom();
  state.planRows.push({
    label: "",
    nominal: "",
    tolerance_display: "",
    criticality: "standard",
    frequency: "always",
    frequency_n: 5,
  });
  renderPlan();
});
planTbody?.addEventListener("click", (e) => {
  const rm = e.target.closest(".js-plan-remove");
  if (!rm) return;
  const tr = rm.closest("tr");
  const idx = tr ? parseInt(tr.dataset.rowIndex || "-1", 10) : -1;
  state.planRows = collectPlanFromDom();
  if (idx >= 0) state.planRows.splice(idx, 1);
  renderPlan();
});
document.getElementById("insp-plan-save")?.addEventListener("click", async () => {
  const rows = collectPlanFromDom();
  setMsg("insp-plan-msg", "Сохранение…");
  try {
    const data = await postForm("save_inspection_plan", { dimensions_json: JSON.stringify(rows) });
    applyInspection(data.inspection);
    setMsg("insp-plan-msg", "Карта сохранена.");
  } catch (err) {
    setMsg("insp-plan-msg", err.message, true);
  }
});

document.getElementById("insp-act-form")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  if (!state.selectedEmpLabel) {
    setMsg("insp-form-msg", "Выберите контролёра.", true);
    return;
  }
  const rows = collectDraftFromDom().filter((r) => (r.actual_value || "").trim());
  if (!rows.length) {
    setMsg("insp-form-msg", "Заполните факт хотя бы для одного пункта.", true);
    return;
  }
  setMsg("insp-form-msg", "Сохранение…");
  try {
    const data = await postForm("create_inspection_session", {
      inspector_emp_code: state.selectedEmpCode,
      inspector_label: state.selectedEmpLabel,
      part_label: (document.getElementById("insp-part-label")?.value || "").trim(),
      first_piece: document.getElementById("insp-first-piece")?.checked ? "1" : "0",
      notes: (document.getElementById("insp-notes")?.value || "").trim(),
      measurements_json: JSON.stringify(rows),
    });
    applyInspection(data.inspection);
    state.draft = [];
    state.activeDraftId = null;
    document.getElementById("insp-act-form")?.reset();
    state.selectedEmpCode = "";
    state.selectedEmpLabel = "";
    renderDraft();
    renderMarkers();
    setMsg("insp-form-msg", "Акт №" + (data.session?.session_no || "") + " сохранён.");
    document.querySelector('[data-insp-tab="journal"]')?.click();
  } catch (err) {
    setMsg("insp-form-msg", err.message, true);
  }
});

journalEl?.addEventListener("click", async (e) => {
  const btn = e.target.closest(".js-del-session");
  if (!btn || !state.canEdit) return;
  if (!confirm("Удалить акт?")) return;
  try {
    const data = await postForm("delete_inspection_session", { session_id: btn.getAttribute("data-id") });
    applyInspection(data.inspection);
  } catch (err) {
    alert(err.message);
  }
});

document.querySelectorAll(".insp-tab").forEach((btn) => {
  btn.addEventListener("click", () => {
    const tab = btn.getAttribute("data-insp-tab");
    document.querySelectorAll(".insp-tab").forEach((b) => {
      const on = b === btn;
      b.classList.toggle("is-active", on);
      b.setAttribute("aria-selected", on ? "true" : "false");
    });
    document.querySelectorAll(".insp-pane").forEach((pane) => {
      const on = pane.getAttribute("data-insp-pane") === tab;
      pane.classList.toggle("is-active", on);
      pane.hidden = !on;
    });
    updateInspTabSlider();
  });
});

(function initEmpCombo() {
  const combo = document.getElementById("insp-emp-combo");
  const sel = document.getElementById("insp-emp-select");
  const input = document.getElementById("insp-emp-search");
  const list = document.getElementById("insp-emp-suggest");
  if (!combo || !sel || !list || !input) return;
  let activeIdx = -1;
  function hide() {
    list.hidden = true;
    input.setAttribute("aria-expanded", "false");
    combo.classList.remove("is-open");
    activeIdx = -1;
  }
  function refresh(q) {
    list.textContent = "";
    const query = (q || "").trim().toLowerCase();
    let n = 0;
    Array.from(sel.options).forEach((opt, idx) => {
      if (idx === 0 || !opt.value) return;
      const text = (opt.textContent || "").trim();
      if (query && !text.toLowerCase().includes(query)) return;
      const li = document.createElement("li");
      li.className = "insp-emp-item";
      li.dataset.code = opt.value;
      li.dataset.label = text;
      li.textContent = text;
      list.appendChild(li);
      n++;
    });
    list.hidden = n === 0;
    input.setAttribute("aria-expanded", n ? "true" : "false");
  }
  input.addEventListener("input", () => refresh(input.value));
  input.addEventListener("focus", () => refresh(input.value));
  list.addEventListener("click", (e) => {
    const item = e.target.closest(".insp-emp-item");
    if (!item) return;
    state.selectedEmpCode = item.dataset.code || "";
    state.selectedEmpLabel = item.dataset.label || "";
    sel.value = state.selectedEmpCode;
    input.value = state.selectedEmpLabel;
    hide();
  });
  document.addEventListener("click", (e) => {
    if (!combo.contains(e.target)) hide();
  });
})();

function initHeaderTooltips() {
  let activePop = null;
  let activeTh = null;

  function hideTip() {
    activePop?.remove();
    activePop = null;
    activeTh = null;
  }

  function showTip(th) {
    const src = th.querySelector(".insp-tip-text");
    if (!src) return;
    const text = src.textContent.trim();
    if (!text) return;
    if (activeTh === th) return;
    hideTip();
    activeTh = th;
    activePop = document.createElement("div");
    activePop.className = "insp-tip-pop";
    activePop.textContent = text;
    activePop.setAttribute("role", "tooltip");
    document.body.appendChild(activePop);

    const rect = th.getBoundingClientRect();
    const pad = 10;
    const popW = activePop.offsetWidth;
    const popH = activePop.offsetHeight;
    let left = rect.left + rect.width / 2 - popW / 2;
    left = Math.max(pad, Math.min(left, window.innerWidth - popW - pad));
    let top = rect.bottom + pad;
    let above = false;
    if (top + popH > window.innerHeight - pad) {
      top = rect.top - popH - pad;
      above = true;
    }
    activePop.classList.toggle("is-above", above);
    activePop.style.left = `${left}px`;
    activePop.style.top = `${top}px`;
    const arrowX = rect.left + rect.width / 2 - left;
    activePop.style.setProperty("--insp-tip-arrow-x", `${Math.max(14, Math.min(popW - 14, arrowX))}px`);
  }

  document.querySelectorAll(".insp-th-tip").forEach((th) => {
    const src = th.querySelector(".insp-tip-text");
    if (!src) return;
    th.setAttribute("title", src.textContent.trim());
    th.tabIndex = 0;
    th.addEventListener("mouseenter", () => showTip(th));
    th.addEventListener("mouseleave", hideTip);
    th.addEventListener("focus", () => showTip(th));
    th.addEventListener("blur", hideTip);
  });

  window.addEventListener("scroll", hideTip, true);
  window.addEventListener("resize", hideTip);
}

canvasWrap?.classList.add("is-pick-mode");

const layoutEl = document.getElementById("insp-layout");
const sideToggle = document.getElementById("insp-side-toggle");
const SIDE_COLLAPSED_KEY = "insp-side-collapsed";

function setSideCollapsed(collapsed) {
  layoutEl?.classList.toggle("is-side-collapsed", collapsed);
  if (sideToggle) {
    sideToggle.setAttribute("aria-expanded", collapsed ? "false" : "true");
    sideToggle.title = collapsed ? "Развернуть панель акта" : "Свернуть панель акта";
  }
  try {
    sessionStorage.setItem(SIDE_COLLAPSED_KEY, collapsed ? "1" : "0");
  } catch (_e) {}
  if (state.pdfDoc) {
    requestAnimationFrame(() => renderPdfPage());
  }
}

sideToggle?.addEventListener("click", () => {
  setSideCollapsed(!layoutEl?.classList.contains("is-side-collapsed"));
});

try {
  if (sessionStorage.getItem(SIDE_COLLAPSED_KEY) === "1") {
    setSideCollapsed(true);
  }
} catch (_e) {}

initDrawingSelect();
renderDraft();
renderJournal();
renderPlan();
initHeaderTooltips();
updateInspTabSlider();
window.addEventListener("resize", () => {
  updateInspTabSlider();
  if (state.pdfDoc) renderPdfPage();
});
