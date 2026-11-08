"""MONGODB, REDIS AND NEO4J (nosql.py, the owner 2026-11-08): each card's Test makes its cheapest read through the driver, fed the shapes the
drivers document - and each keeps the read-only promise its own way: $out / $merge refused, a closed list of Redis reads, a READ transaction."""
import json, sys, types, unittest
from unittest import mock

from taskuary import channels, nosql, reports, scopes
from taskuary.deps import Missing
from taskuary.store import MemoryStore


def card(s, t, pw='pw', **cfg):
    c = s.get_connector_by_type(t)
    s.save_connector({'ConnectorId': c['ConnectorId'], 'Active': 1, 'ConfigJson': json.dumps(cfg), 'Secret': pw}, 't')
    return c['ConnectorId']


def fake_pymongo():
    db = mock.MagicMock()
    db.list_collection_names.return_value = ['vendors', 'orders']
    col = db.__getitem__.return_value
    col.find.return_value.limit.return_value = [{'_id': 'o-1', 'total': 42}]
    col.aggregate.return_value = [{'_id': 'Northwind Supply', 'n': 3}]
    col.count_documents.return_value = 7
    cli = mock.MagicMock(); cli.__getitem__.return_value = db; cli.get_default_database.return_value = db
    return types.SimpleNamespace(MongoClient=mock.Mock(return_value=cli)), cli, col


class EveryOneIsARead(unittest.TestCase):
    def test_registered_on_their_own_cards_at_read(self):
        for t in nosql.TYPES:
            self.assertIn(t, reports.REGISTRY); self.assertEqual((reports.card_of(t), scopes.ACTIONS[t]), (t, 'read'))
            self.assertIn(t, channels.NOSQL)

    def test_mongodb_finds_aggregates_and_refuses_the_writing_stages(self):
        pm, cli, col = fake_pymongo()
        with mock.patch.dict(sys.modules, {'pymongo': pm}):
            s = MemoryStore()
            out = channels.test_connector(s, card(s, 'mongodb', conn_str='mongodb+srv://ro:{password}@cluster0.northwind.example/sales'))
            self.assertTrue(out['ok'], out); self.assertIn('2 collections', out['detail'])
            self.assertEqual(pm.MongoClient.call_args.args[0], 'mongodb+srv://ro:pw@cluster0.northwind.example/sales')
            self.assertIn('o-1', nosql.run_mongodb({'host': 'h', 'collection': 'orders', 'filter': '{"total": {"$gt": 1}}'})[1])
            self.assertIn('7 documents', nosql.run_mongodb({'host': 'h', 'collection': 'orders', 'count': True})[0])
            nosql.run_mongodb({'host': 'h', 'collection': 'orders', 'pipeline': [{'$group': {'_id': '$vendor', 'n': {'$sum': 1}}}]})
            self.assertEqual(col.aggregate.call_args.args[0][-1], {'$limit': 201})
            for bad in ([{'$out': 'copy'}], [{'$match': {}}, {'$merge': {'into': 'x'}}], [{'$facet': {'a': [{'$out': 'y'}]}}],
                        [{'$lookup': {'from': 'x', 'pipeline': [{'$merge': 'z'}], 'as': 'j'}}]):
                with self.subTest(bad=bad), self.assertRaisesRegex(PermissionError, 'only reads'):
                    nosql.run_mongodb({'host': 'h', 'collection': 'orders', 'pipeline': bad})
        self.assertEqual(col.aggregate.call_count, 1)                         # nothing refused was ever sent
        self.assertFalse({'insert_one', 'insert_many', 'update_one', 'update_many', 'delete_one', 'delete_many', 'replace_one', 'drop'}
                         & {c[0] for c in col.method_calls})

    def test_redis_sends_one_read_from_its_list_and_nothing_else(self):
        r = mock.Mock(); r.execute_command.side_effect = lambda *a: {'DBSIZE': 12, 'HGETALL': {'vendor': 'Northwind Supply'}}.get(a[0], ['a', 'b'])
        rd = types.SimpleNamespace(Redis=mock.Mock(return_value=r))
        rd.Redis.from_url = mock.Mock(return_value=r)
        with mock.patch.dict(sys.modules, {'redis': rd}):
            s = MemoryStore()
            out = channels.test_connector(s, card(s, 'redis', host='cache.northwind.example', tls='yes'))
            self.assertTrue(out['ok'], out); self.assertIn('DBSIZE', out['detail'])
            self.assertIs(rd.Redis.call_args.kwargs['ssl'], True)
            self.assertIn('Northwind Supply', nosql.run_redis({'command': 'hgetall', 'args': ['order:1']})[1])
            self.assertEqual(nosql.run_redis({'command': 'LRANGE q 0 -1'})[0], '2 values')
            for bad in ('SET a 1', 'DEL a', 'FLUSHALL', 'KEYS *', 'CONFIG SET dir /tmp', 'EVAL "return 1" 0', 'SCRIPT LOAD x', 'MULTI'):
                with self.subTest(bad=bad), self.assertRaisesRegex(PermissionError, 'not one of the reads'): nosql.run_redis({'command': bad})
        self.assertEqual([c.args[0] for c in r.execute_command.call_args_list], ['DBSIZE', 'HGETALL', 'LRANGE'])

    def test_neo4j_runs_in_a_read_transaction(self):
        rec = mock.Mock(); rec.data.return_value = {'ok': 1}
        tx = mock.Mock(); tx.run.return_value = [rec]
        sess = mock.MagicMock(); sess.__enter__.return_value = sess; sess.execute_read.side_effect = lambda f: f(tx)
        drv = mock.Mock(); drv.session.return_value = sess
        nj = types.SimpleNamespace(GraphDatabase=types.SimpleNamespace(driver=mock.Mock(return_value=drv)), READ_ACCESS='READ')
        with mock.patch.dict(sys.modules, {'neo4j': nj}):
            s = MemoryStore()
            out = channels.test_connector(s, card(s, 'neo4j', uri='neo4j+s://graph.northwind.example'))
        self.assertTrue(out['ok'], out)
        self.assertEqual(drv.session.call_args.kwargs['default_access_mode'], 'READ')
        self.assertEqual(tx.run.call_args.args[0], 'RETURN 1 AS ok'); sess.execute_write.assert_not_called()
        self.assertEqual(nj.GraphDatabase.driver.call_args.kwargs['auth'], ('neo4j', 'pw'))

    def test_a_missing_driver_names_its_extra(self):
        for t, mod in (('mongodb', 'pymongo'), ('redis', 'redis'), ('neo4j', 'neo4j')):
            with self.subTest(t=t), mock.patch.dict(sys.modules, {mod: None}), self.assertRaisesRegex(Missing, rf'taskuary\[{t}\]'):
                nosql.RUN[t]({'command': 'PING'})


if __name__ == '__main__':
    unittest.main()
