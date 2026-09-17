#!/usr/bin/env python3
"""Carga los informes de Google Play en SQLite. Es el archivo, no la vista.

Sin dependencias: `sqlite3` viene en la biblioteca estandar. Uso:
    python3 tools/db_load.py [--dir data/play] [--db data/play.db]
                             [--rehacer] [--resumen]

POR QUE UNA BASE DE DATOS

Hasta v0.7 el panel se generaba parseando un CSV entero en cada build y lo
incrustaba completo en el HTML. Con 9.754 valoraciones eso era razonable. Con
158.895 -y con el historico de 2013 disponible, que son medio millon- deja de
serlo por tres motivos que no se arreglan optimizando el parser:

1. **Ingesta incremental.** Bajar el mes nuevo tiene que costar lo que cuesta el
   mes nuevo, no reprocesar trece anos.
2. **Clasificar una sola vez.** El lexico se aplica al INSERTAR y la etiqueta se
   guarda. Antes se reclasificaban todos los textos en cada build.
3. **Cruzar fuentes.** Reviews, notas, cierres, ANR e instalaciones son cuatro
   montones de CSV sueltos; aqui son tablas que se pueden unir por fecha y por
   version, que es justo lo que hacia falta para saber DONDE duele.

La base es la fuente de verdad y crece sin limite. El panel es una VENTANA
generada desde ella (`panel_build.py`), y sigue siendo un fichero que se abre
con `open index.html`. Si algun dia esa ventana no cabe, se parte la ventana;
la base no se toca.

FORMA DE LAS TABLAS

`reviews` es una fila por valoracion, con o sin texto, ya clasificada.

`stats` es formato largo a proposito: (metrica, fecha, dimension, valor de la
dimension, campo, valor). Anadir una dimension nueva -operador, pais, lo que
Play publique manana- es meter filas, no migrar el esquema. Con indices por
fecha y dimension, las agregaciones que necesita el panel salen en milisegundos
aunque haya millones de filas.
"""
import argparse, csv, glob, json, os, re, sqlite3, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from reviews_build import classify, finish, family, TOPIC_IDS   # mismo lexico, un solo sitio

ESQUEMA = """
CREATE TABLE IF NOT EXISTS reviews (
  key          TEXT PRIMARY KEY,
  package      TEXT NOT NULL,
  version_code INTEGER,
  version_name TEXT,
  lang         TEXT,
  device       TEXT,
  family       TEXT,
  submit_date  TEXT,
  submit_ms    INTEGER,
  update_ms    INTEGER,
  rating       INTEGER,
  title        TEXT,
  text         TEXT,
  reply_date   TEXT,
  reply_text   TEXT,
  topics       TEXT,
  sentiment    TEXT,
  content      INTEGER,
  friction     INTEGER,
  signal       INTEGER,
  src          TEXT
);
CREATE INDEX IF NOT EXISTS ix_rev_fecha   ON reviews(submit_date);
CREATE INDEX IF NOT EXISTS ix_rev_version ON reviews(version_name);
CREATE INDEX IF NOT EXISTS ix_rev_lang    ON reviews(lang);
CREATE INDEX IF NOT EXISTS ix_rev_fam     ON reviews(family);
CREATE INDEX IF NOT EXISTS ix_rev_nota    ON reviews(rating);

CREATE TABLE IF NOT EXISTS stats (
  metric    TEXT NOT NULL,
  date      TEXT NOT NULL,
  dim       TEXT NOT NULL,
  dim_value TEXT NOT NULL,
  field     TEXT NOT NULL,
  value     REAL,
  PRIMARY KEY (metric, date, dim, dim_value, field)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS ix_st_fecha ON stats(metric, dim, date);

CREATE TABLE IF NOT EXISTS ficheros (
  nombre TEXT PRIMARY KEY,
  bytes  INTEGER,
  filas  INTEGER,
  cuando TEXT
);
"""

# Campos numericos de cada informe, con el nombre corto que se guarda.
CAMPOS = {
    'ratings': {'Daily Average Rating': 'daily_avg', 'Total Average Rating': 'total_avg'},
    'crashes': {'Daily Crashes': 'crashes', 'Daily ANRs': 'anrs'},
    'installs': {'Daily Device Installs': 'device_installs',
                 'Daily Device Uninstalls': 'device_uninstalls',
                 'Daily User Installs': 'user_installs',
                 'Daily User Uninstalls': 'user_uninstalls',
                 'Active Device Installs': 'active_devices',
                 'Install events': 'install_events',
                 'Update events': 'update_events',
                 'Uninstall events': 'uninstall_events'},
}
# Columna que identifica el valor de la dimension en cada tipo de fichero.
DIM_COL = {'app_version': 'App Version Code', 'country': 'Country',
           'language': 'Language', 'os_version': 'Android OS Version',
           'device': 'Device', 'carrier': 'Carrier'}


def mes_de(nombre):
    for t in os.path.basename(nombre).replace('.csv', '').split('_'):
        if len(t) == 6 and t.isdigit():
            return t
    return None


def dimension_de(nombre):
    base = os.path.basename(nombre).replace('.csv', '')
    ym = mes_de(nombre)
    return base.split('_' + ym + '_', 1)[1] if ym and '_' + ym + '_' in base else 'overview'


def clave(r):
    """Identidad estable de una valoracion.

    Solo las reviews CON texto traen `Review Link`; el 92 % restante no tiene
    identificador, asi que se compone uno. (submit_ms, device) ya es unico en
    158.893 de 158.895 filas; anadir idioma y nota resuelve el resto sin
    inventar nada. Si el usuario edita la review, vuelve con el mismo
    submit_ms y el upsert la sustituye, que es lo que se quiere.
    """
    link = (r.get('Review Link') or '').strip()
    if link:
        return link
    return ':'.join([(r.get('Review Submit Millis Since Epoch') or '').strip(),
                     (r.get('Device') or '').strip(),
                     (r.get('Reviewer Language') or '').strip(),
                     (r.get('Star Rating') or '').strip()])


def carga_reviews(con, ficheros, verbose=True):
    nuevas = 0
    for f in ficheros:
        filas, lote = 0, []
        for r in csv.DictReader(open(f, encoding='utf-8')):
            texto = (r.get('Review Text') or '').strip()
            titulo = (r.get('Review Title') or '').strip()
            try:
                nota = int(r.get('Star Rating') or 0)
            except ValueError:
                continue
            if not nota:
                continue
            # Clasificar solo si hay texto: el 92 % restante no tiene nada que
            # clasificar y aplicarle el lexico seria inventar una etiqueta.
            if texto:
                tags, sent, content = classify(' '.join([titulo, texto]).strip())
                rec = finish({'g': tags, 's': sent, 'k': 1 if content else 0, 'r': nota})
                topics, sentimiento = ','.join(rec['g']), sent
                content, friction, signal = rec['k'], rec['w'], rec['u']
            else:
                topics, sentimiento, content, friction, signal = '', '', 0, 0, 0
            dev = (r.get('Device') or '').strip()
            lote.append((
                clave(r), r.get('Package Name') or '',
                int(r['App Version Code']) if (r.get('App Version Code') or '').strip().isdigit() else None,
                (r.get('App Version Name') or '').strip(),
                (r.get('Reviewer Language') or '').strip().replace('-', '_').split('_')[0],
                dev, family(dev),
                (r.get('Review Submit Date and Time') or '')[:10],
                int(r['Review Submit Millis Since Epoch']) if (r.get('Review Submit Millis Since Epoch') or '').isdigit() else None,
                int(r['Review Last Update Millis Since Epoch']) if (r.get('Review Last Update Millis Since Epoch') or '').isdigit() else None,
                nota, titulo, texto,
                (r.get('Developer Reply Date and Time') or '')[:10],
                (r.get('Developer Reply Text') or '').strip(),
                topics, sentimiento, content, friction, signal, os.path.basename(f),
            ))
            filas += 1
        con.executemany(
            'INSERT INTO reviews VALUES (' + ','.join(['?'] * 21) + ') '
            'ON CONFLICT(key) DO UPDATE SET '
            'version_code=excluded.version_code, version_name=excluded.version_name, '
            'update_ms=excluded.update_ms, rating=excluded.rating, title=excluded.title, '
            'text=excluded.text, reply_date=excluded.reply_date, reply_text=excluded.reply_text, '
            'topics=excluded.topics, sentiment=excluded.sentiment, content=excluded.content, '
            'friction=excluded.friction, signal=excluded.signal, src=excluded.src',
            lote)
        con.execute('INSERT OR REPLACE INTO ficheros VALUES (?,?,?,?)',
                    (os.path.basename(f), os.path.getsize(f), filas,
                     time.strftime('%Y-%m-%dT%H:%M:%S')))
        nuevas += filas
        if verbose:
            print('   %-58s %6d filas' % (os.path.basename(f), filas))
    return nuevas


def carga_stats(con, metric, ficheros, verbose=True):
    total = 0
    for f in ficheros:
        dim = dimension_de(f)
        col = DIM_COL.get(dim)
        campos = CAMPOS[metric]
        lote, filas = [], 0
        for r in csv.DictReader(open(f, encoding='utf-8')):
            fecha = (r.get('Date') or '').strip()
            if not fecha:
                continue
            valor_dim = (r.get(col) or '').strip() if col else ''
            for cab, corto in campos.items():
                v = (r.get(cab) or '').strip()
                if v == '':
                    continue
                try:
                    lote.append((metric, fecha, dim, valor_dim, corto, float(v)))
                except ValueError:
                    pass
            filas += 1
        con.executemany('INSERT OR REPLACE INTO stats VALUES (?,?,?,?,?,?)', lote)
        con.execute('INSERT OR REPLACE INTO ficheros VALUES (?,?,?,?)',
                    (os.path.basename(f), os.path.getsize(f), filas,
                     time.strftime('%Y-%m-%dT%H:%M:%S')))
        total += len(lote)
        if verbose:
            print('   %-58s %6d filas -> %7d celdas' % (os.path.basename(f), filas, len(lote)))
    return total


def pendientes(con, ficheros, rehacer):
    """Ficheros que faltan o han cambiado de tamano. El mes en curso cambia."""
    if rehacer:
        return ficheros
    ya = {n: b for n, b in con.execute('SELECT nombre, bytes FROM ficheros')}
    return [f for f in ficheros
            if ya.get(os.path.basename(f)) != os.path.getsize(f)]


def resumen(con):
    q = lambda s, *a: con.execute(s, a).fetchone()
    n, txt, d0, d1 = q('SELECT COUNT(*), SUM(text<>""), MIN(submit_date), MAX(submit_date) FROM reviews')
    print('reviews: %s valoraciones, %s con texto (%.1f %%), de %s a %s'
          % (f'{n:,}', f'{txt:,}', txt / max(n, 1) * 100, d0, d1))
    print('nota media: %.3f' % q('SELECT AVG(rating) FROM reviews')[0])
    print('\nstats por metrica y dimension:')
    for m, d, c, a, b in con.execute(
            'SELECT metric, dim, COUNT(*), MIN(date), MAX(date) FROM stats '
            'GROUP BY metric, dim ORDER BY metric, dim'):
        print('   %-9s %-13s %9s celdas   %s → %s' % (m, d, f'{c:,}', a, b))
    print('\nficheros ingeridos: %d' % q('SELECT COUNT(*) FROM ficheros')[0])


def main():
    ap = argparse.ArgumentParser(description='Carga los informes de Play en SQLite.')
    ap.add_argument('--dir', default='data/play')
    ap.add_argument('--db', default='data/play.db')
    ap.add_argument('--rehacer', action='store_true', help='reingiere todo, ignorando lo ya cargado')
    ap.add_argument('--resumen', action='store_true', help='solo enseña el estado de la base')
    a = ap.parse_args()

    os.makedirs(os.path.dirname(a.db) or '.', exist_ok=True)
    con = sqlite3.connect(a.db)
    con.executescript(ESQUEMA)
    if a.resumen:
        resumen(con); return

    con.execute('PRAGMA journal_mode=WAL')
    con.execute('PRAGMA synchronous=NORMAL')
    t0 = time.time()

    rev = sorted(glob.glob(os.path.join(a.dir, 'reviews', '*.csv')))
    falta = pendientes(con, rev, a.rehacer)
    print('reviews: %d ficheros, %d por cargar' % (len(rev), len(falta)))
    with con:
        n = carga_reviews(con, falta)
    print('   -> %s filas' % f'{n:,}')

    for metric in ('ratings', 'crashes', 'installs'):
        fs = sorted(glob.glob(os.path.join(a.dir, metric, '*.csv')))
        falta = pendientes(con, fs, a.rehacer)
        print('\n%s: %d ficheros, %d por cargar' % (metric, len(fs), len(falta)))
        with con:
            c = carga_stats(con, metric, falta)
        print('   -> %s celdas' % f'{c:,}')

    con.execute('ANALYZE')
    con.commit()
    print('\nlisto en %.1f s · %s pesa %.1f MB'
          % (time.time() - t0, a.db, os.path.getsize(a.db) / 1048576))
    print()
    resumen(con)


if __name__ == '__main__':
    main()
