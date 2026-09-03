"""An adaptive, seven-turn interview that writes SOUL.md.

The interview behavior lives in ``skills/soul-interview/SKILL.md`` rather than in seven
hardcoded, IT-shaped questions. The application gives that skill the accumulated transcript
after every answer, so each next question can follow the person instead of a form.
"""
import json
import re
from datetime import datetime
from pathlib import Path

TOTAL_QUESTIONS = 7
SKILL_FILE = Path(__file__).parent / 'skills' / 'soul-interview' / 'SKILL.md'

# Accept the old request shape while installed clients move to the adaptive UI. This is not the
# new interview: these labels only make an already-submitted legacy form intelligible to draft().
_LEGACY_LABELS = {
    'who': 'Who are you, and what is your work?',
    'work': 'What kind of work reaches you?',
    'task': 'What may the assistant handle without asking?',
    'never': 'What must never happen without you?',
    'people': 'Which people and relationships matter?',
    'systems': 'Which systems or sources of truth matter?',
    'voice': 'How should communication sound?',
}


def skill_text() -> str:
    """The portable interview contract used for both questioning and writing."""
    return SKILL_FILE.read_text(encoding='utf-8')


def context(store) -> dict:
    """Facts the app already knows; the assistant should build on them rather than re-ask."""
    from .store import roles_of
    conns = [c for c in store.list_connectors() if c['Active']]
    repos = [s['Address'] for s in store.list_sources() if s.get('Channel') == 'github']
    who = store.get_settings().get('owner') or ''
    people = [f"{p['Name'] or p['Email']} ({p['N']} messages)" for p in store.people(8)]
    return {'owner': who, 'channels': sorted({c['Type'] for c in conns}), 'repos': repos[:12],
            'writes_most': people, 'roles': sorted({r for c in conns for r in roles_of(c)})}


def _known(ctx: dict) -> str:
    bits = [f"Owner name on file: {ctx['owner'] or '(not set)'}",
            f"Connected sources: {', '.join(ctx['channels']) or 'none yet'}",
            f"Known repositories (mention only if relevant): {', '.join(ctx['repos']) or 'none'}",
            f"Frequent correspondents: {'; '.join(ctx['writes_most']) or 'nothing ingested yet'}"]
    return 'WHAT TASKUARY ALREADY KNOWS (facts; do not contradict them):\n' + '\n'.join(bits)


def _answers(value) -> list[dict]:
    """Normalize adaptive transcripts and the previous seven-field request shape."""
    if isinstance(value, list):
        out = []
        for item in value[:TOTAL_QUESTIONS]:
            if not isinstance(item, dict): continue
            question = str(item.get('q') or item.get('question') or '').strip()
            if not question: continue
            out.append({'q': question[:500], 'a': str(item.get('a') or item.get('answer') or '').strip()[:4000]})
        return out
    if isinstance(value, dict):
        return [{'q': label, 'a': str(value.get(key) or '').strip()[:4000]}
                for key, label in _LEGACY_LABELS.items() if key in value]
    return []


def _transcript(answers: list[dict]) -> str:
    if not answers: return '(No questions have been asked yet.)'
    return '\n\n'.join(f"QUESTION {i}: {row['q']}\nANSWER {i}: {row['a'] or '(skipped)'}"
                       for i, row in enumerate(answers, 1))


def _brain(store, llm):
    if llm is not None: return llm
    from .llm import build_llm
    return build_llm(store)


def _json_object(raw: str) -> dict:
    text = str(raw or '').strip().removeprefix('```json').removeprefix('```').removesuffix('```').strip()
    try: return json.loads(text)
    except (TypeError, ValueError):
        match = re.search(r'\{.*\}', text, re.S)
        if not match: raise ValueError('The assistant did not return a question. Try again.')
        try: return json.loads(match.group(0))
        except (TypeError, ValueError) as exc:
            raise ValueError('The assistant returned an unreadable question. Try again.') from exc


def next_question(store, answers, llm=None) -> dict:
    """Generate exactly one next question from everything already said."""
    prior = _answers(answers)
    if len(prior) >= TOTAL_QUESTIONS: raise ValueError('All seven questions have already been asked.')
    brain = _brain(store, llm)
    if not brain:
        raise ValueError('Set up an AI assistant first so the interview can adapt to your answers.')
    number = len(prior) + 1
    prompt = (f"MODE: NEXT_QUESTION\nQUESTION NUMBER: {number} OF {TOTAL_QUESTIONS}\n\n"
              f"{_known(context(store))}\n\nINTERVIEW SO FAR:\n{_transcript(prior)}\n\n"
              "Return the single next question as the JSON object required by the skill. Do not write SOUL.md yet.")
    data = _json_object(brain(skill_text(), prompt, max_tokens=350))
    question = str(data.get('q') or '').strip()
    if not question: raise ValueError('The assistant did not return a question. Try again.')
    if '?' not in question: question = question.rstrip('.') + '?'
    return {'number': number, 'total': TOTAL_QUESTIONS, 'q': question[:500],
            'why': str(data.get('why') or 'This fills in an important part of how the assistant should work for you.').strip()[:500],
            'placeholder': str(data.get('placeholder') or '').strip()[:500]}


def _plain(answers: dict, ctx: dict) -> str:
    """Compatibility fallback for the old fixed form when no AI connector exists."""
    a = lambda k: str(answers.get(k) or '').strip()
    owner = a('who') or ctx.get('owner') or 'the owner'
    lines = ["# SOUL.md - the operator's document", '',
             f"You work for **{owner}**. You are the funnel between everything inbound and their "
             f"attention. **Nothing sends or ships without {owner.split(',')[0]}'s approval.**", '',
             '## What counts as a task', f"- {a('task') or 'A concrete request to do something.'}",
             (f"- What reaches this person: {a('work')}" if a('work') else None), '',
             '## How we respond', f"- {a('voice') or 'Plain, brief, and warm-professional.'}", '',
             '## Escalate (a human decides) when',
             f"- {a('never') or 'The boundary has not yet been specified; ask before acting.'}", '',
             '## Systems and repositories', f"- {a('systems') or ', '.join(ctx.get('repos') or []) or '(not specified)'}", '',
             '## People', f"- {a('people') or '(not specified)'}", '',
             f"<!-- written from the setup interview, {datetime.now().strftime('%Y-%m-%d')} -->"]
    return '\n'.join(line for line in lines if line is not None)


def draft(store, answers, llm=None) -> str:
    """Write SOUL.md from an adaptive transcript (or a legacy form submission)."""
    transcript = _answers(answers)
    if not any(row['a'] for row in transcript): raise ValueError('answer at least one question first')
    ctx = context(store)
    brain = _brain(store, llm)
    if not brain:
        if isinstance(answers, dict): return _plain(answers, ctx)
        raise ValueError('The AI assistant used for the interview is no longer available.')
    prompt = (f"MODE: WRITE_SOUL\n\n{_known(ctx)}\n\nCOMPLETE SEVEN-QUESTION INTERVIEW:\n"
              f"{_transcript(transcript)}")
    out = str(brain(skill_text(), prompt, max_tokens=1800) or '').strip()
    out = out.removeprefix('```markdown').removeprefix('```').removesuffix('```').strip()
    if out: return out
    if isinstance(answers, dict): return _plain(answers, ctx)
    raise ValueError('The assistant did not produce SOUL.md. Try writing it again.')


def write(store, answers, actor: str = 'owner', llm=None) -> str:
    """Draft, save, and audit an owner-controlled SOUL.md."""
    body = draft(store, answers, llm)
    store.save_doc('soul', body, actor)
    transcript = _answers(answers)
    store.audit('doc', 0, 'soul_interview', actor,
                detail={'answered': sum(bool(row['a']) for row in transcript),
                        'questions': len(transcript), 'adaptive': isinstance(answers, list)})
    return body
