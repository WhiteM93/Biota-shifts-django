(function () {
  var root = document.querySelector(".su-page");
  if (!root) return;

  function getCookie(name) {
    var m = document.cookie.match(new RegExp("(?:^|; )" + name.replace(/([.$?*|{}()[\]\\/+^])/g, "\\$1") + "=([^;]*)"));
    return m ? decodeURIComponent(m[1]) : "";
  }

  function csrfToken() {
    var el = root.querySelector('input[name="csrfmiddlewaretoken"]');
    return (el && el.value) || getCookie("csrftoken") || "";
  }

  function ackUrl(updateId) {
    var tpl = root.getAttribute("data-su-ack-url-template") || "";
    return tpl.replace(/\/0\/ack\/?$/, "/" + String(updateId) + "/ack/");
  }

  function pluralLabel(n) {
    n = Math.abs(Number(n) || 0) % 100;
    var n1 = n % 10;
    if (n > 10 && n < 20) return "ознакомились";
    if (n1 === 1) return "ознакомился";
    if (n1 >= 2 && n1 <= 4) return "ознакомились";
    return "ознакомились";
  }

  function setChip(chip, names) {
    if (!chip) return;
    names = Array.isArray(names) ? names.filter(Boolean) : [];
    chip.setAttribute("data-users", names.join("|"));
    chip.classList.toggle("is-empty", names.length === 0);
    chip.setAttribute(
      "aria-label",
      names.length ? "Кто ознакомился" : "Пока никто не ознакомился"
    );
    var countEl = chip.querySelector(".js-su-ack-count");
    var labelEl = chip.querySelector(".su-ack-chip__label");
    if (countEl) countEl.textContent = String(names.length);
    if (labelEl) labelEl.textContent = pluralLabel(names.length);
  }

  function markButtonDone(btn) {
    if (!btn) return;
    btn.disabled = true;
    btn.setAttribute("aria-disabled", "true");
    btn.setAttribute("data-acked", "1");
    btn.classList.remove("btn-primary");
    btn.classList.add("btn-ghost", "su-ack-btn--done");
    btn.textContent = "Ознакомился";
  }

  var tip = document.getElementById("su-ack-tip");

  function hideTip() {
    if (!tip) return;
    tip.hidden = true;
    tip.textContent = "";
  }

  function showTip(chip) {
    if (!tip || !chip) return;
    var raw = chip.getAttribute("data-users") || "";
    var names = raw.split("|").map(function (s) { return s.trim(); }).filter(Boolean);
    if (!names.length) {
      tip.textContent = "Пока никто не ознакомился";
    } else {
      tip.textContent = names.join("\n");
    }
    tip.hidden = false;
    var rect = chip.getBoundingClientRect();
    var tipW = tip.offsetWidth || 180;
    var left = Math.min(
      Math.max(8, rect.left + rect.width / 2 - tipW / 2),
      window.innerWidth - tipW - 8
    );
    var top = rect.bottom + 8;
    if (top + tip.offsetHeight > window.innerHeight - 8) {
      top = Math.max(8, rect.top - tip.offsetHeight - 8);
    }
    tip.style.left = left + "px";
    tip.style.top = top + "px";
  }

  root.addEventListener("mouseover", function (e) {
    var chip = e.target.closest(".js-su-ack-chip");
    if (chip && root.contains(chip)) showTip(chip);
  });
  root.addEventListener("mouseout", function (e) {
    var chip = e.target.closest(".js-su-ack-chip");
    if (!chip) return;
    var related = e.relatedTarget;
    if (related && chip.contains(related)) return;
    hideTip();
  });
  root.addEventListener("focusin", function (e) {
    var chip = e.target.closest(".js-su-ack-chip");
    if (chip) showTip(chip);
  });
  root.addEventListener("focusout", function (e) {
    var chip = e.target.closest(".js-su-ack-chip");
    if (!chip) return;
    var related = e.relatedTarget;
    if (related && chip.contains(related)) return;
    hideTip();
  });
  window.addEventListener("scroll", hideTip, { passive: true });
  window.addEventListener("resize", hideTip);

  root.addEventListener("click", function (e) {
    var btn = e.target.closest(".js-su-ack");
    if (!btn || !root.contains(btn) || btn.disabled || btn.getAttribute("data-acked") === "1") {
      return;
    }
    var card = btn.closest(".su-card");
    var updateId = card && card.getAttribute("data-update-id");
    if (!updateId) return;
    btn.disabled = true;
    fetch(ackUrl(updateId), {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "X-CSRFToken": csrfToken(),
        "X-Requested-With": "XMLHttpRequest",
        Accept: "application/json",
      },
    })
      .then(function (r) {
        return r.json().then(function (data) {
          return { ok: r.ok, data: data };
        });
      })
      .then(function (res) {
        if (!res.ok || !res.data || !res.data.ok) {
          btn.disabled = false;
          return;
        }
        markButtonDone(btn);
        setChip(card.querySelector(".js-su-ack-chip"), res.data.ack_users || []);
      })
      .catch(function () {
        btn.disabled = false;
      });
  });
})();
