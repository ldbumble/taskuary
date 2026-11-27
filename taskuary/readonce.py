"""ONE READ OF A FACT FOR A WHOLE PAGE READ. The rail's build cards every row, and some facts each card asks are the same for every row:
the owner's own addresses, the profiles, the accounts' tags, the mailboxes (0.4.6.11: "all read, next is slower" - each was read again
per row, the addresses copying every connection card each time). `with readonce.once():` keeps each `kept` fact for everything inside;
outside one, `kept` reads afresh as before. Read-only work only, as config.once: a write inside would be shadowed by what was kept."""
import contextvars

_ONCE = contextvars.ContextVar('taskuary_read_once', default=None)


class once:
    def __enter__(self): self.tok = _ONCE.set({} if _ONCE.get() is None else _ONCE.get()); return self
    def __exit__(self, *a): _ONCE.reset(self.tok)


def kept(key, make):
    "make(), once per `once` block - every time outside one."
    if (m := _ONCE.get()) is None: return make()
    if key not in m: m[key] = make()
    return m[key]
