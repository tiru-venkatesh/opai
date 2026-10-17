/* OPAI shared shader background (Stitch glass-orb shader).
 * One <script src="opai-shader.js" defer></script> per page. Behaviour:
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
    /* light palette (Stitch) */
    'const vec3 L_BG_TOP=vec3(0.965,0.972,0.968);const vec3 L_BG_BOT=vec3(0.915,0.932,0.925);',
    'const vec3 L_SAGE=vec3(0.79,0.85,0.82);const vec3 L_TEAL_D=vec3(0.06,0.32,0.34);',
    'const vec3 L_TEAL_L=vec3(0.24,0.62,0.64);const vec3 L_WARM=vec3(0.99,0.99,0.98);',
    /* dark palette (matches the app dark theme paper #120F0F with teal accents) */
    'const vec3 D_BG_TOP=vec3(0.071,0.059,0.059);const vec3 D_BG_BOT=vec3(0.108,0.092,0.092);',
    'const vec3 D_SAGE=vec3(0.12,0.24,0.27);const vec3 D_TEAL_D=vec3(0.10,0.30,0.36);',
    'const vec3 D_TEAL_L=vec3(0.22,0.45,0.53);const vec3 D_WARM=vec3(0.30,0.36,0.37);',
    'float sdSphere(vec3 p,float r){return length(p)-r;}',
    'float smin(float a,float b,float k){float h=clamp(0.5+0.5*(b-a)/k,0.0,1.0);return mix(b,a,h)-k*h*(1.0-h);}',
    'float map(vec3 p,float t,vec2 m){',
    ' vec3 q=p-vec3((m.x-0.5)*0.4,(m.y-0.5)*0.3,0.0);',
    ' vec3 c1=vec3(-0.9+sin(t*0.35)*0.25,0.2+cos(t*0.28)*0.2,0.2+sin(t*0.2)*0.15);',
    ' vec3 c2=vec3(1.1+cos(t*0.3)*0.22,0.6+sin(t*0.4)*0.2,-0.3+cos(t*0.25)*0.2);',
    ' vec3 c3=vec3(0.4+sin(t*0.25+2.0)*0.3,-0.8+cos(t*0.32)*0.2,-0.1);',
    ' vec3 c4=vec3(-0.2+cos(t*0.2)*0.4,0.8+sin(t*0.25)*0.25,-1.2);',
    ' float d=smin(sdSphere(q-c1,0.85),sdSphere(q-c2,0.65),0.45);',
    ' d=smin(d,sdSphere(q-c3,0.55),0.4);d=smin(d,sdSphere(q-c4,1.1),0.6);return d;}',
    'vec3 calcNormal(vec3 p,float t,vec2 m){const float eps=0.002;vec2 e=vec2(1.0,-1.0)*0.5773*eps;',
    ' return normalize(e.xyy*map(p+e.xyy,t,m)+e.yyx*map(p+e.yyx,t,m)+e.yxy*map(p+e.yxy,t,m)+e.xxx*map(p+e.xxx,t,m));}',
    'void main(){',
    ' vec3 C_BG_TOP=mix(L_BG_TOP,D_BG_TOP,u_dark);vec3 C_BG_BOTTOM=mix(L_BG_BOT,D_BG_BOT,u_dark);',
    ' vec3 C_SAGE_SOFT=mix(L_SAGE,D_SAGE,u_dark);vec3 C_TEAL_DARK=mix(L_TEAL_D,D_TEAL_D,u_dark);',
    ' vec3 C_TEAL_LIGHT=mix(L_TEAL_L,D_TEAL_L,u_dark);vec3 C_WARM_WHITE=mix(L_WARM,D_WARM,u_dark);',
    ' vec2 uv=gl_FragCoord.xy/u_resolution.xy;',
    ' vec2 p=(gl_FragCoord.xy-0.5*u_resolution.xy)/min(u_resolution.x,u_resolution.y);',
    ' vec2 m=u_mouse/u_resolution.xy;if(length(u_mouse)<1.0){m=vec2(0.5);}',
    ' float t=u_time*0.45;',
    ' vec2 bgShift=vec2(sin(t*0.2+uv.y*2.0)*0.05,cos(t*0.18+uv.x*2.0)*0.05);',
    ' vec3 bgColor=mix(C_BG_TOP,C_BG_BOTTOM,uv.y+bgShift.y);',
    ' float wave=sin(uv.x*3.1415+t*0.3)*cos(uv.y*2.5-t*0.25);',
    ' vec3 sageDelta=mix(L_SAGE-0.8,vec3(0.02,0.06,0.07),u_dark);',
    ' bgColor+=sageDelta*0.25*smoothstep(-0.5,0.8,wave);',
    ' float tealGlow=1.0-length(uv-vec2(0.5+(m.x-0.5)*0.2,0.45+(m.y-0.5)*0.2));',
    ' bgColor=mix(bgColor,C_TEAL_DARK,clamp(tealGlow*0.12,0.0,1.0));',
    ' vec3 ro=vec3(0.0,0.0,2.5);vec3 rd=normalize(vec3(p,-1.6));',
    ' float dist=0.0;float hitDist=-1.0;float accum=0.0;',
    ' for(int i=0;i<48;i++){vec3 pos=ro+rd*dist;float d=map(pos,t,m);',
    '  if(d<0.003){hitDist=dist;break;}',
    '  accum+=exp(-d*3.5)*0.015;dist+=max(d*0.65,0.02);if(dist>6.0)break;}',
    ' vec3 col=bgColor;',
    ' col=mix(col,mix(C_SAGE_SOFT,C_TEAL_LIGHT,0.35),clamp(accum*0.85,0.0,0.35));',
    ' if(hitDist>0.0){',
    '  vec3 hp=ro+rd*hitDist;vec3 n=calcNormal(hp,t,m);vec3 v=-rd;',
    '  float fr=pow(clamp(1.0-dot(v,n),0.0,1.0),3.0);',
    '  vec3 tint=mix(C_WARM_WHITE,C_TEAL_LIGHT,0.35);tint=mix(tint,C_TEAL_DARK,fr*0.4);',
    '  vec3 ld=normalize(vec3(-0.6,1.2,0.8));',
    '  float sp=pow(max(dot(reflect(-ld,n),v),0.0),24.0);',
    '  vec3 gr=mix(bgColor*0.94,tint,0.28+fr*0.45);gr+=C_WARM_WHITE*sp*0.45;gr+=C_TEAL_LIGHT*fr*0.3;',
    '  col=mix(col,gr,smoothstep(5.0,1.8,hitDist)*0.55);}',
    ' vec2 pt=fract(uv*12.0+vec2(t*0.03,t*0.05))-0.5;',
    ' col+=vec3(smoothstep(0.08,0.0,length(pt))*sin(uv.x*20.0+t*1.5)*0.08)*C_TEAL_LIGHT;',
    ' float vg=1.0-smoothstep(0.5,1.3,length(uv-0.5));col=mix(col*0.98,col,vg);',
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
