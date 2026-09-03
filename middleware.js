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

export const config = {
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

export default function middleware(req) {
  const ip = clientIp(req);
  return allowList().includes(ip) ? undefined : denied(ip);
}
