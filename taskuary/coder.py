"""Coding-task lifecycle: (optional) GitHub issue first, then the CLI works it with a
required report contract, then auto-close or escalation - and the diff rides on the run.
"""
import json, re
from loguru import logger
from .store import task_ref
from . import agents as hub_agents
from . import github as gh

RESULT_MARKER = '===RESULT JSON==='
REPORT_CONTRACT = ('\n\nEnd your output with the marker ' + RESULT_MARKER + ' on its own line, followed by ONE JSON object:\n'
                   '{"summary": "...", "triage": "...", "determination": "...", "actions": "...",\n'
                   ' "email_reply": "<reply to the original sender>", "needs_you": ""}\n'
                   'needs_you is the ONLY thing that keeps this task open. Leave it "" whenever you finished '
                   'the work - INCLUDING when the work was answering a question - and the task closes with '
                   'your report attached. Fill it in ONLY when the owner must approve or decide something in '
                   'the UI before you can go on, and say exactly what you need from them. Never ask a question '
                   'in prose and stop: decide within your CODER.md rules, or put the ask in needs_you.')


def github_cfg(store) -> dict:
    """[github] from config.toml, with the GitHub connector's saved PAT winning."""
    from . import config
    g = dict(config.load().get('github') or {})
    c = store.get_connector_by_type('github', with_secret=True)
    if c and c.get('Secret'): g['token'] = c['Secret']
    return g


FIELDS = ('summary', 'triage', 'determination', 'actions', 'email_reply', 'needs_you')

def parse_coder_result(out: str) -> dict:
    """`needs_you` is the run's whole control flow, so a report we could not parse is itself
    a "needs you" - never a silent close. Legacy `close:false` alone no longer holds a task
    open: answering the question IS the work, and unfinished work has to say what it needs."""
    try:
        tail = out.split(RESULT_MARKER)[-1]
        j = json.loads(re.sub(r'^```(json)?|```$', '', tail.strip(), flags=re.M))
        return {k: str(j.get(k) or '') for k in FIELDS} | {'parsed': True}
    except Exception:
        return dict.fromkeys(FIELDS, '') | {'summary': (out or '')[-800:], 'parsed': False}


def run_coding_task(store, task_id: int, actor: str = 'system', repo: str = None, github_cfg: dict = None,
                    agent: str = 'coder', model: str = None, instruction: str = None) -> dict:
    """`agent` picks WHICH CLI works it (claude, codex, gemini… whatever is configured) and
    `model` which model that CLI runs; `instruction` is the owner's own prompt for this run.
    The lifecycle around them - issue, report contract, close or escalate - is the same."""
    t = store.get_task(task_id)
    if not t: raise ValueError(f'no task {task_id}')
    ctx = hub_agents.task_context(store, task_id)
    tok = (github_cfg or {}).get('token')
    repo = repo or (github_cfg or {}).get('default_repo')
    issue = None
    if tok and repo:
        try:
            issue = gh.create_issue(tok, repo, f'[{task_ref(task_id)}] {(t.get("Title") or "coding task")[:120]}',
                                    f'{ctx}\n\n---\nAgent prompt: work this task per CODER.md; report and close when resolved.')
            store.add_comment(task_id, 'coder', 'agent', f'Opened GitHub issue {repo}#{issue["number"]}: {issue["url"]}')
        except Exception as e:
            logger.warning(f'issue creation failed, continuing without: {e}')

    profile = json.loads((store.get_agent(agent) or {}).get('Config') or '{}')
    cwd = (profile.get('cwd_map') or {}).get(repo)
    where = f'{repo}#{issue["number"]}' if issue else '(no GitHub issue configured)'
    override = {**({'cwd': cwd} if cwd else {}), **({'model': model} if model else {})}
    out = hub_agents.dispatch(store, task_id, agent,
                              (instruction.strip() if instruction and instruction.strip()
                               else 'Work this coding task end to end.')
                              + f' GitHub issue: {where}.'
                              + (f' Repository: {repo}.' if repo else '') + REPORT_CONTRACT,
                              actor, profile_override=override or None)
    if not store.get_task(task_id):                                   # deleted mid-run
        if tok and issue:
            try: gh.close_issue(tok, repo, issue['number'], 'Task deleted while the agent worked - closing.')
            except Exception: pass
        return {'closed': False, 'aborted': 'task deleted mid-run'}
    rep = parse_coder_result(out.get('result') or '')
    err = None
    if out['status'] != 'done':
        run = store.get_run(out['run_id']) or {}
        err = (run.get('LastError') or 'see the run log')[:300]
        rep['determination'] = rep['needs_you'] = f'run failed: {err}'
        store.add_comment(task_id, 'coder', 'agent', f'Coder run FAILED: {err}')
    else:
        # the report lands on the task either way - you read what it did even when it's done
        store.add_comment(task_id, 'coder', 'agent',
                          f"CODER REPORT\nTriage: {rep['triage']}\nDetermination: {rep['determination']}\n"
                          f"Actions: {rep['actions']}\nSummary: {rep['summary']}")
        if not rep['parsed'] and not rep['needs_you']:
            rep['needs_you'] = 'the agent stopped without its report contract - read the run output and decide'
    msgs = store.list_messages(task_id)
    mid = msgs[-1].get('MessageId') if msgs else None
    needs = rep['needs_you'].strip()
    if not needs:
        if tok and issue:
            try: gh.close_issue(tok, repo, issue['number'], f'Closed by the Taskuary coder.\n\n{rep["summary"]}')
            except Exception as e: logger.warning(f'issue close failed: {e}')
        if rep['email_reply'] and mid:
            store.add_review({'TaskId': task_id, 'MessageId': mid, 'RunId': out['run_id'], 'Kind': 'draft_reply',
                              'DraftText': rep['email_reply'], 'Status': 'pending',
                              'Reason': 'coder resolved the task - reply awaiting approval'})
        store.update_task(task_id, {'Status': 'done'}, 'coder')
    else:
        # waiting on a person, and the raw status says so too - the board column, the chip and
        # Status all have to agree, or you get "escalated but in_progress" again
        reason = f'coder needs you: {needs[:300]}'
        existing = store.pending_review(task_id, 'escalation')
        if existing: store.update_review_reason(existing['ReviewId'], reason, out.get('run_id'))
        else: store.add_review({'TaskId': task_id, 'MessageId': mid, 'RunId': out.get('run_id'), 'Kind': 'escalation',
                                'Status': 'pending', 'Reason': reason})
        if (store.get_task(task_id) or {}).get('Status') != 'dropped':
            store.update_task(task_id, {'Status': 'waiting'}, 'coder')
    return {'closed': not needs, 'needs_you': needs, 'repo': repo, 'issue': issue, 'report': rep,
            **({'error': err} if err else {})}
