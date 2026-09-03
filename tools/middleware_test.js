/* Prueba de la restriccion por IP de middleware.js, sin dependencias:
 *
 *     osascript -l JavaScript tools/middleware_test.js
 *
 * El middleware corre en el borde de Vercel, donde no se puede depurar a mano,
 * asi que la logica se prueba aqui con Response y process.env simulados. Lo que
 * cubre y por que: que falle CERRADO sin cabecera de IP, que no se pueda colar
 * una IP falseando x-forwarded-for, que IPv6 no pase por la puerta de IPv4, que
 * ALLOWED_IPS mande sobre la constante y que la pagina 403 escape la IP antes de
 * ensenarla (si no, la propia cabecera seria un vector de inyeccion).
 *
 * OJO: el fichero lleva una COPIA de middleware.js con los export quitados,
 * porque JavaScriptCore no carga modulos ES. Si tocas middleware.js, vuelve a
 * generar esta copia o la prueba dejara de valer.
 */

var ENV = {};
var process = { env: ENV };
function Response(body, init) { this.body = body; this.status = (init||{}).status || 200; this.headers = (init||{}).headers || {}; }
function req(h) { return { headers: { get: function (k) { return Object.prototype.hasOwnProperty.call(h, k) ? h[k] : null; } } }; }
/**
 * Restricción por IP en el borde de Vercel.
 *
 * Solo las IP de la lista pueden llegar al panel; el resto recibe 403 antes de
 * que se sirva una sola línea del HTML. A diferencia de la pantalla de
 * contraseña —que es un cierre de cortesía dentro de un fichero estático—, esto
 * sí es una barrera de servidor: quien no pase de aquí no descarga los datos.
 *
 * Dos decisiones que conviene no cambiar sin pensarlo:
 *
 * 1. FALLA CERRADO. Si no se puede determinar la IP del cliente, se deniega. Al
 *    revés (dejar pasar ante la duda) la restricción no valdría nada.
 * 2. La página de bloqueo DICE LA IP DETECTADA. Sin eso, una IP dinámica que
 *    cambia, o una conexión que sale por IPv6, te dejan fuera sin diagnóstico y
 *    sin saber qué añadir a la lista.
 *
 * Para cambiar la lista sin tocar el código: variable de entorno ALLOWED_IPS en
 * Vercel (Settings → Environment Variables), IP separadas por comas. Si existe,
 * manda sobre la constante de abajo.
 */

/* La IP de partida. Ojo: una IP doméstica suele ser dinámica. */
const DEFAULT_ALLOW = ['90.161.49.230'];

var config = {
  /* Todo salvo la infraestructura interna de Vercel, que debe pasar siempre. */
  matcher: '/((?!_vercel/).*)',
};

function allowList() {
  const raw = process.env.ALLOWED_IPS;
  if (!raw) return DEFAULT_ALLOW;
  const list = raw.split(',').map(s => s.trim()).filter(Boolean);
  return list.length ? list : DEFAULT_ALLOW;
}

/**
 * IP real del cliente.
 *
 * Se prefiere `x-vercel-forwarded-for` porque lo pone la plataforma y el cliente
 * no puede falsearlo. `x-forwarded-for` va después y solo se mira su PRIMER
 * valor: si alguien manda su propia cabecera, Vercel la conserva por delante de
 * la real, así que confiar en el resto de la cadena sería un agujero.
 */
function clientIp(req) {
  const direct = req.headers.get('x-vercel-forwarded-for') || req.headers.get('x-real-ip');
  if (direct) return direct.split(',')[0].trim();
  const xff = req.headers.get('x-forwarded-for');
  if (xff) return xff.split(',')[0].trim();
  return '';
}

const esc = s => String(s).replace(/[&<>"]/g, c =>
  ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

function denied(ip) {
  const shown = ip ? esc(ip) : 'no se ha podido determinar';
  const body = `<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Acceso restringido · BeSoccer Product Lab</title>
<style>
  :root { color-scheme: dark }
  body { margin:0; min-height:100vh; display:grid; place-items:center; padding:24px;
         background:#0e100c; color:#f0f3ea;
         font:400 14px/1.5 Asap,system-ui,-apple-system,"Segoe UI",sans-serif }
  .box { max-width:440px; background:#1b1e1a; border:1px solid #2b2f27; border-radius:3px;
         padding:28px 26px; box-shadow:0 1px 2px rgba(0,0,0,.4) }
  h1 { font-size:20px; font-weight:700; margin:0 0 10px; letter-spacing:-.2px }
  p { margin:0 0 12px; color:#b3bba9 }
  code { font:12.5px ui-monospace,SFMono-Regular,Menlo,monospace;
         background:#22261f; border:1px solid #2b2f27; border-radius:3px; padding:2px 6px; color:#f0f3ea }
  .foot { margin:18px 0 0; font-size:12px; color:#868e7e; line-height:1.55 }
</style></head><body><div class="box">
<h1>Acceso restringido</h1>
<p>Este panel solo admite conexiones desde las direcciones IP autorizadas.</p>
<p>La IP con la que has llegado es <code>${shown}</code>.</p>
<p class="foot">Si es tu conexión habitual, añádela a <code>ALLOWED_IPS</code> en las
variables de entorno del proyecto en Vercel. Una IP doméstica suele ser dinámica y
cambia; y si tu operador te da IPv6, la dirección de arriba no será la IPv4 que
esperabas: añade la que aparece aquí.</p>
</div></body></html>`;
  return new Response(body, {
    status: 403,
    headers: {
      'content-type': 'text/html; charset=utf-8',
      /* Que ni el navegador ni la CDN guarden la respuesta: la IP cambia. */
      'cache-control': 'no-store, must-revalidate',
      'x-robots-tag': 'noindex, nofollow',
    },
  });
}

function middleware(req) {
  const ip = clientIp(req);
  return allowList().includes(ip) ? undefined : denied(ip);
}

var out = [];
function check(name, headers, env, wantAllowed) {
  ENV.ALLOWED_IPS = env;
  var r = middleware(req(headers));
  var allowed = (r === undefined);
  var ok = allowed === wantAllowed;
  out.push((ok ? '  OK  ' : '  MAL ') + name + ' -> ' + (allowed ? 'PASA' : 'BLOQUEA ' + r.status));
  if (!ok) out.push('       (se esperaba ' + (wantAllowed ? 'PASA' : 'BLOQUEA') + ')');
  return ok;
}
var fails = 0;
if (!check('IP autorizada por x-vercel-forwarded-for', {'x-vercel-forwarded-for':'90.161.49.230'}, undefined, true)) fails++;
if (!check('IP autorizada por x-real-ip', {'x-real-ip':'90.161.49.230'}, undefined, true)) fails++;
if (!check('IP autorizada solo en x-forwarded-for', {'x-forwarded-for':'90.161.49.230'}, undefined, true)) fails++;
if (!check('otra IP cualquiera', {'x-vercel-forwarded-for':'8.8.8.8'}, undefined, false)) fails++;
if (!check('sin ninguna cabecera de IP (debe fallar CERRADO)', {}, undefined, false)) fails++;
if (!check('cabecera vacia', {'x-vercel-forwarded-for':''}, undefined, false)) fails++;
if (!check('IPv6 del mismo usuario', {'x-vercel-forwarded-for':'2a0c:5a80:1e0f:aa00::1'}, undefined, false)) fails++;
if (!check('spoofing: cliente prepone la IP buena en x-forwarded-for pero Vercel dice otra',
      {'x-vercel-forwarded-for':'8.8.8.8','x-forwarded-for':'90.161.49.230, 8.8.8.8'}, undefined, false)) fails++;
if (!check('cadena xff, se toma el primero', {'x-forwarded-for':'8.8.8.8, 90.161.49.230'}, undefined, false)) fails++;
if (!check('ALLOWED_IPS manda sobre la constante', {'x-vercel-forwarded-for':'1.2.3.4'}, '1.2.3.4, 5.6.7.8', true)) fails++;
if (!check('ALLOWED_IPS excluye la constante', {'x-vercel-forwarded-for':'90.161.49.230'}, '1.2.3.4', false)) fails++;
if (!check('ALLOWED_IPS vacia cae en la constante', {'x-vercel-forwarded-for':'90.161.49.230'}, '  ,  ', true)) fails++;
/* la pagina de bloqueo tiene que decir la IP y no cachearse */
ENV.ALLOWED_IPS = undefined;
var d = middleware(req({'x-vercel-forwarded-for':'8.8.8.8'}));
out.push(d.body.indexOf('8.8.8.8') >= 0 ? '  OK  la pagina 403 muestra la IP detectada' : '  MAL la pagina 403 no muestra la IP');
out.push(/no-store/.test(d.headers['cache-control']) ? '  OK  403 sin cache' : '  MAL 403 cacheable');
var d2 = middleware(req({}));
out.push(d2.body.indexOf('no se ha podido determinar') >= 0 ? '  OK  sin IP lo dice' : '  MAL sin IP no lo dice');
/* inyeccion via cabecera */
var d3 = middleware(req({'x-vercel-forwarded-for':'<script>alert(1)</script>'}));
out.push(d3.body.indexOf('<script>alert') < 0 ? '  OK  la IP se escapa en el HTML' : '  MAL inyeccion HTML por la cabecera');
out.push('');
out.push(fails ? '=== ' + fails + ' PRUEBAS MAL ===' : '=== todas las pruebas de la restriccion por IP OK ===');
out.join('\n')
