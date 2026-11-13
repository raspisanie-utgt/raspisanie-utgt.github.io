(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.UTGTAppearanceRenderer = factory();
})(typeof window === 'object' ? window : null, function () {
  'use strict';

  const maxDepth = 11, SAMPLES = 49;
  const snowTargets = '.lesson, .tabs button, .group-chip, .theme-btn, .tile, details.news';
  const shapes = {
    snow: [36, 48, 37, ['#d3e6f8', '#f4faff', '#a6c9ed']],
    rain: [38, 210, 130, ['#679ac8', '#8abbee']],
    leaves: [24, 28, 26, ['#bf6128', '#a54731', '#d7973f']],
    petals: [25, 17, 22, ['#dc81a0', '#eaa1b9', '#c590cd']],
    lights: [16, 4, 8, ['#d2a044', '#8dace8']]
  };
  const random = (a, b) => a + Math.random() * (b - a);
  const clamp = (n, a, b) => Math.max(a, Math.min(b, n));

  function budget(width, height, dpr, memory, cores) {
    const mobile = width < 700 || (memory && memory <= 4) || (cores && cores <= 4);
    return { scale: mobile ? 1 : Math.min(dpr || 1, 1.5, Math.sqrt(1600000 / Math.max(1, width * height))),
      count: mobile ? 30 : 60, debris: mobile ? 10 : 24, frameMs: mobile ? 1000 / 24 : 1000 / 30 };
  }
  function depth(previous, snowfall, intensity, seconds) {
    const limit = maxDepth * intensity / 100;
    return clamp(previous + (snowfall ? .17 * intensity / 100 : -.42) * seconds, 0, limit);
  }
  function shed(previous) { return Math.max(0, previous - Math.max(.7, previous * .48)); }
  function createField() { return Array(SAMPLES).fill(0); }
  function maxHeight(field) { return field.reduce((max, n) => Math.max(max, n), 0); }
  function impact(field, normalizedX, amount, limit = maxDepth) {
    const center = clamp(normalizedX, 0, 1) * (field.length - 1);
    for (let i = Math.max(0, Math.floor(center) - 4); i <= Math.min(field.length - 1, Math.ceil(center) + 4); i++) {
      const distance = (i - center) / 1.65;
      field[i] = Math.min(limit, field[i] + amount * Math.exp(-.5 * distance * distance));
    }
    return field;
  }
  function melt(field, dt, rate = .23) {
    for (let i = 0; i < field.length; i++) field[i] = Math.max(0, field[i] - rate * dt);
    return maxHeight(field);
  }
  function collision(x, prevY, y, rect, radius) {
    if (y <= prevY || prevY >= rect.top + 2 || y < rect.top + 2) return false;
    if (rect.top < -6 || (Number.isFinite(rect.viewportHeight) && rect.top > rect.viewportHeight + 6)) return false;
    const leftRadius = typeof radius === 'object' ? radius.left : radius;
    const rightRadius = typeof radius === 'object' ? radius.right : radius;
    // Only the flat upper surface can collect snow; rounded corners cannot.
    const left = rect.left + Math.min(rect.width * .3, Math.max(4, leftRadius)) + 1;
    const right = rect.right - Math.min(rect.width * .3, Math.max(4, rightRadius)) - 1;
    return x >= left && x <= right;
  }

  function create(win, doc) {
    const layer = doc.createElement('canvas');
    layer.className = 'appearance-layer';
    layer.setAttribute('aria-hidden', 'true');
    let ctx;
    try { ctx = layer.getContext('2d'); } catch (_) { /* Canvas optional */ }
    if (!ctx) return { configure() {}, visibility() {} };

    let prefs = { mode: 'off', intensity: 0 }, visual = { effect: 'none' }, reduced = false;
    let width = 0, height = 0, limits = null, resizePending = true;
    let particles = [], debris = [], raf = 0, previousFrame = 0;
    const fields = new Map(); // Stable semantic keys survive the site's periodic innerHTML replacement.
    const attached = new Map();
    let watcher = null, resizeWatcher = null, sheet = null;
    let scanPending = false, rectsDirty = true, lastGeometry = 0, targets = [];
    let lastMeltTime = 0;

    function fallingSnow() {
      return !reduced && visual.effect === 'snow' && prefs.accumulation && prefs.intensity > 0 && prefs.mode !== 'off';
    }
    function hasDrifts() { for (const f of fields.values()) if (maxHeight(f) > .1) return true; return false; }
    function allowingDrifts() {
      return prefs.mode !== 'off' && prefs.intensity > 0 && prefs.accumulation &&
        !(prefs.mode === 'manual' && prefs.manual === 'none');
    }
    function keyFor(el) {
      if (el.matches('.lesson')) return 'lesson:' +
        (el.getAttribute('data-snow-id') || (el.closest('.list')?.id || 'list') + ':' +
        (el.dataset.key || el.textContent.slice(0, 65)));
      if (el.id) return 'id:' + el.id;
      if (el.matches('.tabs button')) return 'tab:' +
        (el.getAttribute('data-date') || el.textContent.trim().replace(/\s+/g, ' '));
      if (el.matches('.tile')) return 'tile:' + (el.dataset.kind || el.textContent.trim().slice(0, 40));
      return 'other:' + el.tagName + ':' + el.className;
    }
    function ensureStyle() {
      if (sheet) return;
      sheet = doc.createElement('style');
      sheet.textContent = [
        '.utgt-snow-mask{position:absolute!important;inset:0!important;z-index:4!important;',
        'pointer-events:none!important;overflow:hidden!important;border-radius:inherit!important;',
        'display:block!important;contain:paint;}',
        '.utgt-snow-drift{position:absolute!important;top:0!important;left:0!important;',
        'width:100%!important;height:16px!important;display:block!important;pointer-events:none!important;}'
      ].join('');
      doc.head.appendChild(sheet);
    }
    function paintDrift(entry) {
      const data = fields.get(entry.key);
      if (!data) return;
      const w = Math.max(1, entry.el.getBoundingClientRect().width);
      const scale = Math.min(win.devicePixelRatio || 1, 1.5);
      const backingW = Math.ceil(w * scale), backingH = Math.ceil(16 * scale);
      if (entry.canvas.width !== backingW || entry.canvas.height !== backingH) {
        entry.canvas.width = backingW;
        entry.canvas.height = backingH;
      }
      const c = entry.canvas.getContext('2d');
      if (!c) return;
      c.setTransform(scale, 0, 0, scale, 0, 0);
      c.clearRect(0, 0, w, 16);
      if (maxHeight(data) < .08) return;
      const grad = c.createLinearGradient(0, 0, 0, 13);
      grad.addColorStop(0, 'rgba(245,251,255,.96)');
      grad.addColorStop(.62, 'rgba(209,230,248,.91)');
      grad.addColorStop(1, 'rgba(137,176,215,.70)');
      c.fillStyle = grad;
      c.beginPath(); c.moveTo(0, 0); c.lineTo(w, 0);
      for (let i = data.length - 1; i >= 0; i--) c.lineTo(i * w / (data.length - 1), data[i]);
      c.closePath(); c.fill();
    }
    function attach(el) {
      if (attached.has(el)) return;
      const style = win.getComputedStyle(el);
      if (style.display === 'none' || !el.getClientRects().length) return;
      const key = keyFor(el);
      if (!fields.has(key)) {
        // Bound old state from many visited weeks; never discard a currently displayed card.
        if (fields.size > 240) {
          const activeKeys = new Set(Array.from(attached.values(), e => e.key));
          for (const old of fields.keys()) {
            if (!activeKeys.has(old)) { fields.delete(old); if (fields.size <= 180) break; }
          }
        }
        fields.set(key, createField());
      }
      const oldPosition = el.style.position;
      const changedPosition = style.position === 'static';
      if (changedPosition) el.style.position = 'relative';
      const mask = doc.createElement('span');
      mask.className = 'utgt-snow-mask';
      mask.setAttribute('aria-hidden', 'true');
      mask.style.borderRadius = style.borderRadius;
      mask.style.clipPath = 'inset(0 round ' + (style.borderRadius || '0px') + ')';
      const surface = doc.createElement('canvas');
      surface.className = 'utgt-snow-drift';
      surface.setAttribute('aria-hidden', 'true');
      mask.appendChild(surface);
      el.appendChild(mask);
      const entry = { el, key, canvas: surface, mask, oldPosition, changedPosition,
        leftRadius: parseFloat(style.borderTopLeftRadius) || 0,
        rightRadius: parseFloat(style.borderTopRightRadius) || 0, lastWidth: 0 };
      attached.set(el, entry);
      if (resizeWatcher) resizeWatcher.observe(el);
      paintDrift(entry);
      rectsDirty = true;
    }
    function release(entry) {
      if (resizeWatcher) resizeWatcher.unobserve(entry.el);
      entry.mask.remove();
      if (entry.changedPosition && entry.el.isConnected) entry.el.style.position = entry.oldPosition;
      attached.delete(entry.el);
    }
    function scan() {
      scanPending = false;
      if (!allowingDrifts() || (!fallingSnow() && !hasDrifts())) return;
      ensureStyle();
      const matches = new Set(doc.querySelectorAll(snowTargets));
      for (const entry of Array.from(attached.values())) {
        if (!entry.el.isConnected || !matches.has(entry.el) || entry.el.closest('dialog, [hidden]')) release(entry);
      }
      for (const el of matches) if (!attached.has(el) && !el.closest('dialog, [hidden]')) attach(el);
      rectsDirty = true;
    }
    function scheduleScan() {
      if (scanPending || doc.hidden || (!fallingSnow() && !hasDrifts())) return;
      scanPending = true;
      win.requestAnimationFrame(scan);
    }
    function ensureObservers() {
      if (watcher || !win.MutationObserver) return;
      watcher = new win.MutationObserver(records => {
        if (records.some(r => Array.from(r.addedNodes).concat(Array.from(r.removedNodes)).some(n =>
          n.nodeType === 1 && !(n.classList &&
          (n.classList.contains('utgt-snow-mask') || n.classList.contains('utgt-snow-drift')))))) scheduleScan();
      });
      watcher.observe(doc.body, {subtree:true, childList:true});
      if (typeof win.ResizeObserver === 'function') {
        resizeWatcher = new win.ResizeObserver(entries => {
          for (const r of entries) {
            const entry = attached.get(r.target);
            if (!entry) continue;
            const w = r.target.getBoundingClientRect().width;
            if (Math.abs(entry.lastWidth - w) > .5) {
              entry.lastWidth = w;
              paintDrift(entry);
            }
          }
          rectsDirty = true;
        });
        for (const entry of attached.values()) resizeWatcher.observe(entry.el);
      }
    }
    function removeCaps(clearData) {
      if (watcher) { watcher.disconnect(); watcher = null; }
      if (resizeWatcher) { resizeWatcher.disconnect(); resizeWatcher = null; }
      for (const entry of Array.from(attached.values())) release(entry);
      targets = []; rectsDirty = true;
      if (clearData) fields.clear();
      if (sheet) { sheet.remove(); sheet = null; }
    }
    function geometry(now) {
      if (!rectsDirty || now - lastGeometry < 65) return;
      const found = [];
      for (const entry of attached.values()) {
        if (!entry.el.isConnected || entry.el.closest('dialog,[hidden]')) continue;
        const box = entry.el.getBoundingClientRect();
        if (box.width < 22 || box.height < 18 || box.top < -8 || box.top > height + 8) continue;
        found.push({entry, box, radius:{left:entry.leftRadius,right:entry.rightRadius}});
      }
      found.sort((a,b) => a.box.top - b.box.top);
      targets = found; rectsDirty = false; lastGeometry = now;
    }
    function resize() {
      width = doc.documentElement.clientWidth; height = win.innerHeight;
      limits = budget(width, height, win.devicePixelRatio, win.navigator.deviceMemory, win.navigator.hardwareConcurrency);
      layer.width = Math.max(1, Math.ceil(width * limits.scale));
      layer.height = Math.max(1, Math.ceil(height * limits.scale));
      ctx.setTransform(limits.scale, 0, 0, limits.scale, 0, 0);
      particles = []; resizePending = false; rectsDirty = true;
      for (const entry of attached.values()) paintDrift(entry);
    }
    function particle(shape, initial) {
      return {x:random(0,width), y:initial ? random(-16,height+3):random(-80,-5),
        r:random(.75,2.5), speed:shape[1]+random(0,shape[2]), phase:random(0,Math.PI*2),
        color:shape[3][Math.floor(random(0,shape[3].length))], ornate:Math.random()<.2};
    }
    function dropDebris(entry, before, evtX) {
      if (!limits) return;
      const rect = entry.el.getBoundingClientRect();
      for (let i=0; i<Math.min(7, Math.ceil(before)); i++) {
        if (debris.length >= limits.debris) break;
        debris.push({x:clamp(evtX+random(-20,20),rect.left,rect.right), y:rect.top+random(0,6),
          vx:random(-45,45), vy:random(-20,15), life:random(.3,.8), r:random(.8,2)});
      }
    }
    function onHit(entry, localX) {
      const f = fields.get(entry.key);
      if (!f) return;
      impact(f, localX, random(.9,1.35), maxDepth * prefs.intensity / 100);
      paintDrift(entry);
    }
    function paintParticles(dt, opacity) {
      const kind = visual.effect;
      const shape = shapes[kind];
      if (!shape || reduced) return;
      const count = Math.min(limits.count, Math.round(shape[0]*opacity*Math.min(1.2,width/560+.5)));
      while (particles.length < count) particles.push(particle(shape,true));
      particles.length = count;
      for (let i=0;i<count;i++) {
        const p=particles[i], previousY=p.y;
        p.phase += dt*(kind==='lights'?.9:1.5);
        p.y += p.speed*dt;
        p.x += (Math.sin(p.phase)*15 + (visual.wind || 0)*2)*dt;
        if (p.y > height+12) { particles[i]=particle(shape,false); continue; }
        if (p.x < -10) p.x=width+9;
        if (p.x > width+10) p.x=-9;
        if (fallingSnow()) {
          let struck=false;
          for (const t of targets) {
            // DOMRect accessors are NOT enumerable. Spreading t.box here breaks all collisions.
            const rect={left:t.box.left,right:t.box.right,top:t.box.top,width:t.box.width,viewportHeight:height};
            if (!collision(p.x,previousY,p.y,rect,t.radius)) continue;
            if (Math.random() > .84) continue; // some flakes pass behind to lower cards
            onHit(t.entry,(p.x-t.box.left)/t.box.width);
            particles[i]=particle(shape,false); struck=true; break;
          }
          if (struck) continue;
        }
        ctx.globalAlpha = kind==='snow'?.75:kind==='lights'?.44:.48;
        ctx.fillStyle=ctx.strokeStyle=p.color;ctx.beginPath();
        if (kind==='rain') {
          ctx.moveTo(p.x,p.y);ctx.lineTo(p.x+(visual.wind||0)*.5,p.y+7+p.r*2);ctx.lineWidth=1;ctx.stroke();
        } else if(kind==='lights' && p.ornate) {
          for(let k=0;k<8;k++){const a=k*Math.PI/4,r=p.r*(k%2?.42:1.45);ctx.lineTo(p.x+Math.cos(a)*r,p.y+Math.sin(a)*r);}ctx.fill();
        } else if(kind==='petals' && p.ornate) {
          for(let k=0;k<5;k++){const a=p.phase+k*Math.PI*.4,x=p.x+Math.cos(a)*p.r,y=p.y+Math.sin(a)*p.r;ctx.moveTo(x+p.r*.5,y);ctx.arc(x,y,p.r*.5,0,2*Math.PI);}ctx.fill();
        } else {
          if(kind==='snow'||kind==='lights')ctx.arc(p.x,p.y,p.r,0,2*Math.PI);
          else ctx.ellipse(p.x,p.y,p.r*1.6,p.r*.65,p.phase,0,2*Math.PI);ctx.fill();
        }
      }
    }
    function paintDebris(dt) {
      ctx.fillStyle='#d7e9fb';ctx.globalAlpha=.7;
      debris=debris.filter(p=>{
        p.life-=dt;p.x+=p.vx*dt;p.y+=p.vy*dt;p.vy+=195*dt;
        if(p.life<=0||p.y>height)return false;
        ctx.beginPath();ctx.arc(p.x,p.y,p.r,0,2*Math.PI);ctx.fill();return true;
      });
    }
    function atmosphere(opacity) {
      const kind=visual.effect;
      if(kind==='sun'||kind==='cloud') {
        const h=Math.min(height*.23,170),g=ctx.createLinearGradient(0,0,0,h);
        g.addColorStop(0,kind==='sun'?'#efaf40':'#83a7cf');g.addColorStop(1,'transparent');
        ctx.globalAlpha=.13*opacity;ctx.fillStyle=g;ctx.fillRect(0,0,width,h);
      }
      if(visual.holiday) {
        const left=visual.holiday[5],right=visual.holiday[6];
        ctx.globalAlpha=.25+opacity*.27;ctx.fillStyle=visual.holiday[0]==='victory'?'#9d6841':'#bb8a44';
        ctx.font='18px system-ui,sans-serif';ctx.textAlign='center';
        ctx.fillText(left,18,height-17);ctx.fillText(right,width-18,height-17);
      }
    }
    function updateMelt(dt) {
      if (fallingSnow() || !hasDrifts()) return;
      let remaining=false;
      for(const f of fields.values()) if(melt(f,dt,.23)>.09) remaining=true;
      for (const entry of attached.values()) paintDrift(entry);
      if (!remaining) removeCaps(true);
    }
    function active() {
      return prefs.mode!=='off' && prefs.intensity>0 &&
        ((!reduced && Boolean(shapes[visual.effect])) || visual.effect==='sun' ||
        visual.effect==='cloud' || !!visual.holiday || debris.length>0 || hasDrifts());
    }
    function tick(time) {
      raf=0;
      if(doc.hidden||!active()) {sync();return;}
      if(resizePending)resize();
      const delta=previousFrame?time-previousFrame:limits.frameMs;
      if(delta<limits.frameMs-1){raf=win.requestAnimationFrame(tick);return;}
      previousFrame=time;
      if (rectsDirty) geometry(time);
      const dt=Math.min(delta/1000,.1),opacity=prefs.intensity/100;
      ctx.clearRect(0,0,width,height);atmosphere(opacity);
      paintParticles(dt,opacity);paintDebris(dt);
      if(!fallingSnow()&&hasDrifts()&&time-lastMeltTime>120) {
        updateMelt(Math.min((time-lastMeltTime)/1000,.4));lastMeltTime=time;
      } else if(fallingSnow()) lastMeltTime=time;
      ctx.globalAlpha=1;
      if (active() && ((!reduced && shapes[visual.effect]) || debris.length || hasDrifts())) raf=win.requestAnimationFrame(tick);
    }
    function sync() {
      if(raf){win.cancelAnimationFrame(raf);raf=0;}
      previousFrame=0;
      if(!allowingDrifts()) removeCaps(true);
      else if(fallingSnow()||hasDrifts()){ensureObservers();scheduleScan();}
      if(!active()){layer.remove();particles=[];debris=[];return;}
      if(!doc.hidden){if(!layer.isConnected){doc.body.appendChild(layer);resizePending=true;}raf=win.requestAnimationFrame(tick);}
    }
    doc.addEventListener('click',event=>{
      if(!prefs.physics||!allowingDrifts())return;
      const el=event.target.closest(snowTargets),entry=el&&attached.get(el);
      if(!entry)return;
      const field=fields.get(entry.key);
      if(!field)return;
      const before=maxHeight(field);
      if(before<.5)return;
      const rect=el.getBoundingClientRect(),x=(event.clientX-rect.left)/rect.width;
      for(let i=0;i<field.length;i++){
        const dist=Math.abs(i/(field.length-1)-x);
        field[i]*=dist<.3?(.22+.6*dist/.3):.72;
      }
      paintDrift(entry);dropDebris(entry,before,event.clientX||rect.left+rect.width/2);
    },true);
    doc.addEventListener('scroll',()=>{rectsDirty=true;},{capture:true,passive:true});
    doc.addEventListener('transitionend',()=>{rectsDirty=true;},true);
    win.addEventListener('resize',()=>{resizePending=true;rectsDirty=true;if(!raf&&active())sync();},{passive:true});
    doc.addEventListener('visibilitychange',()=>{if(!doc.hidden){rectsDirty=true;sync();}else if(raf){win.cancelAnimationFrame(raf);raf=0;}});
    return {
      configure(nextPrefs,nextVisual,motion) {
        if(visual.effect!==nextVisual.effect)particles=[];
        prefs=nextPrefs;visual=nextVisual;reduced=motion;sync();
      },
      visibility:sync
    };
  }
  return {create,budget,depth,shed,collision,createField,impact,melt,maxHeight,maxDepth};
});
