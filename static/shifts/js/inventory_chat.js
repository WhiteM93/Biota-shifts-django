(function () {
  "use strict";

  var root = document.getElementById("inv-chat");
  if (!root) return;

  var url = root.getAttribute("data-url") || "";
  var csrf = root.getAttribute("data-csrf") || "";
  var storageKey = "biota_inv_chat_v1";
  var sessionStorageKey = "biota_inv_chat_session_v1";

  function loadSessionKey() {
    try {
      var k = sessionStorage.getItem(sessionStorageKey);
      if (k && k.length >= 8) return k;
    } catch (e) {
      /* ignore */
    }
    var fresh = "";
    try {
      fresh = (window.crypto && crypto.randomUUID) ? crypto.randomUUID() : String(Date.now()) + "-" + Math.random().toString(16).slice(2);
    } catch (e2) {
      fresh = String(Date.now());
    }
    try {
      sessionStorage.setItem(sessionStorageKey, fresh);
    } catch (e3) {
      /* ignore */
    }
    return fresh;
  }

  function resetSessionKey() {
    try {
      sessionStorage.removeItem(sessionStorageKey);
    } catch (e) {
      /* ignore */
    }
    return loadSessionKey();
  }

  var chatSessionKey = loadSessionKey();

  var fab = root.querySelector(".js-inv-chat-fab");
  var panel = root.querySelector(".js-inv-chat-panel");
  var messagesEl = root.querySelector(".js-inv-chat-messages");
  var form = root.querySelector(".js-inv-chat-form");
  var input = root.querySelector(".js-inv-chat-input");
  var sendBtn = root.querySelector(".js-inv-chat-send");
  var closeBtn = root.querySelector(".js-inv-chat-close");
  var clearBtn = root.querySelector(".js-inv-chat-clear");
  var hintsEl = root.querySelector(".js-inv-chat-hints");
  var pageHintEl = root.querySelector(".js-inv-chat-page-hint");

  function detectPageContext() {
    var path = (location.pathname || "").replace(/\/+$/, "") || "/";
    var params = new URLSearchParams(location.search || "");
    var panelName = (params.get("panel") || "").trim();
    if (/visual-warehouse/.test(path)) {
      return { page: "visual_warehouse", panel: "" };
    }
    if (/\/inventory(\/|$)/.test(path) || path.indexOf("/inventory") !== -1) {
      return { page: "inventory", panel: panelName || "stock" };
    }
    if (/\/products|\/osnast/.test(path)) return { page: "products", panel: "" };
    if (/\/machines/.test(path)) return { page: "machines", panel: "" };
    if (/\/hours/.test(path)) return { page: "hours", panel: "" };
    if (/\/skud|\/discipline/.test(path)) return { page: "skud", panel: "" };
    if (/\/graph|\/regulations/.test(path)) return { page: "graph", panel: "" };
    if (/\/cabinet/.test(path)) return { page: "cabinet", panel: "" };
    if (/\/calculator/.test(path)) return { page: "calculator", panel: "" };
    if (/\/contracts/.test(path)) return { page: "contracts", panel: "" };
    if (/\/forms/.test(path)) return { page: "forms", panel: "" };
    return { page: "other", panel: "" };
  }

  /* Фиксированные подсказки: что умеет чат. fill — только подставить в поле. */
  var CAPABILITY_HINTS = [
    {
      t: "Предложить изменение",
      q: "Добавь в блокнот: ",
      mode: "fill",
      cls: "inv-chat-hint--note",
      title: "Запишет в блокнот без ИИ — допишите текст и нажмите «Спросить»"
    },
    { t: "Где лежит", q: "Где лежит ", mode: "fill" },
    { t: "На руках", q: "Кто держит инструмент на руках?" },
    { t: "Просрочки", q: "Какие выдачи просрочены?" },
    { t: "Без адреса", q: "Какие позиции без адреса ячейки?" },
    { t: "Контроль", q: "Что в контроле остатков ниже минимума?" },
    { t: "Залежь", q: "Какой инструмент давно не двигался?" }
  ];
  var PAGE_HINTS = {
    analysis: "Сейчас «Главная» — сводка склада; контроль минимумов — вкладка «Контроль».",
    watch: "Сейчас «Контроль» — ходовые позиции и остатки ниже минимума.",
    issue_outcome: "Сейчас «Возврат» — кто не вернул и просрочки.",
    issue: "Сейчас «Выдача» — кто брал и что на руках.",
    stock: "Сейчас «Остатки» — адрес ячейки и топ по количеству.",
    arrival: "Сейчас «Приход» — где лежит и что без адреса.",
    purchases: "Сейчас «Закупки» — что ниже минимума в контроле.",
    history: "Сейчас «История» — свежие движения и открытые выдачи.",
    visual_warehouse: "Сейчас визуальный склад — адрес и позиции без адреса."
  };

  function fillInputPrefix(prefix) {
    if (!input) return;
    input.value = prefix;
    input.focus();
    try {
      var n = prefix.length;
      input.setSelectionRange(n, n);
    } catch (e) {
      /* ignore */
    }
  }

  function bindHintButtons() {
    if (!hintsEl) return;
    hintsEl.querySelectorAll(".js-inv-chat-hint").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var t = btn.getAttribute("data-q") || "";
        var mode = btn.getAttribute("data-mode") || "send";
        if (mode === "fill") {
          fillInputPrefix(t);
          return;
        }
        if (input) input.value = "";
        sendQuestion(t);
      });
    });
  }

  function applyPageUi() {
    var ctx = detectPageContext();
    if (hintsEl) {
      hintsEl.innerHTML = "";
      CAPABILITY_HINTS.forEach(function (item) {
        var btn = document.createElement("button");
        btn.type = "button";
        btn.className = "inv-chat-hint js-inv-chat-hint" + (item.cls ? " " + item.cls : "");
        btn.setAttribute("data-q", item.q);
        btn.setAttribute("data-mode", item.mode || "send");
        btn.title = item.title
          || (item.mode === "fill"
            ? "Подставит начало фразы — допишите и нажмите «Спросить»"
            : item.q);
        btn.textContent = item.t;
        hintsEl.appendChild(btn);
      });
      bindHintButtons();
    }
    if (pageHintEl) {
      var msg = "";
      if (ctx.page === "visual_warehouse") msg = PAGE_HINTS.visual_warehouse;
      else if (ctx.page === "inventory") msg = PAGE_HINTS[ctx.panel] || "";
      pageHintEl.textContent = msg;
      pageHintEl.hidden = !msg;
    }
    if (input) {
      input.placeholder = "Вопрос по складу или «Добавь в блокнот: …»";
    }
  }

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
        "Кнопки сверху — что умею: где лежит, кто на руках, просрочки, контроль. «Предложить изменение» — заявка в блокнот админу. Не чаще 1 раза в минуту (админ — без лимита).",
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
      body: JSON.stringify({
        question: q,
        history: payloadHistory,
        session_key: chatSessionKey,
        page_context: detectPageContext()
      }),
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
      chatSessionKey = resetSessionKey();
      renderHistory();
    });
  }
  applyPageUi();
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
