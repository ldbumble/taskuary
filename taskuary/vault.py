"""Connector secrets, sealed by the operating system instead of sitting in the database as text.

The `connector.Secret` column held every password, API key and token in plain text, so a copy of
taskuary.db - a backup, a snapshot taken to replay against, a file an agent went looking for - was
a copy of every credential (guard.py said so: "real credential isolation needs the secrets out of
the database and behind the OS keychain ... that is not built").

What is built now, and what it is not:
- Windows: the secret is sealed with DPAPI (CryptProtectData) under this Windows user. The column
  holds `vault:dpapi:<base64>`, which nobody can open on another machine or as another user.
- macOS / Linux: the secret goes to the system keychain through the `keyring` package when it is
  installed and has a real backend; the column holds `vault:keyring:<id>`.
- Anywhere else it stays as it was, plain - a missing keychain must not cost the owner a connection.
- NOT a wall against a program running as the same user: DPAPI and the keychain both open for it.
  What it stops is the FILE carrying the keys.

`seal` and `unseal` are the only doors; store.py calls them on save and on a with_secret read.
"""
import base64, os, sys, uuid
from loguru import logger

PREFIX, SERVICE = 'vault:', 'taskuary'
_ENTROPY = b'taskuary connector secret'


def _dpapi(data: bytes, protect: bool) -> bytes:
    import ctypes
    from ctypes import wintypes
    class BLOB(ctypes.Structure): _fields_ = [('cbData', wintypes.DWORD), ('pbData', ctypes.POINTER(ctypes.c_char))]
    def blob(b): buf = ctypes.create_string_buffer(b, len(b)); return BLOB(len(b), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char))), buf
    (src, k1), (ent, k2), out = blob(data), blob(_ENTROPY), BLOB()
    fn = ctypes.windll.crypt32.CryptProtectData if protect else ctypes.windll.crypt32.CryptUnprotectData
    # CRYPTPROTECT_UI_FORBIDDEN: never a prompt - a server has nobody to answer it
    if not fn(ctypes.byref(src), None, ctypes.byref(ent), None, None, 0x1, ctypes.byref(out)): raise ctypes.WinError()
    try: return ctypes.string_at(out.pbData, out.cbData)
    finally: ctypes.windll.kernel32.LocalFree(out.pbData)


def _keyring():
    """The keyring module when it has a backend that actually stores something, else None."""
    try:
        import keyring
        from keyring.backends import fail
        return None if isinstance(keyring.get_keyring(), fail.Keyring) else keyring
    except Exception: return None


def mode() -> str:
    """Where a new secret goes: 'dpapi', 'keyring' or 'plain'. TASKUARY_VAULT=plain turns sealing off."""
    if os.environ.get('TASKUARY_VAULT') == 'plain': return 'plain'
    if sys.platform == 'win32': return 'dpapi'
    return 'keyring' if _keyring() else 'plain'


def sealed(v) -> bool: return isinstance(v, str) and v.startswith(PREFIX)


def seal(plain):
    """The value to store for a secret. Empty, None and an already sealed value pass through."""
    if not plain or sealed(plain): return plain
    m = mode()
    try:
        if m == 'dpapi': return f'{PREFIX}dpapi:' + base64.b64encode(_dpapi(plain.encode('utf-8'), True)).decode('ascii')
        if m == 'keyring':
            kid = uuid.uuid4().hex
            _keyring().set_password(SERVICE, kid, plain)
            return f'{PREFIX}keyring:{kid}'
    except Exception as e: logger.warning(f'vault: could not seal a secret ({e}) - it is stored as before')
    return plain


def unseal(stored):
    """The secret itself. A value that cannot be opened (another machine, another user, a keychain
    entry deleted) comes back '' - the connection then fails its sign-in and says so, instead of
    sending ciphertext as a password."""
    if not sealed(stored): return stored
    kind, _, body = stored[len(PREFIX):].partition(':')
    try:
        if kind == 'dpapi': return _dpapi(base64.b64decode(body), False).decode('utf-8')
        if kind == 'keyring': return (_keyring() or _missing()).get_password(SERVICE, body) or ''
    except Exception as e: logger.warning(f'vault: a sealed secret could not be opened here ({e}) - reconnect that connection')
    return ''


def forget(stored):
    """A keychain entry goes with its connection (Remove connection); a DPAPI value is just a column."""
    if sealed(stored) and stored.startswith(f'{PREFIX}keyring:'):
        try: (_keyring() or _missing()).delete_password(SERVICE, stored.split(':', 2)[2])
        except Exception as e: logger.debug(f'vault: nothing to forget ({e})')


def _missing(): raise RuntimeError('the keyring package is not available on this install')
