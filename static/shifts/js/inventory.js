/* inventory.js — extracted from inventory.html, uses data island #inv-options */
var INV = (function () {
  try {
    var el = document.getElementById("inv-options");
    return el ? JSON.parse(el.textContent) : {};
  } catch (e) { return {}; }
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
  var toolMaterialOptions = [{ value: "", label: "Неизвестно" }].concat(
    (INV.tool_material_types || []).map(function (x) { return { value: x.value, label: x.label }; })
  ).concat([{ value: toolMaterialFilterOther, label: "Другое" }]);

  var coatingOptions = (INV.coating_types || []).map(function (x) { return { value: x.value, label: x.label }; });

  var coatingSelectOptions = [
    { value: "none", label: "⬜ Без покрытия", bg: "#aab3c7", color: "#0f172a" },
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
      return '<option value="' + x.value + '">' + x.label + '</option>';
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

  function ensureGroup(cat) {
    var groupId = "arrival-group-" + cat;
    var group = document.getElementById(groupId);
    if (group) return group;
    group = document.createElement("div");
    group.className = "arrival-group";
    group.id = groupId;
    var title = cat === "end_mill" ? "Фрезы" : (cat === "tap" ? "Резьбовой инструмент" : (cat === "center_drill" ? "Центровки" : (cat === "countersink" ? "Зенкера" : "Сверла")));
    var headHtml = cat === "end_mill"
      ? '<tr><th>Тип фрезы</th><th class="short-col">D</th><th class="short-col">R</th><th class="short-col">L</th><th class="short-col">Lc</th><th class="short-col">Z</th><th class="short-col">D осн</th><th class="stack-words">Материал<br>инструмента</th><th>Покрытие</th><th class="stack-words">Материал<br>обработки</th><th class="qty-col">Кол-во</th><th></th></tr>'
      : (cat === "tap"
          ? '<tr><th class="tap-size-col">Размер</th><th class="tap-std-col">Стандарт</th><th class="tap-step-col">Шаг</th><th class="tap-tpi-col">TPI</th><th class="tap-l-col">L</th><th class="tap-lc-col">Lc</th><th class="tap-hole-col">Тип</th><th>Тип инструмента</th><th class="short-col">D осн</th><th class="stack-words">Материал<br>инструмента</th><th>Покрытие</th><th class="stack-words">Материал<br>обработки</th><th class="qty-col">Кол-во</th><th></th></tr>'
          : (cat === "center_drill"
              ? '<tr><th class="short-col">D</th><th class="short-col">L</th><th class="short-col">Угол</th><th class="short-col">D осн</th><th class="stack-words">Материал<br>инструмента</th><th>Покрытие</th><th class="stack-words">Материал<br>обработки</th><th class="qty-col">Кол-во</th><th></th></tr>'
              : (cat === "countersink"
                  ? '<tr><th>Тип</th><th class="short-col">D</th><th class="short-col">Угол</th><th class="short-col">L</th><th class="short-col">Z</th><th class="short-col">D осн</th><th class="stack-words">Материал<br>инструмента</th><th>Покрытие</th><th class="stack-words">Материал<br>обработки</th><th class="qty-col">Кол-во</th><th></th></tr>'
                  : '<tr><th class="short-col">D</th><th class="short-col">L</th><th class="short-col">Lc</th><th class="short-col">Угол</th><th class="short-col">D осн</th><th class="stack-words">Материал<br>инструмента</th><th>Покрытие</th><th class="stack-words">Материал<br>обработки</th><th class="qty-col">Кол-во</th><th></th></tr>')));
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
    var cat = categorySelect.value || "end_mill";
    if (cat !== "end_mill" && cat !== "tap" && cat !== "center_drill" && cat !== "countersink" && cat !== "drill") return;
    var group = ensureGroup(cat);
    var body = group.querySelector(".arrival-group-body");
    var tr = document.createElement("tr");
    arrivalRowSeq += 1;
    tr.setAttribute("data-arrival-row", "1");
    tr.setAttribute("data-category", cat);
    var cells = [];
    if (cat === "end_mill") {
      cells.push('<td><select data-k="mill_type">' + buildOptionsHtml(INV.end_mill_types || []) + '</select></td>');
      cells.push('<td class="short-col"><input type="number" step="0.01" data-k="em_diameter_mm"></td>');
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
      cells.push('<td class="short-col"><input type="number" step="0.01" data-k="cd_diameter_mm"></td>');
      cells.push('<td class="short-col"><input type="number" step="0.01" data-k="cd_overall_length_mm"></td>');
      cells.push('<td class="short-col"><select data-k="cd_angle_deg">' + buildOptionsHtml(INV.center_drill_angles || []) + '</select></td>');
      cells.push('<td class="short-col"><input type="number" step="0.01" data-k="main_diameter_mm"></td>');
      cells.push('<td class="tm-cell tm-cell-tool-material"></td>');
      cells.push('<td class="co-cell"></td>');
      cells.push('<td class="wm-cell"></td>');
      cells.push('<td class="qty-col"><input type="number" min="1" value="1" data-k="quantity"></td>');
    } else if (cat === "countersink") {
      cells.push('<td><select data-k="cs_type">' + buildOptionsHtml(INV.countersink_types || []) + '</select></td>');
      cells.push('<td class="short-col"><input type="number" step="0.01" data-k="cs_diameter_mm"></td>');
      cells.push('<td class="short-col"><select data-k="cs_angle_deg">' + buildOptionsHtml(INV.countersink_angles || []) + '</select></td>');
      cells.push('<td class="short-col"><input type="number" step="0.01" data-k="cs_overall_length_mm"></td>');
      cells.push('<td class="short-col"><input type="number" data-k="cs_flutes_count"></td>');
      cells.push('<td class="short-col"><input type="number" step="0.01" data-k="main_diameter_mm"></td>');
      cells.push('<td class="tm-cell tm-cell-tool-material"></td>');
      cells.push('<td class="co-cell"></td>');
      cells.push('<td class="wm-cell"></td>');
      cells.push('<td class="qty-col"><input type="number" min="1" value="1" data-k="quantity"></td>');
    } else {
      cells.push('<td class="short-col"><input type="number" step="0.01" data-k="dr_diameter_mm"></td>');
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
    var tmCell = tr.querySelector(".tm-cell-tool-material");
    tmCell.appendChild(buildSelect(toolMaterialOptions, ""));
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
    tr.querySelector(".co-cell").appendChild(buildColoredCoatingSelect("none"));
    tr.querySelector(".wm-cell").appendChild(buildColoredWmSelect(""));
    body.appendChild(tr);
  }

  addBtn.addEventListener("click", addRow);
  categorySelect.addEventListener("change", function () {
    // Влияет только на категорию новых строк.
  });
  form.addEventListener("submit", function (e) {
    var rows = [];
    groupsWrap.querySelectorAll("tr[data-arrival-row]").forEach(function (tr) {
      var row = { category: tr.getAttribute("data-category") || "" };
      tr.querySelectorAll("[data-k]").forEach(function (el) {
        var k = el.getAttribute("data-k");
        if (k === "tool_material_custom") return;
        if (k === "tool_material" && (el.value || "") === toolMaterialFilterOther) {
          var cin = tr.querySelector('[data-k="tool_material_custom"]');
          row.tool_material = (cin && cin.value || "").trim();
        } else {
          row[k] = (el.value || "").trim();
        }
      });
      row.movement_date = (arrivalDateInput.value || "").trim();
      row.supplier_name = (supplierSelect.value || "").trim();
      rows.push(row);
    });
    if (!rows.length) {
      e.preventDefault();
      return;
    }
    rowsJsonInput.value = JSON.stringify(rows);
  });

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
      var cls = v ? ("wm-" + v.toLowerCase()) : "";
      var wmLbl = workMaterialLabels[v] || "";
      return v ? ('<span class="wm-badge ' + cls + '" title="' + escapeHtml(wmLbl) + '">' + escapeHtml(v) + "</span>") : "-";
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
