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
  var invTabsWrap = document.querySelector(".js-inv-tabs-wrap");
  var invTabsToggle = document.querySelector(".js-inv-tabs-toggle");

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
  var openCabinetId = null;
  var openContainerId = null;
  var openContainerData = null;
  var editingCabinetId = null;
  var auditMode = false;
  var savingAudit = false;
  var btnBackList = document.querySelector(".js-vw-back-list");

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
    if (dlg === dlgCab) hideCabinetBuilderCtx();
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

  function cabinetSections(cab) {
    var secs = (cab && cab.sections) || [];
    if (secs.length) return secs;
    // fallback synthetic single section from legacy shelves
    var levels = [];
    var n = Math.max(1, parseInt(cab && cab.shelves, 10) || 1);
    var cols = Math.max(1, parseInt(cab && cab.columns, 10) || 1);
    var kind = cabinetKindOf(cab) === "drawer_chest" ? "drawer" : "shelf";
    for (var i = 1; i <= n; i++) {
      levels.push({ id: null, index: i, kind: kind, columns: cols, containers: [] });
    }
    return [{ id: null, index: 1, name: "", levels: levels }];
  }

  function levelById(cab, levelId) {
    if (!levelId) return null;
    var secs = cabinetSections(cab);
    for (var s = 0; s < secs.length; s++) {
      var levels = secs[s].levels || [];
      for (var i = 0; i < levels.length; i++) {
        if (String(levels[i].id) === String(levelId)) return levels[i];
      }
    }
    return null;
  }

  function containersOnLevel(cab, level) {
    if (!level) return [];
    if (level.containers && level.containers.length) return level.containers.slice();
    var lid = level.id;
    return (cab.containers || []).filter(function (c) {
      if (c.parent_id) return false;
      if (lid && c.level_id) return Number(c.level_id) === Number(lid);
      return Number(c.shelf) === Number(level.index);
    });
  }

  function shelfDisplayLabel(cab, shelfTop1, levelsTotal) {
    var total = Math.max(1, parseInt(levelsTotal != null ? levelsTotal : (cab && cab.shelves), 10) || 1);
    var top = Math.max(1, Math.min(parseInt(shelfTop1, 10) || 1, total));
    return pad2(top);
  }

  /** Номер полки сверху вниз (1 = верх), как на экране и в адресе. */
  function shelfTopToDisplayNum(cab, shelfTop1, levelsTotal) {
    return parseInt(shelfDisplayLabel(cab, shelfTop1, levelsTotal), 10) || 1;
  }

  /** Обратно: номер с экрана → значение для БД (1 = верх). */
  function shelfDisplayToTop(cab, displayNum, levelsTotal) {
    var total = Math.max(1, parseInt(levelsTotal != null ? levelsTotal : (cab && cab.shelves), 10) || 1);
    return Math.max(1, Math.min(parseInt(displayNum, 10) || 1, total));
  }

  function placeDisplayLabel(col) {
    return pad2(Math.max(1, parseInt(col, 10) || 1));
  }

  function placeNumFromPosition(stack, column, columns, rows) {
    var cols = Math.max(1, Math.min(12, parseInt(columns, 10) || 1));
    var rowsN = Math.max(1, Math.min(4, parseInt(rows, 10) || 1));
    var st = Math.max(1, Math.min(parseInt(stack, 10) || 1, rowsN));
    var col = Math.max(1, Math.min(parseInt(column, 10) || 1, cols));
    return (rowsN - st) * cols + col;
  }

  function levelRowsOf(level) {
    if (level && level.kind === "drawer") return 1;
    return Math.max(1, Math.min(4, parseInt(level && level.rows, 10) || 1));
  }

  function levelCapacityOf(level) {
    var cols = Math.max(0, parseInt(level && level.columns, 10) || 0);
    if (cols < 1) return 0;
    return cols * levelRowsOf(level);
  }

  /** Места слева от секции на том же ряду полок (сквозная нумерация). */
  function placeOffsetBeforeSection(cab, sectionIndex, shelfTop1) {
    var offset = 0;
    var secs = cabinetSections(cab);
    var wantSec = parseInt(sectionIndex, 10) || 1;
    var wantShelf = parseInt(shelfTop1, 10) || 1;
    for (var i = 0; i < secs.length; i++) {
      var sec = secs[i];
      var si = parseInt(sec.index, 10) || (i + 1);
      if (si >= wantSec) break;
      var levels = sec.levels || [];
      for (var li = 0; li < levels.length; li++) {
        if (Number(levels[li].index) === wantShelf) {
          offset += levelCapacityOf(levels[li]);
          break;
        }
      }
    }
    return offset;
  }

  function sectionIndexOfLevel(cab, level) {
    if (!level) return 1;
    var secs = cabinetSections(cab);
    for (var si = 0; si < secs.length; si++) {
      var levels = secs[si].levels || [];
      for (var li = 0; li < levels.length; li++) {
        if (level.id && levels[li].id === level.id) {
          return parseInt(secs[si].index, 10) || (si + 1);
        }
        if (!level.id && Number(levels[li].index) === Number(level.index) && secs.length === 1) {
          return 1;
        }
      }
    }
    return 1;
  }

  function cabinetLevelsTotal(cab) {
    var max = 1;
    cabinetSections(cab).forEach(function (sec) {
      max = Math.max(max, (sec.levels || []).length || 1);
    });
    return Math.max(max, parseInt(cab && cab.shelves, 10) || 1);
  }

  function shelfPlaceLabels(cab, shelf, level) {
    var peers = level
      ? containersOnLevel(cab, level)
      : (cab.containers || []).filter(function (c) {
          return !c.parent_id && Number(c.shelf) === Number(shelf);
        });
    var cols = Math.max(1, parseInt(level && level.columns, 10) || parseInt(cab.columns, 10) || 1);
    var rowsN = level ? levelRowsOf(level) : 1;
    if (!level) {
      peers.forEach(function (c) {
        rowsN = Math.max(rowsN, parseInt(c.stack, 10) || 1);
      });
    }
    var secIdx = sectionIndexOfLevel(cab, level);
    var offset = placeOffsetBeforeSection(cab, secIdx, level ? level.index : shelf);
    var map = {};
    peers.forEach(function (c) {
      if (c && c.id != null) {
        var local = placeNumFromPosition(c.stack || 1, c.column || 1, cols, rowsN);
        map[c.id] = placeDisplayLabel(offset + local);
      }
    });
    return map;
  }

  function suggestAddress(cab, shelf, col, placeNum, sectionIndex, levelsTotal) {
    var code = (cab && (cab.code || "")).toString().trim().toUpperCase() || "?";
    var place = placeNum != null ? placeNum : col;
    if (sectionIndex != null && placeNum == null) {
      place = placeOffsetBeforeSection(cab, sectionIndex, shelf) + (parseInt(col, 10) || 1);
    }
    var total = levelsTotal != null ? levelsTotal : cabinetLevelsTotal(cab);
    var levelLab = shelfDisplayLabel(cab, shelf, total);
    var placeLab = placeDisplayLabel(place);
    return code + "-" + levelLab + "-" + placeLab;
  }

  function setEditMode(on) {
    editMode = !!on && canEdit;
    root.classList.toggle("is-edit", editMode);
    if (btnToggleEdit) {
      btnToggleEdit.classList.toggle("is-on", editMode);
      btnToggleEdit.setAttribute("aria-pressed", editMode ? "true" : "false");
      btnToggleEdit.textContent = editMode ? "Готово" : "Редактировать";
    }
    if (itemForm) setVisible(itemForm, false);
    if (rulesBlock) setVisible(rulesBlock, false);
    if (photoUploadWrap) setVisible(photoUploadWrap, editMode && canEdit);
    document.body.classList.toggle("vw-is-edit", editMode);
    syncItemMillTypeRow();
    if (openContainerData) renderPhotos(openContainerData);
    renderFloor();
    requestAnimationFrame(function () {
      requestAnimationFrame(syncViewportHeightFit);
    });
  }

  function occupiedMap(cab, level) {
    var map = {};
    var list = level ? containersOnLevel(cab, level) : (cab.containers || []);
    list.forEach(function (cont) {
      if (cont.parent_id) return;
      var st = cont.stack || 1;
      var cs = cont.col_span || 1;
      var keyShelf = level && level.id ? ("L" + level.id) : String(cont.shelf);
      for (var c = cont.column; c < cont.column + cs; c++) {
        map[keyShelf + ":" + st + ":" + c] = cont.id;
      }
    });
    return map;
  }

  function findFreeOnLevel(cab, level) {
    var cols = Math.max(1, parseInt(level && level.columns, 10) || parseInt(cab.columns, 10) || 1);
    var rowsN = levelRowsOf(level);
    var occ = occupiedMap(cab, level);
    var keyShelf = level && level.id ? ("L" + level.id) : String(level.index);
    var capacity = cols * rowsN;
    for (var place = 1; place <= capacity; place++) {
      var rowFromTop = Math.floor((place - 1) / cols);
      var stack = rowsN - rowFromTop;
      var column = ((place - 1) % cols) + 1;
      if (!occ[keyShelf + ":" + stack + ":" + column]) {
        return { shelf: level.index, stack: stack, column: column, level_id: level.id || null };
      }
    }
    return { shelf: level.index, stack: 1, column: cols + 1, level_id: level.id || null };
  }

  function findFreeOnShelf(cab, shelf) {
    var secs = cabinetSections(cab);
    var level = null;
    if (secs.length === 1) {
      var levels = secs[0].levels || [];
      for (var i = 0; i < levels.length; i++) {
        if (Number(levels[i].index) === Number(shelf)) {
          level = levels[i];
          break;
        }
      }
    }
    if (level) return findFreeOnLevel(cab, level);
    var occ = occupiedMap(cab);
    for (var c = 1; c <= cab.columns; c++) {
      if (!occ[shelf + ":1:" + c]) {
        return { shelf: shelf, stack: 1, column: c, level_id: null };
      }
    }
    return { shelf: shelf, stack: 1, column: cab.columns + 1, level_id: null };
  }

  function sortedCabinets() {
    return cabinets.slice().sort(function (a, b) {
      var so = (a.sort_order || 0) - (b.sort_order || 0);
      if (so) return so;
      var ca = String(a.code || "").localeCompare(String(b.code || ""), "ru");
      if (ca) return ca;
      var na = String(a.name || "").localeCompare(String(b.name || ""), "ru");
      if (na) return na;
      return (a.id || 0) - (b.id || 0);
    });
  }

  function cabinetKindNoun(kind) {
    if (kind === "rack") return "Стеллаж";
    if (kind === "drawer_chest") return "Тумба";
    return "Шкаф";
  }

  function countTopContainers(cab) {
    return (cab.containers || []).filter(function (c) { return !c.parent_id; }).length;
  }

  function isMobileTabsMode() {
    return window.matchMedia && window.matchMedia("(max-width: 720px)").matches;
  }

  function setInvTabsCollapsed(collapsed) {
    if (!invTabsWrap) return;
    invTabsWrap.classList.toggle("is-collapsed", !!collapsed);
    if (invTabsToggle) {
      invTabsToggle.setAttribute("aria-expanded", collapsed ? "false" : "true");
      var label = invTabsToggle.querySelector(".inv-tabs-toggle__label");
      if (label) label.textContent = collapsed ? "Меню склада" : "Скрыть меню";
    }
  }

  function syncInvTabsCollapsed(cabinetOpen) {
    if (!invTabsWrap || !isMobileTabsMode()) {
      if (invTabsWrap) invTabsWrap.classList.remove("is-collapsed");
      if (invTabsToggle) {
        invTabsToggle.setAttribute("aria-expanded", "true");
        var label = invTabsToggle.querySelector(".inv-tabs-toggle__label");
        if (label) label.textContent = "Меню склада";
      }
      return;
    }
    setInvTabsCollapsed(!!cabinetOpen);
  }

  function syncOpenCabinetChrome() {
    var openCab = openCabinetId
      ? cabinets.find(function (c) { return c.id === openCabinetId; })
      : null;
    if (btnBackList) setVisible(btnBackList, !!openCab);
    if (floorEl) {
      floorEl.classList.toggle("is-list", !openCab);
      floorEl.classList.toggle("is-open", !!openCab);
    }
    document.documentElement.classList.toggle("vw-cabinet-open", !!openCab);
    document.body.classList.toggle("vw-cabinet-open", !!openCab);
    syncInvTabsCollapsed(!!openCab);
    if (modeHint) {
      if (!openCab) {
        modeHint.textContent = editMode
          ? "Список мебели. Нажмите карточку, чтобы открыть. «Параметры» — изменить шкаф."
          : "Выберите шкаф или стеллаж";
      } else if (editMode) {
        modeHint.textContent = "Правка: «+» или пустое место — создать. Клик по ящику — изменить. «← К списку» — назад.";
      } else {
        modeHint.textContent = "Нажмите на контейнер: список по адресу и инвентаризация";
      }
    }
    if (root) {
      var titleEl = root.querySelector(".vw-title");
      if (titleEl) {
        if (openCab) {
          var code = (openCab.code || "").toString().trim().toUpperCase();
          titleEl.textContent = code
            ? (code + " — " + (openCab.name || cabinetKindNoun(cabinetKindOf(openCab))))
            : (openCab.name || "Мебель");
        } else {
          titleEl.textContent = "Визуальный склад";
        }
      }
    }
  }

  function openCabinetView(cabId) {
    openCabinetId = cabId || null;
    syncOpenCabinetChrome();
    renderFloor();
  }

  function closeCabinetView() {
    openCabinetId = null;
    syncOpenCabinetChrome();
    renderFloor();
  }

  function buildCabinetListCard(cab) {
    var kind = cabinetKindOf(cab);
    var code = (cab.code || "").toString().trim().toUpperCase();
    var places = countTopContainers(cab);
    var card = document.createElement("button");
    card.type = "button";
    card.className = "vw-cab-tile";
    card.dataset.kind = kind;
    card.dataset.cabinetId = String(cab.id);

    var icon = document.createElement("span");
    icon.className = "vw-cab-tile__icon";
    icon.setAttribute("aria-hidden", "true");
    icon.textContent = kind === "rack" ? "▦" : (kind === "drawer_chest" ? "☰" : "▣");
    card.appendChild(icon);

    var body = document.createElement("span");
    body.className = "vw-cab-tile__body";
    var title = document.createElement("strong");
    title.className = "vw-cab-tile__title";
    title.textContent = code ? (code + " — " + (cab.name || "")) : (cab.name || "Без названия");
    body.appendChild(title);
    var meta = document.createElement("span");
    meta.className = "vw-cab-tile__meta";
    meta.textContent = cabinetKindNoun(kind)
      + " · " + (cab.shelves || 0) + " пол."
      + " · " + places + " мест";
    body.appendChild(meta);
    card.appendChild(body);

    card.title = "Открыть";
    card.addEventListener("click", function () {
      openCabinetView(cab.id);
    });

    if (canEdit) {
      var gear = document.createElement("span");
      gear.className = "vw-cab-tile__gear";
      gear.textContent = "⚙";
      gear.title = "Параметры";
      gear.addEventListener("click", function (ev) {
        ev.preventDefault();
        ev.stopPropagation();
        if (!editMode) setEditMode(true);
        openCabinetForm(cab);
      });
      card.appendChild(gear);
    }

    return card;
  }

  function syncViewportHeightFit() {
    if (!root || !floorEl) return;
    document.documentElement.classList.add("vw-fit-height");
    document.body.classList.add("vw-fit-height");
    document.documentElement.classList.toggle("vw-cabinet-open", floorEl.classList.contains("is-open"));
    document.body.classList.toggle("vw-cabinet-open", floorEl.classList.contains("is-open"));

    var nav = document.querySelector(".nav");
    var navH = nav ? Math.ceil(nav.getBoundingClientRect().height) : 56;
    document.documentElement.style.setProperty("--vw-nav-h", navH + "px");

    var vv = window.visualViewport;
    var viewH = vv ? vv.height : window.innerHeight;
    var container = root.closest(".container");
    if (container) {
      var contH = Math.floor(viewH - navH);
      if (contH < 200) contH = 200;
      container.style.height = contH + "px";
      container.style.maxHeight = contH + "px";
    }

    var top = floorEl.getBoundingClientRect().top;
    var avail = Math.floor(viewH - top - 4);
    if (!isFinite(avail) || avail < 160) avail = 160;
    root.style.setProperty("--vw-floor-h", avail + "px");
  }

  function renderFloor() {
    if (!floorEl) return;
    floorEl.querySelectorAll(".vw-cabinet, .vw-cab-tile").forEach(function (n) { n.remove(); });

    if (!cabinets.length) {
      setVisible(emptyEl, true);
      if (emptyEl && !floorEl.contains(emptyEl)) floorEl.appendChild(emptyEl);
      if (openCabinetId) openCabinetId = null;
      syncOpenCabinetChrome();
      syncViewportHeightFit();
      return;
    }
    setVisible(emptyEl, false);

    var openCab = openCabinetId
      ? cabinets.find(function (c) { return c.id === openCabinetId; })
      : null;
    if (openCabinetId && !openCab) {
      openCabinetId = null;
      openCab = null;
    }
    syncOpenCabinetChrome();

    if (!openCab) {
      sortedCabinets().forEach(function (cab) {
        floorEl.appendChild(buildCabinetListCard(cab));
      });
      syncViewportHeightFit();
      return;
    }

    floorEl.appendChild(buildCabinetCard(openCab));
    syncViewportHeightFit();
    requestAnimationFrame(function () {
      syncViewportHeightFit();
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

  function cabinetOptionLabel(cab) {
    var code = (cab && (cab.code || "")).toString().trim().toUpperCase();
    var name = (cab && cab.name) || ("#" + (cab && cab.id));
    var kind = cabinetKindOf(cab);
    var kindLab = kind === "rack" ? "стеллаж" : (kind === "drawer_chest" ? "тумба" : "шкаф");
    return (code ? (code + " — ") : "") + name + " (" + kindLab + ")";
  }

  function fillContainerCabinetSelect(selectedId, disabled) {
    var sel = contForm && contForm.querySelector(".js-vw-cont-cabinet");
    if (!sel) return;
    var cur = String(selectedId || "");
    sel.innerHTML = "";
    cabinets.slice().sort(function (a, b) {
      var ca = (a.code || "").toString();
      var cb = (b.code || "").toString();
      if (ca !== cb) return ca < cb ? -1 : 1;
      return (a.name || "").localeCompare(b.name || "", "ru");
    }).forEach(function (cab) {
      var opt = document.createElement("option");
      opt.value = String(cab.id);
      opt.textContent = cabinetOptionLabel(cab);
      sel.appendChild(opt);
    });
    if (cur && [].some.call(sel.options, function (o) { return o.value === cur; })) {
      sel.value = cur;
    } else if (sel.options.length) {
      sel.selectedIndex = 0;
    }
    sel.disabled = !!disabled;
    var row = contForm.querySelector(".js-vw-cont-cabinet-row");
    var hint = contForm.querySelector(".js-vw-cont-cabinet-hint");
    if (row) setVisible(row, true);
    if (hint) setVisible(hint, !disabled);
  }

  function containerKindLabel(kind) {
    return "Место";
  }

  function placeKindFor(cab, levelKind, isChild, existingKind) {
    if (isChild) return "drawer_cell";
    // Старые органайзеры оставляем как есть при редактировании
    if (existingKind === "organizer") return "organizer";
    if (cabinetKindOf(cab) === "drawer_chest" || levelKind === "drawer") return "drawer_cell";
    if (cabinetKindOf(cab) === "rack") return "shelf_slot";
    return "bin";
  }

  function syncPlaceAddressFromForm() {
    if (!contForm) return "";
    var cabinetId = parseInt((contForm.querySelector(".js-vw-cont-cabinet") || {}).value, 10);
    var cab = cabinets.find(function (c) { return c.id === cabinetId; });
    if (!cab) return "";
    var levelIdEl = contForm.querySelector(".js-vw-cont-level-id");
    var levelId = levelIdEl && levelIdEl.value ? parseInt(levelIdEl.value, 10) : 0;
    var lvl = levelById(cab, levelId);
    var parentId = contForm.dataset.parentId;
    var shelfFormVal = parseInt((contForm.querySelector(".js-vw-cont-shelf") || {}).value, 10) || 1;
    var column = parseInt((contForm.querySelector(".js-vw-cont-column") || {}).value, 10) || 1;
    var levelsTotal = lvl
      ? (function () {
          var secs = cabinetSections(cab);
          for (var si = 0; si < secs.length; si++) {
            var levels = secs[si].levels || [];
            for (var li = 0; li < levels.length; li++) {
              if (lvl.id && levels[li].id === lvl.id) return levels.length;
            }
          }
          return cab.shelves || 1;
        })()
      : (cab.shelves || 1);
    var sectionIndex = null;
    if (lvl && cab) {
      var secs = cabinetSections(cab);
      for (var si = 0; si < secs.length; si++) {
        var levels = secs[si].levels || [];
        for (var li = 0; li < levels.length; li++) {
          if (lvl.id && levels[li].id === lvl.id) {
            sectionIndex = secs[si].index || (si + 1);
            break;
          }
        }
        if (sectionIndex != null) break;
      }
    }
    var shelfTop = parentId
      ? shelfFormVal
      : (lvl && lvl.index
        ? lvl.index
        : shelfDisplayToTop(cab, shelfFormVal, levelsTotal));
    var addr = suggestAddress(cab, shelfTop, column, null, sectionIndex, levelsTotal);
    var addressEl = contForm.querySelector(".js-vw-cont-address");
    if (addressEl) addressEl.value = addr || "";
    var labelEl = contForm.querySelector(".js-vw-cont-label");
    if (labelEl) labelEl.value = addr || "";
    var kindEl = contForm.querySelector(".js-vw-cont-kind");
    if (kindEl && !parentId) {
      var levelKind = (lvl && lvl.kind) || "";
      var existing = kindEl.value === "organizer" ? "organizer" : "";
      kindEl.value = placeKindFor(cab, levelKind, !!parentId, existing);
    }
    return addr || "";
  }

  function buildCabinetCard(cab) {
    var wrap = document.createElement("section");
    wrap.className = "vw-cabinet";
    wrap.dataset.cabinetId = String(cab.id);
    wrap.dataset.kind = cabinetKindOf(cab);
    wrap.style.setProperty("--vw-cols", String(Math.max(1, parseInt(cab.columns, 10) || 1)));
    wrap.style.setProperty("--vw-shelves", String(Math.max(1, parseInt(cab.shelves, 10) || 1)));

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

    var sections = cabinetSections(cab);
    var multi = sections.length > 1;
    var interior = document.createElement("div");
    // Рисуем по рядам полок: неразделённая полка — на всю ширину,
    // разделённая — куски рядом (пустые секции не оставляют «половину»).
    interior.className = "vw-cab-interior" + (multi ? " vw-cab-interior--level-rows" : "");
    if (multi) {
      var maxLi = 0;
      sections.forEach(function (sec) {
        maxLi = Math.max(maxLi, (sec.levels || []).length);
      });
      for (var rowIdx = 0; rowIdx < maxLi; rowIdx++) {
        var pieces = [];
        sections.forEach(function (sec) {
          var levels = (sec.levels || []).slice().sort(function (a, b) {
            return (a.index || 0) - (b.index || 0);
          });
          var lvl = levels[rowIdx];
          if (!lvl) return;
          var cols = parseInt(lvl.columns, 10);
          if (!cols || cols < 1) return;
          pieces.push({ sec: sec, level: lvl });
        });
        if (!pieces.length) continue;
        var levelRow = document.createElement("div");
        var full = pieces.length === 1;
        levelRow.className = "vw-cab-level-row" + (full ? " is-full" : " is-split");
        pieces.forEach(function (p) {
          var bayWrap = document.createElement("div");
          bayWrap.className = "vw-cab-level-piece";
          if (!full) {
            var grow = Math.max(1, parseInt(p.level.columns, 10) || 1);
            bayWrap.style.flex = grow + " 1 0";
            var secLab = document.createElement("div");
            secLab.className = "vw-cab-section-label";
            secLab.textContent = (p.sec.name || "").trim() || ("Секция " + (p.sec.index || 1));
            bayWrap.appendChild(secLab);
          }
          bayWrap.appendChild(buildLevelBay(cab, p.sec, p.level));
          levelRow.appendChild(bayWrap);
        });
        interior.appendChild(levelRow);
      }
    } else {
      var sec0 = sections[0] || { index: 1, levels: [] };
      var levels0 = (sec0.levels || []).slice().sort(function (a, b) {
        return (a.index || 0) - (b.index || 0);
      });
      var levelsWrap = document.createElement("div");
      levelsWrap.className = "vw-cab-section-levels";
      levels0.forEach(function (lvl) {
        levelsWrap.appendChild(buildLevelBay(cab, sec0, lvl));
      });
      interior.appendChild(levelsWrap);
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

  function makeShelfNumEl(cab, shelf, levelsTotal) {
    var shelfNum = document.createElement("span");
    shelfNum.className = "vw-shelf-num";
    shelfNum.textContent = shelfDisplayLabel(cab, shelf, levelsTotal);
    shelfNum.title = "Уровень " + shelfDisplayLabel(cab, shelf, levelsTotal);
    return shelfNum;
  }

  function buildLevelBay(cab, section, level) {
    var cols = parseInt(level && level.columns, 10);
    if (!cols || cols < 1) {
      var spacer = document.createElement("div");
      spacer.className = "vw-bay vw-bay--spacer";
      spacer.setAttribute("aria-hidden", "true");
      return spacer;
    }
    // Тумба — выдвижные ящики; в шкафу/стеллаже ящик стоит на полке, как место.
    if (cabinetKindOf(cab) === "drawer_chest") {
      return buildDrawerBay(cab, section, level);
    }
    return buildBay(cab, section, level);
  }

  function buildDrawerBay(cab, section, level) {
    var shelf = level.index;
    var levelsTotal = (section.levels || []).length || cab.shelves;
    var bay = document.createElement("div");
    bay.className = "vw-bay vw-bay--drawer";
    if (level.id) bay.dataset.levelId = String(level.id);

    var cols = Math.max(1, parseInt(level.columns, 10) || parseInt(cab.columns, 10) || 1);
    var drawer = document.createElement("div");
    drawer.className = "vw-drawer";

    var handle = document.createElement("div");
    handle.className = "vw-drawer-handle";
    handle.appendChild(makeShelfNumEl(cab, shelf, levelsTotal));
    drawer.appendChild(handle);

    var cells = document.createElement("div");
    cells.className = "vw-drawer-cells";
    cells.style.gridTemplateColumns = "repeat(" + cols + ", minmax(0, 1fr))";

    var onShelf = containersOnLevel(cab, level).slice().sort(function (a, b) {
      return (a.column || 1) - (b.column || 1);
    });
    var occupied = occupiedMap(cab, level);
    var keyShelf = level.id ? ("L" + level.id) : String(shelf);

    for (var col = 1; col <= cols; col++) {
      var contAt = null;
      for (var i = 0; i < onShelf.length; i++) {
        var c0 = onShelf[i];
        var start = c0.column || 1;
        var span0 = Math.min(Math.max(1, c0.col_span || 1), cols - start + 1);
        if (col >= start && col < start + span0) {
          if (col === start) contAt = c0;
          else contAt = false;
          break;
        }
      }
      if (contAt === false) continue;
      if (contAt) {
        var span = Math.min(Math.max(1, contAt.col_span || 1), cols - (contAt.column || 1) + 1);
        var slot = document.createElement("div");
        slot.className = "vw-drawer-cell-slot";
        slot.style.gridColumn = (contAt.column || 1) + " / span " + span;
        slot.appendChild(buildBin(cab, contAt, null, section, level));
        cells.appendChild(slot);
      } else {
        var emptySlot = document.createElement("div");
        emptySlot.className = "vw-drawer-cell-slot";
        emptySlot.style.gridColumn = String(col);
        emptySlot.appendChild(buildEmptyDrawerCell(cab, shelf, col, section, level, levelsTotal));
        cells.appendChild(emptySlot);
      }
    }

    drawer.appendChild(cells);
    bay.appendChild(drawer);

    if (editMode) {
      // «+» только если все места заняты — расширить число ячеек (как на полке)
      var freeCol = null;
      for (var c = 1; c <= cols; c++) {
        if (!occupied[keyShelf + ":1:" + c]) { freeCol = c; break; }
      }
      if (freeCol === null) {
        var addBtn = document.createElement("button");
        addBtn.type = "button";
        addBtn.className = "vw-bay-add";
        addBtn.textContent = "+";
        addBtn.title = "Добавить ячейку в ящик " + shelfDisplayLabel(cab, shelf, levelsTotal) + " (добавить место)";
        addBtn.addEventListener("click", function (ev) {
          ev.preventDefault();
          ev.stopPropagation();
          var free = findFreeOnLevel(cab, level);
          openContainerForm(cab, null, free.shelf, 1, free.column, level);
        });
        bay.appendChild(addBtn);
      }
    }
    return bay;
  }

  function buildBay(cab, section, level) {
    var shelf = level.index;
    var levelsTotal = (section.levels || []).length || cab.shelves;
    var isRack = cabinetKindOf(cab) === "rack";
    var isDrawerOnShelf = (level && level.kind) === "drawer";
    var bay = document.createElement("div");
    bay.className = "vw-bay"
      + (isRack ? " vw-bay--rack" : "")
      + (isDrawerOnShelf ? " vw-bay--drawer-on-shelf" : "");
    if (level.id) bay.dataset.levelId = String(level.id);

    var cols = Math.max(1, parseInt(level.columns, 10) || parseInt(cab.columns, 10) || 1);
    var rowsN = levelRowsOf(level);
    var space = document.createElement("div");
    space.className = "vw-bay-space";
    space.style.gridTemplateColumns = "repeat(" + cols + ", minmax(0, 1fr))";
    space.style.gridAutoFlow = "row dense";

    var onShelf = containersOnLevel(cab, level);
    var byCell = {};
    onShelf.forEach(function (cont) {
      var key = String(cont.stack || 1) + ":" + String(cont.column);
      byCell[key] = cont;
    });

    var occupied = occupiedMap(cab, level);
    var placeLabels = shelfPlaceLabels(cab, shelf, level);
    var keyShelf = level.id ? ("L" + level.id) : String(shelf);

    for (var col = 1; col <= cols; col++) {
      var pile = document.createElement("div");
      pile.className = "vw-pile";
      pile.style.gridColumn = String(col);
      var hasAny = false;
      for (var st = 1; st <= rowsN; st++) {
        var cont = byCell[String(st) + ":" + String(col)];
        if (cont) {
          var span = Math.min(cont.col_span || 1, cols - col + 1);
          if (span > 1) pile.style.gridColumn = col + " / span " + span;
          pile.appendChild(buildBin(cab, cont, placeLabels, section, level));
          hasAny = true;
        } else if (!occupied[keyShelf + ":" + st + ":" + col]) {
          pile.appendChild(buildEmptyShelfCell(cab, shelf, col, section, level, levelsTotal, st));
          hasAny = true;
        }
      }
      if (hasAny) space.appendChild(pile);
    }

    if (editMode) {
      var free = findFreeOnLevel(cab, level);
      var freeTaken = free.column > cols;
      if (freeTaken) {
        var addBtn = document.createElement("button");
        addBtn.type = "button";
        addBtn.className = "vw-bay-add";
        addBtn.textContent = "+";
        addBtn.title = (isRack ? "Добавить на полку " : "Поставить ящик на полку ") +
          shelfDisplayLabel(cab, shelf, levelsTotal) + " (добавить место)";
        addBtn.style.gridColumn = String(cols);
        addBtn.style.opacity = "0.85";
        addBtn.addEventListener("click", function (ev) {
          ev.preventDefault();
          ev.stopPropagation();
          var next = findFreeOnLevel(cab, level);
          openContainerForm(cab, null, next.shelf, next.stack, next.column, level);
        });
        space.appendChild(addBtn);
      }
    }

    bay.appendChild(space);
    var ledge = document.createElement("div");
    ledge.className = "vw-bay-ledge";
    ledge.appendChild(makeShelfNumEl(cab, shelf, levelsTotal));
    bay.appendChild(ledge);
    return bay;
  }

  function buildEmptyShelfCell(cab, shelf, col, section, level, levelsTotal, stack) {
    var st = Math.max(1, parseInt(stack, 10) || 1);
    var btn = document.createElement("button");
    btn.type = "button";
    var isDrawerOnShelf = (level && level.kind) === "drawer";
    btn.className = "vw-shelf-empty" + (isDrawerOnShelf ? " vw-shelf-empty--drawer" : "");
    var cols = Math.max(1, parseInt(level && level.columns, 10) || parseInt(cab.columns, 10) || 1);
    var rowsN = levelRowsOf(level);
    var secIdx = section && section.index != null
      ? section.index
      : sectionIndexOfLevel(cab, level);
    var offset = placeOffsetBeforeSection(cab, secIdx, shelf);
    var localPlace = placeNumFromPosition(st, col, cols, rowsN);
    var placeLab = placeDisplayLabel(offset + localPlace);
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
    var shelfLab = shelfDisplayLabel(cab, shelf, levelsTotal != null ? levelsTotal : cabinetLevelsTotal(cab));
    btn.title = editMode
      ? (isDrawerOnShelf
        ? ("Поставить ящик на полку " + shelfLab + ", место " + placeLab)
        : ("Добавить на полку " + shelfLab + ", место " + placeLab))
      : (isDrawerOnShelf
        ? ("Полка " + shelfLab + ", ящик " + placeLab + " — пусто")
        : ("Полка " + shelfLab + ", место " + placeLab + " — пусто"));
    btn.addEventListener("click", function (ev) {
      ev.preventDefault();
      ev.stopPropagation();
      if (editMode && canEdit) openContainerForm(cab, null, shelf, st, col, level);
    });
    if (!editMode) btn.disabled = true;
    return btn;
  }

  function buildEmptyDrawerCell(cab, shelf, col, section, level, levelsTotal) {
    var btn = document.createElement("button");
    btn.type = "button";
    btn.className = "vw-drawer-empty-cell";
    var secIdx = section && section.index != null
      ? section.index
      : sectionIndexOfLevel(cab, level);
    var offset = placeOffsetBeforeSection(cab, secIdx, shelf);
    var placeLab = placeDisplayLabel(offset + (parseInt(col, 10) || 1));
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
    var shelfLab = shelfDisplayLabel(cab, shelf, levelsTotal != null ? levelsTotal : cabinetLevelsTotal(cab));
    btn.title = editMode
      ? ("Добавить ячейку в ящик " + shelfLab + ", место " + placeLab)
      : ("Ящик " + shelfLab + ", место " + placeLab + " — пусто");
    btn.addEventListener("click", function (ev) {
      ev.preventDefault();
      ev.stopPropagation();
      if (editMode && canEdit) openContainerForm(cab, null, shelf, 1, col, level);
    });
    if (!editMode || !canEdit) btn.disabled = true;
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
    var minPx = 8;
    var maxPx = 13;
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

  function buildOrganizer(cab, cont, placeLabels) {
    var wrap = document.createElement("div");
    wrap.className = "vw-organizer";
    wrap.dataset.kind = "organizer";
    wrap.dataset.containerId = String(cont.id);

    var orgPlaceLab = (placeLabels && placeLabels[cont.id])
      || cont.place_label
      || placeDisplayLabel(cont.column);
    if (!cont.parent_id) {
      var orgPlace = document.createElement("span");
      orgPlace.className = "vw-place-num";
      orgPlace.textContent = orgPlaceLab;
      orgPlace.title = "Место " + orgPlaceLab;
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

  function buildBin(cab, cont, placeLabels, section, level) {
    if (cont.kind === "organizer") {
      return buildOrganizer(cab, cont, placeLabels);
    }
    var levelKind = (level && level.kind) || cont.level_kind || "";
    var isSlot = cont.kind === "shelf_slot";
    var isCell = cont.kind === "drawer_cell"
      || cabinetKindOf(cab) === "drawer_chest"
      || levelKind === "drawer";
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

    var placeLab = (placeLabels && placeLabels[cont.id])
      || cont.place_label
      || placeDisplayLabel(cont.column);

    if (!cont.parent_id) {
      var placeBadge = document.createElement("span");
      placeBadge.className = "vw-place-num";
      placeBadge.textContent = placeLab;
      placeBadge.title = "Место " + placeLab;
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
    text.textContent = cont.address || cont.label || "Место";
    labelWrap.appendChild(text);
    var noteText = (cont.notes || "").trim();
    if (noteText) {
      var noteEl = document.createElement("span");
      noteEl.className = "vw-bin-note";
      noteEl.textContent = noteText;
      labelWrap.appendChild(noteEl);
    }
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

    var titleBase = cont.address || cont.label || "Место";
    if (noteText) titleBase += " · " + noteText;
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

  var cabBuilderState = { sections: [] };
  var cabBuilderCtx = { secIndex: 0, levelIndex: 0 };

  function defaultBuilderKind(kind) {
    return kind === "drawer_chest" ? "drawer" : "shelf";
  }

  function makePlaceKinds(count, kind) {
    var k = kind === "drawer" ? "drawer" : "shelf";
    var n = Math.max(0, Math.min(12, parseInt(count, 10) || 0));
    var out = [];
    for (var i = 0; i < n; i++) out.push(k);
    return out;
  }

  function normalizeLevelPlaces(lvl) {
    if (!lvl) return lvl;
    if (lvl.ghost) {
      lvl.columns = 0;
      lvl.placeKinds = [];
      return lvl;
    }
    var cols = Math.max(1, Math.min(12, parseInt(lvl.columns, 10) || 1));
    var kinds = Array.isArray(lvl.placeKinds) ? lvl.placeKinds.slice(0, cols) : [];
    var fallback = lvl.kind === "drawer" ? "drawer" : "shelf";
    while (kinds.length < cols) kinds.push(fallback);
    lvl.placeKinds = kinds;
    lvl.columns = cols;
    lvl.kind = kinds.every(function (x) { return x === "drawer"; }) ? "drawer" : "shelf";
    lvl.rows = lvl.kind === "drawer" ? 1 : Math.max(1, Math.min(4, parseInt(lvl.rows, 10) || 1));
    return lvl;
  }

  function cloneBuilderSections(sections) {
    return (sections || []).map(function (sec) {
      return {
        id: sec.id || null,
        name: sec.name || "",
        levels: (sec.levels || []).map(function (lvl) {
          var cols = Math.max(0, Math.min(12, parseInt(lvl.columns, 10) || 0));
          if (cols <= 0) return makeGhostLevel();
          var kind = lvl.kind === "drawer" ? "drawer" : "shelf";
          return normalizeLevelPlaces({
            id: lvl.id || null,
            kind: kind,
            columns: cols,
            rows: Math.max(1, Math.min(4, parseInt(lvl.rows, 10) || 1)),
            placeKinds: makePlaceKinds(cols, kind),
            ghost: false,
          });
        }),
      };
    });
  }

  function initCabinetBuilderState(cab, kind) {
    var k = kind || "cabinet";
    if (cab) {
      cabBuilderState.sections = cloneBuilderSections(cabinetSections(cab));
    } else {
      var lk = defaultBuilderKind(k);
      var n = k === "drawer_chest" ? 4 : 3;
      var cols = 3;
      var levels = [];
      for (var i = 0; i < n; i++) {
        levels.push(normalizeLevelPlaces({
          id: null,
          kind: lk,
          columns: cols,
          rows: 1,
          placeKinds: makePlaceKinds(cols, lk),
          ghost: false,
        }));
      }
      cabBuilderState.sections = [{ id: null, name: "", levels: levels }];
    }
    if (!cabBuilderState.sections.length) {
      cabBuilderState.sections = [{
        id: null,
        name: "",
        levels: [normalizeLevelPlaces({
          id: null,
          kind: defaultBuilderKind(k),
          columns: 1,
          rows: 1,
          placeKinds: makePlaceKinds(1, defaultBuilderKind(k)),
          ghost: false,
        })],
      }];
    }
    syncBuilderHiddenInputs();
  }

  function builderLevelCount() {
    var max = 1;
    cabBuilderState.sections.forEach(function (sec) {
      max = Math.max(max, (sec.levels || []).length || 1);
    });
    return max;
  }

  function syncBuilderHiddenInputs() {
    if (!cabForm) return;
    var shelvesEl = cabForm.querySelector(".js-vw-cab-shelves");
    var colsEl = cabForm.querySelector(".js-vw-cab-columns");
    var shelves = builderLevelCount();
    var cols = 1;
    var places = 0;
    var drawers = 0;
    cabBuilderState.sections.forEach(function (sec) {
      (sec.levels || []).forEach(function (lvl) {
        if (lvl.ghost) return;
        normalizeLevelPlaces(lvl);
        cols = Math.max(cols, lvl.columns || 1);
        places += lvl.columns || 0;
        (lvl.placeKinds || []).forEach(function (k) {
          if (k === "drawer") drawers += 1;
        });
      });
    });
    if (shelvesEl) shelvesEl.value = String(shelves);
    if (colsEl) colsEl.value = String(cols);
    var meta = cabForm.querySelector(".js-vw-cab-builder-meta");
    if (meta) {
      var secs = cabBuilderState.sections.filter(function (sec) {
        return (sec.levels || []).some(function (lvl) { return !lvl.ghost && (lvl.columns || 0) > 0; });
      }).length;
      meta.textContent =
        (secs > 1 ? secs + " сек. · " : "") +
        shelves + " пол. · " +
        places + " мест" +
        (drawers ? " · " + drawers + " ящ." : "");
    }
  }

  function collectCabinetSectionsPayload() {
    var out = [];
    cabBuilderState.sections.forEach(function (sec) {
      var levels = [];
      var hasReal = false;
      (sec.levels || []).forEach(function (lvl) {
        if (lvl.ghost || !(lvl.columns > 0)) {
          // Пустой ряд — сохраняем, чтобы полки секций оставались на одной высоте.
          levels.push({ kind: "shelf", columns: 0, rows: 1 });
          return;
        }
        normalizeLevelPlaces(lvl);
        hasReal = true;
        var kind = lvl.kind === "drawer" ? "drawer" : "shelf";
        var item = {
          kind: kind,
          columns: lvl.columns,
          rows: kind === "drawer" ? 1 : Math.max(1, Math.min(4, parseInt(lvl.rows, 10) || 1)),
        };
        if (lvl.id) item.id = lvl.id;
        levels.push(item);
      });
      if (!hasReal) return;
      var row = { name: sec.name || "", levels: levels };
      if (sec.id) row.id = sec.id;
      out.push(row);
    });
    return out;
  }

  function hideCabinetBuilderCtx() {
    var menu = cabForm && cabForm.querySelector(".js-vw-cab-ctx");
    if (menu) {
      menu.hidden = true;
      menu.innerHTML = "";
    }
  }

  function showCabinetBuilderCtx(x, y, items) {
    var menu = cabForm && cabForm.querySelector(".js-vw-cab-ctx");
    if (!menu) return;
    menu.innerHTML = "";
    items.forEach(function (it) {
      if (it.sep) {
        var sep = document.createElement("div");
        sep.className = "vw-cab-ctx__sep";
        menu.appendChild(sep);
        return;
      }
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "vw-cab-ctx__item";
      btn.setAttribute("role", "menuitem");
      btn.textContent = it.label;
      btn.addEventListener("click", function () {
        hideCabinetBuilderCtx();
        if (it.action) it.action();
      });
      menu.appendChild(btn);
    });
    menu.hidden = false;
    var pad = 8;
    var rect = menu.getBoundingClientRect();
    var left = Math.min(x, window.innerWidth - rect.width - pad);
    var top = Math.min(y, window.innerHeight - rect.height - pad);
    menu.style.left = Math.max(pad, left) + "px";
    menu.style.top = Math.max(pad, top) + "px";
  }

  function makeGhostLevel() {
    return { id: null, kind: "shelf", columns: 0, rows: 1, placeKinds: [], ghost: true };
  }

  function ensureAlignedLevels(kind) {
    var n = builderLevelCount();
    cabBuilderState.sections.forEach(function (sec) {
      sec.levels = sec.levels || [];
      while (sec.levels.length < n) {
        sec.levels.push(makeGhostLevel());
      }
      sec.levels.forEach(function (lvl) {
        if (!lvl.ghost) normalizeLevelPlaces(lvl);
      });
    });
  }

  function builderAddPlace(secIndex, levelIndex) {
    var sec = cabBuilderState.sections[secIndex];
    if (!sec || !sec.levels[levelIndex] || sec.levels[levelIndex].ghost) return;
    var lvl = normalizeLevelPlaces(sec.levels[levelIndex]);
    if ((lvl.columns || 1) >= 12) return;
    var addKind = lvl.placeKinds[lvl.placeKinds.length - 1] || (lvl.kind === "drawer" ? "drawer" : "shelf");
    lvl.placeKinds.push(addKind);
    lvl.columns = lvl.placeKinds.length;
    normalizeLevelPlaces(lvl);
    renderCabinetBuilder();
  }

  function builderRemovePlace(secIndex, levelIndex) {
    var sec = cabBuilderState.sections[secIndex];
    if (!sec || !sec.levels[levelIndex] || sec.levels[levelIndex].ghost) return;
    var lvl = normalizeLevelPlaces(sec.levels[levelIndex]);
    if ((lvl.columns || 1) <= 1) return;
    lvl.placeKinds.pop();
    lvl.columns = lvl.placeKinds.length;
    normalizeLevelPlaces(lvl);
    renderCabinetBuilder();
  }

  function builderAddShelf(kind) {
    if (builderLevelCount() >= 20) return;
    var lk = defaultBuilderKind(kind);
    // Новая полка на всю ширину: места только в первой секции, у остальных — пустой ряд.
    cabBuilderState.sections.forEach(function (sec, si) {
      sec.levels = sec.levels || [];
      if (si === 0) {
        sec.levels.push(normalizeLevelPlaces({
          id: null,
          kind: lk,
          columns: 1,
          rows: 1,
          placeKinds: makePlaceKinds(1, lk),
          ghost: false,
        }));
      } else {
        sec.levels.push(makeGhostLevel());
      }
    });
    renderCabinetBuilder();
  }

  function builderRemoveShelf(levelIndex) {
    if (builderLevelCount() <= 1) {
      window.alert("Нужна хотя бы одна полка");
      return;
    }
    cabBuilderState.sections.forEach(function (sec) {
      if (sec.levels && sec.levels.length > levelIndex) {
        sec.levels.splice(levelIndex, 1);
      }
    });
    cabBuilderState.sections = cabBuilderState.sections.filter(function (sec) {
      return (sec.levels || []).some(function (lvl) { return !lvl.ghost && (lvl.columns || 0) > 0; });
    });
    if (!cabBuilderState.sections.length) {
      cabBuilderState.sections = [{
        id: null,
        name: "",
        levels: [normalizeLevelPlaces({
          id: null,
          kind: "shelf",
          columns: 1,
          rows: 1,
          placeKinds: makePlaceKinds(1, "shelf"),
          ghost: false,
        })],
      }];
    }
    renderCabinetBuilder();
  }

  function builderSplitShelf(secIndex, levelIndex) {
    var sec = cabBuilderState.sections[secIndex];
    if (!sec || !sec.levels[levelIndex] || sec.levels[levelIndex].ghost) return;
    var lvl = normalizeLevelPlaces(sec.levels[levelIndex]);
    if ((lvl.columns || 1) < 2) {
      window.alert("Чтобы разделить полку, нужно хотя бы 2 места");
      return;
    }
    var kinds = lvl.placeKinds.slice();
    var leftN = Math.ceil(kinds.length / 2);
    var leftKinds = kinds.slice(0, leftN);
    var rightKinds = kinds.slice(leftN);
    var left = { id: sec.id || null, name: sec.name || "", levels: [] };
    var right = { id: null, name: "", levels: [] };
    (sec.levels || []).forEach(function (row, li) {
      if (li === levelIndex) {
        left.levels.push(normalizeLevelPlaces({
          id: lvl.id || null,
          kind: leftKinds[0],
          columns: leftKinds.length,
          rows: 1,
          placeKinds: leftKinds.slice(),
          ghost: false,
        }));
        right.levels.push(normalizeLevelPlaces({
          id: null,
          kind: rightKinds[0],
          columns: rightKinds.length,
          rows: 1,
          placeKinds: rightKinds.slice(),
          ghost: false,
        }));
      } else if (row.ghost) {
        left.levels.push(makeGhostLevel());
        right.levels.push(makeGhostLevel());
      } else {
        // Остальные полки остаются слева целиком; справа — пустой ряд.
        left.levels.push(normalizeLevelPlaces({
          id: row.id || null,
          kind: row.kind,
          columns: row.columns,
          rows: row.rows || 1,
          placeKinds: (row.placeKinds || []).slice(),
          ghost: false,
        }));
        right.levels.push(makeGhostLevel());
      }
    });
    cabBuilderState.sections.splice(secIndex, 1, left, right);
    renderCabinetBuilder();
  }

  function builderMergeWithRight(secIndex, levelIndex) {
    var left = cabBuilderState.sections[secIndex];
    var right = cabBuilderState.sections[secIndex + 1];
    if (!left || !right) return;
    var a = left.levels[levelIndex];
    var b = right.levels[levelIndex];
    if (!a || !b || a.ghost || b.ghost) {
      // Если справа пусто на этой полке — просто убрать пустую секцию, если она вся ghost.
      var rightHas = (right.levels || []).some(function (lvl) { return !lvl.ghost && (lvl.columns || 0) > 0; });
      if (!rightHas) {
        cabBuilderState.sections.splice(secIndex + 1, 1);
        renderCabinetBuilder();
      }
      return;
    }
    normalizeLevelPlaces(a);
    normalizeLevelPlaces(b);
    var mergedKinds = a.placeKinds.concat(b.placeKinds).slice(0, 12);
    a.placeKinds = mergedKinds;
    a.columns = mergedKinds.length;
    a.id = a.id || null;
    normalizeLevelPlaces(a);
    right.levels[levelIndex] = makeGhostLevel();
    var still = (right.levels || []).some(function (lvl) { return !lvl.ghost && (lvl.columns || 0) > 0; });
    if (!still) cabBuilderState.sections.splice(secIndex + 1, 1);
    renderCabinetBuilder();
  }

  function builderSetPlaceKind(secIndex, levelIndex, placeIndex, kind) {
    var sec = cabBuilderState.sections[secIndex];
    if (!sec || !sec.levels[levelIndex] || sec.levels[levelIndex].ghost) return;
    var lvl = normalizeLevelPlaces(sec.levels[levelIndex]);
    if (placeIndex < 0 || placeIndex >= lvl.placeKinds.length) return;
    var want = kind === "drawer" ? "drawer" : "shelf";
    if (lvl.placeKinds[placeIndex] === want) return;
    lvl.placeKinds[placeIndex] = want;
    normalizeLevelPlaces(lvl);
    // Если на одной полке смешались место и ящик — разрежем полку на однородные куски.
    builderNormalizeMixedShelf(secIndex, levelIndex);
    renderCabinetBuilder();
  }

  function builderNormalizeMixedShelf(secIndex, levelIndex) {
    var sec = cabBuilderState.sections[secIndex];
    if (!sec || !sec.levels[levelIndex] || sec.levels[levelIndex].ghost) return;
    var lvl = normalizeLevelPlaces(sec.levels[levelIndex]);
    var kinds = lvl.placeKinds.slice();
    if (!kinds.length) return;
    var uniform = kinds.every(function (k) { return k === kinds[0]; });
    if (uniform) return;

    var groups = [];
    var cur = { kind: kinds[0], kinds: [kinds[0]] };
    for (var i = 1; i < kinds.length; i++) {
      if (kinds[i] === cur.kind) cur.kinds.push(kinds[i]);
      else {
        groups.push(cur);
        cur = { kind: kinds[i], kinds: [kinds[i]] };
      }
    }
    groups.push(cur);
    if (groups.length <= 1) return;

    var replacements = groups.map(function (g, gi) {
      var piece = { id: gi === 0 ? (sec.id || null) : null, name: gi === 0 ? (sec.name || "") : "", levels: [] };
      (sec.levels || []).forEach(function (row, li) {
        if (li !== levelIndex) {
          if (gi === 0 && !row.ghost) {
            piece.levels.push(normalizeLevelPlaces({
              id: row.id || null,
              kind: row.kind,
              columns: row.columns,
              rows: row.rows || 1,
              placeKinds: (row.placeKinds || []).slice(),
              ghost: false,
            }));
          } else {
            piece.levels.push(makeGhostLevel());
          }
        } else {
          piece.levels.push(normalizeLevelPlaces({
            id: gi === 0 ? (lvl.id || null) : null,
            kind: g.kind,
            columns: g.kinds.length,
            rows: 1,
            placeKinds: g.kinds.slice(),
            ghost: false,
          }));
        }
      });
      return piece;
    });
    cabBuilderState.sections.splice(secIndex, 1);
    for (var r = replacements.length - 1; r >= 0; r--) {
      cabBuilderState.sections.splice(secIndex, 0, replacements[r]);
    }
  }

  function openShelfContextMenu(ev, secIndex, levelIndex) {
    ev.preventDefault();
    cabBuilderCtx = { secIndex: secIndex, levelIndex: levelIndex };
    var sec = cabBuilderState.sections[secIndex];
    var lvl = sec && sec.levels[levelIndex];
    if (!lvl || lvl.ghost) return;
    normalizeLevelPlaces(lvl);
    var items = [];
    if ((lvl.columns || 1) >= 2) {
      items.push({
        label: "Разделить эту полку на две",
        action: function () { builderSplitShelf(secIndex, levelIndex); },
      });
    }
    var right = cabBuilderState.sections[secIndex + 1];
    var rightLvl = right && right.levels[levelIndex];
    if (rightLvl && !rightLvl.ghost && (rightLvl.columns || 0) > 0) {
      items.push({
        label: "Объединить с полкой справа",
        action: function () { builderMergeWithRight(secIndex, levelIndex); },
      });
    } else if (right && (right.levels || []).every(function (l) { return l.ghost || !(l.columns > 0); })) {
      items.push({
        label: "Убрать пустую секцию справа",
        action: function () { builderMergeWithRight(secIndex, levelIndex); },
      });
    }
    items.push({ sep: true });
    items.push({
      label: "Удалить полку",
      action: function () { builderRemoveShelf(levelIndex); },
    });
    showCabinetBuilderCtx(ev.clientX, ev.clientY, items);
  }

  function openPlaceContextMenu(ev, secIndex, levelIndex, placeIndex) {
    ev.preventDefault();
    ev.stopPropagation();
    var sec = cabBuilderState.sections[secIndex];
    var lvl = sec && sec.levels[levelIndex];
    if (!lvl || lvl.ghost) return;
    normalizeLevelPlaces(lvl);
    var cur = lvl.placeKinds[placeIndex] || "shelf";
    var items = [
      {
        label: cur === "drawer" ? "Сделать местом на полке" : "Сделать ящиком",
        action: function () {
          builderSetPlaceKind(secIndex, levelIndex, placeIndex, cur === "drawer" ? "shelf" : "drawer");
        },
      },
    ];
    if ((lvl.columns || 1) > 1 && placeIndex === lvl.columns - 1) {
      items.push({
        label: "Убрать это место",
        action: function () { builderRemovePlace(secIndex, levelIndex); },
      });
    }
    showCabinetBuilderCtx(ev.clientX, ev.clientY, items);
  }

  function builderLevelPieces(levelIndex) {
    var pieces = [];
    cabBuilderState.sections.forEach(function (sec, si) {
      var lvl = (sec.levels || [])[levelIndex];
      if (!lvl || lvl.ghost || !(lvl.columns > 0)) return;
      normalizeLevelPlaces(lvl);
      pieces.push({ secIndex: si, level: lvl });
    });
    return pieces;
  }

  function appendBuilderBand(parent, secIndex, levelIndex, lvl, opts) {
    opts = opts || {};
    var band = document.createElement("div");
    var hasDrawer = (lvl.placeKinds || []).some(function (k) { return k === "drawer"; });
    var allDrawer = lvl.kind === "drawer";
    band.className = "vw-cab-builder__band"
      + (allDrawer ? " is-drawer-on-shelf" : "")
      + (hasDrawer && !allDrawer ? " has-drawer" : "")
      + (opts.fullWidth ? " is-full-width" : "");

    if (opts.showSecLabel) {
      var lab = document.createElement("div");
      lab.className = "vw-cab-builder__sec-label";
      lab.textContent = "Секция " + (secIndex + 1);
      band.appendChild(lab);
    }

    var row = document.createElement("div");
    row.className = "vw-cab-builder__row";
    var cols = lvl.columns;
    for (var c = 0; c < cols; c++) {
      (function (placeIndex) {
        var pk = lvl.placeKinds[placeIndex] || "shelf";
        var cell = document.createElement("button");
        cell.type = "button";
        cell.className = "vw-cab-builder__cell" + (pk === "drawer" ? " is-drawer-place" : "");
        cell.title = (pk === "drawer" ? "Ящик на полке" : "Место") + " " + (placeIndex + 1) + " · ПКМ — тип";
        cell.setAttribute("aria-label", (pk === "drawer" ? "Ящик" : "Место") + " " + (placeIndex + 1));
        cell.addEventListener("contextmenu", function (ev) {
          openPlaceContextMenu(ev, secIndex, levelIndex, placeIndex);
        });
        if (placeIndex === cols - 1 && cols > 1) {
          cell.classList.add("is-removable");
          cell.title += " · клик — убрать";
          cell.addEventListener("click", function () {
            builderRemovePlace(secIndex, levelIndex);
          });
        }
        row.appendChild(cell);
      })(c);
    }
    var addRight = document.createElement("button");
    addRight.type = "button";
    addRight.className = "vw-cab-builder__add vw-cab-builder__add--right";
    addRight.textContent = "+";
    addRight.title = "Добавить место справа";
    addRight.setAttribute("aria-label", "Добавить место справа");
    addRight.disabled = cols >= 12;
    addRight.addEventListener("click", function () {
      builderAddPlace(secIndex, levelIndex);
    });
    row.appendChild(addRight);
    band.appendChild(row);

    var rail = document.createElement("button");
    rail.type = "button";
    rail.className = "vw-cab-builder__rail";
    rail.title = opts.fullWidth
      ? "Полка на всю ширину · ПКМ — разделить только эту полку"
      : "Полка · ПКМ — разделить / объединить";
    rail.setAttribute("aria-label", "Полка " + (levelIndex + 1));
    rail.addEventListener("contextmenu", function (ev) {
      openShelfContextMenu(ev, secIndex, levelIndex);
    });
    band.appendChild(rail);
    parent.appendChild(band);
  }

  function renderCabinetBuilder() {
    if (!cabForm) return;
    var canvas = cabForm.querySelector(".js-vw-cab-builder-canvas");
    if (!canvas) return;
    hideCabinetBuilderCtx();
    var kindEl = cabForm.querySelector(".js-vw-cab-kind");
    var kind = kindEl ? kindEl.value : "cabinet";
    ensureAlignedLevels(kind);
    syncBuilderHiddenInputs();

    var title = cabForm.querySelector(".js-vw-cab-builder-title");
    if (title) {
      title.textContent = kind === "drawer_chest"
        ? "Ящики и ячейки"
        : (kind === "rack" ? "Полки стеллажа" : "Полки шкафа");
    }

    canvas.innerHTML = "";
    var wrap = document.createElement("div");
    wrap.className = "vw-cab-builder__rows";
    var nLevels = builderLevelCount();

    for (var li = 0; li < nLevels; li++) {
      var pieces = builderLevelPieces(li);
      if (!pieces.length) continue;
      var levelRow = document.createElement("div");
      var full = pieces.length === 1;
      levelRow.className = "vw-cab-builder__level-row" + (full ? " is-full" : " is-split");
      pieces.forEach(function (p) {
        appendBuilderBand(levelRow, p.secIndex, li, p.level, {
          fullWidth: full,
          showSecLabel: !full,
        });
      });
      wrap.appendChild(levelRow);
    }

    canvas.appendChild(wrap);

    var addShelf = document.createElement("button");
    addShelf.type = "button";
    addShelf.className = "vw-cab-builder__add vw-cab-builder__add--below";
    addShelf.textContent = "+";
    addShelf.title = "Добавить полку снизу";
    addShelf.setAttribute("aria-label", "Добавить полку снизу");
    addShelf.disabled = nLevels >= 20;
    addShelf.addEventListener("click", function () {
      builderAddShelf(kind);
    });
    canvas.appendChild(addShelf);
  }

  function syncCabinetKindLabels() {
    if (!cabForm) return;
    var hint = cabForm.querySelector(".js-vw-cab-kind-hint");
    if (!hint) return;
    hint.textContent =
      "Квадрат на полке — место; ПКМ по квадрату — ящик на полке. ПКМ по полке — разделить только её (остальные остаются на всю ширину). «+» справа/снизу — место или новая полка.";
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
    cabForm.querySelector(".js-vw-cab-notes").value = cab ? (cab.notes || "") : "";
    setVisible(btnDelCab, !!cab);
    if (btnDelCab) {
      btnDelCab.textContent = kind === "rack"
        ? "Удалить стеллаж"
        : (kind === "drawer_chest" ? "Удалить тумбу" : "Удалить шкаф");
    }
    initCabinetBuilderState(cab, kindEl ? kindEl.value : kind);
    syncCabinetKindLabels();
    renderCabinetBuilder();
    openDialog(dlgCab);
  }

  function syncContainerKindOptions(cabKind, selected, isChild, levelKind) {
    var kindSel = contForm.querySelector(".js-vw-cont-kind");
    var value = placeKindFor(
      { kind: cabKind },
      levelKind,
      isChild,
      selected === "organizer" ? "organizer" : ""
    );
    if (kindSel) kindSel.value = value;
    return value;
  }

  function syncOrganizerFields(contKind, cont) {
    var orgRow = contForm.querySelector(".js-vw-cont-organizer-row");
    setVisible(orgRow, false);
    var tiersEl = contForm.querySelector(".js-vw-cont-inner-tiers");
    var colsEl = contForm.querySelector(".js-vw-cont-inner-cols");
    if (tiersEl) tiersEl.value = String(cont && cont.inner_tiers ? cont.inner_tiers : 3);
    if (colsEl) colsEl.value = String(cont && cont.inner_columns ? cont.inner_columns : 2);
  }

  function openContainerForm(cab, cont, shelf, stack, col, level) {
    var cabKind = cabinetKindOf(cab);
    var isChild = !!(cont && cont.parent_id);
    var lvl = level || levelById(cab, cont && cont.level_id) || null;
    var levelKind = (lvl && lvl.kind) || (cont && cont.level_kind) || "";
    var contKind = placeKindFor(cab, levelKind, isChild, cont && cont.kind);
    contForm.querySelector(".js-vw-cont-form-title").textContent = cont
      ? "Место"
      : "Новое место";
    contForm.querySelector(".js-vw-cont-id").value = cont ? String(cont.id) : "";
    var levelIdEl = contForm.querySelector(".js-vw-cont-level-id");
    if (levelIdEl) {
      levelIdEl.value = cont && cont.level_id
        ? String(cont.level_id)
        : (lvl && lvl.id ? String(lvl.id) : "");
    }
    fillContainerCabinetSelect(cab.id, isChild);
    var kindSel = contForm.querySelector(".js-vw-cont-kind");
    if (kindSel) kindSel.value = contKind;
    syncOrganizerFields(contKind, cont);
    contForm.querySelector(".js-vw-cont-color").value = (cont && cont.color) || "#e74c3c";
    var shelfTop = cont ? cont.shelf : (shelf || 1);
    var levelsTotal = (lvl && cab)
      ? (function () {
          var secs = cabinetSections(cab);
          for (var si = 0; si < secs.length; si++) {
            var levels = secs[si].levels || [];
            for (var li = 0; li < levels.length; li++) {
              if (lvl.id && levels[li].id === lvl.id) return levels.length;
              if (!lvl.id && Number(levels[li].index) === Number(shelfTop) && secs.length === 1) return levels.length;
            }
          }
          return cab.shelves;
        })()
      : (cab && cab.shelves);
    var sectionIndex = cont && cont.section_index
      ? cont.section_index
      : (function () {
          if (!lvl || !cab) return null;
          var secs = cabinetSections(cab);
          for (var si = 0; si < secs.length; si++) {
            var levels = secs[si].levels || [];
            for (var li = 0; li < levels.length; li++) {
              if (lvl.id && levels[li].id === lvl.id) return secs[si].index || (si + 1);
            }
          }
          return null;
        })();
    // В форме и в БД: 1 = верхняя полка
    contForm.querySelector(".js-vw-cont-shelf").value = String(
      isChild ? shelfTop : shelfTopToDisplayNum(cab, shelfTop, levelsTotal)
    );
    var stackEl = contForm.querySelector(".js-vw-cont-stack");
    var stackRow = contForm.querySelector(".js-vw-cont-stack-row");
    var stackHint = contForm.querySelector(".js-vw-cont-stack-hint");
    var hideStack = true;
    if (stackEl) stackEl.value = "1";
    if (stackRow) setVisible(stackRow, false);
    if (stackHint) {
      stackHint.textContent = "Полка 1 — верхняя (как в адресе). Место: сверху вниз, слева направо. Адрес подставится сам.";
      setVisible(stackHint, true);
    }
    contForm.querySelector(".js-vw-cont-column").value = String(cont ? cont.column : col || 1);
    var addressEl = contForm.querySelector(".js-vw-cont-address");
    if (addressEl) {
      var addr = cont && cont.address
        ? cont.address
        : suggestAddress(
          cab,
          shelfTop,
          cont ? cont.column : (col || 1),
          null,
          sectionIndex,
          levelsTotal
        );
      addressEl.value = addr || "";
    }
    var labelEl = contForm.querySelector(".js-vw-cont-label");
    if (labelEl) {
      labelEl.value = (addressEl && addressEl.value) || (cont && cont.address) || "";
    }
    var spanSel = contForm.querySelector(".js-vw-cont-colspan");
    var preferredSpan = cont ? (cont.col_span || 1) : 1;
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
      if (cabKind === "drawer_chest") {
        shelfLabel.textContent = "Ящик (1 — верхний, как на экране)";
      } else {
        shelfLabel.textContent = "Полка (1 — верхняя, как на экране)";
      }
    }
    syncShelfLabelHint();
    var shelfInpForHint = contForm.querySelector(".js-vw-cont-shelf");
    if (shelfInpForHint && !shelfInpForHint._vwShelfHintBound) {
      shelfInpForHint._vwShelfHintBound = true;
      shelfInpForHint.addEventListener("input", function () {
        var cabId = parseInt(contForm.querySelector(".js-vw-cont-cabinet").value, 10);
        var currentCab = cabinets.find(function (c) { return c.id === cabId; }) || cab;
        var labelEl2 = shelfInpForHint.closest(".vw-row") &&
          shelfInpForHint.closest(".vw-row").querySelector(".vw-row-label");
        if (!labelEl2) return;
        var parentId = contForm.dataset.parentId;
        if (parentId) {
          labelEl2.textContent = "Ярус внутри";
          return;
        }
        var kindNow = cabinetKindOf(currentCab);
        labelEl2.textContent = kindNow === "drawer_chest"
          ? "Ящик (1 — верхний, как на экране)"
          : "Полка (1 — верхняя, как на экране)";
        syncPlaceAddressFromForm();
      });
    }
    var colInp = contForm.querySelector(".js-vw-cont-column");
    if (colInp && !colInp._vwAddrBound) {
      colInp._vwAddrBound = true;
      colInp.addEventListener("input", function () {
        syncPlaceAddressFromForm();
      });
    }
    var colLabel = contForm.querySelector(".js-vw-cont-column") &&
      contForm.querySelector(".js-vw-cont-column").closest(".vw-row") &&
      contForm.querySelector(".js-vw-cont-column").closest(".vw-row").querySelector(".vw-row-label");
    if (colLabel) {
      colLabel.textContent = isChild ? "Ячейка слева" : "Место";
    }
    // parent id for child cells
    contForm.dataset.parentId = cont && cont.parent_id ? String(cont.parent_id) : "";
    setVisible(btnDelCont, !!cont);
    setVisible(btnOpenContents, !!cont && contKind !== "organizer");
    syncPaletteActive();
    if (!cont || !cont.address) syncPlaceAddressFromForm();
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
    if (ev.key !== "Escape") return;
    var anyOpen = document.querySelector(".vw-modal:not([hidden])");
    if (anyOpen) {
      closeAllDialogs();
      return;
    }
    if (openCabinetId) closeCabinetView();
  });

  if (btnBackList) {
    btnBackList.addEventListener("click", function () {
      closeCabinetView();
    });
  }

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
      var parentId = contForm.dataset.parentId;
      var shelfTop = parentId ? shelf : shelfDisplayToTop(cab, shelf);
      var addressEl = contForm.querySelector(".js-vw-cont-address");
      if (addressEl) addressEl.value = suggestAddress(cab, shelfTop, column);
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
    cabKindSelect.addEventListener("change", function () {
      var kind = cabKindSelect.value;
      var id = cabForm && cabForm.querySelector(".js-vw-cab-id");
      var cabId = id && id.value ? parseInt(id.value, 10) : 0;
      var cab = cabId ? cabinets.find(function (c) { return c.id === cabId; }) : null;
      if (!cab) {
        initCabinetBuilderState(null, kind);
      } else if (kind === "drawer_chest") {
        cabBuilderState.sections.forEach(function (sec) {
          (sec.levels || []).forEach(function (lvl) {
            if (lvl.ghost) return;
            lvl.placeKinds = makePlaceKinds(lvl.columns || 1, "drawer");
            normalizeLevelPlaces(lvl);
          });
        });
      }
      syncCabinetKindLabels();
      renderCabinetBuilder();
    });
  }

  document.addEventListener("click", function (ev) {
    var menu = cabForm && cabForm.querySelector(".js-vw-cab-ctx");
    if (!menu || menu.hidden) return;
    if (menu.contains(ev.target)) return;
    hideCabinetBuilderCtx();
  });
  document.addEventListener("keydown", function (ev) {
    if (ev.key === "Escape") hideCabinetBuilderCtx();
  });
  var contKindSelect = document.querySelector(".js-vw-cont-kind");
  // Тип места выбирается автоматически по мебели — ручного переключения больше нет.
  void contKindSelect;

  var contCabinetSelect = document.querySelector(".js-vw-cont-cabinet");
  if (contCabinetSelect && !contCabinetSelect._vwCabChangeBound) {
    contCabinetSelect._vwCabChangeBound = true;
    contCabinetSelect.addEventListener("change", function () {
      if (!contForm || contForm.dataset.parentId) return;
      var cabId = parseInt(contCabinetSelect.value, 10);
      var cab = cabinets.find(function (c) { return c.id === cabId; });
      if (!cab) return;
      syncPlaceAddressFromForm();
      var shelfInp = contForm.querySelector(".js-vw-cont-shelf");
      var labelEl = shelfInp && shelfInp.closest(".vw-row") &&
        shelfInp.closest(".vw-row").querySelector(".vw-row-label");
      if (labelEl) {
        labelEl.textContent = cabinetKindOf(cab) === "drawer_chest"
          ? "Ящик (1 — верхний, как на экране)"
          : "Полка (1 — верхняя, как на экране)";
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
    var kindVal = kindEl ? kindEl.value : "cabinet";
    var body = {
      name: name,
      code: codeEl ? (codeEl.value || "").trim() : "",
      kind: kindVal,
      notes: cabForm.querySelector(".js-vw-cab-notes").value,
    };
    body.sections = collectCabinetSectionsPayload();
    if (!body.sections.length) {
      window.alert("Добавьте хотя бы одну полку");
      savingCabinet = false;
      return;
    }
    body.shelves = cabForm.querySelector(".js-vw-cab-shelves").value;
    body.columns = cabForm.querySelector(".js-vw-cab-columns").value;
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
    if (!cabinetId) {
      window.alert("Не выбран шкаф — закройте окно и нажмите «+» на полке ещё раз");
      return;
    }
    var addr = syncPlaceAddressFromForm();
    if (!addr) {
      window.alert("Не удалось вычислить адрес — проверьте полку и место");
      return;
    }
    savingContainer = true;
    var idVal = contForm.querySelector(".js-vw-cont-id").value;
    var notesEl = contForm.querySelector(".js-vw-cont-notes");
    var kindSel = contForm.querySelector(".js-vw-cont-kind");
    var cab = cabinets.find(function (c) { return c.id === cabinetId; });
    var cabKind = cabinetKindOf(cab);
    var parentId = parseInt(contForm.dataset.parentId || "", 10) || 0;
    var levelIdEl = contForm.querySelector(".js-vw-cont-level-id");
    var levelId = levelIdEl && levelIdEl.value ? parseInt(levelIdEl.value, 10) : 0;
    var lvl = levelById(cab, levelId);
    var levelKind = (lvl && lvl.kind) || "";
    var existingKind = kindSel ? kindSel.value : "";
    var contKind = placeKindFor(cab, levelKind, !!parentId, existingKind);
    if (kindSel) kindSel.value = contKind;
    var stackVal = 1;
    var tiersEl = contForm.querySelector(".js-vw-cont-inner-tiers");
    var colsEl = contForm.querySelector(".js-vw-cont-inner-cols");
    var shelfFormVal = parseInt(contForm.querySelector(".js-vw-cont-shelf").value, 10) || 1;
    var levelsTotalForSave = lvl
      ? (function () {
          var secs = cabinetSections(cab || {});
          for (var si = 0; si < secs.length; si++) {
            var levels = secs[si].levels || [];
            for (var li = 0; li < levels.length; li++) {
              if (lvl.id && levels[li].id === lvl.id) return levels.length;
            }
          }
          return (cab && cab.shelves) || 1;
        })()
      : ((cab && cab.shelves) || 1);
    var shelfForApi = parentId
      ? shelfFormVal
      : (lvl && lvl.index
        ? lvl.index
        : shelfDisplayToTop(cab || { shelves: 1 }, shelfFormVal, levelsTotalForSave));
    var body = {
      cabinet_id: cabinetId,
      level_id: levelId || null,
      kind: contKind,
      shelf: shelfForApi,
      stack: stackVal,
      column: parseInt(contForm.querySelector(".js-vw-cont-column").value, 10) || 1,
      col_span: parseInt(contForm.querySelector(".js-vw-cont-colspan").value, 10) || 1,
      label: addr,
      color: contForm.querySelector(".js-vw-cont-color").value || "#e74c3c",
      notes: notesEl ? notesEl.value : "",
      address: addr,
      inner_tiers: tiersEl ? parseInt(tiersEl.value, 10) || 3 : 3,
      inner_columns: colsEl ? parseInt(colsEl.value, 10) || 2 : 2,
    };
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
    // Клик по тексту кнопки даёт Text-узел без .closest — берём элемент.
    var t = ev.target;
    if (t && t.nodeType === 3) t = t.parentElement;
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
      var deletedId = parseInt(id, 10);
      fetchJson(detailUrl(apiCabinetTpl, id), { method: "DELETE" })
        .then(function () {
          closeDialog(dlgCab);
          if (openCabinetId === deletedId) openCabinetId = null;
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
      var note = (cont.notes || "").trim();
      if (note) parts.push(note);
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
    if (titleEl) titleEl.textContent = cont.address || cont.label || "Место";
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
  document.documentElement.classList.add("vw-fit-height");
  document.body.classList.add("vw-fit-height");

  if (invTabsToggle && invTabsWrap) {
    invTabsToggle.addEventListener("click", function () {
      setInvTabsCollapsed(!invTabsWrap.classList.contains("is-collapsed"));
      requestAnimationFrame(function () {
        requestAnimationFrame(syncViewportHeightFit);
      });
    });
  }

  loadCabinets();
  window.addEventListener("resize", function () {
    syncInvTabsCollapsed(!!openCabinetId);
    syncViewportHeightFit();
    if (!floorEl) return;
    requestAnimationFrame(function () {
      syncViewportHeightFit();
      floorEl.querySelectorAll(".vw-bin-text").forEach(fitLabelText);
    });
  });
  if (window.visualViewport) {
    window.visualViewport.addEventListener("resize", syncViewportHeightFit);
  }
})();
