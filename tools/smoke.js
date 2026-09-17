/* Prueba de humo de index.html, sin dependencias ni navegador.
 *
 *     osascript -l JavaScript tools/smoke.js            # desde la raíz del repo
 *     osascript -l JavaScript tools/smoke.js otro.html
 *
 * Extrae los bloques <script> del HTML, los ejecuta contra un DOM simulado y
 * renderiza cada vista bajo miles de cortes distintos. Busca dos cosas:
 *   1. excepciones (nombres mal escritos, firmas erróneas, accesos a undefined);
 *   2. cifras degeneradas en el DOM resultante: NaN, Infinity, undefined, null.
 * Lo segundo es lo que se cuela sin que nadie lo vea: un divisor a cero en una
 * primitiva de gráfica no lanza, solo pinta una barra con d="M0 4LNaN…".
 */
ObjC.import('Foundation');

function read(p) {
  const s = $.NSString.stringWithContentsOfFileEncodingError($(p), $.NSUTF8StringEncoding, $());
  if (!s.js) throw new Error('no puedo leer ' + p);
  return ObjC.unwrap(s);
}

const ARGS = ObjC.unwrap($.NSProcessInfo.processInfo.arguments).map(ObjC.unwrap);
const HTML = ARGS.filter(a => /\.html$/.test(a))[0] || 'index.html';

/* ---------------------------------------------------------------- DOM mínimo */
const SHIM = `
var VARS = {};
function Node2(tag, ns) {
  this.tagName = tag; this.ns = ns || null;
  this.children = []; this.attrs = {}; this.dataset = {};
  this._text = ''; this.className = ''; this.hidden = false; this.tabIndex = 0;
  this.style = { cssText: '' };
  this.classList = { _s: {}, add: function (c) { this._s[c] = 1; },
                     remove: function (c) { delete this._s[c]; },
                     contains: function (c) { return !!this._s[c]; } };
}
/* Semántica real: añadir un nodo que ya tiene padre lo MUEVE, no lo duplica.
   El reorden de módulos se apoya justo en eso, así que el shim debe hacerlo. */
function unlink(c) {
  var p = c.parent;
  if (!p) return;
  var i = p.children.indexOf(c);
  if (i >= 0) p.children.splice(i, 1);
  c.parent = null;
}
Node2.prototype.appendChild = function (c) {
  if (c == null) throw new Error('appendChild(null) en <' + this.tagName + '>');
  unlink(c);
  this.children.push(c); c.parent = this; return c;
};
Node2.prototype.insertBefore = function (c, ref) {
  if (c == null) throw new Error('insertBefore(null) en <' + this.tagName + '>');
  unlink(c);
  var i = ref == null ? this.children.length : this.children.indexOf(ref);
  if (i < 0) i = this.children.length;
  this.children.splice(i, 0, c); c.parent = this; return c;
};
Node2.prototype.removeChild = function (c) { unlink(c); return c; };
Object.defineProperty(Node2.prototype, 'nextSibling', {
  get: function () {
    if (!this.parent) return null;
    var i = this.parent.children.indexOf(this);
    return i >= 0 && i + 1 < this.parent.children.length ? this.parent.children[i + 1] : null;
  } });
Node2.prototype.setAttribute = function (k, v) {
  this.attrs[k] = v;
  if (k === 'id') { this.id = v; LIVE[v] = this; }
};
Node2.prototype.getAttribute = function (k) { return k in this.attrs ? this.attrs[k] : null; };
Node2.prototype.addEventListener = function () {};
Node2.prototype.removeEventListener = function () {};
Node2.prototype.getBoundingClientRect = function () { return { width: 520, height: 240, left: 0, top: 0 }; };
Node2.prototype.focus = function () {};
Node2.prototype.click = function () {};
Node2.prototype.closest = function () { return null; };
Node2.prototype.querySelector = function (sel) {
  /* solo lo que usa la página: buscar por clase entre los descendientes */
  if (sel && sel.charAt(0) === '.') {
    var cls = sel.slice(1), found = null;
    (function walk(n) {
      if (found) return;
      (n.children || []).forEach(function (c) {
        if (found) return;
        if ((c.className || '').split(/\s+/).indexOf(cls) >= 0) { found = c; return; }
        walk(c);
      });
    })(this);
    return found;
  }
  return null;
};
Node2.prototype.querySelectorAll = function () { return []; };
function detach(n) {
  /* Al vaciar un nodo, sus hijos salen del documento: sus id dejan de resolver.
     Modelarlo es lo que permite cazar un $('#x') sobre un nodo ya sustituido. */
  if (n.id && LIVE[n.id] === n) delete LIVE[n.id];
  (n.children || []).forEach(detach);
}
Object.defineProperty(Node2.prototype, 'textContent', {
  get: function () { return this._text; },
  set: function (v) {
    (this.children || []).forEach(function (c) { detach(c); c.parent = null; });
    this._text = String(v); this.children = [];
  } });
Object.defineProperty(Node2.prototype, 'firstChild', {
  get: function () { return this.children.length ? this.children[0] : null; } });

var REG = {}, LIVE = {};
var SELALL = { '.tab': [], 'section[role="tabpanel"]': [], '#f-real .rev-only': [] };
/* IDS lo rellena el arranque con los id que existen de verdad en el HTML.
   querySelector devuelve null para lo que no está, igual que un navegador: si
   el shim inventa nodos, un $('#loquesea') roto pasa desapercibido y la
   página se queda en blanco solo en el navegador. */
var IDS = {};
var document = {
  createElement: function (t) { return new Node2(t); },
  createElementNS: function (ns, t) { return new Node2(t, ns); },
  createTextNode: function (t) { var n = new Node2('#text'); n._text = String(t); return n; },
  documentElement: new Node2('html'), body: new Node2('body'),
  title: '',
  addEventListener: function () {},
  querySelector: function (s) {
    if (s.charAt(0) === '#') {
      var id = s.slice(1);
      if (!IDS[id]) return null;      /* no existe en el HTML: como el navegador */
      return LIVE[id] || null;        /* null si se desprendió del documento */
    }
    return REG[s] || (REG[s] = new Node2('div'));
  },
  querySelectorAll: function (s) { return SELALL[s] || []; } };
var Node = Node2;
var window = { addEventListener: function () {} };
function getComputedStyle() { return { getPropertyValue: function () { return '#888888'; } }; }
function matchMedia() { return { matches: false, addEventListener: function () {} }; }
function ResizeObserver() { this.observe = function () {}; this.unobserve = function () {}; this.disconnect = function () {}; }
function requestAnimationFrame() { return 0; }
function setTimeout(f) { try { f(); } catch (e) {} return 0; }
function clearTimeout() {}
function addEventListener() {}
function removeEventListener() {}
var navigator = { language: 'es-ES' };
/* localStorage de verdad, en memoria: sin él la página cae por el try/catch y
   la persistencia del orden y del idioma no se prueba nunca. */
var LS = {};
var localStorage = {
  getItem: function (k) { return Object.prototype.hasOwnProperty.call(LS, k) ? LS[k] : null; },
  setItem: function (k, v) { LS[k] = String(v); },
  removeItem: function (k) { delete LS[k]; } };
/* Construye un nodo con data-i18n y le cuelga como hijos los nodos que llevan
   los id anidados, ya registrados como vivos. */
function mkI18n(prop) {
  return function (spec) {
    var n = new Node2('span');
    n.dataset[prop] = spec.value;
    spec.ids.forEach(function (id) {
      var kid = REG['#' + id] || new Node2('span');
      kid.setAttribute('id', id);
      REG['#' + id] = kid;
      n.appendChild(kid);
    });
    return n;
  };
}
function removeEventListener() {}
`;

/* --------------------------------------------------------------- el barrido */
const DRIVER = `
var report = [], cases = 0;
/* El fichero puede llevar los datos reales o el esqueleto vacío del repositorio
   público. Las dos versiones tienen que pasar, cada una con lo que le toca. */
var HAS_DATA = RD.meta.n > 0;
function texts(n, acc) {
  acc = acc || [];
  if (n._text) acc.push(n._text);
  if (n.attrs) for (var k in n.attrs) if (typeof n.attrs[k] === 'string') acc.push(n.attrs[k]);
  (n.children || []).forEach(function (c) { texts(c, acc); });
  return acc;
}
/* Con límite de palabra a propósito: el texto de las reviews es lenguaje
   natural y "nulle" (francés) o "nulla" (italiano) contienen "null". Con 710
   textos nunca pasó; con 29.000 aparecieron 87 falsos positivos de golpe. Un
   "null" suelto en el DOM sigue cazándose. */
var BAD = /\\bNaN\\b|\\bInfinity\\b|\\bundefined\\b|\\[object|\\bnull\\b/;
function count(n) {
  var k = 1;
  (n.children || []).forEach(function (c) { k += count(c); });
  return k;
}
function tryView(name, fn) {
  cases++;
  var host = new Node2('section');
  try { fn(host); } catch (e) {
    report.push('FALLO ' + name + ': ' + e.message);
    return;
  }
  var t = texts(host).join(' | '), m = t.match(BAD);
  if (m) {
    var i = t.indexOf(m[0]);
    report.push('DEGENERADO ' + name + ' -> …' + t.slice(Math.max(0, i - 80), i + 40) + '…');
  }
}
var base = JSON.parse(JSON.stringify(rstate));
function setCut(c) {
  Object.keys(base).forEach(function (k) { rstate[k] = base[k]; });
  Object.keys(c || {}).forEach(function (k) { rstate[k] = c[k]; });
}
var langs = ['all', 'es', 'fr', 'pt', 'en', 'otros'];
var fams = ['all'].concat(FAMS);
var rats = ['all', 'neg', 'neu', 'pos', '1', '2', '3', '4', '5'];
var sents = ['all', 'neg', 'mix', 'pos', 'ind'];
var topics = RD.meta.topics.map(function (t) { return t.id; }).concat(['all']);

/* 1. idioma x dispositivo x nota, en las dos vistas de detalle */
langs.forEach(function (L) { fams.forEach(function (F) { rats.forEach(function (R) {
  setCut({ lang: L, fam: F, rating: R });
  tryView('rating ' + [L, F, R].join('/'), renderRating);
  tryView('reviews ' + [L, F, R].join('/'), renderReviews);
}); }); });

/* 2. idioma x sentimiento x tema x ruido x fricción */
langs.forEach(function (L) { sents.forEach(function (S) { topics.forEach(function (T) {
  [true, false].forEach(function (C) { [true, false].forEach(function (W) {
    setCut({ lang: L, sent: S, topic: T, content: C, fric: W });
    tryView('rev ' + [L, S, T, C, W].join('/'), renderReviews);
  }); });
}); }); });

/* 2b. LA ENCUESTA. Dimensiones propias: no hay nota ni idioma, así que el
       barrido es versión x Android x tema x ruido. Las combinaciones vacías
       son normales (una versión con 4 respuestas cruzada con un tema raro) y
       la vista tiene que decirlo, no dibujar ceros. */
var sbase = JSON.parse(JSON.stringify(sstate));
function setSCut(c) {
  Object.keys(sbase).forEach(function (k) { sstate[k] = sbase[k]; });
  Object.keys(c || {}).forEach(function (k) { sstate[k] = c[k]; });
}
var svers = ['all'].concat(SD.vers);
var sdevs = ['all'].concat(SD.devs);
var stopics = ['all'].concat(SD.topics.map(function (t) { return t.id; }));
svers.forEach(function (V) { sdevs.forEach(function (D) {
  setSCut({ ver: V, dev: D });
  tryView('survey ' + V + '/' + D, renderSurvey);
}); });
stopics.forEach(function (T) { [true, false].forEach(function (C) {
  setSCut({ topic: T, content: C });
  tryView('survey tema ' + T + '/' + C, renderSurvey);
  setSCut({ topic: T, content: C, ver: SD.vers[0] || 'all' });
  tryView('survey tema+ver ' + T + '/' + C, renderSurvey);
}); });
/* ventanas de un solo día: el caso extremo de muestra mínima */
SD.days.forEach(function (d, i) {
  if (i % 7) return;                       /* uno de cada siete: 3.454 renders no aportan más */
  var v = +d.replace(/-/g, '');
  setSCut({ from: v, to: v });
  tryView('survey día ' + d, renderSurvey);
});
/* rango imposible: desde después de hasta. Corte vacío, y se dice. */
setSCut({ from: +SD.meta.to.replace(/-/g, ''), to: +SD.meta.from.replace(/-/g, '') });
tryView('survey rango vacío', renderSurvey);
setSCut({});

/* 3. ventanas de un solo día: el caso extremo de muestra mínima */
RD.days.forEach(function (d) {
  var v = +d.replace(/-/g, '');
  setCut({ from: v, to: v });
  tryView('día ' + d, renderRating);
  tryView('día ' + d + ' rev', renderReviews);
});

/* 3b. los tres granos de la gráfica temporal, en varios cortes: con grano
       diario hay idiomas que no reúnen base y la serie se queda a huecos, que
       es justo el caso que antes reventaba con 0/0. */
['day', 'week', 'month'].forEach(function (G) {
  [{}, { lang: 'es' }, { lang: 'en' }, { rating: 'neg' }, { fam: 'Tecno' },
   { from: 20260801, to: 20260814 }, { from: 20260615, to: 20260616 }].forEach(function (c) {
    setCut(Object.assign({ grain: G }, c));
    tryView('grano ' + G + ' ' + JSON.stringify(c), renderRating);
  });
});
setCut({});

/* 4. ordenaciones y paginación de la lista de verbatims */
['recent', 'worst', 'long'].forEach(function (S) {
  [10, 40, 500].forEach(function (N) {
    setCut({ sort: S, limit: N });
    tryView('lista ' + S + '/' + N, renderReviews);
  });
});

/* 5. la portada, bajo los mismos cortes que las otras dos */
langs.forEach(function (L) { fams.forEach(function (F) {
  setCut({ lang: L, fam: F });
  tryView('resumen ' + L + '/' + F, renderResumen);
}); });
setCut({});

/* 6. otra vez todo, en inglés: además de cazar fallos, deja en I18N_MISS las
      cadenas que aún no están en el diccionario */
setLocale('en');
I18N_MISS.clear();
/* el marco estático y la puerta también se traducen: si no se llama aquí, sus
   cadenas no entran en el recuento de lo que falta */
try { applyStaticI18n(); } catch (e) { report.push('FALLO applyStaticI18n en inglés: ' + e.message); }
t('Contraseña incorrecta.');
langs.forEach(function (L) { rats.forEach(function (R) {
  setCut({ lang: L, rating: R });
  tryView('EN rating ' + L + '/' + R, renderRating);
  tryView('EN reviews ' + L + '/' + R, renderReviews);
  tryView('EN resumen ' + L + '/' + R, renderResumen);
}); });
topics.forEach(function (T) { sents.forEach(function (S) {
  setCut({ topic: T, sent: S });
  tryView('EN rev ' + T + '/' + S, renderReviews);
}); });
setCut({});
/* La encuesta, en inglés y antes de la foto de I18N_MISS. Es donde se cazan las
   cadenas sin traducir de una pestaña nueva, que son la mitad de los fallos al
   añadir una. Ojo al orden: recoger miss antes de este barrido deja la vista
   nueva fuera del recuento y la prueba pasa en falso. */
stopics.forEach(function (T) {
  setSCut({ topic: T });
  tryView('EN survey ' + T, renderSurvey);
});
sdevs.forEach(function (D) {
  setSCut({ dev: D });
  tryView('EN survey dev ' + D, renderSurvey);
});
setSCut({ from: +SD.meta.to.replace(/-/g, ''), to: +SD.meta.from.replace(/-/g, '') });
tryView('EN survey rango vacío', renderSurvey);
setSCut({});
var miss = Array.from(I18N_MISS).sort();
setLocale('es');

/* 6b. ORDEN DE LOS MÓDULOS: claves únicas, pinza en todos, y que un orden
       guardado se aplique de verdad al repintar sin perder módulos. */
cases++;
(function () {
  var views = { resumen: renderResumen, rating: renderRating, reviews: renderReviews, survey: renderSurvey };
  Object.keys(views).forEach(function (v) {
    var h = new Node2('section');
    views[v](h);
    var grid = h.children[0];
    var mods = (grid.children || []).filter(function (n) { return n.dataset && n.dataset.mod; });
    var keys = mods.map(function (n) { return n.dataset.mod; });
    /* Con el esqueleto vacío (el que va al repositorio público) la vista es solo
       el estado vacío y no hay módulos que ordenar: eso no es un fallo. */
    if (!HAS_DATA) { if (keys.length) report.push('FALLO orden ' + v + ': hay módulos sin datos'); return; }
    if (keys.length < 4) { report.push('FALLO orden ' + v + ': solo ' + keys.length + ' módulos con clave'); return; }
    var dup = keys.filter(function (k, i) { return keys.indexOf(k) !== i; });
    if (dup.length) report.push('FALLO orden ' + v + ': claves repetidas: ' + dup.join(', '));
    mods.forEach(function (n) {
      if (!n.querySelector('.grip')) report.push('FALLO orden ' + v + ': el módulo ' + n.dataset.mod + ' no tiene pinza');
    });
    var want = keys.slice().reverse();
    LS['bsp-order-' + v] = JSON.stringify(want);
    var h2 = new Node2('section');
    views[v](h2);
    var got = (h2.children[0].children || []).filter(function (n) { return n.dataset && n.dataset.mod; })
      .map(function (n) { return n.dataset.mod; });
    if (got.join('|') !== want.join('|'))
      report.push('FALLO orden ' + v + ': el orden guardado no se aplica; quería '
        + want.join(',') + ' y obtuvo ' + got.join(','));
    LS['bsp-order-' + v] = JSON.stringify(['inventada'].concat(keys.slice(0, 2)));
    var h3 = new Node2('section');
    views[v](h3);
    var got3 = (h3.children[0].children || []).filter(function (n) { return n.dataset && n.dataset.mod; }).length;
    if (got3 !== keys.length)
      report.push('FALLO orden ' + v + ': con una clave desconocida se pierden módulos ('
        + got3 + ' de ' + keys.length + ')');
    delete LS['bsp-order-' + v];
  });
})();

/* 6c. LA PUERTA: el hash tiene que aceptar la contraseña y rechazar el resto,
       y el SHA-256 propio tiene que dar los digest conocidos. */
cases++;
(function () {
  var vec = [
    ['', 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'],
    ['abc', 'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad'],
    ['enprincipio', '5a018bd108911f258cadaa301db9f9fb4b7771a2cd4bf97cb0b61b0563dffc33'],
    ['ñandú €', '8f8d5f9b8f0e6a5b0f9d8c5f4a6b7c8d9e0f1a2b3c4d5e6f708192a3b4c5d6e7'],
  ];
  vec.slice(0, 3).forEach(function (v) {
    var got = sha256Hex(v[0]);
    if (got !== v[1]) report.push('FALLO sha256(' + JSON.stringify(v[0]) + '): ' + got + ' != ' + v[1]);
  });
  /* que no reviente con caracteres fuera de ASCII (el digest solo se comprueba estable) */
  var u1 = sha256Hex('ñandú €'), u2 = sha256Hex('ñandú €');
  if (!/^[0-9a-f]{64}$/.test(u1) || u1 !== u2) report.push('FALLO sha256 con UTF-8: ' + u1);
  if (!gateOk('enprincipio')) report.push('FALLO puerta: rechaza la contraseña correcta');
  ['', 'Enprincipio', 'enprincipio ', 'enprincipi', 'otra'].forEach(function (bad) {
    if (gateOk(bad)) report.push('FALLO puerta: acepta ' + JSON.stringify(bad));
  });
  /* la contraseña no puede aparecer en claro en el fuente */
  if (/enprincipio/.test(html)) report.push('FALLO puerta: la contraseña está en claro en el HTML');
})();

/* 7. EL ARRANQUE. Lo de arriba llama a las vistas a mano; esto comprueba el
      camino que recorre el navegador al abrir: los bloques de arranque ya han
      corrido al evaluar, así que el panel de la pestaña inicial tiene que
      haberse pintado y el sello y el pie tienen que tener texto. Si algo
      revienta entre los listeners y el selectTab final, la primera pantalla
      sale en blanco y solo se ve al cambiar de pestaña: esto lo caza. */
cases++;
(function () {
  var panel = document.querySelector('#p-resumen');
  if (!panel) { report.push('FALLO arranque: no existe #p-resumen'); return; }
  var n = count(panel);
  var floor = HAS_DATA ? 40 : 6;
  if (n < floor) report.push('FALLO arranque: #p-resumen se queda casi vacío tras cargar ('
    + n + ' nodos, mínimo ' + floor + '). La pestaña inicial no se pinta.');
  if (!HAS_DATA) {
    /* sin datos, la vista tiene que DECIRLO, no quedarse muda */
    var txt = texts(panel).join(' ');
    if (!/Ninguna valoración|No rating matches/.test(txt))
      report.push('FALLO arranque sin datos: no se ve el estado vacío');
  }
  var stamp = document.querySelector('#stamp');
  if (!stamp || !stamp._text) report.push('FALLO arranque: el sello del encabezado está vacío');
  var foot = document.querySelector('#foot');
  if (!foot || !foot._text) report.push('FALLO arranque: el pie está vacío');
  var rl = document.querySelector('#r-lang');
  if (!rl || !(rl.children || []).length) report.push('FALLO arranque: el filtro de idioma no se ha rellenado');
})();

var probs = report.filter(function (r) { return /^(FALLO|DEGENERADO)/.test(r); });
report.push('datos incrustados: ' + (HAS_DATA ? nf(RD.meta.n) + ' valoraciones' : 'ninguno (esqueleto vacío)'));
probs.slice(0, 25)
  .concat(miss.length ? ['', 'SIN TRADUCIR (' + miss.length + '):'].concat(miss.map(function (m) { return '  ' + JSON.stringify(m) + ','; })) : [])
  .concat(['', (probs.length || miss.length ? 'FALLA' : 'OK') + ' · ' + cases + ' renders · '
    + probs.length + ' problemas · ' + miss.length + ' cadenas sin traducir'])
  .join('\\n')
`;

/* ---------------------------------------------------------------- ejecución */
const html = read(HTML);
const blocks = [];
const re = /<script>([\s\S]*?)<\/script>/g;
let m;
while ((m = re.exec(html)) !== null) blocks.push(m[1]);
if (!blocks.length) throw new Error('no hay bloques <script> en ' + HTML);

const ids = [];
const reId = /\sid="([^"]+)"/g;
let mid;
const htmlOnly = html.replace(/<script>[\s\S]*?<\/script>/g, '');
while ((mid = reId.exec(htmlOnly)) !== null) ids.push(mid[1]);

let src = SHIM + '\nIDS = ' + JSON.stringify(
  ids.reduce((a, k) => { a[k] = 1; return a; }, {})) + ';\n';
/* La puerta se deja abierta antes de cargar: si no, el panel no se pinta y la
   comprobación de arranque no puede distinguir «cerrado» de «roto». La lógica
   de la puerta se prueba aparte, en el driver. */
src += 'LS["bsp-unlocked"] = "e0af6b5aa5737c110804d7f94fbad3781a5c92f206057276ca828df9abec8533";\n';
src += 'Object.keys(IDS).forEach(function (k) {\n'
  + '  var n = new Node2("div"); n.setAttribute("id", k); REG["#" + k] = n;\n'
  + '});\n';

/* Los nodos con data-i18n, con los id que llevan DENTRO. Es lo que hace posible
   cazar el fallo real: traducir un nodo por textContent borra a sus hijos, y un
   $('#hijo') posterior se encuentra un null. Sin esto el shim no lo ve. */
function i18nElements(src2, attr) {
  const out = [];
  const re = new RegExp('<([a-z]+)([^>]*\\s' + attr + '="([^"]*)"[^>]*)>', 'gi');
  let m;
  while ((m = re.exec(src2)) !== null) {
    const tag = m[1], value = m[3];
    if (/\/>$/.test(m[0])) { out.push({ value, ids: [] }); continue; }
    /* extensión del elemento: se cierra la etiqueta contando anidamientos */
    let depth = 1, i = re.lastIndex;
    const open = new RegExp('<' + tag + '[\\s>]', 'gi');
    const close = new RegExp('</' + tag + '>', 'gi');
    while (depth > 0 && i < src2.length) {
      open.lastIndex = i; close.lastIndex = i;
      const o = open.exec(src2), c = close.exec(src2);
      if (!c) break;
      if (o && o.index < c.index) { depth++; i = o.index + 1; }
      else { depth--; i = c.index + c[0].length; }
    }
    const inner = src2.slice(re.lastIndex, i);
    const ids = [];
    let mi; const reId2 = /\sid="([^"]+)"/g;
    while ((mi = reId2.exec(inner)) !== null) ids.push(mi[1]);
    out.push({ value, ids });
  }
  return out;
}
const i18n = i18nElements(htmlOnly, 'data-i18n');
const i18nAria = i18nElements(htmlOnly, 'data-i18n-aria');
src += 'SELALL["[data-i18n]"] = ' + JSON.stringify(i18n) + '.map(mkI18n("i18n"));\n'
     + 'SELALL["[data-i18n-aria]"] = ' + JSON.stringify(i18nAria) + '.map(mkI18n("i18nAria"));\n';
blocks.forEach(b => { src += '\n;\n' + b; });
src += '\n;\n' + DRIVER;

let result;
try {
  result = eval(src);
} catch (e) {
  result = 'FALLA · excepción al cargar la página: ' + e.message + '\n'
    + String(e.stack || '').split('\n').slice(0, 6).join('\n');
}
HTML + ' · ' + blocks.length + ' bloques <script>\n' + result
