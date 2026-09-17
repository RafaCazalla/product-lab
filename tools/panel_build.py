#!/usr/bin/env python3
"""Genera los datos del panel desde SQLite e incrusta los bloques en index.html.

Sin dependencias. Uso:
    python3 tools/panel_build.py [--db data/play.db] [--desde 2024-01-01] [--hasta HOY]
                                 [--inline index.html] [--out data/panel.json] [--empty]

Sustituye a `reviews_build.py <csv> --inline` como paso de construccion. El
lexico de clasificacion sigue viviendo alli y se aplica al CARGAR (db_load.py),
no aqui: este programa solo consulta y empaqueta.

DOS BLOQUES, dos naturalezas:

  RD  las valoraciones, una fila por valoracion, empaquetadas en 12 caracteres
      base36: nota(1) idioma(2) dia(3) dispositivo(3) version(2) respuesta(1).
      El panel las descomprime una vez y filtra por cualquier cruce sin indices.
      Es la misma idea que en v0.3, ensanchada: con 53 idiomas y 987 dias en la
      ventana, el formato de 10 caracteres (idioma en 1, dia en 2) se desbordaba.
      Los anchos nuevos aguantan 1.296 idiomas, 46.656 dias y 5.757 dispositivos
      sin tocar nada.

  ST  las series diarias de Play Console -nota media, cierres, ANR, instalaciones
      activas-, en total y por version. Son AGREGADOS: el panel no necesita las
      1,5 millones de celdas de la base, necesita una fila por dia. Con eso una
      ventana de 20 meses son ~600 puntos por serie.

LA VENTANA ES LA UNICA CONCESION AL TAMANO. La base guarda todo; el panel
publica un rango. Con 2024-01 -> hoy el HTML sale en unos 8 MB, casi la mitad
respuestas del equipo (contestan al 97 % de las reviews con texto). Si algun dia
la ventana no cabe, se acorta la ventana o se sacan las respuestas a un fichero
aparte; la base no se toca.
"""
import argparse, json, os, sqlite3, sys, time
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from reviews_build import TOPIC_IDS, TOPIC_LABEL, Templates, js_literal, b36  # un solo sitio

RW = 12   # ancho de fila: nota(1) idioma(2) dia(3) dispositivo(3) version(2) respuesta(1)
UMBRALES = {'crash_pct': 1.09, 'anr_pct': 0.47, 'device_crash_pct': 8.0}
# Umbrales de "mal comportamiento" de Android vitals, en % de usuarios activos
# diarios que sufren al menos un cierre o ANR percibido. Van en ST.meta para que
# la tarjeta los dibuje y la nota diga de donde salen. OJO: lo que Play publica
# en el bucket son RECUENTOS de eventos, no usuarios afectados; la tasa que se
# puede calcular aqui (eventos / dispositivos activos) no es la misma magnitud
# y la tarjeta tiene que decirlo.

def dias_entre(a, b):
    d0, d1 = date.fromisoformat(a), date.fromisoformat(b)
    return [(d0 + timedelta(days=i)).isoformat() for i in range((d1 - d0).days + 1)]


# ----------------------------------------------------------------------- RD
def construir_rd(con, desde, hasta):
    W = 'submit_date BETWEEN ? AND ?'
    filas = con.execute(f"""
        SELECT rating, lang, submit_date, device, version_name, reply_date, reply_text,
               text, title, topics, sentiment, content, friction, signal
        FROM reviews WHERE {W} ORDER BY submit_ms, key""", (desde, hasta)).fetchall()
    n = len(filas)
    if not n:
        raise SystemExit('no hay valoraciones en la ventana %s → %s' % (desde, hasta))

    # tablas de codigos, ordenadas por volumen para que los indices bajos sean
    # los frecuentes (comprime mejor y las etiquetas mas usadas quedan primero)
    def tabla(idx, vacio):
        c = {}
        for f in filas:
            k = f[idx] or vacio
            c[k] = c.get(k, 0) + 1
        return [k for k, _ in sorted(c.items(), key=lambda kv: -kv[1])]
    langs = tabla(1, '??'); devs = tabla(3, '??'); vers = tabla(4, '')
    days = sorted({f[2] for f in filas})
    iL = {k: i for i, k in enumerate(langs)}; iD = {k: i for i, k in enumerate(devs)}
    iV = {k: i for i, k in enumerate(vers)}; iY = {k: i for i, k in enumerate(days)}
    assert len(langs) < 36 ** 2 and len(days) < 36 ** 3 and len(devs) < 36 ** 3 and len(vers) < 36 ** 2

    tpl = Templates()
    packed, rev, lat_all, dist = [], [], [], [0, 0, 0, 0, 0]
    total = 0
    for k, f in enumerate(filas):
        (rating, lang, sdate, dev, ver, rdate, rtext, text, title, topics, sent, content, fric, sig) = f
        dist[rating - 1] += 1; total += rating
        rlat = -1
        if rtext:
            try:
                rlat = max(0, (date.fromisoformat(rdate) - date.fromisoformat(sdate)).days) if rdate else 0
            except ValueError:
                rlat = 0
            lat_all.append(rlat)
        packed.append(str(rating) + b36(iL[lang or '??'], 2) + b36(iY[sdate], 3)
                      + b36(iD[dev or '??'], 3) + b36(iV[ver or ''], 2)
                      + ('-' if rlat < 0 else b36(min(rlat, 35), 1)))
        if text:
            rev.append({'n': k, 'x': (title + ' — ' + text) if title else text,
                        'g': [t for t in topics.split(',') if t], 's': sent,
                        'k': content, 'w': fric, 'u': sig,
                        'y': tpl.add(rtext) if rtext else -1})

    meses = con.execute(f"""SELECT substr(submit_date,1,7) m, COUNT(*) FROM reviews
                            WHERE {W} GROUP BY m ORDER BY m""", (desde, hasta)).fetchall()
    return {
        'meta': {
            'source': 'Google Play · com.resultadosfutbol.mobile',
            'format': 'rd/2', 'rw': RW,
            'window': {'from': desde, 'to': hasta},
            'n': n, 'n_text': len(rev),
            'from': days[0], 'to': days[-1],
            'avg': round(total / n, 3), 'dist': dist,
            'devices_total': len(devs), 'dedup': 0,
            # Antes: lotes de exportacion manual. Ahora: meses de informe. La
            # tarjeta de cobertura lo lee como "periodos con dato", no como aviso.
            'batches': [[m, c] for m, c in meses],
            'reply_lat': sorted(lat_all),
            'topics': [{'id': t, 'label': TOPIC_LABEL[t]} for t in TOPIC_IDS],
        },
        'langs': langs, 'devs': devs, 'vers': vers, 'days': days,
        'tpl': tpl.list, 'rows': ''.join(packed), 'rev': rev,
    }


# ----------------------------------------------------------------------- ST
def serie(con, metric, dim, dim_value, field, days):
    """Array alineado con `days`; null donde no hay dato."""
    m = dict(con.execute("""SELECT date, value FROM stats
                            WHERE metric=? AND dim=? AND dim_value=? AND field=?""",
                         (metric, dim, dim_value, field)).fetchall())
    # Play publica 0 como nota media el dia en que una version no recibe ninguna
    # valoracion. Una nota va de 1 a 5: el 0 no es un valor, es "sin dato", y si
    # se dejara pasar tiraria hacia abajo cualquier media semanal de una version
    # con poco volumen. Se convierte en null aqui, en el origen, para que ninguna
    # tarjeta tenga que acordarse de filtrarlo.
    es_nota = field in ('daily_avg', 'total_avg')
    out = []
    for d in days:
        v = m.get(d)
        if v is None or (es_nota and v <= 0):
            out.append(None)
        else:
            out.append(round(v, 4) if es_nota else int(v))
    return out


def construir_st(con, desde, hasta, top_versiones=14):
    lo, hi = con.execute("SELECT MIN(date), MAX(date) FROM stats").fetchone()
    if not lo:
        return {'meta': {'from': None, 'to': None, 'thresholds': UMBRALES}, 'days': [],
                'overview': {}, 'versions': []}
    a, b = max(lo, desde), min(hi, hasta)
    days = dias_entre(a, b)

    overview = {
        'rating_daily':    serie(con, 'ratings',  'overview', '', 'daily_avg', days),
        'rating_total':    serie(con, 'ratings',  'overview', '', 'total_avg', days),
        'crashes':         serie(con, 'crashes',  'overview', '', 'crashes', days),
        'anrs':            serie(con, 'crashes',  'overview', '', 'anrs', days),
        'active_devices':  serie(con, 'installs', 'overview', '', 'active_devices', days),
        'user_installs':   serie(con, 'installs', 'overview', '', 'user_installs', days),
        'user_uninstalls': serie(con, 'installs', 'overview', '', 'user_uninstalls', days),
    }

    # Versiones: las que mas valoraciones acumulan en la ventana, mas cualquiera
    # que destaque en ANR aunque nadie la haya resenado (las hay: 91 codigos).
    nombre = dict(con.execute("""SELECT CAST(version_code AS TEXT), version_name FROM reviews
                                 WHERE version_code IS NOT NULL GROUP BY version_code""").fetchall())
    por_reviews = [c for c, in con.execute("""
        SELECT CAST(version_code AS TEXT) FROM reviews
        WHERE version_code IS NOT NULL AND submit_date BETWEEN ? AND ?
        GROUP BY version_code ORDER BY COUNT(*) DESC LIMIT ?""", (desde, hasta, top_versiones))]
    por_anr = [c for c, in con.execute("""
        SELECT dim_value FROM stats WHERE metric='crashes' AND dim='app_version' AND field='anrs'
        AND date BETWEEN ? AND ? GROUP BY dim_value ORDER BY SUM(value) DESC LIMIT 6""", (a, b))]
    codigos = list(dict.fromkeys(por_reviews + por_anr))
    versions = []
    for c in codigos:
        versions.append({
            'code': c, 'name': nombre.get(c, c),
            'rating_daily':   serie(con, 'ratings',  'app_version', c, 'daily_avg', days),
            'crashes':        serie(con, 'crashes',  'app_version', c, 'crashes', days),
            'anrs':           serie(con, 'crashes',  'app_version', c, 'anrs', days),
            'active_devices': serie(con, 'installs', 'app_version', c, 'active_devices', days),
        })
    return {'meta': {'from': a, 'to': b, 'thresholds': UMBRALES,
                     'note': 'recuentos diarios de eventos; la tasa por dispositivo activo NO es la magnitud de los umbrales de Android vitals'},
            'days': days, 'overview': overview, 'versions': versions}


# ------------------------------------------------------------------- inline
def incrustar(path, nombre, obj, tras=None):
    """Sustituye `const NOMBRE = …;` en index.html, o lo crea tras el bloque `tras`."""
    html = open(path, encoding='utf-8').read()
    marca = 'const %s = ' % nombre
    lit = marca + js_literal(obj)
    start = html.find(marca)
    if start >= 0:
        end = html.find(';\n</script>', start)
        if end < 0:
            raise SystemExit('bloque %s sin cierre en %s' % (nombre, path))
        html = html[:start] + lit + html[end:]
    else:
        if not tras:
            raise SystemExit('no existe `%s` en %s y no se ha dicho tras que bloque crearlo' % (marca, path))
        anc = html.find('const %s = ' % tras)
        fin = html.find(';\n</script>', anc) + len(';\n</script>')
        bloque = ('\n\n<script>\n/* Series diarias de Play Console (nota, cierres, ANR, instalaciones),\n'
                  '   generadas por tools/panel_build.py desde data/play.db. */\n' + lit + ';\n</script>')
        html = html[:fin] + bloque + html[fin:]
    open(path, 'w', encoding='utf-8').write(html)
    return len(html)


def vacio():
    hoy = date.today().isoformat()
    rd = {'meta': {'source': 'Google Play · com.resultadosfutbol.mobile (sin datos)', 'format': 'rd/2', 'rw': RW,
                   'window': {'from': hoy, 'to': hoy}, 'n': 0, 'n_text': 0, 'from': hoy, 'to': hoy,
                   'avg': 0, 'dist': [0, 0, 0, 0, 0], 'devices_total': 0, 'dedup': 0, 'batches': [],
                   'reply_lat': [], 'topics': [{'id': t, 'label': TOPIC_LABEL[t]} for t in TOPIC_IDS]},
          'langs': ['es'], 'devs': ['??'], 'vers': [''], 'days': [hoy], 'tpl': [], 'rows': '', 'rev': []}
    st = {'meta': {'from': None, 'to': None, 'thresholds': UMBRALES}, 'days': [], 'overview': {}, 'versions': []}
    return rd, st


def main():
    ap = argparse.ArgumentParser(description='Genera los datos del panel desde SQLite.')
    ap.add_argument('--db', default='data/play.db')
    ap.add_argument('--desde', default='2024-01-01')
    ap.add_argument('--hasta', default=date.today().isoformat())
    ap.add_argument('--inline', default=None, help='index.html en el que incrustar RD y ST')
    ap.add_argument('--out', default='data/panel.json', help='copia legible (RD+ST)')
    ap.add_argument('--empty', action='store_true', help='esqueleto vacio, para el index.html del repositorio')
    a = ap.parse_args()

    t0 = time.time()
    if a.empty:
        rd, st = vacio()
    else:
        con = sqlite3.connect(a.db)
        rd = construir_rd(con, a.desde, a.hasta)
        st = construir_st(con, a.desde, a.hasta)

    os.makedirs(os.path.dirname(a.out) or '.', exist_ok=True)
    with open(a.out, 'w', encoding='utf-8') as fh:
        json.dump({'RD': rd, 'ST': st}, fh, ensure_ascii=False, separators=(',', ':'))

    # desglose del peso: es lo que decide la ventana, asi que se ensena siempre
    peso = lambda o: len(js_literal(o).encode('utf-8')) / 1048576
    print('RD  %5.2f MB   filas %.2f · textos %.2f · respuestas %.2f · tablas %.2f'
          % (peso(rd), len(rd['rows']) / 1048576,
             peso([r['x'] for r in rd['rev']]), peso(rd['tpl']),
             peso({k: rd[k] for k in ('langs', 'devs', 'vers', 'days')})))
    print('ST  %5.2f MB   %d dias · %d versiones' % (peso(st), len(st['days']), len(st['versions'])))
    print('    %s valoraciones · %s con texto · %d idiomas · %s dispositivos · %d versiones · %d dias'
          % (f"{rd['meta']['n']:,}", f"{rd['meta']['n_text']:,}", len(rd['langs']),
             f"{len(rd['devs']):,}", len(rd['vers']), len(rd['days'])))
    if a.inline:
        tam = incrustar(a.inline, 'RD', rd)
        tam = incrustar(a.inline, 'ST', st, tras='RD')
        print('%s: %.1f MB en total' % (a.inline, tam / 1048576))
    print('listo en %.1f s' % (time.time() - t0))


if __name__ == '__main__':
    main()
