import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).parents[1] / 'app'))
from engine import notify

BASE = {'telegram_token': 'synthetic', 'telegram_chat_id': '-1002348762774',
        'telegram_topic_id': '4879'}


def test_invalid_routes_do_not_construct_http_client(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('HTTP must not be reached')
    monkeypatch.setattr(notify.httpx, 'AsyncClient', forbidden)
    for patch in ({'telegram_chat_id': '123'}, {'telegram_chat_id': '-42'},
                  {'telegram_topic_id': ''}, {'telegram_topic_id': '1'},
                  {'telegram_topic_id': '9999'}, {'telegram_topic_id': True},
                  {'telegram_topic_id': '4879.0'}):
        assert asyncio.run(notify._send_telegram('test', {**BASE, **patch})) is False


def test_approved_route_and_api_failure(monkeypatch):
    requests = []
    reply = {'ok': True, 'result': {'message_id': 42}}
    class Client:
        def __init__(self, **kw): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def post(self, url, json):
            requests.append(json)
            return SimpleNamespace(status_code=200, json=lambda: reply)
    monkeypatch.setattr(notify.httpx, 'AsyncClient', Client)
    assert asyncio.run(notify._send_telegram('test', BASE)) is True
    assert requests[0]['message_thread_id'] == 4879
    assert requests[0]['chat_id'] == '-1002348762774'
    reply['ok'] = False
    assert asyncio.run(notify._send_telegram('test', BASE)) is False
    assert len(requests) == 2  # no retries or alternate destinations
    reply['ok'] = True
    for invalid in (0, -1, True, None):
        reply['result']['message_id'] = invalid
        assert asyncio.run(notify._send_telegram('test', BASE)) is False


def test_test_button_does_not_claim_rejected_telegram_delivery(monkeypatch):
    cfg = {**BASE, 'telegram_topic_id': '', 'telegram_enabled': True, 'toast_enabled': False}
    result = asyncio.run(notify.send_test(cfg))
    assert not result.startswith('Enviado:')
