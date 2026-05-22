/* product_detail.js — extracted from product_detail.html, uses data island #pd-options */
var PD = (function () {
  try {
    var el = document.getElementById("pd-options");
    return el ? JSON.parse(el.textContent) : {};
  } catch (e) { return {}; }
})();

  (function () {
    document.querySelectorAll(".js-print-setup-html").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var frameId = btn.getAttribute("data-frame-id") || "";
        if (!frameId) return;
        var frame = document.getElementById(frameId);
        try {
          if (frame && frame.contentWindow) {
            frame.contentWindow.focus();
            frame.contentWindow.print();
            return;
          }
        } catch (err) {}
        var htmlUrl = "";
        if (frame && frame.getAttribute("src")) {
          htmlUrl = frame.getAttribute("src") || "";
        }
        if (!htmlUrl) {
          var openLink = btn.closest(".setup-inline-actions")?.querySelector("a[href]");
          if (openLink) htmlUrl = openLink.getAttribute("href") || "";
        }
        if (!htmlUrl) return;
        var printWin = window.open(htmlUrl, "_blank", "noopener");
        if (!printWin) return;
        var launchPrint = function () {
          try {
            printWin.focus();
            printWin.print();
          } catch (e) {}
        };
        printWin.addEventListener("load", launchPrint, { once: true });
      });
    });
  })();
  (function () {
    function syncSetupHtmlIframeHeight() {
      if (window.innerWidth > 720) return;
      document.querySelectorAll(".setup-inline-pdf iframe").forEach(function (frame) {
        var src = (frame.getAttribute("src") || "").toLowerCase();
        if (!src || (src.indexOf(".html") === -1 && src.indexOf(".htm") === -1)) return;
        var wrap = frame.closest(".setup-inline-pdf");
        if (!wrap) return;
        var applyHeight = function () {
          try {
            var doc = frame.contentDocument || (frame.contentWindow && frame.contentWindow.document);
            if (!doc || !doc.body) return;
            var body = doc.body;
            var html = doc.documentElement;
            var h = Math.max(
              body.scrollHeight || 0,
              body.offsetHeight || 0,
              html ? html.scrollHeight : 0,
              html ? html.offsetHeight : 0
            );
            if (!h) return;
            wrap.classList.add("is-html-embed");
            frame.style.height = h + "px";
          } catch (e) {
            // Ignore non-accessible frames (e.g. PDF viewer).
          }
        };
        frame.addEventListener("load", applyHeight);
        applyHeight();
      });
    }

    syncSetupHtmlIframeHeight();
    window.addEventListener("resize", syncSetupHtmlIframeHeight);
  })();

  (function () {
    var modal = document.getElementById("setup-photo-modal");
    var modalImg = document.getElementById("setup-photo-modal-img");
    var modalCaption = document.getElementById("setup-photo-modal-caption");
    var closeBtn = document.getElementById("setup-photo-modal-close");
    var previewPop = document.getElementById("binding-photo-preview-pop");
    var previewImg = previewPop ? previewPop.querySelector("img") : null;
    if (!modal || !modalImg || !modalCaption || !closeBtn) return;

    var fineHoverMq = window.matchMedia("(hover: hover) and (pointer: fine)");
    var previewHideTimer = null;
    var previewActiveLink = null;

    function hideBindingPreview() {
      if (previewHideTimer) {
        clearTimeout(previewHideTimer);
        previewHideTimer = null;
      }
      if (!previewPop || !previewImg) return;
      previewPop.hidden = true;
      previewPop.setAttribute("aria-hidden", "true");
      previewImg.removeAttribute("src");
      previewActiveLink = null;
    }

    function scheduleHideBindingPreview() {
      if (previewHideTimer) clearTimeout(previewHideTimer);
      previewHideTimer = window.setTimeout(hideBindingPreview, 200);
    }

    function positionBindingPreview(link) {
      if (!previewPop) return;
      var r = link.getBoundingClientRect();
      var pw = 220;
      var ph = 150;
      var gap = 8;
      var left = r.left + r.width / 2 - pw / 2;
      var top = r.bottom + gap;
      var maxL = window.innerWidth - pw - 8;
      left = Math.max(8, Math.min(left, maxL));
      if (top + ph > window.innerHeight - 8) {
        top = r.top - ph - gap;
      }
      if (top < 8) {
        top = r.bottom + gap;
        if (top + ph > window.innerHeight - 8) {
          top = Math.max(8, Math.min(r.top + r.height / 2 - ph / 2, window.innerHeight - ph - 8));
        }
      }
      previewPop.style.left = left + "px";
      previewPop.style.top = top + "px";
    }

    function showBindingPreview(link) {
      if (!previewPop || !previewImg || !fineHoverMq.matches) return;
      var url = link.getAttribute("data-photo-url");
      if (!url || !modal.hidden) return;
      if (previewHideTimer) {
        clearTimeout(previewHideTimer);
        previewHideTimer = null;
      }
      previewActiveLink = link;
      previewImg.alt = link.getAttribute("aria-label") || "";
      previewImg.src = url;
      previewPop.removeAttribute("hidden");
      previewPop.setAttribute("aria-hidden", "false");
      positionBindingPreview(link);
    }

    if (previewPop && previewImg) {
      document.addEventListener(
        "mouseover",
        function (e) {
          var t = e.target;
          if (!t || !t.closest) return;
          var link = t.closest("a.binding-photo-link.setup-photo-open");
          if (!link) return;
          showBindingPreview(link);
        },
        true
      );
      document.addEventListener(
        "mouseout",
        function (e) {
          if (!previewActiveLink || !previewPop) return;
          var rel = e.relatedTarget;
          if (rel) {
            var stillInside =
              previewActiveLink.contains(rel) ||
              previewActiveLink === rel ||
              previewPop.contains(rel) ||
              previewPop === rel;
            if (stillInside) return;
          }
          var from = e.target;
          var fromZone =
            previewActiveLink.contains(from) ||
            previewActiveLink === from ||
            previewPop.contains(from) ||
            previewPop === from;
          if (fromZone) scheduleHideBindingPreview();
        },
        true
      );
      function syncPreviewOnScroll() {
        if (previewPop.hidden || !previewActiveLink) return;
        if (!document.body.contains(previewActiveLink)) {
          hideBindingPreview();
          return;
        }
        positionBindingPreview(previewActiveLink);
      }
      window.addEventListener("scroll", syncPreviewOnScroll, true);
      window.addEventListener("resize", syncPreviewOnScroll);
    }

    function closeModal() {
      modal.hidden = true;
      modalImg.src = "";
      modalCaption.textContent = "";
      document.body.style.overflow = "";
    }

    function openModal(url, caption) {
      hideBindingPreview();
      modalImg.src = url || "";
      modalCaption.textContent = caption || "";
      modal.hidden = false;
      document.body.style.overflow = "hidden";
    }

    document.addEventListener("click", function (e) {
      var a = e.target && e.target.closest ? e.target.closest(".setup-photo-open") : null;
      if (!a) return;
      e.preventDefault();
      openModal(a.getAttribute("data-photo-url"), a.getAttribute("data-photo-caption"));
    });

    modal.addEventListener("click", function (e) {
      var target = e.target;
      if (target && target.getAttribute("data-close-photo-modal") === "1") {
        closeModal();
      }
    });
    closeBtn.addEventListener("click", closeModal);
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && !modal.hidden) {
        closeModal();
      } else if (e.key === "Escape" && previewPop && !previewPop.hidden) {
        hideBindingPreview();
      }
    });
  })();
  (function () {
    var root = document.getElementById("product-tabs");
    if (!root) return;
    var tabButtons = root.querySelectorAll(".product-tab");
    var panels = root.querySelectorAll(".product-tab-panel");
    var programDownloadBtn = document.getElementById("product-program-download");
    var productNoteTaResizeWired = false;

    function getCookie(name) {
      var m = document.cookie.match(new RegExp("(^|; )" + name + "=([^;]*)"));
      return m ? decodeURIComponent(m[2]) : "";
    }

    function setProgramDownloadByTab(tabName) {
      if (!programDownloadBtn) return;
      if (tabName === "drawing") {
        programDownloadBtn.hidden = true;
        return;
      }
      var btn = root.querySelector('.product-tab[data-tab="' + tabName + '"]');
      var programUrl = btn ? (btn.getAttribute("data-program-url") || "") : "";
      var programFilename = btn ? (btn.getAttribute("data-program-filename") || "") : "";
      if (!programUrl) {
        if (tabName === "program") {
          programUrl = root.getAttribute("data-product-program-url") || "";
          programFilename = root.getAttribute("data-product-program-filename") || "";
        } else {
          programDownloadBtn.hidden = true;
          return;
        }
      }
      if (!programUrl) {
        programDownloadBtn.hidden = true;
        return;
      }
      programDownloadBtn.href = programUrl;
      programDownloadBtn.textContent = programFilename || "программа";
      programDownloadBtn.hidden = false;
    }

    function setTopButtonsByTab(tabName) {
      var isSetupTab = /^setup-\d+$/.test(tabName || "");
      var exportSpecsBtn = document.getElementById("setup-export-specs-btn");
      var exportPhotosBtn = document.getElementById("setup-export-photos-btn");
      if (exportSpecsBtn) exportSpecsBtn.hidden = !isSetupTab;
      if (exportPhotosBtn) exportPhotosBtn.hidden = !isSetupTab;
      if (isSetupTab) {
        var m = (tabName || "").match(/^setup-(\d+)$/);
        var setupId = m ? m[1] : "";
        if (setupId) {
          var specsPattern = PD.pdf_url_specs;
          var photosPattern = PD.pdf_url_photos;
          if (exportSpecsBtn) exportSpecsBtn.href = specsPattern.replace("/0/pdf/specs/", "/" + setupId + "/pdf/specs/");
          if (exportPhotosBtn) exportPhotosBtn.href = photosPattern.replace("/0/pdf/photos/", "/" + setupId + "/pdf/photos/");
        }
      }
    }

    function setSideBlocksByTab(tabName) {
      var isDrawing = tabName === "drawing";
      var side = document.getElementById("product-detail-side");
      var meta = document.getElementById("product-detail-meta");
      var grid = document.querySelector(".product-detail-grid");
      var savePreviewBlock = document.getElementById("product-save-preview-block");
      var downloadsBlock = document.getElementById("product-downloads-block");
      if (meta) meta.hidden = !isDrawing;
      if (grid) grid.classList.toggle("has-meta-column", isDrawing);
      if (side) side.hidden = false;
      if (side) side.setAttribute("data-current-tab", tabName || "");
      if (grid) grid.classList.toggle("is-drawing-only", false);
      if (savePreviewBlock) savePreviewBlock.hidden = false;
      if (downloadsBlock) downloadsBlock.hidden = false;
      var sideProgramWrap = document.getElementById("product-side-programs");
      if (sideProgramWrap) {
        var isSetupTab = /^setup-\d+$/.test(tabName || "");
        sideProgramWrap.hidden = !isSetupTab;
        sideProgramWrap.querySelectorAll(".product-side-program-files").forEach(function (el) {
          var isMatch = el.getAttribute("data-setup-tab") === tabName;
          el.hidden = !isMatch;
        });
      }
      document.querySelectorAll(".product-side-notes-panel").forEach(function (el) {
        var isMatch = el.getAttribute("data-notes-for-tab") === tabName;
        el.hidden = !isMatch;
      });
      if (typeof window.startProductCadViewer === "function") {
        window.startProductCadViewer();
      }
      if (typeof window.setProductCadSource === "function") {
        var drawingStlUrl = PD.stl_preview_url;
        window.setProductCadSource(drawingStlUrl);
      }
    }

    function initProductDownloadsCollapse() {
      var block = document.getElementById("product-downloads-block");
      var toggle = document.getElementById("product-downloads-toggle");
      var inner = document.getElementById("product-downloads-inner");
      if (!block || !toggle || !inner) return;
      toggle.addEventListener("click", function () {
        block.classList.toggle("is-collapsed");
        var isCollapsed = block.classList.contains("is-collapsed");
        toggle.setAttribute("aria-expanded", isCollapsed ? "false" : "true");
      });
    }

    function activate(tabName) {
      root.setAttribute("data-current-tab", tabName || "");
      tabButtons.forEach(function (btn) {
        var on = btn.getAttribute("data-tab") === tabName;
        btn.classList.toggle("is-active", on);
        btn.setAttribute("aria-selected", on ? "true" : "false");
      });
      panels.forEach(function (panel) {
        if (panel.getAttribute("data-panel") === tabName) {
          panel.removeAttribute("hidden");
        } else {
          panel.setAttribute("hidden", "hidden");
        }
      });
      setProgramDownloadByTab(tabName);
      setTopButtonsByTab(tabName);
      setSideBlocksByTab(tabName);
      window.requestAnimationFrame(function () {
        resizeAllProductNoteTextareas();
      });
      var setupSelect = document.getElementById("setup-tab-select");
      if (setupSelect) setupSelect.value = tabName;
      try {
        document.dispatchEvent(new CustomEvent("biota:setup-tab-changed", { detail: { tab: tabName } }));
      } catch (_) {}
    }
    tabButtons.forEach(function (btn) {
      btn.addEventListener("click", function () {
        var name = btn.getAttribute("data-tab");
        if (name) activate(name);
      });
    });

    initProductDownloadsCollapse();

    function initProductAssetReplace() {
      document.querySelectorAll(".js-product-asset-replace").forEach(function (btn) {
        btn.addEventListener("click", function () {
          var row = btn.closest("[data-product-asset-row]");
          var inp = row ? row.querySelector(".js-product-asset-file-input") : null;
          if (inp) inp.click();
        });
      });
      document.querySelectorAll(".js-product-asset-file-input").forEach(function (inp) {
        inp.addEventListener("change", async function () {
          var file = inp.files && inp.files[0];
          if (!file) return;
          var fieldName = inp.getAttribute("data-field-name") || "";
          if (!fieldName) return;
          var fd = new FormData();
          fd.append("action", "inline_replace_product_asset");
          fd.append("field_name", fieldName);
          fd.append("file", file);
          try {
            var res = await fetch(window.location.href, {
              method: "POST",
              headers: { "X-CSRFToken": getCookie("csrftoken"), "X-Requested-With": "XMLHttpRequest" },
              body: fd,
              credentials: "same-origin",
            });
            var data = await res.json().catch(function () { return {}; });
            if (!res.ok || !data.ok) {
              alert(data.error || "Не удалось сохранить файл.");
              inp.value = "";
              return;
            }
            window.location.reload();
          } catch (e) {
            alert("Ошибка сети при загрузке файла.");
            inp.value = "";
          }
        });
      });
    }
    initProductAssetReplace();

    function autoResizeProductNoteTextarea(el) {
      if (!el || el.nodeName !== "TEXTAREA") return;
      var cs = window.getComputedStyle(el);
      var maxH = parseFloat(cs.maxHeight);
      if (isNaN(maxH) || maxH <= 0) maxH = 320;
      var minH = parseFloat(cs.minHeight);
      if (isNaN(minH) || minH <= 0) minH = 48;
      el.style.height = "auto";
      var sh = el.scrollHeight;
      el.style.height = Math.min(Math.max(sh, minH), maxH) + "px";
      el.style.overflowY = sh > maxH ? "auto" : "hidden";
    }

    function resizeAllProductNoteTextareas() {
      document.querySelectorAll(".js-product-note-body").forEach(autoResizeProductNoteTextarea);
    }

    function initProductNoteTextareaAutosize() {
      document.querySelectorAll(".js-product-note-body").forEach(function (ta) {
        if (ta.getAttribute("data-note-autosize") === "1") return;
        ta.setAttribute("data-note-autosize", "1");
        var run = function () {
          autoResizeProductNoteTextarea(ta);
        };
        ta.addEventListener("input", run);
        ta.addEventListener("paste", function () {
          window.requestAnimationFrame(function () {
            window.requestAnimationFrame(run);
          });
        });
        run();
      });
      if (!productNoteTaResizeWired) {
        productNoteTaResizeWired = true;
        var resizeTimer = null;
        window.addEventListener("resize", function () {
          if (resizeTimer) window.clearTimeout(resizeTimer);
          resizeTimer = window.setTimeout(function () {
            resizeTimer = null;
            resizeAllProductNoteTextareas();
          }, 120);
        });
      }
    }

    function initProductDrawingNotes() {
      document.querySelectorAll(".js-product-note-form").forEach(function (form) {
        form.addEventListener("submit", async function (e) {
          e.preventDefault();
          var ta = form.querySelector(".js-product-note-body");
          var msg = form.querySelector(".js-product-note-form-msg");
          var body = (ta && ta.value || "").trim();
          if (!body) return;
          if (msg) {
            msg.style.display = "none";
            msg.textContent = "";
          }
          var fd = new FormData();
          fd.append("action", "add_product_note");
          fd.append("body", body);
          var sid = (form.getAttribute("data-note-setup-id") || "").trim();
          if (sid) fd.append("setup_id", sid);
          try {
            var res = await fetch(window.location.href, {
              method: "POST",
              headers: { "X-CSRFToken": getCookie("csrftoken"), "X-Requested-With": "XMLHttpRequest" },
              body: fd,
              credentials: "same-origin",
            });
            var data = await res.json().catch(function () { return {}; });
            if (!res.ok || !data.ok) {
              if (msg) {
                msg.style.display = "";
                msg.textContent = data.error || "Не удалось сохранить заметку.";
              }
              return;
            }
            var tabSlug = "drawing";
            var tabsRoot = document.getElementById("product-tabs");
            if (tabsRoot) {
              var cur = (tabsRoot.getAttribute("data-current-tab") || "").trim();
              if (cur) tabSlug = cur;
            }
            try {
              var u = new URL(window.location.href);
              if (tabSlug && tabSlug !== "drawing") u.searchParams.set("tab", tabSlug);
              else u.searchParams.delete("tab");
              window.location.href = u.toString();
            } catch (_e2) {
              window.location.reload();
            }
          } catch (err) {
            if (msg) {
              msg.style.display = "";
              msg.textContent = "Ошибка сети.";
            }
          }
        });
      });
    }
    initProductDrawingNotes();
    initProductNoteTextareaAutosize();

    function initProductNoteDeletes() {
      document.addEventListener("click", async function (ev) {
        var btn = ev.target && ev.target.closest && ev.target.closest(".js-product-note-delete");
        if (!btn) return;
        ev.preventDefault();
        var id = (btn.getAttribute("data-note-id") || "").trim();
        if (!id || !window.confirm("Удалить эту заметку?")) return;
        var fd = new FormData();
        fd.append("action", "delete_product_note");
        fd.append("note_id", id);
        try {
          var res = await fetch(window.location.href, {
            method: "POST",
            headers: { "X-CSRFToken": getCookie("csrftoken"), "X-Requested-With": "XMLHttpRequest" },
            body: fd,
            credentials: "same-origin",
          });
          var data = await res.json().catch(function () { return {}; });
          if (!res.ok || !data.ok) {
            alert(data.error || "Не удалось удалить заметку.");
            return;
          }
          var li = btn.closest(".product-drawing-notes__item");
          var ul = li && li.parentElement;
          if (li) li.remove();
          if (ul && !ul.querySelector(".product-drawing-notes__item")) {
            var empty = document.createElement("li");
            empty.className = "product-drawing-notes__empty muted";
            empty.textContent = "Пока нет заметок.";
            ul.appendChild(empty);
          }
        } catch (_err) {
          alert("Ошибка сети.");
        }
      });
    }
    initProductNoteDeletes();

    var setupSelect = document.getElementById("setup-tab-select");
    if (setupSelect) {
      setupSelect.addEventListener("change", function () {
        var tab = setupSelect.value || "";
        if (tab) activate(tab);
      });
      var initialTab = setupSelect.value || "drawing";
      activate(initialTab);
      return;
    }
    if (tabButtons.length) {
      activate(tabButtons[0].getAttribute("data-tab") || "");
    } else {
      root.setAttribute("data-current-tab", "drawing");
      setProgramDownloadByTab("drawing");
      setTopButtonsByTab("drawing");
      setSideBlocksByTab("drawing");
    }
  })();
  (function () {
    var editToggleBtn = document.getElementById("setup-inline-edit-btn");
    var root = document.getElementById("product-tabs");
    var detailGrid = document.querySelector(".product-detail-grid");
    if (!root) return;
    var inlineEditMode = false;

    function productDetailMetaEl() {
      return document.getElementById("product-detail-meta");
    }

    function productDetailPlanScope() {
      return detailGrid || document;
    }

    function productDetailPlanWrap() {
      var meta = productDetailMetaEl();
      if (!meta) return null;
      return meta.querySelector(".product-drawing-plan-section")
        || meta.querySelector("[data-product-plan-summary]");
    }

    function forEachPlanCascadeForm(cb) {
      productDetailPlanScope().querySelectorAll("[data-plan-cascade-form]").forEach(cb);
    }

    function syncMetaDrawingInlineEdit(enabled) {
      var meta = productDetailMetaEl();
      if (!meta) return;
      meta.setAttribute("data-inline-edit-mode", enabled ? "1" : "0");
      meta.querySelectorAll("[data-field-text]").forEach(function (node) {
        var field = node.getAttribute("data-field-text") || "";
        if (!field || field === "setup_notes") return;
        if (enabled) {
          node.classList.add("is-inline-edit");
          node.contentEditable = "true";
          node.setAttribute("spellcheck", field === "product_description" ? "true" : "false");
          if (field === "product_description") {
            var emptyLbl = (node.getAttribute("data-empty-label") || "Описание не задано.").trim();
            if ((node.textContent || "").trim() === emptyLbl) node.textContent = "";
          }
        } else {
          node.classList.remove("is-inline-edit");
          node.contentEditable = "false";
          node.removeAttribute("contenteditable");
          if (field === "product_description") {
            var emptyLbl2 = (node.getAttribute("data-empty-label") || "Описание не задано.").trim();
            if (!(node.textContent || "").trim()) node.textContent = emptyLbl2;
          }
        }
      });
    }
    var notesSelection = null;
    var TOOL_TYPE_OPTIONS = (PD.tool_type_choices || []);

    function syncInlineDeleteSetupBtn() {
      var btn = document.getElementById("setup-inline-delete-setup-btn");
      if (!btn) return;
      var inline = document.body.classList.contains("setup-inline-edit-enabled");
      var sel = document.getElementById("setup-tab-select");
      var val = sel ? sel.value : "";
      var isSetup = /^setup-\d+$/.test(val || "");
      if (inline && isSetup) btn.removeAttribute("hidden");
      else btn.setAttribute("hidden", "hidden");
    }
    document.addEventListener("biota:setup-tab-changed", syncInlineDeleteSetupBtn);

    function getCookie(name) {
      var m = document.cookie.match(new RegExp("(^|; )" + name + "=([^;]*)"));
      return m ? decodeURIComponent(m[2]) : "";
    }

    function syncProductPlanSummaryBlocks(summary) {
      if (!summary) return;
      document.querySelectorAll("[data-product-plan-summary]").forEach(function (wrap) {
        var kind = wrap.querySelector("[data-plan-product-kind-line]");
        var b = wrap.querySelector("[data-plan-workpiece-line]");
        var c = wrap.querySelector("[data-plan-material-line]");
        if (kind) kind.textContent = summary.product_kind_line || summary.type_line || "—";
        if (b) b.textContent = summary.workpiece_line || "—";
        if (c) c.textContent = summary.material_line || "—";
      });
    }

    function syncSetupPlanInlineVisibility(wrap) {
      if (!wrap) return;
      var pt = wrap.querySelector(".js-plan-inline-product-type");
      if (!pt) return;
      var ptype = pt.value || "made";
      var wp = wrap.querySelector(".js-plan-inline-workpiece");
      var wpv = wp ? wp.value : "";
      var showMade = ptype === "made";
      var showLaser = showMade && wpv === "laser";
      wrap.classList.toggle("plan-summary-editing-workpiece", showMade);
      wrap.classList.toggle("plan-summary-editing-laser-thick", showLaser);
      wrap.classList.toggle("plan-summary-editing-material", showMade && !!wpv);
    }

    function applyPlanInlineStateToQuickEdits(state) {
      if (!state) return;
      document.querySelectorAll("[data-plan-fields-root]").forEach(function (pr) {
        var typeVal = state.plan_product_type || "made";
        pr.querySelectorAll(".js-product-plan-type").forEach(function (r) {
          r.checked = r.value === typeVal;
        });
        var wp = pr.querySelector(".js-product-plan-workpiece");
        if (wp) wp.value = state.workpiece_type || "";
        var thick = pr.querySelector(".js-product-plan-laser-thick");
        if (thick) thick.value = state.laser_sheet_thickness_mm || "";
        var mat = pr.querySelector(".js-product-plan-made-material, .js-product-plan-laser-mark, .js-plan-inline-material");
        if (mat) mat.value = state.plan_material || state.made_material || state.laser_material_marking || "";
        var wrap = pr.querySelector("[data-workpiece-laser-wrap]");
        var laser = pr.querySelector("[data-laser-panel]");
        var madePanel = pr.querySelector("[data-made-material-panel]");
        var t = pr.querySelector(".js-product-plan-type:checked");
        var ptype = t ? t.value : "made";
        if (wrap) wrap.style.display = ptype === "made" ? "" : "none";
        if (laser && wp) {
          laser.style.display = ptype === "made" && wp.value === "laser" ? "" : "none";
        }
        if (madePanel && wp) {
          madePanel.style.display =
            ptype === "made" && wp.value && wp.value !== "laser" ? "" : "none";
        }
      });
      document.querySelectorAll("[data-product-plan-summary]").forEach(function (wrap) {
        var pt = wrap.querySelector(".js-plan-inline-product-type");
        if (pt) pt.value = state.plan_product_type || "made";
        var wp = wrap.querySelector(".js-plan-inline-workpiece");
        if (wp) wp.value = state.workpiece_type || "";
        var thick = wrap.querySelector(".js-plan-inline-laser-thick");
        if (thick) thick.value = state.laser_sheet_thickness_mm || "";
        var mat = wrap.querySelector(".js-plan-inline-material");
        if (mat) mat.value = state.plan_material || state.made_material || state.laser_material_marking || "";
        syncSetupPlanInlineVisibility(wrap);

      });
      forEachPlanCascadeForm(function (cascadeFormContainer) {
        if (cascadeFormContainer._cascadeFormManager) {
          cascadeFormContainer._cascadeFormManager.syncFromServer(state);
        }
      });
    }

    window.biotaSyncProductPlanSummaries = syncProductPlanSummaryBlocks;
    window.biotaApplyPlanInlineStateToQuickEdits = applyPlanInlineStateToQuickEdits;

    function getCurrentTabName() {
      var sel = document.getElementById("setup-tab-select");
      if (sel && sel.value) return sel.value;
      var activeTab = root.querySelector(".product-tab.is-active");
      return activeTab ? (activeTab.getAttribute("data-tab") || "") : "";
    }

    function activeSetupPanel() {
      var tabName = getCurrentTabName();
      if (!tabName || tabName === "drawing") return null;
      return root.querySelector('.product-tab-panel[data-panel="' + tabName + '"]');
    }

    function normalizeToolNumber(raw) {
      var src = (raw || "").trim().toUpperCase();
      if (!src) return "";
      var m = src.match(/^(?:T\s*)?(\d{1,4})$/);
      if (!m) return src;
      var n = parseInt(m[1], 10) || 0;
      if (n < 100) return "T" + String(n).padStart(2, "0");
      return "T" + n;
    }

    function expectedCorrectors(toolNo) {
      var norm = normalizeToolNumber(toolNo);
      if (!norm || norm.charAt(0) !== "T" || norm.length < 3) return { h: "", d: "" };
      var suffix = norm.slice(1).padStart(2, "0");
      return { h: "H" + suffix, d: "D" + suffix };
    }

    function toolNumberSortKey(text) {
      var norm = normalizeToolNumber((text || "").trim());
      if (norm && norm.charAt(0) === "T" && norm.length > 1) {
        var rest = norm.slice(1);
        if (/^\d+$/.test(rest)) return [0, parseInt(rest, 10)];
      }
      if (norm) return [1, String(norm).toUpperCase()];
      return [2, ""];
    }

    function sortSetupToolsTbodyByToolNumber(tbody) {
      if (!tbody) return;
      var rows = Array.prototype.slice.call(tbody.querySelectorAll("tr"));
      rows.sort(function (a, b) {
        var ta = a.querySelector('td[data-tool-col="tool_number"]');
        var tb = b.querySelector('td[data-tool-col="tool_number"]');
        var ka = toolNumberSortKey(ta ? ta.textContent : "");
        var kb = toolNumberSortKey(tb ? tb.textContent : "");
        if (ka[0] !== kb[0]) return ka[0] - kb[0];
        if (ka[0] === 0) return (ka[1] || 0) - (kb[1] || 0);
        var sa = String(ka[1] || "");
        var sb = String(kb[1] || "");
        if (sa < sb) return -1;
        if (sa > sb) return 1;
        return 0;
      });
      rows.forEach(function (r) {
        tbody.appendChild(r);
      });
    }

    function sortPanelSetupToolRows(panel) {
      if (!panel) return;
      panel.querySelectorAll(".setup-tools-view tbody").forEach(sortSetupToolsTbodyByToolNumber);
    }

    function syncRowOrderDisplay(panel) {
      if (!panel) return;
      panel.querySelectorAll(".setup-tools-view.has-tool-row-move tbody tr").forEach(function (tr, i) {
        tr.setAttribute("data-tool-row-index", String(i));
      });
    }

    function maxToolNumericInPanel(panel) {
      var max = 0;
      panel.querySelectorAll('.setup-tools-view td[data-tool-col="tool_number"]').forEach(function (td) {
        var nStr = normalizeToolNumber(td.textContent || "");
        if (!nStr || nStr.charAt(0) !== "T") return;
        var num = parseInt(nStr.slice(1), 10);
        if (!isNaN(num) && num > max) max = num;
      });
      return max;
    }

    function nextToolNumberDisplay(panel) {
      var max = maxToolNumericInPanel(panel);
      var n = max + 1;
      if (n < 100) return "T" + String(n).padStart(2, "0");
      return "T" + n;
    }

    function appendSetupToolRow(panel) {
      if (!panel) return;
      var tbody = panel.querySelector(".setup-tools-view tbody");
      if (!tbody) return;
      var toolNo = nextToolNumberDisplay(panel);
      var tr = document.createElement("tr");
      var tdActions = document.createElement("td");
      tdActions.className = "setup-tools-row-actions-cell";
      var innerActions = document.createElement("div");
      innerActions.className = "setup-tools-row-actions-cell-inner";
      var btnRm = document.createElement("button");
      btnRm.type = "button";
      btnRm.className = "btn btn-ghost setup-tools-remove-row-btn js-setup-tools-remove-row";
      btnRm.title = "Удалить строку";
      btnRm.setAttribute("aria-label", "Удалить строку инструмента");
      var icRm = document.createElement("i");
      icRm.className = "fi fi-br-cross ui-icon";
      icRm.setAttribute("aria-hidden", "true");
      btnRm.appendChild(icRm);
      innerActions.appendChild(btnRm);
      tdActions.appendChild(innerActions);
      tr.appendChild(tdActions);
      var tdNo = document.createElement("td");
      tdNo.setAttribute("data-tool-col", "tool_number");
      tdNo.textContent = toolNo;
      tr.appendChild(tdNo);
      var tdCor = document.createElement("td");
      tdCor.setAttribute("data-tool-col", "correction_enabled");
      tdCor.setAttribute("data-correction-enabled", "0");
      tdCor.className = "setup-tool-correction-cell";
      var spanBox = document.createElement("span");
      spanBox.className = "setup-tool-correction-box";
      spanBox.setAttribute("aria-hidden", "true");
      tdCor.appendChild(spanBox);
      tr.appendChild(tdCor);
      ["kor_n", "kor_d"].forEach(function (col) {
        var td = document.createElement("td");
        td.setAttribute("data-tool-col", col);
        tr.appendChild(td);
      });
      var tdType = document.createElement("td");
      tdType.setAttribute("data-tool-col", "tool_type");
      tdType.setAttribute("data-tool-type-value", "");
      tr.appendChild(tdType);
      ["diameter", "overhang", "note"].forEach(function (col) {
        var td = document.createElement("td");
        td.setAttribute("data-tool-col", col);
        tr.appendChild(td);
      });
      tbody.appendChild(tr);
      sortSetupToolsTbodyByToolNumber(tbody);
      syncRowOrderDisplay(panel);
      if (inlineEditMode) setToolsEditMode(panel, true, tr);
      syncToolOverrideClasses(panel);
    }

    function getRowToolType(row) {
      var c = row.querySelector('td[data-tool-col="tool_type"]');
      if (!c) return "";
      var sel = c.querySelector("select.js-inline-tool-type");
      if (sel) return (sel.value || "").trim();
      return (c.getAttribute("data-tool-type-value") || c.textContent || "").trim();
    }

    function looksLikeDescriptiveDiameter(s) {
      var t = (s || "").trim();
      if (!t) return false;
      if (/^[mM]\d/.test(t)) return false;
      if (/^(?:[⌀ØφΦ]\s*)?[\d.,]+(?:\s*(?:мм|mm))?\s*$/i.test(t)) return false;
      if (/^[dD]\d/.test(t)) return false;
      return true;
    }

    var TOOL_TYPES_METRIC_THREAD = { Метчик: 1, Раскатник: 1, Резьбофреза: 1 };
    function toolTypeUsesMetricThreadDiameter(tt) {
      return !!TOOL_TYPES_METRIC_THREAD[(tt || "").trim()];
    }

    function stripLeadingDiameterMarksOnly(s) {
      var u = (s || "").trim();
      if (!u) return "";
      while (true) {
        var v = u.replace(/^\s+/, "");
        if (/^[⌀ØφΦ]/.test(v)) {
          u = v.slice(1).replace(/^\s+/, "");
          continue;
        }
        var dm = v.match(/^[dD](\d.*)$/);
        if (dm) {
          u = dm[1].trim();
          continue;
        }
        break;
      }
      return u.trim();
    }

    function formatToolDiameterDisplay(text, toolType) {
      var s = (text || "").trim();
      if (!s) return "";
      var tt = (toolType || "").trim();
      if (tt === "Другое") {
        return stripLeadingDiameterMarksOnly(s);
      }
      if (toolTypeUsesMetricThreadDiameter(tt)) {
        var u = s;
        while (true) {
          var v = u.replace(/^\s+/, "");
          if (/^[⌀ØφΦ]/.test(v)) {
            u = v.slice(1).replace(/^\s+/, "");
            continue;
          }
          var dm = v.match(/^[dD](\d.*)$/);
          if (dm) {
            u = dm[1].trim();
            continue;
          }
          break;
        }
        u = u.trim();
        if (!u) return "";
        if (/^m/i.test(u)) return "M" + u.slice(1).replace(/^\s+/, "");
        return "M" + u;
      }
      if (/^[mM]\d/.test(s)) return s;
      if (looksLikeDescriptiveDiameter(s)) return s;
      var t = s;
      while (true) {
        var v2 = t.replace(/^\s+/, "");
        if (/^[⌀ØφΦ]/.test(v2)) {
          t = v2.slice(1).replace(/^\s+/, "");
          continue;
        }
        var dm2 = v2.match(/^[dD](\d.*)$/);
        if (dm2) {
          t = dm2[1].trim();
          continue;
        }
        break;
      }
      t = t.trim();
      return t ? "⌀" + t : "⌀";
    }

    function formatToolOverhangDisplay(text) {
      var s = (text || "").trim();
      if (!s) return "";
      var base = s.replace(/\s*(?:мм|mm)\s*$/i, "").trim();
      return base ? base + " мм" : "";
    }

    function syncToolOverrideClasses(panel) {
      if (!panel) return;
      panel.querySelectorAll(".setup-tools-view tbody tr").forEach(function (row) {
        var toolCell = row.querySelector('td[data-tool-col="tool_number"]');
        var hCell = row.querySelector('td[data-tool-col="kor_n"]');
        var dCell = row.querySelector('td[data-tool-col="kor_d"]');
        if (!toolCell || !hCell || !dCell) return;
        var exp = expectedCorrectors(toolCell.textContent || "");
        var curH = (hCell.textContent || "").trim().toUpperCase();
        var curD = (dCell.textContent || "").trim().toUpperCase();
        var hOverride = !!(exp.h && curH && curH !== exp.h);
        var dOverride = !!(exp.d && curD && curD !== exp.d);
        hCell.classList.toggle("setup-tool-override", hOverride);
        dCell.classList.toggle("setup-tool-override", dOverride);
      });
    }

    function setToolsEditMode(panel, enabled, singleRowOpt) {
      if (enabled) sortPanelSetupToolRows(panel);
      var rows = singleRowOpt
        ? [singleRowOpt]
        : Array.prototype.slice.call(panel.querySelectorAll(".setup-tools-view tbody tr"));
      rows.forEach(function (row) {
        row.querySelectorAll("td[data-tool-col]").forEach(function (cell) {
          var col = cell.getAttribute("data-tool-col") || "";
          if (col === "tool_number") {
            if (enabled) {
              cell.textContent = (cell.textContent || "").trim();
              cell.classList.add("is-inline-edit");
              cell.setAttribute("contenteditable", "true");
              cell.setAttribute("spellcheck", "false");
            } else {
              var rawTn = (cell.textContent || "").trim().toUpperCase();
              var normTn = normalizeToolNumber(rawTn);
              cell.textContent = normTn || rawTn || "";
              cell.classList.remove("is-inline-edit");
              cell.removeAttribute("contenteditable");
            }
            return;
          }
          if (col === "correction_enabled") {
            cell.classList.remove("is-inline-edit");
            cell.removeAttribute("contenteditable");
            return;
          }
          if (col === "tool_type") {
            if (enabled) {
              var cur = cell.getAttribute("data-tool-type-value") || (cell.textContent || "").trim();
              cell.innerHTML = "";
              var sel = document.createElement("select");
              sel.className = "js-inline-tool-type";
              TOOL_TYPE_OPTIONS.forEach(function (optDef) {
                var opt = document.createElement("option");
                opt.value = optDef.value;
                opt.textContent = optDef.label;
                if (optDef.value === cur) opt.selected = true;
                sel.appendChild(opt);
              });
              cell.appendChild(sel);
              cell.classList.add("is-inline-edit");
            } else {
              var selectEl = cell.querySelector("select.js-inline-tool-type");
              if (selectEl) {
                var val = selectEl.value || "";
                cell.setAttribute("data-tool-type-value", val);
                cell.textContent = val;
              }
              cell.classList.remove("is-inline-edit");
            }
            return;
          }
          if (enabled) {
            cell.textContent = cell.textContent || "";
            cell.classList.add("is-inline-edit");
            cell.setAttribute("contenteditable", "true");
            cell.setAttribute("spellcheck", "false");
            if (col === "kor_n" || col === "kor_d") {
              var raw = (cell.textContent || "").toUpperCase().trim();
              var digits = raw.replace(/[^0-9]/g, "");
              cell.textContent = digits;
            }
          } else {
            if (col === "kor_n" || col === "kor_d") {
              var digitsOut = (cell.textContent || "").replace(/[^0-9]/g, "");
              if (digitsOut) {
                var prefix = col === "kor_n" ? "H" : "D";
                cell.textContent = prefix + digitsOut;
              } else {
                cell.textContent = "";
              }
            } else if (col === "diameter" || col === "overhang") {
              var ttRow = getRowToolType(row);
              if (col === "diameter") {
                cell.textContent = formatToolDiameterDisplay((cell.textContent || "").trim(), ttRow);
              } else {
                cell.textContent = formatToolOverhangDisplay((cell.textContent || "").trim());
              }
            }
            cell.classList.remove("is-inline-edit");
            cell.removeAttribute("contenteditable");
          }
        });
      });
      if (!enabled) {
        sortPanelSetupToolRows(panel);
        syncToolOverrideClasses(panel);
      }
      if (panel.querySelector(".setup-tools-view.has-tool-row-move")) syncRowOrderDisplay(panel);
    }

    function collectToolsRows(panel) {
      var rows = [];
      panel.querySelectorAll(".setup-tools-view tbody tr").forEach(function (row) {
        var getCellValue = function (colName) {
          var cell = row.querySelector('td[data-tool-col="' + colName + '"]');
          if (!cell) return "";
          if (colName === "correction_enabled") {
            return cell.getAttribute("data-correction-enabled") === "1";
          }
          if (colName === "tool_type") {
            var sel = cell.querySelector("select.js-inline-tool-type");
            return (sel ? sel.value : (cell.getAttribute("data-tool-type-value") || cell.textContent || "")).trim();
          }
          if (colName === "kor_n" || colName === "kor_d") {
            var digits = (cell.textContent || "").replace(/[^0-9]/g, "");
            if (digits) {
              return (colName === "kor_n" ? "H" : "D") + digits;
            }
            var tnCell = row.querySelector('td[data-tool-col="tool_number"]');
            var tnRaw = (tnCell && tnCell.textContent ? tnCell.textContent : "").trim().toUpperCase();
            var tnNorm = normalizeToolNumber(tnRaw) || tnRaw;
            var exp = expectedCorrectors(tnNorm);
            if (colName === "kor_n" && exp.h) return exp.h;
            if (colName === "kor_d" && exp.d) return exp.d;
            return "";
          }
          if (colName === "tool_number") {
            var tRaw = (cell.textContent || "").trim().toUpperCase();
            return normalizeToolNumber(tRaw) || tRaw;
          }
          return (cell.textContent || "").trim();
        };
        rows.push({
          tool_number: getCellValue("tool_number"),
          correction_enabled: getCellValue("correction_enabled"),
          kor_n: getCellValue("kor_n"),
          kor_d: getCellValue("kor_d"),
          tool_type: getCellValue("tool_type"),
          diameter: getCellValue("diameter"),
          overhang: getCellValue("overhang"),
          note: getCellValue("note"),
        });
      });
      return rows;
    }

    function syncPhotoDnDMode(panel, enabled) {
      if (!panel) return;
      var wraps = panel.querySelectorAll(".product-setup-photos");
      wraps.forEach(function (wrap) {
        if (enabled) wrap.classList.add("is-inline-edit");
        else wrap.classList.remove("is-inline-edit");
      });
      panel.querySelectorAll(".setup-photo-figure").forEach(function (figure) {
        var photoId = (figure.getAttribute("data-photo-id") || "").trim();
        if (enabled && photoId) {
          figure.setAttribute("draggable", "true");
        } else {
          figure.removeAttribute("draggable");
          figure.classList.remove("is-dragging", "is-drop-target");
        }
      });
    }

    function syncSpecDnDMode(panel, enabled) {
      if (!panel) return;
      var stack = panel.querySelector(".setup-spec-stack");
      if (!stack) return;
      if (enabled) stack.classList.add("is-inline-edit");
      else stack.classList.remove("is-inline-edit");
      stack.querySelectorAll(".setup-spec-box").forEach(function (box) {
        if (box.classList.contains("setup-spec-box-header")) return;
        if (enabled) {
          box.setAttribute("draggable", "true");
        } else {
          box.removeAttribute("draggable");
          box.classList.remove("is-dragging", "is-drop-target", "is-drop-before", "is-drop-after", "is-drop-commit");
        }
      });
    }

    async function persistSetupPhotosOrder(photosWrap, setupId) {
      if (!photosWrap || !setupId) return;
      var ids = [];
      photosWrap.querySelectorAll(".setup-photo-figure[data-photo-id]").forEach(function (figure) {
        var id = (figure.getAttribute("data-photo-id") || "").trim();
        if (id) ids.push(id);
      });
      if (!ids.length) return;
      var fd = new FormData();
      fd.append("action", "inline_reorder_setup_photos");
      fd.append("setup_id", setupId);
      fd.append("photo_ids", ids.join(","));
      var res = await fetch(window.location.href, {
        method: "POST",
        headers: { "X-CSRFToken": getCookie("csrftoken"), "X-Requested-With": "XMLHttpRequest" },
        body: fd,
        credentials: "same-origin",
      });
      var data = await res.json();
      if (!res.ok || !data.ok) {
        alert(data.error || "Не удалось сохранить порядок фото.");
      }
    }

    function parseGcodeSystemDisplay(str) {
      var s = (str || "").trim();
      var m = /^G54\.1\s*P\s*(\d{1,2})\s*$/i.exec(s);
      if (m) {
        var n = Math.min(99, Math.max(0, parseInt(m[1], 10) || 0));
        return { sel: "__G54_1_P__", pText: String(n) };
      }
      var u = s.toUpperCase();
      if (/^G5[4-9]$/.test(u)) return { sel: u, pText: "0" };
      return { sel: "G54", pText: "0" };
    }

    function syncGcodeControlsFromSpan(gcodeSpan, gSel, pWrap, pSpan) {
      if (!gSel || !gcodeSpan) return;
      var parsed = parseGcodeSystemDisplay(gcodeSpan.textContent || "G54");
      gSel.value = parsed.sel;
      if (pSpan) pSpan.textContent = parsed.pText;
      if (pWrap) pWrap.hidden = parsed.sel !== "__G54_1_P__";
    }

    function syncGcodeSpanFromControls(gcodeSpan, gSel, pSpan) {
      if (!gSel || !gcodeSpan) return;
      if (gSel.value === "__G54_1_P__") {
        var n = Math.min(99, Math.max(0, parseInt((pSpan && pSpan.textContent) || "0", 10) || 0));
        gcodeSpan.textContent = "G54.1 P" + n;
      } else {
        gcodeSpan.textContent = gSel.value || "G54";
      }
    }

    function collectGcodeSystemFromWrap(wrap) {
      if (!wrap) return "G54";
      var gSel = wrap.querySelector(".js-inline-gcode-system");
      var pSpan = wrap.querySelector(".js-inline-gcode-p");
      var gcodeSpan = wrap.querySelector('[data-field-text="gcode_system"]');
      if (!gSel || !gcodeSpan) return "G54";
      if (gSel.value === "__G54_1_P__") {
        var n = Math.min(99, Math.max(0, parseInt((pSpan && pSpan.textContent) || "0", 10) || 0));
        return "G54.1 P" + n;
      }
      return gSel.value || "G54";
    }

    function bindingPhotoUrlFromBox(box, fieldName) {
      if (!box || !fieldName) return "";
      var btn = box.querySelector('.setup-binding-photo-btn[data-photo-field="' + fieldName + '"]');
      var rail = btn ? btn.closest(".setup-binding-photo-rail") : null;
      if (!rail) return "";
      var link = rail.querySelector(".binding-photo-link");
      if (!link) return "";
      return (link.getAttribute("data-photo-url") || link.getAttribute("href") || "").trim();
    }

    function syncBindingPhotoButtonsInPanel(panel, show) {
      if (!panel) return;
      panel.querySelectorAll(".setup-binding-photo-btn").forEach(function (btn) {
        if (show) btn.removeAttribute("hidden");
        else btn.setAttribute("hidden", "hidden");
      });
    }

    function collectBindingSpecBlocksFromStack(panelSetup) {
      var stack = panelSetup.querySelector(".setup-spec-stack");
      if (!stack) return [];
      return Array.from(stack.querySelectorAll(".setup-spec-box:not(.setup-spec-box-header)")).map(function (box) {
        var bx = box.querySelector('[data-field-text="binding_x"]');
        var by = box.querySelector('[data-field-text="binding_y"]');
        var bz = box.querySelector('[data-field-text="binding_z"]');
        var gw = box.querySelector(".setup-gcode-value");
        function normDash(el) {
          var t = el ? (el.textContent || "").trim() : "";
          return t === "—" ? "" : t;
        }
        return {
          binding_x: normDash(bx),
          binding_y: normDash(by),
          binding_z: normDash(bz),
          gcode_system: collectGcodeSystemFromWrap(gw),
          binding_x_photo: bindingPhotoUrlFromBox(box, "binding_x_photo"),
          binding_y_photo: bindingPhotoUrlFromBox(box, "binding_y_photo"),
          binding_z_photo: bindingPhotoUrlFromBox(box, "binding_z_photo"),
        };
      });
    }

    function setGcodePWrapVisibilityFromSelect(sel) {
      if (!sel) return;
      var wrap = sel.closest(".setup-gcode-value");
      var pWrap = wrap ? wrap.querySelector(".js-inline-gcode-p-wrap") : null;
      if (!pWrap) return;
      var show = sel.value === "__G54_1_P__";
      pWrap.hidden = !show;
      var pSpan = wrap ? wrap.querySelector(".js-inline-gcode-p") : null;
      var inlineOn = document.body.classList.contains("setup-inline-edit-enabled");
      if (!pSpan || !inlineOn) return;
      if (show) {
        pSpan.classList.add("is-inline-edit");
        pSpan.setAttribute("contenteditable", "true");
        pSpan.setAttribute("spellcheck", "false");
      } else {
        pSpan.classList.remove("is-inline-edit");
        pSpan.removeAttribute("contenteditable");
      }
    }

    function reindexExtraBindingBlocks(stack) {
      if (!stack) return;
      Array.from(stack.querySelectorAll(".setup-spec-box-extra")).forEach(function (box, idx) {
        box.setAttribute("data-extra-block-index", String(idx));
        box.querySelectorAll(".setup-binding-photo-btn, .setup-binding-photo-input").forEach(function (el) {
          el.setAttribute("data-extra-block-index", String(idx));
        });
      });
    }

    function applyBindingPhotoUrlToBox(box, fieldName, url, captionPrefix) {
      if (!box) return;
      var rowFieldMap = {
        binding_x_photo: "Привязка X",
        binding_y_photo: "Привязка Y",
        binding_z_photo: "Привязка Z",
      };
      var label = rowFieldMap[fieldName] || "Фото";
      var isExtra = box.classList.contains("setup-spec-box-extra");
      var caption = (captionPrefix ? captionPrefix + " — " : "") + label + (isExtra ? " (доп.)" : "");
      var btn = box.querySelector('.setup-binding-photo-btn[data-photo-field="' + fieldName + '"]');
      if (!btn) return;
      var rail = btn.closest(".setup-binding-photo-rail");
      if (!rail) return;
      rail.querySelectorAll(".binding-photo-link").forEach(function (link) {
        if (link.remove) link.remove();
      });
      if (url) {
        var link = document.createElement("a");
        link.href = url;
        link.className = "binding-photo-link setup-photo-open";
        link.setAttribute("data-photo-url", url);
        link.setAttribute("data-photo-caption", caption);
        link.setAttribute("aria-label", "Открыть фото: " + label);
        link.innerHTML = '<i class="fi fi-rr-camera ui-icon" aria-hidden="true"></i>';
        rail.insertBefore(link, btn);
      }
      btn.innerHTML = '<i class="fi fi-rr-add-document ui-icon" aria-hidden="true"></i>';
    }

    function buildExtraSpecBoxFromSource(sourceBox, clearValues) {
      if (!sourceBox) return null;
      var clone = sourceBox.cloneNode(true);
      clone.classList.remove("setup-spec-box-extra");
      clone.classList.add("setup-spec-box-extra");
      clone.removeAttribute("data-extra-block-index");
      clone.querySelectorAll("[data-field-text]").forEach(function (el) {
        var field = el.getAttribute("data-field-text") || "";
        if (clearValues) {
          if (field === "gcode_system") el.textContent = "G54";
          else el.textContent = "—";
        }
        if (inlineEditMode && field !== "gcode_system") {
          el.classList.add("is-inline-edit");
          el.setAttribute("contenteditable", "true");
          el.setAttribute("spellcheck", "false");
        } else {
          el.classList.remove("is-inline-edit");
          el.removeAttribute("contenteditable");
        }
      });
      clone.querySelectorAll(".setup-program-files-inline").forEach(function (wrap) {
        if (!clearValues) return;
        var ul = wrap.querySelector(".setup-program-files-list");
        if (ul) ul.innerHTML = "";
        var emptyMsg = wrap.querySelector(".setup-program-tab-empty-msg");
        if (emptyMsg) emptyMsg.hidden = false;
        wrap.querySelectorAll(".js-setup-program-file-delete").forEach(function (b) {
          if (b.remove) b.remove();
        });
      });
      clone.querySelectorAll(".js-inline-gcode-system").forEach(function (sel) {
        var wrap = sel.closest(".setup-gcode-value");
        var pWrap = wrap ? wrap.querySelector(".js-inline-gcode-p-wrap") : null;
        var pSpan = wrap ? wrap.querySelector(".js-inline-gcode-p") : null;
        if (clearValues) {
          sel.value = "G54";
          if (pSpan) pSpan.textContent = "0";
          if (pWrap) pWrap.setAttribute("hidden", "hidden");
        }
        var span = wrap ? wrap.querySelector('[data-field-text="gcode_system"]') : null;
        if (inlineEditMode) {
          sel.removeAttribute("hidden");
          if (span) span.setAttribute("hidden", "hidden");
          setGcodePWrapVisibilityFromSelect(sel);
        } else {
          sel.setAttribute("hidden", "hidden");
          if (pWrap) pWrap.setAttribute("hidden", "hidden");
          if (span) {
            span.removeAttribute("hidden");
            if (!clearValues) syncGcodeSpanFromControls(span, sel, pSpan);
            else span.textContent = sel.value || "G54";
          }
          if (pSpan) {
            pSpan.classList.remove("is-inline-edit");
            pSpan.removeAttribute("contenteditable");
          }
        }
      });
      if (clearValues) {
        clone.querySelectorAll(".setup-photo-open, .binding-photo-link").forEach(function (link) {
          if (link.remove) link.remove();
        });
      }
      return clone;
    }

    function syncDrawingPanelQuickEdit(enabled) {
      var meta = productDetailMetaEl();
      if (!meta) return;
      var toolbar = meta.querySelector(".description-toolbar");
      if (toolbar) {
        if (enabled) toolbar.removeAttribute("hidden");
        else toolbar.setAttribute("hidden", "hidden");
      }
      var planSection = meta.querySelector(".product-drawing-plan-section");
      if (planSection) planSection.classList.toggle("is-plan-readonly", !enabled);
      meta.querySelectorAll("[data-plan-cascade-form] select, [data-plan-cascade-form] input").forEach(function (el) {
        el.disabled = !enabled;
      });
    }

    function refreshInlineFieldTitles(scope, isInlineMode) {
      var wrap = scope || root;
      wrap.querySelectorAll("[data-field-text]").forEach(function (node) {
        var field = node.getAttribute("data-field-text") || "";
        if (!field || field === "setup_notes") return;
        if (field === "product_description") {
          var emptyLabel = (node.getAttribute("data-empty-label") || "Описание не задано.").trim();
          if (isInlineMode && (node.textContent || "").trim() === emptyLabel) node.textContent = "";
          if (!isInlineMode && !(node.textContent || "").trim()) node.textContent = emptyLabel;
        }
        if (isInlineMode) {
          node.removeAttribute("title");
          return;
        }
        var txt = (node.textContent || "").replace(/\s+/g, " ").trim();
        if (!txt || txt === "—") {
          node.removeAttribute("title");
          return;
        }
        node.setAttribute("title", txt);
      });
    }

    function exitInlineEditAfterSave() {
      if (inlineEditMode) toggleInlineEdit();
    }

    function toggleInlineEdit() {
      inlineEditMode = !inlineEditMode;
      document.body.classList.toggle("setup-inline-edit-enabled", inlineEditMode);
      root.querySelectorAll(".product-tab-panel").forEach(function (panel) {
        var isDrawingPanel = panel.id === "panel-drawing";
        var toolbar = panel.querySelector(".setup-inline-toolbar-block");
        if (toolbar) {
          if (inlineEditMode && !isDrawingPanel) toolbar.removeAttribute("hidden");
          else toolbar.setAttribute("hidden", "hidden");
        }
        panel.setAttribute("data-inline-edit-mode", inlineEditMode ? "1" : "0");
        panel.querySelectorAll("[data-field-text]").forEach(function (node) {
          var field = node.getAttribute("data-field-text");
          if (!field) return;
          if (field === "gcode_system") {
            var wrap = node.closest(".setup-gcode-value");
            var gSel = wrap ? wrap.querySelector(".js-inline-gcode-system") : null;
            var pWrap = wrap ? wrap.querySelector(".js-inline-gcode-p-wrap") : null;
            var pSpan = wrap ? wrap.querySelector(".js-inline-gcode-p") : null;
            if (inlineEditMode) {
              node.setAttribute("hidden", "hidden");
              if (gSel) {
                syncGcodeControlsFromSpan(node, gSel, pWrap, pSpan);
                gSel.removeAttribute("hidden");
                setGcodePWrapVisibilityFromSelect(gSel);
              }
            } else {
              node.removeAttribute("hidden");
              if (gSel) {
                syncGcodeSpanFromControls(node, gSel, pSpan);
                gSel.setAttribute("hidden", "hidden");
              }
              if (pWrap) pWrap.setAttribute("hidden", "hidden");
              if (pSpan) {
                pSpan.classList.remove("is-inline-edit");
                pSpan.removeAttribute("contenteditable");
              }
            }
            node.classList.remove("is-inline-edit");
            node.removeAttribute("contenteditable");
            return;
          }
          if (inlineEditMode) {
            node.classList.add("is-inline-edit");
            node.setAttribute("contenteditable", "true");
            node.setAttribute("spellcheck", field === "setup_notes" || field === "product_description" ? "true" : "false");
            if (field === "product_description") {
              var emptyLbl = (node.getAttribute("data-empty-label") || "Описание не задано.").trim();
              if ((node.textContent || "").trim() === emptyLbl) node.textContent = "";
            }
          } else {
            node.classList.remove("is-inline-edit");
            node.removeAttribute("contenteditable");
            if (field === "product_description") {
              var emptyLbl2 = (node.getAttribute("data-empty-label") || "Описание не задано.").trim();
              if (!(node.textContent || "").trim()) node.textContent = emptyLbl2;
            }
          }
        });
        if (!isDrawingPanel) {
          panel.querySelectorAll(".setup-photo-inline-controls").forEach(function (row) {
            if (inlineEditMode) row.removeAttribute("hidden");
            else row.setAttribute("hidden", "hidden");
          });
          panel.querySelectorAll(".setup-spec-actions").forEach(function (row) {
            if (inlineEditMode) row.removeAttribute("hidden");
            else row.setAttribute("hidden", "hidden");
          });
          panel.querySelectorAll(".setup-photo-caption").forEach(function (cap) {
            if (inlineEditMode) {
              cap.classList.add("is-inline-edit");
              cap.setAttribute("contenteditable", "true");
              cap.setAttribute("spellcheck", "true");
            } else {
              cap.classList.remove("is-inline-edit");
              cap.removeAttribute("contenteditable");
            }
          });
          panel.querySelectorAll(".setup-photo-add-row").forEach(function (row) {
            if (inlineEditMode) row.removeAttribute("hidden");
            else row.setAttribute("hidden", "hidden");
          });
          panel.querySelectorAll(".setup-tools-add-row").forEach(function (row) {
            if (inlineEditMode) row.removeAttribute("hidden");
            else row.setAttribute("hidden", "hidden");
          });
          setToolsEditMode(panel, inlineEditMode);
          if (panel.querySelector(".setup-tools-view.has-tool-row-move")) {
            syncRowOrderDisplay(panel);
          }
          syncPhotoDnDMode(panel, inlineEditMode);
          syncSpecDnDMode(panel, inlineEditMode);
        }
        panel.querySelectorAll(".setup-binding-photo-btn").forEach(function (btn) {
          if (inlineEditMode) btn.removeAttribute("hidden");
          else btn.setAttribute("hidden", "hidden");
        });
        panel.querySelectorAll(".setup-program-upload-btn").forEach(function (btn) {
          if (inlineEditMode) btn.removeAttribute("hidden");
          else btn.setAttribute("hidden", "hidden");
        });
      });
      document.querySelectorAll(".setup-program-upload-btn").forEach(function (btn) {
        if (inlineEditMode) btn.removeAttribute("hidden");
        else btn.setAttribute("hidden", "hidden");
      });
      var planSumAll = productDetailPlanWrap();
      if (planSumAll && planSumAll.querySelector("[data-product-plan-summary]")) {
        syncSetupPlanInlineVisibility(planSumAll.querySelector("[data-product-plan-summary]"));
      }
      root.querySelectorAll(".product-tab-panel").forEach(function (panel) {
        refreshInlineFieldTitles(panel, inlineEditMode);
      });
      var metaRoot = productDetailMetaEl();
      if (metaRoot) refreshInlineFieldTitles(metaRoot, inlineEditMode);
      syncMetaDrawingInlineEdit(inlineEditMode);
      if (editToggleBtn) {
        editToggleBtn.textContent = inlineEditMode ? "Сохранить изменения" : "Быстрое редактирование";
      }
      syncDrawingPanelQuickEdit(inlineEditMode);
      syncInlineDeleteSetupBtn();
      window.dispatchEvent(new CustomEvent("setup-inline-edit-mode", { detail: { enabled: inlineEditMode } }));
    }

    function forceDisableInlineEdit() {
      inlineEditMode = false;
      document.body.classList.remove("setup-inline-edit-enabled");
      if (editToggleBtn) {
        editToggleBtn.textContent = "Быстрое редактирование";
      }
      root.querySelectorAll(".setup-inline-toolbar-block").forEach(function (toolbar) {
        toolbar.setAttribute("hidden", "hidden");
      });
      (detailGrid || root).querySelectorAll("[data-field-text]").forEach(function (node) {
        node.classList.remove("is-inline-edit");
        node.removeAttribute("contenteditable");
      });
      syncMetaDrawingInlineEdit(false);
      syncDrawingPanelQuickEdit(false);
      root.querySelectorAll(".setup-photo-inline-controls").forEach(function (row) {
        row.setAttribute("hidden", "hidden");
      });
      root.querySelectorAll(".setup-spec-actions").forEach(function (row) {
        row.setAttribute("hidden", "hidden");
      });
      root.querySelectorAll(".setup-photo-add-row").forEach(function (row) {
        row.setAttribute("hidden", "hidden");
      });
      root.querySelectorAll(".setup-photo-caption").forEach(function (cap) {
        cap.classList.remove("is-inline-edit");
        cap.removeAttribute("contenteditable");
      });
      root.querySelectorAll(".setup-binding-photo-btn").forEach(function (btn) {
        btn.setAttribute("hidden", "hidden");
      });
      document.querySelectorAll(".setup-program-upload-btn").forEach(function (btn) {
        btn.setAttribute("hidden", "hidden");
      });
      root.querySelectorAll(".setup-gcode-value").forEach(function (wrap) {
        var gcodeSpan = wrap.querySelector('[data-field-text="gcode_system"]');
        var sel = wrap.querySelector(".js-inline-gcode-system");
        var pWrap = wrap.querySelector(".js-inline-gcode-p-wrap");
        var pSpan = wrap.querySelector(".js-inline-gcode-p");
        if (gcodeSpan && sel) {
          syncGcodeSpanFromControls(gcodeSpan, sel, pSpan);
          gcodeSpan.removeAttribute("hidden");
        }
        if (sel) sel.setAttribute("hidden", "hidden");
        if (pWrap) pWrap.setAttribute("hidden", "hidden");
        if (pSpan) {
          pSpan.classList.remove("is-inline-edit");
          pSpan.removeAttribute("contenteditable");
        }
      });
      root.querySelectorAll(".product-tab-panel").forEach(function (panel) {
        panel.setAttribute("data-inline-edit-mode", "0");
        setToolsEditMode(panel, false);
        syncPhotoDnDMode(panel, false);
        syncSpecDnDMode(panel, false);
        refreshInlineFieldTitles(panel, false);
      });
      syncDrawingPanelQuickEdit(false);
      syncInlineDeleteSetupBtn();
      window.dispatchEvent(new CustomEvent("setup-inline-edit-mode", { detail: { enabled: false } }));
    }

    forceDisableInlineEdit();

    root.querySelectorAll("[data-product-plan-summary]").forEach(function (wrap) {
      var pt = wrap.querySelector(".js-plan-inline-product-type");
      var wp = wrap.querySelector(".js-plan-inline-workpiece");
      function onPlanInlineChange() {
        syncSetupPlanInlineVisibility(wrap);
      }
      if (pt) pt.addEventListener("change", onPlanInlineChange);
      if (wp) wp.addEventListener("change", onPlanInlineChange);
      syncSetupPlanInlineVisibility(wrap);
    });

    // Инициализация каскадной формы (в #product-detail-meta, вне #product-tabs)
    forEachPlanCascadeForm(function (formContainer) {
      if (formContainer._cascadeFormManager) return;
      if (typeof PlanCascadeFormManager !== "undefined") {
        formContainer._cascadeFormManager = new PlanCascadeFormManager(formContainer);
      }
    });

    root.addEventListener(
      "paste",
      function (e) {
        if (e.target && e.target.classList && e.target.classList.contains("js-inline-gcode-p")) {
          e.preventDefault();
          var clipG = e.clipboardData || window.clipboardData;
          var textG = clipG && clipG.getData ? clipG.getData("text/plain") || "" : "";
          e.target.textContent = (textG || "").replace(/[^0-9]/g, "").slice(0, 2);
          return;
        }
        var td = e.target && e.target.closest ? e.target.closest("table.setup-tools-view td.is-inline-edit[data-tool-col]") : null;
        if (!td) return;
        var col = td.getAttribute("data-tool-col") || "";
        if (col === "tool_type") return;
        e.preventDefault();
        var clip = e.clipboardData || window.clipboardData;
        var text = clip && clip.getData ? clip.getData("text/plain") || "" : "";
        var inserted = false;
        if (typeof document.execCommand === "function") {
          try {
            inserted = document.execCommand("insertText", false, text);
          } catch (err1) {}
        }
        if (!inserted) {
          var sel = window.getSelection();
          if (!sel.rangeCount) return;
          var range = sel.getRangeAt(0);
          range.deleteContents();
          var node = document.createTextNode(text);
          range.insertNode(node);
          range.setStart(node, node.nodeValue.length);
          range.collapse(true);
          sel.removeAllRanges();
          sel.addRange(range);
        }
      },
      true
    );

    root.addEventListener("input", function (e) {
      var t = e.target;
      if (!t || !t.closest) return;
      if (t.classList && t.classList.contains("js-inline-gcode-p")) {
        var dg = (t.textContent || "").replace(/[^0-9]/g, "").slice(0, 2);
        if (t.textContent !== dg) t.textContent = dg;
        return;
      }
    });

    root.addEventListener(
      "keydown",
      function (e) {
        var gPkd = e.target && e.target.classList && e.target.classList.contains("js-inline-gcode-p");
        if (gPkd) {
          if (e.ctrlKey || e.metaKey || e.altKey) return;
          var gk = e.key || "";
          if (
            gk === "Backspace" ||
            gk === "Delete" ||
            gk === "Tab" ||
            gk === "Escape" ||
            gk === "ArrowLeft" ||
            gk === "ArrowRight" ||
            gk === "Home" ||
            gk === "End"
          )
            return;
          if (gk === "Enter") {
            e.preventDefault();
            e.target.blur();
            return;
          }
          if (gk.length === 1 && !/[0-9]/.test(gk)) e.preventDefault();
          return;
        }
      },
      true
    );

    root.addEventListener(
      "focusout",
      function (e) {
        if (!inlineEditMode) return;
        var tdTn = e.target && e.target.closest && e.target.closest('td[data-tool-col="tool_number"].is-inline-edit');
        if (!tdTn) return;
        var trFo = tdTn.closest("tr");
        var tbodyFo = trFo && trFo.parentNode;
        var panelFo = trFo && trFo.closest(".product-tab-panel");
        if (!trFo || !tbodyFo || String(tbodyFo.tagName || "").toUpperCase() !== "TBODY" || !panelFo) return;
        window.setTimeout(function () {
          if (!inlineEditMode) return;
          if (tdTn.contains(document.activeElement)) return;
          sortSetupToolsTbodyByToolNumber(tbodyFo);
          syncRowOrderDisplay(panelFo);
          syncToolOverrideClasses(panelFo);
        }, 0);
      },
      true
    );

    function getInlineSetupIds() {
      var raw = (root.getAttribute("data-inline-setup-ids") || "").trim();
      if (!raw) return [];
      return raw.split(",").map(function (s) { return s.trim(); }).filter(Boolean);
    }

    function appendPlanFieldsToPayload(payload, planWrap) {
      if (!planWrap) return true;

      // Проверить наличие каскадной формы
      var cascadeFormContainer = planWrap.querySelector("[data-plan-cascade-form]");
      if (cascadeFormContainer && cascadeFormContainer._cascadeFormManager) {
        // Использовать новую каскадную форму
        var cascadeManager = cascadeFormContainer._cascadeFormManager;

        // Валидировать форму
        var validation = cascadeManager.validateForm();
        if (!validation.valid) {
          var planMsg =
            validation.errors && validation.errors.length
              ? validation.errors.join("\n")
              : "Заполните поля плана перед сохранением.";
          alert(planMsg);
          return false;
        }

        // Получить payload из менеджера
        var formData = cascadeManager.getFormPayload();

        // Добавить в payload FormData
        payload.append("sync_plan_from_inline", "1");
        payload.append("product_type", formData.product_type || "");
        payload.append("plan_product_type", formData.product_type || "");
        payload.append("workpiece_type", formData.workpiece_type || "");
        payload.append("laser_thickness", formData.laser_thickness || "");
        payload.append("laser_sheet_thickness_mm", formData.laser_thickness || "");
        payload.append("material", formData.material || "");
        payload.append("plan_material", formData.material || "");
        payload.append("workpiece_size", formData.workpiece_size || "");
        payload.append("workpiece_type_enum", formData.workpiece_type_enum || "");

        return true;
      }

      // Fallback на старый способ для совместимости
      var planTypeEl = planWrap ? planWrap.querySelector(".js-plan-inline-product-type") : null;
      if (!planWrap || !planTypeEl) return true;
      var ptype = (planTypeEl.value || "made").trim();
      var wpSel = planWrap.querySelector(".js-plan-inline-workpiece");
      var wpVal = wpSel ? (wpSel.value || "").trim() : "";
      /* Без типа заготовки для «Изделие» сервер отклонит sync_plan; сохраняем только наладку, план не трогаем. */
      if (ptype === "made" && !wpVal) {
        return true;
      }
      payload.append("sync_plan_from_inline", "1");
      payload.append("plan_product_type", ptype);
      payload.append("workpiece_type", wpVal);
      var thickIn = planWrap.querySelector(".js-plan-inline-laser-thick");
      payload.append("laser_sheet_thickness_mm", thickIn ? (thickIn.value || "").trim() : "");
      var matIn = planWrap.querySelector(".js-plan-inline-material");
      var matVal = matIn ? (matIn.value || "").trim() : "";
      payload.append("plan_material", matVal);
      payload.append("made_material", matVal);
      payload.append("laser_material_marking", matVal);
      return true;
    }

    function fillBindingSpecBoxFromData(box, blk) {
      if (!box || !blk) return;
      function setField(attr, val) {
        var el = box.querySelector('[data-field-text="' + attr + '"]');
        var s = val != null ? String(val).trim() : "";
        if (el) el.textContent = s ? s : "—";
      }
      setField("binding_x", blk.binding_x);
      setField("binding_y", blk.binding_y);
      setField("binding_z", blk.binding_z);
      var gcodeStr = (blk.gcode_system && String(blk.gcode_system).trim()) || "G54";
      var gWrap = box.querySelector(".setup-gcode-value");
      var gspan = gWrap ? gWrap.querySelector('[data-field-text="gcode_system"]') : null;
      var gSel = gWrap ? gWrap.querySelector(".js-inline-gcode-system") : null;
      var pW = gWrap ? gWrap.querySelector(".js-inline-gcode-p-wrap") : null;
      var pS = gWrap ? gWrap.querySelector(".js-inline-gcode-p") : null;
      if (gspan) gspan.textContent = gcodeStr;
      if (gspan && gSel && pW && pS) {
        syncGcodeControlsFromSpan(gspan, gSel, pW, pS);
      }
      var setupCaption = "";
      var activeBtn = root.querySelector(".product-tab.is-active");
      if (activeBtn) setupCaption = activeBtn.getAttribute("data-setup-name") || "";
      ["binding_x_photo", "binding_y_photo", "binding_z_photo"].forEach(function (fieldName) {
        if (blk[fieldName]) applyBindingPhotoUrlToBox(box, fieldName, blk[fieldName], setupCaption);
      });
    }

    function rebuildBindingExtraBoxesFromResponse(panelSetup, setupPayload) {
      if (!panelSetup || !setupPayload) return;
      var stack = panelSetup.querySelector(".setup-spec-stack");
      if (!stack) return;
      var extras = setupPayload.binding_extra_blocks;
      stack.querySelectorAll(".setup-spec-box-extra").forEach(function (n) {
        if (n && n.remove) n.remove();
      });
      if (!extras || !extras.length) {
        syncSpecDnDMode(panelSetup, document.body.classList.contains("setup-inline-edit-enabled"));
        return;
      }
      var mainBox = stack.querySelector(".setup-spec-box:not(.setup-spec-box-extra)");
      if (!mainBox) return;
      var inlineOn = document.body.classList.contains("setup-inline-edit-enabled");
      extras.forEach(function (blk) {
        var node = buildExtraSpecBoxFromSource(mainBox, true);
        if (!node) return;
        fillBindingSpecBoxFromData(node, blk);
        var gWrap = node.querySelector(".setup-gcode-value");
        var gspan = gWrap ? gWrap.querySelector('[data-field-text="gcode_system"]') : null;
        var gSel = gWrap ? gWrap.querySelector(".js-inline-gcode-system") : null;
        var pW = gWrap ? gWrap.querySelector(".js-inline-gcode-p-wrap") : null;
        var pS = gWrap ? gWrap.querySelector(".js-inline-gcode-p") : null;
        if (gspan && gSel && pW && pS) {
          if (inlineOn) {
            gspan.setAttribute("hidden", "hidden");
            gSel.removeAttribute("hidden");
            setGcodePWrapVisibilityFromSelect(gSel);
          } else {
            syncGcodeSpanFromControls(gspan, gSel, pS);
            gspan.removeAttribute("hidden");
            gSel.setAttribute("hidden", "hidden");
            pW.setAttribute("hidden", "hidden");
            if (pS) {
              pS.classList.remove("is-inline-edit");
              pS.removeAttribute("contenteditable");
            }
          }
        }
        stack.appendChild(node);
      });
      reindexExtraBindingBlocks(stack);
      syncSpecDnDMode(panelSetup, inlineOn);
      if (inlineOn) syncBindingPhotoButtonsInPanel(panelSetup, true);
    }

    function applyProductMetaToDom(productData) {
      if (!productData) return;
      if (Object.prototype.hasOwnProperty.call(productData, "name")) {
        var nameVal = (productData.name || "").trim();
        (detailGrid || root).querySelectorAll('[data-field-text="product_name"]').forEach(function (el) {
          el.textContent = nameVal || "—";
        });
        var sideName = document.getElementById("product-side-name");
        if (sideName) sideName.textContent = nameVal || "—";
      }
      if (Object.prototype.hasOwnProperty.call(productData, "description")) {
        var descEl = (detailGrid || root).querySelector('[data-field-text="product_description"]');
        if (descEl) {
          var emptyLabel = (descEl.getAttribute("data-empty-label") || "Описание не задано.").trim();
          var descVal = (productData.description || "").trim();
          descEl.innerHTML = descVal || emptyLabel;
        }
      }
    }

    function applyInlineUpdateResponseToDom(setupId, data) {
      if (!data || !data.setup) return;
      if (data.product) applyProductMetaToDom(data.product);
      if (data.product_drawing) {
        var pd = data.product_drawing;
        var pds = root.querySelector("#plan-product-drawing-blank-size");
        var pdt = root.querySelector("#plan-product-drawing-blank-type");
        if (pds && Object.prototype.hasOwnProperty.call(pd, "drawing_blank_size")) {
          pds.textContent = pd.drawing_blank_size || "—";
        }
        if (pdt && Object.prototype.hasOwnProperty.call(pd, "drawing_blank_type")) {
          pdt.textContent = pd.drawing_blank_type || "—";
        }
      }
      var scopes = [];
      var pSetup = root.querySelector("#panel-setup-" + setupId);
      if (pSetup) scopes.push(pSetup);
      scopes.forEach(function (panel) {
        panel.querySelectorAll("[data-field-text]").forEach(function (node) {
          if (node.closest(".setup-spec-box-extra")) return;
          var k = node.getAttribute("data-field-text");
          if (!k || !Object.prototype.hasOwnProperty.call(data.setup, k)) return;
          var val = data.setup[k];
          if (k === "setup_notes") {
            node.innerHTML = val ? val : "Наладка не заполнена.";
            if (val) normalizeSetupNotesImages(node);
          } else if (k === "gcode_system") {
            node.textContent = val || "G54";
            var gWrap = node.closest(".setup-gcode-value");
            if (gWrap) {
              var gSel = gWrap.querySelector(".js-inline-gcode-system");
              var pW = gWrap.querySelector(".js-inline-gcode-p-wrap");
              var pS = gWrap.querySelector(".js-inline-gcode-p");
              if (gSel && pW && pS) syncGcodeControlsFromSpan(node, gSel, pW, pS);
              if (gSel && document.body.classList.contains("setup-inline-edit-enabled")) {
                setGcodePWrapVisibilityFromSelect(gSel);
              }
            }
          } else if (k === "name") {
            node.textContent = val || "";
          } else {
            node.textContent = val || "—";
          }
        });
        refreshInlineFieldTitles(panel, false);
        rebuildBindingExtraBoxesFromResponse(panel, data.setup);
      });
    }

    function updateSetupTabLabelFromResponse(setupTab, data) {
      if (!setupTab || !data || !data.setup) return;
      var tabName = setupTab.getAttribute("data-tab") || "";
      var setupIndex = setupTab.getAttribute("data-setup-index") || "";
      var setupName = (data.setup.name ? data.setup.name : "").trim();
      if (setupName) {
        setupTab.setAttribute("data-setup-name", setupName);
        if (setupIndex) setupTab.textContent = "Уст. " + setupIndex;
        var setupOption = document.querySelector('#setup-tab-select option[value="' + tabName + '"]');
        if (setupOption) {
          setupOption.textContent = setupIndex ? ("Уст. " + setupIndex + " — " + setupName) : setupName;
        }
      }
    }

    function appendProductMetaFields(payload) {
      var pnameEl = (detailGrid || root).querySelector('[data-field-text="product_name"]');
      if (pnameEl) payload.append("product_name", (pnameEl.textContent || "").replace(/\s+/g, " ").trim());
      var pdescEl = (detailGrid || root).querySelector('[data-field-text="product_description"]');
      if (pdescEl) {
        var emptyLabel = (pdescEl.getAttribute("data-empty-label") || "Описание не задано.").trim();
        var descText = (pdescEl.textContent || "").replace(/\s+/g, " ").trim();
        var descHtml = (pdescEl.innerHTML || "").trim();
        payload.append(
          "product_description",
          !descText || descText === emptyLabel ? "" : descHtml
        );
      }
    }

    function buildInlineSetupPayload(setupId, panelSetup, saveOpts) {
      if (typeof saveOpts === "boolean") {
        saveOpts = { productMeta: saveOpts, planSync: saveOpts };
      }
      saveOpts = saveOpts || {};
      var productMeta = !!saveOpts.productMeta;
      var planSync = !!saveOpts.planSync;
      var payload = new FormData();
      payload.append("action", "inline_update_setup");
      payload.append("setup_id", setupId);
      var pdsEl = root.querySelector("#plan-product-drawing-blank-size");
      var pdtEl = root.querySelector("#plan-product-drawing-blank-type");
      if (pdsEl) {
        var s = (pdsEl.textContent || "").replace(/\s+/g, " ").trim();
        payload.append("drawing_blank_size", s === "—" ? "" : s);
      }
      if (pdtEl) {
        var tt = (pdtEl.textContent || "").replace(/\s+/g, " ").trim();
        payload.append("drawing_blank_type", tt === "—" ? "" : tt);
      }
      if (panelSetup) {
        ["workpiece", "size", "material"].forEach(function (name) {
          var el = panelSetup.querySelector('[data-field-text="' + name + '"]');
          var txt = el ? (el.textContent || "").trim() : "";
          payload.append(name, txt === "—" ? "" : txt);
        });
        var nameEl = panelSetup.querySelector('[data-field-text="name"]');
        var nameTxt = nameEl ? (nameEl.textContent || "").trim() : "";
        payload.append("name", nameTxt);
        var bindingBlocks = collectBindingSpecBlocksFromStack(panelSetup);
        var first = bindingBlocks.length
          ? bindingBlocks[0]
          : { binding_x: "", binding_y: "", binding_z: "", gcode_system: "G54" };
        payload.append("binding_x", first.binding_x || "");
        payload.append("binding_y", first.binding_y || "");
        payload.append("binding_z", first.binding_z || "");
        payload.append("gcode_system", first.gcode_system || "G54");
        var extras = bindingBlocks.length > 1 ? bindingBlocks.slice(1) : [];
        payload.append("binding_extra_blocks_json", JSON.stringify(extras));
        var notesEl = panelSetup.querySelector('[data-field-text="setup_notes"]');
        var notesText = notesEl ? (notesEl.innerHTML || "").trim() : "";
        payload.append("setup_notes", notesText === "Наладка не заполнена." ? "" : notesText);
        payload.append("rows_json", JSON.stringify(collectToolsRows(panelSetup)));
      } else {
        payload.append("workpiece", "");
        payload.append("size", "");
        payload.append("material", "");
        payload.append("name", "");
        payload.append("binding_x", "");
        payload.append("binding_y", "");
        payload.append("binding_z", "");
        payload.append("gcode_system", "G54");
        payload.append("binding_extra_blocks_json", "[]");
        payload.append("setup_notes", "");
        payload.append("rows_json", "[]");
      }
      if (productMeta) appendProductMetaFields(payload);
      if (planSync) {
        if (!appendPlanFieldsToPayload(payload, productDetailPlanWrap())) {
          return null;
        }
      }
      return payload;
    }

    async function readJsonInlineSaveResponse(res) {
      var ct = (res.headers.get("content-type") || "").toLowerCase();
      if (ct.indexOf("application/json") === -1) {
        var snippet = "";
        try {
          snippet = (await res.text()).replace(/\s+/g, " ").trim().slice(0, 160);
        } catch (_) {}
        alert(
          "Сервер вернул не JSON (HTTP " +
            res.status +
            "). Обычно это редирект из‑за прав, истекшей сессии или ошибка на сервере — обновите страницу и войдите снова." +
            (snippet ? "\n\nФрагмент ответа:\n" + snippet : "")
        );
        return null;
      }
      var data = null;
      try {
        data = await res.json();
      } catch (e) {
        alert("Не удалось разобрать JSON в ответе сервера. Обновите страницу.");
        return null;
      }
      if (!res.ok || !data || !data.ok) {
        alert((data && data.error) || "Не удалось сохранить (HTTP " + res.status + ").");
        return null;
      }
      return data;
    }

    var deleteSetupBtn = document.getElementById("setup-inline-delete-setup-btn");
    if (deleteSetupBtn) {
      deleteSetupBtn.addEventListener("click", async function () {
        if (!inlineEditMode) return;
        var sel = document.getElementById("setup-tab-select");
        var val = sel ? sel.value : "";
        var m = /^setup-(\d+)$/.exec(val || "");
        if (!m) return;
        if (
          !window.confirm(
            "Удалить эту установку? Все данные вкладки (фото, инструмент, заметки по ней) будут удалены безвозвратно."
          )
        ) {
          return;
        }
        if (!(getCookie("csrftoken") || "").trim()) {
          alert("Не найден CSRF-токен в cookies (csrftoken). Обновите страницу.");
          return;
        }
        var fd = new FormData();
        fd.append("action", "inline_delete_setup");
        fd.append("setup_id", m[1]);
        try {
          var res = await fetch(window.location.href, {
            method: "POST",
            headers: { "X-CSRFToken": getCookie("csrftoken"), "X-Requested-With": "XMLHttpRequest" },
            body: fd,
            credentials: "same-origin",
          });
          var data = await readJsonInlineSaveResponse(res);
          if (!data) return;
          if (!res.ok || !data.ok) {
            alert(data.error || "Не удалось удалить установку.");
            return;
          }
          if (data.redirect) {
            window.location.href = data.redirect;
            return;
          }
          window.location.reload();
        } catch (_err) {
          alert("Ошибка сети при удалении установки.");
        }
      });
    }

    if (editToggleBtn) {
    editToggleBtn.addEventListener(
      "click",
      async function (e) {
      if (!inlineEditMode) {
        toggleInlineEdit();
        return;
      }
      e.preventDefault();
      e.stopImmediatePropagation();
      try {
      if (!(getCookie("csrftoken") || "").trim()) {
        alert("Не найден CSRF-токен в cookies (csrftoken). Обновите страницу или проверьте настройки браузера для этого сайта.");
        return;
      }
      var currentTab = getCurrentTabName();
      if (currentTab === "drawing") {
        var ids = getInlineSetupIds();
        if (!ids.length) {
          alert("Нет установок для сохранения. Если установки должны быть — обновите страницу.");
          return;
        }
        var planSummaryOut = null;
        var planInlineOut = null;
        for (var i = 0; i < ids.length; i++) {
          var sid = ids[i];
          var panelSetup = root.querySelector("#panel-setup-" + sid);
          var payload = buildInlineSetupPayload(sid, panelSetup, {
            productMeta: i === 0,
            planSync: false,
          });
          if (!payload) return;
          var res = await fetch(window.location.href, {
            method: "POST",
            headers: {
              "X-CSRFToken": getCookie("csrftoken"),
              "X-Requested-With": "XMLHttpRequest",
            },
            body: payload,
            credentials: "same-origin",
          });
          var data = await readJsonInlineSaveResponse(res);
          if (!data) return;
          try {
            applyInlineUpdateResponseToDom(sid, data);
          } catch (domErr) {
            console.error(domErr);
          }
          var tabEl = root.querySelector("#tab-setup-" + sid);
          if (tabEl) updateSetupTabLabelFromResponse(tabEl, data);
          if (data.plan_summary) planSummaryOut = data.plan_summary;
          if (data.plan_inline_state) planInlineOut = data.plan_inline_state;
        }
        if (planSummaryOut) syncProductPlanSummaryBlocks(planSummaryOut);
        if (planInlineOut) applyPlanInlineStateToQuickEdits(planInlineOut);
        exitInlineEditAfterSave();
        return;
      }

      var tabSlug = getCurrentTabName();
      var panel = root.querySelector('.product-tab-panel[data-panel="' + tabSlug + '"]');
      var slugMatch = (tabSlug || "").match(/^setup-(\d+)$/);
      if (!panel || !slugMatch) {
        alert(
          "Не удалось определить активную установку. В списке «Изделие / Уст. …» выберите нужную установку и снова нажмите «Сохранить изменения».\n(Сейчас в списке: «" +
            (tabSlug || "(пусто)") +
            "».)"
        );
        return;
      }
      var sidOne = slugMatch[1];
      var setupTab = root.querySelector('.product-tab[data-tab="' + tabSlug + '"]');
      var payloadOne = buildInlineSetupPayload(sidOne, panel, {
        productMeta: true,
        planSync: false,
      });
      if (!payloadOne) return;
      var resOne = await fetch(window.location.href, {
        method: "POST",
        headers: {
          "X-CSRFToken": getCookie("csrftoken"),
          "X-Requested-With": "XMLHttpRequest",
        },
        body: payloadOne,
        credentials: "same-origin",
      });
      var dataOne = await readJsonInlineSaveResponse(resOne);
      if (!dataOne) return;
      try {
        applyInlineUpdateResponseToDom(sidOne, dataOne);
        if (setupTab) updateSetupTabLabelFromResponse(setupTab, dataOne);
      } catch (domErr2) {
        console.error(domErr2);
      }
      if (dataOne.plan_summary) syncProductPlanSummaryBlocks(dataOne.plan_summary);
      if (dataOne.plan_inline_state) applyPlanInlineStateToQuickEdits(dataOne.plan_inline_state);
      exitInlineEditAfterSave();
      } catch (e) {
        console.error(e);
        alert("Ошибка при сохранении: " + (e && e.message ? e.message : String(e)));
      }
    },
      true
    );
    }

    (function maybeOpenQuickEditFromUrl() {
      try {
        var params = new URLSearchParams(window.location.search);
        if (params.get("quick_edit") !== "1" || !editToggleBtn || inlineEditMode) return;
        toggleInlineEdit();
        params.delete("quick_edit");
        var qs = params.toString();
        window.history.replaceState({}, "", window.location.pathname + (qs ? "?" + qs : ""));
      } catch (_e) {}
    })();

    root.addEventListener("click", function (e) {
      var el = e.target;
      if (!el) return;
      var noteToggle = el.closest && el.closest(".js-setup-tools-note-toggle");
      if (noteToggle) {
        var wrap = noteToggle.closest(".setup-tools-table-wrap");
        var table = wrap && wrap.querySelector("table.setup-tools-view");
        if (table) {
          var show = !table.classList.contains("setup-tools-show-note");
          table.classList.toggle("setup-tools-show-note", show);
          noteToggle.setAttribute("aria-expanded", show ? "true" : "false");
          var labelShow = noteToggle.getAttribute("data-label-show") || "Показать примечания";
          var labelHide = noteToggle.getAttribute("data-label-hide") || "Скрыть примечания";
          noteToggle.textContent = show ? labelHide : labelShow;
        }
        e.preventDefault();
        return;
      }
      var removeToolRow = el.closest && el.closest(".js-setup-tools-remove-row");
      if (removeToolRow) {
        if (!inlineEditMode) return;
        e.preventDefault();
        var rowRm = removeToolRow.closest("tr");
        var panelRm = removeToolRow.closest(".product-tab-panel");
        var tbodyRm = rowRm && rowRm.parentNode;
        if (!rowRm || !panelRm || !tbodyRm) return;
        if (tbodyRm.querySelectorAll("tr").length <= 1) {
          alert("Нельзя удалить последнюю строку таблицы инструмента.");
          return;
        }
        rowRm.remove();
        syncRowOrderDisplay(panelRm);
        syncToolOverrideClasses(panelRm);
        return;
      }
      var addToolBtn = el.closest && el.closest(".js-setup-tools-add-row");
      if (addToolBtn) {
        if (!inlineEditMode) return;
        var panelAdd = addToolBtn.closest(".product-tab-panel");
        if (panelAdd) appendSetupToolRow(panelAdd);
        return;
      }
      var correctionCell = el.closest ? el.closest('td[data-tool-col="correction_enabled"]') : null;
      if (correctionCell) {
        if (!inlineEditMode) return;
        var enabled = correctionCell.getAttribute("data-correction-enabled") === "1";
        var nextEnabled = !enabled;
        correctionCell.setAttribute("data-correction-enabled", nextEnabled ? "1" : "0");
        var box = correctionCell.querySelector(".setup-tool-correction-box");
        if (box) box.classList.toggle("is-checked", nextEnabled);
        return;
      }
      if (!inlineEditMode) return;
      if (el.closest && el.closest(".product-tab")) {
        forceDisableInlineEdit();
      }
    });

    root.addEventListener("mouseup", function () {
      var panel = activeSetupPanel();
      if (!panel || !inlineEditMode) return;
      var notesEl = panel.querySelector('[data-field-text="setup_notes"]');
      if (!notesEl) return;
      var sel = window.getSelection();
      if (sel && sel.rangeCount && notesEl.contains(sel.anchorNode)) {
        notesSelection = sel.getRangeAt(0).cloneRange();
      }
    });

    root.addEventListener("click", function (e) {
      var addBtn = e.target && e.target.closest ? e.target.closest(".js-setup-spec-add") : null;
      var copyBtn = e.target && e.target.closest ? e.target.closest(".js-setup-spec-copy") : null;
      var removeBtn = e.target && e.target.closest ? e.target.closest(".js-setup-spec-remove") : null;
      if (removeBtn) {
        if (!inlineEditMode) return;
        var boxToRemove = removeBtn.closest(".setup-spec-box");
        var panelForRemove = activeSetupPanel();
        if (!boxToRemove || !panelForRemove) return;
        var stackForRemove = panelForRemove.querySelector(".setup-spec-stack");
        if (!stackForRemove) return;
        var boxes = Array.from(stackForRemove.querySelectorAll(".setup-spec-box:not(.setup-spec-box-header)"));
        if (boxes.length <= 1) {
          alert("Нельзя удалить последний блок.");
          return;
        }
        var stackRemoved = boxToRemove.parentNode;
        boxToRemove.remove();
        if (stackRemoved) reindexExtraBindingBlocks(stackRemoved);
        return;
      }
      if (!addBtn && !copyBtn) return;
      if (!inlineEditMode) return;
      var panel = activeSetupPanel();
      if (!panel) return;
      var stack = panel.querySelector(".setup-spec-stack");
      if (!stack) return;
      var source = null;
      if (copyBtn) {
        source = copyBtn.closest(".setup-spec-box");
      }
      if (!source) {
        source = stack.querySelector(".setup-spec-box:not(.setup-spec-box-extra)");
      }
      if (!source) return;
      if (addBtn) {
        var emptyBox = buildExtraSpecBoxFromSource(source, true);
        if (emptyBox) {
          stack.appendChild(emptyBox);
          reindexExtraBindingBlocks(stack);
          syncSpecDnDMode(panel, true);
          syncBindingPhotoButtonsInPanel(panel, true);
        }
      } else if (copyBtn) {
        var copyBox = buildExtraSpecBoxFromSource(source, false);
        if (copyBox) {
          source.after(copyBox);
          reindexExtraBindingBlocks(stack);
          syncSpecDnDMode(panel, true);
          syncBindingPhotoButtonsInPanel(panel, true);
        }
      }
    });

    function clearSpecDropHints(scope) {
      var base = scope || root;
      base.querySelectorAll(".setup-spec-box.is-drop-target, .setup-spec-box.is-drop-before, .setup-spec-box.is-drop-after").forEach(function (el) {
        el.classList.remove("is-drop-target", "is-drop-before", "is-drop-after");
      });
    }

    function markSpecDropTarget(stack, dragging, clientY) {
      if (!stack || !dragging) return null;
      var boxes = Array.from(stack.querySelectorAll(".setup-spec-box:not(.setup-spec-box-header)")).filter(function (b) { return b !== dragging; });
      if (!boxes.length) return null;
      var target = boxes[boxes.length - 1];
      for (var i = 0; i < boxes.length; i++) {
        var box = boxes[i];
        var rect = box.getBoundingClientRect();
        if (clientY < rect.bottom) {
          target = box;
          break;
        }
      }
      clearSpecDropHints(stack);
      target.classList.add("is-drop-target");
      target.classList.add("is-drop-before");
      stack.__dropTarget = target;
      stack.__dropAfter = false;
      return target;
    }

    var draggedSpecBox = null;
    root.addEventListener("dragstart", function (e) {
      var box = e.target && e.target.closest ? e.target.closest(".setup-spec-stack.is-inline-edit .setup-spec-box[draggable='true']") : null;
      if (!box) return;
      draggedSpecBox = box;
      box.classList.add("is-dragging");
      try {
        e.dataTransfer.effectAllowed = "move";
        e.dataTransfer.setData("text/plain", box.getAttribute("data-spec-box-id") || "spec-box");
      } catch (_) {}
    });
    root.addEventListener("dragend", function (e) {
      var box = draggedSpecBox || (e.target && e.target.closest ? e.target.closest(".setup-spec-box") : null);
      if (box) box.classList.remove("is-dragging");
      draggedSpecBox = null;
      clearSpecDropHints(root);
    });
    root.addEventListener("dragover", function (e) {
      var stack = e.target && e.target.closest ? e.target.closest(".setup-spec-stack.is-inline-edit") : null;
      var dragging = draggedSpecBox || root.querySelector(".setup-spec-stack.is-inline-edit .setup-spec-box.is-dragging");
      if (!stack || !dragging) return;
      e.preventDefault();
      markSpecDropTarget(stack, dragging, e.clientY);
      try { e.dataTransfer.dropEffect = "move"; } catch (_) {}
    });
    root.addEventListener("dragleave", function (e) {
      var stack = e.target && e.target.closest ? e.target.closest(".setup-spec-stack.is-inline-edit") : null;
      if (!stack) return;
      var rel = e.relatedTarget;
      if (!rel || !stack.contains(rel)) clearSpecDropHints(stack);
    });
    root.addEventListener("drop", function (e) {
      var stack = e.target && e.target.closest ? e.target.closest(".setup-spec-stack.is-inline-edit") : null;
      var dragging = draggedSpecBox || root.querySelector(".setup-spec-stack.is-inline-edit .setup-spec-box.is-dragging");
      if (!stack || !dragging) return;
      e.preventDefault();
      var target = stack.__dropTarget || markSpecDropTarget(stack, dragging, e.clientY);
      if (!target || target === dragging) {
        clearSpecDropHints(stack);
        return;
      }
      stack.insertBefore(dragging, target);
      dragging.classList.remove("is-dragging");
      dragging.classList.add("is-drop-commit");
      setTimeout(function () { dragging.classList.remove("is-drop-commit"); }, 280);
      clearSpecDropHints(stack);
      stack.__dropTarget = null;
      stack.__dropAfter = null;
      draggedSpecBox = null;
    });

    root.querySelectorAll(".setup-inline-toolbar-block").forEach(function (tb) {
      tb.querySelectorAll(".js-notes-cmd").forEach(function (btn) {
        btn.addEventListener("click", function () {
          var panel = btn.closest(".product-tab-panel");
          if (!panel) return;
          var notesEl = panel.querySelector('[data-field-text="setup_notes"]');
          if (!notesEl) return;
          notesEl.focus();
          if (notesSelection) {
            var sel = window.getSelection();
            sel.removeAllRanges();
            sel.addRange(notesSelection);
          }
          document.execCommand(btn.getAttribute("data-cmd"), false, null);
        });
      });
      var fontSel = tb.querySelector(".js-notes-fontsize");
      if (fontSel) {
        fontSel.addEventListener("change", function () {
          var panel = fontSel.closest(".product-tab-panel");
          if (!panel) return;
          var notesEl = panel.querySelector('[data-field-text="setup_notes"]');
          if (!notesEl) return;
          notesEl.focus();
          if (notesSelection) {
            var sel = window.getSelection();
            sel.removeAllRanges();
            sel.addRange(notesSelection);
          }
          document.execCommand("fontSize", false, fontSel.value);
        });
      }
    });

    document.addEventListener("click", async function (e) {
      var btnSaveCaption = e.target.closest(".js-setup-photo-save-caption");
      if (btnSaveCaption) {
        var figure = btnSaveCaption.closest(".setup-photo-figure");
        if (!figure) return;
        var photoId = figure.getAttribute("data-photo-id") || "";
        if (!photoId) return;
        var captionEl = figure.querySelector(".setup-photo-caption");
        var caption = captionEl ? (captionEl.textContent || "").trim() : "";
        var fd = new FormData();
        fd.append("action", "inline_update_setup_photo_caption");
        fd.append("photo_id", photoId);
        fd.append("caption", caption);
        var resCap = await fetch(window.location.href, {
          method: "POST",
          headers: { "X-CSRFToken": getCookie("csrftoken"), "X-Requested-With": "XMLHttpRequest" },
          body: fd,
          credentials: "same-origin",
        });
        var dataCap = await resCap.json();
        if (!resCap.ok || !dataCap.ok) {
          alert(dataCap.error || "Не удалось сохранить подпись.");
        }
        return;
      }

      var btnProgFileDel = e.target.closest(".js-setup-program-file-delete");
      if (btnProgFileDel) {
        if (!confirm("Удалить этот файл программы?")) return;
        var sidDel = btnProgFileDel.getAttribute("data-setup-id") || "";
        var pidDel = btnProgFileDel.getAttribute("data-program-file-id") || "";
        if (!sidDel || !pidDel) return;
        var fdProgDel = new FormData();
        fdProgDel.append("action", "inline_delete_setup_program_file");
        fdProgDel.append("setup_id", sidDel);
        fdProgDel.append("program_file_id", pidDel);
        var resProgDel = await fetch(window.location.href, {
          method: "POST",
          headers: { "X-CSRFToken": getCookie("csrftoken"), "X-Requested-With": "XMLHttpRequest" },
          body: fdProgDel,
          credentials: "same-origin",
        });
        var dataProgDel = await resProgDel.json();
        if (!resProgDel.ok || !dataProgDel.ok) {
          alert(dataProgDel.error || "Не удалось удалить файл.");
          return;
        }
        var panelProg = btnProgFileDel.closest(".product-tab-panel");
        renderSetupProgramFilesList(panelProg, sidDel, dataProgDel);
        var tabProg = document.getElementById("tab-setup-" + sidDel);
        if (tabProg) {
          if (dataProgDel.program_url) {
            tabProg.setAttribute("data-program-url", dataProgDel.program_url);
            tabProg.setAttribute("data-program-filename", dataProgDel.program_filename || "");
          } else {
            tabProg.removeAttribute("data-program-url");
            tabProg.removeAttribute("data-program-filename");
          }
        }
        var tabNameNow = (root.querySelector(".product-tab.is-active") || {}).getAttribute("data-tab") || "";
        setProgramDownloadByTab(tabNameNow);
        return;
      }

      var btnDelete = e.target.closest(".js-setup-photo-delete");
      if (btnDelete) {
        var figureDel = btnDelete.closest(".setup-photo-figure");
        if (!figureDel) return;
        var photoIdDel = figureDel.getAttribute("data-photo-id") || "";
        if (!photoIdDel) {
          figureDel.remove();
          return;
        }
        if (!confirm("Удалить блок фото?")) return;
        var fdDel = new FormData();
        fdDel.append("action", "inline_delete_setup_photo");
        fdDel.append("photo_id", photoIdDel);
        var resDel = await fetch(window.location.href, {
          method: "POST",
          headers: { "X-CSRFToken": getCookie("csrftoken"), "X-Requested-With": "XMLHttpRequest" },
          body: fdDel,
          credentials: "same-origin",
        });
        var dataDel = await resDel.json();
        if (!resDel.ok || !dataDel.ok) {
          alert(dataDel.error || "Не удалось удалить.");
          return;
        }
        figureDel.remove();
        return;
      }

      var btnAdd = e.target.closest(".js-add-empty-photo-block");
      if (btnAdd) {
        var setupId = btnAdd.getAttribute("data-setup-id") || "";
        if (!setupId) return;
        var panel = btnAdd.closest(".product-tab-panel");
        if (!panel) return;
        var photosWrap = panel.querySelector(".product-setup-photos");
        if (!photosWrap) {
          photosWrap = document.createElement("div");
          photosWrap.className = "product-setup-photos";
          btnAdd.closest(".setup-photo-add-row").before(photosWrap);
        }
        var draft = document.createElement("figure");
        draft.className = "setup-photo-figure setup-photo-draft";
        draft.innerHTML = '' +
          '<div class="muted" style="width:100%;text-align:center;padding:8px 6px;border:1px dashed var(--bio-filter-border);border-radius:4px;">Новый блок</div>' +
          '<input type="file" class="js-new-photo-file" accept="image/*,.jpg,.jpeg,.png,.webp,.gif" />' +
          '<figcaption class="muted"><input type="text" class="js-new-photo-caption" placeholder="Описание" style="width:100%;"/></figcaption>' +
          '<div class="setup-photo-inline-controls">' +
            '<button type="button" class="btn btn-ghost js-save-new-photo">Сохранить</button>' +
            '<button type="button" class="btn btn-ghost js-setup-photo-delete">×</button>' +
          '</div>';
        photosWrap.appendChild(draft);
        return;
      }

      var btnBindingPhoto = e.target.closest(".setup-binding-photo-btn");
      if (btnBindingPhoto) {
        var setupIdBtn = btnBindingPhoto.getAttribute("data-setup-id") || "";
        var fieldBtn = btnBindingPhoto.getAttribute("data-photo-field") || "";
        if (!setupIdBtn || !fieldBtn) return;
        var localScope = btnBindingPhoto.closest(".setup-spec-box") || btnBindingPhoto.closest(".product-tab-panel") || root;
        var extraIdx = btnBindingPhoto.getAttribute("data-extra-block-index");
        var input = null;
        if (extraIdx != null && extraIdx !== "") {
          input = localScope.querySelector(
            '.setup-binding-photo-input[data-setup-id="' +
              setupIdBtn +
              '"][data-photo-field-input="' +
              fieldBtn +
              '"][data-extra-block-index="' +
              extraIdx +
              '"]'
          );
        } else {
          input = localScope.querySelector(
            '.setup-binding-photo-input[data-setup-id="' + setupIdBtn + '"][data-photo-field-input="' + fieldBtn + '"]:not([data-extra-block-index])'
          );
          if (!input) {
            input = localScope.querySelector(
              '.setup-binding-photo-input[data-setup-id="' + setupIdBtn + '"][data-photo-field-input="' + fieldBtn + '"]'
            );
          }
        }
        if (input) input.click();
      }

      var btnProgramUpload = e.target.closest(".setup-program-upload-btn");
      if (btnProgramUpload) {
        var setupIdProgram = btnProgramUpload.getAttribute("data-setup-id") || "";
        if (!setupIdProgram) return;
        var localProgramScope = btnProgramUpload.closest(".setup-program-files-inline") || btnProgramUpload.closest(".setup-spec-box") || btnProgramUpload.closest(".product-tab-panel") || root;
        var programInput = localProgramScope.querySelector('.setup-program-upload-input[data-setup-program-input="' + setupIdProgram + '"]');
        if (programInput) programInput.click();
        return;
      }

      var btnSaveNew = e.target.closest(".js-save-new-photo");
      if (btnSaveNew) {
        var draftFig = btnSaveNew.closest(".setup-photo-figure");
        if (!draftFig) return;
        var panelDraft = btnSaveNew.closest(".product-tab-panel");
        if (!panelDraft) return;
        var activeTab = root.querySelector(".product-tab.is-active");
        if (!activeTab) return;
        var tabId = activeTab.id || "";
        var m = tabId.match(/tab-setup-(\d+)/);
        if (!m) return;
        var setupIdDraft = m[1];
        var fileInput = draftFig.querySelector(".js-new-photo-file");
        var captionInput = draftFig.querySelector(".js-new-photo-caption");
        var fileObj = fileInput && fileInput.files ? fileInput.files[0] : null;
        if (!fileObj) {
          alert("Выберите фото для нового блока.");
          return;
        }
        var fdNew = new FormData();
        fdNew.append("action", "inline_create_setup_photo");
        fdNew.append("setup_id", setupIdDraft);
        fdNew.append("caption", captionInput ? (captionInput.value || "") : "");
        fdNew.append("image", fileObj);
        var resNew = await fetch(window.location.href, {
          method: "POST",
          headers: { "X-CSRFToken": getCookie("csrftoken"), "X-Requested-With": "XMLHttpRequest" },
          body: fdNew,
          credentials: "same-origin",
        });
        var dataNew = await resNew.json();
        if (!resNew.ok || !dataNew.ok) {
          alert(dataNew.error || "Не удалось добавить блок фото.");
          return;
        }
        var ph = dataNew.photo;
        draftFig.className = "setup-photo-figure";
        draftFig.setAttribute("data-photo-id", String(ph.id));
        draftFig.setAttribute("data-setup-id", String(setupIdDraft));
        draftFig.innerHTML = '' +
          '<a href="' + ph.image_url + '" class="setup-photo-open" data-photo-url="' + ph.image_url + '" data-photo-caption="' + (ph.caption || "") + '">' +
            '<img src="' + ph.image_url + '" alt="' + (ph.caption || "") + '" loading="lazy" />' +
          '</a>' +
          '<figcaption class="muted setup-photo-caption is-inline-edit" data-caption-editable="1" contenteditable="true" spellcheck="true" title="Двойной щелчок — открыть фото">' + (ph.caption || "") + '</figcaption>' +
          '<div class="setup-photo-inline-controls" hidden>' +
            '<button type="button" class="btn btn-ghost js-setup-photo-save-caption" title="Сохранить подпись">Сохранить</button>' +
            '<button type="button" class="btn btn-ghost js-setup-photo-delete" title="Удалить блок">×</button>' +
          '</div>';
        if (inlineEditMode) {
          draftFig.setAttribute("draggable", "true");
        }
      }
    });

    function escapeHtmlAttr(s) {
      return String(s || "")
        .replace(/&/g, "&amp;")
        .replace(/"/g, "&quot;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;");
    }

    function escapeHtml(s) {
      return String(s || "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;");
    }

    function normalizeSetupNotesImages(el) {
      if (!el || !el.querySelectorAll) return;
      el.querySelectorAll("img").forEach(function (img) {
        var src = (img.getAttribute("src") || "").trim();
        if (!src) {
          img.remove();
          return;
        }
        var alt = (img.getAttribute("alt") || "").trim();
        var label = alt || "Фото";
        var a = document.createElement("a");
        a.href = src;
        a.className = "setup-notes-photo-ref setup-photo-open";
        a.setAttribute("data-photo-url", src);
        a.setAttribute("data-photo-caption", label);
        a.title = "Открыть изображение";
        a.textContent = label;
        var parent = img.parentNode;
        img.replaceWith(a);
        if (parent && parent.tagName === "P") {
          parent.classList.add("setup-notes-photo-ref-wrap");
        } else if (parent) {
          var wrap = document.createElement("p");
          wrap.className = "setup-notes-photo-ref-wrap";
          parent.insertBefore(wrap, a);
          wrap.appendChild(a);
        }
      });
    }

    var draggedPhotoFigure = null;
    root.addEventListener("click", function (e) {
      var cap = e.target && e.target.closest ? e.target.closest(".setup-photo-caption") : null;
      if (!cap) return;
      if (e.target.closest && e.target.closest(".setup-photo-inline-controls")) return;
      if (cap.isContentEditable) return;
      var fig = cap.closest(".setup-photo-figure");
      if (!fig) return;
      var link = fig.querySelector("a.setup-photo-open");
      if (!link) return;
      e.preventDefault();
      e.stopPropagation();
      link.click();
    });
    root.addEventListener("dblclick", function (e) {
      var cap = e.target && e.target.closest ? e.target.closest(".setup-photo-caption") : null;
      if (!cap || !cap.isContentEditable) return;
      if (e.target.closest && e.target.closest(".setup-photo-inline-controls")) return;
      var fig = cap.closest(".setup-photo-figure");
      if (!fig) return;
      var link = fig.querySelector("a.setup-photo-open");
      if (!link) return;
      e.preventDefault();
      e.stopPropagation();
      link.click();
    });

    root.addEventListener("dragstart", function (e) {
      var figure = e.target && e.target.closest ? e.target.closest(".setup-photo-figure[draggable='true']") : null;
      if (!figure || !inlineEditMode) return;
      draggedPhotoFigure = figure;
      figure.classList.add("is-dragging");
      if (e.dataTransfer) {
        e.dataTransfer.effectAllowed = "copyMove";
        e.dataTransfer.setData("text/plain", figure.getAttribute("data-photo-id") || "");
      }
    });

    root.addEventListener("dragover", function (e) {
      if (!draggedPhotoFigure || !inlineEditMode) return;
      var notesEl = e.target && e.target.closest ? e.target.closest(".product-setup-notes.is-inline-edit") : null;
      if (notesEl) {
        var pNotes = notesEl.closest(".product-tab-panel");
        var pFig = draggedPhotoFigure.closest(".product-tab-panel");
        if (pNotes && pFig && pNotes === pFig) {
          e.preventDefault();
          if (e.dataTransfer) e.dataTransfer.dropEffect = "copy";
          notesEl.classList.add("is-photo-drop-target");
          root.querySelectorAll(".product-setup-notes.is-photo-drop-target").forEach(function (n) {
            if (n !== notesEl) n.classList.remove("is-photo-drop-target");
          });
          root.querySelectorAll(".setup-photo-figure.is-drop-target").forEach(function (f) {
            f.classList.remove("is-drop-target");
          });
          return;
        }
      }
      root.querySelectorAll(".product-setup-notes.is-photo-drop-target").forEach(function (n) {
        n.classList.remove("is-photo-drop-target");
      });
      var target = e.target && e.target.closest ? e.target.closest(".setup-photo-figure[draggable='true']") : null;
      if (!draggedPhotoFigure || !target || target === draggedPhotoFigure) return;
      e.preventDefault();
      if (e.dataTransfer) e.dataTransfer.dropEffect = "move";
      var wrap = target.closest(".product-setup-photos");
      if (wrap) {
        wrap.querySelectorAll(".setup-photo-figure.is-drop-target").forEach(function (el) {
          if (el !== target) el.classList.remove("is-drop-target");
        });
      }
      target.classList.add("is-drop-target");
    });

    root.addEventListener("dragleave", function (e) {
      var notesLeave = e.target && e.target.closest ? e.target.closest(".product-setup-notes.is-photo-drop-target") : null;
      if (notesLeave && (!e.relatedTarget || !notesLeave.contains(e.relatedTarget))) {
        notesLeave.classList.remove("is-photo-drop-target");
      }
      var target = e.target && e.target.closest ? e.target.closest(".setup-photo-figure.is-drop-target") : null;
      if (target) target.classList.remove("is-drop-target");
    });

    root.addEventListener("drop", async function (e) {
      var notesEl = e.target && e.target.closest ? e.target.closest(".product-setup-notes.is-inline-edit") : null;
      if (notesEl && draggedPhotoFigure && inlineEditMode) {
        var pNotes = notesEl.closest(".product-tab-panel");
        var pFig = draggedPhotoFigure.closest(".product-tab-panel");
        if (pNotes && pFig && pNotes === pFig) {
          e.preventDefault();
          notesEl.classList.remove("is-photo-drop-target");
          var link = draggedPhotoFigure.querySelector("a.setup-photo-open");
          var imgUrl = link ? (link.getAttribute("data-photo-url") || link.getAttribute("href") || "") : "";
          var capEl = draggedPhotoFigure.querySelector(".setup-photo-caption");
          var alt = capEl ? (capEl.textContent || "").trim() : "";
          if (imgUrl) {
            notesEl.focus();
            var capLabel = alt || "Фото";
            var html =
              '<p class="setup-notes-photo-ref-wrap">' +
              '<a href="' +
              escapeHtmlAttr(imgUrl) +
              '" class="setup-notes-photo-ref setup-photo-open" data-photo-url="' +
              escapeHtmlAttr(imgUrl) +
              '" data-photo-caption="' +
              escapeHtmlAttr(capLabel) +
              '" title="Открыть изображение">' +
              escapeHtml(capLabel) +
              "</a></p>";
            var ok = false;
            if (typeof document.execCommand === "function") {
              try {
                ok = document.execCommand("insertHTML", false, html);
              } catch (errIns) {}
            }
            if (!ok) {
              notesEl.insertAdjacentHTML("beforeend", html);
            }
          }
          draggedPhotoFigure.classList.remove("is-dragging");
          draggedPhotoFigure = null;
          return;
        }
      }
      var target = e.target && e.target.closest ? e.target.closest(".setup-photo-figure[draggable='true']") : null;
      if (!draggedPhotoFigure || !target || target === draggedPhotoFigure) return;
      e.preventDefault();
      var photosWrap = target.closest(".product-setup-photos");
      var setupId = target.getAttribute("data-setup-id") || draggedPhotoFigure.getAttribute("data-setup-id") || "";
      if (!photosWrap || !setupId) return;
      var movedFig = draggedPhotoFigure;
      photosWrap.insertBefore(movedFig, target);
      photosWrap.querySelectorAll(".is-drop-target").forEach(function (el) {
        el.classList.remove("is-drop-target");
      });
      movedFig.classList.remove("is-dragging");
      movedFig.classList.add("is-drop-commit");
      setTimeout(function () {
        movedFig.classList.remove("is-drop-commit");
      }, 280);
      await persistSetupPhotosOrder(photosWrap, setupId);
    });

    root.addEventListener("dragend", function () {
      root.querySelectorAll(".product-setup-notes.is-photo-drop-target").forEach(function (n) {
        n.classList.remove("is-photo-drop-target");
      });
      root.querySelectorAll(".setup-photo-figure.is-dragging, .setup-photo-figure.is-drop-target").forEach(function (figure) {
        figure.classList.remove("is-dragging", "is-drop-target");
      });
      draggedPhotoFigure = null;
    });

    async function handleBindingPhotoInputChange(input) {
        var file = input.files && input.files[0];
        if (!file) return;
        var setupId = input.getAttribute("data-setup-id") || "";
        var fieldName = input.getAttribute("data-photo-field-input") || "";
        if (!setupId || !fieldName) return;
        var fd = new FormData();
        fd.append("action", "inline_replace_binding_photo");
        fd.append("setup_id", setupId);
        fd.append("field_name", fieldName);
        var extraIdx = input.getAttribute("data-extra-block-index");
        if (extraIdx != null && extraIdx !== "") {
          fd.append("extra_block_index", extraIdx);
        }
        fd.append("image", file);
        var res = await fetch(window.location.href, {
          method: "POST",
          headers: { "X-CSRFToken": getCookie("csrftoken"), "X-Requested-With": "XMLHttpRequest" },
          body: fd,
          credentials: "same-origin",
        });
        var data = await res.json();
        if (!res.ok || !data.ok) {
          alert(data.error || "Не удалось обновить фото.");
          input.value = "";
          return;
        }
        var box = input.closest(".setup-spec-box");
        var setupName = "";
        var activeBtn = root.querySelector(".product-tab.is-active");
        if (activeBtn) setupName = activeBtn.getAttribute("data-setup-name") || "";
        if (box) applyBindingPhotoUrlToBox(box, fieldName, data.url, setupName);
        input.value = "";
    }

    function renderSetupProgramFilesList(panel, setupId, data) {
      if (!data || !setupId) return;
      var wraps = document.querySelectorAll('.setup-program-files-inline[data-setup-id="' + setupId + '"]');
      if (!wraps.length) return;
      var editMode =
        !!(panel && panel.getAttribute("data-inline-edit-mode") === "1") ||
        !!root.querySelector('.product-tab-panel[data-inline-edit-mode="1"]') ||
        document.body.classList.contains("setup-inline-edit-enabled");
      var files = data.program_files || [];
      wraps.forEach(function (wrap) {
        var ul = wrap.querySelector(".setup-program-files-list");
        if (!ul) return;
        var isSide = wrap.classList.contains("product-side-program-files");
        ul.textContent = "";
        if (!files.length) {
          /* пустой список — текст в .setup-program-tab-empty-msg */
        } else {
          files.forEach(function (f) {
            var li = document.createElement("li");
            li.className = "setup-program-file-item" + (isSide ? " setup-program-file-item-side" : "");
            li.setAttribute("data-program-file-id", String(f.id));
            var a = document.createElement("a");
            a.href = f.url || "#";
            a.setAttribute("download", "");
            a.className = isSide ? "btn product-btn-program setup-side-program-download" : "setup-program-file-link";
            a.textContent = f.name || "";
            li.appendChild(a);
            if (editMode) {
              var del = document.createElement("button");
              del.type = "button";
              del.className = "btn btn-ghost setup-program-file-delete js-setup-program-file-delete";
              del.setAttribute("data-program-file-id", String(f.id));
              del.setAttribute("data-setup-id", String(setupId));
              del.title = "Удалить файл";
              del.setAttribute("aria-label", "Удалить файл программы");
              del.innerHTML = '<i class="fi fi-br-cross ui-icon" aria-hidden="true"></i>';
              li.appendChild(del);
            }
            ul.appendChild(li);
          });
        }
      });
      var emptyMsg = document.querySelector(
        '.product-side-program-files[data-setup-id="' + setupId + '"] .setup-program-tab-empty-msg'
      );
      if (emptyMsg) emptyMsg.hidden = files.length > 0;
    }

    async function uploadSetupProgramFile(setupId, file, panelHint) {
        if (!file || !setupId) return;
        var fd = new FormData();
        fd.append("action", "inline_replace_setup_program");
        fd.append("setup_id", setupId);
        fd.append("program_file", file);
        var res = await fetch(window.location.href, {
          method: "POST",
          headers: { "X-CSRFToken": getCookie("csrftoken"), "X-Requested-With": "XMLHttpRequest" },
          body: fd,
          credentials: "same-origin",
        });
        var data = await res.json();
        if (!res.ok || !data.ok) {
          alert(data.error || "Не удалось загрузить программу.");
          return;
        }
        var panel = panelHint || null;
        renderSetupProgramFilesList(panel, setupId, data);
        var tabBtn = document.getElementById("tab-setup-" + setupId) || root.querySelector(".product-tab.is-active");
        if (tabBtn) {
          tabBtn.setAttribute("data-program-url", data.program_url || "");
          tabBtn.setAttribute("data-program-filename", data.program_filename || file.name || "");
        }
        var tabNameNow = (root.querySelector(".product-tab.is-active") || {}).getAttribute("data-tab") || "";
        setProgramDownloadByTab(tabNameNow);
    }

    async function handleProgramUploadInputChange(input) {
        var file = input.files && input.files[0];
        if (!file) return;
        var setupId = input.getAttribute("data-setup-program-input") || "";
        if (!setupId) return;
        var panel = input.closest(".product-tab-panel");
        if (!panel) {
          var activeTabBtn = root.querySelector(".product-tab.is-active");
          var tabSlug = activeTabBtn ? activeTabBtn.getAttribute("data-tab") : "";
          if (tabSlug) panel = root.querySelector('.product-tab-panel[data-panel="' + tabSlug + '"]');
        }
        await uploadSetupProgramFile(setupId, file, panel);
        input.value = "";
    }

    document.addEventListener("change", function (e) {
      var input = e.target;
      if (!input || !input.classList) return;
      if (input.classList.contains("setup-binding-photo-input")) {
        handleBindingPhotoInputChange(input);
        return;
      }
      if (input.classList.contains("js-inline-gcode-system")) {
        setGcodePWrapVisibilityFromSelect(input);
        return;
      }
      if (input.classList.contains("setup-program-upload-input")) {
        handleProgramUploadInputChange(input);
      }
    });
    document.addEventListener("dragover", function (e) {
      var row = e.target && e.target.closest ? e.target.closest(".setup-program-meta-row") : null;
      if (!row) return;
      if (!e.dataTransfer || !e.dataTransfer.files || !e.dataTransfer.files.length) return;
      e.preventDefault();
      row.classList.add("is-file-drop-target");
      try { e.dataTransfer.dropEffect = "copy"; } catch (_) {}
    });
    document.addEventListener("dragleave", function (e) {
      var row = e.target && e.target.closest ? e.target.closest(".setup-program-meta-row.is-file-drop-target") : null;
      if (!row) return;
      row.classList.remove("is-file-drop-target");
    });
    document.addEventListener("drop", async function (e) {
      var row = e.target && e.target.closest ? e.target.closest(".setup-program-meta-row") : null;
      if (!row) return;
      if (!e.dataTransfer || !e.dataTransfer.files || !e.dataTransfer.files.length) return;
      e.preventDefault();
      row.classList.remove("is-file-drop-target");
      var wrap = row.closest(".setup-program-files-inline");
      if (!wrap) return;
      var setupId = wrap.getAttribute("data-setup-id") || "";
      if (!setupId) return;
      var file = e.dataTransfer.files[0];
      if (!file) return;
      var panelHint = wrap.closest(".product-tab-panel");
      await uploadSetupProgramFile(setupId, file, panelHint);
    });

    root.querySelectorAll('[data-field-text="setup_notes"]').forEach(function (n) {
      normalizeSetupNotesImages(n);
    });

    // Панель форматирования описания (contenteditable)
    (function initDescriptionFormatting() {
      var meta = productDetailMetaEl();
      if (!meta) return;
      var descriptionArea = meta.querySelector(".product-drawing-description[data-field-text='product_description']");
      if (!descriptionArea) return;

      var savedDescRange = null;
      var INLINE_FMT = { bold: "strong", italic: "em", underline: "u" };
      var INLINE_FMT_TAGS = {
        bold: ["STRONG", "B"],
        italic: ["EM", "I"],
        underline: ["U"],
      };
      var toolbar = meta.querySelector(".description-toolbar");

      function isDescEditing() {
        return (
          document.body.classList.contains("setup-inline-edit-enabled") &&
          meta.getAttribute("data-inline-edit-mode") === "1" &&
          descriptionArea.isContentEditable
        );
      }

      function selectionInDescription() {
        var sel = window.getSelection();
        if (!sel || !sel.rangeCount) return false;
        return descriptionArea.contains(sel.anchorNode);
      }

      function selectionHasInlineFmt(cmd) {
        var tags = INLINE_FMT_TAGS[cmd];
        if (!tags) return false;
        var sel = window.getSelection();
        if (!sel || !sel.rangeCount) return false;
        var node = sel.anchorNode;
        if (!node || !descriptionArea.contains(node)) return false;
        if (node.nodeType === Node.TEXT_NODE) node = node.parentNode;
        while (node && node !== descriptionArea) {
          if (node.nodeType === Node.ELEMENT_NODE && tags.indexOf((node.tagName || "").toUpperCase()) >= 0) {
            return true;
          }
          node = node.parentNode;
        }
        return false;
      }

      function queryAlignActive(cmd) {
        var sel = window.getSelection();
        if (!sel || !sel.rangeCount) return false;
        var block = findAlignBlock(sel.getRangeAt(0));
        var expected = cmd === "justifyLeft" ? "left" : cmd === "justifyCenter" ? "center" : "right";
        var attr = block.getAttribute ? block.getAttribute("data-desc-align") : "";
        if (attr) {
          if (cmd === "justifyLeft") return attr === "left";
          return attr === expected;
        }
        var ta = (block.style.textAlign || window.getComputedStyle(block).textAlign || "left").toLowerCase();
        if (cmd === "justifyLeft") return ta === "left" || ta === "start";
        return ta === expected;
      }

      function queryFmtActive(cmd) {
        if (!selectionInDescription()) return false;
        if (cmd === "justifyLeft" || cmd === "justifyCenter" || cmd === "justifyRight") {
          return queryAlignActive(cmd);
        }
        var sel = window.getSelection();
        if (!sel || !sel.rangeCount) return false;
        if (sel.getRangeAt(0).collapsed) {
          return selectionHasInlineFmt(cmd);
        }
        try {
          return document.queryCommandState(cmd);
        } catch (errState) {
          return selectionHasInlineFmt(cmd);
        }
      }

      function unwrapElement(el) {
        var parent = el.parentNode;
        if (!parent) return;
        while (el.firstChild) parent.insertBefore(el.firstChild, el);
        parent.removeChild(el);
      }

      function unwrapInlineFmt(cmd) {
        var tags = INLINE_FMT_TAGS[cmd];
        if (!tags) return;
        var range = getActiveRange();
        if (!range) return;
        var selector = tags.map(function (t) {
          return t.toLowerCase();
        }).join(",");

        if (range.collapsed) {
          var node = range.startContainer;
          if (node.nodeType === Node.TEXT_NODE) node = node.parentNode;
          while (node && node !== descriptionArea) {
            if (node.nodeType === Node.ELEMENT_NODE && tags.indexOf((node.tagName || "").toUpperCase()) >= 0) {
              unwrapElement(node);
              return;
            }
            node = node.parentNode;
          }
          return;
        }

        var matches = Array.prototype.slice.call(descriptionArea.querySelectorAll(selector));
        matches = matches.filter(function (el) {
          try {
            return range.intersectsNode(el);
          } catch (errIntersect) {
            var elRange = document.createRange();
            elRange.selectNodeContents(el);
            return (
              range.compareBoundaryPoints(Range.END_TO_START, elRange) < 0 &&
              range.compareBoundaryPoints(Range.START_TO_END, elRange) > 0
            );
          }
        });
        matches.sort(function (a, b) {
          if (a.contains(b)) return 1;
          if (b.contains(a)) return -1;
          return 0;
        });
        matches.forEach(unwrapElement);
      }

      function syncDescToolbarState() {
        if (!toolbar) return;
        var buttons = toolbar.querySelectorAll(".desc-format-btn[data-cmd]");
        if (!isDescEditing() || !selectionInDescription()) {
          buttons.forEach(function (btn) {
            btn.classList.remove("is-active");
          });
          return;
        }
        descriptionArea.focus({ preventScroll: true });
        buttons.forEach(function (btn) {
          var cmd = btn.getAttribute("data-cmd") || "";
          var active = false;
          if (INLINE_FMT[cmd]) {
            active = queryFmtActive(cmd);
          } else if (cmd === "justifyLeft" || cmd === "justifyCenter" || cmd === "justifyRight") {
            active = queryAlignActive(cmd);
          } else if (cmd === "insertUnorderedList" || cmd === "insertOrderedList") {
            try {
              active = document.queryCommandState(cmd);
            } catch (errList) { /* ignore */ }
          }
          btn.classList.toggle("is-active", !!active);
        });
      }

      function captureDescRange() {
        if (!isDescEditing()) return;
        var sel = window.getSelection();
        if (!sel || !sel.rangeCount) return;
        var range = sel.getRangeAt(0);
        if (!descriptionArea.contains(range.commonAncestorContainer)) return;
        savedDescRange = range.cloneRange();
        syncDescToolbarState();
      }

      function restoreDescRange() {
        descriptionArea.focus({ preventScroll: true });
        var sel = window.getSelection();
        if (!sel) return;
        sel.removeAllRanges();
        if (savedDescRange) {
          try {
            sel.addRange(savedDescRange);
            return;
          } catch (err) { /* fall through */ }
        }
        var range = document.createRange();
        range.selectNodeContents(descriptionArea);
        range.collapse(false);
        sel.addRange(range);
      }

      function getActiveRange() {
        restoreDescRange();
        var sel = window.getSelection();
        if (!sel || !sel.rangeCount) return null;
        var range = sel.getRangeAt(0);
        if (!descriptionArea.contains(range.commonAncestorContainer)) return null;
        return range;
      }

      function setSelectionRange(range) {
        var sel = window.getSelection();
        if (!sel || !range) return;
        sel.removeAllRanges();
        sel.addRange(range);
      }

      function wrapRangeWithTag(range, tagName) {
        var el = document.createElement(tagName);
        if (range.collapsed) {
          el.appendChild(document.createTextNode("\u200b"));
          range.insertNode(el);
          var caret = document.createRange();
          caret.selectNodeContents(el);
          caret.collapse(false);
          setSelectionRange(caret);
          return;
        }
        try {
          range.surroundContents(el);
        } catch (errWrap) {
          var fragment = range.extractContents();
          el.appendChild(fragment);
          range.insertNode(el);
        }
        var after = document.createRange();
        after.selectNodeContents(el);
        after.collapse(false);
        setSelectionRange(after);
      }

      function findAlignBlock(range) {
        var node = range.commonAncestorContainer;
        if (node.nodeType === Node.TEXT_NODE) node = node.parentNode;
        while (node && node !== descriptionArea) {
          if (node.nodeType === Node.ELEMENT_NODE) {
            var tag = (node.tagName || "").toUpperCase();
            if (tag === "UL" || tag === "OL") return node;
            if (tag === "LI") {
              var listParent = node.parentNode;
              if (listParent && (listParent.tagName === "UL" || listParent.tagName === "OL")) {
                return listParent;
              }
            }
            if (tag === "P" || tag === "DIV" || tag === "H1" || tag === "H2" || tag === "H3") {
              return node;
            }
          }
          node = node.parentNode;
        }
        return descriptionArea;
      }

      function applyAlignToElement(el, align) {
        if (!el) return;
        var tag = (el.tagName || "").toUpperCase();
        var isList = tag === "UL" || tag === "OL";
        el.style.textAlign = align;
        if (isList) {
          if (align === "left" || align === "start") {
            el.removeAttribute("data-desc-align");
            el.style.listStylePosition = "";
            el.style.paddingLeft = "";
            el.style.width = "";
            el.style.maxWidth = "";
            el.style.marginLeft = "";
            el.style.marginRight = "";
          } else {
            el.setAttribute("data-desc-align", align);
            el.style.listStylePosition = "inside";
            el.style.paddingLeft = "0";
            el.style.width = "fit-content";
            el.style.maxWidth = "100%";
            el.style.marginLeft = "auto";
            el.style.marginRight = align === "center" ? "auto" : "0";
          }
          return;
        }
        if (align === "left" || align === "start") {
          el.removeAttribute("data-desc-align");
        } else {
          el.setAttribute("data-desc-align", align);
        }
        if (tag === "P" || tag === "DIV") {
          el.querySelectorAll("ul, ol").forEach(function (list) {
            if (descriptionArea.contains(list)) applyAlignToElement(list, align);
          });
        }
      }

      function syncListAlignFromAncestors() {
        descriptionArea.querySelectorAll("ul, ol").forEach(function (list) {
          if (list.getAttribute("data-desc-align")) return;
          var ta = (list.style.textAlign || "").toLowerCase();
          if (ta === "center" || ta === "right") {
            applyAlignToElement(list, ta);
            return;
          }
          var node = list.parentElement;
          while (node && node !== descriptionArea) {
            var parentTa = (node.style.textAlign || window.getComputedStyle(node).textAlign || "").toLowerCase();
            if (parentTa === "center" || parentTa === "right") {
              applyAlignToElement(list, parentTa);
              return;
            }
            if (node.getAttribute && node.getAttribute("data-desc-align")) {
              applyAlignToElement(list, node.getAttribute("data-desc-align"));
              return;
            }
            node = node.parentElement;
          }
        });
      }

      function applyAlignFallback(align) {
        var range = getActiveRange();
        if (!range) return;
        var block = findAlignBlock(range);
        applyAlignToElement(block, align);
        if (block === descriptionArea) {
          descriptionArea.querySelectorAll("ul, ol").forEach(function (list) {
            try {
              if (range.intersectsNode(list)) applyAlignToElement(list, align);
            } catch (errListAlign) {
              applyAlignToElement(list, align);
            }
          });
        } else if (align !== "left" && align !== "start") {
          var lists = block.querySelectorAll ? block.querySelectorAll("ul, ol") : [];
          Array.prototype.forEach.call(lists, function (list) {
            try {
              if (range.intersectsNode(list)) applyAlignToElement(list, align);
            } catch (errListAlign) {
              applyAlignToElement(list, align);
            }
          });
        }
        syncListAlignFromAncestors();
      }

      function runDescCommand(cmd) {
        if (!cmd || !isDescEditing()) return;
        restoreDescRange();
        descriptionArea.focus({ preventScroll: true });

        if (INLINE_FMT[cmd]) {
          var wasActive = queryFmtActive(cmd);
          if (wasActive) {
            try {
              document.execCommand(cmd, false, null);
            } catch (errOff) { /* ignore */ }
            if (queryFmtActive(cmd)) unwrapInlineFmt(cmd);
          } else {
            var okInline = false;
            try {
              okInline = document.execCommand(cmd, false, null);
            } catch (errInline) { /* ignore */ }
            if (!okInline || !queryFmtActive(cmd)) {
              var range = getActiveRange();
              if (range) wrapRangeWithTag(range, INLINE_FMT[cmd]);
            }
          }
          captureDescRange();
          syncDescToolbarState();
          return;
        }

        if (cmd === "justifyLeft" || cmd === "justifyCenter" || cmd === "justifyRight") {
          var align = cmd === "justifyLeft" ? "left" : cmd === "justifyCenter" ? "center" : "right";
          var alignActive = queryFmtActive(cmd);
          if (alignActive && cmd !== "justifyLeft") {
            try {
              document.execCommand("justifyLeft", false, null);
            } catch (errAlignOff) { /* ignore */ }
            applyAlignFallback("left");
          } else if (!alignActive) {
            try {
              document.execCommand(cmd, false, null);
            } catch (errAlign) { /* ignore */ }
            applyAlignFallback(align);
          }
          captureDescRange();
          syncDescToolbarState();
          return;
        }

        if (cmd === "insertUnorderedList" || cmd === "insertOrderedList") {
          try {
            document.execCommand(cmd, false, null);
          } catch (errList) { /* ignore */ }
          syncListAlignFromAncestors();
          captureDescRange();
          syncDescToolbarState();
        }
      }

      descriptionArea.addEventListener("keyup", captureDescRange);
      descriptionArea.addEventListener("mouseup", captureDescRange);
      descriptionArea.addEventListener("focus", captureDescRange);
      document.addEventListener("selectionchange", function () {
        if (!isDescEditing()) return;
        if (!selectionInDescription()) return;
        var sel = window.getSelection();
        if (sel && sel.rangeCount) {
          var range = sel.getRangeAt(0);
          if (descriptionArea.contains(range.commonAncestorContainer)) {
            savedDescRange = range.cloneRange();
          }
        }
        syncDescToolbarState();
      });
      window.addEventListener("setup-inline-edit-mode", function (ev) {
        if (ev && ev.detail && ev.detail.enabled) {
          window.setTimeout(function () {
            syncListAlignFromAncestors();
            syncDescToolbarState();
          }, 0);
        } else if (toolbar) {
          toolbar.querySelectorAll(".desc-format-btn.is-active").forEach(function (btn) {
            btn.classList.remove("is-active");
          });
        }
      });

      descriptionArea.addEventListener("keydown", function (e) {
        if (!isDescEditing()) return;
        if (!(e.ctrlKey || e.metaKey) || e.altKey) return;
        var key = (e.key || "").toLowerCase();
        var cmd = key === "b" ? "bold" : key === "i" ? "italic" : key === "u" ? "underline" : "";
        if (!cmd) return;
        e.preventDefault();
        runDescCommand(cmd);
      });

      document.addEventListener(
        "mousedown",
        function (e) {
          var btn = e.target && e.target.closest ? e.target.closest("#product-detail-meta .desc-format-btn") : null;
          if (!btn) return;
          if (!isDescEditing()) return;
          e.preventDefault();
          e.stopPropagation();
          runDescCommand(btn.getAttribute("data-cmd"));
        },
        true
      );
    })();
  })();
  (function () {
    var MAX_GCODE_HIGHLIGHT_CHARS = 120000;
    function esc(s) {
      return s
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;");
    }

    function renderToken(token) {
      if (/^N\d+$/i.test(token)) return '<span class="gc-line">' + esc(token) + "</span>";
      if (/^(?:G|M|T)\d+(?:\.\d+)?$/i.test(token)) return '<span class="gc-cmd">' + esc(token) + "</span>";
      if (/^(?:X|Y|Z|A|B|C|I|J|K|U|V|W|F|S|H|D|R)-?\d+(?:\.\d+)?$/i.test(token)) return '<span class="gc-axis">' + esc(token) + "</span>";
      if (/^-?\d+(?:\.\d+)?$/.test(token)) return '<span class="gc-num">' + esc(token) + "</span>";
      return esc(token);
    }

    function highlightPlainSegment(seg) {
      var re = /([A-Za-z][A-Za-z0-9.+-]*|-?\d+(?:\.\d+)?)/g;
      var out = "";
      var last = 0;
      var m;
      while ((m = re.exec(seg)) !== null) {
        if (m.index > last) out += esc(seg.slice(last, m.index));
        out += renderToken(m[0]);
        last = re.lastIndex;
      }
      if (last < seg.length) out += esc(seg.slice(last));
      return out;
    }

    function highlightLine(line) {
      var commentStart = line.indexOf(";");
      var parenStart = line.indexOf("(");
      if (parenStart !== -1 && (commentStart === -1 || parenStart < commentStart)) {
        commentStart = parenStart;
      }
      if (commentStart === -1) return highlightPlainSegment(line);
      var code = line.slice(0, commentStart);
      var comment = line.slice(commentStart);
      return highlightPlainSegment(code) + '<span class="gc-comment">' + esc(comment) + "</span>";
    }

    function highlightGcode(text) {
      return text
        .split("\n")
        .map(function (line) { return highlightLine(line); })
        .join("\n");
    }

    document.querySelectorAll(".program-gcode-pre").forEach(function (el) {
      if (el.dataset.gcodeHighlighted === "1") return;
      var src = el.textContent || "";
      if (src.length > MAX_GCODE_HIGHLIGHT_CHARS) {
        // Avoid browser freeze on very large programs.
        el.dataset.gcodeHighlighted = "skip";
        return;
      }
      el.innerHTML = highlightGcode(src);
      el.dataset.gcodeHighlighted = "1";
    });
  })();
  (function () {
    var searchState = new Map();

    function clearSearchMarks(pre) {
      pre.querySelectorAll("mark.gc-search-hit").forEach(function (m) {
        m.replaceWith(document.createTextNode(m.textContent || ""));
      });
      pre.normalize();
    }
    function clearToolMarks(pre) {
      pre.querySelectorAll("mark.gc-tool-hit").forEach(function (m) {
        m.replaceWith(document.createTextNode(m.textContent || ""));
      });
      pre.normalize();
    }

    function markInTextNode(node, matcher) {
      var count = 0;
      var current = node;
      while (current && current.nodeType === Node.TEXT_NODE) {
        var source = current.nodeValue || "";
        var match = matcher(source);
        if (!match) break;
        var mid = current.splitText(match.index);
        var tail = mid.splitText(match.length);
        var mark = document.createElement("mark");
        mark.className = "gc-search-hit";
        mark.textContent = mid.nodeValue;
        mid.parentNode.replaceChild(mark, mid);
        count += 1;
        current = tail;
      }
      return count;
    }

    function buildMatcher(rawQuery) {
      var q = (rawQuery || "").trim();
      if (!q) return null;
      var toolMatch = q.match(/^(?:T)?0*(\d{1,3})$/i);
      if (toolMatch) {
        var num = String(Number(toolMatch[1] || "0"));
        var reTool = new RegExp("\\bT0*" + num + "\\b", "i");
        return function (source) {
          var m = reTool.exec(source);
          if (!m) return null;
          return { index: m.index, length: m[0].length };
        };
      }
      var qLower = q.toLowerCase();
      return function (source) {
        var idx = source.toLowerCase().indexOf(qLower);
        if (idx === -1) return null;
        return { index: idx, length: q.length };
      };
    }

    function applySearch(pre, query) {
      clearSearchMarks(pre);
      var matcher = buildMatcher(query);
      if (!matcher) return [];
      var walker = document.createTreeWalker(pre, NodeFilter.SHOW_TEXT);
      var nodes = [];
      var n;
      while ((n = walker.nextNode())) nodes.push(n);
      nodes.forEach(function (textNode) {
        markInTextNode(textNode, matcher);
      });
      return Array.from(pre.querySelectorAll("mark.gc-search-hit"));
    }

    function setCurrentHit(pre, matches, index) {
      matches.forEach(function (m) { m.classList.remove("is-current"); });
      if (!matches.length) return -1;
      var safe = ((index % matches.length) + matches.length) % matches.length;
      var current = matches[safe];
      current.classList.add("is-current");
      current.scrollIntoView({ block: "center", inline: "nearest", behavior: "smooth" });
      return safe;
    }

    function bindSearchInput(input) {
      var targetId = input.getAttribute("data-program-target");
      if (!targetId) return;
      var pre = document.getElementById(targetId);
      if (!pre) return;
      if (pre.dataset.gcodeHighlighted === "skip") {
        input.disabled = true;
        input.placeholder = "Поиск отключен: файл программы слишком большой";
        var navBtnsLarge = document.querySelectorAll('.program-search-nav[data-program-target="' + targetId + '"], .program-tool-nav[data-program-target="' + targetId + '"], .program-search-clear[data-program-target="' + targetId + '"]');
        navBtnsLarge.forEach(function (btn) { btn.disabled = true; });
        var countElLarge = document.querySelector('.program-search-count[data-program-target="' + targetId + '"]');
        if (countElLarge) countElLarge.textContent = "Большой файл: подсветка/поиск отключены";
        return;
      }
      var countEl = document.querySelector('.program-search-count[data-program-target="' + targetId + '"]');
      var clearBtn = document.querySelector('.program-search-clear[data-program-target="' + targetId + '"]');
      var navBtns = Array.from(document.querySelectorAll('.program-search-nav[data-program-target="' + targetId + '"]'));
      var toolNavBtns = Array.from(document.querySelectorAll('.program-tool-nav[data-program-target="' + targetId + '"]'));

      function updateCount(matches, currentIdx) {
        if (!countEl) return;
        if (!matches.length) {
          countEl.textContent = "Совпадений: 0";
          return;
        }
        countEl.textContent = "Совпадений: " + matches.length + " (текущее: " + (currentIdx + 1) + ")";
      }

      function refresh() {
        clearToolMarks(pre);
        var matches = applySearch(pre, input.value || "");
        var currentIdx = matches.length ? 0 : -1;
        if (matches.length) currentIdx = setCurrentHit(pre, matches, currentIdx);
        searchState.set(targetId, { matches: matches, currentIdx: currentIdx });
        updateCount(matches, currentIdx);
      }

      input.addEventListener("input", refresh);
      input.addEventListener("keydown", function (e) {
        if (e.key === "Enter") {
          e.preventDefault();
          var st = searchState.get(targetId);
          if (!st || !st.matches.length) return;
          var dir = e.shiftKey ? -1 : 1;
          st.currentIdx = setCurrentHit(pre, st.matches, st.currentIdx + dir);
          updateCount(st.matches, st.currentIdx);
        }
      });
      if (clearBtn) {
        clearBtn.addEventListener("click", function () {
          input.value = "";
          refresh();
          input.focus();
        });
      }
      navBtns.forEach(function (btn) {
        btn.addEventListener("click", function () {
          var st = searchState.get(targetId);
          if (!st || !st.matches.length) return;
          var dir = Number(btn.getAttribute("data-nav") || "0");
          if (!dir) return;
          st.currentIdx = setCurrentHit(pre, st.matches, st.currentIdx + dir);
          updateCount(st.matches, st.currentIdx);
        });
      });

      function collectToolMarks() {
        clearToolMarks(pre);
        var walker = document.createTreeWalker(pre, NodeFilter.SHOW_TEXT);
        var nodes = [];
        var n;
        while ((n = walker.nextNode())) nodes.push(n);
        var toolRe = /\bT0*\d+\b/gi;
        nodes.forEach(function (textNode) {
          var cur = textNode;
          while (cur && cur.nodeType === Node.TEXT_NODE) {
            var src = cur.nodeValue || "";
            toolRe.lastIndex = 0;
            var m = toolRe.exec(src);
            if (!m) break;
            var mid = cur.splitText(m.index);
            var tail = mid.splitText(m[0].length);
            var mark = document.createElement("mark");
            mark.className = "gc-tool-hit";
            mark.textContent = mid.nodeValue;
            mid.parentNode.replaceChild(mark, mid);
            cur = tail;
          }
        });
        return Array.from(pre.querySelectorAll("mark.gc-tool-hit"));
      }

      function setCurrentTool(matches, idx) {
        matches.forEach(function (m) { m.classList.remove("is-current-tool"); });
        if (!matches.length) return -1;
        var safe = ((idx % matches.length) + matches.length) % matches.length;
        var current = matches[safe];
        current.classList.add("is-current-tool");
        current.scrollIntoView({ block: "center", inline: "nearest", behavior: "smooth" });
        return safe;
      }

      var toolState = { matches: [], idx: -1 };
      toolNavBtns.forEach(function (btn) {
        btn.addEventListener("click", function () {
          if ((input.value || "").trim()) {
            input.value = "";
            refresh();
          }
          if (!toolState.matches.length) {
            toolState.matches = collectToolMarks();
            toolState.idx = -1;
          }
          var dir = Number(btn.getAttribute("data-tool-nav") || "0");
          if (!dir || !toolState.matches.length) return;
          toolState.idx = setCurrentTool(toolState.matches, toolState.idx + dir);
          if (countEl) countEl.textContent = "Инструменты: " + toolState.matches.length + " (текущий: " + (toolState.idx + 1) + ")";
        });
      });
    }

    document.querySelectorAll(".program-search-input").forEach(bindSearchInput);
  })();
