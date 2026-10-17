/**
 * 3D-отрисовка траектории G-кода (Three.js + OrbitControls).
 * API: window.BiotaGcodeToolpathView.render / dispose / setVisible / resize
 */
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { parseGcodeToolpath } from "./gcode_toolpath.js";

const RAPID_COLOR = 0x64748b;
const FEED_COLOR = 0x38bdf8;
const GRID_COLOR = 0x334155;

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
    raf: 0,
    ro: null,
  };
  const ro = new ResizeObserver(function () {
    resize();
  });
  ro.observe(host);
  state.ro = ro;
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
 * @param {{emptyEl?: HTMLElement, noteEl?: HTMLElement}|undefined} ui
 */
function render(host, gcodeText, ui) {
  const emptyEl = ui && ui.emptyEl;
  const noteEl = ui && ui.noteEl;
  if (!host) return null;
  const parsed = parseGcodeToolpath(gcodeText || "");
  const st = ensureScene(host);

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
      noteEl.textContent = "Траектория упрощена (слишком много точек).";
    } else {
      noteEl.hidden = true;
      noteEl.textContent = "";
    }
  }

  const root = new THREE.Group();
  // CNC: X right, Y depth, Z up — Three already Z-up via camera.up
  const rapid = makeLineSegments(parsed.rapid, RAPID_COLOR);
  const feed = makeLineSegments(parsed.feed, FEED_COLOR);
  if (rapid) root.add(rapid);
  if (feed) root.add(feed);
  st.pathRoot = root;
  st.scene.add(root);

  st.helpers = buildHelpers(parsed.bbox);
  st.scene.add(st.helpers);
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
