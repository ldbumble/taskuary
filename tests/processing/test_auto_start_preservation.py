"""Startup preserves the pre-assistant unattended-work choice before any intake begins."""
import asyncio
from contextlib import ExitStack, asynccontextmanager, contextmanager
from unittest import mock

from taskuary import processing_all, server, wabridge
from taskuary.store import SQLiteStore


@asynccontextmanager
async def _no_membership_worker(_store):
    yield


def _legacy_opt_out(path):
    store = SQLiteStore(str(path))
    store.set_setting('coder_auto_enabled', '0', 'owner')
    # This is the on-disk shape from before general_auto_enabled and the one-time
    # migration marker existed. Reopen through the real constructor: it seeds the
    # newly introduced switch to 1 with no owner, and startup must still recover
    # the older owner's broader "no unattended sessions" choice before intake.
    store._exec("DELETE FROM setting WHERE Name IN ('general_auto_enabled','auto_start_upgraded')")
    store.cx.close()
    reopened = SQLiteStore(str(path))
    seeded = reopened._one("SELECT * FROM setting WHERE Name='general_auto_enabled'")
    assert seeded['Value'] == '1' and not seeded.get('UpdatedBy')
    assert 'auto_start_upgraded' not in reopened.get_settings()
    return reopened


@contextmanager
def _lifespan_boundaries(store):
    """Replace every worker, connector, and owner-document boundary around _lifespan."""
    specs = {
        'bind': (server.live_bus, 'bind', {}),
        'open_drains': (server, '_open_drain_workers', {'return_value': True}),
        'close_drains': (server, '_close_drain_workers', {'return_value': True}),
        'recover': (server.hub_term, 'recover_after_restart', {}),
        'shutdown_sessions': (server.hub_term, 'shutdown_sessions', {}),
        'shutdown_children': (server.hub_agents, 'shutdown_cli_children', {}),
        'bridge': (wabridge, 'start_configured', {}),
        'catchup': (server, 'catch_up_on_startup', {}),
        'heal_docs': (server, '_heal_owner_docs', {}),
        'refresh_soul': (server, '_refresh_soul_connections', {}),
        'learn': (server.learn, 'note_verdicts', {}),
        'watch': (server.waitroom, 'watch', {}),
        'threads': (server.threading, 'Thread', {}),
        'triage_upgrade': (store, 'upgrade_triage_failures', {'return_value': 0}),
    }
    with ExitStack() as stack:
        stack.enter_context(mock.patch.object(server, 'store', store))
        stack.enter_context(mock.patch.object(server.demo, 'enabled', return_value=False))
        stack.enter_context(mock.patch.object(
            processing_all, 'membership_lifecycle', _no_membership_worker))
        doubles = {name: stack.enter_context(mock.patch.object(target, attr, **kwargs))
                   for name, (target, attr, kwargs) in specs.items()}
        yield doubles


def test_legacy_owner_opt_out_is_migrated_before_bridge_or_catchup_can_observe_it(tmp_path):
    store = _legacy_opt_out(tmp_path / 'legacy-opt-out.db')
    observed = []
    try:
        with _lifespan_boundaries(store) as doubles:
            bridge, catchup = doubles['bridge'], doubles['catchup']
            bridge.side_effect = lambda _store: observed.append(
                ('bridge', _store.get_settings().get('general_auto_enabled')))
            catchup.side_effect = lambda: observed.append(
                ('catchup', store.get_settings().get('general_auto_enabled')))

            async def enter_once():
                async with server._lifespan(None):
                    observed.append(('yield', store.get_settings().get('general_auto_enabled')))
            asyncio.run(enter_once())

        assert observed == [('bridge', '0'), ('catchup', '0'), ('yield', '0')]
        assert store.get_settings()['auto_start_upgraded'] == '1'
        assert store._one("SELECT UpdatedBy FROM setting WHERE Name='general_auto_enabled'")['UpdatedBy'] == 'upgrade'
        doubles['open_drains'].assert_called_once_with(store)
        assert doubles['threads'].call_count == 2  # harmless mocked poll clocks start after migration
    finally:
        store.cx.close()


def test_failed_auto_start_upgrade_aborts_before_any_intake_or_worker_admission(tmp_path):
    store = _legacy_opt_out(tmp_path / 'failed-upgrade.db')
    try:
        with _lifespan_boundaries(store) as doubles, \
             mock.patch.object(store, 'upgrade_auto_start',
                               side_effect=RuntimeError('migration failed')):

            async def enter_once():
                async with server._lifespan(None):
                    raise AssertionError('failed migration must not yield a running application')

            try:
                asyncio.run(enter_once())
            except RuntimeError as error:
                assert str(error) == 'migration failed'
            else:
                raise AssertionError('startup accepted a failed auto-start migration')

        doubles['bind'].assert_called_once()  # loop binding is side-effect free and precedes storage work
        for name in ('open_drains', 'close_drains', 'recover', 'shutdown_sessions',
                     'shutdown_children', 'bridge', 'catchup', 'heal_docs',
                     'refresh_soul', 'learn', 'watch', 'threads', 'triage_upgrade'):
            doubles[name].assert_not_called()
        assert store.get_settings()['general_auto_enabled'] == '1'
        assert not store._one(
            "SELECT UpdatedBy FROM setting WHERE Name='general_auto_enabled'")['UpdatedBy']
        assert 'auto_start_upgraded' not in store.get_settings()
    finally:
        store.cx.close()
