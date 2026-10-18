/* OPAI hero shader: the Stitch "kinetic prismatic ribbon" WebGL background.
   Usage: <canvas data-opai-shader></canvas> inside a positioned container. Falls back silently to the CSS gradient. */
(function () {
  var FS = `precision highp float;
uniform float u_time;
uniform vec2 u_resolution;
uniform vec2 u_mouse;
varying vec2 v_texCoord;

// Simplex-style noise and rotation helpers
vec3 permute(vec3 x) { return mod(((x*34.0)+1.0)*x, 289.0); }

float snoise(vec2 v){
  const vec4 C = vec4(0.211324865405187, 0.366025403784439,
           -0.577350269189626, 0.024390243902439);
  vec2 i  = floor(v + dot(v, C.yy) );
  vec2 x0 = v -   i + dot(i, C.xx);
  vec2 i1;
  i1 = (x0.x > x0.y) ? vec2(1.0, 0.0) : vec2(0.0, 1.0);
  vec4 x12 = x0.xyxy + C.xxzz;
  x12.xy -= i1;
  i = mod(i, 289.0);
  vec3 p = permute( permute( i.y + vec3(0.0, i1.y, 1.0 ))
  + i.x + vec3(0.0, i1.x, 1.0 ));
  vec3 m = max(0.5 - vec3(dot(x0,x0), dot(x12.xy,x12.xy),
    dot(x12.zw,x12.zw)), 0.0);
  m = m*m ;
  m = m*m ;
  vec3 x = 2.0 * fract(p * C.www) - 1.0;
  vec3 h = abs(x) - 0.5;
  vec3 ox = floor(x + 0.5);
  vec3 a0 = x - ox;
  m *= 1.79284291400159 - 0.85373472095314 * ( a0*a0 + h*h );
  vec3 g;
  g.x  = a0.x  * x0.x  + h.x  * x0.y;
  g.yz = a0.yz * x12.xz + h.yz * x12.yw;
  return 130.0 * dot(m, g);
}

mat2 rot(float a) {
  float c = cos(a), s = sin(a);
  return mat2(c, -s, s, c);
}

void main() {
    vec2 uv = gl_FragCoord.xy / u_resolution.xy;
    vec2 mouse = u_mouse / u_resolution.xy;
    float aspect = u_resolution.x / u_resolution.y;
    vec2 p = (uv - 0.5) * vec2(aspect, 1.0);

    float t = u_time * 0.28;

    // Interactive mouse displacement with smooth falloff
    vec2 mPos = (mouse - 0.5) * vec2(aspect, 1.0);
    float mDist = length(p - mPos);
    p += (p - mPos) * exp(-mDist * 4.0) * 0.12;

    // Kinetic Prismatic Ribbon & Caustic Wave Formula
    vec2 pRot = p * rot(t * 0.15 + length(p) * 0.35);

    // Multi-harmonic oscillating wave bands
    float wave1 = sin(pRot.x * 3.8 + t * 1.2 + snoise(p * 2.2));
    float wave2 = cos(pRot.y * 4.2 - t * 0.9 + wave1 * 0.6);
    float wave3 = sin((pRot.x + pRot.y) * 2.5 + t * 0.7);

    // Prismatic chromatic dispersion / refraction simulation
    float rField = snoise(p * 2.6 + vec2(wave1 * 0.4, wave2 * 0.3) + vec2(0.015, -0.015));
    float gField = snoise(p * 2.6 + vec2(wave1 * 0.4, wave2 * 0.3));
    float bField = snoise(p * 2.6 + vec2(wave1 * 0.4, wave2 * 0.3) - vec2(0.015, -0.015));

    // Caustic luminous ribbon filaments
    float filament = 1.0 - smoothstep(0.0, 0.28, abs(wave2 + wave3 * 0.5));
    filament = pow(filament, 2.5);

    float filament2 = 1.0 - smoothstep(0.0, 0.32, abs(wave1 - wave2 * 0.4));
    filament2 = pow(filament2, 3.0);

    // Palette: Crisp high-luminance porcelain surface with electric kinetic aura
    vec3 cBase = vec3(0.98, 0.98, 1.0);            // Pure luminous porcelain #fafaff
    vec3 cLilac = vec3(0.925, 0.933, 0.995);       // Soft lavender ice #eceffa
    vec3 cViolet = vec3(0.533, 0.282, 0.965);      // Deep KARNA Electric Violet #8848f6
    vec3 cCyan = vec3(0.247, 0.584, 0.988);        // Prismatic Cyan #3f95fc
    vec3 cLime = vec3(0.796, 0.973, 0.388);        // Cyber Kinetic Lime #cbf863
    vec3 cMagenta = vec3(0.851, 0.314, 0.882);     // Prismatic Magenta highlight

    // Radial center soft glow
    float rad = length(uv - vec2(0.5, 0.46));
    float centerGlow = smoothstep(0.9, 0.1, rad);

    // Composite layers
    vec3 color = mix(cBase, cLilac, clamp(rField * 0.5 + 0.5, 0.0, 1.0));
    
    // Violet and cyan wave currents
    color = mix(color, cViolet, clamp((gField * 0.5 + 0.5) * centerGlow * 0.65, 0.0, 1.0));
    color = mix(color, cCyan, clamp((bField * 0.5 + 0.5) * 0.4, 0.0, 1.0));

    // Luminous caustic highlights
    color += cLime * filament * 0.38;
    color += cMagenta * filament2 * 0.25;
    color += cViolet * filament * filament2 * 0.45;

    // High-frequency subtle analog micro-dithering (renders crisp and stops any banding)
    float dither = fract(sin(dot(gl_FragCoord.xy, vec2(12.9898, 78.233))) * 43758.5453) * 0.012 - 0.006;
    color += dither;

    gl_FragColor = vec4(color, 1.0);
}`;
  var VS = 'attribute vec2 a_position;void main(){gl_Position=vec4(a_position,0.0,1.0);}';
  function start(canvas) {
    var gl = canvas.getContext('webgl', { antialias: false, alpha: false }); if (!gl) return;
    function sh(t, s) { var o = gl.createShader(t); gl.shaderSource(o, s); gl.compileShader(o); return gl.getShaderParameter(o, gl.COMPILE_STATUS) ? o : null; }
    var v = sh(gl.VERTEX_SHADER, VS), f = sh(gl.FRAGMENT_SHADER, FS); if (!v || !f) return;
    var p = gl.createProgram(); gl.attachShader(p, v); gl.attachShader(p, f); gl.linkProgram(p);
    if (!gl.getProgramParameter(p, gl.LINK_STATUS)) return; gl.useProgram(p);
    var b = gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER, b);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]), gl.STATIC_DRAW);
    var pos = gl.getAttribLocation(p, 'a_position'); gl.enableVertexAttribArray(pos); gl.vertexAttribPointer(pos, 2, gl.FLOAT, false, 0, 0);
    var uT = gl.getUniformLocation(p, 'u_time'), uR = gl.getUniformLocation(p, 'u_resolution'), uM = gl.getUniformLocation(p, 'u_mouse');
    var scale = Math.min(window.devicePixelRatio || 1, 1.5) * 0.75;          /* shader is soft: render below native res to save battery */
    var mouse = { x: 0.5, y: 0.5 }, visible = true, raf = 0, still = window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches;
    function size() { var w = Math.max(1, Math.round(canvas.clientWidth * scale)), h = Math.max(1, Math.round(canvas.clientHeight * scale)); if (canvas.width !== w || canvas.height !== h) { canvas.width = w; canvas.height = h; } }
    window.addEventListener('mousemove', function (e) { var r = canvas.getBoundingClientRect(); if (r.width && r.height) { mouse.x = (e.clientX - r.left) / r.width; mouse.y = 1 - (e.clientY - r.top) / r.height; } }, { passive: true });
    function draw(t) {
      size(); gl.viewport(0, 0, canvas.width, canvas.height);
      gl.uniform1f(uT, t * 0.001); gl.uniform2f(uR, canvas.width, canvas.height); gl.uniform2f(uM, mouse.x * canvas.width, mouse.y * canvas.height);
      gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
    }
    function loop(t) { raf = 0; if (!visible || document.hidden) return; draw(t); raf = requestAnimationFrame(loop); }
    function kick() { if (!raf && !still) raf = requestAnimationFrame(loop); }
    draw(0); if (still) return;
    if ('IntersectionObserver' in window) new IntersectionObserver(function (e) { visible = e[0].isIntersecting; if (visible) kick(); }).observe(canvas);
    document.addEventListener('visibilitychange', kick); kick();
  }
  function init() { document.querySelectorAll('canvas[data-opai-shader]').forEach(function (c) { try { start(c); } catch (e) {} }); }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
