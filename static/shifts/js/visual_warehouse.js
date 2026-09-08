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
  var apiPhotosTpl = root.getAttribute("data-api-photos-tpl") || "";
  var apiPhotoDelTpl = root.getAttribute("data-api-photo-del-tpl") || "";
  var auditOkDays = Math.max(1, parseInt(root.getAttribute("data-audit-ok-days"), 10) || 30);
  var auditWarnDays = Math.max(auditOkDays, parseInt(root.getAttribute("data-audit-warn-days"), 10) || 90);

  var floorEl = root.querySelector(".js-vw-floor");
  var emptyEl = root.querySelector(".js-vw-empty");
  var modeHint = root.querySelector(".js-vw-mode-hint");
  var btnToggleEdit = root.querySelector(".js-vw-toggle-edit");

  // Модалки вне .vw-page — ищем в document и вешаем на body
  var dlgCab = document.querySelector(".js-vw-dlg-cabinet");
  var dlgCont = document.querySelector(".js-vw-dlg-container");
  var dlgContents = document.querySelector(".js-vw-dlg-contents");
  var dlgAudits = document.querySelector(".js-vw-dlg-audits");
  var dlgPhoto = document.querySelector(".js-vw-dlg-photo");
  [dlgCab, dlgCont, dlgContents, dlgAudits, dlgPhoto].forEach(function (dlg) {
    if (dlg && dlg.parentElement !== document.body) {
      document.body.appendChild(dlg);
    }
  });

  var cabForm = document.querySelector(".js-vw-cab-form");
  var contForm = document.querySelector(".js-vw-cont-form");
  var itemForm = document.querySelector(".js-vw-item-form");
  var itemsEl = document.querySelector(".js-vw-items");
  var stockToolsEl = document.querySelector(".js-vw-stock-tools");
  var toolsCountEl = document.querySelector(".js-vw-tools-count");
  var rulesBlock = document.querySelector(".js-vw-rules-block");
  var auditsEl = document.querySelector(".js-vw-audits");
  var auditsMetaEl = document.querySelector(".js-vw-audits-meta");
  var btnShowAudits = document.querySelector(".js-vw-show-audits");
  var btnShowAuditsLabel = document.querySelector(".js-vw-show-audits-label");
  var subEl = document.querySelector(".js-vw-contents-sub");
  var statsEl = document.querySelector(".js-vw-contents-stats");
  var photosEl = document.querySelector(".js-vw-photos");
  var photoUploadWrap = document.querySelector(".js-vw-photo-upload");
  var photoFileInput = document.querySelector(".js-vw-photo-file");
  var photoPickBtn = document.querySelector(".js-vw-photo-pick");
  var photoPickLabel = document.querySelector(".js-vw-photo-pick-label");
  var photoPickNameEl = document.querySelector(".js-vw-photo-pick-name");
  var photoMsgEl = document.querySelector(".js-vw-photo-msg");
  var photoViewTitle = document.querySelector(".js-vw-photo-view-title");
  var photoViewImg = document.querySelector(".js-vw-photo-view-img");
  var photoViewMeta = document.querySelector(".js-vw-photo-view-meta");
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
  var auditNewTapTypeRow = document.querySelector(".js-vw-audit-new-tap-type-row");
  var auditNewTapType = document.querySelector(".js-vw-audit-new-tap-type");
  var auditNewHoleRow = document.querySelector(".js-vw-audit-new-hole-row");
  var auditNewHoleType = document.querySelector(".js-vw-audit-new-hole-type");
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
    body_tool: "Корпусной инструмент",
    tap: "Резьбовой",
    center_drill: "Центровки",
    countersink: "Зенкера",
    drill: "Сверла",
    reamer: "Развертки",
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
  var TAP_TYPE_LABELS = {
    cutting: "Режущий метчик",
    forming: "Метчик-раскатник",
    thread_mill: "Резьбофреза",
  };
  var HOLE_TYPE_LABELS = {
    through: "Сквозное",
    blind: "Глухое",
    any: "Универсальное",
  };
  var THREAD_KIND_LABELS = {
    standard: "Стандарт",
    non_standard: "Не стандарт",
  };
  var COUNTERSINK_TYPE_LABELS = {
    hand: "Ручной",
    machine: "Машинный",
  };
  var SUBTYPE_OPTIONS = {};
  try {
    var subtypeEl = document.getElementById("vw-subtype-options");
    if (subtypeEl) SUBTYPE_OPTIONS = JSON.parse(subtypeEl.textContent || "{}") || {};
  } catch (e) {
    SUBTYPE_OPTIONS = {};
  }

  function csrfToken() {
    var m = document.cookie.match(/(?:^|; )csrftoken=([^;]+)/);
    return m ? decodeURIComponent(m[1]) : "";
  }

  function detailUrl(tpl, id) {
    var s = String(tpl || "");
    var sid = encodeURIComponent(String(id));
    if (!s) return s;
    // Placeholder pk=0: /…/0/ или /…/0/audits/
    if (s.indexOf("/0/") !== -1) return s.replace("/0/", "/" + sid + "/");
    if (/\/0\/?$/.test(s)) return s.replace(/\/0\/?$/, "/" + sid + "/");
    return s;
  }

  function containerAuditsUrl(containerId) {
    var base = detailUrl(apiContTpl, containerId);
    if (base) return String(base).replace(/\/?$/, "/") + "audits/";
    return detailUrl(apiAuditsTpl, containerId);
  }

  function containerPhotosUrl(containerId) {
    var base = detailUrl(apiContTpl, containerId);
    if (base) return String(base).replace(/\/?$/, "/") + "photos/";
    return detailUrl(apiPhotosTpl, containerId);
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

  function fetchForm(url, formData, method) {
    return fetch(url, {
      method: method || "POST",
      credentials: "same-origin",
      headers: {
        "X-Requested-With": "XMLHttpRequest",
        Accept: "application/json",
        "X-CSRFToken": csrfToken(),
      },
      body: formData,
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

  function todayIsoDate() {
    var d = new Date();
    var m = String(d.getMonth() + 1).padStart(2, "0");
    var day = String(d.getDate()).padStart(2, "0");
    return d.getFullYear() + "-" + m + "-" + day;
  }

  function formatBinAuditDate(raw) {
    var s = String(raw || "").trim();
    if (!s) return "";
    var datePart = s.split(" ")[0];
    var m = /^(\d{2})\.(\d{2})\.(\d{4})$/.exec(datePart);
    if (m) return m[1] + "." + m[2] + "." + m[3].slice(-2);
    var iso = s.slice(0, 10);
    var p = iso.split("-");
    if (p.length === 3 && p[0].length === 4) {
      return p[2] + "." + p[1] + "." + p[0].slice(-2);
    }
    return datePart;
  }

  function parseAuditDate(cont) {
    var iso = String((cont && cont.last_audited_at_iso) || "").trim();
    if (iso) {
      var d = new Date(iso);
      if (!isNaN(d.getTime())) return d;
    }
    var raw = String((cont && cont.last_audited_at) || "").trim();
    if (!raw) return null;
    var datePart = raw.split(" ")[0];
    var m = /^(\d{2})\.(\d{2})\.(\d{4})$/.exec(datePart);
    if (m) {
      return new Date(parseInt(m[3], 10), parseInt(m[2], 10) - 1, parseInt(m[1], 10));
    }
    var p = datePart.split("-");
    if (p.length === 3 && p[0].length === 4) {
      return new Date(parseInt(p[0], 10), parseInt(p[1], 10) - 1, parseInt(p[2], 10));
    }
    return null;
  }

  function auditFreshnessClass(cont) {
    var d = parseAuditDate(cont);
    if (!d) return "is-overdue";
    var now = new Date();
    var start = new Date(d.getFullYear(), d.getMonth(), d.getDate());
    var today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    var days = Math.floor((today - start) / 86400000);
    if (days < 0) days = 0;
    if (days <= auditOkDays) return "is-ok";
    if (days <= auditWarnDays) return "is-warn";
    return "is-overdue";
  }

  function auditFreshnessTitle(cls, auditDate) {
    if (cls === "is-ok") return "Инвентаризация актуальна" + (auditDate ? (" (" + auditDate + ")") : "");
    if (cls === "is-warn") return "Пора планировать инвентаризацию" + (auditDate ? (" (" + auditDate + ")") : "");
    return auditDate
      ? ("Нужно провести инвентаризацию (последняя " + auditDate + ")")
      : "Инвентаризация не проводилась";
  }

  function syncPhotoUploadLabel() {
    if (!photoPickLabel) return;
    var hasPhoto =
      !!(openContainerData && ((openContainerData.photos && openContainerData.photos.length) || openContainerData.content_photo_date));
    photoPickLabel.textContent = hasPhoto ? "Заменить фото" : "Загрузить фото";
  }

  function resetPhotoPickUi() {
    if (photoFileInput) photoFileInput.value = "";
    if (photoPickNameEl) photoPickNameEl.textContent = "";
    if (photoPickBtn) photoPickBtn.disabled = false;
    if (photoMsgEl) photoMsgEl.textContent = "";
    syncPhotoUploadLabel();
  }

  function setPhotoUploadBusy(busy, message) {
    if (photoPickBtn) photoPickBtn.disabled = !!busy;
    if (photoPickNameEl && message) photoPickNameEl.textContent = message;
    if (photoMsgEl && message) photoMsgEl.textContent = message;
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
    [dlgCab, dlgCont, dlgContents, dlgAudits, dlgPhoto].forEach(closeDialog);
  }

  function pad2(n) {
    var v = Math.max(0, parseInt(n, 10) || 0);
    return v < 10 ? "0" + v : String(v);
  }

  function shelfDisplayLabel(cab, shelfTop1) {
    var total = Math.max(1, parseInt(cab && cab.shelves, 10) || 1);
    var top = Math.max(1, Math.min(parseInt(shelfTop1, 10) || 1, total));
    return pad2(total - top + 1);
  }

  function placeDisplayLabel(col) {
    return pad2(Math.max(1, parseInt(col, 10) || 1));
  }

  function suggestAddress(cab, shelf, col) {
    var code = (cab && (cab.code || "")).toString().trim().toUpperCase() || "?";
    return code + "-" + shelfDisplayLabel(cab, shelf) + "-" + placeDisplayLabel(col);
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
        ? "Правка: «+» или пустое место — создать место/контейнер. Клик по ящику — изменить. Содержимое задаётся на складе (адрес). «Готово» — просмотр."
        : "Нажмите на контейнер: список по адресу со склада и инвентаризация";
    }
    if (itemForm) setVisible(itemForm, false);
    if (rulesBlock) setVisible(rulesBlock, false);
    if (photoUploadWrap) setVisible(photoUploadWrap, editMode && canEdit);
    document.body.classList.toggle("vw-is-edit", editMode);
    syncItemMillTypeRow();
    if (openContainerData) renderPhotos(openContainerData);
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

    var sorted = cabinets.slice().sort(function (a, b) {
      var so = (a.sort_order || 0) - (b.sort_order || 0);
      if (so) return so;
      var ca = String(a.code || "").localeCompare(String(b.code || ""), "ru");
      if (ca) return ca;
      var na = String(a.name || "").localeCompare(String(b.name || ""), "ru");
      if (na) return na;
      return (a.id || 0) - (b.id || 0);
    });
    sorted.forEach(function (cab) {
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
    if (kind === "organizer") return "Органайзер";
    return "Контейнер";
  }

  function buildCabinetCard(cab) {
    var wrap = document.createElement("section");
    wrap.className = "vw-cabinet";
    wrap.dataset.cabinetId = String(cab.id);
    wrap.dataset.kind = cabinetKindOf(cab);
    wrap.style.setProperty("--vw-cols", String(Math.max(1, parseInt(cab.columns, 10) || 1)));

    var name = document.createElement("h2");
    name.className = "vw-cabinet-name";
    var code = (cab.code || "").toString().trim().toUpperCase();
    name.textContent = code ? (code + " — " + (cab.name || "")) : (cab.name || "");
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

  function makeShelfNumEl(cab, shelf) {
    var shelfNum = document.createElement("span");
    shelfNum.className = "vw-shelf-num";
    shelfNum.textContent = shelfDisplayLabel(cab, shelf);
    shelfNum.title = "Полка " + shelfDisplayLabel(cab, shelf);
    return shelfNum;
  }

  function buildDrawerBay(cab, shelf) {
    var bay = document.createElement("div");
    bay.className = "vw-bay vw-bay--drawer";

    var cols = Math.max(1, parseInt(cab.columns, 10) || 1);
    var drawer = document.createElement("div");
    drawer.className = "vw-drawer";

    var handle = document.createElement("div");
    handle.className = "vw-drawer-handle";
    handle.appendChild(makeShelfNumEl(cab, shelf));
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

    for (var col = 1; col <= cols; col++) {
      var contAt = null;
      for (var i = 0; i < onShelf.length; i++) {
        var c0 = onShelf[i];
        var start = c0.column || 1;
        var span0 = Math.min(Math.max(1, c0.col_span || 1), cols - start + 1);
        if (col >= start && col < start + span0) {
          if (col === start) contAt = c0;
          else contAt = false; // covered by span
          break;
        }
      }
      if (contAt === false) continue;
      if (contAt) {
        var span = Math.min(Math.max(1, contAt.col_span || 1), cols - (contAt.column || 1) + 1);
        var slot = document.createElement("div");
        slot.className = "vw-drawer-cell-slot";
        slot.style.gridColumn = (contAt.column || 1) + " / span " + span;
        slot.appendChild(buildBin(cab, contAt));
        cells.appendChild(slot);
      } else {
        var emptySlot = document.createElement("div");
        emptySlot.className = "vw-drawer-cell-slot";
        emptySlot.style.gridColumn = String(col);
        emptySlot.appendChild(buildEmptyDrawerCell(cab, shelf, col));
        cells.appendChild(emptySlot);
      }
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
        ? ("Добавить ячейку в ящик " + shelfDisplayLabel(cab, shelf) + ", место " + placeDisplayLabel(freeCol))
        : ("Добавить ячейку в ящик " + shelfDisplayLabel(cab, shelf) + " (добавить место)");
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
    var isRack = cabinetKindOf(cab) === "rack";
    var bay = document.createElement("div");
    bay.className = "vw-bay" + (isRack ? " vw-bay--rack" : "");

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

    // Полная сетка мест с номерами: и на шкафу, и на стеллаже
    for (var col = 1; col <= cols; col++) {
      var list = (piles[String(col)] || []).slice().sort(function (a, b) {
        return (a.stack || 1) - (b.stack || 1);
      });
      if (list.length) {
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
      } else if (!occupied[shelf + ":1:" + col]) {
        space.appendChild(buildEmptyShelfCell(cab, shelf, col));
      }
    }

    if (editMode) {
      // Один «+» только если полка заполнена (расширить число мест)
      var freeCol = null;
      for (var c = 1; c <= cols; c++) {
        if (!occupied[shelf + ":1:" + c]) {
          freeCol = c;
          break;
        }
      }
      if (freeCol === null) {
        var addBtn = document.createElement("button");
        addBtn.type = "button";
        addBtn.className = "vw-bay-add";
        addBtn.textContent = "+";
        addBtn.title = (isRack ? "Добавить на полку " : "Поставить ящик на полку ") +
          shelfDisplayLabel(cab, shelf) + " (добавить место)";
        addBtn.style.gridColumn = String(cols);
        addBtn.style.opacity = "0.85";
        addBtn.addEventListener("click", function (ev) {
          ev.preventDefault();
          ev.stopPropagation();
          var free = findFreeOnShelf(cab, shelf);
          openContainerForm(cab, null, free.shelf, free.stack, free.column);
        });
        space.appendChild(addBtn);
      }
    }

    bay.appendChild(space);

    var ledge = document.createElement("div");
    ledge.className = "vw-bay-ledge";
    ledge.appendChild(makeShelfNumEl(cab, shelf));
    bay.appendChild(ledge);

    return bay;
  }

  function buildEmptyShelfCell(cab, shelf, col) {
    var btn = document.createElement("button");
    btn.type = "button";
    btn.className = "vw-shelf-empty";
    btn.style.gridColumn = String(col);
    var placeLab = placeDisplayLabel(col);
    var num = document.createElement("span");
    num.className = "vw-place-num";
    num.textContent = placeLab;
    btn.appendChild(num);
    if (editMode) {
      var plus = document.createElement("span");
      plus.className = "vw-shelf-empty-plus";
      plus.textContent = "+";
      btn.appendChild(plus);
    }
    btn.title = editMode
      ? ("Добавить на полку " + shelfDisplayLabel(cab, shelf) + ", место " + placeLab)
      : ("Полка " + shelfDisplayLabel(cab, shelf) + ", место " + placeLab + " — пусто");
    btn.addEventListener("click", function (ev) {
      ev.preventDefault();
      ev.stopPropagation();
      if (editMode && canEdit) {
        openContainerForm(cab, null, shelf, 1, col);
      }
    });
    if (!editMode || !canEdit) {
      btn.disabled = true;
    }
    return btn;
  }

  function buildEmptyDrawerCell(cab, shelf, col) {
    var btn = document.createElement("button");
    btn.type = "button";
    btn.className = "vw-drawer-empty-cell";
    var placeLab = placeDisplayLabel(col);
    var num = document.createElement("span");
    num.className = "vw-place-num";
    num.textContent = placeLab;
    btn.appendChild(num);
    if (editMode) {
      var plus = document.createElement("span");
      plus.className = "vw-shelf-empty-plus";
      plus.textContent = "+";
      btn.appendChild(plus);
    }
    btn.title = editMode
      ? ("Добавить ячейку в ящик " + shelfDisplayLabel(cab, shelf) + ", место " + placeLab)
      : ("Ящик " + shelfDisplayLabel(cab, shelf) + ", место " + placeLab + " — пусто");
    btn.addEventListener("click", function (ev) {
      ev.preventDefault();
      ev.stopPropagation();
      if (editMode && canEdit) {
        openContainerForm(cab, null, shelf, 1, col);
      }
    });
    if (!editMode || !canEdit) {
      btn.disabled = true;
    }
    return btn;
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

  function buildOrganizer(cab, cont) {
    var wrap = document.createElement("div");
    wrap.className = "vw-organizer";
    wrap.dataset.kind = "organizer";
    wrap.dataset.containerId = String(cont.id);

    if (!cont.parent_id) {
      var orgPlace = document.createElement("span");
      orgPlace.className = "vw-place-num";
      orgPlace.textContent = placeDisplayLabel(cont.column);
      orgPlace.title = "Место " + placeDisplayLabel(cont.column);
      wrap.appendChild(orgPlace);
    }

    var title = document.createElement("div");
    title.className = "vw-organizer-title";
    title.textContent = cont.label || "Органайзер";
    wrap.appendChild(title);

    var tiers = Math.max(1, parseInt(cont.inner_tiers, 10) || 1);
    var cols = Math.max(1, parseInt(cont.inner_columns, 10) || 1);
    var children = (cont.children || []).slice().sort(function (a, b) {
      return (a.shelf - b.shelf) || (a.column - b.column);
    });
    var byKey = {};
    children.forEach(function (ch) {
      byKey[ch.shelf + ":" + ch.column] = ch;
    });

    for (var t = 1; t <= tiers; t++) {
      var tier = document.createElement("div");
      tier.className = "vw-organizer-tier";
      var handle = document.createElement("div");
      handle.className = "vw-organizer-tier-handle";
      handle.setAttribute("aria-hidden", "true");
      tier.appendChild(handle);
      var cells = document.createElement("div");
      cells.className = "vw-organizer-tier-cells";
      cells.style.gridTemplateColumns = "repeat(" + cols + ", minmax(0, 1fr))";
      for (var c = 1; c <= cols; c++) {
        var slot = document.createElement("div");
        slot.className = "vw-drawer-cell-slot";
        var child = byKey[t + ":" + c];
        if (child) {
          slot.appendChild(buildBin(cab, child));
        } else {
          var empty = document.createElement("div");
          empty.className = "vw-drawer-empty";
          empty.style.padding = "8px 2px";
          empty.textContent = "—";
          slot.appendChild(empty);
        }
        cells.appendChild(slot);
      }
      tier.appendChild(cells);
      wrap.appendChild(tier);
    }

    if (editMode && canEdit) {
      var editBtn = document.createElement("button");
      editBtn.type = "button";
      editBtn.className = "vw-organizer-edit";
      editBtn.textContent = "Параметры органайзера";
      editBtn.addEventListener("click", function (ev) {
        ev.preventDefault();
        ev.stopPropagation();
        openContainerForm(cab, cont);
      });
      wrap.appendChild(editBtn);
    }
    return wrap;
  }

  function buildBin(cab, cont) {
    if (cont.kind === "organizer") {
      return buildOrganizer(cab, cont);
    }
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

    if (!cont.parent_id) {
      var placeBadge = document.createElement("span");
      placeBadge.className = "vw-place-num";
      placeBadge.textContent = placeDisplayLabel(cont.column);
      placeBadge.title = "Место " + placeDisplayLabel(cont.column);
      btn.appendChild(placeBadge);
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

    var auditDate = formatBinAuditDate(cont.last_audited_at || "");
    var freshCls = auditFreshnessClass(cont);
    var footer = document.createElement("span");
    footer.className = "vw-bin-footer";
    var stamp = document.createElement("span");
    stamp.className = "vw-bin-audit " + freshCls + (auditDate ? "" : " is-empty");
    stamp.textContent = auditDate || "—";
    stamp.title = auditFreshnessTitle(freshCls, auditDate);
    footer.appendChild(stamp);
    btn.appendChild(footer);

    var titleBase = cont.label || containerKindLabel(cont.kind);
    var placeLab = placeDisplayLabel(cont.column);
    btn.title = editMode
      ? (titleBase + " · место " + placeLab + " — изменить")
      : (titleBase + " · место " + placeLab + " — список инструментов" + (auditDate ? ("; инв. " + auditDate) : ""));
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
    var codeEl = cabForm.querySelector(".js-vw-cab-code");
    if (codeEl) codeEl.value = cab ? (cab.code || "") : "";
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

  function syncContainerKindOptions(cabKind, selected, isChild) {
    var kindSel = contForm.querySelector(".js-vw-cont-kind");
    if (!kindSel) return selected || "bin";
    var allowed;
    if (isChild) allowed = ["drawer_cell"];
    else if (cabKind === "rack") allowed = ["shelf_slot", "bin", "organizer"];
    else if (cabKind === "drawer_chest") allowed = ["drawer_cell", "bin"];
    else allowed = ["bin", "organizer"];
    [].forEach.call(kindSel.options, function (opt) {
      var ok = allowed.indexOf(opt.value) >= 0;
      opt.hidden = !ok;
      opt.disabled = !ok;
    });
    var value = selected && allowed.indexOf(selected) >= 0
      ? selected
      : allowed[0];
    kindSel.value = value;
    if (kindSel.value !== value) {
      [].forEach.call(kindSel.options, function (opt) {
        if (opt.value === value) opt.selected = true;
      });
    }
    return value;
  }

  function syncOrganizerFields(contKind, cont) {
    var orgRow = contForm.querySelector(".js-vw-cont-organizer-row");
    var orgHint = contForm.querySelector(".js-vw-cont-organizer-hint");
    var show = contKind === "organizer";
    setVisible(orgRow, show);
    setVisible(orgHint, show);
    var tiersEl = contForm.querySelector(".js-vw-cont-inner-tiers");
    var colsEl = contForm.querySelector(".js-vw-cont-inner-cols");
    if (tiersEl) tiersEl.value = String(cont && cont.inner_tiers ? cont.inner_tiers : 3);
    if (colsEl) colsEl.value = String(cont && cont.inner_columns ? cont.inner_columns : 2);
  }

  function openContainerForm(cab, cont, shelf, stack, col) {
    var cabKind = cabinetKindOf(cab);
    var isChild = !!(cont && cont.parent_id);
    var contKind = cont
      ? (cont.kind === "shelf_slot"
        ? "shelf_slot"
        : (cont.kind === "organizer"
          ? "organizer"
          : (cont.kind === "drawer_cell" || isChild ? "drawer_cell" : "bin")))
      : (cabKind === "rack" ? "shelf_slot" : (cabKind === "drawer_chest" ? "drawer_cell" : "bin"));
    contForm.querySelector(".js-vw-cont-form-title").textContent = cont
      ? (isChild ? "Ячейка органайзера" : containerKindLabel(contKind))
      : (cabKind === "drawer_chest"
        ? "Новая ячейка"
        : (cabKind === "rack" ? "Новое место" : "Новый контейнер"));
    contForm.querySelector(".js-vw-cont-id").value = cont ? String(cont.id) : "";
    contForm.querySelector(".js-vw-cont-cabinet").value = String(cab.id);
    var kindRow = contForm.querySelector(".js-vw-cont-kind-row");
    var kindSel = contForm.querySelector(".js-vw-cont-kind");
    if (kindRow && kindSel) {
      setVisible(kindRow, true);
      contKind = syncContainerKindOptions(cabKind, contKind, isChild);
      kindSel.disabled = isChild;
    }
    syncOrganizerFields(contKind, cont);
    contForm.querySelector(".js-vw-cont-label").value = cont ? cont.label : "";
    contForm.querySelector(".js-vw-cont-color").value = (cont && cont.color) || "#e74c3c";
    contForm.querySelector(".js-vw-cont-shelf").value = String(cont ? cont.shelf : shelf || 1);
    var stackEl = contForm.querySelector(".js-vw-cont-stack");
    var stackRow = contForm.querySelector(".js-vw-cont-stack-row");
    var stackHint = contForm.querySelector(".js-vw-cont-stack-hint");
    var hideStack = isChild || cabKind === "drawer_chest" || contKind === "shelf_slot" || contKind === "drawer_cell" || contKind === "organizer";
    if (stackEl) stackEl.value = String(hideStack ? 1 : (cont ? (cont.stack || 1) : stack || 1));
    if (stackRow) setVisible(stackRow, !hideStack);
    if (stackHint) {
      if (contKind === "organizer") {
        stackHint.textContent = "Органайзер может занимать несколько мест по ширине — так подписи ячеек читаются нормально.";
        setVisible(stackHint, true);
      } else if (isChild) {
        stackHint.textContent = "Подпись ячейки (например «M2 СК»). Ярус и место — внутри органайзера.";
        setVisible(stackHint, true);
      } else if (cabKind === "drawer_chest") {
        stackHint.textContent = "В тумбе каждый ярус — отдельный ящик; ячейки разделяются внутри него.";
        setVisible(stackHint, true);
      } else if (hideStack) {
        stackHint.textContent = "Для этого типа ярус всегда 1.";
        setVisible(stackHint, true);
      } else {
        stackHint.textContent = "Ярус 1 на полке. Ярус 2 — поверх другого ящика в том же месте.";
        setVisible(stackHint, true);
      }
    }
    contForm.querySelector(".js-vw-cont-column").value = String(cont ? cont.column : col || 1);
    var addressEl = contForm.querySelector(".js-vw-cont-address");
    if (addressEl) {
      var addr = cont && cont.address
        ? cont.address
        : suggestAddress(
          cab,
          cont ? cont.shelf : (shelf || 1),
          cont ? cont.column : (col || 1)
        );
      addressEl.value = addr || "";
    }
    var spanSel = contForm.querySelector(".js-vw-cont-colspan");
    var preferredSpan = 1;
    if (contKind === "organizer") {
      var innerCols = cont
        ? Math.max(1, parseInt(cont.inner_columns, 10) || 1)
        : Math.max(1, parseInt((contForm.querySelector(".js-vw-cont-inner-cols") || {}).value, 10) || 2);
      preferredSpan = Math.max(cont ? (cont.col_span || 1) : 2, Math.min(innerCols, 3));
      if (!cont) preferredSpan = Math.max(2, Math.min(innerCols, 3));
    } else if (cont) {
      preferredSpan = cont.col_span || 1;
    }
    var spanVal = String(preferredSpan);
    if (spanSel && spanSel.tagName === "SELECT") {
      if (![].some.call(spanSel.options, function (o) { return o.value === spanVal; })) {
        var opt = document.createElement("option");
        opt.value = spanVal;
        opt.textContent = spanVal + " места";
        spanSel.appendChild(opt);
      }
      spanSel.value = spanVal;
      spanSel.disabled = isChild;
    }
    var notesEl = contForm.querySelector(".js-vw-cont-notes");
    if (notesEl) notesEl.value = cont ? (cont.notes || "") : "";
    // не ставим max — иначе браузер молча блокирует «Сохранить»
    contForm.querySelector(".js-vw-cont-shelf").removeAttribute("max");
    contForm.querySelector(".js-vw-cont-column").removeAttribute("max");
    var shelfLabel = contForm.querySelector(".js-vw-cont-shelf") &&
      contForm.querySelector(".js-vw-cont-shelf").closest(".vw-row") &&
      contForm.querySelector(".js-vw-cont-shelf").closest(".vw-row").querySelector(".vw-row-label");
    function syncShelfLabelHint() {
      if (!shelfLabel) return;
      if (isChild) {
        shelfLabel.textContent = "Ярус внутри";
        return;
      }
      var shelfInp = contForm.querySelector(".js-vw-cont-shelf");
      var shelfVal = parseInt(shelfInp && shelfInp.value, 10) || 1;
      var disp = shelfDisplayLabel(cab, shelfVal);
      if (cabKind === "drawer_chest") {
        shelfLabel.textContent = "Ящик (1 — верхний, на экране " + disp + ")";
      } else {
        shelfLabel.textContent = "Полка (1 — верхняя, на экране " + disp + ")";
      }
    }
    syncShelfLabelHint();
    var shelfInpForHint = contForm.querySelector(".js-vw-cont-shelf");
    if (shelfInpForHint && !shelfInpForHint._vwShelfHintBound) {
      shelfInpForHint._vwShelfHintBound = true;
      shelfInpForHint.addEventListener("input", function () {
        var cabId = parseInt(contForm.querySelector(".js-vw-cont-cabinet").value, 10);
        var currentCab = cabinets.find(function (c) { return c.id === cabId; }) || cab;
        var labelEl = shelfInpForHint.closest(".vw-row") &&
          shelfInpForHint.closest(".vw-row").querySelector(".vw-row-label");
        if (!labelEl) return;
        var parentId = contForm.dataset.parentId;
        if (parentId) {
          labelEl.textContent = "Ярус внутри";
          return;
        }
        var shelfVal = parseInt(shelfInpForHint.value, 10) || 1;
        var disp = shelfDisplayLabel(currentCab, shelfVal);
        var kindNow = cabinetKindOf(currentCab);
        labelEl.textContent = kindNow === "drawer_chest"
          ? ("Ящик (1 — верхний, на экране " + disp + ")")
          : ("Полка (1 — верхняя, на экране " + disp + ")");
      });
    }
    var colLabel = contForm.querySelector(".js-vw-cont-column") &&
      contForm.querySelector(".js-vw-cont-column").closest(".vw-row") &&
      contForm.querySelector(".js-vw-cont-column").closest(".vw-row").querySelector(".vw-row-label");
    if (colLabel) {
      colLabel.textContent = isChild ? "Ячейка слева" : "Место слева";
    }
    // parent id for child cells
    contForm.dataset.parentId = cont && cont.parent_id ? String(cont.parent_id) : "";
    setVisible(btnDelCont, !!cont);
    setVisible(btnOpenContents, !!cont && contKind !== "organizer");
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

  var btnSuggestAddress = document.querySelector(".js-vw-cont-address-suggest");
  if (btnSuggestAddress) {
    btnSuggestAddress.addEventListener("click", function () {
      if (!contForm) return;
      var cabId = parseInt(contForm.querySelector(".js-vw-cont-cabinet").value, 10);
      var cab = cabinets.find(function (c) { return c.id === cabId; });
      if (!cab) return;
      var shelf = parseInt(contForm.querySelector(".js-vw-cont-shelf").value, 10) || 1;
      var column = parseInt(contForm.querySelector(".js-vw-cont-column").value, 10) || 1;
      var addressEl = contForm.querySelector(".js-vw-cont-address");
      if (addressEl) addressEl.value = suggestAddress(cab, shelf, column);
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
  var contKindSelect = document.querySelector(".js-vw-cont-kind");
  if (contKindSelect) {
    contKindSelect.addEventListener("change", function () {
      var cabId = parseInt(contForm.querySelector(".js-vw-cont-cabinet").value, 10);
      var cab = cabinets.find(function (c) { return c.id === cabId; });
      var kind = contKindSelect.value;
      syncOrganizerFields(kind, null);
      var hideStack = kind === "shelf_slot" || kind === "drawer_cell" || kind === "organizer" || cabinetKindOf(cab) === "drawer_chest";
      var stackRow = contForm.querySelector(".js-vw-cont-stack-row");
      if (stackRow) setVisible(stackRow, !hideStack);
      var spanSel = contForm.querySelector(".js-vw-cont-colspan");
      if (spanSel) {
        spanSel.disabled = false;
        if (kind === "organizer") {
          var colsEl = contForm.querySelector(".js-vw-cont-inner-cols");
          var innerCols = Math.max(1, parseInt(colsEl && colsEl.value, 10) || 2);
          var prefer = String(Math.max(2, Math.min(innerCols, 3)));
          if (![].some.call(spanSel.options, function (o) { return o.value === prefer; })) {
            var opt = document.createElement("option");
            opt.value = prefer;
            opt.textContent = prefer + " места";
            spanSel.appendChild(opt);
          }
          if (parseInt(spanSel.value, 10) < 2) spanSel.value = prefer;
        }
      }
    });
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
    var codeEl = cabForm.querySelector(".js-vw-cab-code");
    var body = {
      name: name,
      code: codeEl ? (codeEl.value || "").trim() : "",
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
    var rawKind = kindSel ? kindSel.value : "bin";
    var parentId = parseInt(contForm.dataset.parentId || "", 10) || 0;
    var contKind = "bin";
    if (parentId) {
      contKind = "drawer_cell";
    } else if (rawKind === "organizer") {
      contKind = "organizer";
    } else if (cabKind === "rack") {
      contKind = rawKind === "shelf_slot" ? "shelf_slot" : (rawKind === "organizer" ? "organizer" : "bin");
    } else if (cabKind === "drawer_chest") {
      contKind = rawKind === "bin" ? "bin" : "drawer_cell";
    } else {
      contKind = rawKind === "organizer" ? "organizer" : "bin";
    }
    var stackVal = parseInt(contForm.querySelector(".js-vw-cont-stack").value, 10) || 1;
    if (contKind === "shelf_slot" || contKind === "drawer_cell" || contKind === "organizer" || cabKind === "drawer_chest") {
      stackVal = 1;
    }
    var tiersEl = contForm.querySelector(".js-vw-cont-inner-tiers");
    var colsEl = contForm.querySelector(".js-vw-cont-inner-cols");
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
      inner_tiers: tiersEl ? parseInt(tiersEl.value, 10) || 3 : 3,
      inner_columns: colsEl ? parseInt(colsEl.value, 10) || 2 : 2,
    };
    var addressEl = contForm.querySelector(".js-vw-cont-address");
    if (addressEl) body.address = (addressEl.value || "").trim();
    if (parentId) body.parent_id = parentId;
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

  function val(sel) {
    var el = itemForm && itemForm.querySelector(sel);
    return el ? (el.value || "").trim() : "";
  }
  function setVal(sel, v) {
    var el = itemForm && itemForm.querySelector(sel);
    if (el) el.value = v == null ? "" : String(v);
  }

  function saveItem() {
    if (!openContainerId || !itemForm) return;
    var title = val(".js-vw-item-title");
    if (!title) {
      alert("Укажите, что лежит");
      return;
    }
    var ruleKind = val(".js-vw-item-rule-kind") || "include";
    var category = val(".js-vw-item-category");
    if (ruleKind === "exclude" && !category) {
      alert("Для исключения выберите категорию (или исключите конкретный инструмент из списка выше).");
      return;
    }
    var body = {
      container_id: openContainerId,
      title: title,
      rule_kind: ruleKind,
      tool_category: category,
      mill_type: category === "end_mill" ? val(".js-vw-f-mill_type") : "",
      flutes_count:
        category === "end_mill"
          ? val(".js-vw-f-flutes")
          : category === "countersink"
            ? val(".js-vw-f-cs_flutes")
            : category === "reamer"
              ? val(".js-vw-f-reamer_flutes")
              : "",
      corner_radius_mm: category === "end_mill" ? val(".js-vw-f-corner-r") : "",
      body_cutter_type: category === "body_tool" ? val(".js-vw-f-body_cutter") : "",
      body_family: category === "body_tool" ? val(".js-vw-f-body_family") : "",
      brand: category === "body_tool" ? val(".js-vw-f-brand") : "",
      shank_type: category === "body_tool" ? val(".js-vw-f-shank") : "",
      mount_thread: category === "body_tool" ? val(".js-vw-f-mount_thread") : "",
      teeth_count: category === "body_tool" ? val(".js-vw-f-teeth") : "",
      coolant_filter: category === "body_tool" ? val(".js-vw-f-coolant") : "",
      insert_compat: category === "body_tool" ? val(".js-vw-f-insert_compat") : "",
      tap_type: category === "tap" ? val(".js-vw-f-tap_type") : "",
      thread_kind: category === "tap" ? val(".js-vw-f-thread_kind") : "",
      thread_standard: category === "tap" ? val(".js-vw-f-thread_standard") : "",
      hole_type: category === "tap" ? val(".js-vw-f-hole_type") : "",
      size_label: category === "tap" ? val(".js-vw-f-size") : (category === "countersink" ? val(".js-vw-f-cs_size") : ""),
      pitch_mm: category === "tap" ? val(".js-vw-f-pitch") : "",
      insert_family: category === "insert" ? val(".js-vw-f-ins_family") : "",
      insert_shape: category === "insert" ? val(".js-vw-f-ins_shape") : "",
      collet_type: category === "collet" ? val(".js-vw-f-collet_type") : "",
      collet_er_size: category === "collet" ? val(".js-vw-f-er_size") : "",
      countersink_type: category === "countersink" ? val(".js-vw-f-countersink_type") : "",
      angle_deg:
        category === "countersink"
          ? val(".js-vw-f-cs_angle")
          : category === "center_drill"
            ? val(".js-vw-f-cd_angle")
            : category === "drill"
              ? val(".js-vw-f-drill_angle")
              : category === "reamer"
                ? val(".js-vw-f-reamer_accuracy")
                : "",
      diameter_from_mm: itemForm.querySelector(".js-vw-item-dfrom").value,
      diameter_to_mm: itemForm.querySelector(".js-vw-item-dto").value,
      quantity_note: val(".js-vw-item-qty"),
    };
    fetchJson(apiItemUpsert, { method: "POST", body: body })
      .then(function () {
        itemForm.querySelectorAll("input.vw-control, select.vw-control").forEach(function (el) {
          if (el.classList.contains("js-vw-item-rule-kind")) return;
          if (el.classList.contains("js-vw-item-category")) {
            el.value = "";
            return;
          }
          if (el.tagName === "SELECT") el.selectedIndex = 0;
          else el.value = "";
        });
        syncItemFilterFields();
        return openContents(openContainerId);
      })
      .then(function () { return loadCabinets(); })
      .catch(function (e) { alert(e.message); });
  }

  function syncItemRuleKindUi() {
    if (!itemForm) return;
    var kindEl = itemForm.querySelector(".js-vw-item-rule-kind");
    var heading = itemForm.querySelector(".js-vw-item-form-heading");
    var titleLabel = itemForm.querySelector(".js-vw-item-title-label");
    var saveBtn = itemForm.querySelector(".js-vw-item-save");
    var titleInput = itemForm.querySelector(".js-vw-item-title");
    var isExclude = kindEl && kindEl.value === "exclude";
    if (heading) heading.textContent = isExclude ? "Добавить исключение" : "Добавить содержимое";
    if (titleLabel) titleLabel.textContent = isExclude ? "Что исключить" : "Что лежит";
    if (saveBtn) saveBtn.textContent = isExclude ? "Исключить" : "Добавить";
    if (titleInput) {
      titleInput.placeholder = isExclude ? "Напр. раскатники / M8" : "Режущие нестандарт / Головки APKT";
    }
  }

  function syncItemFilterFields() {
    if (!itemForm) return;
    var catEl = itemForm.querySelector(".js-vw-item-category");
    var diamRow = itemForm.querySelector(".js-vw-item-diam-row");
    if (!catEl) return;
    var cat = catEl.value;
    itemForm.querySelectorAll(".js-vw-item-panel").forEach(function (panel) {
      setVisible(panel, panel.getAttribute("data-cat") === cat);
    });
    var showDiam =
      cat === "end_mill" ||
      cat === "body_tool" ||
      cat === "drill" ||
      cat === "reamer" ||
      cat === "center_drill" ||
      cat === "countersink" ||
      cat === "tap";
    if (diamRow) setVisible(diamRow, showDiam);
    if (!showDiam) {
      setVal(".js-vw-item-dfrom", "");
      setVal(".js-vw-item-dto", "");
    }
    syncItemRuleKindUi();
  }

  function syncItemMillTypeRow() {
    syncItemFilterFields();
  }

  function appendToolStockMeta(metaEl, tool, extraParts) {
    if (!metaEl || !tool) return;

    var typeLabel = (tool.type_label || tool.category_label || "").trim();
    if (typeLabel) {
      var typeLine = document.createElement("div");
      typeLine.className = "vw-tool-type";
      typeLine.textContent = typeLabel;
      metaEl.appendChild(typeLine);
    }

    var specsText = (tool.specs || "").trim();
    if (!specsText || specsText === "—") {
      var fallback = [];
      if (tool.subtype_label) fallback.push(tool.subtype_label);
      else if (tool.mill_type_label) fallback.push(tool.mill_type_label);
      if (tool.hole_type_label) fallback.push(tool.hole_type_label);
      if (tool.size_label) fallback.push(tool.size_label);
      if (tool.diameter_mm != null) fallback.push("Ø " + tool.diameter_mm);
      if (tool.corner_radius_mm != null) fallback.push("R " + tool.corner_radius_mm);
      if (tool.overall_length_mm != null) fallback.push("L " + tool.overall_length_mm);
      if (tool.cutting_length_mm != null) fallback.push("Lc " + tool.cutting_length_mm);
      if (tool.flutes_count != null) fallback.push("Z " + tool.flutes_count);
      if (tool.pitch_mm != null) fallback.push("шаг " + tool.pitch_mm);
      if (tool.angle_deg != null && tool.angle_deg !== "") fallback.push("∠ " + tool.angle_deg);
      if (tool.main_diameter_mm != null) fallback.push("Dосн " + tool.main_diameter_mm);
      specsText = fallback.join(" · ");
    }
    if (specsText) {
      var specsLine = document.createElement("div");
      specsLine.className = "vw-tool-specs";
      specsLine.textContent = specsText;
      metaEl.appendChild(specsLine);
    }

    var parts = [];
    if (tool.tool_material_label) parts.push(tool.tool_material_label);
    if (Array.isArray(extraParts)) {
      extraParts.forEach(function (p) {
        if (p) parts.push(p);
      });
    }
    if (tool.notes) parts.push(tool.notes);
    if (parts.length) {
      var line = document.createElement("div");
      line.textContent = parts.join(" · ");
      metaEl.appendChild(line);
    }

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


    metaEl.appendChild(badges);
  }

  function excludeStockTool(tool) {
    if (!openContainerId || !tool || !tool.id) return;
    var label = (tool.name || tool.type_label || ("#" + tool.id)).trim();
    var body = {
      container_id: openContainerId,
      title: "Исключить: " + label,
      rule_kind: "exclude",
      tool_category: tool.category || "",
      tool_item_id: tool.id,
      mill_type: "",
      tap_type: "",
      hole_type: "",
      countersink_type: "",
      collet_type: "",
      size_label: "",
      diameter_from_mm: "",
      diameter_to_mm: "",
      quantity_note: "",
    };
    fetchJson(apiItemUpsert, { method: "POST", body: body })
      .then(function () { return openContents(openContainerId); })
      .then(function () { return loadCabinets(); })
      .catch(function (e) { alert(e.message); });
  }

  function renderStockTools(container) {
    if (!stockToolsEl) return;
    stockToolsEl.innerHTML = "";
    var tools = container.stock_tools || [];
    if (toolsCountEl) {
      if (tools.length) {
        toolsCountEl.hidden = false;
        toolsCountEl.textContent = String(tools.length);
      } else {
        toolsCountEl.hidden = true;
        toolsCountEl.textContent = "";
      }
    }
    if (!tools.length) {
      var addr = (container && container.address) || "";
      stockToolsEl.innerHTML =
        "<li class='vw-item vw-item--empty'><span class='vw-item-meta'>" +
        (addr
          ? ("На адресе " + addr + " пока нет позиций. На складе у инструмента выберите мебель / полку / место.")
          : "У места нет адреса. Создайте контейнер на визуальном складе, затем назначьте адрес позиции на складе.") +
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
      title.textContent = tool.type_label || tool.name || "Инструмент";
      left.appendChild(title);
      if (tool.name && tool.type_label && tool.name !== tool.type_label) {
        var nameSub = document.createElement("div");
        nameSub.className = "vw-item-subname";
        nameSub.textContent = tool.name;
        left.appendChild(nameSub);
      }
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
    syncAuditsButton(audits);
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
          var kind = ln.delta > 0 ? "surplus" : (ln.delta < 0 ? "deficit" : "");
          if (kind) li.className = "is-" + kind;
          var title = ln.delta > 0 ? "Излишек" : (ln.delta < 0 ? "Недостача" : "Изменение");
          li.textContent =
            title +
            ": " +
            (ln.tool_name || ("#" + ln.tool_id)) +
            " — было " +
            ln.expected_qty +
            ", факт " +
            ln.counted_qty +
            " (" +
            sign +
            ln.delta +
            ")" +
            (ln.note ? ". " + ln.note : "");
          ul.appendChild(li);
        });
        card.appendChild(ul);
      }
      auditsEl.appendChild(card);
    });
  }

  function syncAuditsButton(audits) {
    if (!btnShowAuditsLabel) return;
    var n = (audits || []).length;
    btnShowAuditsLabel.textContent = n ? "История (" + n + ")" : "История";
  }

  function appendContentsStat(parent, label, value, muted) {
    var item = document.createElement("div");
    item.className = "vw-contents-stat" + (muted ? " is-muted" : "");
    var lbl = document.createElement("span");
    lbl.className = "vw-contents-stat-label";
    lbl.textContent = label;
    var val = document.createElement("span");
    val.className = "vw-contents-stat-value";
    val.textContent = value;
    item.appendChild(lbl);
    item.appendChild(val);
    parent.appendChild(item);
  }

  function renderContentsHeadInfo(cont) {
    if (!cont) return;
    if (subEl) {
      var cab = cabinets.find(function (c) { return c.id === cont.cabinet_id; });
      var shelfLab = cont.shelf_label || (cab ? shelfDisplayLabel(cab, cont.shelf) : pad2(cont.shelf));
      var placeLab = cont.place_label || placeDisplayLabel(cont.column);
      var parts = [];
      if (cont.address) parts.push(cont.address);
      parts.push("Полка " + shelfLab + ", место " + placeLab);
      var n = (cont.stock_tools || []).length;
      parts.push(n + " поз.");
      if (cont.notes) parts.push(cont.notes);
      subEl.textContent = parts.join(" · ");
    }
    if (statsEl) {
      statsEl.innerHTML = "";
      appendContentsStat(
        statsEl,
        "Инвентаризация",
        cont.last_audited_at
          ? cont.last_audited_at + (cont.last_audited_by ? " · " + cont.last_audited_by : "")
          : "не проводилась",
        !cont.last_audited_at
      );
      appendContentsStat(
        statsEl,
        "Фото содержимого",
        cont.content_photo_date || "не загружалось",
        !cont.content_photo_date
      );
    }
  }

  function openAuditsHistory() {
    if (!dlgAudits) return;
    if (auditsMetaEl && openContainerData) {
      auditsMetaEl.textContent = openContainerData.label || "";
    } else if (auditsMetaEl) {
      auditsMetaEl.textContent = "";
    }
    openDialog(dlgAudits);
  }

  function loadAudits(containerId) {
    if (!apiAuditsTpl) return Promise.resolve([]);
    return fetchJson(containerAuditsUrl(containerId)).then(function (data) {
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
    if (dlgContents) dlgContents.classList.toggle("is-audit", auditMode);
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
    var needsDiam = cat === "end_mill" || cat === "drill" || cat === "reamer" || cat === "center_drill" || cat === "countersink";
    setVisible(auditNewMillRow, isMill);
    setVisible(auditNewTapTypeRow, isTap);
    setVisible(auditNewHoleRow, isTap);
    setVisible(auditNewFlutesRow, isMill);
    setVisible(auditNewDiamRow, needsDiam);
    setVisible(auditNewSizeRow, isTap);
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
    if (auditNewTapType) auditNewTapType.value = "cutting";
    if (auditNewHoleType) auditNewHoleType.value = "through";
    var items = (openContainerData && openContainerData.items) || [];
    for (var i = 0; i < items.length; i++) {
      var it = items[i];
      if (it.diameter_from_mm != null && auditNewDiameter && !auditNewDiameter.value) {
        auditNewDiameter.value = String(it.diameter_from_mm);
      }
      if (it.mill_type && auditNewMillType) auditNewMillType.value = it.mill_type;
      if (it.tap_type && auditNewTapType) auditNewTapType.value = it.tap_type;
      if (it.hole_type && auditNewHoleType) auditNewHoleType.value = it.hole_type;
      if (it.size_label && auditNewSize) auditNewSize.value = it.size_label;
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
    if (opts.tool && opts.tool.name && opts.name && opts.tool.name !== opts.name) {
      var sub = document.createElement("div");
      sub.className = "vw-item-subname";
      sub.textContent = opts.tool.name;
      name.appendChild(sub);
    }
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
        name: tool.type_label || tool.name || ("#" + tool.id),
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
    var tapType = category === "tap" && auditNewTapType ? auditNewTapType.value : "";
    var holeType = category === "tap" && auditNewHoleType ? auditNewHoleType.value : "";
    var flutes = auditNewFlutes ? auditNewFlutes.value : "";
    var note = auditNewNote ? (auditNewNote.value || "").trim() : "";

    var needsDiam = category === "end_mill" || category === "drill" || category === "reamer" || category === "center_drill" || category === "countersink";
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
      tap_type: tapType,
      hole_type: holeType,
      diameter_mm: needsDiam ? diameter : "",
      size_label: sizeLabel,
      name: name,
      quantity: qty,
      flutes_count: flutes,
      note: note || "найден при инвентаризации",
    };
    var metaParts = [CAT_LABELS[category] || category];
    if (millType) metaParts.push(MILL_TYPE_LABELS[millType] || millType);
    if (tapType) metaParts.push(TAP_TYPE_LABELS[tapType] || tapType);
    if (holeType) metaParts.push(HOLE_TYPE_LABELS[holeType] || holeType);
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
    fetchJson(containerAuditsUrl(openContainerId), {
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
    if (titleEl) titleEl.textContent = cont.label;
    renderContentsHeadInfo(cont);
    renderPhotos(cont);
    syncPhotoUploadLabel();
    renderStockTools(cont);
  }

  function openPhotoView(photo) {
    if (!dlgPhoto || !photo || !photo.url) return;
    if (photoViewTitle) photoViewTitle.textContent = photo.caption || "Фото содержимого";
    if (photoViewImg) {
      photoViewImg.src = photo.url;
      photoViewImg.alt = photo.caption || "Фото содержимого";
    }
    if (photoViewMeta) {
      var metaParts = [];
      if (photo.photo_date) metaParts.push("дата фото: " + photo.photo_date);
      if (photo.uploaded_by) metaParts.push(photo.uploaded_by);
      if (photo.created_at) metaParts.push("загружено " + photo.created_at);
      photoViewMeta.textContent = metaParts.join(" · ");
    }
    openDialog(dlgPhoto);
  }

  function closePhotoView() {
    if (!dlgPhoto) return;
    dlgPhoto.hidden = true;
    document.body.classList.remove("vw-modal-open");
    if (photoViewImg) {
      photoViewImg.removeAttribute("src");
      photoViewImg.alt = "";
    }
  }

  function renderPhotos(container) {
    if (!photosEl) return;
    photosEl.innerHTML = "";
    var photos = (container && container.photos) || [];
    var photo = photos.length ? photos[0] : null;
    if (!photo) {
      var empty = document.createElement("div");
      empty.className = "vw-photo-empty";
      empty.innerHTML = (window.BiotaIcons ? window.BiotaIcons.html("action.picture", "ui-icon") : '<i class="fi fi-rr-picture ui-icon" aria-hidden="true"></i>') + '<span>Фото не загружено</span>';
      photosEl.appendChild(empty);
      return;
    }
    var wrap = document.createElement("div");
    wrap.className = "vw-photo-current";
    var btn = document.createElement("button");
    btn.type = "button";
    btn.className = "vw-photo-current-btn";
    btn.title = "Открыть фото";
    var img = document.createElement("img");
    img.src = photo.url || "";
    img.alt = "Фото содержимого";
    img.loading = "lazy";
    btn.appendChild(img);
    btn.addEventListener("click", function () {
      openPhotoView(photo);
    });
    wrap.appendChild(btn);
    var meta = document.createElement("div");
    meta.className = "vw-photo-current-meta";
    meta.textContent = "Загружено " + (photo.photo_date || "—");
    wrap.appendChild(meta);
    if (canEdit && editMode) {
      var del = document.createElement("button");
      del.type = "button";
      del.className = "vw-photo-current-del";
      del.textContent = "×";
      del.title = "Удалить фото";
      del.addEventListener("click", function (ev) {
        ev.preventDefault();
        ev.stopPropagation();
        if (!confirm("Удалить фото содержимого?")) return;
        fetchJson(detailUrl(apiPhotoDelTpl, photo.id), { method: "DELETE" })
          .then(function (data) {
            if (data.container) {
              openContainerData = Object.assign({}, openContainerData || {}, data.container, { photos: data.photos || [] });
              applyContentsView(openContainerData);
            }
            resetPhotoPickUi();
            return loadCabinets();
          })
          .catch(function (e) {
            alert(e.message);
          });
      });
      wrap.appendChild(del);
    }
    photosEl.appendChild(wrap);
  }

  function uploadContainerPhoto(file) {
    if (!canEdit || !editMode || !openContainerId) return;
    file = file || (photoFileInput && photoFileInput.files && photoFileInput.files[0]);
    if (!file) {
      if (photoMsgEl) photoMsgEl.textContent = "Выберите файл изображения.";
      return;
    }
    var fd = new FormData();
    fd.append("image", file);
    setPhotoUploadBusy(true, "Загрузка «" + file.name + "»…");
    fetchForm(containerPhotosUrl(openContainerId), fd, "POST")
      .then(function (data) {
        if (data.container) {
          openContainerData = data.container;
          applyContentsView(openContainerData);
        } else if (data.photos) {
          openContainerData = Object.assign({}, openContainerData || {}, { photos: data.photos });
          applyContentsView(openContainerData);
        }
        resetPhotoPickUi();
        return loadCabinets();
      })
      .catch(function (e) {
        if (photoMsgEl) photoMsgEl.textContent = e.message;
        if (photoPickNameEl) photoPickNameEl.textContent = "";
        if (photoPickBtn) photoPickBtn.disabled = false;
      });
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
      var isExclude = it.rule_kind === "exclude";
      var li = document.createElement("li");
      li.className = "vw-item" + (isExclude ? " is-exclude" : "");
      var top = document.createElement("div");
      top.className = "vw-item-top";
      var left = document.createElement("div");
      var title = document.createElement("div");
      title.className = "vw-item-title";
      var titleText = it.title || "";
      if (isExclude && !/^исключить\s*:/i.test(titleText)) {
        titleText = "Исключить: " + titleText;
      }
      title.textContent = titleText;
      left.appendChild(title);
      var meta = document.createElement("div");
      meta.className = "vw-item-meta";
      var parts = [];
      parts.push(isExclude ? "исключение" : "учитывать");
      if (it.tool_item_id) parts.push("позиция #" + it.tool_item_id);
      if (it.tool_category) parts.push(CAT_LABELS[it.tool_category] || it.tool_category);
      if (it.tool_category === "end_mill" && it.mill_type) {
        parts.push(MILL_TYPE_LABELS[it.mill_type] || it.mill_type);
      }
      if (it.tool_category === "end_mill" && it.flutes_count != null) parts.push("Z" + it.flutes_count);
      if (it.tool_category === "end_mill" && it.corner_radius_mm != null) parts.push("R" + it.corner_radius_mm);
      if (it.tool_category === "body_tool" && it.body_cutter_type) {
        var btLab = (SUBTYPE_OPTIONS.body_tool && SUBTYPE_OPTIONS.body_tool.options || []).reduce(function (acc, o) {
          acc[o.value] = o.label;
          return acc;
        }, {});
        parts.push(btLab[it.body_cutter_type] || it.body_cutter_type);
      }
      if (it.tool_category === "body_tool" && it.brand) parts.push(it.brand);
      if (it.tool_category === "body_tool" && it.shank_type) parts.push(it.shank_type);
      if (it.tool_category === "body_tool" && it.mount_thread) parts.push(it.mount_thread);
      if (it.tool_category === "body_tool" && it.teeth_count != null) parts.push("Z" + it.teeth_count);
      if (it.tool_category === "body_tool" && it.coolant_filter === "1") parts.push("СОЖ");
      if (it.tool_category === "body_tool" && it.coolant_filter === "0") parts.push("без СОЖ");
      if (it.tool_category === "body_tool" && it.insert_compat) {
        parts.push("пластины: " + it.insert_compat);
      }
      if (it.tool_category === "tap" && it.tap_type) {
        parts.push(TAP_TYPE_LABELS[it.tap_type] || it.tap_type);
      }
      if (it.tool_category === "tap" && it.thread_kind) {
        parts.push(THREAD_KIND_LABELS[it.thread_kind] || it.thread_kind);
      }
      if (it.tool_category === "tap" && it.thread_standard) parts.push(it.thread_standard);
      if (it.tool_category === "tap" && it.hole_type) {
        parts.push(HOLE_TYPE_LABELS[it.hole_type] || it.hole_type);
      }
      if (it.tool_category === "tap" && it.pitch_mm != null) parts.push("шаг " + it.pitch_mm);
      if (it.tool_category === "insert" && it.insert_family) parts.push(it.insert_family);
      if (it.tool_category === "insert" && it.insert_shape) parts.push(it.insert_shape);
      if (it.tool_category === "collet" && it.collet_type) {
        parts.push(it.collet_type.toUpperCase());
      }
      if (it.tool_category === "collet" && it.collet_er_size) parts.push(it.collet_er_size);
      if (it.tool_category === "countersink" && it.countersink_type) {
        parts.push(COUNTERSINK_TYPE_LABELS[it.countersink_type] || it.countersink_type);
      }
      if (it.angle_deg) parts.push(it.angle_deg + "°");
      if (it.size_label) parts.push(it.size_label);
      if (it.diameter_from_mm != null || it.diameter_to_mm != null) {
        parts.push("Ø " + (it.diameter_from_mm != null ? it.diameter_from_mm : "?") + "–" + (it.diameter_to_mm != null ? it.diameter_to_mm : "?"));
      }
      if (it.quantity_note) parts.push(it.quantity_note);
      if (!isExclude && it.stock_qty != null) parts.push("на складе: " + it.stock_qty);
      meta.textContent = parts.join(" · ") || "—";
      left.appendChild(meta);
      top.appendChild(left);
      if (canEdit && editMode) {
        var del = document.createElement("button");
        del.type = "button";
        del.className = "vw-item-del";
        del.textContent = "×";
        del.title = isExclude ? "Убрать исключение" : "Удалить правило";
        del.addEventListener("click", function () {
          if (!confirm(isExclude ? "Убрать исключение?" : "Удалить?")) return;
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
    if (dlgAudits) closeDialog(dlgAudits);
    if (itemForm) setVisible(itemForm, false);
    if (rulesBlock) setVisible(rulesBlock, false);
    if (photoUploadWrap) setVisible(photoUploadWrap, editMode && canEdit);
    if (photoMsgEl) photoMsgEl.textContent = "";
    resetPhotoPickUi();
    syncItemMillTypeRow();
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

  if (btnShowAudits) {
    btnShowAudits.addEventListener("click", function () {
      openAuditsHistory();
    });
  }
  document.querySelectorAll(".js-vw-audits-close").forEach(function (btn) {
    btn.addEventListener("click", function (e) {
      e.preventDefault();
      closeDialog(dlgAudits);
    });
  });

  if (photoPickBtn && photoFileInput) {
    photoPickBtn.addEventListener("click", function () {
      if (!canEdit || !editMode) {
        if (photoMsgEl) photoMsgEl.textContent = "Сначала включите режим «Редактировать».";
        return;
      }
      photoFileInput.click();
    });
    photoFileInput.addEventListener("change", function () {
      var file = photoFileInput.files && photoFileInput.files[0];
      if (!file) return;
      uploadContainerPhoto(file);
    });
  }
  document.querySelectorAll(".js-vw-photo-close").forEach(function (btn) {
    btn.addEventListener("click", function (e) {
      e.preventDefault();
      closePhotoView();
    });
  });
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && dlgPhoto && !dlgPhoto.hidden) {
      closePhotoView();
    }
  });

  if (itemForm) {
    var catSel = itemForm.querySelector(".js-vw-item-category");
    if (catSel) catSel.addEventListener("change", syncItemFilterFields);
    var ruleKindSel = itemForm.querySelector(".js-vw-item-rule-kind");
    if (ruleKindSel) ruleKindSel.addEventListener("change", syncItemRuleKindUi);
    syncItemFilterFields();
  }

  setEditMode(false);
  loadCabinets();
})();
