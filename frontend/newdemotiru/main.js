/* Controller: layout presets, WebGL, intro, pointer + scroll interaction, custom cursor. */
(function () {
  'use strict';

  /* ======= TWEAK HERE =======
     hor: planet edge height (0 centre, -0.5 bottom) · rad: horizon curvature · tilt: radians
     sunX: sun position on horizon · k: city cell size · bright: light intensity            */
  var CONFIG = {
    desktop: { hor: -0.20, rad: 2.60, tilt: 0.05, sunX: 0.50, k: 1.7, bright: 1.35 },
    tablet:  { hor: -0.17, rad: 1.70, tilt: 0.10, sunX: 0.24, k: 2.3, bright: 1.3 },
    mobile:  { hor: -0.24, rad: 0.95, tilt: 0.24, sunX: 0.10, k: 2.5, bright: 1.45 }
  };
  var INTRO_MS = 2600, RIPPLE_LIFE = 2.7;

  function preset() {
    var a = innerWidth / innerHeight;
    return a < 0.8 ? CONFIG.mobile : a < 1.3 ? CONFIG.tablet : CONFIG.desktop;
  }

  var root = document.documentElement;
  var fine = matchMedia('(pointer: fine)').matches;
  var still = matchMedia('(prefers-reduced-motion: reduce)').matches;

  /* ---------- reveal on scroll ---------- */
  if ('IntersectionObserver' in window) {
    var io = new IntersectionObserver(function (es) {
      es.forEach(function (x) { if (x.isIntersecting) { x.target.classList.add('in'); io.unobserve(x.target); } });
    }, { threshold: 0.15 });
    document.querySelectorAll('.reveal').forEach(function (n) { io.observe(n); });
  } else {
    document.querySelectorAll('.reveal').forEach(function (n) { n.classList.add('in'); });
  }

  /* ---------- WebGL ---------- */
  var cv = document.getElementById('sky');
  var gl = cv.getContext('webgl', { antialias: false, alpha: false, powerPreference: 'high-performance' }) ||
           cv.getContext('experimental-webgl');
  if (!gl) { root.classList.add('no-gl'); return; }

  function compile(type, src) {
    var s = gl.createShader(type); gl.shaderSource(s, src); gl.compileShader(s);
    if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) { console.error(gl.getShaderInfoLog(s)); return null; }
    return s;
  }
  var vs = compile(gl.VERTEX_SHADER, 'attribute vec2 a;void main(){gl_Position=vec4(a,0.,1.);}');
  var fs = compile(gl.FRAGMENT_SHADER, window.TIRU_FRAG);
  if (!vs || !fs) { root.classList.add('no-gl'); return; }
  var pr = gl.createProgram();
  gl.attachShader(pr, vs); gl.attachShader(pr, fs); gl.linkProgram(pr);
  if (!gl.getProgramParameter(pr, gl.LINK_STATUS)) { console.error(gl.getProgramInfoLog(pr)); root.classList.add('no-gl'); return; }
  gl.useProgram(pr);

  var buf = gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER, buf);
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
  var loc = gl.getAttribLocation(pr, 'a');
  gl.enableVertexAttribArray(loc); gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);

  var U = {};
  ['R','T','M','uHor','uRad','uTilt','uSunX','uK','uIntro','uBright','uPortrait','uScroll','uVel','uPtrOn','uPtr','uRip']
    .forEach(function (n) { U[n] = gl.getUniformLocation(pr, n); });

  var dpr = Math.min(window.devicePixelRatio || 1, 1.5), minDpr = 0.7;
  function resize() {
    cv.width = Math.floor(innerWidth * dpr);
    cv.height = Math.floor(innerHeight * dpr);
    gl.viewport(0, 0, cv.width, cv.height);
    readScroll();
  }

  /* ---------- scroll: smoothed progress + velocity ---------- */
  var range = 1, sTarget = 0, sCur = 0, sPrev = 0, vel = 0;
  function readScroll() {
    range = Math.max(1, root.scrollHeight - innerHeight);
    sTarget = Math.min(1, Math.max(0, (window.scrollY || root.scrollTop) / range));
    root.style.setProperty('--sp', sTarget.toFixed(4));
  }
  addEventListener('scroll', function () { readScroll(); if (still) requestAnimationFrame(frame); }, { passive: true });
  addEventListener('resize', resize);

  /* ---------- pointer: glow, lens and click shockwaves ---------- */
  var ptr = { x: 0, y: -0.3, sx: 0, sy: -0.3, on: 0, target: 0 };
  var ripples = [{t:-1,x:0,y:0},{t:-1,x:0,y:0},{t:-1,x:0,y:0},{t:-1,x:0,y:0}], ripI = 0;
  var rbuf = new Float32Array(12), interacted = false, t0 = performance.now();

  function toUV(cx, cy) { return { x: (cx - innerWidth / 2) / innerHeight, y: (innerHeight / 2 - cy) / innerHeight }; }
  function setPtr(e) {
    var u = toUV(e.clientX, e.clientY);
    ptr.x = u.x; ptr.y = u.y; ptr.target = 1;
    if (!interacted) { ptr.sx = u.x; ptr.sy = u.y; }
    interacted = true;
    if (cur) { curX = e.clientX; curY = e.clientY; cur.classList.add('on'); }
  }
  function pulse(x, y) {
    var r = ripples[ripI++ % 4]; r.x = x; r.y = y; r.t = performance.now();
  }
  addEventListener('pointermove', setPtr, { passive: true });
  addEventListener('pointerdown', function (e) {
    setPtr(e);
    var u = toUV(e.clientX, e.clientY); pulse(u.x, u.y);
    if (cur) cur.classList.add('down');
  }, { passive: true });
  addEventListener('pointerup', function (e) {
    if (cur) cur.classList.remove('down');
    if (e.pointerType !== 'mouse') setTimeout(function () { ptr.target = 0; }, 650);
  }, { passive: true });
  document.addEventListener('pointerleave', function () { ptr.target = 0; if (cur) cur.classList.remove('on'); });

  /* gentle hint: one idle shockwave if nobody has touched anything yet */
  setTimeout(function () { if (!interacted) pulse(0.22, -0.28); }, 3400);
  setTimeout(function () { if (!interacted) pulse(-0.2, -0.32); }, 8000);

  /* device tilt parallax */
  var tx = .5, ty = .5, mx = .5, my = .5;
  addEventListener('pointermove', function (e) { tx = e.clientX / innerWidth; ty = 1 - e.clientY / innerHeight; }, { passive: true });
  addEventListener('deviceorientation', function (e) {
    if (e.gamma == null) return;
    tx = .5 + Math.max(-30, Math.min(30, e.gamma)) / 120;
    ty = .5 - Math.max(-30, Math.min(30, (e.beta || 45) - 45)) / 120;
  });

  /* ---------- custom cursor (fine pointers only) ---------- */
  var cur = null, dot, ring, curX = -100, curY = -100, rx = -100, ry = -100;
  if (fine) {
    cur = document.getElementById('cursor'); dot = cur.querySelector('.cdot'); ring = cur.querySelector('.cring');
    root.classList.add('has-cursor');
    document.addEventListener('pointerover', function (e) {
      cur.classList.toggle('link', !!e.target.closest('a,button,[data-hover]'));
    });
  }

  resize();

  /* ---------- frame loop ---------- */
  var last = t0, slow = 0, running = false;
  function ease(x) { x = Math.min(Math.max(x, 0), 1); return 1 - Math.pow(1 - x, 3); }

  function frame(now) {
    running = false;
    var dt = now - last; last = now;
    if (dt > 26) slow++; else slow = Math.max(0, slow - 1);
    if (slow > 25 && dpr > minDpr) { dpr = Math.max(minDpr, dpr * .82); slow = 0; resize(); }

    mx += (tx - mx) * .04; my += (ty - my) * .04;
    ptr.sx += (ptr.x - ptr.sx) * .16; ptr.sy += (ptr.y - ptr.sy) * .16;
    ptr.on += (ptr.target - ptr.on) * .09;
    sCur += (sTarget - sCur) * .07;
    var dv = Math.abs(sCur - sPrev) * range / innerHeight; sPrev = sCur;
    vel += (Math.min(dv * 14, 1) - vel) * .12;

    if (cur) {
      rx += (curX - rx) * .18; ry += (curY - ry) * .18;
      dot.style.transform = 'translate3d(' + curX + 'px,' + curY + 'px,0)';
      ring.style.transform = 'translate3d(' + rx + 'px,' + ry + 'px,0)';
    }

    for (var i = 0; i < 4; i++) {
      var r = ripples[i], age = r.t < 0 ? -1 : (now - r.t) / 1000;
      if (age > RIPPLE_LIFE) { r.t = -1; age = -1; }
      rbuf[i * 3] = r.x; rbuf[i * 3 + 1] = r.y; rbuf[i * 3 + 2] = age;
    }

    var P = preset();
    var intro = still ? 1 : ease((now - t0 - 150) / INTRO_MS);
    gl.uniform2f(U.R, cv.width, cv.height);
    gl.uniform1f(U.T, (now - t0) / 1000);
    gl.uniform2f(U.M, mx, my);
    gl.uniform1f(U.uHor, P.hor);
    gl.uniform1f(U.uRad, P.rad);
    gl.uniform1f(U.uTilt, P.tilt);
    gl.uniform1f(U.uSunX, P.sunX);
    gl.uniform1f(U.uK, P.k);
    gl.uniform1f(U.uBright, P.bright);
    gl.uniform1f(U.uIntro, intro);
    gl.uniform1f(U.uPortrait, innerWidth / innerHeight < 0.9 ? 1 : 0);
    gl.uniform1f(U.uScroll, sCur);
    gl.uniform1f(U.uVel, vel);
    gl.uniform1f(U.uPtrOn, ptr.on);
    gl.uniform2f(U.uPtr, ptr.sx, ptr.sy);
    gl.uniform3fv(U.uRip, rbuf);
    gl.drawArrays(gl.TRIANGLES, 0, 3);

    if (!still && !document.hidden) { running = true; requestAnimationFrame(frame); }
  }
  requestAnimationFrame(frame);
  document.addEventListener('visibilitychange', function () {
    if (!document.hidden && !still && !running) { last = performance.now(); running = true; requestAnimationFrame(frame); }
  });
  if (still) addEventListener('resize', function () { requestAnimationFrame(frame); });
})();
