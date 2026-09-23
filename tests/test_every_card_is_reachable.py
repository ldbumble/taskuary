"""A card that cannot spend its own credential is not connected, whatever the page says.

LinkedIn shipped this way (2026-09-22). The executor was written, the report types were in
REGISTRY, the card was seeded, the catalogue listed it - and three seams were missing, each of
which alone makes the connector useless:

  1. no entry in CONNECTION_OF, so the saved token never reached the executor. Every call
     answered "LinkedIn needs an access token" with the token sitting on the card.
  2. no entry in the Connections page's metadata, so the card opened with a Credentials step
     holding NO FIELDS - nowhere to type the token in the first place.
  3. no branch in test_connector, so Test answered "no test for connector type 'linkedin'".

None of them is visible from the executor's own tests, which is why they are checked here
instead: these assertions fail on the NEXT connector somebody wires up half way.
"""
import json
import pathlib
import re
import unittest

from taskuary import channels
from taskuary.reports import CARD_OF, CONNECTION_OF, REGISTRY, resolve_cfg
from taskuary.store import MemoryStore

ROOT = pathlib.Path(__file__).resolve().parents[1]

# Cards whose whole configuration is public: nothing to resolve, so no CONNECTION_OF entry.
KEYLESS = {'reader', 'coingecko', 'frankfurter', 'yahoo', 'sec_edgar', 'fred', 'screen',
           'handbook', 'knowledge', 'local_file', 'sqlite', 'rss', 'digest', 'evening_inbox',
           'automate'}


# Two executors that reach for their own card instead of taking a resolved cfg - Calendar reads
# whichever mailbox card carries the OAuth fields, and the Zoho report drives its own token
# refresh. They predate this guard; they are named rather than quietly skipped.
SELF_FETCHING = {'calendar', 'zoho_monthly_invoices'}


class ASavedSecretReachesItsExecutor(unittest.TestCase):
    def test_every_report_type_with_a_card_can_resolve_it(self):
        """CARD_OF says which card a report type spends. CONNECTION_OF is how it gets there, and
        a type named in one but not the other is a credential that goes nowhere."""
        missing = sorted(t for t, card in CARD_OF.items()
                         if card not in KEYLESS and t not in CONNECTION_OF and t not in SELF_FETCHING)
        self.assertEqual(missing, [], f'no CONNECTION_OF entry: {missing}')

    def test_the_secret_actually_arrives_under_the_name_the_executor_reads(self):
        """Not just present - resolved. A resolver pointed at the wrong card type returns {} and
        looks exactly like a card nobody has filled in."""
        s = MemoryStore()
        seen = {}
        for rtype, card in sorted(CARD_OF.items()):
            if card in KEYLESS or rtype not in CONNECTION_OF: continue
            c = s.get_connector_by_type(card)
            if not c: continue                      # a card with no seeded row is its own test
            if card not in seen:
                s.save_connector({'ConnectorId': c['ConnectorId'], 'Secret': f'sec-{card}',
                                  'Active': 1}, 'test')
                seen[card] = True
            cfg = resolve_cfg(s, {'type': rtype})
            self.assertIn(f'sec-{card}', cfg.values(),
                          f'{rtype} does not see the secret saved on its {card} card: {cfg}')


class EveryCardCanBeTested(unittest.TestCase):
    """Test is the only way an owner finds out a credential is wrong before a scheduled report
    comes back empty on Monday. A card with no branch says "no test for connector type" - which
    reads as a broken product, not a missing one."""

    # The Company Hub is Taskuary's own store. There is no remote end to reach, so there is
    # nothing a Test could tell anyone.
    NO_REMOTE = {'handbook'}

    def _covered(self) -> set:
        src = (ROOT / 'taskuary' / 'channels.py').read_text(encoding='utf-8')
        region = src[src.index('def test_connector'):src.index('no test for connector type')]
        out = set(re.findall(r"'([a-z0-9_]+)'", region))
        for name in ('RESEARCH', 'PAGE_READERS', 'DB_ENGINES', 'CHAT_SERVERS', 'AI_TYPES'):
            if name in region: out |= set(getattr(channels, name))
        return out

    def test_every_seeded_card_has_a_branch(self):
        covered = self._covered()
        missing = sorted({c['Type'] for c in MemoryStore().list_connectors()}
                         - covered - self.NO_REMOTE)
        self.assertEqual(missing, [], f'no Test branch in channels.test_connector: {missing}')


class EveryCardIsOnThePage(unittest.TestCase):
    """A connector nobody can open is a connector nobody has.

    ConnectorsView lists each group's cards by type - channelCards([...]) for a channel,
    dataCards([...]) for a tool or report source - and describes each one in META or DATA_META. A
    type LISTED but not DESCRIBED renders a setup stepper with no fields in it, which is what
    LinkedIn did: the Credentials step was there, ticked, and empty.
    """

    def test_every_working_card_is_rendered_by_some_group(self):
        """THE OTHER DIRECTION, and the one that was missing.

        The test below asks that everything a group LISTS is described. It never asked whether a
        working connector is listed at all - so eight market cards (Twelve Data, Alpha Vantage,
        Finnhub, Polygon, Tiingo, FMP, Alpaca, FRED) sat seeded, registered, scoped and testable,
        with report types the Reports tab OFFERED, and no way to open the card their API key has
        to live on. A report could be built and could never run. Robinhood and Company Hub had
        card definitions that no group rendered, which is the same hole by a shorter route
        (2026-09-22).
        """
        src = (ROOT / 'website' / 'src' / 'ConnectorsView.jsx').read_text(encoding='utf-8')
        groups = src[src.index('const groups = ['):src.index('const hits = q ?')]
        listed = set(re.findall(r'specialCards\("([a-z0-9_]+)"', groups))
        for call in re.findall(r'(?:channelCards|dataCards|plannedCards)\(\[(.*?)\]\)', groups, re.S):
            listed |= set(re.findall(r'"([a-z0-9_]+)"', call))
        catalogue = json.loads((ROOT / 'taskuary' / 'connectorcatalog.json').read_text(encoding='utf-8'))
        working = {r['type'] for r in catalogue['cards'] if not r['planned']}
        missing = sorted(t for t in {c['Type'] for c in MemoryStore().list_connectors()} & working
                         if t not in listed)
        self.assertEqual(missing, [], f'seeded and working, but no group renders it: {missing}')

    def test_every_type_a_group_lists_is_also_described(self):
        src = (ROOT / 'website' / 'src' / 'ConnectorsView.jsx').read_text(encoding='utf-8')
        described = set(re.findall(r'^  ([a-z0-9_]+): \{', src, re.M))
        listed = set()
        for call in re.findall(r'(?:channelCards|dataCards)\(\[(.*?)\]\)', src, re.S):
            listed |= set(re.findall(r'"([a-z0-9_]+)"', call))
        missing = sorted(listed - described)
        self.assertEqual(missing, [], f'listed in a group but not described: {missing}')


if __name__ == '__main__':
    unittest.main()
