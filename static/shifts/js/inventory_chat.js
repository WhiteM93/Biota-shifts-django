(function () {
  "use strict";

  var root = document.getElementById("inv-chat");
  if (!root) return;

  var url = root.getAttribute("data-url") || "";
  var csrf = root.getAttribute("data-csrf") || "";
  var storageKey = "biota_inv_chat_v1";

  var fab = root.querySelector(".js-inv-chat-fab");
  var panel = root.querySelector(".js-inv-chat-panel");
  var messagesEl = root.querySelector(".js-inv-chat-messages");
  var form = root.querySelector(".js-inv-chat-form");
  var input = root.querySelector(".js-inv-chat-input");
  var sendBtn = root.querySelector(".js-inv-chat-send");
  var closeBtn = root.querySelector(".js-inv-chat-close");
  var clearBtn = root.querySelector(".js-inv-chat-clear");

  function loadHistory() {
    try {
      var raw = sessionStorage.getItem(storageKey);
      var data = raw ? JSON.parse(raw) : [];
      return Array.isArray(data) ? data : [];
    } catch (e) {
      return [];
    }
  }

  function saveHistory(list) {
    try {
      sessionStorage.setItem(storageKey, JSON.stringify(list.slice(-24)));
    } catch (e) {
      /* ignore */
    }
  }

  var history = loadHistory();

  function appendBubble(role, text, cls) {
    var div = document.createElement("div");
    div.className = "inv-chat-msg inv-chat-msg--" + role + (cls ? " " + cls : "");
    div.textContent = text;
    messagesEl.appendChild(div);
    messagesEl.scrollTop = messagesEl.scrollHeight;
    return div;
  }

  function renderHistory() {
    messagesEl.innerHTML = "";
    if (!history.length) {
      appendBubble(
        "meta",
        "Спросите про выдачи, остатки или топ инструмента. Нужны ключи YandexGPT в .env.secrets.",
        "inv-chat-msg--meta"
      );
      return;
    }
    history.forEach(function (m) {
      appendBubble(m.role === "user" ? "user" : "bot", m.text || "");
    });
  }

  function setOpen(open) {
    if (!panel || !fab) return;
    panel.hidden = !open;
    fab.setAttribute("aria-expanded", open ? "true" : "false");
    if (open && input) {
      setTimeout(function () {
        input.focus();
      }, 50);
    }
  }

  function getCookie(name) {
    var m = document.cookie.match(new RegExp("(?:^|; )" + name + "=([^;]*)"));
    return m ? decodeURIComponent(m[1]) : "";
  }

  function csrfToken() {
    return csrf || getCookie("csrftoken") || "";
  }

  function sendQuestion(text) {
    var q = (text || "").trim();
    if (!q || !url) return;
    appendBubble("user", q);
    history.push({ role: "user", text: q });
    saveHistory(history);

    if (sendBtn) sendBtn.disabled = true;
    if (input) input.disabled = true;
    var pending = appendBubble("bot", "Думаю…");

    var payloadHistory = history
      .slice(0, -1)
      .filter(function (m) {
        return m.role === "user" || m.role === "assistant";
      })
      .map(function (m) {
        return { role: m.role === "user" ? "user" : "assistant", text: m.text };
      });

    fetch(url, {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": csrfToken(),
      },
      body: JSON.stringify({ question: q, history: payloadHistory }),
    })
      .then(function (resp) {
        return resp.json().then(function (data) {
          return { status: resp.status, data: data || {} };
        });
      })
      .then(function (res) {
        var data = res.data;
        var reply = (data.reply || "").trim();
        var err = (data.error || "").trim();
        if (pending && pending.parentNode) pending.parentNode.removeChild(pending);
        if (data.ok && reply) {
          appendBubble("bot", reply);
          history.push({ role: "assistant", text: reply });
          saveHistory(history);
        } else {
          appendBubble("bot", err || "Не удалось получить ответ.", "inv-chat-msg--err");
        }
      })
      .catch(function () {
        if (pending && pending.parentNode) pending.parentNode.removeChild(pending);
        appendBubble("bot", "Ошибка сети.", "inv-chat-msg--err");
      })
      .finally(function () {
        if (sendBtn) sendBtn.disabled = false;
        if (input) {
          input.disabled = false;
          input.focus();
        }
      });
  }

  if (fab) {
    fab.addEventListener("click", function () {
      setOpen(panel.hidden);
    });
  }
  if (closeBtn) {
    closeBtn.addEventListener("click", function () {
      setOpen(false);
    });
  }
  if (clearBtn) {
    clearBtn.addEventListener("click", function () {
      history = [];
      saveHistory(history);
      renderHistory();
    });
  }
  root.querySelectorAll(".js-inv-chat-hint").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var t = btn.getAttribute("data-q") || btn.textContent || "";
      if (input) input.value = t;
      sendQuestion(t);
    });
  });
  if (form) {
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      var t = input ? input.value : "";
      if (input) input.value = "";
      sendQuestion(t);
    });
  }
  if (input) {
    input.addEventListener("keydown", function (e) {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        form && form.requestSubmit ? form.requestSubmit() : sendQuestion(input.value);
        if (input) input.value = "";
      }
    });
  }

  renderHistory();
})();
