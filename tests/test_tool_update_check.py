"""AGENT-BROWSER SAYS WHEN IT IS BEHIND (the owner, 2026-11-07): its card shows "update available" when the version here is older than npm's
latest. Checked at most once a day, in a thread, kept in a file - never on a page's request - and an offline machine is no answer, never
an error."""
import json, time
from types import SimpleNamespace
from unittest import mock

from taskuary import clis


def checked(have='agent-browser 0.5.0\n', latest='0.6.1', net=None):
    ran = SimpleNamespace(stdout=have)
    get = net or (lambda url, timeout: SimpleNamespace(json=lambda: {'version': latest}))
    with mock.patch('taskuary.pathcache.which', return_value='C:/npm/agent-browser.cmd'), mock.patch('taskuary.spawn.run', return_value=ran), \
            mock.patch('requests.get', side_effect=get) as g:
        out = clis.check_versions()
    return out, g


def test_a_tool_behind_npm_says_update_available():
    out, g = checked()
    assert out['agent-browser'] == {'have': '0.5.0', 'latest': '0.6.1'}
    assert g.call_args_list[0].args[0] == 'https://registry.npmjs.org/agent-browser/latest'
    with mock.patch.object(clis, 'versions', return_value=out), mock.patch('taskuary.pathcache.which', return_value='C:/npm/agent-browser.cmd'):
        ab = next(t for t in clis.tools() if t['name'] == 'agent-browser')
    assert (ab['version'], ab['latest'], ab['update']) == ('0.5.0', '0.6.1', '0.6.1')
    out, _ = checked(have='agent-browser 0.10.0')                      # 0.10 is newer than 0.6, not older
    with mock.patch.object(clis, 'versions', return_value=out): assert next(t for t in clis.tools() if t['name'] == 'agent-browser')['update'] == ''


def test_offline_is_no_answer_and_never_an_error():
    def down(url, timeout): raise OSError('no network')
    out, _ = checked(net=down)
    assert out['agent-browser'] == {'have': '0.5.0', 'latest': ''}
    with mock.patch.object(clis, 'versions', return_value=out): assert next(t for t in clis.tools() if t['name'] == 'agent-browser')['update'] == ''


def test_it_checks_at_most_once_a_day_and_never_on_the_request():
    f = clis._versions_file(); f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps({'at': time.time(), 'agent-browser': {'have': '0.5.0', 'latest': '0.6.1'}}), encoding='utf-8')
    with mock.patch('threading.Thread') as th:
        assert clis.versions()['agent-browser']['latest'] == '0.6.1'; th.assert_not_called()        # fresh: read from the file, nothing run
        assert clis.versions(now=time.time() + clis.DAY + 1)['agent-browser']['have'] == '0.5.0'    # a day old: the old answer now...
        th.assert_called_once(); assert th.call_args.kwargs['target'] is clis.check_versions          # ...and the check behind it
    clis._CHECKING.clear()
