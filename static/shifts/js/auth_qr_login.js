(function () {
  "use strict";

  var root = document.querySelector(".js-auth-qr");
  if (!root) return;

  var statusUrl = root.getAttribute("data-status-url") || "";
  var token = root.getAttribute("data-token") || "";
  var nextUrl = root.getAttribute("data-next") || "";
  var statusEl = root.querySelector(".js-auth-qr-status");
  var frameEl = root.querySelector(".js-auth-qr-frame");
  var timer = null;
  var busy = false;

  function setStatus(text) {
    if (statusEl) statusEl.textContent = text || "";
  }

  function poll() {
    if (!statusUrl || !token || busy) return;
    busy = true;
    var url = statusUrl + "?token=" + encodeURIComponent(token);
    if (nextUrl) url += "&next=" + encodeURIComponent(nextUrl);
    fetch(url, {
      credentials: "same-origin",
      headers: { Accept: "application/json", "X-Requested-With": "XMLHttpRequest" },
    })
      .then(function (r) {
        return r.json().then(function (data) {
          return { status: r.status, data: data || {} };
        });
      })
      .then(function (res) {
        var data = res.data;
        if (!data.ok && data.error) {
          setStatus(data.error);
          return;
        }
        var st = data.status || "";
        if (st === "ready" || st === "logged_in") {
          setStatus("Вход подтверждён…");
          window.location.href = data.redirect || "/";
          return;
        }
        if (st === "expired") {
          token = data.token || "";
          root.setAttribute("data-token", token);
          if (frameEl && data.qr_svg) frameEl.innerHTML = data.qr_svg;
          setStatus("Код обновлён — отсканируйте снова");
          return;
        }
        if (st === "pending") {
          setStatus("Отсканируйте камерой телефона");
        }
      })
      .catch(function () {
        setStatus("Нет связи — проверьте сеть");
      })
      .finally(function () {
        busy = false;
      });
  }

  timer = window.setInterval(poll, 2000);
  poll();
  window.addEventListener("beforeunload", function () {
    if (timer) window.clearInterval(timer);
  });
})();
