"""Exercise a running, explicitly enabled local mock API without logging secrets."""
import json
import os
import uuid
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError

BASE = 'http://127.0.0.1:8787'
HEADERS = {'Content-Type': 'application/json'}
if os.environ.get('BRIEFMINT_API_KEY'):
    HEADERS['X-BriefMint-API-Key'] = os.environ['BRIEFMINT_API_KEY']


def call(path, data=None, headers=None):
    request = Request(BASE + path, data=None if data is None else json.dumps(data).encode(),
                      headers=HEADERS | (headers or {}))
    try:
        response = urlopen(request, timeout=10)
    except HTTPError as exc:
        response = exc
    with response:
        return response.status, json.loads(response.read())


if __name__ == '__main__':
    _, health = call('/health')
    if health.get('mode') != 'mock':
        raise SystemExit('This example only exercises local mock mode. No real payment is attempted.')
    data = json.loads((Path(__file__).resolve().parents[1] / 'examples' / 'launch.json').read_text())
    status, body = call('/v1/orders', {'request': data}, {'Idempotency-Key': 'api_demo_' + uuid.uuid4().hex})
    if status != 201:
        raise SystemExit('Order creation failed; check API configuration.')
    order = body['order']
    auth = {'Authorization': 'Bearer ' + order['accessToken']}
    before, unpaid = call(order['resourceId'], headers=auth)
    assert before == 402 and 'brief' not in unpaid
    status, receipt = call('/v1/mock-payments', {'orderId': order['id']}, auth)
    if status != 200:
        raise SystemExit('Start the local server with BRIEFMINT_ENABLE_MOCK_PAYMENTS=1.')
    after, paid = call(order['resourceId'], headers=auth | {receipt['proofHeader']: receipt['proof']})
    assert after == 200 and paid['fulfillmentConfirmed']
    print(json.dumps({'mode': 'mock', 'realMoney': False, 'beforePayment': before,
                      'afterPayment': after, 'brief': paid['brief']}, ensure_ascii=False, indent=2))
