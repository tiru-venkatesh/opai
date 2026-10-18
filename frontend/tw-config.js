/* Shared Tailwind (CDN) theme for the public pages: landing + login/signup. */
tailwind.config = {
  theme: { extend: {
    colors: {"primary":"#6b34d6","secondary":"#4647d5","outline":"#7b7486","tertiary-fixed":"#caf165","secondary-container":"#6063f0","on-tertiary-fixed":"#151f00","on-secondary":"#ffffff","primary-fixed":"#e9ddff","on-primary-fixed":"#23005b","surface-container-highest":"#dce2f7","surface":"#f9f9ff","on-primary":"#ffffff","secondary-fixed":"#e1e0ff","on-secondary-fixed":"#06006c","surface-container":"#e9edff","error":"#ba1a1a","outline-variant":"#cbc3d7","surface-container-high":"#e1e8fd","inverse-surface":"#293040","inverse-on-surface":"#edf0ff","surface-container-low":"#f1f3ff","tertiary":"#4b6300","error-container":"#ffdad6","on-error-container":"#93000a","on-surface-variant":"#4a4454","on-surface":"#141b2b","primary-container":"#8452f0","surface-container-lowest":"#ffffff","background":"#f9f9ff","tertiary-fixed-dim":"#afd44b","primary-fixed-dim":"#d1bcff","secondary-fixed-dim":"#c0c1ff"},
    borderRadius: {"DEFAULT":"1rem","lg":"2rem","xl":"3rem","full":"9999px"},
    fontFamily: {"sans":["Geist","system-ui","sans-serif"],"mono":["JetBrains Mono","ui-monospace","monospace"]}
  } }
};
