/**
 * Выставление станков:
 * 1) паспорт + схема X2/Y2
 * 2) прогон стола по углам → порядок регулировки ног
 */
(function () {
  "use strict";

  var panel = document.getElementById("calc-panel-leveling");
  if (!panel) return;

  var canEdit = panel.getAttribute("data-can-edit") === "1";
  var cards = [];
  var activeId = null;
  var uiPage = 1;
  var PAGE_STORE_KEY = "biota_calc_lv_page";
  try {
    var savedPage = parseInt(sessionStorage.getItem(PAGE_STORE_KEY) || "1", 10);
    if (savedPage === 2) uiPage = 2;
  } catch (ePage) {}
  var cornerReadings = {}; // key bl|br|fr|fl|c -> {x, y}
  var lastAdvice = null; // { order:[{num, action, turns, delta}], highlight }
  var DEFAULT_TOL = 0.02;

  var CORNERS = [
    { key: "c", n: 1, label: "центр · 0", x: 0.5, y: 0.5, tag: "0" },
    { key: "bl", n: 2, label: "X− Y+", x: 0, y: 0, tag: "X− Y+" }, // зад–лево (верх схемы)
    { key: "br", n: 3, label: "X+ Y+", x: 1, y: 0, tag: "X+ Y+" }, // зад–право
    { key: "fr", n: 4, label: "X+ Y−", x: 1, y: 1, tag: "X+ Y−" }, // перед–право (низ = оператор)
    { key: "fl", n: 5, label: "X− Y−", x: 0, y: 1, tag: "X− Y−" }, // перед–лево
  ];

  try {
    var raw = document.getElementById("calc-leveling-cards-json");
    cards = raw ? JSON.parse(raw.textContent || "[]") : [];
    if (!Array.isArray(cards)) cards = [];
  } catch (e) {
    cards = [];
  }

  function $(id) {
    return document.getElementById(id);
  }

  function csrfToken() {
    var m = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
    if (m) return decodeURIComponent(m[1]);
    var inp = document.querySelector("input[name=csrfmiddlewaretoken]");
    return inp ? inp.value : "";
  }

  function parseNum(elOrVal) {
    var v =
      elOrVal && elOrVal.value !== undefined
        ? String(elOrVal.value || "")
        : String(elOrVal == null ? "" : elOrVal);
    v = v.trim().replace(",", ".");
    if (!v) return null;
    var n = parseFloat(v);
    return isNaN(n) ? null : n;
  }

  function fmt(n, digits) {
    if (n == null || isNaN(n)) return "—";
    var d = digits == null ? 2 : digits;
    return String(Number(n).toFixed(d)).replace(/\.?0+$/, "") || "0";
  }

  function escapeHtml(s) {
    return String(s || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function findCard(id) {
    for (var i = 0; i < cards.length; i++) {
      if (String(cards[i].id) === String(id)) return cards[i];
    }
    return null;
  }

  function setStatus(msg) {
    var el = $("lv-card-status");
    if (el) el.textContent = msg || "";
  }

  function postJson(payload) {
    return fetch(window.location.pathname, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": csrfToken(),
      },
      body: JSON.stringify(payload),
      credentials: "same-origin",
    }).then(function (r) {
      return r.json().then(function (data) {
        return { okHttp: r.ok, data: data };
      });
    });
  }

  function upsertCardLocal(card) {
    var found = false;
    cards = cards.map(function (c) {
      if (String(c.id) === String(card.id)) {
        found = true;
        return card;
      }
      return c;
    });
    if (!found) cards.push(card);
    cards.sort(function (a, b) {
      return String(a.name || "").localeCompare(String(b.name || ""), "ru");
    });
  }

  /** Номера опор слева / справа: подряд 1…N (без пропусков). */
  function footNumsForCount(n) {
    n = Math.max(4, Math.min(16, n || 8));
    if (n % 2) n += 1;
    var pairs = n / 2;
    var left = [];
    var right = [];
    for (var i = 0; i < pairs; i++) {
      left.push(i + 1);
      right.push(pairs + i + 1);
    }
    return { left: left, right: right };
  }

  function buildFeet(w, L, x2, y2, feetN) {
    w = Math.max(100, w || 1200);
    L = Math.max(100, L || 2200);
    x2 = Math.max(50, Math.min(w, x2 || w));
    y2 = Math.max(50, Math.min(L, y2 || L));
    var nums = footNumsForCount(feetN);
    var rows = nums.left.length;
    var x0 = Math.round((w - x2) / 2);
    var x1 = x0 + x2;
    var y0 = Math.round((L - y2) / 2);
    var out = [];
    for (var i = 0; i < rows; i++) {
      var y = rows === 1 ? y0 + y2 / 2 : y0 + (y2 * i) / (rows - 1);
      y = Math.round(y * 10) / 10;
      out.push({ num: nums.left[i], x_mm: x0, y_mm: y });
      out.push({ num: nums.right[i], x_mm: x1, y_mm: y });
    }
    return out;
  }

  function readSetup() {
    var w = parseInt($("lv-bed-w").value, 10) || 1200;
    var L = parseInt($("lv-bed-l").value, 10) || 2200;
    var x2 = parseInt($("lv-x2").value, 10);
    var y2 = parseInt($("lv-y2").value, 10);
    if (!x2 || x2 < 50) x2 = w;
    if (!y2 || y2 < 50) y2 = L;
    var n = parseInt($("lv-feet-n").value, 10) || 8;
    n = Math.max(4, Math.min(16, n));
    if (n % 2) n += 1;
    return { w: w, L: L, x2: x2, y2: y2, feetN: n };
  }

  function currentFeet() {
    var s = readSetup();
    return buildFeet(s.w, s.L, s.x2, s.y2, s.feetN);
  }

  function tolOf() {
    var card = findCard(activeId);
    var t = card && card.workflow && card.workflow.tol_mm_m;
    if (t != null && Number(t) > 0) return Number(t);
    var fromForm = parseNum($("lv-tol"));
    return fromForm != null && fromForm > 0 ? fromForm : DEFAULT_TOL;
  }

  function pitchOf() {
    var card = findCard(activeId);
    var p = card && card.thread_pitch_mm;
    var n = p != null ? Number(p) : parseNum($("lv-pitch"));
    return n && n > 0 ? n : 1.5;
  }

  function showPage(n) {
    uiPage = n === 2 ? 2 : 1;
    try {
      sessionStorage.setItem(PAGE_STORE_KEY, String(uiPage));
    } catch (e) {}
    var p1 = $("lv-page-1");
    var p2 = $("lv-page-2");
    if (p1) p1.hidden = uiPage !== 1;
    if (p2) p2.hidden = uiPage !== 2;
    document.querySelectorAll(".lv-page-tab").forEach(function (b) {
      b.classList.toggle("is-active", String(b.getAttribute("data-page")) === String(uiPage));
    });
    var tabs1 = $("lv-page-tabs");
    if (tabs1) tabs1.hidden = !activeId;
    if (uiPage === 1) renderSetupDiagram();
    if (uiPage === 2) {
      renderCornerList();
      renderLevelMap();
    }
  }

  function renderSetupDiagram() {
    var el = $("lv-setup-diagram");
    if (!el) return;
    var s = readSetup();
    var padL = 48;
    var padR = 28;
    var padT = 28;
    var padB = 44;
    var vw = 300;
    var aspect = s.L / Math.max(1, s.w);
    var vh = Math.max(260, Math.min(520, Math.round((vw - padL - padR) * aspect + padT + padB)));
    var bedW = vw - padL - padR;
    var bedH = vh - padT - padB;
    var sx = bedW / s.w;
    var sy = bedH / s.L;
    var feet = buildFeet(s.w, s.L, s.x2, s.y2, s.feetN);
    var x0base = Math.round((s.w - s.x2) / 2);
    var y0base = Math.round((s.L - s.y2) / 2);
    var sameBase = s.x2 === s.w && s.y2 === s.L;

    // стол (W×L) — внешний контур
    var tableRect =
      '<rect x="' +
      padL +
      '" y="' +
      padT +
      '" width="' +
      bedW +
      '" height="' +
      bedH +
      '" class="lv-setup-table"/>';

    // база опор (X2×Y2) — если отличается от стола
    var baseRect = "";
    if (!sameBase) {
      baseRect =
        '<rect x="' +
        (padL + x0base * sx) +
        '" y="' +
        (padT + y0base * sy) +
        '" width="' +
        s.x2 * sx +
        '" height="' +
        s.y2 * sy +
        '" class="lv-setup-bed"/>';
    } else {
      baseRect =
        '<rect x="' +
        padL +
        '" y="' +
        padT +
        '" width="' +
        bedW +
        '" height="' +
        bedH +
        '" class="lv-setup-bed"/>';
    }

    var dots = feet
      .map(function (f) {
        var cx = padL + f.x_mm * sx;
        var cy = padT + f.y_mm * sy;
        return (
          '<g class="lv-setup-foot">' +
          '<circle cx="' +
          cx +
          '" cy="' +
          cy +
          '" r="11"/>' +
          '<text x="' +
          cx +
          '" y="' +
          (cy + 4) +
          '" text-anchor="middle">' +
          f.num +
          "</text></g>"
        );
      })
      .join("");

    var midX = padL + bedW / 2;
    var midY = padT + bedH / 2;
    // размерные подписи W / L на схеме стола
    var dimW =
      '<text class="lv-setup-dim lv-setup-dim-w" x="' +
      midX +
      '" y="' +
      (vh - 12) +
      '" text-anchor="middle">W = ' +
      s.w +
      " мм</text>" +
      '<line class="lv-setup-dimline" x1="' +
      padL +
      '" y1="' +
      (vh - 28) +
      '" x2="' +
      (padL + bedW) +
      '" y2="' +
      (vh - 28) +
      '"/>';
    var dimL =
      '<text class="lv-setup-dim lv-setup-dim-l" x="' +
      14 +
      '" y="' +
      midY +
      '" text-anchor="middle" transform="rotate(-90 14 ' +
      midY +
      ')">L = ' +
      s.L +
      " мм</text>" +
      '<line class="lv-setup-dimline" x1="' +
      28 +
      '" y1="' +
      padT +
      '" x2="' +
      28 +
      '" y2="' +
      (padT + bedH) +
      '"/>';

    var dimX2Y2 = "";
    if (!sameBase) {
      var bx = padL + x0base * sx + (s.x2 * sx) / 2;
      var by = padT + y0base * sy + (s.y2 * sy) / 2;
      dimX2Y2 =
        '<text class="lv-setup-dim2" x="' +
        bx +
        '" y="' +
        (padT + y0base * sy + s.y2 * sy - 6) +
        '" text-anchor="middle">X2=' +
        s.x2 +
        "</text>" +
        '<text class="lv-setup-dim2" x="' +
        (padL + x0base * sx + 10) +
        '" y="' +
        by +
        '" text-anchor="middle" transform="rotate(-90 ' +
        (padL + x0base * sx + 10) +
        " " +
        by +
        ')">Y2=' +
        s.y2 +
        "</text>";
    } else {
      dimX2Y2 =
        '<text class="lv-setup-dim2" x="' +
        midX +
        '" y="' +
        (padT + bedH - 8) +
        '" text-anchor="middle">X2=W · Y2=L</text>';
    }

    el.innerHTML =
      '<svg viewBox="0 0 ' +
      vw +
      " " +
      vh +
      '" class="lv-setup-svg" role="img">' +
      '<text x="' +
      midX +
      '" y="16" text-anchor="middle" class="lv-bed-lbl">зад</text>' +
      '<text x="' +
      midX +
      '" y="' +
      (vh - 2) +
      '" text-anchor="middle" class="lv-bed-lbl" opacity="0">.</text>' +
      tableRect +
      baseRect +
      dimW +
      dimL +
      dimX2Y2 +
      dots +
      '<text x="' +
      midX +
      '" y="' +
      (padT + bedH + 14) +
      '" text-anchor="middle" class="lv-bed-lbl">оператор</text>' +
      "</svg>" +
      '<p class="lv-setup-caption muted"><b>W</b> — ширина (лево↔право) · <b>L</b> — длина (зад→к вам) · красный контур — база опор X2×Y2</p>';
  }

  function renderCornerList() {
    var root = $("lv-corner-list");
    if (!root) return;
    root.innerHTML = CORNERS.map(function (c) {
      var r = cornerReadings[c.key] || {};
      return (
        '<div class="lv-corner-row" data-corner="' +
        c.key +
        '">' +
        '<div class="lv-corner-label">' +
        '<span class="lv-corner-n">' +
        c.n +
        "</span>" +
        '<span class="lv-corner-name">' +
        escapeHtml(c.label) +
        "</span></div>" +
        '<label class="lv-corner-field">' +
        '<span class="lv-corner-axis">поперёк W</span>' +
        '<input type="number" step="0.01" inputmode="decimal" data-axis="x" value="' +
        (r.x != null ? r.x : "") +
        '" placeholder="мм/м" aria-label="Уровень поперёк в точке ' +
        c.n +
        '">' +
        "</label>" +
        '<label class="lv-corner-field">' +
        '<span class="lv-corner-axis">вдоль L</span>' +
        '<input type="number" step="0.01" inputmode="decimal" data-axis="y" value="' +
        (r.y != null ? r.y : "") +
        '" placeholder="мм/м" aria-label="Уровень вдоль в точке ' +
        c.n +
        '">' +
        "</label>" +
        "</div>"
      );
    }).join("");
  }

  function syncCornersFromDom() {
    CORNERS.forEach(function (c) {
      var row = document.querySelector('.lv-corner-row[data-corner="' + c.key + '"]');
      if (!row) return;
      var ix = row.querySelector('input[data-axis="x"]');
      var iy = row.querySelector('input[data-axis="y"]');
      var x = parseNum(ix);
      var y = parseNum(iy);
      if (x == null && y == null) {
        delete cornerReadings[c.key];
      } else {
        cornerReadings[c.key] = { x: x, y: y };
      }
    });
  }

  function cornerHeight(key) {
    var r = cornerReadings[key];
    if (!r) return null;
    if (r.x != null && r.y != null) return (Number(r.x) + Number(r.y)) / 2;
    if (r.x != null) return Number(r.x);
    if (r.y != null) return Number(r.y);
    return null;
  }

  /** Высота в точке по Inverse Distance Weighting (углы + центр). */
  function heightAt(nx, ny, points) {
    var sumW = 0;
    var sum = 0;
    for (var i = 0; i < points.length; i++) {
      var p = points[i];
      var dx = nx - p.x;
      var dy = ny - p.y;
      var d2 = dx * dx + dy * dy;
      if (d2 < 1e-12) return p.h;
      var w = 1 / d2;
      sum += w * p.h;
      sumW += w;
    }
    return sumW > 0 ? sum / sumW : 0;
  }

  function turnsFor(deltaMm, pitchMm) {
    var pitch = Math.max(0.1, pitchMm || 1.5);
    var turns = Math.abs(deltaMm) / pitch;
    if (turns < 0.08) return null;
    if (turns < 0.2) return "≈⅛";
    if (turns < 0.35) return "≈¼";
    if (turns < 0.6) return "≈½";
    if (turns < 0.9) return "≈¾";
    return "≈" + fmt(turns, 1);
  }

  function buildAdvice() {
    syncCornersFromDom();
    var missing = [];
    var points = [];
    CORNERS.forEach(function (c) {
      var h = cornerHeight(c.key);
      if (h == null) missing.push(c.n);
      else points.push({ x: c.x, y: c.y, h: h, key: c.key });
    });
    if (missing.length) {
      return {
        ok: false,
        steps: [
          {
            html:
              "Заполните точки: <strong>" +
              missing.join(", ") +
              "</strong> (4 угла + центр).",
          },
        ],
        warn: "",
        order: [],
        highlight: {},
      };
    }

    var feet = currentFeet();
    var s = readSetup();
    var w = s.w;
    var L = s.L;
    var tol = tolOf();
    var pitch = pitchOf();
    var scale = Math.max(0.3, w / 1000);

    var vals = feet.map(function (f) {
      var nx = Math.max(0, Math.min(1, (Number(f.x_mm) || 0) / w));
      var ny = Math.max(0, Math.min(1, (Number(f.y_mm) || 0) / L));
      var h = heightAt(nx, ny, points);
      return { num: f.num, h: h, x_mm: f.x_mm, y_mm: f.y_mm };
    });
    var sum = 0;
    vals.forEach(function (v) {
      sum += v.h;
    });
    var mean = sum / vals.length;

    // скручивание: центр vs среднее углов
    var cornersOnly = points.filter(function (p) {
      return p.key !== "c";
    });
    var cPt = points.filter(function (p) {
      return p.key === "c";
    })[0];
    var twistWarn = "";
    if (cPt && cornersOnly.length === 4) {
      var cPred = heightAt(0.5, 0.5, cornersOnly);
      var twist = Math.abs(cPt.h - cPred);
      if (twist > tol * 2) {
        twistWarn =
          "Центр отличается от плоскости углов на " +
          fmt(twist, 3) +
          " мм/м — возможен перекос/скручивание станины.";
      }
    }

    var highlight = {};
    var order = [];
    vals
      .slice()
      .sort(function (a, b) {
        return Math.abs(b.h - mean) - Math.abs(a.h - mean);
      })
      .forEach(function (v) {
        var diff = v.h - mean;
        if (Math.abs(diff) <= tol) {
          highlight[v.num] = { kind: "ok", order: null, label: "ok" };
          return;
        }
        var dh = Math.abs(diff) * scale;
        var t = turnsFor(dh, pitch) || "чуть";
        var kind = diff > 0 ? "down" : "up";
        var stepN = order.length + 1;
        highlight[v.num] = {
          kind: kind,
          order: stepN,
          label: (kind === "down" ? "↓" : "↑") + t,
        };
        order.push({
          num: v.num,
          kind: kind,
          turns: t,
          diff: diff,
          step: stepN,
        });
      });

    if (!order.length) {
      return {
        ok: true,
        steps: [{ html: "Все опоры в допуске (±" + tol + " мм/м). Можно оставлять." }],
        warn: twistWarn,
        order: [],
        highlight: highlight,
      };
    }

    var steps = order.map(function (o) {
      var act =
        o.kind === "down"
          ? '<b class="lv-act-down">опустить</b> (вкрутить)'
          : '<b class="lv-act-up">поднять</b> (выкрутить)';
      return {
        html:
          "<strong>" +
          o.step +
          ".</strong> нога <strong>" +
          o.num +
          "</strong> — " +
          act +
          " на " +
          o.turns +
          " об. <span class=\"muted\">Δ " +
          fmt(o.diff, 2) +
          " мм/м</span>",
      };
    });

    return {
      ok: false,
      steps: steps,
      warn:
        (twistWarn ? twistWarn + " " : "") +
        "Крутите по порядку (красные цифры справа). После правки снова снимите точки.",
      order: order,
      highlight: highlight,
    };
  }

  function renderLevelMap() {
    var el = $("lv-level-map");
    if (!el) return;
    var s = readSetup();
    var feet = currentFeet();
    var pad = 28;
    var vw = 300;
    var aspect = s.y2 / Math.max(1, s.x2);
    var vh = Math.max(240, Math.min(520, Math.round(vw * aspect)));
    var sx = (vw - 2 * pad) / s.x2;
    var sy = (vh - 2 * pad) / s.y2;
    var x0 = Math.round((s.w - s.x2) / 2);
    var y0 = Math.round((s.L - s.y2) / 2);
    var hi = (lastAdvice && lastAdvice.highlight) || {};

    var dots = feet
      .map(function (f) {
        var cx = pad + (f.x_mm - x0) * sx;
        var cy = pad + (f.y_mm - y0) * sy;
        var h = hi[f.num];
        var cls = "lv-level-foot";
        if (h && h.kind === "down") cls += " is-down";
        if (h && h.kind === "up") cls += " is-up";
        if (h && h.kind === "ok") cls += " is-ok";
        var orderBadge =
          h && h.order
            ? '<circle class="lv-level-order-bg" cx="' +
              (cx + 14) +
              '" cy="' +
              (cy - 12) +
              '" r="9"/>' +
              '<text class="lv-level-order" x="' +
              (cx + 14) +
              '" y="' +
              (cy - 8) +
              '" text-anchor="middle">' +
              h.order +
              "</text>"
            : "";
        var sub =
          h && h.label
            ? '<text class="lv-level-sub" x="' +
              cx +
              '" y="' +
              (cy + 22) +
              '" text-anchor="middle">' +
              escapeHtml(h.label) +
              "</text>"
            : "";
        return (
          '<g class="' +
          cls +
          '">' +
          '<circle cx="' +
          cx +
          '" cy="' +
          cy +
          '" r="13"/>' +
          '<text class="lv-level-num" x="' +
          cx +
          '" y="' +
          (cy + 4) +
          '" text-anchor="middle">' +
          f.num +
          "</text>" +
          orderBadge +
          sub +
          "</g>"
        );
      })
      .join("");

    el.innerHTML =
      '<svg viewBox="0 0 ' +
      vw +
      " " +
      vh +
      '" class="lv-level-svg" role="img">' +
      '<text x="' +
      vw / 2 +
      '" y="14" text-anchor="middle" class="lv-bed-lbl">Y+</text>' +
      '<text x="' +
      vw / 2 +
      '" y="' +
      (vh - 2) +
      '" text-anchor="middle" class="lv-bed-lbl">Y−</text>' +
      '<text x="10" y="' +
      vh / 2 +
      '" text-anchor="middle" class="lv-bed-lbl" transform="rotate(-90 10 ' +
      vh / 2 +
      ')">X−</text>' +
      '<text x="' +
      (vw - 10) +
      '" y="' +
      vh / 2 +
      '" text-anchor="middle" class="lv-bed-lbl" transform="rotate(90 ' +
      (vw - 10) +
      " " +
      vh / 2 +
      ')">X+</text>' +
      dots +
      "</svg>";
  }

  function analyze() {
    lastAdvice = buildAdvice();
    var box = $("lv-advice");
    var ol = $("lv-steps");
    var warn = $("lv-warn");
    if (box) box.hidden = false;
    if (ol) {
      ol.innerHTML = lastAdvice.steps
        .map(function (s) {
          return "<li>" + s.html + "</li>";
        })
        .join("");
    }
    if (warn) warn.textContent = lastAdvice.warn || "";
    renderLevelMap();
  }

  function renderSelect() {
    var sel = $("lv-card-select");
    if (!sel) return;
    var html = '<option value="">— выберите —</option>';
    cards.forEach(function (c) {
      html +=
        '<option value="' +
        c.id +
        '"' +
        (String(c.id) === String(activeId) ? " selected" : "") +
        ">" +
        escapeHtml(c.name || "#" + c.id) +
        (c.serial_number ? " / " + escapeHtml(c.serial_number) : "") +
        "</option>";
    });
    sel.innerHTML = html;
  }

  function renderList() {
    var ul = $("lv-card-list");
    var empty = $("lv-list-empty");
    if (!ul) return;
    ul.innerHTML = "";
    if (!cards.length) {
      if (empty) empty.hidden = false;
      renderSelect();
      return;
    }
    if (empty) empty.hidden = true;
    cards.forEach(function (card) {
      var li = document.createElement("li");
      var btn = document.createElement("button");
      btn.type = "button";
      if (String(card.id) === String(activeId)) btn.className = "is-active";
      btn.innerHTML =
        "<span>" +
        escapeHtml(card.name || "Без имени") +
        "</span>" +
        (card.serial_number
          ? '<span class="lv-sn">' + escapeHtml(card.serial_number) + "</span>"
          : "");
      btn.addEventListener("click", function () {
        selectCard(card.id);
      });
      li.appendChild(btn);
      ul.appendChild(li);
    });
    renderSelect();
  }

  function loadCornersFromCard(card) {
    cornerReadings = {};
    lastAdvice = null;
    var cr = card && card.workflow && card.workflow.corner_readings;
    if (cr && typeof cr === "object") {
      CORNERS.forEach(function (c) {
        if (cr[c.key]) cornerReadings[c.key] = cr[c.key];
      });
    }
  }

  function fillForm(card) {
    $("lv-name").value = (card && card.name) || "";
    $("lv-serial").value = (card && card.serial_number) || "";
    $("lv-weight").value = card && card.weight_kg != null ? card.weight_kg : "";
    var w = (card && card.bed_width_mm) || 1200;
    var L = (card && card.bed_length_mm) || 2200;
    $("lv-bed-w").value = w;
    $("lv-bed-l").value = L;
    $("lv-feet-n").value = (card && card.feet_count) || 8;
    var wf = (card && card.workflow) || {};
    $("lv-x2").value = wf.x2_mm != null ? wf.x2_mm : w;
    $("lv-y2").value = wf.y2_mm != null ? wf.y2_mm : L;
    if ($("lv-pitch")) $("lv-pitch").value = (card && card.thread_pitch_mm) || "1.5";
    if ($("lv-tol")) $("lv-tol").value = wf.tol_mm_m != null ? wf.tol_mm_m : DEFAULT_TOL;
    if ($("lv-notes")) $("lv-notes").value = (card && card.notes) || "";
    loadCornersFromCard(card);
  }

  function readCardForm() {
    var s = readSetup();
    var feet = buildFeet(s.w, s.L, s.x2, s.y2, s.feetN);
    var card = findCard(activeId);
    var wf = Object.assign({}, (card && card.workflow) || {});
    wf.x2_mm = s.x2;
    wf.y2_mm = s.y2;
    wf.tol_mm_m = wf.tol_mm_m != null ? wf.tol_mm_m : DEFAULT_TOL;
    syncCornersFromDom();
    wf.corner_readings = cornerReadings;
    wf.done = Object.assign({}, wf.done || {});
    wf.done.card = true;
    wf.done.feet = true;
    delete wf.stage;
    var layout = "rect8";
    if (s.feetN <= 4) layout = "rect4";
    else if (s.feetN <= 6) layout = "rect6";
    return {
      action: "save_leveling_card",
      id: activeId || 0,
      name: ($("lv-name").value || "").trim(),
      serial_number: ($("lv-serial").value || "").trim(),
      weight_kg: ($("lv-weight").value || "").trim(),
      feet_count: s.feetN,
      foot_layout: layout,
      bed_width_mm: s.w,
      bed_length_mm: s.L,
      thread_pitch_mm: ($("lv-pitch") && $("lv-pitch").value) || "1.5",
      table_span_x_mm: s.w,
      table_span_y_mm: s.L,
      notes: ($("lv-notes") && $("lv-notes").value) || "",
      feet_positions: feet,
      workflow: wf,
    };
  }

  function selectCard(id) {
    activeId = id;
    var card = findCard(id);
    if (!card) {
      $("lv-main").hidden = true;
      renderList();
      return;
    }
    fillForm(card);
    $("lv-main").hidden = false;
    showPage(uiPage === 2 ? 2 : 1);
    setStatus(card.updated_at ? "Обновлено: " + card.updated_at : "");
    renderList();
  }

  function newCard() {
    activeId = null;
    $("lv-main").hidden = false;
    fillForm({
      name: "",
      bed_width_mm: 1200,
      bed_length_mm: 2200,
      feet_count: 8,
      thread_pitch_mm: "1.5",
      foot_layout: "rect8",
      workflow: { x2_mm: 1200, y2_mm: 2200, tol_mm_m: DEFAULT_TOL },
    });
    showPage(1);
    setStatus("Новая карточка — заполните и сохраните.");
    renderList();
    $("lv-name").focus();
  }

  function saveCard(thenPage) {
    if (!canEdit) return Promise.resolve(false);
    var payload = readCardForm();
    if (!payload.name) {
      setStatus("Укажите модель станка.");
      showPage(1);
      $("lv-name").focus();
      return Promise.resolve(false);
    }
    $("lv-x2").value = payload.workflow.x2_mm;
    $("lv-y2").value = payload.workflow.y2_mm;
    $("lv-feet-n").value = payload.feet_count;
    setStatus("Сохранение…");
    return postJson(payload).then(function (res) {
      if (!res.data || !res.data.ok) {
        setStatus((res.data && res.data.error) || "Ошибка.");
        return false;
      }
      upsertCardLocal(res.data.card);
      activeId = res.data.card.id;
      fillForm(res.data.card);
      setStatus("Сохранено.");
      renderList();
      showPage(thenPage || uiPage);
      return true;
    });
  }

  // events
  $("lv-new-card").addEventListener("click", function () {
    if (!canEdit) return;
    newCard();
  });

  $("lv-card-select").addEventListener("change", function () {
    var id = $("lv-card-select").value;
    if (!id) {
      $("lv-main").hidden = true;
      activeId = null;
      return;
    }
    selectCard(id);
  });

  $("lv-save-card").addEventListener("click", function () {
    saveCard(1);
  });

  $("lv-goto-2").addEventListener("click", function () {
    saveCard(2).then(function (ok) {
      if (ok) showPage(2);
    });
  });

  document.querySelectorAll(".lv-page-tab").forEach(function (b) {
    b.addEventListener("click", function () {
      var n = parseInt(b.getAttribute("data-page"), 10);
      if (n === 2 && !activeId) {
        setStatus("Сначала сохраните паспорт станка.");
        return;
      }
      showPage(n);
    });
  });

  $("lv-delete-card").addEventListener("click", function () {
    if (!canEdit || !activeId) {
      setStatus("Нечего удалять.");
      return;
    }
    if (!window.confirm("Удалить карточку станка?")) return;
    postJson({ action: "delete_leveling_card", id: activeId }).then(function (res) {
      if (!res.data || !res.data.ok) {
        setStatus((res.data && res.data.error) || "Ошибка.");
        return;
      }
      cards = cards.filter(function (c) {
        return String(c.id) !== String(activeId);
      });
      activeId = null;
      $("lv-main").hidden = true;
      setStatus("");
      renderList();
    });
  });

  ["lv-bed-w", "lv-bed-l", "lv-x2", "lv-y2", "lv-feet-n"].forEach(function (id) {
    var el = $(id);
    if (!el) return;
    el.addEventListener("input", function () {
      renderSetupDiagram();
      if (uiPage === 2) renderLevelMap();
    });
    el.addEventListener("change", function () {
      renderSetupDiagram();
      if (uiPage === 2) renderLevelMap();
    });
  });

  $("lv-bed-w").addEventListener("change", function () {
    var w = parseInt($("lv-bed-w").value, 10) || 1200;
    var x2 = parseInt($("lv-x2").value, 10);
    if (!x2 || x2 > w) $("lv-x2").value = w;
    renderSetupDiagram();
  });
  $("lv-bed-l").addEventListener("change", function () {
    var L = parseInt($("lv-bed-l").value, 10) || 2200;
    var y2 = parseInt($("lv-y2").value, 10);
    if (!y2 || y2 > L) $("lv-y2").value = L;
    renderSetupDiagram();
  });

  $("lv-analyze").addEventListener("click", analyze);

  $("lv-clear-corners").addEventListener("click", function () {
    cornerReadings = {};
    lastAdvice = null;
    renderCornerList();
    renderLevelMap();
    var adv = $("lv-advice");
    if (adv) adv.hidden = true;
  });

  $("lv-save-measure").addEventListener("click", function () {
    if (!canEdit || !activeId) {
      setStatus("Сначала сохраните паспорт.");
      return;
    }
    analyze();
    var payload = readCardForm();
    payload.id = activeId;
    payload.workflow.corner_readings = cornerReadings;
    payload.workflow.done = payload.workflow.done || {};
    payload.workflow.done.static = true;
    postJson(payload).then(function (res) {
      if (!res.data || !res.data.ok) {
        setStatus((res.data && res.data.error) || "Ошибка.");
        return;
      }
      upsertCardLocal(res.data.card);
      setStatus("Замер углов сохранён.");
    });
    var avg = 0;
    var n = 0;
    CORNERS.forEach(function (c) {
      var h = cornerHeight(c.key);
      if (h != null) {
        avg += h;
        n += 1;
      }
    });
    postJson({
      action: "save_leveling_measurement",
      id: activeId,
      kind: "corners",
      level_x: n ? avg / n : null,
      level_y: null,
    });
  });

  var cornerList = $("lv-corner-list");
  if (cornerList) {
    cornerList.addEventListener("change", function () {
      syncCornersFromDom();
      lastAdvice = null;
    });
  }

  // init
  renderList();
  if (cards.length) selectCard(cards[0].id);
  else if (canEdit) newCard();
})();
