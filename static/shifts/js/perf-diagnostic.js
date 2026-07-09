(function () {
  "use strict";

  var cfg = window.__biotaPerfDiag;
  if (!cfg || !cfg.ingestUrl) return;

  function cookie(name) {
    var m = document.cookie.match(new RegExp("(?:^|; )" + name + "=([^;]*)"));
    return m ? decodeURIComponent(m[1]) : "";
  }

  function connInfo() {
    var c = navigator.connection || navigator.mozConnection || navigator.webkitConnection;
    if (!c) return {};
    return {
      effectiveType: c.effectiveType || "",
      downlink: typeof c.downlink === "number" ? c.downlink : null,
      rtt: typeof c.rtt === "number" ? c.rtt : null,
      saveData: !!c.saveData,
    };
  }

  function slowResources(limit) {
    var out = [];
    try {
      var entries = performance.getEntriesByType("resource") || [];
      for (var i = 0; i < entries.length; i++) {
        var e = entries[i];
        if (e.duration < 1000) continue;
        var name = e.name || "";
        try {
          name = new URL(name, window.location.href).pathname;
        } catch (_err) {}
        out.push({
          name: name.slice(-120),
          dur_ms: Math.round(e.duration),
          type: e.initiatorType || "",
        });
        if (out.length >= limit) break;
      }
    } catch (_e2) {}
    return out;
  }

  function sendReport() {
    var nav = performance.getEntriesByType("navigation")[0];
    if (!nav || nav.loadEventEnd <= 0) return;

    var ttfb = Math.round(nav.responseStart - nav.requestStart);
    var dom = Math.round(nav.domContentLoadedEventEnd - nav.startTime);
    var load = Math.round(nav.loadEventEnd - nav.startTime);
    var ttfbLimit = cfg.ttfbMs || 2500;
    var loadLimit = cfg.loadMs || 5000;
    if (ttfb < ttfbLimit && load < loadLimit) return;

    var payload = {
      path: window.location.pathname + window.location.search,
      ttfb_ms: ttfb,
      dom_ms: dom,
      load_ms: load,
      is_mobile: cfg.isMobile || false,
      user_agent: navigator.userAgent || "",
      connection: connInfo(),
      slow_resources: slowResources(12),
      viewport: window.innerWidth + "x" + window.innerHeight,
      device_memory: navigator.deviceMemory || null,
      referrer: document.referrer || "",
    };

    fetch(cfg.ingestUrl, {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": cookie("csrftoken"),
      },
      body: JSON.stringify(payload),
      keepalive: true,
    }).catch(function () {});
  }

  if (document.readyState === "complete") {
    setTimeout(sendReport, 0);
  } else {
    window.addEventListener("load", function () {
      setTimeout(sendReport, 0);
    });
  }
})();
