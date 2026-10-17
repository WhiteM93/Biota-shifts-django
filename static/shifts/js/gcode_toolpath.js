/**
 * Разбор G-кода → точки траектории (rapid / feed) для 3D-предпросмотра.
 * Экспорт ESM + window.BiotaGcodeToolpath для вызова из обычных скриптов.
 */
const MAX_POINTS = 80000;
const ARC_CHORD_DEG = 6;

function stripComments(line) {
  let s = String(line || "");
  const semi = s.indexOf(";");
  if (semi >= 0) s = s.slice(0, semi);
  // Убрать (комментарии), в т.ч. вложенные по одному проходу
  let out = "";
  let depth = 0;
  for (let i = 0; i < s.length; i++) {
    const ch = s[i];
    if (ch === "(") {
      depth++;
      continue;
    }
    if (ch === ")") {
      if (depth > 0) depth--;
      continue;
    }
    if (depth === 0) out += ch;
  }
  return out.trim();
}

function parseWords(line) {
  const words = [];
  const re = /([A-Za-z])\s*([-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?)/g;
  let m;
  while ((m = re.exec(line)) !== null) {
    words.push({ letter: m[1].toUpperCase(), value: parseFloat(m[2]) });
  }
  return words;
}

function pushSegment(target, ax, ay, az, bx, by, bz, lineNo) {
  if (!Number.isFinite(ax) || !Number.isFinite(ay) || !Number.isFinite(az)) return;
  if (!Number.isFinite(bx) || !Number.isFinite(by) || !Number.isFinite(bz)) return;
  if (ax === bx && ay === by && az === bz) return;
  target.push(ax, ay, az, bx, by, bz, lineNo);
}

function expandArcXY(cx, cy, x0, y0, z0, x1, y1, z1, cw, out, lineNo, maxPtsLeft) {
  const a0 = Math.atan2(y0 - cy, x0 - cx);
  let a1 = Math.atan2(y1 - cy, x1 - cx);
  const r = Math.hypot(x0 - cx, y0 - cy);
  if (!(r > 1e-9)) {
    pushSegment(out, x0, y0, z0, x1, y1, z1, lineNo);
    return 1;
  }
  let da = a1 - a0;
  if (cw) {
    while (da > 0) da -= Math.PI * 2;
    if (Math.abs(da) < 1e-9) da = -Math.PI * 2;
  } else {
    while (da < 0) da += Math.PI * 2;
    if (Math.abs(da) < 1e-9) da = Math.PI * 2;
  }
  const steps = Math.max(2, Math.ceil((Math.abs(da) * 180) / Math.PI / ARC_CHORD_DEG));
  const n = Math.min(steps, Math.max(1, maxPtsLeft));
  let px = x0;
  let py = y0;
  let pz = z0;
  let count = 0;
  for (let i = 1; i <= n; i++) {
    const t = i / n;
    const a = a0 + da * t;
    const nx = cx + r * Math.cos(a);
    const ny = cy + r * Math.sin(a);
    const nz = z0 + (z1 - z0) * t;
    pushSegment(out, px, py, pz, nx, ny, nz, lineNo);
    px = nx;
    py = ny;
    pz = nz;
    count++;
  }
  return count;
}

/**
 * @param {string} text
 * @returns {{
 *   rapid: Float32Array,
 *   feed: Float32Array,
 *   rapidLineNos: Int32Array,
 *   feedLineNos: Int32Array,
 *   bbox: {min:[number,number,number], max:[number,number,number]}|null,
 *   pointCount: number,
 *   truncated: boolean,
 *   moveCount: number
 * }}
 */
export function parseGcodeToolpath(text) {
  const rapidRaw = [];
  const feedRaw = [];
  let truncated = false;
  let moveCount = 0;
  let pointBudget = MAX_POINTS;

  let x = 0;
  let y = 0;
  let z = 0;
  let absolute = true;
  let motion = 0; // 0 rapid, 1 feed, 2 cw, 3 ccw
  let plane = 17; // G17 XY
  let havePos = false;

  const lines = String(text || "").split(/\r?\n/);
  for (let li = 0; li < lines.length; li++) {
    if (pointBudget <= 0) {
      truncated = true;
      break;
    }
    const cleaned = stripComments(lines[li]);
    if (!cleaned) continue;
    const words = parseWords(cleaned);
    if (!words.length) continue;

    let nx = null;
    let ny = null;
    let nz = null;
    let iOff = null;
    let jOff = null;
    let kOff = null;
    let rVal = null;
    let motionThis = null;
    let g28 = false;

    for (let wi = 0; wi < words.length; wi++) {
      const { letter, value } = words[wi];
      if (letter === "G") {
        const g = Math.round(value);
        if (g === 90) absolute = true;
        else if (g === 91) absolute = false;
        else if (g === 17) plane = 17;
        else if (g === 18) plane = 18;
        else if (g === 19) plane = 19;
        else if (g === 0) motionThis = 0;
        else if (g === 1) motionThis = 1;
        else if (g === 2) motionThis = 2;
        else if (g === 3) motionThis = 3;
        else if (g === 28 || g === 30) g28 = true;
      } else if (letter === "X") nx = value;
      else if (letter === "Y") ny = value;
      else if (letter === "Z") nz = value;
      else if (letter === "I") iOff = value;
      else if (letter === "J") jOff = value;
      else if (letter === "K") kOff = value;
      else if (letter === "R") rVal = value;
    }

    if (motionThis !== null) motion = motionThis;

    const hasAxis = nx !== null || ny !== null || nz !== null;
    if (!hasAxis && !g28) continue;

    let tx = x;
    let ty = y;
    let tz = z;
    if (g28) {
      // Упрощённо: указанные оси → 0, иначе все в 0
      if (nx === null && ny === null && nz === null) {
        tx = 0;
        ty = 0;
        tz = 0;
      } else {
        if (nx !== null) tx = 0;
        if (ny !== null) ty = 0;
        if (nz !== null) tz = 0;
      }
    } else if (absolute) {
      if (nx !== null) tx = nx;
      if (ny !== null) ty = ny;
      if (nz !== null) tz = nz;
    } else {
      if (nx !== null) tx = x + nx;
      if (ny !== null) ty = y + ny;
      if (nz !== null) tz = z + nz;
    }

    const lineNo = li + 1;
    const kind = g28 ? 0 : motion;
    const dest = kind === 0 ? rapidRaw : feedRaw;

    if (havePos && (kind === 2 || kind === 3) && plane === 17 && !g28) {
      if (iOff !== null || jOff !== null) {
        const cx = x + (iOff || 0);
        const cy = y + (jOff || 0);
        const used = expandArcXY(cx, cy, x, y, z, tx, ty, tz, kind === 2, dest, lineNo, pointBudget);
        pointBudget -= used;
      } else if (rVal !== null && Number.isFinite(rVal)) {
        const dx = tx - x;
        const dy = ty - y;
        const chord = Math.hypot(dx, dy);
        if (chord < 1e-9) {
          pushSegment(dest, x, y, z, tx, ty, tz, lineNo);
          pointBudget -= 1;
        } else {
          let rr = Math.abs(rVal);
          if (rr < chord / 2) rr = chord / 2;
          const h = Math.sqrt(Math.max(0, rr * rr - (chord * chord) / 4));
          const mx = (x + tx) / 2;
          const my = (y + ty) / 2;
          const ux = -dy / chord;
          const uy = dx / chord;
          const sign = (kind === 2 ? -1 : 1) * (rVal >= 0 ? 1 : -1);
          const cx = mx + ux * h * sign;
          const cy = my + uy * h * sign;
          const used = expandArcXY(cx, cy, x, y, z, tx, ty, tz, kind === 2, dest, lineNo, pointBudget);
          pointBudget -= used;
        }
      } else {
        pushSegment(dest, x, y, z, tx, ty, tz, lineNo);
        pointBudget -= 1;
      }
      moveCount++;
    } else if (havePos) {
      pushSegment(dest, x, y, z, tx, ty, tz, lineNo);
      pointBudget -= 1;
      moveCount++;
    }

    x = tx;
    y = ty;
    z = tz;
    havePos = true;
    if (pointBudget <= 0) truncated = true;
  }

  function pack(raw) {
    const nSeg = Math.floor(raw.length / 7);
    const coords = new Float32Array(nSeg * 6);
    const lineNos = new Int32Array(nSeg);
    for (let i = 0; i < nSeg; i++) {
      const o = i * 7;
      const c = i * 6;
      coords[c] = raw[o];
      coords[c + 1] = raw[o + 1];
      coords[c + 2] = raw[o + 2];
      coords[c + 3] = raw[o + 3];
      coords[c + 4] = raw[o + 4];
      coords[c + 5] = raw[o + 5];
      lineNos[i] = raw[o + 6] | 0;
    }
    return { coords, lineNos };
  }

  const rapid = pack(rapidRaw);
  const feed = pack(feedRaw);
  let minX = Infinity;
  let minY = Infinity;
  let minZ = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;
  let maxZ = -Infinity;
  function grow(arr) {
    for (let i = 0; i < arr.length; i += 3) {
      const px = arr[i];
      const py = arr[i + 1];
      const pz = arr[i + 2];
      if (px < minX) minX = px;
      if (py < minY) minY = py;
      if (pz < minZ) minZ = pz;
      if (px > maxX) maxX = px;
      if (py > maxY) maxY = py;
      if (pz > maxZ) maxZ = pz;
    }
  }
  grow(rapid.coords);
  grow(feed.coords);
  const pointCount = (rapid.coords.length + feed.coords.length) / 3;
  const bbox =
    pointCount > 0
      ? { min: [minX, minY, minZ], max: [maxX, maxY, maxZ] }
      : null;

  return {
    rapid: rapid.coords,
    feed: feed.coords,
    rapidLineNos: rapid.lineNos,
    feedLineNos: feed.lineNos,
    bbox,
    pointCount,
    truncated,
    moveCount,
  };
}

const api = { parseGcodeToolpath, MAX_POINTS };
if (typeof window !== "undefined") {
  window.BiotaGcodeToolpath = api;
}
export default api;
