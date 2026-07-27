(function () {
  var root = document.querySelector(".vw-page");
  if (!root) return;

  var canEdit = root.getAttribute("data-can-edit") === "1";
  var apiCabinets = root.getAttribute("data-api-cabinets") || "";
  var apiCabinetTpl = root.getAttribute("data-api-cabinet-tpl") || "";
  var apiContUpsert = root.getAttribute("data-api-container-upsert") || "";
  var apiContTpl = root.getAttribute("data-api-container-tpl") || "";
  var apiItemUpsert = root.getAttribute("data-api-item-upsert") || "";
  var apiItemDelTpl = root.getAttribute("data-api-item-del-tpl") || "";
  var apiAuditsTpl = root.getAttribute("data-api-audits-tpl") || "";

  var floorEl = root.querySelector(".js-vw-floor");
  var emptyEl = root.querySelector(".js-vw-empty");
  var modeHint = root.querySelector(".js-vw-mode-hint");
  var btnToggleEdit = root.querySelector(".js-vw-toggle-edit");

  // Модалки вне .vw-page — ищем в document и вешаем на body
  var dlgCab = document.querySelector(".js-vw-dlg-cabinet");
  var dlgCont = document.querySelector(".js-vw-dlg-container");
  var dlgContents = document.querySelector(".js-vw-dlg-contents");
  [dlgCab, dlgCont, dlgContents].forEach(function (dlg) {
    if (dlg && dlg.parentElement !== document.body) {
      document.body.appendChild(dlg);
    }
  });

  var cabForm = document.querySelector(".js-vw-cab-form");
  var contForm = document.querySelector(".js-vw-cont-form");
  var itemForm = document.querySelector(".js-vw-item-form");
  var itemsEl = document.querySelector(".js-vw-items");
  var stockToolsEl = document.querySelector(".js-vw-stock-tools");
  var rulesBlock = document.querySelector(".js-vw-rules-block");
  var auditsEl = document.querySelector(".js-vw-audits");
  var viewPane = document.querySelector(".js-vw-view-pane");
  var auditPane = document.querySelector(".js-vw-audit-pane");
  var auditLinesEl = document.querySelector(".js-vw-audit-lines");
  var auditNotesEl = document.querySelector(".js-vw-audit-notes");
  var auditMsgEl = document.querySelector(".js-vw-audit-msg");
  var btnStartAudit = document.querySelector(".js-vw-start-audit");
  var btnCancelAudit = document.querySelector(".js-vw-cancel-audit");
  var btnSaveAudit = document.querySelector(".js-vw-save-audit");
  var btnAuditAddTool = document.querySelector(".js-vw-audit-add-tool");
  var auditAddRoot = document.querySelector(".js-vw-audit-add");
  var auditNewCategory = document.querySelector(".js-vw-audit-new-category");
  var auditNewMillRow = document.querySelector(".js-vw-audit-new-mill-row");
  var auditNewMillType = document.querySelector(".js-vw-audit-new-mill-type");
  var auditNewDiamRow = document.querySelector(".js-vw-audit-new-diam-row");
  var auditNewDiameter = document.querySelector(".js-vw-audit-new-diameter");
  var auditNewSizeRow = document.querySelector(".js-vw-audit-new-size-row");
  var auditNewSize = document.querySelector(".js-vw-audit-new-size");
  var auditNewName = document.querySelector(".js-vw-audit-new-name");
  var auditNewQty = document.querySelector(".js-vw-audit-new-qty");
  var auditNewFlutesRow = document.querySelector(".js-vw-audit-new-flutes-row");
  var auditNewFlutes = document.querySelector(".js-vw-audit-new-flutes");
  var auditNewNote = document.querySelector(".js-vw-audit-new-note");
  var btnDelCab = document.querySelector(".js-vw-del-cabinet");
  var btnDelCont = document.querySelector(".js-vw-del-container");
  var btnOpenContents = document.querySelector(".js-vw-open-contents");

  var cabinets = [];
  var editMode = false;
  var openContainerId = null;
  var openContainerData = null;
  var editingCabinetId = null;
  var auditMode = false;
  var savingAudit = false;

  var CAT_LABELS = {
    end_mill: "Фрезы",
    tap: "Резьбовой",
    center_drill: "Центровки",
    countersink: "Зенкера",
    drill: "Сверла",
    insert: "Пластинки",
    collet: "Цанги",
  };
  var MILL_TYPE_LABELS = {
    end: "Концевая",
    roughing: "Обдирочная",
    t_slot: "Т-образная",
    radius: "Радиусная",
    ball: "Сферическая",
  };

  function csrfToken() {
    var m = document.cookie.match(/(?:^|; )csrftoken=([^;]+)/);
    return m ? decodeURIComponent(m[1]) : "";
  }

  function detailUrl(tpl, id) {
    return String(tpl || "").replace(/\/0\/?$/, "/" + id + "/");
  }

  function fetchJson(url, opts) {
    opts = opts || {};
    var headers = {
      "X-Requested-With": "XMLHttpRequest",
      Accept: "application/json",
    };
    if (opts.body != null || (opts.method && opts.method !== "GET")) {
      headers["X-CSRFToken"] = csrfToken();
    }
    if (opts.body != null) headers["Content-Type"] = "application/json";
    return fetch(url, {
      method: opts.method || "GET",
      credentials: "same-origin",
      headers: headers,
      body: opts.body != null ? JSON.stringify(opts.body) : undefined,
    }).then(function (res) {
      return res.text().then(function (text) {
        var data = {};
        try {
          data = text ? JSON.parse(text) : {};
        } catch (_e) {
          throw new Error(res.ok ? "Некорректный ответ сервера" : ("Ошибка " + res.status));
        }
        if (!res.ok || data.ok === false) {
          throw new Error((data && (data.error || data.message)) || ("Ошибка " + res.status));
        }
        return data;
      });
    });
  }

  function escapeHtml(s) {
    return String(s || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function setVisible(el, on) {
    if (!el) return;
    el.hidden = !on;
    el.classList.toggle("vw-is-hidden", !on);
  }

  function openDialog(dlg) {
    if (!dlg) return;
    dlg.hidden = false;
    dlg.removeAttribute("hidden");
    document.body.classList.add("vw-modal-open");
  }

  function closeDialog(dlg) {
    if (!dlg) return;
    dlg.hidden = true;
    dlg.setAttribute("hidden", "");
    if (dlg === dlgContents) setAuditMode(false);
    if (!document.querySelector(".vw-modal:not([hidden])")) {
      document.body.classList.remove("vw-modal-open");
    }
  }

  function closeAllDialogs() {
    [dlgCab, dlgCont, dlgContents].forEach(closeDialog);
  }

  function setEditMode(on) {
    editMode = !!on && canEdit;
    root.classList.toggle("is-edit", editMode);
    if (btnToggleEdit) {
      btnToggleEdit.classList.toggle("is-on", editMode);
      btnToggleEdit.setAttribute("aria-pressed", editMode ? "true" : "false");
      btnToggleEdit.textContent = editMode ? "Готово" : "Редактировать";
    }
    if (modeHint) {
      modeHint.textContent = editMode
        ? "Правка: «+» на полке — новый ящик. Клик по ящику — изменить ячейку. «Готово» — снова только просмотр содержимого."
        : "Нажмите на ящик, чтобы увидеть список инструментов";
    }
    if (itemForm) setVisible(itemForm, editMode && canEdit);
    if (rulesBlock) setVisible(rulesBlock, editMode && canEdit);
    renderFloor();
  }

  function occupiedMap(cab) {
    var map = {};
    (cab.containers || []).forEach(function (cont) {
      var st = cont.stack || 1;
      var cs = cont.col_span || 1;
      for (var c = cont.column; c < cont.column + cs; c++) {
        map[cont.shelf + ":" + st + ":" + c] = cont.id;
      }
    });
    return map;
  }

  function findFreeOnShelf(cab, shelf) {
    var occ = occupiedMap(cab);
    for (var c = 1; c <= cab.columns; c++) {
      if (!occ[shelf + ":1:" + c]) {
        return { shelf: shelf, stack: 1, column: c };
      }
    }
    return { shelf: shelf, stack: 1, column: cab.columns + 1 };
  }

  function renderFloor() {
    if (!floorEl) return;
    floorEl.querySelectorAll(".vw-cabinet").forEach(function (n) { n.remove(); });

    if (!cabinets.length) {
      setVisible(emptyEl, true);
      if (emptyEl && !floorEl.contains(emptyEl)) floorEl.appendChild(emptyEl);
      return;
    }
    setVisible(emptyEl, false);

    cabinets.forEach(function (cab) {
      floorEl.appendChild(buildCabinetCard(cab));
    });
    requestAnimationFrame(function () {
      floorEl.querySelectorAll(".vw-bin-text").forEach(fitLabelText);
    });
  }

  function cabinetKindOf(cab) {
    if (!cab) return "cabinet";
    if (cab.kind === "rack") return "rack";
    if (cab.kind === "drawer_chest") return "drawer_chest";
    return "cabinet";
  }

  function cabinetKindTitle(kind) {
    if (kind === "rack") return "стеллажа";
    if (kind === "drawer_chest") return "тумбы";
    return "шкафа";
  }

  function containerKindLabel(kind) {
    if (kind === "shelf_slot") return "На полке";
    if (kind === "drawer_cell") return "Ячейка";
    return "Контейнер";
  }

  function buildCabinetCard(cab) {
    var wrap = document.createElement("section");
    wrap.className = "vw-cabinet";
    wrap.dataset.cabinetId = String(cab.id);
    wrap.dataset.kind = cabinetKindOf(cab);

    var name = document.createElement("h2");
    name.className = "vw-cabinet-name";
    name.textContent = cab.name;
    wrap.appendChild(name);

    var frame = document.createElement("div");
    frame.className = "vw-cab-frame";

    var doorL = document.createElement("div");
    doorL.className = "vw-cab-door vw-cab-door--left";
    doorL.setAttribute("aria-hidden", "true");
    frame.appendChild(doorL);

    var interior = document.createElement("div");
    interior.className = "vw-cab-interior";
    for (var shelf = 1; shelf <= cab.shelves; shelf++) {
      interior.appendChild(buildBay(cab, shelf));
    }
    frame.appendChild(interior);

    var doorR = document.createElement("div");
    doorR.className = "vw-cab-door vw-cab-door--right";
    doorR.setAttribute("aria-hidden", "true");
    frame.appendChild(doorR);

    wrap.appendChild(frame);

    var base = document.createElement("div");
    base.className = "vw-cab-base";
    base.setAttribute("aria-hidden", "true");
    wrap.appendChild(base);

    if (canEdit) {
      var bar = document.createElement("div");
      bar.className = "vw-cabinet-toolbar";
      var btnEdit = document.createElement("button");
      btnEdit.type = "button";
      btnEdit.className = "vw-btn-ghost";
      btnEdit.textContent = "Параметры " + cabinetKindTitle(cabinetKindOf(cab));
      btnEdit.addEventListener("click", function () { openCabinetForm(cab); });
      bar.appendChild(btnEdit);
      wrap.appendChild(bar);
    }

    return wrap;
  }

  function buildDrawerBay(cab, shelf) {
    var bay = document.createElement("div");
    bay.className = "vw-bay vw-bay--drawer";

    var head = document.createElement("div");
    head.className = "vw-bay-head";
    head.textContent = "Ящик " + shelf;
    bay.appendChild(head);

    var cols = Math.max(1, parseInt(cab.columns, 10) || 1);
    var drawer = document.createElement("div");
    drawer.className = "vw-drawer";

    var handle = document.createElement("div");
    handle.className = "vw-drawer-handle";
    handle.setAttribute("aria-hidden", "true");
    drawer.appendChild(handle);

    var cells = document.createElement("div");
    cells.className = "vw-drawer-cells";
    cells.style.gridTemplateColumns = "repeat(" + cols + ", minmax(0, 1fr))";

    var onShelf = (cab.containers || []).filter(function (c) {
      return c.shelf === shelf;
    }).slice().sort(function (a, b) {
      return (a.column || 1) - (b.column || 1);
    });

    var occupied = occupiedMap(cab);

    onShelf.forEach(function (cont) {
      var span = Math.min(Math.max(1, cont.col_span || 1), cols - (cont.column || 1) + 1);
      var slot = document.createElement("div");
      slot.className = "vw-drawer-cell-slot";
      slot.style.gridColumn = (cont.column || 1) + " / span " + span;
      slot.appendChild(buildBin(cab, cont));
      cells.appendChild(slot);
    });

    if (!onShelf.length && !editMode) {
      var empty = document.createElement("div");
      empty.className = "vw-drawer-empty";
      empty.textContent = "пустой ящик";
      cells.appendChild(empty);
    }

    drawer.appendChild(cells);
    bay.appendChild(drawer);

    if (editMode) {
      var freeCol = null;
      for (var c = 1; c <= cols; c++) {
        if (!occupied[shelf + ":1:" + c]) {
          freeCol = c;
          break;
        }
      }
      var addBtn = document.createElement("button");
      addBtn.type = "button";
      addBtn.className = "vw-bay-add";
      addBtn.textContent = "+";
      addBtn.title = freeCol
        ? ("Добавить ячейку в ящик " + shelf + ", место " + freeCol)
        : ("Добавить ячейку в ящик " + shelf + " (добавить место)");
      addBtn.addEventListener("click", function (ev) {
        ev.preventDefault();
        ev.stopPropagation();
        var free = findFreeOnShelf(cab, shelf);
        openContainerForm(cab, null, free.shelf, 1, free.column);
      });
      bay.appendChild(addBtn);
    }

    return bay;
  }

  function buildBay(cab, shelf) {
    if (cabinetKindOf(cab) === "drawer_chest") {
      return buildDrawerBay(cab, shelf);
    }
    var bay = document.createElement("div");
    bay.className = "vw-bay";

    var head = document.createElement("div");
    head.className = "vw-bay-head";
    head.textContent = "Полка " + shelf;
    bay.appendChild(head);

    var cols = Math.max(1, parseInt(cab.columns, 10) || 1);
    var space = document.createElement("div");
    space.className = "vw-bay-space";
    space.style.gridTemplateColumns = "repeat(" + cols + ", minmax(0, 1fr))";
    space.style.gridAutoFlow = "row dense";

    var onShelf = (cab.containers || []).filter(function (c) {
      return c.shelf === shelf;
    });

    // Стопки: одно место слева → несколько ярусов
    var piles = {};
    var order = [];
    onShelf.forEach(function (cont) {
      var key = String(cont.column);
      if (!piles[key]) {
        piles[key] = [];
        order.push(cont.column);
      }
      piles[key].push(cont);
    });
    order.sort(function (a, b) { return a - b; });

    var occupied = occupiedMap(cab);

    order.forEach(function (col) {
      var list = piles[String(col)].slice().sort(function (a, b) {
        return (a.stack || 1) - (b.stack || 1);
      });
      var span = 1;
      list.forEach(function (cont) {
        span = Math.max(span, cont.col_span || 1);
      });
      span = Math.min(span, cols - col + 1);

      var pile = document.createElement("div");
      pile.className = "vw-pile";
      pile.style.gridColumn = col + " / span " + span;
      list.forEach(function (cont) {
        pile.appendChild(buildBin(cab, cont));
      });
      space.appendChild(pile);
    });

    if (!order.length && !editMode) {
      var empty = document.createElement("div");
      empty.className = "vw-bay-empty";
      empty.textContent = "пусто";
      space.appendChild(empty);
    }

    if (editMode) {
      // Один «+» в первой свободной ячейке этой полки (ярус 1)
      var freeCol = null;
      for (var c = 1; c <= cols; c++) {
        if (!occupied[shelf + ":1:" + c]) {
          freeCol = c;
          break;
        }
      }
      var addBtn = document.createElement("button");
      addBtn.type = "button";
      addBtn.className = "vw-bay-add";
      addBtn.textContent = "+";
      addBtn.title = freeCol
        ? ("Поставить ящик на полку " + shelf + ", место " + freeCol)
        : ("Поставить ящик на полку " + shelf + " (добавить место)");
      if (freeCol) {
        addBtn.style.gridColumn = String(freeCol);
      } else {
        // полка заполнена — кнопка в конце, расширит сетку
        addBtn.style.gridColumn = String(cols);
        addBtn.style.opacity = "0.85";
      }
      addBtn.addEventListener("click", function (ev) {
        ev.preventDefault();
        ev.stopPropagation();
        var free = findFreeOnShelf(cab, shelf);
        openContainerForm(cab, null, free.shelf, free.stack, free.column);
      });
      space.appendChild(addBtn);
    }

    bay.appendChild(space);

    var ledge = document.createElement("div");
    ledge.className = "vw-bay-ledge";
    ledge.setAttribute("aria-hidden", "true");
    bay.appendChild(ledge);

    return bay;
  }

  function contrastText(hex) {
    var h = String(hex || "").replace("#", "");
    if (h.length !== 6) return "#1a1a1a";
    var r = parseInt(h.slice(0, 2), 16);
    var g = parseInt(h.slice(2, 4), 16);
    var b = parseInt(h.slice(4, 6), 16);
    var y = (r * 299 + g * 587 + b * 114) / 1000;
    return y > 160 ? "#1a1a1a" : "#f5f5f5";
  }

  function fitLabelText(el) {
    if (!el) return;
    var minPx = 7;
    var maxPx = 12;
    var size = maxPx;
    el.style.fontSize = size + "px";
    // Shrink until each line fits width and block fits parent height.
    var guard = 0;
    while (size > minPx && guard < 40) {
      guard += 1;
      var overflowW = el.scrollWidth > el.clientWidth + 1;
      var overflowH = el.scrollHeight > el.clientHeight + 1;
      var parent = el.parentElement;
      if (parent) {
        overflowH = overflowH || el.scrollHeight > parent.clientHeight + 1;
      }
      if (!overflowW && !overflowH) break;
      size -= 0.5;
      el.style.fontSize = size + "px";
    }
  }

  function buildBin(cab, cont) {
    var isSlot = cont.kind === "shelf_slot";
    var isCell = cont.kind === "drawer_cell" || cabinetKindOf(cab) === "drawer_chest";
    var btn = document.createElement("button");
    btn.type = "button";
    if (isSlot) {
      btn.className = "vw-shelf-slot";
      btn.dataset.kind = "shelf_slot";
    } else if (isCell) {
      btn.className = "vw-drawer-cell";
      btn.dataset.kind = "drawer_cell";
    } else {
      btn.className = "vw-bin";
      btn.dataset.kind = "bin";
    }

    var labelWrap = document.createElement("span");
    labelWrap.className = "vw-bin-label";
    var color = cont.color || "#e74c3c";
    labelWrap.style.background = color;
    labelWrap.style.color = contrastText(color);

    var text = document.createElement("span");
    text.className = "vw-bin-text";
    // Keep user newlines; no auto-wrap (CSS white-space: pre)
    text.textContent = cont.label || containerKindLabel(cont.kind);
    labelWrap.appendChild(text);
    btn.appendChild(labelWrap);

    var auditDate = cont.last_audited_at || "";
    var stamp = document.createElement("span");
    stamp.className = "vw-bin-audit" + (auditDate ? "" : " is-empty");
    stamp.textContent = auditDate ? ("инв. " + auditDate.split(" ")[0]) : "не проверялся";
    btn.appendChild(stamp);

    var titleBase = cont.label || containerKindLabel(cont.kind);
    btn.title = editMode
      ? (titleBase + " — изменить")
      : (titleBase + " — список инструментов" + (auditDate ? ("; инв. " + auditDate) : ""));
    btn.addEventListener("click", function (ev) {
      ev.preventDefault();
      ev.stopPropagation();
      if (editMode) openContainerForm(cab, cont);
      else openContents(cont.id);
    });

    // Fit after layout
    requestAnimationFrame(function () {
      fitLabelText(text);
    });
    return btn;
  }

  function loadCabinets() {
    return fetchJson(apiCabinets).then(function (data) {
      cabinets = data.cabinets || [];
      renderFloor();
    }).catch(function (e) {
      if (emptyEl) {
        setVisible(emptyEl, true);
        emptyEl.innerHTML = "<p style='color:#e74c3c'>" + escapeHtml(e.message) + "</p>";
      }
    });
  }

  function syncCabinetKindLabels() {
    if (!cabForm) return;
    var kindEl = cabForm.querySelector(".js-vw-cab-kind");
    var kind = kindEl ? kindEl.value : "cabinet";
    var shelvesLabel = cabForm.querySelector(".js-vw-cab-shelves-label");
    var columnsLabel = cabForm.querySelector(".js-vw-cab-columns-label");
    var hint = cabForm.querySelector(".js-vw-cab-kind-hint");
    if (kind === "drawer_chest") {
      if (shelvesLabel) shelvesLabel.textContent = "Ярусов (ящиков)";
      if (columnsLabel) columnsLabel.textContent = "Ячеек в ящике";
      if (hint) {
        hint.textContent = "Тумба — многоярусные ящики. Число ячеек = разделители внутри каждого ящика.";
      }
    } else if (kind === "rack") {
      if (shelvesLabel) shelvesLabel.textContent = "Полок";
      if (columnsLabel) columnsLabel.textContent = "Мест в ряд (макс.)";
      if (hint) {
        hint.textContent = "Стеллаж — открытый: контейнеры или содержимое прямо на полке.";
      }
    } else {
      if (shelvesLabel) shelvesLabel.textContent = "Полок";
      if (columnsLabel) columnsLabel.textContent = "Мест в ряд (макс.)";
      if (hint) {
        hint.textContent = "Шкаф — с дверцами и контейнерами.";
      }
    }
  }

  function openCabinetForm(cab) {
    editingCabinetId = cab ? cab.id : null;
    var kind = cabinetKindOf(cab);
    cabForm.querySelector(".js-vw-cab-form-title").textContent = cab
      ? ("Параметры " + cabinetKindTitle(kind))
      : "Новая мебель";
    cabForm.querySelector(".js-vw-cab-id").value = cab ? String(cab.id) : "";
    var kindEl = cabForm.querySelector(".js-vw-cab-kind");
    if (kindEl) kindEl.value = cab ? kind : "cabinet";
    cabForm.querySelector(".js-vw-cab-name").value = cab ? cab.name : "";
    cabForm.querySelector(".js-vw-cab-shelves").value = cab ? String(cab.shelves) : (kind === "drawer_chest" ? "6" : "5");
    cabForm.querySelector(".js-vw-cab-columns").value = cab ? String(cab.columns) : (kind === "drawer_chest" ? "4" : "4");
    cabForm.querySelector(".js-vw-cab-notes").value = cab ? (cab.notes || "") : "";
    setVisible(btnDelCab, !!cab);
    if (btnDelCab) {
      btnDelCab.textContent = kind === "rack"
        ? "Удалить стеллаж"
        : (kind === "drawer_chest" ? "Удалить тумбу" : "Удалить шкаф");
    }
    syncCabinetKindLabels();
    openDialog(dlgCab);
  }

  function syncContainerKindOptions(cabKind, selected) {
    var kindSel = contForm.querySelector(".js-vw-cont-kind");
    if (!kindSel) return selected || "bin";
    var allowed;
    if (cabKind === "rack") allowed = ["bin", "shelf_slot"];
    else if (cabKind === "drawer_chest") allowed = ["drawer_cell", "bin"];
    else allowed = ["bin"];
    [].forEach.call(kindSel.options, function (opt) {
      opt.hidden = allowed.indexOf(opt.value) < 0;
      opt.disabled = opt.hidden;
    });
    var value = selected && allowed.indexOf(selected) >= 0
      ? selected
      : (cabKind === "drawer_chest" ? "drawer_cell" : "bin");
    kindSel.value = value;
    return value;
  }

  function openContainerForm(cab, cont, shelf, stack, col) {
    var cabKind = cabinetKindOf(cab);
    var contKind = cont
      ? (cont.kind === "shelf_slot"
        ? "shelf_slot"
        : (cont.kind === "drawer_cell" ? "drawer_cell" : "bin"))
      : (cabKind === "drawer_chest" ? "drawer_cell" : "bin");
    contForm.querySelector(".js-vw-cont-form-title").textContent = cont
      ? containerKindLabel(contKind)
      : (cabKind === "drawer_chest"
        ? "Новая ячейка"
        : (cabKind === "rack" ? "Новое содержимое" : "Новый контейнер"));
    contForm.querySelector(".js-vw-cont-id").value = cont ? String(cont.id) : "";
    contForm.querySelector(".js-vw-cont-cabinet").value = String(cab.id);
    var kindRow = contForm.querySelector(".js-vw-cont-kind-row");
    var kindSel = contForm.querySelector(".js-vw-cont-kind");
    if (kindRow && kindSel) {
      var showKind = cabKind === "rack" || cabKind === "drawer_chest";
      setVisible(kindRow, showKind);
      contKind = syncContainerKindOptions(cabKind, contKind);
      kindSel.disabled = !showKind;
    }
    contForm.querySelector(".js-vw-cont-label").value = cont ? cont.label : "";
    contForm.querySelector(".js-vw-cont-color").value = (cont && cont.color) || "#e74c3c";
    contForm.querySelector(".js-vw-cont-shelf").value = String(cont ? cont.shelf : shelf || 1);
    var stackEl = contForm.querySelector(".js-vw-cont-stack");
    var stackRow = contForm.querySelector(".js-vw-cont-stack-row");
    var stackHint = contForm.querySelector(".js-vw-cont-stack-hint");
    var hideStack = cabKind === "drawer_chest" || contKind === "shelf_slot" || contKind === "drawer_cell";
    if (stackEl) stackEl.value = String(hideStack ? 1 : (cont ? (cont.stack || 1) : stack || 1));
    if (stackRow) setVisible(stackRow, !hideStack);
    if (stackHint) {
      setVisible(stackHint, !hideStack);
      if (cabKind === "drawer_chest") {
        stackHint.textContent = "В тумбе каждый ярус — отдельный ящик; ячейки разделяются внутри него.";
        setVisible(stackHint, true);
      } else {
        stackHint.textContent = "Ярус 1 на полке. Ярус 2 — поверх другого ящика в том же месте.";
      }
    }
    contForm.querySelector(".js-vw-cont-column").value = String(cont ? cont.column : col || 1);
    var spanSel = contForm.querySelector(".js-vw-cont-colspan");
    var spanVal = String(cont ? (cont.col_span || 1) : 1);
    if (spanSel && spanSel.tagName === "SELECT") {
      if (![].some.call(spanSel.options, function (o) { return o.value === spanVal; })) {
        var opt = document.createElement("option");
        opt.value = spanVal;
        opt.textContent = spanVal + " места";
        spanSel.appendChild(opt);
      }
      spanSel.value = spanVal;
    }
    var notesEl = contForm.querySelector(".js-vw-cont-notes");
    if (notesEl) notesEl.value = cont ? (cont.notes || "") : "";
    // не ставим max — иначе браузер молча блокирует «Сохранить»
    contForm.querySelector(".js-vw-cont-shelf").removeAttribute("max");
    contForm.querySelector(".js-vw-cont-column").removeAttribute("max");
    var shelfLabel = contForm.querySelector(".js-vw-cont-shelf") &&
      contForm.querySelector(".js-vw-cont-shelf").closest(".vw-row") &&
      contForm.querySelector(".js-vw-cont-shelf").closest(".vw-row").querySelector(".vw-row-label");
    if (shelfLabel) {
      shelfLabel.textContent = cabKind === "drawer_chest" ? "Ящик (1 — верхний)" : "Полка (1 — верхняя)";
    }
    setVisible(btnDelCont, !!cont);
    setVisible(btnOpenContents, !!cont);
    syncPaletteActive();
    openDialog(dlgCont);
  }

  function syncPaletteActive() {
    if (!contForm) return;
    var color = contForm.querySelector(".js-vw-cont-color").value;
    document.querySelectorAll(".js-vw-palette .vw-swatch").forEach(function (s) {
      s.classList.toggle("is-active", s.getAttribute("data-color") === color);
    });
  }

  document.querySelectorAll(".js-vw-dlg-cancel").forEach(function (btn) {
    btn.addEventListener("click", function (ev) {
      ev.preventDefault();
      ev.stopPropagation();
      closeDialog(btn.closest(".vw-modal"));
    });
  });

  document.addEventListener("keydown", function (ev) {
    if (ev.key === "Escape") closeAllDialogs();
  });

  if (btnToggleEdit) {
    btnToggleEdit.addEventListener("click", function () {
      setEditMode(!editMode);
    });
  }

  var btnNew = root.querySelector(".js-vw-new-cabinet");
  if (btnNew) {
    btnNew.addEventListener("click", function () {
      if (!editMode) setEditMode(true);
      openCabinetForm(null);
    });
  }

  document.querySelectorAll(".js-vw-palette .vw-swatch").forEach(function (s) {
    s.addEventListener("click", function () {
      if (!contForm) return;
      contForm.querySelector(".js-vw-cont-color").value = s.getAttribute("data-color");
      syncPaletteActive();
    });
  });

  var cabKindSelect = document.querySelector(".js-vw-cab-kind");
  if (cabKindSelect) {
    cabKindSelect.addEventListener("change", syncCabinetKindLabels);
  }

  var savingCabinet = false;
  var savingContainer = false;

  function saveCabinet() {
    if (!cabForm || savingCabinet) return;
    var id = (cabForm.querySelector(".js-vw-cab-id").value || "").trim();
    var name = (cabForm.querySelector(".js-vw-cab-name").value || "").trim();
    if (!name) {
      window.alert("Укажите название шкафа");
      return;
    }
    savingCabinet = true;
    var kindEl = cabForm.querySelector(".js-vw-cab-kind");
    var body = {
      name: name,
      kind: kindEl ? kindEl.value : "cabinet",
      shelves: cabForm.querySelector(".js-vw-cab-shelves").value,
      columns: cabForm.querySelector(".js-vw-cab-columns").value,
      notes: cabForm.querySelector(".js-vw-cab-notes").value,
    };
    var req = id
      ? fetchJson(detailUrl(apiCabinetTpl, id), { method: "PATCH", body: body })
      : fetchJson(apiCabinets, { method: "POST", body: body });
    req.then(function () {
      closeDialog(dlgCab);
      return loadCabinets();
    }).catch(function (e) {
      window.alert(e.message);
    }).then(function () {
      savingCabinet = false;
    });
  }

  function saveContainer() {
    if (!contForm || savingContainer) return;
    var cabinetId = parseInt(contForm.querySelector(".js-vw-cont-cabinet").value, 10);
    var label = (contForm.querySelector(".js-vw-cont-label").value || "").replace(/\r\n/g, "\n").replace(/\r/g, "\n");
    label = label.replace(/[ \t]+\n/g, "\n").replace(/\n[ \t]+/g, "\n").replace(/^\n+|\n+$/g, "");
    if (!cabinetId) {
      window.alert("Не выбран шкаф — закройте окно и нажмите «+» на полке ещё раз");
      return;
    }
    if (!label.trim()) {
      window.alert("Напишите подпись на этикетке");
      contForm.querySelector(".js-vw-cont-label").focus();
      return;
    }
    savingContainer = true;
    var idVal = contForm.querySelector(".js-vw-cont-id").value;
    var notesEl = contForm.querySelector(".js-vw-cont-notes");
    var kindSel = contForm.querySelector(".js-vw-cont-kind");
    var cab = cabinets.find(function (c) { return c.id === cabinetId; });
    var cabKind = cabinetKindOf(cab);
    var contKind = "bin";
    if (cabKind === "rack" && kindSel) {
      contKind = kindSel.value === "shelf_slot" ? "shelf_slot" : "bin";
    } else if (cabKind === "drawer_chest") {
      contKind = (kindSel && kindSel.value === "bin") ? "bin" : "drawer_cell";
    }
    var stackVal = parseInt(contForm.querySelector(".js-vw-cont-stack").value, 10) || 1;
    if (contKind === "shelf_slot" || contKind === "drawer_cell" || cabKind === "drawer_chest") {
      stackVal = 1;
    }
    var body = {
      cabinet_id: cabinetId,
      kind: contKind,
      shelf: parseInt(contForm.querySelector(".js-vw-cont-shelf").value, 10) || 1,
      stack: stackVal,
      column: parseInt(contForm.querySelector(".js-vw-cont-column").value, 10) || 1,
      col_span: parseInt(contForm.querySelector(".js-vw-cont-colspan").value, 10) || 1,
      label: label,
      color: contForm.querySelector(".js-vw-cont-color").value || "#e74c3c",
      notes: notesEl ? notesEl.value : "",
    };
    if (idVal) body.id = parseInt(idVal, 10);
    var saveBtn = document.querySelector(".js-vw-cont-save");
    if (saveBtn) {
      saveBtn.disabled = true;
      saveBtn.textContent = "Сохранение…";
    }
    fetchJson(apiContUpsert, { method: "POST", body: body })
      .then(function (data) {
        closeDialog(dlgCont);
        if (data.cabinet) {
          var idx = cabinets.findIndex(function (c) { return c.id === data.cabinet.id; });
          if (idx >= 0) cabinets[idx] = data.cabinet;
        }
        return loadCabinets();
      })
      .catch(function (e) {
        window.alert(e.message || "Не удалось сохранить");
      })
      .then(function () {
        savingContainer = false;
        if (saveBtn) {
          saveBtn.disabled = false;
          saveBtn.textContent = "Сохранить";
        }
      });
  }

  // Один обработчик на документ — без onclick и без вторых listener'ов
  document.addEventListener("click", function (ev) {
    var t = ev.target;
    if (!t || !t.closest) return;
    if (t.closest(".js-vw-cab-save")) {
      ev.preventDefault();
      saveCabinet();
      return;
    }
    if (t.closest(".js-vw-cont-save")) {
      ev.preventDefault();
      saveContainer();
      return;
    }
    if (t.closest(".js-vw-item-save")) {
      ev.preventDefault();
      saveItem();
    }
  });

  if (btnDelCab) {
    btnDelCab.addEventListener("click", function () {
      var id = cabForm.querySelector(".js-vw-cab-id").value;
      if (!id) return;
      if (!confirm("Удалить шкаф и все контейнеры?")) return;
      fetchJson(detailUrl(apiCabinetTpl, id), { method: "DELETE" })
        .then(function () {
          closeDialog(dlgCab);
          return loadCabinets();
        })
        .catch(function (e) { alert(e.message); });
    });
  }

  if (btnDelCont) {
    btnDelCont.addEventListener("click", function () {
      var id = contForm.querySelector(".js-vw-cont-id").value;
      if (!id) return;
      if (!confirm("Удалить контейнер?")) return;
      fetchJson(detailUrl(apiContTpl, id), { method: "DELETE" })
        .then(function () {
          closeDialog(dlgCont);
          return loadCabinets();
        })
        .catch(function (e) { alert(e.message); });
    });
  }

  if (btnOpenContents) {
    btnOpenContents.addEventListener("click", function () {
      var id = contForm.querySelector(".js-vw-cont-id").value;
      if (!id) return;
      closeDialog(dlgCont);
      openContents(id);
    });
  }

  function saveItem() {
    if (!openContainerId || !itemForm) return;
    var title = (itemForm.querySelector(".js-vw-item-title").value || "").trim();
    if (!title) {
      alert("Укажите, что лежит");
      return;
    }
    var category = itemForm.querySelector(".js-vw-item-category").value;
    var millTypeEl = itemForm.querySelector(".js-vw-item-mill-type");
    var body = {
      container_id: openContainerId,
      title: title,
      tool_category: category,
      mill_type: category === "end_mill" && millTypeEl ? millTypeEl.value : "",
      diameter_from_mm: itemForm.querySelector(".js-vw-item-dfrom").value,
      diameter_to_mm: itemForm.querySelector(".js-vw-item-dto").value,
      quantity_note: itemForm.querySelector(".js-vw-item-qty").value,
    };
    fetchJson(apiItemUpsert, { method: "POST", body: body })
      .then(function () {
        itemForm.querySelector(".js-vw-item-title").value = "";
        itemForm.querySelector(".js-vw-item-dfrom").value = "";
        itemForm.querySelector(".js-vw-item-dto").value = "";
        itemForm.querySelector(".js-vw-item-qty").value = "";
        if (millTypeEl) millTypeEl.value = "";
        return openContents(openContainerId);
      })
      .then(function () { return loadCabinets(); })
      .catch(function (e) { alert(e.message); });
  }

  function syncItemMillTypeRow() {
    if (!itemForm) return;
    var cat = itemForm.querySelector(".js-vw-item-category");
    var row = itemForm.querySelector(".js-vw-item-mill-type-row");
    if (!cat || !row) return;
    var show = cat.value === "end_mill";
    row.hidden = !show;
    if (!show) {
      var mt = itemForm.querySelector(".js-vw-item-mill-type");
      if (mt) mt.value = "";
    }
  }

  function appendToolStockMeta(metaEl, tool, extraParts) {
    var parts = [];
    if (tool.category_label) parts.push(tool.category_label);
    if (tool.mill_type_label) parts.push(tool.mill_type_label);
    if (tool.diameter_mm != null) parts.push("Ø " + tool.diameter_mm);
    if (tool.tool_material_label) parts.push(tool.tool_material_label);
    if (Array.isArray(extraParts)) {
      extraParts.forEach(function (p) {
        if (p) parts.push(p);
      });
    }
    if (tool.notes) parts.push(tool.notes);

    var line = document.createElement("div");
    line.textContent = parts.join(" · ") || "—";
    metaEl.appendChild(line);

    var badges = document.createElement("div");
    badges.className = "vw-tool-badges";

    var coating = tool.coating_type || "none";
    var coatWrap = document.createElement("span");
    coatWrap.className = "vw-coating-cell";
    coatWrap.title = tool.coating_title || tool.coating_label || "";
    var coatDot = document.createElement("span");
    coatDot.className = "vw-coating-dot swatch-" + coating;
    coatWrap.appendChild(coatDot);
    if (coating === "none") {
      var coatLab = document.createElement("span");
      coatLab.className = "vw-coating-label";
      coatLab.textContent = "без покрытия";
      coatWrap.appendChild(coatLab);
    }
    badges.appendChild(coatWrap);

    var codes = tool.work_material_codes || [];
    if (codes.length) {
      var wmWrap = document.createElement("span");
      wmWrap.className = "vw-wm-squares";
      codes.forEach(function (code) {
        var sq = document.createElement("span");
        sq.className = "vw-wm-square wm-" + String(code || "").toLowerCase();
        sq.textContent = code;
        sq.title = tool.work_material_label || code;
        wmWrap.appendChild(sq);
      });
      badges.appendChild(wmWrap);
    } else if (tool.work_material_label) {
      var wmTxt = document.createElement("span");
      wmTxt.className = "vw-wm-text";
      wmTxt.textContent = tool.work_material_label;
      badges.appendChild(wmTxt);
    }

    metaEl.appendChild(badges);
  }

  function renderStockTools(container) {
    if (!stockToolsEl) return;
    stockToolsEl.innerHTML = "";
    var tools = container.stock_tools || [];
    if (!tools.length) {
      stockToolsEl.innerHTML =
        "<li class='vw-item'><span class='vw-item-meta'>На складе нет подходящих инструментов. " +
        (editMode
          ? "Добавьте правило содержимого ниже (категория и Ø)."
          : "В режиме «Редактировать» можно настроить содержимое ящика.") +
        "</span></li>";
      return;
    }
    tools.forEach(function (tool) {
      var li = document.createElement("li");
      li.className = "vw-item";
      var top = document.createElement("div");
      top.className = "vw-item-top";
      var left = document.createElement("div");
      var title = document.createElement("div");
      title.className = "vw-item-title";
      title.textContent = tool.name || "Инструмент";
      left.appendChild(title);
      var meta = document.createElement("div");
      meta.className = "vw-item-meta";
      appendToolStockMeta(meta, tool, ["кол-во: " + (tool.quantity != null ? tool.quantity : 0)]);
      left.appendChild(meta);
      top.appendChild(left);
      var qty = document.createElement("span");
      qty.className = "vw-item-qty";
      qty.textContent = String(tool.quantity != null ? tool.quantity : 0);
      qty.title = "Количество на складе";
      top.appendChild(qty);
      li.appendChild(top);
      stockToolsEl.appendChild(li);
    });
  }

  function renderAudits(audits) {
    if (!auditsEl) return;
    auditsEl.innerHTML = "";
    if (!audits || !audits.length) {
      auditsEl.innerHTML = "<p class='vw-item-meta'>Проверок ещё не было.</p>";
      return;
    }
    audits.forEach(function (a) {
      var card = document.createElement("article");
      card.className = "vw-audit-card";
      var head = document.createElement("div");
      head.className = "vw-audit-card-head";
      head.textContent =
        (a.audited_at || "") +
        " · " +
        (a.audited_by || "—") +
        (a.changes_count
          ? (" · изменено " + a.changes_count)
          : " · без расхождений");
      card.appendChild(head);
      if (a.notes) {
        var note = document.createElement("p");
        note.className = "vw-item-meta";
        note.textContent = a.notes;
        card.appendChild(note);
      }
      var changed = (a.lines || []).filter(function (ln) {
        return ln.status === "adjusted" || ln.delta;
      });
      if (changed.length) {
        var ul = document.createElement("ul");
        ul.className = "vw-audit-changes";
        changed.forEach(function (ln) {
          var li = document.createElement("li");
          var sign = ln.delta > 0 ? "+" : "";
          li.textContent =
            (ln.tool_name || ("#" + ln.tool_id)) +
            ": " +
            ln.expected_qty +
            "→" +
            ln.counted_qty +
            " (" +
            sign +
            ln.delta +
            ")" +
            (ln.note ? " — " + ln.note : "");
          ul.appendChild(li);
        });
        card.appendChild(ul);
      }
      auditsEl.appendChild(card);
    });
  }

  function loadAudits(containerId) {
    if (!apiAuditsTpl) return Promise.resolve([]);
    return fetchJson(detailUrl(apiAuditsTpl, containerId)).then(function (data) {
      renderAudits(data.audits || []);
      return data.audits || [];
    }).catch(function () {
      renderAudits([]);
      return [];
    });
  }

  function setAuditMode(on) {
    auditMode = !!on && canEdit;
    setVisible(viewPane, !auditMode);
    setVisible(auditPane, auditMode);
    if (btnStartAudit) setVisible(btnStartAudit, !auditMode && canEdit);
    if (!auditMode && auditMsgEl) auditMsgEl.textContent = "";
  }

  function defaultAuditCategory() {
    var items = (openContainerData && openContainerData.items) || [];
    for (var i = 0; i < items.length; i++) {
      if (items[i].tool_category) return items[i].tool_category;
    }
    var tools = (openContainerData && openContainerData.stock_tools) || [];
    if (tools.length && tools[0].category) return tools[0].category;
    return "end_mill";
  }

  function syncAuditNewFields() {
    var cat = auditNewCategory ? auditNewCategory.value : "";
    var isMill = cat === "end_mill";
    var isTap = cat === "tap";
    var needsDiam = cat === "end_mill" || cat === "drill" || cat === "center_drill" || cat === "countersink";
    if (auditNewMillRow) auditNewMillRow.hidden = !isMill;
    if (auditNewFlutesRow) auditNewFlutesRow.hidden = !isMill;
    if (auditNewDiamRow) auditNewDiamRow.hidden = !needsDiam;
    if (auditNewSizeRow) auditNewSizeRow.hidden = !isTap;
  }

  function prefillsAuditNewForm() {
    if (auditNewCategory) auditNewCategory.value = defaultAuditCategory();
    if (auditNewQty) auditNewQty.value = "1";
    if (auditNewName) auditNewName.value = "";
    if (auditNewDiameter) auditNewDiameter.value = "";
    if (auditNewSize) auditNewSize.value = "";
    if (auditNewFlutes) auditNewFlutes.value = "";
    if (auditNewNote) auditNewNote.value = "";
    if (auditNewMillType) auditNewMillType.value = "end";
    var items = (openContainerData && openContainerData.items) || [];
    for (var i = 0; i < items.length; i++) {
      var it = items[i];
      if (it.diameter_from_mm != null && auditNewDiameter && !auditNewDiameter.value) {
        auditNewDiameter.value = String(it.diameter_from_mm);
      }
      if (it.mill_type && auditNewMillType) auditNewMillType.value = it.mill_type;
      break;
    }
    syncAuditNewFields();
    if (auditAddRoot) auditAddRoot.open = false;
  }

  function appendAuditRow(opts) {
    if (!auditLinesEl) return;
    var row = document.createElement("div");
    row.className = "vw-audit-row" + (opts.isNew ? " is-new" : "");
    if (opts.isNew) {
      row.dataset.isNew = "1";
      row.dataset.newPayload = JSON.stringify(opts.payload || {});
    } else {
      row.dataset.toolId = String(opts.toolId);
    }
    row.dataset.expected = String(opts.expected != null ? opts.expected : 0);

    var name = document.createElement("div");
    name.className = "vw-audit-row-name";
    var nameTitle = document.createElement("div");
    nameTitle.textContent = opts.name || ("#" + (opts.toolId || ""));
    name.appendChild(nameTitle);
    var meta = document.createElement("div");
    meta.className = "vw-item-meta";
    if (opts.isNew) {
      meta.textContent = (opts.meta || "новый") + " · ожидается: 0";
    } else if (opts.tool) {
      appendToolStockMeta(meta, opts.tool, [
        "ожидается: " + (opts.expected != null ? opts.expected : 0),
      ]);
    } else {
      meta.textContent = "ожидается: " + (opts.expected != null ? opts.expected : 0);
    }
    name.appendChild(meta);
    if (opts.isNew) {
      var del = document.createElement("button");
      del.type = "button";
      del.className = "vw-item-del";
      del.textContent = "×";
      del.title = "Убрать из списка";
      del.addEventListener("click", function () {
        row.remove();
      });
      var top = document.createElement("div");
      top.className = "vw-item-top";
      top.appendChild(name);
      top.appendChild(del);
      row.appendChild(top);
    } else {
      row.appendChild(name);
    }

    var countedLabel = document.createElement("label");
    countedLabel.className = "vw-audit-field";
    countedLabel.innerHTML = "<span>Факт</span>";
    var countedInp = document.createElement("input");
    countedInp.type = "number";
    countedInp.min = "0";
    countedInp.step = "1";
    countedInp.className = "vw-control js-vw-audit-counted";
    countedInp.value = String(opts.counted != null ? opts.counted : 0);
    countedLabel.appendChild(countedInp);
    row.appendChild(countedLabel);

    var noteLabel = document.createElement("label");
    noteLabel.className = "vw-audit-field vw-audit-field--note";
    noteLabel.innerHTML = "<span>Примечание</span>";
    var noteInp = document.createElement("input");
    noteInp.type = "text";
    noteInp.maxLength = 300;
    noteInp.className = "vw-control js-vw-audit-note";
    noteInp.placeholder = opts.isNew ? "Новый инструмент" : "Если расхождение — почему";
    if (opts.note) noteInp.value = opts.note;
    noteLabel.appendChild(noteInp);
    row.appendChild(noteLabel);

    auditLinesEl.appendChild(row);
  }

  function startAuditMode() {
    if (!canEdit || !openContainerData) return;
    var tools = openContainerData.stock_tools || [];
    if (!auditLinesEl) return;
    auditLinesEl.innerHTML = "";
    if (auditNotesEl) auditNotesEl.value = "";
    if (auditMsgEl) auditMsgEl.textContent = "";
    tools.forEach(function (tool) {
      appendAuditRow({
        toolId: tool.id,
        tool: tool,
        name: tool.name || ("#" + tool.id),
        expected: tool.quantity != null ? tool.quantity : 0,
        counted: tool.quantity != null ? tool.quantity : 0,
      });
    });
    prefillsAuditNewForm();
    setAuditMode(true);
  }

  function cancelAuditMode() {
    setAuditMode(false);
  }

  function addNewToolToAuditList() {
    if (!auditMode || !auditLinesEl) return;
    var category = auditNewCategory ? auditNewCategory.value : "";
    if (!category) {
      alert("Выберите категорию");
      return;
    }
    var qty = parseInt(auditNewQty && auditNewQty.value, 10);
    if (isNaN(qty) || qty < 0) qty = 0;
    var diameter = auditNewDiameter ? auditNewDiameter.value : "";
    var sizeLabel = auditNewSize ? (auditNewSize.value || "").trim() : "";
    var name = auditNewName ? (auditNewName.value || "").trim() : "";
    var millType = category === "end_mill" && auditNewMillType ? auditNewMillType.value : "";
    var flutes = auditNewFlutes ? auditNewFlutes.value : "";
    var note = auditNewNote ? (auditNewNote.value || "").trim() : "";

    var needsDiam = category === "end_mill" || category === "drill" || category === "center_drill" || category === "countersink";
    if (needsDiam && (diameter === "" || isNaN(parseFloat(diameter)))) {
      alert("Укажите диаметр");
      return;
    }
    if (category === "tap" && !sizeLabel) {
      alert("Укажите размер метчика (например M6)");
      return;
    }
    if ((category === "insert" || category === "collet") && !name) {
      alert("Укажите название");
      return;
    }

    var payload = {
      category: category,
      mill_type: millType,
      diameter_mm: needsDiam ? diameter : "",
      size_label: sizeLabel,
      name: name,
      quantity: qty,
      flutes_count: flutes,
      note: note || "найден при инвентаризации",
    };
    var metaParts = [CAT_LABELS[category] || category];
    if (millType) metaParts.push(MILL_TYPE_LABELS[millType] || millType);
    if (needsDiam) metaParts.push("Ø " + diameter);
    if (sizeLabel) metaParts.push(sizeLabel);
    appendAuditRow({
      isNew: true,
      name: name || ((CAT_LABELS[category] || category) + (needsDiam ? (" Ø" + diameter) : (sizeLabel ? (" " + sizeLabel) : ""))),
      meta: metaParts.join(" · "),
      expected: 0,
      counted: qty,
      note: payload.note,
      payload: payload,
    });
    if (auditNewName) auditNewName.value = "";
    if (auditNewNote) auditNewNote.value = "";
    if (auditNewQty) auditNewQty.value = "1";
    if (auditAddRoot) auditAddRoot.open = false;
  }

  function saveAudit() {
    if (!openContainerId || savingAudit || !auditLinesEl) return;
    var rows = auditLinesEl.querySelectorAll(".vw-audit-row");
    if (!rows.length) {
      alert("Нет позиций для проверки. Добавьте инструмент или отмените.");
      return;
    }
    var lines = [];
    var newTools = [];
    var ok = true;
    rows.forEach(function (row) {
      var countedInp = row.querySelector(".js-vw-audit-counted");
      var noteInp = row.querySelector(".js-vw-audit-note");
      var counted = parseInt(countedInp && countedInp.value, 10);
      if (isNaN(counted) || counted < 0) counted = 0;
      var note = noteInp ? noteInp.value : "";
      if (row.dataset.isNew === "1") {
        var payload = {};
        try {
          payload = JSON.parse(row.dataset.newPayload || "{}");
        } catch (e) {
          ok = false;
          return;
        }
        payload.quantity = counted;
        payload.note = note || payload.note || "найден при инвентаризации";
        newTools.push(payload);
      } else {
        var toolId = parseInt(row.dataset.toolId, 10);
        lines.push({
          tool_id: toolId,
          counted_qty: counted,
          note: note,
        });
      }
    });
    if (!ok) {
      alert("Ошибка в данных нового инструмента");
      return;
    }
    savingAudit = true;
    if (btnSaveAudit) {
      btnSaveAudit.disabled = true;
      btnSaveAudit.textContent = "Сохранение…";
    }
    if (auditMsgEl) {
      auditMsgEl.textContent = "";
      auditMsgEl.classList.remove("is-error");
    }
    fetchJson(detailUrl(apiAuditsTpl, openContainerId), {
      method: "POST",
      body: {
        notes: auditNotesEl ? auditNotesEl.value : "",
        lines: lines,
        new_tools: newTools,
      },
    })
      .then(function (data) {
        var changes = (data.audit && data.audit.changes_count) || 0;
        if (auditMsgEl) {
          auditMsgEl.textContent = changes
            ? ("Проверка сохранена: изменено " + changes)
            : "Проверка сохранена: без расхождений";
        }
        if (data.container) {
          openContainerData = data.container;
          applyContentsView(data.container);
        }
        setAuditMode(false);
        return loadAudits(openContainerId).then(function () {
          return loadCabinets();
        });
      })
      .catch(function (e) {
        if (auditMsgEl) {
          auditMsgEl.textContent = e.message || "Ошибка";
          auditMsgEl.classList.add("is-error");
        } else {
          alert(e.message);
        }
      })
      .then(function () {
        savingAudit = false;
        if (btnSaveAudit) {
          btnSaveAudit.disabled = false;
          btnSaveAudit.textContent = "Сохранить проверку";
        }
      });
  }

  function applyContentsView(cont) {
    var titleEl = document.querySelector(".js-vw-contents-title");
    var metaEl = document.querySelector(".js-vw-contents-meta");
    if (titleEl) titleEl.textContent = cont.label;
    if (metaEl) {
      var n = (cont.stock_tools || []).length;
      var parts = [
        "Полка " + cont.shelf + ", место " + cont.column,
        "позиций: " + n,
      ];
      if (cont.notes) parts.splice(1, 0, cont.notes);
      if (cont.last_audited_at) {
        parts.push("инв. " + cont.last_audited_at + (cont.last_audited_by ? (" · " + cont.last_audited_by) : ""));
      } else {
        parts.push("инвентаризация не проводилась");
      }
      metaEl.textContent = parts.join(" · ");
    }
    renderStockTools(cont);
    renderItems(cont);
  }

  function renderItems(container) {
    if (!itemsEl) return;
    itemsEl.innerHTML = "";
    var items = container.items || [];
    if (!items.length) {
      itemsEl.innerHTML = "<li class='vw-item'><span class='vw-item-meta'>Правил пока нет — список выше строится по подписи ящика.</span></li>";
      return;
    }
    items.forEach(function (it) {
      var li = document.createElement("li");
      li.className = "vw-item";
      var top = document.createElement("div");
      top.className = "vw-item-top";
      var left = document.createElement("div");
      var title = document.createElement("div");
      title.className = "vw-item-title";
      title.textContent = it.title;
      left.appendChild(title);
      var meta = document.createElement("div");
      meta.className = "vw-item-meta";
      var parts = [];
      if (it.tool_category) parts.push(CAT_LABELS[it.tool_category] || it.tool_category);
      if (it.tool_category === "end_mill" && it.mill_type) {
        parts.push(MILL_TYPE_LABELS[it.mill_type] || it.mill_type);
      }
      if (it.diameter_from_mm != null || it.diameter_to_mm != null) {
        parts.push("Ø " + (it.diameter_from_mm != null ? it.diameter_from_mm : "?") + "–" + (it.diameter_to_mm != null ? it.diameter_to_mm : "?"));
      }
      if (it.quantity_note) parts.push(it.quantity_note);
      if (it.stock_qty != null) parts.push("на складе: " + it.stock_qty);
      meta.textContent = parts.join(" · ") || "—";
      left.appendChild(meta);
      top.appendChild(left);
      if (canEdit && editMode) {
        var del = document.createElement("button");
        del.type = "button";
        del.className = "vw-item-del";
        del.textContent = "×";
        del.addEventListener("click", function () {
          if (!confirm("Удалить?")) return;
          fetchJson(detailUrl(apiItemDelTpl, it.id), { method: "DELETE" })
            .then(function () { return openContents(container.id); })
            .then(function () { return loadCabinets(); })
            .catch(function (e) { alert(e.message); });
        });
        top.appendChild(del);
      }
      li.appendChild(top);
      itemsEl.appendChild(li);
    });
  }

  function openContents(containerId) {
    openContainerId = containerId;
    setAuditMode(false);
    if (itemForm) setVisible(itemForm, editMode && canEdit);
    if (rulesBlock) setVisible(rulesBlock, editMode && canEdit);
    return fetchJson(detailUrl(apiContTpl, containerId)).then(function (data) {
      var cont = data.container;
      openContainerData = cont;
      applyContentsView(cont);
      openDialog(dlgContents);
      return loadAudits(containerId);
    }).catch(function (e) { alert(e.message); });
  }

  if (btnStartAudit) {
    btnStartAudit.addEventListener("click", function () {
      startAuditMode();
    });
  }
  if (btnCancelAudit) {
    btnCancelAudit.addEventListener("click", function () {
      cancelAuditMode();
    });
  }
  if (btnSaveAudit) {
    btnSaveAudit.addEventListener("click", function () {
      saveAudit();
    });
  }
  if (btnAuditAddTool) {
    btnAuditAddTool.addEventListener("click", function () {
      addNewToolToAuditList();
    });
  }
  if (auditNewCategory) {
    auditNewCategory.addEventListener("change", syncAuditNewFields);
  }

  if (itemForm) {
    var catSel = itemForm.querySelector(".js-vw-item-category");
    if (catSel) catSel.addEventListener("change", syncItemMillTypeRow);
    syncItemMillTypeRow();
  }

  setEditMode(false);
  loadCabinets();
})();
