/**
 * Журнал действий графика/регламентов (только admin, кнопка «Лог»).
 */
(function (global) {
  "use strict";

  function getCookie(name) {
    var m = document.cookie.match("(^|;) ?" + name + "=([^;]*)(;|$)");
    return m ? decodeURIComponent(m[2]) : null;
  }

  function init(cfg) {
    var section = cfg.section || "";
    var ingestUrl = cfg.ingestUrl || "";
    var listUrl = cfg.listUrl || "";
    var toggle = document.getElementById("section-debug-log-toggle");
    var panel = document.getElementById("section-debug-log-panel");
    var listEl = document.getElementById("section-debug-log-list");
    var traceCb = document.getElementById("section-debug-log-trace");
    if (!toggle || !panel || !listEl || !section) return null;

    var traceOn = false;
    var pollTimer = null;
    var lastTopId = 0;

    function log(eventType, summary, details) {
      if (!ingestUrl) return;
      var body = {
        section: section,
        event_type: eventType || "client",
        summary: String(summary || "").slice(0, 500),
        details: details && typeof details === "object" ? details : {},
      };
      fetch(ingestUrl, {
        method: "POST",
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": getCookie("csrftoken") || "",
        },
        body: JSON.stringify(body),
      }).catch(function () {});
    }

    function trace(eventType, summary, details) {
      if (!traceOn) return;
      log(eventType, summary, details);
    }

    function renderRows(rows, prepend) {
      if (!rows || !rows.length) return;
      var html = "";
      rows.forEach(function (r) {
        if (r.id > lastTopId) lastTopId = r.id;
        var det = "";
        try {
          var d = r.details || {};
          if (Object.keys(d).length) det = JSON.stringify(d);
        } catch (e) {}
        html +=
          '<div class="section-debug-log-item" data-id="' +
          r.id +
          '">' +
          '<div class="section-debug-log-item__meta">' +
          r.at +
          " · " +
          (r.actor || "—") +
          " · " +
          (r.event_type || "") +
          "</div>" +
          '<div class="section-debug-log-item__sum">' +
          (r.summary || "") +
          "</div>" +
          (det ? '<div class="section-debug-log-item__det">' + det + "</div>" : "") +
          "</div>";
      });
      if (prepend) {
        listEl.insertAdjacentHTML("afterbegin", html);
      } else {
        listEl.innerHTML = html + listEl.innerHTML;
      }
    }

    function fetchList(afterId) {
      var url = listUrl + "?section=" + encodeURIComponent(section) + "&limit=80";
      if (afterId) url += "&after_id=" + encodeURIComponent(String(afterId));
      return fetch(url, { credentials: "same-origin" })
        .then(function (r) {
          return r.json();
        })
        .then(function (data) {
          if (data && data.ok && data.rows) return data.rows;
          return [];
        })
        .catch(function () {
          return [];
        });
    }

    function refresh(full) {
      if (full) {
        listEl.innerHTML = "";
        lastTopId = 0;
        return fetchList(null).then(function (rows) {
          renderRows(rows, false);
        });
      }
      return fetchList(lastTopId).then(function (rows) {
        if (rows.length) renderRows(rows, true);
      });
    }

    function setOpen(on) {
      panel.classList.toggle("is-open", on);
      toggle.classList.toggle("is-open", on);
      toggle.setAttribute("aria-expanded", on ? "true" : "false");
      if (on) {
        refresh(true);
        pollTimer = setInterval(function () {
          refresh(false);
        }, 3000);
      } else if (pollTimer) {
        clearInterval(pollTimer);
        pollTimer = null;
      }
    }

    toggle.addEventListener("click", function () {
      setOpen(!panel.classList.contains("is-open"));
    });
    if (traceCb) {
      traceCb.addEventListener("change", function () {
        traceOn = !!traceCb.checked;
        log("client_trace", traceOn ? "Подробная запись включена" : "Подробная запись выключена");
      });
    }

    var api = { log: log, trace: trace, refresh: refresh };
    global.SectionDebugLog = api;
    return api;
  }

  global.SectionDebugLogInit = init;
})(window);
