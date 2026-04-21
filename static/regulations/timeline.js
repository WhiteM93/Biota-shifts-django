/**
 * Шкала 08:00–20:00: drag + resize произвольных ползунков + перегруз.
 */
(function () {
  function regEditingEnabled() {
    const root = document.getElementById("reg-timeline-root");
    return !!(root && root.dataset.editing === "1");
  }

  const TL_START = 8 * 60;
  const TL_END = 20 * 60;
  const TL_MIN = TL_END - TL_START;
  /** Шаг перемещения и длительности блоков (минуты) */
  const SNAP_MIN = 5;

  function clamp(v, a, b) {
    return Math.max(a, Math.min(b, v));
  }

  function snap5(x) {
    return Math.round(x / SNAP_MIN) * SNAP_MIN;
  }

  function parseHm(s) {
    const m = /^(\d{1,2}):(\d{2})$/.exec(String(s).trim());
    if (!m) return 0;
    return parseInt(m[1], 10) * 60 + parseInt(m[2], 10);
  }

  function fmtHm(minDay) {
    const h = Math.floor(minDay / 60);
    const mi = minDay % 60;
    return String(h).padStart(2, "0") + ":" + String(mi).padStart(2, "0");
  }

  /** минуты дня → минуты от начала шкалы (8:00) */
  function dayMinToRel(m) {
    return clamp(m - TL_START, 0, TL_MIN);
  }

  function relToDayMin(rel) {
    return clamp(Math.round(rel), 0, TL_MIN);
  }

  function pct(rel) {
    return (rel / TL_MIN) * 100;
  }

  function relFromPct(p) {
    return (p / 100) * TL_MIN;
  }

  function setBlockFromRel(block, startRel, durRel) {
    startRel = snap5(clamp(startRel, 0, TL_MIN));
    durRel = snap5(clamp(durRel, SNAP_MIN, TL_MIN));
    if (startRel + durRel > TL_MIN) {
      durRel = snap5(Math.max(SNAP_MIN, TL_MIN - startRel));
    }
    if (durRel < SNAP_MIN) {
      durRel = SNAP_MIN;
    }
    block.style.left = pct(startRel) + "%";
    block.style.width = pct(durRel) + "%";
    block.dataset.startRel = String(startRel);
    block.dataset.durRel = String(durRel);
    syncBlockTimes(block);
  }

  function syncBlockTimes(block) {
    const r = readBlock(block);
    const t0 = fmtHm(TL_START + r.startRel);
    const t1 = fmtHm(TL_START + r.startRel + r.durRel);
    const el0 = block.querySelector(".reg-block__start");
    const el1 = block.querySelector(".reg-block__end");
    if (el0) el0.textContent = t0;
    if (el1) el1.textContent = t1;
  }

  function readBlock(block) {
    const startRel = parseFloat(block.dataset.startRel || "0", 10);
    const durRel = parseFloat(block.dataset.durRel || "30", 10);
    return { startRel, durRel };
  }

  function metaForTrack(tr, cfgRows) {
    const id = parseInt(tr.dataset.id, 10);
    return (cfgRows || []).find(function (r) {
      return r.id === id;
    }) || {};
  }

  /**
   * Перегруз: 5-мин слоты — пересечение любых ползунков.
   */
  function computeOverload(rows) {
    const slot = 5;
    const slots = Math.ceil(TL_MIN / slot);
    const cnt = new Array(slots).fill(0);
    rows.forEach(function (r) {
      const ivs = [];
      (r.breaks || []).forEach(function (b) {
        const k = (b.color_kind || "").toLowerCase();
        if (k !== "bf" && k !== "ln") return;
        ivs.push([
          dayMinToRel(parseHm(b.start)),
          dayMinToRel(parseHm(b.end)),
        ]);
      });
      for (let i = 0; i < slots; i++) {
        const seg0 = i * slot;
        const seg1 = seg0 + slot;
        let hit = false;
        for (let k = 0; k < ivs.length; k++) {
          const a = ivs[k][0];
          const b = ivs[k][1];
          if (b > a && seg1 > a && seg0 < b) {
            hit = true;
            break;
          }
        }
        if (hit) cnt[i] += 1;
      }
    });
    return cnt;
  }

  function buildOverloadRow(tr, cfgRows) {
    const o = { breaks: [] };
    tr.querySelectorAll(".reg-block").forEach(function (blk) {
      const r = readBlock(blk);
      const labEl = blk.querySelector(".reg-block-label");
      o.breaks.push({
        label: labEl ? String(labEl.value || "").trim() : "Ползунок",
        start: fmtHm(TL_START + r.startRel),
        end: fmtHm(TL_START + r.startRel + r.durRel),
        color_kind: blk.dataset.kind || "ex",
      });
    });
    return o;
  }

  function rowsFromDomForOverload(cfgRows) {
    const out = [];
    document.querySelectorAll(".reg-track[data-id]").forEach(function (tr) {
      out.push(buildOverloadRow(tr, cfgRows));
    });
    return out;
  }

  function getOverloadThreshold() {
    const inp = document.getElementById("reg-ovl-limit");
    let v = inp ? parseInt(inp.value, 10) : 10;
    if (isNaN(v) || v < 1) v = 10;
    if (v > 999) v = 999;
    return v;
  }

  function renderOverload(track, rows) {
    track.innerHTML = "";
    if (!rows || !rows.length) return;
    const cnt = computeOverload(rows);
    const slot = 5;
    const thr = getOverloadThreshold();
    track.dataset.threshold = String(thr);
    cnt.forEach(function (n, i) {
      if (n <= thr) return;
      const seg0 = i * slot;
      const seg1 = seg0 + slot;
      const w = slot;
      const t0 = fmtHm(TL_START + seg0);
      const t1 = fmtHm(TL_START + seg1);
      const el = document.createElement("div");
      el.className = "reg-ovl-seg";
      el.style.left = pct(seg0) + "%";
      el.style.width = pct(w) + "%";
      el.title =
        "Интервал " +
        t0 +
        "–" +
        t1 +
        " (ровно 5 мин): одновременно " +
        n +
        " чел. (порог: не больше " +
        thr +
        ")";
      el.setAttribute(
        "aria-label",
        "Перегруз с " + t0 + " до " + t1 + ", " + n + " человек"
      );
      const lab = document.createElement("span");
      lab.className = "reg-ovl-seg__lab";
      lab.textContent = t0 + "–" + t1;
      el.appendChild(lab);
      track.appendChild(el);
    });
  }

  function bindOverloadControls() {
    const inp = document.getElementById("reg-ovl-limit");
    const ovl = document.getElementById("reg-ovl-track");
    if (!inp || !ovl) return;
    function refresh() {
      renderOverload(ovl, rowsFromDomForOverload(window.__regCfgRows || []));
    }
    inp.addEventListener("change", refresh);
    inp.addEventListener("input", refresh);
  }

  window.syncRegTimelineEditingUi = function () {
    const root = document.getElementById("reg-timeline-root");
    const on = regEditingEnabled();
    const ovl = document.getElementById("reg-ovl-limit");
    const save = document.getElementById("reg-save");
    if (root) root.classList.toggle("reg-shell--readonly", !on);
    if (ovl) ovl.readOnly = !on;
    // Режим редактирования должен запрещать только изменение шкалы, но не сохранение.
    if (save) save.disabled = false;
  };

  function wireBlock(track, block) {
    block.addEventListener("mousedown", function onDown(e) {
      if (e.button !== 0) return;
      if (!regEditingEnabled()) return;
      const rowLocked = track.closest(".reg-emp-row");
      if (rowLocked && rowLocked.classList.contains("reg-row--locked")) return;
      const br = block.getBoundingClientRect();
      const edgePx = 12;
      const atLeft = e.clientX <= br.left + edgePx;
      const atRight = e.clientX >= br.right - edgePx;
      const mode = atLeft || atRight ? "resize" : "drag";
      const edge = atLeft ? "left" : atRight ? "right" : null;

      const tw = track.clientWidth;
      if (tw <= 0) return;

      const startX = e.clientX;
      const r0 = readBlock(block);
      const startRel = r0.startRel;
      const startDur = r0.durRel;

      e.preventDefault();

      function onMove(ev) {
        const dx = ev.clientX - startX;
        const dRel = (dx / tw) * TL_MIN;
        if (mode === "drag") {
          const nr = clamp(startRel + dRel, 0, TL_MIN - startDur);
          setBlockFromRel(block, nr, startDur);
        } else if (mode === "resize" && edge === "right") {
          const nd = clamp(startDur + dRel, 5, TL_MIN - startRel);
          setBlockFromRel(block, startRel, nd);
        } else if (mode === "resize" && edge === "left") {
          const nr = clamp(startRel + dRel, 0, startRel + startDur - 5);
          const nd = clamp(startDur - (nr - startRel), 5, TL_MIN - nr);
          setBlockFromRel(block, nr, nd);
        }
      }

      function onUp() {
        document.removeEventListener("mousemove", onMove);
        document.removeEventListener("mouseup", onUp);
        const ovl = document.getElementById("reg-ovl-track");
        if (ovl) renderOverload(ovl, rowsFromDomForOverload(window.__regCfgRows || []));
      }

      document.addEventListener("mousemove", onMove);
      document.addEventListener("mouseup", onUp);
    });
  }

  window.initRegTimeline = function (cfg) {
    const root = document.getElementById("reg-timeline-root");
    if (!root) return;
    window.__regCfgRows = cfg.rows || [];
    const ovl = document.getElementById("reg-ovl-track");
    root.querySelectorAll(".reg-track[data-id]").forEach(function (track) {
      track.querySelectorAll(".reg-block").forEach(function (block) {
        const s = block.dataset.startHm;
        const e = block.dataset.endHm;
        const rs = dayMinToRel(parseHm(s));
        const re = dayMinToRel(parseHm(e));
        const dur = Math.max(SNAP_MIN, re - rs);
        setBlockFromRel(block, snap5(rs), dur);
        wireBlock(track, block);
      });
    });
    if (ovl) {
      if (cfg.rows && cfg.rows.length) {
        renderOverload(ovl, rowsFromDomForOverload(window.__regCfgRows));
      } else {
        ovl.innerHTML = "";
      }
    }
    bindOverloadControls();
    if (window.syncRegTimelineEditingUi) window.syncRegTimelineEditingUi();
  };

  window.saveRegTimeline = function (apiUrl, dateIso, getCookie) {
    const root = document.getElementById("reg-timeline-root");
    if (!root) {
      return Promise.reject(new Error("нет разметки"));
    }
    const items = [];
    root.querySelectorAll(".reg-track[data-id]").forEach(function (tr) {
      const id = tr.dataset.id;
      if (!id) return;
      const item = {
        id: parseInt(id, 10),
        breaks: [],
      };
      tr.querySelectorAll(".reg-block").forEach(function (blk) {
        const r = readBlock(blk);
        const labelEl = blk.querySelector(".reg-block-label");
        item.breaks.push({
          label: labelEl ? String(labelEl.value || "").trim() : "Ползунок",
          start: fmtHm(TL_START + r.startRel),
          end: fmtHm(TL_START + r.startRel + r.durRel),
          color_kind: blk.dataset.kind || "ex",
        });
      });
      items.push(item);
    });
    const token = getCookie("csrftoken");
    if (!token) {
      return Promise.reject(new Error("Нет CSRF-cookie (csrftoken). Обновите страницу или проверьте настройки cookies."));
    }
    return fetch(apiUrl, {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": token,
      },
      body: JSON.stringify({ date: dateIso, items: items }),
    }).then(function (r) {
      if (!r.ok) {
        return r.text().then(function (t) {
          var msg = r.status === 403 ? "403: CSRF или сессия (обновите страницу, проверьте домен в CSRF_TRUSTED_ORIGINS)." : r.statusText;
          if (t && t.length < 200) msg += " " + t;
          throw new Error(msg);
        });
      }
      var ct = (r.headers.get("Content-Type") || "").toLowerCase();
      if (ct.indexOf("application/json") < 0) {
        return r.text().then(function (t) {
          throw new Error(
            "Ответ не JSON (часто сессия истекла — войдите снова). Начало ответа: " + (t || "").slice(0, 120)
          );
        });
      }
      return r.json();
    });
  };

  function nextBreakLabel(track) {
    let n = 1;
    track.querySelectorAll(".reg-block").forEach(function (blk) {
      if ((blk.dataset.kind || "").toLowerCase() !== "br") return;
      const v = (blk.querySelector(".reg-block-label") || {}).value || "";
      const m = /Перерыв\s+(\d+)/i.exec(v);
      if (m) n = Math.max(n, parseInt(m[1], 10) + 1);
    });
    return "Перерыв " + n;
  }

  function createBreakBlock(track, kind) {
    const k = (kind || "br").toLowerCase();
    const cls = k === "bf" ? "bf" : k === "ln" ? "ln" : "br";
    const label = k === "bf" ? "Завтрак" : k === "ln" ? "Обед" : nextBreakLabel(track);
    const startMin = k === "bf" ? 9 * 60 : k === "ln" ? 12 * 60 : 14 * 60;
    const blk = document.createElement("div");
    blk.className = "reg-block reg-block--" + cls;
    blk.dataset.kind = cls;
    blk.innerHTML =
      '<span class="reg-block__edge reg-block__edge--left" aria-hidden="true"></span>' +
      '<span class="reg-block__edge reg-block__edge--right" aria-hidden="true"></span>' +
      '<span class="reg-block__start"></span><span class="reg-block__end"></span>' +
      '<button type="button" class="reg-block-del" title="Удалить ползунок" aria-label="Удалить ползунок">✕</button>' +
      '<input type="text" class="reg-block-label" value="' + label + '" maxlength="100" placeholder="Название">';
    track.appendChild(blk);
    setBlockFromRel(blk, dayMinToRel(startMin), 30);
    wireBlock(track, blk);
  }

  /**
   * Meta API: только замок.
   */
  window.regBindMetaControls = function (apiUrl, dateIso, getCookie) {
    const root = document.getElementById("reg-timeline-root");
    if (!root) return;

    function postUpdates(updates) {
      const token =
        typeof getCookie === "function" ? getCookie("csrftoken") : "";
      return fetch(apiUrl, {
        method: "POST",
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": token || "",
        },
        body: JSON.stringify({ date: dateIso, updates: updates }),
      }).then(function (r) {
        if (!r.ok) {
          return r.text().then(function (t) {
            var msg = r.status === 403 ? "403 CSRF/сессия" : r.statusText;
            if (t && t.length < 200) msg += " " + t;
            throw new Error(msg);
          });
        }
        return r.json();
      });
    }

    root.addEventListener("click", function (ev) {
      const lockBtn = ev.target.closest(".reg-lock-btn");
      if (lockBtn) {
        if (!regEditingEnabled()) return;
        ev.preventDefault();
        const id = parseInt(lockBtn.getAttribute("data-id"), 10);
        const row = lockBtn.closest(".reg-emp-row");
        if (!row || isNaN(id)) return;
        const willLock = !row.classList.contains("reg-row--locked");
        postUpdates([{ id: id, locked: willLock }])
          .then(function () {
            row.classList.toggle("reg-row--locked", willLock);
            lockBtn.textContent = willLock ? "🔒" : "🔓";
            lockBtn.setAttribute("aria-pressed", willLock ? "true" : "false");
          })
          .catch(function () {
            window.alert("Не удалось сохранить замок");
          });
        return;
      }
    });

    root.addEventListener("click", function (ev) {
      const addBtn = ev.target.closest(".reg-add-btn");
      if (addBtn) {
        if (!regEditingEnabled()) return;
        const row = addBtn.closest(".reg-emp-row");
        const track = row && row.querySelector(".reg-track[data-id]");
        if (!track) return;
        createBreakBlock(track, addBtn.getAttribute("data-kind"));
        const ovl = document.getElementById("reg-ovl-track");
        if (ovl) renderOverload(ovl, rowsFromDomForOverload(window.__regCfgRows || []));
        return;
      }
      const delBtn = ev.target.closest(".reg-block-del");
      if (delBtn) {
        if (!regEditingEnabled()) return;
        const blk = delBtn.closest(".reg-block");
        if (!blk) return;
        blk.remove();
        const ovl = document.getElementById("reg-ovl-track");
        if (ovl) renderOverload(ovl, rowsFromDomForOverload(window.__regCfgRows || []));
      }
    });
  };
})();
