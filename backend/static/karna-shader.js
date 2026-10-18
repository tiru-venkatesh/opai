/* KARNA chat shader background (lilac / royal / violet aurora + lime accent, mouse-reactive).
 * One <script src="karna-shader.js" defer></script> per page. Behaviour:
 *  - fixed full-screen canvas behind all content (z-index:-1, pointer-events:none)
 *  - light palette by default, dark palette when <html data-theme="dark"> (follows the theme toggle live)
 *  - cheap: renders at reduced resolution, 30 fps, pauses when the tab is hidden
 *  - one static frame (no animation) for prefers-reduced-motion, Save-Data, or weak devices
 *  - body only becomes transparent AFTER the first frame is drawn; if WebGL is missing/fails, the page keeps its normal solid background
 *  - off switches: ?shader=0 in the URL, or localStorage opai_shader = "0"; auto-off in ?embed=1 and when printing
 */
(function () {
  'use strict';
  if (window.__opaiShader) return;
  window.__opaiShader = true;

  var doc = document, root = doc.documentElement, q = location.search;
  try { if (/[?&]shader=0/.test(q) || localStorage.getItem('opai_shader') === '0') return; } catch (e) {}
  if (/[?&]embed=1/.test(q)) return;

  var reduce = window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)');
  var conn = navigator.connection || {};
  var weak = !!(conn.saveData || (navigator.deviceMemory && navigator.deviceMemory <= 2) ||
                (navigator.hardwareConcurrency && navigator.hardwareConcurrency <= 2));
  var still = !!((reduce && reduce.matches) || weak);
  var small = Math.min(screen.width || 1024, window.innerWidth || 1024) < 700;

  var VS = 'attribute vec2 a_position;void main(){gl_Position=vec4(a_position,0.0,1.0);}';

  var FS = [
    '#ifdef GL_FRAGMENT_PRECISION_HIGH',
    'precision highp float;',
    '#else',
    'precision mediump float;',
    '#endif',
    'uniform float u_time;uniform vec2 u_resolution;uniform vec2 u_mouse;uniform float u_dark;',
    'vec3 permute(vec3 x){return mod(((x*34.0)+1.0)*x,289.0);}',
    'float snoise(vec2 v){',
    ' const vec4 C=vec4(0.211324865405187,0.366025403784439,-0.577350269189626,0.024390243902439);',
    ' vec2 i=floor(v+dot(v,C.yy));vec2 x0=v-i+dot(i,C.xx);',
    ' vec2 i1=(x0.x>x0.y)?vec2(1.0,0.0):vec2(0.0,1.0);',
    ' vec4 x12=x0.xyxy+C.xxzz;x12.xy-=i1;i=mod(i,289.0);',
    ' vec3 p=permute(permute(i.y+vec3(0.0,i1.y,1.0))+i.x+vec3(0.0,i1.x,1.0));',
    ' vec3 m=max(0.5-vec3(dot(x0,x0),dot(x12.xy,x12.xy),dot(x12.zw,x12.zw)),0.0);m=m*m;m=m*m;',
    ' vec3 x=2.0*fract(p*C.www)-1.0;vec3 h=abs(x)-0.5;vec3 ox=floor(x+0.5);vec3 a0=x-ox;',
    ' m*=1.79284291400159-0.85373472095314*(a0*a0+h*h);',
    ' vec3 g;g.x=a0.x*x0.x+h.x*x0.y;g.yz=a0.yz*x12.xz+h.yz*x12.yw;return 130.0*dot(m,g);}',
    'void main(){',
    ' vec2 st=gl_FragCoord.xy/u_resolution.xy;',
    ' vec2 mouse=u_mouse/u_resolution.xy;',
    ' float aspect=u_resolution.x/u_resolution.y;',
    ' vec2 p=(st-0.5)*vec2(aspect,1.0);',
    ' float t=u_time*0.25;',
    ' float n1=snoise(p*1.8+vec2(t*0.4,-t*0.3));',
    ' float n2=snoise(p*3.2-vec2(n1*0.6,t*0.5)+mouse*0.3);',
    ' float n3=snoise(p*2.5+vec2(n2*0.8,t*0.2));',
    ' vec3 cBg=mix(vec3(0.976,0.973,0.992),vec3(0.055,0.043,0.125),u_dark);',
    ' vec3 cLav=mix(vec3(0.910,0.918,0.988),vec3(0.105,0.082,0.235),u_dark);',
    ' vec3 cPur=mix(vec3(0.518,0.322,0.941),vec3(0.330,0.190,0.640),u_dark);',
    ' vec3 cRoy=mix(vec3(0.365,0.376,0.929),vec3(0.200,0.210,0.620),u_dark);',
    ' vec3 cLime=mix(vec3(0.812,0.965,0.412),vec3(0.420,0.520,0.150),u_dark);',
    ' float radial=length(st-vec2(0.5,0.45));',
    ' float glow1=smoothstep(0.85,0.1,radial+n1*0.35);',
    ' float glow2=smoothstep(0.7,0.05,length(st-vec2(0.65,0.3))+n2*0.3);',
    ' float lime=smoothstep(0.92,0.15,length(st-vec2(0.5,0.15))+n3*0.4)*0.18;',
    ' vec3 col=mix(cBg,cLav,clamp(n1*0.7+0.3,0.0,1.0));',
    ' col=mix(col,cRoy,clamp(glow1*0.45*(n2*0.5+0.5),0.0,1.0));',
    ' col=mix(col,cPur,clamp(glow2*0.55*(n3*0.5+0.5),0.0,1.0));',
    ' col=mix(col,cLime,clamp(lime,0.0,1.0));',
    ' col+=fract(sin(dot(gl_FragCoord.xy,vec2(12.9898,78.233)))*43758.5453)*0.018-0.009;',
    ' gl_FragColor=vec4(col,1.0);}'
  ].join('\n');

  function start() {
    if (!doc.body || doc.getElementById('opai-shader')) return;

    var canvas = doc.createElement('canvas');
    canvas.id = 'opai-shader';
    canvas.setAttribute('aria-hidden', 'true');
    canvas.style.cssText = 'position:fixed;left:0;top:0;width:100%;height:100%;z-index:-1;pointer-events:none;display:block';

    var gl = null;
    try {
      gl = canvas.getContext('webgl', { alpha: false, antialias: false, depth: false, stencil: false,
                                        powerPreference: 'low-power', preserveDrawingBuffer: false }) ||
           canvas.getContext('experimental-webgl');
    } catch (e) {}
    if (!gl) return;

    function compile(type, src) {
      var s = gl.createShader(type);
      gl.shaderSource(s, src); gl.compileShader(s);
      if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) {
        try { console.warn('[opai-shader] compile failed:', gl.getShaderInfoLog(s)); } catch (e) {}
        return null;
      }
      return s;
    }
    var vs = compile(gl.VERTEX_SHADER, VS), fs = compile(gl.FRAGMENT_SHADER, FS);
    if (!vs || !fs) return;
    var prog = gl.createProgram();
    gl.attachShader(prog, vs); gl.attachShader(prog, fs); gl.linkProgram(prog);
    if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) return;
    gl.useProgram(prog);

    var buf = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buf);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]), gl.STATIC_DRAW);
    var loc = gl.getAttribLocation(prog, 'a_position');
    gl.enableVertexAttribArray(loc);
    gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);
    var uTime = gl.getUniformLocation(prog, 'u_time'), uRes = gl.getUniformLocation(prog, 'u_resolution'),
        uMouse = gl.getUniformLocation(prog, 'u_mouse'), uDark = gl.getUniformLocation(prog, 'u_dark');

    doc.body.insertBefore(canvas, doc.body.firstChild);

    var scale = small ? 0.35 : 0.5, W = 2, H = 2;
    function size() {
      var w = Math.max(2, Math.round((window.innerWidth || 1024) * scale)),
          h = Math.max(2, Math.round((window.innerHeight || 768) * scale));
      var k = Math.min(1, 960 / Math.max(w, h)); w = Math.round(w * k); h = Math.round(h * k);
      if (w !== W || h !== H) { W = canvas.width = w; H = canvas.height = h; gl.viewport(0, 0, W, H); }
    }

    function isDark() {
      return root.getAttribute('data-theme') === 'dark' || root.classList.contains('dark') ? 1 : 0;
    }
    var dark = isDark(), darkTarget = dark;
    var mx = 0.5, my = 0.5, tx = 0.5, ty = 0.5;       // normalised mouse (eased)
    var time = still ? 7.5 : 0, last = 0, raf = 0, shown = false, lost = false;

    function draw() {
      if (lost) return;
      gl.uniform1f(uTime, time);
      gl.uniform2f(uRes, W, H);
      gl.uniform2f(uMouse, mx * W, my * H);
      gl.uniform1f(uDark, dark);
      gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
      if (!shown) { shown = true; root.classList.add('opai-shader-on'); }
    }

    function frame(now) {
      raf = 0;
      if (doc.hidden || lost) return;
      if (now - last >= 33) {                          // ~30 fps cap
        var dt = last ? Math.min((now - last) / 1000, 0.1) : 0.033;
        last = now; time += dt;
        mx += (tx - mx) * 0.06; my += (ty - my) * 0.06;
        dark += (darkTarget - dark) * 0.12;
        draw();
      }
      raf = requestAnimationFrame(frame);
    }
    function run() { if (!still && !raf && !doc.hidden && !lost) raf = requestAnimationFrame(frame); }
    function halt() { if (raf) { cancelAnimationFrame(raf); raf = 0; } last = 0; }

    size(); draw();                                     // first frame immediately (also the only frame in "still" mode)
    run();

    var rt = 0;
    addEventListener('resize', function () { clearTimeout(rt); rt = setTimeout(function () { size(); draw(); }, 150); });
    doc.addEventListener('visibilitychange', function () { doc.hidden ? halt() : run(); });
    if (!still && !small) {
      addEventListener('mousemove', function (e) {
        tx = e.clientX / Math.max(1, window.innerWidth); ty = 1 - e.clientY / Math.max(1, window.innerHeight);
      }, { passive: true });
    }

    // follow the theme toggle live
    try {
      new MutationObserver(function () {
        darkTarget = isDark();
        if (still) { dark = darkTarget; draw(); }
      }).observe(root, { attributes: true, attributeFilter: ['data-theme', 'class'] });
    } catch (e) {}
    if (reduce && reduce.addEventListener) reduce.addEventListener('change', function () { location.reload(); });

    // GPU reset: fall back to the page's normal solid background instead of a frozen/black frame
    canvas.addEventListener('webglcontextlost', function (e) {
      e.preventDefault(); lost = true; halt(); root.classList.remove('opai-shader-on'); canvas.style.display = 'none';
    });
    canvas.addEventListener('webglcontextrestored', function () { location.reload(); });
  }

  var st = doc.createElement('style');
  st.textContent = '@media screen{html.opai-shader-on body{background:transparent!important}}' +
                   '@media print{#opai-shader{display:none!important}}';
  (doc.head || root).appendChild(st);

  if (doc.body) start(); else doc.addEventListener('DOMContentLoaded', start);
})();
