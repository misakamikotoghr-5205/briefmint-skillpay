"""SQLite transaction boundary for payment binding and exactly-once generation."""
import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

from .generator import normalize_request, request_hash, generate_brief
from .payments import PaymentError, amount


class StoreError(ValueError):
    pass


class Conflict(StoreError):
    pass


class Unauthorized(StoreError):
    pass


class Store:
    def __init__(self, path, clock=time.time):
        self.path, self.clock = str(path), clock
        if self.path == ':memory:':
            raise StoreError('use a persistent SQLite file, not an in-memory database')
        target = Path(self.path)
        target.parent.mkdir(parents=True, exist_ok=True)
        # Create the private ledger atomically before sqlite opens it.
        fd = os.open(target, os.O_CREAT | os.O_RDWR, 0o600)
        os.close(fd)
        os.chmod(target, 0o600)
        with self.transaction() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS orders (
                    id TEXT PRIMARY KEY, idempotency_key TEXT UNIQUE NOT NULL,
                    request_hash TEXT NOT NULL, input_json TEXT NOT NULL,
                    amount TEXT NOT NULL, currency TEXT NOT NULL,
                    resource_id TEXT NOT NULL UNIQUE, created_at REAL NOT NULL,
                    pay_before REAL NOT NULL, mode TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('PENDING_PAYMENT','PENDING_CONFIRM','FULFILLED','CANCELLED')),
                    token TEXT NOT NULL, trade_no TEXT UNIQUE,
                    proof_hash TEXT, result_json TEXT, generation_count INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS audit (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT, order_id TEXT NOT NULL,
                    event TEXT NOT NULL, details_json TEXT NOT NULL, at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            ''')
            db.execute('INSERT OR IGNORE INTO settings VALUES (?, ?)', ('mock_secret', secrets.token_hex(32)))

    @contextmanager
    def transaction(self):
        db = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        db.row_factory = sqlite3.Row
        try:
            db.execute('PRAGMA foreign_keys=ON')
            db.execute('BEGIN IMMEDIATE')
            yield db
            if db.in_transaction:
                db.execute('COMMIT')
        except Exception:
            if db.in_transaction:
                db.execute('ROLLBACK')
            raise
        finally:
            db.close()

    def _audit(self, db, order_id, event, details):
        db.execute('INSERT INTO audit(order_id,event,details_json,at) VALUES(?,?,?,?)',
                   (order_id, event, json.dumps(details, sort_keys=True), self.clock()))

    def mock_secret(self):
        with self.transaction() as db:
            return db.execute('SELECT value FROM settings WHERE key=?', ('mock_secret',)).fetchone()[0]

    def create(self, data, idempotency_key, mode='mock'):
        if not isinstance(idempotency_key, str) or not re.fullmatch(r'[A-Za-z0-9_-]{12,128}', idempotency_key):
            raise StoreError('Idempotency-Key must contain 12–128 letters, digits, hyphens or underscores')
        normalized, digest = normalize_request(data), request_hash(data)
        with self.transaction() as db:
            row = db.execute('SELECT * FROM orders WHERE idempotency_key=?', (idempotency_key,)).fetchone()
            if row:
                if row['request_hash'] != digest or row['mode'] != mode:
                    raise Conflict('idempotency key already belongs to a different request or payment mode')
                return dict(row), False
            order_id = 'bm_' + secrets.token_urlsafe(16)
            now = self.clock()
            db.execute('''INSERT INTO orders
                (id,idempotency_key,request_hash,input_json,amount,currency,resource_id,created_at,pay_before,mode,status,token)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?)''',
                (order_id, idempotency_key, digest, json.dumps(normalized, ensure_ascii=False),
                 '2.99', 'CNY', '/b/' + order_id, now, now + 1800,
                 mode, 'PENDING_PAYMENT', secrets.token_urlsafe(32)))
            self._audit(db, order_id, 'ORDER_CREATED', {'amount': '2.99', 'currency': 'CNY', 'mode': mode})
            return dict(db.execute('SELECT * FROM orders WHERE id=?', (order_id,)).fetchone()), True

    def get(self, order_id, token):
        with self.transaction() as db:
            row = db.execute('SELECT * FROM orders WHERE id=?', (order_id,)).fetchone()
            if not row or not isinstance(token, str) or not hmac.compare_digest(row['token'], token):
                raise Unauthorized('order or access token is invalid')
            return dict(row)

    @staticmethod
    def public(order, include_token=False):
        result = {'id': order['id'], 'amount': order['amount'], 'currency': order['currency'],
                  'resourceId': order['resource_id'], 'createdAt': order['created_at'],
                  'payBefore': order['pay_before'], 'status': order['status'], 'mode': order['mode'],
                  'realMoney': order['mode'] == 'alipay-production'}
        if include_token:
            result['accessToken'] = order['token']
        return result

    def prepare(self, order_id, token, verified, proof_hash, mode):
        if not isinstance(verified, dict) or verified.get('active') is not True:
            raise PaymentError('payment is not active')
        with self.transaction() as db:
            row = db.execute('SELECT * FROM orders WHERE id=?', (order_id,)).fetchone()
            if not row or not hmac.compare_digest(row['token'], token):
                raise Unauthorized('order or access token is invalid')
            order = dict(row)
            if order['mode'] != mode:
                raise PaymentError('payment mode does not match the persisted order')
            if (verified.get('out_trade_no') != order_id or verified.get('resource_id') != order['resource_id']
                    or verified.get('currency') != 'CNY' or amount(verified.get('amount')) != order['amount']):
                raise PaymentError('payment amount, currency, order or resource binding rejected')
            trade_no = verified.get('trade_no')
            if not isinstance(trade_no, str) or not trade_no or len(trade_no) > 128:
                raise PaymentError('verified trade number is missing or invalid')
            if order['status'] == 'CANCELLED':
                raise PaymentError('order has been cancelled')
            if order['status'] in ('PENDING_CONFIRM', 'FULFILLED'):
                if order['trade_no'] != trade_no or order['proof_hash'] != proof_hash:
                    raise PaymentError('order already bound to a different verified payment proof')
                return order
            if self.clock() >= order['pay_before']:
                raise PaymentError('order payment deadline has passed')
            if db.execute('SELECT id FROM orders WHERE trade_no=?', (trade_no,)).fetchone():
                raise PaymentError('trade has already been used for another order')
            result = generate_brief(json.loads(order['input_json']))
            db.execute('''UPDATE orders SET status='PENDING_CONFIRM',trade_no=?,proof_hash=?,
                          result_json=?,generation_count=generation_count+1 WHERE id=?''',
                       (trade_no, proof_hash, json.dumps(result, ensure_ascii=False, sort_keys=True), order_id))
            self._audit(db, order_id, 'PAYMENT_VERIFIED', {'tradeReference': hashlib.sha256(trade_no.encode()).hexdigest()[:16]})
            self._audit(db, order_id, 'BRIEF_PREPARED', {'inputSha256': order['request_hash']})
            return dict(db.execute('SELECT * FROM orders WHERE id=?', (order_id,)).fetchone())

    def mark_fulfilled(self, order_id, trade_no):
        with self.transaction() as db:
            row = db.execute('SELECT * FROM orders WHERE id=?', (order_id,)).fetchone()
            if not row or row['trade_no'] != trade_no or row['status'] not in ('PENDING_CONFIRM', 'FULFILLED'):
                raise Conflict('cannot confirm an unprepared or differently bound order')
            if row['status'] == 'PENDING_CONFIRM':
                db.execute("UPDATE orders SET status='FULFILLED' WHERE id=?", (order_id,))
                self._audit(db, order_id, 'FULFILLMENT_CONFIRMED', {})
            return dict(db.execute('SELECT * FROM orders WHERE id=?', (order_id,)).fetchone())

    def cancel(self, order_id, token):
        self.get(order_id, token)
        with self.transaction() as db:
            row = db.execute('SELECT * FROM orders WHERE id=?', (order_id,)).fetchone()
            if row['status'] in ('PENDING_CONFIRM', 'FULFILLED'):
                raise Conflict('a verified payment cannot be locally cancelled; reconcile with the provider')
            if row['status'] != 'CANCELLED':
                db.execute("UPDATE orders SET status='CANCELLED' WHERE id=?", (order_id,))
                self._audit(db, order_id, 'ORDER_CANCELLED', {})
            return dict(db.execute('SELECT * FROM orders WHERE id=?', (order_id,)).fetchone())

    def audit(self, order_id, token):
        self.get(order_id, token)
        with self.transaction() as db:
            return [{'seq': row['seq'], 'event': row['event'], 'details': json.loads(row['details_json']), 'at': row['at']}
                    for row in db.execute('SELECT * FROM audit WHERE order_id=? ORDER BY seq', (order_id,))]
