"""Talk back to the agent: the task thread IS the chat. Your message resumes the agent's
most recent CLI session (claude -p --resume style, per the profile's resume_args); its
reply appends as a comment. No session yet -> a fresh dispatch carries the message.
"""
import json
from datetime import datetime
from loguru import logger
from . import agents as hub_agents

CHAT_SUFFIX = ('\n\n(You are continuing your work on this task. Reply to the owner conversationally '
               'and act on the request within your rules. If you take actions, say what you did.)')


def message_agent(store, task_id: int, text: str, actor: str) -> dict:
    try:
        last = next((r for r in store.list_runs(task_id) if r.get('SessionId')), None)
        profile = json.loads((store.get_agent('coder') or {}).get('Config') or '{}')
        if not last:
            out = hub_agents.dispatch(store, task_id, 'coder', f'Message from the owner: {text}{CHAT_SUFFIX}', actor)
            return {'ok': out['status'] == 'done', 'run_id': out['run_id'], 'resumed': False}
        run_id = store.start_run(task_id, 'coder', f'(chat) {text[:200]}', actor)
        trace = []
        def _t(kind, name, detail):
            trace.append({'at': datetime.now().isoformat(sep=' ', timespec='seconds'), 'kind': kind,
                          'name': name, 'detail': str(detail)[:12000 if kind == 'prompt' else 2000]})
            store.update_run(run_id, {'TraceJson': json.dumps(trace)})
        try:
            out, sid, diff = hub_agents.run_cli(profile, f'Message from the owner: {text}{CHAT_SUFFIX}', _t,
                                                resume=last['SessionId'])
            store.update_run(run_id, {'Status': 'done', 'Result': out, 'SessionId': sid or last['SessionId'],
                                      **({'DiffText': diff} if diff else {}),
                                      'TraceJson': json.dumps(trace)}, finished=True)
            if store.get_task(task_id): store.add_comment(task_id, 'coder', 'agent', out)
            return {'ok': True, 'run_id': run_id, 'resumed': True}
        except Exception as e:
            store.update_run(run_id, {'Status': 'error', 'LastError': str(e)[:2000], 'TraceJson': json.dumps(trace)}, finished=True)
            if store.get_task(task_id): store.add_comment(task_id, 'coder', 'agent', f'(agent unavailable: {str(e)[:200]})')
            return {'ok': False, 'why': str(e)[:300]}
    except Exception as e:
        logger.exception('message_agent failed')
        return {'ok': False, 'why': str(e)[:300]}
