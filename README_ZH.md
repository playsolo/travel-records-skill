# Travel Records

[English](README.md) · [下载预览版](https://github.com/playsolo/travel-records-skill/releases)

从旧邮件、账单 PDF 和截图找回旅行记录。把酒店住宿、航班和餐厅预订整理成可核对的清单，保留日期、消费金额和来源。结果可以独立使用，也可以导出到 FotoNest。

## 看一个例子

| 新读到的资料 | 核对结果 |
| --- | --- |
| 同一酒店、同两晚的两份独立订单，另有一封转发件 | 保留两份订单，转发件并入原订单。两间房合计 USD 200，住宿只计 2 晚。 |
| 一间房的最终账单显示住了 3 晚，另一间已取消 | 计入 3 晚和 USD 140，保留取消记录供回查。 |

这组结果来自[可运行的合成样例](README.md#try-the-demo)，试跑无需连接邮箱或安装 FotoNest。

## 安装到 Codex

在你希望启用 Skill 的项目目录运行：

```bash
npx skills add playsolo/travel-records-skill --skill travel-records --agent codex
```

安装需要 Node.js 和 npx。本地核对脚本需要 Python 3.9 或更高版本，以及 `jsonschema`。也可以从 [GitHub](https://github.com/playsolo/travel-records-skill) 下载完整目录，让 Agent 读取 [SKILL.md](SKILL.md)。

先提供几封邮件或文件，再试问：

> 请用 travel-records 整理这批酒店资料。列出入住和退房日期、去重后的住宿晚数、消费金额和每条结果的依据。按账单核对金额，保留取消记录和需要我复核的项目。

使用自己的邮箱时，由 Agent 通过你授权的连接器读取指定范围。随附脚本在本地合并证据和核对金额。公开样例均为合成数据。

## 当前验证范围

[用自己的 Gmail 验收](docs/gmail-acceptance.zh-CN.md)

已用少量真实材料核对携程酒店水单和发票 PDF、飞猪酒店入住凭证、带 Booking.com 合作订单号的携程邮件，以及一封 SLH 双房确认邮件。真实样本覆盖有限。可选的 FotoNest v1 文件导入目前可在 Debug 构建中使用。

[MIT 许可](LICENSE)允许使用、修改和分发，保留原版权和许可声明即可。
