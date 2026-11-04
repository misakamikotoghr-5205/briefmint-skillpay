# BriefMint · 有凭据的项目 Brief

把目标、受众、交付范围和已知事实整理成可交接的项目 Brief，附事实来源、验收标准、执行步骤和待决问题。提供 Python CLI、JSON API，以及可打包的标准 Skill。没有网站。

默认完全本地运行：确定性规则生成内容，模拟支付收据测试付费交付流程，**不调用 LLM、不真实收款**。Analyst、Skeptic、Editor 是三个可审计规则角色。API 的可选支付宝适配器采用官方 A402 按量付费协议；没有虚构 SkillPay 私有接口，也未声称完成商户开通、真实沙箱联调或平台审核。

## 30 秒运行

需要 Python 3.10+。默认演示没有第三方依赖。

```bash
python3 -m briefmint --db /tmp/briefmint-demo.sqlite3 demo --input examples/launch.json
```

输出 `beforePayment: 402`、`afterPayment: 200`、`idempotentReplay: true`，以及完整 JSON / Markdown Brief 和脱敏事件账本。示例里的店铺资料均为虚构输入。将 JSON 换成自己的材料即可；缺失证据会生成待确认项，不会补造市场数据。

## 本地 JSON API

```bash
BRIEFMINT_ENABLE_MOCK_PAYMENTS=1 python3 -m briefmint serve
```

在另一个终端运行：

```bash
python3 scripts/api_demo.py
```

这会实际请求本地 API，验证未支付时不返回 Brief，然后使用明确标注的模拟收据完成交付。模拟支付端点默认关闭，只能在本地、mock 模式且明确开启后使用。启动时不会发起交易。

| 接口 | 输入 / 结果 |
| --- | --- |
| `GET /health` | 模式与生成器说明，不含配置 |
| `GET /v1/catalog` | 服务端固定商品价格：演示价格 CNY 2.99 |
| `POST /v1/orders` | `{"request": {...}}`，必须带 `Idempotency-Key`；返回订单与私有 `accessToken` |
| `GET /b/{orderId}` | 带订单 Bearer token；无有效支付凭据返回 402，有效且确认履约后返回 Brief |
| `GET /v1/orders/{id}` | 带订单 token，查询公有状态，不含原始输入、凭据或内容 |
| `GET /v1/orders/{id}/audit` | 带订单 token，查看脱敏事件 |
| `POST /v1/orders/{id}/cancel` | 带订单 token 和空 JSON；只能取消尚未验付的订单 |
| `POST /v1/mock-payments` | 仅显式启用的本地 mock；`{"orderId":"..."}` + 订单 token |

创建订单请求示例：

```json
{
  "request": {
    "title": "Refill shop launch",
    "audience": "Owner and designer",
    "objective": "Explain how customers can refill their containers",
    "deliverables": ["An A4 poster"],
    "constraints": ["No unsupported environmental claims"],
    "facts": [{"text": "Clean containers are accepted.", "source": "Owner policy"}]
  }
}
```

`Idempotency-Key` 需为 12–128 位字母、数字、连字符或下划线；建议使用随机 UUID，并与 token 一样保密。相同 key 和输入恢复同一订单，不同输入返回 409。金额由服务端决定，客户端传价格会被拒绝。订单 token 放在 `Authorization: Bearer ...`，不放 URL。配置全局 API key 时另带 `X-BriefMint-API-Key`。

## 交付与恢复

```text
PENDING_PAYMENT → 验付与事务内绑定 → PENDING_CONFIRM → 平台确认成功 → FULFILLED
       └─ 可取消 / 过期不交付            └─ 同凭据重试，不重复生成
```

SQLite 使用事务和唯一约束：验证签名、金额、CNY、订单、资源、有效状态与交易唯一性后才生成并保存内容；确认失败返回 502 且不暴露内容。同一已验证凭据可在截止时间之后恢复确认，已完成订单只返回保存结果。并发重试只生成一次。账本文件权限为 0600；审计不记录原始 token、proof、密钥或 SDK 异常正文。

源码采用 MIT，用户可以直接调用本地生成器。付费隔离属于托管 API 的交付边界，不是对公开源码的加密或数字版权保护。

## 官方适配与 SkillPay 上架

[集成说明](docs/integration.md) 逐项标注官方来源、协议字段、SDK 版本、测试边界和未完成事项。SkillPay 管理 Skill 商品购买/交付；本项目 JSON API 采用单独的 Alipay AI 按量付费 / Machine Pay 协议。选择参赛赛道时应按实际交付形态核验。

```bash
python3 scripts/package_skill.py
```

生成 `dist/briefmint-skill.zip`：含 `SKILL.md`、运行代码、示例与集成说明，能够在仓库外独立运行。它是待人工审核的上传候选，尚未发布、认证或收费。平台产品协议、定价、安全审核和上架需在有权操作的商户会话中完成。

真实配置必须显式选择 `alipay-sandbox` 或 `alipay-production` 并安装 `requirements-real.txt`。按 [.env.example](.env.example) 私下配置商户、服务 ID 和密钥文件。配置缺失、模式拼写错误或生产使用沙箱服务 ID 都会终止启动，不回退到 mock。默认 mock 使用 `X-BriefMint-Mock-Payment-*`，不会生成能被真实钱包识别的账单。

内置 HTTP server 用于本地开发。没有上线、退款或真实支付验收结论；生产前需要官方联调及部署、TLS、访问控制、备份、对账与退款流程。

## 验证

```bash
sh scripts/verify.sh
```

本地测试覆盖未支付拒绝交付、篡改签名、错金额/币种/订单/资源、过期/取消、交易重复使用、幂等与并发、确认失败恢复、持久化、HTTP 授权和自包含 Skill 包。可选 SDK 测试使用官方 request/model 类和客户端替身，默认未安装 SDK 时跳过；它们不产生支付。没有配置 GitHub Actions，也没有 CI 或真实支付通过声明。

详见 [PAYATHON 2026 官方页面](https://aipay.alipay.com/community/events/payathon-2026)。本仓库没有替用户报名或提交作品。
