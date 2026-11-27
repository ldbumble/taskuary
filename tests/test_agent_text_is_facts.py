"""WHAT AN AGENT IS TOLD IS FACTS, NEVER ITS LINES (the owner, 2026-11-23 and 2026-11-27: "code should never tell an agent what to do"). An agent
gets context, tools and one sentence; a sentence the code scripts for it to say ("say so in one line: ...", "never call it ...") is the
code doing its job. This guards only that shape, over every registry an agent reads from: each tool's description and short line, each
guide, and every named prompt constant in the package. It names no string of today's - a new scripted line anywhere fails it."""
import ast, re
from pathlib import Path
from taskuary import agenttools, apiagent, guides

PKG = Path(agenttools.__file__).parent
SCRIPTED = re.compile('|'.join([
    r'\bsay (?:so|it|that|why)?\s*in one (?:plain |short )?line',            # "say so in one line"
    r'\b(?:tell|say to) (?:the owner|him|them)\b[^.]{0,40}\bin one (?:plain )?line',
    r'\bnever call it\b', r'\byou must say\b', r'\bas if for the first time\b',
    r'\bnever (?:say|tell (?:the owner|him|them))\b', r'\bdo not (?:say|mention)\b',
    r'\b(?:say|tell (?:the owner|him|them))\s*:?\s*"[A-Z][^"]{8,}"',         # a quoted sentence it must say
]), re.I)


def _consts():
    "(where, text) of every module-level UPPERCASE string constant in the package - the named prompt lines."
    for f in sorted(PKG.glob('*.py')):
        for n in ast.parse(f.read_text(encoding='utf-8')).body:
            # ...not the words a constant keeps only to recognise what older installs were told (OLD_PROMPTS, _SUMMARY_WAS)
            if isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name) and n.targets[0].id.isupper() \
                    and not re.search(r'(^_?OLD_|_WAS$)', n.targets[0].id):
                v = n.value
                parts = [v.value] if isinstance(v, ast.Constant) and isinstance(v.value, str) else \
                        [c.value for c in ast.walk(v) if isinstance(c, ast.Constant) and isinstance(c.value, str)]
                if parts: yield f'{f.name}:{n.lineno} {n.targets[0].id}', ' '.join(parts)


def _described(o, where):
    if isinstance(o, dict):
        if isinstance(o.get('description'), str): yield where, o['description']
        for k, x in o.items(): yield from _described(x, f'{where}.{k}')
    elif isinstance(o, (list, tuple)):
        for x in o: yield from _described(x, where)


def _registries():
    for n, (_, d, s, _door) in agenttools.TOOLS.items(): yield f'tool {n}', d; yield from _described(s, f'tool {n}')
    for n, d in agenttools.SHORT.items(): yield f'short {n}', d
    for n, d in {**apiagent.SHORT, **apiagent.FULL}.items(): yield f'api {n}', d
    for t in guides.GUIDES: yield f'guide {t}', guides.read(t)


def test_nothing_an_agent_reads_scripts_what_it_says():
    bad = [f'{w}: ...{t[max(0, m.start() - 60):m.end() + 40]}...' for w, t in [*_registries(), *_consts()] if (m := SCRIPTED.search(t))]
    assert not bad, 'scripted speech in what an agent is told - say the fact, not its words:\n' + '\n'.join(bad)


def test_the_guard_sees_the_shape():
    for said in ('If so, say so in one line.', 'Never call it "unavailable".', 'tell the owner in one line what you did',
                 'say: "I did not read your earlier mail because of it."', 'and do not mention it.'):
        assert SCRIPTED.search(said), said
    for fact in ('The draft is put down - kept under Not sent.', 'his answer comes to you.', '`why`: one line on what changed.'):
        assert not SCRIPTED.search(fact), fact
