(function () {
  var root = document.querySelector(".st-page");
  if (!root) return;

  var canEdit = root.getAttribute("data-can-edit") === "1";
  var apiTypes = root.getAttribute("data-api-types") || "";
  var apiTypeTpl = root.getAttribute("data-api-type-tpl") || "";
  var apiTypeMoveTpl = root.getAttribute("data-api-type-move-tpl") || "";
  var apiSubtypes = root.getAttribute("data-api-subtypes") || "";
  var apiSubtypeDelTpl = root.getAttribute("data-api-subtype-del-tpl") || "";
  var apiFields = root.getAttribute("data-api-fields") || "";
  var apiFieldDelTpl = root.getAttribute("data-api-field-del-tpl") || "";

  var treeEl = root.querySelector(".js-st-tree");
  var emptyEl = root.querySelector(".js-st-types-empty");

  var dlgType = document.querySelector(".js-st-dlg-type");
  var dlgSubtype = document.querySelector(".js-st-dlg-subtype");
  var dlgMove = document.querySelector(".js-st-dlg-move");
  var dlgField = document.querySelector(".js-st-dlg-field");
  var typeForm = document.querySelector(".js-st-type-form");
  var subtypeForm = document.querySelector(".js-st-subtype-form");
  var moveForm = document.querySelector(".js-st-move-form");
  var fieldForm = document.querySelector(".js-st-field-form");

  var types = [];
  var expanded = Object.create(null);

  function csrfToken() {
    var m = document.cookie.match(/(?:^|; )csrftoken=([^;]+)/);
    return m ? decodeURIComponent(m[1]) : "";
  }

  function detailUrl(tpl, id) {
    return String(tpl || "").replace(/\/0\/?$/, "/" + id + "/");
  }

  function fetchJson(url, opts) {
    opts = opts || {};
    var headers = {
      "X-Requested-With": "XMLHttpRequest",
      Accept: "application/json",
    };
    if (opts.body != null || (opts.method && opts.method !== "GET")) {
      headers["X-CSRFToken"] = csrfToken();
    }
    if (opts.body != null) headers["Content-Type"] = "application/json";
    return fetch(url, {
      method: opts.method || "GET",
      credentials: "same-origin",
      headers: headers,
      body: opts.body != null ? JSON.stringify(opts.body) : undefined,
    }).then(function (res) {
      return res.text().then(function (text) {
        var data = {};
        try {
          data = text ? JSON.parse(text) : {};
        } catch (e) {
          data = {};
        }
        if (!res.ok || data.ok === false) {
          throw new Error((data && data.error) || res.statusText || "Ошибка запроса");
        }
        return data;
      });
    });
  }

  function openDialog(dlg) {
    if (!dlg) return;
    if (typeof dlg.showModal === "function") dlg.showModal();
    else dlg.setAttribute("open", "open");
  }

  function closeDialog(dlg) {
    if (!dlg) return;
    if (typeof dlg.close === "function") dlg.close();
    else dlg.removeAttribute("open");
  }

  function slugHint(text) {
    return String(text || "")
      .toLowerCase()
      .replace(/_/g, "-")
      .replace(/[^a-z0-9а-яё-]+/gi, "-")
      .replace(/-+/g, "-")
      .replace(/^-|-$/g, "")
      .slice(0, 64);
  }

  function isOpen(key) {
    return expanded[key] !== false;
  }

  function setOpen(key, open) {
    expanded[key] = !!open;
  }

  function fieldMeta(f) {
    var parts = [f.field_kind_label || f.field_kind || ""];
    if (f.required) parts.push("обяз.");
    if (f.unit) parts.push(f.unit);
    if (f.key) parts.push(f.key);
    return parts.filter(Boolean).join(" · ");
  }

  function makeBtn(cls, text, title, onClick) {
    var b = document.createElement("button");
    b.type = "button";
    b.className = cls;
    b.textContent = text;
    if (title) b.title = title;
    b.addEventListener("click", function (e) {
      e.stopPropagation();
      onClick();
    });
    return b;
  }

  function makeNode(opts) {
    var li = document.createElement("li");
    li.className = "st-node " + (opts.className || "") + (opts.isOff ? " is-off" : "");
    li.setAttribute("role", "treeitem");
    li.setAttribute("aria-expanded", opts.hasChildren ? (opts.open ? "true" : "false") : "false");

    var row = document.createElement("div");
    row.className = "st-node__row";

    var toggle = document.createElement("button");
    toggle.type = "button";
    toggle.className = "st-node__toggle" + (opts.hasChildren ? "" : " is-leaf");
    toggle.setAttribute("aria-label", opts.open ? "Свернуть" : "Развернуть");
    toggle.textContent = opts.hasChildren ? (opts.open ? "−" : "+") : "·";
    if (opts.hasChildren) {
      toggle.addEventListener("click", function (e) {
        e.stopPropagation();
        setOpen(opts.key, !isOpen(opts.key));
        renderTree();
      });
    }
    row.appendChild(toggle);

    var label = document.createElement("div");
    label.className = "st-node__label";
    var name = document.createElement("span");
    name.className = "st-node__name";
    name.textContent = opts.name;
    label.appendChild(name);
    if (opts.badge) {
      var badge = document.createElement("span");
      badge.className = "st-node__badge";
      badge.textContent = opts.badge;
      label.appendChild(badge);
    }
    if (opts.meta) {
      var meta = document.createElement("span");
      meta.className = "st-node__meta";
      meta.textContent = opts.meta;
      label.appendChild(meta);
    }
    row.appendChild(label);

    if (opts.actions && opts.actions.length) {
      var actions = document.createElement("div");
      actions.className = "st-node__actions";
      opts.actions.forEach(function (a) {
        actions.appendChild(a);
      });
      row.appendChild(actions);
    }

    li.appendChild(row);

    if (opts.hasChildren) {
      var children = document.createElement("ul");
      children.className = "st-node__children";
      children.setAttribute("role", "group");
      if (!opts.open) children.hidden = true;
      if (opts.buildChildren) opts.buildChildren(children);
      li.appendChild(children);
    }
    return li;
  }

  function appendFieldNodes(parentUl, fields, typeId, subtypeId) {
    if (!fields || !fields.length) {
      parentUl.appendChild(
        makeNode({
          key: "empty-field-" + typeId + "-" + (subtypeId || 0),
          className: "st-node--field",
          name: "нет характеристик",
          meta: "",
          hasChildren: false,
          open: false,
        })
      );
      return;
    }
    fields.forEach(function (f) {
      var actions = [];
      if (canEdit) {
        actions.push(
          makeBtn("st-btn-tiny", "Изменить", "", function () {
            openFieldDialog(f, typeId, subtypeId);
          })
        );
        actions.push(
          makeBtn("st-btn-tiny", "×", "Удалить", function () {
            if (!confirm("Удалить характеристику «" + f.label + "»?")) return;
            fetchJson(detailUrl(apiFieldDelTpl, f.id), { method: "DELETE" })
              .then(loadTree)
              .catch(function (e) {
                alert(e.message);
              });
          })
        );
      }
      parentUl.appendChild(
        makeNode({
          key: "field-" + f.id,
          className: "st-node--field",
          name: f.label + (f.required ? " *" : ""),
          meta: fieldMeta(f),
          hasChildren: false,
          open: false,
          actions: actions,
        })
      );
    });
  }

  function renderTree() {
    if (!treeEl) return;
    treeEl.innerHTML = "";
    if (!types.length) {
      if (emptyEl) emptyEl.hidden = false;
      return;
    }
    if (emptyEl) emptyEl.hidden = true;

    types.forEach(function (t) {
      var typeKey = "type-" + t.id;
      var typeOpen = isOpen(typeKey);
      var typeActions = [];
      if (canEdit) {
        typeActions.push(
          makeBtn("st-btn-tiny", "+ Поле", "Общая характеристика", function () {
            openFieldDialog(null, t.id, null);
          })
        );
        typeActions.push(
          makeBtn("st-btn-tiny", "+ Подтип", "", function () {
            openSubtypeDialog(null, t.id);
          })
        );
        typeActions.push(
          makeBtn("st-btn-tiny", "В…", "Сделать подтипом другого типа", function () {
            openMoveDialog(t);
          })
        );
        typeActions.push(
          makeBtn("st-btn-tiny", "Изменить", "", function () {
            openTypeDialog(t);
          })
        );
        typeActions.push(
          makeBtn("st-btn-tiny", "×", "Удалить тип", function () {
            if (!confirm("Удалить тип «" + t.name + "» со всеми подтипами и полями?")) return;
            fetchJson(detailUrl(apiTypeTpl, t.id), { method: "DELETE" })
              .then(loadTree)
              .catch(function (e) {
                alert(e.message);
              });
          })
        );
      }

      treeEl.appendChild(
        makeNode({
          key: typeKey,
          className: "st-node--type",
          name: t.name,
          badge: t.code || "",
          meta:
            "подтипов: " +
            ((t.subtypes && t.subtypes.length) || 0) +
            " · общих полей: " +
            ((t.fields && t.fields.length) || 0) +
            (t.is_active ? "" : " · выкл."),
          isOff: !t.is_active,
          hasChildren: true,
          open: typeOpen,
          actions: typeActions,
          buildChildren: function (childrenUl) {
            var fieldsKey = "type-fields-" + t.id;
            var fieldsOpen = isOpen(fieldsKey);
            var fieldsActions = [];
            if (canEdit) {
              fieldsActions.push(
                makeBtn("st-btn-tiny", "+", "Добавить поле", function () {
                  openFieldDialog(null, t.id, null);
                })
              );
            }
            childrenUl.appendChild(
              makeNode({
                key: fieldsKey,
                className: "st-node--group",
                name: "Общие характеристики",
                meta: String((t.fields && t.fields.length) || 0),
                hasChildren: true,
                open: fieldsOpen,
                actions: fieldsActions,
                buildChildren: function (ul) {
                  appendFieldNodes(ul, t.fields || [], t.id, null);
                },
              })
            );

            var subsKey = "type-subs-" + t.id;
            var subsOpen = isOpen(subsKey);
            var subsActions = [];
            if (canEdit) {
              subsActions.push(
                makeBtn("st-btn-tiny", "+", "Добавить подтип", function () {
                  openSubtypeDialog(null, t.id);
                })
              );
            }
            childrenUl.appendChild(
              makeNode({
                key: subsKey,
                className: "st-node--group",
                name: "Подтипы",
                meta: String((t.subtypes && t.subtypes.length) || 0),
                hasChildren: true,
                open: subsOpen,
                actions: subsActions,
                buildChildren: function (subsUl) {
                  var subs = t.subtypes || [];
                  if (!subs.length) {
                    subsUl.appendChild(
                      makeNode({
                        key: "empty-sub-" + t.id,
                        className: "st-node--subtype",
                        name: "нет подтипов",
                        hasChildren: false,
                        open: false,
                      })
                    );
                    return;
                  }
                  subs.forEach(function (s) {
                    var subKey = "subtype-" + s.id;
                    var subOpen = isOpen(subKey);
                    var subActions = [];
                    if (canEdit) {
                      subActions.push(
                        makeBtn("st-btn-tiny", "+ Поле", "", function () {
                          openFieldDialog(null, t.id, s.id);
                        })
                      );
                      subActions.push(
                        makeBtn("st-btn-tiny", "Изменить", "", function () {
                          openSubtypeDialog(s, t.id);
                        })
                      );
                      subActions.push(
                        makeBtn("st-btn-tiny", "×", "Удалить подтип", function () {
                          if (!confirm("Удалить подтип «" + s.name + "»?")) return;
                          fetchJson(detailUrl(apiSubtypeDelTpl, s.id), { method: "DELETE" })
                            .then(loadTree)
                            .catch(function (e) {
                              alert(e.message);
                            });
                        })
                      );
                    }
                    subsUl.appendChild(
                      makeNode({
                        key: subKey,
                        className: "st-node--subtype",
                        name: s.name,
                        badge: s.code || "",
                        meta:
                          "полей: " +
                          ((s.fields && s.fields.length) || 0) +
                          (s.is_active ? "" : " · выкл."),
                        isOff: !s.is_active,
                        hasChildren: true,
                        open: subOpen,
                        actions: subActions,
                        buildChildren: function (ul) {
                          appendFieldNodes(ul, s.fields || [], t.id, s.id);
                        },
                      })
                    );
                  });
                },
              })
            );
          },
        })
      );
    });
  }

  function ensureDefaultExpanded() {
    types.forEach(function (t) {
      var typeKey = "type-" + t.id;
      if (expanded[typeKey] === undefined) expanded[typeKey] = true;
      var fieldsKey = "type-fields-" + t.id;
      if (expanded[fieldsKey] === undefined) expanded[fieldsKey] = true;
      var subsKey = "type-subs-" + t.id;
      if (expanded[subsKey] === undefined) expanded[subsKey] = true;
    });
  }

  function loadTree() {
    var url = apiTypes + (apiTypes.indexOf("?") >= 0 ? "&" : "?") + "details=1";
    return fetchJson(url).then(function (data) {
      types = data.types || [];
      ensureDefaultExpanded();
      renderTree();
    });
  }

  function setAllExpanded(open) {
    types.forEach(function (t) {
      setOpen("type-" + t.id, open);
      setOpen("type-fields-" + t.id, open);
      setOpen("type-subs-" + t.id, open);
      (t.subtypes || []).forEach(function (s) {
        setOpen("subtype-" + s.id, open);
      });
    });
    renderTree();
  }

  function openTypeDialog(t) {
    if (!typeForm || !dlgType) return;
    typeForm.querySelector(".js-st-type-form-title").textContent = t ? "Изменить тип" : "Новый тип";
    typeForm.querySelector(".js-st-type-id").value = t ? String(t.id) : "";
    typeForm.querySelector(".js-st-type-name").value = t ? t.name : "";
    typeForm.querySelector(".js-st-type-code").value = t ? t.code : "";
    typeForm.querySelector(".js-st-type-notes").value = t ? t.notes || "" : "";
    typeForm.querySelector(".js-st-type-active").checked = t ? !!t.is_active : true;
    openDialog(dlgType);
  }

  function openMoveDialog(t) {
    if (!moveForm || !dlgMove || !t) return;
    var others = types.filter(function (x) {
      return x.id !== t.id;
    });
    if (!others.length) {
      alert("Нужен ещё хотя бы один тип — создайте «Режущий инструмент» или «Оснастка» и снова нажмите «В…».");
      return;
    }
    var hint = moveForm.querySelector(".js-st-move-hint");
    if (hint) {
      hint.textContent =
        "«" +
        t.name +
        "» станет подтипом выбранного типа. Бывшие подтипы превратятся в характеристику «Вид».";
    }
    moveForm.querySelector(".js-st-move-source-id").value = String(t.id);
    var sel = moveForm.querySelector(".js-st-move-target");
    sel.innerHTML = "";
    others.forEach(function (x) {
      var opt = document.createElement("option");
      opt.value = String(x.id);
      opt.textContent = x.name + (x.code ? " (" + x.code + ")" : "");
      sel.appendChild(opt);
    });
    openDialog(dlgMove);
  }

  function openSubtypeDialog(s, typeId) {
    if (!subtypeForm || !dlgSubtype) return;
    subtypeForm.querySelector(".js-st-subtype-form-title").textContent = s ? "Изменить подтип" : "Новый подтип";
    subtypeForm.querySelector(".js-st-subtype-id").value = s ? String(s.id) : "";
    subtypeForm.querySelector(".js-st-subtype-type-id").value = String(typeId || (s && s.tool_type_id) || "");
    subtypeForm.querySelector(".js-st-subtype-name").value = s ? s.name : "";
    subtypeForm.querySelector(".js-st-subtype-code").value = s ? s.code : "";
    subtypeForm.querySelector(".js-st-subtype-notes").value = s ? s.notes || "" : "";
    subtypeForm.querySelector(".js-st-subtype-active").checked = s ? !!s.is_active : true;
    openDialog(dlgSubtype);
  }

  function syncFieldChoicesRow() {
    if (!fieldForm) return;
    var kind = fieldForm.querySelector(".js-st-field-kind").value;
    var row = fieldForm.querySelector(".js-st-field-choices-row");
    if (row) row.hidden = kind !== "select";
  }

  function openFieldDialog(f, typeId, subtypeId) {
    if (!fieldForm || !dlgField) return;
    fieldForm.querySelector(".js-st-field-form-title").textContent = f ? "Изменить характеристику" : "Новая характеристика";
    fieldForm.querySelector(".js-st-field-id").value = f ? String(f.id) : "";
    fieldForm.querySelector(".js-st-field-type-id").value = String(typeId || (f && f.tool_type_id) || "");
    fieldForm.querySelector(".js-st-field-subtype-id").value =
      subtypeId != null && subtypeId !== ""
        ? String(subtypeId)
        : f && f.subtype_id
          ? String(f.subtype_id)
          : "";
    fieldForm.querySelector(".js-st-field-label").value = f ? f.label : "";
    fieldForm.querySelector(".js-st-field-key").value = f ? f.key : "";
    fieldForm.querySelector(".js-st-field-kind").value = f ? f.field_kind : "text";
    fieldForm.querySelector(".js-st-field-choices").value = f && f.choices ? f.choices.join("\n") : "";
    fieldForm.querySelector(".js-st-field-unit").value = f ? f.unit || "" : "";
    fieldForm.querySelector(".js-st-field-help").value = f ? f.help_text || "" : "";
    fieldForm.querySelector(".js-st-field-required").checked = f ? !!f.required : false;
    syncFieldChoicesRow();
    openDialog(dlgField);
  }

  document.querySelectorAll(".js-st-dlg-cancel").forEach(function (btn) {
    btn.addEventListener("click", function () {
      closeDialog(btn.closest("dialog"));
    });
  });

  var btnNewType = root.querySelector(".js-st-new-type");
  if (btnNewType) btnNewType.addEventListener("click", function () { openTypeDialog(null); });
  var btnExpand = root.querySelector(".js-st-expand-all");
  if (btnExpand) btnExpand.addEventListener("click", function () { setAllExpanded(true); });
  var btnCollapse = root.querySelector(".js-st-collapse-all");
  if (btnCollapse) btnCollapse.addEventListener("click", function () { setAllExpanded(false); });

  if (typeForm) {
    typeForm.addEventListener("submit", function (e) {
      e.preventDefault();
      var id = typeForm.querySelector(".js-st-type-id").value;
      var name = (typeForm.querySelector(".js-st-type-name").value || "").trim();
      var body = {
        name: name,
        code: (typeForm.querySelector(".js-st-type-code").value || "").trim() || slugHint(name),
        notes: typeForm.querySelector(".js-st-type-notes").value || "",
        is_active: typeForm.querySelector(".js-st-type-active").checked,
      };
      var req = id
        ? fetchJson(detailUrl(apiTypeTpl, id), { method: "POST", body: body })
        : fetchJson(apiTypes, { method: "POST", body: body });
      req
        .then(function (data) {
          closeDialog(dlgType);
          if (data.type && data.type.id) setOpen("type-" + data.type.id, true);
          return loadTree();
        })
        .catch(function (err) { alert(err.message); });
    });
  }

  if (subtypeForm) {
    subtypeForm.addEventListener("submit", function (e) {
      e.preventDefault();
      var id = subtypeForm.querySelector(".js-st-subtype-id").value;
      var typeId = subtypeForm.querySelector(".js-st-subtype-type-id").value;
      var name = (subtypeForm.querySelector(".js-st-subtype-name").value || "").trim();
      var body = {
        id: id || undefined,
        tool_type_id: typeId,
        name: name,
        code: (subtypeForm.querySelector(".js-st-subtype-code").value || "").trim() || slugHint(name),
        notes: subtypeForm.querySelector(".js-st-subtype-notes").value || "",
        is_active: subtypeForm.querySelector(".js-st-subtype-active").checked,
      };
      fetchJson(apiSubtypes, { method: "POST", body: body })
        .then(function (data) {
          closeDialog(dlgSubtype);
          setOpen("type-" + typeId, true);
          setOpen("type-subs-" + typeId, true);
          if (data.subtype && data.subtype.id) setOpen("subtype-" + data.subtype.id, true);
          return loadTree();
        })
        .catch(function (err) { alert(err.message); });
    });
  }

  if (moveForm) {
    moveForm.addEventListener("submit", function (e) {
      e.preventDefault();
      var sourceId = moveForm.querySelector(".js-st-move-source-id").value;
      var targetId = moveForm.querySelector(".js-st-move-target").value;
      if (!sourceId || !targetId) return;
      var source = types.find(function (x) {
        return String(x.id) === String(sourceId);
      });
      var target = types.find(function (x) {
        return String(x.id) === String(targetId);
      });
      var msg =
        "Переместить «" +
        ((source && source.name) || sourceId) +
        "» в тип «" +
        ((target && target.name) || targetId) +
        "» как подтип?\nБывшие подтипы станут списком «Вид».";
      if (!confirm(msg)) return;
      fetchJson(detailUrl(apiTypeMoveTpl, sourceId), {
        method: "POST",
        body: { target_type_id: Number(targetId) },
      })
        .then(function (data) {
          closeDialog(dlgMove);
          setOpen("type-" + targetId, true);
          setOpen("type-subs-" + targetId, true);
          if (data.moved_subtype_id) setOpen("subtype-" + data.moved_subtype_id, true);
          return loadTree();
        })
        .catch(function (err) {
          alert(err.message);
        });
    });
  }

  if (fieldForm) {
    var kindSel = fieldForm.querySelector(".js-st-field-kind");
    if (kindSel) kindSel.addEventListener("change", syncFieldChoicesRow);
    fieldForm.addEventListener("submit", function (e) {
      e.preventDefault();
      var id = fieldForm.querySelector(".js-st-field-id").value;
      var typeId = fieldForm.querySelector(".js-st-field-type-id").value;
      var subtypeId = fieldForm.querySelector(".js-st-field-subtype-id").value;
      var label = (fieldForm.querySelector(".js-st-field-label").value || "").trim();
      var body = {
        id: id || undefined,
        tool_type_id: typeId,
        subtype_id: subtypeId || null,
        label: label,
        key: (fieldForm.querySelector(".js-st-field-key").value || "").trim() || slugHint(label),
        field_kind: fieldForm.querySelector(".js-st-field-kind").value,
        choices: fieldForm.querySelector(".js-st-field-choices").value || "",
        unit: fieldForm.querySelector(".js-st-field-unit").value || "",
        help_text: fieldForm.querySelector(".js-st-field-help").value || "",
        required: fieldForm.querySelector(".js-st-field-required").checked,
      };
      fetchJson(apiFields, { method: "POST", body: body })
        .then(function () {
          closeDialog(dlgField);
          setOpen("type-" + typeId, true);
          if (subtypeId) {
            setOpen("type-subs-" + typeId, true);
            setOpen("subtype-" + subtypeId, true);
          } else {
            setOpen("type-fields-" + typeId, true);
          }
          return loadTree();
        })
        .catch(function (err) { alert(err.message); });
    });
  }

  loadTree().catch(function (e) {
    alert(e.message);
  });
})();
