"""A send the channel refused before anything went is NOT SENT, never "delivery unknown" (the owner, 2026-11-08: a WhatsApp reply read
"Delivery has not been confirmed - Check delivery" when the bridge had answered 503 {"error":"not connected to WhatsApp"})."""
import requests
from taskuary import outbound


def test_a_503_or_not_connected_was_refused_before_anything_went():
    for e in (RuntimeError('bridge /send failed (503): {"error":"not connected to WhatsApp"}'),
              RuntimeError('signal-cli: account not linked'), requests.exceptions.ConnectionError('Connection refused')):
        assert outbound.refused_before_send(e) and not outbound.delivery_uncertain(e), e

def test_a_real_maybe_stays_unknown():
    for e in (requests.exceptions.Timeout('read timed out'), RuntimeError('graph send failed (502): bad gateway'),
              outbound.UncertainDelivery('1 message part(s) were sent before a later part failed: not connected')):
        assert outbound.delivery_uncertain(e), e
