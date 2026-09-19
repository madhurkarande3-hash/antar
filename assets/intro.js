/* ANTAR intro: "The Watching Circle"
   Designed by Star (Madhur Karande) in Claude Design. Ported to plain JavaScript so it
   starts instantly with no React, Babel or runtime: same geometry, cues, easing and fonts.
   Every frame is a pure function of the clock T, exactly like the original.

   Usage: AntarIntro.play(overlayElement, { mode: 'full' | 'short', onDone })
*/
(function () {
  'use strict';
  var Easing = {
    easeOutQuad: function (t) { return t * (2 - t); },
    easeOutCubic: function (t) { return (--t) * t * t + 1; },
    easeInOutSine: function (t) { return -(Math.cos(Math.PI * t) - 1) / 2; },
    easeInExpo: function (t) { return t === 0 ? 0 : Math.pow(2, 10 * (t - 1)); },
    easeOutBack: function (t) { var c1 = 1.70158, c3 = c1 + 1; return 1 + c3 * Math.pow(t - 1, 3) + c1 * Math.pow(t - 1, 2); }
  };
  var clamp = function (v, lo, hi) { return Math.max(lo, Math.min(hi, v)); };

  /* Scenes and settings exactly as authored */
  var SCENES = [['Void', .6], ['Spark', .6], ['InnerCircle', .8], ['Construct', .9], ['OuterRings', .9], ['Glyphs', .7],
                ['Settle', .6], ['EyeOpen', 1.4], ['Notice', .6], ['Hold', .8], ['Surge', 1.0], ['Reveal', 2.6]];
  var CUES = {}, TOTAL = 0;
  SCENES.forEach(function (s) { CUES[s[0]] = Math.round(TOTAL * 1000) / 1000; TOTAL += s[1]; });
  TOTAL = Math.round(TOTAL * 1000) / 1000;
  var P = { logoText: '* A.N.T.A.R. *', subtitle: 'we will keep you alive', circleScale: 0.71, detail: 'dense',
            imperfections: true, rotationSpeed: 1, eyeSize: 1.5, lineBrightness: 1.6, glow: 2, particleDensity: 2.5, silver: '#dfe8e6' };

  /* ── 1. CONFIGURATION ───────────────────────────────────────────────────── */
  var CONFIG = {
    STAGE_W: 1920,
    STAGE_H: 1080,
    OUTER_FRAC: 0.86,     // outermost ring diameter ÷ stage height
    EYE_RISE: 0.075,      // eye sits this fraction of R ABOVE true centre
    EYE_SIZE: 1,
    LINE_BRIGHTNESS: 1,
    GLOW: 1,
    ROTATION: 1,          // global rotation-speed multiplier
    PARTICLES: 1,         // density multiplier (base count below)
    PARTICLE_BASE: 44,
    DETAIL: 1,            // glyph / tick density multiplier
    SILVER: '#dfe5ee',
    PARALLAX_PX: 10,      // max cursor parallax offset, in stage units
    IMPERFECTIONS: true,
    SEED: 20260917,
    INK: { l1: 0.24, l2: 0.58, l3: 0.92 },              // three intensity levels
    STROKE: { micro: 1.3, thin: 1.7, mid: 2.3, major: 3.1 },
  };

  /* ── 2. PRIMITIVES ──────────────────────────────────────────────────────── */
  var TAU = Math.PI * 2;
  var D = Math.PI / 180;

  function rngFrom(seed) {
    var a = seed >>> 0;
    return function () {
      a = (a + 0x6D2B79F5) | 0;
      var t = Math.imul(a ^ (a >>> 15), 1 | a);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }
  function n2(v) { return Math.round(v * 100) / 100; }
  function px(r, a) { return [r * Math.cos(a), r * Math.sin(a)]; }

  // All path builders are centred on (0,0) so their layer <g> can rotate freely.
  function pRing(r) {
    return 'M0 ' + n2(-r) + 'A' + n2(r) + ' ' + n2(r) + ' 0 0 1 0 ' + n2(r) +
           'A' + n2(r) + ' ' + n2(r) + ' 0 0 1 0 ' + n2(-r);
  }
  function pArc(r, a0, a1) {
    var p0 = px(r, a0), p1 = px(r, a1), d = a1 - a0;
    return 'M' + n2(p0[0]) + ' ' + n2(p0[1]) + 'A' + n2(r) + ' ' + n2(r) + ' 0 ' +
           (Math.abs(d) > Math.PI ? 1 : 0) + ' ' + (d > 0 ? 1 : 0) + ' ' +
           n2(p1[0]) + ' ' + n2(p1[1]);
  }
  function pSpoke(r0, r1, a) {
    var p0 = px(r0, a), p1 = px(r1, a);
    return 'M' + n2(p0[0]) + ' ' + n2(p0[1]) + 'L' + n2(p1[0]) + ' ' + n2(p1[1]);
  }
  function pPoly(r, n, step, rot) {
    var d = '';
    for (var i = 0; i <= n; i++) {
      var p = px(r, rot + ((i * step) % n) * TAU / n);
      d += (i ? 'L' : 'M') + n2(p[0]) + ' ' + n2(p[1]);
    }
    return d;
  }
  function pDot(cx, cy, rad) {
    return 'M' + n2(cx - rad) + ' ' + n2(cy) +
           'a' + n2(rad) + ' ' + n2(rad) + ' 0 1 0 ' + n2(rad * 2) + ' 0' +
           'a' + n2(rad) + ' ' + n2(rad) + ' 0 1 0 ' + n2(-rad * 2) + ' 0';
  }

  // An invented alphabet: each glyph is a handful of strokes in a unit box.
  // { l: polyline points } or { a: [cx, cy, r, deg0, deg1] } arc.
  var GLYPHS = [
    [{ l: [[0, -0.5], [0, 0.5]] }, { l: [[-0.34, -0.16], [0.34, -0.16]] }, { l: [[-0.2, 0.32], [0.2, 0.32]] }],
    [{ l: [[-0.4, -0.42], [0.4, -0.42], [0, 0.5], [-0.4, -0.42]] }],
    [{ a: [0, 0, 0.4, -90, 150] }, { l: [[0, -0.4], [0, 0.42]] }],
    [{ l: [[-0.4, 0.4], [0, -0.45], [0.4, 0.4]] }, { l: [[-0.2, 0.04], [0.2, 0.04]] }],
    [{ l: [[-0.34, -0.42], [0.34, -0.42]] }, { l: [[0, -0.42], [0, 0.08]] }, { a: [0, 0.24, 0.22, -175, 175] }],
    [{ l: [[-0.38, -0.3], [0.38, 0.3]] }, { l: [[0.38, -0.3], [-0.38, 0.3]] }, { l: [[0, -0.5], [0, 0.5]] }],
    [{ a: [0, 0, 0.44, 25, 335] }, { l: [[-0.24, 0], [0.24, 0]] }],
    [{ l: [[-0.3, -0.45], [-0.3, 0.45]] }, { l: [[-0.3, -0.45], [0.3, -0.02]] }, { l: [[-0.3, 0.08], [0.26, 0.45]] }],
    [{ l: [[0, -0.5], [0.34, 0], [0, 0.5], [-0.34, 0], [0, -0.5]] }],
    [{ l: [[-0.36, -0.26], [0.36, -0.26]] }, { l: [[-0.26, 0.04], [0.26, 0.04]] }, { l: [[-0.14, 0.34], [0.14, 0.34]] }],
    [{ a: [0, -0.1, 0.28, 180, 360] }, { l: [[0, 0.14], [0, 0.48]] }, { l: [[-0.2, 0.48], [0.2, 0.48]] }],
    [{ l: [[-0.4, 0.44], [0, -0.5], [0.4, 0.44], [-0.4, 0.44]] }, { l: [[0, -0.12], [0, 0.44]] }],
    [{ a: [0, 0, 0.42, -60, 60] }, { a: [0, 0, 0.42, 120, 240] }, { l: [[0, -0.2], [0, 0.2]] }],
    [{ l: [[0, -0.48], [0, 0.48]] }, { a: [0, -0.2, 0.2, -90, 90] }, { a: [0, 0.2, 0.2, 90, 270] }],
    [{ l: [[-0.36, -0.36], [0.36, -0.36], [0.36, 0.36]] }, { l: [[-0.36, 0.1], [0.1, 0.1]] }],
    [{ a: [0, 0, 0.34, 0, 350] }, { l: [[-0.46, 0], [-0.34, 0]] }, { l: [[0.34, 0], [0.46, 0]] }],
  ];

  function pGlyph(gi, cx, cy, s, rot) {
    var g = GLYPHS[((gi % GLYPHS.length) + GLYPHS.length) % GLYPHS.length];
    var co = Math.cos(rot), si = Math.sin(rot);
    function T(x, y) { return [cx + (x * co - y * si) * s, cy + (x * si + y * co) * s]; }
    var d = '';
    for (var i = 0; i < g.length; i++) {
      var st = g[i], j, q;
      if (st.l) {
        for (j = 0; j < st.l.length; j++) {
          q = T(st.l[j][0], st.l[j][1]);
          d += (j ? 'L' : 'M') + n2(q[0]) + ' ' + n2(q[1]);
        }
      } else {
        var a0 = st.a[3] * D, a1 = st.a[4] * D, rr = st.a[2] * s;
        var q0 = T(st.a[0] + st.a[2] * Math.cos(a0), st.a[1] + st.a[2] * Math.sin(a0));
        var q1 = T(st.a[0] + st.a[2] * Math.cos(a1), st.a[1] + st.a[2] * Math.sin(a1));
        d += 'M' + n2(q0[0]) + ' ' + n2(q0[1]) + 'A' + n2(rr) + ' ' + n2(rr) + ' 0 ' +
             (Math.abs(a1 - a0) > Math.PI ? 1 : 0) + ' ' + (a1 > a0 ? 1 : 0) + ' ' +
             n2(q1[0]) + ' ' + n2(q1[1]);
      }
    }
    return d;
  }

  /* ── 3. GEOMETRY ────────────────────────────────────────────────────────────
     One pass builds every layer. A layer carries its own drift rate, how
     strongly it re-centres on the eye later (`follow`), and a deliberate
     offset (`dx`,`dy`) where the structure is meant to be imperfect.
     An element carries: d (path), w (stroke), lvl (1|2|3 intensity),
     rN (normalised radius — drives the illumination wave), st (0..1 stagger).
     Repetitive furniture (tick rings, spoke fans) is MERGED into one
     multi-subpath path so the dash reveal writes it around the circle
     tick-by-tick at the cost of a single DOM node.
  ── */
  function buildCircle(R, opt) {
    var dm = opt.detail, imp = opt.imperfections, S = opt.stroke;
    var rng = rngFrom(opt.seed);
    var layers = [];
    var i;

    function L(key, phase, rate, o) {
      o = o || {};
      var l = {
        key: key, phase: phase, rate: rate,
        pulse: o.pulse || 0, follow: o.follow || 0, recede: o.recede || 0,
        dx: o.dx || 0, dy: o.dy || 0, ph: rng() * TAU, els: [],
      };
      layers.push(l);
      return l;
    }
    function E(l, d, w, lvl, rN, st) { l.els.push({ d: d, w: w, lvl: lvl, rN: rN, st: st }); }
    function cnt(n) { return Math.max(4, Math.round(n * dm)); }
    function merged(n, fn) { var d = ''; for (var k = 0; k < n; k++) d += fn(k); return d; }

    /* A — the core sigil. Pulses instead of rotating; dissolves before the eye. */
    var A = L('core', 'core', 0, { pulse: 0.55, follow: 1 });
    E(A, pRing(R * 0.030), S.mid, 3, 0.030, 0.00);
    E(A, pRing(R * 0.062), S.thin, 2, 0.062, 0.25);
    E(A, merged(8, function (k) { return pSpoke(R * 0.066, R * 0.082, k * TAU / 8 + 11 * D); }), S.micro, 1, 0.075, 0.50);
    E(A, merged(4, function (k) { var p = px(R * 0.098, k * TAU / 4 + 45 * D); return pDot(p[0], p[1], R * 0.0045); }), S.micro, 2, 0.098, 0.80);

    /* B — the first true ring, its triangle, and three arcs (one cut short). */
    var B = L('inner', 'inner', -1.5, { follow: 0.85, recede: 0.55 });
    E(B, pRing(R * 0.186), S.major, 3, 0.186, 0.00);
    E(B, pRing(R * 0.199), S.micro, 1, 0.199, 0.35);
    E(B, pPoly(R * 0.162, 3, 1, -90 * D), S.thin, 2, 0.162, 0.20);
    E(B, merged(12, function (k) { return pSpoke(R * 0.199, R * 0.217, k * TAU / 12); }), S.micro, 1, 0.208, 0.55);
    E(B, pArc(R * 0.234, 8 * D, 100 * D), S.thin, 2, 0.234, 0.70);
    E(B, pArc(R * 0.234, 128 * D, imp ? 194 * D : 214 * D), S.thin, 2, 0.234, 0.80);
    E(B, pArc(R * 0.234, 242 * D, 334 * D), S.thin, 2, 0.234, 0.90);

    /* C — heptagon + heptagram construction with node points. */
    var C = L('mid1', 'mid', -0.55, { follow: 0.5, recede: 0.34 });
    E(C, pRing(R * 0.262), S.mid, 2, 0.262, 0.00);
    E(C, pRing(R * 0.274), S.micro, 1, 0.274, 0.30);
    E(C, pPoly(R * 0.262, 7, 1, -90 * D), S.thin, 1, 0.262, 0.20);
    E(C, pPoly(R * 0.262, 7, 3, -84 * D), S.thin, 2, 0.262, 0.45);
    E(C, merged(7, function (k) { var p = px(R * 0.262, -90 * D + k * TAU / 7); return pDot(p[0], p[1], R * 0.010); }), S.thin, 3, 0.262, 0.60);
    E(C, merged(cnt(24), function (k) { return pSpoke(R * 0.274, R * 0.288, k * TAU / cnt(24)); }), S.micro, 1, 0.281, 0.75);

    /* D — arc group band, drifting the other way. */
    var Dl = L('mid2', 'mid', 1.25, { follow: 0.35, recede: 0.14 });
    E(Dl, pRing(R * 0.336), S.micro, 1, 0.336, 0.10);
    for (i = 0; i < 6; i++) {
      E(Dl, pArc(R * 0.354, i * 60 * D + 6 * D, i * 60 * D + 54 * D), S.mid, 2, 0.354, 0.25 + i * 0.05);
    }
    E(Dl, merged(6, function (k) { return pArc(R * 0.322, k * 60 * D + 36 * D, k * 60 * D + 58 * D); }), S.micro, 1, 0.322, 0.50);
    E(Dl, merged(12, function (k) { return pSpoke(R * 0.336, R * 0.354, k * TAU / 12 + 3 * D); }), S.micro, 1, 0.345, 0.65);
    E(Dl, merged(3, function (k) { var a = k * TAU / 3 - 90 * D, p = px(R * 0.384, a); return pGlyph(8, p[0], p[1], R * 0.038, a + 90 * D); }), S.thin, 2, 0.384, 0.85);

    /* E — inner rune band. One glyph is deliberately askew. */
    var Eb = L('glyphIn', 'glyph', -0.42, { follow: 0.25 });
    var gn = cnt(24);
    E(Eb, pRing(R * 0.452), S.micro, 1, 0.452, 0.00);
    E(Eb, pRing(R * 0.516), S.micro, 1, 0.516, 0.06);
    for (i = 0; i < gn; i++) {
      var a = i * TAU / gn - 90 * D;
      var skew = (imp && i === 7) ? 22 * D : 0;
      var pg = px(R * 0.484, a);
      E(Eb, pGlyph(3 + i * 5, pg[0], pg[1], R * 0.034, a + 90 * D + skew), S.thin, 2, 0.484, 0.12 + 0.84 * (i / gn));
    }
    E(Eb, merged(gn, function (k) { return pSpoke(R * 0.452, R * 0.464, (k + 0.5) * TAU / gn - 90 * D); }), S.micro, 1, 0.458, 0.55);

    /* F — the primary ring: nonagram, node dots, radial divisions. */
    var F = L('primary', 'outer', 0.48, { pulse: 0.18, follow: 0.15 });
    E(F, pRing(R * 0.588), S.major, 3, 0.588, 0.00);
    E(F, pRing(R * 0.575), S.micro, 1, 0.575, 0.18);
    E(F, pPoly(R * 0.588, 9, 2, -90 * D), S.thin, 2, 0.588, 0.30);
    E(F, merged(9, function (k) { var p = px(R * 0.588, -90 * D + k * TAU / 9); return pDot(p[0], p[1], R * 0.008); }), S.thin, 3, 0.588, 0.50);
    E(F, merged(cnt(18), function (k) { return pSpoke(R * 0.588, R * 0.660, k * TAU / cnt(18) - 90 * D); }), S.micro, 1, 0.624, 0.62);
    E(F, pRing(R * 0.660), S.thin, 2, 0.660, 0.80);

    /* G — astronomical marks. This whole ring sits a few pixels off true. */
    var G = L('astro', 'outer', -0.26, { follow: 0.1, dx: imp ? 3 : 0, dy: imp ? -2.5 : 0 });
    E(G, pRing(R * 0.706), S.micro, 1, 0.706, 0.05);
    E(G, pPoly(R * 0.706, 13, 5, 14 * D), S.micro, 1, 0.706, 0.20);
    for (i = 0; i < 8; i++) {
      var ag = i * 45 * D + 22.5 * D, pm = px(R * 0.706, ag);
      E(G, pGlyph(10 + i * 3, pm[0], pm[1], R * 0.030, ag + 90 * D), S.thin, 2, 0.706, 0.30 + i * 0.045);
    }
    for (i = 0; i < 4; i++) {
      var span = (imp && i === 2) ? 34 * D : 62 * D;   // one arc left unfinished
      E(G, pArc(R * 0.726, i * 90 * D + 14 * D, i * 90 * D + 14 * D + span), S.mid, 2, 0.726, 0.62 + i * 0.07);
    }

    /* H — the rim: segmented ring, microscopic ticks, four directional marks. */
    var H = L('rim', 'outer', 0.20, { follow: 0.05 });
    for (i = 0; i < 8; i++) {
      E(H, pArc(R * 0.792, i * 45 * D + 3 * D, i * 45 * D + 42 * D), S.mid, 2, 0.792, 0.10 + i * 0.045);
    }
    E(H, pRing(R * 0.806), S.micro, 1, 0.806, 0.45);
    var tn = cnt(60);
    E(H, merged(tn, function (k) { return pSpoke(R * 0.806, R * (k % 5 === 0 ? 0.828 : 0.818), k * TAU / tn); }), S.micro, 1, 0.814, 0.55);
    for (i = 0; i < 4; i++) {
      var ad = i * 90 * D - 90 * D, pd = px(R * 0.850, ad);
      E(H, pGlyph(1, pd[0], pd[1], R * 0.028, ad + 90 * D), S.thin, 3, 0.850, 0.76 + i * 0.04);
    }

    /* I — outermost rune band and the hairline that closes the circle. */
    var I = L('outermost', 'glyph', -0.14, { follow: 0 });
    var on = cnt(32);
    E(I, pRing(R * 0.902), S.micro, 1, 0.902, 0.10);
    for (i = 0; i < on; i++) {
      var sk = (imp && i > on * 0.62) ? 4.5 * D : 0;   // the spacing opens up once
      var ao = i * TAU / on - 90 * D + sk, po = px(R * 0.945, ao);
      E(I, pGlyph(2 + i * 7, po[0], po[1], R * 0.026, ao + 90 * D), S.micro, 1, 0.945, 0.15 + 0.78 * (i / on));
    }
    E(I, pRing(R * 0.988), S.thin, 2, 0.988, 0.92);
    E(I, merged(4, function (k) {
      var ar = k * 90 * D - 90 * D, pr = px(R * 0.988, ar);
      return pDot(pr[0], pr[1], R * 0.006) + pSpoke(R * 0.966, R * 1.010, ar);
    }), S.thin, 2, 0.988, 0.96);

    /* J — the long radial divisions that tie the whole structure together. */
    var J = L('radials', 'outer', 0.05, { follow: 0.2 });
    E(J, merged(12, function (k) {
      return pSpoke(R * 0.252, R * 0.792, k * TAU / 12 - 90 * D + ((imp && k === 5) ? 2.6 * D : 0));
    }), S.micro, 1, 0.48, 0.00);
    E(J, merged(cnt(24), function (k) {
      return pSpoke(R * 0.588, R * 0.706, k * TAU / cnt(24) - 90 * D + 7.5 * D);
    }), S.micro, 1, 0.647, 0.40);

    return { layers: layers };
  }

  /* ── 4. MOTION ──────────────────────────────────────────────────────────── */
  function ease(fn, a, b, T) { return fn(clamp((T - a) / Math.max(1e-4, b - a), 0, 1)); }
  var MOTION = {
    enter: function (a, b, T) { return ease(Easing.easeOutCubic, a, b, T); },
    draw:  function (a, b, T) { return ease(Easing.easeInOutSine, a, b, T); },
    pop:   function (a, b, T) { return ease(Easing.easeOutBack, a, b, T); },
  };
  // A gaussian illumination front travelling out through the geometry.
  function wave(rN, front, w) {
    if (front < -1) return 0;
    var d = (rN - front) / w;
    return Math.exp(-d * d * 0.5);
  }


  var NS = 'http://www.w3.org/2000/svg';
  function el(tag, attrs, parent) {
    var n = document.createElementNS(NS, tag);
    for (var k in attrs) n.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(n);
    return n;
  }
  function set(n, k, v) { if (n['_' + k] !== v) { n['_' + k] = v; n.setAttribute(k, v); } }

  function play(host, opts) {
    opts = opts || {};
    var reduced = !!(window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches);
    var W = CONFIG.STAGE_W, H = CONFIG.STAGE_H, cx = W / 2, cy = H / 2;
    var R = H * 0.5 * P.circleScale, eyeSize = P.eyeSize, glow = P.glow, bright = P.lineBrightness;
    var rot = reduced ? 0 : P.rotationSpeed, silver = P.silver, INK = CONFIG.INK;
    var dm = P.detail === 'low' ? 0.6 : P.detail === 'dense' ? 1.3 : 1;
    var geo = buildCircle(R, { seed: CONFIG.SEED, detail: dm, imperfections: P.imperfections, stroke: CONFIG.STROKE });

    /* ---- build the scene graph once ---- */
    host.innerHTML = '';
    var svg = el('svg', { 'class': 'twc-svg', preserveAspectRatio: 'xMidYMid meet' }, host);
    var defs = el('defs', {}, svg);
    var vig = el('radialGradient', { id: 'twc-vig', cx: '50%', cy: '50%', r: '78%' }, defs);
    [['0%', '#0b0b0d'], ['35%', '#090909'], ['68%', '#050505'], ['100%', '#000000']].forEach(function (s) { el('stop', { offset: s[0], 'stop-color': s[1] }, vig); });
    var eg = el('radialGradient', { id: 'twc-eyeglow' }, defs);
    [['0%', .42], ['40%', .09], ['100%', 0]].forEach(function (s) { el('stop', { offset: s[0], 'stop-color': '#ffffff', 'stop-opacity': s[1] }, eg); });
    var clip = el('clipPath', { id: 'twc-lid' }, defs), clipPath = el('path', {}, clip);
    var bg = el('rect', { fill: 'url(#twc-vig)' }, svg);
    var gMotes = el('g', {}, svg);
    var gCentre = el('g', { transform: 'translate(' + cx + ' ' + cy + ')' }, svg);
    var gPar = el('g', {}, gCentre);
    var gCircle = el('g', {}, gPar);
    var dash = { pathLength: 1, 'stroke-dasharray': '1 1', fill: 'none', 'stroke-linecap': 'round' };
    function strokeAttrs(extra) { var o = {}; for (var k in dash) o[k] = dash[k]; for (k in extra) o[k] = extra[k]; return o; }

    var layerDom = geo.layers.map(function (layer) {
      var g = el('g', {}, gCircle);
      var items = layer.els.map(function (e) {
        var bloom = e.lvl >= 2 ? el('path', strokeAttrs({ d: e.d, 'stroke-width': n2(e.w * 4.6) }), g) : null;
        var main = el('path', strokeAttrs({ d: e.d, 'stroke-width': n2(e.w) }), g);
        return { e: e, main: main, bloom: bloom };
      });
      return { layer: layer, g: g, items: items };
    });

    var gSpark = el('g', {}, gPar);
    el('circle', { r: n2(R * 0.10), fill: 'url(#twc-eyeglow)', opacity: .8 }, gSpark);
    el('circle', { r: 2.4, fill: '#ffffff' }, gSpark);
    el('path', { d: 'M' + n2(-R * 0.05) + ' 0H' + n2(R * 0.05) + 'M0 ' + n2(-R * 0.05) + 'V' + n2(R * 0.05), stroke: '#fff', 'stroke-width': 1, 'stroke-opacity': .45 }, gSpark);

    var eyeY = -R * CONFIG.EYE_RISE;
    var gEye = el('g', { transform: 'translate(0 ' + n2(eyeY) + ')' }, gPar);
    gEye.style.filter = 'drop-shadow(0 0 ' + n2(3 * glow) + 'px rgba(255,255,255,0.62)) drop-shadow(0 0 ' + n2(13 * glow) + 'px rgba(255,255,255,0.26))';
    var eAmb = el('circle', { r: n2(R * 0.42), fill: 'url(#twc-eyeglow)' }, gEye);
    var eBrow = el('path', strokeAttrs({ stroke: silver, 'stroke-width': CONFIG.STROKE.micro }), gEye);
    var gIn = el('g', { 'clip-path': 'url(#twc-lid)' }, gEye);
    var irisR = R * 0.106 * eyeSize;
    var rays = '', sig = '', k;
    for (k = 0; k < 28; k++) rays += pSpoke(irisR * 0.80, irisR * (k % 4 === 0 ? 1.0 : 0.93), k * TAU / 28);
    for (k = 0; k < 6; k++) { var aa = k * TAU / 6 + 0.3, pp = px(irisR * 0.34, aa); sig += pGlyph(5 + k * 3, pp[0], pp[1], irisR * 0.2, aa + 90 * D); }
    var iris = [
      [pRing(irisR), CONFIG.STROKE.thin, .8], [pRing(irisR * .74), CONFIG.STROKE.micro, .55], [pRing(irisR * .5), CONFIG.STROKE.micro, .4],
      [rays, CONFIG.STROKE.micro, .5], [sig, CONFIG.STROKE.micro, .42]
    ].map(function (a) { return { n: el('path', strokeAttrs({ d: a[0], stroke: silver, 'stroke-width': a[1] }), gIn), k: a[2] }; });
    var pup = el('ellipse', { fill: '#ffffff' }, gIn);
    var pupR = el('ellipse', { fill: 'none', stroke: silver, 'stroke-width': CONFIG.STROKE.micro }, gIn);
    var lidU = el('path', strokeAttrs({ 'stroke-width': CONFIG.STROKE.major }), gEye);
    var lidL = el('path', strokeAttrs({ 'stroke-width': CONFIG.STROKE.mid }), gEye);
    var corn = el('path', strokeAttrs({ stroke: silver, 'stroke-width': CONFIG.STROKE.thin }), gEye);
    var flashR = el('rect', { fill: '#ffffff', opacity: 0 }, svg);

    var rg = rngFrom(CONFIG.SEED + 7), motes = [];
    var mn = Math.round(CONFIG.PARTICLE_BASE * P.particleDensity);
    for (k = 0; k < mn; k++) {
      var ma = rg() * TAU, rr = Math.sqrt(0.05 + 0.95 * rg());
      var m = { a: ma, x: cx + Math.cos(ma) * rr * R * 1.45, y: cy + Math.sin(ma) * rr * R * 1.25,
                f1: rg() * TAU, f2: rg() * TAU, f3: rg() * TAU, sp: 0.6 + rg() * 0.9, sz: 0.7 + rg() * 1.4 };
      m.n = el('circle', { r: n2(m.sz), fill: '#ffffff' }, gMotes);
      motes.push(m);
    }

    var logo = document.createElement('div'); logo.className = 'twc-logo';
    logo.innerHTML = '<div class="twc-mark"></div><div class="twc-rule"></div><div class="twc-sub"></div>';
    logo.querySelector('.twc-mark').textContent = P.logoText;
    logo.querySelector('.twc-sub').textContent = P.subtitle;
    host.appendChild(logo);
    var mark = logo.querySelector('.twc-mark'), rule = logo.querySelector('.twc-rule'), sub = logo.querySelector('.twc-sub');

    /* ---- fit: keep the whole circle on screen on any shape of display ---- */
    var vb = { x: 0, y: 0, w: W, h: H }, unit = 1;
    function fit() {
      var aspect = innerWidth / innerHeight, need = R * 2.12;   // circle plus a little air
      vb.h = Math.max(H, need / aspect);                        // portrait screens widen the view instead of cropping
      vb.w = vb.h * aspect; vb.x = cx - vb.w / 2; vb.y = cy - vb.h / 2;
      svg.setAttribute('viewBox', [vb.x, vb.y, vb.w, vb.h].map(n2).join(' '));
      [bg, flashR].forEach(function (r) { r.setAttribute('x', n2(vb.x)); r.setAttribute('y', n2(vb.y)); r.setAttribute('width', n2(vb.w)); r.setAttribute('height', n2(vb.h)); });
      unit = innerHeight / vb.h;
      host.style.setProperty('--twc-s', Math.min(unit, innerWidth / 1180));   // logo never overflows narrow screens
    }
    fit(); addEventListener('resize', fit);

    /* ---- cursor parallax, as authored ---- */
    var curX = 0, curY = 0;
    function onMove(e) { curX = clamp((e.clientX / innerWidth - 0.5) * 2, -1, 1); curY = clamp((e.clientY / innerHeight - 0.5) * 2, -1, 1); }
    var hover = !(window.matchMedia && matchMedia('(hover: none)').matches);
    if (!reduced && hover) addEventListener('pointermove', onMove, { passive: true });

    var PH = {
      core:  { t0: CUES.Spark + 0.30, spread: 0.28, dur: 0.30 },
      inner: { t0: CUES.InnerCircle,  spread: 0.52, dur: 0.44 },
      mid:   { t0: CUES.Construct,    spread: 0.58, dur: 0.46 },
      outer: { t0: CUES.OuterRings,   spread: 0.60, dur: 0.46 },
      glyph: { t0: CUES.Glyphs,       spread: 0.48, dur: 0.26 }
    };

    function frame(T) {
      var sparkOn = clamp((T - (CUES.Spark + 0.04)) / 0.10, 0, 1);
      var flicker = (T > CUES.Spark + 0.20 && T < CUES.Spark + 0.27) ? 0.12 : 1;
      var sparkB = sparkOn * flicker * (0.34 + 0.66 * MOTION.enter(CUES.Spark + 0.28, CUES.Spark + 0.62, T)) *
        (1 - MOTION.enter(CUES.InnerCircle + 0.08, CUES.InnerCircle + 0.48, T));

      var eOut = MOTION.enter(CUES.EyeOpen + 0.04, CUES.EyeOpen + 0.40, T);
      var eIris = MOTION.enter(CUES.EyeOpen + 0.30, CUES.EyeOpen + 0.82, T);
      var ePup = MOTION.enter(CUES.EyeOpen + 0.60, CUES.EyeOpen + 0.96, T);
      var aperture = MOTION.enter(CUES.EyeOpen + 0.10, CUES.EyeOpen + 0.42, T) * 0.30 + MOTION.enter(CUES.EyeOpen + 0.80, CUES.EyeOpen + 1.34, T) * 0.70;
      aperture *= 1 - 0.11 * Math.sin(clamp((T - CUES.Notice) / 0.50, 0, 1) * Math.PI);
      aperture *= 1 + 0.13 * MOTION.enter(CUES.Surge, CUES.Surge + 0.28, T);
      if (!reduced) aperture *= 1 - 0.035 * (0.5 + 0.5 * Math.sin(T * 0.8 - 1.2));

      var notice = clamp((T - CUES.Notice) / 0.55, 0, 1);
      var look = Math.sin(notice * Math.PI) * -0.20 + notice * 0.06;
      var pupX = look * R * 0.026 * eyeSize + curX * R * 0.013 * eyeSize;
      var pupY = curY * R * 0.006 * eyeSize + Math.sin(notice * Math.PI) * R * 0.007 * eyeSize;
      var ew = R * 0.238 * eyeSize, hu = R * 0.166 * eyeSize * aperture, hl = R * 0.132 * eyeSize * aperture;

      var ce = clamp((T - (CUES.EyeOpen + 0.52)) / 1.00, 0, 1);
      var frontEye = ce > 0 ? -0.06 + 1.36 * Easing.easeOutQuad(ce) : -2;
      var cs = clamp((T - (CUES.Surge + 0.02)) / 0.42, 0, 1);
      var frontSurge = cs > 0 ? -0.10 + 1.48 * cs : -2;
      var peak = MOTION.enter(CUES.Surge + 0.16, CUES.Surge + 0.40, T) * (1 - MOTION.enter(CUES.Surge + 0.48, CUES.Surge + 0.60, T));
      var collapseP = reduced ? 0 : clamp((T - (CUES.Surge + 0.46)) / 0.34, 0, 1);
      var collapseK = 1 - 0.94 * Easing.easeInExpo(collapseP);
      var circleFade = reduced ? 1 - MOTION.enter(CUES.Surge + 0.30, CUES.Surge + 0.95, T) : 1 - 0.9 * collapseP * collapseP;
      var flash = reduced ? 0 : clamp(MOTION.enter(CUES.Surge + 0.78, CUES.Surge + 0.88, T) - MOTION.enter(CUES.Surge + 0.88, CUES.Surge + 0.97, T), 0, 1);
      var reorient = MOTION.enter(CUES.Notice - 0.10, CUES.Notice + 0.80, T);
      var eyePresence = MOTION.enter(CUES.EyeOpen + 0.55, CUES.Notice + 0.45, T) * (1 - MOTION.enter(CUES.Surge, CUES.Surge + 0.26, T));

      /* motes */
      var moteDrift = MOTION.enter(CUES.EyeOpen + 0.60, CUES.Hold + 0.4, T);
      var ambient = Math.max(peak, wave(0.5, frontEye, 0.4));
      for (var mi = 0; mi < motes.length; mi++) {
        var mo = motes[mi];
        var bl = 0.5 + 0.5 * Math.sin(T * 0.55 * mo.sp + mo.f3), blink = Math.sin(T * 0.31 + mo.f2);
        var op = (0.09 + 0.46 * bl) * (blink < -0.55 ? clamp((blink + 0.80) / 0.25, 0, 1) : 1);
        var dx = (reduced ? 0 : Math.sin(T * 0.13 + mo.f1) * 26) + Math.cos(mo.a) * moteDrift * 36;
        var dy = (reduced ? 0 : Math.cos(T * 0.11 + mo.f2) * 22) + Math.sin(mo.a) * moteDrift * 32;
        set(mo.n, 'cx', n2(mo.x + dx)); set(mo.n, 'cy', n2(mo.y + dy));
        set(mo.n, 'opacity', n2(clamp(op * (0.8 + 0.8 * ambient), 0, 1)));
      }

      /* circle layers */
      set(gPar, 'transform', 'translate(' + n2(curX * CONFIG.PARALLAX_PX) + ' ' + n2(curY * CONFIG.PARALLAX_PX) + ')');
      set(gCircle, 'opacity', n2(clamp(circleFade, 0, 1)));
      set(gCircle, 'transform', 'translate(0 ' + n2(eyeY) + ') scale(' + n2(collapseK) + ') translate(0 ' + n2(-eyeY) + ')');
      for (var li = 0; li < layerDom.length; li++) {
        var L = layerDom[li], layer = L.layer, ph = PH[layer.phase], fade = 1;
        if (layer.key === 'core') fade = 1 - MOTION.enter(CUES.Settle - 0.05, CUES.Settle + 0.45, T);
        if (layer.recede) fade *= 1 - layer.recede * eyePresence;
        var anyOn = false;
        for (var ii = 0; ii < L.items.length; ii++) {
          var it = L.items[ii], e = it.e, start = ph.t0 + e.st * ph.spread;
          var pr = fade <= 0.002 ? 0 : reduced ? MOTION.enter(ph.t0, ph.t0 + ph.spread + ph.dur, T) : MOTION.draw(start, start + ph.dur, T);
          if (pr <= 0.001){ set(it.main, 'visibility', 'hidden'); if (it.bloom) set(it.bloom, 'visibility', 'hidden'); continue; }
          var base = (e.lvl === 1 ? INK.l1 : e.lvl === 2 ? INK.l2 : INK.l3) * bright;
          var settle = clamp((T - (start + ph.dur)) / 0.70, 0, 1);
          var b = base * (1 + 0.55 * (1 - settle));
          var boost = Math.max(wave(e.rN, frontEye, 0.17) * 0.92, wave(e.rN, frontSurge, 0.22), peak);
          b = b + (1 - b) * boost * 0.95;
          if (layer.pulse && !reduced) b *= 1 + layer.pulse * 0.22 * Math.sin(T * 0.85 + layer.ph);
          b = clamp(b, 0, 1) * fade * (reduced ? pr : 1);
          var col = b > 0.88 ? '#ffffff' : silver, off = reduced ? 0 : n2(1 - pr);
          if (it.bloom){
            if (b > 0.30){ set(it.bloom, 'visibility', 'visible'); set(it.bloom, 'stroke', col); set(it.bloom, 'stroke-opacity', n2(clamp(b * 0.085 * glow, 0, 0.3))); set(it.bloom, 'stroke-dashoffset', off); }
            else set(it.bloom, 'visibility', 'hidden');
          }
          set(it.main, 'visibility', 'visible'); set(it.main, 'stroke', col); set(it.main, 'stroke-opacity', n2(b)); set(it.main, 'stroke-dashoffset', off);
          anyOn = true;
        }
        if (anyOn){
          var deg = (reduced ? 0 : layer.rate * rot * T) + layer.follow * 3.0 * reorient;
          var ty = layer.dy + layer.follow * eyeY * 0.55 * reorient;
          set(L.g, 'transform', 'translate(' + n2(layer.dx) + ' ' + n2(ty) + ') rotate(' + n2(deg) + ')');
        }
      }

      /* spark */
      set(gSpark, 'visibility', sparkB > 0.004 ? 'visible' : 'hidden'); set(gSpark, 'opacity', n2(clamp(sparkB, 0, 1)));

      /* eye */
      var eyeVis = Math.max(eOut * 0.55, eIris) * (1 - MOTION.enter(CUES.Surge + 0.84, CUES.Surge + 0.92, T));
      set(gEye, 'visibility', eyeVis > 0.004 ? 'visible' : 'hidden');
      if (eyeVis > 0.004){
        var eyeLine = clamp((0.34 + 0.5 * eIris) * bright + (1 - 0.34) * Math.max(peak, MOTION.enter(CUES.Surge, CUES.Surge + 0.24, T)), 0, 1);
        var irisOp = eIris * (0.5 + 0.5 * eyeLine), lidCol = eyeLine > 0.88 ? '#ffffff' : silver;
        set(eAmb, 'opacity', n2(clamp((0.14 + 0.46 * eIris + 0.5 * MOTION.enter(CUES.Surge, CUES.Surge + 0.3, T)) * glow * eyeVis, 0, 1)));
        set(eBrow, 'd', 'M' + n2(-ew * 1.24) + ' ' + n2(-hu * 0.25) + 'Q0 ' + n2(-hu * 2.5 - R * 0.02) + ' ' + n2(ew * 1.24) + ' ' + n2(-hu * 0.25));
        set(eBrow, 'stroke-opacity', n2(0.22 * eyeLine * eyeVis)); set(eBrow, 'stroke-dashoffset', n2(1 - eOut));
        set(clipPath, 'd', 'M' + n2(-ew) + ' 0Q0 ' + n2(-hu * 2) + ' ' + n2(ew) + ' 0Q0 ' + n2(hl * 2) + ' ' + n2(-ew) + ' 0Z');
        for (var ri = 0; ri < iris.length; ri++){ set(iris[ri].n, 'stroke-opacity', n2(iris[ri].k * irisOp)); set(iris[ri].n, 'stroke-dashoffset', n2(1 - eIris)); }
        set(pup, 'cx', n2(pupX)); set(pup, 'cy', n2(pupY));
        set(pup, 'rx', n2(R * 0.0185 * eyeSize * (0.4 + 0.6 * ePup)));
        set(pup, 'ry', n2(R * 0.064 * eyeSize * (0.3 + 0.7 * ePup) * (0.35 + 0.65 * aperture)));
        set(pup, 'opacity', n2(0.94 * ePup * eyeVis));
        set(pupR, 'cx', n2(pupX)); set(pupR, 'cy', n2(pupY)); set(pupR, 'rx', n2(R * 0.028 * eyeSize));
        set(pupR, 'ry', n2(R * 0.080 * eyeSize * (0.35 + 0.65 * aperture))); set(pupR, 'stroke-opacity', n2(0.4 * ePup * eyeLine));
        set(lidU, 'd', 'M' + n2(-ew) + ' 0Q0 ' + n2(-hu * 2) + ' ' + n2(ew) + ' 0'); set(lidU, 'stroke', lidCol);
        set(lidU, 'stroke-opacity', n2(clamp(0.9 * eyeLine * eyeVis, 0, 1))); set(lidU, 'stroke-dashoffset', n2(1 - eOut));
        set(lidL, 'd', 'M' + n2(-ew) + ' 0Q0 ' + n2(hl * 2) + ' ' + n2(ew) + ' 0'); set(lidL, 'stroke', lidCol);
        set(lidL, 'stroke-opacity', n2(clamp(0.78 * eyeLine * eyeVis, 0, 1))); set(lidL, 'stroke-dashoffset', n2(1 - eOut));
        set(corn, 'd', 'M' + n2(-ew) + ' 0L' + n2(-ew * 1.34) + ' ' + n2(-R * 0.012) + 'M' + n2(ew) + ' 0L' + n2(ew * 1.34) + ' ' + n2(-R * 0.012));
        set(corn, 'stroke-opacity', n2(0.5 * eyeLine * eyeVis)); set(corn, 'stroke-dashoffset', n2(1 - eOut));
      }
      set(flashR, 'opacity', n2(flash));

      /* logo reveal (no loop outro here: the page fades in instead) */
      var logoIn = MOTION.enter(CUES.Reveal + 0.35, CUES.Reveal + 1.50, T);
      var ruleIn = MOTION.enter(CUES.Reveal + 1.00, CUES.Reveal + 1.90, T);
      var subIn = MOTION.enter(CUES.Reveal + 1.35, CUES.Reveal + 2.20, T);
      logo.style.opacity = n2(logoIn);
      logo.style.visibility = logoIn > 0.002 ? 'visible' : 'hidden';
      mark.style.letterSpacing = n2(0.30 - 0.16 * logoIn) + 'em'; mark.style.textIndent = n2(0.30 - 0.16 * logoIn) + 'em';
      mark.style.transform = 'scale(' + n2(0.985 + 0.015 * logoIn) + ')';
      rule.style.width = 'calc(340px * var(--twc-s) * ' + n2(ruleIn) + ')';
      sub.style.opacity = n2(subIn);
    }

    /* ---- clock ---- */
    var startT = opts.mode === 'short' ? CUES.Settle : 0;
    var endT = TOTAL - 0.34;                    // the authored outro starts here; hand over to the page
    var t0 = null, raf = 0, done = false;
    function tick(now) {
      if (t0 == null) t0 = now;
      var T = startT + (now - t0) / 1000;
      frame(Math.min(T, endT));
      if (T >= endT) return finish();
      raf = requestAnimationFrame(tick);
    }
    function finish() {
      if (done) return; done = true;
      cancelAnimationFrame(raf);
      removeEventListener('pointermove', onMove); removeEventListener('resize', fit);
      if (opts.onDone) opts.onDone();
    }
    frame(startT);
    raf = requestAnimationFrame(tick);
    return { skip: finish, duration: endT - startT, renderAt: function (T) { cancelAnimationFrame(raf); frame(T); } };
  }

  window.AntarIntro = { play: play, CUES: CUES, TOTAL: TOTAL };
})();
