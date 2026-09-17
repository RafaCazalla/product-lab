#!/usr/bin/env python3
"""Descarga los informes masivos de Google Play desde su bucket de Cloud Storage.

Sin dependencias. Uso:
    python3 tools/play_reports.py --desde 202401 [--hasta 202612]
                                  [--que reviews,ratings,crashes]
                                  [--dir data/play] [--listar]

QUE ES ESTO Y POR QUE NO ES LA API DE RESENAS

`reviews_fetch.py` habla con la API `reviews.list`, que solo devuelve 7 dias y
solo reviews CON texto. Esto es otra cosa y para el panel es mejor fuente: los
informes mensuales que Play deposita en un bucket privado, con historico largo
-en esta cuenta, resenas desde agosto de 2013- y, lo importante, CON las
valoraciones sin texto incluidas. En una muestra de septiembre de 2026 habia
3.625 valoraciones de las que solo 293 llevaban texto: las otras 3.332 no salen
por la API y aqui si.

Tres carpetas interesan al panel:

    reviews/          valoraciones con y sin texto, columna a columna
    stats/ratings/    nota media DIARIA por version, pais, idioma, dispositivo
    stats/crashes/    cierres y ANR DIARIOS por version de app

TRES TRAMPAS, y las tres cuestan una tarde si no se saben:

1. Los CSV vienen en UTF-16. Leidos como UTF-8 salen con bytes nulos entre
   letras y no casca: simplemente todo esta mal. Aqui se detecta por BOM y se
   guardan ya convertidos a UTF-8, que es lo que consume el resto del repo.
2. El bucket tiene los informes de TODAS las apps de la cuenta. Hay que filtrar
   por nombre de paquete o te traes datos de otro producto.
3. Los informes se publican con 3 a 7 dias de retraso y el fichero del mes en
   curso sigue creciendo. Por eso se vuelve a descargar siempre el ultimo mes
   aunque ya exista en local.

AUTENTICACION

Lee el token de `~/.config/besoccer/token.txt` (el que sale del OAuth Playground,
dura una hora) o, si existe, la clave de cuenta de servicio en
`~/.config/besoccer/play-sa.json`, que no caduca y es la que hace falta para
automatizar esto. Se prefiere la cuenta de servicio cuando esta disponible.
"""
import argparse, base64, hashlib, json, os, sys, time, urllib.error, urllib.parse, urllib.request

BUCKET = 'pubsite_prod_4963780278402870090'
PACKAGE = 'com.resultadosfutbol.mobile'
TOKEN_FILE = os.path.expanduser('~/.config/besoccer/token.txt')
KEY_FILE = os.path.expanduser('~/.config/besoccer/play-sa.json')
SCOPE = 'https://www.googleapis.com/auth/devstorage.read_only'

GRUPOS = {
    'reviews':  ['reviews/'],
    'ratings':  ['stats/ratings/'],
    'crashes':  ['stats/crashes/'],
    'installs': ['stats/installs/'],
}
# `device` se deja fuera por defecto: son 48 MB en ratings y 12 en crashes, y el
# panel ya cruza dispositivo desde las propias reviews. Se pide con --dimensiones.
DIM_POR_DEFECTO = ['overview', 'app_version', 'country', 'language', 'os_version']


# ------------------------------------------------------------------ credencial
def _token_de_cuenta_de_servicio(path):
    """Firma el JWT en Python puro. La explicacion larga, en reviews_fetch.py."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from reviews_fetch import rs256, b64u          # misma firma, un solo sitio
    sa = json.load(open(path, encoding='utf-8'))
    now = int(time.time())
    head = b64u(json.dumps({'alg': 'RS256', 'typ': 'JWT'}, separators=(',', ':')).encode())
    body = b64u(json.dumps({'iss': sa['client_email'], 'scope': SCOPE,
                            'aud': 'https://oauth2.googleapis.com/token',
                            'iat': now, 'exp': now + 3600}, separators=(',', ':')).encode())
    msg = head + b'.' + body
    jwt = msg + b'.' + b64u(rs256(msg, sa['private_key']))
    data = urllib.parse.urlencode({
        'grant_type': 'urn:ietf:params:oauth:grant-type:jwt-bearer',
        'assertion': jwt.decode()}).encode()
    req = urllib.request.Request('https://oauth2.googleapis.com/token', data=data)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)['access_token']


def credencial():
    if os.path.exists(KEY_FILE):
        print('credencial: cuenta de servicio')
        return _token_de_cuenta_de_servicio(KEY_FILE)
    if os.path.exists(TOKEN_FILE):
        tok = open(TOKEN_FILE, encoding='utf-8').read().strip().strip('"')
        if tok:
            print('credencial: token del OAuth Playground (caduca en una hora)')
            return tok
    raise SystemExit(
        'No hay credencial.\n\n'
        'O bien %s con un token del OAuth Playground,\n'
        'o bien %s con la clave de una cuenta de servicio.' % (TOKEN_FILE, KEY_FILE))


# ------------------------------------------------------------------------ GCS
def _get(url, token, binario=False):
    req = urllib.request.Request(url, headers={'Authorization': 'Bearer ' + token})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            return r.read() if binario else json.load(r)
    except urllib.error.HTTPError as e:
        detalle = e.read().decode('utf-8', 'replace')[:300]
        if e.code == 401:
            raise SystemExit('Token caducado o invalido (401).\n%s\n\n'
                             'Si venia del OAuth Playground, dura una hora: saca otro.' % detalle)
        if e.code == 403:
            raise SystemExit('Sin permiso sobre el bucket (403).\n%s' % detalle)
        raise SystemExit('HTTP %s\n%s' % (e.code, detalle))


def listar(token, prefijo):
    salida, pagina = [], None
    while True:
        q = {'prefix': prefijo, 'maxResults': 1000}
        if pagina:
            q['pageToken'] = pagina
        d = _get('https://storage.googleapis.com/storage/v1/b/%s/o?%s'
                 % (BUCKET, urllib.parse.urlencode(q)), token)
        salida += [(o['name'], int(o.get('size', 0))) for o in d.get('items', [])]
        pagina = d.get('nextPageToken')
        if not pagina:
            return salida


def descargar(token, objeto):
    return _get('https://storage.googleapis.com/storage/v1/b/%s/o/%s?alt=media'
                % (BUCKET, urllib.parse.quote(objeto, safe='')), token, binario=True)


# ----------------------------------------------------------------- utilidades
def a_utf8(crudo):
    """Los informes vienen en UTF-16 con BOM. Se guarda ya convertido."""
    if crudo[:2] in (b'\xff\xfe', b'\xfe\xff'):
        return crudo.decode('utf-16').encode('utf-8')
    return crudo.lstrip(b'\xef\xbb\xbf')


def mes_de(nombre):
    """AAAAMM del nombre del fichero, o None."""
    for trozo in os.path.basename(nombre).replace('.csv', '').split('_'):
        if len(trozo) == 6 and trozo.isdigit():
            return trozo
    return None


def dimension_de(nombre):
    base = os.path.basename(nombre).replace('.csv', '')
    ym = mes_de(nombre)
    return base.split('_' + ym + '_', 1)[1] if ym and '_' + ym + '_' in base else 'overview'


def main():
    ap = argparse.ArgumentParser(description='Descarga informes masivos de Google Play.')
    ap.add_argument('--desde', default='202401', help='AAAAMM inclusive')
    ap.add_argument('--hasta', default='209912', help='AAAAMM inclusive')
    ap.add_argument('--que', default='reviews,ratings,crashes')
    ap.add_argument('--dimensiones', default=','.join(DIM_POR_DEFECTO),
                    help="dimensiones de stats/; 'todas' incluye device, que pesa mucho")
    ap.add_argument('--dir', default='data/play')
    ap.add_argument('--paquete', default=PACKAGE)
    ap.add_argument('--listar', action='store_true', help='solo enumera, no descarga')
    a = ap.parse_args()

    token = credencial()
    dims = None if a.dimensiones == 'todas' else set(a.dimensiones.split(','))
    mes_actual = time.strftime('%Y%m')
    total_bytes = nuevos = saltados = 0

    for grupo in [g.strip() for g in a.que.split(',') if g.strip()]:
        if grupo not in GRUPOS:
            raise SystemExit('grupo desconocido: %s (hay %s)' % (grupo, ', '.join(GRUPOS)))
        for prefijo in GRUPOS[grupo]:
            objetos = [(n, s) for n, s in listar(token, prefijo) if a.paquete in n]
            objetos = [(n, s) for n, s in objetos
                       if (mes_de(n) or '') >= a.desde and (mes_de(n) or '') <= a.hasta]
            if dims is not None and grupo != 'reviews':
                objetos = [(n, s) for n, s in objetos if dimension_de(n) in dims]
            objetos.sort()
            print('\n%s: %d ficheros en el rango' % (prefijo, len(objetos)))
            if a.listar:
                for n, s in objetos:
                    print('   %-70s %8.1f KB' % (os.path.basename(n), s / 1024))
                continue
            destino_dir = os.path.join(a.dir, grupo)
            os.makedirs(destino_dir, exist_ok=True)
            for n, s in objetos:
                destino = os.path.join(destino_dir, os.path.basename(n))
                # El mes en curso sigue creciendo: se vuelve a bajar siempre.
                if os.path.exists(destino) and mes_de(n) != mes_actual:
                    saltados += 1
                    continue
                datos = a_utf8(descargar(token, n))
                open(destino, 'wb').write(datos)
                total_bytes += len(datos); nuevos += 1
                print('   %-66s %7.1f KB' % (os.path.basename(n), len(datos) / 1024))

    if not a.listar:
        print('\n%d ficheros nuevos (%.1f MB), %d ya estaban.' % (nuevos, total_bytes / 1048576, saltados))
        print('Guardados en %s/, ya convertidos a UTF-8.' % a.dir)


if __name__ == '__main__':
    main()
