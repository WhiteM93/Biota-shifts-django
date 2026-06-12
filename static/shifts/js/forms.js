(function () {
  var root = document.querySelector(".forms-page");
  if (!root) return;

  var apiListUrl = root.getAttribute("data-api-list-url") || "";
  var apiDetailTpl = root.getAttribute("data-api-detail-tpl") || "";
  var canEdit = (root.getAttribute("data-can-edit") || "") === "1";

  var emptyEl = root.querySelector(".js-forms-empty");
  var editorEl = root.querySelector(".js-forms-editor");
  var propsPanel = root.querySelector(".js-forms-props");
  var canvasStage = root.querySelector(".js-forms-canvas-stage");
  var sheetScaler = root.querySelector(".js-forms-sheet-scaler");
  var listEl = root.querySelector(".js-forms-list");
  var sheetEl = root.querySelector(".js-forms-sheet");
  var sheetFrameEl = root.querySelector(".js-forms-sheet-frame");
  var sheetInnerEl = root.querySelector(".js-forms-sheet-inner");
  var printRoot = root.querySelector(".js-forms-print-root");
  var printBtn = root.querySelector(".js-forms-print");

  var nameInput = root.querySelector(".js-forms-name");
  var orientationSelect = root.querySelector(".js-forms-orientation");
  var borderCheck = root.querySelector(".js-forms-border");
  var borderPanel = root.querySelector(".forms-border-panel");
  var borderInsetInput = root.querySelector(".js-forms-border-inset");
  var marginMmInput = root.querySelector(".js-forms-margin-mm");
  var borderWidthInput = root.querySelector(".js-forms-border-width");
  var borderStyleSelect = root.querySelector(".js-forms-border-style");
  var headingPropsBlock = root.querySelector(".js-forms-heading-props");
  var headingAlignBtns = root.querySelectorAll(".js-forms-heading-align");
  var headingSizeInput = root.querySelector(".js-forms-heading-size");
  var activeHeadingId = null;
  var tablePropsBlock = root.querySelector(".js-forms-table-props");
  var tableToolbarHost = root.querySelector(".js-forms-table-toolbar-host");
  var activeTableId = null;

  var dialogNew = root.querySelector(".js-forms-dialog-new");
  var dialogNewForm = root.querySelector(".js-forms-new-form");
  var newNameInput = root.querySelector(".js-forms-new-name");
  var newOrientationSelect = root.querySelector(".js-forms-new-orientation");
  var newBorderCheck = root.querySelector(".js-forms-new-border");

  var dialogPrompt = root.querySelector(".js-forms-dialog-prompt");
  var promptForm = root.querySelector(".js-forms-prompt-form");
  var promptTitle = root.querySelector(".js-forms-prompt-title");
  var promptFields = root.querySelector(".js-forms-prompt-fields");

  var forms = [];
  var currentId = null;
  var saveTimer = null;
  var saveSeq = 0;
  var promptResolver = null;
  var tableSelection = {};
  var TABLE_DEFAULT_BG = "#ffffff";
  var MM_PX = 96 / 25.4;
  var sheetFitTimer = null;
  var DEFAULT_PAGE_SETTINGS = {
    margin_mm: 12,
    border_inset_mm: 8,
    border_width_mm: 1,
    border_style: "solid",
    border_color: "#000000",
  };

  if (!canEdit) root.classList.add("is-readonly");

  function normalizePageSettings(raw) {
    var src = raw && typeof raw === "object" ? raw : {};
    var style = String(src.border_style || DEFAULT_PAGE_SETTINGS.border_style).toLowerCase();
    if (["solid", "dashed", "dotted", "double"].indexOf(style) < 0) style = "solid";
    function mm(key, def, lo, hi) {
      var val = parseFloat(src[key]);
      if (isNaN(val)) val = def;
      return Math.round(Math.max(lo, Math.min(hi, val)) * 10) / 10;
    }
    return {
      margin_mm: mm("margin_mm", 12, 0, 40),
      border_inset_mm: mm("border_inset_mm", 8, 0, 40),
      border_width_mm: mm("border_width_mm", 1, 0.1, 5),
      border_style: style,
      border_color: "#000000",
    };
  }

  function setPanelVisible(el, visible) {
    if (!el) return;
    el.hidden = !visible;
    el.classList.toggle("forms-is-hidden", !visible);
  }

  function findElementById(id) {
    var form = currentForm();
    if (!form || !id) return null;
    var els = form.elements || [];
    for (var i = 0; i < els.length; i++) {
      if (els[i].id === id) return els[i];
    }
    return null;
  }

  function normHeadingAlign(align) {
    align = String(align || "left").toLowerCase();
    return ["left", "center", "right"].indexOf(align) >= 0 ? align : "left";
  }

  function normHeadingFontSize(size) {
    var fs = parseInt(size, 10);
    if (isNaN(fs)) fs = 16;
    return Math.max(8, Math.min(48, fs));
  }

  function ensureHeadingFields(elData) {
    if (!elData || elData.type !== "heading") return;
    elData.align = normHeadingAlign(elData.align);
    elData.font_size = normHeadingFontSize(elData.font_size);
  }

  function applyHeadingStyles(input, elData) {
    if (!input || !elData) return;
    ensureHeadingFields(elData);
    input.style.fontSize = elData.font_size + "pt";
    input.style.textAlign = elData.align;
  }

  function syncHeadingPropsUi(elData) {
    if (!headingPropsBlock) return;
    if (!canEdit || !elData || elData.type !== "heading") {
      setPanelVisible(headingPropsBlock, false);
      return;
    }
    ensureHeadingFields(elData);
    setPanelVisible(headingPropsBlock, true);
    if (headingSizeInput) headingSizeInput.value = String(elData.font_size);
    headingAlignBtns.forEach(function (btn) {
      btn.classList.toggle("is-active", btn.getAttribute("data-align") === elData.align);
    });
  }

  function setActiveHeading(elData) {
    if (elData && elData.type === "heading") {
      activeHeadingId = elData.id;
      syncHeadingPropsUi(elData);
    } else {
      activeHeadingId = null;
      syncHeadingPropsUi(null);
    }
  }

  function getActiveHeading() {
    var elData = findElementById(activeHeadingId);
    return elData && elData.type === "heading" ? elData : null;
  }

  function updateActiveHeadingDom(elData) {
    if (!elData || !sheetInnerEl) return;
    var wrap = sheetInnerEl.querySelector('.forms-el[data-el-id="' + elData.id + '"]');
    var h = wrap && wrap.querySelector(".forms-el-heading");
    if (h) {
      applyHeadingStyles(h, elData);
      autoGrowTextarea(h);
    }
  }

  function normOrientation(orientation) {
    return orientation === "landscape" ? "landscape" : "portrait";
  }

  function sheetPageSizeMm(orientation) {
    var o = normOrientation(orientation);
    return o === "landscape"
      ? { w: 297, h: 210 }
      : { w: 210, h: 297 };
  }

  function scheduleSheetFitScale() {
    clearTimeout(sheetFitTimer);
    sheetFitTimer = setTimeout(function () {
      sheetFitTimer = null;
      updateSheetFitScale();
    }, 40);
  }

  function updateSheetFitScale() {
    if (!canvasStage || !sheetEl || !sheetScaler) return;
    var form = currentForm();
    if (!form || editorEl.hidden) return;
    var size = sheetPageSizeMm(form.orientation);
    var pageW = size.w * MM_PX;
    var pageH = size.h * MM_PX;
    var pad = 32;
    var availW = Math.max(80, canvasStage.clientWidth - pad);
    var availH = Math.max(80, canvasStage.clientHeight - pad);
    var scale = Math.min(availW / pageW, availH / pageH, 1);
    sheetEl.style.transform = "scale(" + scale + ")";
    sheetEl.style.transformOrigin = "top left";
    sheetScaler.style.width = Math.round(pageW * scale) + "px";
    sheetScaler.style.height = Math.round(pageH * scale) + "px";
  }

  function applySheetOrientation(form) {
    if (!form || !sheetEl || !sheetScaler) return;
    var o = normOrientation(form.orientation);
    var size = sheetPageSizeMm(o);
    form.orientation = o;
    sheetEl.setAttribute("data-orientation", o);
    sheetEl.style.width = size.w + "mm";
    sheetEl.style.height = size.h + "mm";
    sheetEl.style.minHeight = "";
    sheetEl.style.maxHeight = "";
    sheetEl.style.maxWidth = "";
    scheduleSheetFitScale();
  }

  function updateSheetScalerWidth(form) {
    applySheetOrientation(form);
  }

  function ensureFormPageSettings(form) {
    form.page_settings = normalizePageSettings(form.page_settings);
    return form.page_settings;
  }

  function applyPageLayout(form, sheet, frame, inner) {
    if (!form || !sheet || !frame || !inner) return;
    var ps = ensureFormPageSettings(form);
    if (sheet === sheetEl) {
      applySheetOrientation(form);
    } else {
      sheet.setAttribute("data-orientation", normOrientation(form.orientation));
    }

    if (form.show_border) {
      frame.style.top = ps.border_inset_mm + "mm";
      frame.style.left = ps.border_inset_mm + "mm";
      frame.style.right = ps.border_inset_mm + "mm";
      frame.style.bottom = ps.border_inset_mm + "mm";
      frame.style.border = ps.border_width_mm + "mm " + ps.border_style + " #000000";
    } else {
      frame.style.top = "0";
      frame.style.left = "0";
      frame.style.right = "0";
      frame.style.bottom = "0";
      frame.style.border = "none";
    }
    inner.style.padding = ps.margin_mm + "mm";
  }

  function syncBorderPanelUi(form) {
    if (!form) return;
    var ps = ensureFormPageSettings(form);
    if (borderCheck) borderCheck.checked = !!form.show_border;
    if (borderInsetInput) borderInsetInput.value = ps.border_inset_mm;
    if (marginMmInput) marginMmInput.value = ps.margin_mm;
    if (borderWidthInput) borderWidthInput.value = ps.border_width_mm;
    if (borderStyleSelect) borderStyleSelect.value = ps.border_style;
    if (borderPanel) borderPanel.classList.toggle("is-border-on", !!form.show_border);
    applyPageLayout(form, sheetEl, sheetFrameEl, sheetInnerEl);
    updateSheetScalerWidth(form);
  }

  function readPageSettingsFromUi(form) {
    if (!form) return;
    var ps = ensureFormPageSettings(form);
    if (borderInsetInput) ps.border_inset_mm = parseFloat(borderInsetInput.value) || 0;
    if (marginMmInput) ps.margin_mm = parseFloat(marginMmInput.value) || 0;
    if (borderWidthInput) ps.border_width_mm = parseFloat(borderWidthInput.value) || 1;
    if (borderStyleSelect) ps.border_style = borderStyleSelect.value;
    form.page_settings = normalizePageSettings(ps);
    if (borderCheck) form.show_border = borderCheck.checked;
    syncBorderPanelUi(form);
    scheduleSave();
  }

  function makeCell(text) {
    return {
      text: text || "",
      bg: TABLE_DEFAULT_BG,
      colspan: 1,
      rowspan: 1,
      hidden: false,
      align: "left",
      font_size: 12,
      bold: false,
      italic: false,
      underline: false,
    };
  }

  function normCellAlign(align) {
    align = String(align || "left").toLowerCase();
    return ["left", "center", "right"].indexOf(align) >= 0 ? align : "left";
  }

  function normCellFontSize(size) {
    var fs = parseInt(size, 10);
    if (isNaN(fs)) fs = 12;
    return Math.max(8, Math.min(48, fs));
  }

  function ensureCellFormat(cell) {
    if (!cell || typeof cell !== "object") return;
    cell.align = normCellAlign(cell.align);
    cell.font_size = normCellFontSize(cell.font_size);
    cell.bold = !!cell.bold;
    cell.italic = !!cell.italic;
    cell.underline = !!cell.underline;
  }

  function applyCellTextStyles(inp, cellData) {
    if (!inp || !cellData) return;
    ensureCellFormat(cellData);
    inp.style.textAlign = cellData.align;
    inp.style.fontSize = cellData.font_size + "pt";
    inp.style.fontWeight = cellData.bold ? "700" : "normal";
    inp.style.fontStyle = cellData.italic ? "italic" : "normal";
    inp.style.textDecoration = cellData.underline ? "underline" : "none";
  }

  function forEachSelectedMasterCell(elData, fn) {
    var sel = getTableSel(elData);
    if (!sel) return;
    normalizeTableCells(elData);
    var r1 = Math.min(sel.r1, sel.r2);
    var r2 = Math.max(sel.r1, sel.r2);
    var c1 = Math.min(sel.c1, sel.c2);
    var c2 = Math.max(sel.c1, sel.c2);
    var seen = {};
    for (var r = r1; r <= r2; r++) {
      for (var c = c1; c <= c2; c++) {
        var m = findMasterCell(elData, r, c);
        var key = m.r + "," + m.c;
        if (seen[key]) continue;
        seen[key] = true;
        fn(m.cell, m.r, m.c);
      }
    }
  }

  function updateTableCellFormatDom(elData) {
    var elWrap = sheetInnerEl && sheetInnerEl.querySelector('.forms-el[data-el-id="' + elData.id + '"]');
    if (!elWrap) return;
    elWrap.querySelectorAll(".forms-el-table td").forEach(function (td) {
      var r = parseInt(td.getAttribute("data-row") || "", 10);
      var c = parseInt(td.getAttribute("data-col") || "", 10);
      var ta = td.querySelector("textarea");
      if (!ta || isNaN(r) || isNaN(c)) return;
      var cellData = elData.cells[r] && elData.cells[r][c];
      if (!cellData || cellData.hidden) return;
      applyCellTextStyles(ta, cellData);
    });
  }

  function primarySelectedCell(elData) {
    var sel = getTableSel(elData);
    if (!sel) return null;
    var r = Math.min(sel.r1, sel.r2);
    var c = Math.min(sel.c1, sel.c2);
    return findMasterCell(elData, r, c);
  }

  function normalizeTableSizes(elData) {
    var cols = elData.cols || 1;
    var rows = elData.rows || 1;
    var i;
    if (!Array.isArray(elData.col_widths) || elData.col_widths.length !== cols) {
      var w = Math.floor((100 / cols) * 100) / 100;
      elData.col_widths = [];
      for (i = 0; i < cols; i++) elData.col_widths.push(w);
      var sum = 0;
      for (i = 0; i < cols; i++) sum += elData.col_widths[i];
      elData.col_widths[cols - 1] = Math.round((elData.col_widths[cols - 1] + (100 - sum)) * 10) / 10;
    } else {
      for (i = 0; i < cols; i++) {
        var cw = parseFloat(elData.col_widths[i]);
        if (isNaN(cw)) cw = 100 / cols;
        elData.col_widths[i] = Math.round(Math.max(5, Math.min(95, cw)) * 10) / 10;
      }
      var total = 0;
      for (i = 0; i < cols; i++) total += elData.col_widths[i];
      if (total > 0 && Math.abs(total - 100) > 0.05) {
        for (i = 0; i < cols; i++) {
          elData.col_widths[i] = Math.round((elData.col_widths[i] / total) * 1000) / 10;
        }
        var total2 = 0;
        for (i = 0; i < cols; i++) total2 += elData.col_widths[i];
        elData.col_widths[cols - 1] = Math.round((elData.col_widths[cols - 1] + (100 - total2)) * 10) / 10;
      }
    }
    if (!Array.isArray(elData.row_heights) || elData.row_heights.length !== rows) {
      elData.row_heights = [];
      for (i = 0; i < rows; i++) elData.row_heights.push(0);
    } else {
      for (i = 0; i < rows; i++) {
        var rh = parseInt(elData.row_heights[i], 10);
        elData.row_heights[i] = isNaN(rh) || rh < 0 ? 0 : Math.min(300, rh);
      }
    }
  }

  function normalizeTableCells(elData) {
    var rows = elData.rows || 1;
    var cols = elData.cols || 1;
    if (!elData.cells || !elData.cells.length) elData.cells = [];
    while (elData.cells.length < rows) elData.cells.push([]);
    elData.cells = elData.cells.slice(0, rows);
    for (var r = 0; r < rows; r++) {
      while (elData.cells[r].length < cols) elData.cells[r].push(makeCell(""));
      elData.cells[r] = elData.cells[r].slice(0, cols);
      for (var c = 0; c < cols; c++) {
        var raw = elData.cells[r][c];
        if (typeof raw === "string") {
          elData.cells[r][c] = makeCell(raw);
        } else if (!raw || typeof raw !== "object") {
          elData.cells[r][c] = makeCell("");
        } else {
          elData.cells[r][c] = {
            text: raw.text || "",
            bg: raw.bg || TABLE_DEFAULT_BG,
            colspan: Math.max(1, parseInt(raw.colspan, 10) || 1),
            rowspan: Math.max(1, parseInt(raw.rowspan, 10) || 1),
            hidden: !!raw.hidden,
            align: raw.align,
            font_size: raw.font_size,
            bold: raw.bold,
            italic: raw.italic,
            underline: raw.underline,
          };
          ensureCellFormat(elData.cells[r][c]);
        }
      }
    }
    normalizeTableSizes(elData);
  }

  function rowSpanHeight(elData, startRow, span) {
    var total = 0;
    for (var k = 0; k < span; k++) {
      var rh = elData.row_heights[startRow + k] || 0;
      if (rh <= 0) return 0;
      total += rh;
    }
    return total;
  }

  function applyTdRowHeight(td, heightPx) {
    var ta = td.querySelector("textarea");
    if (heightPx > 0) {
      td.classList.add("forms-td-fixed-h");
      td.style.height = heightPx + "px";
      td.style.minHeight = heightPx + "px";
      td.style.maxHeight = heightPx + "px";
      if (ta) {
        ta.style.height = "100%";
        ta.style.minHeight = "0";
        ta.style.maxHeight = "100%";
        ta.style.resize = "none";
        ta.style.overflow = "auto";
      }
    } else {
      td.classList.remove("forms-td-fixed-h");
      td.style.height = "";
      td.style.minHeight = "";
      td.style.maxHeight = "";
      if (ta) {
        ta.style.height = "";
        ta.style.minHeight = "";
        ta.style.maxHeight = "";
        ta.style.resize = "";
        ta.style.overflow = "";
      }
    }
  }

  function applyTableSizes(table, elData) {
    if (!table || !elData) return;
    normalizeTableSizes(elData);
    var cg = table.querySelector("colgroup");
    if (!cg) {
      cg = document.createElement("colgroup");
      table.insertBefore(cg, table.firstChild);
    }
    cg.innerHTML = "";
    for (var i = 0; i < elData.cols; i++) {
      var col = document.createElement("col");
      col.style.width = elData.col_widths[i] + "%";
      cg.appendChild(col);
    }
    var trs = table.querySelectorAll("tr");
    for (var ri = 0; ri < trs.length; ri++) {
      trs[ri].style.height = "";
      trs[ri].style.minHeight = "";
      var tds = trs[ri].children;
      for (var j = 0; j < tds.length; j++) {
        var td = tds[j];
        if (td.tagName !== "TD") continue;
        var rowspan = td.rowSpan || 1;
        var rowIdx = parseInt(td.getAttribute("data-row") || "", 10);
        if (isNaN(rowIdx)) rowIdx = ri;
        if (rowspan > 1) {
          applyTdRowHeight(td, rowSpanHeight(elData, rowIdx, rowspan));
        } else {
          applyTdRowHeight(td, elData.row_heights[ri] || 0);
        }
      }
    }
  }

  function setColWidth(elData, colIndex, newWidth) {
    normalizeTableSizes(elData);
    newWidth = Math.round(Math.max(5, Math.min(95, newWidth)) * 10) / 10;
    var delta = newWidth - elData.col_widths[colIndex];
    if (Math.abs(delta) < 0.05) return;
    if (colIndex < elData.cols - 1) {
      var next = Math.round((elData.col_widths[colIndex + 1] - delta) * 10) / 10;
      if (next < 5) return;
      elData.col_widths[colIndex] = newWidth;
      elData.col_widths[colIndex + 1] = next;
    } else if (colIndex > 0) {
      var prev = Math.round((elData.col_widths[colIndex - 1] - delta) * 10) / 10;
      if (prev < 5) return;
      elData.col_widths[colIndex] = newWidth;
      elData.col_widths[colIndex - 1] = prev;
    }
  }

  function setRowHeight(elData, rowIndex, height) {
    normalizeTableSizes(elData);
    var h = parseInt(height, 10);
    elData.row_heights[rowIndex] = isNaN(h) || h < 0 ? 0 : Math.min(300, h);
  }

  function tableEdgeHit(td, clientX, clientY) {
    var rect = td.getBoundingClientRect();
    var edge = 8;
    var onCol = clientX >= rect.right - edge && clientX <= rect.right + 2;
    var onRow = clientY >= rect.bottom - edge && clientY <= rect.bottom + 2;
    if (onCol && onRow) {
      var distCol = rect.right - clientX;
      var distRow = rect.bottom - clientY;
      return distCol <= distRow ? "col" : "row";
    }
    if (onCol) return "col";
    if (onRow) return "row";
    return null;
  }

  function tableTdFromEvent(table, ev) {
    var node = ev.target;
    while (node && node !== table) {
      if (node.tagName === "TD") return node;
      node = node.parentElement;
    }
    return null;
  }

  function bindTableResizeEvents(table, elData) {
    if (!canEdit || table.dataset.resizeBound === "1") return;
    table.dataset.resizeBound = "1";

    table.addEventListener("mousemove", function (ev) {
      var td = tableTdFromEvent(table, ev);
      table.querySelectorAll("td.is-col-resize, td.is-row-resize").forEach(function (cell) {
        cell.classList.remove("is-col-resize", "is-row-resize");
      });
      if (!td) return;
      var edge = tableEdgeHit(td, ev.clientX, ev.clientY);
      if (edge === "col" || edge === "both") td.classList.add("is-col-resize");
      if (edge === "row" || edge === "both") td.classList.add("is-row-resize");
    });

    table.addEventListener("mouseleave", function () {
      table.querySelectorAll("td.is-col-resize, td.is-row-resize").forEach(function (cell) {
        cell.classList.remove("is-col-resize", "is-row-resize");
      });
    });

    table.addEventListener("mousedown", function (ev) {
      var td = tableTdFromEvent(table, ev);
      if (!td) return;
      var edge = tableEdgeHit(td, ev.clientX, ev.clientY);
      if (!edge) return;
      var rr = parseInt(td.getAttribute("data-row") || "", 10);
      var cc = parseInt(td.getAttribute("data-col") || "", 10);
      if (isNaN(rr) || isNaN(cc)) return;
      var cellData = elData.cells[rr] && elData.cells[rr][cc];
      if (!cellData || cellData.hidden) return;
      var boundaryCol = cc + (cellData.colspan || 1) - 1;
      var boundaryRow = rr + (cellData.rowspan || 1) - 1;
      if ((edge === "col" || edge === "both") && boundaryCol < elData.cols - 1) {
        ev.preventDefault();
        ev.stopPropagation();
        startColResize(elData, boundaryCol, ev, table);
        return;
      }
      if (edge === "row" || edge === "both") {
        ev.preventDefault();
        ev.stopPropagation();
        if (boundaryRow < elData.rows - 1) {
          startRowResize(elData, boundaryRow, ev, table, false);
        } else {
          startRowResize(elData, boundaryRow, ev, table, true);
        }
      }
    }, true);
  }

  function startColResize(elData, colIndex, ev, table) {
    if (!table || colIndex >= elData.cols - 1) return;
    normalizeTableSizes(elData);
    var startX = ev.clientX;
    var startLeft = elData.col_widths[colIndex];
    var startRight = elData.col_widths[colIndex + 1];
    var tableWidth = table.getBoundingClientRect().width || table.offsetWidth || 1;
    document.body.classList.add("forms-table-resizing", "forms-table-resizing--col");

    function onMove(e) {
      var deltaPct = ((e.clientX - startX) / tableWidth) * 100;
      var left = Math.round((startLeft + deltaPct) * 10) / 10;
      var right = Math.round((startRight - deltaPct) * 10) / 10;
      if (left < 5 || right < 5) return;
      elData.col_widths[colIndex] = left;
      elData.col_widths[colIndex + 1] = right;
      applyTableSizes(table, elData);
      refreshTableSelectionDom(elData);
    }

    function onUp() {
      document.removeEventListener("mousemove", onMove);
      document.removeEventListener("mouseup", onUp);
      document.body.classList.remove("forms-table-resizing", "forms-table-resizing--col");
      scheduleSave();
    }

    document.addEventListener("mousemove", onMove);
    document.addEventListener("mouseup", onUp);
  }

  function measureRowHeight(table, rowIndex) {
    var trs = table.querySelectorAll("tr");
    var tr = trs[rowIndex];
    return tr ? Math.round(tr.getBoundingClientRect().height) : 24;
  }

  function startRowResize(elData, rowIndex, ev, table, singleRow) {
    if (!table || rowIndex < 0 || rowIndex >= elData.rows) return;
    normalizeTableSizes(elData);
    var startY = ev.clientY;
    document.body.classList.add("forms-table-resizing", "forms-table-resizing--row");

    if (singleRow) {
      var startH = elData.row_heights[rowIndex] || 0;
      if (startH <= 0) startH = measureRowHeight(table, rowIndex);
      function onMoveSingle(e) {
        var h = Math.round(Math.max(20, startH + (e.clientY - startY)));
        elData.row_heights[rowIndex] = h;
        applyTableSizes(table, elData);
        refreshTableSelectionDom(elData);
      }
      function onUpSingle() {
        document.removeEventListener("mousemove", onMoveSingle);
        document.removeEventListener("mouseup", onUpSingle);
        document.body.classList.remove("forms-table-resizing", "forms-table-resizing--row");
        scheduleSave();
      }
      document.addEventListener("mousemove", onMoveSingle);
      document.addEventListener("mouseup", onUpSingle);
      return;
    }

    if (rowIndex >= elData.rows - 1) return;
    var startTop = elData.row_heights[rowIndex] || 0;
    var startBottom = elData.row_heights[rowIndex + 1] || 0;
    if (startTop <= 0) startTop = measureRowHeight(table, rowIndex);
    if (startBottom <= 0) startBottom = measureRowHeight(table, rowIndex + 1);

    function onMove(e) {
      var delta = e.clientY - startY;
      var top = Math.round(Math.max(20, startTop + delta));
      var bottom = Math.round(Math.max(20, startBottom - delta));
      elData.row_heights[rowIndex] = top;
      elData.row_heights[rowIndex + 1] = bottom;
      applyTableSizes(table, elData);
      refreshTableSelectionDom(elData);
    }

    function onUp() {
      document.removeEventListener("mousemove", onMove);
      document.removeEventListener("mouseup", onUp);
      document.body.classList.remove("forms-table-resizing", "forms-table-resizing--row");
      scheduleSave();
    }

    document.addEventListener("mousemove", onMove);
    document.addEventListener("mouseup", onUp);
  }

  function findMasterCell(elData, r, c) {
    normalizeTableCells(elData);
    for (var rr = 0; rr <= r; rr++) {
      for (var cc = 0; cc <= c; cc++) {
        var cell = elData.cells[rr][cc];
        if (!cell || cell.hidden) continue;
        if (r >= rr && r < rr + cell.rowspan && c >= cc && c < cc + cell.colspan) {
          return { r: rr, c: cc, cell: cell };
        }
      }
    }
    return { r: r, c: c, cell: elData.cells[r][c] };
  }

  function getTableSel(elData) {
    return tableSelection[elData.id] || null;
  }

  function setTableSel(elData, r, c, extend) {
    if (!extend || !tableSelection[elData.id]) {
      tableSelection[elData.id] = { r1: r, c1: c, r2: r, c2: c };
      return;
    }
    var sel = tableSelection[elData.id];
    sel.r2 = r;
    sel.c2 = c;
  }

  function isCellInSelection(elData, r, c) {
    var sel = getTableSel(elData);
    if (!sel) return false;
    var r1 = Math.min(sel.r1, sel.r2);
    var r2 = Math.max(sel.r1, sel.r2);
    var c1 = Math.min(sel.c1, sel.c2);
    var c2 = Math.max(sel.c1, sel.c2);
    return r >= r1 && r <= r2 && c >= c1 && c <= c2;
  }

  function selectionIsRectangle(elData) {
    var sel = getTableSel(elData);
    if (!sel) return false;
    return sel.r1 !== sel.r2 || sel.c1 !== sel.c2;
  }

  function mergeSelectedCells(elData) {
    var sel = getTableSel(elData);
    if (!sel) return;
    normalizeTableCells(elData);
    var r1 = Math.min(sel.r1, sel.r2);
    var r2 = Math.max(sel.r1, sel.r2);
    var c1 = Math.min(sel.c1, sel.c2);
    var c2 = Math.max(sel.c1, sel.c2);
    if (r1 === r2 && c1 === c2) return;

    for (var r = r1; r <= r2; r++) {
      for (var c = c1; c <= c2; c++) {
        var m = findMasterCell(elData, r, c);
        if (m.r < r1 || m.c < c1 || m.r + m.cell.rowspan - 1 > r2 || m.c + m.cell.colspan - 1 > c2) {
          alert("Выделите прямоугольник без уже объединённых ячеек.");
          return;
        }
      }
    }

    var master = elData.cells[r1][c1];
    master.colspan = c2 - c1 + 1;
    master.rowspan = r2 - r1 + 1;
    master.hidden = false;
    for (var rr = r1; rr <= r2; rr++) {
      for (var cc = c1; cc <= c2; cc++) {
        if (rr === r1 && cc === c1) continue;
        elData.cells[rr][cc] = makeCell("");
        elData.cells[rr][cc].hidden = true;
      }
    }
    tableSelection[elData.id] = { r1: r1, c1: c1, r2: r1, c2: c1 };
    scheduleSave();
    renderCanvas();
  }

  function splitSelectedCell(elData) {
    var sel = getTableSel(elData);
    if (!sel) return;
    normalizeTableCells(elData);
    var r = Math.min(sel.r1, sel.r2);
    var c = Math.min(sel.c1, sel.c2);
    var m = findMasterCell(elData, r, c);
    var rEnd = m.r + m.cell.rowspan - 1;
    var cEnd = m.c + m.cell.colspan - 1;
    if (m.cell.colspan === 1 && m.cell.rowspan === 1) return;
    for (var rr = m.r; rr <= rEnd; rr++) {
      for (var cc = m.c; cc <= cEnd; cc++) {
        var cl = elData.cells[rr][cc];
        cl.hidden = false;
        cl.colspan = 1;
        cl.rowspan = 1;
        cl.bg = cl.bg || TABLE_DEFAULT_BG;
        if (rr !== m.r || cc !== m.c) cl.text = "";
      }
    }
    tableSelection[elData.id] = { r1: m.r, c1: m.c, r2: m.r, c2: m.c };
    scheduleSave();
    renderCanvas();
  }

  function copyCellContent(from, to) {
    if (!from || !to) return;
    to.text = from.text || "";
    to.bg = from.bg || TABLE_DEFAULT_BG;
    to.align = from.align;
    to.font_size = from.font_size;
    to.bold = from.bold;
    to.italic = from.italic;
    to.underline = from.underline;
    ensureCellFormat(to);
  }

  function promoteRowspanMaster(elData, delR, m) {
    var nextR = delR + 1;
    if (nextR >= elData.rows) return;
    var rs = m.cell.rowspan || 1;
    var cs = m.cell.colspan || 1;
    var masterCell = elData.cells[nextR][m.c];
    copyCellContent(m.cell, masterCell);
    masterCell.colspan = cs;
    masterCell.rowspan = rs - 1;
    masterCell.hidden = false;
    for (var rr = nextR; rr < nextR + rs - 1; rr++) {
      for (var cc = m.c; cc < m.c + cs; cc++) {
        if (rr === nextR && cc === m.c) continue;
        elData.cells[rr][cc] = makeCell("");
        elData.cells[rr][cc].hidden = true;
      }
    }
  }

  function deleteRowAt(elData, delR) {
    if (elData.rows <= 1) return;
    normalizeTableCells(elData);
    var seen = {};
    for (var c = 0; c < elData.cols; c++) {
      var m = findMasterCell(elData, delR, c);
      var key = m.r + "," + m.c;
      if (seen[key]) continue;
      seen[key] = true;
      if (m.r === delR) {
        if (m.cell.rowspan > 1) promoteRowspanMaster(elData, delR, m);
      } else if (m.r < delR && m.r + m.cell.rowspan - 1 >= delR) {
        m.cell.rowspan -= 1;
      }
    }
    elData.cells.splice(delR, 1);
    if (Array.isArray(elData.row_heights)) elData.row_heights.splice(delR, 1);
    elData.rows -= 1;
    normalizeTableCells(elData);
  }

  function deleteSelectedRows(elData) {
    var sel = getTableSel(elData);
    if (!sel) return;
    normalizeTableCells(elData);
    var r1 = Math.min(sel.r1, sel.r2);
    var r2 = Math.max(sel.r1, sel.r2);
    var count = r2 - r1 + 1;
    if (elData.rows - count < 1) {
      alert("Нельзя удалить все строки таблицы.");
      return;
    }
    captureEditorState();
    for (var r = r2; r >= r1; r--) deleteRowAt(elData, r);
    var c = Math.min(sel.c1, sel.c2);
    var newR = Math.min(r1, elData.rows - 1);
    tableSelection[elData.id] = { r1: newR, c1: c, r2: newR, c2: c };
    scheduleSave();
    renderCanvas();
  }

  function applyBgToSelection(elData, color) {
    var sel = getTableSel(elData);
    if (!sel) return;
    normalizeTableCells(elData);
    var r1 = Math.min(sel.r1, sel.r2);
    var r2 = Math.max(sel.r1, sel.r2);
    var c1 = Math.min(sel.c1, sel.c2);
    var c2 = Math.max(sel.c1, sel.c2);
    var seen = {};
    for (var r = r1; r <= r2; r++) {
      for (var c = c1; c <= c2; c++) {
        var m = findMasterCell(elData, r, c);
        var key = m.r + "," + m.c;
        if (seen[key]) continue;
        seen[key] = true;
        m.cell.bg = color || TABLE_DEFAULT_BG;
      }
    }
    scheduleSave();
    renderCanvas();
  }

  function buildTableToolbar(elData) {
    var bar = document.createElement("div");
    bar.className = "forms-table-toolbar";
    if (!canEdit) return bar;

    var hint = document.createElement("span");
    hint.className = "forms-table-toolbar-hint";
    hint.textContent = "Клик — выбор, Shift+клик — диапазон, край ячейки — размер";
    bar.appendChild(hint);

    var btnMerge = document.createElement("button");
    btnMerge.type = "button";
    btnMerge.className = "forms-add-btn js-forms-table-merge";
    btnMerge.textContent = "Объединить";
    btnMerge.disabled = !selectionIsRectangle(elData);
    btnMerge.addEventListener("click", function () { mergeSelectedCells(elData); });
    bar.appendChild(btnMerge);

    var btnSplit = document.createElement("button");
    btnSplit.type = "button";
    btnSplit.className = "forms-add-btn";
    btnSplit.textContent = "Разъединить";
    btnSplit.addEventListener("click", function () { splitSelectedCell(elData); });
    bar.appendChild(btnSplit);

    var btnDelRow = document.createElement("button");
    btnDelRow.type = "button";
    btnDelRow.className = "forms-add-btn js-forms-table-del-row";
    btnDelRow.textContent = "Удалить строку";
    btnDelRow.title = "Удалить выбранные строки";
    btnDelRow.addEventListener("click", function () { deleteSelectedRows(elData); });
    bar.appendChild(btnDelRow);

    var colorLabel = document.createElement("label");
    colorLabel.title = "Цвет фона выбранных ячеек";
    var colorText = document.createElement("span");
    colorText.textContent = "Фон:";
    var colorInput = document.createElement("input");
    colorInput.type = "color";
    colorInput.className = "forms-table-color-input";
    colorInput.value = TABLE_DEFAULT_BG;
    colorInput.addEventListener("input", function () {
      applyBgToSelection(elData, colorInput.value);
    });
    colorLabel.appendChild(colorText);
    colorLabel.appendChild(colorInput);
    bar.appendChild(colorLabel);

    var colWidthLabel = document.createElement("label");
    colWidthLabel.className = "forms-table-size-field";
    colWidthLabel.title = "Ширина выбранного столбца, %";
    var colWidthText = document.createElement("span");
    colWidthText.textContent = "Столбец, %:";
    var colWidthInput = document.createElement("input");
    colWidthInput.type = "number";
    colWidthInput.className = "forms-table-size-input js-forms-table-col-width";
    colWidthInput.min = "5";
    colWidthInput.max = "95";
    colWidthInput.step = "0.1";
    colWidthInput.addEventListener("change", function () {
      var sel = getTableSel(elData);
      if (!sel) return;
      var c = Math.min(sel.c1, sel.c2);
      setColWidth(elData, c, parseFloat(colWidthInput.value));
      var elWrap = sheetInnerEl && sheetInnerEl.querySelector('.forms-el[data-el-id="' + elData.id + '"]');
      var table = elWrap && elWrap.querySelector(".forms-el-table");
      if (table) applyTableSizes(table, elData);
      refreshTableSelectionDom(elData);
      scheduleSave();
    });
    colWidthLabel.appendChild(colWidthText);
    colWidthLabel.appendChild(colWidthInput);
    bar.appendChild(colWidthLabel);

    var rowHeightLabel = document.createElement("label");
    rowHeightLabel.className = "forms-table-size-field";
    rowHeightLabel.title = "Высота выбранной строки, px (пусто — авто)";
    var rowHeightText = document.createElement("span");
    rowHeightText.textContent = "Строка, px:";
    var rowHeightInput = document.createElement("input");
    rowHeightInput.type = "number";
    rowHeightInput.className = "forms-table-size-input js-forms-table-row-height";
    rowHeightInput.min = "0";
    rowHeightInput.max = "300";
    rowHeightInput.step = "1";
    rowHeightInput.placeholder = "авто";
    function applyRowHeightFromInput() {
      var sel = getTableSel(elData);
      if (!sel) return;
      var r = Math.min(sel.r1, sel.r2);
      var raw = rowHeightInput.value.trim();
      setRowHeight(elData, r, raw === "" ? 0 : parseInt(raw, 10));
      var elWrap = sheetInnerEl && sheetInnerEl.querySelector('.forms-el[data-el-id="' + elData.id + '"]');
      var table = elWrap && elWrap.querySelector(".forms-el-table");
      if (table) applyTableSizes(table, elData);
      refreshTableSelectionDom(elData);
      scheduleSave();
    }
    rowHeightInput.addEventListener("input", applyRowHeightFromInput);
    rowHeightInput.addEventListener("change", applyRowHeightFromInput);
    rowHeightLabel.appendChild(rowHeightText);
    rowHeightLabel.appendChild(rowHeightInput);
    bar.appendChild(rowHeightLabel);

    var fmtGroup = document.createElement("div");
    fmtGroup.className = "forms-table-fmt-group";
    fmtGroup.setAttribute("role", "group");
    fmtGroup.setAttribute("aria-label", "Формат текста ячейки");

    function mkFmtBtn(label, title, className, onClick) {
      var b = document.createElement("button");
      b.type = "button";
      b.className = "forms-table-fmt-btn " + className;
      b.textContent = label;
      b.title = title;
      b.addEventListener("click", function () {
        onClick();
        updateTableCellFormatDom(elData);
        refreshTableSelectionDom(elData);
        scheduleSave();
      });
      return b;
    }

    var alignLabels = { left: "◧", center: "☰", right: "◨" };
    var alignTitles = { left: "Слева", center: "По центру", right: "Справа" };
    ["left", "center", "right"].forEach(function (align) {
      var btn = mkFmtBtn(alignLabels[align], alignTitles[align], "js-forms-cell-align", function () {
        forEachSelectedMasterCell(elData, function (cell) { cell.align = align; });
      });
      btn.setAttribute("data-align", align);
      fmtGroup.appendChild(btn);
    });

    fmtGroup.appendChild(mkFmtBtn("B", "Жирный", "js-forms-cell-bold", function () {
      var primary = primarySelectedCell(elData);
      var next = primary ? !primary.cell.bold : true;
      forEachSelectedMasterCell(elData, function (cell) { cell.bold = next; });
    }));

    fmtGroup.appendChild(mkFmtBtn("I", "Курсив", "js-forms-cell-italic forms-table-fmt-btn--italic", function () {
      var primary = primarySelectedCell(elData);
      var next = primary ? !primary.cell.italic : true;
      forEachSelectedMasterCell(elData, function (cell) { cell.italic = next; });
    }));

    fmtGroup.appendChild(mkFmtBtn("U", "Подчёркивание", "js-forms-cell-underline forms-table-fmt-btn--underline", function () {
      var primary = primarySelectedCell(elData);
      var next = primary ? !primary.cell.underline : true;
      forEachSelectedMasterCell(elData, function (cell) { cell.underline = next; });
    }));

    var fontSizeLabel = document.createElement("label");
    fontSizeLabel.className = "forms-table-size-field";
    fontSizeLabel.title = "Размер шрифта выбранной ячейки, pt";
    var fontSizeText = document.createElement("span");
    fontSizeText.textContent = "Шрифт, pt:";
    var fontSizeInput = document.createElement("input");
    fontSizeInput.type = "number";
    fontSizeInput.className = "forms-table-size-input js-forms-cell-font-size";
    fontSizeInput.min = "8";
    fontSizeInput.max = "48";
    fontSizeInput.step = "1";
    function applyFontSizeFromInput() {
      var fs = normCellFontSize(fontSizeInput.value);
      forEachSelectedMasterCell(elData, function (cell) { cell.font_size = fs; });
      fontSizeInput.value = String(fs);
      updateTableCellFormatDom(elData);
      refreshTableSelectionDom(elData);
      scheduleSave();
    }
    fontSizeInput.addEventListener("input", applyFontSizeFromInput);
    fontSizeInput.addEventListener("change", applyFontSizeFromInput);
    fontSizeLabel.appendChild(fontSizeText);
    fontSizeLabel.appendChild(fontSizeInput);
    fmtGroup.appendChild(fontSizeLabel);
    bar.appendChild(fmtGroup);

    return bar;
  }

  function refreshTableToolbarControls(elData) {
    if (!tableToolbarHost || !elData) return;
    var mergeBtn = tableToolbarHost.querySelector(".js-forms-table-merge");
    if (mergeBtn) mergeBtn.disabled = !selectionIsRectangle(elData);
    var sel = getTableSel(elData);
    var delRowBtn = tableToolbarHost.querySelector(".js-forms-table-del-row");
    if (delRowBtn && sel) {
      var dr1 = Math.min(sel.r1, sel.r2);
      var dr2 = Math.max(sel.r1, sel.r2);
      delRowBtn.disabled = elData.rows - (dr2 - dr1 + 1) < 1;
      delRowBtn.textContent = dr2 > dr1 ? "Удалить строки" : "Удалить строку";
    } else if (delRowBtn) {
      delRowBtn.disabled = true;
      delRowBtn.textContent = "Удалить строку";
    }
    var colInput = tableToolbarHost.querySelector(".js-forms-table-col-width");
    var rowInput = tableToolbarHost.querySelector(".js-forms-table-row-height");
    if (sel && colInput && rowInput) {
      normalizeTableSizes(elData);
      var c = Math.min(sel.c1, sel.c2);
      var r = Math.min(sel.r1, sel.r2);
      colInput.value = String(elData.col_widths[c]);
      rowInput.value = elData.row_heights[r] > 0 ? String(elData.row_heights[r]) : "";
    }
    var primary = primarySelectedCell(elData);
    var fontInput = tableToolbarHost.querySelector(".js-forms-cell-font-size");
    if (primary && primary.cell) {
      ensureCellFormat(primary.cell);
      if (fontInput) fontInput.value = String(primary.cell.font_size);
      tableToolbarHost.querySelectorAll(".js-forms-cell-align").forEach(function (btn) {
        btn.classList.toggle("is-active", btn.getAttribute("data-align") === primary.cell.align);
      });
      var boldBtn = tableToolbarHost.querySelector(".js-forms-cell-bold");
      var italicBtn = tableToolbarHost.querySelector(".js-forms-cell-italic");
      var underlineBtn = tableToolbarHost.querySelector(".js-forms-cell-underline");
      if (boldBtn) boldBtn.classList.toggle("is-active", !!primary.cell.bold);
      if (italicBtn) italicBtn.classList.toggle("is-active", !!primary.cell.italic);
      if (underlineBtn) underlineBtn.classList.toggle("is-active", !!primary.cell.underline);
    } else {
      if (fontInput) fontInput.value = "";
      tableToolbarHost.querySelectorAll(".js-forms-cell-align, .js-forms-cell-bold, .js-forms-cell-italic, .js-forms-cell-underline").forEach(function (btn) {
        btn.classList.remove("is-active");
      });
    }
  }

  function syncTableToolbar(elData, forceRebuild) {
    if (!tablePropsBlock || !tableToolbarHost) return;
    if (!canEdit || !elData || elData.type !== "table" || !getTableSel(elData)) {
      activeTableId = null;
      setPanelVisible(tablePropsBlock, false);
      tableToolbarHost.innerHTML = "";
      return;
    }
    var rebuild = !!forceRebuild || activeTableId !== elData.id || !tableToolbarHost.firstChild;
    activeTableId = elData.id;
    setPanelVisible(tablePropsBlock, true);
    if (rebuild) {
      tableToolbarHost.innerHTML = "";
      tableToolbarHost.appendChild(buildTableToolbar(elData));
    }
    refreshTableToolbarControls(elData);
  }

  function renderTableElement(elData, wrap) {
    normalizeTableCells(elData);

    var tableWrap = document.createElement("div");
    tableWrap.className = "forms-el-table-wrap";
    var table = document.createElement("table");
    table.className = "forms-el-table";

    for (var ri = 0; ri < elData.rows; ri++) {
      var tr = document.createElement("tr");
      for (var ci = 0; ci < elData.cols; ci++) {
        var cellData = elData.cells[ri][ci];
        if (!cellData || cellData.hidden) continue;

        var td = document.createElement("td");
        td.dataset.row = String(ri);
        td.dataset.col = String(ci);
        if (cellData.colspan > 1) td.colSpan = cellData.colspan;
        if (cellData.rowspan > 1) td.rowSpan = cellData.rowspan;
        td.style.backgroundColor = cellData.bg || TABLE_DEFAULT_BG;

        if (isCellInSelection(elData, ri, ci)) td.classList.add("is-selected");

        var cell = document.createElement("textarea");
        cell.rows = 2;
        cell.className = "forms-el-table-cell";
        cell.value = cellData.text || "";
        if (!canEdit) cell.readOnly = true;
        applyCellTextStyles(cell, cellData);
        (function (rr, cc, inp, data) {
          inp.addEventListener("input", function () {
            data.text = inp.value;
            scheduleSave();
          });
          if (canEdit) {
            inp.addEventListener("mousedown", function (ev) {
              if (ev.shiftKey) {
                ev.preventDefault();
                setTableSel(elData, rr, cc, true);
                syncTableToolbar(elData);
                refreshTableSelectionDom(elData);
              } else {
                setTableSel(elData, rr, cc, false);
                syncTableToolbar(elData);
                refreshTableSelectionDom(elData);
              }
            });
          }
        })(ri, ci, cell, cellData);

        td.appendChild(cell);
        tr.appendChild(td);
      }
      table.appendChild(tr);
    }

    applyTableSizes(table, elData);
    bindTableResizeEvents(table, elData);
    tableWrap.appendChild(table);
    wrap.appendChild(tableWrap);
  }

  function refreshTableSelectionDom(elData) {
    var elWrap = sheetInnerEl && sheetInnerEl.querySelector('.forms-el[data-el-id="' + elData.id + '"]');
    if (!elWrap) return;
    elWrap.querySelectorAll(".forms-el-table td").forEach(function (td) {
      var r = parseInt(td.getAttribute("data-row") || "", 10);
      var c = parseInt(td.getAttribute("data-col") || "", 10);
      if (isNaN(r) || isNaN(c)) return;
      td.classList.toggle("is-selected", isCellInSelection(elData, r, c));
    });
    if (elData.id === activeTableId) refreshTableToolbarControls(elData);
  }

  function apiDetailUrl(id) {
    return apiDetailTpl.replace(/\/0\/?$/, "/" + id + "/");
  }

  function getCookie(name) {
    var parts = ("; " + document.cookie).split("; " + name + "=");
    if (parts.length === 2) return parts.pop().split(";").shift() || "";
    return "";
  }

  function uid() {
    return "el-" + Date.now().toString(36) + "-" + Math.random().toString(36).slice(2, 8);
  }

  function currentForm() {
    for (var i = 0; i < forms.length; i++) {
      if (forms[i].id === currentId) return forms[i];
    }
    return null;
  }

  function fetchJson(url, options) {
    var opts = options || {};
    opts.headers = opts.headers || {};
    opts.headers["X-Requested-With"] = "XMLHttpRequest";
    if (opts.body && typeof opts.body === "object" && !(opts.body instanceof FormData)) {
      opts.headers["Content-Type"] = "application/json";
      opts.body = JSON.stringify(opts.body);
    }
    if (opts.method && opts.method !== "GET") {
      opts.headers["X-CSRFToken"] = getCookie("csrftoken");
    }
    return fetch(url, opts).then(function (r) {
      return r.json().then(function (data) {
        if (!r.ok || !data.ok) {
          var err = (data && data.error) || "Ошибка запроса";
          throw new Error(err);
        }
        return data;
      });
    });
  }

  function captureEditorState() {
    var form = currentForm();
    if (!form || !sheetInnerEl) return;
    var byId = {};
    (form.elements || []).forEach(function (el) {
      if (el && el.id) byId[el.id] = el;
    });

    sheetInnerEl.querySelectorAll(".forms-el[data-el-id]").forEach(function (wrap) {
      var elData = byId[wrap.getAttribute("data-el-id") || ""];
      if (!elData) return;
      if (elData.type === "heading") {
        var h = wrap.querySelector(".forms-el-heading");
        if (h) elData.text = h.value;
      } else if (elData.type === "text") {
        var ta = wrap.querySelector(".forms-el-text");
        if (ta) elData.text = ta.value;
      } else if (elData.type === "checkbox") {
        var lbl = wrap.querySelector(".forms-el-checkbox-label");
        var box = wrap.querySelector(".forms-el-checkbox-box");
        if (lbl) elData.label = lbl.value;
        if (box) elData.checked = box.classList.contains("is-checked");
      } else if (elData.type === "date" || elData.type === "fio") {
        var dl = wrap.querySelector(".forms-el-field-label");
        var dv = wrap.querySelector(".forms-el-field-value");
        if (dl) elData.label = dl.value;
        if (dv) elData.value = dv.value;
      } else if (elData.type === "item") {
        var dn = wrap.querySelector(".forms-el-field-num");
        var dlItem = wrap.querySelector(".forms-el-field-label");
        var dvItem = wrap.querySelector(".forms-el-field-value");
        if (dn) elData.num = dn.value;
        if (dlItem) elData.label = dlItem.value;
        if (dvItem) elData.value = dvItem.value;
      } else if (elData.type === "list") {
        var inputs = wrap.querySelectorAll(".forms-el-list-input");
        elData.items = [];
        inputs.forEach(function (inp) {
          elData.items.push(inp.value);
        });
      } else if (elData.type === "table") {
        wrap.querySelectorAll(".forms-el-table td").forEach(function (td) {
          var r = parseInt(td.getAttribute("data-row") || "", 10);
          var c = parseInt(td.getAttribute("data-col") || "", 10);
          var cellTa = td.querySelector("textarea");
          if (!cellTa || isNaN(r) || isNaN(c)) return;
          if (!elData.cells[r]) elData.cells[r] = [];
          if (!elData.cells[r][c] || typeof elData.cells[r][c] !== "object") {
            elData.cells[r][c] = makeCell(cellTa.value);
          } else {
            elData.cells[r][c].text = cellTa.value;
          }
        });
      }
    });
  }

  function applySavedForm(saved, replaceElements) {
    var idx = forms.findIndex(function (f) { return f.id === saved.id; });
    if (idx < 0) return;
    if (replaceElements) {
      forms[idx] = saved;
      return;
    }
    var cur = forms[idx];
    cur.name = saved.name;
    cur.orientation = normOrientation(saved.orientation);
    cur.show_border = saved.show_border;
    cur.page_settings = saved.page_settings;
    cur.updated_at = saved.updated_at;
  }

  function saveFormById(formId, replaceElementsOnSuccess) {
    if (!canEdit || !formId) return Promise.resolve();
    var form = null;
    for (var i = 0; i < forms.length; i++) {
      if (forms[i].id === formId) {
        form = forms[i];
        break;
      }
    }
    if (!form) return Promise.resolve();
    if (formId === currentId) captureEditorState();

    var seq = ++saveSeq;
    return fetchJson(apiDetailUrl(formId), {
      method: "PATCH",
      body: {
        name: form.name,
        orientation: form.orientation,
        show_border: form.show_border,
        page_settings: ensureFormPageSettings(form),
        elements: form.elements,
      },
    }).then(function (data) {
      if (seq !== saveSeq) return;
      applySavedForm(data.form, !!replaceElementsOnSuccess || currentId !== data.form.id);
      if (currentId === data.form.id) applySheetOrientation(currentForm());
      renderList();
    }).catch(function (e) {
      console.error(e);
      alert(e.message || "Не удалось сохранить форму");
    });
  }

  function scheduleSave() {
    if (!canEdit || !currentId) return;
    clearTimeout(saveTimer);
    saveTimer = setTimeout(function () {
      saveTimer = null;
      saveFormById(currentId, false);
    }, 500);
  }

  function flushSave() {
    clearTimeout(saveTimer);
    saveTimer = null;
    captureEditorState();
    if (!currentId) return Promise.resolve();
    return saveFormById(currentId, false);
  }

  function renderList() {
    listEl.innerHTML = "";
    forms.forEach(function (f) {
      var li = document.createElement("li");
      li.className = "forms-list-item";

      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "forms-list-btn" + (f.id === currentId ? " is-active" : "");
      btn.textContent = f.name || "Без названия";
      btn.addEventListener("click", function () { selectForm(f.id); });

      li.appendChild(btn);

      if (canEdit) {
        var del = document.createElement("button");
        del.type = "button";
        del.className = "forms-list-del";
        del.title = "Удалить";
        del.setAttribute("aria-label", "Удалить форму");
        del.textContent = "×";
        del.addEventListener("click", function (e) {
          e.stopPropagation();
          deleteForm(f.id);
        });
        li.appendChild(del);
      }

      listEl.appendChild(li);
    });
  }

  function showFormUi(form) {
    if (!form) {
      setActiveHeading(null);
      syncTableToolbar(null);
      setPanelVisible(emptyEl, true);
      setPanelVisible(editorEl, false);
      setPanelVisible(propsPanel, false);
      if (printBtn) printBtn.disabled = true;
      renderList();
      return;
    }
    setActiveHeading(null);
    syncTableToolbar(null);
    setPanelVisible(emptyEl, false);
    setPanelVisible(editorEl, true);
    setPanelVisible(propsPanel, true);
    if (printBtn) printBtn.disabled = false;

    if (nameInput) nameInput.value = form.name || "";
    if (orientationSelect) orientationSelect.value = form.orientation || "portrait";
    syncBorderPanelUi(form);
    updateSheetScalerWidth(form);
    renderCanvas();
    renderList();
  }

  function selectForm(id) {
    if (id === currentId) {
      renderList();
      return;
    }
    clearTimeout(saveTimer);
    saveTimer = null;
    captureEditorState();

    var prevId = currentId;
    var doSwitch = function () {
      currentId = id;
      showFormUi(currentForm());
    };

    if (canEdit && prevId) {
      saveFormById(prevId, true).then(doSwitch);
    } else {
      doSwitch();
    }
  }

  function elToolbar(elData, index) {
    var bar = document.createElement("div");
    bar.className = "forms-el-toolbar";
    if (!canEdit) return bar;

    function mkBtn(label, title, fn) {
      var b = document.createElement("button");
      b.type = "button";
      b.className = "forms-el-btn";
      b.textContent = label;
      b.title = title;
      b.addEventListener("click", fn);
      return b;
    }

    bar.appendChild(mkBtn("↑", "Выше", function () {
      if (index <= 0) return;
      var form = currentForm();
      var tmp = form.elements[index - 1];
      form.elements[index - 1] = form.elements[index];
      form.elements[index] = tmp;
      renderCanvas();
      scheduleSave();
    }));
    bar.appendChild(mkBtn("↓", "Ниже", function () {
      var form = currentForm();
      if (index >= form.elements.length - 1) return;
      var tmp = form.elements[index + 1];
      form.elements[index + 1] = form.elements[index];
      form.elements[index] = tmp;
      renderCanvas();
      scheduleSave();
    }));
    bar.appendChild(mkBtn("×", "Удалить", function () {
      var form = currentForm();
      form.elements.splice(index, 1);
      renderCanvas();
      scheduleSave();
    }));
    return bar;
  }

  function autoGrowTextarea(ta) {
    if (!ta) return;
    if (!ta.isConnected) {
      requestAnimationFrame(function () { autoGrowTextarea(ta); });
      return;
    }
    var style = window.getComputedStyle(ta);
    var lineHeight = parseFloat(style.lineHeight);
    if (!lineHeight || isNaN(lineHeight)) {
      lineHeight = (parseFloat(style.fontSize) || 14) * 1.35;
    }
    var minH = Math.ceil(lineHeight);
    if (!ta.value) {
      ta.style.height = minH + "px";
      return;
    }
    ta.style.height = minH + "px";
    ta.style.height = Math.max(minH, ta.scrollHeight) + "px";
  }

  function bindTextInput(input, elData, key) {
    function sync() {
      elData[key] = input.value;
      scheduleSave();
    }
    input.addEventListener("input", sync);
    input.addEventListener("change", sync);
    input.addEventListener("blur", function () {
      elData[key] = input.value;
      flushSave();
    });
  }

  function renderElement(elData, index) {
    var wrap = document.createElement("div");
    wrap.className = "forms-el";
    wrap.dataset.elId = elData.id;
    wrap.appendChild(elToolbar(elData, index));

    if (elData.type === "heading") {
      ensureHeadingFields(elData);
      var h = document.createElement("textarea");
      h.className = "forms-el-heading";
      h.rows = 1;
      h.value = elData.text || "";
      h.placeholder = "Заголовок";
      if (!canEdit) h.readOnly = true;
      applyHeadingStyles(h, elData);
      bindTextInput(h, elData, "text");
      h.addEventListener("input", function () { autoGrowTextarea(h); });
      wrap.appendChild(h);
      autoGrowTextarea(h);
    } else if (elData.type === "text") {
      var ta = document.createElement("textarea");
      ta.className = "forms-el-text";
      ta.value = elData.text || "";
      ta.placeholder = "Текстовый блок";
      if (!canEdit) ta.readOnly = true;
      bindTextInput(ta, elData, "text");
      wrap.appendChild(ta);
    } else if (elData.type === "table") {
      renderTableElement(elData, wrap);
    } else if (elData.type === "checkbox") {
      var row = document.createElement("div");
      row.className = "forms-el-checkbox";
      var box = document.createElement("div");
      box.className = "forms-el-checkbox-box" + (elData.checked ? " is-checked" : "");
      box.setAttribute("role", "checkbox");
      box.setAttribute("aria-checked", elData.checked ? "true" : "false");
      if (canEdit) {
        box.addEventListener("click", function () {
          elData.checked = !elData.checked;
          box.classList.toggle("is-checked", elData.checked);
          box.setAttribute("aria-checked", elData.checked ? "true" : "false");
          scheduleSave();
        });
      }
      var lbl = document.createElement("textarea");
      lbl.className = "forms-el-checkbox-label";
      lbl.rows = 1;
      lbl.value = elData.label || "";
      lbl.placeholder = "Подпись к галочке";
      if (!canEdit) lbl.readOnly = true;
      bindTextInput(lbl, elData, "label");
      lbl.addEventListener("input", function () { autoGrowTextarea(lbl); });
      row.appendChild(box);
      row.appendChild(lbl);
      wrap.appendChild(row);
      autoGrowTextarea(lbl);
    } else if (elData.type === "list") {
      var listTag = elData.ordered ? "ol" : "ul";
      var listNode = document.createElement(listTag);
      listNode.className = "forms-el-list";
      if (!elData.items || !elData.items.length) elData.items = [""];
      elData.items.forEach(function (itemText, ii) {
        var li = document.createElement("li");
        var inp = document.createElement("input");
        inp.type = "text";
        inp.className = "forms-el-list-input";
        inp.value = itemText || "";
        if (!canEdit) inp.readOnly = true;
        (function (idx, input) {
          input.addEventListener("input", function () {
            elData.items[idx] = input.value;
            scheduleSave();
          });
        })(ii, inp);
        li.appendChild(inp);
        listNode.appendChild(li);
      });
      wrap.appendChild(listNode);
    } else if (elData.type === "date" || elData.type === "fio") {
      var fieldRow = document.createElement("div");
      fieldRow.className = "forms-el-field forms-el-field--" + elData.type;
      var fieldLabel = document.createElement("input");
      fieldLabel.type = "text";
      fieldLabel.className = "forms-el-field-label";
      fieldLabel.value = elData.label || (elData.type === "fio" ? "ФИО:" : "Дата:");
      fieldLabel.placeholder = "Подпись";
      if (!canEdit) fieldLabel.readOnly = true;
      bindTextInput(fieldLabel, elData, "label");
      var fieldValue = document.createElement("input");
      fieldValue.type = "text";
      fieldValue.className = "forms-el-field-value";
      fieldValue.value = elData.value || "";
      fieldValue.placeholder = elData.placeholder || (
        elData.type === "fio" ? "Фамилия Имя Отчество" : "дд.мм.гггг"
      );
      if (!canEdit) fieldValue.readOnly = true;
      bindTextInput(fieldValue, elData, "value");
      fieldRow.appendChild(fieldLabel);
      fieldRow.appendChild(fieldValue);
      wrap.appendChild(fieldRow);
    } else if (elData.type === "item") {
      var itemRow = document.createElement("div");
      itemRow.className = "forms-el-field forms-el-field--item";
      var itemNum = document.createElement("input");
      itemNum.type = "text";
      itemNum.className = "forms-el-field-num";
      itemNum.value = elData.num || "1.";
      itemNum.placeholder = "1.";
      itemNum.title = "Номер";
      if (!canEdit) itemNum.readOnly = true;
      bindTextInput(itemNum, elData, "num");
      var itemLabel = document.createElement("input");
      itemLabel.type = "text";
      itemLabel.className = "forms-el-field-label";
      itemLabel.value = elData.label || "";
      itemLabel.placeholder = "Текст пункта";
      if (!canEdit) itemLabel.readOnly = true;
      bindTextInput(itemLabel, elData, "label");
      var itemValue = document.createElement("input");
      itemValue.type = "text";
      itemValue.className = "forms-el-field-value";
      itemValue.value = elData.value || "";
      itemValue.placeholder = elData.placeholder || "";
      if (!canEdit) itemValue.readOnly = true;
      bindTextInput(itemValue, elData, "value");
      itemRow.appendChild(itemNum);
      itemRow.appendChild(itemLabel);
      itemRow.appendChild(itemValue);
      wrap.appendChild(itemRow);
    } else if (elData.type === "line") {
      var hr = document.createElement("hr");
      hr.className = "forms-el-line";
      wrap.appendChild(hr);
    }

    return wrap;
  }

  function renderCanvas() {
    var form = currentForm();
    if (!form) return;
    captureEditorState();
    sheetInnerEl.innerHTML = "";
    (form.elements || []).forEach(function (el, i) {
      sheetInnerEl.appendChild(renderElement(el, i));
    });
    if (activeTableId) {
      var tableEl = findElementById(activeTableId);
      if (tableEl && tableEl.type === "table" && getTableSel(tableEl)) {
        syncTableToolbar(tableEl, true);
        refreshTableSelectionDom(tableEl);
      } else {
        syncTableToolbar(null);
      }
    }
    syncHeadingPropsUi(getActiveHeading());
    scheduleSheetFitScale();
  }

  function openPrompt(title, fieldsHtml) {
    if (!dialogPrompt || !promptTitle || !promptFields) return Promise.resolve(false);
    promptTitle.textContent = title;
    promptFields.innerHTML = fieldsHtml;
    dialogPrompt.showModal();
    return new Promise(function (resolve) {
      promptResolver = resolve;
    });
  }

  function addElement(type) {
    var form = currentForm();
    if (!form) return;

    var el = { id: uid(), type: type };

    if (type === "table") {
      openPrompt("Таблица", (
        '<label class="forms-row"><span class="forms-row-label">Строк</span>' +
        '<input type="number" class="forms-control forms-control--num js-prompt-rows" min="1" max="50" value="3" required></label>' +
        '<label class="forms-row"><span class="forms-row-label">Столбцов</span>' +
        '<input type="number" class="forms-control forms-control--num js-prompt-cols" min="1" max="20" value="4" required></label>'
      )).then(function (ok) {
        if (!ok) return;
        el.rows = parseInt(promptFields.querySelector(".js-prompt-rows").value, 10) || 3;
        el.cols = parseInt(promptFields.querySelector(".js-prompt-cols").value, 10) || 4;
        el.cells = [];
        normalizeTableCells(el);
        form.elements.push(el);
        renderCanvas();
        scheduleSave();
      });
      return;
    }

    if (type === "list") {
      openPrompt("Список", (
        '<label class="forms-row"><span class="forms-row-label">Пунктов</span>' +
        '<input type="number" class="forms-control forms-control--num js-prompt-items" min="1" max="50" value="3" required></label>' +
        '<label class="forms-toggle forms-toggle--dialog">' +
        '<input type="checkbox" class="js-prompt-ordered">' +
        '<span>Нумерованный список</span></label>'
      )).then(function (ok) {
        if (!ok) return;
        var n = parseInt(promptFields.querySelector(".js-prompt-items").value, 10) || 3;
        el.ordered = !!promptFields.querySelector(".js-prompt-ordered").checked;
        el.items = [];
        for (var i = 0; i < n; i++) el.items.push("");
        form.elements.push(el);
        renderCanvas();
        scheduleSave();
      });
      return;
    }

    if (type === "checkbox") {
      el.label = "";
      el.checked = false;
    } else if (type === "date") {
      el.label = "Дата:";
      el.value = "";
      el.placeholder = "дд.мм.гггг";
    } else if (type === "fio") {
      el.label = "ФИО:";
      el.value = "";
      el.placeholder = "Фамилия Имя Отчество";
    } else if (type === "item") {
      el.num = "1.";
      el.label = "";
      el.value = "";
      el.placeholder = "";
    } else if (type === "heading") {
      el.text = "";
      el.align = "left";
      el.font_size = 16;
    } else if (type === "text") {
      el.text = "";
    }

    form.elements.push(el);
    renderCanvas();
    scheduleSave();
  }

  function deleteForm(id) {
    if (!confirm("Удалить эту форму?")) return;
    fetchJson(apiDetailUrl(id), { method: "DELETE" }).then(function () {
      forms = forms.filter(function (f) { return f.id !== id; });
      if (currentId === id) {
        currentId = forms.length ? forms[0].id : null;
      }
      selectForm(currentId);
      renderList();
    }).catch(function (e) {
      alert(e.message || "Не удалось удалить");
    });
  }

  function createForm(ev) {
    if (ev) ev.preventDefault();
    var name = (newNameInput.value || "").trim();
    if (!name) return;
    fetchJson(apiListUrl, {
      method: "POST",
      body: {
        name: name,
        orientation: newOrientationSelect.value,
        show_border: newBorderCheck.checked,
        page_settings: DEFAULT_PAGE_SETTINGS,
      },
    }).then(function (data) {
      data.form.orientation = normOrientation(data.form.orientation);
      forms.push(data.form);
      if (dialogNew) dialogNew.close();
      if (newNameInput) newNameInput.value = "";
      selectForm(data.form.id);
      renderList();
    }).catch(function (e) {
      alert(e.message || "Не удалось создать форму");
    });
  }

  function printForm() {
    var form = currentForm();
    if (!form) return;
    captureEditorState();
    form.orientation = normOrientation(form.orientation);
    printRoot.innerHTML = "";
    var sheet = document.createElement("div");
    sheet.className = "forms-print-sheet";
    sheet.setAttribute("data-orientation", form.orientation);
    var frame = document.createElement("div");
    frame.className = "forms-print-frame";
    var inner = document.createElement("div");
    inner.className = "forms-print-inner";
    (form.elements || []).forEach(function (el, i) {
      inner.appendChild(renderElement(el, i));
    });
    frame.appendChild(inner);
    sheet.appendChild(frame);
    applyPageLayout(form, sheet, frame, inner);
    printRoot.appendChild(sheet);
    printRoot.hidden = false;

    var style = document.createElement("style");
    style.textContent = "@page { size: A4 " + (form.orientation === "landscape" ? "landscape" : "portrait") + "; margin: 0; }";
    document.head.appendChild(style);

    window.print();

    setTimeout(function () {
      document.head.removeChild(style);
      printRoot.hidden = true;
      printRoot.innerHTML = "";
      renderCanvas();
    }, 300);
  }

  function loadForms() {
    fetchJson(apiListUrl).then(function (data) {
      forms = (data.forms || []).map(function (f) {
        f.orientation = normOrientation(f.orientation);
        return f;
      });
      renderList();
      if (forms.length && !currentId) {
        selectForm(forms[0].id);
      }
    }).catch(function (e) {
      console.error(e);
      listEl.innerHTML = "<li style='color:var(--fp-muted);font-size:13px;padding:8px'>Не удалось загрузить формы</li>";
    });
  }

  var btnNew = root.querySelector(".js-forms-new");
  if (btnNew && dialogNew) {
    btnNew.addEventListener("click", function () {
      if (!canEdit) return;
      newNameInput.value = "";
      newOrientationSelect.value = "portrait";
      newBorderCheck.checked = true;
      dialogNew.showModal();
      setTimeout(function () { if (newNameInput) newNameInput.focus(); }, 50);
    });
  }

  var btnDialogCancel = root.querySelector(".js-forms-dialog-cancel");
  if (btnDialogCancel && dialogNew) {
    btnDialogCancel.addEventListener("click", function () {
      dialogNew.close();
    });
  }

  if (dialogNewForm) {
    dialogNewForm.addEventListener("submit", createForm);
  }

  var btnPromptCancel = root.querySelector(".js-forms-prompt-cancel");
  if (btnPromptCancel && dialogPrompt) {
    btnPromptCancel.addEventListener("click", function () {
      if (promptResolver) promptResolver(false);
      promptResolver = null;
      dialogPrompt.close();
    });
  }

  if (promptForm && dialogPrompt) {
    promptForm.addEventListener("submit", function (e) {
      e.preventDefault();
      if (promptResolver) promptResolver(true);
      promptResolver = null;
      dialogPrompt.close();
    });
  }

  root.querySelectorAll(".js-forms-add").forEach(function (btn) {
    btn.addEventListener("click", function () {
      addElement(btn.getAttribute("data-type"));
    });
  });

  root.addEventListener("focusin", function (e) {
    if (headingPropsBlock && headingPropsBlock.contains(e.target)) return;
    if (tablePropsBlock && tablePropsBlock.contains(e.target)) return;
    var wrap = e.target.closest(".forms-el");
    if (!wrap || !sheetInnerEl || !sheetInnerEl.contains(wrap)) {
      setActiveHeading(null);
      syncTableToolbar(null);
      return;
    }
    var elData = findElementById(wrap.getAttribute("data-el-id") || "");
    if (elData && elData.type === "heading") setActiveHeading(elData);
    else setActiveHeading(null);
    if (!elData || elData.type !== "table") syncTableToolbar(null);
  });

  headingAlignBtns.forEach(function (btn) {
    btn.addEventListener("click", function () {
      var elData = getActiveHeading();
      if (!elData) return;
      elData.align = normHeadingAlign(btn.getAttribute("data-align"));
      updateActiveHeadingDom(elData);
      syncHeadingPropsUi(elData);
      scheduleSave();
    });
  });

  if (headingSizeInput) {
    headingSizeInput.addEventListener("input", function () {
      var elData = getActiveHeading();
      if (!elData) return;
      elData.font_size = normHeadingFontSize(headingSizeInput.value);
      updateActiveHeadingDom(elData);
      scheduleSave();
    });
    headingSizeInput.addEventListener("change", function () {
      var elData = getActiveHeading();
      if (!elData) return;
      elData.font_size = normHeadingFontSize(headingSizeInput.value);
      headingSizeInput.value = String(elData.font_size);
      updateActiveHeadingDom(elData);
      flushSave();
    });
  }

  if (nameInput) nameInput.addEventListener("input", function () {
    var form = currentForm();
    if (!form) return;
    form.name = nameInput.value;
    scheduleSave();
    renderList();
  });

  if (orientationSelect) orientationSelect.addEventListener("change", function () {
    var form = currentForm();
    if (!form) return;
    form.orientation = normOrientation(orientationSelect.value);
    if (orientationSelect.value !== form.orientation) orientationSelect.value = form.orientation;
    applySheetOrientation(form);
    syncBorderPanelUi(form);
    scheduleSave();
  });

  if (borderCheck) borderCheck.addEventListener("change", readPageSettingsFromUi);

  [borderInsetInput, marginMmInput, borderWidthInput, borderStyleSelect].forEach(function (el) {
    if (!el) return;
    el.addEventListener("input", function () {
      var form = currentForm();
      if (!form) return;
      readPageSettingsFromUi(form);
    });
    el.addEventListener("change", function () {
      var form = currentForm();
      if (!form) return;
      readPageSettingsFromUi(form);
    });
  });

  if (printBtn) {
    printBtn.addEventListener("click", function () {
      flushSave().then(printForm);
    });
  }

  window.addEventListener("beforeunload", function () {
    if (!canEdit || !currentId) return;
    captureEditorState();
    var form = currentForm();
    if (!form) return;
    try {
      fetch(apiDetailUrl(currentId), {
        method: "PATCH",
        keepalive: true,
        headers: {
          "Content-Type": "application/json",
          "X-Requested-With": "XMLHttpRequest",
          "X-CSRFToken": getCookie("csrftoken"),
        },
        body: JSON.stringify({
          name: form.name,
          orientation: form.orientation,
          show_border: form.show_border,
          page_settings: ensureFormPageSettings(form),
          elements: form.elements,
        }),
      });
    } catch (e) { /* ignore */ }
  });

  if (canvasStage && typeof ResizeObserver !== "undefined") {
    var sheetFitObserver = new ResizeObserver(function () {
      scheduleSheetFitScale();
    });
    sheetFitObserver.observe(canvasStage);
  }

  window.addEventListener("resize", scheduleSheetFitScale);

  loadForms();
})();
