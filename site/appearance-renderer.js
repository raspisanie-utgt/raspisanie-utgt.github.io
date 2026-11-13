(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.UTGTAppearanceRenderer = factory();
})(typeof window === 'object' ? window : null, function () {
  'use strict';

  const maxDepth = 9;
  const frameInterval = 1000 / 30;
  const shapes = {
    snow: [30, 35, 30, ['#b3d0ee', '#f4faff']],
    rain: [38, 210, 130, ['#679ac8', '#8abbee']],
    leaves: [24, 28, 26, ['#bf6128', '#a54731', '#d7973f']],
    petals: [25, 17, 22, ['#dc81a0', '#eaa1b9', '#c590cd']],
    lights: [16, 4, 8, ['#d2a044', '#8dace8']]
  };
  const targets = '.lesson, .tabs button, .tile, details > summary, .group-chip, .theme-btn';
  const range = (min, max) => min + Math.random() * (max - min);

  function budget(width, height, dpr, memory, cores) {
    const small = width < 700 || (memory && memory <= 4) || (cores && cores <= 4);
    return {
      scale: small ? 1 : Math.min(dpr || 1, 1.5, Math.sqrt(1600000 / Math.max(1, width * height))),
      count: small ? 24 : 54, debris: small ? 12 : 25,
      frameMs: small ? 1000 / 24 : frameInterval
    };
  }
  function depth(previous, snowfall, intensity, seconds) {
    const limit = maxDepth * intensity / 100;
    return Math.max(0, Math.min(limit, previous + (snowfall ? .17 * intensity / 100 : -.42) * seconds));
  }
  function shed(previous) { return Math.max(0, previous - Math.max(.7, previous * .48)); }
  // Testable rule: a falling flake crosses a card's top surface, from above,
  // inside the flat part (not through a rounded corner).
  function collision(x, previousY, nextY, rect, radius) {
    if (nextY < previousY || previousY > rect.top || nextY < rect.top) return false;
    const inset = Math.min(rect.width / 4, Math.max(5, radius * .65));
    return x >= rect.left + inset && x <= rect.right - inset;
  }

  function create(win, doc) {
    const canvas = doc.createElement('canvas');
    canvas.className = 'appearance-layer';
    canvas.setAttribute('aria-hidden', 'true');
    let ctx;
    try { ctx = canvas.getContext('2d'); } catch (_) { /* no canvas on some devices */ }
    if (!ctx) return { configure() {}, visibility() {} };

    let prefs = { mode: 'off', intensity: 0 }, visual = { effect: 'none' }, reduced = false;
    let width = 0, height = 0, limits = null, frame = 0, last = 0, resizePending = true;
    let particles = [], debris = [], capCSS = null, capObserver = null, boundsDirty = true;
    let hitTargets = [], lastScan = 0;
    const caps = new Set();
    const capData = new WeakMap();  // one accumulation depth for each individual card

    function snowOn() { return visual.effect === 'snow' && prefs.accumulation && !reduced && prefs.intensity > 0; }
    function active() {
      return prefs.mode !== 'off' && prefs.intensity > 0 &&
        (!reduced && !!shapes[visual.effect] || visual.effect === 'sun' || visual.effect === 'cloud' || visual.holiday || debris.length);
    }
    function particle(shape, initial) {
      return { x: range(0, width), y: initial ? range(-20, height) : range(-65, -5),
        r: range(.8, 2.7), speed: shape[1] + range(0, shape[2]), phase: range(0, Math.PI * 2),
        color: shape[3][Math.floor(range(0, shape[3].length))], ornate: Math.random() < .2 };
    }
    function resize() {
      width = doc.documentElement.clientWidth;
      height = win.innerHeight;
      limits = budget(width, height, win.devicePixelRatio, win.navigator.deviceMemory, win.navigator.hardwareConcurrency);
      canvas.width = Math.max(1, Math.floor(width * limits.scale));
      canvas.height = Math.max(1, Math.floor(height * limits.scale));
      ctx.setTransform(limits.scale, 0, 0, limits.scale, 0, 0);
      particles = [];
      boundsDirty = true;
      resizePending = false;
    }

    function setCapHeight(item) {
      // A clipped, local DOM overlay, moving *with* the card, not a canvas in screen coordinates.
      item.cap.style.height = Math.max(0, item.depth).toFixed(2) + 'px';
      item.cap.style.opacity = item.depth > .1 ? '1' : '0';
    }

    function attachCaps() {
      if (!snowOn()) return;
      for (const el of doc.querySelectorAll(targets)) {
        if (!el.isConnected || el.closest('dialog, [hidden]') || getItem(el)) continue;
        const style = win.getComputedStyle(el);
        if (style.display === 'none') continue;
        if (style.position === 'static') el.style.position = 'relative';
        const radius = Math.max(0, parseFloat(style.borderTopLeftRadius) || 12);
        const cap = doc.createElement('span');
        cap.className = 'utgt-snow-cap';
        cap.setAttribute('aria-hidden', 'true');
        cap.style.borderTopLeftRadius = radius + 'px';
        cap.style.borderTopRightRadius = Math.max(0, parseFloat(style.borderTopRightRadius) || radius) + 'px';
        const surface = doc.createElement('span');
        surface.className = 'utgt-snow-surface';
        cap.appendChild(surface);
        el.appendChild(cap);
        const item = { el, cap, depth: 0, radius };
        capData.set(el, item);
        caps.add(item);
        setCapHeight(item);
      }
      boundsDirty = true;
    }

    function syncCaps() {
      if (!snowOn()) {
        if (capObserver) { capObserver.disconnect(); capObserver = null; }
        for (const item of caps) item.cap.remove();
        caps.clear();
        // WeakMap entries must be cleared by replacement on re-entry; see activeCapData below.
        hitTargets = [];
        boundsDirty = true;
        return;
      }
      if (!capCSS) {
        capCSS = doc.createElement('style');
        capCSS.textContent = [
          '.utgt-snow-cap{position:absolute!important;top:0;left:0;right:0;z-index:4;',
          'height:0;overflow:hidden;pointer-events:none!important;opacity:0;',
          'transition:height .28s ease-out,opacity .28s ease-out;',
          'box-sizing:border-box;display:block!important;}',
          '.utgt-snow-surface{position:absolute;top:0;left:0;width:100%;height:100%;',
          'background:linear-gradient(180deg,#eef7ff,#adc8e2);',
          'clip-path:polygon(0 0,100% 0,100% 72%,94% 86%,88% 70%,82% 90%,75% 70%,',
          '68% 84%,60% 68%,52% 94%,43% 70%,35% 86%,26% 70%,18% 91%,10% 72%,4% 87%,0 73%);}',
          '@media (prefers-reduced-motion:reduce){.utgt-snow-cap{transition:none!important;}}'
        ].join('');
        doc.head.appendChild(capCSS);
      }
      attachCaps();
      if (!capObserver && win.MutationObserver) {
        capObserver = new win.MutationObserver(records => {
          if (records.some(record => [...record.addedNodes].some(n =>
            n.nodeType === 1 && !(n.classList && (n.classList.contains('utgt-snow-cap') || n.classList.contains('utgt-snow-surface'))))))
            attachCaps();
        });
        capObserver.observe(doc.body, { subtree: true, childList: true });
      }
    }

    // Ignore stale WeakMap entries when the effect has been turned off and on.
    function getItem(el) {
      const item = capData.get(el);
      return item && item.cap.isConnected ? item : null;
    }
    function measureCaps() {
      if (!snowOn()) { hitTargets = []; return; }
      hitTargets = [];
      for (const item of caps) {
        if (!item.cap.isConnected || !item.el.isConnected) { caps.delete(item); continue; }
        if (item.el.closest('dialog, [hidden]')) continue;
        const rect = item.el.getBoundingClientRect();
        if (rect.width < 18 || rect.height < 12 || rect.top < -12 || rect.top > height + 12) continue;
        hitTargets.push({ item, rect });
      }
      boundsDirty = false;
    }

    function shedCard(el) {
      if (!prefs.physics || !snowOn() || !limits) return;
      const item = getItem(el);
      if (!item || item.depth < .5) return;
      const rect = el.getBoundingClientRect(), before = item.depth;
      item.depth = shed(before);
      setCapHeight(item);
      for (let i = 0; i < Math.min(7, Math.ceil(before)); i++) {
        if (debris.length >= limits.debris) break;
        debris.push({ x: range(rect.left + 8, rect.right - 8), y: rect.top + 3,
          vx: range(-30, 30), vy: range(-40, 10), r: range(.7, 2), life: range(.35, .8) });
      }
    }

    function paintParticles(dt, opacity) {
      const kind = visual.effect, shape = shapes[kind];
      if (!shape || reduced) return;
      const count = Math.min(limits.count, Math.round(shape[0] * opacity * Math.min(1.4, width / 530 + .55)));
      while (particles.length < count) particles.push(particle(shape, true));
      particles.length = count;
      // When scrolling, measure current card positions on every animation frame.
      // This is cheap for ~10-20 visible cards and prevents viewport-stuck snow.
      if (snowOn()) measureCaps();
      for (let i = 0; i < count; i++) {
        const p = particles[i], oldY = p.y;
        p.phase += dt * (kind === 'lights' ? .9 : 1.5);
        p.y += p.speed * dt;
        p.x += (Math.sin(p.phase) * 15 + (visual.wind || 0) * (kind === 'rain' ? 3 : 2)) * dt;
        if (p.y > height + 10) { particles[i] = particle(shape, false); continue; }
        if (p.x < -8) p.x = width + 8;
        if (p.x > width + 8) p.x = -8;

        if (snowOn()) {
          let landed = false;
          for (const { item, rect } of hitTargets) {
            if (!collision(p.x, oldY, p.y, rect, item.radius)) continue;
            // Real impact: remove this falling flake and increase only that card's snow.
            item.depth = Math.min(maxDepth * prefs.intensity / 100, item.depth +
              (.65 + .20 * Math.random()) * (.7 + prefs.intensity / 100));
            setCapHeight(item);
            particles[i] = particle(shape, false);
            landed = true;
            break;
          }
          if (landed) continue;
        }
        ctx.globalAlpha = kind === 'lights' ? .22 + .2 * (1 + Math.sin(p.phase)) : kind === 'snow' ? .58 : .46;
        ctx.fillStyle = ctx.strokeStyle = p.color;
        ctx.beginPath();
        if (kind === 'rain') {
          ctx.moveTo(p.x, p.y); ctx.lineTo(p.x + (visual.wind || 0) * .45, p.y + 7 + p.r * 2);
          ctx.lineWidth = 1; ctx.stroke();
        } else if (kind === 'lights' && p.ornate) {
          for (let k = 0; k < 8; k++) {
            const a = k * Math.PI / 4, r = p.r * (k % 2 ? .42 : 1.45);
            ctx.lineTo(p.x + Math.cos(a) * r, p.y + Math.sin(a) * r);
          }
          ctx.fill();
        } else if (kind === 'petals' && p.ornate) {
          for (let k = 0; k < 5; k++) {
            const a = p.phase + k * Math.PI * .4;
            const x = p.x + Math.cos(a) * p.r, y = p.y + Math.sin(a) * p.r;
            ctx.moveTo(x + p.r * .5, y); ctx.arc(x, y, p.r * .5, 0, 2 * Math.PI);
          }
          ctx.fill();
        } else {
          if (kind === 'snow' || kind === 'lights') ctx.arc(p.x, p.y, p.r, 0, 2 * Math.PI);
          else ctx.ellipse(p.x, p.y, p.r * 1.6, p.r * .65, p.phase, 0, 2 * Math.PI);
          ctx.fill();
        }
      }
    }

    function paintDebris(dt) {
      ctx.fillStyle = '#dcecff'; ctx.globalAlpha = .73;
      debris = debris.filter(p => {
        p.life -= dt; p.x += p.vx * dt; p.y += p.vy * dt; p.vy += 195 * dt;
        if (p.life <= 0 || p.y > height) return false;
        ctx.beginPath(); ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2); ctx.fill();
        return true;
      });
    }

    function atmosphere(opacity) {
      const kind = visual.effect;
      if (kind === 'sun' || kind === 'cloud') {
        const tint = ctx.createLinearGradient(0, 0, 0, Math.min(height * .23, 170));
        tint.addColorStop(0, kind === 'sun' ? '#efaf40' : '#83a7cf');
        tint.addColorStop(1, 'transparent');
        ctx.globalAlpha = .13 * opacity;
        ctx.fillStyle = tint; ctx.fillRect(0, 0, width, Math.min(height * .23, 170));
      }
      if (visual.holiday) {
        const [, , , , , left, right] = visual.holiday;
        ctx.globalAlpha = .25 + opacity * .27;
        ctx.fillStyle = visual.holiday[0] === 'victory' ? '#9d6841' : '#bb8a44';
        ctx.font = '18px system-ui, sans-serif'; ctx.textAlign = 'center';
        ctx.fillText(left, 18, height - 17); ctx.fillText(right, width - 18, height - 17);
      }
    }
    function draw(time) {
      frame = 0;
      if (doc.hidden || !active()) { sync(); return; }
      const delta = last ? time - last : frameInterval;
      if (delta < (limits ? limits.frameMs : frameInterval) - 1) {
        frame = win.requestAnimationFrame(draw); return;
      }
      last = time;
      if (resizePending) resize();
      const dt = Math.min(delta / 1000, .1), opacity = prefs.intensity / 100;
      ctx.clearRect(0, 0, width, height);
      atmosphere(opacity);
      paintParticles(dt, opacity);
      paintDebris(dt);
      ctx.globalAlpha = 1;
      frame = win.requestAnimationFrame(draw);
    }
    function sync() {
      if (frame) win.cancelAnimationFrame(frame);
      frame = last = 0;
      if (!active()) {
        canvas.remove();
        particles = []; debris = [];
      } else if (!doc.hidden) {
        if (!canvas.isConnected) { doc.body.appendChild(canvas); resizePending = true; }
        frame = win.requestAnimationFrame(draw);
      }
    }
    doc.addEventListener('click', event => {
      const el = event.target.closest(targets);
      if (el && el.tagName !== 'SUMMARY') shedCard(el);
    }, true);
    doc.addEventListener('toggle', event => {
      if (event.target.tagName === 'DETAILS') {
        const el = event.target.querySelector(':scope > summary');
        if (el) shedCard(el);
      }
    }, true);
    win.addEventListener('resize', () => { resizePending = true; boundsDirty = true; }, { passive: true });
    return {
      configure(nextPrefs, nextVisual, motion) {
        if (visual.effect !== nextVisual.effect) particles = [];
        prefs = nextPrefs; visual = nextVisual; reduced = motion;
        syncCaps();
        sync();
      },
      visibility: sync
    };
  }
  return { create, budget, depth, shed, collision, maxDepth };
});
