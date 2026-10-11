/**
 * 3D-визуализация заготовки / нуля / траектории датчика (Canvas).
 * Зум + отработка по кадрам.
 */
(function () {
  "use strict";

  const ROOT = "hb-viz";
  let canvas = null;
  let ctx = null;
  let wrap = null;
  let raf = 0;
  let yaw = -0.65;
  let pitch = 0.55;
  let zoom = 1;
  let dragging = false;
  let lastX = 0;
  let lastY = 0;
  let lastSnap = null;
  let ro = null;
  let bound = false;

  /** @type {{x:number,y:number,z:number,kind:string,label:string}[]} */
  let pathCache = [];
  let playing = true;
  let frameIdx = 0; // индекс точки на пути (кадр)
  let animSegT = 0; // 0..1 внутри текущего сегмента при play
  let lastTs = 0;

  const KIND_LABEL = {
    approach: "Подход",
    travel: "Переезд",
    probe: "Замер",
    retract: "Отвод",
    home: "Дом",
    from_home: "Из дома",
    to_home: "В дом",
  };

  function $(id) {
    return document.getElementById(id);
  }

  function project(x, y, z, scale, cx, cy) {
    const cyaw = Math.cos(yaw);
    const syaw = Math.sin(yaw);
    const cp = Math.cos(pitch);
    const sp = Math.sin(pitch);
    const x1 = x * cyaw - y * syaw;
    const y1 = x * syaw + y * cyaw;
    const y2 = y1 * cp - z * sp;
    const z2 = y1 * sp + z * cp;
    return {
      sx: cx + x1 * scale,
      sy: cy - z2 * scale,
      depth: y2,
    };
  }

  function drawLine(a, b, color, width) {
    ctx.beginPath();
    ctx.moveTo(a.sx, a.sy);
    ctx.lineTo(b.sx, b.sy);
    ctx.strokeStyle = color;
    ctx.lineWidth = width || 1.5;
    ctx.stroke();
  }

  function drawPoly(pts, fill, stroke, width) {
    if (!pts.length) return;
    ctx.beginPath();
    ctx.moveTo(pts[0].sx, pts[0].sy);
    for (let i = 1; i < pts.length; i++) ctx.lineTo(pts[i].sx, pts[i].sy);
    ctx.closePath();
    if (fill) {
      ctx.fillStyle = fill;
      ctx.fill();
    }
    if (stroke) {
      ctx.strokeStyle = stroke;
      ctx.lineWidth = width || 1.2;
      ctx.stroke();
    }
  }

  function drawBox(hx, hy, hz, scale, cx, cy) {
    const c = [
      [-hx, -hy, 0],
      [hx, -hy, 0],
      [hx, hy, 0],
      [-hx, hy, 0],
      [-hx, -hy, hz],
      [hx, -hy, hz],
      [hx, hy, hz],
      [-hx, hy, hz],
    ].map((p) => project(p[0], p[1], p[2], scale, cx, cy));

    const faces = [
      [0, 1, 2, 3],
      [4, 5, 6, 7],
      [0, 1, 5, 4],
      [1, 2, 6, 5],
      [2, 3, 7, 6],
      [3, 0, 4, 7],
    ];
    const faceAvg = faces.map((f) => {
      let d = 0;
      for (const i of f) d += c[i].depth;
      return { f, d: d / f.length };
    });
    faceAvg.sort((a, b) => a.d - b.d);
    for (const { f } of faceAvg) {
      const pts = f.map((i) => c[i]);
      const isTop = f[0] >= 4;
      drawPoly(
        pts,
        isTop ? "rgba(143,156,255,0.22)" : "rgba(143,156,255,0.10)",
        "rgba(143,156,255,0.55)",
        1.2
      );
    }
  }

  /** Цилиндр: ось Z, радиус r, высота hz */
  function drawCylinder(r, hz, scale, cx, cy) {
    const segs = 28;
    const bot = [];
    const top = [];
    for (let i = 0; i < segs; i++) {
      const a = (i / segs) * Math.PI * 2;
      const x = r * Math.cos(a);
      const y = r * Math.sin(a);
      bot.push(project(x, y, 0, scale, cx, cy));
      top.push(project(x, y, hz, scale, cx, cy));
    }
    // боковые грани (от дальних к ближним)
    const sides = [];
    for (let i = 0; i < segs; i++) {
      const j = (i + 1) % segs;
      const depth = (bot[i].depth + bot[j].depth + top[i].depth + top[j].depth) / 4;
      sides.push({ i, j, depth });
    }
    sides.sort((a, b) => a.depth - b.depth);
    for (const s of sides) {
      drawPoly(
        [bot[s.i], bot[s.j], top[s.j], top[s.i]],
        "rgba(143,156,255,0.10)",
        "rgba(143,156,255,0.35)",
        1
      );
    }
    drawPoly(bot, "rgba(143,156,255,0.08)", "rgba(143,156,255,0.45)", 1.2);
    drawPoly(top, "rgba(143,156,255,0.22)", "rgba(143,156,255,0.65)", 1.4);
  }

  function drawAxes(ox, oy, oz, len, scale, cx, cy) {
    const o = project(ox, oy, oz, scale, cx, cy);
    const ax = project(ox + len, oy, oz, scale, cx, cy);
    const ay = project(ox, oy + len, oz, scale, cx, cy);
    const az = project(ox, oy, oz + len, scale, cx, cy);
    drawLine(o, ax, "#e07a6a", 2.2);
    drawLine(o, ay, "#6dbf8a", 2.2);
    drawLine(o, az, "#7ec8e3", 2.2);
    ctx.fillStyle = "#e8c547";
    ctx.beginPath();
    ctx.arc(o.sx, o.sy, 4.5, 0, Math.PI * 2);
    ctx.fill();
    ctx.font = "600 11px system-ui,sans-serif";
    ctx.fillStyle = "#e07a6a";
    ctx.fillText("X", ax.sx + 4, ax.sy);
    ctx.fillStyle = "#6dbf8a";
    ctx.fillText("Y", ay.sx + 4, ay.sy);
    ctx.fillStyle = "#7ec8e3";
    ctx.fillText("Z", az.sx + 4, az.sy);
  }

  /** Точка «дома» станка — снаружи заготовки (G28). */
  function homePark(snap, approachZ) {
    const hx = Math.max(20, Number(snap.blankX) / 2 || 20);
    const hy = Math.max(20, Number(snap.blankY) / 2 || 20);
    const margin = Math.max(36, Math.max(hx, hy) * 0.4);
    return {
      x: hx + margin,
      y: hy + margin,
      z: approachZ + Math.max(28, Math.abs(Number(snap.approachZ) || 10) * 1.5),
    };
  }

  function pushFrame(path, nRef, x, y, z, kind, labelSuffix, ptIndex) {
    nRef.n += 1;
    const base = KIND_LABEL[kind] || kind;
    path.push({
      x,
      y,
      z,
      kind,
      label: `N${String(nRef.n * 10).padStart(4, "0")} ${base}${labelSuffix || ""}`,
      ptIndex: ptIndex || 0,
    });
  }

  function appendHomeFooter(path, nRef, snap, park) {
    const footZ = Boolean(snap.homeZ);
    const footY = Boolean(snap.homeY);
    const footX = Boolean(snap.homeX);
    if (!path.length || !(footZ || footY || footX)) return;
    const last = path[path.length - 1];
    let cx = last.x;
    let cy = last.y;
    let cz = last.z;
    if (footZ) {
      cz = park.z;
      pushFrame(path, nRef, cx, cy, cz, "to_home", " Z (G28)", 0);
    }
    if (footY) {
      cy = park.y;
      pushFrame(path, nRef, cx, cy, cz, "to_home", " Y (G28)", 0);
    }
    if (footX) {
      cx = park.x;
      pushFrame(path, nRef, cx, cy, cz, "to_home", " X (G28)", 0);
    }
    if (cx !== park.x || cy !== park.y || cz !== park.z) {
      pushFrame(path, nRef, park.x, park.y, park.z, "home", "", 0);
    }
  }

  /** Угол XYZ (O9103 §6.5): касания X → Y → Z с возвратом к подъезду */
  function buildCornerPath(snap) {
    const ox = Number(snap.originX) || 0;
    const oy = Number(snap.originY) || 0;
    const hz = Math.max(8, Number(snap.blankZ) || 50);
    const clear = Math.max(6, Number(snap.clearance) || 15);
    const dirX = Number(snap.dirX) || 1;
    const dirY = Number(snap.dirY) || 1;
    const stepX = Math.max(4, Math.abs(Number(snap.stepX) || 10));
    const stepY = Math.max(4, Math.abs(Number(snap.stepY) || 10));
    const stepZ = Math.max(4, Math.abs(Number(snap.stepZ) || 10));
    const sideZ = Math.max(hz * 0.35, hz - Math.min(stepZ, hz * 0.5));
    // подъезд снаружи угла (в системе центра заготовки)
    const sx = ox - dirX * clear;
    const sy = oy - dirY * clear;
    const az = hz + Math.max(12, Math.abs(Number(snap.approachZ) || 100) * 0.08);
    const park = homePark(snap, az);
    const path = [];
    const nRef = { n: 0 };
    const showHeaderHome = snap.headerHome !== false;
    const anyHome = showHeaderHome || snap.homeZ || snap.homeY || snap.homeX;

    if (anyHome) {
      pushFrame(path, nRef, park.x, park.y, park.z, "home", " (G28)", 0);
      pushFrame(path, nRef, sx, sy, az, "from_home", "", 0);
    } else {
      pushFrame(path, nRef, sx, sy, az, "approach", "", 0);
    }

    // 1) X — плоскость YZ
    pushFrame(path, nRef, sx, sy, sideZ, "travel", " · к X", 1);
    pushFrame(path, nRef, ox, sy, sideZ, "probe", " · X", 1);
    pushFrame(path, nRef, sx, sy, sideZ, "retract", "", 1);
    pushFrame(path, nRef, sx, sy, az, "travel", "", 1);

    // 2) Y — плоскость XZ
    pushFrame(path, nRef, sx, sy, sideZ, "travel", " · к Y", 2);
    pushFrame(path, nRef, sx, oy, sideZ, "probe", " · Y", 2);
    pushFrame(path, nRef, sx, sy, sideZ, "retract", "", 2);
    pushFrame(path, nRef, sx, sy, az, "travel", "", 2);

    // 3) Z — плоскость XY (верх)
    const midX = ox - dirX * (clear * 0.45);
    const midY = oy - dirY * (clear * 0.45);
    pushFrame(path, nRef, midX, midY, az, "travel", " · к Z", 3);
    pushFrame(path, nRef, midX, midY, Math.max(0, hz - stepZ * 0.15), "probe", " · Z", 3);
    pushFrame(path, nRef, midX, midY, az, "retract", "", 3);

    appendHomeFooter(path, nRef, snap, park);
    return path;
  }

  /** Гибкая привязка: probes[] из buildBindBody */
  function buildBindPath(snap) {
    const probes = snap.probes || [];
    if (probes.length === 1 && probes[0].kind === "corner") {
      return buildCornerPath({ ...snap, ...probes[0] });
    }
    if (probes.some((p) => p.kind === "corner")) {
      return buildCornerPath(snap);
    }

    const ox = Number(snap.originX) || 0;
    const oy = Number(snap.originY) || 0;
    const hz = Math.max(8, Number(snap.blankZ) || 50);
    const az = hz + Math.max(12, Math.abs(Number(snap.approachZ) || 100) * 0.08);
    const clear = Math.max(6, Number(snap.clearance) || 15);
    const park = homePark(snap, az);
    const path = [];
    const nRef = { n: 0 };
    const showHeaderHome = snap.headerHome !== false;
    const anyHome = showHeaderHome || snap.homeZ || snap.homeY || snap.homeX;

    let started = false;
    const ensureStart = (x, y) => {
      if (started) return;
      if (anyHome) {
        pushFrame(path, nRef, park.x, park.y, park.z, "home", " (G28)", 0);
        pushFrame(path, nRef, x, y, az, "from_home", "", 0);
      } else {
        pushFrame(path, nRef, x, y, az, "approach", "", 0);
      }
      started = true;
    };

    probes.forEach((pr, idx) => {
      const i = idx + 1;
      if (pr.kind === "edgeX") {
        const sign = Number(pr.sign) || -1;
        const y = oy + Number(pr.y || 0);
        const sx = ox - sign * clear;
        const px = ox;
        const sideZ = Math.max(4, hz * 0.45);
        ensureStart(sx, y);
        pushFrame(path, nRef, sx, y, az, "travel", " · к X", i);
        pushFrame(path, nRef, sx, y, sideZ, "travel", "", i);
        pushFrame(path, nRef, px, y, sideZ, "probe", " · X", i);
        pushFrame(path, nRef, sx, y, sideZ, "retract", "", i);
        pushFrame(path, nRef, sx, y, az, "travel", "", i);
      } else if (pr.kind === "edgeY") {
        const sign = Number(pr.sign) || -1;
        const x = ox + Number(pr.x || 0);
        const sy = oy - sign * clear;
        const py = oy;
        const sideZ = Math.max(4, hz * 0.45);
        ensureStart(x, sy);
        pushFrame(path, nRef, x, sy, az, "travel", " · к Y", i);
        pushFrame(path, nRef, x, sy, sideZ, "travel", "", i);
        pushFrame(path, nRef, x, py, sideZ, "probe", " · Y", i);
        pushFrame(path, nRef, x, sy, sideZ, "retract", "", i);
        pushFrame(path, nRef, x, sy, az, "travel", "", i);
      } else if (pr.kind === "hole" || pr.kind === "boss" || pr.kind === "webX" || pr.kind === "webY") {
        const cx = ox + Number(pr.x || 0);
        const cy = oy + Number(pr.y || 0);
        const r = Math.max(8, Number(pr.d || 40) / 2);
        const depth = hz + (Number(pr.zDepth) || -5);
        const pz = Math.max(2, Math.min(hz * 0.85, depth > 0 ? depth : hz * 0.55));
        ensureStart(cx, cy);
        pushFrame(path, nRef, cx, cy, az, "travel", ` · ${pr.kind}`, i);
        // крест касаний по диаметру
        pushFrame(path, nRef, cx + r, cy, pz, "probe", " · +X", i);
        pushFrame(path, nRef, cx, cy, az, "retract", "", i);
        pushFrame(path, nRef, cx - r, cy, pz, "probe", " · −X", i);
        pushFrame(path, nRef, cx, cy, az, "retract", "", i);
        if (pr.kind === "hole" || pr.kind === "boss" || pr.kind === "webY") {
          pushFrame(path, nRef, cx, cy + r, pz, "probe", " · +Y", i);
          pushFrame(path, nRef, cx, cy, az, "retract", "", i);
          pushFrame(path, nRef, cx, cy - r, pz, "probe", " · −Y", i);
          pushFrame(path, nRef, cx, cy, az, "retract", "", i);
        }
      } else if (pr.kind === "zBlank") {
        const x = ox + Number(pr.x || 0);
        const y = oy + Number(pr.y || 0);
        ensureStart(x, y);
        pushFrame(path, nRef, x, y, az, "travel", " · Z", i);
        pushFrame(path, nRef, x, y, Math.max(0, hz - 2), "probe", " · Z заг.", i);
        pushFrame(path, nRef, x, y, az, "retract", "", i);
      } else if (pr.kind === "zTile") {
        const x = ox + Number(pr.x || 0);
        const y = oy + Number(pr.y || 0);
        const th = Math.max(4, Number(pr.tileT) || 10);
        ensureStart(x, y);
        pushFrame(path, nRef, x, y, az, "travel", " · плитка", i);
        pushFrame(path, nRef, x, y, Math.max(0, th - 1), "probe", " · Z плитка", i);
        pushFrame(path, nRef, x, y, az, "retract", "", i);
      }
    });

    if (!started && anyHome) {
      pushFrame(path, nRef, park.x, park.y, park.z, "home", " (G28)", 0);
    }
    appendHomeFooter(path, nRef, snap, park);
    return path;
  }

  function buildPath(snap) {
    if (snap && (snap.mode === "corner" || snap.mode === "bind")) {
      if (snap.mode === "bind") return buildBindPath(snap);
      return buildCornerPath(snap);
    }

    const pts = snap.points || [];
    const ox = Number(snap.originX) || 0;
    const oy = Number(snap.originY) || 0;
    const hz = Number(snap.blankZ) || 0;
    const az = hz + Math.abs(Number(snap.approachZ) || 10);
    const pz =
      hz +
      (Number(snap.stepZ) < 0
        ? Number(snap.stepZ)
        : -Math.abs(Number(snap.stepZ) || 11));
    const park = homePark(snap, az);
    const path = [];
    const nRef = { n: 0 };
    const showHeaderHome = snap.headerHome !== false; // шапка всегда G28 Z/Y
    const footZ = Boolean(snap.homeZ);
    const footY = Boolean(snap.homeY);
    const footX = Boolean(snap.homeX);
    const anyHome = showHeaderHome || footZ || footY || footX;

    // Старт: после шапки УП (G28 Z → G28 Y) датчик в доме
    if (anyHome) {
      pushFrame(path, nRef, park.x, park.y, park.z, "home", " (G28)", 0);
    }

    pts.forEach((p, i) => {
      const x = ox + Number(p.x);
      const y = oy + Number(p.y);
      if (i === 0 && anyHome) {
        pushFrame(path, nRef, x, y, az, "from_home", "", 1);
      } else {
        pushFrame(path, nRef, x, y, az, i === 0 ? "approach" : "travel", "", i + 1);
      }
      pushFrame(path, nRef, x, y, Math.max(0, pz), "probe", ` · т.${i + 1}`, i + 1);
      pushFrame(path, nRef, x, y, az, "retract", "", i + 1);
    });

    appendHomeFooter(path, nRef, snap, park);
    return path;
  }

  function sensorPos() {
    if (!pathCache.length) return null;
    const i = Math.max(0, Math.min(frameIdx, pathCache.length - 1));
    if (!playing || i >= pathCache.length - 1) {
      return pathCache[i];
    }
    const a = pathCache[i];
    const b = pathCache[i + 1];
    const t = animSegT;
    return {
      x: a.x + (b.x - a.x) * t,
      y: a.y + (b.y - a.y) * t,
      z: a.z + (b.z - a.z) * t,
      kind: b.kind,
      label: b.label,
    };
  }

  function drawPath(path, scale, cx, cy) {
    if (path.length < 2) return;
    const active = Math.max(0, Math.min(frameIdx, path.length - 1));
    for (let i = 1; i < path.length; i++) {
      const a = project(path[i - 1].x, path[i - 1].y, path[i - 1].z, scale, cx, cy);
      const b = project(path[i].x, path[i].y, path[i].z, scale, cx, cy);
      const done = i <= active;
      const current = i === active + (playing && animSegT > 0 ? 1 : 0) || i - 1 === active;
      const kind = path[i].kind;
      let color = "rgba(212,160,23,0.35)";
      let w = 1.2;
      if (done || (playing && i === active + 1)) {
        if (kind === "probe") {
          color = "#e07a6a";
          w = 2.2;
        } else if (kind === "travel") {
          color = "rgba(126,200,227,0.85)";
          w = 1.6;
        } else if (kind === "from_home") {
          color = "rgba(167,139,250,0.95)";
          w = 2.0;
        } else if (kind === "to_home" || kind === "home") {
          color = "rgba(52,211,153,0.95)";
          w = 2.0;
        } else {
          color = "rgba(212,160,23,0.9)";
          w = 1.8;
        }
      }
      if (current && !playing) {
        w += 0.6;
      }
      drawLine(a, b, color, w);
    }

    path.forEach((p) => {
      const q = project(p.x, p.y, p.z, scale, cx, cy);
      if (p.kind === "probe") {
        ctx.fillStyle = "#e8c547";
        ctx.beginPath();
        ctx.arc(q.sx, q.sy, 3.2, 0, Math.PI * 2);
        ctx.fill();
      } else if (p.kind === "home") {
        // маркер дома
        ctx.fillStyle = "#34d399";
        ctx.strokeStyle = "rgba(255,255,255,0.7)";
        ctx.lineWidth = 1.2;
        ctx.beginPath();
        ctx.moveTo(q.sx, q.sy - 6);
        ctx.lineTo(q.sx + 5, q.sy - 1);
        ctx.lineTo(q.sx + 5, q.sy + 5);
        ctx.lineTo(q.sx - 5, q.sy + 5);
        ctx.lineTo(q.sx - 5, q.sy - 1);
        ctx.closePath();
        ctx.fill();
        ctx.stroke();
      }
    });

    const s = sensorPos();
    if (!s) return;
    const sp = project(s.x, s.y, s.z, scale, cx, cy);
    ctx.fillStyle = "#8f9cff";
    ctx.strokeStyle = "rgba(255,255,255,0.65)";
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.arc(sp.sx, sp.sy, 6, 0, Math.PI * 2);
    ctx.fill();
    ctx.stroke();
    const tip = project(s.x, s.y, Math.max(0, s.z - 12), scale, cx, cy);
    drawLine(sp, tip, "rgba(232,238,242,0.75)", 1.5);
  }

  function fitScale(snap, w, h) {
    const hx = Math.max(20, snap.blankX / 2);
    const hy = Math.max(20, snap.blankY / 2);
    const hz = Math.max(20, snap.blankZ);
    let span = Math.max(hx, hy) * 2.4 + hz;
    // дом снаружи заготовки — чуть отдаляем камеру
    if (snap.headerHome !== false || snap.homeZ || snap.homeY || snap.homeX) {
      span *= 1.38;
    }
    return ((Math.min(w, h) * 0.42) / span) * zoom;
  }

  function updateHud() {
    const zoomEl = $("hb-viz-zoom");
    if (zoomEl) zoomEl.textContent = Math.round(zoom * 100) + "%";
    const frameEl = $("hb-viz-frame");
    const total = pathCache.length;
    const i = total ? Math.min(frameIdx, total - 1) + 1 : 0;
    const cur = total ? pathCache[Math.min(frameIdx, total - 1)] : null;
    if (frameEl) {
      frameEl.textContent = total
        ? `Кадр ${i}/${total}` + (cur ? ` · ${KIND_LABEL[cur.kind] || cur.kind}` : "")
        : "Нет кадров";
    }
    const detail = $("hb-viz-frame-detail");
    if (detail) detail.textContent = cur ? cur.label : "";
    const playBtn = $("hb-viz-play");
    if (playBtn) {
      playBtn.textContent = playing ? "❚❚" : "▶";
      playBtn.title = playing ? "Пауза" : "Пуск";
      playBtn.setAttribute("aria-label", playing ? "Пауза" : "Пуск");
    }
  }

  function paint() {
    if (!canvas || !ctx || !lastSnap) return;
    const dpr = window.devicePixelRatio || 1;
    const w = canvas.clientWidth;
    const h = canvas.clientHeight;
    if (w < 10 || h < 10) return;
    if (canvas.width !== Math.floor(w * dpr) || canvas.height !== Math.floor(h * dpr)) {
      canvas.width = Math.floor(w * dpr);
      canvas.height = Math.floor(h * dpr);
    }
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);

    const g = ctx.createLinearGradient(0, 0, 0, h);
    g.addColorStop(0, "rgba(15,20,28,0.95)");
    g.addColorStop(1, "rgba(20,28,38,0.98)");
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, w, h);

    const cx = w * 0.5;
    const cy = h * 0.56;
    const scale = fitScale(lastSnap, w, h);
    const hx = lastSnap.blankX / 2;
    const hy = lastSnap.blankY / 2;
    const hz = lastSnap.blankZ;

    ctx.globalAlpha = 0.35;
    const gridN = 4;
    for (let i = -gridN; i <= gridN; i++) {
      const t = (i / gridN) * Math.max(hx, hy) * 1.15;
      drawLine(
        project(-hx * 1.15, t, 0, scale, cx, cy),
        project(hx * 1.15, t, 0, scale, cx, cy),
        "rgba(155,176,216,0.25)",
        1
      );
      drawLine(
        project(t, -hy * 1.15, 0, scale, cx, cy),
        project(t, hy * 1.15, 0, scale, cx, cy),
        "rgba(155,176,216,0.25)",
        1
      );
    }
    ctx.globalAlpha = 1;

    if (lastSnap.shape === "cylinder") {
      const r = Math.max(8, Number(lastSnap.diameter) || hx);
      drawCylinder(r, hz, scale, cx, cy);
      drawAxes(lastSnap.originX, lastSnap.originY, hz, r * 0.45, scale, cx, cy);
    } else {
      drawBox(hx, hy, hz, scale, cx, cy);
      drawAxes(lastSnap.originX, lastSnap.originY, hz, Math.min(hx, hy) * 0.35, scale, cx, cy);
    }
    // соседняя плитка для Z
    const tilePr = (lastSnap.probes || []).find((p) => p.kind === "zTile");
    if (tilePr) {
      const tw = Math.max(8, Number(tilePr.tileW) || 40) / 2;
      const th = Math.max(8, Number(tilePr.tileH) || 40) / 2;
      const tt = Math.max(4, Number(tilePr.tileT) || 10);
      const tx = Number(lastSnap.originX || 0) + Number(tilePr.x || 0);
      const ty = Number(lastSnap.originY || 0) + Number(tilePr.y || 0);
      const corners = [
        [tx - tw, ty - th, 0],
        [tx + tw, ty - th, 0],
        [tx + tw, ty + th, 0],
        [tx - tw, ty + th, 0],
        [tx - tw, ty - th, tt],
        [tx + tw, ty - th, tt],
        [tx + tw, ty + th, tt],
        [tx - tw, ty + th, tt],
      ].map((p) => project(p[0], p[1], p[2], scale, cx, cy));
      drawPoly(
        [corners[4], corners[5], corners[6], corners[7]],
        "rgba(212,160,23,0.28)",
        "rgba(212,160,23,0.85)",
        1.3
      );
      [
        [0, 4],
        [1, 5],
        [2, 6],
        [3, 7],
      ].forEach(([a, b]) => drawLine(corners[a], corners[b], "rgba(212,160,23,0.55)", 1));
    }
    drawPath(pathCache, scale, cx, cy);

    ctx.font = "500 11px system-ui,sans-serif";
    ctx.fillStyle = "rgba(155,176,216,0.95)";
    ctx.fillText("ЛКМ — вращение · колесо — зум", 12, h - 12);
    updateHud();
  }

  function loop(ts) {
    if (playing && pathCache.length > 1) {
      const dt = lastTs ? Math.min(0.05, (ts - lastTs) / 1000) : 0;
      lastTs = ts;
      // ~1.2 сек на сегмент
      animSegT += dt / 1.15;
      while (animSegT >= 1 && frameIdx < pathCache.length - 1) {
        animSegT -= 1;
        frameIdx += 1;
      }
      if (frameIdx >= pathCache.length - 1 && animSegT >= 1) {
        frameIdx = 0;
        animSegT = 0;
      }
    } else {
      lastTs = ts;
    }
    paint();
    raf = requestAnimationFrame(loop);
  }

  function setZoom(z) {
    zoom = Math.max(0.35, Math.min(4.5, z));
    paint();
  }

  function stepFrame(dir) {
    playing = false;
    animSegT = 0;
    if (!pathCache.length) {
      updateHud();
      return;
    }
    frameIdx = Math.max(0, Math.min(pathCache.length - 1, frameIdx + dir));
    paint();
  }

  function togglePlay() {
    playing = !playing;
    animSegT = 0;
    if (playing && frameIdx >= pathCache.length - 1) frameIdx = 0;
    updateHud();
  }

  function resetFrame() {
    playing = false;
    frameIdx = 0;
    animSegT = 0;
    paint();
  }

  function onPointerDown(e) {
    dragging = true;
    lastX = e.clientX;
    lastY = e.clientY;
    if (canvas) canvas.setPointerCapture(e.pointerId);
  }
  function onPointerMove(e) {
    if (!dragging) return;
    const dx = e.clientX - lastX;
    const dy = e.clientY - lastY;
    lastX = e.clientX;
    lastY = e.clientY;
    yaw += dx * 0.01;
    pitch = Math.max(0.15, Math.min(1.35, pitch + dy * 0.01));
  }
  function onPointerUp(e) {
    dragging = false;
    try {
      if (canvas) canvas.releasePointerCapture(e.pointerId);
    } catch (_) {}
  }
  function onWheel(e) {
    e.preventDefault();
    const factor = e.deltaY > 0 ? 0.9 : 1.11;
    setZoom(zoom * factor);
  }

  function bindControls() {
    const zin = $("hb-viz-zoom-in");
    const zout = $("hb-viz-zoom-out");
    const play = $("hb-viz-play");
    const prev = $("hb-viz-prev");
    const next = $("hb-viz-next");
    const restart = $("hb-viz-restart");
    if (zin) zin.addEventListener("click", () => setZoom(zoom * 1.2));
    if (zout) zout.addEventListener("click", () => setZoom(zoom / 1.2));
    if (play) play.addEventListener("click", () => togglePlay());
    if (prev) prev.addEventListener("click", () => stepFrame(-1));
    if (next) next.addEventListener("click", () => stepFrame(1));
    if (restart) restart.addEventListener("click", () => resetFrame());
  }

  function bind() {
    wrap = $(ROOT);
    canvas = $("hb-viz-canvas");
    if (!wrap || !canvas) return false;
    ctx = canvas.getContext("2d");
    if (!bound) {
      canvas.addEventListener("pointerdown", onPointerDown);
      canvas.addEventListener("pointermove", onPointerMove);
      canvas.addEventListener("pointerup", onPointerUp);
      canvas.addEventListener("pointercancel", onPointerUp);
      canvas.addEventListener("wheel", onWheel, { passive: false });
      bindControls();
      if (typeof ResizeObserver !== "undefined") {
        ro = new ResizeObserver(() => paint());
        ro.observe(wrap);
      }
      bound = true;
    }
    if (!raf) raf = requestAnimationFrame(loop);
    return true;
  }

  function update(snap) {
    if (!canvas && !bind()) return;
    const prevLen = pathCache.length;
    lastSnap = snap;
    pathCache = buildPath(snap);
    if (frameIdx >= pathCache.length) frameIdx = Math.max(0, pathCache.length - 1);
    if (!prevLen && pathCache.length) {
      frameIdx = 0;
      animSegT = 0;
    }
    wrap = $(ROOT);
    if (wrap) wrap.hidden = false;
    paint();
  }

  function hide() {
    wrap = $(ROOT);
    if (wrap) wrap.hidden = true;
  }

  window.HexbindViz = { update, hide, bind };
})();
