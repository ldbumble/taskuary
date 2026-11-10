"""Teams for a PERSONAL account, read through the browser (teamsweb.py). No real Teams here: the page is a synthetic snapshot in the
shape Teams' own markup has (data-tid markers, chat-list-item_<id>, data-mid), with invented people, and the browser is a stand-in."""
import json
from unittest import mock
from fastapi.testclient import TestClient
from taskuary import outbound, server, teamsweb as tw
from taskuary.store import MemoryStore

DM, GRP = '19:aa11-bb22@unq.gbl.spaces', '19:cc33dd44@thread.v2'

def item(cid, title, preview, when, unread=False):
    return (f'<div id="chat-list-item_{cid}" role="treeitem" class="{"fui-unread" if unread else ""}" aria-label="{title}, chat">'
            f'<span id="title-chat-list-item_{cid}">{title}</span><time datetime="{when}">10:0</time>'
            f'<span data-tid="chat-list-item-preview">{preview}</span></div>')

def msg(mid, text, author=None, when='2026-11-09T09:00:00.000Z', mine=False):
    head = f'<span data-tid="message-author-name">{author}</span>' if author else ''
    return (f'<div data-tid="chat-pane-item"><div class="{"fui-ChatMyMessage" if mine else "fui-ChatMessage"}">'
            f'<div data-tid="chat-pane-message" data-mid="{mid}">{head}<time datetime="{when}">9:00</time>'
            f'<div id="content-{mid}"><p>{text}</p></div></div></div></div>')

SYSTEM = '<div data-tid="chat-pane-item"><div data-tid="control-message">Gail Moreno added Ray Colton to the chat.</div></div>'


class FakePage:
    def __init__(self, url='https://teams.live.com/v2/', chats=(), panes=None, shell=True):
        self.snap = {'url': url, 'list': list(chats), 'shell': shell, 'signin': False}
        self.panes, self.opened, self.sent = panes or {}, [], []
    def chats(self): return self.snap
    def open(self, cid): self.opened.append(cid); return self.panes.get(cid, [])
    def send(self, cid, text): self.sent.append((cid, text)); return {'ok': True}


def _card(s, cfg=None):
    return s.save_connector({'Type': 'teams', 'Name': 'Teams', 'Active': 1, 'Roles': 'trigger',
                             'ConfigJson': json.dumps({'account_type': 'personal', **(cfg or {})})}, 't')


def test_the_chat_list_parses():
    cs = tw.parse_chats([item(DM, 'Erin Blake', 'see you at 3', '2026-11-09T09:01:00Z', unread=True), item(GRP, 'Weekend plans', 'ok!', '2026-11-08T20:00:00Z')])
    assert [c['id'] for c in cs] == [DM, GRP]
    assert cs[0] == {'id': DM, 'title': 'Erin Blake', 'preview': 'see you at 3', 'when': '2026-11-09T09:01:00Z', 'unread': True, 'dm': True}
    assert not cs[1]['unread'] and not cs[1]['dm']


def test_messages_parse_with_runs_mine_and_system_lines():
    ms = tw.parse_messages([msg('1001', 'Are you free Friday?', 'Erin Blake'), msg('1002', 'For the lake trip'), SYSTEM,
                            msg('1003', 'Yes!', mine=True), msg('1004', '<b>Great</b> &amp; thanks', 'Erin Blake')])
    assert [(m['id'], m['author'], m['mine']) for m in ms] == [('1001', 'Erin Blake', False), ('1002', 'Erin Blake', False),
                                                              ('1003', 'You', True), ('1004', 'Erin Blake', False)]
    assert ms[3]['text'] == 'Great & thanks' and ms[0]['when'] == '2026-11-09T09:00:00.000Z'


def test_the_page_state_is_told_apart():
    assert tw.state_of({'url': 'https://teams.live.com/v2/', 'shell': True}) == 'ok'
    assert tw.state_of({'url': 'https://login.live.com/oauth20_authorize.srf?x=1'}) == 'signed_out'
    assert tw.state_of({'url': 'https://teams.live.com/v2/', 'shell': False, 'list': []}) == 'changed'
    assert tw.state_of({'url': 'https://teams.live.com/free', 'signin': True}) == 'signed_out'


def test_poll_files_new_messages_once_each():
    s = MemoryStore(); cid = _card(s)
    page = FakePage(chats=[item(DM, 'Erin Blake', 'Yes!', '2026-11-09T09:03:00Z', unread=True)],
                    panes={DM: [msg('1001', 'Are you free Friday to look over the budget?', 'Erin Blake'), msg('1003', 'Yes!', mine=True)]})
    assert tw.poll(s, s.get_connector(cid), page=page) >= 1
    assert s.message_exists(f'teams:live:{DM}:1001') and s.message_exists(f'teams:live:{DM}:1003')
    assert json.loads(s.get_connector(cid)['ConfigJson'])['web_seen'][DM]['mid'] == '1003'
    # the same page again: not unread now, the row did not move - the chat is not even opened, and nothing is filed twice
    page.snap['list'] = [item(DM, 'Erin Blake', 'Yes!', '2026-11-09T09:03:00Z')]; page.opened.clear()
    assert tw.poll(s, s.get_connector(cid), page=page) == 0 and page.opened == []
    # a new line: only what follows the last one read is filed
    page.snap['list'] = [item(DM, 'Erin Blake', 'Thanks', '2026-11-09T09:05:00Z')]
    page.panes[DM] = page.panes[DM] + [msg('1005', 'Thanks - sending it over now', 'Erin Blake')]
    with mock.patch('taskuary.ingest.ingest_message', wraps=__import__('taskuary.ingest', fromlist=['x']).ingest_message) as ing:
        tw.poll(s, s.get_connector(cid), page=page)
    assert [c.args[1]['external_id'] for c in ing.call_args_list] == [f'teams:live:{DM}:1005']
    assert ing.call_args_list[0].args[1]['from_name'] == 'Erin Blake' and ing.call_args_list[0].args[1]['conversation_id'] == f'teams:live:{DM}'


def test_signed_out_and_changed_page_stop_the_read_in_words():
    s = MemoryStore(); c = s.get_connector(_card(s))
    for page, why in ((FakePage(url='https://login.live.com/login.srf'), tw.SIGNED_OUT), (FakePage(shell=False), tw.CHANGED)):
        try: tw.poll(s, c, page=page); assert False, 'should have stopped'
        except RuntimeError as e: assert str(e) == why
        assert page.opened == []


def test_the_poller_takes_the_browser_road_and_puts_the_failure_on_the_card():
    from taskuary import channels
    s = MemoryStore(); cid = _card(s)
    with mock.patch.object(tw, 'Page', lambda _cid: FakePage(url='https://login.live.com/')), \
         mock.patch.object(channels, 'graph_creds', side_effect=AssertionError('Graph must not be asked')):
        channels._poll_one(s, s.get_connector(cid), False, 0, None, False)
    assert s.get_connector(cid)['LastError'] == tw.SIGNED_OUT


def test_a_reply_is_typed_into_the_chat_through_the_browser():
    s = MemoryStore(); _card(s)
    page = FakePage()
    with mock.patch.object(tw, 'Page', lambda _cid: page):
        out = outbound.send_teams(s, f'live:{DM}', 'Friday works for me')
    assert page.sent == [(DM, 'Friday works for me')] and out == {'channel': 'teams', 'chat': f'live:{DM}'}
    page.send = lambda cid, text: {'ok': False, 'why': 'no Send button'}
    with mock.patch.object(tw, 'Page', lambda _cid: page):
        try: outbound.send_teams(s, f'live:{DM}', 'again'); assert False
        except RuntimeError as e: assert 'no Send button' in str(e)


def test_a_reply_to_a_filed_message_goes_back_to_its_chat():
    s = MemoryStore(); _card(s)
    with mock.patch.object(tw, 'send', return_value={'channel': 'teams', 'chat': f'live:{DM}'}) as sent:
        outbound.send_teams(s, f'live:{DM}', 'On my way')
    assert sent.call_args.args[1:3] == (f'live:{DM}', 'On my way')


def test_the_card_signs_in_in_its_own_browser():
    s = MemoryStore(); cid = _card(s)
    from taskuary import browserview
    with mock.patch.object(server, 'store', s), mock.patch.object(browserview, 'installed', return_value=True), \
         mock.patch.object(browserview, 'start', return_value=True) as start:
        r = TestClient(server.app).post(f'/api/connectors/{cid}/teamsweb/signin')
    assert r.status_code == 200 and r.json() == {'sid': f'teamsweb-{cid}'}
    assert start.call_args.args == (f'teamsweb-{cid}', tw.HOME)
    work = s.save_connector({'Type': 'teams', 'Name': 'Work Teams', 'Active': 1, 'ConfigJson': '{}'}, 't')
    with mock.patch.object(server, 'store', s):
        assert TestClient(server.app).post(f'/api/connectors/{work}/teamsweb/signin').status_code == 409
