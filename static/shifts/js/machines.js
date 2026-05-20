  (function () {
    var LS_SCHEDULE_PRODUCTS = "biota_machines_schedule_product_ids_v1";
    var LS_SCHEDULE_CODES = "biota_machines_schedule_machine_codes_v1";
    var LS_QUICK_EXTRA = "biota_machines_quick_rows_extra_v1";
    var LS_QUICK_SERVER = "biota_machines_quick_server_rows_v1";
    var LS_SCHEDULE_EXTRA = "biota_machines_schedule_rows_extra_v1";
    var LS_CONTENT_VER = "biota_machines_content_version_v1";
    var MIME_SCHEDULE_DRAG = "application/x-biota-schedule-row";
    var scheduleDragHoverField = null;

    // 16 цветов: 8 основных + 8 оттенков
    var COLOR_PALETTE = [
      "#FF4D4D", "#FF8C00", "#EAB308", "#22C55E", "#06B6D4", "#3B82F6", "#A855F7", "#F472B6",
      "#B91C1C", "#C05621", "#A16207", "#15803D", "#0E7490", "#1D4ED8", "#7E22CE", "#BE185D",
    ];
    var colorPickerTarget = null;

    var root = document.querySelector(".machines-page");
    var toggleBtn = document.querySelector(".js-machines-inline-edit-toggle");
    var canQuickEdit = root && (root.getAttribute("data-machines-quick-edit") || "") === "1";
    var hasServerBoard = root && (root.getAttribute("data-machines-has-server") || "") === "1";
    var btnAddQuick = document.querySelector(".js-machines-add-quick-row");
    var btnAddSchedule = document.querySelector(".js-machines-add-schedule-row");
    var quickWrap = root ? root.querySelector(".machines-quick-rows") : null;
    var scheduleWrap = root ? root.querySelector(".machines-schedule-rows") : null;
    var tplQuick = document.getElementById("machines-tpl-quick-row");
    var tplSchedule = document.getElementById("machines-tpl-schedule-row");

    function getCookie(name) {
      var parts = ("; " + document.cookie).split("; " + name + "=");
      if (parts.length === 2) return parts.pop().split(";").shift() || "";
      return "";
    }

    function splitQuickProductLabel(t) {
      var s = sanitizeQuickProductText(t);
      var m = s.match(/^(.+?)\s+[—–\-]\s+(.+)$/);
      if (!m) return { sku: s, title: "" };
      return { sku: m[1].trim(), title: m[2].trim() };
    }

    function sanitizeQuickProductText(t) {
      var s = (t != null ? String(t) : "").replace(/\u200b/g, "").replace(/\s+/g, " ").trim();
      // «кукуу — — — —» → «кукуu» после серии пустых разделителей
      s = s.replace(/(?:\s+[—–\-]\s*)+$/, "").trim();
      s = s.replace(/(\s+[—–\-]\s*){2,}/g, " - ");
      return s;
    }

    function getQuickFieldFlatText(inner) {
      if (!inner) return "";
      var sku = inner.querySelector(":scope > .machines-quick-field-part--sku");
      var title = inner.querySelector(":scope > .machines-quick-field-part--title");
      if (sku && title && inner.classList.contains("is-split")) {
        var a = (sku.textContent || "").replace(/\u200b/g, "").trim();
        var b = (title.textContent || "").replace(/\u200b/g, "").trim();
        if (a && b) return a + " - " + b;
        if (a) return a;
        return b;
      }
      return (inner.textContent || "").replace(/\u200b/g, "").trim();
    }

    function ensureQuickNotesBody(notesCell) {
      if (!notesCell || !notesCell.classList.contains("machines-cell--notes")) return null;
      var body = notesCell.querySelector(":scope > .machines-quick-notes-body");
      if (body) return body;
      body = document.createElement("div");
      body.className = "machines-quick-notes-body";
      var placeholder = notesCell.getAttribute("data-placeholder");
      if (placeholder) {
        body.setAttribute("data-placeholder", placeholder);
        notesCell.removeAttribute("data-placeholder");
      }
      var toMove = [];
      Array.prototype.slice.call(notesCell.childNodes).forEach(function (node) {
        if (node.nodeType === 1 && node.classList && node.classList.contains("machines-quick-row-delete")) return;
        toMove.push(node);
      });
      toMove.forEach(function (node) {
        notesCell.removeChild(node);
        body.appendChild(node);
      });
      notesCell.insertBefore(body, notesCell.firstChild);
      return body;
    }

    function readQuickNotesText(notesCell) {
      if (!notesCell) return "";
      ensureQuickNotesBody(notesCell);
      var body = notesCell.querySelector(":scope > .machines-quick-notes-body");
      var el = body || notesCell;
      return (el.textContent || "").replace(/\u200b/g, "").trim();
    }

    function resolveQuickEditableCell(el) {
      if (!el) return null;
      if (el.closest(".machines-quick-notes-body")) {
        return el.closest(".machines-cell--notes");
      }
      var inner = el.closest(".machines-quick-field-view[contenteditable='true']");
      if (inner) {
        return inner.closest(".machines-cell--field") || inner.closest(".machines-cell");
      }
      return el.closest(".machines-quick-row > .machines-cell[contenteditable='true']");
    }

    function quickFieldEditableInner(cell) {
      if (!cell || !cell.classList.contains("machines-cell--field") || cell.classList.contains("machines-cell--notes")) {
        return null;
      }
      return cell.querySelector(":scope > .machines-quick-field-and-setup > .machines-quick-field-view");
    }

    function isQuickEditableCellActive(cell) {
      if (!cell) return false;
      if (cell.classList.contains("machines-cell--notes")) {
        var notesBody = cell.querySelector(":scope > .machines-quick-notes-body");
        return !!(notesBody && notesBody.getAttribute("contenteditable") === "true");
      }
      var inner = quickFieldEditableInner(cell);
      if (inner) return inner.getAttribute("contenteditable") === "true";
      return cell.getAttribute("contenteditable") === "true";
    }

    function fillQuickFieldViewTwoParts(inner, t) {
      if (!inner || !inner.classList || !inner.classList.contains("machines-quick-field-view")) return;
      var parts = splitQuickProductLabel(t != null ? String(t) : "");
      var sku = inner.querySelector(":scope > .machines-quick-field-part--sku");
      var title = inner.querySelector(":scope > .machines-quick-field-part--title");
      if (!sku || !title) {
        inner.textContent = t != null ? String(t) : "";
        return;
      }
      sku.textContent = parts.sku;
      title.textContent = parts.title;
      if (parts.sku && parts.title) inner.classList.add("is-split");
      else inner.classList.remove("is-split");
    }

    function readQuickProductSlotPlainText(cell) {
      if (!cell) return "";
      var inner = cell.querySelector(".machines-quick-field-view");
      if (inner) return getQuickFieldFlatText(inner);
      return (cell.textContent || "").replace(/\u200b/g, "").trim();
    }

    function collapseQuickFieldViewForEdit(inner) {
      if (!inner || !inner.classList.contains("machines-quick-field-view")) return;
      var flat = sanitizeQuickProductText(getQuickFieldFlatText(inner));
      inner.classList.remove("is-split");
      while (inner.firstChild) {
        inner.removeChild(inner.firstChild);
      }
      if (flat) {
        inner.appendChild(document.createTextNode(flat));
      }
    }

    function collectMachinesBoardPayload() {
      var machine_rows = [];
      quickWrap.querySelectorAll(".machines-quick-row").forEach(function (row) {
        var cells = row.querySelectorAll(":scope > .machines-cell");
        if (cells.length < 4) return;
        var curPidRaw = readQuickFieldProductPidAttr(cells[1]);
        var nextPidRaw = readQuickFieldProductPidAttr(cells[2]);
        var curPid = null;
        var nextPid = null;
        if (curPidRaw) {
          var cpn = parseInt(curPidRaw, 10);
          if (!isNaN(cpn)) curPid = cpn;
        }
        if (nextPidRaw) {
          var npn = parseInt(nextPidRaw, 10);
          if (!isNaN(npn)) nextPid = npn;
        }
        machine_rows.push({
          code: (cells[0].textContent || "").trim(),
          current: readQuickProductSlotPlainText(cells[1]),
          next: readQuickProductSlotPlainText(cells[2]),
          extra: readQuickNotesText(cells[3]),
          tag: "Т",
          current_product_id: curPid,
          next_product_id: nextPid,
          current_setup_id: readQuickFieldSetupIdAttr(cells[1]) || null,
          next_setup_id: readQuickFieldSetupIdAttr(cells[2]) || null,
        });
      });
      var schedule_rows = [];
      scheduleWrap.querySelectorAll(".machines-schedule-row").forEach(function (row) {
        var labelCell = row.querySelector(".machines-cell--schedule-label");
        var codeEl = row.querySelector(".machines-cell--schedule-code");
        var hid = labelCell ? labelCell.querySelector(".js-machines-product-id") : null;
        var pidRaw = hid ? (hid.value || "").trim() : "";
        var pid = null;
        if (pidRaw) {
          var pn = parseInt(pidRaw, 10);
          if (!isNaN(pn)) pid = pn;
        }
        var qtyEl = row.querySelector(".machines-cell--schedule-qty");
        var priorityEl = row.querySelector(".machines-cell--schedule-priority");
        var colorTrigger = row.querySelector(".js-machines-color-trigger");
        schedule_rows.push({
          label: labelCell ? (labelCell.getAttribute("data-original-label") || "").trim() : "",
          machine_code: codeEl ? (codeEl.textContent || "").trim() : "",
          product_id: pid,
          setup_id: (function () {
            var sh = labelCell ? labelCell.querySelector(".js-machines-setup-id") : null;
            var raw = sh ? (sh.value || "").trim() : "";
            if (!raw) return null;
            var sn = parseInt(raw, 10);
            return isNaN(sn) ? null : sn;
          })(),
          qty: qtyEl ? (qtyEl.textContent || "").trim() : "",
          priority: priorityEl ? (priorityEl.textContent || "").trim() : "",
          color: colorTrigger ? (colorTrigger.dataset.color || "").trim() : "",
        });
      });
      var cv = parseInt((root.getAttribute("data-machines-content-version") || "0").trim(), 10);
      return {
        action: "save_machines_board",
        content_version: isNaN(cv) ? null : cv,
        machine_rows: machine_rows,
        schedule_rows: schedule_rows,
      };
    }

    async function postMachinesBoardToServer() {
      if (!canQuickEdit) return true;
      var token = (getCookie("csrftoken") || "").trim();
      if (!token) {
        alert("Нет CSRF-токена (csrftoken). Обновите страницу.");
        return false;
      }
      var body = collectMachinesBoardPayload();
      try {
        var res = await fetch(window.location.pathname || "/machines/", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-CSRFToken": token,
            "X-Requested-With": "XMLHttpRequest",
          },
          body: JSON.stringify(body),
          credentials: "same-origin",
        });
        var data = null;
        try {
          data = await res.json();
        } catch (ej) {
          data = null;
        }
        if (!res.ok || !data || !data.ok) {
          alert((data && data.error) || "Не удалось сохранить сводку на сервер.");
          return false;
        }
        return true;
      } catch (e) {
        alert("Ошибка сети при сохранении сводки.");
        return false;
      }
    }

    if (!root || !quickWrap || !scheduleWrap || !tplQuick || !tplSchedule) return;

    var btnHistory = root.querySelector(".js-machines-history-btn");
    var historyBackdrop = root.querySelector(".js-machines-history-backdrop");
    var historyPanel = root.querySelector("#machines-history-panel");
    var historyList = root.querySelector(".js-machines-history-list");

    var previewPop = document.getElementById("machines-quick-preview-pop");
    var previewImg = previewPop ? previewPop.querySelector(".machines-quick-preview-pop-img") : null;
    var previewEmpty = previewPop ? previewPop.querySelector(".machines-quick-preview-pop-empty") : null;
    var quickPreviewPidShown = null;
    if (previewPop && previewPop.parentElement !== document.body) {
      document.body.appendChild(previewPop);
    }

    function positionQuickPreviewPop(clientX, clientY) {
      if (!previewPop) return;
      previewPop.style.left = "0px";
      previewPop.style.top = "0px";
      var rect = previewPop.getBoundingClientRect();
      var pad = 12;
      var w = rect.width || previewPop.offsetWidth || 260;
      var h = rect.height || previewPop.offsetHeight || 180;
      var vw = Math.max(document.documentElement.clientWidth || 0, window.innerWidth || 0);
      var vh = Math.max(document.documentElement.clientHeight || 0, window.innerHeight || 0);
      var x = clientX + pad;
      var y = clientY + pad;
      if (x + w > vw - 8) x = clientX - w - pad;
      if (y + h > vh - 8) y = clientY - h - pad;
      x = Math.max(8, Math.min(x, vw - w - 8));
      y = Math.max(8, Math.min(y, vh - h - 8));
      previewPop.style.left = x + "px";
      previewPop.style.top = y + "px";
    }

    function hideQuickPreview() {
      quickPreviewPidShown = null;
      if (!previewPop) return;
      previewPop.hidden = true;
      previewPop.setAttribute("aria-hidden", "true");
      if (previewImg) {
        previewImg.removeAttribute("src");
        previewImg.hidden = true;
      }
      if (previewEmpty) previewEmpty.hidden = false;
    }

    function showQuickPreviewForPid(pidStr, clientX, clientY) {
      if (!previewPop || !previewImg || !previewEmpty) return;
      if (quickPreviewPidShown === pidStr && !previewPop.hidden) {
        positionQuickPreviewPop(clientX, clientY);
        return;
      }
      quickPreviewPidShown = pidStr;
      var url = previewUrlById(pidStr);
      if (url) {
        previewImg.hidden = false;
        previewEmpty.hidden = true;
        previewImg.onload = function () {
          positionQuickPreviewPop(clientX, clientY);
        };
        previewImg.src = url;
      } else {
        previewImg.hidden = true;
        previewImg.removeAttribute("src");
        previewEmpty.hidden = false;
      }
      previewPop.hidden = false;
      previewPop.setAttribute("aria-hidden", "false");
      requestAnimationFrame(function () {
        positionQuickPreviewPop(clientX, clientY);
      });
    }

    function normMachineCodeKey(s) {
      return (s || "").replace(/\r\n|\r|\n/g, " ").replace(/\s+/g, " ").trim().toUpperCase();
    }

    function hueFromMachineCode(code) {
      var c = normMachineCodeKey(code);
      if (!c) return 210;
      var palette = [212, 148, 28, 276, 186, 338, 92, 248, 12, 168, 302, 54];
      var numeric = c.match(/\d+/g);
      if (numeric && numeric.length) {
        var n = parseInt(numeric[numeric.length - 1], 10);
        if (!isNaN(n)) return palette[Math.abs(n) % palette.length];
      }
      var h = 0;
      for (var i = 0; i < c.length; i++) h = (h * 31 + c.charCodeAt(i)) | 0;
      return palette[Math.abs(h) % palette.length];
    }

    function findScheduleLabelByMachineAndProduct(machineCode, productId) {
      if (!scheduleWrap) return null;
      var mc = normMachineCodeKey(machineCode);
      var ps = String(productId || "").trim();
      if (!mc || !ps) return null;
      var labels = scheduleWrap.querySelectorAll(".machines-cell--schedule-label");
      for (var i = 0; i < labels.length; i++) {
        var lb = labels[i];
        if (normMachineCodeKey(lb.getAttribute("data-machine-code") || "") !== mc) continue;
        var hid = lb.querySelector(".js-machines-product-id");
        if (!hid || (hid.value || "").trim() !== ps) continue;
        return lb;
      }
      return null;
    }

    function flushQuickSetupSelectionsToSchedule() {
      if (!quickWrap || !scheduleWrap) return;
      quickWrap.querySelectorAll(".machines-quick-row").forEach(function (qrow) {
        var cells = qrow.querySelectorAll(":scope > .machines-cell");
        if (cells.length < 3) return;
        var code = (cells[0].textContent || "").replace(/\r\n|\r|\n/g, " ").replace(/\s+/g, " ").trim();
        [1, 2].forEach(function (ix) {
          var fcell = cells[ix];
          var qsel = fcell.querySelector(".js-machines-quick-setup-select");
          var pid = readQuickFieldProductPidAttr(fcell);
          if (!qsel || !code || !pid) return;
          var sch = findScheduleLabelByMachineAndProduct(code, pid);
          if (!sch) return;
          var sh = sch.querySelector(".js-machines-setup-id");
          if (sh) sh.value = (qsel.value || "").trim();
        });
      });
    }

    function syncQuickFieldSetupSelect(fieldCell) {
      var sel = fieldCell.querySelector(".js-machines-quick-setup-select");
      if (!sel) return;
      var qrow = fieldCell.closest(".machines-quick-row");
      if (!qrow || !quickWrap.contains(qrow)) return;
      var cells = qrow.querySelectorAll(":scope > .machines-cell");
      if (cells.length < 3) return;
      if (fieldCell !== cells[1] && fieldCell !== cells[2]) return;
      var edit = root.getAttribute("data-inline-edit-mode") === "1";
      var code = (cells[0].textContent || "").replace(/\r\n|\r|\n/g, " ").replace(/\s+/g, " ").trim();
      var pid = readQuickFieldProductPidAttr(fieldCell);
      var setups = setupsArrayByProductId(pid);
      sel.textContent = "";
      if (!pid || !code) {
        var z0 = document.createElement("option");
        z0.value = "";
        z0.textContent = "—";
        sel.appendChild(z0);
        sel.value = "";
        sel.disabled = true;
        return;
      }
      if (!setups.length) {
        var z1 = document.createElement("option");
        z1.value = "";
        z1.textContent = "Нет установок";
        sel.appendChild(z1);
        sel.value = "";
        sel.disabled = true;
        return;
      }
      if (setups.length > 1) {
        var ph = document.createElement("option");
        ph.value = "";
        ph.textContent = "—";
        sel.appendChild(ph);
      }
      setups.forEach(function (su, idx) {
        var o = document.createElement("option");
        o.value = String(su.id);
        var nm = (su.name || "").trim();
        o.textContent = nm || "без названия";
        sel.appendChild(o);
      });
      var prevSetup =
        (fieldCell.getAttribute("data-current-setup-id") || sel.getAttribute("data-current-setup-id") || "").trim();
      if (!prevSetup) {
        var schLabel = findScheduleLabelByMachineAndProduct(code, pid);
        var schHid = schLabel ? schLabel.querySelector(".js-machines-setup-id") : null;
        prevSetup = schHid ? (schHid.value || "").trim() : (sel.value || "").trim();
      }
      var valid = setups.some(function (s) {
        return String(s.id) === String(prevSetup);
      });
      var selected = valid ? prevSetup : setups.length === 1 ? String(setups[0].id) : "";
      sel.value = selected;
      if (selected) {
        fieldCell.setAttribute("data-current-setup-id", selected);
        sel.setAttribute("data-current-setup-id", selected);
      } else {
        fieldCell.removeAttribute("data-current-setup-id");
        sel.removeAttribute("data-current-setup-id");
      }
      sel.disabled = !canQuickEdit || !edit || !pid || !setups.length;
    }

    function syncAllQuickFieldSetupSelects() {
      if (!quickWrap) return;
      quickWrap.querySelectorAll(".machines-quick-row").forEach(function (qrow) {
        var cells = qrow.querySelectorAll(":scope > .machines-cell");
        if (cells.length >= 3) {
          syncQuickFieldSetupSelect(cells[1]);
          syncQuickFieldSetupSelect(cells[2]);
        }
      });
    }

    function syncMachineCodeAppearance() {
      if (!quickWrap || !scheduleWrap) return;
      quickWrap.querySelectorAll(".machines-quick-row").forEach(function (row) {
        var ce = row.querySelector(":scope > .machines-cell--code");
        if (!ce) return;
        var v = normMachineCodeKey(ce.textContent);
        if (!v) {
          ce.removeAttribute("data-mc-tone");
          ce.style.removeProperty("--mc-hue");
          return;
        }
        ce.setAttribute("data-mc-tone", "1");
        ce.style.setProperty("--mc-hue", String(hueFromMachineCode(v)));
      });
      scheduleWrap.querySelectorAll(".machines-cell--schedule-code").forEach(function (ce) {
        var v = normMachineCodeKey(ce.textContent);
        if (!v) {
          ce.removeAttribute("data-mc-tone");
          ce.style.removeProperty("--mc-hue");
          return;
        }
        ce.setAttribute("data-mc-tone", "1");
        ce.style.setProperty("--mc-hue", String(hueFromMachineCode(v)));
      });
      syncAllQuickFieldSetupSelects();
    }

    var _catalog = null;
    var suggestTimer = null;
    var LS_PAGE_HISTORY = "biota_machines_page_history_v1";
    var MAX_PAGE_HISTORY = 150;

    function readJson(key, fallback) {
      try {
        var raw = localStorage.getItem(key);
        if (!raw) return fallback;
        var o = JSON.parse(raw);
        return o;
      } catch (e) {
        return fallback;
      }
    }

    function writeJson(key, val) {
      try {
        localStorage.setItem(key, JSON.stringify(val));
      } catch (e) {}
    }

    function getMachinesActor() {
      return (root.getAttribute("data-username") || "").trim() || "Неизвестный пользователь";
    }

    function pushPageHistory(what) {
      var msg = String(what || "").trim().slice(0, 500);
      if (!msg) return;
      var list = readJson(LS_PAGE_HISTORY, []);
      if (!Array.isArray(list)) list = [];
      list.unshift({
        ts: Date.now(),
        who: getMachinesActor(),
        what: msg
      });
      if (list.length > MAX_PAGE_HISTORY) list = list.slice(0, MAX_PAGE_HISTORY);
      writeJson(LS_PAGE_HISTORY, list);
      if (historyPanel && !historyPanel.hidden && historyList) renderHistoryList();
    }

    function formatHistoryTime(ts) {
      try {
        return new Date(ts || 0).toLocaleString("ru-RU", {
          day: "2-digit",
          month: "2-digit",
          year: "numeric",
          hour: "2-digit",
          minute: "2-digit",
          second: "2-digit"
        });
      } catch (e) {
        return "—";
      }
    }

    function renderHistoryList() {
      if (!historyList) return;
      var list = readJson(LS_PAGE_HISTORY, []);
      if (!Array.isArray(list) || list.length === 0) {
        historyList.innerHTML = '<p class="muted machines-history-empty">Пока нет записей в истории.</p>';
        return;
      }
      historyList.textContent = "";
      list.forEach(function (entry) {
        var wrap = document.createElement("div");
        wrap.className = "machines-history-entry";
        var meta = document.createElement("div");
        meta.className = "machines-history-entry__meta";
        meta.textContent = (entry.who || "—") + " · " + formatHistoryTime(entry.ts);
        var whatEl = document.createElement("div");
        whatEl.className = "machines-history-entry__what";
        whatEl.textContent = entry.what || "";
        wrap.appendChild(meta);
        wrap.appendChild(whatEl);
        historyList.appendChild(wrap);
      });
    }

    function openHistoryPanel() {
      if (!historyPanel || !historyBackdrop || !btnHistory) return;
      historyPanel.hidden = false;
      historyBackdrop.hidden = false;
      historyBackdrop.setAttribute("aria-hidden", "false");
      btnHistory.setAttribute("aria-expanded", "true");
      document.body.style.overflow = "hidden";
      renderHistoryList();
      try {
        var clos = historyPanel.querySelector(".js-machines-history-close");
        if (clos) clos.focus();
      } catch (e1) {}
    }

    function closeHistoryPanel() {
      if (!historyPanel || !historyBackdrop || !btnHistory) return;
      historyPanel.hidden = true;
      historyBackdrop.hidden = true;
      historyBackdrop.setAttribute("aria-hidden", "true");
      btnHistory.setAttribute("aria-expanded", "false");
      document.body.style.overflow = "";
    }

    function onHistoryEscape(e) {
      if (e.key !== "Escape") return;
      if (!historyPanel || historyPanel.hidden) return;
      closeHistoryPanel();
    }

    function readStore() {
      var o = readJson(LS_SCHEDULE_PRODUCTS, {});
      return o && typeof o === "object" ? o : {};
    }

    function writeStore(map) {
      writeJson(LS_SCHEDULE_PRODUCTS, map);
    }

    function dataTransferHasScheduleDrag(dt) {
      if (!dt || !dt.types) return false;
      try {
        if (typeof dt.types.contains === "function" && dt.types.contains(MIME_SCHEDULE_DRAG)) return true;
      } catch (e1) {}
      for (var ti = 0; ti < dt.types.length; ti++) {
        if (dt.types[ti] === MIME_SCHEDULE_DRAG) return true;
      }
      return false;
    }

    function clearScheduleDropHover() {
      if (scheduleDragHoverField) {
        scheduleDragHoverField.classList.remove("machines-drop-target");
        scheduleDragHoverField = null;
      }
    }

    function scheduleLabelDisplayText(labelCell) {
      if (!labelCell) return "";
      var hid = labelCell.querySelector(".js-machines-product-id");
      if (hid && (hid.value || "").trim()) {
        var nm = nameById(hid.value.trim());
        if (nm) return nm;
      }
      var span = labelCell.querySelector(".machines-schedule-label-view");
      if (span && (span.textContent || "").trim()) return span.textContent.trim();
      return (labelCell.getAttribute("data-original-label") || "").trim();
    }

    function syncScheduleDragHandles(on) {
      scheduleWrap.querySelectorAll(".machines-schedule-drag-handle").forEach(function (h) {
        if (on) {
          h.setAttribute("draggable", "true");
        } else {
          h.removeAttribute("draggable");
        }
      });
    }

    function persistScheduleMachineCodes() {
      var map = {};
      scheduleWrap.querySelectorAll(".machines-cell--schedule-label").forEach(function (label) {
        var idx = label.getAttribute("data-schedule-index");
        if (idx === null || idx === undefined || idx === "") return;
        var row = label.closest(".machines-schedule-row");
        var codeEl = row && row.querySelector(".machines-cell--schedule-code");
        map[idx] = codeEl ? (codeEl.textContent || "").trim() : "";
      });
      writeJson(LS_SCHEDULE_CODES, map);
    }

    function applyScheduleMachineCodes() {
      var map = readJson(LS_SCHEDULE_CODES, null);
      if (!map || typeof map !== "object") return;
      scheduleWrap.querySelectorAll(".machines-cell--schedule-label").forEach(function (label) {
        var idx = label.getAttribute("data-schedule-index");
        if (idx === null || idx === undefined || idx === "") return;
        if (!Object.prototype.hasOwnProperty.call(map, idx)) return;
        var code = map[idx] != null ? String(map[idx]).trim() : "";
        var row = label.closest(".machines-schedule-row");
        var codeEl = row && row.querySelector(".machines-cell--schedule-code");
        if (!codeEl) return;
        codeEl.textContent = code;
        label.setAttribute("data-machine-code", code);
        if (code) {
          codeEl.classList.remove("is-empty");
        } else {
          codeEl.classList.add("is-empty");
        }
      });
      syncMachineCodeAppearance();
    }

    function getCatalog() {
      if (_catalog) return _catalog;
      var el = document.getElementById("machines-products-data");
      if (!el || !el.textContent) {
        _catalog = [];
        return _catalog;
      }
      try {
        _catalog = JSON.parse(el.textContent);
        if (!Array.isArray(_catalog)) _catalog = [];
      } catch (e) {
        _catalog = [];
      }
      return _catalog;
    }

    function nameById(id) {
      var sid = String(id);
      var cat = getCatalog();
      for (var i = 0; i < cat.length; i++) {
        if (String(cat[i].id) === sid) return (cat[i].name || "").trim();
      }
      return "";
    }

    function setupsArrayByProductId(pidStr) {
      var sid = String(pidStr || "").trim();
      if (!sid) return [];
      var cat = getCatalog();
      for (var j = 0; j < cat.length; j++) {
        if (String(cat[j].id) === sid) {
          var arr = cat[j].setups;
          return Array.isArray(arr) ? arr : [];
        }
      }
      return [];
    }

    function setupLineFromSetups(setups, setupIdStr) {
      var want = String(setupIdStr || "").trim();
      if (!want || !setups || !setups.length) return "";
      for (var i = 0; i < setups.length; i++) {
        if (String(setups[i].id) === want) {
          var nm = (setups[i].name || "").trim();
          return nm ? "Уст. " + String(i + 1) + " — " + nm : "Уст. " + String(i + 1);
        }
      }
      return "";
    }

    function syncScheduleSetupUi(labelCell) {
      if (!labelCell) return;
      var setupHid = labelCell.querySelector(".js-machines-setup-id");
      var productHid = labelCell.querySelector(".js-machines-product-id");
      if (!setupHid || !productHid) return;
      var pid = (productHid.value || "").trim();
      var setups = setupsArrayByProductId(pid);
      var prevSetup = (setupHid.value || "").trim();
      if (!pid) {
        setupHid.value = "";
        syncAllQuickFieldSetupSelects();
        return;
      }
      if (!setups.length) {
        setupHid.value = "";
        syncAllQuickFieldSetupSelects();
        return;
      }
      var valid = setups.some(function (s) {
        return String(s.id) === String(prevSetup);
      });
      var selected = valid ? prevSetup : setups.length === 1 ? String(setups[0].id) : "";
      setupHid.value = selected;
      syncAllQuickFieldSetupSelects();
    }

    function catalogHasId(id) {
      if (!id) return true;
      return !!nameById(id);
    }

    function previewUrlById(id) {
      var sid = String(id);
      var cat = getCatalog();
      for (var i = 0; i < cat.length; i++) {
        if (String(cat[i].id) === sid) return (cat[i].list_preview_url || "").trim();
      }
      return "";
    }

    function productDetailHrefFromId(pidStr) {
      var tpl = (root.getAttribute("data-product-detail-url-tpl") || "").trim();
      var sent = String(root.getAttribute("data-product-detail-sentinel") || "").trim();
      var pid = (pidStr || "").trim();
      if (!tpl || !sent || !pid) return "";
      return tpl.split(sent).join(pid);
    }

    function productSetupDetailHref(baseHref, setupId) {
      var href = (baseHref || "").trim();
      var sid = (setupId || "").trim();
      if (!href || !sid) return href;
      try {
        var u = new URL(href, window.location.origin);
        u.searchParams.set("tab", "setup-" + sid);
        return u.pathname + u.search + u.hash;
      } catch (e) {
        return href + (href.indexOf("?") === -1 ? "?" : "&") + "tab=setup-" + encodeURIComponent(sid);
      }
    }

    function readQuickFieldSetupIdAttr(cell) {
      if (!cell) return "";
      var sel = cell.querySelector(".js-machines-quick-setup-select");
      var fromSelect = sel ? (sel.value || sel.getAttribute("data-current-setup-id") || "").trim() : "";
      if (fromSelect) return fromSelect;
      return (cell.getAttribute("data-current-setup-id") || "").trim();
    }

    function maybeOpenQuickSetupFromClick(e) {
      if (!e || root.getAttribute("data-inline-edit-mode") === "1") return false;
      var field = e.target.closest(".machines-quick-row > .machines-cell--field:not(.machines-cell--notes)");
      if (!field || !quickWrap.contains(field)) return false;
      var sel = field.querySelector(".js-machines-quick-setup-select");
      if (!sel) return false;
      var rect = sel.getBoundingClientRect();
      var insideSetupControl =
        e.clientX >= rect.left && e.clientX <= rect.right && e.clientY >= rect.top && e.clientY <= rect.bottom;
      if (!insideSetupControl) return false;
      var setupId = readQuickFieldSetupIdAttr(field);
      if (!setupId) return false;
      var href = (field.getAttribute("data-product-href") || "").trim();
      if (!href) return false;
      e.preventDefault();
      e.stopPropagation();
      window.location.href = productSetupDetailHref(href, setupId);
      return true;
    }

    function readQuickFieldProductPidAttr(cell) {
      if (!cell) return "";
      var sp = cell.querySelector(".machines-quick-field-view");
      var v = sp ? (sp.getAttribute("data-preview-product-id") || "").trim() : "";
      if (v) return v;
      return (cell.getAttribute("data-preview-product-id") || "").trim();
    }

    function clearQuickFieldProductRef(cell) {
      cell.removeAttribute("data-preview-product-id");
      cell.removeAttribute("data-product-href");
      cell.removeAttribute("data-current-setup-id");
      var sp = cell.querySelector(".machines-quick-field-view");
      if (sp) {
        sp.removeAttribute("data-preview-product-id");
        sp.removeAttribute("data-product-href");
      }
      syncQuickFieldSetupSelect(cell);
    }

    function setQuickFieldProductRef(cell, pidStr) {
      var pid = (pidStr || "").trim();
      if (!pid || !nameById(pid)) {
        clearQuickFieldProductRef(cell);
        return;
      }
      cell.setAttribute("data-preview-product-id", pid);
      var href = productDetailHrefFromId(pid);
      if (href) cell.setAttribute("data-product-href", href);
      else cell.removeAttribute("data-product-href");
      var sp = cell.querySelector(".machines-quick-field-view");
      if (sp) {
        sp.setAttribute("data-preview-product-id", pid);
        if (href) sp.setAttribute("data-product-href", href);
        else sp.removeAttribute("data-product-href");
      }
      syncQuickFieldSetupSelect(cell);
    }

    function syncQuickFieldProductRefAfterBlur(cell) {
      if (!cell || !cell.classList.contains("machines-cell--field") || cell.classList.contains("machines-cell--notes")) return;
      var qrow = cell.closest(".machines-quick-row");
      if (!qrow || !quickWrap.contains(qrow)) return;
      var cells = qrow.querySelectorAll(":scope > .machines-cell");
      if (cells.length < 4) return;
      if (cell !== cells[1] && cell !== cells[2]) return;
      var pid = readQuickFieldProductPidAttr(cell);
      if (!pid) {
        syncQuickFieldSetupSelect(cell);
        return;
      }
      if (!nameById(pid)) {
        clearQuickFieldProductRef(cell);
        syncQuickFieldSetupSelect(cell);
        return;
      }
      var t = readQuickProductSlotPlainText(cell).replace(/\r\n|\r|\n/g, " ").trim();
      if (!t) {
        clearQuickFieldProductRef(cell);
      }
      syncQuickFieldSetupSelect(cell);
    }

    function closeSuggestExcept(exceptCombo) {
      root.querySelectorAll(".machines-schedule-product-combo.is-open").forEach(function (c) {
        if (exceptCombo && c === exceptCombo) return;
        c.classList.remove("is-open");
        var row = c.closest(".machines-schedule-row");
        if (row) row.classList.remove("machines-schedule-row--suggest-open");
        var p = c.querySelector(".machines-product-suggest");
        if (p) p.hidden = true;
      });
    }

    function syncProductComboDisplay(cell) {
      var span = cell.querySelector(".machines-schedule-label-view");
      var hid = cell.querySelector(".js-machines-product-id");
      var search = cell.querySelector(".js-machines-product-search");
      var combo = cell.querySelector(".js-machines-product-combo");
      if (!span || !hid || !search) return;
      var id = (hid.value || "").trim();
      if (id) {
        var nm = nameById(id);
        if (!nm) {
          var keep = (span.textContent || "").trim();
          if (!keep) keep = (cell.getAttribute("data-original-label") || "").trim();
          nm = keep || id;
        }
        span.textContent = nm;
        search.value = nm;
        cell.classList.remove("is-empty");
      } else {
        var orig = (cell.getAttribute("data-original-label") || "").trim();
        span.textContent = orig;
        search.value = "";
        if (!orig) cell.classList.add("is-empty");
        else cell.classList.remove("is-empty");
      }
      if (combo) combo.classList.remove("is-open");
      var panel = cell.querySelector(".machines-product-suggest");
      if (panel) panel.hidden = true;
      var hidVal = (hid.value || "").trim();
      if (hidVal) {
        setQuickFieldProductRef(cell, hidVal);
      } else {
        clearQuickFieldProductRef(cell);
      }
      syncScheduleSetupUi(cell);
    }

    // ─── Цветовой пикер ──────────────────────────────────────────────

    function ensureColorPickerPopInBody() {
      var pop = document.getElementById("machines-color-picker-pop");
      if (pop && pop.parentNode !== document.body) {
        document.body.appendChild(pop);
      }
      return pop;
    }

    function bindColorPickerPopEvents() {
      var pop = ensureColorPickerPopInBody();
      if (!pop || pop.dataset.eventsBound) return;
      pop.dataset.eventsBound = "1";
      pop.addEventListener("mouseover", function (e) {
        var pick = e.target.closest(".js-machines-color-pick");
        if (!pick || !colorPickerTarget) return;
        var row = colorPickerTarget.closest(".machines-schedule-row");
        if (row) {
          applyColorToRow(row, pick.dataset.color || "");
          syncScheduleColorsToQuickRows();
        }
      });
      pop.addEventListener("mouseleave", function () {
        if (!colorPickerTarget) return;
        var row = colorPickerTarget.closest(".machines-schedule-row");
        if (row) {
          applyColorToRow(row, colorPickerTarget.dataset.color || "");
          syncScheduleColorsToQuickRows();
        }
      });
    }

    function buildColorPickerPop() {
      var pop = ensureColorPickerPopInBody();
      if (!pop || pop.dataset.built) return;
      pop.dataset.built = "1";
      var clearRow = document.createElement("div");
      var clearBtn = document.createElement("button");
      clearBtn.type = "button";
      clearBtn.className = "machines-color-picker-pop__clear-btn js-machines-color-pick";
      clearBtn.dataset.color = "";
      clearBtn.textContent = "✕  Без цвета";
      clearRow.appendChild(clearBtn);
      pop.appendChild(clearRow);
      var row1 = document.createElement("div");
      row1.className = "machines-color-picker-pop__row";
      var row2 = document.createElement("div");
      row2.className = "machines-color-picker-pop__row";
      for (var i = 0; i < 8; i++) {
        [row1, row2].forEach(function (rowEl, ri) {
          var btn = document.createElement("button");
          btn.type = "button";
          btn.className = "machines-color-picker-pop__swatch js-machines-color-pick";
          btn.dataset.color = COLOR_PALETTE[ri * 8 + i];
          btn.style.background = COLOR_PALETTE[ri * 8 + i];
          btn.title = COLOR_PALETTE[ri * 8 + i];
          rowEl.appendChild(btn);
        });
      }
      pop.appendChild(row1);
      pop.appendChild(row2);
      bindColorPickerPopEvents();
    }

    function openColorPicker(triggerBtn) {
      buildColorPickerPop();
      var pop = ensureColorPickerPopInBody();
      if (!pop || !triggerBtn) return;
      colorPickerTarget = triggerBtn;
      pop.hidden = false;
      pop.style.visibility = "hidden";
      pop.style.top = "0px";
      pop.style.left = "0px";
      requestAnimationFrame(function () {
        if (!colorPickerTarget || pop.hidden) return;
        var rect = colorPickerTarget.getBoundingClientRect();
        var popW = pop.offsetWidth || 200;
        var popH = pop.offsetHeight || 90;
        var top = rect.bottom + 4;
        var left = rect.left;
        if (left + popW > window.innerWidth - 8) left = rect.right - popW;
        if (top + popH > window.innerHeight - 8) top = rect.top - popH - 4;
        if (left < 4) left = 4;
        pop.style.top = top + "px";
        pop.style.left = left + "px";
        pop.style.visibility = "";
        var cur = (colorPickerTarget.dataset.color || "").toLowerCase();
        pop.querySelectorAll(".js-machines-color-pick").forEach(function (b) {
          b.classList.toggle("is-selected", (b.dataset.color || "").toLowerCase() === cur);
        });
      });
    }

    function closeColorPicker() {
      var pop = document.getElementById("machines-color-picker-pop");
      if (pop) pop.hidden = true;
      colorPickerTarget = null;
    }

    function persistScheduleColorChange() {
      saveScheduleClientRows();
      syncScheduleColorsToQuickRows();
    }

    function applyColorToRow(row, color) {
      var colorCell = row.querySelector(".machines-cell--schedule-color");
      var triggerBtn = colorCell ? colorCell.querySelector(".js-machines-color-trigger") : null;
      if (triggerBtn) {
        triggerBtn.dataset.color = color || "";
        triggerBtn.style.background = color || "";
      }
      if (color) {
        row.style.setProperty("--srow-bg", color);
        row.setAttribute("data-row-color", "1");
      } else {
        row.style.removeProperty("--srow-bg");
        row.removeAttribute("data-row-color");
      }
    }

    function syncScheduleColorsToQuickRows() {
      // Строим карту product_id → color из строк плана
      var colorMap = {};
      scheduleWrap.querySelectorAll(".machines-schedule-row").forEach(function (row) {
        var labelCell = row.querySelector(".machines-cell--schedule-label");
        var triggerBtn = row.querySelector(".js-machines-color-trigger");
        if (!labelCell || !triggerBtn) return;
        var hid = labelCell.querySelector(".js-machines-product-id");
        var pid = hid ? (hid.value || "").trim() : "";
        var color = (triggerBtn.dataset.color || "").trim();
        if (pid && color) colorMap[pid] = color;
      });
      // Применяем к ячейкам станков
      quickWrap.querySelectorAll(".machines-quick-row").forEach(function (row) {
        row.querySelectorAll(".machines-cell--field:not(.machines-cell--notes)").forEach(function (cell) {
          var pid = (cell.getAttribute("data-preview-product-id") || "").trim();
          if (pid && colorMap[pid]) {
            cell.style.setProperty("--product-bg", colorMap[pid]);
            cell.setAttribute("data-product-color", "1");
          } else {
            cell.style.removeProperty("--product-bg");
            cell.removeAttribute("data-product-color");
          }
        });
      });
    }

    function normalizeScheduleSortCell(cell) {
      if (!cell) return;
      var t = (cell.textContent || "").replace(/\u200b/g, "").trim();
      cell.textContent = t;
      if (t) cell.classList.remove("is-empty");
      else cell.classList.add("is-empty");
    }

    function parseSchedulePriorityValue(text) {
      var t = (text || "").trim();
      if (!t) return Number.POSITIVE_INFINITY;
      var n = parseInt(t, 10);
      return isNaN(n) ? Number.POSITIVE_INFINITY : n;
    }

    function parseScheduleQtyValue(text) {
      var t = (text || "").trim();
      if (!t) return 0;
      var n = parseInt(t, 10);
      return isNaN(n) ? 0 : n;
    }

    function prepareScheduleRowsForSave() {
      if (!scheduleWrap) return;
      var ae = document.activeElement;
      if (ae && scheduleWrap.contains(ae)) {
        var activeSortCell = ae.closest(".machines-cell--schedule-priority, .machines-cell--schedule-qty");
        if (activeSortCell) {
          normalizeScheduleSortCell(activeSortCell);
          try {
            ae.blur();
          } catch (eBlurSort) {}
        }
      }
      scheduleWrap.querySelectorAll(".machines-cell--schedule-priority, .machines-cell--schedule-qty").forEach(function (cell) {
        normalizeScheduleSortCell(cell);
      });
      sortScheduleRowsByPriorityQty();
    }

    function sortScheduleRowsByPriorityQty() {
      if (!scheduleWrap) return;
      var rows = Array.prototype.slice.call(scheduleWrap.querySelectorAll(".machines-schedule-row"));
      rows.sort(function (a, b) {
        var priA = a.querySelector(".machines-cell--schedule-priority");
        var priB = b.querySelector(".machines-cell--schedule-priority");
        var pa = parseSchedulePriorityValue(priA ? priA.textContent : "");
        var pb = parseSchedulePriorityValue(priB ? priB.textContent : "");
        if (pa !== pb) return pa - pb;
        var qtyA = a.querySelector(".machines-cell--schedule-qty");
        var qtyB = b.querySelector(".machines-cell--schedule-qty");
        return parseScheduleQtyValue(qtyB ? qtyB.textContent : "") - parseScheduleQtyValue(qtyA ? qtyA.textContent : "");
      });
      rows.forEach(function (row) {
        scheduleWrap.appendChild(row);
      });
    }

    // ─────────────────────────────────────────────────────────────────

    function persistAllProducts() {
      var map = readStore();
      root.querySelectorAll(".machines-cell--schedule-label").forEach(function (cell) {
        var idx = cell.getAttribute("data-schedule-index");
        if (idx === null || idx === undefined || idx === "") return;
        var hid = cell.querySelector(".js-machines-product-id");
        if (!hid) return;
        map[idx] = (hid.value || "").trim();
      });
      writeStore(map);
    }

    function applyStoredSelections() {
      var map = readStore();
      root.querySelectorAll(".machines-cell--schedule-label").forEach(function (cell) {
        var idx = cell.getAttribute("data-schedule-index");
        if (idx === null || idx === undefined || idx === "" || !Object.prototype.hasOwnProperty.call(map, idx)) return;
        var raw = map[idx];
        var hid = cell.querySelector(".js-machines-product-id");
        if (!hid) return;
        var want = raw === "" || raw === null ? "" : String(raw);
        if (want && !catalogHasId(want)) {
          delete map[idx];
          writeStore(map);
          syncProductComboDisplay(cell);
          return;
        }
        hid.value = want;
        syncProductComboDisplay(cell);
      });
    }

    function syncScheduleCodeVisibility() {
      var quickRows = quickWrap ? quickWrap.querySelectorAll(".machines-quick-row") : [];
      var machineMap = {};
      quickRows.forEach(function (qrow) {
        var cells = qrow.querySelectorAll(":scope > .machines-cell");
        if (cells.length < 3) return;
        var code = (cells[0].textContent || "").trim();
        if (!code) return;
        var codeCell = cells[0];
        var hue = codeCell.style.getPropertyValue("--mc-hue") || "";
        var pid = (cells[1].getAttribute("data-preview-product-id") || "").trim();
        machineMap[code] = { pid: pid, hue: hue, fieldCell: cells[1] };
      });
      root.querySelectorAll(".machines-quick-row .machines-cell--field:not(.machines-cell--notes)").forEach(function (fc) {
        fc.classList.remove("is-match");
        fc.style.removeProperty("--mc-hue");
      });
      root.querySelectorAll(".machines-cell--schedule-label").forEach(function (lc) {
        lc.classList.remove("is-match");
        lc.style.removeProperty("--mc-hue");
      });
      root.querySelectorAll(".machines-schedule-row").forEach(function (srow) {
        var label = srow.querySelector(".machines-cell--schedule-label");
        var codeCell = srow.querySelector(".machines-cell--schedule-code");
        if (!label || !codeCell) return;
        var mc = (label.getAttribute("data-machine-code") || "").trim();
        var hid = label.querySelector(".js-machines-product-id");
        var schedPid = hid ? (hid.value || "").trim() : "";
        codeCell.classList.remove("is-match");
        codeCell.style.removeProperty("--mc-hue");
        if (!mc || !schedPid) {
          codeCell.textContent = mc;
          return;
        }
        var info = machineMap[mc];
        var workPid = info ? info.pid : "";
        if (workPid === schedPid) {
          codeCell.textContent = mc;
          codeCell.classList.remove("is-empty");
          var hue = info ? info.hue : "";
          if (hue) {
            codeCell.classList.add("is-match");
            codeCell.style.setProperty("--mc-hue", hue);
            label.classList.add("is-match");
            label.style.setProperty("--mc-hue", hue);
            if (info.fieldCell) {
              info.fieldCell.classList.add("is-match");
              info.fieldCell.style.setProperty("--mc-hue", hue);
            }
          }
        } else {
          codeCell.textContent = "";
          codeCell.classList.add("is-empty");
        }
      });
    }

    function serverQuickRows() {
      return Array.prototype.slice.call(quickWrap.querySelectorAll(".machines-quick-row")).filter(function (r) {
        return r.getAttribute("data-client-row") !== "1";
      });
    }

    function normalizeQuickEditableCell(cell) {
      if (!cell) return;
      var isNotes = cell.classList.contains("machines-cell--notes");
      if (!isNotes && !isQuickEditableCellActive(cell)) return;
      ensureQuickProductViewSpan(cell);
      var inner = quickFieldEditableInner(cell) || cell.querySelector(".machines-quick-field-view");
      var raw;
      if (cell.classList.contains("machines-cell--notes")) {
        ensureQuickNotesBody(cell);
        var notesBodyNorm = cell.querySelector(":scope > .machines-quick-notes-body");
        raw = notesBodyNorm
          ? (notesBodyNorm.textContent || "").replace(/\u200b/g, "")
          : (cell.textContent || "").replace(/\u200b/g, "");
      } else if (inner && cell.classList.contains("machines-cell--field")) {
        raw = sanitizeQuickProductText(getQuickFieldFlatText(inner)).replace(/\u200b/g, "");
      } else {
        raw = (cell.textContent || "").replace(/\u200b/g, "");
      }
      var t;
      if (cell.classList.contains("machines-cell--notes")) {
        t = raw.replace(/\r\n/g, "\n").replace(/\r/g, "\n").trim();
      } else {
        t = sanitizeQuickProductText(raw.replace(/\r\n|\r|\n/g, " ").trim());
        if (cell.classList.contains("machines-cell--code")) {
          t = t.replace(/\s+/g, " ");
        }
      }
      if (inner && !cell.classList.contains("machines-cell--notes")) {
        fillQuickFieldViewTwoParts(inner, t);
      } else if (cell.classList.contains("machines-cell--notes")) {
        var notesBodySet = cell.querySelector(":scope > .machines-quick-notes-body");
        if (notesBodySet) notesBodySet.textContent = t;
        else cell.textContent = t;
      } else {
        cell.textContent = t;
      }
      if (t) cell.classList.remove("is-empty");
      else cell.classList.add("is-empty");
    }

    function syncQuickEditability(on) {
      quickWrap.querySelectorAll(".machines-quick-row > .machines-cell").forEach(function (cell) {
        if (cell.classList.contains("machines-cell--notes")) {
          var notesBody = ensureQuickNotesBody(cell);
          cell.removeAttribute("contenteditable");
          cell.removeAttribute("spellcheck");
          if (on && notesBody) {
            notesBody.setAttribute("contenteditable", "true");
            notesBody.setAttribute("spellcheck", "false");
          } else {
            if (!on) normalizeQuickEditableCell(cell);
            if (notesBody) {
              notesBody.removeAttribute("contenteditable");
              notesBody.removeAttribute("spellcheck");
            }
          }
          return;
        }
        if (on) {
          if (cell.classList.contains("machines-cell--field") && !cell.classList.contains("machines-cell--notes")) {
            cell.removeAttribute("contenteditable");
            cell.removeAttribute("spellcheck");
            var innerOn = quickFieldEditableInner(cell) || cell.querySelector(".machines-quick-field-view");
            if (innerOn) {
              collapseQuickFieldViewForEdit(innerOn);
            }
            var andSetup = cell.querySelector(".machines-quick-field-and-setup");
            if (andSetup) andSetup.setAttribute("contenteditable", "false");
            if (innerOn) {
              innerOn.setAttribute("contenteditable", "true");
              innerOn.setAttribute("spellcheck", "false");
            }
          } else {
            cell.setAttribute("contenteditable", "true");
            cell.setAttribute("spellcheck", "false");
          }
        } else {
          normalizeQuickEditableCell(cell);
          syncQuickFieldProductRefAfterBlur(cell);
          cell.removeAttribute("contenteditable");
          cell.removeAttribute("spellcheck");
          var andSetupOff = cell.querySelector(".machines-quick-field-and-setup");
          if (andSetupOff) andSetupOff.removeAttribute("contenteditable");
          var innerOff = cell.querySelector(".machines-quick-field-view");
          if (innerOff) innerOff.removeAttribute("contenteditable");
        }
      });
    }

    function syncScheduleProductInteractions(on) {
      var en = !!on;
      scheduleWrap.querySelectorAll(".machines-cell--schedule-qty").forEach(function (cell) {
        if (en) {
          cell.setAttribute("contenteditable", "true");
          cell.setAttribute("spellcheck", "false");
        } else {
          cell.removeAttribute("contenteditable");
          cell.removeAttribute("spellcheck");
        }
      });
      scheduleWrap.querySelectorAll(".machines-cell--schedule-priority").forEach(function (cell) {
        if (en) {
          cell.setAttribute("contenteditable", "true");
          cell.setAttribute("spellcheck", "false");
        } else {
          cell.removeAttribute("contenteditable");
          cell.removeAttribute("spellcheck");
        }
      });
      // color-cell управляется через пикер, contenteditable не нужен
      root.querySelectorAll(".js-machines-product-search").forEach(function (inp) {
        inp.disabled = !en;
        inp.setAttribute("aria-disabled", en ? "false" : "true");
      });
      if (btnAddQuick) {
        btnAddQuick.disabled = !en;
        btnAddQuick.setAttribute("aria-disabled", en ? "false" : "true");
      }
      if (btnAddSchedule) {
        btnAddSchedule.disabled = !en;
        btnAddSchedule.setAttribute("aria-disabled", en ? "false" : "true");
      }
      root.querySelectorAll(".js-machines-quick-setup-select").forEach(function (qsel) {
        qsel.disabled = true;
        qsel.setAttribute("aria-disabled", "true");
      });
      if (en && canQuickEdit) {
        syncAllQuickFieldSetupSelects();
      }
    }

    function persistQuickServerRows() {
      var expect = parseInt(quickWrap.getAttribute("data-server-quick-count") || "0", 10);
      var srv = serverQuickRows();
      if (isNaN(expect) || srv.length !== expect) return;
      var list = srv.map(function (row) {
        var cells = row.querySelectorAll(":scope > .machines-cell");
        if (cells.length < 4) return { c: "", n: "", e: "", x: "", t: "", cp: "", ep: "", cs: "", es: "" };
        return {
          c: (cells[0].textContent || "").trim(),
          n: readQuickProductSlotPlainText(cells[1]),
          e: readQuickProductSlotPlainText(cells[2]),
          x: readQuickNotesText(cells[3]),
          t: "Т",
          cp: readQuickFieldProductPidAttr(cells[1]),
          ep: readQuickFieldProductPidAttr(cells[2]),
          cs: readQuickFieldSetupIdAttr(cells[1]),
          es: readQuickFieldSetupIdAttr(cells[2])
        };
      });
      writeJson(LS_QUICK_SERVER, list);
    }

    function restoreQuickServerOverrides() {
      var expect = parseInt(quickWrap.getAttribute("data-server-quick-count") || "0", 10);
      var stored = readJson(LS_QUICK_SERVER, null);
      if (!Array.isArray(stored) || stored.length !== expect) return;
      var srv = serverQuickRows();
      if (srv.length !== expect) return;
      srv.forEach(function (row, i) {
        var r = stored[i];
        if (!r || typeof r !== "object") return;
        var cells = row.querySelectorAll(":scope > .machines-cell");
        if (cells.length < 4) return;
        setQuickCellText(cells[0], r.c, { skipClearProductRef: true });
        setQuickCellText(cells[1], r.n, { skipClearProductRef: true });
        setQuickCellText(cells[2], r.e, { skipClearProductRef: true });
        setQuickCellText(cells[3], r.x, { skipClearProductRef: true });
        if ((r.cs || "").trim()) cells[1].setAttribute("data-current-setup-id", String(r.cs).trim());
        if ((r.cp || "").trim()) setQuickFieldProductRef(cells[1], String(r.cp).trim());
        else clearQuickFieldProductRef(cells[1]);
        if ((r.es || "").trim()) cells[2].setAttribute("data-current-setup-id", String(r.es).trim());
        if ((r.ep || "").trim()) setQuickFieldProductRef(cells[2], String(r.ep).trim());
        else clearQuickFieldProductRef(cells[2]);
      });
    }

    async function setEditMode(on) {
      if (!on) {
        prepareScheduleRowsForSave();
        if (canQuickEdit) {
          var okSave = await postMachinesBoardToServer();
          if (!okSave) return;
        }
      }
      root.setAttribute("data-inline-edit-mode", on ? "1" : "0");
      if (on) {
        hideQuickPreview();
      }
      if (toggleBtn) {
        toggleBtn.setAttribute("aria-pressed", on ? "true" : "false");
        toggleBtn.textContent = on ? "Сохранить" : "Быстрое редактирование";
      }
      closeSuggestExcept(null);
      if (!on) {
        var aeCombo = document.activeElement;
        if (aeCombo && aeCombo.closest && aeCombo.closest(".js-machines-product-combo")) {
          try {
            aeCombo.blur();
          } catch (eBlur) {}
        }
      }
      syncScheduleProductInteractions(on);
      syncQuickEditability(on);
      syncScheduleDragHandles(on);
      if (!on) {
        root.querySelectorAll(".machines-cell--schedule-label").forEach(syncProductComboDisplay);
        persistAllProducts();
        persistScheduleMachineCodes();
        persistQuickServerRows();
        saveQuickClientRows();
        syncMachineCodeAppearance();
      } else {
        root.querySelectorAll(".machines-cell--schedule-label").forEach(syncProductComboDisplay);
      }
      if (on) {
        pushPageHistory("Включено быстрое редактирование страницы «Станки».");
      } else {
        pushPageHistory(
          canQuickEdit
            ? "Выключено быстрое редактирование; сводка сохранена на сервере."
            : "Выключено быстрое редактирование."
        );
      }
    }

    if (toggleBtn && canQuickEdit) {
      toggleBtn.addEventListener("click", async function () {
        var on = root.getAttribute("data-inline-edit-mode") !== "1";
        await setEditMode(on);
      });
    }

    if (btnHistory && historyBackdrop && historyPanel) {
      btnHistory.addEventListener("click", function () {
        if (historyPanel.hidden) openHistoryPanel();
        else closeHistoryPanel();
      });
      historyBackdrop.addEventListener("click", closeHistoryPanel);
      var histCloseBtn = historyPanel.querySelector(".js-machines-history-close");
      if (histCloseBtn) histCloseBtn.addEventListener("click", closeHistoryPanel);
    }
    document.addEventListener("keydown", onHistoryEscape);

    quickWrap.addEventListener("click", function (e) {
      var btn = e.target.closest(".js-machines-quick-row-delete");
      if (!btn || root.getAttribute("data-inline-edit-mode") !== "1") return;
      e.stopPropagation();
      var row = btn.closest(".machines-quick-row");
      if (!row) return;
      row.remove();
      saveQuickClientRows();
    });

    quickWrap.addEventListener("click", function (e) {
      var btn = e.target.closest(".js-machines-cell-clear");
      if (!btn || root.getAttribute("data-inline-edit-mode") !== "1") return;
      var cell = btn.closest(".machines-cell--field");
      if (!cell) return;
      setQuickCellText(cell, "");
      clearQuickFieldProductRef(cell);
      syncQuickFieldSetupSelect(cell);
      syncScheduleCodeVisibility();
    });

    scheduleWrap.addEventListener("click", function (e) {
      // Удаление строки
      var delBtn = e.target.closest(".js-machines-schedule-row-delete");
      if (delBtn && root.getAttribute("data-inline-edit-mode") === "1") {
        e.stopPropagation();
        var row = delBtn.closest(".machines-schedule-row");
        if (row) {
          var labelCell = row.querySelector(".machines-cell--schedule-label");
          if (labelCell) {
            var idx = labelCell.getAttribute("data-schedule-index");
            if (idx !== null && idx !== "") { var map = readStore(); delete map[idx]; writeStore(map); }
          }
          row.remove();
          saveScheduleClientRows();
          syncScheduleColorsToQuickRows();
        }
        return;
      }
      // Открытие цветового пикера
      var colorTrigger = e.target.closest(".js-machines-color-trigger");
      if (colorTrigger && root.getAttribute("data-inline-edit-mode") === "1") {
        e.preventDefault();
        e.stopPropagation();
        if (colorPickerTarget === colorTrigger) {
          var popEl = document.getElementById("machines-color-picker-pop");
          if (popEl && !popEl.hidden) {
            closeColorPicker();
            return;
          }
        }
        openColorPicker(colorTrigger);
        return;
      }
    });

    scheduleWrap.addEventListener("pointerdown", function (e) {
      var colorTrigger = e.target.closest(".js-machines-color-trigger");
      if (!colorTrigger || root.getAttribute("data-inline-edit-mode") !== "1") return;
      if (e.target.closest(".js-machines-schedule-row-delete")) return;
      e.stopPropagation();
    });

    scheduleWrap.addEventListener(
      "blur",
      function (e) {
        var cell = e.target.closest(".machines-cell--schedule-priority, .machines-cell--schedule-qty");
        if (!cell || !scheduleWrap.contains(cell)) return;
        normalizeScheduleSortCell(cell);
        saveScheduleClientRows();
      },
      true
    );

    // Выбор цвета из пикера
    document.addEventListener("mousedown", function (e) {
      var pop = document.getElementById("machines-color-picker-pop");
      if (!pop || pop.hidden) return;
      var pick = e.target.closest(".js-machines-color-pick");
      if (pick && pop.contains(pick)) {
        e.preventDefault();
        var color = pick.dataset.color || "";
        if (colorPickerTarget) {
          var row = colorPickerTarget.closest(".machines-schedule-row");
          if (row) {
            applyColorToRow(row, color);
            persistScheduleColorChange();
          }
        }
        closeColorPicker();
        return;
      }
      // Клик вне пикера — закрыть
      if (!pop.contains(e.target) && !e.target.closest(".js-machines-color-trigger")) {
        closeColorPicker();
      }
    });

    scheduleWrap.addEventListener("dragstart", function (e) {
      var handle = e.target.closest(".machines-schedule-drag-handle");
      if (!handle || !scheduleWrap.contains(handle)) return;
      if (root.getAttribute("data-inline-edit-mode") !== "1") {
        e.preventDefault();
        return;
      }
      var cell = handle.closest(".machines-cell--schedule-label");
      if (!cell) return;
      var idx = cell.getAttribute("data-schedule-index");
      if (idx === null || idx === undefined || idx === "") return;
      var hid = cell.querySelector(".js-machines-product-id");
      var pid = hid && (hid.value || "").trim() ? String(hid.value).trim() : "";
      var display = scheduleLabelDisplayText(cell);
      var payload = { scheduleIndex: String(idx), productId: pid, display: display };
      try {
        e.dataTransfer.setData(MIME_SCHEDULE_DRAG, JSON.stringify(payload));
        e.dataTransfer.setData("text/plain", display);
      } catch (err2) {}
      e.dataTransfer.effectAllowed = "copy";
    });

    scheduleWrap.addEventListener("dragend", function () {
      clearScheduleDropHover();
    });

    quickWrap.addEventListener("dragenter", function (e) {
      if (root.getAttribute("data-inline-edit-mode") !== "1") return;
      if (!dataTransferHasScheduleDrag(e.dataTransfer)) return;
      var fieldEnter = e.target.closest(".machines-quick-row > .machines-cell--field:not(.machines-cell--notes)");
      if (!fieldEnter || !quickWrap.contains(fieldEnter)) return;
      e.preventDefault();
    });

    quickWrap.addEventListener("dragover", function (e) {
      if (root.getAttribute("data-inline-edit-mode") !== "1") return;
      if (!dataTransferHasScheduleDrag(e.dataTransfer)) return;
      var field = e.target.closest(".machines-quick-row > .machines-cell--field:not(.machines-cell--notes)");
      if (!field || !quickWrap.contains(field)) {
        clearScheduleDropHover();
        return;
      }
      e.preventDefault();
      e.dataTransfer.dropEffect = "copy";
      if (scheduleDragHoverField !== field) {
        clearScheduleDropHover();
        scheduleDragHoverField = field;
        field.classList.add("machines-drop-target");
      }
    });

    quickWrap.addEventListener("dragleave", function (e) {
      var field = e.target.closest(".machines-quick-row > .machines-cell--field:not(.machines-cell--notes)");
      if (!field || !quickWrap.contains(field)) return;
      var rel = e.relatedTarget;
      if (rel && field.contains(rel)) return;
      if (scheduleDragHoverField === field) {
        field.classList.remove("machines-drop-target");
        scheduleDragHoverField = null;
      }
    });

    quickWrap.addEventListener("drop", function (e) {
      if (root.getAttribute("data-inline-edit-mode") !== "1") return;
      var field = e.target.closest(".machines-quick-row > .machines-cell--field:not(.machines-cell--notes)");
      if (!field || !quickWrap.contains(field)) return;
      var raw = "";
      try {
        raw = e.dataTransfer.getData(MIME_SCHEDULE_DRAG);
      } catch (err3) {}
      if (!raw) {
        e.preventDefault();
        return;
      }
      var payload = null;
      try {
        payload = JSON.parse(raw);
      } catch (err4) {
        e.preventDefault();
        return;
      }
      if (!payload || payload.scheduleIndex === undefined || payload.scheduleIndex === null) {
        e.preventDefault();
        return;
      }
      e.preventDefault();
      clearScheduleDropHover();
      var display = (payload.display != null && String(payload.display).trim()) || "";
      if (!display && payload.productId) display = nameById(String(payload.productId)) || "";
      var qrow = field.closest(".machines-quick-row");
      if (!qrow) return;
      var qcells = qrow.querySelectorAll(":scope > .machines-cell");
      if (qcells.length < 4) return;
      var machineCode = (qcells[0].textContent || "").trim();
      machineCode = machineCode.replace(/\r\n|\r|\n/g, " ").replace(/\s+/g, " ").trim();
      setQuickCellText(field, display);
      if (payload.productId) {
        setQuickFieldProductRef(field, String(payload.productId));
      } else {
        clearQuickFieldProductRef(field);
      }
      if (field.getAttribute("contenteditable") === "true") {
        normalizeQuickEditableCell(field);
      }
      var schLabel = scheduleWrap.querySelector(
        '.machines-cell--schedule-label[data-schedule-index="' + String(payload.scheduleIndex) + '"]'
      );
      if (!schLabel) return;
      var schRow = schLabel.closest(".machines-schedule-row");
      var codeEl = schRow && schRow.querySelector(".machines-cell--schedule-code");
      if (codeEl) {
        codeEl.textContent = machineCode;
        schLabel.setAttribute("data-machine-code", machineCode);
        if (machineCode) {
          codeEl.classList.remove("is-empty");
        } else {
          codeEl.classList.add("is-empty");
        }
      }
      persistAllProducts();
      persistScheduleMachineCodes();
      persistQuickServerRows();
      saveQuickClientRows();
      syncMachineCodeAppearance();
      syncScheduleCodeVisibility();
      var fieldLabel = "ячейка";
      if (field === qcells[1]) fieldLabel = "«Сейчас»";
      else if (field === qcells[2]) fieldLabel = "«Далее»";
      else if (field === qcells[0]) fieldLabel = "«Код станка»";
      var si = parseInt(String(payload.scheduleIndex), 10);
      if (isNaN(si)) si = 0;
      pushPageHistory(
        "Из плана (строка №" +
          String(si + 1) +
          ") перенесено на станок " +
          machineCode +
          ", поле " +
          fieldLabel +
          ": «" +
          (display || "—") +
          "»."
      );
    });

    root.addEventListener("mouseover", function (e) {
      var sl = e.target.closest(".machines-cell--schedule-label");
      if (sl && scheduleWrap.contains(sl)) {
        var pSched = (sl.getAttribute("data-preview-product-id") || "").trim();
        if (pSched) {
          showQuickPreviewForPid(pSched, e.clientX, e.clientY);
        } else {
          hideQuickPreview();
        }
        return;
      }
      var fld = e.target.closest(".machines-quick-row > .machines-cell--field:not(.machines-cell--notes)");
      if (fld && quickWrap.contains(fld)) {
        var pQuick = readQuickFieldProductPidAttr(fld);
        if (pQuick) {
          showQuickPreviewForPid(pQuick, e.clientX, e.clientY);
        } else {
          hideQuickPreview();
        }
        return;
      }
      hideQuickPreview();
    });

    root.addEventListener("mousemove", function (e) {
      if (!previewPop || previewPop.hidden) return;
      positionQuickPreviewPop(e.clientX, e.clientY);
    });

    root.addEventListener("mouseleave", function (e) {
      if (e.relatedTarget && root.contains(e.relatedTarget)) return;
      hideQuickPreview();
    });

    root.addEventListener("click", function (e) {
      if (maybeOpenQuickSetupFromClick(e)) return;
      if (root.getAttribute("data-inline-edit-mode") === "1") return;
      if (e.button !== 0) return;
      if (e.target.closest(".js-machines-quick-setup-select")) return;
      var linkEl = e.target.closest("[data-product-href]");
      if (!linkEl || !root.contains(linkEl)) return;
      var href = (linkEl.getAttribute("data-product-href") || "").trim();
      if (!href) return;
      var ok = false;
      if (scheduleWrap.contains(linkEl) && linkEl.classList.contains("machines-cell--schedule-label")) {
        ok = true;
      } else if (quickWrap.contains(linkEl)) {
        if (linkEl.classList.contains("machines-quick-field-view")) ok = true;
        else if (linkEl.classList.contains("machines-cell--field") && !linkEl.classList.contains("machines-cell--notes")) {
          ok = true;
        }
      }
      if (!ok) return;
      e.preventDefault();
      if (e.ctrlKey || e.metaKey) {
        window.open(href, "_blank", "noopener,noreferrer");
      } else {
        window.location.href = href;
      }
    });

    function renderSuggestPanel(combo, query) {
      var panel = combo.querySelector(".machines-product-suggest");
      if (!panel) return;
      var cat = getCatalog();
      var q = (query || "").trim().toLowerCase();
      var max = 200;
      var hits = [];
      if (!q) {
        hits = cat.slice(0, max);
      } else {
        for (var i = 0; i < cat.length && hits.length < max; i++) {
          var p = cat[i];
          var nm = (p.name || "").toLowerCase();
          var idStr = String(p.id);
          if (nm.indexOf(q) !== -1 || idStr.indexOf(q) !== -1) hits.push(p);
        }
      }
      panel.textContent = "";
      var clearBtn = document.createElement("button");
      clearBtn.type = "button";
      clearBtn.className = "machines-product-suggest-item machines-product-suggest-clear";
      clearBtn.setAttribute("role", "option");
      clearBtn.dataset.productId = "";
      clearBtn.textContent = "— не выбрано";
      panel.appendChild(clearBtn);
      hits.forEach(function (p) {
        var b = document.createElement("button");
        b.type = "button";
        b.className = "machines-product-suggest-item";
        b.setAttribute("role", "option");
        b.dataset.productId = String(p.id);
        b.textContent = p.name || "";
        panel.appendChild(b);
      });
      if (hits.length === 0 && q) {
        var empty = document.createElement("div");
        empty.className = "machines-product-suggest-empty muted";
        empty.textContent = "Ничего не найдено";
        panel.appendChild(empty);
      }
      panel.hidden = false;
      panel.classList.remove("opens-up");
      // Определяем, нужно ли открыть дропдаун вверх
      var searchEl = combo.querySelector(".js-machines-product-search");
      if (searchEl) {
        var searchRect = searchEl.getBoundingClientRect();
        var panelHeight = panel.offsetHeight || 240;
        if (searchRect.bottom + panelHeight + 4 > window.innerHeight - 8) {
          panel.classList.add("opens-up");
        }
      } else {
        var rect = panel.getBoundingClientRect();
        if (rect.bottom > window.innerHeight - 8) {
          panel.classList.add("opens-up");
        }
      }
      combo.classList.add("is-open");
      var schRow = combo.closest(".machines-schedule-row");
      if (schRow) schRow.classList.add("machines-schedule-row--suggest-open");
    }

    root.addEventListener("input", function (e) {
      var search = e.target.closest(".js-machines-product-search");
      if (!search) return;
      if (root.getAttribute("data-inline-edit-mode") !== "1") return;
      var combo = search.closest(".js-machines-product-combo");
      if (!combo) return;
      clearTimeout(suggestTimer);
      suggestTimer = setTimeout(function () {
        renderSuggestPanel(combo, search.value);
      }, 100);
    });

    root.addEventListener("focusin", function (e) {
      var search = e.target.closest(".js-machines-product-search");
      if (!search || root.getAttribute("data-inline-edit-mode") !== "1") return;
      var combo = search.closest(".js-machines-product-combo");
      if (!combo) return;
      closeSuggestExcept(combo);
      renderSuggestPanel(combo, search.value);
    });

    root.addEventListener("mousedown", function (e) {
      var item = e.target.closest("button.machines-product-suggest-item");
      if (!item || !item.closest(".machines-product-suggest")) return;
      if (root.getAttribute("data-inline-edit-mode") !== "1") return;
      e.preventDefault();
      var combo = item.closest(".js-machines-product-combo");
      var cell = combo ? combo.closest(".machines-cell--schedule-label") : null;
      if (!combo || !cell) return;
      var hid = combo.querySelector(".js-machines-product-id");
      var search = combo.querySelector(".js-machines-product-search");
      if (!hid || !search) return;
      var pid = item.getAttribute("data-product-id");
      hid.value = pid != null && pid !== "" ? String(pid) : "";
      if (hid.value) {
        search.value = nameById(hid.value);
      } else {
        search.value = "";
      }
      closeSuggestExcept(null);
      syncProductComboDisplay(cell);
      persistAllProducts();
      syncScheduleCodeVisibility();
      syncScheduleColorsToQuickRows();
      var idxStr = (cell.getAttribute("data-schedule-index") || "").trim();
      var lineNo = "";
      if (idxStr !== "") {
        var ni = parseInt(idxStr, 10);
        if (!isNaN(ni)) lineNo = " (строка плана №" + String(ni + 1) + ")";
      }
      if (hid.value) {
        var nm = (search.value || "").trim() || nameById(hid.value);
        pushPageHistory("План" + lineNo + ": выбрано изделие «" + nm + "».");
      } else {
        pushPageHistory("План" + lineNo + ": сброшен выбор изделия («не выбрано»).");
      }
      try {
        search.focus();
      } catch (err) {}
    });

    root.addEventListener(
      "blur",
      function (e) {
        var search = e.target.closest(".js-machines-product-search");
        if (!search) return;
        if (root.getAttribute("data-inline-edit-mode") !== "1") return;
        var cell = search.closest(".machines-cell--schedule-label");
        if (!cell) return;
        var hid = cell.querySelector(".js-machines-product-id");
        if (!hid) return;
        window.setTimeout(function () {
          var ae = document.activeElement;
          if (ae && ae.closest && ae.closest(".machines-product-suggest")) return;
          if (hid.value) search.value = nameById(hid.value);
          else search.value = "";
        }, 0);
      },
      true
    );

    root.addEventListener("change", function (e) {
      var qsel = e.target.closest(".js-machines-quick-setup-select");
      if (!qsel || !root.contains(qsel)) return;
      if (root.getAttribute("data-inline-edit-mode") !== "1" || !canQuickEdit) return;
      var fieldCell = qsel.closest(".machines-quick-row > .machines-cell--field:not(.machines-cell--notes)");
      if (!fieldCell || !quickWrap.contains(fieldCell)) return;
      var qrow = fieldCell.closest(".machines-quick-row");
      if (!qrow) return;
      var cells = qrow.querySelectorAll(":scope > .machines-cell");
      if (cells.length < 3) return;
      var selectedSetup = (qsel.value || "").trim();
      if (selectedSetup) {
        fieldCell.setAttribute("data-current-setup-id", selectedSetup);
        qsel.setAttribute("data-current-setup-id", selectedSetup);
      } else {
        fieldCell.removeAttribute("data-current-setup-id");
        qsel.removeAttribute("data-current-setup-id");
      }
    });

    document.addEventListener("click", function (e) {
      if (!root || !root.contains(e.target)) return;
      if (e.target.closest(".js-machines-product-combo")) return;
      closeSuggestExcept(null);
    });

    function ensureQuickProductViewSpan(cell) {
      var qrow = cell && cell.closest(".machines-quick-row");
      if (!qrow || !quickWrap.contains(qrow)) return;
      if (!cell.classList.contains("machines-cell--field") || cell.classList.contains("machines-cell--notes")) return;
      var cells = qrow.querySelectorAll(":scope > .machines-cell");
      if (cells.length < 3 || (cell !== cells[1] && cell !== cells[2])) return;
      if (cell.querySelector(".machines-quick-field-view")) return;
      var migrated = (cell.textContent || "").trim();
      var cp = (cell.getAttribute("data-preview-product-id") || "").trim();
      var ch = (cell.getAttribute("data-product-href") || "").trim();
      cell.textContent = "";
      var andSetup = document.createElement("div");
      andSetup.className = "machines-quick-field-and-setup";
      var span = document.createElement("span");
      span.className = "machines-quick-field-view";
      if (cp) span.setAttribute("data-preview-product-id", cp);
      if (ch) span.setAttribute("data-product-href", ch);
      var sku = document.createElement("span");
      sku.className = "machines-quick-field-part machines-quick-field-part--sku";
      var title = document.createElement("span");
      title.className = "machines-quick-field-part machines-quick-field-part--title";
      span.appendChild(sku);
      span.appendChild(title);
      var qsel = document.createElement("select");
      qsel.className = "machines-quick-setup-select js-machines-quick-setup-select";
      qsel.setAttribute("aria-label", "Установка наладки");
      qsel.disabled = true;
      var opt0 = document.createElement("option");
      opt0.value = "";
      opt0.textContent = "—";
      qsel.appendChild(opt0);
      andSetup.appendChild(span);
      andSetup.appendChild(qsel);
      cell.appendChild(andSetup);
      fillQuickFieldViewTwoParts(span, migrated);
      syncQuickFieldSetupSelect(cell);
    }

    function setQuickCellText(cell, text, opts) {
      opts = opts || {};
      var t = (text != null ? String(text) : "").trim();
      if (cell.classList.contains("machines-cell--notes")) {
        ensureQuickNotesBody(cell);
        var notesBody = cell.querySelector(":scope > .machines-quick-notes-body");
        if (notesBody) notesBody.textContent = t;
        if (t) cell.classList.remove("is-empty");
        else cell.classList.add("is-empty");
        return;
      }
      ensureQuickProductViewSpan(cell);
      var inner = cell.querySelector(".machines-quick-field-view");
      if (inner) {
        fillQuickFieldViewTwoParts(inner, t);
      } else {
        cell.textContent = t;
      }
      if (t) cell.classList.remove("is-empty");
      else cell.classList.add("is-empty");
      if (opts.skipClearProductRef) {
        var qrowSkip = cell.closest(".machines-quick-row");
        if (qrowSkip && quickWrap.contains(qrowSkip)) {
          var cSkip = qrowSkip.querySelectorAll(":scope > .machines-cell");
          if (cSkip.length >= 3 && (cell === cSkip[1] || cell === cSkip[2])) {
            syncQuickFieldSetupSelect(cell);
          }
        }
        return;
      }
      if (!cell.classList.contains("machines-cell--field") || cell.classList.contains("machines-cell--notes")) return;
      var qrow = cell.closest(".machines-quick-row");
      if (!qrow) return;
      var cells = qrow.querySelectorAll(":scope > .machines-cell");
      if (cells.length < 4) return;
      if (cell === cells[1] || cell === cells[2]) {
        clearQuickFieldProductRef(cell);
      }
    }

    quickWrap.addEventListener("focusin", function (e) {
      var cell = resolveQuickEditableCell(e.target);
      if (!cell || root.getAttribute("data-inline-edit-mode") !== "1") return;
      var inner = cell.querySelector(".machines-quick-field-view");
      if (inner && !cell.classList.contains("machines-cell--notes")) {
        if ((inner.textContent || "").replace(/\u200b/g, "").length === 0 && inner.childNodes.length === 0) {
          inner.appendChild(document.createTextNode("\u200b"));
        }
        return;
      }
      if (cell.classList.contains("machines-cell--notes")) {
        var notesBodyFocus = cell.querySelector(":scope > .machines-quick-notes-body") || cell;
        if ((notesBodyFocus.textContent || "").replace(/\u200b/g, "").length === 0 && notesBodyFocus.childNodes.length === 0) {
          notesBodyFocus.appendChild(document.createTextNode("\u200b"));
        }
      }
    });

    quickWrap.addEventListener("click", function (e) {
      var btn = e.target.closest(".js-machines-cell-clear");
      if (!btn || root.getAttribute("data-inline-edit-mode") !== "1") return;
      var cell = btn.closest(".machines-cell--field");
      if (!cell) return;
      setQuickCellText(cell, "");
      clearQuickFieldProductRef(cell);
      syncQuickFieldSetupSelect(cell);
      syncScheduleCodeVisibility();
    });

    quickWrap.addEventListener(
      "blur",
      function (e) {
        var cell = resolveQuickEditableCell(e.target);
        if (!cell || !quickWrap.contains(cell)) return;
        normalizeQuickEditableCell(cell);
        syncQuickFieldProductRefAfterBlur(cell);
        var qrow = cell.closest(".machines-quick-row");
        if (qrow) {
          var qcells = qrow.querySelectorAll(":scope > .machines-cell");
          if (qcells.length && cell === qcells[0]) {
            syncMachineCodeAppearance();
          }
        }
        syncScheduleCodeVisibility();
      },
      true
    );

    quickWrap.addEventListener("input", function (e) {
      var cell = resolveQuickEditableCell(e.target);
      if (!cell || root.getAttribute("data-inline-edit-mode") !== "1") return;
      if (cell.classList.contains("machines-cell--notes")) {
        var notesBodyInput = cell.querySelector(":scope > .machines-quick-notes-body") || cell;
        var nraw = notesBodyInput.textContent || "";
        if (nraw.indexOf("\r") !== -1) {
          notesBodyInput.textContent = nraw.replace(/\r\n/g, "\n").replace(/\r/g, "\n");
        }
        var vis = (notesBodyInput.textContent || "").replace(/\u200b/g, "").trim();
        if (vis) cell.classList.remove("is-empty");
        else cell.classList.add("is-empty");
        return;
      }
      var innerInput = quickFieldEditableInner(cell) || cell.querySelector(".machines-quick-field-view");
      var raw = innerInput ? innerInput.textContent || "" : cell.textContent || "";
      if (raw.indexOf("\n") === -1 && raw.indexOf("\r") === -1) return;
      var t = sanitizeQuickProductText(raw.replace(/\r\n|\r|\n/g, " "));
      if (innerInput) {
        if (t !== raw.replace(/\r\n|\r|\n/g, " ")) innerInput.textContent = t;
      } else if (t !== raw.replace(/\r\n|\r|\n/g, " ")) {
        cell.textContent = t;
      }
    });

    quickWrap.addEventListener("paste", function (e) {
      var cell = resolveQuickEditableCell(e.target);
      if (!cell || root.getAttribute("data-inline-edit-mode") !== "1") return;
      e.preventDefault();
      var text = (e.clipboardData && e.clipboardData.getData("text/plain")) || "";
      if (cell.classList.contains("machines-cell--notes")) {
        text = text.replace(/\r\n/g, "\n").replace(/\r/g, "\n");
      } else {
        text = text.replace(/\r\n|\r|\n/g, " ").replace(/\s+/g, " ").trim();
      }
      try {
        document.execCommand("insertText", false, text);
      } catch (err1) {
        var inner = cell.querySelector(".machines-quick-field-view");
        if (inner && !cell.classList.contains("machines-cell--notes")) {
          inner.textContent = ((inner.textContent || "") + text).replace(/\r\n|\r|\n/g, " ");
        } else {
          var notesBodyPaste = cell.querySelector(":scope > .machines-quick-notes-body") || cell;
          notesBodyPaste.textContent = ((notesBodyPaste.textContent || "") + text).replace(/\r\n|\r|\n/g, " ");
        }
      }
    });

    function saveQuickClientRows() {
      var rows = [];
      quickWrap.querySelectorAll('.machines-quick-row[data-client-row="1"]').forEach(function (row) {
        var cells = row.querySelectorAll(":scope > .machines-cell");
        if (cells.length < 4) return;
        rows.push({
          c: (cells[0].textContent || "").trim(),
          n: readQuickProductSlotPlainText(cells[1]),
          e: readQuickProductSlotPlainText(cells[2]),
          x: readQuickNotesText(cells[3]),
          t: "Т",
          cp: readQuickFieldProductPidAttr(cells[1]),
          ep: readQuickFieldProductPidAttr(cells[2]),
          cs: readQuickFieldSetupIdAttr(cells[1]),
          es: readQuickFieldSetupIdAttr(cells[2])
        });
      });
      writeJson(LS_QUICK_EXTRA, rows);
    }

    function restoreQuickClientRows() {
      var rows = readJson(LS_QUICK_EXTRA, []);
      if (!Array.isArray(rows)) return;
      rows.forEach(function (r) {
        var tpl = tplQuick.content.querySelector(".machines-quick-row");
        if (!tpl) return;
        var row = tpl.cloneNode(true);
        var cells = row.querySelectorAll(":scope > .machines-cell");
        if (cells.length < 4) return;
        setQuickCellText(cells[0], r.c, { skipClearProductRef: true });
        setQuickCellText(cells[1], r.n, { skipClearProductRef: true });
        setQuickCellText(cells[2], r.e, { skipClearProductRef: true });
        setQuickCellText(cells[3], r.x, { skipClearProductRef: true });
        if ((r.cs || "").trim()) cells[1].setAttribute("data-current-setup-id", String(r.cs).trim());
        if ((r.cp || "").trim()) setQuickFieldProductRef(cells[1], String(r.cp).trim());
        else clearQuickFieldProductRef(cells[1]);
        if ((r.es || "").trim()) cells[2].setAttribute("data-current-setup-id", String(r.es).trim());
        if ((r.ep || "").trim()) setQuickFieldProductRef(cells[2], String(r.ep).trim());
        else clearQuickFieldProductRef(cells[2]);
        quickWrap.appendChild(row);
      });
    }

    function allocScheduleIndex() {
      var cur = parseInt(scheduleWrap.getAttribute("data-next-schedule-index") || "0", 10);
      if (isNaN(cur)) cur = 0;
      scheduleWrap.setAttribute("data-next-schedule-index", String(cur + 1));
      return cur;
    }

    function fillScheduleRowNode(row, idx, machineCode, origLabel) {
      var labelCell = row.querySelector(".machines-cell--schedule-label");
      var codeCell = row.querySelector(".machines-cell--schedule-code");
      var combo = row.querySelector(".js-machines-product-combo");
      var hid = row.querySelector(".js-machines-product-id");
      var search = row.querySelector(".js-machines-product-search");
      var span = row.querySelector(".machines-schedule-label-view");
      if (!labelCell || !codeCell || !combo || !hid || !search || !span) return;
      labelCell.setAttribute("data-schedule-index", String(idx));
      combo.setAttribute("data-schedule-select", String(idx));
      labelCell.setAttribute("data-machine-code", machineCode || "");
      labelCell.setAttribute("data-original-label", origLabel || "");
      hid.value = "";
      search.value = "";
      span.textContent = "";
      var mc = (machineCode || "").trim();
      codeCell.textContent = mc;
      if (mc) {
        codeCell.classList.remove("is-empty");
      } else {
        codeCell.classList.add("is-empty");
      }
      if ((origLabel || "").trim()) {
        span.textContent = (origLabel || "").trim();
        labelCell.classList.remove("is-empty");
      } else {
        span.textContent = "";
        labelCell.classList.add("is-empty");
      }
      clearQuickFieldProductRef(labelCell);
      var setupHid = labelCell.querySelector(".js-machines-setup-id");
      if (setupHid) setupHid.value = "";
      syncScheduleSetupUi(labelCell);
    }

    function saveScheduleClientRows() {
      var list = [];
      scheduleWrap.querySelectorAll('.machines-schedule-row[data-client-row="1"]').forEach(function (row) {
        var codeEl = row.querySelector(".machines-cell--schedule-code");
        var qtyEl = row.querySelector(".machines-cell--schedule-qty");
        var priorityEl = row.querySelector(".machines-cell--schedule-priority");
        var colorTrigger = row.querySelector(".js-machines-color-trigger");
        list.push({
          machine_code: (codeEl && codeEl.textContent ? codeEl.textContent : "").trim(),
          qty: (qtyEl && qtyEl.textContent ? qtyEl.textContent : "").trim(),
          priority: (priorityEl && priorityEl.textContent ? priorityEl.textContent : "").trim(),
          color: colorTrigger ? (colorTrigger.dataset.color || "").trim() : "",
        });
      });
      writeJson(LS_SCHEDULE_EXTRA, list);
    }

    function restoreScheduleClientRows() {
      var list = readJson(LS_SCHEDULE_EXTRA, []);
      if (!Array.isArray(list)) return;
      list.forEach(function (item) {
        var tpl = tplSchedule.content.querySelector(".machines-schedule-row");
        if (!tpl) return;
        var row = tpl.cloneNode(true);
        var idx = allocScheduleIndex();
        fillScheduleRowNode(row, idx, item.machine_code || "", "");
        var qtyEl = row.querySelector(".machines-cell--schedule-qty");
        if (qtyEl && item.qty) {
          qtyEl.textContent = item.qty;
          qtyEl.classList.remove("is-empty");
        }
        var priorityEl = row.querySelector(".machines-cell--schedule-priority");
        if (priorityEl && item.priority) {
          priorityEl.textContent = item.priority;
          priorityEl.classList.remove("is-empty");
        }
        if (item.color) applyColorToRow(row, item.color);
        scheduleWrap.appendChild(row);
      });
    }

    function addQuickRow() {
      if (root.getAttribute("data-inline-edit-mode") !== "1") return;
      var tpl = tplQuick.content.querySelector(".machines-quick-row");
      if (!tpl) return;
      var row = tpl.cloneNode(true);
      quickWrap.appendChild(row);
      syncQuickEditability(root.getAttribute("data-inline-edit-mode") === "1");
      saveQuickClientRows();
      pushPageHistory("Добавлена новая строка станка (пустая).");
    }

    function addScheduleRow() {
      if (root.getAttribute("data-inline-edit-mode") !== "1") return;
      var tpl = tplSchedule.content.querySelector(".machines-schedule-row");
      if (!tpl) return;
      var row = tpl.cloneNode(true);
      var idx = allocScheduleIndex();
      fillScheduleRowNode(row, idx, "", "");
      // Удаляем возможный устаревший продукт по этому idx из localStorage
      var map = readStore();
      if (Object.prototype.hasOwnProperty.call(map, String(idx))) {
        delete map[String(idx)];
        writeStore(map);
      }
      scheduleWrap.appendChild(row);
      saveScheduleClientRows();
      applyStoredSelections();
      pushPageHistory("Добавлена новая строка плана работ.");
    }

    if (btnAddQuick) btnAddQuick.addEventListener("click", addQuickRow);
    if (btnAddSchedule) btnAddSchedule.addEventListener("click", addScheduleRow);

    (function syncMachinesContentVersion() {
      var ver = (root.getAttribute("data-machines-content-version") || "0").trim();
      var prev = null;
      try {
        prev = localStorage.getItem(LS_CONTENT_VER);
      } catch (e0) {}
      if (prev !== ver) {
        try {
          localStorage.removeItem(LS_QUICK_SERVER);
        } catch (e1) {}
        try {
          localStorage.setItem(LS_CONTENT_VER, ver);
        } catch (e2) {}
      }
    })();

    if (!hasServerBoard) {
      restoreQuickServerOverrides();
      restoreQuickClientRows();
      restoreScheduleClientRows();
      applyStoredSelections();
      applyScheduleMachineCodes();
    }
    // Trim whitespace from server-rendered notes cells
    quickWrap && quickWrap.querySelectorAll(".machines-cell--notes").forEach(function (cell) {
      ensureQuickNotesBody(cell);
      var t = readQuickNotesText(cell);
      var body = cell.querySelector(":scope > .machines-quick-notes-body");
      if (body && body.textContent !== t) body.textContent = t;
      if (t) cell.classList.remove("is-empty");
      else cell.classList.add("is-empty");
    });
    quickWrap && quickWrap.querySelectorAll(".machines-quick-field-view").forEach(function (inner) {
      var t = sanitizeQuickProductText(getQuickFieldFlatText(inner));
      fillQuickFieldViewTwoParts(inner, t);
      var fieldCell = inner.closest(".machines-cell--field");
      if (fieldCell) {
        if (t) fieldCell.classList.remove("is-empty");
        else fieldCell.classList.add("is-empty");
      }
    });
    root.querySelectorAll(".machines-cell--schedule-label").forEach(syncProductComboDisplay);
    syncMachineCodeAppearance();
    syncScheduleProductInteractions(root.getAttribute("data-inline-edit-mode") === "1");
    syncScheduleCodeVisibility();
    // Инициализация цветов серверных строк и цветовой подсветки станков
    buildColorPickerPop();
    scheduleWrap.querySelectorAll(".machines-schedule-row").forEach(function (row) {
      var triggerBtn = row.querySelector(".js-machines-color-trigger");
      if (triggerBtn && triggerBtn.dataset.color) applyColorToRow(row, triggerBtn.dataset.color);
    });
    syncScheduleColorsToQuickRows();
    sortScheduleRowsByPriorityQty();
  })();
