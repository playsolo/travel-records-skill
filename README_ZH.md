# Travel Records

[English](README.md) · [下载预览版](https://github.com/playsolo/travel-records-skill/releases)

从旧邮件、账单 PDF 和截图找回旅行记录。把酒店住宿、航班和餐厅预订整理成可核对的清单，保留日期、消费金额和来源。结果可以独立使用，也可以导出到 FotoNest。

## 看一个例子

| 新读到的资料 | 核对结果 |
| --- | --- |
| 同一酒店、同两晚的两份独立订单，另有一封转发件 | 保留两份订单，转发件并入原订单。两间房合计 USD 200，住宿只计 2 晚。 |
| 一间房的最终账单显示住了 3 晚，另一间已取消 | 计入 3 晚和 USD 140，保留取消记录供回查。 |

这组结果来自[可运行的合成样例](README.md#try-the-demo)，试跑无需连接邮箱或安装 FotoNest。

## 安装桌面插件（GitHub 分发）

面向支持 Git 插件市场的桌面客户端。完整安装产物位于 [`desktop-plugin` 分支](https://github.com/playsolo/travel-records-skill/tree/desktop-plugin)，无需自行打包。它不是 OpenAI 公共目录上架版本。

在客户端的 **Add plugin marketplace** 中填写：

- Source：`https://github.com/playsolo/travel-records-skill.git`
- Git ref：`desktop-plugin`
- Sparse paths：留空

添加后选择 **fotonest-travel** 来源并安装 **Travel Records**。若客户端没有此入口，但已有支持插件的 `codex` 命令，可运行：

```bash
codex plugin marketplace add playsolo/travel-records-skill --ref desktop-plugin
codex plugin add travel-records@fotonest-travel
```

随后运行首次设置、单独授权 Gmail，并在新会话中先核对一段已知行程。需要 Python 3.9+、可写私有工作区和 `jsonschema`；首次设置会检查环境并可准备隔离依赖。只在支持本地执行的桌面环境使用，网页、手机和无人值守续跑尚未验收。客户端或组织策略可能限制添加市场。

更新可运行 `codex plugin marketplace upgrade fotonest-travel`，再在客户端检查并安装可用的插件更新；添加过旧私有市场的用户应选择新的 **fotonest-travel** 来源。

## 开发者本地打包

公共目录提交候选包为 `0.1.0-preview.1`；尚未上架，发布后台当前要求先完成开发者身份验证。见[提交状态与流程](docs/plugin-publication.md)和[隐私说明](docs/privacy.md)。

GitHub 分发使用同一打包工具加 `--marketplace-name fotonest-travel`，只把产物中的 `.agents/` 和 `plugins/` 放入分发分支。该分支是生成产物，不在那里手改技能或核对脚本。

开发者可将完整 skill 和首次设置打成一个本地插件：

```bash
python3 scripts/package_plugin.py --output /absolute/private/travel-plugin
codex plugin marketplace add /absolute/private/travel-plugin
codex plugin add travel-records@fotonest-travel-private
```

输出目录必须是新目录，且位于源码之外。成品同时包含本地 marketplace 和插件 ZIP；`plugin/` 是打包蓝图，不能代替成品安装。已有核对脚本从同一份源码打包，不维护另一套提取实现。

安装后在桌面 App 的插件目录找到 **Travel Records**，运行首次设置；新会话中可使用随包提供的技能。若 App 尚未刷新本地插件列表，重启后再检查。首次设置使用安装包内的资源，不通过数据分析 Python 临时下载 GitHub。它检查资源、私有工作区和 Python 依赖，再通过宿主核实已有 Gmail 账号及文件交付能力。必要时可在私有工作区准备隔离运行环境，失败时报告缺失能力；不要求用户修改全局 Python 或提供连接标识。

这是私有桌面安装原型，未上架公共目录，也未验收网页、手机或无人值守续跑。安装本身不授权邮箱访问；正常使用仍需宿主提供已授权 Gmail 工具或用户提供资料。普通核对无需 FotoNest，导入需另外核实 App 支持。

## 安装到 Codex

在你希望启用 Skill 的项目目录运行：

```bash
npx skills add playsolo/travel-records-skill --skill travel-records --agent codex
```

安装需要 Node.js 和 npx。本地核对脚本需要 Python 3.9 或更高版本，以及 `jsonschema`。也可以从 [GitHub](https://github.com/playsolo/travel-records-skill) 下载完整目录，让 Agent 读取 [SKILL.md](SKILL.md)。

先提供几封邮件或文件，再试问：

> 请用 travel-records 整理这批酒店资料。列出入住和退房日期、去重后的住宿晚数、消费金额和每条结果的依据。按账单核对金额，保留取消记录和需要我复核的项目。

使用自己的邮箱时，由 Agent 通过你授权的连接器读取指定范围。随附脚本在本地合并证据和核对金额。公开样例均为合成数据。

## 在会话中通过链接使用

先让 Agent 确认实际读到了完整 `SKILL.md` 及本次任务所需引用文件。GitHub 页面或 raw 文件读取失败时，可尝试[完整 ZIP](https://codeload.github.com/playsolo/travel-records-skill/zip/refs/heads/main)，或通过当前环境支持的文件方式提供完整目录，保留 `references/` 和 `scripts/`。提供链接不等于加载成功；仍读不到必需文件时，应停止技能提取并报告真实错误，不自行生成临时导入格式。

长任务开始前，先确认私有输出目录可写、文件如何交付。工作区路径不等于下载链接；无法发布附件时，应保留进度并说明限制，小批结果可完整回贴文件内容。细节见[技能加载与文件交付](references/execution-and-delivery.md)。

## 当前验证范围

[用自己的 Gmail 验收](docs/gmail-acceptance.zh-CN.md)

[桌面内测介绍、合成结果样例与推广素材](marketing/README.md)

已用少量真实材料核对携程酒店水单和发票 PDF、飞猪酒店入住凭证、带 Booking.com 合作订单号的携程邮件，以及一封 SLH 双房确认邮件。真实样本覆盖有限。可选的 FotoNest v1 文件导入目前可在 Debug 构建中使用。

[MIT 许可](LICENSE)允许使用、修改和分发，保留原版权和许可声明即可。
