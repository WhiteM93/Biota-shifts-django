(function () {
  var catSel = document.getElementById("inv-watch-category");
  var fieldSel = document.getElementById("inv-watch-group-field");
  var dataEl = document.getElementById("inv-watch-group-fields");
  if (!catSel || !fieldSel || !dataEl) return;

  var byCat = {};
  try {
    byCat = JSON.parse(dataEl.textContent || "{}") || {};
  } catch (err) {
    byCat = {};
  }

  function fillFields(cat, keepValue) {
    var rows = byCat[cat] || [];
    var prev = keepValue || fieldSel.value;
    fieldSel.innerHTML = "";
    rows.forEach(function (pair) {
      var key = pair[0];
      var label = pair[1];
      var opt = document.createElement("option");
      opt.value = key;
      opt.textContent = label;
      if (key === prev) opt.selected = true;
      fieldSel.appendChild(opt);
    });
    if (!fieldSel.value && rows.length) {
      fieldSel.value = rows[0][0];
    }
  }

  catSel.addEventListener("change", function () {
    fillFields(catSel.value, "");
  });
})();
