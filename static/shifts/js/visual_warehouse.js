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
  var btnDelCab = document.querySelector(".js-vw-del-cabinet");
  var btnDelCont = document.querySelector(".js-vw-del-container");

  var cabinets = [];
  var editMode = false;
  var openContainerId = null;
  var editingCabinetId = null;

  var CAT_LABELS = {
    end_mill: "Фрезы",
    tap: "Резьбовой",
    center_drill: "Центровки",
    countersink: "Зенкера",
    drill: "Сверла",
    insert: "Пластинки",
    collet: "Цанги",
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
        ? "Правка: «+» на полке — новый ящик. Клик по ящику — изменить. Готово — снова только просмотр."
        : "Как в цехе: откройте шкаф глазами — нажмите на ящик, чтобы увидеть что внутри";
    }
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
  }

  function buildCabinetCard(cab) {
    var wrap = document.createElement("section");
    wrap.className = "vw-cabinet";
    wrap.dataset.cabinetId = String(cab.id);

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
      btnEdit.textContent = "Параметры шкафа";
      btnEdit.addEventListener("click", function () { openCabinetForm(cab); });
      bar.appendChild(btnEdit);
      wrap.appendChild(bar);
    }

    return wrap;
  }

  function buildBay(cab, shelf) {
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

  function buildBin(cab, cont) {
    var btn = document.createElement("button");
    btn.type = "button";
    btn.className = "vw-bin";
    btn.style.background = cont.color || "#e74c3c";
    btn.style.color = contrastText(cont.color);
    var text = document.createElement("span");
    text.className = "vw-bin-text";
    text.textContent = cont.label || "Ящик";
    btn.appendChild(text);
    btn.title = editMode
      ? ((cont.label || "Ящик") + " — изменить")
      : ((cont.label || "Ящик") + " — открыть");
    btn.addEventListener("click", function () {
      if (editMode) openContainerForm(cab, cont);
      else openContents(cont.id);
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

  function openCabinetForm(cab) {
    editingCabinetId = cab ? cab.id : null;
    cabForm.querySelector(".js-vw-cab-form-title").textContent = cab ? "Параметры шкафа" : "Новый шкаф";
    cabForm.querySelector(".js-vw-cab-id").value = cab ? String(cab.id) : "";
    cabForm.querySelector(".js-vw-cab-name").value = cab ? cab.name : "";
    cabForm.querySelector(".js-vw-cab-shelves").value = cab ? String(cab.shelves) : "5";
    cabForm.querySelector(".js-vw-cab-columns").value = cab ? String(cab.columns) : "4";
    cabForm.querySelector(".js-vw-cab-notes").value = cab ? (cab.notes || "") : "";
    setVisible(btnDelCab, !!cab);
    openDialog(dlgCab);
  }

  function openContainerForm(cab, cont, shelf, stack, col) {
    contForm.querySelector(".js-vw-cont-form-title").textContent = cont ? "Ящик" : "Новый ящик";
    contForm.querySelector(".js-vw-cont-id").value = cont ? String(cont.id) : "";
    contForm.querySelector(".js-vw-cont-cabinet").value = String(cab.id);
    contForm.querySelector(".js-vw-cont-label").value = cont ? cont.label : "";
    contForm.querySelector(".js-vw-cont-color").value = (cont && cont.color) || "#e74c3c";
    contForm.querySelector(".js-vw-cont-shelf").value = String(cont ? cont.shelf : shelf || 1);
    contForm.querySelector(".js-vw-cont-stack").value = String(cont ? (cont.stack || 1) : stack || 1);
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
    setVisible(btnDelCont, !!cont);
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
    var body = {
      name: name,
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
    var label = (contForm.querySelector(".js-vw-cont-label").value || "").trim();
    if (!cabinetId) {
      window.alert("Не выбран шкаф — закройте окно и нажмите «+» на полке ещё раз");
      return;
    }
    if (!label) {
      window.alert("Напишите подпись на ящике");
      contForm.querySelector(".js-vw-cont-label").focus();
      return;
    }
    savingContainer = true;
    var idVal = contForm.querySelector(".js-vw-cont-id").value;
    var notesEl = contForm.querySelector(".js-vw-cont-notes");
    var body = {
      cabinet_id: cabinetId,
      shelf: parseInt(contForm.querySelector(".js-vw-cont-shelf").value, 10) || 1,
      stack: parseInt(contForm.querySelector(".js-vw-cont-stack").value, 10) || 1,
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

  function saveItem() {
    if (!openContainerId || !itemForm) return;
    var title = (itemForm.querySelector(".js-vw-item-title").value || "").trim();
    if (!title) {
      alert("Укажите, что лежит");
      return;
    }
    var body = {
      container_id: openContainerId,
      title: title,
      tool_category: itemForm.querySelector(".js-vw-item-category").value,
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
        return openContents(openContainerId);
      })
      .then(function () { return loadCabinets(); })
      .catch(function (e) { alert(e.message); });
  }

  function renderItems(container) {
    if (!itemsEl) return;
    itemsEl.innerHTML = "";
    var items = container.items || [];
    if (!items.length) {
      itemsEl.innerHTML = "<li class='vw-item'><span class='vw-item-meta'>Пусто</span></li>";
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
      if (it.diameter_from_mm != null || it.diameter_to_mm != null) {
        parts.push("Ø " + (it.diameter_from_mm != null ? it.diameter_from_mm : "?") + "–" + (it.diameter_to_mm != null ? it.diameter_to_mm : "?"));
      }
      if (it.quantity_note) parts.push(it.quantity_note);
      if (it.stock_qty != null) parts.push("на складе: " + it.stock_qty);
      meta.textContent = parts.join(" · ") || "—";
      left.appendChild(meta);
      top.appendChild(left);
      if (canEdit) {
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
    return fetchJson(detailUrl(apiContTpl, containerId)).then(function (data) {
      var cont = data.container;
      var titleEl = document.querySelector(".js-vw-contents-title");
      var metaEl = document.querySelector(".js-vw-contents-meta");
      if (titleEl) titleEl.textContent = cont.label;
      if (metaEl) {
        metaEl.textContent = "Полка " + cont.shelf + ", место " + cont.column +
          (cont.notes ? " · " + cont.notes : "");
      }
      renderItems(cont);
      openDialog(dlgContents);
    }).catch(function (e) { alert(e.message); });
  }

  setEditMode(false);
  loadCabinets();
})();
