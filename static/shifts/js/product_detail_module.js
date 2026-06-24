/* product_detail_module.js — extracted from product_detail.html ES module block, uses data island #pd-options */
import * as THREE from "three";
import { TrackballControls } from "three/addons/controls/TrackballControls.js";
import { STLLoader } from "three/addons/loaders/STLLoader.js";

const PD = (function () {
  try {
    const el = document.getElementById("pd-options");
    return el ? JSON.parse(el.textContent) : {};
  } catch (e) { return {}; }
})();


  const host = document.getElementById("product-cad-viewport");
  const tabsRoot = document.getElementById("product-tabs");
  const saveBtn = document.getElementById("save-list-preview-btn");
  const saveMsg = document.getElementById("save-list-preview-msg");
  const setupStlBtn = document.getElementById("cad-setup-stl-btn");
  const setupStlInput = document.getElementById("cad-setup-stl-input");
  let stlUrl = host && host.dataset.stlUrl ? new URL(host.dataset.stlUrl, window.location.origin).href : "";
  const savePreviewUrl = PD.save_list_preview_url;
  let inlineEditEnabled = false;
  let cadRenderer = null;
  let cadViewerStarted = false;
  let cadViewerState = null;
  let cadLoadToken = 0;

  function clearCadLoading() {
    if (!host) return;
    host.querySelectorAll(".product-cad-loading").forEach((el) => el.remove());
  }

  function showCadError(text) {
    clearCadLoading();
    if (!host) return;
    host.querySelectorAll("p.muted").forEach((el) => el.remove());
    const p = document.createElement("p");
    p.className = "muted";
    p.style.padding = "12px";
    p.textContent = text;
    host.appendChild(p);
  }

  function disposeCadViewer() {
    if (!cadViewerState) return;
    try {
      if (cadViewerState.rafId) cancelAnimationFrame(cadViewerState.rafId);
    } catch (e) {}
    try {
      if (cadViewerState.onResize) window.removeEventListener("resize", cadViewerState.onResize);
    } catch (e) {}
    try {
      if (cadViewerState.controls) cadViewerState.controls.dispose();
    } catch (e) {}
    try {
      if (cadViewerState.root) {
        cadViewerState.root.traverse((obj) => {
          if (obj && obj.geometry && typeof obj.geometry.dispose === "function") obj.geometry.dispose();
          if (obj && obj.material) {
            if (Array.isArray(obj.material)) {
              obj.material.forEach((m) => m && m.dispose && m.dispose());
            } else if (typeof obj.material.dispose === "function") {
              obj.material.dispose();
            }
          }
        });
      }
    } catch (e) {}
    try {
      if (cadViewerState.renderer) cadViewerState.renderer.dispose();
    } catch (e) {}
    cadViewerState = null;
  }

  let _layoutTries = 0;
  function waitLayout(cb) {
    if (!host) return;
    if (host.clientWidth >= 32) {
      cb();
      return;
    }
    _layoutTries += 1;
    if (_layoutTries < 90) {
      requestAnimationFrame(() => waitLayout(cb));
    } else {
      showCadError("Недостаточно места для предпросмотра. Скачайте файл ниже.");
    }
  }

  function fitCameraToObject(camera, controls, root, margin) {
    const pad = margin == null ? 1.32 : margin;
    const box = new THREE.Box3().setFromObject(root);
    if (box.isEmpty()) return;
    const center = box.getCenter(new THREE.Vector3());
    const sphere = box.getBoundingSphere(new THREE.Sphere());
    const radius = Math.max(sphere.radius, 1e-6);

    const vFov = (camera.fov * Math.PI) / 180;
    const aspect = Math.max(camera.aspect, 1e-6);
    const hFov = 2 * Math.atan(Math.tan(vFov / 2) * aspect);
    const distV = radius / Math.sin(vFov / 2);
    const distH = radius / Math.sin(hFov / 2);
    const distance = pad * Math.max(distV, distH);

    const dir = new THREE.Vector3(0.62, 0.42, 0.72).normalize();
    camera.position.copy(center).add(dir.multiplyScalar(distance));
    camera.near = Math.max(distance / 300, 0.001);
    camera.far = Math.max(distance * 300, 1000);
    camera.updateProjectionMatrix();

    if (controls.target) controls.target.copy(center);
    camera.lookAt(center);
    controls.update();
    if (controls.target0) controls.target0.copy(controls.target);
    if (controls.position0) controls.position0.copy(camera.position);
    if (controls.up0) controls.up0.copy(camera.up);
  }

  const cadPixelRatioCap = 2;

  /** Только canvas: блокируем прокрутку страницы колесом (без своего pointer capture). */
  function bindCadWheelGuard(canvas) {
    if (!canvas || canvas.dataset.cadWheelGuard === "1") return;
    canvas.dataset.cadWheelGuard = "1";
    canvas.addEventListener(
      "wheel",
      function (e) {
        e.preventDefault();
      },
      { passive: false }
    );
    canvas.addEventListener("contextmenu", function (e) {
      e.preventDefault();
    });
  }

  /** Trackball: свободный обзор и инерция; без своего pointer capture (только Orbit/Trackball на canvas). */
  function createCadControls(camera, domElement) {
    const controls = new TrackballControls(camera, domElement);
    controls.rotateSpeed = 3.2;
    controls.zoomSpeed = 1.2;
    controls.panSpeed = 0.75;
    controls.staticMoving = false;
    controls.dynamicDampingFactor = 0.2;
    bindCadWheelGuard(domElement);
    return controls;
  }

  function bindCadViewReset(hostEl, controls, getRoot) {
    if (!hostEl || hostEl.dataset.cadDblclickBound === "1") return;
    hostEl.dataset.cadDblclickBound = "1";
    hostEl.addEventListener("dblclick", function () {
      const root = typeof getRoot === "function" ? getRoot() : null;
      if (root && controls) {
        fitCameraToObject(controls.object, controls, root);
      } else if (typeof controls.reset === "function") {
        controls.reset();
        controls.update();
      }
    });
  }

  function triggerCadResize(refit) {
    if (cadViewerState && typeof cadViewerState.onResize === "function") {
      requestAnimationFrame(function () {
        if (cadViewerState && cadViewerState.onResize) cadViewerState.onResize(refit);
      });
    }
  }

  function getCadFullscreenElement() {
    return document.fullscreenElement || document.webkitFullscreenElement || null;
  }

  function bindCadFullscreen() {
    const btn = document.getElementById("product-cad-fullscreen-btn");
    const block = document.getElementById("product-cad-block");
    if (!btn || !block || !host) return;

    function isCadFullscreen() {
      return getCadFullscreenElement() === block || block.classList.contains("is-cad-fullscreen-fallback");
    }

    function setFullscreenUi(active) {
      btn.classList.toggle("is-active", active);
      btn.title = active ? "Выйти из полноэкранного режима (Esc)" : "На весь экран";
      btn.setAttribute("aria-label", btn.title);
      btn.setAttribute("aria-pressed", active ? "true" : "false");
    }

    function exitCadFullscreen() {
      if (getCadFullscreenElement() === block) {
        const exitFn = document.exitFullscreen || document.webkitExitFullscreen;
        if (exitFn) exitFn.call(document);
      }
      block.classList.remove("is-cad-fullscreen-fallback");
      document.body.classList.remove("product-cad-fullscreen-active");
      setFullscreenUi(false);
      triggerCadResize(true);
    }

    function enterCadFullscreen() {
      const req = block.requestFullscreen || block.webkitRequestFullscreen;
      if (req) {
        return Promise.resolve(req.call(block)).catch(function () {
          block.classList.add("is-cad-fullscreen-fallback");
          document.body.classList.add("product-cad-fullscreen-active");
          setFullscreenUi(true);
          triggerCadResize(true);
        });
      }
      block.classList.add("is-cad-fullscreen-fallback");
      document.body.classList.add("product-cad-fullscreen-active");
      setFullscreenUi(true);
      triggerCadResize(true);
      return Promise.resolve();
    }

    btn.addEventListener("click", function () {
      if (isCadFullscreen()) exitCadFullscreen();
      else enterCadFullscreen();
    });

    document.addEventListener("fullscreenchange", function () {
      const active = getCadFullscreenElement() === block;
      if (!active && block.classList.contains("is-cad-fullscreen-fallback")) return;
      if (!active) {
        block.classList.remove("is-cad-fullscreen-fallback");
        document.body.classList.remove("product-cad-fullscreen-active");
      }
      setFullscreenUi(active || block.classList.contains("is-cad-fullscreen-fallback"));
      triggerCadResize(true);
    });
    document.addEventListener("webkitfullscreenchange", function () {
      document.dispatchEvent(new Event("fullscreenchange"));
    });

    document.addEventListener("keydown", function (ev) {
      if (ev.key === "Escape" && block.classList.contains("is-cad-fullscreen-fallback")) {
        exitCadFullscreen();
      }
    });

    window.showProductCadFullscreenBtn = function () {
      btn.hidden = false;
    };
  }

  function showCadFullscreenBtn() {
    if (typeof window.showProductCadFullscreenBtn === "function") window.showProductCadFullscreenBtn();
  }

  /** Контур граней + flat shading на меше */
  function addProductStlEdges(mesh, geometry, angleDeg) {
    try {
      const edgeGeo = new THREE.EdgesGeometry(geometry, angleDeg);
      const lines = new THREE.LineSegments(
        edgeGeo,
        new THREE.LineBasicMaterial({ color: 0x1e2436, depthTest: true, transparent: true, opacity: 0.92 })
      );
      mesh.add(lines);
    } catch (_e) {}
  }

  function mountMiniStlViewer(targetHost, url) {
    if (!targetHost || !url) return;
    if (targetHost.querySelector("canvas")) return;
    targetHost.innerHTML = "";
    const scene = new THREE.Scene();
    scene.background = null;
    const h = targetHost.clientHeight || 220;
    const w = Math.max(targetHost.clientWidth || 200, 120);
    const camera = new THREE.PerspectiveCamera(50, w / h, 0.005, 1e7);
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, cadPixelRatioCap));
    renderer.setClearColor(0x000000, 0);
    renderer.setSize(w, h);
    if ("outputColorSpace" in renderer) renderer.outputColorSpace = THREE.SRGBColorSpace;
    if ("toneMapping" in renderer) {
      renderer.toneMapping = THREE.ACESFilmicToneMapping;
      renderer.toneMappingExposure = 1.08;
    }
    targetHost.appendChild(renderer.domElement);

    scene.add(new THREE.AmbientLight(0xffffff, 0.38));
    scene.add(new THREE.HemisphereLight(0xdde4ff, 0x1a1e28, 0.55));
    const key = new THREE.DirectionalLight(0xffffff, 0.85);
    key.position.set(6, 10, 8);
    scene.add(key);
    const fill = new THREE.DirectionalLight(0xb8c8ff, 0.35);
    fill.position.set(-8, 2, -6);
    scene.add(fill);

    const controls = createCadControls(camera, renderer.domElement);
    let miniRoot = null;

    new STLLoader().load(
      new URL(url, window.location.origin).href,
      function (geometry) {
        geometry.computeBoundingSphere();
        geometry.center();
        geometry.computeVertexNormals();
        const mesh = new THREE.Mesh(
          geometry,
          new THREE.MeshStandardMaterial({
            color: 0xc4cef0,
            metalness: 0.06,
            roughness: 0.28,
            flatShading: true,
          })
        );
        addProductStlEdges(mesh, geometry, 12);
        const root = new THREE.Group();
        root.add(mesh);
        scene.add(root);
        miniRoot = root;
        fitCameraToObject(camera, controls, root);
      },
      undefined,
      function () {
        targetHost.innerHTML = '<p class="muted" style="padding:8px;margin:0;">Не удалось загрузить STL.</p>';
      }
    );
    bindCadViewReset(targetHost, controls, function () {
      return miniRoot;
    });
    function onResize() {
      const rw = targetHost.clientWidth;
      const rh = targetHost.clientHeight || 220;
      camera.aspect = rw / rh;
      camera.updateProjectionMatrix();
      renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, cadPixelRatioCap));
      renderer.setSize(rw, rh);
    }
    window.addEventListener("resize", onResize);
    let miniRaf = 0;
    (function tick() {
      miniRaf = requestAnimationFrame(tick);
      controls.update();
      renderer.render(scene, camera);
    })();
  }

  function runStlViewer() {
    if (!host || !stlUrl) return;
    if (host.querySelector("canvas")) return;
    if (cadViewerStarted) return;
    cadViewerStarted = true;

    const scene = new THREE.Scene();
    scene.background = null;
    const h0 = host.clientHeight || 260;
    const w0 = Math.max(host.clientWidth || 200, 200);
    const camera = new THREE.PerspectiveCamera(50, w0 / h0, 0.005, 1e7);
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, preserveDrawingBuffer: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, cadPixelRatioCap));
    renderer.setClearColor(0x000000, 0);
    renderer.setSize(w0, h0);
    if ("outputColorSpace" in renderer) renderer.outputColorSpace = THREE.SRGBColorSpace;
    if ("toneMapping" in renderer) {
      renderer.toneMapping = THREE.ACESFilmicToneMapping;
      renderer.toneMappingExposure = 1.08;
    }
    cadRenderer = renderer;
    host.appendChild(renderer.domElement);
    showCadFullscreenBtn();

    scene.add(new THREE.AmbientLight(0xffffff, 0.38));
    scene.add(new THREE.HemisphereLight(0xdde4ff, 0x1a1e28, 0.55));
    const key = new THREE.DirectionalLight(0xffffff, 0.85);
    key.position.set(6, 10, 8);
    scene.add(key);
    const fill = new THREE.DirectionalLight(0xb8c8ff, 0.35);
    fill.position.set(-8, 2, -6);
    scene.add(fill);
    const rim = new THREE.DirectionalLight(0xffffff, 0.28);
    rim.position.set(0, -6, 10);
    scene.add(rim);

    const controls = createCadControls(camera, renderer.domElement);
    bindCadViewReset(host, controls, function () {
      return cadViewerState && cadViewerState.root ? cadViewerState.root : null;
    });

    function onResize(refit) {
      const w = host.clientWidth;
      const h = host.clientHeight || 260;
      if (w < 1 || h < 1) return;
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, cadPixelRatioCap));
      renderer.setSize(w, h);
      if (refit && cadViewerState && cadViewerState.root) {
        fitCameraToObject(camera, controls, cadViewerState.root);
      }
    }
    window.addEventListener("resize", function () { onResize(false); });

    function tick() {
      const rafId = requestAnimationFrame(tick);
      if (cadViewerState) cadViewerState.rafId = rafId;
      controls.update();
      renderer.render(scene, camera);
    }
    const myToken = ++cadLoadToken;
    cadViewerState = {
      renderer: renderer,
      controls: controls,
      onResize: onResize,
      root: null,
      rafId: null,
      loadToken: myToken,
    };
    tick();

    new STLLoader().load(
      stlUrl,
      function (geometry) {
        if (!cadViewerState || cadViewerState.loadToken !== myToken) {
          try { geometry.dispose(); } catch (e) {}
          return;
        }
        clearCadLoading();
        geometry.computeBoundingSphere();
        geometry.center();
        geometry.computeVertexNormals();

        const mat = new THREE.MeshStandardMaterial({
          color: 0xc4cef0,
          metalness: 0.06,
          roughness: 0.28,
          flatShading: true,
        });
        const mesh = new THREE.Mesh(geometry, mat);

        addProductStlEdges(mesh, geometry, 12);

        const root = new THREE.Group();
        root.add(mesh);
        scene.add(root);
        if (cadViewerState && cadViewerState.loadToken === myToken) {
          cadViewerState.root = root;
        }
        onResize(true);
        fitCameraToObject(camera, controls, root);
        requestAnimationFrame(function () {
          onResize(true);
          fitCameraToObject(camera, controls, root);
        });
      },
      undefined,
      function () {
        if (!cadViewerState || cadViewerState.loadToken !== myToken) return;
        showCadError("Не удалось загрузить STL для предпросмотра. Скачайте файл по ссылке ниже.");
      }
    );
  }

  function startCadViewerWhenVisible() {
    if (!host || !stlUrl) return;
    if (host.querySelector("canvas")) return;
    _layoutTries = 0;
    try {
      waitLayout(() => runStlViewer());
    } catch (e) {
      showCadError("Предпросмотр 3D недоступен в этом браузере. Скачайте файл ниже.");
    }
  }
  window.startProductCadViewer = startCadViewerWhenVisible;
  window.setProductCadSource = function (nextUrl) {
    if (!host) return;
    stlUrl = nextUrl ? new URL(nextUrl, window.location.origin).href : "";
    host.dataset.stlUrl = stlUrl;
    disposeCadViewer();
    host.innerHTML = '<p class="muted product-cad-loading">Загрузка предпросмотра…</p>';
    cadViewerStarted = false;
    if (cadRenderer) {
      try { cadRenderer.dispose(); } catch (e) {}
      cadRenderer = null;
    }
    startCadViewerWhenVisible();
  };
  function refreshSetupCadButton() {
    if (!setupStlBtn || !tabsRoot) return;
    var sideEl = document.getElementById("product-detail-side");
    var activeTab = tabsRoot.querySelector(".product-tab.is-active");
    var tabName = activeTab ? (activeTab.getAttribute("data-tab") || "") : "";
    if (!tabName) {
      var setupSelect = document.getElementById("setup-tab-select");
      tabName = setupSelect ? (setupSelect.value || "") : "";
    }
    if (sideEl) sideEl.setAttribute("data-current-tab", tabName || "");
    var isSetupTab = tabName.indexOf("setup-") === 0;
    setupStlBtn.hidden = !(isSetupTab && inlineEditEnabled);
    if (!(isSetupTab && inlineEditEnabled)) return;
    var hasSetupStl = !!(activeTab && (activeTab.getAttribute("data-setup-stl-url") || "").trim());
    setupStlBtn.textContent = hasSetupStl ? "Заменить 3D" : "Залить 3D";
  }
  window.addEventListener("setup-inline-edit-mode", function (ev) {
    inlineEditEnabled = !!(ev && ev.detail && ev.detail.enabled);
    refreshSetupCadButton();
  });
  document.addEventListener("click", function (ev) {
    var btn = ev.target && ev.target.closest ? ev.target.closest(".product-tab, #setup-tab-select") : null;
    if (btn) setTimeout(refreshSetupCadButton, 0);
  });
  if (setupStlBtn && setupStlInput) {
    setupStlBtn.addEventListener("click", function () {
      setupStlInput.click();
    });
    setupStlInput.addEventListener("change", async function () {
      var f = setupStlInput.files && setupStlInput.files[0];
      if (!f) return;
      if (!/\.stl$/i.test(f.name || "")) {
        alert("Можно загружать только STL.");
        setupStlInput.value = "";
        return;
      }
      var activeTab = tabsRoot ? tabsRoot.querySelector(".product-tab.is-active") : null;
      if (!activeTab) return;
      var tabId = activeTab.id || "";
      var m = tabId.match(/tab-setup-(\d+)/);
      if (!m) return;
      var setupId = m[1];
      var fd = new FormData();
      fd.append("action", "inline_replace_setup_stl");
      fd.append("setup_id", setupId);
      fd.append("stl_file", f);
      var resp = await fetch(window.location.href, {
        method: "POST",
        headers: { "X-CSRFToken": getCookie("csrftoken"), "X-Requested-With": "XMLHttpRequest" },
        body: fd,
        credentials: "same-origin",
      });
      var data = await resp.json();
      if (!resp.ok || !data.ok) {
        alert(data.error || "Не удалось загрузить STL.");
        setupStlInput.value = "";
        return;
      }
      activeTab.setAttribute("data-setup-stl-url", data.url || "");
      window.setProductCadSource(data.url || "");
      refreshSetupCadButton();
      setupStlInput.value = "";
    });
  }
  const side = document.getElementById("product-detail-side");
  if (!side || !side.hidden) {
    startCadViewerWhenVisible();
  }
  document.querySelectorAll(".setup-cad-mini-viewport").forEach((mini) => {
    const miniUrl = mini.getAttribute("data-setup-stl-url") || "";
    if (miniUrl) mountMiniStlViewer(mini, miniUrl);
  });
  refreshSetupCadButton();
  bindCadFullscreen();

  function getCookie(name) {
    const m = document.cookie.match(new RegExp("(^|; )" + name + "=([^;]*)"));
    return m ? decodeURIComponent(m[2]) : "";
  }

  if (saveBtn) {
    saveBtn.addEventListener("click", function () {
      if (!cadRenderer || !cadRenderer.domElement) {
        if (saveMsg) saveMsg.textContent = "3D ещё не готово для сохранения.";
        return;
      }
      saveBtn.disabled = true;
      if (saveMsg) saveMsg.textContent = "Сохраняю превью...";
      cadRenderer.domElement.toBlob(async function (blob) {
        if (!blob) {
          saveBtn.disabled = false;
          if (saveMsg) saveMsg.textContent = "Не удалось создать изображение.";
          return;
        }
        try {
          const fd = new FormData();
          fd.append("preview_image", blob, "preview.png");
          const r = await fetch(savePreviewUrl, {
            method: "POST",
            headers: { "X-CSRFToken": getCookie("csrftoken") },
            body: fd,
            credentials: "same-origin",
          });
          const j = await r.json();
          if (!r.ok || !j.ok) throw new Error(j.error || "Ошибка сохранения.");
          if (saveMsg) saveMsg.textContent = "Превью сохранено. Откройте список изделий для проверки.";
        } catch (err) {
          if (saveMsg) saveMsg.textContent = "Не удалось сохранить превью.";
        } finally {
          saveBtn.disabled = false;
        }
      }, "image/png");
    });
  }

