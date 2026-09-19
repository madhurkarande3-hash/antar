/* ANTAR intro gate: plays "The Watching Circle" (short cut) over a page while it starts.
   Include right after <body>, after assets/intro.js. Skip: button, click, Esc/Enter/Space.
   Turn off with ?intro=off. The page underneath keeps loading and running normally. */
(function () {
  'use strict';
  var q = new URLSearchParams(location.search).get('intro');
  if (q === 'off' || !window.AntarIntro) return;
  var base = (document.currentScript && document.currentScript.src || '').replace(/[^/]*$/, '');
  var css = document.createElement('style');
  css.textContent =
    "@font-face{font-family:'Cormorant Garamond';src:url('" + base + "fonts/cormorant-garamond-latin.woff2') format('woff2');font-weight:300 700;font-display:swap}" +
    "@font-face{font-family:'Lora';src:url('" + base + "fonts/lora-latin.woff2') format('woff2');font-weight:400 700;font-display:swap}" +
    "#antarGate{position:fixed;inset:0;z-index:2147483000;background:#000;overflow:hidden;transition:opacity .7s ease;cursor:pointer}" +
    "#antarGate.out{opacity:0;pointer-events:none}" +
    "#antarGate .twc-stage{position:absolute;inset:0}" +
    "#antarGate .twc-svg{position:absolute;inset:0;width:100%;height:100%;display:block}" +
    "#antarGate .twc-logo{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:max(14px, calc(34px * var(--twc-s,1)));visibility:hidden;pointer-events:none}" +
    "#antarGate .twc-mark{font:400 max(30px, calc(104px * var(--twc-s,1)))/1 'Cormorant Garamond',Georgia,serif;color:#f6f7fa;white-space:nowrap}" +
    "#antarGate .twc-rule{height:1px;background:rgba(223,229,238,.45);width:0}" +
    "#antarGate .twc-sub{font:max(9.5px, calc(17px * var(--twc-s,1))) 'Lora',Georgia,serif;color:rgba(223,229,238,.62);letter-spacing:.46em;text-indent:.46em;text-transform:uppercase;white-space:nowrap}" +
    "#antarGate .gate-ui{position:absolute;left:0;right:0;bottom:0;display:flex;justify-content:space-between;align-items:center;padding:18px 22px;gap:12px;font:500 11.5px/1 ui-monospace,Menlo,Consolas,monospace;color:rgba(223,232,230,.45);letter-spacing:.06em}" +
    "#antarGate .gate-ui i{display:inline-block;width:6px;height:6px;border-radius:50%;background:#5ce1e6;box-shadow:0 0 8px rgba(92,225,230,.6);margin-right:8px;vertical-align:middle}" +
    "#antarGate button{background:none;border:1px solid rgba(223,232,230,.22);color:rgba(223,232,230,.75);font:600 12px/1 system-ui,sans-serif;letter-spacing:.18em;text-transform:uppercase;padding:8px 14px;cursor:pointer}" +
    "#antarGate button:hover{color:#fff;border-color:rgba(223,232,230,.6)}";
  document.head.appendChild(css);
  var gate = document.createElement('div');
  gate.id = 'antarGate'; gate.setAttribute('aria-label', 'ANTAR intro');
  gate.innerHTML = '<div class="twc-stage"></div><div class="gate-ui"><span><i></i>' +
    (document.body.getAttribute('data-intro-label') || 'Starting ANTAR') + '</span><button type="button">Skip intro</button></div>';
  document.body.appendChild(gate);
  var done = false, player;
  function end() {
    if (done) return; done = true;
    gate.classList.add('out');
    removeEventListener('keydown', keys, true);
    setTimeout(function () { gate.remove(); css.remove(); }, 750);
  }
  function keys(e) {           // while the intro is up, keys belong to it, not to the page underneath
    e.stopImmediatePropagation();
    if (['Escape', 'Enter', ' '].indexOf(e.key) >= 0) { e.preventDefault(); player ? player.skip() : end(); }
  }
  addEventListener('keydown', keys, true);
  gate.addEventListener('click', function () { player ? player.skip() : end(); });
  player = AntarIntro.play(gate.querySelector('.twc-stage'), { mode: q === 'full' ? 'full' : 'short', onDone: end });
})();
