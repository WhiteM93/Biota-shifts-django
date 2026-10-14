(function () {
  "use strict";

  var cfg = window.__biotaSiteStats;
  if (!cfg || !cfg.ingestUrl) return;

  var MAX_ERRORS_PER_PAGE = 5;
  var sentErrors = 0;
  var seen = {};
  var flushTimer = null;

  function send(events) {
    if (!events.length) return;
    try {
      fetch(cfg.ingestUrl, {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", "X-CSRFToken": cfg.csrf || "" },
        body: JSON.stringify({ events: events }),
        keepalive: true,
      }).catch(function () {});
    } catch (_e) {}
  }

  function pagePath() {
    return (window.location.pathname + window.location.search).slice(0, 300);
  }

  function flushErrors() {
    flushTimer = null;
    var q = window.__biotaErrQ || [];
    var out = [];
    while (q.length) {
      var e = q.shift();
      if (sentErrors >= MAX_ERRORS_PER_PAGE) continue;
      if (seen[e.message]) continue;
      seen[e.message] = true;
      sentErrors += 1;
      e.kind = "js_error";
      e.path = pagePath();
      out.push(e);
    }
    send(out);
  }

  window.__biotaErrFlush = function () {
    if (!flushTimer) flushTimer = setTimeout(flushErrors, 1500);
  };
  if ((window.__biotaErrQ || []).length) window.__biotaErrFlush();

  function transferKb(nav) {
    var total = nav.transferSize || 0;
    try {
      var res = performance.getEntriesByType("resource") || [];
      for (var i = 0; i < res.length; i++) total += res[i].transferSize || 0;
    } catch (_e) {}
    return Math.round(total / 1024);
  }

  function sendPageMetrics() {
    var nav = performance.getEntriesByType && performance.getEntriesByType("navigation")[0];
    if (!nav || nav.loadEventEnd <= 0) return;
    var c = navigator.connection || navigator.mozConnection || navigator.webkitConnection;
    send([
      {
        kind: "page",
        req_id: cfg.reqId,
        ttfb_ms: Math.round(nav.responseStart),
        dom_ms: Math.round(nav.domContentLoadedEventEnd),
        load_ms: Math.round(nav.loadEventEnd),
        transfer_kb: transferKb(nav),
        net: (c && c.effectiveType) || "",
      },
    ]);
  }

  if (document.readyState === "complete") {
    setTimeout(sendPageMetrics, 0);
  } else {
    window.addEventListener("load", function () {
      setTimeout(sendPageMetrics, 0);
    });
  }
})();
