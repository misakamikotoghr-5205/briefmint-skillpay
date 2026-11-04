import argparse
import ipaddress
import json
import os
import secrets
import sys
from pathlib import Path

from .http_api import make_server
from .payments import MockProvider, AlipayProvider, ConfigurationError, PaymentError
from .service import Service
from .store import Store, StoreError
from .generator import InputError


def create_service(db, environ=None):
    env = os.environ if environ is None else environ
    mode = env.get('BRIEFMINT_PAYMENT_MODE', 'mock')
    if mode not in ('mock', 'alipay-sandbox', 'alipay-production'):
        raise ConfigurationError('unknown payment mode; no fallback to mock is allowed')
    # Validate real configuration before touching the local ledger.
    provider = AlipayProvider(env) if mode != 'mock' else None
    store = Store(db)
    return Service(store, provider or MockProvider(store.mock_secret()))


def main(argv=None):
    parser = argparse.ArgumentParser(description='BriefMint — payment-gated deterministic project briefs')
    parser.add_argument('--db', default='var/briefmint.sqlite3', help='private SQLite ledger path')
    sub = parser.add_subparsers(dest='command', required=True)
    serve = sub.add_parser('serve', help='run the local JSON API')
    serve.add_argument('--host', default='127.0.0.1')
    serve.add_argument('--port', type=int, default=8787)
    for name in ('demo', 'create'):
        command = sub.add_parser(name)
        command.add_argument('--input', required=True, help='JSON request file')
        if name == 'create':
            command.add_argument('--idempotency-key', required=True)
    for name in ('status', 'deliver', 'mock-pay', 'audit', 'cancel'):
        command = sub.add_parser(name)
        command.add_argument('--order', required=True)
        command.add_argument('--token-file', required=True, help='file containing the private order access token')
        if name == 'deliver':
            command.add_argument('--proof-file')
    args = parser.parse_args(argv)
    try:
        service = create_service(args.db)
        if args.command == 'serve':
            api_key = os.environ.get('BRIEFMINT_API_KEY', '')
            try:
                local = ipaddress.ip_address(args.host).is_loopback
            except ValueError:
                local = args.host == 'localhost'
            if not local and (os.environ.get('BRIEFMINT_ALLOW_REMOTE') != '1' or len(api_key) < 32):
                raise ConfigurationError('remote bind requires explicit BRIEFMINT_ALLOW_REMOTE=1 and a strong API key')
            server = make_server((args.host, args.port), service, api_key=api_key,
                                 enable_mock_payments=os.environ.get('BRIEFMINT_ENABLE_MOCK_PAYMENTS') == '1')
            print(json.dumps({'listening': f'http://{args.host}:{server.server_port}', 'mode': service.provider.mode,
                              'notice': 'Local mock mode: no real money moves.' if service.provider.mode == 'mock' else 'Official A402 adapter configured; no live transaction is performed at startup.'}), flush=True)
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                pass
            finally:
                server.server_close()
            return 0
        if args.command in ('demo', 'create'):
            data = json.loads(Path(args.input).read_text())
            if args.command == 'demo' and service.provider.mode != 'mock':
                raise ConfigurationError('demo is available only in mock mode and never makes a real payment')
            order, created = service.create(data, args.idempotency_key if args.command == 'create' else 'demo_' + secrets.token_hex(12))
            if args.command == 'create':
                output = {'order': order, 'created': created, 'notice': 'Keep accessToken private.'}
            else:
                status_before, before, _ = service.deliver(order['id'], order['accessToken'])
                receipt = service.mock_pay(order['id'], order['accessToken'])
                status_after, after, _ = service.deliver(order['id'], order['accessToken'], receipt['proof'])
                status_repeat, repeat, _ = service.deliver(order['id'], order['accessToken'], receipt['proof'])
                assert status_before == 402 and 'brief' not in before
                assert status_after == status_repeat == 200 and after['brief'] == repeat['brief']
                output = {'mode': 'mock', 'realMoney': False, 'beforePayment': status_before,
                          'afterPayment': status_after, 'idempotentReplay': repeat['replayed'],
                          'order': {key: value for key, value in order.items() if key != 'accessToken'},
                          'brief': after['brief'], 'audit': service.store.audit(order['id'], order['accessToken'])}
        else:
            token = Path(args.token_file).read_text().strip()
            if args.command == 'status':
                output = service.store.public(service.store.get(args.order, token))
            elif args.command == 'mock-pay':
                output = service.mock_pay(args.order, token)
            elif args.command == 'audit':
                output = {'events': service.store.audit(args.order, token)}
            elif args.command == 'cancel':
                output = service.store.public(service.store.cancel(args.order, token))
            else:
                proof = Path(args.proof_file).read_text().strip() if args.proof_file else None
                status, body, headers = service.deliver(args.order, token, proof)
                output = {'status': status, 'headers': headers, 'body': body}
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return 0
    except (ConfigurationError, PaymentError, StoreError, InputError, OSError, ValueError) as exc:
        print(json.dumps({'error': type(exc).__name__, 'message': str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
