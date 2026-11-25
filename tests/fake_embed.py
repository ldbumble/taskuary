"""A stand-in embedder for tests: no server, no model. Each text lands on the axis of the first JOB it is declared to be about -
`jobs` maps a job to the marker phrases a test's own invented texts carry - and a text about none of them on an axis of its own, so
it is alike to nothing. What the code under test reads is only the similarity, exactly as it reads a real embedder's."""
import itertools
from contextlib import contextmanager
from unittest import mock

from taskuary import kbembed, textsim

_n = itertools.count()


def embedder(jobs: dict, dim: int = 256):
    axes = {j: i for i, j in enumerate(jobs)}
    seen = {}

    def embed(texts):
        out = []
        for t in texts:
            low = str(t).lower()
            j = next((j for j, marks in jobs.items() if any(m.lower() in low for m in marks)), None)
            i = axes[j] if j is not None else seen.setdefault(low, len(axes) + len(seen)) % dim
            v = [0.0] * dim; v[i] = 1.0
            out.append(kbembed.pack(v))
        embed.calls.append(list(texts))
        return out
    embed.model, embed.calls = f'fake-{next(_n)}', []
    return embed


@contextmanager
def meaning(jobs: dict):
    """textsim reads this embedder while the block runs."""
    e = embedder(jobs)
    with mock.patch.object(textsim, 'embedder', lambda store: e): yield e


@contextmanager
def no_embedder():
    with mock.patch.object(textsim, 'embedder', lambda store: None): yield


def reader(jobs: dict, calls: list = None):
    """A stand-in for the light model textsim.pick asks where no embedder runs: it reads THE TASK, finds the job it is about (as
    `embedder` does) and picks every listed id whose line is about that job - what a model reading the titles would answer."""
    import json, re
    def job_of(t): return next((j for j, marks in jobs.items() if any(m.lower() in str(t).lower() for m in marks)), None)
    def brain(system, user, **kw):
        if calls is not None: calls.append(user)
        lists, _, task = user.rpartition('\n\nTHE TASK:\n')
        j = job_of(task)
        ids = [m.group(1) for m in re.finditer(r'(?m)^([A-Z]+\d+)\. (.*)$', lists) if j and job_of(m.group(2)) == j]
        return json.dumps({'picks': ids})
    return brain


@contextmanager
def reads(jobs: dict, calls: list = None):
    """No embedder, and the light model is `reader`: the road most computers take."""
    from taskuary import llm
    with mock.patch.object(textsim, 'embedder', lambda store: None), mock.patch.object(llm, 'build_llm', lambda *a, **k: reader(jobs, calls)): yield
