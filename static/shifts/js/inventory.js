/* inventory.js — extracted from inventory.html, uses data island #inv-options */
var INV = (function () {
  try {
    var el = document.getElementById("inv-options");
    return el ? JSON.parse(el.textContent) : {};
  } catch (e) { return {}; }
})();

(function () {
  var DELETE_STEPS = 5;
  var STEP_CLASS_PREFIX = "btn-inv-delete--s";

  function resetDeleteButton(btn) {
    btn.setAttribute("data-step", "0");
    btn.className = "btn btn-inv-delete btn-inv-delete--s0";
    btn.setAttribute("aria-label", "Удалить: 0 из " + DELETE_STEPS);
    btn.title = "Удалить: нажмите " + DELETE_STEPS + " раз";
  }

  function setDeleteStep(btn, step) {
    btn.setAttribute("data-step", String(step));
    btn.className = "btn btn-inv-delete " + STEP_CLASS_PREFIX + step;
    btn.setAttribute("aria-label", "Удалить: " + step + " из " + DELETE_STEPS);
    btn.title = step < DELETE_STEPS
      ? "Удалить: ещё " + (DELETE_STEPS - step) + " наж."
      : "Подтвердить удаление";
  }

  document.querySelectorAll(".inv-stock-delete-form").forEach(function (form) {
    var btn = form.querySelector(".btn-inv-delete");
    if (!btn) return;
    resetDeleteButton(btn);
    btn.addEventListener("click", function () {
      var step = parseInt(btn.getAttribute("data-step") || "0", 10) + 1;
      if (step < DELETE_STEPS) {
        setDeleteStep(btn, step);
        return;
      }
      setDeleteStep(btn, DELETE_STEPS);
      if (window.confirm("Удалить эту позицию склада?")) {
        form.submit();
      } else {
        resetDeleteButton(btn);
      }
    });
  });
})();

(function () {
  var exportBtn = document.getElementById("inv-stock-export-csv");
  var tableWrap = document.querySelector(".inv-stock-table-wrap table.data-grid");
  if (exportBtn && tableWrap) {
    exportBtn.addEventListener("click", function () {
      var rows = [];
      var headers = [];
      tableWrap.querySelectorAll("thead th").forEach(function (th) {
        headers.push((th.textContent || "").trim().replace(/\s+/g, " "));
      });
      if (headers.length) rows.push(headers);
      tableWrap.querySelectorAll("tbody tr").forEach(function (tr) {
        var cells = [];
        tr.querySelectorAll("td").forEach(function (td) {
          cells.push('"' + (td.textContent || "").trim().replace(/"/g, '""').replace(/\s+/g, " ") + '"');
        });
        if (cells.length) rows.push(cells.join(";"));
      });
      if (rows.length < 2) return;
      var blob = new Blob(["\uFEFF" + rows.join("\r\n")], { type: "text/csv;charset=utf-8" });
      var a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = "sklad_" + (new Date().toISOString().slice(0, 10)) + ".csv";
      a.click();
      URL.revokeObjectURL(a.href);
    });
  }
})();

(function () {
  var form = document.getElementById("inventory-stock-filter-form");
  if (!form) return;
  var sel = form.querySelector(".js-stock-filter-tool-material");
  var inp = form.querySelector(".js-stock-filter-tool-material-custom");
  if (!sel || !inp) return;
  function sync(fromUserChange) {
    var isOther = sel.value === INV.tool_material_filter_other;
    inp.style.display = isOther ? "block" : "none";
    if (!isOther && fromUserChange) inp.value = "";
  }
  sel.addEventListener("change", function () { sync(true); });
  sync(false);
})();

(function () {
  var inputs = document.querySelectorAll(".defect-cell-input");
  var rowToggles = document.querySelectorAll(".defects-row-edit-toggle");
  if (!rowToggles.length) return;
  var saveTimer = null;
  var inSubmit = false;
  var pendingFormId = "";
  var editableForms = new Set();

  function submitDefectForm(formId) {
    var form = formId ? document.getElementById(formId) : null;
    if (!form || inSubmit) return;
    inSubmit = true;
    form.submit();
  }

  function applyRowEditState(formId, editing) {
    document.querySelectorAll('.defect-cell-input[form="' + formId + '"]').forEach(function (el) {
      if (el.tagName === "SELECT") {
        el.disabled = !editing;
      } else {
        el.readOnly = !editing;
      }
    });
  }

  inputs.forEach(function (el) {
    el.addEventListener("change", function () {
      var formId = el.getAttribute("form") || "";
      if (!formId || !editableForms.has(formId)) return;
      pendingFormId = formId;
      if (saveTimer) clearTimeout(saveTimer);
      saveTimer = setTimeout(function () {
        submitDefectForm(pendingFormId);
      }, 240);
    });
    el.addEventListener("blur", function () {
      var formId = el.getAttribute("form") || "";
      if (!formId || !editableForms.has(formId)) return;
      pendingFormId = formId;
    });
  });

  rowToggles.forEach(function (btn) {
    var formId = btn.getAttribute("data-defect-form-id") || "";
    if (!formId) return;
    applyRowEditState(formId, false);
    btn.addEventListener("click", function () {
      var editing = !editableForms.has(formId);
      if (editing) editableForms.add(formId);
      else editableForms.delete(formId);
      applyRowEditState(formId, editing);
      btn.textContent = editing ? "🔓" : "🔒";
      btn.title = editing ? "Выключить редактирование строки" : "Включить редактирование строки";
      btn.setAttribute("aria-label", btn.title);
    });
  });
})();
(function () {
  var searchInputs = document.querySelectorAll(".js-defect-responsible-search");
  if (!searchInputs.length) return;

  function normalizeText(s) {
    return String(s || "").toLowerCase().replace(/\s+/g, " ").trim();
  }

  function applyFilter(input) {
    var listId = input.getAttribute("data-target-list");
    var list = listId ? document.getElementById(listId) : null;
    if (!list) return;
    var q = normalizeText(input.value);
    var rows = list.querySelectorAll(".defect-responsible-option");
    rows.forEach(function (row) {
      var txt = normalizeText(row.textContent);
      row.style.display = !q || txt.indexOf(q) !== -1 ? "" : "none";
    });
  }

  searchInputs.forEach(function (inp) {
    inp.addEventListener("input", function () { applyFilter(inp); });
    applyFilter(inp);
  });
})();
(function () {
  var tables = document.querySelectorAll(".js-sortable-table");
  if (!tables.length) return;

  function toSortableValue(cell) {
    var raw = (cell.getAttribute("data-sort") || cell.textContent || "").trim();
    var normalized = raw.replace(",", ".");
    var num = parseFloat(normalized);
    if (!Number.isNaN(num) && /^-?\d+(\.\d+)?$/.test(normalized)) return num;
    return raw.toLowerCase();
  }

  Array.prototype.forEach.call(tables, function (table) {
    var headers = table.querySelectorAll("thead th.sortable");
    var tbody = table.querySelector("tbody");
    if (!headers.length || !tbody) return;
    Array.prototype.forEach.call(headers, function (th, idx) {
      th.addEventListener("click", function () {
        var isAsc = !th.classList.contains("is-asc");
        Array.prototype.forEach.call(headers, function (h) { h.classList.remove("is-asc", "is-desc"); });
        th.classList.add(isAsc ? "is-asc" : "is-desc");

        var rows = Array.prototype.slice.call(tbody.querySelectorAll("tr"));
        rows.sort(function (a, b) {
          var aCell = a.children[idx];
          var bCell = b.children[idx];
          var av = toSortableValue(aCell);
          var bv = toSortableValue(bCell);
          if (av < bv) return isAsc ? -1 : 1;
          if (av > bv) return isAsc ? 1 : -1;
          return 0;
        });
        rows.forEach(function (row) { tbody.appendChild(row); });
      });
    });
  });
})();
(function () {
  var categorySelects = document.querySelectorAll(".js-tool-category");
  var searchInputs = document.querySelectorAll(".js-tool-search");

  function normalizeText(s) {
    return String(s || "")
      .toLowerCase()
      .replace(/,/g, ".")
      .replace(/\s+/g, " ")
      .trim();
  }

  /* --- Generic combo helpers (pure DOM builders, no global state) --- */

  function combNormCoatingClass(code) {
    var c = String(code || "none").trim().toLowerCase();
    if (c === "none" || c === "yellow" || c === "brown" || c === "black" || c === "multicolor" || c === "blue" || c === "other") return c;
    return "other";
  }

  function combNormWmClass(wm) {
    var c = String(wm || "").trim().toLowerCase();
    if (c === "p" || c === "m" || c === "k" || c === "n" || c === "s" || c === "h" || c === "pw") return c;
    return "";
  }

  function combAppendInlineSpecs(card, opt, material, qty) {
    var row = document.createElement("div");
    row.className = "issue-tool-opt-inline";

    var mat = document.createElement("span");
    mat.className = "issue-tool-opt-mat";
    var m = material != null ? String(material).trim() : "";
    mat.textContent = m && m !== "—" ? m : "—";
    row.appendChild(mat);

    var coatSlot = document.createElement("span");
    coatSlot.className = "issue-tool-opt-chip-slot";
    var rawCt = (opt.getAttribute("data-issue-coating-type") || "none").trim();
    var ct = combNormCoatingClass(rawCt);
    var coatTitle = (opt.getAttribute("data-issue-coating-title") || "").trim();
    var sw = document.createElement("span");
    sw.className = "swatch swatch-" + ct;
    if (coatTitle) sw.setAttribute("title", coatTitle);
    coatSlot.appendChild(sw);
    if (ct === "none") {
      var lab = document.createElement("span");
      lab.className = "coating-inline-label";
      lab.textContent = "без покрытия";
      coatSlot.appendChild(lab);
    }
    row.appendChild(coatSlot);

    var moSlot = document.createElement("span");
    moSlot.className = "issue-tool-opt-chip-slot";
    var wm = (opt.getAttribute("data-issue-wm") || "").trim();
    var wmTitle = (opt.getAttribute("data-issue-wm-title") || "").trim();
    var wmClass = combNormWmClass(wm);
    if (!wm) {
      moSlot.className += " issue-tool-opt-mo-empty";
      moSlot.textContent = "—";
    } else if (wmClass) {
      var wmSpan = document.createElement("span");
      wmSpan.className = "wm-square wm-" + wmClass;
      wmSpan.textContent = wm;
      if (wmTitle) wmSpan.setAttribute("title", wmTitle);
      moSlot.appendChild(wmSpan);
    } else {
      moSlot.textContent = wm;
      if (wmTitle) moSlot.setAttribute("title", wmTitle);
    }
    row.appendChild(moSlot);

    var qSpan = document.createElement("span");
    qSpan.className = "issue-tool-opt-qty";
    var q = qty != null ? String(qty).trim() : "";
    qSpan.textContent = !q || q === "—" ? "—" : q + " шт";
    row.appendChild(qSpan);

    card.appendChild(row);
  }

  function combFillOptionButton(b, opt) {
    var type = (opt.getAttribute("data-issue-type") || "").trim();
    var specs = (opt.getAttribute("data-issue-specs") || "").trim();
    var material = (opt.getAttribute("data-issue-material") || "").trim();
    var qty = (opt.getAttribute("data-issue-qty") || "").trim();
    var extra = (opt.getAttribute("data-issue-extra") || "").trim();
    var fallback = (opt.textContent || "").trim();
    b.textContent = "";
    b.setAttribute("aria-label", fallback || "Инструмент");
    if (!type && !specs && !material) {
      b.textContent = fallback;
      return;
    }
    var card = document.createElement("div");
    card.className = "issue-tool-opt-card";
    if (type) {
      var ty = document.createElement("div");
      ty.className = "issue-tool-opt-type";
      ty.textContent = type;
      card.appendChild(ty);
    }
    if (specs) {
      var sp = document.createElement("div");
      sp.className = "issue-tool-opt-specs";
      sp.textContent = specs;
      card.appendChild(sp);
    }
    combAppendInlineSpecs(card, opt, material, qty);
    if (extra) {
      var ex = document.createElement("div");
      ex.className = "issue-tool-opt-extra";
      ex.textContent = extra;
      card.appendChild(ex);
    }
    b.appendChild(card);
  }

  /* --- Generic combo controller (accepts wrap element + select element) --- */

  function comboClose(wrap) {
    if (!wrap) return;
    wrap.classList.remove("is-open");
    var panel = wrap.querySelector(".js-issue-tool-combo-panel");
    var btn = wrap.querySelector(".js-issue-tool-combo-btn");
    if (panel) panel.hidden = true;
    if (btn) btn.setAttribute("aria-expanded", "false");
  }

  function comboUpdateLabel(wrap, sel) {
    var textEl = wrap && wrap.querySelector(".js-issue-tool-combo-text");
    if (!textEl || !sel) return;
    var opt = sel.options[sel.selectedIndex];
    textEl.textContent = (!opt || !opt.value) ? "Выбрать..." : (opt.textContent || "").trim();
  }

  function comboEnsurePanel(wrap, sel) {
    var panel = wrap && wrap.querySelector(".js-issue-tool-combo-panel");
    if (!sel || !panel) return;
    if (panel.getAttribute("data-built") === "1") return;
    panel.setAttribute("data-built", "1");
    panel.innerHTML = "";
    Array.prototype.forEach.call(sel.options, function (opt, idx) {
      if (idx === 0) return;
      var b = document.createElement("button");
      b.type = "button";
      b.className = "issue-tool-combo-opt";
      b.setAttribute("role", "option");
      b.setAttribute("data-opt-index", String(idx));
      combFillOptionButton(b, opt);
      b.hidden = !!opt.hidden;
      panel.appendChild(b);
    });
    panel.addEventListener("click", function (e) {
      var ob = e.target.closest(".issue-tool-combo-opt");
      if (!ob || !wrap.contains(ob) || ob.hidden) return;
      var idx = parseInt(ob.getAttribute("data-opt-index"), 10);
      if (isNaN(idx) || idx < 1) return;
      sel.selectedIndex = idx;
      try { sel.dispatchEvent(new Event("change", { bubbles: true })); } catch (eCh) {}
      comboUpdateLabel(wrap, sel);
      comboClose(wrap);
    });
  }

  function comboSyncVisibility(wrap, sel) {
    var panel = wrap && wrap.querySelector(".js-issue-tool-combo-panel");
    if (!sel || !panel || panel.getAttribute("data-built") !== "1") return;
    Array.prototype.forEach.call(panel.querySelectorAll(".issue-tool-combo-opt"), function (btn) {
      var idx = parseInt(btn.getAttribute("data-opt-index"), 10);
      var opt = sel.options[idx];
      if (!opt) return;
      btn.hidden = !!opt.hidden;
    });
  }

  function comboBindUi(wrap, sel) {
    var btn = wrap && wrap.querySelector(".js-issue-tool-combo-btn");
    if (!wrap || !sel || !btn || btn.getAttribute("data-bound") === "1") return;
    btn.setAttribute("data-bound", "1");
    btn.addEventListener("click", function (e) {
      e.preventDefault();
      e.stopPropagation();
      if (wrap.classList.contains("is-open")) {
        comboClose(wrap);
      } else {
        comboEnsurePanel(wrap, sel);
        comboSyncVisibility(wrap, sel);
        var panel = wrap.querySelector(".js-issue-tool-combo-panel");
        var b = wrap.querySelector(".js-issue-tool-combo-btn");
        if (!panel || !b) return;
        wrap.classList.add("is-open");
        panel.hidden = false;
        b.setAttribute("aria-expanded", "true");
      }
    });
    sel.addEventListener("change", function () { comboUpdateLabel(wrap, sel); });
    document.addEventListener("click", function (e) {
      if (!wrap.classList.contains("is-open")) return;
      if (wrap.contains(e.target)) return;
      comboClose(wrap);
    });
    document.addEventListener("keydown", function (e) {
      if (e.key !== "Escape") return;
      comboClose(wrap);
    });
  }

  function filterToolOptions(targetId) {
    if (!targetId) return;
    var toolSelect = document.getElementById(targetId);
    if (!toolSelect) return;
    var categorySelect = document.querySelector('.js-tool-category[data-target-select="' + targetId + '"]');
    var searchInput = document.querySelector('.js-tool-search[data-target-select="' + targetId + '"]');
    var selectedCategory = categorySelect ? categorySelect.value : "";
    var queryRaw = normalizeText(searchInput ? searchInput.value : "");
    var queryCompact = queryRaw.replace(/\.0+\b/g, "");

    Array.prototype.forEach.call(toolSelect.options, function (opt, idx) {
      if (idx === 0) { opt.hidden = false; return; }
      var optionCategory = opt.getAttribute("data-category");
      var categoryMatch = !selectedCategory || optionCategory === selectedCategory;
      var text = normalizeText(opt.textContent);
      var textCompact = text.replace(/\.0+\b/g, "");
      var searchMatch = !queryRaw || text.indexOf(queryRaw) !== -1 || textCompact.indexOf(queryCompact) !== -1;
      opt.hidden = !(categoryMatch && searchMatch);
    });

    var wrap = toolSelect.closest(".js-issue-tool-combo");
    if (wrap) {
      comboEnsurePanel(wrap, toolSelect);
      comboSyncVisibility(wrap, toolSelect);
    }
    if (toolSelect.selectedIndex > 0 && toolSelect.options[toolSelect.selectedIndex].hidden) {
      toolSelect.selectedIndex = 0;
    }
    if (wrap) comboUpdateLabel(wrap, toolSelect);
  }

  if (categorySelects.length || searchInputs.length) {
    Array.prototype.forEach.call(categorySelects, function (select) {
      var targetId = select.getAttribute("data-target-select");
      select.addEventListener("change", function () { filterToolOptions(targetId); });
      filterToolOptions(targetId);
    });
    Array.prototype.forEach.call(searchInputs, function (input) {
      var targetId = input.getAttribute("data-target-select");
      input.addEventListener("input", function () { filterToolOptions(targetId); });
      filterToolOptions(targetId);
    });
  }

  /* Initialize issue panel combo */
  var issueWrap = document.querySelector("#issue-block .js-issue-tool-combo");
  var issueSel = document.getElementById("issue-tool-select");
  if (issueWrap && issueSel) comboBindUi(issueWrap, issueSel);

  /* Initialize issue-outcome panel combo */
  var outcomeWrap = document.querySelector("#issue-outcome-block .js-issue-tool-combo");
  var outcomeSel = document.getElementById("issue-id-select");
  if (outcomeWrap && outcomeSel) {
    comboBindUi(outcomeWrap, outcomeSel);
    var outcomeSearch = document.getElementById("issue-search-input");
    if (outcomeSearch) {
      function filterOutcomeOptions() {
        var queryRaw = normalizeText(outcomeSearch.value);
        var queryCompact = queryRaw.replace(/\.0+\b/g, "");
        Array.prototype.forEach.call(outcomeSel.options, function (opt, idx) {
          if (idx === 0) { opt.hidden = false; return; }
          var text = normalizeText(opt.textContent + " " + (opt.getAttribute("data-issue-extra") || ""));
          var textCompact = text.replace(/\.0+\b/g, "");
          opt.hidden = !(!queryRaw || text.indexOf(queryRaw) !== -1 || textCompact.indexOf(queryCompact) !== -1);
        });
        comboEnsurePanel(outcomeWrap, outcomeSel);
        comboSyncVisibility(outcomeWrap, outcomeSel);
        if (outcomeSel.selectedIndex > 0 && outcomeSel.options[outcomeSel.selectedIndex].hidden) {
          outcomeSel.selectedIndex = 0;
        }
        comboUpdateLabel(outcomeWrap, outcomeSel);
      }
      outcomeSearch.addEventListener("input", filterOutcomeOptions);
    }
  }
})();
(function () {
  var categorySelect = document.getElementById("arrival-bulk-category");
  var arrivalDateInput = document.getElementById("arrival-bulk-date");
  var supplierSelect = document.getElementById("arrival-bulk-supplier");
  var addBtn = document.getElementById("arrival-bulk-add-row");
  var groupsWrap = document.getElementById("arrival-bulk-groups");
  var form = document.getElementById("arrival-bulk-form");
  var rowsJsonInput = document.getElementById("arrival-bulk-rows-json");
  if (!categorySelect || !arrivalDateInput || !supplierSelect || !addBtn || !groupsWrap || !form || !rowsJsonInput) return;

  function biotaCssToken(name) {
    return (getComputedStyle(document.documentElement).getPropertyValue(name) || "").trim();
  }

  var toolMaterialFilterOther = INV.tool_material_filter_other;
  var insertFamilyOther = INV.insert_family_other || "OTHER";
  function normalizeInsertFamilyValue(v) {
    return (v || "").trim().toUpperCase();
  }

  function buildInsertFamilyCellHtml() {
    var opts = buildOptionsHtml(INV.milling_insert_families || []);
    return (
      '<div class="arrival-field-combo js-arrival-field-combo">' +
      '<select data-k="ins_family" class="arrival-field-combo-native" tabindex="-1" aria-hidden="true">' +
      opts +
      "</select>" +
      '<button type="button" class="arrival-field-combo-btn js-arrival-combo-btn" aria-haspopup="listbox" aria-expanded="false">' +
      '<span class="arrival-field-combo-text js-arrival-combo-text">— не указано —</span>' +
      '<span class="arrival-field-combo-chevron" aria-hidden="true"></span>' +
      "</button>" +
      '<div class="arrival-field-combo-panel js-arrival-combo-panel" hidden role="listbox"></div>' +
      "</div>" +
      '<input type="text" class="ins-family-custom" data-k="ins_family_custom" maxlength="24" ' +
      'placeholder="APMT" style="display:none;margin-top:4px;max-width:100%;text-transform:uppercase">'
    );
  }

  function arrivalComboResetPanel(wrap) {
    var panel = wrap && wrap.querySelector(".js-arrival-combo-panel");
    if (panel) panel.removeAttribute("data-built");
  }

  function arrivalComboPanelEl(wrap) {
    return (wrap && wrap._floatingPanel) || (wrap && wrap.querySelector(".js-arrival-combo-panel"));
  }

  function arrivalComboClose(wrap) {
    if (!wrap) return;
    wrap.classList.remove("is-open");
    var panel = arrivalComboPanelEl(wrap);
    var btn = wrap.querySelector(".js-arrival-combo-btn");
    if (panel) {
      panel.hidden = true;
      panel.style.position = "";
      panel.style.left = "";
      panel.style.top = "";
      panel.style.width = "";
      panel.style.right = "";
      panel.style.zIndex = "";
      if (panel.parentNode === document.body) {
        wrap.appendChild(panel);
      }
    }
    wrap._floatingPanel = null;
    if (btn) btn.setAttribute("aria-expanded", "false");
  }

  function arrivalComboUpdateLabel(wrap, sel) {
    var textEl = wrap && wrap.querySelector(".js-arrival-combo-text");
    if (!textEl || !sel) return;
    var opt = sel.options[sel.selectedIndex];
    textEl.textContent = opt ? (opt.textContent || "").trim() : "";
  }

  function arrivalComboPositionPanel(wrap) {
    var panel = arrivalComboPanelEl(wrap);
    var btn = wrap.querySelector(".js-arrival-combo-btn");
    if (!panel || !btn) return;
    var rect = btn.getBoundingClientRect();
    var width = Math.max(rect.width, 140);
    panel.style.position = "fixed";
    panel.style.left = Math.max(8, Math.min(rect.left, window.innerWidth - width - 8)) + "px";
    panel.style.top = rect.bottom + 4 + "px";
    panel.style.width = width + "px";
    panel.style.right = "auto";
    panel.style.zIndex = "10000";
    requestAnimationFrame(function () {
      var pr = panel.getBoundingClientRect();
      if (pr.bottom > window.innerHeight - 8) {
        panel.style.top = Math.max(8, rect.top - pr.height - 4) + "px";
      }
    });
  }

  function arrivalComboEnsurePanel(wrap, sel) {
    var panel = wrap && wrap.querySelector(".js-arrival-combo-panel");
    if (!sel || !panel || panel.getAttribute("data-built") === "1") return;
    panel.setAttribute("data-built", "1");
    panel.innerHTML = "";
    Array.prototype.forEach.call(sel.options, function (opt, idx) {
      var b = document.createElement("button");
      b.type = "button";
      b.className = "arrival-combo-opt";
      b.setAttribute("role", "option");
      b.setAttribute("data-opt-index", String(idx));
      b.textContent = (opt.textContent || "").trim() || opt.value;
      panel.appendChild(b);
    });
    panel.addEventListener("click", function (e) {
      var ob = e.target.closest(".arrival-combo-opt");
      if (!ob || !panel.contains(ob)) return;
      var idx = parseInt(ob.getAttribute("data-opt-index"), 10);
      if (isNaN(idx) || idx < 0) return;
      sel.selectedIndex = idx;
      try {
        sel.dispatchEvent(new Event("change", { bubbles: true }));
      } catch (_eCh) {}
      arrivalComboUpdateLabel(wrap, sel);
      arrivalComboClose(wrap);
    });
  }

  function arrivalComboOpen(wrap, sel) {
    document.querySelectorAll(".js-arrival-field-combo.is-open").forEach(function (w) {
      if (w !== wrap) arrivalComboClose(w);
    });
    arrivalComboEnsurePanel(wrap, sel);
    var panel = wrap.querySelector(".js-arrival-combo-panel");
    var btn = wrap.querySelector(".js-arrival-combo-btn");
    if (!panel || !btn) return;
    wrap._floatingPanel = panel;
    document.body.appendChild(panel);
    wrap.classList.add("is-open");
    panel.hidden = false;
    btn.setAttribute("aria-expanded", "true");
    arrivalComboPositionPanel(wrap);
  }

  function arrivalComboBindUi(wrap, sel) {
    var btn = wrap && wrap.querySelector(".js-arrival-combo-btn");
    if (!wrap || !sel || !btn || btn.getAttribute("data-bound") === "1") return;
    btn.setAttribute("data-bound", "1");
    btn.addEventListener("click", function (e) {
      e.preventDefault();
      e.stopPropagation();
      if (wrap.classList.contains("is-open")) {
        arrivalComboClose(wrap);
        return;
      }
      window.setTimeout(function () {
        arrivalComboOpen(wrap, sel);
      }, 0);
    });
    sel.addEventListener("change", function () {
      arrivalComboUpdateLabel(wrap, sel);
    });
    arrivalComboUpdateLabel(wrap, sel);
    if (!window.__arrivalComboDocBound) {
      window.__arrivalComboDocBound = true;
      document.addEventListener("mousedown", function (e) {
        document.querySelectorAll(".js-arrival-field-combo.is-open").forEach(function (w) {
          var panel = arrivalComboPanelEl(w);
          var btn = w.querySelector(".js-arrival-combo-btn");
          if (btn && btn.contains(e.target)) return;
          if (panel && panel.contains(e.target)) return;
          if (w.contains(e.target)) return;
          arrivalComboClose(w);
        });
      });
      document.addEventListener("keydown", function (e) {
        if (e.key !== "Escape") return;
        document.querySelectorAll(".js-arrival-field-combo.is-open").forEach(arrivalComboClose);
      });
      window.addEventListener("resize", function () {
        document.querySelectorAll(".js-arrival-field-combo.is-open").forEach(function (w) {
          arrivalComboPositionPanel(w);
        });
      });
      window.addEventListener(
        "scroll",
        function () {
          document.querySelectorAll(".js-arrival-field-combo.is-open").forEach(function (w) {
            arrivalComboPositionPanel(w);
          });
        },
        true
      );
    }
  }

  function ensureInsertFamilySelectOption(sel, value) {
    var v = normalizeInsertFamilyValue(value);
    if (!v || v === insertFamilyOther) return;
    var found = Array.prototype.some.call(sel.options, function (o) {
      return o.value === v;
    });
    if (!found) {
      var otherOpt = Array.prototype.find.call(sel.options, function (o) {
        return o.value === insertFamilyOther;
      });
      var o = document.createElement("option");
      o.value = v;
      o.textContent = v;
      if (otherOpt) sel.insertBefore(o, otherOpt);
      else sel.appendChild(o);
    }
    sel.value = v;
    var wrap = sel.closest(".js-arrival-field-combo");
    if (wrap) {
      arrivalComboResetPanel(wrap);
      arrivalComboUpdateLabel(wrap, sel);
    }
  }

  function wireInsertFamilyCell(cell) {
    var wrap = cell.querySelector(".js-arrival-field-combo");
    var sel = cell.querySelector('select[data-k="ins_family"]');
    var cin = cell.querySelector('[data-k="ins_family_custom"]');
    if (wrap && sel) arrivalComboBindUi(wrap, sel);
    if (!sel || !cin) return;
    function syncCustom() {
      var isOther = sel.value === insertFamilyOther;
      cin.style.display = isOther ? "block" : "none";
      if (!isOther) cin.value = "";
    }
    sel.addEventListener("change", syncCustom);
    cin.addEventListener("input", function () {
      var start = cin.selectionStart;
      var end = cin.selectionEnd;
      var before = cin.value;
      cin.value = normalizeInsertFamilyValue(before);
      if (start != null && end != null) {
        var delta = cin.value.length - before.length;
        cin.setSelectionRange(Math.max(0, start + delta), Math.max(0, end + delta));
      }
    });
    syncCustom();
  }
  var arrivalCsrfEl = form.querySelector('input[name="csrfmiddlewaretoken"]');
  var arrivalCsrfToken = arrivalCsrfEl ? arrivalCsrfEl.value : "";

  function loadToolMaterialExtrasFromPage() {
    try {
      var el = document.getElementById("stock-tool-material-extras-json");
      var parsed = el ? JSON.parse(el.textContent || "[]") : [];
      return Array.isArray(parsed) ? parsed.filter(Boolean) : [];
    } catch (_e) {
      return [];
    }
  }

  var insertToolMaterialStdKeys = { "": true, carbide: true, hss: true, hss_co: true };

  function buildArrivalInsertAlloyMaterialOptions() {
    var base = [{ value: "", label: "—" }];
    (INV.insert_chipbreaker_grades || []).forEach(function (g) {
      base.push({ value: g, label: g });
    });
    base.push({ value: toolMaterialFilterOther, label: "Другое" });
    return base;
  }

  function resolveInsertArrivalRowMaterials(row) {
    if ((row.category || "") !== "insert") return;
    var tm = (row.tool_material || "").trim();
    if (tm && !insertToolMaterialStdKeys[tm]) {
      row.ins_grade = tm;
      row.tool_material = "carbide";
    } else if (!tm) {
      row.ins_grade = "";
      row.tool_material = "";
    } else {
      row.ins_grade = "";
      row.tool_material = tm;
    }
  }

  function buildArrivalToolMaterialOptions() {
    var base = [{ value: "", label: "Неизвестно" }].concat(
      (INV.tool_material_types || []).map(function (x) { return { value: x.value, label: x.label }; })
    );
    var std = {};
    base.forEach(function (o) { std[o.value] = true; });
    loadToolMaterialExtrasFromPage().forEach(function (v) {
      if (!v || std[v] || v === toolMaterialFilterOther) return;
      base.push({ value: v, label: v });
      std[v] = true;
    });
    base.push({ value: toolMaterialFilterOther, label: "Другое" });
    return base;
  }

  var toolMaterialOptions = buildArrivalToolMaterialOptions();

  function addExtraToToolMaterialOptions(value) {
    var v = (value || "").trim();
    if (!v || v === toolMaterialFilterOther) return;
    if (toolMaterialOptions.some(function (o) { return o.value === v; })) return;
    var otherIdx = -1;
    for (var i = 0; i < toolMaterialOptions.length; i += 1) {
      if (toolMaterialOptions[i].value === toolMaterialFilterOther) {
        otherIdx = i;
        break;
      }
    }
    var opt = { value: v, label: v };
    if (otherIdx >= 0) toolMaterialOptions.splice(otherIdx, 0, opt);
    else toolMaterialOptions.push(opt);
  }

  function ensureToolMaterialSelectOption(sel, value) {
    var v = (value || "").trim();
    if (!v) return;
    addExtraToToolMaterialOptions(v);
    var found = Array.prototype.some.call(sel.options, function (o) { return o.value === v; });
    if (!found) {
      var otherOpt = Array.prototype.find.call(sel.options, function (o) {
        return o.value === toolMaterialFilterOther;
      });
      var o = document.createElement("option");
      o.value = v;
      o.textContent = v;
      if (otherOpt) sel.insertBefore(o, otherOpt);
      else sel.appendChild(o);
    }
    sel.value = v;
  }

  function registerToolMaterialExtra(value) {
    var v = (value || "").trim();
    if (!v) return Promise.resolve(null);
    var body = new URLSearchParams();
    body.set("action", "register_tool_material_extra");
    body.set("value", v);
    if (arrivalCsrfToken) body.set("csrfmiddlewaretoken", arrivalCsrfToken);
    return fetch(form.getAttribute("action") || window.location.pathname, {
      method: "POST",
      headers: {
        "Content-Type": "application/x-www-form-urlencoded",
        "X-Requested-With": "XMLHttpRequest",
      },
      body: body.toString(),
      credentials: "same-origin",
    })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data && data.ok && data.value) return data.value;
        return null;
      })
      .catch(function () { return null; });
  }

  function applyCustomToolMaterial(tmSel, tmCustom) {
    var v = (tmCustom.value || "").trim();
    if (!v || tmSel.value !== toolMaterialFilterOther) return;
    registerToolMaterialExtra(v).then(function (saved) {
      var use = saved || v;
      ensureToolMaterialSelectOption(tmSel, use);
      tmCustom.value = "";
      tmCustom.style.display = "none";
    });
  }

  var coatingOptions = (INV.coating_types || []).map(function (x) { return { value: x.value, label: x.label }; });

  var coatingSelectOptions = [
    { value: "none", label: "нет", bg: "#aab3c7", color: "#0f172a" },
    { value: "yellow", label: "🟨 Жёлтое", bg: "#f6c343", color: "#0f172a" },
    { value: "brown", label: "🟫 Коричн.", bg: "#8b5a2b", color: "#ffffff" },
    { value: "black", label: "⬛ Чёрное", bg: "#151515", color: "#ffffff" },
    { value: "multicolor", label: "🌈 Цветн.", bg: "#4f5d82", color: "#ffffff" },
    { value: "blue", label: "🟦 Синее", bg: "#2877f0", color: "#ffffff" },
    { value: "other", label: "🟪 Другое", bioBg: "--bio-filter-border", color: "#ffffff" }
  ];
  function buildSelect(options, selected) {
    var sel = document.createElement("select");
    options.forEach(function (opt) {
      var o = document.createElement("option");
      o.value = opt.value;
      o.textContent = opt.label;
      if (opt.title) o.setAttribute("title", opt.title);
      if (opt.bioBg) {
        var bv = biotaCssToken(opt.bioBg);
        if (bv) o.style.backgroundColor = bv;
      } else if (opt.bg) {
        o.style.backgroundColor = opt.bg;
      }
      if (opt.color) o.style.color = opt.color;
      if ((selected || "") === opt.value) o.selected = true;
      sel.appendChild(o);
    });
    return sel;
  }

  var wmOptionTitles = { "": "?" };
  (INV.work_material_types || []).forEach(function (x) { wmOptionTitles[x.value] = x.label; });

  var coatingOptionTitles = {};
  (INV.coating_types || []).forEach(function (x) { coatingOptionTitles[x.value] = x.hoverTitle; });

  var arrivalRowSeq = 0;
  var wmSelectTheme = {
    "": { bg: "#8b949e", color: "#fff" },
    "P": { bg: "#2f72ff", color: "#fff" },
    "M": { bg: "#f6b93b", color: "#111" },
    "K": { bg: "#e25a5a", color: "#fff" },
    "N": { bg: "#2bb673", color: "#fff" },
    "S": { bg: "#8f7cff", color: "#fff" },
    "H": { bg: "#6d6d6d", color: "#fff" },
    "PW": { bg: "#eef2f7", color: "#1a1d21" }
  };
  var coatingSelectTheme = {
    "none": { bg: "#aab3c7", color: "#0f172a" },
    "yellow": { bg: "#f6c343", color: "#0f172a" },
    "brown": { bg: "#8b5a2b", color: "#fff" },
    "black": { bg: "#151515", color: "#fff" },
    "multicolor": { bgImage: "linear-gradient(120deg, #f44336 0%, #ff9800 20%, #ffeb3b 35%, #4caf50 52%, #2196f3 70%, #9c27b0 100%)", color: "#fff" },
    "blue": { bg: "#2877f0", color: "#fff" },
    "other": { bioBg: "--bio-filter-border", color: "#fff" }
  };
  function applyWmSelectClass(sel) {
    if (!sel) return;
    sel.classList.remove("wm-all", "wm-p", "wm-m", "wm-k", "wm-n", "wm-s", "wm-h", "wm-pw");
    var rawValue = sel.value || "";
    var value = rawValue.toLowerCase();
    sel.classList.add(value ? ("wm-" + value) : "wm-all");
    var theme = wmSelectTheme[rawValue] || wmSelectTheme[""];
    sel.style.backgroundImage = "none";
    sel.style.backgroundColor = theme.bg;
    sel.style.color = theme.color;
  }
  function buildColoredWmSelect(selected) {
    var opts = [
      { value: "", label: "?", bg: "#8b949e", color: "#ffffff" },
      { value: "P", label: "P", bg: "#2f72ff", color: "#ffffff" },
      { value: "M", label: "M", bg: "#f6b93b", color: "#111111" },
      { value: "K", label: "K", bg: "#e25a5a", color: "#ffffff" },
      { value: "N", label: "N", bg: "#2bb673", color: "#ffffff" },
      { value: "S", label: "S", bg: "#8f7cff", color: "#ffffff" },
      { value: "H", label: "H", bg: "#6d6d6d", color: "#ffffff" },
      { value: "PW", label: "PW", bg: "#eef2f7", color: "#1a1d21" },
    ];
    var sel = buildSelect(opts, selected || "");
    Array.prototype.forEach.call(sel.options, function (o) {
      var t = wmOptionTitles[o.value];
      if (t) o.setAttribute("title", t);
    });
    sel.setAttribute("data-k", "work_material");
    sel.classList.add("arrival-wm-select");
    applyWmSelectClass(sel);
    sel.addEventListener("change", function () {
      applyWmSelectClass(sel);
    });
    return sel;
  }
  function applyCoatingSelectClass(sel) {
    if (!sel) return;
    coatingOptions.forEach(function (opt) {
      sel.classList.remove("coating-" + opt.value);
    });
    var v = sel.value || "none";
    sel.classList.add("coating-" + v);
    var theme = coatingSelectTheme[v] || coatingSelectTheme.none;
    sel.style.backgroundImage = theme.bgImage || "none";
    if (theme.bioBg) {
      var tb = biotaCssToken(theme.bioBg);
      sel.style.backgroundColor = tb || "transparent";
    } else {
      sel.style.backgroundColor = theme.bg || "transparent";
    }
    sel.style.color = theme.color || "#fff";
  }
  function buildColoredCoatingSelect(selected) {
    var sel = buildSelect(coatingSelectOptions, selected || "none");
    Array.prototype.forEach.call(sel.options, function (o) {
      var t = coatingOptionTitles[o.value];
      if (t) o.setAttribute("title", t);
    });
    sel.setAttribute("data-k", "coating_type");
    sel.classList.add("arrival-coating-select");
    applyCoatingSelectClass(sel);
    sel.addEventListener("change", function () {
      applyCoatingSelectClass(sel);
    });
    return sel;
  }

  function buildOptionsHtml(items) {
    return items.map(function (x) {
      return '<option value="' + x.value + '">' + x.label + "</option>";
    }).join("");
  }

  function buildInsertIsoCodeOptionsHtml(items) {
    return (items || []).map(function (x) {
      var code = x.value || "";
      var full = x.label || code;
      var titleAttr = full !== code ? ' title="' + String(full).replace(/"/g, "&quot;") + '"' : "";
      return '<option value="' + code + '"' + titleAttr + ">" + code + "</option>";
    }).join("");
  }

  function buildTapStandardOptionsHtml(items) {
    return items.map(function (x) {
      return '<option value="' + x.value + '">' + (x.value === "metric" ? "M" : x.label) + '</option>';
    }).join("");
  }

  function buildTapHoleOptionsHtml(items) {
    return items.map(function (x) {
      var lbl = x.value === "through" ? "Скв" : (x.value === "blind" ? "Глх" : (x.value === "universal" ? "Унив" : x.label));
      return '<option value="' + x.value + '">' + lbl + '</option>';
    }).join("");
  }

  function arrivalRequiredDiamCell(dataKey) {
    return (
      '<td class="short-col"><input type="number" step="0.01" min="0.01" class="arrival-diam-input" data-k="' +
      dataKey +
      '" required aria-required="true" title="Обязательно">'
    );
  }

  var arrivalDiamRequiredByCategory = {
    drill: { key: "dr_diameter_mm", label: "диаметр D (мм) для сверла" },
    end_mill: { key: "em_diameter_mm", label: "диаметр D (мм) для фрезы" },
    center_drill: { key: "cd_diameter_mm", label: "диаметр D (мм) для центровки" },
    countersink: { key: "cs_diameter_mm", label: "диаметр D (мм) для зенкера" },
  };

  function validateInsertRow(tr, rowIndex) {
    var bad = false;
    ["ins_shape", "ins_edge_code", "ins_thickness_code", "ins_nose_code", "ins_machining_app"].forEach(function (k) {
        var el = tr.querySelector('[data-k="' + k + '"]');
        if (!el || !(el.value || "").trim()) {
          if (el) el.classList.add("is-invalid");
          bad = true;
        }
      }
    );
    return bad
      ? [
          {
            msg: "Строка " + rowIndex + ": для пластины укажите форму, L, S, R и вид обработки.",
            el: null,
          },
        ]
      : [];
  }

  function clearArrivalBulkErrors() {
    var box = document.getElementById("arrival-bulk-errors");
    if (box) {
      box.hidden = true;
      box.textContent = "";
    }
    groupsWrap.querySelectorAll(".is-invalid").forEach(function (el) {
      el.classList.remove("is-invalid");
    });
  }

  function showArrivalBulkError(message) {
    var box = document.getElementById("arrival-bulk-errors");
    if (!box) return;
    box.textContent = message;
    box.hidden = !message;
    if (message) box.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }

  function isPositiveNumberField(el) {
    if (!el) return false;
    var v = String(el.value || "").trim().replace(",", ".");
    if (!v) return false;
    var n = parseFloat(v);
    return !isNaN(n) && n > 0;
  }

  function validateArrivalBulkRows() {
    var issues = [];
    groupsWrap.querySelectorAll("tr[data-arrival-row]").forEach(function (tr, i) {
      var cat = tr.getAttribute("data-category") || "";
      var wmEl = tr.querySelector('[data-k="work_material"]');
      if (!wmEl || !(wmEl.value || "").trim()) {
        if (wmEl) wmEl.classList.add("is-invalid");
        issues.push({
          msg: "Строка " + (i + 1) + ": укажите хотя бы одну группу материала обработки (P, M, K…).",
          el: wmEl,
        });
      }
      if (cat === "insert") {
        issues = issues.concat(validateInsertRow(tr, i + 1));
        return;
      }
      var spec = arrivalDiamRequiredByCategory[cat];
      if (!spec) return;
      var el = tr.querySelector('[data-k="' + spec.key + '"]');
      if (!isPositiveNumberField(el)) {
        if (el) el.classList.add("is-invalid");
        issues.push({ msg: "Строка " + (i + 1) + ": укажите " + spec.label + ".", el: el });
      }
    });
    return issues;
  }

  var arrivalGroupTitles = {
    end_mill: "Фрезы",
    tap: "Резьбовой инструмент",
    center_drill: "Центровки",
    countersink: "Зенкера",
    drill: "Сверла",
    insert: "Пластинки",
  };

  var insertColTips = INV.insert_column_tooltips || {};

  function escapeThTitle(s) {
    return String(s || "").replace(/"/g, "&quot;");
  }

  function insertArrivalTh(key, label, cls) {
    var tip = insertColTips[key];
    var c = cls ? ' class="' + cls + '"' : "";
    var ti = tip ? ' title="' + escapeThTitle(tip) + '"' : "";
    return "<th" + c + ti + ">" + label + "</th>";
  }

  function escAttr(s) {
    return String(s || "").replace(/[&<>"']/g, function (c) {
      return ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c];
    });
  }

  function insertMachiningAppIconSvg(app) {
    var svgOpen = '<svg class="insert-app-icon" viewBox="0 0 20 20" width="18" height="18" aria-hidden="true">';
    if (app === "1") {
      return (
        svgOpen +
        '<path fill="currentColor" d="M10 2.2 12.4 6h4l-3.4 2.5 1.3 4.5L10 10.8 6.7 13l1.3-4.5L4.6 6h4L10 2.2z"/></svg>'
      );
    }
    if (app === "2") {
      return (
        svgOpen +
        '<path fill="currentColor" d="M2.5 2.5h5v15h-5v-15zm10 0h5v15h-5v-15zM7.5 8.5h5v3h-5v-3z"/></svg>'
      );
    }
    return svgOpen + '<circle cx="10" cy="10" r="7.2" fill="currentColor"/></svg>';
  }

  function parseCsvCodes(raw) {
    return String(raw || "")
      .split(",")
      .map(function (s) {
        return s.trim();
      })
      .filter(Boolean);
  }

  function syncMultiToggleHidden(picker, btnSelector, hidden, attrName) {
    var vals = [];
    picker.querySelectorAll(btnSelector + ".is-active").forEach(function (btn) {
      var v = btn.getAttribute(attrName);
      if (v) vals.push(v);
    });
    vals.sort();
    hidden.value = vals.join(",");
    hidden.classList.remove("is-invalid");
  }

  function buildInsertMachiningAppCellHtml(defaultCsv) {
    var apps = INV.insert_machining_applications || [
      { value: "1", label: "Чистовая" },
      { value: "2", label: "Получистовая" },
      { value: "3", label: "Черновая" },
    ];
    var selected = {};
    parseCsvCodes(defaultCsv || "").forEach(function (v) {
      selected[v] = true;
    });
    var parts = ['<td class="insert-app-col"><div class="insert-app-picker" role="group" aria-label="Вид обработки">'];
    apps.forEach(function (a) {
      var active = selected[a.value] ? " is-active" : "";
      parts.push(
        '<button type="button" class="insert-app-opt' +
          active +
          '" data-app="' +
          escAttr(a.value) +
          '" title="' +
          escAttr(a.label) +
          '" aria-pressed="' +
          (selected[a.value] ? "true" : "false") +
          '">' +
          insertMachiningAppIconSvg(a.value) +
          '<span class="insert-app-sr">' +
          escAttr(a.label) +
          "</span></button>"
      );
    });
    parts.push('<input type="hidden" data-k="ins_machining_app" value="' + escAttr(parseCsvCodes(defaultCsv).join(",")) + '">');
    parts.push("</div></td>");
    return parts.join("");
  }

  function wireInsertMachiningAppPicker(tr) {
    var picker = tr.querySelector(".insert-app-picker");
    if (!picker) return;
    var hidden = picker.querySelector('[data-k="ins_machining_app"]');
    if (!hidden) return;
    picker.querySelectorAll(".insert-app-opt").forEach(function (btn) {
      btn.addEventListener("click", function (ev) {
        ev.preventDefault();
        ev.stopPropagation();
        btn.classList.toggle("is-active");
        btn.setAttribute("aria-pressed", btn.classList.contains("is-active") ? "true" : "false");
        syncMultiToggleHidden(picker, ".insert-app-opt", hidden, "data-app");
      });
    });
  }

  var arrivalWmMultiTheme = {
    P: { bg: "#2f72ff", color: "#fff" },
    M: { bg: "#f6b93b", color: "#111" },
    K: { bg: "#e25a5a", color: "#fff" },
    N: { bg: "#2bb673", color: "#fff" },
    S: { bg: "#8f7cff", color: "#fff" },
    H: { bg: "#6d6d6d", color: "#fff" },
    PW: { bg: "#eef2f7", color: "#1a1d21" },
  };

  function buildArrivalWmMultiPickerHtml(selectedCsv) {
    var selected = {};
    parseCsvCodes(selectedCsv || "").forEach(function (v) {
      selected[v] = true;
    });
    var opts = [
      { value: "P", label: "P" },
      { value: "M", label: "M" },
      { value: "K", label: "K" },
      { value: "N", label: "N" },
      { value: "S", label: "S" },
      { value: "H", label: "H" },
      { value: "PW", label: "PW" },
    ];
    var parts = ['<div class="arrival-wm-multi-picker" role="group" aria-label="Материал обработки">'];
    opts.forEach(function (o) {
      var active = selected[o.value] ? " is-active" : "";
      var theme = arrivalWmMultiTheme[o.value] || {};
      var style =
        theme.bg ? ' style="background:' + theme.bg + ";color:" + (theme.color || "#fff") + ';"' : "";
      var title = wmOptionTitles[o.value] || o.label;
      parts.push(
        '<button type="button" class="arrival-wm-opt arrival-wm-opt--' +
          o.value.toLowerCase() +
          active +
          '" data-wm="' +
          escAttr(o.value) +
          '" title="' +
          escAttr(title) +
          '" aria-pressed="' +
          (selected[o.value] ? "true" : "false") +
          '"' +
          style +
          ">" +
          escAttr(o.label) +
          "</button>"
      );
    });
    parts.push(
      '<input type="hidden" data-k="work_material" value="' + escAttr(parseCsvCodes(selectedCsv).join(",")) + '">'
    );
    parts.push("</div>");
    return parts.join("");
  }

  function wireArrivalWmMultiPicker(tr) {
    var picker = tr.querySelector(".arrival-wm-multi-picker");
    if (!picker) return;
    var hidden = picker.querySelector('[data-k="work_material"]');
    if (!hidden) return;
    picker.querySelectorAll(".arrival-wm-opt").forEach(function (btn) {
      btn.addEventListener("click", function (ev) {
        ev.preventDefault();
        ev.stopPropagation();
        btn.classList.toggle("is-active");
        btn.setAttribute("aria-pressed", btn.classList.contains("is-active") ? "true" : "false");
        syncMultiToggleHidden(picker, ".arrival-wm-opt", hidden, "data-wm");
      });
    });
  }

  var arrivalGroupHeadHtml = {
    end_mill: '<tr><th>Тип фрезы</th><th class="short-col">D</th><th class="short-col">R</th><th class="short-col">L</th><th class="short-col">Lc</th><th class="short-col">Z</th><th class="short-col">D осн</th><th class="stack-words">Материал<br>инструмента</th><th>Покрытие</th><th class="stack-words">Материал<br>обработки</th><th class="qty-col">Кол-во</th><th></th></tr>',
    tap: '<tr><th class="tap-size-col">Размер</th><th class="tap-std-col">Стандарт</th><th class="tap-step-col">Шаг</th><th class="tap-tpi-col">TPI</th><th class="tap-l-col">L</th><th class="tap-lc-col">Lc</th><th class="tap-hole-col">Тип</th><th>Тип инструмента</th><th class="short-col">D осн</th><th class="stack-words">Материал<br>инструмента</th><th>Покрытие</th><th class="stack-words">Материал<br>обработки</th><th class="qty-col">Кол-во</th><th></th></tr>',
    center_drill: '<tr><th class="short-col">D</th><th class="short-col">L</th><th class="short-col">Угол</th><th class="short-col">D осн</th><th class="stack-words">Материал<br>инструмента</th><th>Покрытие</th><th class="stack-words">Материал<br>обработки</th><th class="qty-col">Кол-во</th><th></th></tr>',
    countersink: '<tr><th>Тип</th><th class="short-col">D</th><th class="short-col">Угол</th><th class="short-col">L</th><th class="short-col">Z</th><th class="short-col">D осн</th><th class="stack-words">Материал<br>инструмента</th><th>Покрытие</th><th class="stack-words">Материал<br>обработки</th><th class="qty-col">Кол-во</th><th></th></tr>',
    drill: '<tr><th class="short-col">D</th><th class="short-col">L</th><th class="short-col">Lc</th><th class="short-col">Угол</th><th class="short-col">D осн</th><th class="stack-words">Материал<br>инструмента</th><th>Покрытие</th><th class="stack-words">Материал<br>обработки</th><th class="qty-col">Кол-во</th><th></th></tr>',
    insert:
      "<tr>" +
      insertArrivalTh("family", "Семейство") +
      insertArrivalTh("shape", "Форма") +
      insertArrivalTh("edge_l", "L", "short-col insert-code-col") +
      insertArrivalTh("thickness_s", "S", "short-col insert-code-col") +
      insertArrivalTh("radius_r", "R", "short-col insert-code-col") +
      insertArrivalTh("machining_application", "Обр.", "insert-app-col") +
      insertArrivalTh("tool_material", "Сплав", "stack-words tm-col-tool-material") +
      insertArrivalTh("coating", "Покрытие") +
      insertArrivalTh("work_material", "Материал<br>обработки", "stack-words") +
      insertArrivalTh("quantity", "Кол-во", "qty-col") +
      insertArrivalTh("row_remove", "×") +
      "</tr>",
  };

  function ensureGroup(cat) {
    var groupId = "arrival-group-" + cat;
    var group = document.getElementById(groupId);
    if (group) return group;
    group = document.createElement("div");
    group.className = "arrival-group";
    group.id = groupId;
    var title = arrivalGroupTitles[cat] || "Инструмент";
    var headHtml = arrivalGroupHeadHtml[cat] || arrivalGroupHeadHtml.drill;
    group.innerHTML = '' +
      '<h4>' + title + '</h4>' +
      '<div class="table-wrap arrival-bulk-table-wrap">' +
        '<table class="data-grid arrival-bulk-table">' +
          '<thead>' + headHtml + '</thead>' +
          '<tbody class="arrival-group-body"></tbody>' +
        '</table>' +
      '</div>';
    groupsWrap.appendChild(group);
    return group;
  }

  function addRow() {
    var cat = (categorySelect.value || "").trim();
    if (!cat) {
      showArrivalBulkError("Сначала выберите категорию инструмента.");
      categorySelect.focus();
      return;
    }
    if (!arrivalGroupTitles[cat]) return;
    var group = ensureGroup(cat);
    var body = group.querySelector(".arrival-group-body");
    var tr = document.createElement("tr");
    arrivalRowSeq += 1;
    tr.setAttribute("data-arrival-row", "1");
    tr.setAttribute("data-category", cat);
    var cells = [];
    if (cat === "end_mill") {
      cells.push('<td><select data-k="mill_type">' + buildOptionsHtml(INV.end_mill_types || []) + '</select></td>');
      cells.push(arrivalRequiredDiamCell("em_diameter_mm"));
      cells.push('<td class="short-col"><input type="number" step="0.01" data-k="em_corner_radius_mm"></td>');
      cells.push('<td class="short-col"><input type="number" step="0.01" data-k="em_overall_length_mm"></td>');
      cells.push('<td class="short-col"><input type="number" step="0.01" data-k="em_cutting_length_mm"></td>');
      cells.push('<td class="short-col"><input type="number" data-k="em_flutes_count"></td>');
      cells.push('<td class="short-col"><input type="number" step="0.01" data-k="main_diameter_mm"></td>');
      cells.push('<td class="tm-cell tm-cell-tool-material"></td>');
      cells.push('<td class="co-cell"></td>');
      cells.push('<td class="wm-cell"></td>');
      cells.push('<td class="qty-col"><input type="number" min="1" value="1" data-k="quantity"></td>');
    } else if (cat === "tap") {
      cells.push('<td class="tap-size-col"><input type="text" data-k="size_label" placeholder="M2"></td>');
      cells.push('<td class="tap-std-col"><select data-k="thread_standard">' + buildTapStandardOptionsHtml(INV.thread_standards || []) + '</select></td>');
      cells.push('<td class="tap-step-col"><input type="number" step="0.001" data-k="tap_pitch_mm"></td>');
      cells.push('<td class="tap-tpi-col"><input type="number" data-k="tap_tpi"></td>');
      cells.push('<td class="tap-l-col"><input type="number" step="0.01" data-k="tap_overall_length_mm"></td>');
      cells.push('<td class="tap-lc-col"><input type="number" step="0.01" data-k="tap_cutting_length_mm"></td>');
      cells.push('<td class="tap-hole-col"><select data-k="hole_type">' + buildTapHoleOptionsHtml(INV.tap_hole_types || []) + '</select></td>');
      cells.push('<td><select data-k="tap_type">' + buildOptionsHtml(INV.tap_tool_types || []) + '</select></td>');
      cells.push('<td class="short-col"><input type="number" step="0.01" data-k="main_diameter_mm"></td>');
      cells.push('<td class="tm-cell tm-cell-tool-material"></td>');
      cells.push('<td class="co-cell"></td>');
      cells.push('<td class="wm-cell"></td>');
      cells.push('<td class="qty-col"><input type="number" min="1" value="1" data-k="quantity"></td>');
    } else if (cat === "center_drill") {
      cells.push(arrivalRequiredDiamCell("cd_diameter_mm"));
      cells.push('<td class="short-col"><input type="number" step="0.01" data-k="cd_overall_length_mm"></td>');
      cells.push('<td class="short-col"><select data-k="cd_angle_deg">' + buildOptionsHtml(INV.center_drill_angles || []) + '</select></td>');
      cells.push('<td class="short-col"><input type="number" step="0.01" data-k="main_diameter_mm"></td>');
      cells.push('<td class="tm-cell tm-cell-tool-material"></td>');
      cells.push('<td class="co-cell"></td>');
      cells.push('<td class="wm-cell"></td>');
      cells.push('<td class="qty-col"><input type="number" min="1" value="1" data-k="quantity"></td>');
    } else if (cat === "countersink") {
      cells.push('<td><select data-k="cs_type">' + buildOptionsHtml(INV.countersink_types || []) + '</select></td>');
      cells.push(arrivalRequiredDiamCell("cs_diameter_mm"));
      cells.push('<td class="short-col"><select data-k="cs_angle_deg">' + buildOptionsHtml(INV.countersink_angles || []) + '</select></td>');
      cells.push('<td class="short-col"><input type="number" step="0.01" data-k="cs_overall_length_mm"></td>');
      cells.push('<td class="short-col"><input type="number" data-k="cs_flutes_count"></td>');
      cells.push('<td class="short-col"><input type="number" step="0.01" data-k="main_diameter_mm"></td>');
      cells.push('<td class="tm-cell tm-cell-tool-material"></td>');
      cells.push('<td class="co-cell"></td>');
      cells.push('<td class="wm-cell"></td>');
      cells.push('<td class="qty-col"><input type="number" min="1" value="1" data-k="quantity"></td>');
    } else if (cat === "insert") {
      cells.push('<td class="ins-family-cell">' + buildInsertFamilyCellHtml() + "</td>");
      cells.push('<td><select data-k="ins_shape" required>' + buildOptionsHtml(INV.insert_shapes || []) + '</select></td>');
      cells.push('<td class="short-col insert-code-col"><select data-k="ins_edge_code" required>' + buildInsertIsoCodeOptionsHtml(INV.insert_edge_length_codes || []) + "</select></td>");
      cells.push('<td class="short-col insert-code-col"><select data-k="ins_thickness_code" required>' + buildInsertIsoCodeOptionsHtml(INV.insert_thickness_codes || []) + "</select></td>");
      cells.push('<td class="short-col insert-code-col"><select data-k="ins_nose_code" required>' + buildInsertIsoCodeOptionsHtml(INV.insert_nose_radius_codes || []) + "</select></td>");
      cells.push(buildInsertMachiningAppCellHtml(""));
      cells.push('<td class="tm-cell tm-cell-tool-material"></td>');
      cells.push('<td class="co-cell"></td>');
      cells.push('<td class="wm-cell"></td>');
      cells.push('<td class="qty-col"><input type="number" min="1" value="1" data-k="quantity"></td>');
    } else if (cat === "drill") {
      cells.push(arrivalRequiredDiamCell("dr_diameter_mm"));
      cells.push('<td class="short-col"><input type="number" step="0.01" data-k="dr_overall_length_mm"></td>');
      cells.push('<td class="short-col"><input type="number" step="0.01" data-k="dr_cutting_length_mm"></td>');
      cells.push('<td class="short-col"><input type="number" step="0.01" data-k="dr_angle_deg"></td>');
      cells.push('<td class="short-col"><input type="number" step="0.01" data-k="main_diameter_mm"></td>');
      cells.push('<td class="tm-cell tm-cell-tool-material"></td>');
      cells.push('<td class="co-cell"></td>');
      cells.push('<td class="wm-cell"></td>');
      cells.push('<td class="qty-col"><input type="number" min="1" value="1" data-k="quantity"></td>');
    }
    cells.push('<td><button type="button" class="btn btn-ghost js-arrival-row-remove">×</button></td>');
    tr.innerHTML = cells.join("");
    var insFamilyCell = tr.querySelector(".ins-family-cell");
    if (insFamilyCell) wireInsertFamilyCell(insFamilyCell);
    wireInsertMachiningAppPicker(tr);
    var tmCell = tr.querySelector(".tm-cell-tool-material");
    var tmOpts = cat === "insert" ? buildArrivalInsertAlloyMaterialOptions() : toolMaterialOptions;
    var tmDefault = "";
    tmCell.appendChild(buildSelect(tmOpts, tmDefault));
    var tmSel = tmCell.querySelector("select");
    tmSel.setAttribute("data-k", "tool_material");
    var tmCustom = document.createElement("input");
    tmCustom.type = "text";
    tmCustom.maxLength = 80;
    tmCustom.className = "tm-tool-material-custom";
    tmCustom.setAttribute("data-k", "tool_material_custom");
    tmCustom.style.display = "none";
    tmCustom.style.marginTop = "4px";
    tmCustom.style.maxWidth = "100%";
    tmCustom.placeholder = "Свой материал";
    tmCell.appendChild(tmCustom);
    tmSel.addEventListener("change", function () {
      var isO = tmSel.value === toolMaterialFilterOther;
      tmCustom.style.display = isO ? "block" : "none";
      if (!isO) tmCustom.value = "";
    });
    tmCustom.addEventListener("blur", function () {
      applyCustomToolMaterial(tmSel, tmCustom);
    });
    tmCustom.addEventListener("keydown", function (e) {
      if (e.key === "Enter") {
        e.preventDefault();
        tmCustom.blur();
      }
    });
    tr.querySelector(".co-cell").appendChild(buildColoredCoatingSelect("none"));
    var wmCell = tr.querySelector(".wm-cell");
    wmCell.innerHTML = buildArrivalWmMultiPickerHtml("");
    wireArrivalWmMultiPicker(tr);
    body.appendChild(tr);
  }

  addBtn.addEventListener("click", addRow);
  categorySelect.addEventListener("change", function () {
    clearArrivalBulkErrors();
  });

  var arrivalBlock = document.getElementById("arrival-block");
  if (arrivalBlock) {
    arrivalBlock.addEventListener("keydown", function (e) {
      if (e.key !== "Enter") return;
      var t = e.target;
      if (!t) return;
      if (t.tagName === "TEXTAREA") return;
      if (t.type === "submit" || (t.tagName === "BUTTON" && (t.type || "") === "submit")) return;
      e.preventDefault();
    });
  }

  groupsWrap.addEventListener("input", function (e) {
    var t = e.target;
    if (!t || !t.classList || !t.classList.contains("is-invalid")) return;
    if (isPositiveNumberField(t)) t.classList.remove("is-invalid");
  });

  form.addEventListener("submit", function (e) {
    clearArrivalBulkErrors();
    var issues = validateArrivalBulkRows();
    if (issues.length) {
      e.preventDefault();
      showArrivalBulkError(issues.map(function (x) { return x.msg; }).join(" "));
      if (issues[0].el) issues[0].el.focus();
      return;
    }

    var rows = [];
    groupsWrap.querySelectorAll("tr[data-arrival-row]").forEach(function (tr) {
      var row = { category: tr.getAttribute("data-category") || "" };
      tr.querySelectorAll("[data-k]").forEach(function (el) {
        var k = el.getAttribute("data-k");
        if (k === "tool_material_custom" || k === "ins_family_custom") return;
        if (k === "tool_material" && (el.value || "") === toolMaterialFilterOther) {
          var cin = tr.querySelector('[data-k="tool_material_custom"]');
          row.tool_material = (cin && cin.value || "").trim();
        } else if (k === "ins_family") {
          if ((el.value || "") === insertFamilyOther) {
            var fin = tr.querySelector('[data-k="ins_family_custom"]');
            row.ins_family = normalizeInsertFamilyValue(fin && fin.value || "");
          } else {
            row.ins_family = normalizeInsertFamilyValue(el.value || "");
          }
        } else {
          row[k] = (el.value || "").trim();
        }
      });
      row.movement_date = (arrivalDateInput.value || "").trim();
      row.supplier_name = (supplierSelect.value || "").trim();
      resolveInsertArrivalRowMaterials(row);
      rows.push(row);
    });
    if (!rows.length) {
      e.preventDefault();
      showArrivalBulkError("Добавьте хотя бы одну строку прихода.");
      return;
    }
    rowsJsonInput.value = JSON.stringify(rows);
    showArrivalBulkError("");
  });

  form.addEventListener("submit", function () {
    groupsWrap.querySelectorAll(".ins-family-custom").forEach(function (cin) {
      var tr = cin.closest("tr[data-arrival-row]");
      if (!tr) return;
      var sel = tr.querySelector('select[data-k="ins_family"]');
      if (!sel || sel.value !== insertFamilyOther) return;
      var v = normalizeInsertFamilyValue(cin.value || "");
      if (v) ensureInsertFamilySelectOption(sel, v);
    });
    groupsWrap.querySelectorAll(".tm-tool-material-custom").forEach(function (cin) {
      var tr = cin.closest("tr[data-arrival-row]");
      if (!tr) return;
      var sel = tr.querySelector('select[data-k="tool_material"]');
      if (!sel || sel.value !== toolMaterialFilterOther) return;
      var v = (cin.value || "").trim();
      if (v) ensureToolMaterialSelectOption(sel, v);
    });
  }, true);

  groupsWrap.addEventListener("click", function (e) {
    var rm = e.target.closest(".js-arrival-row-remove");
    if (!rm) return;
    var row = rm.closest("tr[data-arrival-row]");
    if (row) row.remove();
    var grp = rm.closest(".arrival-group");
    if (grp && !grp.querySelector("tr[data-arrival-row]")) grp.remove();
  });

  document.addEventListener("biota-theme-change", function () {
    document.querySelectorAll(".arrival-coating-select").forEach(function (sel) {
      applyCoatingSelectClass(sel);
      coatingSelectOptions.forEach(function (opt) {
        var o = Array.prototype.find.call(sel.options, function (x) {
          return x.value === opt.value;
        });
        if (!o) return;
        if (opt.bioBg) {
          var bv = biotaCssToken(opt.bioBg);
          if (bv) o.style.backgroundColor = bv;
        } else if (opt.bg) {
          o.style.backgroundColor = opt.bg;
        }
      });
    });
  });
})();
(function () {
  var editableCells = document.querySelectorAll(".stock-inline-edit");
  if (!editableCells.length) return;
  var csrfEl = document.querySelector('input[name="csrfmiddlewaretoken"]');
  var csrfToken = csrfEl ? csrfEl.value : "";
  var activeCell = null;

  var millTypeLabels = {};
  (INV.end_mill_types || []).forEach(function (x) { millTypeLabels[x.value] = x.label; });

  var toolMaterialLabels = { "": "Неизвестно" };
  (INV.tool_material_types || []).forEach(function (x) { toolMaterialLabels[x.value] = x.label; });

  var toolMaterialFilterOtherStock = INV.tool_material_filter_other;
  try {
    var _tmJsonEl = document.getElementById("stock-tool-material-extras-json");
    var _tmParsed = _tmJsonEl ? JSON.parse(_tmJsonEl.textContent || "[]") : [];
    if (Array.isArray(_tmParsed)) {
      _tmParsed.forEach(function (x) {
        if (x && !Object.prototype.hasOwnProperty.call(toolMaterialLabels, x)) toolMaterialLabels[x] = x;
      });
    }
  } catch (_tmErr) {}
  toolMaterialLabels[toolMaterialFilterOtherStock] = "Другое";

  var coatingLabels = {};
  (INV.coating_types || []).forEach(function (x) { coatingLabels[x.value] = x.label; });

  var coatingFullTitles = {};
  (INV.coating_types || []).forEach(function (x) { coatingFullTitles[x.value] = x.hoverTitle; });

  var workMaterialLabels = { "": "-" };
  (INV.work_material_types || []).forEach(function (x) { workMaterialLabels[x.value] = x.label; });

  function escapeHtml(s) {
    return String(s || "").replace(/[&<>"']/g, function (c) {
      return ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c];
    });
  }

  function formatCell(field, value) {
    var v = (value || "").trim();
    if (!v) return "-";
    if (field === "mill_type") return millTypeLabels[v] || v;
    if (field === "tool_material") return toolMaterialLabels[v] || escapeHtml(v);
    if (field === "coating_type") {
      var ct = coatingFullTitles[v] || coatingLabels[v] || v;
      var inner =
        '<span class="coating-dot swatch-' + escapeHtml(v) + '" title="' + escapeHtml(ct) + '"></span>';
      if (v === "none") {
        inner +=
          '<span class="coating-inline-label">' +
          escapeHtml(coatingLabels["none"] || "без покрытия") +
          "</span>";
      }
      return '<span class="coating-cell">' + inner + "</span>";
    }
    if (field === "work_material") {
      var codes = parseCsvCodes(v);
      if (!codes.length) return "-";
      return codes
        .map(function (code) {
          var cls = "wm-" + code.toLowerCase();
          var wmLbl = workMaterialLabels[code] || "";
          return (
            '<span class="wm-badge ' +
            cls +
            '" title="' +
            escapeHtml(wmLbl) +
            '">' +
            escapeHtml(code) +
            "</span>"
          );
        })
        .join(" ");
    }
    if (field === "em_diameter_mm") return "Ø" + v.replace(/\.00$/, "").replace(/(\.\d*[1-9])0+$/, "$1");
    if (field === "quantity") return "<strong>" + escapeHtml(v) + "</strong>";
    return escapeHtml(v.replace(/\.00$/, "").replace(/(\.\d*[1-9])0+$/, "$1"));
  }

  function buildSelect(field, current) {
    var options = [];
    if (field === "mill_type") {
      options = Object.keys(millTypeLabels).map(function (k) {
        return { value: k, label: millTypeLabels[k], title: millTypeLabels[k] };
      });
    } else if (field === "tool_material") {
      options = [{ value: "", label: "Неизвестно", title: "" }].concat(
        Object.keys(toolMaterialLabels).filter(function (k) { return k; }).map(function (k) {
          return { value: k, label: toolMaterialLabels[k], title: toolMaterialLabels[k] };
        })
      );
      if (current && !options.some(function (o) { return o.value === current; })) {
        options.splice(1, 0, { value: current, label: current, title: current });
        if (!Object.prototype.hasOwnProperty.call(toolMaterialLabels, current)) toolMaterialLabels[current] = current;
      }
    } else if (field === "coating_type") {
      options = Object.keys(coatingLabels).map(function (k) {
        return { value: k, label: coatingLabels[k], title: coatingFullTitles[k] || coatingLabels[k] };
      });
    } else if (field === "work_material") {
      options = [{ value: "", label: "-", title: "" }].concat(
        Object.keys(workMaterialLabels).filter(function (k) { return k; }).map(function (k) {
          return { value: k, label: workMaterialLabels[k], title: workMaterialLabels[k] };
        })
      );
    }
    var sel = document.createElement("select");
    sel.className = "stock-inline-editor";
    options.forEach(function (opt) {
      var o = document.createElement("option");
      o.value = opt.value;
      o.textContent = opt.label;
      if (opt.title) o.setAttribute("title", opt.title);
      if ((current || "") === opt.value) o.selected = true;
      sel.appendChild(o);
    });
    return sel;
  }

  function saveCell(cell, value, editor) {
    var toolId = cell.getAttribute("data-tool-id");
    var field = cell.getAttribute("data-field");
    var oldValue = cell.getAttribute("data-value") || "";
    if (value === oldValue) {
      cell.innerHTML = formatCell(field, oldValue);
      activeCell = null;
      return;
    }
    cell.classList.add("is-saving");
    var body = new FormData();
    body.append("action", "update_tool_cell");
    body.append("tool_id", toolId);
    body.append("field", field);
    body.append("value", value);
    fetch(window.location.pathname + window.location.search, {
      method: "POST",
      headers: { "X-CSRFToken": csrfToken },
      body: body
    }).then(function (resp) { return resp.json(); }).then(function (data) {
      if (!data || !data.ok) throw new Error((data && data.error) || "Ошибка сохранения");
      cell.setAttribute("data-value", value);
      cell.innerHTML = formatCell(field, value);
    }).catch(function (err) {
      alert(err.message || "Ошибка сохранения");
      cell.innerHTML = formatCell(field, oldValue);
    }).finally(function () {
      cell.classList.remove("is-saving");
      activeCell = null;
    });
  }

  function activateToolMaterialCell(cell, current) {
    var editor = buildSelect("tool_material", current);
    cell.innerHTML = "";
    cell.appendChild(editor);
    activeCell = cell;
    editor.focus();
    var cancelled = false;
    function revert() {
      cancelled = true;
      cell.innerHTML = formatCell("tool_material", cell.getAttribute("data-value") || "");
      activeCell = null;
    }
    function saveTm(val) {
      saveCell(cell, val, editor);
    }
    editor.addEventListener("keydown", function (e) {
      if (e.key === "Escape") {
        e.preventDefault();
        revert();
      }
    });
    editor.addEventListener("change", function () {
      if (editor.value === toolMaterialFilterOtherStock) {
        var inp = document.createElement("input");
        inp.type = "text";
        inp.className = "stock-inline-editor";
        inp.maxLength = 80;
        inp.value = "";
        inp.placeholder = "Материал, до 80 символов";
        cell.innerHTML = "";
        cell.appendChild(inp);
        activeCell = cell;
        inp.focus();
        inp.addEventListener("keydown", function (e) {
          if (e.key === "Enter") {
            e.preventDefault();
            var nv = (inp.value || "").trim();
            if (nv) saveTm(nv);
            else revert();
          }
          if (e.key === "Escape") {
            e.preventDefault();
            revert();
          }
        });
        inp.addEventListener("blur", function () {
          if (cancelled) return;
          var nv = (inp.value || "").trim();
          if (nv) saveTm(nv);
          else revert();
        });
        return;
      }
      saveTm((editor.value || "").trim());
    });
    editor.addEventListener("blur", function () {
      if (cancelled) return;
      setTimeout(function () {
        if (activeCell !== cell) return;
        if (!cell.contains(document.activeElement) && editor.parentNode && editor.value !== toolMaterialFilterOtherStock) {
          saveTm((editor.value || "").trim());
        }
      }, 0);
    });
  }

  function activateWorkMaterialCell(cell, current) {
    cell.innerHTML = buildArrivalWmMultiPickerHtml(current);
    var picker = cell.querySelector(".arrival-wm-multi-picker");
    var hidden = picker && picker.querySelector('[data-k="work_material"]');
    if (!picker || !hidden) return;
    activeCell = cell;
    picker.querySelectorAll(".arrival-wm-opt").forEach(function (btn) {
      btn.addEventListener("click", function (ev) {
        ev.preventDefault();
        ev.stopPropagation();
        btn.classList.toggle("is-active");
        btn.setAttribute("aria-pressed", btn.classList.contains("is-active") ? "true" : "false");
        syncMultiToggleHidden(picker, ".arrival-wm-opt", hidden, "data-wm");
      });
    });
    var cancelled = false;
    function revert() {
      cancelled = true;
      cell.innerHTML = formatCell("work_material", cell.getAttribute("data-value") || "");
      activeCell = null;
    }
    function commit() {
      if (cancelled || activeCell !== cell) return;
      var val = (hidden.value || "").trim();
      if (!val) {
        alert("Выберите хотя бы одну группу материала обработки.");
        return;
      }
      saveCell(cell, val, hidden);
    }
    cell.addEventListener(
      "keydown",
      function (e) {
        if (e.key === "Escape") {
          e.preventDefault();
          revert();
        }
        if (e.key === "Enter") {
          e.preventDefault();
          commit();
        }
      },
      { once: false }
    );
    setTimeout(function () {
      document.addEventListener(
        "click",
        function onDocClick(e) {
          if (!cell.contains(e.target)) commit();
        },
        { once: true }
      );
    }, 0);
  }

  function activate(cell) {
    if (activeCell === cell) return;
    if (activeCell) return;
    var field = cell.getAttribute("data-field");
    var type = cell.getAttribute("data-type");
    var current = cell.getAttribute("data-value") || "";
    if (field === "tool_material" && type === "select") {
      activateToolMaterialCell(cell, current);
      return;
    }
    if (field === "work_material") {
      activateWorkMaterialCell(cell, current);
      return;
    }
    var editor = (type === "select") ? buildSelect(field, current) : document.createElement("input");
    if (type !== "select") {
      editor.type = "number";
      editor.className = "stock-inline-editor";
      editor.step = type === "int" ? "1" : "0.01";
      editor.value = current;
      editor.title = "Enter - сохранить, Esc - отменить";
    }
    var cancelled = false;
    function finish(save) {
      if (!activeCell) return;
      var newValue = (editor.value || "").trim();
      if (!save || cancelled) {
        cell.innerHTML = formatCell(field, current);
        activeCell = null;
        return;
      }
      saveCell(cell, newValue, editor);
    }
    editor.addEventListener("keydown", function (e) {
      if (e.key === "Enter") { e.preventDefault(); finish(true); }
      if (e.key === "Escape") { cancelled = true; finish(false); }
    });
    editor.addEventListener("blur", function () {
      if (type === "select") finish(true);
      else finish(false);
    });
    editor.addEventListener("change", function () {
      if (type === "select") finish(true);
    });
    cell.innerHTML = "";
    cell.appendChild(editor);
    activeCell = cell;
    editor.focus();
    if (editor.select) editor.select();
  }

  editableCells.forEach(function (cell) {
    cell.addEventListener("click", function () { activate(cell); });
  });
})();
(function () {
  var rows = document.querySelectorAll(".issue-candidate-row");
  var issueSelect = document.getElementById("issue-id-select");
  if (!rows.length) return;
  Array.prototype.forEach.call(rows, function (row) {
    row.addEventListener("click", function (evt) {
      if (evt.target.closest("input, button, select, textarea, form, label")) return;
      var issueId = row.getAttribute("data-issue-id");
      if (issueSelect) issueSelect.value = issueId;
      var firstInput = row.querySelector('input[name="returned_qty"]');
      if (firstInput) firstInput.focus();
    });
  });
})();
