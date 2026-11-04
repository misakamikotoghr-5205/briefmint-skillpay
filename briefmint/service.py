import hashlib
import json

from .payments import PaymentError, b64encode


class Service:
    def __init__(self, store, provider):
        self.store, self.provider = store, provider

    def create(self, data, idempotency_key):
        order, created = self.store.create(data, idempotency_key, self.provider.mode)
        return self.store.public(order, include_token=True), created

    def _challenge(self, order, message='Payment is required before delivery.'):
        if order['status'] in ('PENDING_CONFIRM', 'FULFILLED'):
            return 409, {'mode': self.provider.mode, 'code': 'ORIGINAL_PROOF_REQUIRED',
                         'message': 'This order is already bound to a verified payment. Retry with the original proof; do not pay again.'}, {}
        if order['status'] == 'CANCELLED' or self.store.clock() >= order['pay_before']:
            return 410, {'mode': self.provider.mode, 'code': 'ORDER_NOT_PAYABLE', 'message': 'Order is cancelled or expired; create a new order.'}, {}
        return 402, {'mode': self.provider.mode, 'realMoney': self.provider.mode == 'alipay-production',
                     'code': 'PAYMENT_REQUIRED', 'message': message, 'order': self.store.public(order)}, {
                         self.provider.needed_header: self.provider.challenge(order)}

    def deliver(self, order_id, token, proof=None):
        order = self.store.get(order_id, token)
        if order['mode'] != self.provider.mode:
            raise PaymentError('this order was created in another payment mode')
        if not proof:
            return self._challenge(order)
        proof_hash = hashlib.sha256(proof.encode()).hexdigest()
        # Resume an already verified exact proof without another charge or generation.
        if order['status'] in ('PENDING_CONFIRM', 'FULFILLED') and order['proof_hash'] == proof_hash:
            prepared = order
        else:
            try:
                verified = self.provider.verify(proof)
                prepared = self.store.prepare(order_id, token, verified, proof_hash, self.provider.mode)
            except PaymentError:
                return self._challenge(order, 'Payment proof was rejected. No brief has been delivered.')
        replayed = prepared['status'] == 'FULFILLED'
        if not replayed:
            if not self.provider.confirm(prepared['trade_no']):
                return 502, {'mode': self.provider.mode, 'code': 'CONFIRMATION_PENDING',
                             'message': 'The brief is safely prepared. Retry with the same proof; no content is delivered before confirmation.'}, {}
            prepared = self.store.mark_fulfilled(order_id, prepared['trade_no'])
        return 200, {'mode': self.provider.mode, 'realMoney': self.provider.mode == 'alipay-production',
                     'orderId': order_id, 'fulfillmentConfirmed': True, 'replayed': replayed,
                     'brief': json.loads(prepared['result_json'])}, {
                         self.provider.validation_header: b64encode({'out_trade_no': order_id,
                             'trade_no': prepared['trade_no'], 'resource_id': prepared['resource_id'], 'validated': True})}

    def mock_pay(self, order_id, token):
        if self.provider.mode != 'mock':
            raise PaymentError('mock payment is disabled for all Alipay modes')
        order = self.store.get(order_id, token)
        if order['mode'] != 'mock' or order['status'] == 'CANCELLED' or self.store.clock() >= order['pay_before']:
            raise PaymentError('mock order is not payable')
        return {'mode': 'mock', 'realMoney': False, 'proofHeader': self.provider.proof_header,
                'proof': self.provider.mock_pay(order), 'notice': 'Synthetic local receipt. No real money moved.'}
