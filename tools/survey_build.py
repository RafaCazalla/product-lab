#!/usr/bin/env python3
"""CSV de encuesta -> JSON clasificado.

Reutiliza el clasificador de reviews_build.py a proposito: si las dos pestanas
usan taxonomias distintas, no se pueden comparar, y comparar es justo lo que da
valor a tener dos fuentes.

PRIVACIDAD: la columna "Usuario" del CSV es un token de registro de FCM. Es una
credencial viva -- con ella se puede enviar una notificacion a ese dispositivo --
y este panel se publica. El token NUNCA sale de aqui: se guarda solo un hash
truncado, que sirve para contar respondentes unicos y detectar repetidos.

  python3 tools/survey_build.py <csv> -o data/survey.json
  python3 tools/survey_build.py <csv> --inline index.html
  python3 tools/survey_build.py <csv> --audit
"""
import argparse, csv, hashlib, json, re, sys, collections
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from reviews_build import (classify, TOPIC_IDS, TOPIC_LABEL, js_literal)

# El clasificador se escribio para resenas de tienda, donde "mejor" es elogio.
# Respondiendo a "que podriamos mejorar", casi siempre es una peticion. Se
# renombra el bucket en vez de retocar el lexico: el limite es de encuadre de la
# pregunta, no de vocabulario, y esconderlo con un parche lo haria invisible.
SURVEY_LABEL = {'praise': 'Sin queja identificable'}

# ---------------------------------------------------------------- redaccion
# La gente escribe su correo y su movil en una caja de texto libre, y este
# panel se publica. Se tachan ANTES de clasificar y antes de guardar, asi que
# el dato personal no llega ni al JSON ni al HTML. Van aqui y no en un retoque
# del HTML a mano para que valga tambien para el siguiente CSV.
# Se marca en vez de borrar: asi al leer el verbatim se ve que falta algo y no
# parece que la frase estuviera cortada.
REDACT = [
    ('email',    re.compile(r'[\w.+-]+@[\w-]+\.[\w.]{2,}')),
    ('tarjeta',  re.compile(r'(?<!\d)(?:\d[ -]?){16}(?!\d)')),
    ('iban',     re.compile(r'\b[A-Z]{2}\d{2}[ ]?\d{4}[ ]?\d{4}[\d ]*')),
    ('dni',      re.compile(r'\b\d{8}[- ]?[A-Za-z]\b')),
    # movil espanol: 9 digitos que empiezan por 6 o 7, con o sin prefijo. Va el
    # ultimo para no comerse trozos de un IBAN o de una tarjeta ya tachados.
    ('telefono', re.compile(r'(?<!\d)(?:\+34[ -]?)?[67]\d{2}[ -]?\d{2}[ -]?\d{2}[ -]?\d{2}(?!\d)')),
]
REDACTED = collections.Counter()

def redact(text):
    for name, rx in REDACT:
        text, k = rx.subn('[dato personal retirado]', text)
        if k:
            REDACTED[name] += k
    return text

SALT = b'bsp-survey-v1'          # el hash no tiene que ser estable entre proyectos


def short_id(token: str) -> str:
    return hashlib.sha256(SALT + token.encode('utf-8')).hexdigest()[:12]


def android_ver(dev: str) -> str:
    """'android (v16)' -> 'v16'. Se queda el literal si no encaja."""
    m = re.search(r'\(([^)]+)\)', dev or '')
    return m.group(1) if m else (dev or 'desconocido')


def read_rows(path):
    with open(path, encoding='utf-8-sig', newline='') as fh:
        sample = fh.read(4096); fh.seek(0)
        delim = ';' if sample.count(';') > sample.count(',') else ','
        yield from csv.DictReader(fh, delimiter=delim)


def build(path):
    raw = list(read_rows(path))
    if not raw:
        sys.exit('CSV vacio')

    need = {'Pregunta', 'Usuario', 'Comentario', 'Fecha'}
    missing = need - set(raw[0])
    if missing:
        sys.exit(f'faltan columnas: {sorted(missing)}')

    vers, devs, days, langs = [], [], [], []
    def idx(tbl, val):
        try:    return tbl.index(val)
        except ValueError:
            tbl.append(val); return len(tbl) - 1

    out, seen = [], collections.Counter()
    questions = collections.Counter()

    for r in raw:
        text = redact((r.get('Comentario') or '').strip())
        day  = (r.get('Fecha') or '')[:10]
        if not day:
            continue
        uid  = short_id(r.get('Usuario') or '')
        seen[uid] += 1
        q = (r.get('Pregunta') or '').strip()
        questions[q] += 1

        tags, sent, content = classify(text)
        # No hay nota en una encuesta, asi que la friccion sale solo del texto.
        # Y 'praise' no lo pone classify(): es excluyente y lo decide finish(), que
        # aqui no sirve porque depende de la estrella. Se replica sin ella.
        tags = [t for t in tags if t != 'praise']
        fric = sent in ('neg', 'mix')
        if not tags and sent == 'pos' and not fric:
            tags = ['praise']
        tags = [t for t in TOPIC_IDS if t in tags]

        out.append({
            'v': idx(vers,  (r.get('App Version') or '?').strip()),
            'd': idx(devs,  android_ver(r.get('Dispositivo'))),
            'y': idx(days,  day),
            'l': idx(langs, (r.get('ISO Code') or r.get('Idioma') or '?').strip()),
            't': text,
            'g': tags,
            's': sent,
            'c': 1 if content else 0,
            'w': 1 if fric else 0,
        })

    out.sort(key=lambda o: days[o['y']])
    # reindexar dias en orden cronologico
    order = sorted(range(len(days)), key=lambda i: days[i])
    remap = {old: new for new, old in enumerate(order)}
    days  = [days[i] for i in order]
    for o in out:
        o['y'] = remap[o['y']]

    n = len(out)
    ncont = sum(o['c'] for o in out)
    return {
        'meta': {
            'source':    Path(path).name,
            'question':  questions.most_common(1)[0][0] if questions else '',
            'questions': len(questions),
            'kind':      'exit',          # tipo 1: disparada tras "no me gusta"
            'n':         n,
            'content':   ncont,
            'people':    len(seen),
            'redacted':  sum(REDACTED.values()),
            'repeat':    sum(1 for c in seen.values() if c > 1),
            'from':      days[0] if days else '',
            'to':        days[-1] if days else '',
        },
        'vers': vers, 'devs': devs, 'days': days, 'langs': langs,
        'topics': [{'id': t, 'label': SURVEY_LABEL.get(t, TOPIC_LABEL[t])}
                   for t in TOPIC_IDS],
        'r': out,
    }


def audit(data):
    per = collections.Counter()
    for o in data['r']:
        if not o['c']:
            continue
        for g in (o['g'] or ['(sin tema)']):
            per[g] += 1
    cont = data['meta']['content']
    print(f"respuestas {data['meta']['n']} | con contenido {cont} "
          f"({100*cont/data['meta']['n']:.1f}%) | personas {data['meta']['people']}")
    print(f"ventana {data['meta']['from']} -> {data['meta']['to']}")
    print(f"pregunta: {data['meta']['question']!r}\n")
    for g, c in per.most_common():
        lab = TOPIC_LABEL.get(g, g)
        print(f'  {c:5}  ({100*c/cont:5.1f}%)  {lab}')
    print('\n--- muestras por tema ---')
    for g, _ in per.most_common():
        ex = [o['t'] for o in data['r'] if o['c'] and g in (o['g'] or [])][:4]
        print(f'\n### {TOPIC_LABEL.get(g,g)}')
        for e in ex:
            print('   -', e[:150].replace('\n', ' '))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('csv')
    ap.add_argument('-o', '--out')
    ap.add_argument('--inline', metavar='INDEX_HTML')
    ap.add_argument('--audit', action='store_true')
    a = ap.parse_args()

    data = build(a.csv)
    if REDACTED:
        print('datos personales tachados: '
              + ', '.join(f'{k} x{v}' for k, v in sorted(REDACTED.items())), file=sys.stderr)

    if a.audit:
        audit(data); return

    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding='utf-8')
        print(f'escrito {a.out}  ({Path(a.out).stat().st_size/1024:.0f} KB)')

    if a.inline:
        # Corte de cadenas, NO re.sub: en la cadena de reemplazo de re.sub las
        # barras invertidas son escapes, y el JSON va lleno de \u003c. Con
        # re.sub el bloque sale corrupto y la pagina no arranca.
        p = Path(a.inline); html = p.read_text(encoding='utf-8')
        start = html.find('const SD = ')
        if start < 0:
            sys.exit('no encuentro `const SD = ` en ' + a.inline)
        end = html.find(';\n</script>', start)
        if end < 0:
            sys.exit('no encuentro el final del bloque de datos en ' + a.inline)
        lit = 'const SD = ' + js_literal(data)
        p.write_text(html[:start] + lit + html[end:], encoding='utf-8')
        print(f'incrustado en {a.inline}  ({len(lit)/1024:.0f} KB)')


if __name__ == '__main__':
    main()
