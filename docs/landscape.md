# 已有产品、开源对照与本次改进

核查日期：2026-11-04。阅读了下列官方页面及仓库 README、LICENSE；比较的是公开可验证能力，没有登录产品账户进行体验，也没有把源码可见等同于开源许可。

## 这项创意哪些已经存在

写项目 Brief、用模板整理需求、先澄清再交付、验付后发放数字内容都已有实现。本项目不是这些概念的首创，也不是下列项目的 fork。

| 对照 | 已存在的相关能力 | BriefMint 当前差距 | 值得保留或借鉴的方向 |
| --- | --- | --- | --- |
| [ChatPRD 官方模板](https://www.chatprd.ai/docs/included-templates)、[产品说明](https://www.chatprd.ai/docs/what-is-chatprd) | 专门的产品文档工作区，含 PRD、开发 Brief、功能规格等模板 | 没有对话式文档修订、知识库、团队协作或模型推理；模板生成质量不应与完整产品等同 | 借鉴在形成交接文档前明确上下文与缺口的流程；保留本地、来源受限、可重现的窄用途 |
| [GitHub Spec Kit README](https://github.com/github/spec-kit/blob/38c40ae25a4f1c025e1a2dd6a450095d17acab47/README.md) | 规范、澄清、检查清单和一致性分析，连接编码 Agent 的实施流程 | BriefMint 只产出前期交接 Brief，不生成完整软件项目或维护开发生命周期 | 把“材料是否足以继续”作为可执行步骤；不照搬其完整框架或命令体系 |
| [ACT README](https://github.com/antgroup/ACT/blob/ad8a9428fff2b7e025be1f1e8b9bc40b8e224a49/README.md)、[卖方参考](https://github.com/antgroup/ACT/blob/ad8a9428fff2b7e025be1f1e8b9bc40b8e224a49/integrations/alipay/seller-java/README.md) | A402 交易/信任协议、支付证明校验与支付宝卖方样例 | 本项目未完成真实商户/沙箱联调，也没有完整 ACT 身份、授权、对账与退款能力 | 保留本地持久化、原子生成与幂等恢复；协议能力不能由 mock 成功冒充 |
| [Alipay AI README](https://github.com/alipay/ai/blob/c4a6d8d58b906bc77e2d88a0adbc0b64e34560a5/README.md) | 官方支付开发 Skill 与接入合同 | 这是支付接入资料，不是 Brief 产品；本项目只是按文档适配，非官方产品 | 继续采用已核实 A402 验付/履约确认接口，避免编造 SkillPay API |

## 版本、许可证与采用方式

| 来源 | 本次核查版本 / 许可 | 采用方式 |
| --- | --- | --- |
| ChatPRD | 官方网页，访问日如上；未见该产品的开源实现授权，不能视作 MIT 软件 | 仅比较公开产品流程；不复制模板正文、界面或代码 |
| `github/spec-kit` | commit `38c40ae25a4f1c025e1a2dd6a450095d17acab47`；[MIT LICENSE](https://github.com/github/spec-kit/blob/38c40ae25a4f1c025e1a2dd6a450095d17acab47/LICENSE) | 借鉴检查/澄清阶段的设计，预检规则和实现独立编写；未安装、复制或 fork |
| `antgroup/ACT` | commit `ad8a9428fff2b7e025be1f1e8b9bc40b8e224a49`；README 标明代码 [Apache-2.0](https://github.com/antgroup/ACT/blob/ad8a9428fff2b7e025be1f1e8b9bc40b8e224a49/LICENSE)，协议文档 CC BY 4.0 | 仅作协议与工程边界对照，未复制其实现；本次未改动支付合同 |
| `alipay/ai` | commit `c4a6d8d58b906bc77e2d88a0adbc0b64e34560a5`；核查的根目录未提供 LICENSE | 仅依据官方接口合同独立实现适配，不把整个公开仓库当作可任意再许可的代码库 |

也检查了 [GPT Pilot](https://github.com/Pythagora-io/gpt-pilot/tree/9b763fdaf0020c7d8abacc7b58b2b09e57494623) 的需求澄清流程；该版本 [LICENSE](https://github.com/Pythagora-io/gpt-pilot/blob/9b763fdaf0020c7d8abacc7b58b2b09e57494623/LICENSE) 为 **FSL-1.1-MIT / MIT Future License**，不能直接标成当前 MIT 开源。其 README 标注不再积极维护。本次没有运行或复制其代码，选择维护边界更清楚的 Spec Kit 作为主要设计对照。

没有新增第三方代码、依赖、商标素材或原文模板，因此没有把外部源码混入本项目 MIT 许可；已有可选官方 SDK 继续遵循其自身许可。

## 已实装：下单前免费需求预检

以前：用户只能创建订单，直到交付后才看到材料不足形成的待确认项。

现在：`python3 -m briefmint preflight --input request.json` 和 `POST /v1/preflight` 在下单前返回字段级检查、补充问题和统一输入哈希。检查交付物/约束/事实是否存在、来源是否为空或占位、URL 是否不完整或带凭据，以及规范化后重复的事实。只有结构错误阻止下单就绪；其余缺口作为警告由用户决定。不会假装检测语义矛盾或验证外部事实。

这一步不生成付费 Brief，不创建订单/审计流水，也不调用支付 provider。CLI 甚至不初始化 SQLite 或商户 SDK；付款与交付路径继续独立验付、失败关闭。`--strict` 可把待补材料转为退出码 `2`，便于自己的工作流在付费前检查。

## 验证与仍有的差距

- 新增 7 项预检测试：完整/缺材料/无效输入、重复与多来源归属、带凭据或不完整 URL、CLI 不建账本/不初始化商户、HTTP 不验付/不生成内容/不建订单。
- 原支付、金额绑定、跨订单、截止时间、并发、确认失败重试、不会重复挑战已付款订单及包独立运行测试仍运行。
- 运行 `sh scripts/verify.sh` 重现；安装可选 SDK 后，`python -m unittest discover -s tests -v` 也覆盖 3 项离线 SDK request/model 合同测试。它们不是远程支付验收。

预检是确定性结构检查，不是产品专家评审或事实查证。后续如果需要更强的语义文档修订，可采用明确披露的模型后端；当前没有为了比较而增加未经验证的模型或真实收费。
