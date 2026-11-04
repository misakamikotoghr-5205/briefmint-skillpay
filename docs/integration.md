# Integration boundary and official sources

Verified on 2026-11-04. No merchant account, production key, platform upload, live payment, or live sandbox transaction was used to build this repository.

## SkillPay package

[SkillPay’s official site](https://skillpay.alipay.com/) describes platform-managed Skill sales. [Its upload form](https://skillpay.alipay.com/creator/product-new) accepts `.zip`, `.md`, or a folder and requires review. The generated `dist/briefmint-skill.zip` is a standard, self-contained upload candidate. Compatibility of its final listing and commercial terms still requires platform review. It is not already listed or certified. No private SkillPay payment API is invented here.

The local source is MIT licensed. A public source repository cannot protect a paid Skill’s plaintext. Evaluate pricing and distribution accordingly; this project makes no revenue or exclusivity claim.

## JSON API: documented Alipay A402 path

The optional API payment adapter is **AI 按量付费 / Machine Pay**, a distinct product from SkillPay’s marketplace. Its baseline is the [official Alipay AI repository](https://github.com/alipay/ai), commit `c4a6d8d58b906bc77e2d88a0adbc0b64e34560a5`, including:

- `skills/alipay-aipay/references/integration/modules/interface-contract/aipay-interface-contract.md`
- `skills/alipay-aipay/references/integration/modules/code-examples/python/4-按量付费/A2MPaymentDemo.md`

The official contract uses a merchant-signed `Payment-Needed` bill on HTTP 402, a buyer-supplied `Payment-Proof`, server-side verification, and fulfillment confirmation. It explicitly separates this flow from web/app checkout and asynchronous payment notifications. Accordingly, this adapter has no fabricated callback, `notify_url`, generic “mark paid” endpoint, or front-end success-page trust.

[Verification API documentation](https://aipay.alipay.com/docs/ai-receive/api-list/alipay-aipay-agent-payment-verify.md) specifies `alipay.aipay.agent.payment.verify`. BriefMint passes a model with `trade_no`, `payment_proof`, and optional `client_session`. It requires success, `active=true`, matching trade, persisted order, amount, currency, and resource binding. Missing amounts are rejected even in sandbox. The documented `resource_id` field is deprecated and may be absent in some deployments; this strict adapter fails closed if it is missing, so account-specific behavior must be verified before rollout.

[Fulfillment API documentation](https://aipay.alipay.com/docs/ai-receive/api-list/alipay-aipay-agent-fulfillment-confirm.md) specifies `alipay.aipay.agent.fulfillment.confirm` with `trade_no`. A brief is generated and persisted once, withheld until this confirmation succeeds, then marked fulfilled. Failed confirmations can be retried with the identical proof without regenerating or charging again. Exact previously verified proofs also resume after the original payment deadline.

The [official Python SDK](https://github.com/alipay/alipay-sdk-python-all) handles signed requests and verifies gateway response signatures with the configured Alipay public key. `skip_sign` is explicitly false. No SDK logger is enabled, and raw responses, keys, tokens, and proofs are omitted from API errors and audit logs.

## Modes and configuration

| Mode | Gateway and credential behavior | Headers |
| --- | --- | --- |
| `mock` (default) | Local HMAC receipts; no network, no real money | `X-BriefMint-Mock-Payment-*` only |
| `alipay-sandbox` | Official sandbox gateway, documented `api_mock_service_id`, actual sandbox merchant configuration required | Official `Payment-*` headers |
| `alipay-production` | Official production gateway, real registered service ID, required merchant configuration; sandbox ID forbidden | Official `Payment-*` headers |

Install `requirements-real.txt` only for Alipay modes. Set the fields in `.env.example` privately using your deployment’s configuration mechanism; the application does not auto-load `.env`. Keys are read only from explicitly configured files in the documented raw Base64 format. Never commit them. Missing/invalid configuration terminates startup; there is no fallback to mock. HTTP Alipay modes also require a strong `BRIEFMINT_API_KEY`.

Only the local mocked lifecycle and SDK request classes have been checked here. Before real operation, complete merchant authorization, product/service registration, key provisioning, official sandbox payment and signature tests, account-specific response checks, operational monitoring, TLS, access control, backups, reconciliation, and a documented refund procedure. The built-in server is a local development server. There is no refund implementation or production readiness claim.

## PAYATHON 2026

The [official event page](https://aipay.alipay.com/community/events/payathon-2026) distinguishes Skill Pay (AI Skills) from Machine Pay (usage-based services). It lists registration through December 1 and submission through December 9, 2026, and evaluates the product, payment integration, authentic commercialization, and user feedback. This repository supplies an original runnable prototype and an upload candidate; it does not claim registration, submission, approval, paid users, or completion of the required real commercial validation. Confirm the chosen track and current rules in the official account before submission.
