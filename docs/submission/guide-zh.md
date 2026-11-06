# BriefMint 国内投稿材料与最短下一步

材料整理于 2026-11-06。只补已有原型的中文字段、真实离线演示附件与上传清单；未登录、签约、上架、录屏或报名。

## 最小实际入口

1. [PAYATHON 官方赛事页](https://aipay.alipay.com/community/events/payathon-2026)：点击报名，以本人支付宝登录。已有完整产品前也可报名，但不能把报名算作品提交。
2. **若选择 Skill Pay 主赛道：**进入[官方商品上架页](https://skillpay.alipay.com/creator/product-new)，使用同一合格支付宝账户。先核对商品/售卖设定与协议，再上传候选包并等待审核。
3. **若选择 Machine Pay：**现有 JSON API 才对应[按量付费产品](https://aipay.alipay.com/products/machine-pay)。需真实服务开通、可访问部署与付款/交付验证；不能用 SkillPay 上架替代。

同一作品不能跨赛道重复投稿。报名截止 **2026-12-01 23:59:59 北京时间**，作品截止 **12-09 23:59:59 北京时间**，12/26 线下决赛。身份、账户绑定及条款以[官方细则](https://render.alipay.com/p/yuyan/180022670000190962/index.html)最终核对：支付宝需绑定手机号并以合格身份完成实人认证，港澳台/外籍实名当前不能报名；报名账户与 AI 付接入账户须相同。常住中国不能替代这些账户条件。

## 已备材料，直接复用

| 材料 | 位置 / 本轮实查 |
| --- | --- |
| 中英文名称与介绍 | [现有投稿稿](../submission-draft.md)，新增中文商品描述；无须重新起草 |
| Skill 上传候选 | `dist/briefmint-skill.zip`，22,852 bytes；包内 `briefmint/SKILL.md` 及运行代码与当前源文件逐项相符 |
| 文件校验与运行证据 | [offline-demo-20261106.json](offline-demo-20261106.json)，含完整包 SHA-256、条目检查与实际 CLI 结果 |
| 可展示交付物 | [brief-sample.md](brief-sample.md)，实际规则生成的虚构小店 Brief |
| 缺材料示例 | [preflight-missing-input.json](preflight-missing-input.json)，实际 strict 预检返回退出码2、4项警告，不建订单、不生成 Brief |
| 真实协议边界 | [integration.md](../integration.md)，区分 SkillPay 与 Machine Pay |

包格式兼容性和商品能力仍须平台审核；“本地文件相符”不是平台认证。既有包未重打，以免产生无意义的重复版本。

## 约90秒的录屏备选脚本

这是备选演示长度，不是已核实的官方视频时长要求，也不是成片。保持画面标题 **本地规则生成 / 模拟支付 / 无真实收款**。在项目根目录运行；只用虚构样例，账本用新的临时目录。

```sh
python3 -m briefmint preflight --input docs/submission/preflight-missing-input.json --strict
# 预期退出2：材料待补，不代表程序崩溃。
python3 -m briefmint preflight --input examples/launch.json --strict
briefmint_demo_dir=$(mktemp -d)
BRIEFMINT_PAYMENT_MODE=mock python3 -m briefmint --db "$briefmint_demo_dir/demo.sqlite3" demo --input examples/launch.json
```

| 画面 | 旁白与实际可见结果 |
| --- | --- |
| 0:00–0:25，缺材料预检 | “先指出缺口再决定是否继续。”本轮4项警告；没有创建订单或付款。 |
| 0:25–0:40，完整材料预检 | “材料结构与来源标签齐备不等于事实已经被验证。”本轮0项阻断/警告，仍需所有者审阅。 |
| 0:40–1:05，模拟交付摘要 | 指出 `beforePayment=402`、`afterPayment=200`、`idempotentReplay=true`。明确使用合成收据，没有支付宝交易。 |
| 1:05–1:30，样例交付物 | 展示2条来源、3项交付范围、验收清单与待决问题；三个角色均为确定性规则。 |

优先展示已脱敏的运行记录与样例；现场运行 CLI 后也不要转而展示账本、订单令牌或支付 proof。当前没有网站界面，不制作假平台截图。

## 上传前还缺什么

- **最先要确认：**本人可用于报名和 AI 付的同一支付宝账户，手机号/实人认证资格；选择一个赛道和真实商品/服务方案。联系邮箱、昵称、头像等只填官方表单，不写入公共仓库。
- **Skill Pay：**本人确定买断或订阅及价格/试用方案。公开页提示售卖模式选择后不能更改；完成 SkillPay、AI按量付费、即刻收所需协议和审核，取得实际商品链接。开源 MIT 与离线可运行能力须如实说明。
- **Machine Pay：**实际商户/服务开通、密钥配置、官方沙箱联调、可访问部署、真实验付/履约记录；现有 mock 不能代替。当前不具备这些事实，不能填真实付费用户或交易额。
- **最终参评：**按登录后实际表单补作品与运行入口，保持评审期间可用；本人核对最终规则、授权和材料后正式提交并保存回执。商品上架与赛事提交分别确认。

本轮无外部账号可做的材料已补齐；真实账户身份、协议选择及支付上线无法由离线附件补造。
