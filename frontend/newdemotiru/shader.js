/* Earth-horizon shader — cursor-reactive + scroll-driven rotation.
   Layout comes from uniforms (see main.js CONFIG). */
window.TIRU_FRAG = `
precision highp float;
uniform vec2 R; uniform float T; uniform vec2 M;
uniform float uHor,uRad,uTilt,uSunX,uK,uIntro,uBright,uPortrait;
uniform float uScroll,uVel,uPtrOn,uSpan;
uniform vec2 uPtr;
uniform vec3 uRip[4];           // x, y (screen units), age in seconds (<0 = inactive)

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
  float sc=uScroll;
  float scE=sc*sc*(3.-2.*sc);

  // geometry: scrolling lifts the planet, tilts it and sweeps the sun across
  vec2 p=rot(uTilt+scE*.10+m.x*.02)*(uv+m*.012);
  float Rad=uRad;
  float hor=uHor+(sc*.62+scE*.30)-(1.-e)*.5;
  vec2 c=vec2(0.,hor-Rad);
  vec2 q=p-c;
  float len=length(q);
  float d=len-Rad;
  float t=max(-d,0.);

  vec3 col=vec3(0.);

  // stars drift opposite to the rotation (parallax)
  vec2 g=(uv+vec2(sc*.35,0.))*mix(78.,54.,uPortrait);
  vec2 id=floor(g);float r=h21(id);
  vec2 f=fract(g)-.5;vec2 o=(h22(id)-.5)*.6;
  float st=smoothstep(.07,0.,length(f-o))*step(.945,r);
  st*=.55+.45*sin(T*(1.2+r*3.)+r*50.);
  col+=vec3(st)*.85*smoothstep(0.,.03,d)*e;

  // sun
  float sx=mix(uSunX,-.24,scE);
  vec2 sunP=vec2(sx,c.y+sqrt(Rad*Rad-sx*sx));
  vec2 sd=p-sunP;
  float sunSide=exp(-pow(abs(p.x-sunP.x)*mix(1.1,2.2,uPortrait),2.));

  // pointer terms
  vec2 dir=uv-uPtr;
  float dp=length(dir);
  float gl=exp(-dp*dp*mix(24.,60.,uPortrait))*uPtrOn;

  // atmosphere rim (brightens when the cursor is near the limb)
  float rim=exp(-max(d,0.)*mix(30.,24.,uPortrait));
  col+=vec3(.82,.9,1.)*rim*(.32*sunSide+.55*exp(-dp*dp*14.)*uPtrOn)*smoothstep(-.01,.01,d)*e;

  if(d<0.){
    // lens: surface bulges toward the cursor
    float tt=max(t-gl*.03,0.);
    float Z=1./(tt+.045);
    vec2 qd=q+dir*gl*.10;
    // scroll = rotation of the planet around its axis
    vec2 P=vec2(qd.x*Z+T*.03+sc*uSpan*12.,Z)*uK;
    float fade=smoothstep(0.,.07,t);

    // shockwaves travel across the planet SURFACE (ground-plane distance -> ellipses in perspective)
    float rg=0.;
    vec2 Gp=vec2(qd.x*Z,Z);
    mat2 RT=rot(uTilt+scE*.10+m.x*.02);
    for(int i=0;i<4;i++){
      float age=uRip[i].z;
      if(age>=0.){
        vec2 qr=RT*(uRip[i].xy+m*.012)-c;
        float tr=max(Rad-length(qr),.14);
        float Zr=1./(tr+.045);
        float rr=length(Gp-vec2(qr.x*Zr,Zr));
        float w=rr-age*3.2;
        float life=1.-smoothstep(0.,2.7,age);
        rg+=(exp(-w*w*4.)+.4*exp(-(w+.9)*(w+.9)*5.))*life;
      }
    }
    // thin orbit ring that follows the cursor
    float halo=exp(-pow((dp-(.085+.012*sin(T*3.)))*48.,2.))*uPtrOn;

    vec3 v=vor(P);
    float edge=1.-smoothstep(0.,.045,v.y-v.x);
    float mask=smoothstep(.42,.78,fbm(P*.32+3.7));

    float lines=edge*(.18+.82*mask);
    float pul=.5+.5*sin(T*6.+v.z*30.);
    float nodes=smoothstep(.07,.0,v.x)*step(.40,v.z)*(.3+mask*1.5);
    nodes*=.65+.35*sin(T*2.+v.z*40.);
    vec2 gp=P*mix(15.,22.,uPortrait);vec2 gc=floor(gp);vec2 gf=abs(fract(gp)-.5);
    float spark=step(.80,h21(gc))*step(max(gf.x,gf.y),.20)*(.55+.45*sin(T*1.6+h21(gc+3.)*30.));
    float dust=spark*(.25+mask*1.2);

    float boost=1.+gl*2.4+rg*5.+halo*2.2+uVel*.9;
    float s=(lines*.62*boost
            +nodes*1.9*(1.+gl*3.2*pul+rg*7.+uVel*1.2)
            +dust*1.05*(1.+gl*2.+rg*3.+uVel))*fade*uBright;
    s*=.30+.70*smoothstep(0.,.35,t);
    s*=1.-.30*scE;
    col+=vec3(.93,.96,1.)*s*e;

    // soft energy under the cursor + cyan shockwave tint
    float body=.35+.65*smoothstep(0.,.3,t);
    col+=vec3(.80,.92,1.)*gl*.30*body*fade;
    col+=vec3(.55,.82,1.)*(rg*.36+halo*.24)*body*fade;

    col+=vec3(.8,.9,1.)*exp(-t*38.)*.28*(.3+sunSide)*e;
    col+=vec3(.004,.005,.007);
  }

  // sunrise flare (kicks up with scroll speed)
  float core=exp(-length(sd)*mix(24.,34.,uPortrait))*1.7;
  float streak=.010/(length(sd*vec2(mix(.14,.30,uPortrait),1.))+.016);
  float halo2=.020/(length(sd)+.09);
  float thin=exp(-abs(sd.y)*150.)*exp(-abs(sd.x)*1.8)*.6;
  col+=vec3(1.,.98,.95)*(core+streak*.55+halo2*.6+thin)*(.2+.8*e)*(1.+uVel*.45);

  col=1.-exp(-col*1.35);
  col*=1.-.40*dot(uv*.9,uv*.9);

  // ---- neutral palette map; uTint controls how much sage is left (0 = grey, 1 = full sage) ----
  float L=clamp(dot(col,vec3(.299,.587,.114))*1.12,0.,1.);
  vec3 c0=vec3(.040,.040,.037),c1=vec3(.090,.090,.085),c2=vec3(.420,.420,.405),c3=vec3(.560,.560,.540);
  vec3 c4=vec3(.690,.690,.670),c5=vec3(.820,.820,.800),c6=vec3(.945,.945,.930);
  vec3 pc=mix(c0,c1,smoothstep(0.,.10,L));
  pc=mix(pc,c2,smoothstep(.10,.32,L));
  pc=mix(pc,c3,smoothstep(.32,.48,L));
  pc=mix(pc,c4,smoothstep(.48,.64,L));
  pc=mix(pc,c5,smoothstep(.64,.80,L));
  pc=mix(pc,c6,smoothstep(.80,1.,L));
  const float TINT=.10;
  pc*=mix(vec3(1.),vec3(.93,1.,.86),TINT*2.);
  float skyG=smoothstep(.55,-.35,uv.y);
  pc+=vec3(.030,.030,.028)*skyG*(1.-L);
  pc+=(h21(gl_FragCoord.xy+T)-.5)*.012;
  col=pc;
  gl_FragColor=vec4(max(col,0.),1.);
}
`;
