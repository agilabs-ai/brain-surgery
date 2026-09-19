/*!
 * cloud.js - ambient dithered pixel-cloud background.
 *
 * Portions of the GLSL below (the simplex noise, the pixel-grid quantisation and the
 * ordered Bayer dither it is thresholded against) are derived from Paper Shaders
 * <https://github.com/paper-design/shaders>, Copyright the Paper Shaders authors,
 * licensed under the Apache License, Version 2.0 (the "License"). You may obtain a
 * copy of the License at http://www.apache.org/licenses/LICENSE-2.0
 * Unless required by applicable law or agreed to in writing, software distributed
 * under the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR
 * CONDITIONS OF ANY KIND, either express or implied. See the License for the
 * specific language governing permissions and limitations under the License.
 *
 * Everything else (the mask compositor, mount lifecycle and degradation paths) is
 * original to this file.
 *
 *   BSCloud.mount(element, options) -> handle with .destroy()
 *
 * No imports, no network, no build step. Safe to inline into a single static
 * HTML file and open over file://.
 */
(function (global) {
  'use strict';

  if (!global || !global.document) return;

  var CANVAS_CLASS = 'bs-cloud-canvas';
  var HOST_CLASS = 'bs-cloud-host';
  var ANCHOR_CLASS = 'bs-cloud-anchor';
  var ON_CLASS = 'bs-cloud-on';
  var FALLBACK_CLASS = 'bs-cloud-fallback';
  var KEY = '__bsCloud';

  /* ------------------------------------------------------------------ shaders */

  var VERT = [
    'attribute vec2 a_position;',
    'void main() { gl_Position = vec4(a_position, 0.0, 1.0); }'
  ].join('\n');

  var FRAG = [
    'precision highp float;',
    '',
    'uniform vec2  u_resolution;',   // device pixels
    'uniform float u_pixelRatio;',
    'uniform float u_time;',
    'uniform float u_pxSize;',       // dither cell, CSS px
    'uniform float u_scale;',        // feature size of the cloud
    'uniform float u_dither;',       // 1 random, 2 bayer2, 3 bayer4, 4 bayer8
    'uniform float u_lo;',
    'uniform float u_hi;',
    'uniform float u_ceiling;',
    'uniform vec3  u_color;',
    'uniform float u_opacity;',
    'uniform sampler2D u_mask;',
    '',
    /* --- simplex noise (Paper Shaders / Ashima, Apache-2.0 / MIT lineage) --- */
    'vec3 permute(vec3 x) { return mod(((x * 34.0) + 1.0) * x, 289.0); }',
    'float snoise(vec2 v) {',
    '  const vec4 C = vec4(0.211324865405187, 0.366025403784439,',
    '                     -0.577350269189626, 0.024390243902439);',
    '  vec2 i  = floor(v + dot(v, C.yy));',
    '  vec2 x0 = v - i + dot(i, C.xx);',
    '  vec2 i1 = (x0.x > x0.y) ? vec2(1.0, 0.0) : vec2(0.0, 1.0);',
    '  vec4 x12 = x0.xyxy + C.xxzz;',
    '  x12.xy -= i1;',
    '  i = mod(i, 289.0);',
    '  vec3 p = permute(permute(i.y + vec3(0.0, i1.y, 1.0)) + i.x + vec3(0.0, i1.x, 1.0));',
    '  vec3 m = max(0.5 - vec3(dot(x0, x0), dot(x12.xy, x12.xy), dot(x12.zw, x12.zw)), 0.0);',
    '  m = m * m; m = m * m;',
    '  vec3 x = 2.0 * fract(p * C.www) - 1.0;',
    '  vec3 h = abs(x) - 0.5;',
    '  vec3 ox = floor(x + 0.5);',
    '  vec3 a0 = x - ox;',
    '  m *= 1.79284291400159 - 0.85373472095314 * (a0 * a0 + h * h);',
    '  vec3 g;',
    '  g.x  = a0.x * x0.x + h.x * x0.y;',
    '  g.yz = a0.yz * x12.xz + h.yz * x12.yw;',
    '  return 130.0 * dot(m, g);',
    '}',
    '',
    /* --- ordered dither, computed instead of table-looked-up so this stays GLSL ES 1.00 --- */
    'float bayer2(vec2 a) { a = floor(a); return fract(a.x * 0.5 + a.y * a.y * 0.75); }',
    'float bayer4(vec2 a) { return bayer2(0.5 * a) * 0.25 + bayer2(a); }',
    'float bayer8(vec2 a) { return bayer4(0.5 * a) * 0.25 + bayer2(a); }',
    'float hash21(vec2 p) {',
    '  p = fract(p * vec2(0.3183099, 0.3678794)) + 0.1;',
    '  p += dot(p, p + 19.19);',
    '  return fract(p.x * p.y);',
    '}',
    '',
    'void main() {',
    '  float px = max(1.0, u_pxSize * u_pixelRatio);',
    '  vec2 cell = gl_FragCoord.xy / px;',
    '  vec2 snapped = (floor(cell) + 0.5) * px;',
    '',
    /* cloud field: two drifting octaves, sampled on the quantised grid */
    '  vec2 p = (snapped - 0.5 * u_resolution) / (u_pixelRatio * 900.0 * max(0.05, u_scale));',
    '  float t = 0.5 * u_time;',
    '  float n = 0.5 * snoise(p - vec2(0.0, 0.30 * t));',
    '  n += 0.5 * snoise(2.0 * p + vec2(0.06 * t, 0.32 * t));',
    '  float shape = smoothstep(u_lo, u_hi, 0.5 + 0.5 * n) * u_ceiling;',
    '',
    /* the mask is the whole job: it decides where the cloud is allowed to exist */
    '  vec2 muv = clamp(snapped / u_resolution, 0.0, 1.0);',
    '  shape *= texture2D(u_mask, muv).a;',
    '',
    '  float d;',
    '  if (u_dither < 1.5)      { d = hash21(snapped); }',
    '  else if (u_dither < 2.5) { d = bayer2(cell); }',
    '  else if (u_dither < 3.5) { d = bayer4(cell); }',
    '  else                     { d = bayer8(cell); }',
    '',
    '  float on = step(0.5, shape + d - 0.5);',
    '  float a = on * u_opacity;',
    '  gl_FragColor = vec4(u_color * a, a);',  // premultiplied
    '}'
  ].join('\n');

  /* ------------------------------------------------------------------- helpers */

  function clamp(v, lo, hi) { return v < lo ? lo : (v > hi ? hi : v); }
  function smooth(t) { t = clamp(t, 0, 1); return t * t * (3 - 2 * t); }
  function num(v, d) { v = parseFloat(v); return isFinite(v) ? v : d; }

  var probeCtx = null;
  function normaliseColor(input) {
    if (!input) return null;
    var s = String(input).trim();
    if (!s) return null;
    var m = /^#([0-9a-f]{3,8})$/i.exec(s);
    if (m) {
      var h = m[1];
      if (h.length === 3 || h.length === 4) {
        h = h.split('').map(function (c) { return c + c; }).join('');
      }
      if (h.length === 6 || h.length === 8) {
        return [
          parseInt(h.slice(0, 2), 16) / 255,
          parseInt(h.slice(2, 4), 16) / 255,
          parseInt(h.slice(4, 6), 16) / 255,
          h.length === 8 ? parseInt(h.slice(6, 8), 16) / 255 : 1
        ];
      }
    }
    m = /^rgba?\(([^)]+)\)$/i.exec(s);
    if (m) {
      var parts = m[1].split(/[\s,\/]+/).filter(Boolean);
      if (parts.length >= 3) {
        var ch = function (x) {
          return /%$/.test(x) ? parseFloat(x) / 100 : parseFloat(x) / 255;
        };
        return [
          clamp(ch(parts[0]), 0, 1), clamp(ch(parts[1]), 0, 1), clamp(ch(parts[2]), 0, 1),
          parts.length > 3 ? clamp(num(parts[3], 1), 0, 1) : 1
        ];
      }
    }
    // Last resort: let the 2D canvas resolve named colours / hsl() / oklch().
    try {
      if (!probeCtx) probeCtx = document.createElement('canvas').getContext('2d');
      if (probeCtx) {
        probeCtx.fillStyle = '#000';
        probeCtx.fillStyle = s;
        var resolved = probeCtx.fillStyle;
        if (resolved && resolved !== s) return normaliseColor(resolved);
      }
    } catch (e) { /* ignore */ }
    return null;
  }

  function luminance(rgb) {
    return 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2];
  }

  function mixToward(rgb, target, amount) {
    return [
      rgb[0] + (target[0] - rgb[0]) * amount,
      rgb[1] + (target[1] - rgb[1]) * amount,
      rgb[2] + (target[2] - rgb[2]) * amount
    ];
  }

  function cssVar(name, fallback) {
    try {
      var v = getComputedStyle(document.documentElement).getPropertyValue(name);
      v = v && v.trim();
      return v || fallback;
    } catch (e) { return fallback; }
  }

  /* The ground is whatever actually paints behind the hero. Walk up until something
     is opaque enough to count, then fall back to the page token, then to white. */
  function readGround(el) {
    var node = el;
    while (node && node.nodeType === 1) {
      var bg = null;
      try { bg = getComputedStyle(node).backgroundColor; } catch (e) { bg = null; }
      var rgb = normaliseColor(bg);
      if (rgb && rgb[3] > 0.5) return rgb;
      node = node.parentElement;
    }
    return normaliseColor(cssVar('--bg', '')) || normaliseColor('#ffffff');
  }

  /* A host is very often an `position:absolute; inset:0` overlay, which has no
     intrinsic size of its own and can still measure zero on an early layout pass.
     Fall back to the box such an overlay actually covers, so the canvas is never
     sized 1px tall and then left there. */
  function measureHost(el) {
    var r = el.getBoundingClientRect();
    if (r.width >= 2 && r.height >= 2) return r;
    var p = el.offsetParent || el.parentElement;
    while (p && p.getBoundingClientRect) {
      var pr = p.getBoundingClientRect();
      if (pr.width >= 2 && pr.height >= 2) return pr;
      p = p.parentElement;
    }
    return r;
  }

  /* --------------------------------------------------------------- mask canvas */

  /* Soft-edged rectangle painted into whatever composite op is current.
     Solid core, smoothstep ramps on the four sides, radial ramps in the corners.
     No ctx.filter, so it behaves identically everywhere. */
  function softRect(ctx, x, y, w, h, f, a) {
    if (w <= 0 || h <= 0 || a <= 0) return;
    var STEPS = 8, i, t;

    ctx.fillStyle = 'rgba(0,0,0,' + a + ')';
    ctx.fillRect(x, y, w, h);
    if (f <= 0) return;

    function ramp(g, invert) {
      for (i = 0; i <= STEPS; i++) {
        t = i / STEPS;
        g.addColorStop(t, 'rgba(0,0,0,' + (a * (invert ? smooth(t) : 1 - smooth(t))) + ')');
      }
      return g;
    }

    ctx.fillStyle = ramp(ctx.createLinearGradient(x - f, 0, x, 0), true);
    ctx.fillRect(x - f, y, f, h);
    ctx.fillStyle = ramp(ctx.createLinearGradient(x + w, 0, x + w + f, 0), false);
    ctx.fillRect(x + w, y, f, h);
    ctx.fillStyle = ramp(ctx.createLinearGradient(0, y - f, 0, y), true);
    ctx.fillRect(x, y - f, w, f);
    ctx.fillStyle = ramp(ctx.createLinearGradient(0, y + h, 0, y + h + f), false);
    ctx.fillRect(x, y + h, w, f);

    var corners = [[x, y, -1, -1], [x + w, y, 1, -1], [x, y + h, -1, 1], [x + w, y + h, 1, 1]];
    for (var c = 0; c < corners.length; c++) {
      var cx = corners[c][0], cy = corners[c][1];
      ctx.fillStyle = ramp(ctx.createRadialGradient(cx, cy, 0, cx, cy, f), false);
      ctx.fillRect(corners[c][2] < 0 ? cx - f : cx, corners[c][3] < 0 ? cy - f : cy, f, f);
    }
  }

  function resolveClearTargets(host, list) {
    var out = [];
    if (!list) return out;
    if (!Array.isArray(list)) list = [list];
    for (var i = 0; i < list.length; i++) {
      var item = list[i];
      if (!item) continue;
      var spec = (typeof item === 'string' || item.nodeType === 1) ? { target: item } : item;
      var target = spec.target || spec.el || spec.element || spec.selector;
      if (!target) continue;
      var nodes = [];
      if (target.nodeType === 1) {
        nodes = [target];
      } else {
        try {
          nodes = Array.prototype.slice.call(host.querySelectorAll(target));
          if (!nodes.length) nodes = Array.prototype.slice.call(document.querySelectorAll(target));
        } catch (e) { nodes = []; }
      }
      for (var n = 0; n < nodes.length; n++) {
        out.push({ node: nodes[n], spec: spec });
      }
    }
    return out;
  }

  function buildMask(state) {
    var o = state.options;
    var rect = state.rect || measureHost(state.el);
    var W = Math.max(1, rect.width), H = Math.max(1, rect.height);
    var mw = Math.round(clamp(W / 4, 64, 480));
    var mh = Math.round(clamp(H / 4, 64, 480));

    var cv = state.maskCanvas;
    if (cv.width !== mw) cv.width = mw;
    if (cv.height !== mh) cv.height = mh;
    var ctx = state.maskCtx;
    if (!ctx) return null;

    // Work in host CSS pixels; the transform squashes it into the small mask canvas,
    // so every feather distance below is a real on-screen distance.
    ctx.setTransform(mw / W, 0, 0, mh / H, 0, 0);
    ctx.globalCompositeOperation = 'source-over';
    ctx.clearRect(0, 0, W, H);
    ctx.fillStyle = '#ffffff';
    ctx.fillRect(0, 0, W, H);
    ctx.globalCompositeOperation = 'destination-out';

    var STEPS = 8, i, t, g;

    // 1. Top band stays clear so a nav can sit on plain ground.
    var top = Math.max(0, num(o.topInset, 0));
    if (top > 0) {
      var topFeather = Math.max(8, num(o.topFeather, Math.max(48, top)));
      var total = top + topFeather;
      g = ctx.createLinearGradient(0, 0, 0, total);
      var k = top / total;
      g.addColorStop(0, 'rgba(0,0,0,1)');
      for (i = 0; i <= STEPS; i++) {
        t = i / STEPS;
        g.addColorStop(k + (1 - k) * t, 'rgba(0,0,0,' + (1 - smooth(t)) + ')');
      }
      ctx.fillStyle = g;
      ctx.fillRect(0, 0, W, total);
    }

    // 2. Fade out before the hero ends, so there is no seam against the page below.
    var fb = clamp(num(o.fadeBottom, 0), 0, 1);
    if (fb > 0) {
      var y0 = H * (1 - fb);
      g = ctx.createLinearGradient(0, y0, 0, H);
      for (i = 0; i <= STEPS; i++) {
        t = i / STEPS;
        g.addColorStop(t * 0.88, 'rgba(0,0,0,' + smooth(t) + ')');
      }
      g.addColorStop(1, 'rgba(0,0,0,1)');
      ctx.fillStyle = g;
      ctx.fillRect(0, y0, W, H - y0);
    }

    // 3. Push the content boxes toward transparent, softly.
    // The feather is a fixed pixel distance, which is right on a wide hero but eats a
    // narrow one whole: at 400px the headline and the card, grown by 130px each, leave
    // no field at all. Cap it against the host width so the falloff stays proportional
    // and a little texture survives in the gutters on a phone.
    var narrow = Math.min(1, W / 900);
    var pad = num(o.clearPadding, 18) * (0.6 + 0.4 * narrow);
    var feather = num(o.feather, 130) * (0.45 + 0.55 * narrow);
    var targets = resolveClearTargets(state.el, o.clear);
    for (i = 0; i < targets.length; i++) {
      var node = targets[i].node, spec = targets[i].spec;
      if (!node || !node.getBoundingClientRect) continue;
      var r = node.getBoundingClientRect();
      if (r.width <= 0 || r.height <= 0) continue;
      var p = num(spec.padding, pad);
      var f = Math.max(0, num(spec.feather, feather));
      var strength = clamp(num(spec.strength, 1), 0, 1);
      softRect(ctx, (r.left - rect.left) - p, (r.top - rect.top) - p,
        r.width + p * 2, r.height + p * 2, f, strength);
    }

    ctx.globalCompositeOperation = 'source-over';
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    return cv;
  }

  /* ------------------------------------------------------------------ webgl bits */

  function compile(gl, type, src) {
    var sh = gl.createShader(type);
    if (!sh) return null;
    gl.shaderSource(sh, src);
    gl.compileShader(sh);
    if (!gl.getShaderParameter(sh, gl.COMPILE_STATUS)) {
      gl.deleteShader(sh);
      return null;
    }
    return sh;
  }

  function link(gl, vsSrc, fsSrc) {
    var vs = compile(gl, gl.VERTEX_SHADER, vsSrc);
    var fs = compile(gl, gl.FRAGMENT_SHADER, fsSrc);
    if (!vs || !fs) {
      if (vs) gl.deleteShader(vs);
      if (fs) gl.deleteShader(fs);
      return null;
    }
    var prog = gl.createProgram();
    if (!prog) return null;
    gl.attachShader(prog, vs);
    gl.attachShader(prog, fs);
    gl.linkProgram(prog);
    gl.deleteShader(vs);
    gl.deleteShader(fs);
    if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) {
      gl.deleteProgram(prog);
      return null;
    }
    return prog;
  }

  /* ----------------------------------------------------------------- the mount */

  var DEFAULTS = {
    clear: null,          // selectors / elements whose boxes are pushed toward transparent
    topInset: 0,          // px band kept clear at the top (nav)
    topFeather: null,     // px of softness under that band (default: max(48, topInset))
    fadeBottom: 0.3,      // fraction of host height over which the cloud fades to nothing
    clearPadding: 18,     // px grown around each cleared box before feathering
    feather: 130,         // px of falloff around each cleared box
    accentVar: '--blue',  // page token the accent is read from
    accent: null,         // hard override
    ground: null,         // hard override for the detected page ground
    opacity: null,        // hard override for the final alpha
    pixelSize: 3,         // dither cell size, CSS px
    scale: 0.45,          // cloud feature size
    speed: 0.16,          // drift; 0 renders a single frame
    frame: 2600,          // seed time, also the frame reduced-motion freezes on
    dither: '4x4',        // '2x2' | '4x4' | '8x8' | 'noise'
    density: 0.15,        // -1 .. 1, shifts how much of the field lights up
    maxPixelRatio: 2,
    maxPixels: 2400000,
    fadeIn: false,        // true adds a CSS opacity transition on the first reveal
    resizeDebounce: 120
  };

  var DITHER = { noise: 1, random: 1, '2x2': 2, '4x4': 3, '8x8': 4 };

  function noopHandle(el) {
    return {
      el: el || null,
      canvas: null,
      ok: false,
      destroy: function () {},
      refresh: function () {},
      setOptions: function () {}
    };
  }

  function fail(el, canvas) {
    try { if (canvas && canvas.parentNode) canvas.parentNode.removeChild(canvas); } catch (e) {}
    try {
      if (el && el.classList) {
        el.classList.remove(ON_CLASS);
        el.classList.add(HOST_CLASS);
        el.classList.add(FALLBACK_CLASS);
      }
    } catch (e) {}
  }

  function mount(el, options) {
    if (!el || el.nodeType !== 1) return noopHandle(el);

    // Idempotent: a second mount replaces the first, it never stacks canvases.
    try {
      if (el[KEY] && typeof el[KEY].destroy === 'function') el[KEY].destroy();
      var stale = el.querySelectorAll('canvas.' + CANVAS_CLASS);
      for (var s = 0; s < stale.length; s++) {
        if (stale[s].parentNode) stale[s].parentNode.removeChild(stale[s]);
      }
    } catch (e) {}

    var o = {}, key;
    for (key in DEFAULTS) if (Object.prototype.hasOwnProperty.call(DEFAULTS, key)) o[key] = DEFAULTS[key];
    if (options) for (key in options) if (Object.prototype.hasOwnProperty.call(options, key)) o[key] = options[key];

    var canvas = null, gl = null, state = null, destroyed = false;
    // Declared out here because `teardown` unbinds them; function declarations
    // inside the try block below would be block-scoped under "use strict".
    var onVisibility = null, onResize = null, onMotion = null, refresh = null;
    var onContextRestored = null;

    function teardown(markFallback) {
      if (destroyed) return;
      destroyed = true;
      try { if (state && state.raf) cancelAnimationFrame(state.raf); } catch (e) {}
      try { if (state && state.resizeTimer) clearTimeout(state.resizeTimer); } catch (e) {}
      try { if (state && state.lostTimer) clearTimeout(state.lostTimer); } catch (e) {}
      try { if (state && state.ro) state.ro.disconnect(); } catch (e) {}
      try { if (state && state.io) state.io.disconnect(); } catch (e) {}
      try { if (onVisibility) document.removeEventListener('visibilitychange', onVisibility); } catch (e) {}
      try { if (onResize) global.removeEventListener('resize', onResize); } catch (e) {}
      try { if (state && state.motionMq && onMotion) removeMq(state.motionMq, onMotion); } catch (e) {}
      try { if (canvas) canvas.removeEventListener('webglcontextlost', onContextLost); } catch (e) {}
      try { if (canvas && onContextRestored) canvas.removeEventListener('webglcontextrestored', onContextRestored); } catch (e) {}
      try {
        if (gl && state) {
          if (state.program) gl.deleteProgram(state.program);
          if (state.buffer) gl.deleteBuffer(state.buffer);
          if (state.texture) gl.deleteTexture(state.texture);
          var lose = gl.getExtension('WEBGL_lose_context');
          if (lose) lose.loseContext();
        }
      } catch (e) {}
      try { if (canvas && canvas.parentNode) canvas.parentNode.removeChild(canvas); } catch (e) {}
      try {
        el.classList.remove(ON_CLASS);
        if (markFallback) {
          el.classList.add(FALLBACK_CLASS);
        } else {
          el.classList.remove(HOST_CLASS);
          el.classList.remove(ANCHOR_CLASS);
          el.style.removeProperty('--bs-cloud-top');
        }
      } catch (e) {}
      if (el[KEY] === handle) { try { delete el[KEY]; } catch (e) { el[KEY] = null; } }
    }

    function bail() {
      teardown(true);
    }

    /* A lost context is usually a transient GPU event, so give it one chance to
       come back. Either way the canvas is hidden immediately, so nothing stale or
       half-drawn is ever on screen, and if the restore does not arrive we drop to
       the static fallback and the page still looks finished. */
    function onContextLost(ev) {
      try { ev.preventDefault(); } catch (e) {}
      if (destroyed) return;
      try { if (state && state.raf !== null) { cancelAnimationFrame(state.raf); state.raf = null; } } catch (e) {}
      try { if (canvas) canvas.classList.remove(ON_CLASS); } catch (e) {}
      if (!state || state.restores >= 2) { bail(); return; }
      state.lost = true;
      try { if (state.lostTimer) clearTimeout(state.lostTimer); } catch (e) {}
      state.lostTimer = setTimeout(function () {
        if (!destroyed && state && state.lost) bail();
      }, 2500);
    }

    function addMq(mq, fn) {
      if (!mq) return;
      if (mq.addEventListener) mq.addEventListener('change', fn);
      else if (mq.addListener) mq.addListener(fn);
    }
    function removeMq(mq, fn) {
      if (!mq) return;
      if (mq.removeEventListener) mq.removeEventListener('change', fn);
      else if (mq.removeListener) mq.removeListener(fn);
    }

    function prefersReducedMotion() {
      try {
        return !!(global.matchMedia && global.matchMedia('(prefers-reduced-motion: reduce)').matches);
      } catch (e) { return false; }
    }

    var handle = null;

    try {
      // Claim the host (and expose the nav inset) first, so every failure path
      // below lands on a host that the static CSS fallback can already style.
      el.classList.add(HOST_CLASS);
      el.classList.remove(FALLBACK_CLASS);
      // Only anchor a host that is not already positioned. Forcing position here
      // would flatten an `inset:0` overlay host into a zero-height flow element.
      try {
        if (getComputedStyle(el).position === 'static') el.classList.add(ANCHOR_CLASS);
      } catch (e) { el.classList.add(ANCHOR_CLASS); }
      try { el.style.setProperty('--bs-cloud-top', Math.max(0, num(o.topInset, 0)) + 'px'); } catch (e) {}

      // ---- colour comes from the page, not from the shader -------------------
      var accentRaw = o.accent || cssVar(o.accentVar || '--blue', '') || '#154cff';
      var accent = normaliseColor(accentRaw) || normaliseColor('#154cff');
      var ground = (o.ground && normaliseColor(o.ground)) || readGround(el);
      var groundLum = luminance(ground);
      var dark = groundLum < 0.5;

      // Dark ground: lift the accent toward white and carry a little more alpha,
      // otherwise a mid blue at 12% just disappears into near-black.
      var color = dark ? mixToward(accent, [1, 1, 1], 0.34) : accent.slice(0, 3);
      var opacity = o.opacity !== null && o.opacity !== undefined
        ? clamp(num(o.opacity, 0.13), 0, 1)
        : (dark ? 0.26 : 0.15);

      var density = clamp(num(o.density, 0), -1, 1);
      var lo = clamp(0.40 - density * 0.16, 0.05, 0.95);
      var hi = clamp(1.04 - density * 0.10, lo + 0.05, 1.6);

      canvas = document.createElement('canvas');
      canvas.className = CANVAS_CLASS;
      canvas.setAttribute('aria-hidden', 'true');
      canvas.setAttribute('role', 'presentation');
      canvas.style.pointerEvents = 'none';
      if (o.fadeIn) canvas.classList.add('bs-cloud-fade');

      var attrs = {
        alpha: true,
        premultipliedAlpha: true,
        antialias: false,
        depth: false,
        stencil: false,
        preserveDrawingBuffer: false,
        powerPreference: 'low-power',
        failIfMajorPerformanceCaveat: false
      };
      gl = canvas.getContext('webgl', attrs) || canvas.getContext('experimental-webgl', attrs);
      if (!gl) { fail(el, canvas); return noopHandle(el); }

      // All GL-side resources live in one place so they can be rebuilt after a
      // context restore without re-running the whole mount.
      var program = null, buffer = null, texture = null, U = {};

      function setupGL() {
        program = link(gl, VERT, FRAG);
        if (!program) return false;

        buffer = gl.createBuffer();
        gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
        gl.bufferData(gl.ARRAY_BUFFER,
          new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
        var loc = gl.getAttribLocation(program, 'a_position');
        gl.enableVertexAttribArray(loc);
        gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);

        texture = gl.createTexture();
        gl.activeTexture(gl.TEXTURE0);
        gl.bindTexture(gl.TEXTURE_2D, texture);
        gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, true);
        gl.pixelStorei(gl.UNPACK_PREMULTIPLY_ALPHA_WEBGL, false);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);

        U = {};
        ['u_resolution', 'u_pixelRatio', 'u_time', 'u_pxSize', 'u_scale', 'u_dither',
          'u_lo', 'u_hi', 'u_ceiling', 'u_color', 'u_opacity', 'u_mask'].forEach(function (n) {
          U[n] = gl.getUniformLocation(program, n);
        });

        gl.useProgram(program);
        gl.uniform1i(U.u_mask, 0);
        gl.uniform1f(U.u_pxSize, Math.max(1, num(o.pixelSize, 3)));
        gl.uniform1f(U.u_scale, num(o.scale, 0.62));
        gl.uniform1f(U.u_dither, DITHER[String(o.dither)] || 3);
        gl.uniform1f(U.u_lo, lo);
        gl.uniform1f(U.u_hi, hi);
        gl.uniform1f(U.u_ceiling, 0.94);
        gl.uniform3f(U.u_color, color[0], color[1], color[2]);
        gl.uniform1f(U.u_opacity, opacity);
        gl.disable(gl.DEPTH_TEST);
        gl.clearColor(0, 0, 0, 0);

        if (state) { state.program = program; state.buffer = buffer; state.texture = texture; }
        return true;
      }

      var maskCanvas = document.createElement('canvas');
      var maskCtx = null;
      try { maskCtx = maskCanvas.getContext('2d'); } catch (e) { maskCtx = null; }
      if (!maskCtx) { fail(el, canvas); return noopHandle(el); }

      state = {
        el: el, options: o, program: null, buffer: null, texture: null,
        maskCanvas: maskCanvas, maskCtx: maskCtx,
        raf: null, resizeTimer: null, ro: null, io: null, motionMq: null,
        rect: null, retries: 0, lost: false, lostTimer: null, restores: 0,
        w: 0, h: 0, ratio: 1, time: num(o.frame, 0) * 0.001,
        last: 0, inView: true, painted: false,
        still: prefersReducedMotion() || num(o.speed, 0) === 0
      };

      if (!setupGL()) { fail(el, canvas); return noopHandle(el); }

      el.insertBefore(canvas, el.firstChild);

      function sizeCanvas() {
        var rect = measureHost(el);
        state.rect = rect;
        var cssW = Math.max(1, Math.round(rect.width));
        var cssH = Math.max(1, Math.round(rect.height));
        var dpr = clamp(global.devicePixelRatio || 1, 1, Math.max(1, num(o.maxPixelRatio, 2)));
        var maxPx = Math.max(100000, num(o.maxPixels, 2400000));
        var w = Math.round(cssW * dpr), h = Math.round(cssH * dpr);
        if (w * h > maxPx) {
          var k = Math.sqrt(maxPx / (w * h));
          w = Math.max(1, Math.round(w * k));
          h = Math.max(1, Math.round(h * k));
          dpr = w / cssW;
        }
        if (canvas.width !== w || canvas.height !== h) {
          canvas.width = w;
          canvas.height = h;
        }
        state.w = w; state.h = h; state.ratio = dpr;
        return rect.width >= 2 && rect.height >= 2;
      }

      function uploadMask() {
        var cv = buildMask(state);
        if (!cv) return false;
        gl.activeTexture(gl.TEXTURE0);
        gl.bindTexture(gl.TEXTURE_2D, texture);
        gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, cv);
        return true;
      }

      function draw() {
        if (destroyed) return;
        if (!state.w || !state.h) return;
        gl.viewport(0, 0, state.w, state.h);
        gl.useProgram(program);
        gl.activeTexture(gl.TEXTURE0);
        gl.bindTexture(gl.TEXTURE_2D, texture);
        gl.uniform2f(U.u_resolution, state.w, state.h);
        gl.uniform1f(U.u_pixelRatio, state.ratio);
        gl.uniform1f(U.u_time, state.time);
        gl.clear(gl.COLOR_BUFFER_BIT);
        gl.enable(gl.BLEND);
        gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA);
        gl.drawArrays(gl.TRIANGLES, 0, 3);
        if (!state.painted) {
          // The frame above is complete, so revealing now can never show a partial one.
          state.painted = true;
          canvas.classList.add(ON_CLASS);
        }
      }

      refresh = function () {
        if (destroyed || (state && state.lost)) return;
        try {
          if (!sizeCanvas()) {
            // Layout has not settled (or the host is momentarily collapsed).
            // Come back for a few frames rather than sitting on a 1px canvas.
            if (state.retries < 12) {
              state.retries++;
              requestAnimationFrame(function () { if (!destroyed) refresh(); });
            }
            return;
          }
          state.retries = 0;
          if (!uploadMask()) { bail(); return; }
          draw();
        } catch (e) { bail(); }
      };

      function tick(now) {
        state.raf = null;
        if (destroyed || state.still) return;
        var dt = state.last ? Math.min(64, now - state.last) : 16;
        state.last = now;
        state.time += dt * 0.001 * num(o.speed, 0.16);
        try { draw(); } catch (e) { bail(); return; }
        state.raf = requestAnimationFrame(tick);
      }

      function shouldRun() {
        if (destroyed || state.still || state.lost) return false;
        if (document.hidden) return false;
        return state.inView;
      }

      function sync() {
        if (shouldRun()) {
          if (state.raf === null) {
            state.last = 0;
            state.raf = requestAnimationFrame(tick);
          }
        } else if (state.raf !== null) {
          cancelAnimationFrame(state.raf);
          state.raf = null;
        }
      }

      onVisibility = function () { sync(); };

      onResize = function () {
        if (destroyed) return;
        if (state.resizeTimer) clearTimeout(state.resizeTimer);
        state.resizeTimer = setTimeout(function () {
          state.resizeTimer = null;
          refresh();
        }, Math.max(0, num(o.resizeDebounce, 120)));
      };

      onMotion = function () {
        if (destroyed) return;
        state.still = prefersReducedMotion() || num(o.speed, 0) === 0;
        if (state.still) {
          if (state.raf !== null) { cancelAnimationFrame(state.raf); state.raf = null; }
          state.time = num(o.frame, 0) * 0.001;
          try { draw(); } catch (e) { bail(); }
        } else {
          sync();
        }
      };

      onContextRestored = function () {
        if (destroyed || !state || !state.lost) return;
        state.lost = false;
        state.restores++;
        if (state.lostTimer) { clearTimeout(state.lostTimer); state.lostTimer = null; }
        try {
          if (!setupGL()) { bail(); return; }
          state.painted = false;
          state.retries = 0;
          refresh();
          sync();
        } catch (e) { bail(); }
      };

      canvas.addEventListener('webglcontextlost', onContextLost, false);
      canvas.addEventListener('webglcontextrestored', onContextRestored, false);

      if (global.ResizeObserver) {
        state.ro = new ResizeObserver(onResize);
        state.ro.observe(el);
      } else {
        global.addEventListener('resize', onResize);
      }

      if (global.IntersectionObserver) {
        state.io = new IntersectionObserver(function (entries) {
          for (var i = 0; i < entries.length; i++) state.inView = entries[i].isIntersecting;
          sync();
        }, { rootMargin: '120px' });
        state.io.observe(el);
      }

      document.addEventListener('visibilitychange', onVisibility);

      try {
        state.motionMq = global.matchMedia && global.matchMedia('(prefers-reduced-motion: reduce)');
        addMq(state.motionMq, onMotion);
      } catch (e) {}

      refresh();
      sync();

      // Late layout (webfonts, images) moves the boxes the mask was cut around.
      if (document.fonts && document.fonts.ready && document.fonts.ready.then) {
        document.fonts.ready.then(function () { if (!destroyed) refresh(); }, function () {});
      }
      global.addEventListener('load', function () { if (!destroyed) refresh(); }, { once: true });

      handle = {
        el: el,
        canvas: canvas,
        ok: true,
        options: o,
        refresh: refresh,
        destroy: function () { teardown(false); }
      };
      el[KEY] = handle;
      return handle;

    } catch (err) {
      try { teardown(true); } catch (e) {}
      fail(el, canvas);
      return noopHandle(el);
    }
  }

  global.BSCloud = {
    version: '1.0.0',
    defaults: DEFAULTS,
    mount: mount,
    get: function (el) { return (el && el[KEY]) || null; },
    destroy: function (el) {
      if (el && el[KEY] && el[KEY].destroy) el[KEY].destroy();
    }
  };

})(typeof window !== 'undefined' ? window : this);
