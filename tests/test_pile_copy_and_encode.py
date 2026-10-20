"""The pile's cheaper copy and encode must be invisible: the same tree as copy.deepcopy, the same bytes as JSONResponse."""
import copy, json
from datetime import datetime

from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from taskuary.funnel_presentation import detach


def _tree():
    shared = {'key': 'msg:1', 'who': 'Erin Blake', 'tags': ['a', 'b']}
    return {'items': [shared, {'key': 'msg:2', 'kids': [shared], 'n': 2, 'f': 1.5, 'ok': True, 'none': None}],
            'alerts': [shared], 'set': {3, 1}, 'tup': (1, [2]), 'when': datetime(2026, 10, 20, 7, 30), 'ü': 'naïve'}


def test_detach_is_deepcopy():
    t = _tree(); a, b = detach(t), copy.deepcopy(t)
    assert a == b and a is not t
    assert a['items'][0] is a['items'][1]['kids'][0] is a['alerts'][0]       # shared stays shared, as deepcopy keeps it
    assert a['items'][0] is not t['items'][0] and a['items'][0]['tags'] is not t['items'][0]['tags']
    a['items'][0]['who'] = 'Gail Moreno'
    assert t['items'][0]['who'] == 'Erin Blake' and a['alerts'][0]['who'] == 'Gail Moreno'


def test_encoded_is_jsonresponse_byte_for_byte():
    from taskuary import server
    for v in (_tree(), {'items': [], 'rev': 'x:0:0'}, {'emoji': '✓ done', 'big': 10 ** 20, 'neg': -0.0}):
        r = server._encoded(v)
        assert r.body == JSONResponse(jsonable_encoder(v)).body
        assert r.media_type == 'application/json' and r.status_code == 200


def test_encoded_refuses_what_jsonresponse_refuses():
    from taskuary import server
    import pytest
    with pytest.raises(ValueError): server._encoded({'x': float('nan')})
    with pytest.raises(ValueError): JSONResponse(jsonable_encoder({'x': float('nan')}))
