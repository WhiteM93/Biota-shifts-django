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

  function boot() {
    if (typeof Chart === "undefined") return;
    if (!document.querySelector(".inv-dash")) return;
    var data = parsePayload();
    if (!data) return;

    var text = cssVar("--bio-text", "#1f2933");
    var muted = cssVar("--bio-text-muted", "#6b7280");
    var grid = cssVar("--glass-border", "#d8dde6");

    Chart.defaults.color = muted;
    Chart.defaults.borderColor = grid;
    Chart.defaults.font.family = getComputedStyle(document.body).fontFamily || "system-ui, sans-serif";

    var barEl = document.getElementById("inv-dash-bar");
    if (barEl && data.nomenclature && data.nomenclature.labels.length) {
      new Chart(barEl, {
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
                color: muted,
              },
              grid: { display: false },
            },
            y: {
              beginAtZero: true,
              title: { display: true, text: "Количество", color: muted },
              ticks: { precision: 0, color: muted },
              grid: { color: grid },
            },
          },
        },
      });
    }

    var pieEl = document.getElementById("inv-dash-pie");
    if (pieEl && data.categories && data.categories.labels.length) {
      var colors = palette(data.categories.labels.length);
      new Chart(pieEl, {
        type: "pie",
        data: {
          labels: data.categories.labels,
          datasets: [
            {
              data: data.categories.values,
              backgroundColor: colors,
              borderColor: cssVar("--bio-bg-card", "#fff"),
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
                font: { size: 11 },
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
      });
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
