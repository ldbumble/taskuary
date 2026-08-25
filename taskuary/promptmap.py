"""What is actually in the prompt - block by block, and where each block came from.

Three AI calls decide almost everything Taskuary does: triage (is this work?), the reply writer,
and the coding agent's opening prompt. Each is assembled from a different set of documents, notes
and message text, and until now the only way to know what a model was told was to read the code
that builds it. That is not a reasonable answer to "why did it decide that?".

`taskuary prompts` prints each one for a REAL message on your own machine, split into labelled
blocks with the source of every block named - the document, the database table, or the constant
in the code - so a wrong verdict can be traced to the text that caused it.
"""
import json
from .store import task_ref

MAP = 'prompt map'


def _blocks_triage(store, msg: dict, mid: int) -> list:
    """(label, source, text) for every part of the triage prompt, in prompt order."""
    from .ingest import owner_addresses, relevant_notes
    from .learn import injectable
    from .triage import INTENT_SYSTEM, addressed_to_you, strip_boilerplate
    m = {'from_email': msg.get('FromEmail'), 'subject': msg.get('Subject'), 'body': msg.get('BodyText'),
         'source_name': msg.get('SourceName'), 'channel': msg.get('Channel')}
    doc = store.doc('triage') or ''
    base = doc.strip() or INTENT_SYSTEM
    soul, learned = store.doc('soul') or '', injectable(store.doc('learned') or '')
    notes, left = relevant_notes(store, [m['from_email'] or ''],
                                 f"{m['subject'] or ''} {m['body'] or ''}"[:4000],
                                 subject=m['subject'] or '', source=m['source_name'] or '')
    mine = owner_addresses(store)
    how = addressed_to_you(m, mine)
    out = [('the classifier instructions', 'TRIAGE.md' if doc.strip() else 'triage.INTENT_SYSTEM (the doc is blank)', base)]
    if soul: out.append(("the operator's document", 'SOUL.md', soul[:2500]))
    if learned: out.append(('the learned profile', 'LEARNED.md (active sections only - hypotheses are gated out)', learned[:1500]))
    if notes:
        out.append(('standing notes that apply to THIS message', f'memory table - {len(notes)} of '
                    f'{len(notes) + left} applied, ranked by ingest.relevant_notes',
                    '\n'.join(f'- {n}' for n in notes)))
    out.append(('the message itself (this is the USER turn, everything above is SYSTEM)',
                'message table, signature and legal footer trimmed by triage.strip_boilerplate',
                json.dumps({'from': m['from_email'], 'subject': m['subject'],
                            **({'addressed_to_you': how, 'recipients': 0} if how else {}),
                            'body': strip_boilerplate(str(m['body'] or ''))[:1500]}, indent=2)))
    return out


def _blocks_reply(store, tid: int) -> list:
    from .ingest import notes_for
    from .learn import injectable
    from .responder import BREVITY, CHAT, CHAT_CHANNELS, EMAIL, NOT_YET, SYSTEM, style_doc
    msgs = [m for m in store.list_messages(tid) if m.get('Status') != 'context']
    last = msgs[-1] if msgs else {}
    soul = store.doc('soul') or ''
    owner = soul.split('You work for **')[1].split('**')[0] if 'You work for **' in soul else 'the owner'
    chat = str(last.get('Channel') or '').lower() in CHAT_CHANNELS
    sty, lrn = style_doc(store), injectable(store.doc('learned') or '')
    notes = notes_for(store, {'from_email': last.get('FromEmail'), 'subject': last.get('Subject'),
                              'body': last.get('BodyText')}, budget=1500)
    out = [('who is writing and the rules of the reply', 'responder.SYSTEM + BREVITY + '
            + ('CHAT (a chat channel)' if chat else 'EMAIL') + ' + NOT_YET (code)',
            SYSTEM.format(owner=owner) + BREVITY + (CHAT if chat else EMAIL) + '\n' + NOT_YET)]
    if soul: out.append(('your document, addressed to the writer as themselves', 'SOUL.md', soul[:4000]))
    if sty: out.append(('your voice, distilled from mail you actually sent', 'STYLE.md', sty[:2500]))
    if lrn: out.append(('the learned profile', 'LEARNED.md (active sections only)', lrn[:2000]))
    if notes: out.append(('standing notes for this sender/topic', 'memory table (ingest.notes_for)',
                          '\n'.join(f'- {n}' for n in notes)))
    out.append(('the thread being answered (USER turn)', 'message table, boilerplate trimmed',
                '\n\n'.join(f"--- {m.get('FromName') or m.get('FromEmail')} · {m.get('SentAt')}\n"
                            f"{str(m.get('BodyText') or '')[:600]}" for m in msgs)))
    return out


def _blocks_coder(store, tid: int) -> list:
    """The coding agent gets ONE typed line, not a system/user pair - so the map is its parts."""
    from . import terminal
    from .agents import memory_block
    from .ingest import source_rules
    msgs = [m for m in store.list_messages(tid) if m.get('Status') != 'context']
    m = msgs[-1] if msgs else None
    seed = terminal.seed_text(store, tid)
    out = [('THE WHOLE PROMPT, as one line typed into the session', 'terminal.seed_text', seed), (None, None, None)]
    out += [('the ask and the mail behind it', 'task + message tables', str((m or {}).get('Subject') or '')),
            ("this source's standing instruction", 'the connector card (GitHub PR/issue rules, or task_prompt)',
             source_rules(store, m) if m else ''),
            ('your document', 'SOUL.md (flattened, addresses stripped)', ' '.join((store.doc('soul') or '').split())[:600]),
            ('the coder rules', 'CODER.md (flattened)', terminal.rules_text(store)[:600]),
            ('standing notes for this thread', 'memory table (agents.memory_block)', memory_block(store, msgs)),
            ('what to do, and what not to go looking for', 'terminal.seed_text (code)', 'see the whole prompt above')]
    return [b for b in out if b[0] is None or b[2]]


def render(store, message_id: int = None, task_id: int = None, width: int = 96) -> str:
    """The three prompts, block by block, for a real item on this machine."""
    lines, bar = [], '─' * width

    def section(title, note, blocks):
        nonlocal lines
        lines += ['', '═' * width, title.upper(), note, '═' * width]
        if not blocks:
            lines.append('  (nothing to show - see the note above)')
            return
        for label, src, text in blocks:
            if label is None:
                lines += ['', bar, 'THE SAME PROMPT, BROKEN UP - where each part came from:', bar]
                continue
            body = (text or '').strip()
            lines += ['', f'┌─ {label}', f'│  source: {src}', f'│  {len(body)} characters', '└' + bar[1:]]
            lines += ['   ' + l for l in body.splitlines()[:40]]
            if len(body.splitlines()) > 40: lines.append(f'   … {len(body.splitlines()) - 40} more lines')

    msg = store.get_message(message_id) if message_id else None
    if msg is None:
        msg = next((m for m in store.scan_messages(limit=200) if m.get('BodyText')), None)
    if msg:
        full = store.get_message(msg['MessageId'])
        section(f"1. triage - is message {full['MessageId']} work?",
                f"asked once per inbound message. Verdict: task / reply_only / fyi.\n"
                f"the message: \"{(full.get('Subject') or '')[:70]}\" from {full.get('FromEmail')}",
                _blocks_triage(store, full, full['MessageId']))
    else:
        section('1. triage', 'no message with a body on this machine yet - sync first', [])

    tid = task_id or next((t['TaskId'] for t in store.list_tasks() if store.list_messages(t['TaskId'])), None)
    if tid:
        section(f'2. the reply writer - drafting on {task_ref(tid)}',
                'asked when triage says reply_only, or when you press Draft. Output: the reply text.',
                _blocks_reply(store, tid))
        section(f'3. the coding agent - opening prompt on {task_ref(tid)}',
                'typed into the CLI session as ONE line. Not a system/user pair: a session prompt.',
                _blocks_coder(store, tid))
    else:
        section('2. the reply writer', 'no task with messages on this machine yet', [])
    return '\n'.join(lines)
