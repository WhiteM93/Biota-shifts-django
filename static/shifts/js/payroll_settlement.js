(function () {
  var dataEl = document.getElementById('payroll-preview-data');
  var form = document.querySelector('form.pr-form');
  if (!dataEl || !form) return;
  var PREVIEW = {};
  try {
    PREVIEW = JSON.parse(dataEl.textContent);
  } catch (e) {
    return;
  }
  var rows = PREVIEW.rows || [];
  var dayRate = parseFloat(PREVIEW.day_rate) || 0;
  var nightRate = parseFloat(PREVIEW.night_rate) || 0;
  var shiftHours = Math.max(0, parseInt(PREVIEW.shift_hours, 10) || 0);
  var advanceLastDay = Math.min(31, Math.max(1, parseInt(PREVIEW.advance_last_day, 10) || 20));

  function shiftKindForRow(r) {
    var g = String(r.graph_shift || r.graph || '').trim().toLowerCase();
    if (g === 'н' || g === 'n') return 'н';
    if (g === 'д' || g === 'd') return 'д';
    return '';
  }

  function rateForShiftKind(kind) {
    return kind === 'н' ? nightRate : dayRate;
  }

  function defaultTabForRow(r) {
    if (r.default_tab_h != null && !isNaN(Number(r.default_tab_h))) {
      return Number(r.default_tab_h);
    }
    return shiftKindForRow(r) ? shiftHours : 0;
  }

  function dayOkForAdvance(r) {
    var d = parseInt(String(r.date_iso || '').slice(8, 10), 10);
    return Number.isFinite(d) && d <= advanceLastDay;
  }

  function parseNum(s) {
    var t = (s == null ? '' : String(s)).trim().replace(',', '.');
    if (t === '') return null;
    var n = Number(t);
    return Number.isFinite(n) ? n : null;
  }

  function round2(x) {
    return Math.round(x * 100) / 100;
  }

  function tabHoursByDate() {
    var byDate = {};
    rows.forEach(function (r) {
      var iso = r.date_iso;
      var inp = form.querySelector('[name="tab_' + iso + '"]');
      var raw = inp ? inp.value : '';
      var t = parseNum(raw);
      if (raw.trim() === '' || t === null) {
        byDate[iso] = defaultTabForRow(r);
      } else {
        byDate[iso] = round2(t);
      }
    });
    return byDate;
  }

  function computeTotalsCore(options) {
    options = options || {};
    var dayPred = options.dayPred;
    var includeFixedRub = options.includeFixedRub !== false;
    var byDate = tabHoursByDate();
    var base = 0;
    var skudSum = 0;
    var tabSum = 0;
    rows.forEach(function (r) {
      if (dayPred && !dayPred(r)) return;
      var h = byDate[r.date_iso] || 0;
      var sk = Number(r.skud_h) || 0;
      tabSum += h;
      skudSum += sk;
      base += h * rateForShiftKind(shiftKindForRow(r));
    });
    base = round2(base);
    skudSum = round2(skudSum);
    tabSum = round2(tabSum);

    var qMax = 20;
    var rMax = 20;
    var mMax = 10;
    var pqRaw =
      parseNum(
        form.querySelector('[name="penalty_quality_pct"]') &&
          form.querySelector('[name="penalty_quality_pct"]').value
      ) || 0;
    var prRaw =
      parseNum(
        form.querySelector('[name="penalty_result_pct"]') &&
          form.querySelector('[name="penalty_result_pct"]').value
      ) || 0;
    var pmRaw =
      parseNum(
        form.querySelector('[name="penalty_mode_pct"]') &&
          form.querySelector('[name="penalty_mode_pct"]').value
      ) || 0;
    var qEff = Math.min(qMax, Math.max(0, pqRaw));
    var rEff = Math.min(rMax, Math.max(0, prRaw));
    var mEff = Math.min(mMax, Math.max(0, pmRaw));
    var guaranteed = round2((base * 50) / 100);
    var qualityPay = round2((base * qEff) / 100);
    var resultPay = round2((base * rEff) / 100);
    var modePay = round2((base * mEff) / 100);
    var tabPayout = round2(guaranteed + qualityPay + resultPay + modePay);
    var penalties = round2(base - tabPayout);
    var pctSum = round2(qMax - qEff + (rMax - rEff) + (mMax - mEff));
    var bPct =
      parseNum(
        form.querySelector('[name="bonus_percent"]') &&
          form.querySelector('[name="bonus_percent"]').value
      ) || 0;
    if (bPct < 0) bPct = 0;
    var bonusPctAmt = round2((base * bPct) / 100);
    var bRub =
      parseNum(
        form.querySelector('[name="bonus_rub"]') && form.querySelector('[name="bonus_rub"]').value
      ) || 0;
    if (bRub < 0) bRub = 0;
    bRub = round2(bRub);
    var penRub =
      parseNum(
        form.querySelector('[name="penalty_rub"]') && form.querySelector('[name="penalty_rub"]').value
      ) || 0;
    if (penRub < 0) penRub = 0;
    penRub = round2(penRub);
    if (!includeFixedRub) {
      bRub = 0;
      penRub = 0;
    }
    var total = round2(tabPayout + bonusPctAmt + bRub - penRub);
    if (total < 0) total = 0;
    return {
      base_tab: base,
      tab_payout: tabPayout,
      total_skud_hours: skudSum,
      total_tab_hours: tabSum,
      penalties: penalties,
      bonus_pct_amount: bonusPctAmt,
      bonus_rub: bRub,
      penalty_rub: penRub,
      total: total,
      penalty_pct_sum: pctSum,
    };
  }

  function computeTotalsSkud() {
    var base = 0;
    rows.forEach(function (r) {
      var sk = Number(r.skud_h) || 0;
      base += sk * rateForShiftKind(shiftKindForRow(r));
    });
    base = round2(base);
    var qMax = 20;
    var rMax = 20;
    var mMax = 10;
    var pqRaw =
      parseNum(
        form.querySelector('[name="penalty_quality_pct"]') &&
          form.querySelector('[name="penalty_quality_pct"]').value
      ) || 0;
    var prRaw =
      parseNum(
        form.querySelector('[name="penalty_result_pct"]') &&
          form.querySelector('[name="penalty_result_pct"]').value
      ) || 0;
    var pmRaw =
      parseNum(
        form.querySelector('[name="penalty_mode_pct"]') &&
          form.querySelector('[name="penalty_mode_pct"]').value
      ) || 0;
    var qEff = Math.min(qMax, Math.max(0, pqRaw));
    var rEff = Math.min(rMax, Math.max(0, prRaw));
    var mEff = Math.min(mMax, Math.max(0, pmRaw));
    var tabPayout = round2(
      base * 0.5 + (base * qEff) / 100 + (base * rEff) / 100 + (base * mEff) / 100
    );
    var bPct =
      parseNum(
        form.querySelector('[name="bonus_percent"]') &&
          form.querySelector('[name="bonus_percent"]').value
      ) || 0;
    if (bPct < 0) bPct = 0;
    var bonusPctAmt = round2((base * bPct) / 100);
    var bRub =
      parseNum(
        form.querySelector('[name="bonus_rub"]') && form.querySelector('[name="bonus_rub"]').value
      ) || 0;
    if (bRub < 0) bRub = 0;
    bRub = round2(bRub);
    var penRub =
      parseNum(
        form.querySelector('[name="penalty_rub"]') && form.querySelector('[name="penalty_rub"]').value
      ) || 0;
    if (penRub < 0) penRub = 0;
    penRub = round2(penRub);
    var total = round2(tabPayout + bonusPctAmt + bRub - penRub);
    if (total < 0) total = 0;
    return total;
  }

  function fmtRu(n) {
    return (Number(n) || 0).toLocaleString('ru-RU', {
      minimumFractionDigits: 0,
      maximumFractionDigits: 2,
    });
  }

  function computeGrossThroughAdvanceDay() {
    var byDate = tabHoursByDate();
    var tabSum = 0;
    var skudSum = 0;
    var gross = 0;
    rows.forEach(function (r) {
      if (!dayOkForAdvance(r)) return;
      var h = byDate[r.date_iso] || 0;
      var sk = Number(r.skud_h) || 0;
      tabSum += h;
      skudSum += sk;
      gross += h * rateForShiftKind(shiftKindForRow(r));
    });
    return {
      total_tab_hours: round2(tabSum),
      total_skud_hours: round2(skudSum),
      gross_accrual_rub: round2(gross),
    };
  }

  function renderGrossSlice(s) {
    var el;
    el = document.getElementById('payroll-pl-until20-tab-h');
    if (el) el.textContent = fmtRu(s.total_tab_hours);
    el = document.getElementById('payroll-pl-until20-skud-h');
    if (el) el.textContent = fmtRu(s.total_skud_hours);
    el = document.getElementById('payroll-pl-until20-gross');
    if (el) el.textContent = fmtRu(s.gross_accrual_rub);
  }

  function renderTotals(t) {
    var el;
    el = document.getElementById('payroll-pl-base');
    if (el) el.textContent = fmtRu(t.base_tab);
    el = document.getElementById('payroll-pl-tab-pay');
    if (el) el.textContent = fmtRu(t.tab_payout);
    el = document.getElementById('payroll-pl-tab-h');
    if (el) el.textContent = fmtRu(t.total_tab_hours);
    el = document.getElementById('payroll-pl-skud-h');
    if (el) el.textContent = fmtRu(t.total_skud_hours);
    el = document.getElementById('payroll-pl-bonus-pct');
    if (el) el.textContent = fmtRu(t.bonus_pct_amount);
    el = document.getElementById('payroll-pl-bonus-rub');
    if (el) el.textContent = fmtRu(t.bonus_rub);
    el = document.getElementById('payroll-pl-pen-total');
    if (el)
      el.textContent = fmtRu(
        round2((Number(t.penalties) || 0) + (Number(t.penalty_rub) || 0))
      );
    el = document.getElementById('payroll-pl-total');
    if (el) el.textContent = fmtRu(t.total);
    el = document.getElementById('payroll-pl-total-skud');
    if (el) el.textContent = fmtRu(computeTotalsSkud());
    renderAdvanceBalance(t);
  }

  function renderAdvanceBalance(t) {
    var inp = form.querySelector('[name="advance_rub"]');
    var adv = parseNum(inp && inp.value) || 0;
    if (adv < 0) adv = 0;
    adv = round2(adv);
    var rem = round2(t.total - adv);
    var over = 0;
    if (rem < 0) {
      over = round2(-rem);
      rem = 0;
    }
    var el = document.getElementById('payroll-pl-remainder-after');
    if (el) el.textContent = fmtRu(rem);
    var rowOver = document.getElementById('pr-chip-overpay');
    var elOver = document.getElementById('payroll-pl-advance-over');
    if (rowOver && elOver) {
      if (over > 0) {
        rowOver.hidden = false;
        elOver.textContent = fmtRu(over);
      } else {
        rowOver.hidden = true;
        elOver.textContent = '—';
      }
    }
  }

  var scheduled = null;
  function refresh() {
    renderTotals(computeTotalsCore({}));
    renderGrossSlice(computeGrossThroughAdvanceDay());
  }
  function scheduleRefresh() {
    if (scheduled) clearTimeout(scheduled);
    scheduled = setTimeout(function () {
      scheduled = null;
      refresh();
    }, 48);
  }

  function formatSliderVal(v) {
    if (!Number.isFinite(v)) return '0';
    var r = Math.round(v * 10) / 10;
    return Math.abs(r - Math.round(r)) < 0.001 ? String(Math.round(r)) : r.toFixed(1);
  }

  function bindSlider(rangeId, outputId) {
    var range = document.getElementById(rangeId);
    var out = document.getElementById(outputId);
    if (!range || !out) return;
    function sync() {
      out.textContent = formatSliderVal(parseFloat(range.value));
    }
    sync();
    range.addEventListener('input', sync);
  }

  bindSlider('pr-range-quality', 'pr-out-quality');
  bindSlider('pr-range-result', 'pr-out-result');
  bindSlider('pr-range-mode', 'pr-out-mode');
  bindSlider('pr-range-bonus-pct', 'pr-out-bonus-pct');

  form.addEventListener('input', scheduleRefresh);
  form.addEventListener('change', scheduleRefresh);
  refresh();
})();
