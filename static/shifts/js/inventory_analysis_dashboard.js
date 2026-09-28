(function () {
  function parsePayload() {
    var el = document.getElementById("inv-dash-charts-data");
    if (!el) return null;
    try {
      return JSON.parse(el.textContent || "");
    } catch (err) {
      return null;
    }
  }

  function palette(n) {
    var base = [
      "#3b6ea5",
      "#5b9bd5",
      "#ed7d31",
      "#70ad47",
      "#ffc000",
      "#9e480e",
      "#264478",
      "#a5a5a5",
      "#4472c4",
      "#c55a11",
      "#548235",
      "#bf8f00",
    ];
    var out = [];
    for (var i = 0; i < n; i++) out.push(base[i % base.length]);
    return out;
  }

  function cssVar(name, fallback) {
    var v = getComputedStyle(document.documentElement).getPropertyValue(name);
    return (v || "").trim() || fallback;
  }

  function themeColors() {
    var dawn = document.documentElement.getAttribute("data-theme") === "dawn";
    return {
      text: cssVar("--bio-body-fg", dawn ? "#3c362f" : "#eaf0ff"),
      muted: cssVar("--bio-muted", dawn ? "#6b6258" : "#c5d0ea"),
      grid: cssVar("--glass-border", dawn ? "#d8dde6" : "rgba(201, 213, 255, 0.18)"),
      card: cssVar("--bio-surface-panel", dawn ? "#fff" : "#151b2a"),
    };
  }

  function applyChartTheme(chart, colors) {
    if (!chart) return;
    var opts = chart.options || {};
    Chart.defaults.color = colors.text;
    if (opts.plugins && opts.plugins.legend && opts.plugins.legend.labels) {
      opts.plugins.legend.labels.color = colors.text;
    }
    if (opts.scales) {
      ["x", "y"].forEach(function (axis) {
        if (!opts.scales[axis]) return;
        if (opts.scales[axis].ticks) opts.scales[axis].ticks.color = colors.text;
        if (opts.scales[axis].title) opts.scales[axis].title.color = colors.muted;
        if (opts.scales[axis].grid) opts.scales[axis].grid.color = colors.grid;
      });
    }
    if (chart.data && chart.data.datasets) {
      chart.data.datasets.forEach(function (ds) {
        if (chart.config && chart.config.type === "pie") ds.borderColor = colors.card;
      });
    }
    chart.update();
  }

  function boot() {
    if (typeof Chart === "undefined") return;
    if (!document.querySelector(".inv-dash")) return;
    var data = parsePayload();
    if (!data) return;

    var colors = themeColors();
    var text = colors.text;
    var muted = colors.muted;
    var grid = colors.grid;

    Chart.defaults.color = text;
    Chart.defaults.borderColor = grid;
    Chart.defaults.font.family = getComputedStyle(document.body).fontFamily || "system-ui, sans-serif";

    var charts = [];
    var barEl = document.getElementById("inv-dash-bar");
    if (barEl && data.nomenclature && data.nomenclature.labels.length) {
      charts.push(new Chart(barEl, {
        type: "bar",
        data: {
          labels: data.nomenclature.labels,
          datasets: [
            {
              label: "Количество",
              data: data.nomenclature.values,
              backgroundColor: "#5b9bd5",
              borderColor: "#3b6ea5",
              borderWidth: 1,
              borderRadius: 3,
              maxBarThickness: 42,
            },
          ],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: { display: false },
            tooltip: {
              callbacks: {
                label: function (ctx) {
                  return " " + (ctx.parsed.y || 0) + " шт.";
                },
              },
            },
          },
          scales: {
            x: {
              ticks: {
                maxRotation: 45,
                minRotation: 0,
                autoSkip: true,
                font: { size: 10 },
                color: text,
              },
              grid: { display: false },
            },
            y: {
              beginAtZero: true,
              title: { display: true, text: "Количество", color: muted },
              ticks: { precision: 0, color: text },
              grid: { color: grid },
            },
          },
        },
      }));
    }

    var pieEl = document.getElementById("inv-dash-pie");
    if (pieEl && data.categories && data.categories.labels.length) {
      var sliceColors = palette(data.categories.labels.length);
      charts.push(new Chart(pieEl, {
        type: "pie",
        data: {
          labels: data.categories.labels,
          datasets: [
            {
              data: data.categories.values,
              backgroundColor: sliceColors,
              borderColor: colors.card,
              borderWidth: 2,
            },
          ],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: {
              position: "right",
              labels: {
                boxWidth: 12,
                boxHeight: 12,
                padding: 10,
                color: text,
                font: { size: 12 },
                usePointStyle: false,
              },
            },
            tooltip: {
              callbacks: {
                label: function (ctx) {
                  var v = ctx.parsed || 0;
                  return " " + ctx.label + ": " + v + " шт.";
                },
              },
            },
          },
        },
      }));
    }

    window.addEventListener("biota-theme-change", function () {
      var next = themeColors();
      charts.forEach(function (ch) {
        applyChartTheme(ch, next);
      });
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
