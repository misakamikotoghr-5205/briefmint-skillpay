---
name: briefmint
description: Turn a project objective, audience, deliverables, constraints, and supplied facts into a source-bounded project brief with acceptance criteria. Use for creative or product handoffs, including evaluation of the bundled payment-gated API. Excludes external research and legal or financial advice.
---

Produce a brief whose claims can be traced to the user’s materials. The bundled generator is deterministic; disclose that it does not call an LLM or research the web.

Collect `title`, `audience`, and `objective`. Add optional `deliverables` and `constraints` arrays, plus `facts` as objects with `text` and optional `source`. Do not fill missing evidence with invented numbers, market claims, or customer testimony. Missing optional information becomes an open decision in the result.

Save the input as JSON in the user’s chosen workspace. The self-contained archive puts the executable at `scripts/run.py`. Resolve that path relative to this skill, then run:

```text
python3 <skill-dir>/scripts/run.py --db <private-ledger-path> demo --input <input-json-path>
```

This local evaluation uses a clearly labeled synthetic payment receipt; it never makes a real payment. Read the JSON output, confirm `beforePayment=402`, `afterPayment=200`, and `idempotentReplay=true`, then deliver the brief’s Markdown and explain any open decisions. Preserve its evidence attribution and generator disclosure. Avoid showing private order tokens or payment proofs.

For a hosted paid service or merchant setup, read [the integration boundary](references/integration.md). The API’s real adapter implements the official Alipay A402 protocol; it is separate from SkillPay’s platform-managed Skill purchase. Do not invent private SkillPay endpoints or claim a mock run proves platform purchase, certification, commercial readiness, or real revenue. SkillPay listing, agreements, security review, and pricing happen in the merchant’s authorized platform session.

If a live A402 service requests payment, show the actual merchant, product, amount, and payment terms and use the official buyer payment flow in the target Agent. A local mock receipt never satisfies a live payment. Only complete delivery after the server verifies the actual proof and confirms fulfillment.
