(function () {
  "use strict";
  if (window.__biotaAddrHintReady) return;
  window.__biotaAddrHintReady = true;

  (function initAddressHintModal() {
    var modal = document.querySelector(".js-addr-hint-modal");
    var openBtns = Array.prototype.slice.call(document.querySelectorAll(".js-stock-addr-hint-open"));
    if (!modal || !openBtns.length) return;

    var searchInput = modal.querySelector(".js-addr-hint-search");
    var body = modal.querySelector(".js-addr-hint-body");
    var countEl = modal.querySelector(".js-addr-hint-count");
    var printFurnSel = modal.querySelector(".js-addr-hint-print-furn");
    var printBtn = modal.querySelector(".js-addr-hint-print");
    var root = document.getElementById("inv-chat");
    var labelUrl =
      (root && root.getAttribute("data-addr-label-url")) ||
      (typeof INV !== "undefined" && INV && INV.warehouse_address_label_url) ||
      "/inventory/api/warehouse-address-label/";
    var rows = body ? Array.prototype.slice.call(body.querySelectorAll("tr[data-search]")) : [];
    var emptyRow = null;

    function csrfToken() {
      var el = document.querySelector('input[name="csrfmiddlewaretoken"]');
      return el ? el.value : "";
    }

    function ensureEmptyRow() {
      if (emptyRow || !body) return emptyRow;
      emptyRow = document.createElement("tr");
      emptyRow.className = "js-addr-hint-filter-empty";
      emptyRow.innerHTML =
        '<td colspan="3" class="inv-addr-hint-table__empty">Ничего не найдено</td>';
      emptyRow.hidden = true;
      body.appendChild(emptyRow);
      return emptyRow;
    }

    function refreshRowSearch(tr) {
      if (!tr) return;
      var addr = tr.getAttribute("data-addr") || "";
      var furn = (tr.querySelector(".inv-addr-hint-table__furn") || {}).textContent || "";
      var editBtn = tr.querySelector(".js-addr-hint-edit");
      var input = tr.querySelector(".js-addr-hint-label");
      var nameText = tr.querySelector(".js-addr-hint-name-text");
      var label = "";
      if (input) label = input.value;
      else if (editBtn) label = editBtn.getAttribute("data-label") || (nameText ? nameText.textContent : "");
      else if (nameText) label = nameText.textContent;
      tr.setAttribute(
        "data-search",
        [addr, label, furn].join(" ").replace(/\s+/g, " ").trim()
      );
    }

    function filterRows() {
      var q = String((searchInput && searchInput.value) || "").trim().toLowerCase();
      var shown = 0;
      rows.forEach(function (tr) {
        var hay = String(tr.getAttribute("data-search") || "").toLowerCase();
        var ok = !q || hay.indexOf(q) !== -1;
        tr.hidden = !ok;
        if (ok) shown += 1;
      });
      var empty = ensureEmptyRow();
      if (empty) empty.hidden = shown > 0 || rows.length === 0;
      if (countEl) {
        if (!rows.length) {
          countEl.hidden = true;
        } else {
          countEl.hidden = false;
          countEl.textContent = q
            ? ("Показано " + shown + " из " + rows.length)
            : ("Всего адресов: " + rows.length);
        }
      }
    }

    function setStatus(cell, text, kind) {
      var st = cell && cell.querySelector(".js-addr-hint-status");
      if (!st) return;
      if (!text) {
        st.hidden = true;
        st.textContent = "";
        st.className = "inv-addr-hint-table__status js-addr-hint-status";
        return;
      }
      st.hidden = false;
      st.textContent = text;
      st.className =
        "inv-addr-hint-table__status js-addr-hint-status" +
        (kind ? " is-" + kind : "");
    }

    function displayNameFor(editBtn, label) {
      var lab = String(label || "").trim();
      if (lab) return lab;
      return "Нажмите, чтобы задать";
    }

    function finishEdit(input, opts) {
      opts = opts || {};
      var cell = input && input.closest("td");
      var editBtn = cell && cell.querySelector(".js-addr-hint-edit");
      if (!editBtn || !input) return;
      var saved = String(opts.label != null ? opts.label : (editBtn.getAttribute("data-label") || "")).trim();
      editBtn.setAttribute("data-label", saved);
      var nameText = editBtn.querySelector(".js-addr-hint-name-text");
      if (nameText) nameText.textContent = displayNameFor(editBtn, saved);
      editBtn.hidden = false;
      input.remove();
      refreshRowSearch(cell.closest("tr"));
      filterRows();
    }

    function saveLabel(input) {
      if (!input || input.disabled) return;
      var cell = input.closest("td");
      var editBtn = cell && cell.querySelector(".js-addr-hint-edit");
      var address = String(input.getAttribute("data-address") || "").trim();
      var label = String(input.value || "").trim();
      var prev = String(input.getAttribute("data-saved") || "");
      if (!address) {
        setStatus(cell, "Нет адреса", "err");
        return;
      }
      if (!label) {
        setStatus(cell, "Укажите наименование", "err");
        return;
      }
      if (label === prev) {
        setStatus(cell, "", "");
        finishEdit(input, { label: prev });
        return;
      }
      setStatus(cell, "Сохранение…", "busy");
      input.disabled = true;
      fetch(labelUrl, {
        method: "POST",
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": csrfToken(),
          "X-Requested-With": "XMLHttpRequest",
        },
        body: JSON.stringify({ address: address, label: label }),
      })
        .then(function (r) { return r.json().then(function (data) { return { okHttp: r.ok, data: data }; }); })
        .then(function (res) {
          input.disabled = false;
          if (!res.data || !res.data.ok) {
            setStatus(cell, (res.data && res.data.error) || "Ошибка сохранения", "err");
            return;
          }
          var saved = String(res.data.label || label).trim();
          var addr = String(res.data.address || address || "").trim().toUpperCase();
          if (addr && typeof warehouseAddressTitles !== "undefined") {
            warehouseAddressTitles[addr] = saved;
            if (typeof applyAddressCellTitles === "function") applyAddressCellTitles();
          }
          if (editBtn) {
            editBtn.setAttribute("data-label", saved);
            if (res.data.container_id) {
              editBtn.setAttribute("data-container-id", String(res.data.container_id));
              var tr = editBtn.closest("tr");
              if (tr) tr.setAttribute("data-container-id", String(res.data.container_id));
            }
          }
          finishEdit(input, { label: saved });
          setStatus(cell, "Сохранено", "ok");
          setTimeout(function () { setStatus(cell, "", ""); }, 1200);
        })
        .catch(function () {
          input.disabled = false;
          setStatus(cell, "Сеть / ошибка", "err");
        });
    }

    function startEdit(editBtn) {
      if (!editBtn || editBtn.hidden) return;
      var cell = editBtn.closest("td");
      if (!cell || cell.querySelector(".js-addr-hint-label")) return;
      var input = document.createElement("input");
      input.type = "text";
      input.className = "inv-addr-hint-table__input js-addr-hint-label";
      input.maxLength = 120;
      input.value = String(editBtn.getAttribute("data-label") || "").trim();
      input.placeholder = String(editBtn.getAttribute("data-placeholder") || "Наименование");
      input.setAttribute("data-container-id", editBtn.getAttribute("data-container-id") || "");
      input.setAttribute("data-address", editBtn.getAttribute("data-address") || "");
      input.setAttribute("data-saved", String(editBtn.getAttribute("data-label") || "").trim());
      input.setAttribute("aria-label", "Наименование для " + (editBtn.getAttribute("data-address") || ""));
      editBtn.hidden = true;
      cell.insertBefore(input, editBtn.nextSibling);
      input.focus();
      input.select();

      function end() {
        saveLabel(input);
      }
      input.addEventListener("blur", end);
      input.addEventListener("keydown", function (ev) {
        if (ev.key === "Enter") {
          ev.preventDefault();
          input.blur();
        } else if (ev.key === "Escape") {
          ev.preventDefault();
          ev.stopPropagation();
          input.removeEventListener("blur", end);
          setStatus(cell, "", "");
          finishEdit(input, { label: input.getAttribute("data-saved") || "" });
        }
      });
    }

    function escapeHtml(s) {
      return String(s || "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;");
    }

    function collectPrintLines() {
      var furnId = printFurnSel ? String(printFurnSel.value || "") : "";
      var furnTitle = "Вся мебель";
      if (printFurnSel && printFurnSel.selectedIndex >= 0) {
        furnTitle = printFurnSel.options[printFurnSel.selectedIndex].text || furnTitle;
      }
      var lines = [];
      rows.forEach(function (tr) {
        if (furnId && String(tr.getAttribute("data-furn-id") || "") !== furnId) return;
        var addr = tr.getAttribute("data-addr") || "";
        var editBtn = tr.querySelector(".js-addr-hint-edit");
        var input = tr.querySelector(".js-addr-hint-label");
        var nameText = tr.querySelector(".js-addr-hint-name-text");
        var name = "";
        if (input) {
          name = String(input.value || input.getAttribute("placeholder") || "").trim();
        } else if (editBtn) {
          name = String(editBtn.getAttribute("data-label") || "").trim()
            || String((nameText && nameText.textContent) || "").trim();
        } else {
          name = String((nameText && nameText.textContent) || "").trim();
        }
        var furn = String((tr.querySelector(".inv-addr-hint-table__furn") || {}).textContent || "")
          .replace(/\s+/g, " ")
          .trim();
        if (!addr) return;
        lines.push({
          address: addr,
          name: name || "—",
          furniture: furn || "—",
        });
      });
      return { lines: lines, furnId: furnId, furnTitle: furnTitle };
    }

    function printRows() {
      var payload = collectPrintLines();
      var lines = payload.lines;
      var furnTitle = payload.furnTitle;
      if (!lines.length) {
        window.alert(payload.furnId ? "Нет адресов для выбранной мебели." : "Нет адресов для печати.");
        return;
      }
      var w = window.open("", "_blank");
      if (!w) {
        window.alert("Разрешите всплывающие окна для печати.");
        return;
      }
      var rowsHtml = lines
        .map(function (row) {
          return (
            "<tr><td class='addr'>" +
            escapeHtml(row.address) +
            "</td><td>" +
            escapeHtml(row.name) +
            "</td><td>" +
            escapeHtml(row.furniture) +
            "</td></tr>"
          );
        })
        .join("");
      w.document.open();
      w.document.write(
        "<!doctype html><html><head><meta charset='utf-8'><title>Адреса склада — " +
          escapeHtml(furnTitle) +
          "</title><style>" +
          "body{font:14px/1.35 system-ui,Segoe UI,sans-serif;color:#111;margin:18px;}" +
          "h1{font-size:18px;margin:0 0 4px;} .meta{color:#555;margin:0 0 14px;font-size:12px;}" +
          "table{width:100%;border-collapse:collapse;} th,td{border:1px solid #ccc;padding:6px 8px;text-align:left;vertical-align:top;}" +
          "th{background:#f3f3f3;font-size:12px;text-transform:uppercase;letter-spacing:.03em;}" +
          "td.addr{font-family:ui-monospace,Consolas,monospace;font-weight:700;white-space:nowrap;width:1%;}" +
          "@media print{body{margin:8mm;} .noprint{display:none!important;}}" +
          "</style></head><body>" +
          "<button class='noprint' onclick='window.print()' style='margin-bottom:12px;padding:6px 12px;'>Печать</button>" +
          "<h1>Подсказка по адресам</h1>" +
          "<p class='meta'>" +
          escapeHtml(furnTitle) +
          " · " +
          lines.length +
          " шт.</p>" +
          "<table><thead><tr><th>Адрес</th><th>Наименование</th><th>Мебель</th></tr></thead><tbody>" +
          rowsHtml +
          "</tbody></table>" +
          "<script>window.onload=function(){setTimeout(function(){window.print();},80);}<\\/script>" +
          "</body></html>"
      );
      w.document.close();
    }

    function openModal() {
      modal.hidden = false;
      document.documentElement.classList.add("inv-addr-hint-open");
      filterRows();
      if (searchInput) {
        setTimeout(function () { searchInput.focus(); }, 30);
      }
    }

    function closeModal() {
      modal.hidden = true;
      document.documentElement.classList.remove("inv-addr-hint-open");
    }

    openBtns.forEach(function (btn) {
      btn.addEventListener("click", openModal);
    });
    modal.querySelectorAll(".js-addr-hint-close").forEach(function (btn) {
      btn.addEventListener("click", closeModal);
    });
    if (searchInput) {
      searchInput.addEventListener("input", filterRows);
      searchInput.addEventListener("keydown", function (ev) {
        if (ev.key === "Escape") {
          ev.preventDefault();
          closeModal();
        }
      });
    }
    if (printBtn) printBtn.addEventListener("click", printRows);
    modal.addEventListener("click", function (ev) {
      var btn = ev.target.closest(".js-addr-hint-edit");
      if (btn && modal.contains(btn)) startEdit(btn);
    });
    document.addEventListener("keydown", function (ev) {
      if (ev.key === "Escape" && modal && !modal.hidden) {
        if (ev.target && ev.target.classList && ev.target.classList.contains("js-addr-hint-label")) return;
        closeModal();
      }
    });
  })()
})();
