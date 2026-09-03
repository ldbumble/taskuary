"""The report's findings, written as rules over probe_out.json - so "is it fixed" is a number.

Run probe.py first, then this. Each rule is one finding: a row it matches is a row that still
breaks. Nothing here knows about the fix; it only knows what the page must never do.
"""
import json, os, sys, collections

OUT = os.path.join(os.path.dirname(__file__), 'probe_out.json')

# What the words mean, whatever is on the table. None = not a decision at all (a question, a
# negation, a remark): the model answers it and nothing is carried out.
EXPECT = {
    'next': 'next', 'done': 'done', 'later': 'later', 'tomorrow': 'skip', 'skip': 'skip', 'skip it': 'skip',
    'approve': 'approve', 'send it': 'approve', 'looks good, send it': 'approve',
    'reply and tell them we will look at it': 'reply', 'tell them to ignore it': 'reply',
    'let them know we will fix it by Friday': 'reply', 'tell Chana it is handled': 'reply',
    'reply: not ours, sorry': 'reply', 'remember to reply to him': 'reply',
    'not ours': 'not_ours', 'not my problem': 'not_ours', 'ignore it': 'not_ours',
    "don't ignore this one": None, 'leave it open': None, 'leave it with the agent': None,
    'never again': 'not_ours_remember', 'that sender is spam': 'not_ours_sender',
    'remember that Kishan handles refunds': 'remember',
    'send it to the coder': 'coder', 'look into it': 'coder', 'can you check if the report ran?': None,
    "I'll take it": 'mine', "I'll handle this": 'mine', 'mine': 'mine', 'make it a task': 'mine',
    'close it': 'closed', 'close the task': 'closed', 'stop the agent': 'stop_agent', 'wrap it up': 'stop_agent',
    'rerun it': 'rerun', 'split it': 'split', 'set up a weekly report on refunds': 'setup',
    'skip all the newsletters': 'clear', "it's handled": 'done',
    "what's this about?": None, 'who sent this?': None, 'summarize the thread': None,
    'show me the draft': None, 'what did I miss?': None,
    'make the reply shorter': 'redraft', 'forward it to Chana': 'forward', 'assign it to Chana': 'forward',
    'ask Chana to handle it': 'forward', 'delete it': 'archive', 'archive it': 'archive',
    'snooze it': 'later', 'remind me tomorrow': 'skip',
    'approve and remember that Kishan handles refunds': 'approve',
    'answer the agent: yes remove them': 'answer_agent', 'tell the agent yes': 'answer_agent',
}
# the card's primary, said as a word: what "yes" means depends on what is on the table
ASSENT = {'review': 'approve', 'proposal': 'approve', 'agent-asking': 'answer_agent', 'idea': 'followup'}
ASSENT_WORDS = ('yes', 'ok', 'sure', 'go ahead', 'do it')
AGENT_ONLY = {'yes remove them': 'answer_agent'}
# verbs the PAGE has an explicit branch for; anything else must not reach done(null)
PAGE_VERBS = {'reply', 'approve', 'not_ours', 'not_ours_remember', 'not_ours_sender', 'coder', 'mine', 'rerun',
              'close', 'closed', 'stop_agent', 'walkthrough', 'created', 'clear', 'setup', 'done', 'later', 'skip',
              'next', 'setting', 'split', 'remember', 'answer_agent', 'redraft', 'forward', 'archive', 'followup', 'ack'}
CLAIMS = ('Sending it as drafted', 'Queued the rerun', 'Closing the task', 'Not ours, then', 'On your list',
          'Sent off to the coding agent', 'Filed, and remembered', 'that sender is noise', 'Remembered.')


def expected(row):
    ph, item = row['phrase'], row['item']
    if ph in AGENT_ONLY: return AGENT_ONLY[ph] if item == 'agent-asking' else '?'
    if ph in ASSENT_WORDS: return ASSENT.get(item, '?')
    return EXPECT.get(ph, '?')


def flags(row):
    out, verb, say, page = [], row.get('verb'), row.get('say') or '', ' | '.join(row.get('page') or [])
    eff = row.get('effects') or {}
    if any(k.startswith('task') and str(v).endswith('-> None') for k, v in eff.items()):
        out.append('A1 deleted-a-task')                      # the chat may file and archive; it may never delete
    if 'PAGE-REFUSED' in page or 'error banner' in page:
        if any(c in say for c in CLAIMS): out.append('B receipt-then-refused')
        else: out.append('B page-could-not')
    if verb and verb not in PAGE_VERBS and any(str(v).endswith('-> done') for k, v in eff.items() if k.startswith('fs[')):
        out.append('B no-branch-settled-it')
    exp = expected(row)
    if exp != '?' and verb != exp and not (verb is None and 'nothing to' in say.lower()):
        out.append(f'C verb {verb} != {exp}')
    if row.get('spawned') and row['phrase'] in ('can you check if the report ran?',):
        out.append('C coder-on-a-question')
    return out


def main():
    rows = json.load(open(OUT, encoding='utf-8'))
    hits, by = [], collections.Counter()
    for r in rows:
        f = flags(r)
        if f: hits.append((r, f)); by.update(x.split(' ')[0] + ' ' + x.split(' ')[1] for x in f)
    print(f'{len(hits)} flagged of {len(rows)}')
    for k, n in by.most_common(): print(f'  {n:4d}  {k}')
    if '-v' in sys.argv:
        for r, f in hits: print(f"  [{'; '.join(f)}] {r['item']:16s} {r['phrase']!r:52s} verb={r.get('verb')} say={r.get('say', '')[:60]!r}")
    return len(hits)


if __name__ == '__main__': sys.exit(0 if main() == 0 else 0)
