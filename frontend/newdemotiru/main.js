/* Controller: layout presets, WebGL setup, intro, parallax, adaptive resolution. */
(function () {
  'use strict';

  /* ======= TWEAK HERE =======
     hor   : height of the planet's top edge. 0 = screen centre, -0.5 = bottom, +0.5 = top
     rad   : planet radius (bigger = flatter horizon)
     tilt  : radians; positive = horizon rises to the right
     sunX  : sun position along the horizon (-0.5 left … +0.5 right, in screen-height units)
     k     : city-network cell size (bigger = smaller cells)
     bright: city light intensity                                                       */
  var CONFIG = {
    desktop: { hor: -0.20, rad: 2.60, tilt: 0.05,  sunX: 0.50, k: 1.7, bright: 1.35 },
    tablet:  { hor: -0.17, rad: 1.70, tilt: 0.10,  sunX: 0.24, k: 2.3, bright: 1.3 },
    mobile:  { hor: -0.24, rad: 0.95, tilt: 0.24,  sunX: 0.10, k: 2.5, bright: 1.45 }
  };
  var INTRO_MS = 2600;

  function preset() {
    var a = innerWidth / innerHeight;
    return a < 0.8 ? CONFIG.mobile : a < 1.3 ? CONFIG.tablet : CONFIG.desktop;
  }

  var cv = document.getElementById('sky');
  var gl = cv.getContext('webgl', { antialias: false, alpha: false, powerPreference: 'high-performance' }) ||
           cv.getContext('experimental-webgl');
  if (!gl) { document.documentElement.classList.add('no-gl'); return; }

  function compile(type, src) {
    var s = gl.createShader(type); gl.shaderSource(s, src); gl.compileShader(s);
    if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) { console.error(gl.getShaderInfoLog(s)); return null; }
    return s;
  }
  var vs = compile(gl.VERTEX_SHADER, 'attribute vec2 a;void main(){gl_Position=vec4(a,0.,1.);}');
  var fs = compile(gl.FRAGMENT_SHADER, window.TIRU_FRAG);
  if (!vs || !fs) { document.documentElement.classList.add('no-gl'); return; }

  var pr = gl.createProgram();
  gl.attachShader(pr, vs); gl.attachShader(pr, fs); gl.linkProgram(pr);
  if (!gl.getProgramParameter(pr, gl.LINK_STATUS)) { console.error(gl.getProgramInfoLog(pr)); document.documentElement.classList.add('no-gl'); return; }
  gl.useProgram(pr);

  var buf = gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER, buf);
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
  var loc = gl.getAttribLocation(pr, 'a');
  gl.enableVertexAttribArray(loc); gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);

  var U = {};
  ['R','T','M','uHor','uRad','uTilt','uSunX','uK','uIntro','uBright','uPortrait'].forEach(function (n) {
    U[n] = gl.getUniformLocation(pr, n);
  });

  var dpr = Math.min(window.devicePixelRatio || 1, 1.5), minDpr = 0.7;
  function resize() {
    cv.width = Math.floor(innerWidth * dpr);
    cv.height = Math.floor(innerHeight * dpr);
    gl.viewport(0, 0, cv.width, cv.height);
  }
  addEventListener('resize', resize); resize();

  var tx = .5, ty = .5, mx = .5, my = .5;
  addEventListener('pointermove', function (e) { tx = e.clientX / innerWidth; ty = 1 - e.clientY / innerHeight; });
  addEventListener('deviceorientation', function (e) {
    if (e.gamma == null) return;
    tx = .5 + Math.max(-30, Math.min(30, e.gamma)) / 120;
    ty = .5 - Math.max(-30, Math.min(30, (e.beta || 45) - 45)) / 120;
  });

  var still = matchMedia('(prefers-reduced-motion: reduce)').matches;
  var t0 = performance.now(), last = t0, slow = 0, frames = 0, running = false;

  function ease(x) { x = Math.min(Math.max(x, 0), 1); return 1 - Math.pow(1 - x, 3); }

  function frame(now) {
    running = false;
    var dt = now - last; last = now;

    // adaptive resolution: if we're consistently slow, render fewer pixels
    if (dt > 26) slow++; else slow = Math.max(0, slow - 1);
    if (slow > 25 && dpr > minDpr) { dpr = Math.max(minDpr, dpr * .82); slow = 0; resize(); }

    mx += (tx - mx) * .04; my += (ty - my) * .04;
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
    gl.drawArrays(gl.TRIANGLES, 0, 3);

    if (!still && !document.hidden) { running = true; requestAnimationFrame(frame); }
  }
  requestAnimationFrame(frame);
  document.addEventListener('visibilitychange', function () {
    if (!document.hidden && !still && !running) { last = performance.now(); running = true; requestAnimationFrame(frame); }
  });
  if (still) addEventListener('resize', function () { requestAnimationFrame(frame); });
})();
