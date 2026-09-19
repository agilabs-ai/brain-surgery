/* ------------------------------------------------------------------
   BSCharts: the three charts on the Brain Surgery performance report.

     BSCharts.arms(el, result, opts)         stacked arm bars, one row per model
     BSCharts.interaction(el, result, opts)  the 2x2, model crossed with setup
     BSCharts.taskGrid(el, result, opts)     per-task, per-trial small multiples

   No libraries, no network, no fonts. Every number rendered comes out of the
   result object; nothing is derived that the pipeline did not already compute,
   except where a comment says so explicitly. Where a value is absent the chart
   says "not measured" rather than drawing a zero, because a zero is a claim.

   Input is a brain-surgery/0.5 result (eval/to_result.py).
   ------------------------------------------------------------------ */
(function (global) {
  'use strict';

  var SVG_NS = 'http://www.w3.org/2000/svg';

  /* ---------- tiny DOM helpers ---------- */

  function h(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  }

  function svg(tag, attrs) {
    var n = document.createElementNS(SVG_NS, tag);
    for (var k in attrs) if (Object.prototype.hasOwnProperty.call(attrs, k)) n.setAttribute(k, attrs[k]);
    return n;
  }

  function titled(node, text) {
    var t = svg('title');
    t.textContent = text;
    node.insertBefore(t, node.firstChild);
    return node;
  }

  function mount(el, cls, opts) {
    // Idempotent: re-rendering the same mount replaces, never appends.
    el.textContent = '';
    el.classList.add('bs-chart', cls);
    var head = h('div', 'bs-head');
    if (opts.title !== false) head.append(h('h3', 'bs-title', opts.title || ''));
    if (opts.subtitle) head.append(h('p', 'bs-sub', opts.subtitle));
    if (head.childNodes.length) el.append(head);
    return el;
  }

  /* ---------- numbers ---------- */

  var NA = 'not measured';

  function isNum(v) { return typeof v === 'number' && isFinite(v); }

  // Fixed one decimal everywhere so the tabular columns line up on the point.
  function pct(v) { return isNum(v) ? v.toFixed(1) + '%' : NA; }

  function signed(v, suffix) {
    if (!isNum(v)) return NA;
    return (v > 0 ? '+' : v < 0 ? '-' : '') + Math.abs(v).toFixed(1) + (suffix || '');
  }

  function signClass(v) { return !isNum(v) || v === 0 ? '' : v > 0 ? 'bs-pos' : 'bs-neg'; }

  function clampPct(v) { return Math.max(0, Math.min(100, isNum(v) ? v : 0)); }

  /* Read a model id as a person would say it: claude-haiku-4-5-20251001 -> Haiku 4.5.
     Purely a formatting pass; if it cannot parse, the raw id is shown unchanged. */
  function modelName(id) {
    if (typeof id !== 'string' || !id) return null;
    var body = id.replace(/^claude-/i, '').replace(/-\d{8}$/, '');
    var words = [], nums = [];
    body.split(/[-_]/).forEach(function (part) {
      if (!part) return;
      if (/^\d+$/.test(part)) nums.push(part);
      else words.push(part.charAt(0).toUpperCase() + part.slice(1));
    });
    if (!words.length) return id;
    return (words.join(' ') + ' ' + nums.join('.')).trim();
  }

  // Arm labels read "base model, no skill". The half before the comma is the
  // model qualifier, the half after is the setup.
  function labelHalves(label) {
    var parts = String(label || '').split(/,\s*/);
    return { model: parts[0] || '', setup: parts.slice(1).join(', ') || '' };
  }

  /* ---------- result readers ---------- */

  function contrastsOf(result) {
    var c = (result && result.contrasts) || {};
    return Object.keys(c).map(function (k) { return c[k]; }).filter(Boolean);
  }

  function findContrast(result, fromArm, toArm) {
    var all = contrastsOf(result);
    for (var i = 0; i < all.length; i++) {
      var c = all[i];
      if (c.before && c.after && c.before.arm === fromArm && c.after.arm === toArm) return c;
    }
    return null;
  }

  function gridArm(result, arm) {
    var arms = result && result.grid && result.grid.arms;
    return (arms && arms[arm]) || null;
  }

  /* ==================================================================
     1. ARM BARS
     ================================================================== */

  /* Each row is one bar of three stacked segments rather than two grouped
     bars. Grouped bars ask the eye to measure the gap between two floating
     ends; stacked puts the lift directly on the baseline it was added to, and
     the third segment keeps the unclosed headroom in the picture. That is the
     whole argument of the page: the skill closes part of what is left, and a
     lot is still left. */

  var DEFAULT_ROWS = [
    { without: 'A', with: 'B', model: 'base' },
    { without: 'C', with: 'D', model: 'strong' }
  ];

  function armRowData(result, spec, names) {
    var c = findContrast(result, spec.without, spec.with);
    var gWithout = gridArm(result, spec.without);
    var gWith = gridArm(result, spec.with);

    // Prefer the contrast: its two rates, the delta and the gain are all
    // computed over the same paired set of tasks, so they agree with each
    // other. Mixing a grid rate with a paired delta would not.
    var before = c ? c.before : (gWithout ? { rate: gWithout.rate, label: gWithout.label } : null);
    var after = c ? c.after : (gWith ? { rate: gWith.rate, label: gWith.label } : null);

    var deltaPts = c ? c.delta_points
      : (before && after && isNum(before.rate) && isNum(after.rate)
        ? Math.round((after.rate - before.rate) * 10) / 10 : null);

    var gain = c ? c.normalized_gain : null;

    var modelId = result && result.grid && result.grid.models ? result.grid.models[spec.model] : null;
    var pretty = (names && names[spec.model]) || modelName(modelId);
    var halves = labelHalves((after && after.label) || (gWith && gWith.label) || '');

    return {
      arms: [spec.without, spec.with],
      model: pretty || halves.model || spec.model,
      qualifier: halves.model,
      before: before,
      after: after,
      delta: deltaPts,
      gain: gain,
      tasks: c ? c.tasks_compared : (gWith ? gWith.tasks : null)
    };
  }

  function numCell(key, value, cls, signCls) {
    var cell = h('div', 'bs-cell ' + cls);
    cell.append(h('span', 'bs-cell-k', key));
    var v = h('span', 'bs-cell-v bs-n' + (signCls ? ' ' + signCls : ''), value);
    if (value === NA) v.classList.add('bs-na');
    cell.append(v);
    return cell;
  }

  function buildTrack(row) {
    var b = row.before && isNum(row.before.rate) ? clampPct(row.before.rate) : null;
    var a = row.after && isNum(row.after.rate) ? clampPct(row.after.rate) : null;
    var track = h('div', 'bs-track');

    if (b == null && a == null) {
      track.append(h('div', 'bs-seg bs-seg-head'));
      track.setAttribute('role', 'img');
      track.setAttribute('aria-label', 'Not measured.');
      return track;
    }

    var lo = Math.min(b == null ? a : b, a == null ? b : a);
    var hi = Math.max(b == null ? a : b, a == null ? b : a);
    var gaining = a != null && b != null && a >= b;

    // Segment 1 is always the solid floor both arms reached. When the skill
    // loses ground the middle band is what was lost, so it is tinted red
    // instead of the pale accent; the solid part still means "held".
    var base = h('div', 'bs-seg bs-seg-base');
    base.style.width = lo + '%';
    base.title = (gaining ? row.before && row.before.label : row.after && row.after.label) + ': ' + pct(lo);

    var band = h('div', 'bs-seg ' + (gaining ? 'bs-seg-lift' : 'bs-seg-loss'));
    band.style.width = (hi - lo) + '%';
    band.title = (gaining ? 'Lift from the skill: ' : 'Lost by the change: ') + signed(row.delta, ' points');

    var head = h('div', 'bs-seg bs-seg-head');
    head.style.width = (100 - hi) + '%';
    head.title = 'Headroom left to 100%: ' + pct(100 - hi);

    if (hi - lo > 0.01) base.classList.add('bs-seg-gap');
    if (100 - hi > 0.01) band.classList.add('bs-seg-gap');

    // No gridlines inside the fill: a rule crossing a segment reads as a
    // segment boundary and invents a break that is not in the data. The scale
    // at the foot of the stack carries the reference instead.
    track.append(base, band, head);
    track.setAttribute('role', 'img');
    track.setAttribute('aria-label',
      row.model + ': ' + pct(b) + ' without the skill, ' + pct(a) + ' with it, ' +
      signed(row.delta, ' points') + '. ' + pct(100 - hi) + ' of headroom is still open.');
    return track;
  }

  function buildCI(row) {
    var b = row.before && row.before.ci95;
    var a = row.after && row.after.ci95;
    if (!b && !a) return null;
    var wrap = h('div', 'bs-ci');
    var text = [];
    [[b, 'bs-ci-b', row.before], [a, 'bs-ci-a', row.after]].forEach(function (pair) {
      var ci = pair[0];
      if (!ci || !isNum(ci[0]) || !isNum(ci[1])) return;
      var lo = clampPct(ci[0]), hi = clampPct(ci[1]);
      var rule = h('i', pair[1]);
      rule.style.left = lo + '%';
      rule.style.width = Math.max(0, hi - lo) + '%';
      var who = pair[2] && pair[2].label ? pair[2].label : '';
      rule.title = '95% interval, ' + who + ': ' + pct(lo) + ' to ' + pct(hi);
      text.push(who + ' ' + pct(lo) + ' to ' + pct(hi));
      wrap.append(rule);
    });
    if (!wrap.childNodes.length) return null;
    wrap.append(h('span', 'bs-sr', 'Wilson 95% intervals on the pooled trials: ' + text.join('; ') + '.'));
    return wrap;
  }

  function arms(el, result, opts) {
    opts = opts || {};
    mount(el, 'bs-arms', {
      title: opts.title === undefined ? 'Pass rate by model and setup' : opts.title,
      subtitle: opts.subtitle
    });

    var rows = opts.rows || DEFAULT_ROWS;
    var showCI = opts.ci !== false;

    var head = h('div', 'bs-arms-head');
    head.append(h('span', '', ''));
    ['without', 'with', 'delta', 'gain'].forEach(function (k) {
      head.append(h('span', 'bs-h-num', k === 'delta' ? 'Δ' : k));
    });
    head.append(h('span', '', 'pass rate, 0 to 100%'));
    el.append(head);

    var body = h('div', 'bs-arms-body');

    rows.forEach(function (spec) {
      var row = armRowData(result, spec, opts.modelNames);
      var tr = h('div', 'bs-arm-row');

      var name = h('div', 'bs-arm-name');
      name.append(h('span', 'bs-arm-model', row.model));
      if (row.qualifier && row.qualifier !== row.model) {
        name.append(h('span', 'bs-arm-qual', row.qualifier));
      }
      tr.append(name);

      var nums = h('div', 'bs-arm-nums');
      nums.append(numCell('without', pct(row.before && row.before.rate), 'bs-cell-without'));
      nums.append(numCell('with', pct(row.after && row.after.rate), 'bs-cell-with'));
      nums.append(numCell('Δ', signed(row.delta), 'bs-cell-delta', signClass(row.delta)));
      nums.append(numCell('gain', signed(row.gain, '%'), 'bs-cell-gain'));
      tr.append(nums);

      var bar = h('div', 'bs-arm-bar');
      bar.append(buildTrack(row));
      if (showCI) {
        var ci = buildCI(row);
        if (ci) bar.append(ci);
      }
      tr.append(bar);
      body.append(tr);
    });

    el.append(body);

    // The scale lives once at the foot of the stack, in the bar column, so the
    // rows stay a clean read and the zero baseline is still stated.
    var foot = h('div', 'bs-arm-row bs-arms-foot');
    foot.append(h('span'));
    var footNums = h('div', 'bs-arm-nums');
    for (var i = 0; i < 4; i++) footNums.append(h('span'));
    foot.append(footNums);
    var scaleWrap = h('div', 'bs-arm-bar');
    var scale = h('div', 'bs-scale');
    [0, 25, 50, 75, 100].forEach(function (p) {
      var s = h('span', '', p === 0 ? '0' : p === 100 ? '100%' : String(p));
      s.style.left = p + '%';
      scale.append(s);
    });
    scaleWrap.append(scale);
    foot.append(scaleWrap);
    el.append(foot);

    if (opts.legend !== false) {
      var legend = h('div', 'bs-legend');
      [['bs-swatch-base', 'rate without the skill'],
       ['bs-swatch-lift', 'what the skill added'],
       ['bs-swatch-head', 'headroom left to 100%']].forEach(function (pair) {
        var item = h('span');
        item.append(h('i', 'bs-swatch ' + pair[0]), document.createTextNode(pair[1]));
        legend.append(item);
      });
      el.append(legend);
    }

    if (opts.note !== false) {
      el.append(h('p', 'bs-note',
        'gain is the share of the remaining headroom the skill closed, so a rise from a low base ' +
        'and a rise from a high base are not read as the same achievement. The thin rules under each ' +
        'bar are Wilson 95% intervals on the pooled trials.'));
    }
    return el;
  }

  /* ==================================================================
     2. THE 2x2
     ================================================================== */

  function arrowSvg(dir, cls, label) {
    var node;
    if (dir === 'right') {
      node = svg('svg', { width: 46, height: 9, viewBox: '0 0 46 9', 'aria-hidden': 'true', focusable: 'false' });
      node.append(svg('path', { d: 'M0 4.5H39', stroke: 'currentColor', 'stroke-width': '1.5' }));
      node.append(svg('path', { d: 'M38 0.7L45 4.5L38 8.3Z', fill: 'currentColor' }));
    } else {
      node = svg('svg', { width: 9, height: 40, viewBox: '0 0 9 40', 'aria-hidden': 'true', focusable: 'false' });
      node.append(svg('path', { d: 'M4.5 0V33', stroke: 'currentColor', 'stroke-width': '1.5' }));
      node.append(svg('path', { d: 'M0.7 32L4.5 39L8.3 32Z', fill: 'currentColor' }));
    }
    node.setAttribute('class', cls || '');
    return titled(node, label);
  }

  function quadCell(result, arm, area, isSkill, best) {
    var g = gridArm(result, arm);
    var cell = h('div', 'bs-q ' + area + (isSkill ? ' bs-q-skill' : '') + (best ? ' bs-q-best' : ''));
    var halves = labelHalves(g && g.label);
    if (best) cell.title = 'Highest of the four arms.';

    cell.append(h('span', 'bs-q-model', halves.model));

    var top = h('div', 'bs-q-top');
    top.append(h('span', 'bs-q-arm', arm));
    var rate = h('strong', 'bs-q-rate bs-n');
    if (g && isNum(g.rate)) {
      rate.append(document.createTextNode(g.rate.toFixed(1)), h('small', '', '%'));
    } else {
      rate.textContent = NA;
      rate.classList.add('bs-na');
    }
    top.append(rate);
    cell.append(top);
    // Split so the narrow layout, which already prints the model above the
    // number, does not repeat it in the label underneath.
    var lab = h('span', 'bs-q-lab');
    if (g && halves.setup) {
      lab.append(h('span', 'bs-q-lab-model', halves.model + ', '));
      lab.append(document.createTextNode(halves.setup));
    } else {
      lab.textContent = (g && g.label) || 'not run';
    }
    cell.append(lab);

    var bar = h('div', 'bs-q-bar');
    var fill = h('i');
    fill.style.width = (g && isNum(g.rate) ? clampPct(g.rate) : 0) + '%';
    bar.append(fill);
    bar.title = ((g && g.label) || arm) + ': ' + pct(g && g.rate);
    cell.append(bar);
    return cell;
  }

  function deltaBlock(contrast, dir, cls, caption) {
    var wrap = h('div', 'bs-ar ' + cls);
    if (!contrast || !isNum(contrast.delta_points)) {
      wrap.append(h('span', 'bs-ar-cap', 'not measured'));
      return wrap;
    }
    var d = contrast.delta_points;
    var sc = signClass(d);
    var num = h('span', 'bs-ar-num bs-n ' + sc, signed(d));
    var art = arrowSvg(dir, sc, contrast.label + ': ' + signed(d, ' points'));
    wrap.title = contrast.label + ': ' + signed(d, ' points');

    // Horizontal: number over the shaft, in the narrow gutter between cells.
    // Vertical: the gutter is a full cell wide, so the number and its caption
    // sit beside the arrow instead of stacking on top of it.
    if (dir === 'right') {
      wrap.append(num, art, h('span', 'bs-ar-cap', caption));
    } else {
      var txt = h('div', 'bs-ar-txt');
      txt.append(num, h('span', 'bs-ar-cap', caption));
      wrap.append(art, txt);
    }
    return wrap;
  }

  function interaction(el, result, opts) {
    opts = opts || {};
    mount(el, 'bs-inter', {
      title: opts.title === undefined ? 'Model crossed with setup' : opts.title,
      subtitle: opts.subtitle === undefined
        ? 'Moving right adds the candidate skill. Moving down upgrades the model.'
        : opts.subtitle
    });

    var setupLift = findContrast(result, 'A', 'B');
    var modelLift = findContrast(result, 'A', 'C');
    var strongLift = findContrast(result, 'C', 'D');
    var stacked = findContrast(result, 'A', 'D');
    var crossCorner = findContrast(result, 'C', 'B');

    // Which cell is the ceiling, so it can be marked. Read, not assumed.
    var rates = {};
    ['A', 'B', 'C', 'D'].forEach(function (k) {
      var g = gridArm(result, k);
      if (g && isNum(g.rate)) rates[k] = g.rate;
    });
    var best = Object.keys(rates).sort(function (x, y) { return rates[y] - rates[x]; })[0];

    var models = (result && result.grid && result.grid.models) || {};
    var baseName = (opts.modelNames && opts.modelNames.base) || modelName(models.base) || 'base model';
    var strongName = (opts.modelNames && opts.modelNames.strong) || modelName(models.strong) || 'stronger model';

    var g2 = h('div', 'bs-grid2');
    g2.append(h('div', 'bs-hn', 'no skill'));
    g2.append(h('div', 'bs-hs', 'with the candidate skill'));
    g2.append(h('div', 'bs-rowhead bs-rb', baseName));
    g2.append(h('div', 'bs-rowhead bs-rs', strongName));

    g2.append(quadCell(result, 'A', 'bs-qa', false, best === 'A'));
    g2.append(quadCell(result, 'B', 'bs-qb', true, best === 'B'));
    g2.append(quadCell(result, 'C', 'bs-qc', false, best === 'C'));
    g2.append(quadCell(result, 'D', 'bs-qd', true, best === 'D'));

    g2.append(deltaBlock(setupLift, 'right', 'bs-ar-h', 'skill alone'));
    g2.append(deltaBlock(strongLift, 'right', 'bs-ar-h bs-ar-cd', 'skill alone'));
    g2.append(deltaBlock(modelLift, 'down', 'bs-ar-v', 'model alone'));

    // The centre of the matrix is exactly where the A to D diagonal crosses,
    // so the combined delta is annotated there instead of drawing a line that
    // would cut through the four cells.
    var mid = h('div', 'bs-mid');
    if (stacked) {
      mid.append(h('span', 'bs-mid-num bs-n ' + signClass(stacked.delta_points), '↘ ' + signed(stacked.delta_points)));
      mid.append(h('span', 'bs-mid-cap', 'both changes'));
      mid.title = stacked.label + ': ' + signed(stacked.delta_points, ' points');
    } else {
      mid.append(h('span', 'bs-mid-cap', 'both: not measured'));
    }
    g2.append(mid);

    el.append(g2);

    // A spoken version of the same matrix, for anyone not reading the geometry.
    var spoken = ['A', 'B', 'C', 'D'].filter(function (k) { return rates[k] != null; })
      .map(function (k) { return gridArm(result, k).label + ' ' + pct(rates[k]); }).join('; ');
    el.append(h('p', 'bs-sr', 'Pass rate by arm: ' + spoken + '.'));

    if (crossCorner && isNum(crossCorner.delta_points)) {
      var cross = h('p', 'bs-cross');
      cross.append(document.createTextNode('Cross corner: '));
      cross.append(h('b', '', crossCorner.after.label));
      cross.append(document.createTextNode(' beats '));
      cross.append(h('b', '', crossCorner.before.label));
      cross.append(document.createTextNode(' by ' + signed(crossCorner.delta_points, ' points') + '.'));
      el.append(cross);
    }

    if (opts.note !== false && modelLift && isNum(modelLift.delta_points) && modelLift.delta_points < 0) {
      el.append(h('p', 'bs-note',
        'The vertical step is the model upgrade on its own, with the setup held fixed. It is negative here, ' +
        'so the stronger model did not pay for itself until the skill was in place.'));
    }
    return el;
  }

  /* ==================================================================
     3. PER-TASK SMALL MULTIPLES
     ================================================================== */

  /* Deliberately not aggregated. Six tasks times three trials is eighteen
     coin flips per arm, and the only honest way to show that is to draw all
     eighteen. */

  function collectTrials(result, armOrder) {
    // task_id -> arm -> {passed, total}. Contrasts overlap by design (A appears
    // in several), so the first reading of a cell wins and later ones are only
    // checked for agreement.
    var byTask = {};
    var order = [];
    contrastsOf(result).forEach(function (c) {
      if (!Array.isArray(c.pairs) || !c.before || !c.after) return;
      c.pairs.forEach(function (p) {
        if (!p || !p.task_id) return;
        if (!byTask[p.task_id]) { byTask[p.task_id] = {}; order.push(p.task_id); }
        var cell = byTask[p.task_id];
        [['before', c.before.arm], ['after', c.after.arm]].forEach(function (side) {
          var t = p.trials && p.trials[side[0]];
          if (!t || !isNum(t.total)) return;
          if (!cell[side[1]]) cell[side[1]] = { passed: t.passed, total: t.total };
        });
      });
    });
    return { byTask: byTask, order: order };
  }

  function ticks(cell, armLabel, taskId) {
    var total = cell.total, passed = cell.passed;
    var w = 7, gap = 3, hgt = 13;
    var node = svg('svg', {
      width: total * w + (total - 1) * gap,
      height: hgt,
      viewBox: '0 0 ' + (total * w + (total - 1) * gap) + ' ' + hgt,
      role: 'img'
    });
    for (var i = 0; i < total; i++) {
      var pass = i < passed;
      node.append(svg('rect', {
        x: i * (w + gap), y: 0, width: w, height: hgt, rx: 2,
        // Class, not a fill attribute: a var() inside a presentation attribute
        // is not reliably resolved.
        'class': pass ? 'bs-tick-on' : 'bs-tick-off'
      }));
    }
    titled(node, taskId + ', ' + armLabel + ': ' + passed + ' of ' + total + ' trials passed');
    return node;
  }

  function taskGrid(el, result, opts) {
    opts = opts || {};
    mount(el, 'bs-tasks', {
      title: opts.title === undefined ? 'Every trial, task by task' : opts.title,
      subtitle: opts.subtitle === undefined
        ? 'One mark per trial. Filled passed, hollow failed.'
        : opts.subtitle
    });

    var armOrder = opts.arms || ['A', 'B', 'C', 'D'];
    var data = collectTrials(result, armOrder);
    var tasks = data.order.slice().sort();
    if (opts.sort === 'movement') {
      // Movers first: the reason this chart exists is to name which tasks moved.
      var ref = findContrast(result, armOrder[0], armOrder[1]);
      var swing = {};
      if (ref && Array.isArray(ref.pairs)) {
        ref.pairs.forEach(function (p) {
          var b = p.trials.before, a = p.trials.after;
          swing[p.task_id] = Math.abs((a.passed / a.total) - (b.passed / b.total));
        });
      }
      tasks.sort(function (x, y) { return (swing[y] || 0) - (swing[x] || 0) || (x < y ? -1 : 1); });
    }

    var scroll = h('div', 'bs-tg-scroll');
    var table = h('div', 'bs-tg');
    table.style.setProperty('--bs-cols', armOrder.length);

    var head = h('div', 'bs-tg-head');
    head.append(h('span', '', 'task'));
    armOrder.forEach(function (arm) {
      var g = gridArm(result, arm);
      var cell = h('span');
      cell.append(h('b', 'bs-tg-arm', arm));
      var halves = labelHalves(g && g.label);
      if (halves.setup) {
        cell.append(h('span', 'bs-tg-armlab', halves.model));
        cell.append(h('span', 'bs-tg-armlab bs-tg-armset', halves.setup));
      } else {
        cell.append(h('span', 'bs-tg-armlab', (g && g.label) || ''));
      }
      head.append(cell);
    });
    table.append(head);

    if (!tasks.length) {
      table.append(h('p', 'bs-note', 'No per-task trials in this result.'));
    }

    tasks.forEach(function (taskId) {
      var row = h('div', 'bs-tg-row');
      row.append(h('div', 'bs-tg-task', taskId));
      armOrder.forEach(function (arm) {
        var cell = data.byTask[taskId][arm];
        var box = h('div', 'bs-tg-cell');
        if (!cell || !isNum(cell.total) || cell.total === 0) {
          // Explicit, because a blank cell here would be read as a total fail.
          box.append(h('span', 'bs-tg-missing', 'not run'));
        } else {
          var g = gridArm(result, arm);
          box.style.color = (arm === 'B' || arm === 'D' || (g && /with/.test(g.label || '')))
            ? 'var(--blue,#154cff)' : 'var(--ink,#050505)';
          box.append(ticks(cell, (g && g.label) || arm, taskId));
          box.append(h('span', 'bs-tg-count bs-n', cell.passed + '/' + cell.total));
        }
        row.append(box);
      });
      table.append(row);
    });

    scroll.append(table);
    el.append(scroll);

    if (opts.note !== false) {
      var trials = result && result.grid ? result.grid.trials_per_task : null;
      var n = result && result.grid ? result.grid.tasks : null;
      var bits = [];
      if (isNum(n) && isNum(trials)) bits.push(n + ' tasks, ' + trials + ' trials each, so ' + (n * trials) + ' runs per arm.');
      bits.push('An arm with no run for a task is marked not run, never scored as a fail.');
      el.append(h('p', 'bs-note', bits.join(' ')));
    }
    return el;
  }

  global.BSCharts = { arms: arms, interaction: interaction, taskGrid: taskGrid, version: '1.0.0' };
})(typeof window !== 'undefined' ? window : this);
