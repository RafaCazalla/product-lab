#!/usr/bin/env python3
"""Incrusta el logo de BeSoccer en index.html como data URI.

    python3 tools/embed_logo.py "besoccer_hor_monocolor_w (4).png" --inline index.html

Por qué existe en vez de un <img src="fichero.png">: la página tiene que seguir
abriéndose con `open index.html` y publicándose como un Artifact de un solo
fichero, donde las imágenes externas están bloqueadas por CSP. Un data URI
cumple las dos cosas.

Qué hace, y por qué cada paso:

1. Recorta al trazo. El original trae 3000x800 con ~120 px de margen
   transparente por lado; ese margen se comería la altura útil en la barra.
2. Reescala con filtro de caja a la altura pedida (por defecto 3x de los 22 px
   de CSS, para que quede nítido en pantallas de densidad 3).
3. Reencoda como PNG **gris + alfa**. El logo monocolor tiene un único color de
   trazo (blanco puro), así que los tres canales RGB son constantes y sobran:
   se guarda un canal de gris fijo y el alfa, que es lo único que lleva forma.
   De 56 KB a menos de 4.

Sin dependencias: decodifica y escribe el PNG con `zlib` de la biblioteca
estándar. Solo acepta PNG de 8 bits sin entrelazar (RGBA, RGB, gris o gris+alfa).
"""
import argparse, base64, re, struct, sys, zlib

MARK = 'id="logo"'


def unfilter(raw, w, h, bpp):
    """Deshace los filtros por fila del PNG. Devuelve los píxeles en crudo."""
    stride = w * bpp
    out = bytearray()
    prev = bytearray(stride)
    pos = 0
    for _ in range(h):
        f = raw[pos]; pos += 1
        line = bytearray(raw[pos:pos + stride]); pos += stride
        if f == 1:
            for x in range(bpp, stride):
                line[x] = (line[x] + line[x - bpp]) & 255
        elif f == 2:
            for x in range(stride):
                line[x] = (line[x] + prev[x]) & 255
        elif f == 3:
            for x in range(stride):
                a = line[x - bpp] if x >= bpp else 0
                line[x] = (line[x] + ((a + prev[x]) >> 1)) & 255
        elif f == 4:
            for x in range(stride):
                a = line[x - bpp] if x >= bpp else 0
                b = prev[x]
                c = prev[x - bpp] if x >= bpp else 0
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                line[x] = (line[x] + pr) & 255
        elif f != 0:
            raise SystemExit('filtro PNG desconocido: %d' % f)
        out += line
        prev = line
    return out


def read_png(path):
    """-> (ancho, alto, alfa) con el alfa como bytearray de w*h."""
    d = open(path, 'rb').read()
    if d[:8] != b'\x89PNG\r\n\x1a\n':
        raise SystemExit('no es un PNG: ' + path)
    i, idat, ihdr = 8, b'', None
    while i < len(d):
        ln = struct.unpack('>I', d[i:i + 4])[0]
        typ = d[i + 4:i + 8]
        if typ == b'IHDR':
            ihdr = struct.unpack('>IIBBBBB', d[i + 8:i + 21])
        elif typ == b'IDAT':
            idat += d[i + 8:i + 8 + ln]
        i += 12 + ln
    w, h, depth, ctype, _, _, inter = ihdr
    if depth != 8 or inter:
        raise SystemExit('solo PNG de 8 bits sin entrelazar (esto es depth=%d inter=%d)' % (depth, inter))
    bpp = {0: 1, 2: 3, 4: 2, 6: 4}.get(ctype)
    if bpp is None:
        raise SystemExit('colortype %d no soportado (se admiten 0, 2, 4 y 6)' % ctype)
    px = unfilter(zlib.decompress(idat), w, h, bpp)
    alpha = bytearray(w * h)
    if ctype in (0, 2):                     # sin canal alfa: todo opaco
        for k in range(w * h):
            alpha[k] = 255
    else:
        off = bpp - 1                       # el alfa es el último canal
        for k in range(w * h):
            alpha[k] = px[k * bpp + off]
    return w, h, alpha


def ink_box(w, h, alpha, thr=8):
    """Rectángulo con trazo visible. El umbral evita que un alfa residual de
    compresión cuente como tinta y deje márgenes fantasma."""
    x0, y0, x1, y1 = w, h, -1, -1
    for y in range(h):
        row = y * w
        for x in range(w):
            if alpha[row + x] > thr:
                if x < x0: x0 = x
                if x > x1: x1 = x
                if y < y0: y0 = y
                if y > y1: y1 = y
    if x1 < 0:
        raise SystemExit('la imagen está entera transparente')
    return x0, y0, x1, y1


def box_resize(w, alpha, box, th):
    """Reescala el alfa a `th` de alto con filtro de caja (media por celda).
    Un muestreo por vecino más cercano dejaría el trazo con dientes a 22 px."""
    x0, y0, x1, y1 = box
    cw, ch = x1 - x0 + 1, y1 - y0 + 1
    tw = round(cw * th / ch)
    out = bytearray(tw * th)
    for ty in range(th):
        sy0, sy1 = y0 + ty * ch // th, y0 + (ty + 1) * ch // th
        if sy1 <= sy0: sy1 = sy0 + 1
        for tx in range(tw):
            sx0, sx1 = x0 + tx * cw // tw, x0 + (tx + 1) * cw // tw
            if sx1 <= sx0: sx1 = sx0 + 1
            s = n = 0
            for yy in range(sy0, sy1):
                base = yy * w
                for xx in range(sx0, sx1):
                    s += alpha[base + xx]; n += 1
            out[ty * tw + tx] = (s + n // 2) // n
    return tw, th, out


def write_gray_alpha(tw, th, alpha, gray=255):
    """PNG colortype 4 (gris + alfa). El gris es constante, así que zlib lo
    aplasta y el peso se lo lleva solo la forma."""
    def chunk(typ, data):
        return (struct.pack('>I', len(data)) + typ + data
                + struct.pack('>I', zlib.crc32(typ + data) & 0xffffffff))
    rows = bytearray()
    for ty in range(th):
        rows.append(0)                      # filtro 0: la fila alterna gris/alfa
        for tx in range(tw):
            rows.append(gray)
            rows.append(alpha[ty * tw + tx])
    return (b'\x89PNG\r\n\x1a\n'
            + chunk(b'IHDR', struct.pack('>IIBBBBB', tw, th, 8, 4, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(bytes(rows), 9))
            + chunk(b'IEND', b''))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('png', help='logo de origen (PNG de 8 bits)')
    ap.add_argument('--height', type=int, default=66,
                    help='alto en píxeles del asset; 3x de los 22 px de CSS (por defecto 66)')
    ap.add_argument('--inline', metavar='INDEX_HTML',
                    help='sustituye el src y las dimensiones del <img id="logo"> de ese fichero')
    a = ap.parse_args()

    w, h, alpha = read_png(a.png)
    box = ink_box(w, h, alpha)
    tw, th, small = box_resize(w, alpha, box, a.height)
    png = write_gray_alpha(tw, th, small)
    b64 = base64.b64encode(png).decode('ascii')
    src = 'data:image/png;base64,' + b64
    print('%s: %dx%d, trazo en %dx%d -> %dx%d · %d bytes (%.1f KB en base64)'
          % (a.png, w, h, box[2] - box[0] + 1, box[3] - box[1] + 1, tw, th,
             len(png), len(b64) / 1024))

    if not a.inline:
        return
    html = open(a.inline, encoding='utf-8').read()
    if MARK not in html:
        raise SystemExit('no encuentro un <img %s> en %s' % (MARK, a.inline))
    def sub(m):
        tag = m.group(0)
        tag = re.sub(r'src="[^"]*"', 'src="%s"' % src, tag)
        tag = re.sub(r'width="\d+"', 'width="%d"' % tw, tag)
        tag = re.sub(r'height="\d+"', 'height="%d"' % th, tag)
        return tag
    new, n = re.subn(r'<img[^>]*' + MARK + r'[^>]*>', sub, html)
    if n != 1:
        raise SystemExit('esperaba una etiqueta y he encontrado %d' % n)
    open(a.inline, 'w', encoding='utf-8').write(new)
    print('%s: logo incrustado (%.1f KB en total)' % (a.inline, len(new.encode()) / 1024))


if __name__ == '__main__':
    main()
