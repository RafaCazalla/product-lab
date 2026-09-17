#!/usr/bin/env python3
"""Recoge las reviews de Google Play por la API y las acumula en un CSV.

Sin dependencias. Uso:
    python3 tools/reviews_fetch.py [--key ~/.config/besoccer/play-sa.json]
                                   [--package com.resultadosfutbol.mobile]
                                   [--out data/play_reviews.csv] [--dry-run]

Escribe exactamente las columnas que espera `reviews_build.py`, mas `review_id`,
asi que la cadena completa es:

    reviews_fetch.py  ->  data/play_reviews.csv  ->  reviews_build.py  ->  index.html

POR QUE ESTE PROGRAMA EXISTE, que es lo que hay que entender antes de tocarlo:

La API `reviews.list` tiene dos limites duros y documentados:

1. Solo devuelve los ULTIMOS 7 DIAS. No hay paginacion hacia atras ni filtro de
   fechas. Es un grifo, no un archivo: si pasan ocho dias sin ejecutar esto, esas
   reviews se pierden para siempre y no hay forma de recuperarlas.
2. Solo devuelve reviews CON TEXTO. Las valoraciones sin comentario -el 92,7 % de
   lo que recibe la app- no salen por aqui. La nota media, su reparto y el rating
   por version o dispositivo vienen de los informes mensuales de Play Console en
   Cloud Storage, que es otro mecanismo.

De (1) sale la unica regla de operacion que importa: ESTO SE EJECUTA A DIARIO.
El panel no dibuja series temporales precisamente porque la recoleccion anterior
llego en 9 lotes de cobertura desigual; ejecutar esto a diario es lo que arregla
la causa, no un adorno de automatizacion.

De (2) sale que este programa NO sustituye a la exportacion de informes: la
complementa.

Y una mejora que viene de regalo: la API da `reviewId`, estable. La deduplicacion
de `reviews_build.py` usa hoy una huella conservadora (texto + dispositivo +
fecha + nota) porque el CSV exportado a mano no traia identificador y la misma
review volvia en lotes posteriores. Con `review_id` la deduplicacion pasa a ser
exacta.
"""
import argparse, base64, csv, hashlib, json, os, sys, time, urllib.error, urllib.parse, urllib.request
from datetime import date, datetime, timezone

TOKEN_URL = 'https://oauth2.googleapis.com/token'
SCOPE = 'https://www.googleapis.com/auth/androidpublisher'
API = 'https://androidpublisher.googleapis.com/androidpublisher/v3/applications/{pkg}/reviews'
COLUMNS = ['review_id', 'rating', 'language', 'device', 'app_version', 'date',
           'text', 'developer_reply_text', 'developer_reply_date', 'took_date']


# --------------------------------------------------------------- firma RS256
# Se firma en Python puro a proposito. Las alternativas eran meter `google-auth`
# -una dependencia en un repo que no tiene ninguna- o llamar a `openssl -sign`,
# que obliga a escribir la clave privada en un fichero temporal. Aqui la clave
# solo existe en memoria. Verificado byte a byte contra `openssl dgst -sha256`.
def _der_len(b, i):
    """(offset del contenido, longitud) leyendo la longitud DER en i."""
    n = b[i]
    if n < 0x80:
        return i + 1, n
    k = n & 0x7f
    return i + 1 + k, int.from_bytes(b[i + 1:i + 1 + k], 'big')


def _der_ints(b, i, count):
    """Los `count` primeros INTEGER de la SEQUENCE que empieza en i."""
    assert b[i] == 0x30, 'se esperaba SEQUENCE'
    i, _ = _der_len(b, i + 1)
    out = []
    while len(out) < count:
        assert b[i] == 0x02, 'se esperaba INTEGER'
        j, ln = _der_len(b, i + 1)
        out.append(int.from_bytes(b[j:j + ln], 'big'))
        i = j + ln
    return out


def rsa_key(pem):
    """(modulo, exponente privado) de una clave PKCS#8 sin cifrar."""
    body = ''.join(l for l in pem.strip().splitlines() if not l.startswith('-----'))
    der = base64.b64decode(body)
    i, _ = _der_len(der, 1)                      # dentro de la SEQUENCE exterior
    j, ln = _der_len(der, i + 1); i = j + ln     # version
    j, ln = _der_len(der, i + 1); i = j + ln     # AlgorithmIdentifier
    assert der[i] == 0x04, 'la clave no es PKCS#8 sin cifrar'
    j, ln = _der_len(der, i + 1)
    _ver, n, _e, d = _der_ints(der[j:j + ln], 0, 4)
    return n, d


SHA256_DIGESTINFO = bytes.fromhex('3031300d060960864801650304020105000420')


def rs256(msg, pem):
    n, d = rsa_key(pem)
    k = (n.bit_length() + 7) // 8
    t = SHA256_DIGESTINFO + hashlib.sha256(msg).digest()
    if k < len(t) + 11:
        raise SystemExit('clave demasiado corta para RS256')
    em = b'\x00\x01' + b'\xff' * (k - len(t) - 3) + b'\x00' + t
    return pow(int.from_bytes(em, 'big'), d, n).to_bytes(k, 'big')


def b64u(b):
    return base64.urlsafe_b64encode(b).rstrip(b'=')


# ------------------------------------------------------------------- acceso
def access_token(sa):
    now = int(time.time())
    head = b64u(json.dumps({'alg': 'RS256', 'typ': 'JWT'}, separators=(',', ':')).encode())
    body = b64u(json.dumps({
        'iss': sa['client_email'], 'scope': SCOPE, 'aud': TOKEN_URL,
        'iat': now, 'exp': now + 3600,
    }, separators=(',', ':')).encode())
    msg = head + b'.' + body
    jwt = msg + b'.' + b64u(rs256(msg, sa['private_key']))
    data = urllib.parse.urlencode({
        'grant_type': 'urn:ietf:params:oauth:grant-type:jwt-bearer',
        'assertion': jwt.decode(),
    }).encode()
    try:
        with urllib.request.urlopen(urllib.request.Request(TOKEN_URL, data=data), timeout=30) as r:
            return json.load(r)['access_token']
    except urllib.error.HTTPError as e:
        detail = e.read().decode('utf-8', 'replace')[:400]
        raise SystemExit(
            'No se ha podido obtener el token (HTTP %s).\n%s\n\n'
            'Si el mensaje habla de "invalid_grant" o de permisos, casi siempre es una\n'
            'de estas dos: la API androidpublisher no esta activada en el proyecto, o\n'
            'la cuenta de servicio aun no ha propagado en Play Console. La propagacion\n'
            'tarda HASTA 24 HORAS desde que se invita al usuario.' % (e.code, detail))


def get(url, token):
    req = urllib.request.Request(url, headers={'Authorization': 'Bearer ' + token})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        detail = e.read().decode('utf-8', 'replace')[:400]
        if e.code in (401, 403):
            raise SystemExit(
                'Permiso denegado (HTTP %s).\n%s\n\n'
                'La cuenta de servicio necesita, en Play Console -> Usuarios y permisos,\n'
                'el permiso de cuenta "Ver informacion de la app y descargar informes\n'
                'masivos". Y recuerda que tarda hasta 24 horas en hacer efecto.' % (e.code, detail))
        if e.code == 404:
            raise SystemExit(
                'No existe esa app (HTTP 404).\n%s\n\n'
                'Revisa el --package: tiene que ser el nombre de paquete exacto.' % detail)
        raise SystemExit('Error HTTP %s\n%s' % (e.code, detail))


# ------------------------------------------------------------------- mapeo
def iso_day(ts):
    """Timestamp de la API (segundos) -> YYYY-MM-DD en UTC."""
    if not ts:
        return ''
    secs = int(ts.get('seconds', 0))
    return datetime.fromtimestamp(secs, timezone.utc).date().isoformat()


def to_row(rev, took):
    """Una review de la API -> una fila con el esquema de reviews_build.py.

    `date` sale de lastModified del comentario del usuario, que es lo que da la
    API: no hay fecha de creacion. Para una review vista por primera vez las dos
    coinciden; si el usuario la edita, esta fecha se mueve. Se acepta porque es
    lo unico que hay, y porque `took_date` conserva cuando la vimos nosotros.
    """
    user, dev = {}, {}
    for c in rev.get('comments', []):
        if 'userComment' in c:
            user = c['userComment']
        elif 'developerComment' in c:
            dev = c['developerComment']
    if not user:
        return None
    lang = (user.get('reviewerLanguage') or '').replace('-', '_').split('_')[0]
    return {
        'review_id': rev.get('reviewId', ''),
        'rating': str(user.get('starRating', '')),
        'language': lang or '??',
        'device': user.get('device') or '??',
        'app_version': user.get('appVersionName') or '',
        'date': iso_day(user.get('lastModified')),
        'text': (user.get('text') or '').replace('\r', ' ').replace('\n', ' ').strip(),
        'developer_reply_text': (dev.get('text') or '').replace('\r', ' ').replace('\n', ' ').strip(),
        'developer_reply_date': iso_day(dev.get('lastModified')) if dev else '',
        'took_date': took,
    }


# -------------------------------------------------------------------- upsert
def load_existing(path):
    if not os.path.exists(path):
        return {}, []
    with open(path, encoding='utf-8') as fh:
        rows = list(csv.DictReader(fh))
    return {r.get('review_id', ''): r for r in rows if r.get('review_id')}, rows


def main():
    ap = argparse.ArgumentParser(description='Recoge reviews de Google Play por la API.')
    ap.add_argument('--key', default=os.path.expanduser('~/.config/besoccer/play-sa.json'))
    ap.add_argument('--package', default='com.resultadosfutbol.mobile')
    ap.add_argument('--out', default='data/play_reviews.csv')
    ap.add_argument('--dry-run', action='store_true',
                    help='autentica y lee, pero no escribe: sirve para comprobar permisos')
    a = ap.parse_args()

    if not os.path.exists(a.key):
        raise SystemExit(
            'No encuentro la clave en %s\n\n'
            'Se descarga de Google Cloud Console: Cuentas de servicio -> tu cuenta ->\n'
            'Claves -> Anadir clave -> Crear clave nueva -> JSON.' % a.key)
    with open(a.key, encoding='utf-8') as fh:
        sa = json.load(fh)
    if sa.get('type') != 'service_account':
        raise SystemExit('Ese JSON no es una clave de cuenta de servicio.')

    print('cuenta de servicio: %s' % sa.get('client_email'))
    token = access_token(sa)
    print('token obtenido')

    took = date.today().isoformat()
    url = API.format(pkg=urllib.parse.quote(a.package)) + '?maxResults=100'
    fetched, pages = [], 0
    while True:
        data = get(url, token)
        batch = data.get('reviews', [])
        fetched.extend(batch)
        pages += 1
        nxt = (data.get('tokenPagination') or {}).get('nextPageToken')
        print('  pagina %d: %d reviews' % (pages, len(batch)))
        if not nxt:
            break
        url = (API.format(pkg=urllib.parse.quote(a.package))
               + '?maxResults=100&token=' + urllib.parse.quote(nxt))

    rows = [r for r in (to_row(x, took) for x in fetched) if r]
    print('recogidas %d reviews con texto (ventana de 7 dias de la API)' % len(rows))

    if a.dry_run:
        for r in rows[:3]:
            print('  ejemplo: %s* %s %s %s "%s"' % (r['rating'], r['language'],
                                                    r['app_version'], r['date'], r['text'][:60]))
        print('--dry-run: no se escribe nada')
        return

    have, order = load_existing(a.out)
    nuevas = actualizadas = 0
    for r in rows:
        prev = have.get(r['review_id'])
        if prev is None:
            have[r['review_id']] = r
            order.append(r)
            nuevas += 1
        else:
            # `took_date` conserva CUANDO LA VIMOS NOSOTROS la primera vez: si se
            # sobrescribiera, una review antigua pareceria recien recogida y la
            # tarjeta de cobertura de muestra mentiria.
            r['took_date'] = prev.get('took_date') or r['took_date']
            if any(prev.get(k, '') != r[k] for k in COLUMNS):
                actualizadas += 1
            order[order.index(prev)] = r
            have[r['review_id']] = r

    os.makedirs(os.path.dirname(a.out) or '.', exist_ok=True)
    tmp = a.out + '.tmp'
    with open(tmp, 'w', encoding='utf-8', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS, extrasaction='ignore')
        w.writeheader()
        for r in order:
            w.writerow({k: r.get(k, '') for k in COLUMNS})
    os.replace(tmp, a.out)
    print('%s: %d filas en total (%d nuevas, %d actualizadas)'
          % (a.out, len(order), nuevas, actualizadas))
    if nuevas == 0 and actualizadas == 0 and order:
        print('nota: nada nuevo. Con ejecucion diaria es lo normal algunos dias.')


if __name__ == '__main__':
    main()
