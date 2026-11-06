# BriefMint — submission text candidate

Prepared 2026-11-06. This file is a draft, not a registration, listing, accepted agreement, payment record, or submitted entry. Enter personal and merchant details only in the official account, never in this repository.

## Product name

BriefMint — evidence-backed creative briefs with a payment gate

## Short description

BriefMint turns a structured launch request and user-provided source notes into a reviewable creative brief. A free preflight identifies missing inputs and source gaps before the buyer commits. The API releases a persisted brief only after payment verification and fulfillment confirmation succeed.

## Problem and value

Small teams often pay for a creative deliverable before discovering that the input lacks an audience, constraints, or evidence. BriefMint exposes these gaps first, then binds payment to one order, resource, amount and currency. Confirmation failures can resume with the original proof without creating a second deliverable or inviting a second payment. The work is intended to demonstrate a usable commercial workflow, not to claim sales or unique invention of paid Skills.

## What can be demonstrated now

- Local free preflight, three bounded drafting roles, source references, and an auditable brief.
- Offline mock order/payment/confirmation and adversarial proof rejection.
- A self-contained Skill package at `dist/briefmint-skill.zip` and an optional official-SDK Alipay adapter.

Run `sh scripts/verify.sh` and the README's local demo before recording. Use only fictional sample inputs. The current draft uses deterministic local roles; it does not claim a live language-model call.

## Track decision required before submission

The [official PAYATHON page](https://aipay.alipay.com/community/events/payathon-2026) distinguishes Skill Pay from Machine Pay. Choose one track for this work; the same work must not be submitted to multiple tracks. The Skill ZIP is a marketplace upload candidate. The API's A402 integration is the separate Machine Pay product. Neither a mock receipt nor a GitHub repository proves a live payment integration.

The official rules use Beijing time: registration ends December 1 at 23:59:59, submission December 9 at 23:59:59, 2026. The registrant's Alipay account must be phone-bound, identity-verified using an eligible mainland identity, and the same account used for the product's AI Pay integration. The rules currently exclude Hong Kong, Macao, Taiwan and foreign verification identities. Supply private contact and account details only in the official form; minors require guardian consent. A deployed, accessible application and a genuine payment/delivery chain are required.

For Skill Pay, the account owner must choose the actual sale mode and price, review the platform's agreements, upload at [SkillPay product creation](https://skillpay.alipay.com/creator/product-new), and retain the actual review/listing result. Do not invent a price here: the public source is MIT and that fact must be disclosed in the offering.

## Incomplete external evidence

No verified merchant/service onboarding, real sandbox transaction, production payment, paid user, SkillPay listing, platform approval or event registration is claimed. Record only actual outcomes after the account owner completes them. `docs/integration.md` states the implemented protocol and remaining operational boundaries.

Repository: https://github.com/misakamikotoghr-5205/briefmint-skillpay

License: MIT. AI assistance: built and reviewed with coordinated Codex agents; no fabricated provider or platform usage.

## 中文商品字段候选

名称：**BriefMint｜带证据清单的项目交接 Brief**

描述候选（适用于待审稿，需与实际售卖范围一致）：

> 把目标、受众、交付物、约束及自有事实整理成可交接的项目 Brief。先免费预检材料缺口与来源标签，再输出范围、验收标准、风险和待确认问题。内置生成器为本地确定性规则，不调用大模型或替你验证事实；可选托管 API 有验付与履约确认门禁。源码 MIT 公开，Skill 包可离线运行；托管支付能力仍需商户实际接入与验证。

买断/订阅、价格、免费试用、售后承诺与实际交付范围由账号持有人确定；示例 API 的 2.99 元不是已确定的 SkillPay 商品定价。没有虚构用户量、交易额、上架链接或平台通过记录。

本轮新增的[中文操作与演示清单](submission/guide-zh.md)、[实际离线运行记录](submission/offline-demo-20261106.json)和[生成 Brief 样例](submission/brief-sample.md)可用于准备投稿；已有英文说明不重复另写。
