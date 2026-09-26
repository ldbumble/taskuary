"""The API speaks pydantic v2.

We require `pydantic>=2`, but v1's accessors still answer through a deprecation shim: every
`body.dict()` in the API logged `PydanticDeprecatedSince20` on each request, and the method is
gone in v3. `server.py` was the last place that called it - ten times, all on request bodies.
This test is the lock, so the eleventh does not arrive quietly.
"""
import pathlib
import re
import unittest

SERVER = pathlib.Path(__file__).resolve().parent.parent / 'taskuary' / 'server.py'
V1_DICT = re.compile(r'\.dict\(\s*\)')


class NoPydanticV1Tests(unittest.TestCase):
    def test_the_api_does_not_call_the_v1_dict(self):
        hits = [f'  server.py:{n}: {line.strip()}'
                for n, line in enumerate(SERVER.read_text(encoding='utf-8').splitlines(), 1)
                if V1_DICT.search(line)]
        self.assertEqual(hits, [], 'pydantic v1 `.dict()` is back - use `.model_dump()`:\n' + '\n'.join(hits))


if __name__ == '__main__': unittest.main()
