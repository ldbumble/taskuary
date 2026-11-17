import unittest
from unittest import mock
from loguru import logger
from taskuary import logs


class TestLogs(unittest.TestCase):
    def tearDown(self): logger.remove()

    def test_a_data_folder_the_log_cannot_open_never_stops_the_app(self):
        """A Windows computer's data folder existed, yet the log's makedirs refused it and the app died before its window."""
        real, paths = logger.add, []
        def add(sink, **kw):
            if not hasattr(sink, 'write'):
                paths.append(str(sink))
                if len(paths) == 1: raise FileExistsError(183, 'Cannot create a file when that file already exists')
            return real(sink, **kw)
        with mock.patch.object(logger, 'add', side_effect=add): logs.setup()
        self.assertEqual(len(paths), 2)
        self.assertNotEqual(paths[0], paths[1], 'the log moved to the temp folder')
        # ...and everything that names the log names THAT file (2026-11-17: sent to the data folder's, two months stale)
        self.assertEqual(logs.where(), paths[1])
        from fastapi.testclient import TestClient
        from taskuary import server
        self.assertEqual(TestClient(server.app).get('/api/version').json()['log'], paths[1])


if __name__ == '__main__': unittest.main()
