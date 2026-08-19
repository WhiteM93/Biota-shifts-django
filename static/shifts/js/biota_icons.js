(function (global) {
  "use strict";

  function spec(key) {
    var map = global.__biotaIcons || {};
    return map[key] || null;
  }

  function escapeHtml(s) {
    return String(s || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function html(key, extraClass) {
    var s = spec(key);
    extraClass = extraClass || "";
    if (!s) return "";
    if (s.kind === "flaticon") {
      return (
        '<i class="' +
        escapeHtml(s.value + " biota-icon biota-icon--fi " + extraClass) +
        '" aria-hidden="true"></i>'
      );
    }
    if (s.kind === "hugeicons") {
      if (s.inline) {
        if (!extraClass) return s.inline;
        if (s.inline.indexOf('class="') !== -1) {
          return s.inline.replace(/class="([^"]*)"/, function (_, cls) {
            return 'class="' + cls + " " + escapeHtml(extraClass) + '"';
          });
        }
        return s.inline.replace("<svg", '<svg class="' + escapeHtml(extraClass) + '"');
      }
      return (
        '<img class="biota-icon biota-icon--svg biota-icon--hgi ' +
        escapeHtml(extraClass) +
        '" src="' +
        escapeHtml(s.value) +
        '" width="16" height="16" alt="" aria-hidden="true" loading="lazy">'
      );
    }
    if (s.kind === "svg_static") {
      return (
        '<img class="biota-icon biota-icon--svg ' +
        escapeHtml(extraClass) +
        '" src="' +
        escapeHtml(s.value) +
        '" alt="" aria-hidden="true" loading="lazy">'
      );
    }
    if (s.kind === "emoji" || s.kind === "text") {
      return (
        '<span class="biota-icon biota-icon--text ' +
        escapeHtml(extraClass) +
        '" aria-hidden="true">' +
        escapeHtml(s.value) +
        "</span>"
      );
    }
    return "";
  }

  global.BiotaIcons = {
    spec: spec,
    html: html,
  };
})(window);
