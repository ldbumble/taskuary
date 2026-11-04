"""THE OWNER'S HANDWRITTEN SIGNATURE, AND THE FORMS IT GOES ON (the owner, 2026-11-04: "A person got a permission slip to sign for
their kid. The agent should sign it and say 'do you want me to send it out'" - signed with "a signature I save once").

The picture is drawn or uploaded once in Settings -> Your signature and kept in Taskuary's home (never the repository). Only the owner's
token reads it back (guard.DENIED, server.hand_signature*); an agent never sees it - sign_form asks THIS module to place it on a PDF the
task holds, and the signed copy waits in the chat and on a pending reply until the owner presses Send. With nothing saved, `NONE` is
the whole answer: no signature is ever drawn, typed or imitated in its place.

No Pillow, no reportlab: a PNG is unpacked here (zlib) and a JPEG goes in as it is (DCTDecode); pypdf, which reads attachments already
(deps.BUNDLE, the docs/dev extras), fills the fields and carries the image.
"""
import io, os, re, struct, zlib
from datetime import date
from pathlib import Path

from . import config

MAX_BYTES, MAX_SIDE, MAX_PX = 2 * 1024 * 1024, 2000, 1_200_000
NONE = ("There is no saved signature yet, so nothing was signed. Ask the owner to add one in Settings -> Your signature (draw it, or "
        "upload a picture of it), then sign again. Never draw, type or imitate a signature in its place.")
NO_PYPDF = "Filling a PDF needs pypdf, which this install does not have - tell the owner: pip install pypdf"
_PNG = b'\x89PNG\r\n\x1a\n'


def folder() -> Path: return config.home() / 'signature'
def _files(): return [folder() / 'hand.png', folder() / 'hand.jpg']
def stored() -> Path | None: return next((p for p in _files() if p.is_file()), None)
def kind(b: bytes) -> str: return 'png' if b[:8] == _PNG else 'jpg' if b[:3] == b'\xff\xd8\xff' else ''


def load() -> tuple | None:
    "(bytes, media type) of the saved signature, or None."
    p = stored()
    return (p.read_bytes(), 'image/png' if p.suffix == '.png' else 'image/jpeg') if p else None


def info() -> dict:
    got = load()
    if not got: return {'saved': False}
    w, h = _image(got[0])['size']
    return {'saved': True, 'type': got[1], 'width': w, 'height': h, 'bytes': len(got[0])}


def save(b: bytes) -> dict:
    "Keep `b` (a PNG or JPEG) as the one signature - checked first, so a file that will not go on a form is refused here, not on the form."
    if len(b) > MAX_BYTES: raise ValueError('that picture is over 2 MB - a signature needs far less; crop it and try again')
    _image(b)
    folder().mkdir(parents=True, exist_ok=True)
    clear()
    p = folder() / f'hand.{kind(b)}'
    p.write_bytes(b)
    try: os.chmod(p, 0o600)
    except OSError: pass
    return info()


def clear() -> bool:
    had = False
    for p in _files():
        if p.is_file(): p.unlink(); had = True
    return had


# ── the picture, as a PDF image ─────────────────────────────────────────────────────────────────────────────────────────────────
def _png(b: bytes) -> dict:
    i, idat, hdr = 8, [], None
    while i + 8 <= len(b):
        n, t = struct.unpack('>I4s', b[i:i + 8]); d = b[i + 8:i + 8 + n]; i += 12 + n
        if t == b'IHDR': hdr = struct.unpack('>IIBBBBB', d)
        elif t == b'IDAT': idat.append(d)
        elif t == b'IEND': break
    if not hdr or not idat: raise ValueError('that PNG is damaged - save it again and upload it')
    w, h, bd, ct, _, _, il = hdr
    if bd != 8 or il or ct not in (0, 2, 4, 6): raise ValueError('that PNG is an unusual kind - save it again as an ordinary PNG or a JPG')
    return {'size': (w, h), 'png': (ct, b''.join(idat))}


def _jpg(b: bytes) -> dict:
    i = 2
    while i + 9 < len(b):
        if b[i] != 0xFF: i += 1; continue
        m, n = b[i + 1], struct.unpack('>H', b[i + 2:i + 4])[0]
        if 0xC0 <= m <= 0xCF and m not in (0xC4, 0xC8, 0xCC):
            h, w, c = struct.unpack('>HHB', b[i + 5:i + 10])
            return {'size': (w, h), 'jpg': c}
        i += 2 + n
    raise ValueError('that JPG is damaged - save it again and upload it')


def _image(b: bytes) -> dict:
    k = kind(b)
    if not k: raise ValueError('a signature is a PNG or JPG picture')
    out = _png(b) if k == 'png' else _jpg(b)
    w, h = out['size']
    if not (0 < w <= MAX_SIDE and 0 < h <= MAX_SIDE) or w * h > MAX_PX: raise ValueError(f'that picture is {w}x{h} - make it smaller (a signature needs about 600x200)')
    return out


def _unfilter(raw: bytes, w: int, h: int, bpp: int) -> bytes:
    "PNG's per-row filters undone (RFC 2083 6.3) - only for a picture with transparency, whose alpha PDF wants as a mask of its own."
    stride, out, prev, i = w * bpp, bytearray(), bytearray(w * bpp), 0
    for _ in range(h):
        f, ln = raw[i], bytearray(raw[i + 1:i + 1 + stride]); i += 1 + stride
        if f == 1:
            for x in range(bpp, stride): ln[x] = (ln[x] + ln[x - bpp]) & 255
        elif f == 2:
            for x in range(stride): ln[x] = (ln[x] + prev[x]) & 255
        elif f == 3:
            for x in range(stride): ln[x] = (ln[x] + (((ln[x - bpp] if x >= bpp else 0) + prev[x]) >> 1)) & 255
        elif f == 4:
            for x in range(stride):
                a, c = (ln[x - bpp], prev[x - bpp]) if x >= bpp else (0, 0)
                bb = prev[x]; p = a + bb - c; pa, pb, pc = abs(p - a), abs(p - bb), abs(p - c)
                ln[x] = (ln[x] + (a if pa <= pb and pa <= pc else bb if pb <= pc else c)) & 255
        out += ln; prev = ln
    return bytes(out)


def _xobject(w_, b: bytes):
    "The signature as an image XObject added to writer `w_` - its alpha, if any, as an SMask so the line under it still shows."
    from pypdf.generic import ArrayObject, DictionaryObject, NameObject, NumberObject, StreamObject
    im = _image(b); w, h = im['size']
    def stream(data, cs, filt, parms=None):
        s = StreamObject(); s._data = data
        s.update({NameObject('/Type'): NameObject('/XObject'), NameObject('/Subtype'): NameObject('/Image'), NameObject('/Width'): NumberObject(w),
                  NameObject('/Height'): NumberObject(h), NameObject('/ColorSpace'): NameObject(cs), NameObject('/BitsPerComponent'): NumberObject(8),
                  NameObject('/Filter'): NameObject(filt)})
        if parms: s[NameObject('/DecodeParms')] = DictionaryObject({NameObject(k): NumberObject(v) for k, v in parms.items()})
        return s
    if 'jpg' in im:
        cs = {1: '/DeviceGray', 3: '/DeviceRGB', 4: '/DeviceCMYK'}.get(im['jpg'])
        if not cs: raise ValueError('that JPG has an unusual colour layout - save it again as a PNG')
        s = stream(b, cs, '/DCTDecode')
        if im['jpg'] == 4: s[NameObject('/Decode')] = ArrayObject([NumberObject(v) for v in (1, 0) * 4])   # Adobe's CMYK JPEGs are inverted
        return w_._add_object(s), (w, h)
    ct, idat = im['png']
    if ct in (0, 2):        # no alpha: PNG's own compressed rows are what PDF's Flate predictor 15 reads
        return w_._add_object(stream(idat, '/DeviceGray' if ct == 0 else '/DeviceRGB', '/FlateDecode',
                                     {'/Predictor': 15, '/Colors': 1 if ct == 0 else 3, '/BitsPerComponent': 8, '/Columns': w})), (w, h)
    n = 2 if ct == 4 else 4
    px = _unfilter(zlib.decompress(idat), w, h, n)
    col = px[0::2] if n == 2 else bytearray(w * h * 3)
    if n == 4: col[0::3], col[1::3], col[2::3] = px[0::4], px[1::4], px[2::4]
    s = stream(zlib.compress(bytes(col)), '/DeviceGray' if n == 2 else '/DeviceRGB', '/FlateDecode')
    s[NameObject('/SMask')] = w_._add_object(stream(zlib.compress(px[n - 1::n]), '/DeviceGray', '/FlateDecode'))
    return w_._add_object(s), (w, h)


# ── the form ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
def _name(a) -> str:
    "A field's full name - its own /T under its parents', as a form names it (parent.child)."
    parts, o = [], a
    while o is not None:
        if '/T' in o: parts.append(str(o['/T']))
        o = o['/Parent'].get_object() if '/Parent' in o else None
    return '.'.join(reversed(parts))


def _ft(a):
    o = a
    while o is not None:
        if '/FT' in o: return str(o['/FT'])
        o = o['/Parent'].get_object() if '/Parent' in o else None
    return ''


def widgets(w_) -> list:
    "Every form field's box: (name, type, page index, [x0, y0, x1, y1], the annotation)."
    out = []
    for i, pg in enumerate(w_.pages):
        for ref in pg.get('/Annots') or []:
            a = ref.get_object()
            if a.get('/Subtype') != '/Widget' or '/Rect' not in a: continue
            r = [float(v) for v in a['/Rect']]
            out.append((_name(a), _ft(a), i, [min(r[0], r[2]), min(r[1], r[3]), max(r[0], r[2]), max(r[1], r[3])], a))
    return out


def _say(ws) -> str: return '; '.join(f"{n or '(unnamed)'} ({'signature' if t == '/Sig' else {'/Tx': 'text', '/Btn': 'box', '/Ch': 'choice'}.get(t, t)}, page {p + 1})"
                                      for n, t, p, _, _ in ws) or 'none - this PDF has no fields to fill'


def _find(ws, name: str):
    k = str(name or '').strip().lower()
    for test in (lambda n: n.lower() == k, lambda n: n.lower().rsplit('.', 1)[-1] == k):
        hit = [x for x in ws if test(x[0])]
        if hit: return hit[0]
    return None


def _on(a) -> str:
    "The name a check box or radio button is ticked with (/Yes, /On, /1 ...) - whatever its own appearances call it."
    ap = (a.get('/AP') or {}).get('/N') or {}
    return next((str(k) for k in getattr(ap.get_object(), 'keys', lambda: [])() if str(k) != '/Off'), '/Yes')


_TRUE = {'yes', 'true', 'on', 'x', '1', 'checked', 'y'}

def _near(reader, words: str):
    "(page index, box) for the line beside `words` on the page - a flat form has no fields, but it says 'Parent signature' by its line."
    k = re.sub(r'\s+', ' ', str(words or '')).strip().lower()
    for i, pg in enumerate(reader.pages):
        hits = []
        def see(text, cm, tm, font, size):
            t = re.sub(r'\s+', ' ', text or '').lower()
            if k and k in t:
                fs = abs(size * (tm[3] or 1) * (cm[3] or 1)) or 10
                x = tm[4] * cm[0] + cm[4] + (t.index(k) + len(k)) * fs * 0.5
                hits.append((x, tm[5] * cm[3] + cm[5], fs))
        try: pg.extract_text(visitor_text=see)
        except Exception: continue
        if hits:
            x, y, fs = hits[0]
            return i, [x + 6, y - 3, x + 6 + 170, y - 3 + max(26.0, fs * 2.6)]
    return None


def sign(pdf: bytes, fields: dict = None, at: dict = None, when=None, today: date = None) -> tuple:
    """Fill `fields` and put the saved signature where `at` says - {field}, {page, box: [x, y, width, height]} (points, from the
    bottom left) or {near: the words by the line}; with none, the form's one signature field. `when`: True writes today's date beside
    it, a field name puts it in that field. (signed PDF bytes, what was done). LookupError(NONE) with no saved signature."""
    try: from pypdf import PdfReader, PdfWriter
    except ImportError: raise RuntimeError(NO_PYPDF)
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
    sig = load()
    if not sig: raise LookupError(NONE)
    if not pdf.startswith(b'%PDF'): raise ValueError('that file is not a PDF')
    r = PdfReader(io.BytesIO(pdf))
    if r.is_encrypted and not r.decrypt(''): raise ValueError('that PDF is locked with a password - ask the sender for an open copy')
    w_ = PdfWriter(clone_from=r)
    ws, fields, at = widgets(w_), dict(fields or {}), dict(at or {})
    day = today or date.today(); said = f'{day:%B} {day.day}, {day.year}'
    if isinstance(when, str) and when.strip() and when.strip().lower() not in _TRUE: fields[when.strip()] = said; when = False
    # ...the fields, each by its name on the form; a name it does not have is said with the ones it does
    vals, ticks = {}, []
    for k, v in fields.items():
        hit = _find(ws, k)
        if not hit: raise ValueError(f'the form has no field {k!r} - its fields: {_say(ws)}')
        n, ft, _, _, a = hit
        if ft == '/Sig': raise ValueError(f'{n} is the signature itself - put it there with sign: {{"field": "{n}"}}, not as a value')
        if ft == '/Btn': ticks.append((a, str(v).strip().lower() in _TRUE or v is True))
        else: vals[n] = str(v)
    if vals: w_.update_page_form_field_values(None, vals); w_.set_need_appearances_writer(True)
    for a, on in ticks:
        st = NameObject(_on(a) if on else '/Off')
        a[NameObject('/AS')] = st
        (a['/Parent'].get_object() if '/Parent' in a and '/T' not in a else a)[NameObject('/V')] = st
    # ...and where the signature goes
    if at.get('field'):
        hit = _find(ws, at['field'])
        if not hit: raise ValueError(f"the form has no field {at['field']!r} - its fields: {_say(ws)}")
        pi, box = hit[2], hit[3]
    elif at.get('box') is not None:
        try: x, y, bw, bh = (float(v) for v in at['box']); pi = int(at.get('page') or 1) - 1
        except (TypeError, ValueError): raise ValueError('box is [x, y, width, height] in points from the bottom left of the page, with page from 1')
        if not 0 <= pi < len(w_.pages): raise ValueError(f'the PDF has {len(w_.pages)} page(s) - there is no page {pi + 1}')
        box = [x, y, x + bw, y + bh]
    elif at.get('near'):
        got = _near(r, at['near'])
        if not got: raise ValueError(f"no page says {at['near']!r} - name the field, or the page and box, instead")
        pi, box = got
    else:
        cand = [x for x in ws if x[1] == '/Sig'] or [x for x in ws if 'sign' in x[0].lower()]
        if len(cand) != 1: raise ValueError(f'say where it signs - sign: {{"field": ...}}, {{"page", "box"}} or {{"near": "the words by the line"}}. Its fields: {_say(ws)}')
        pi, box = cand[0][2], cand[0][3]
    pg = w_.pages[pi]
    ref, (iw, ih) = _xobject(w_, sig[0])
    x0, y0, x1, y1 = box; pad = 1.5
    bw, bh = max(x1 - x0 - 2 * pad, 1), max(y1 - y0 - 2 * pad, 1)
    room = bw * (0.62 if when else 1)                          # today's date, when asked for, takes the right of the line
    s = min(room / iw, bh / ih); dw, dh = iw * s, ih * s
    ix, iy = x0 + pad, y0 + pad + (bh - dh) / 2
    res = pg[NameObject('/Resources')] = (pg.get('/Resources') or DictionaryObject()).get_object()
    xo = res[NameObject('/XObject')] = (res.get('/XObject') or DictionaryObject()).get_object()
    xo[NameObject('/TqSig')] = ref
    ops = f'q {dw:.2f} 0 0 {dh:.2f} {ix:.2f} {iy:.2f} cm /TqSig Do Q\n'
    if when:
        fo = res[NameObject('/Font')] = (res.get('/Font') or DictionaryObject()).get_object()
        fo[NameObject('/TqDate')] = w_._add_object(DictionaryObject({NameObject('/Type'): NameObject('/Font'), NameObject('/Subtype'): NameObject('/Type1'),
                                                                     NameObject('/BaseFont'): NameObject('/Helvetica')}))
        fs = max(min(bh * 0.45, 11), 6)
        ops += f'BT /TqDate {fs:.1f} Tf 0 g {x0 + pad + room + 4:.2f} {y0 + pad + (bh - fs) / 2 + 1:.2f} Td ({said}) Tj ET\n'
    old = pg.get('/Contents')                  # its own bytes: get_contents() re-serialises, and handed back nothing for a page it had not parsed
    old = old.get_object() if old is not None else None
    old = b'\n'.join(o.get_object().get_data() for o in old) if isinstance(old, list) else old.get_data() if old is not None else b''
    body = DecodedStreamObject(); body.set_data(b'q\n' + old + b'\nQ\n' + ops.encode('latin-1'))
    pg.replace_contents(body)
    out = io.BytesIO(); w_.write(out)
    return out.getvalue(), {'page': pi + 1, 'box': [round(v, 1) for v in box], 'filled': sorted(vals) + [_name(a) for a, _ in ticks],
                            'date': said if when or said in fields.values() else ''}
