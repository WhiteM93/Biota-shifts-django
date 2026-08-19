(function () {
  "use strict";

  var editor = document.getElementById("cabinet-icon-editor");
  if (!editor) return;

  var titleEl = document.getElementById("cabinet-icon-editor-title");
  var keyEl = document.getElementById("cabinet-icon-editor-key");
  var previewEl = document.getElementById("cabinet-icon-editor-preview");
  var kindEl = document.getElementById("cabinet-icon-editor-kind");
  var valueEl = document.getElementById("cabinet-icon-editor-value");
  var defaultEl = document.getElementById("cabinet-icon-editor-default");
  var closeBtn = document.getElementById("cabinet-icon-editor-close");
  var form = document.getElementById("cabinet-icons-form");

  var activeTile = null;
  var activeFormKey = "";

  function escapeHtml(s) {
    return String(s || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function renderPreview(kind, value) {
    if (kind === "flaticon") {
      return (
        '<i class="' +
        escapeHtml(value + " biota-icon biota-icon--fi") +
        '" aria-hidden="true"></i>'
      );
    }
    if (kind === "hugeicons") {
      return (
        '<img class="biota-icon biota-icon--svg biota-icon--hgi" src="/static/icons/hugeicons/svg/' +
        escapeHtml(value) +
        '.svg" alt="" aria-hidden="true">'
      );
    }
    if (kind === "svg_static") {
      return (
        '<img class="biota-icon biota-icon--svg" src="/static/' +
        escapeHtml(value.replace(/^\/+/, "")) +
        '" alt="" aria-hidden="true">'
      );
    }
    if (kind === "emoji" || kind === "text") {
      return (
        '<span class="biota-icon biota-icon--text" aria-hidden="true">' +
        escapeHtml(value) +
        "</span>"
      );
    }
    return '<span class="cabinet-icon-editor__partial">SVG · ' + escapeHtml(value) + "</span>";
  }

  function hiddenInput(formKey, field) {
    if (!form) return null;
    return form.querySelector(
      'input[data-icon-field="' + field + '"][data-form-key="' + formKey + '"]'
    );
  }

  function syncHiddenFields() {
    if (!activeFormKey) return;
    var kindInp = hiddenInput(activeFormKey, "kind");
    var valInp = hiddenInput(activeFormKey, "value");
    if (kindInp) kindInp.value = kindEl.value;
    if (valInp) valInp.value = valueEl.value;
  }

  function updateTilePreview(tile) {
    if (!tile) return;
    var glyph = tile.querySelector(".cabinet-icon-tile__glyph");
    if (!glyph) return;
    glyph.innerHTML = renderPreview(kindEl.value, valueEl.value);
    tile.dataset.iconKind = kindEl.value;
    tile.dataset.iconValue = valueEl.value;
    var defKind = tile.dataset.iconDefaultKind || "";
    var defVal = tile.dataset.iconDefaultValue || "";
    var overridden = kindEl.value !== defKind || valueEl.value !== defVal;
    tile.classList.toggle("is-overridden", overridden);
    var tip = tile.querySelector(".cabinet-icon-tile__tip");
    if (tip) {
      var rows = tip.querySelectorAll(".cabinet-icon-tile__tip-row code");
      if (rows.length >= 3) {
        rows[1].textContent = kindEl.value;
        rows[2].textContent = valueEl.value;
      }
      var badge = tip.querySelector(".cabinet-icon-tile__tip-badge");
      if (overridden && !badge) {
        badge = document.createElement("span");
        badge.className = "cabinet-icon-tile__tip-badge";
        badge.textContent = "изменено";
        tip.appendChild(badge);
      } else if (!overridden && badge) {
        badge.remove();
      }
    }
  }

  function openEditor(tile) {
    if (!tile) return;
    if (activeTile) activeTile.classList.remove("is-selected");
    activeTile = tile;
    activeFormKey = tile.dataset.formKey || "";
    activeTile.classList.add("is-selected");

    var label = tile.dataset.iconLabel || "";
    var key = tile.dataset.iconKey || "";
    var kind = tile.dataset.iconKind || "text";
    var value = tile.dataset.iconValue || "";
    var defKind = tile.dataset.iconDefaultKind || "";
    var defVal = tile.dataset.iconDefaultValue || "";

    if (titleEl) titleEl.textContent = label;
    if (keyEl) keyEl.textContent = key;
    if (kindEl) kindEl.value = kind;
    if (valueEl) valueEl.value = value;
    if (defaultEl) {
      defaultEl.textContent = "По умолчанию: " + defKind + " — " + defVal;
    }
    if (previewEl) previewEl.innerHTML = renderPreview(kind, value);
    editor.hidden = false;
    editor.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }

  function closeEditor() {
    if (activeTile) activeTile.classList.remove("is-selected");
    activeTile = null;
    activeFormKey = "";
    editor.hidden = true;
  }

  document.querySelectorAll(".cabinet-icon-tile").forEach(function (tile) {
    tile.addEventListener("click", function () {
      openEditor(tile);
    });
  });

  if (closeBtn) {
    closeBtn.addEventListener("click", function () {
      closeEditor();
    });
  }

  function onEditorInput() {
    syncHiddenFields();
    updateTilePreview(activeTile);
    if (previewEl) previewEl.innerHTML = renderPreview(kindEl.value, valueEl.value);
  }

  if (kindEl) kindEl.addEventListener("change", onEditorInput);
  if (valueEl) valueEl.addEventListener("input", onEditorInput);

  if (form) {
    form.addEventListener("submit", function () {
      syncHiddenFields();
    });
  }
})();
