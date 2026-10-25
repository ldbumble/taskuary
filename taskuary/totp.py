"""AUTHENTICATOR CODES for a saved sign-in (the owner, 2026-10-25: "Yes: TOTP codes in the sign-in vault").

A site that asks for a six-digit code after the password stopped a browser job cold: the owner had to be at the pane with their
phone. The owner can now keep the site's authenticator key (the base32 text a site shows beside its QR code, or the whole
otpauth:// link the QR code holds) with the saved sign-in, sealed like the password, and the server types the code itself.

RFC 6238 (TOTP) over RFC 4226 (HOTP), written here with hmac and hashlib - forty lines did not need a dependency, and a library
that reads the key is one more place it travels through. Tested against the RFC's own vectors (tests/test_totp.py).
"""
import base64, hashlib, hmac, json, re, struct, time
from urllib.parse import parse_qs, unquote, urlsplit

ALGOS = {'SHA1': hashlib.sha1, 'SHA256': hashlib.sha256, 'SHA512': hashlib.sha512}
class BadKey(ValueError): "What the owner pasted is not a key a code can be made from - said on the page they pasted it into."


def _b32(s: str) -> str:
    "A key as the base32 the RFC means: upper case, no spaces or dashes (the way sites print it), padded - or BadKey."
    k = re.sub(r'[\s-]+', '', str(s or '')).upper().rstrip('=')
    if not k or not re.fullmatch(r'[A-Z2-7]+', k): raise BadKey('that is not an authenticator key - it is the base32 text beside the QR code')
    k += '=' * (-len(k) % 8)
    try: raw = base64.b32decode(k)
    except Exception: raise BadKey('that authenticator key does not decode')
    # under 80 bits is no key a real site issues (RFC 4226 asks 128, says 160): a typo'd half key would type wrong codes for ever
    if len(raw) < 10: raise BadKey('that authenticator key is too short - copy all of it')
    return k


def parse(text) -> dict:
    """{secret, digits, period, algorithm} from what the owner pasted: a bare key, or an otpauth://totp/ link. Anything else -
    an HOTP counter link, an unknown hash, a code length no site uses - is BadKey, never a guess that types wrong codes."""
    t = str(text or '').strip()
    if not t.lower().startswith('otpauth:'): return {'secret': _b32(t), 'digits': 6, 'period': 30, 'algorithm': 'SHA1'}
    u = urlsplit(t)
    if u.netloc.lower() != 'totp': raise BadKey('only a time-based (totp) authenticator link can be kept')
    q = {k.lower(): v[0] for k, v in parse_qs(u.query).items()}
    algo, digits, period = q.get('algorithm', 'SHA1').upper(), q.get('digits', '6'), q.get('period', '30')
    if algo not in ALGOS: raise BadKey(f'that authenticator link uses {algo}, which no authenticator app types')
    if digits not in ('6', '7', '8') or not period.isdigit() or not 10 <= int(period) <= 300:
        raise BadKey('that authenticator link asks for a code length or period no site uses')
    return {'secret': _b32(unquote(q.get('secret', ''))), 'digits': int(digits), 'period': int(period), 'algorithm': algo}


def dumps(cfg: dict) -> str: return json.dumps(cfg, separators=(',', ':'), sort_keys=True)
def loads(s: str) -> dict:
    "A kept key back from the vault, checked again: a row edited by hand must not type codes from a key nobody validated."
    d = json.loads(s)
    if d.get('algorithm') not in ALGOS or d.get('digits') not in (6, 7, 8) or not 10 <= int(d.get('period') or 0) <= 300: raise BadKey('the kept key is damaged')
    return {**d, 'secret': _b32(d['secret'])}


def hotp(key: bytes, counter: int, digits: int = 6, algorithm: str = 'SHA1') -> str:
    "RFC 4226 5.3: HMAC the 8-byte counter, take 31 bits at the offset the last nibble names, keep the low `digits` of it."
    h = hmac.new(key, struct.pack('>Q', counter), ALGOS[algorithm]).digest()
    o = h[-1] & 0x0F
    return str((struct.unpack('>I', h[o:o + 4])[0] & 0x7FFFFFFF) % 10 ** digits).zfill(digits)


def code(cfg: dict, at: float = None) -> str:
    "The code an authenticator app shows at `at` (now): RFC 6238's T = floor(unix time / period)."
    t = time.time() if at is None else at
    return hotp(base64.b32decode(cfg['secret']), int(t // cfg['period']), cfg['digits'], cfg['algorithm'])


def left(cfg: dict, at: float = None) -> float:
    "Seconds before this code turns over - a code typed in its last breath arrives as the next one's."
    t = time.time() if at is None else at
    return cfg['period'] - (t % cfg['period'])
