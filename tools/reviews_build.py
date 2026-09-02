#!/usr/bin/env python3
"""Clasifica las reviews de Google Play y genera el JSON que consume index.html.

Sin dependencias. Uso:
    python3 tools/reviews_build.py <csv> [-o data/reviews.json] [--audit]

El etiquetado es lexico multiidioma (es/fr/pt/en/it/ca + arabe basico) sobre el texto
en crudo, normalizado sin acentos. Cada review puede llevar varios temas; el
sentimiento sale SOLO del texto (no del rating) para que el cruce rating x sentimiento
tenga informacion, y vale 'ind' cuando el texto no da senal.
"""
import argparse, csv, json, math, re, sys, unicodedata
from collections import Counter, defaultdict
from datetime import date

# ---------------------------------------------------------------- normalizacion
def norm(s):
    s = unicodedata.normalize('NFD', s.lower())
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')
    return re.sub(r'\s+', ' ', s)

def rx(*alts):
    return re.compile('|'.join(alts))

# ------------------------------------------------------------------- taxonomia
# Cada tema: (id, etiqueta, patron). El orden fija el orden de presentacion.
TOPICS = [
    ('ads',     'Publicidad excesiva', rx(
        r'\bpublicidad\b', r'\banunci', r'\bpubli\b', r'\bpub\b', r'\bpublicit',
        r'\bads?\b', r'\badds?\b', r'\badvert', r'\bpropaganda\b', r'\breklam',
        r'\bspot\b', r'\bcomerciales\b', r'\bvideos? de \d+\b', r'\bتطبيق.*اعلان', r'\bاعلان')),
    ('ads_paid', 'Anuncios con suscripción activa', None),   # co-ocurrencia, ver abajo
    ('betting', 'Publicidad de apuestas', rx(
        r'\bapuesta', r'\bcasas? de apuesta', r'\bbetting\b', r'\bparis? sportif',
        r'\bapostas?\b', r'\bcasas de aposta', r'\bcasino\b', r'\b1xbet\b', r'\bbetano\b',
        r'\bbwin\b', r'\bcodere\b', r'\bmelbet\b', r'\bpronostic', r'\bbookmaker')),
    ('chat',    'Chat y comentarios retirados', rx(
        r'\bchat', r'\bcomentario', r'\bcomentar\b', r'\bcoment', r'\bcommentaire',
        r'\bmensaje', r'\bmensagen', r'\bmessage', r'\bglobal\b', r'\bforo\b',
        r'\bopiniones\b', r'\bconversa')),
    ('crash',   'No abre o se cierra', rx(
        r'\bno (se )?(abre|abr[ei])', r'\bno funciona', r'\bno carga', r'\bse cierra',
        r'\bse cuelga', r'\bcuelga\b', r'\bme saca\b', r'\bse sale\b', r'\bsale del app',
        r'\bpetard', r'\bcrash', r'\bbug\b', r'\bfall[ao]s?\b', r'\berror',
        r'\bne (s.)?(ouvre|marche|fonctionne)', r'\brefuse de', r'\bcess[ée] de fonctionner',
        r'\bne fonctionne plus', r'\bnao (abre|funciona|carrega)', r'\bfecha sozinho',
        r'\bsai do app', r"\bdoesn'?t (open|work)", r'\bwon.?t open', r'\bkeeps closing',
        r'\bblanco\b', r'\bpantalla en blanco', r'\bimposible (entrar|abrir)',
        r'\bno (puedo|se puede) (entrar|abrir|acceder)', r'\bplanta\b', r'\btrava\b')),
    ('perf',    'Lentitud y consumo', rx(
        r'\blent[ao]', r'\bmuy lenta', r'\bva lenta', r'\btarda\b', r'\bpesada\b',
        r'\bslow\b', r'\bbater[ií]a', r'\bbattery\b', r'\bcalienta', r'\bmemoria\b',
        r'\bespacio\b', r'\bconsume\b', r'\bdemora')),
    ('data',    'Datos, cobertura y estadísticas', rx(
        r'\bresultado', r'\bestadistic', r'\bdatos?\b', r'\bligas?\b', r'\bliga\b',
        r'\bcompetici', r'\btorneo', r'\bcampeonato', r'\bequipos?\b', r'\bjugador',
        r'\bplantilla', r'\balineaci', r'\bminuto\b', r'\bretras', r'\bdesactualiz',
        r'\bincorrect', r'\berrone', r'\bno actualiza', r'\bfaltan?\b', r'\bno aparece',
        r'\bmarcador', r'\bgoles?\b', r'\bstats?\b', r'\bstatistic', r'\bleagues?\b',
        r'\bmissing\b', r'\bhead[- ]?to[- ]?head\b', r'\bh2h\b', r'\bclassement',
        r'\bcalendrier', r'\bstatistiqu', r'\bligue', r'\bequipe', r'\bjoueur',
        r'\bfemenin', r'\bfeminin', r'\btransfer', r'\bfichaje')),
    ('notif',   'Notificaciones', rx(
        r'\bnotificaci', r'\bnotificac', r'\bnotification', r'\bnotifica',
        r'\bavis[oa]s?\b', r'\balert', r'\bmolestando en la noche', r'\bpush\b')),
    ('update',  'Regresión tras actualizar', None),   # co-ocurrencia, ver abajo
    ('ux',      'Interfaz, registro y usabilidad', rx(
        r'\binterfaz\b', r'\bdiseno\b', r'\bmenu\b', r'\bpantalla\b',
        r'\bregistr', r'\biniciar sesion', r'\blogin\b', r'\bcuenta\b', r'\bcontrasena\b',
        r'\bconfus', r'\bcomplicad', r'\bidioma\b', r'\btraducci', r'\bmodo oscuro\b',
        r'\bversion anterior\b', r'\bnavega', r'\bencontrar\b', r'\bboton')),
    ('pay',     'Precio y suscripción', rx(
        r'\bsuscripci', r'\bsubscri', r'\bsubscric', r'\bpremium\b', r'\bpago\b',
        r'\bpagar\b', r'\bpagu[ée]', r'\bprecio\b', r'\bcobr', r'\babonn', r'\babonam',
        r'\bpaye\b', r'\bpaid\b', r'\bpayment\b', r'\bdinero\b', r'\breembols',
        r'\bde pago\b', r'\bcaro\b', r'\babono\b', r'\bassinatura\b', r'\babone')),
    ('praise',  'Elogio sin petición', None),                 # excluyente, ver finish()
]
TOPIC_IDS = [t[0] for t in TOPICS]
TOPIC_LABEL = {t[0]: t[1] for t in TOPICS}

# ads_paid = habla de suscripcion/pago Y de anuncios
_BY_ID = {t[0]: t[2] for t in TOPICS}
PAY_RX = _BY_ID['pay']
ADS_RX = _BY_ID['ads']

# ------------------------------------------------------------------ sentimiento
POS = rx(r'\bexcelente\b', r'\bexcelent', r'\bexcellent', r'\bmuy buena?\b', r'\bmuy bien\b',
         r'\bbuena?\b', r'\bbueno\b', r'\bgenial\b', r'\bperfect', r'\bmejor\b', r'\bla mejor\b',
         r'\bme gusta\b', r'\bme encanta\b', r'\brecomiend', r'\bgracias\b', r'\bfelicidades\b',
         r'\benhorabuena\b', r'\bmaravillos', r'\bfantastic', r'\bincreible\b', r'\bcompleta\b',
         r'\butil\b', r'\brapida\b', r'\bfiable\b', r'\btop\b', r'\bsuper\b', r'\bcontento\b',
         r'\bsatisfait', r'\bmagnifiqu', r'\bformidable\b', r'\bgeni[ao]l', r'\bbien\b',
         r'\bbon(ne)?\b', r'\btres bon', r'\bmeilleur', r'\bj.aime\b', r'\bparfait',
         r'\botim[ao]\b', r'\bbo[am]\b', r'\bmuito bo', r'\bgostei\b', r'\bmelhor\b',
         r'\bparabens\b', r'\bgood\b', r'\bgreat\b', r'\bbest\b', r'\bnice\b', r'\blove\b',
         r'\bawesome\b', r'\bamazing\b', r'\bjmil\b', r'\bرائع', r'\bجميل', r'\bجيد',
         r'\bممتاز', r'\bالافضل')
NEG = rx(r'\bmal[ao]?\b', r'\bpeor\b', r'\bpesim', r'\bhorrible\b', r'\bhorroros',
         r'\basco\b', r'\bda asco\b', r'\bvergonzos', r'\bverguenza\b',
         r'\bbasura\b', r'\bdesinstal', r'\binservible\b', r'\bestafa\b',
         r'\bengan', r'\bharto\b', r'\baturd', r'\basfixiante', r'\bmolest', r'\bpereza\b',
         r'\bdemasiad', r'\bmuchisim', r'\bexcesiv', r'\bimposible\b', r'\bodio\b',
         r'\bnul\b', r'\bmauvais', r'\blamentable\b', r'\bdecu\b', r'\bdeteste',
         r'\bhonteux', r'\btrop de\b', r'\bpior\b', r'\bruim\b', r'\bhorrivel',
         r'\bodiei\b', r'\bpessim', r'\bbad\b', r'\bworst\b', r'\bawful\b',
         r'\bterrible\b', r'\bdisgusting\b', r'\bhate\b', r'\bboring\b', r'\buseless\b',
         r'\bzero\b', r'\bسيئ')
# positivos negados: "no muy bien", "pas bon", "not good". Se evaluan primero y el
# tramo negado se borra antes de buscar positivos, para que no cuenten como elogio.
NEGATED = rx(r'\bno (muy |es |esta |era |tan )?(buen[ao]?|bien|util|mejor|sirve|funciona|carga|abre|me gusta|recomiend|vale)\w*',
             r'\bne (pas |plus )?(fonctionne|marche|s.ouvre)\w*', r'\bpas (tres |si )?(bon|bien|top)\w*',
             r'\bplus (de )?(bon|bien)\w*', r'\bnao (e |esta |muito )?(bo[am]|bem|gostei|funciona|abre)\w*',
             r'\bnot (very |so )?(good|nice|working|great)\w*', r'\bdoesn.?t work\w*',
             r'\bnao gost\w*', r'\bno me gusta\w*', r'\bلا يعمل')
# negativos negados: "no molesta", "sin publicidad", "aucune publicite". El tramo se
# borra antes de buscar negativos, para que no cuenten como queja.
UNNEG = rx(r'\bno (me )?(molest|import|falla|falta|pesa|tiene anuncio|hay anuncio|hay publicidad)\w*',
           r'\b(no|nada) (de )?(malo|mala|pesim|horrible)\w*', r'\bpara nada mal\w*',
           r'\bsin (publicidad|anuncios|problemas|fallos)\w*', r'\bnunca (falla|me falla)\w*',
           r'\baucune? (publicite|pub|probleme)\w*', r'\bsans (publicite|pub|probleme)\w*',
           r'\bsem (publicidade|anuncios|problema)\w*', r'\bno (tiene|trae) (mucha )?(publicidad|anuncios)\w*',
           r'\bnot (bad|boring)\w*', r'\bnada mal\w*')
ADVERS = rx(r'\bpero\b', r'\bmais\b', r'\bbut\b',
            r'\bsin embargo\b', r'\bcependant\b', r'\btoutefois\b', r'\bporem\b',
            r'\bcontudo\b', r'\baunque\b', r'\bexcepto\b', r'\blo unico\b',
            r'\bel unico\b', r'\bunica pega\b', r'\bhowever\b', r'\bsolo que\b')
# peticiones: senal de intencion aunque no haya palabra negativa
ASK = rx(r'\bdeberian?\b', r'\bdevuelv', r'\bvuelva\b', r'\bvuelvan\b', r'\bquiero\b',
         r'\bquero\b', r'\bfalta', r'\bseria bueno\b', r'\bpor favor\b', r'\bs.il vous plait\b',
         r'\bplease\b', r'\bpodrian\b', r'\bespero que\b', r'\bmejorar', r'\barreglen\b',
         r'\bsugerencia\b', r'\bpido\b', r'\bnecesito\b', r'\bagreguen\b', r'\banadir\b',
         r'\bconsider', r'\bbring back\b', r'\bramenez\b', r'\bremett', r'\bpourquoi\b',
         r'\bpor que\b', r'\bporque quit', r'\bpor q\b')
# regresion: la app empeoro al actualizar (palabra de version + senal de "antes si")
UPD  = rx(r'\bactualizaci', r'\bactualiz', r'\bupdate\b', r'\bmise a jour\b',
          r'\batualizac', r'\bnueva version\b', r'\bnova versao\b', r'\bultima version\b',
          r'\bderniere (version|mise)\b', r'\bversion nueva\b', r'\bnew version\b')
WAS  = rx(r'\bantes\b', r'\bauparavant\b', r'\bavant\b', r'\bantigament', r'\bya no\b',
          r'\bdesde (la |que )', r'\bdepuis\b', r'\bdesde a ultima\b', r'\bafter the\b',
          r'\bsince the\b', r'\bnao (mais|funciona)\b', r'\bahora\b', r'\bmaintenant\b',
          r'\bagora\b', r'\bnow\b', r'\bversion anterior\b', r'\brecent')
# stopwords: si un texto no trae ninguna, casi seguro no es una frase (nombre propio,
# aporreo de teclado). Es el filtro que separa "review" de "ruido".
STOP = set(('de la el los las que y no pero muy es esta esto para con por un una mas si '
            'me te se lo al del en su sus como mi todo todos hay ya sin sobre cuando '
            'le les des est pas plus tres dans sur avec pour ce cette il elle nous vous '
            'mais tout tous rien bien trop je jai cest suis etre fait '
            'o a os as que nao muito para com por um uma mais se do da dos das nos '
            'the is are a to and of it this that for in on with you my not have has '
            'app aplicacion application aplicativo').split())

def has_content(n, words, tags, p, g, ask):
    if tags or p or g or ask:
        return True
    return any(w in STOP for w in words)
# ------------------------------------------------------------------- familias
def family(dev):
    if dev.startswith('TECNO-'):   return 'Tecno'
    if dev.startswith('Infinix-'): return 'Infinix'
    if dev.startswith('itel-'):    return 'itel'
    if dev.startswith('HN'):       return 'Honor'
    if re.match(r'^a\d{2}', dev):  return 'Samsung Galaxy A*'
    return 'Sin identificar'
TRANSSION = {'Tecno', 'Infinix', 'itel'}

# ------------------------------------------------------------------ clasificar
def classify(text):
    """-> (tags, sentimiento, contenido, friccion)"""
    n = norm(text)
    words = re.findall(r'[a-z؀-ۿ]{2,}', n)
    tags = []
    for tid, _, pat in TOPICS:
        if pat is not None and pat.search(n):
            tags.append(tid)
    if PAY_RX.search(n) and ADS_RX.search(n):
        tags.append('ads_paid')
    if UPD.search(n) and WAS.search(n):
        tags.append('update')

    # sentimiento: primero los positivos negados, luego lo que queda
    neg_hit = bool(NEGATED.search(n))
    p = bool(POS.search(NEGATED.sub(' ', n)))
    g = bool(NEG.search(UNNEG.sub(' ', n))) or neg_hit
    ask = bool(ASK.search(n))

    if p and g:
        sent = 'mix'
    elif g:
        sent = 'neg'
    elif p and ask and ADVERS.search(n):
        sent = 'mix'
    elif p:
        sent = 'pos'
    elif ask:
        sent = 'mix'
    else:
        sent = 'ind'

    content = has_content(n, words, [t for t in tags if t != 'praise'], p, g, ask)
    return tags, sent, content

def finish(rec):
    """Anade 'praise' (excluyente), friccion y senal accionable."""
    tags = [t for t in rec['g'] if t != 'praise']
    rt, sent = rec['r'], rec['s']
    fric = rt <= 3 or sent in ('neg', 'mix')
    if not tags and sent == 'pos' and not fric:
        tags = ['praise']
    rec['g'] = [t for t in TOPIC_IDS if t in tags]
    rec['w'] = 1 if fric else 0
    rec['u'] = 1 if (rec['k'] and [t for t in rec['g'] if t != 'praise']) else 0
    return rec

def b36(v, width):
    """Entero -> base36 de ancho fijo. Es el empaquetado de las filas."""
    d = '0123456789abcdefghijklmnopqrstuvwxyz'
    out = ''
    for _ in range(width):
        out = d[v % 36] + out; v //= 36
    if v: raise ValueError('no cabe en %d chars' % width)
    return out

GREET = re.compile(r'^(Bonjour|Hola|Ol[áa]|Hello|Hi|Salut)\s+[^,]{0,30},')

class Templates:
    """Tabla de plantillas de respuesta: dedupe por texto con el saludo normalizado."""
    def __init__(self):
        self.idx, self.list = {}, []
    def add(self, txt):
        t = GREET.sub(r'\1 {nombre},', txt.strip())[:420]
        if t not in self.idx:
            self.idx[t] = len(self.list); self.list.append(t)
        return self.idx[t]

def wilson(k, n, z=1.96):
    if n == 0: return (0.0, 0.0)
    p = k / n; den = 1 + z * z / n
    c = p + z * z / (2 * n); m = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return ((c - m) / den, (c + m) / den)

# ------------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('csv', nargs='?')
    ap.add_argument('-o', '--out', default='data/reviews.json')
    ap.add_argument('--audit', action='store_true', help='imprime el etiquetado para revisarlo')
    ap.add_argument('--empty', action='store_true',
                    help='no lee el CSV: emite el esqueleto de datos VACIO. Es lo que se '
                         'sube al repositorio publico, para no publicar el texto de las '
                         'reviews. La pagina arranca y ensena su estado vacio.')
    ap.add_argument('--inline', metavar='INDEX_HTML',
                    help='ademas de escribir el JSON, sustituye el bloque `const RD = ...;` '
                         'de ese index.html. Es la forma reproducible de actualizar el panel.')
    a = ap.parse_args()

    if a.empty:
        empty_out(a)
        return
    if not a.csv:
        raise SystemExit('falta el CSV (o usa --empty)')
    with open(a.csv, encoding='utf-8') as fh:
        rows = list(csv.DictReader(fh))
    rows, dropped = dedupe(rows)

    recs = []
    dev_stats = defaultdict(lambda: [0, 0])          # device -> [n, n_1_2]
    fam_stats = defaultdict(lambda: [0, 0, 0])       # family -> [n, suma, n_1_2]
    lang_stats = defaultdict(lambda: [0, 0, 0, 0])   # lang -> [n, suma, n_1_2, n_texto]
    ver_stats = defaultdict(lambda: [0, 0, 0])
    day_stats = defaultdict(lambda: [0, 0, 0])
    lot = Counter()
    tpl = Templates()
    reply_by_rating = defaultdict(lambda: [0, 0])
    lat = []

    for r in rows:
        rt = int(r['rating']); lg = r['language'] or '??'
        dv = r['device'] or '??'; fm = family(dv)
        vs = r['app_version'] or ''
        dy = r['date']; txt = r['text'].strip()
        rep = r['developer_reply_text'].strip()
        rep_lat = None
        if rep and r['developer_reply_date'] not in ('NULL', ''):
            try:
                rep_lat = (date.fromisoformat(r['developer_reply_date'][:10])
                           - date.fromisoformat(dy)).days
            except ValueError:
                pass

        dev_stats[dv][0] += 1;  dev_stats[dv][1] += rt <= 2
        fam_stats[fm][0] += 1;  fam_stats[fm][1] += rt; fam_stats[fm][2] += rt <= 2
        lang_stats[lg][0] += 1; lang_stats[lg][1] += rt; lang_stats[lg][2] += rt <= 2
        lang_stats[lg][3] += bool(txt)
        ver_stats[vs][0] += 1;  ver_stats[vs][1] += rt; ver_stats[vs][2] += rt <= 2
        day_stats[dy][0] += 1;  day_stats[dy][1] += rt; day_stats[dy][2] += rt <= 2
        lot[r['took_date'][:10]] += 1
        reply_by_rating[rt][0] += 1; reply_by_rating[rt][1] += bool(rep)
        if rep_lat is not None:
            lat.append(rep_lat)

        if txt:
            tags, sent, content = classify(txt)
            recs.append(finish({
                'i': int(r['id']), 'r': rt, 'l': lg, 'd': dv,
                'v': vs, 't': dy, 'x': txt, 'g': tags, 's': sent,
                'k': 1 if content else 0,
                'y': tpl.add(rep) if rep else -1,
                'yl': rep_lat if rep_lat is not None else -1,
            }))

    if a.audit:
        audit(recs)
        return

    n = len(rows)
    tot = sum(int(r['rating']) for r in rows)

    # ---- tablas de codigos: las filas se empaquetan como indices base36 ----
    langs = [k for k, _ in sorted(lang_stats.items(), key=lambda kv: -kv[1][0])]
    devs_t = [k for k, _ in sorted(dev_stats.items(), key=lambda kv: -kv[1][0])]
    vers_t = [k for k, _ in sorted(ver_stats.items(), key=lambda kv: -kv[1][0])]
    days_t = sorted(day_stats)
    iL = {k: i for i, k in enumerate(langs)}
    iD = {k: i for i, k in enumerate(devs_t)}
    iV = {k: i for i, k in enumerate(vers_t)}
    iY = {k: i for i, k in enumerate(days_t)}

    # 10 chars por valoracion: rating(1) idioma(1) dia(2) device(3) version(2) respuesta(1)
    # respuesta: '-' sin responder, si no la latencia en dias en base36 (tope 35)
    packed, rev_out = [], []
    row_of = {}
    for k, r in enumerate(rows):
        rep = r['developer_reply_text'].strip()
        rlat = -1
        if rep and r['developer_reply_date'] not in ('NULL', ''):
            try:
                rlat = (date.fromisoformat(r['developer_reply_date'][:10])
                        - date.fromisoformat(r['date'])).days
            except ValueError:
                rlat = 0
        elif rep:
            rlat = 0
        packed.append(
            r['rating'][0]
            + b36(iL[r['language'] or '??'], 1)
            + b36(iY[r['date']], 2)
            + b36(iD[r['device'] or '??'], 3)
            + b36(iV[r['app_version'] or ''], 2)
            + ('-' if rlat < 0 else b36(min(max(rlat, 0), 35), 1)))
        row_of[int(r['id'])] = k

    for rec in recs:
        rec['n'] = row_of[rec['i']]
        rev_out.append({'n': rec['n'], 'x': rec['x'], 'g': rec['g'], 's': rec['s'],
                        'k': rec['k'], 'w': rec['w'], 'u': rec['u'], 'y': rec['y']})

    devs = [{'d': d, 'n': v[0], 'b': v[1],
             'lo': round(wilson(v[1], v[0])[0], 4), 'hi': round(wilson(v[1], v[0])[1], 4),
             'f': family(d)}
            for d, v in dev_stats.items() if v[0] >= 30]
    devs.sort(key=lambda x: -x['n'])

    out = {
        'meta': {
            'source': 'Google Play · com.resultadosfutbol.mobile',
            'n': n, 'n_text': len(recs),
            'from': min(r['date'] for r in rows), 'to': max(r['date'] for r in rows),
            'avg': round(tot / n, 3),
            'dist': [sum(1 for r in rows if int(r['rating']) == k) for k in range(1, 6)],
            'devices_total': len(dev_stats),
            'dedup': dropped,
            'batches': sorted(lot.items()),
            'reply_lat': sorted(lat),
            'topics': [{'id': t, 'label': TOPIC_LABEL[t]} for t in TOPIC_IDS],
        },
        'langs': langs, 'devs': devs_t, 'vers': vers_t, 'days': days_t,
        'tpl': [t[:240] for t in tpl.list],
        'rows': ''.join(packed),
        'dev': devs,
        'rev': rev_out,
    }
    import os
    os.makedirs(os.path.dirname(a.out) or '.', exist_ok=True)
    with open(a.out, 'w', encoding='utf-8') as fh:
        json.dump(out, fh, ensure_ascii=False, separators=(',', ':'))
    sz = os.path.getsize(a.out)
    print(f"{a.out}: {sz/1024:.1f} KB · {n} valoraciones · {len(recs)} con texto · "
          f"{len(devs)} modelos con n>=30 · {len(tpl.list)} plantillas")
    print(f"reingestas descartadas: {dropped}")
    if a.inline:
        inline_into(a.inline, out)
    cov = sum(1 for r in recs if [t for t in r['g'] if t != 'praise'])
    print(f"temas de problema: {cov}/{len(recs)} ({cov/len(recs):.1%})")
    print("sentimiento:", dict(Counter(r['s'] for r in recs)))
    print("sin contenido:", sum(1 for r in recs if not r['k']),
          "| friccion:", sum(1 for r in recs if r['w']),
          "| accionables:", sum(1 for r in recs if r['u']))
    print("temas:", dict(Counter(t for r in recs for t in r['g']).most_common()))
    print("tablas:", f"idiomas={len(langs)} devices={len(devs_t)} versiones={len(vers_t)} dias={len(days_t)}")

def dedupe(rows):
    """Quita reviews reingeridas: la misma review vuelve en un lote posterior
    con un id nuevo, y así una sola queja se cuenta dos o tres veces.

    La huella exige coincidencia exacta de texto + dispositivo + fecha + nota,
    texto de al menos 20 caracteres (por debajo de eso, dos usuarios distintos
    pueden escribir «ouvrir» el mismo dia en el mismo modelo y no seria un
    duplicado) y que el grupo aparezca en lotes de recoleccion distintos, que
    es la marca de la reingesta. Se conserva la fila del lote mas antiguo.

    Ojo con lo que esto NO puede hacer: en las valoraciones SIN texto la huella
    se queda en dispositivo + fecha + nota + version, que muchisimos usuarios
    distintos comparten de forma legitima. Alli la reingesta es indetectable,
    asi que puede quedar una inflacion pequena del mismo tipo sin ver.
    """
    seen, out, dropped = {}, [], 0
    for r in rows:
        txt = r['text'].strip()
        if len(txt) < 20:
            out.append(r); continue
        k = (txt, r['device'], r['date'], r['rating'])
        prev = seen.get(k)
        if prev is None:
            seen[k] = r; out.append(r); continue
        if prev['took_date'][:10] == r['took_date'][:10]:
            out.append(r); continue          # mismo lote: son dos reviews
        dropped += 1
        if r['took_date'] < prev['took_date']:   # nos queda la del lote mas antiguo
            out[out.index(prev)] = r
            seen[k] = r
    return out, dropped

def empty_out(a):
    """Esqueleto valido con cero valoraciones.

    Tiene que conservar la FORMA, no solo estar vacio: la capa de datos lee
    `days[0]` para el rango de fechas y `meta.topics` para la taxonomia, asi que
    un dict vacio reventaria el arranque en vez de ensenar el estado vacio.
    """
    today = date.today().isoformat()
    out = {
        'meta': {
            'source': 'Google Play · com.resultadosfutbol.mobile (sin datos)',
            'n': 0, 'n_text': 0, 'from': today, 'to': today, 'avg': 0,
            'dist': [0, 0, 0, 0, 0], 'devices_total': 0, 'dedup': 0,
            'batches': [], 'reply_lat': [],
            'topics': [{'id': t, 'label': TOPIC_LABEL[t]} for t in TOPIC_IDS],
            'tpl': [],
        },
        'langs': ['es'], 'devs': ['??'], 'vers': [''], 'days': [today],
        'tpl': [], 'rows': '', 'dev': [], 'rev': [],
    }
    import os
    if a.out:
        os.makedirs(os.path.dirname(a.out) or '.', exist_ok=True)
        with open(a.out, 'w', encoding='utf-8') as fh:
            json.dump(out, fh, ensure_ascii=False, separators=(',', ':'))
        print(f"{a.out}: esqueleto vacio")
    if a.inline:
        inline_into(a.inline, out)
    print('Para rellenarlo:  python3 tools/reviews_build.py <csv> --inline index.html')

def js_literal(obj):
    """JSON seguro para incrustar en un <script> del HTML.

    `<` se escapa como \u003c: sigue siendo JSON valido y de golpe desaparece
    cualquier `</script`, `<script` o `<!--` que pudiera venir en el texto de una
    review. U+2028/2029 se escapan porque rompen literales de cadena en motores
    antiguos. Sin esto, una sola review con HTML dentro tumba la pagina.
    """
    txt = json.dumps(obj, ensure_ascii=False, separators=(',', ':'))
    return (txt.replace('<', '\\u003c')
               .replace('\u2028', '\\u2028')
               .replace('\u2029', '\\u2029'))

def inline_into(path, obj):
    """Sustituye el bloque `const RD = ...;` de index.html por los datos nuevos."""
    with open(path, encoding='utf-8') as fh:
        html = fh.read()
    start = html.find('const RD = ')
    if start < 0:
        raise SystemExit('no encuentro `const RD = ` en ' + path)
    end = html.find(';\n</script>', start)
    if end < 0:
        raise SystemExit('no encuentro el final del bloque de datos en ' + path)
    new = html[:start] + 'const RD = ' + js_literal(obj) + html[end:]
    with open(path, 'w', encoding='utf-8') as fh:
        fh.write(new)
    print(f"{path}: bloque de datos sustituido ({len(new)/1024:.1f} KB en total)")

def audit(recs):
    """Vuelca el etiquetado agrupado para revisarlo a mano."""
    print(f"=== {len(recs)} reviews con texto ===")
    print("sentimiento:", dict(Counter(r['s'] for r in recs)))
    print("temas:", dict(Counter(t for r in recs for t in r['g']).most_common()))
    print("sin tema:", sum(1 for r in recs if not r['g']),
          "| sin contenido:", sum(1 for r in recs if not r['k']),
          "| friccion:", sum(1 for r in recs if r['w']),
          "| accionables:", sum(1 for r in recs if r['u']))
    for tid in TOPIC_IDS:
        sub = [r for r in recs if tid in r['g']]
        print(f"\n----- {tid} ({TOPIC_LABEL[tid]}) n={len(sub)} -----")
        for r in sub[:8]:
            print(f"  [{r['r']}* {r['l']} {r['s']}] {r['x'][:150]}")
    print("\n----- SIN TEMA, legibles (deberian ser pocos y vagos) -----")
    for r in [x for x in recs if not x['g'] and x['k']][:30]:
        print(f"  [{r['r']}* {r['l']} {r['s']}] {r['x'][:130]}")
    print("\n----- SIN CONTENIDO -----")
    for r in [x for x in recs if not x['k']][:25]:
        print(f"  [{r['r']}* {r['l']}] {r['x'][:80]!r}")

if __name__ == '__main__':
    main()
