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
    'remember that Kishan handles refunds': 'remembered',    # Taskuary writes the row itself
    'send it to the coder': 'coder', 'look into it': 'coder', 'can you check if the report ran?': None,
    "I'll take it": 'mine', "I'll handle this": 'mine', 'mine': 'mine', 'make it a task': 'mine',
    'close it': 'closed', 'close the task': 'closed', 'stop the agent': 'stop_agent', 'wrap it up': 'stop_agent',
    'rerun it': 'rerun', 'split it': 'split', 'set up a weekly report on refunds': 'walkthrough',
    'skip all the newsletters': 'clear', "it's handled": 'done',
    "what's this about?": None, 'who sent this?': None, 'summarize the thread': None,
    'show me the draft': None, 'what did I miss?': None,
    'make the reply shorter': 'redraft', 'forward it to Chana': 'forward', 'assign it to Chana': 'forward',
    'ask Chana to handle it': 'forward', 'delete it': 'archive', 'archive it': 'archive',   # forward = 'forwarded' once written
    'snooze it': 'later', 'remind me tomorrow': 'skip',
    'approve and remember that Kishan handles refunds': 'approve',
    'answer the agent: yes remove them': 'answer_agent', 'tell the agent yes': 'answer_agent',
    # naming another subject: resolved and done THERE, or asked about - never carried out on the table
    'not ours, facilities handles the payroll portal outage': None, 'close the payroll portal one': None,
    'approve the invoice one': None,
}
# the card's primary, said as a word: what "yes" means depends on what is on the table
ASSENT = {'review': 'approve', 'proposal': 'approve', 'agent-asking': 'answer_agent', 'idea': 'followup',
          'review(no draft)': 'reply'}      # nothing drafted yet: "yes" writes one, it does not send one
ASSENT_WORDS = ('yes', 'ok', 'sure', 'go ahead', 'do it')
AGENT_ONLY = {'yes remove them': 'answer_agent'}
# verbs the PAGE has an explicit branch for; anything else must not reach done(null)
PAGE_VERBS = {'reply', 'approve', 'not_ours', 'not_ours_remember', 'not_ours_sender', 'coder', 'mine', 'rerun',
              'close', 'closed', 'stop_agent', 'walkthrough', 'created', 'clear', 'setup', 'done', 'later', 'skip',
              'next', 'setting', 'split', 'remember', 'answer_agent', 'redraft', 'forward', 'archive', 'followup', 'ack'}
CLAIMS = ('Sending it as drafted', 'Queued the rerun', 'Closing the task', 'Not ours, then', 'On your list',
          'Sent off to the coding agent', 'Filed, and remembered', 'that sender is noise', 'Remembered.')


# the verb the receipt reports once Taskuary has already carried it out itself
SAME = {'forward': 'forwarded', 'close': 'closed', 'remember': 'remembered', 'setup': 'walkthrough'}
# an honest "I did not do that, and here is why" is never a failure: it is the whole point
HONEST = ('nothing to', 'could not', 'careful -', 'nothing is on the table', 'yes to what', 'remember what')


def expected(row):
    ph, item = row['phrase'], row['item']
    # "done" about an agent parked on a question ends the job: the task closes and the session
    # with it, so the verb that comes back is `closed`
    if item == 'agent-asking' and EXPECT.get(ph) == 'done': return 'closed'
    if ph in AGENT_ONLY: return AGENT_ONLY[ph] if item == 'agent-asking' else '?'
    if ph in ASSENT_WORDS: return ASSENT.get(item, '?')
    return EXPECT.get(ph, '?')


def flags(row):
    out, verb, say, page = [], row.get('verb'), row.get('say') or '', ' | '.join(row.get('page') or [])
    eff = row.get('effects') or {}
    gone = any(k.startswith('task') and str(v).endswith('-> None') for k, v in eff.items())
    # filing a chatter task deletes it, and always has. What must never be deleted is WORK - a task
    # an agent has been on - or anything at all when the sentence named some other subject.
    if gone and (row['item'] == 'agent-asking' or 'acting on the named item' in page): out.append('A1 deleted-work')
    if gone and expected(row) is None: out.append('A1 deleted-on-a-named-subject')
    if 'PAGE-REFUSED' in page or 'error banner' in page:
        if any(c in say for c in CLAIMS): out.append('B receipt-then-refused')
        else: out.append('B page-could-not')
    if verb and verb not in PAGE_VERBS and any(str(v).endswith('-> done') for k, v in eff.items() if k.startswith('fs[')):
        out.append('B no-branch-settled-it')
    exp = expected(row)
    if exp != '?' and verb == SAME.get(exp): exp = verb
    if exp != '?' and verb != exp and not (verb is None and any(h in say.lower() for h in HONEST)):
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
