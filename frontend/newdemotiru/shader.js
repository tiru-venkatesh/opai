/* Earth-horizon fragment shader. All layout comes from uniforms (see main.js CONFIG). */
window.TIRU_FRAG = `
precision highp float;
uniform vec2 R; uniform float T; uniform vec2 M;
uniform float uHor,uRad,uTilt,uSunX,uK,uIntro,uBright,uPortrait;

float h21(vec2 p){p=fract(p*vec2(123.34,456.21));p+=dot(p,p+45.32);return fract(p.x*p.y);}
vec2 h22(vec2 p){float n=h21(p);return vec2(n,h21(p+n+17.3));}
float noise(vec2 p){vec2 i=floor(p),f=fract(p);f=f*f*(3.-2.*f);
  return mix(mix(h21(i),h21(i+vec2(1.,0.)),f.x),mix(h21(i+vec2(0.,1.)),h21(i+vec2(1.,1.)),f.x),f.y);}
float fbm(vec2 p){float a=.5,s=0.;for(int i=0;i<5;i++){s+=a*noise(p);p=p*2.03+vec2(1.7,9.2);a*=.5;}return s;}
mat2 rot(float a){float c=cos(a),s=sin(a);return mat2(c,-s,s,c);}

vec3 vor(vec2 p){
  vec2 i=floor(p),f=fract(p);float d1=8.,d2=8.,id=0.;
  for(int y=-1;y<=1;y++)for(int x=-1;x<=1;x++){
    vec2 g=vec2(float(x),float(y));
    vec2 o=h22(i+g);o=.5+.42*sin(T*.12+6.2831*o);
    vec2 r=g+o-f;float d=dot(r,r);
    if(d<d1){d2=d1;d1=d;id=h21(i+g);}else if(d<d2){d2=d;}
  }
  return vec3(sqrt(d1),sqrt(d2),id);
}

void main(){
  vec2 uv=(gl_FragCoord.xy-.5*R)/R.y;
  vec2 m=(M-.5);
  float e=uIntro;

  // planet geometry: huge circle, only the top limb is visible
  vec2 p=rot(uTilt+m.x*.02)*(uv+m*.01);
  float hor=uHor-(1.-e)*.5;
  vec2 c=vec2(0.,hor-uRad);
  vec2 q=p-c;
  float len=length(q);
  float d=len-uRad;
  float t=max(-d,0.);

  vec3 col=vec3(0.);

  // stars (fade near the sun so the flare stays clean)
  vec2 g=uv*mix(78.,54.,uPortrait);
  vec2 id=floor(g);float r=h21(id);
  vec2 f=fract(g)-.5;vec2 o=(h22(id)-.5)*.6;
  float st=smoothstep(.07,0.,length(f-o))*step(.945,r);
  st*=.55+.45*sin(T*(1.2+r*3.)+r*50.);
  col+=vec3(st)*.85*smoothstep(0.,.03,d)*e;

  // sun sits exactly on the limb
  float sx=uSunX;
  vec2 sunP=vec2(sx,c.y+sqrt(uRad*uRad-sx*sx));
  vec2 sd=p-sunP;
  float sunSide=exp(-pow(abs(p.x-sunP.x)*mix(1.1,2.2,uPortrait),2.));

  // atmosphere rim above the limb
  float rim=exp(-max(d,0.)*mix(30.,24.,uPortrait));
  col+=vec3(.82,.9,1.)*rim*.32*sunSide*smoothstep(-.01,.01,d)*e;

  // surface: perspective ground plane with a glowing voronoi network
  if(d<0.){
    float Z=1./(t+.045);
    vec2 P=vec2(q.x*Z+T*.03,Z)*uK;
    float fade=smoothstep(0.,.07,t);

    vec3 v=vor(P);
    float edge=1.-smoothstep(0.,.045,v.y-v.x);
    float mask=smoothstep(.42,.78,fbm(P*.32+3.7));

    float lines=edge*(.18+.82*mask);
    float nodes=smoothstep(.07,.0,v.x)*step(.40,v.z)*(.3+mask*1.5);
    nodes*=.65+.35*sin(T*2.+v.z*40.);
    vec2 gp=P*mix(15.,22.,uPortrait);vec2 gc=floor(gp);vec2 gf=abs(fract(gp)-.5);
    float spark=step(.80,h21(gc))*step(max(gf.x,gf.y),.20)*(.55+.45*sin(T*1.6+h21(gc+3.)*30.));
    float dust=spark*(.25+mask*1.2);

    float s=(lines*.62+nodes*1.9+dust*1.05)*fade*uBright;
    s*=.30+.70*smoothstep(0.,.35,t);
    col+=vec3(.93,.96,1.)*s*e;

    col+=vec3(.8,.9,1.)*exp(-t*38.)*.28*(.3+sunSide)*e;
    col+=vec3(.004,.005,.007);
  }

  // sunrise flare
  float core=exp(-length(sd)*mix(24.,34.,uPortrait))*1.7;
  float streak=.010/(length(sd*vec2(mix(.14,.30,uPortrait),1.))+.016);
  float halo=.020/(length(sd)+.09);
  float thin=exp(-abs(sd.y)*150.)*exp(-abs(sd.x)*1.8)*.6;
  col+=vec3(1.,.98,.95)*(core+streak*.55+halo*.6+thin)*(.2+.8*e);

  // grade
  col=1.-exp(-col*1.35);
  col*=1.-.40*dot(uv*.9,uv*.9);
  col+=(h21(gl_FragCoord.xy+T)-.5)*.016;
  gl_FragColor=vec4(max(col,0.),1.);
}
`;
