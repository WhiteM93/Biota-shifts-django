(function () {
  "use strict";

  var root = document.getElementById("wc-root");
  if (!root) return;

  var canEdit = root.getAttribute("data-can-edit") === "1";
  var editMode = false;
  var stageFilter = "all";
  var collapsedSplits = {};
  try {
    collapsedSplits = JSON.parse(sessionStorage.getItem("wc-collapsed-splits") || "{}") || {};
  } catch (_e2) {
    collapsedSplits = {};
  }
  var contracts = [];
  try {
    var boot = document.getElementById("wc-bootstrap");
    contracts = boot ? JSON.parse(boot.textContent || "[]") : [];
  } catch (_e) {
    contracts = [];
  }

  var listEl = root.querySelector(".js-wc-list");
  var emptyEl = root.querySelector(".js-wc-empty");
  var filterEmptyEl = root.querySelector(".js-wc-filter-empty");
  var filtersEl = root.querySelector(".js-wc-filters");
  var btnEdit = root.querySelector(".js-wc-toggle-edit");
  var btnNewCab = root.querySelector(".js-wc-new-contract");
  var dlgCab = document.querySelector(".js-wc-dlg-contract");
  var dlgPos = document.querySelector(".js-wc-dlg-position");
  var dlgSplit = document.querySelector(".js-wc-dlg-split");
  var cabForm = document.querySelector(".js-wc-contract-form");
  var posForm = document.querySelector(".js-wc-position-form");
  var splitForm = document.querySelector(".js-wc-split-form");

  var OP_CATALOG = [
    "Лазерный",
    "Фрезерный",
    "Токарный",
    "Гальваника",
    "Слесарный",
    "Монтаж",
    "Размонтаж",
    "Сварка",
    "Гибка",
    "Покраска",
    "Маркировка",
    "Мойка",
    "Упаковка"
  ];

  function opToneClass(name) {
    var n = String(name || "").toLowerCase();
    if (n.indexOf("лазер") >= 0) return "wc-tone-laser";
    if (n.indexOf("фрезер") >= 0) return "wc-tone-mill";
    if (n.indexOf("токар") >= 0) return "wc-tone-lathe";
    if (n.indexOf("гальван") >= 0) return "wc-tone-galv";
    if (n.indexOf("слесар") >= 0 || n.indexOf("сесар") >= 0) return "wc-tone-fitter";
    if (n.indexOf("размонт") >= 0) return "wc-tone-demount";
    if (n.indexOf("монтаж") >= 0) return "wc-tone-mount";
    if (n.indexOf("свар") >= 0) return "wc-tone-weld";
    if (n.indexOf("гибк") >= 0) return "wc-tone-bend";
    if (n.indexOf("покра") >= 0) return "wc-tone-paint";
    if (n.indexOf("маркир") >= 0) return "wc-tone-mark";
    if (n.indexOf("мойк") >= 0) return "wc-tone-wash";
    if (n.indexOf("упак") >= 0) return "wc-tone-pack";
    return "wc-tone-default";
  }

  function csrfToken() {
    var m = document.cookie.match(/(?:^|; )csrftoken=([^;]+)/);
    return m ? decodeURIComponent(m[1]) : "";
  }

  function detailUrl(tpl, id) {
    return String(tpl || "").replace(/\/0(\/|$)/, "/" + id + "$1");
  }

  function fetchJson(url, opts) {
    opts = opts || {};
    var headers = opts.headers || {};
    headers["X-Requested-With"] = "XMLHttpRequest";
    if (opts.body != null) {
      headers["Content-Type"] = "application/json";
      headers["X-CSRFToken"] = csrfToken();
    }
    return fetch(url, {
      method: opts.method || "GET",
      headers: headers,
      body: opts.body != null ? JSON.stringify(opts.body) : undefined,
      credentials: "same-origin"
    }).then(function (res) {
      return res.json().then(function (data) {
        if (!res.ok || (data && data.ok === false)) {
          throw new Error((data && data.error) || ("Ошибка " + res.status));
        }
        return data;
      });
    });
  }

  function escapeHtml(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function setEditMode(on) {
    editMode = !!on && canEdit;
    root.classList.toggle("is-edit", editMode);
    if (btnEdit) {
      btnEdit.setAttribute("aria-pressed", editMode ? "true" : "false");
      btnEdit.setAttribute("aria-label", editMode ? "Готово" : "Редактировать");
      btnEdit.setAttribute("title", editMode ? "Готово" : "Редактировать");
      btnEdit.classList.toggle("is-on", editMode);
    }
    root.querySelectorAll(".wc-edit-only").forEach(function (el) {
      el.hidden = !editMode;
    });
    render();
  }

  function openDialog(dlg) {
    if (!dlg) return;
    if (typeof dlg.showModal === "function") dlg.showModal();
    else dlg.setAttribute("open", "");
  }

  function closeDialog(dlg) {
    if (!dlg) return;
    if (typeof dlg.close === "function") dlg.close();
    else dlg.removeAttribute("open");
  }

  function findContract(id) {
    return contracts.find(function (c) { return c.id === id; });
  }

  function findPosition(contractId, posId) {
    var c = findContract(contractId);
    if (!c) return null;
    return (c.positions || []).find(function (p) { return p.id === posId; }) || null;
  }

  function upsertContractLocal(cab) {
    var i = contracts.findIndex(function (c) { return c.id === cab.id; });
    if (i >= 0) contracts[i] = cab;
    else contracts.push(cab);
  }

  function upsertPositionLocal(pos) {
    var c = findContract(pos.contract_id);
    if (!c) return;
    c.positions = c.positions || [];
    var i = c.positions.findIndex(function (p) { return p.id === pos.id; });
    if (i >= 0) c.positions[i] = pos;
    else c.positions.push(pos);
    c.positions = flattenPositionsLocal(c.positions);
    c.positions_count = c.positions.length;
    c.positions_qty = c.positions.reduce(function (s, p) { return s + (p.quantity || 0); }, 0);
  }

  function flattenPositionsLocal(list) {
    var byParent = {};
    (list || []).forEach(function (p) {
      var key = p.parent_id == null ? "root" : String(p.parent_id);
      if (!byParent[key]) byParent[key] = [];
      byParent[key].push(p);
    });
    Object.keys(byParent).forEach(function (k) {
      byParent[k].sort(function (a, b) {
        return (a.sort_order - b.sort_order) || (a.id - b.id);
      });
    });
    var out = [];
    function walk(p, depth) {
      p.split_depth = depth;
      out.push(p);
      (byParent[String(p.id)] || []).forEach(function (ch) {
        walk(ch, depth + 1);
      });
    }
    (byParent.root || []).forEach(function (r) {
      walk(r, 0);
    });
    return out;
  }

  function removePositionLocal(posId) {
    var idNum = parseInt(posId, 10);
    contracts.forEach(function (c) {
      var remove = {};
      remove[idNum] = true;
      var changed = true;
      while (changed) {
        changed = false;
        (c.positions || []).forEach(function (p) {
          if (p.parent_id && remove[p.parent_id] && !remove[p.id]) {
            remove[p.id] = true;
            changed = true;
          }
        });
      }
      c.positions = (c.positions || []).filter(function (p) { return !remove[p.id]; });
      c.positions_count = c.positions.length;
      c.positions_qty = c.positions.reduce(function (s, p) { return s + (p.quantity || 0); }, 0);
    });
  }

  function currentOpName(pos) {
    if (!pos || !pos.current_operation_id) return "";
    var opId = Number(pos.current_operation_id);
    var ops = pos.operations || [];
    for (var i = 0; i < ops.length; i++) {
      if (Number(ops[i].id) === opId) return ops[i].name || "";
    }
    return "";
  }

  function positionStageKey(pos) {
    if (!pos) return "not_started";
    if (pos.stage === "done") return "done";
    if (pos.stage === "paused") return "paused";
    if (pos.stage === "operation") {
      var name = currentOpName(pos);
      return name ? ("op:" + name) : "operation";
    }
    return "not_started";
  }

  function positionMatchesFilter(pos) {
    if (stageFilter === "all") return true;
    var key = positionStageKey(pos);
    if (key === stageFilter) return true;
    // пауза на конкретной операции тоже попадает в фильтр этой операции
    if (stageFilter.indexOf("op:") === 0 && pos.stage === "paused") {
      var pausedName = currentOpName(pos);
      return pausedName && stageFilter === "op:" + pausedName;
    }
    return false;
  }

  function collectStageStats() {
    var stats = {
      all: { count: 0, qty: 0 },
      not_started: { count: 0, qty: 0 },
      paused: { count: 0, qty: 0 },
      done: { count: 0, qty: 0 },
      ops: {}
    };
    OP_CATALOG.forEach(function (name) {
      stats.ops[name] = { count: 0, qty: 0 };
    });
    contracts.forEach(function (c) {
      (c.positions || []).forEach(function (p) {
        var key = positionStageKey(p);
        var qty = Number(p.quantity || 0);
        stats.all.count += 1;
        stats.all.qty += qty;
        if (key === "done") {
          stats.done.count += 1;
          stats.done.qty += qty;
        } else if (key === "paused") {
          stats.paused.count += 1;
          stats.paused.qty += qty;
        } else if (key.indexOf("op:") === 0) {
          var name = key.slice(3);
          if (!stats.ops[name]) stats.ops[name] = { count: 0, qty: 0 };
          stats.ops[name].count += 1;
          stats.ops[name].qty += qty;
        } else {
          stats.not_started.count += 1;
          stats.not_started.qty += qty;
        }
      });
    });
    return stats;
  }

  function renderFilters() {
    if (!filtersEl) return;
    var stats = collectStageStats();
    filtersEl.innerHTML = "";

    function addChip(key, label, count, qty, tone) {
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "wc-filter-chip" + (tone ? (" " + tone) : "");
      if (stageFilter === key) btn.classList.add("is-active");
      btn.dataset.filter = key;
      btn.setAttribute("aria-pressed", stageFilter === key ? "true" : "false");
      var text = document.createElement("span");
      text.className = "wc-filter-chip-label";
      text.textContent = label;
      btn.appendChild(text);
      var meta = document.createElement("span");
      meta.className = "wc-filter-chip-meta";
      meta.textContent = String(count || 0);
      if (qty) meta.title = qty + " шт.";
      btn.appendChild(meta);
      btn.addEventListener("click", function () {
        stageFilter = key;
        render();
      });
      filtersEl.appendChild(btn);
    }

    addChip("all", "Все", stats.all.count, stats.all.qty, "wc-tone-all");
    addChip("not_started", "Не запущено", stats.not_started.count, stats.not_started.qty, "wc-tone-idle");
    addChip("paused", "Пауза", stats.paused.count, stats.paused.qty, "wc-tone-pause");

    var opNames = Object.keys(stats.ops).sort(function (a, b) {
      var ia = OP_CATALOG.indexOf(a);
      var ib = OP_CATALOG.indexOf(b);
      if (ia < 0) ia = 999;
      if (ib < 0) ib = 999;
      if (ia !== ib) return ia - ib;
      return a.localeCompare(b, "ru");
    });
    opNames.forEach(function (name) {
      var s = stats.ops[name] || { count: 0, qty: 0 };
      addChip("op:" + name, name, s.count, s.qty, opToneClass(name));
    });

    addChip("done", "Готово", stats.done.count, stats.done.qty, "wc-tone-done");
  }

  function render() {
    if (!listEl) return;
    renderFilters();
    listEl.innerHTML = "";
    if (!contracts.length) {
      if (emptyEl) emptyEl.hidden = false;
      if (filterEmptyEl) filterEmptyEl.hidden = true;
      return;
    }
    if (emptyEl) emptyEl.hidden = true;

    var shownAny = false;
    contracts.forEach(function (cab, idx) {
      var allPositions = cab.positions || [];
      var positions = allPositions.filter(positionMatchesFilter);
      if (stageFilter !== "all" && !positions.length && !editMode) return;

      shownAny = true;
      var details = document.createElement("details");
      details.className = "wc-contract js-wc-contract";
      var forceOpen = stageFilter !== "all";
      details.open = forceOpen || idx === 0 || !!cab._keepOpen;
      details.dataset.contractId = String(cab.id);

      var summary = document.createElement("summary");
      summary.className = "wc-contract-summary";

      var chevron = document.createElement("span");
      chevron.className = "wc-contract-chevron";
      chevron.setAttribute("aria-hidden", "true");
      summary.appendChild(chevron);

      var nameEl = document.createElement("span");
      nameEl.className = "wc-contract-name";
      nameEl.textContent = cab.name || "Без названия";
      summary.appendChild(nameEl);

      var metaEl = document.createElement("span");
      metaEl.className = "wc-contract-meta";
      var metaCount = stageFilter === "all"
        ? (cab.positions_count || allPositions.length || 0)
        : positions.length;
      var metaQty = stageFilter === "all"
        ? (cab.positions_qty || 0)
        : positions.reduce(function (s, p) { return s + (p.quantity || 0); }, 0);
      metaEl.textContent = metaCount + " поз. · " + metaQty + " шт.";
      summary.appendChild(metaEl);

      if (editMode) {
        var cabActs = document.createElement("span");
        cabActs.className = "wc-contract-acts";
        cabActs.addEventListener("click", function (ev) {
          ev.preventDefault();
          ev.stopPropagation();
        });

        var btnEditCab = document.createElement("button");
        btnEditCab.type = "button";
        btnEditCab.className = "wc-icon-btn";
        btnEditCab.title = "Изменить название";
        btnEditCab.setAttribute("aria-label", "Изменить контракт");
        btnEditCab.innerHTML =
          '<svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true" focusable="false">' +
          '<path fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" ' +
          'd="M12 20h9M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4 12.5-12.5z"/>' +
          "</svg>";
        btnEditCab.addEventListener("click", function (ev) {
          ev.preventDefault();
          ev.stopPropagation();
          openContractForm(cab);
        });
        cabActs.appendChild(btnEditCab);

        var btnDelCab = document.createElement("button");
        btnDelCab.type = "button";
        btnDelCab.className = "wc-icon-btn wc-icon-btn-danger";
        btnDelCab.title = "Удалить контракт";
        btnDelCab.setAttribute("aria-label", "Удалить контракт");
        btnDelCab.innerHTML =
          '<svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true" focusable="false">' +
          '<path fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" ' +
          'd="M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6"/>' +
          "</svg>";
        btnDelCab.addEventListener("click", function (ev) {
          ev.preventDefault();
          ev.stopPropagation();
          deleteContract(cab);
        });
        cabActs.appendChild(btnDelCab);
        summary.appendChild(cabActs);
      }

      details.appendChild(summary);

      var body = document.createElement("div");
      body.className = "wc-contract-body";

      if (cab.notes) {
        var notes = document.createElement("p");
        notes.className = "wc-contract-notes";
        notes.textContent = cab.notes;
        body.appendChild(notes);
      }

      if (editMode) {
        var bar = document.createElement("div");
        bar.className = "wc-contract-toolbar";
        var btnAddPos = document.createElement("button");
        btnAddPos.type = "button";
        btnAddPos.className = "wc-btn-primary wc-btn-compact";
        btnAddPos.textContent = "+ Изделие";
        btnAddPos.addEventListener("click", function (ev) {
          ev.preventDefault();
          ev.stopPropagation();
          openPositionForm(cab, null);
        });
        bar.appendChild(btnAddPos);
        body.appendChild(bar);
      }

      if (!positions.length) {
        var empty = document.createElement("p");
        empty.className = "wc-empty-inline";
        empty.textContent = "Нет позиций в этом контракте.";
        body.appendChild(empty);
      } else {
        var wrap = document.createElement("div");
        wrap.className = "wc-table-wrap";
        var table = document.createElement("table");
        table.className = "wc-table";
        table.innerHTML =
          "<thead><tr>" +
          "<th class=\"wc-col-name\">Изделие</th>" +
          "<th class=\"wc-col-stage\">Этап</th>" +
          "<th class=\"wc-col-desc\">Описание</th>" +
          "<th class=\"wc-col-qty\">Кол-во</th>" +
          (editMode ? "<th class=\"wc-col-act\"></th>" : "") +
          "</tr></thead>";
        var tbody = document.createElement("tbody");
        positions.forEach(function (pos) {
          if (isSplitCollapsedAway(cab, pos)) return;
          tbody.appendChild(buildPositionRow(cab, pos));
        });
        table.appendChild(tbody);
        wrap.appendChild(table);
        body.appendChild(wrap);
      }

      details.appendChild(body);
      details.addEventListener("toggle", function () {
        if (stageFilter === "all") cab._keepOpen = details.open;
      });
      listEl.appendChild(details);
    });

    if (filterEmptyEl) filterEmptyEl.hidden = shownAny || stageFilter === "all";
    if (!shownAny && stageFilter !== "all" && emptyEl) emptyEl.hidden = true;
  }

  function buildPositionRow(cab, pos) {
    var tr = document.createElement("tr");
    tr.dataset.positionId = String(pos.id);
    var depth = Math.max(0, parseInt(pos.split_depth, 10) || 0);
    if (pos.parent_id) {
      tr.classList.add("is-split");
      tr.style.setProperty("--split-depth", String(depth));
    }

    var tdName = document.createElement("td");
    tdName.className = "wc-col-name";
    var nameWrap = document.createElement("div");
    nameWrap.className = "wc-name-cell";

    var nameMain = document.createElement("div");
    nameMain.className = "wc-name-main";
    if (pos.parent_id) {
      var mark = document.createElement("span");
      mark.className = "wc-split-mark";
      mark.setAttribute("aria-hidden", "true");
      mark.textContent = "↘";
      nameMain.appendChild(mark);
      var nameSpan = document.createElement("span");
      nameSpan.className = "wc-split-name";
      nameSpan.textContent = pos.name || "";
      nameMain.appendChild(nameSpan);
    } else {
      nameMain.textContent = pos.name || "";
    }
    nameWrap.appendChild(nameMain);

    var splitKids = countDirectSplits(cab, pos.id);
    if (splitKids > 0) {
      var collapsed = !!collapsedSplits[String(pos.id)];
      var btnFold = document.createElement("button");
      btnFold.type = "button";
      btnFold.className = "wc-split-fold-btn" + (collapsed ? " is-collapsed" : "");
      btnFold.title = collapsed
        ? ("Показать отрывы (" + splitKids + ")")
        : ("Свернуть отрывы (" + splitKids + ")");
      btnFold.setAttribute(
        "aria-label",
        collapsed ? "Показать отрывы" : "Свернуть отрывы"
      );
      btnFold.setAttribute("aria-expanded", collapsed ? "false" : "true");
      btnFold.innerHTML =
        '<span class="wc-split-fold-chevron" aria-hidden="true"></span>' +
        '<span class="wc-split-fold-count">' + splitKids + "</span>";
      btnFold.addEventListener("click", function (ev) {
        ev.preventDefault();
        ev.stopPropagation();
        var key = String(pos.id);
        if (collapsedSplits[key]) delete collapsedSplits[key];
        else collapsedSplits[key] = 1;
        try {
          sessionStorage.setItem("wc-collapsed-splits", JSON.stringify(collapsedSplits));
        } catch (_e3) {}
        render();
      });
      nameWrap.appendChild(btnFold);
    }

    if (editMode && (pos.quantity || 0) > 1) {
      var btnSplit = document.createElement("button");
      btnSplit.type = "button";
      btnSplit.className = "wc-icon-btn";
      btnSplit.title = "Отрыв";
      btnSplit.setAttribute("aria-label", "Отрыв: оторвать часть количества");
      btnSplit.innerHTML =
        '<svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true" focusable="false">' +
        '<path fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" ' +
        'd="M6 3v12a3 3 0 0 0 3 3h3M6 9h7a3 3 0 0 1 3 3v6M15 18l3 3 3-3"/>' +
        "</svg>";
      btnSplit.addEventListener("click", function (ev) {
        ev.preventDefault();
        ev.stopPropagation();
        openSplitForm(pos);
      });
      nameWrap.appendChild(btnSplit);
    }

    tdName.appendChild(nameWrap);
    tr.appendChild(tdName);

    var tdStage = document.createElement("td");
    tdStage.className = "wc-col-stage";

    var stageWrap = document.createElement("div");
    stageWrap.className = "wc-stage-wrap";

    var ops = pos.operations || [];
    if (ops.length) {
      stageWrap.appendChild(buildOpsPipeline(pos, ops));
    } else {
      var empty = document.createElement("div");
      empty.className = "wc-ops-now is-idle";
      empty.textContent = pos.stage_label || "Нет операций";
      stageWrap.appendChild(empty);
    }
    tdStage.appendChild(stageWrap);
    tr.appendChild(tdStage);

    var tdDesc = document.createElement("td");
    tdDesc.className = "wc-col-desc";
    tdDesc.textContent = pos.description || "—";
    tr.appendChild(tdDesc);

    var tdQty = document.createElement("td");
    tdQty.className = "wc-col-qty";
    tdQty.appendChild(buildQtyCell(cab, pos));
    tr.appendChild(tdQty);

    if (editMode) {
      var tdAct = document.createElement("td");
      tdAct.className = "wc-col-act";
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "wc-icon-btn";
      btn.title = "Изменить";
      btn.setAttribute("aria-label", "Изменить изделие");
      btn.innerHTML =
        '<svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true" focusable="false">' +
        '<path fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" ' +
        'd="M12 20h9M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4 12.5-12.5z"/>' +
        "</svg>";
      btn.addEventListener("click", function () {
        openPositionForm(cab, pos);
      });
      tdAct.appendChild(btn);
      tr.appendChild(tdAct);
    }

    return tr;
  }

  function sumDescendantQty(cab, posId) {
    var total = 0;
    var positions = (cab && cab.positions) || [];
    function walk(parentId) {
      positions.forEach(function (p) {
        if (Number(p.parent_id) === Number(parentId)) {
          total += Number(p.quantity || 0);
          walk(p.id);
        }
      });
    }
    walk(posId);
    return total;
  }

  function countDirectSplits(cab, posId) {
    var n = 0;
    ((cab && cab.positions) || []).forEach(function (p) {
      if (Number(p.parent_id) === Number(posId)) n += 1;
    });
    return n;
  }

  function isSplitCollapsedAway(cab, pos) {
    if (!pos || !pos.parent_id) return false;
    // при фильтре по этапу не прячем совпавшие отрывы
    if (stageFilter !== "all") return false;
    var positions = (cab && cab.positions) || [];
    var byId = {};
    positions.forEach(function (p) { byId[p.id] = p; });
    var cur = pos;
    var guard = 0;
    while (cur && cur.parent_id && guard < 20) {
      if (collapsedSplits[String(cur.parent_id)]) return true;
      cur = byId[cur.parent_id];
      guard += 1;
    }
    return false;
  }

  function buildQtyCell(cab, pos) {
    var wrap = document.createElement("div");
    wrap.className = "wc-qty-cell";
    var qty = Number(pos.quantity || 0);
    var splitOff = sumDescendantQty(cab, pos.id);
    var full = qty + splitOff;

    var main = document.createElement("div");
    main.className = "wc-qty-main";
    main.textContent = String(qty);
    wrap.appendChild(main);

    if (pos.parent_id) {
      wrap.classList.add("is-split-qty");
      var tip = document.createElement("div");
      tip.className = "wc-qty-sub";
      tip.textContent = "отрыв";
      tip.title = "Отрыв от родительской позиции";
      wrap.appendChild(tip);
    } else if (splitOff > 0) {
      wrap.classList.add("has-splits");
      var sub = document.createElement("div");
      sub.className = "wc-qty-sub";
      sub.innerHTML = '<span class="wc-qty-full">из ' + full + '</span>' +
        '<span class="wc-qty-tag">отрыв</span>';
      sub.title =
        "Полное количество " + full + " шт.: остаток " + qty +
        ", в отрывах " + splitOff;
      wrap.appendChild(sub);
    }

    return wrap;
  }

  function buildOpsPipeline(pos, ops) {
    var route = document.createElement("div");
    route.className = "wc-ops-pipeline";
    route.setAttribute("role", "list");
    route.setAttribute("aria-label", "Маршрут операций");

    var paused = pos.stage === "paused";
    var allDone = pos.stage === "done";
    var onOp = pos.stage === "operation";
    var notStarted = !allDone && !paused && !onOp;
    var freezeId = (onOp || paused) ? Number(pos.current_operation_id || 0) : 0;
    var currentIdx = -1;
    if (freezeId) {
      for (var i = 0; i < ops.length; i++) {
        if (Number(ops[i].id) === freezeId) {
          currentIdx = i;
          break;
        }
      }
    }

    var chips = document.createElement("div");
    chips.className = "wc-ops-chips";
    chips.setAttribute("role", "presentation");

    function appendArrow() {
      var arrow = document.createElement("span");
      arrow.className = "wc-ops-arrow";
      arrow.setAttribute("aria-hidden", "true");
      arrow.textContent = "→";
      chips.appendChild(arrow);
    }

    function makeChip(label, classNames, title, onClick) {
      var chip = document.createElement("button");
      chip.type = "button";
      chip.className = "wc-op-chip " + classNames;
      chip.setAttribute("role", "listitem");
      chip.textContent = label;
      chip.title = title || label;
      if (!canEdit) {
        chip.disabled = true;
      } else {
        chip.addEventListener("click", function (ev) {
          ev.preventDefault();
          ev.stopPropagation();
          onClick();
        });
      }
      chips.appendChild(chip);
      return chip;
    }

    // Порядковый маршрут
    var idleCls = notStarted
      ? "wc-op-chip-idle is-current"
      : allDone
        ? "wc-op-chip-idle is-done"
        : "wc-op-chip-idle is-todo";
    var idleChip = makeChip(
      "Не запущено",
      idleCls,
      canEdit ? "Производство ещё не запущено" : "Не запущено",
      function () {
        saveStage(pos, { stage: "not_started", current_operation_id: null });
      }
    );
    if (notStarted) idleChip.setAttribute("aria-current", "step");

    ops.forEach(function (op, idx) {
      appendArrow();
      var tone = opToneClass(op.name);
      var cls;
      var title;
      if (allDone) {
        cls = "is-done " + tone;
        title = canEdit ? ("Поставить этап: " + (op.name || "")) : (op.name || "");
      } else if (idx === currentIdx && paused) {
        cls = "is-paused-at is-current " + tone;
        title = "Пауза на этапе: " + (op.name || "");
      } else if (idx === currentIdx && onOp) {
        cls = "is-current " + tone;
        title = op.name || "";
      } else {
        cls = "is-todo " + tone;
        title = canEdit ? ("Поставить этап: " + (op.name || "")) : (op.name || "");
      }
      var chip = makeChip(op.name || ("Оп. " + (idx + 1)), cls, title, function () {
        saveStage(pos, {
          stage: "operation",
          current_operation_id: op.id,
        });
      });
      if (idx === currentIdx && !allDone) {
        chip.setAttribute("aria-current", "step");
      }
    });

    appendArrow();
    var doneCls = allDone ? "is-done-flag" : "is-todo";
    var doneChip = makeChip(
      "Готово",
      "wc-op-chip-done " + doneCls,
      canEdit
        ? (allDone ? "Все этапы пройдены" : "Отметить: все этапы пройдены")
        : "Готово",
      function () {
        saveStage(pos, { stage: "done", current_operation_id: null });
      }
    );
    if (allDone) doneChip.setAttribute("aria-current", "step");

    // Отдельный не порядковый статус — пауза (запоминает текущий этап)
    var sep = document.createElement("span");
    sep.className = "wc-ops-sep";
    sep.setAttribute("aria-hidden", "true");
    chips.appendChild(sep);

    var pauseCls = paused ? "wc-op-chip-pause is-paused" : "wc-op-chip-pause is-todo";
    var pauseTitle = "Поставить позицию на паузу";
    if (paused) {
      var frozenName = currentIdx >= 0 ? (ops[currentIdx].name || "") : "";
      pauseTitle = frozenName
        ? ("Пауза (остановились на «" + frozenName + "»)")
        : "Производство на паузе";
    } else if (onOp && currentIdx >= 0) {
      pauseTitle = "Пауза на этапе «" + (ops[currentIdx].name || "") + "»";
    }
    var pauseChip = makeChip(
      "Пауза",
      pauseCls,
      canEdit ? pauseTitle : "Пауза",
      function () {
        var body = { stage: "paused", current_operation_id: null };
        if ((pos.stage === "operation" || pos.stage === "paused") && pos.current_operation_id) {
          body.current_operation_id = pos.current_operation_id;
        }
        saveStage(pos, body);
      }
    );
    if (paused) {
      pauseChip.setAttribute("aria-current", "step");
      route.classList.add("is-paused");
    }

    route.appendChild(chips);
    return route;
  }

  function saveStage(pos, body) {
    var url = detailUrl(root.getAttribute("data-api-stage-tpl"), pos.id);
    fetchJson(url, { method: "POST", body: body || {} })
      .then(function (data) {
        upsertPositionLocal(data.position);
        render();
      })
      .catch(function (e) {
        window.alert(e.message);
        render();
      });
  }

  function openContractForm(cab) {
    if (!cabForm || !dlgCab) return;
    cabForm.querySelector(".js-wc-contract-form-title").textContent = cab ? "Контракт" : "Новый контракт";
    cabForm.querySelector(".js-wc-contract-id").value = cab ? String(cab.id) : "";
    cabForm.querySelector(".js-wc-contract-name").value = cab ? (cab.name || "") : "";
    cabForm.querySelector(".js-wc-contract-notes").value = cab ? (cab.notes || "") : "";
    var del = cabForm.querySelector(".js-wc-contract-del");
    if (del) del.hidden = !cab;
    openDialog(dlgCab);
  }

  function deleteContract(cab) {
    if (!cab || !cab.id) return;
    var label = cab.name || ("#" + cab.id);
    if (!window.confirm("Удалить контракт «" + label + "» и все его изделия?")) return;
    fetchJson(detailUrl(root.getAttribute("data-api-contract-del-tpl"), cab.id), {
      method: "POST",
      body: {}
    })
      .then(function () {
        contracts = contracts.filter(function (c) { return c.id !== cab.id; });
        closeDialog(dlgCab);
        render();
      })
      .catch(function (e) { window.alert(e.message); });
  }

  function clearOpsList() {
    var box = posForm && posForm.querySelector(".js-wc-ops-list");
    if (box) box.innerHTML = "";
  }

  var draggedOpRow = null;

  function bindOpsListDnD(box) {
    if (!box || box._wcDndBound) return;
    box._wcDndBound = true;
    box.addEventListener("dragover", function (ev) {
      ev.preventDefault();
      if (!draggedOpRow) return;
      var over = ev.target.closest(".wc-op-row");
      if (!over || over === draggedOpRow || over.parentNode !== box) return;
      var rect = over.getBoundingClientRect();
      var before = ev.clientY < rect.top + rect.height / 2;
      if (before) box.insertBefore(draggedOpRow, over);
      else box.insertBefore(draggedOpRow, over.nextSibling);
      renumberOps();
    });
    box.addEventListener("drop", function (ev) {
      ev.preventDefault();
      if (draggedOpRow) draggedOpRow.classList.remove("is-dragging");
      draggedOpRow = null;
      renumberOps();
    });
  }

  function addOpRow(name) {
    var box = posForm.querySelector(".js-wc-ops-list");
    if (!box) return;
    bindOpsListDnD(box);

    var row = document.createElement("div");
    row.className = "wc-op-row";

    var handle = document.createElement("button");
    handle.type = "button";
    handle.className = "wc-op-drag";
    handle.title = "Перетащить";
    handle.setAttribute("aria-label", "Перетащить операцию");
    handle.draggable = true;
    handle.innerHTML = '<span aria-hidden="true">⋮⋮</span>';
    handle.addEventListener("dragstart", function (ev) {
      draggedOpRow = row;
      row.classList.add("is-dragging");
      ev.dataTransfer.effectAllowed = "move";
      ev.dataTransfer.setData("text/plain", "op-row");
      try {
        ev.dataTransfer.setDragImage(row, 24, 16);
      } catch (_e) {}
    });
    handle.addEventListener("dragend", function () {
      row.classList.remove("is-dragging");
      draggedOpRow = null;
      renumberOps();
    });

    var num = document.createElement("span");
    num.className = "wc-op-num";

    var sel = document.createElement("select");
    sel.className = "wc-control js-wc-op-name";
    sel.setAttribute("aria-label", "Операция");

    var blank = document.createElement("option");
    blank.value = "";
    blank.textContent = "— выберите —";
    sel.appendChild(blank);

    var chosen = (name || "").trim();
    var names = OP_CATALOG.slice();
    if (chosen && names.indexOf(chosen) < 0) names.unshift(chosen);
    names.forEach(function (opName) {
      var opt = document.createElement("option");
      opt.value = opName;
      opt.textContent = opName;
      sel.appendChild(opt);
    });
    sel.value = chosen;

    var del = document.createElement("button");
    del.type = "button";
    del.className = "wc-btn-ghost wc-btn-compact js-wc-op-del";
    del.title = "Удалить";
    del.setAttribute("aria-label", "Удалить операцию");
    del.textContent = "×";
    del.addEventListener("click", function () {
      row.remove();
      renumberOps();
    });

    row.appendChild(handle);
    row.appendChild(num);
    row.appendChild(sel);
    row.appendChild(del);
    box.appendChild(row);
    renumberOps();
  }

  function renumberOps() {
    var box = posForm.querySelector(".js-wc-ops-list");
    if (!box) return;
    [].forEach.call(box.querySelectorAll(".wc-op-row"), function (row, i) {
      var n = row.querySelector(".wc-op-num");
      if (n) n.textContent = String(i + 1);
    });
  }

  function collectOps() {
    var box = posForm.querySelector(".js-wc-ops-list");
    if (!box) return [];
    var out = [];
    [].forEach.call(box.querySelectorAll(".js-wc-op-name"), function (inp) {
      var v = (inp.value || "").trim();
      if (v) out.push(v);
    });
    return out;
  }

  function openPositionForm(cab, pos) {
    if (!posForm || !dlgPos) return;
    posForm.querySelector(".js-wc-position-form-title").textContent = pos ? "Изделие" : "Новое изделие";
    posForm.querySelector(".js-wc-position-id").value = pos ? String(pos.id) : "";
    posForm.querySelector(".js-wc-position-contract-id").value = String(cab.id);
    posForm.querySelector(".js-wc-position-name").value = pos ? (pos.name || "") : "";
    posForm.querySelector(".js-wc-position-desc").value = pos ? (pos.description || "") : "";
    posForm.querySelector(".js-wc-position-qty").value = String(pos ? (pos.quantity || 1) : 1);
    clearOpsList();
    var ops = pos && pos.operations && pos.operations.length
      ? pos.operations
      : [{ name: "Лазерный" }, { name: "Фрезерный" }];
    if (!pos) ops = [{ name: "" }];
    ops.forEach(function (op) { addOpRow(op.name || ""); });
    var del = posForm.querySelector(".js-wc-position-del");
    if (del) del.hidden = !pos;
    openDialog(dlgPos);
  }

  function openSplitForm(pos) {
    if (!splitForm || !dlgSplit || !pos) return;
    var maxQty = Math.max(1, (pos.quantity || 1) - 1);
    splitForm.querySelector(".js-wc-split-position-id").value = String(pos.id);
    var hint = splitForm.querySelector(".js-wc-split-hint");
    if (hint) {
      hint.textContent =
        "Сейчас " + (pos.quantity || 0) + " шт. Отрыв станет отдельной строкой со своим этапом.";
    }
    var qtyInp = splitForm.querySelector(".js-wc-split-qty");
    qtyInp.max = String(maxQty);
    qtyInp.value = String(Math.min(1, maxQty));
    openDialog(dlgSplit);
  }

  if (btnEdit) {
    btnEdit.addEventListener("click", function () {
      setEditMode(!editMode);
    });
  }
  if (btnNewCab) {
    btnNewCab.addEventListener("click", function () {
      openContractForm(null);
    });
  }

  root.querySelector(".js-wc-expand-all") && root.querySelector(".js-wc-expand-all").addEventListener("click", function () {
    contracts.forEach(function (c) { c._keepOpen = true; });
    root.querySelectorAll(".js-wc-contract").forEach(function (el) { el.open = true; });
  });
  root.querySelector(".js-wc-collapse-all") && root.querySelector(".js-wc-collapse-all").addEventListener("click", function () {
    contracts.forEach(function (c) { c._keepOpen = false; });
    root.querySelectorAll(".js-wc-contract").forEach(function (el) { el.open = false; });
  });

  document.querySelectorAll(".js-wc-dlg-cancel").forEach(function (btn) {
    btn.addEventListener("click", function () {
      closeDialog(btn.closest("dialog"));
    });
  });

  var btnOpAdd = document.querySelector(".js-wc-op-add");
  if (btnOpAdd) {
    btnOpAdd.addEventListener("click", function () {
      addOpRow("");
    });
  }

  if (cabForm) {
    cabForm.addEventListener("submit", function (ev) {
      ev.preventDefault();
      var id = (cabForm.querySelector(".js-wc-contract-id").value || "").trim();
      var name = (cabForm.querySelector(".js-wc-contract-name").value || "").trim();
      if (!name) {
        window.alert("Укажите название");
        return;
      }
      var body = {
        name: name,
        notes: cabForm.querySelector(".js-wc-contract-notes").value || ""
      };
      if (id) body.id = parseInt(id, 10);
      fetchJson(root.getAttribute("data-api-contract"), { method: "POST", body: body })
        .then(function (data) {
          upsertContractLocal(data.contract);
          data.contract._keepOpen = true;
          closeDialog(dlgCab);
          render();
        })
        .catch(function (e) { window.alert(e.message); });
    });
    var delCab = cabForm.querySelector(".js-wc-contract-del");
    if (delCab) {
      delCab.addEventListener("click", function () {
        var id = (cabForm.querySelector(".js-wc-contract-id").value || "").trim();
        if (!id) return;
        var cab = findContract(parseInt(id, 10));
        if (cab) deleteContract(cab);
        else {
          deleteContract({ id: parseInt(id, 10), name: cabForm.querySelector(".js-wc-contract-name").value || "" });
        }
      });
    }
  }

  if (posForm) {
    posForm.addEventListener("submit", function (ev) {
      ev.preventDefault();
      var id = (posForm.querySelector(".js-wc-position-id").value || "").trim();
      var contractId = parseInt(posForm.querySelector(".js-wc-position-contract-id").value, 10);
      var name = (posForm.querySelector(".js-wc-position-name").value || "").trim();
      if (!name) {
        window.alert("Укажите изделие");
        return;
      }
      var ops = collectOps();
      var body = {
        contract_id: contractId,
        name: name,
        description: posForm.querySelector(".js-wc-position-desc").value || "",
        quantity: parseInt(posForm.querySelector(".js-wc-position-qty").value, 10) || 1,
        operations: ops
      };
      if (id) body.id = parseInt(id, 10);
      var req = fetchJson(root.getAttribute("data-api-position"), { method: "POST", body: body });
      req.then(function (data) {
        var pos = data.position;
        if (id) {
          return fetchJson(detailUrl(root.getAttribute("data-api-ops-tpl"), pos.id), {
            method: "POST",
            body: { operations: ops }
          }).then(function (d2) {
            upsertPositionLocal(d2.position);
          });
        }
        upsertPositionLocal(pos);
      }).then(function () {
        var cab = findContract(contractId);
        if (cab) cab._keepOpen = true;
        closeDialog(dlgPos);
        render();
      }).catch(function (e) { window.alert(e.message); });
    });
    var delPos = posForm.querySelector(".js-wc-position-del");
    if (delPos) {
      delPos.addEventListener("click", function () {
        var id = (posForm.querySelector(".js-wc-position-id").value || "").trim();
        if (!id || !window.confirm("Удалить изделие?")) return;
        fetchJson(detailUrl(root.getAttribute("data-api-position-del-tpl"), id), { method: "POST", body: {} })
          .then(function () {
            removePositionLocal(id);
            closeDialog(dlgPos);
            render();
          })
          .catch(function (e) { window.alert(e.message); });
      });
    }
  }

  if (splitForm) {
    splitForm.addEventListener("submit", function (ev) {
      ev.preventDefault();
      var id = (splitForm.querySelector(".js-wc-split-position-id").value || "").trim();
      var qty = parseInt(splitForm.querySelector(".js-wc-split-qty").value, 10) || 0;
      if (!id || qty < 1) {
        window.alert("Укажите количество отрыва");
        return;
      }
      fetchJson(detailUrl(root.getAttribute("data-api-split-tpl"), id), {
        method: "POST",
        body: { quantity: qty }
      })
        .then(function (data) {
          if (data.parent) upsertPositionLocal(data.parent);
          if (data.child) upsertPositionLocal(data.child);
          var cab = data.parent && findContract(data.parent.contract_id);
          if (cab) cab._keepOpen = true;
          closeDialog(dlgSplit);
          render();
        })
        .catch(function (e) { window.alert(e.message); });
    });
  }

  contracts.forEach(function (c) {
    c.positions = flattenPositionsLocal(c.positions || []);
  });

  setEditMode(false);
  render();
})();
