/**
 * Генератор программ привязки Hexagon (вкладка калькулятора).
 * Формат как MetaWork / Fanuc + Hexagon m&h (G65 P9103)
 */
(function () {
"use strict";

const STORAGE_KEY = "hexagon-probe-gen-v8";
const ROOT_ID = "calc-panel-hexbind";

function $(id) {
  return document.getElementById(id);
}

/** @typedef {{ key: string, label: string, type?: string, step?: string, rows?: number, options?: {value:string,label:string}[], default: string|number|boolean, readonly?: boolean, wide?: boolean, span2?: boolean, section?: string, chip?: string, pattern?: string, maxlength?: string, placeholder?: string, showIf?: (s: Record<string, any>) => boolean }} FieldDef */

/** Fanuc: G54 X=#5221 … G59 X=#5321 */
function mainWcsAxisVar(wcs, axis /*1=X,2=Y,3=Z*/) {
  return 5221 + 20 * (Number(wcs) - 54) + (Number(axis) - 1);
}

/** Fanuc G54.1 Pn: база #7001, шаг 20 */
function extWcsAxisVar(base, p, axis /*1=X,2=Y,3=Z*/) {
  return Number(base) + 20 * (Number(p) - 1) + (Number(axis) - 1);
}

function parseNumToken(raw) {
  const n = Number(String(raw || "").replace(",", "."));
  return Number.isFinite(n) ? n : NaN;
}

/**
 * Точки построчно:
 *   X1 Y0
 *   X-2 Y5
 *   X-123 Y-345
 *   X10.5Y-3.2
 * также старый вид: -234, 173.5  или  -234 173.5
 */
function parsePoints(text) {
  const points = [];
  for (const raw of String(text || "").split(/\r?\n/)) {
    let line = raw.replace(/[;#].*$/, "").trim();
    if (!line) continue;
    line = line.replace(/,/g, " ").replace(/\s+/g, " ").trim();

    const labeled = line.match(
      /^[Xx]\s*([+-]?\d*\.?\d+)\s*[Yy]\s*([+-]?\d*\.?\d+)\s*$/i
    );
    if (labeled) {
      const x = parseNumToken(labeled[1]);
      const y = parseNumToken(labeled[2]);
      if (Number.isFinite(x) && Number.isFinite(y)) points.push({ x, y });
      continue;
    }

    const labeledYx = line.match(
      /^[Yy]\s*([+-]?\d*\.?\d+)\s*[Xx]\s*([+-]?\d*\.?\d+)\s*$/i
    );
    if (labeledYx) {
      const y = parseNumToken(labeledYx[1]);
      const x = parseNumToken(labeledYx[2]);
      if (Number.isFinite(x) && Number.isFinite(y)) points.push({ x, y });
      continue;
    }

    // X1Y0 без пробела
    const tight = line.match(/^X\s*([+-]?\d*\.?\d+)\s*Y\s*([+-]?\d*\.?\d+)\s*$/i);
    if (tight) {
      const x = parseNumToken(tight[1]);
      const y = parseNumToken(tight[2]);
      if (Number.isFinite(x) && Number.isFinite(y)) points.push({ x, y });
      continue;
    }

    const parts = line.split(/[\s]+/).filter(Boolean);
    if (parts.length >= 2) {
      const x = parseNumToken(parts[0]);
      const y = parseNumToken(parts[1]);
      if (Number.isFinite(x) && Number.isFinite(y)) points.push({ x, y });
    }
  }
  return points;
}

function formatPointLine(x, y) {
  const round3 = (v) => {
    const n = Number(v);
    if (!Number.isFinite(n)) return 0;
    const r = Math.round(n * 1000) / 1000;
    return Number.isInteger(r) ? r : r;
  };
  const rx = round3(x);
  const ry = round3(y);
  const sx = Number.isInteger(rx) ? String(rx) : String(rx);
  const sy = Number.isInteger(ry) ? String(ry) : String(ry);
  return `X${sx} Y${sy}`;
}

/** Эталонный контур (центр заготовки = 0,0), мм */
const RAW_DEFAULT_POINTS = [
  [-234, 173.5],
  [-204, 173.5],
  [-65, 173.5],
  [-35, 173.5],
  [35, 173.5],
  [65, 173.5],
  [204, 173.5],
  [234, 173.5],
  [244, 105.5],
  [244, 75.5],
  [244, -75.5],
  [244, -105.5],
  [234, -173.5],
  [204, -173.5],
  [65, -173.5],
  [35, -173.5],
  [-35, -173.5],
  [-65, -173.5],
  [-204, -173.5],
  [-234, -173.5],
  [-244, -105.5],
  [-244, -75.5],
  [-244, 75.5],
  [-244, 105.5],
];

/** Плита: ширина (X), высота (Y), толщина (Z). Цилиндр: диаметр, длина (по Z). */
const DEFAULT_BLANK_W = 488;
const DEFAULT_BLANK_H = 347;
const DEFAULT_BLANK_T = 50;
const DEFAULT_BLANK_DIA = 120;
const DEFAULT_BLANK_LEN = 80;

function isCylinderBlank(s) {
  return String(s && s.blankShape) === "cylinder";
}

/** Габариты заготовки в системе центра (XY сверху, Z вверх) */
function blankExtents(s) {
  const shape = isCylinderBlank(s) ? "cylinder" : "plate";
  if (shape === "cylinder") {
    const dia = Number(s.blankDia);
    const len = Number(s.blankLen);
    const d = Number.isFinite(dia) && dia > 0 ? dia : DEFAULT_BLANK_DIA;
    const l = Number.isFinite(len) && len > 0 ? len : DEFAULT_BLANK_LEN;
    return { shape, w: d, h: d, t: l, dia: d, len: l };
  }
  const w = Number(s.blankW);
  const h = Number(s.blankH);
  const t = Number(s.blankT);
  return {
    shape: "plate",
    w: Number.isFinite(w) && w > 0 ? w : DEFAULT_BLANK_W,
    h: Number.isFinite(h) && h > 0 ? h : DEFAULT_BLANK_H,
    t: Number.isFinite(t) && t > 0 ? t : DEFAULT_BLANK_T,
  };
}

/** Положение нуля привязки в системе «центр заготовки» */
function originInCenterFrame(blankX, blankY, mode) {
  const hx = Number(blankX) / 2;
  const hy = Number(blankY) / 2;
  if (!Number.isFinite(hx) || !Number.isFinite(hy)) return { ox: 0, oy: 0 };
  switch (String(mode || "center")) {
    case "sw":
      return { ox: -hx, oy: -hy };
    case "se":
      return { ox: hx, oy: -hy };
    case "nw":
      return { ox: -hx, oy: hy };
    case "ne":
      return { ox: hx, oy: hy };
    case "px":
      return { ox: hx, oy: 0 };
    case "mx":
      return { ox: -hx, oy: 0 };
    case "py":
      return { ox: 0, oy: hy };
    case "my":
      return { ox: 0, oy: -hy };
    default:
      return { ox: 0, oy: 0 };
  }
}

/** Точки от центра заготовки → координаты относительно выбранной привязки */
function mapPointsToOrigin(points, blankX, blankY, mode) {
  const { ox, oy } = originInCenterFrame(blankX, blankY, mode);
  return points.map((p) => ({ x: Number(p.x) - ox, y: Number(p.y) - oy }));
}

/** Контур плиты по периметру (центр = 0,0) */
function buildContourFromBlank(blankW, blankH) {
  const bx = Number(blankW);
  const by = Number(blankH);
  const sx = Number.isFinite(bx) && bx > 0 ? bx / DEFAULT_BLANK_W : 1;
  const sy = Number.isFinite(by) && by > 0 ? by / DEFAULT_BLANK_H : 1;
  return RAW_DEFAULT_POINTS.map(([x, y]) => formatPointLine(x * sx, y * sy)).join("\n");
}

/** Контур по окружности цилиндра (вид сверху, ось Z) */
function buildContourCylinder(dia, count) {
  const d = Number(dia);
  const r = (Number.isFinite(d) && d > 0 ? d : DEFAULT_BLANK_DIA) / 2;
  const n = Math.max(8, Math.min(36, Math.floor(Number(count) || 16)));
  const lines = [];
  for (let i = 0; i < n; i++) {
    const a = (i / n) * Math.PI * 2;
    lines.push(formatPointLine(r * Math.cos(a), r * Math.sin(a)));
  }
  return lines.join("\n");
}

function buildContourForState(s) {
  const ext = blankExtents(s);
  if (ext.shape === "cylinder") return buildContourCylinder(ext.dia, 16);
  return buildContourFromBlank(ext.w, ext.h);
}

function originModeLabel(mode) {
  switch (String(mode || "center")) {
    case "sw":
      return "X- Y-";
    case "se":
      return "X+ Y-";
    case "nw":
      return "X- Y+";
    case "ne":
      return "X+ Y+";
    case "px":
      return "+X";
    case "mx":
      return "-X";
    case "py":
      return "+Y";
    case "my":
      return "-Y";
    default:
      return "CENTER";
  }
}

function normalizeOName(raw) {
  const s = String(raw || "").trim().toUpperCase();
  const exact = s.match(/^O(\d{4})$/);
  if (exact) return "O" + exact[1];
  const withO = s.match(/^O(\d{1,4})$/);
  if (withO) return "O" + withO[1].padStart(4, "0");
  const digitsOnly = s.replace(/\D/g, "").slice(0, 4);
  if (digitsOnly.length) return "O" + digitsOnly.padStart(4, "0");
  return "O0001";
}

function isValidOName(raw) {
  return /^O\d{4}$/.test(String(raw || "").trim().toUpperCase());
}

/** Pause after tool change: "" | M00 | M01 */
function pauseAfterTool(s) {
  const c = String(s && s.pauseCode != null ? s.pauseCode : "").trim().toUpperCase();
  if (c === "M00" || c === "M01") return c;
  return null;
}

/** TxxM06 + optional pause (без G28 — дом только в шапке/футере) */
function toolChangeBlock(s) {
  const lines = [`T${Number(s.tool) || 20}M06`];
  const pause = pauseAfterTool(s);
  if (pause) lines.push(pause);
  return lines;
}

/** Число в стиле Fanuc: 10 → 10. ; 173.5 → 173.5 ; 0 → 0. */
function F(v) {
  const n = Number(v);
  if (!Number.isFinite(n)) return "0.";
  if (Number.isInteger(n)) return `${n}.`;
  return String(n);
}

function F2(v) {
  const n = Number(v);
  if (!Number.isFinite(n)) return "0.00";
  return n.toFixed(2).replace(/\.?0+$/, (m) => (m.includes(".") ? m : "")) || "0";
}

/** Z0.00 как в шапке примера */
function FzHome(v) {
  const n = Number(v);
  if (!Number.isFinite(n)) return "0.00";
  return n.toFixed(2);
}

function todayStamp() {
  try {
    return new Date().toString();
  } catch {
    return "";
  }
}

/**
 * Назначение W для точки i (0-based).
 * Как в примере: сначала W1…W6 (G54…G59), дальше W-1, W-2… (G54.1).
 */
function wForPoint(index, useG54G59First) {
  if (useG54G59First && index < 6) {
    return { w: index + 1, kind: "std", p: index + 1 }; // W1=G54 … W6=G59
  }
  const p = useG54G59First ? index - 5 : index + 1; // after 6 std → P1
  return { w: -p, kind: "ext", p };
}

/** Блок копирования XY из G54 → G55…G59 и G54.1 P1…Pmax */
function buildXyCopyBlock(extCount, extBase, sourceWcs = 54) {
  const srcX = mainWcsAxisVar(sourceWcs, 1);
  const srcY = mainWcsAxisVar(sourceWcs, 2);
  const lines = [];
  // G55…G59 (W2…W6) — как в примере MetaWork
  for (let wcs = 55; wcs <= 59; wcs++) {
    const x = mainWcsAxisVar(wcs, 1);
    const y = mainWcsAxisVar(wcs, 2);
    lines.push(`#${x} = #${srcX} (G${wcs}X = G${sourceWcs}X)`);
    lines.push(`#${y} = #${srcY} (G${wcs}Y = G${sourceWcs}Y)`);
  }
  for (let p = 1; p <= extCount; p++) {
    const x = extWcsAxisVar(extBase, p, 1);
    const y = extWcsAxisVar(extBase, p, 2);
    lines.push(`#${x} = #${srcX} (P${p}X = G${sourceWcs}X)`);
    lines.push(`#${y} = #${srcY} (P${p}Y = G${sourceWcs}Y)`);
  }
  return lines;
}

/** Компактный подъезд: меняем только изменившиеся оси */
function moveToXY(prev, x, y) {
  const lx = F(x);
  const ly = F(y);
  if (!prev) return `G00 G90 X${lx} Y${ly}`;
  const sameX = Number(prev.x) === Number(x);
  const sameY = Number(prev.y) === Number(y);
  if (sameX && sameY) return null;
  if (sameY) return `X${lx}`;
  if (sameX) return `Y${ly}`;
  return `X${lx} Y${ly}`;
}

const DEFAULT_POINTS = RAW_DEFAULT_POINTS.map(([x, y]) => formatPointLine(x, y)).join("\n");

/** @type {FieldDef[]} */
const HEADER_FIELDS = [
  {
    key: "fileName",
    label: "Программа (O + 4 цифры)",
    type: "text",
    default: "O2224",
    section: "Программа",
    pattern: "^O\\d{4}$",
    maxlength: "5",
    placeholder: "O2224",
  },
  { key: "opName", label: "OPERATION NAME", type: "text", default: "MILL_CONTROL", section: "Программа", span2: true },
  { key: "partComment", label: "Комментарий детали", type: "text", default: "PRODUT6", section: "Программа", span2: true },
  { key: "tool", label: "Инструмент T", type: "number", default: 20, section: "Инструмент" },
  { key: "hOffset", label: "Вылет H", type: "number", default: 20, section: "Инструмент" },
  { key: "wcs", label: "WCS", type: "number", default: 54, section: "Инструмент" },
  {
    key: "pauseCode",
    label: "Пауза после TxxM06",
    type: "segment",
    default: "M00",
    section: "Инструмент",
    wide: true,
    options: [
      { value: "", label: "Off" },
      { value: "M00", label: "M00" },
      { value: "M01", label: "M01" },
    ],
  },
];

/** @type {FieldDef[]} */
const FOOTER_HOME_FIELDS = [
  { key: "homeZ", label: "Отвод Z", chip: "Z", type: "chip", default: true },
  { key: "homeY", label: "Отвод Y", chip: "Y", type: "chip", default: true },
  { key: "homeX", label: "Отвод X", chip: "X", type: "chip", default: false },
];

/** @type {FieldDef[]} */
const FOOTER_END_FIELDS = [
  { key: "endProgram", label: "Конец программы (M-код)", type: "checkbox", default: true, wide: true },
  {
    key: "endCode",
    label: "Код конца",
    type: "segment",
    default: "M30",
    wide: true,
    options: [
      { value: "M30", label: "M30" },
      { value: "M99", label: "M99" },
    ],
    showIf: (s) => Boolean(s.endProgram),
  },
];

/**
 * @type {{ id: string, name: string, description: string, fields: FieldDef[], generate: (s: Record<string, any>) => string[] }[]}
 */
const TEMPLATES = [
  {
    id: "z-points-vasyuki",
    name: "Точки Z",
    description: "",
    fields: [
      {
        key: "useBlankCalc",
        label: "Считать от заготовки",
        type: "checkbox",
        default: true,
      },
      {
        key: "blankShape",
        label: "Форма заготовки",
        type: "segment",
        default: "plate",
        wide: true,
        showIf: (s) => Boolean(s.useBlankCalc),
        options: [
          { value: "plate", label: "Плита" },
          { value: "cylinder", label: "Цилиндр" },
        ],
      },
      {
        key: "blankT",
        label: "Толщина, мм (Z)",
        type: "number",
        step: "0.001",
        default: DEFAULT_BLANK_T,
        showIf: (s) => Boolean(s.useBlankCalc) && !isCylinderBlank(s),
      },
      {
        key: "blankW",
        label: "Ширина, мм (X)",
        type: "number",
        step: "0.001",
        default: DEFAULT_BLANK_W,
        showIf: (s) => Boolean(s.useBlankCalc) && !isCylinderBlank(s),
      },
      {
        key: "blankH",
        label: "Высота, мм (Y)",
        type: "number",
        step: "0.001",
        default: DEFAULT_BLANK_H,
        showIf: (s) => Boolean(s.useBlankCalc) && !isCylinderBlank(s),
      },
      {
        key: "blankDia",
        label: "Диаметр, мм",
        type: "number",
        step: "0.001",
        default: DEFAULT_BLANK_DIA,
        showIf: (s) => Boolean(s.useBlankCalc) && isCylinderBlank(s),
      },
      {
        key: "blankLen",
        label: "Длина, мм (ось Z)",
        type: "number",
        step: "0.001",
        default: DEFAULT_BLANK_LEN,
        showIf: (s) => Boolean(s.useBlankCalc) && isCylinderBlank(s),
      },
      {
        key: "originMode",
        label: "Привязка (ноль)",
        type: "select",
        default: "center",
        wide: true,
        showIf: (s) => Boolean(s.useBlankCalc),
        options: [
          { value: "center", label: "Центр" },
          { value: "sw", label: "Угол / край X− Y−" },
          { value: "se", label: "Угол / край X+ Y−" },
          { value: "nw", label: "Угол / край X− Y+" },
          { value: "ne", label: "Угол / край X+ Y+" },
          { value: "px", label: "Край +X" },
          { value: "mx", label: "Край −X" },
          { value: "py", label: "Край +Y" },
          { value: "my", label: "Край −Y" },
        ],
      },
      {
        key: "syncContour",
        label: "Точки по контуру заготовки",
        type: "checkbox",
        default: true,
        showIf: (s) => Boolean(s.useBlankCalc),
      },
      {
        key: "points",
        label: "Точки (от центра заготовки: X1 Y0)",
        type: "textarea",
        rows: 10,
        default: DEFAULT_POINTS,
      },
      { key: "approachZ", label: "Z подхода", type: "number", step: "0.001", default: 10 },
      { key: "stepZ", label: "Шаг Z (A91)", type: "number", step: "0.001", default: -11 },
      {
        key: "useG54G59First",
        label: "Сначала W1…W6 (G54…G59), дальше W-1…",
        type: "checkbox",
        default: false,
      },
      {
        key: "copyXy",
        label: "Копировать привязки XY перед замером",
        type: "checkbox",
        default: true,
      },
      {
        key: "copySourceWcs",
        label: "Откуда копировать (G5x)",
        type: "number",
        default: 54,
        showIf: (s) => Boolean(s.copyXy),
      },
      {
        key: "copyStdG55G59",
        label: "Копировать в G55…G59",
        type: "checkbox",
        default: true,
        showIf: (s) => Boolean(s.copyXy),
      },
      {
        key: "minExtCopy",
        label: "G54.1 Pn копировать (= число точек)",
        type: "number",
        default: parsePoints(DEFAULT_POINTS).length,
        showIf: (s) => Boolean(s.copyXy),
      },
    ],
    generate(s) {
      let points = parsePoints(s.points);
      const approachZ = F(s.approachZ);
      const stepZ = F(s.stepZ);
      const extBase = 7001;
      const useStd = Boolean(s.useG54G59First);
      const lines = [];

      if (!points.length) {
        lines.push("(!!! нет точек — укажите X… Y… !!!)");
        return lines;
      }

      if (s.useBlankCalc) {
        const ext = blankExtents(s);
        const mode = s.originMode || "center";
        points = mapPointsToOrigin(points, ext.w, ext.h, mode);
        if (ext.shape === "cylinder") {
          lines.push(
            `(BLANK: CYL D${F(ext.dia)} L${F(ext.len)}  ORIGIN: ${originModeLabel(mode)})`
          );
        } else {
          lines.push(
            `(BLANK: PLATE T${F(ext.t)} W${F(ext.w)} H${F(ext.h)}  ORIGIN: ${originModeLabel(mode)})`
          );
        }
      }

      let maxP = 0;
      points.forEach((_, i) => {
        const { kind, p } = wForPoint(i, useStd);
        if (kind === "ext") maxP = Math.max(maxP, p);
      });
      const extCopy = Math.max(maxP, Math.floor(Number(s.minExtCopy) || 0));
      const srcWcs = Number(s.copySourceWcs) || 54;

      if (s.copyXy) {
        if (s.copyStdG55G59 !== false) {
          lines.push(...buildXyCopyBlock(extCopy, extBase, srcWcs));
        } else if (extCopy > 0) {
          // только Pn
          const srcX = mainWcsAxisVar(srcWcs, 1);
          const srcY = mainWcsAxisVar(srcWcs, 2);
          for (let p = 1; p <= extCopy; p++) {
            const x = extWcsAxisVar(extBase, p, 1);
            const y = extWcsAxisVar(extBase, p, 2);
            lines.push(`#${x} = #${srcX} (P${p}X = G${srcWcs}X)`);
            lines.push(`#${y} = #${srcY} (P${p}Y = G${srcWcs}Y)`);
          }
        }
      }

      lines.push("M09");
      lines.push(`(OPERATION NAME: ${String(s.opName || "MILL_CONTROL").replace(/[()]/g, "")})`);
      lines.push(...toolChangeBlock(s));
      lines.push(`(${String(s.partComment || "PART").replace(/[()]/g, "")})`);
      lines.push(`G${Number(s.wcs) || 54}`);

      let prev = null;
      points.forEach((pt, idx) => {
        const { w } = wForPoint(idx, useStd);
        const move = moveToXY(prev, pt.x, pt.y);
        if (idx === 0) {
          lines.push(move);
          lines.push(`G43H${Number(s.hOffset) || 20}`);
          lines.push(`G00 Z${approachZ}`);
        } else if (move) {
          lines.push(move);
        }
        lines.push(`G65 P9103 A91 W${w} Z${stepZ}`);
        lines.push(`G00 Z${approachZ}`);
        prev = pt;
      });

      return lines;
    },
  }
];

function generateHeader(h) {
  const oName = normalizeOName(h.fileName);
  return [
    "%",
    oName,
    `(DATE: ${todayStamp()})`,
    "",
    "G91 G28 Z0.00",
    "G91 G28 Y0.0",
    "G40 G17 G49 G80",
    "",
  ];
}

function generateFooter(f) {
  const lines = [];
  if (f.homeZ) lines.push("G91 G28 Z0.00");
  if (f.homeY) lines.push("G91 G28 Y0.0");
  if (f.homeX) lines.push("G91 G28 X0.0");
  if (f.endProgram) {
    const code = String(f.endCode || "M30").toUpperCase() === "M99" ? "M99" : "M30";
    lines.push(code);
  }
  lines.push("%");
  return lines;
}

/** Проставляет N0010, N0020… на все строки кроме % и пустых */
function withNNumbers(lines, start = 10, step = 10) {
  let n = start;
  return lines.map((line) => {
    if (line === "" || line === "%") return line;
    const labeled = `N${String(n).padStart(4, "0")} ${line}`;
    n += step;
    return labeled;
  });
}

function buildProgram(state) {
  const tpl = TEMPLATES.find((t) => t.id === state.templateId) || TEMPLATES[0];
  const merged = { ...state.header, ...state.template };
  const raw = [...generateHeader(state.header), ...tpl.generate(merged), ...generateFooter(state.footer)];
  // %, O#### и пустые строки — без N; остальное — с N
  const out = [];
  let n = 10;
  for (const line of raw) {
    if (line === "%") {
      out.push("%");
      continue;
    }
    if (line === "") {
      out.push("");
      continue;
    }
    if (/^O\d{4}$/i.test(line)) {
      out.push(line.toUpperCase());
      continue;
    }
    out.push(`N${String(n).padStart(4, "0")} ${line}`);
    n += 10;
  }
  return out.join("\n");
}

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

/** Подсветка Fanuc/NC для вывода программы */
function highlightNc(text) {
  const bags = [];
  const park = (html) => {
    bags.push(html);
    return `\uE000${bags.length - 1}\uE001`;
  };

  let s = escapeHtml(text);

  // комментарии ( … )
  s = s.replace(/\([^)]*\)/g, (m) => park(`<span class="hb-tok-cmt">${m}</span>`));

  // номера кадров
  s = s.replace(/\bN\d+\b/g, (m) => park(`<span class="hb-tok-n">${m}</span>`));

  // макропеременные #5221
  s = s.replace(/#\d+/g, (m) => park(`<span class="hb-tok-var">${m}</span>`));

  // ключевые слова макроса
  s = s.replace(/\b(IF|THEN|ABS|GT|LE|GE|EQ|NE|AND|OR)\b/g, (m) =>
    park(`<span class="hb-tok-kw">${m}</span>`)
  );

  // % начало/конец
  s = s.replace(/(^|\n)%(?=\n|$)/g, (_, a) => `${a}${park('<span class="hb-tok-pct">%</span>')}`);

  // номер программы O2224
  s = s.replace(/(^|\n)(O\d{4})(?=\n|$)/g, (_, a, o) => `${a}${park(`<span class="hb-tok-o">${o}</span>`)}`);

  // слова адреса: G65, M06, X-123., W-1, P9103, T20, H20, A91…
  s = s.replace(/([A-Za-z])([+-]?(?:\d+\.?\d*|\.\d+))/g, (m, letter, num) => {
    const L = letter.toUpperCase();
    let cls = "hb-tok-addr";
    if (L === "G") cls = "hb-tok-g";
    else if (L === "M") cls = "hb-tok-m";
    else if (L === "N") cls = "hb-tok-n";
    else if ("XYZW".includes(L)) cls = "hb-tok-axis";
    else if ("ADTPHFS".includes(L)) cls = "hb-tok-param";
    return park(`<span class="${cls}"><span class="hb-tok-letter">${letter}</span>${num}</span>`);
  });

  s = s.replace(/\uE000(\d+)\uE001/g, (_, i) => bags[Number(i)] || "");
  return s;
}

function renderProgram(codeEl, text) {
  if (!codeEl) return;
  codeEl.dataset.raw = text;
  codeEl.innerHTML = highlightNc(text);
}

function defaultState() {
  const header = Object.fromEntries(HEADER_FIELDS.map((f) => [f.key, f.default]));
  const footer = Object.fromEntries(
    [...FOOTER_HOME_FIELDS, ...FOOTER_END_FIELDS].map((f) => [f.key, f.default])
  );
  const templateId = TEMPLATES[0].id;
  const template = Object.fromEntries(TEMPLATES[0].fields.map((f) => [f.key, f.default]));
  return { header, footer, templateId, template };
}

function migrateFooter(saved) {
  const base = Object.fromEntries(
    [...FOOTER_HOME_FIELDS, ...FOOTER_END_FIELDS].map((f) => [f.key, f.default])
  );
  const src = saved && typeof saved === "object" ? saved : {};
  const footer = { ...base, ...src };
  // v4 → v5: endM30 → endProgram + endCode
  if (src.endM30 !== undefined && src.endProgram === undefined) {
    footer.endProgram = Boolean(src.endM30);
    footer.endCode = "M30";
  }
  if (src.homeZ === undefined && src.homeY !== undefined) {
    // старый футер всегда делал G28 Z
    footer.homeZ = true;
  }
  if (String(footer.endCode).toUpperCase() === "M99") footer.endCode = "M99";
  else footer.endCode = "M30";
  delete footer.endM30;
  return footer;
}

function loadState() {
  try {
    let raw = localStorage.getItem(STORAGE_KEY);
    let fromLegacy = false;
    if (!raw) {
      raw =
        localStorage.getItem("hexagon-probe-gen-v7") ||
        localStorage.getItem("hexagon-probe-gen-v6") ||
        localStorage.getItem("hexagon-probe-gen-v5") ||
        localStorage.getItem("hexagon-probe-gen-v4");
      fromLegacy = Boolean(raw);
    }
    if (!raw) return defaultState();
    const parsed = JSON.parse(raw);
    const base = defaultState();
    const header = { ...base.header, ...(parsed.header || {}) };
    delete header.userName;
    header.fileName = normalizeOName(header.fileName);
    const template = { ...base.template, ...(parsed.template || {}) };
    // blankX/Y → ширина/высота/толщина
    if (template.blankW == null && template.blankX != null) template.blankW = template.blankX;
    if (template.blankH == null && template.blankY != null) template.blankH = template.blankY;
    if (template.blankT == null) template.blankT = DEFAULT_BLANK_T;
    delete template.blankX;
    delete template.blankY;
    // старое: pauseBeforeProbe (bool) → pauseCode
    if (typeof template.pauseBeforeProbe === "boolean" && parsed.header?.pauseCode === undefined) {
      header.pauseCode = template.pauseBeforeProbe ? "M00" : "";
    }
    delete template.pauseBeforeProbe;
    const pc = String(header.pauseCode || "").toUpperCase();
    header.pauseCode = pc === "M01" ? "M01" : pc === "M00" ? "M00" : "";
    const footer = migrateFooter(parsed.footer);
    // перенос со старых ключей: дефолты переключателей
    if (fromLegacy) {
      template.useG54G59First = false;
      template.copyXy = true;
      template.useBlankCalc = true;
      template.blankW = template.blankW != null ? template.blankW : DEFAULT_BLANK_W;
      template.blankH = template.blankH != null ? template.blankH : DEFAULT_BLANK_H;
      template.blankT = template.blankT != null ? template.blankT : DEFAULT_BLANK_T;
      template.originMode = template.originMode || "center";
      template.syncContour = template.syncContour !== undefined ? template.syncContour : true;
      template.minExtCopy = parsePoints(template.points || "").length || base.template.minExtCopy;
      footer.endProgram = true;
      footer.endCode = "M30";
    }
    let templateId = parsed.templateId || base.templateId;
    // неизвестные / снятые шаблоны → «Точки Z»
    if (!TEMPLATES.some((t) => t.id === templateId)) {
      templateId = base.templateId;
    }
    return {
      header,
      footer,
      templateId,
      template,
    };
  } catch {
    return defaultState();
  }
}

function saveState(state) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
}

function el(tag, props = {}, children = []) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (k === "className") node.className = v;
    else if (k === "text") node.textContent = v;
    else if (k.startsWith("on") && typeof v === "function") node.addEventListener(k.slice(2).toLowerCase(), v);
    else if (v !== undefined && v !== null) node.setAttribute(k, String(v));
  }
  for (const child of children) {
    if (child == null) continue;
    node.append(typeof child === "string" ? document.createTextNode(child) : child);
  }
  return node;
}

function fieldClass(field) {
  const parts = ["hb-field"];
  const wideDefault =
    field.type === "textarea" || field.type === "checkbox" || field.type === "segment";
  const wide = field.wide === undefined ? wideDefault : Boolean(field.wide);
  if (wide) parts.push("wide");
  if (field.span2) parts.push("span2");
  return parts.join(" ");
}

function renderChip(field, value, onChange) {
  const input = el("input", { id: `hb-f-${field.key}`, type: "checkbox" });
  input.checked = Boolean(value);
  const chip = el("label", {
    className: "hb-chip" + (input.checked ? " is-on" : ""),
    for: `hb-f-${field.key}`,
    title: field.label,
  });
  chip.append(
    input,
    el("span", { className: "hb-chip-key", text: field.chip || "?" }),
    el("span", { text: "G28" })
  );
  input.addEventListener("change", () => {
    chip.classList.toggle("is-on", input.checked);
    onChange(input.checked);
  });
  return chip;
}

function renderSegment(field, value, onChange) {
  const wrap = el("div", { className: fieldClass(field) });
  wrap.append(el("span", { className: "hb-label", text: field.label }));
  const seg = el("div", { className: "hb-seg", role: "group", "aria-label": field.label });
  const cur = String(value ?? field.default ?? "");
  for (const opt of field.options || []) {
    const btn = el("button", {
      type: "button",
      className: "hb-seg-btn" + (String(opt.value) === cur ? " is-active" : ""),
      text: opt.label,
    });
    btn.addEventListener("click", () => {
      if (String(opt.value) === cur) return;
      onChange(opt.value);
    });
    seg.append(btn);
  }
  wrap.append(seg);
  return wrap;
}

function renderToggle(field, value, onChange) {
  const wrap = el("div", { className: fieldClass(field) });
  const input = el("input", { id: `hb-f-${field.key}`, type: "checkbox" });
  input.checked = Boolean(value);
  const lab = el("label", {
    className: "hb-toggle" + (input.checked ? " is-on" : ""),
    for: `hb-f-${field.key}`,
  });
  lab.append(
    input,
    el("span", { className: "hb-switch", "aria-hidden": "true" }),
    el("span", { className: "hb-toggle-text", text: field.label })
  );
  input.addEventListener("change", () => {
    lab.classList.toggle("is-on", input.checked);
    onChange(input.checked);
  });
  wrap.append(lab);
  return wrap;
}

function renderField(field, value, onChange) {
  if (field.type === "chip") return renderChip(field, value, onChange);
  if (field.type === "segment") return renderSegment(field, value, onChange);
  if (field.type === "checkbox") return renderToggle(field, value, onChange);

  const wrap = el("div", { className: fieldClass(field) });
  wrap.append(el("label", { text: field.label, for: `hb-f-${field.key}` }));

  if (field.type === "select") {
    const select = el("select", { id: `hb-f-${field.key}` });
    for (const opt of field.options || []) {
      const o = el("option", { value: opt.value, text: opt.label });
      if (String(value) === String(opt.value)) o.selected = true;
      select.append(o);
    }
    select.addEventListener("change", () => onChange(select.value));
    wrap.append(select);
    return wrap;
  }

  if (field.type === "textarea") {
    const ta = el("textarea", { id: `hb-f-${field.key}`, rows: String(field.rows || 4) });
    ta.value = value ?? "";
    ta.addEventListener("input", () => onChange(ta.value));
    wrap.append(ta);
    return wrap;
  }

  const input = el("input", {
    id: `hb-f-${field.key}`,
    type: field.type === "number" ? "number" : "text",
    value: value ?? "",
  });
  if (field.step) input.step = field.step;
  if (field.pattern) input.pattern = field.pattern;
  if (field.maxlength) input.maxLength = Number(field.maxlength) || 5;
  if (field.placeholder) input.placeholder = field.placeholder;
  if (field.readonly) {
    input.readOnly = true;
    input.classList.add("hb-readonly");
  } else if (field.key === "fileName") {
    input.spellcheck = false;
    input.autocomplete = "off";
    input.title = "Формат: O и 4 цифры, например O2224";
    input.addEventListener("input", () => {
      let v = String(input.value || "").toUpperCase().replace(/[^O0-9]/g, "");
      if (v && v[0] !== "O") v = "O" + v.replace(/O/g, "");
      if (v.length > 5) v = v.slice(0, 5);
      if (input.value !== v) input.value = v;
      onChange(v);
      input.classList.toggle("hb-invalid", v.length > 0 && !isValidOName(v));
    });
    input.addEventListener("blur", () => {
      const fixed = normalizeOName(input.value);
      input.value = fixed;
      input.classList.remove("hb-invalid");
      onChange(fixed);
    });
  } else {
    input.addEventListener("input", () => {
      onChange(field.type === "number" ? input.value : input.value);
    });
  }
  if (field.key === "fileName" && value && !isValidOName(value)) {
    input.classList.add("hb-invalid");
  }
  wrap.append(input);
  return wrap;
}

function appendFieldsWithSections(container, fields, values, onFieldChange) {
  let lastSection = null;
  for (const f of fields) {
    if (f.section && f.section !== lastSection) {
      container.append(el("div", { className: "hb-section-label", text: f.section }));
      lastSection = f.section;
    }
    container.append(
      renderField(f, values[f.key], (v) => onFieldChange(f, v))
    );
  }
}

function main() {
  const root = $(ROOT_ID);
  if (!root) return;

  let state = loadState();
  const ensureTemplateFields = () => {
    const tpl = TEMPLATES.find((t) => t.id === state.templateId) || TEMPLATES[0];
    const next = {};
    for (const f of tpl.fields) {
      next[f.key] = state.template[f.key] !== undefined ? state.template[f.key] : f.default;
    }
    state.template = next;
  };
  ensureTemplateFields();
  // старый дефолт 18 → число точек с данными
  if (state.templateId === "z-points-vasyuki") {
    const nPts = parsePoints(state.template.points).length;
    const cur = Number(state.template.minExtCopy);
    if (nPts > 0 && (!Number.isFinite(cur) || cur === 18)) {
      state.template.minExtCopy = nPts;
    }
  }

  const headerFieldsEl = $("hb-header-fields");
  const templateSelect = $("hb-template-select");
  const templateFieldsEl = $("hb-template-fields");
  const footerHomeEl = $("hb-footer-home");
  const footerFieldsEl = $("hb-footer-fields");
  const codeEl = $("hb-code");
  const lineCountEl = $("hb-line-count");
  const toast = $("hb-toast");
  const btnCopy = $("hb-btn-copy");
  const btnSave = $("hb-btn-save");
  const btnReset = $("hb-btn-reset");
  if (
    !headerFieldsEl ||
    !templateSelect ||
    !templateFieldsEl ||
    !footerHomeEl ||
    !footerFieldsEl ||
    !codeEl ||
    !btnCopy ||
    !btnSave ||
    !btnReset
  ) {
    return;
  }

  // нормализуем имя программы при старте
  state.header.fileName = normalizeOName(state.header.fileName);

  for (const t of TEMPLATES) {
    templateSelect.append(el("option", { value: t.id, text: t.name }));
  }
  templateSelect.value = state.templateId;

  function applyContourFromBlank() {
    if (!state.template.useBlankCalc || !state.template.syncContour) return false;
    const next = buildContourForState(state.template);
    if (next === state.template.points) return false;
    state.template.points = next;
    syncMinExtCopyToPoints();
    const ta = $("hb-f-points");
    if (ta && document.activeElement !== ta) ta.value = next;
    return true;
  }

  function updateLineCount(text) {
    if (!lineCountEl) return;
    const n = String(text || "")
      .split(/\r?\n/)
      .filter((l) => l.trim() !== "").length;
    lineCountEl.textContent = n ? `${n} строк` : "";
  }

  function updateViz() {
    if (!window.HexbindViz || typeof window.HexbindViz.update !== "function") return;
    const tpl = TEMPLATES.find((t) => t.id === state.templateId) || TEMPLATES[0];
    const footer = state.footer || {};
    const homeSnap = {
      headerHome: true,
      homeZ: footer.homeZ === undefined ? true : Boolean(footer.homeZ),
      homeY: footer.homeY === undefined ? true : Boolean(footer.homeY),
      homeX: Boolean(footer.homeX),
    };
    if (tpl.id !== "z-points-vasyuki") {
      window.HexbindViz.hide();
      return;
    }
    let pts = parsePoints(state.template.points);
    const useBlank = Boolean(state.template.useBlankCalc);
    const mode = state.template.originMode || "center";
    let ext = useBlank
      ? blankExtents(state.template)
      : { shape: "plate", w: DEFAULT_BLANK_W, h: DEFAULT_BLANK_H, t: DEFAULT_BLANK_T };
    if (!useBlank && pts.length) {
      let minX = Infinity;
      let maxX = -Infinity;
      let minY = Infinity;
      let maxY = -Infinity;
      pts.forEach((p) => {
        minX = Math.min(minX, p.x);
        maxX = Math.max(maxX, p.x);
        minY = Math.min(minY, p.y);
        maxY = Math.max(maxY, p.y);
      });
      ext = {
        shape: "plate",
        w: Math.max(40, (maxX - minX) * 1.08 || DEFAULT_BLANK_W),
        h: Math.max(40, (maxY - minY) * 1.08 || DEFAULT_BLANK_H),
        t: DEFAULT_BLANK_T,
      };
    }
    const origin = useBlank
      ? originInCenterFrame(ext.w, ext.h, mode)
      : { ox: 0, oy: 0 };
    const wcsPts = useBlank ? mapPointsToOrigin(pts, ext.w, ext.h, mode) : pts;
    const approachZ = Number(state.template.approachZ);
    const stepZ = Number(state.template.stepZ);
    const blankZ = Math.max(8, ext.t || DEFAULT_BLANK_T);
    const badge = $("hb-viz-badge");
    if (badge) {
      badge.textContent =
        (ext.shape === "cylinder" ? "Ø" : "плита · ") +
        (wcsPts.length ? `${wcsPts.length} точ.` : "нет точек");
    }
    window.HexbindViz.update({
      mode: "points",
      shape: ext.shape,
      blankX: ext.w,
      blankY: ext.h,
      blankZ,
      diameter: ext.dia || ext.w,
      originX: origin.ox,
      originY: origin.oy,
      approachZ: Number.isFinite(approachZ) ? approachZ : 10,
      stepZ: Number.isFinite(stepZ) ? stepZ : -11,
      points: wcsPts,
      ...homeSnap,
    });
  }

  function refresh(opts) {
    opts = opts || {};
    ensureTemplateFields();
    saveState(state);
    const prog = buildProgram(state);
    renderProgram(codeEl, prog);
    updateLineCount(prog);
    updateViz();
    if (opts.repaintTemplate) paintTemplate();
  }

  function paintHeader() {
    headerFieldsEl.replaceChildren();
    appendFieldsWithSections(headerFieldsEl, HEADER_FIELDS, state.header, (f, v) => {
      if (f.readonly) return;
      if (f.key === "fileName") {
        state.header.fileName = String(v || "");
        refresh();
        return;
      }
      state.header[f.key] = f.type === "number" ? (v === "" ? f.default : Number(v)) : v;
      refresh();
      if (f.type === "segment") paintHeader();
    });
  }

  function downloadProgram() {
    state.header.fileName = normalizeOName(state.header.fileName);
    const name = state.header.fileName;
    const text = buildProgram(state);
    renderProgram(codeEl, text);
    updateLineCount(text);
    saveState(state);
    try {
      const blob = new Blob([text.replace(/\n/g, "\r\n")], { type: "application/octet-stream" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = name; // без расширения — «без формата»
      a.rel = "noopener";
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      showToast("Сохранено: " + name);
    } catch {
      showToast("Не удалось сохранить");
    }
  }

  function paintFooter() {
    footerHomeEl.replaceChildren();
    for (const f of FOOTER_HOME_FIELDS) {
      footerHomeEl.append(
        renderField(f, state.footer[f.key], (v) => {
          state.footer[f.key] = v;
          refresh();
        })
      );
    }
    footerFieldsEl.replaceChildren();
    for (const f of FOOTER_END_FIELDS) {
      if (typeof f.showIf === "function" && !f.showIf(state.footer)) continue;
      footerFieldsEl.append(
        renderField(f, state.footer[f.key], (v) => {
          state.footer[f.key] = v;
          const repaint = f.key === "endProgram" || f.type === "segment";
          refresh();
          if (repaint) paintFooter();
        })
      );
    }
  }

  function syncMinExtCopyToPoints() {
    const n = parsePoints(state.template.points).length;
    state.template.minExtCopy = n;
    const inp = $("hb-f-minExtCopy");
    if (inp && document.activeElement !== inp) inp.value = String(n);
    return n;
  }

  function paintTemplate() {
    const tpl = TEMPLATES.find((t) => t.id === state.templateId) || TEMPLATES[0];
    const merged = { ...state.header, ...state.template };
    templateFieldsEl.replaceChildren();

    const onField = (f, v) => {
      const prev = state.template[f.key];

      if (f.key === "points") {
        state.template.points = v;
        const wasSync = Boolean(state.template.syncContour);
        if (wasSync) state.template.syncContour = false;
        syncMinExtCopyToPoints();
        refresh({ repaintTemplate: wasSync });
        return;
      }

      if (f.key === "minExtCopy") {
        state.template.minExtCopy = v === "" ? 0 : Number(v);
        refresh();
        return;
      }

      if (f.key === "copyXy") {
        state.template.copyXy = Boolean(v);
        if (state.template.copyXy) syncMinExtCopyToPoints();
        refresh({ repaintTemplate: prev !== state.template.copyXy });
        return;
      }

      if (
        f.key === "useBlankCalc" ||
        f.key === "blankShape" ||
        f.key === "blankW" ||
        f.key === "blankH" ||
        f.key === "blankT" ||
        f.key === "blankDia" ||
        f.key === "blankLen" ||
        f.key === "syncContour" ||
        f.key === "originMode"
      ) {
        state.template[f.key] =
          f.type === "number" ? (v === "" ? f.default : Number(v)) : v;
        if (
          state.template.useBlankCalc &&
          state.template.syncContour &&
          (f.key === "syncContour" ||
            f.key === "blankW" ||
            f.key === "blankH" ||
            f.key === "blankDia" ||
            f.key === "blankShape" ||
            f.key === "useBlankCalc")
        ) {
          applyContourFromBlank();
        }
        const needRepaint =
          f.type === "checkbox" ||
          f.type === "segment" ||
          f.key === "useBlankCalc" ||
          f.key === "blankShape" ||
          f.key === "originMode";
        refresh({ repaintTemplate: needRepaint });
        if (
          f.key === "blankW" ||
          f.key === "blankH" ||
          f.key === "blankDia" ||
          f.key === "blankShape"
        ) {
          const ta = $("hb-f-points");
          if (ta) ta.value = state.template.points || "";
        }
        return;
      }

      state.template[f.key] = f.type === "number" ? (v === "" ? f.default : Number(v)) : v;
      const needRepaint =
        f.type === "checkbox" ||
        f.type === "segment" ||
        typeof f.showIf === "function";
      refresh({
        repaintTemplate: needRepaint && prev !== state.template[f.key],
      });
    };

    for (const f of tpl.fields) {
      if (typeof f.showIf === "function" && !f.showIf(merged)) continue;
      templateFieldsEl.append(renderField(f, state.template[f.key], (v) => onField(f, v)));
    }
  }

  templateSelect.addEventListener("change", () => {
    state.templateId = templateSelect.value;
    const tpl = TEMPLATES.find((t) => t.id === state.templateId) || TEMPLATES[0];
    state.template = Object.fromEntries(tpl.fields.map((f) => [f.key, f.default]));
    if (tpl.id === "z-points-vasyuki") syncMinExtCopyToPoints();
    paintTemplate();
    refresh();
  });

  btnCopy.addEventListener("click", async () => {
    const text = codeEl.dataset.raw || codeEl.textContent || "";
    try {
      await navigator.clipboard.writeText(text);
      showToast("Скопировано");
    } catch {
      const range = document.createRange();
      range.selectNodeContents(codeEl);
      const sel = window.getSelection();
      sel.removeAllRanges();
      sel.addRange(range);
      showToast("Выделите и скопируйте");
    }
  });

  btnSave.addEventListener("click", () => {
    downloadProgram();
  });

  btnReset.addEventListener("click", () => {
    state = defaultState();
    templateSelect.value = state.templateId;
    paintHeader();
    paintFooter();
    paintTemplate();
    refresh();
    showToast("Сброшено");
  });

  function showToast(msg) {
    if (!toast) return;
    toast.textContent = msg;
    toast.classList.add("show");
    clearTimeout(showToast._t);
    showToast._t = setTimeout(() => toast.classList.remove("show"), 1600);
  }

  window.addEventListener("hb-viz-refresh", () => {
    updateViz();
  });

  paintHeader();
  paintFooter();
  paintTemplate();
  refresh();
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", main);
} else {
  main();
}
})();
