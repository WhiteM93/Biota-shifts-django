/**
 * 3D-отрисовка траектории G-кода (Three.js + OrbitControls).
 * API: window.BiotaGcodeToolpathView.render / dispose / setVisible / resize
 * Клик по точке пути — координаты X/Y/Z (и номер строки).
 */
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { parseGcodeToolpath } from "./gcode_toolpath.js";

const RAPID_COLOR = 0x64748b;
const FEED_COLOR = 0x38bdf8;
const GRID_COLOR = 0x334155;
const PICK_COLOR = 0xfbbf24;
const PICK_PX = 16;
const CLICK_SLOP_PX = 6;

let state = null;

function themeIsDawn() {
  try {
    return document.documentElement.getAttribute("data-theme") === "dawn";
  } catch (_e) {
    return false;
  }
}

function disposeObject3d(obj) {
  if (!obj) return;
  obj.traverse(function (child) {
    if (child.geometry) child.geometry.dispose();
    if (child.material) {
      if (Array.isArray(child.material)) {
        child.material.forEach(function (m) {
          if (m && m.dispose) m.dispose();
        });
      } else if (child.material.dispose) {
        child.material.dispose();
      }
    }
  });
}

function makeLineSegments(coords, color) {
  if (!coords || coords.length < 6) return null;
  const geom = new THREE.BufferGeometry();
  geom.setAttribute("position", new THREE.BufferAttribute(coords, 3));
  const mat = new THREE.LineBasicMaterial({
    color: color,
    transparent: true,
    opacity: color === RAPID_COLOR ? 0.55 : 0.95,
  });
  return new THREE.LineSegments(geom, mat);
}

function fitCamera(camera, controls, bbox) {
  if (!bbox) return;
  const min = new THREE.Vector3(bbox.min[0], bbox.min[1], bbox.min[2]);
  const max = new THREE.Vector3(bbox.max[0], bbox.max[1], bbox.max[2]);
  const box = new THREE.Box3(min, max);
  const center = box.getCenter(new THREE.Vector3());
  const size = box.getSize(new THREE.Vector3());
  const maxDim = Math.max(size.x, size.y, size.z, 1);
  const dist = maxDim * 1.8;
  camera.near = Math.max(maxDim / 1000, 0.01);
  camera.far = Math.max(maxDim * 100, 1000);
  camera.position.set(center.x + dist * 0.7, center.y - dist * 0.85, center.z + dist * 0.65);
  camera.up.set(0, 0, 1);
  camera.lookAt(center);
  camera.updateProjectionMatrix();
  controls.target.copy(center);
  controls.minDistance = maxDim * 0.05;
  controls.maxDistance = maxDim * 40;
  controls.update();
}

function fmtCoord(n) {
  if (!Number.isFinite(n)) return "—";
  return (Math.round(n * 1000) / 1000).toString();
}

function collectPickPoints(parsed) {
  const map = new Map();
  function add(coords, lineNos, kind) {
    if (!coords) return;
    const nSeg = Math.floor(coords.length / 6);
    for (let i = 0; i < nSeg; i++) {
      const o = i * 6;
      const lineNo = lineNos && lineNos[i] ? lineNos[i] : 0;
      // оба конца сегмента; приоритет у feed при совпадении ключа
      for (let end = 0; end < 2; end++) {
        const x = coords[o + end * 3];
        const y = coords[o + end * 3 + 1];
        const z = coords[o + end * 3 + 2];
        const key = x.toFixed(4) + "|" + y.toFixed(4) + "|" + z.toFixed(4);
        const prev = map.get(key);
        if (!prev || (prev.kind === "rapid" && kind === "feed")) {
          map.set(key, { x, y, z, lineNo, kind });
        } else if (prev && !prev.lineNo && lineNo) {
          prev.lineNo = lineNo;
        }
      }
    }
  }
  add(parsed.rapid, parsed.rapidLineNos, "rapid");
  add(parsed.feed, parsed.feedLineNos, "feed");
  return Array.from(map.values());
}

function clearPickUi() {
  if (!state) return;
  if (state.pickMarker) {
    state.scene.remove(state.pickMarker);
    disposeObject3d(state.pickMarker);
    state.pickMarker = null;
  }
  if (state.pickEl) {
    state.pickEl.hidden = true;
    state.pickEl.textContent = "";
  }
}

function showPick(pt) {
  if (!state || !pt) return;
  clearPickUi();
  const span = state.pickSpan || 10;
  const r = Math.max(span * 0.012, 0.15);
  const geom = new THREE.SphereGeometry(r, 16, 12);
  const mat = new THREE.MeshBasicMaterial({
    color: PICK_COLOR,
    depthTest: false,
    transparent: true,
    opacity: 0.95,
  });
  const mesh = new THREE.Mesh(geom, mat);
  mesh.position.set(pt.x, pt.y, pt.z);
  mesh.renderOrder = 10;
  state.pickMarker = mesh;
  state.scene.add(mesh);

  const kindLabel = pt.kind === "rapid" ? "быстрый" : "рабочий";
  let text = "X" + fmtCoord(pt.x) + "  Y" + fmtCoord(pt.y) + "  Z" + fmtCoord(pt.z) + "  ·  " + kindLabel;
  if (pt.lineNo) text += "  ·  стр. " + pt.lineNo;
  if (state.pickEl) {
    state.pickEl.hidden = false;
    state.pickEl.textContent = text;
  }
}

function canvasPointerPos(ev) {
  const rect = state.renderer.domElement.getBoundingClientRect();
  return {
    x: ev.clientX - rect.left,
    y: ev.clientY - rect.top,
    w: Math.max(1, rect.width),
    h: Math.max(1, rect.height),
  };
}

function findNearestPick(clientX, clientY) {
  if (!state || !state.pickPoints || !state.pickPoints.length) return null;
  const rect = state.renderer.domElement.getBoundingClientRect();
  const sx = clientX - rect.left;
  const sy = clientY - rect.top;
  const w = Math.max(1, rect.width);
  const h = Math.max(1, rect.height);
  const v = new THREE.Vector3();
  let best = null;
  let bestD2 = PICK_PX * PICK_PX;
  for (let i = 0; i < state.pickPoints.length; i++) {
    const p = state.pickPoints[i];
    v.set(p.x, p.y, p.z).project(state.camera);
    if (v.z < -1 || v.z > 1) continue;
    const px = (v.x * 0.5 + 0.5) * w;
    const py = (-v.y * 0.5 + 0.5) * h;
    const dx = px - sx;
    const dy = py - sy;
    const d2 = dx * dx + dy * dy;
    if (d2 < bestD2) {
      bestD2 = d2;
      best = p;
    }
  }
  return best;
}

function onPointerDown(ev) {
  if (!state || ev.button !== 0) return;
  const p = canvasPointerPos(ev);
  state.ptrDown = { x: p.x, y: p.y, id: ev.pointerId };
}

function onPointerUp(ev) {
  if (!state || !state.ptrDown || ev.button !== 0) return;
  const down = state.ptrDown;
  state.ptrDown = null;
  const p = canvasPointerPos(ev);
  const dx = p.x - down.x;
  const dy = p.y - down.y;
  if (dx * dx + dy * dy > CLICK_SLOP_PX * CLICK_SLOP_PX) return;
  const hit = findNearestPick(ev.clientX, ev.clientY);
  if (hit) showPick(hit);
  else clearPickUi();
}

function bindPickEvents() {
  if (!state || !state.renderer || state.pickBound) return;
  const el = state.renderer.domElement;
  el.addEventListener("pointerdown", onPointerDown);
  el.addEventListener("pointerup", onPointerUp);
  el.style.cursor = "crosshair";
  state.pickBound = true;
}

function unbindPickEvents() {
  if (!state || !state.renderer || !state.pickBound) return;
  const el = state.renderer.domElement;
  el.removeEventListener("pointerdown", onPointerDown);
  el.removeEventListener("pointerup", onPointerUp);
  state.pickBound = false;
}

function stopLoop() {
  if (!state) return;
  if (state.raf) {
    cancelAnimationFrame(state.raf);
    state.raf = 0;
  }
  if (state.ro) {
    try {
      state.ro.disconnect();
    } catch (_e) {}
    state.ro = null;
  }
}

function dispose() {
  stopLoop();
  if (!state) return;
  unbindPickEvents();
  clearPickUi();
  if (state.controls) state.controls.dispose();
  if (state.pathRoot) {
    state.scene.remove(state.pathRoot);
    disposeObject3d(state.pathRoot);
  }
  if (state.helpers) {
    state.scene.remove(state.helpers);
    disposeObject3d(state.helpers);
  }
  if (state.renderer) {
    state.renderer.dispose();
    if (state.renderer.domElement && state.renderer.domElement.parentNode) {
      state.renderer.domElement.parentNode.removeChild(state.renderer.domElement);
    }
  }
  state = null;
}

function resize() {
  if (!state || !state.host) return;
  const w = Math.max(1, state.host.clientWidth);
  const h = Math.max(1, state.host.clientHeight);
  state.camera.aspect = w / h;
  state.camera.updateProjectionMatrix();
  state.renderer.setSize(w, h, false);
}

function animate() {
  if (!state) return;
  state.raf = requestAnimationFrame(animate);
  state.controls.update();
  state.renderer.render(state.scene, state.camera);
}

function ensureScene(host) {
  if (state && state.host === host) return state;
  dispose();
  const dawn = themeIsDawn();
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(dawn ? 0xf7f2ea : 0x0f172a);
  const w = Math.max(1, host.clientWidth);
  const h = Math.max(1, host.clientHeight);
  const camera = new THREE.PerspectiveCamera(42, w / h, 0.1, 1e6);
  camera.up.set(0, 0, 1);
  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.setSize(w, h, false);
  host.appendChild(renderer.domElement);
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.dampingFactor = 0.08;
  controls.screenSpacePanning = true;
  state = {
    host,
    scene,
    camera,
    renderer,
    controls,
    pathRoot: null,
    helpers: null,
    pickMarker: null,
    pickPoints: [],
    pickSpan: 10,
    pickEl: null,
    ptrDown: null,
    pickBound: false,
    raf: 0,
    ro: null,
  };
  const ro = new ResizeObserver(function () {
    resize();
  });
  ro.observe(host);
  state.ro = ro;
  bindPickEvents();
  animate();
  return state;
}

function buildHelpers(bbox) {
  const group = new THREE.Group();
  let span = 100;
  if (bbox) {
    span = Math.max(
      bbox.max[0] - bbox.min[0],
      bbox.max[1] - bbox.min[1],
      bbox.max[2] - bbox.min[2],
      10
    );
  }
  const gridSize = span * 1.4;
  const divisions = 10;
  const grid = new THREE.GridHelper(gridSize, divisions, GRID_COLOR, GRID_COLOR);
  grid.rotation.x = Math.PI / 2;
  grid.material.transparent = true;
  grid.material.opacity = 0.35;
  if (bbox) {
    const cx = (bbox.min[0] + bbox.max[0]) / 2;
    const cy = (bbox.min[1] + bbox.max[1]) / 2;
    const cz = bbox.min[2];
    grid.position.set(cx, cy, cz);
  }
  group.add(grid);
  const axes = new THREE.AxesHelper(span * 0.25);
  if (bbox) {
    axes.position.set(bbox.min[0], bbox.min[1], bbox.min[2]);
  }
  group.add(axes);
  return group;
}

/**
 * @param {HTMLElement} host canvas container
 * @param {string} gcodeText
 * @param {{emptyEl?: HTMLElement, noteEl?: HTMLElement, pickEl?: HTMLElement}|undefined} ui
 */
function render(host, gcodeText, ui) {
  const emptyEl = ui && ui.emptyEl;
  const noteEl = ui && ui.noteEl;
  const pickEl = ui && ui.pickEl;
  if (!host) return null;
  const parsed = parseGcodeToolpath(gcodeText || "");
  const st = ensureScene(host);
  st.pickEl = pickEl || null;
  clearPickUi();

  if (st.pathRoot) {
    st.scene.remove(st.pathRoot);
    disposeObject3d(st.pathRoot);
    st.pathRoot = null;
  }
  if (st.helpers) {
    st.scene.remove(st.helpers);
    disposeObject3d(st.helpers);
    st.helpers = null;
  }
  st.pickPoints = [];

  if (!parsed.pointCount) {
    if (emptyEl) {
      emptyEl.hidden = false;
      emptyEl.textContent = "Нет перемещений для отрисовки.";
    }
    if (noteEl) {
      noteEl.hidden = true;
      noteEl.textContent = "";
    }
    return parsed;
  }

  if (emptyEl) emptyEl.hidden = true;
  if (noteEl) {
    if (parsed.truncated) {
      noteEl.hidden = false;
      noteEl.textContent = "Траектория упрощена (слишком много точек). Клик по точке — координаты.";
    } else {
      noteEl.hidden = false;
      noteEl.textContent = "Клик по точке траектории — координаты.";
    }
  }

  const root = new THREE.Group();
  const rapid = makeLineSegments(parsed.rapid, RAPID_COLOR);
  const feed = makeLineSegments(parsed.feed, FEED_COLOR);
  if (rapid) root.add(rapid);
  if (feed) root.add(feed);
  st.pathRoot = root;
  st.scene.add(root);

  st.helpers = buildHelpers(parsed.bbox);
  st.scene.add(st.helpers);
  st.pickPoints = collectPickPoints(parsed);
  if (parsed.bbox) {
    st.pickSpan = Math.max(
      parsed.bbox.max[0] - parsed.bbox.min[0],
      parsed.bbox.max[1] - parsed.bbox.min[1],
      parsed.bbox.max[2] - parsed.bbox.min[2],
      10
    );
  }
  fitCamera(st.camera, st.controls, parsed.bbox);
  resize();
  return parsed;
}

function setVisible(visible) {
  if (!state || !state.renderer) return;
  state.renderer.domElement.style.visibility = visible ? "visible" : "hidden";
  if (visible) resize();
}

const api = { render, dispose, setVisible, resize };
window.BiotaGcodeToolpathView = api;
export default api;
