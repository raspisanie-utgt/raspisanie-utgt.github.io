(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.UTGTAppearanceRenderer = factory();
})(typeof window === 'object' ? window : null, function () {
  'use strict';

  const maxDepth = 4;
  const edgeLimit = 14;
  const maxPixels = 1600000;
  const frameInterval = 1000 / 30;
  const shapes = {
    snow: [56, 18, 32, ['#8bb8e8', '#f1f8ff']],
    rain: [38, 210, 130, ['#679ac8', '#8abbee']],
    leaves: [24, 28, 26, ['#bf6128', '#a54731', '#d7973f']],
    petals: [25, 17, 22, ['#dc81a0', '#eaa1b9', '#c590cd']],
    lights: [16, 4, 8, ['#d2a044', '#8dace8']]
  };
  const targets = '.lesson, .tile, details > summary';
  const range = (min, max) => min + Math.random() * (max - min);

  function budget(width, height, dpr, memory, cores) {
    const small = width < 700 || (memory && memory <= 4) || (cores && cores <= 4);
    return { scale: small ? 1 : Math.min(dpr || 1, 1.5, Math.sqrt(maxPixels / Math.max(1, width * height))),
      count: small ? 15 : 45, debris: small ? 8 : 20, frameMs: small ? 1000 / 20 : frameInterval };
  }

  function depth(previous, snowfall, intensity, seconds) {
    const limit = maxDepth * intensity / 100;
    return Math.max(0, Math.min(limit, previous + (snowfall ? .17 * intensity / 100 : -.42) * seconds));
  }

  function shed(previous) { return Math.max(0, previous - Math.max(.7, previous * .48)); }

  function create(win, doc) {
    const canvas = doc.createElement('canvas');
    canvas.className = 'appearance-layer';
    canvas.setAttribute('aria-hidden', 'true');
    let ctx;
    try { ctx = canvas.getContext('2d'); } catch (_) { /* canvas is optional */ }
    if (!ctx) return { configure() {}, visibility() {} };
    let prefs = { intensity: 0 }, visual = { effect: 'none', holiday: null }, reduced = false;
    let width = 0, height = 0, limits, frame = 0, last = 0, nextMeasure = 0;
    let particles = [], debris = [], edges = [], piles = new WeakMap();
    let level = 0, dirty = true, discover = true, resizing = true;
    const visible = new Set();
    const watched = new Set();
    const mark = () => { dirty = true; };
    const observer = typeof win.IntersectionObserver === 'function' ? new win.IntersectionObserver(entries => {
      for (const entry of entries) {
        if (!watched.has(entry.target)) continue;
        if (entry.isIntersecting) visible.add(entry.target);
        else visible.delete(entry.target);
      }
      mark();
    }) : null;
    const mutation = new win.MutationObserver(records => {
      if (records.some(record => record.type === 'childList')) discover = true;
      mark();
    });
    const resizeObserver = typeof win.ResizeObserver === 'function' ? new win.ResizeObserver(mark) : null;
    let tracking = false;

    function track(enabled) {
      if (enabled === tracking) return;
      tracking = enabled;
      if (enabled) {
        discover = dirty = true;
        mutation.observe(doc.body, { subtree: true, childList: true, attributes: true, attributeFilter: ['open', 'hidden'] });
        if (resizeObserver) resizeObserver.observe(doc.body);
      } else {
        mutation.disconnect();
        if (observer) observer.disconnect();
        if (resizeObserver) resizeObserver.disconnect();
        visible.clear(); watched.clear(); edges = [];
      }
    }

    function measure() {
      if (discover) {
        const matches = new Set(doc.querySelectorAll(targets));
        for (const el of watched) if (!matches.has(el)) {
          if (observer) observer.unobserve(el);
          watched.delete(el); visible.delete(el);
        }
        for (const el of matches) if (!watched.has(el)) {
          watched.add(el);
          if (observer) observer.observe(el);
          else visible.add(el);
        }
        discover = false;
      }
      edges = [];
      for (const el of visible) {
        if (edges.length >= edgeLimit) break;
        if (!el.isConnected || el.closest('dialog, [hidden]')) continue;
        const box = el.getBoundingClientRect();
        if (box.width < 24 || box.height < 12 || box.top < 10 || box.top >= height - 5) continue;
        const style = win.getComputedStyle(el);
        const radius = Math.max(0, Math.min(box.height / 2, box.width / 2, parseFloat(style.borderTopLeftRadius) || 12));
        const left = Math.max(3, box.left);
        const right = Math.min(width - 3, box.right);
        if (right - left >= 16) edges.push({ el, left, right, top: box.top, radius, width: box.width, height: box.height, boxLeft: box.left });
      }
      dirty = false;
    }

    function resize() {
      width = doc.documentElement.clientWidth;
      height = win.innerHeight;
      limits = budget(width, height, win.devicePixelRatio, win.navigator.deviceMemory, win.navigator.hardwareConcurrency);
      canvas.width = Math.max(1, Math.floor(width * limits.scale));
      canvas.height = Math.max(1, Math.floor(height * limits.scale));
      ctx.setTransform(limits.scale, 0, 0, limits.scale, 0, 0);
      particles = [];
      dirty = true;
      resizing = false;
    }

    function particle(shape, initial) {
      return { x: range(0, width), y: initial ? range(0, height) : range(-48, -8),
        r: range(.8, 3.5), speed: shape[1] + range(0, shape[2]), phase: range(0, 6.28),
        color: shape[3][Math.floor(range(0, shape[3].length))], ornate: Math.random() < .24 };
    }

    function snowfall() { return visual.effect === 'snow' && prefs.accumulation && !reduced; }
    function canMelt() { return false; }
    function animate() { return !reduced && (Boolean(shapes[visual.effect]) || canMelt() || debris.length > 0); }
    function active() {
      const staticArt = visual.effect === 'sun' || visual.effect === 'cloud' || visual.holiday;
      return prefs.mode !== 'off' && prefs.intensity > 0 && (staticArt || animate());
    }

    function paintParticles(dt, opacity) {
      const kind = visual.effect;
      const shape = shapes[kind];
      if (!shape || reduced) return;
      const count = Math.min(limits.count, Math.round(shape[0] * opacity * Math.min(1.2, width / 680 + .45)));
      while (particles.length < count) particles.push(particle(shape, true));
      particles.length = count;
      for (let i = 0; i < count; i++) {
        const p = particles[i];
        p.phase += dt * (kind === 'lights' ? .9 : 1.5);
        p.y += p.speed * dt;
        p.x += (Math.sin(p.phase) * 15 + visual.wind * (kind === 'rain' ? 3 : 2)) * dt;
        if (p.y > height + 12) { particles[i] = particle(shape, false); continue; }
        if (p.x < -8) p.x = width + 8;
        if (p.x > width + 8) p.x = -8;
        ctx.globalAlpha = kind === 'lights' ? .22 + .22 * (1 + Math.sin(p.phase)) : kind === 'snow' ? .55 : .46;
        ctx.fillStyle = ctx.strokeStyle = p.color;
        ctx.beginPath();
        if (kind === 'rain') {
          ctx.moveTo(p.x, p.y); ctx.lineTo(p.x + visual.wind * .45, p.y + 7 + p.r * 2);
          ctx.lineWidth = 1; ctx.stroke();
        } else {
          if (kind === 'lights' && p.ornate) {
            for (let point = 0; point < 8; point++) {
              const angle = point * Math.PI / 4;
              const radius = p.r * (point % 2 ? .42 : 1.45);
              ctx.lineTo(p.x + Math.cos(angle) * radius, p.y + Math.sin(angle) * radius);
            }
          } else if (kind === 'petals' && p.ornate) {
            for (let petal = 0; petal < 5; petal++) {
              const angle = p.phase + petal * Math.PI * .4;
              const x = p.x + Math.cos(angle) * p.r * .7;
              const y = p.y + Math.sin(angle) * p.r * .7;
              ctx.moveTo(x + p.r * .54, y);
              ctx.arc(x, y, p.r * .54, 0, Math.PI * 2);
            }
          } else if (kind === 'snow' || kind === 'lights') ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
          else ctx.ellipse(p.x, p.y, p.r * 1.6, p.r * .65, p.phase, 0, Math.PI * 2);
          ctx.fill();
        }
      }
    }

    // Snow caps are DOM children of cards, not coordinates on a fixed canvas.
    // They therefore remain attached on scroll, browser zoom, and dynamic layout.
    const capTargets = '.lesson, .tile, details > summary, .tabs button';
    let capWatch = null, capStyle = null;
    const caps = new Set();
    function ensureCaps() {
      if (!snowfall()) return;
      for (const el of doc.querySelectorAll(capTargets)) {
        if (el.closest('dialog, [hidden]') || el.querySelector(':scope > .utgt-snow-cap')) continue;
        const css = win.getComputedStyle(el);
        if (css.position === 'static') el.style.position = 'relative';
        const cap = doc.createElement('span');
        cap.className = 'utgt-snow-cap';
        cap.setAttribute('aria-hidden', 'true');
        el.appendChild(cap);
        caps.add(cap);
      }
    }
    function setSnowCaps(enabled) {
      if (!enabled) {
        if (capWatch) { capWatch.disconnect(); capWatch = null; }
        for (const cap of caps) cap.remove();
        caps.clear();
        if (capStyle) { capStyle.remove(); capStyle = null; }
        return;
      }
      if (!capStyle) {
        capStyle = doc.createElement('style');
        capStyle.textContent = '.utgt-snow-cap{position:absolute!important;pointer-events:none!important;top:0;left:0;right:0;z-index:3;height:5px;max-height:5px;background:#cbdff2;border-radius:inherit;opacity:.65;clip-path:polygon(0 0,100% 0,100% 55%,94% 70%,87% 54%,79% 83%,72% 63%,64% 76%,55% 58%,46% 82%,37% 64%,28% 76%,19% 60%,10% 79%,0 55%)}';
        doc.head.appendChild(capStyle);
      }
      capStyle.textContent = capStyle.textContent.replace(/opacity:[^;]+;/, 'opacity:' + Math.min(.8, .3 + prefs.intensity / 200) + ';');
      ensureCaps();
      if (!capWatch && win.MutationObserver) {
        capWatch = new win.MutationObserver(records => {
          if (records.some(record => Array.from(record.addedNodes).some(node => node.nodeType === 1 && !(node.classList && node.classList.contains('utgt-snow-cap'))))) ensureCaps();
        });
        capWatch.observe(doc.body, {childList:true,subtree:true});
      }
    }
    function paintEdges() { /* Caps belong to their elements, not the canvas. */ }

    function paintDebris(dt) {
      ctx.fillStyle = '#c5e1ff'; ctx.globalAlpha = .7;
      debris = debris.filter(p => {
        p.life -= dt;
        p.x += p.vx * dt;
        p.y += p.vy * dt;
        p.vy += 195 * dt;
        if (p.life <= 0 || p.y > height) return false;
        ctx.beginPath(); ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2); ctx.fill();
        return true;
      });
    }

    function atmosphere(opacity) {
      const kind = visual.effect;
      if (kind === 'sun' || kind === 'cloud') {
        const band = Math.min(height * .23, 170);
        const tint = ctx.createLinearGradient(0, 0, 0, band);
        tint.addColorStop(0, kind === 'sun' ? '#efaf40' : '#83a7cf');
        tint.addColorStop(1, 'transparent');
        ctx.globalAlpha = .13 * opacity;
        ctx.fillStyle = tint;
        ctx.fillRect(0, 0, width, band);
      }
      if (visual.holiday) {
        const [, , , , , left, right] = visual.holiday;
        ctx.globalAlpha = .25 + opacity * .27;
        ctx.fillStyle = visual.holiday[0] === 'victory' ? '#9d6841' : '#bb8a44';
        ctx.font = '18px system-ui, sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText(left, 18, height - 17);
        ctx.fillText(right, width - 18, height - 17);
      }
    }

    function draw(time) {
      frame = 0;
      if (doc.hidden || !active()) return sync();
      const delta = last ? time - last : frameInterval;
      if (delta < (limits ? limits.frameMs : frameInterval) - 1) { frame = win.requestAnimationFrame(draw); return; }
      last = time;
      if (resizing) resize();
      if (tracking && dirty) measure();
      const dt = Math.min(delta / 1000, .1);
      const opacity = prefs.intensity / 100;
      ctx.clearRect(0, 0, width, height);
      atmosphere(opacity);
      paintParticles(dt, opacity);
      paintEdges(dt, opacity);
      paintDebris(dt);
      ctx.globalAlpha = 1;
      if (!snowfall() && !canMelt()) track(false);
      if (animate()) frame = win.requestAnimationFrame(draw);
      else if (!active()) sync();
    }

    function sync() {
      if (frame) win.cancelAnimationFrame(frame);
      frame = last = 0;
      if (!active()) {
        canvas.remove(); track(false);
        particles = []; debris = []; piles = new WeakMap(); level = 0;
      } else if (!doc.hidden) {
        if (!canvas.isConnected) { doc.body.appendChild(canvas); resizing = true; }
        frame = win.requestAnimationFrame(draw);
      }
    }

    function shake(event, slide) {
      if (!prefs.physics || reduced || doc.hidden || !limits) return;
      const el = slide ? event.target.querySelector(':scope > summary') : event.target.closest(targets);
      // The subsequent toggle event handles clicks on a details summary.
      if (!el || (!slide && el.tagName === 'SUMMARY')) return;
      const edge = edges.find(item => item.el === el);
      const pile = edge && piles.get(el);
      if (!pile || pile.height < .55) return;
      const amount = pile.height;
      pile.height = shed(amount);
      for (let i = 0; i < Math.min(7, Math.ceil(amount * 2)); i++) {
        if (debris.length >= limits.debris) break;
        debris.push({ x: range(edge.left, edge.right), y: edge.top - amount,
          vx: range(-24, 24), vy: range(slide ? 16 : -28, 45), r: range(.8, 2.2), life: range(.35, .85) });
      }
    }

    win.addEventListener('resize', () => { resizing = true; if (!frame && active()) sync(); }, { passive: true });
    doc.addEventListener('scroll', mark, { capture: true, passive: true });
    doc.addEventListener('transitionend', mark);
    doc.addEventListener('click', event => shake(event, false), true);
    doc.addEventListener('toggle', event => { if (event.target.tagName === 'DETAILS') shake(event, true); }, true);

    return {
      configure(nextPrefs, nextVisual, motion) {
        if (visual.effect !== nextVisual.effect) particles = [];
        prefs = nextPrefs; visual = nextVisual; reduced = motion;
        if (!prefs.accumulation || reduced || prefs.mode === 'off' || !prefs.intensity) {
          level = 0; debris = []; piles = new WeakMap();
        }
        track(false);
        setSnowCaps(snowfall());
        sync();
      },
      visibility: sync
    };
  }

  return { create, budget, depth, shed, maxDepth };
});
