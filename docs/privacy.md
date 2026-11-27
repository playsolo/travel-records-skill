# Travel Records privacy / 隐私说明

Effective date / 生效日期：2026-11-27

## 中文

Travel Records 由 FotoNest 项目维护，源代码和支持入口位于 [playsolo/travel-records-skill](https://github.com/playsolo/travel-records-skill)。本说明适用于仓库提供的技能、桌面插件及本地核对脚本。

### 处理哪些数据、用于什么

根据你授权的任务范围，Agent 可处理相关邮件正文、附件、截图或你提供的文件，以整理旅行日期、住宿与航班、餐饮预订、订单状态、金额、币种和证据来源。资料可能包含姓名、联系方式、订单及会员信息。请仅提供任务必需资料，移除不需要的身份证件号码、完整银行卡号、安全码和账号凭证。插件不会要求密码、授权令牌或验证码。

安装插件不会连接邮箱或扩大权限。邮箱资料通过宿主已有且由你授权的连接器读取。提取任务不授权发送、删除或修改邮件。

### 数据经过哪里

宿主客户端、模型服务和你选择的连接器会按其各自条款与账号设置处理任务数据。本地核对脚本在你的私有工作区保存会话、来源证据和输出；这些文件可能包含邮件内容或敏感行程，不能只因是 JSON 或 CSV 就当作已脱敏。

此发布包不包含向 FotoNest 运营的服务器上传旅行资料的服务，也没有内置使用统计上报。维护者不会仅因你安装插件而收到邮箱或生成结果。若你另行选择上传反馈、共享聊天或导入其他产品，相应服务将按其规则处理你提交的内容。

首次设置在需要准备依赖时会连接 PyPI 下载 Python 包；技能包和源代码也可能经 OpenAI、GitHub 等分发。提供商可能处理下载及请求元数据；这些下载不是旅行资料上传。

### 保留、删除与控制

本地会话、证据与结果保留在你选择的工作区，直到你自行删除；没有自动清理期限。卸载插件不应视为已删除独立工作区里的资料。聊天、模型服务、连接器和下载服务的数据保留遵循各自政策与账号设置。

你可以缩小邮件日期或账号范围、使用文件代替邮箱、通过宿主撤销 Gmail 连接，并删除本地输出。撤销连接或删除本地文件不会自动删除第三方服务已保存的聊天或日志，请到对应服务管理。

### 支持与更新

通过 [GitHub Issues](https://github.com/playsolo/travel-records-skill/issues) 提交问题时仅附脱敏摘要，不要公开原始邮件、账单、订单号或凭证。公开反馈由 GitHub 按其政策保存。隐私问题也可先提交不含个人资料的问题，安排进一步沟通。本说明随实际功能和数据处理方式变化更新。

## English

Travel Records is maintained by the FotoNest project at [playsolo/travel-records-skill](https://github.com/playsolo/travel-records-skill). This notice covers the repository's skills, desktop plugin and local reconciliation scripts.

### Data and purposes

Within your authorized scope, the agent may process relevant email bodies, attachments, screenshots and supplied files to reconstruct travel dates, hotels, flights, dining reservations, order status, amounts, currencies and source evidence. Documents may contain names, contact details, booking references and membership information. Provide only necessary material; remove unnecessary government identifiers, full payment-card numbers, security codes and credentials. The plugin does not request passwords, authorization tokens or one-time codes.

Installation does not connect your mailbox or expand access. Mail is read through a host connector you authorize. Extraction does not authorize sending, deleting or modifying mail.

### Processing and recipients

Your host client, model service and selected connectors process task data under their own terms and account settings. Local scripts save sessions, source evidence and outputs in your private workspace. Those files can contain mail content and sensitive itineraries; JSON and CSV are not automatically redacted.

This package includes no service for uploading travel evidence to a FotoNest-operated server and no built-in usage telemetry. Installing it does not send your mailbox or results to the maintainers. If you choose to send feedback, share a chat or import files into another product, that service processes the submitted data under its own rules.

Setup may download Python dependencies from PyPI. OpenAI, GitHub or other providers may distribute the package or source. Providers may process download/request metadata; these downloads do not upload travel evidence.

### Retention and controls

Local sessions, evidence and results remain in your chosen workspace until you delete them; there is no automatic expiry. Uninstalling the plugin should not be assumed to delete a separate workspace. Chat, model, connector and download-service retention follows each provider's policies and your account settings.

You can narrow mail dates and account scope, supply documents instead of connecting mail, revoke Gmail access through the host and delete local outputs. Revocation or local deletion does not automatically delete third-party chats or logs; manage those in the relevant service.

### Support and changes

Use [GitHub Issues](https://github.com/playsolo/travel-records-skill/issues) with redacted summaries only. Do not post original mail, bills, booking references or credentials. Public feedback is retained by GitHub under its policies. For a privacy concern, start with a non-personal report to arrange further communication. This notice will change when the actual functionality or data processing changes.
