(function (global) {
  var DELETE_STEPS = 5;
  var STEP_PREFIX = "btn-inv-delete--s";
  var TRASH_SVG =
    '<svg class="btn-inv-delete__icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
    '<path d="M3 6h18"/>' +
    '<path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6"/>' +
    '<path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>' +
    '<line x1="10" y1="11" x2="10" y2="17"/>' +
    '<line x1="14" y1="11" x2="14" y2="17"/>' +
    "</svg>";

  function ensureIcon(btn) {
    if (!btn || btn.querySelector(".btn-inv-delete__icon")) return;
    btn.innerHTML = TRASH_SVG;
  }

  function captureBaseClasses(btn) {
    if (!btn || btn.getAttribute("data-delete-base")) return;
    var parts = btn.className.split(/\s+/).filter(Boolean);
    var filtered = parts.filter(function (c) {
      return c !== "btn-inv-delete" && !/^btn-inv-delete--s\d+$/.test(c);
    });
    if (filtered.indexOf("btn") === -1) filtered.unshift("btn");
    filtered.push("btn-inv-delete");
    btn.setAttribute("data-delete-base", filtered.join(" "));
  }

  function reset(btn) {
    if (!btn) return;
    captureBaseClasses(btn);
    ensureIcon(btn);
    var base = btn.getAttribute("data-delete-base") || "btn btn-inv-delete";
    btn.setAttribute("data-step", "0");
    btn.className = base + " btn-inv-delete--s0";
    btn.setAttribute("aria-label", "Удалить: 0 из " + DELETE_STEPS);
    btn.title = "Удалить: нажмите " + DELETE_STEPS + " раз";
  }

  function setStep(btn, step) {
    if (!btn) return;
    captureBaseClasses(btn);
    ensureIcon(btn);
    var base = btn.getAttribute("data-delete-base") || "btn btn-inv-delete";
    btn.setAttribute("data-step", String(step));
    btn.className = base + " " + STEP_PREFIX + step;
    btn.setAttribute("aria-label", "Удалить: " + step + " из " + DELETE_STEPS);
    btn.title =
      step < DELETE_STEPS
        ? "Удалить: ещё " + (DELETE_STEPS - step) + " наж."
        : "Подтвердить удаление";
  }

  function init(btn) {
    if (!btn) return;
    btn.removeAttribute("data-delete-base");
    reset(btn);
  }

  function handleClick(btn, confirmMsg, onFinal) {
    if (!btn) return false;
    captureBaseClasses(btn);
    ensureIcon(btn);
    var step = parseInt(btn.getAttribute("data-step") || "0", 10) + 1;
    if (step < DELETE_STEPS) {
      setStep(btn, step);
      return false;
    }
    setStep(btn, DELETE_STEPS);
    if (confirmMsg && !window.confirm(confirmMsg)) {
      reset(btn);
      return false;
    }
    reset(btn);
    if (onFinal) onFinal();
    return true;
  }

  function initAll(scope, selector) {
    var root = scope || document;
    root.querySelectorAll(selector || ".btn-inv-delete").forEach(init);
  }

  function resetAll(scope, selector) {
    var root = scope || document;
    root.querySelectorAll(selector || ".btn-inv-delete").forEach(reset);
  }

  function initForms(formSelector, confirmMsg, options) {
    var opts = options || {};
    document.querySelectorAll(formSelector || ".biota-delete-form").forEach(function (form) {
      if (form.getAttribute("data-delete-initialized") === "1") return;
      var btn = form.querySelector(".btn-inv-delete");
      if (!btn) return;
      form.setAttribute("data-delete-initialized", "1");
      init(btn);
      btn.addEventListener("click", function (e) {
        if (opts.stopPropagation) e.stopPropagation();
        if (opts.preventDefault) e.preventDefault();
        var step = parseInt(btn.getAttribute("data-step") || "0", 10) + 1;
        if (step < DELETE_STEPS) {
          setStep(btn, step);
          return;
        }
        setStep(btn, DELETE_STEPS);
        var msg = confirmMsg || form.getAttribute("data-delete-confirm") || "Удалить?";
        if (window.confirm(msg)) {
          form.submit();
        } else {
          reset(btn);
        }
      });
    });
  }

  function bootDefaultForms() {
    initForms(".inv-stock-delete-form", "Удалить эту позицию склада?");
    initForms(".product-tile-delete-form", "Удалить эту наладку?", { stopPropagation: true });
  }

  global.BiotaDeleteBtn = {
    DELETE_STEPS: DELETE_STEPS,
    TRASH_SVG: TRASH_SVG,
    ensureIcon: ensureIcon,
    reset: reset,
    setStep: setStep,
    init: init,
    handleClick: handleClick,
    initAll: initAll,
    resetAll: resetAll,
    initForms: initForms,
    bootDefaultForms: bootDefaultForms,
  };

  if (typeof document !== "undefined") {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", bootDefaultForms);
    } else {
      bootDefaultForms();
    }
  }
})(typeof window !== "undefined" ? window : this);
