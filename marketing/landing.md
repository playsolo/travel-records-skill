# Travel Records

## 中文介绍页文案

### 把邮箱里的旅行线索，整理成可核对的记录

酒店确认函、改期邮件、最终账单、机票和餐厅预订散落在邮箱里。Travel Records 帮你整理日期、状态、金额和来源，方便回顾旅行，也方便查出需要进一步核对的地方。

**桌面私有内测中。** [先看合成样例](sample-output.md) · [查看当前安装说明](../README_ZH.md)

### 从找到资料，到核对结果

- **住宿：** 整理入住和退房日期，结合账单核对实际住宿，保留取消和修改记录。
- **航班与餐饮：** 整理航段、用餐预订及可读取的消费依据，区分预订与实际发生。
- **来源与复核：** 保留原始资料线索，标出冲突、缺少附件或无法确认的字段。
- **独立使用：** 核对结果可交付为 CSV 和核对 JSON；整理旅行记录无需安装 FotoNest。

### 一个例子

两份独立订房确认，加上一封转发件，先整理为两份订单。随后补入一份最终账单和另一份订单的取消邮件：保留两份订单历史，实际住宿更新为 3 晚，采信金额更新为 USD 140.00。

这是随项目提供的合成核对案例，不是对真实邮箱的提取速度或完整率承诺。[查看输入与结果](sample-output.md)

### 第一次怎样用

内测先确认桌面环境、安装和授权连接是否可用，再选择一段自己记得的行程。连接 Gmail 需要你单独授权，也可以先提供少量邮件或文件核对。

安装和首次设置完成后，可以这样说：

> 请用 Travel Records 整理我 2026 年邮件中的住宿、航班和餐饮记录。只检查 2026 年发送的邮件，保留证据来源和待复核项，并说明搜索范围、已读取数量和剩余任务。

首次建议把范围缩小到一段已知行程。按邮件年份检查，可能缺少其他年份发来的预订或账单；你明确扩展年份后，可以沿用原记录补入证据。

### 邮箱和数据如何处理

技能用于读取和核对，不授权发送、删除或修改邮件。安装插件也不等于授权邮箱访问。邮件通过宿主提供的已授权连接器读取，Agent 会处理资料；本地脚本归并证据并保存结果。具体的数据处理规则取决于所用客户端、连接服务和账号设置。

请将原始账单、附件和输出保存在私有位置。公开反馈只提交脱敏摘要，检查并移除姓名、邮箱、订单号、会员号和支付信息。

### 当前支持范围

当前是私有桌面插件原型，尚未上架公共插件目录。网页、手机和无人值守连续执行尚未验收；大范围提取可能需要继续处理。真实材料验证以有限酒店样本为主，航班和餐饮仍需更多真实案例核对。结果会标明范围和待处理事项，需结合原件复核。

FotoNest v1 文件导入目前仅在 Debug 构建提供，普通旅行清单可以独立使用。

## English introduction copy

### Turn travel emails into records you can check

Hotel confirmations, amendments, final bills, flight tickets and dining reservations are scattered across your inbox. Travel Records organizes dates, status, amounts and source references so you can review your trips and see what still needs checking.

**Private desktop beta.** [View the synthetic example](sample-output.md) · [Read the current installation guide](../README.md)

Review hotel stays, flight segments and dining reservations with their supporting evidence. Keep cancellations and changes, distinguish bookings from completed travel, and flag conflicts or unreadable attachments. Results can be delivered as CSV and review JSON; FotoNest is optional.

In the supplied synthetic example, two independent bookings and a forwarded copy become two orders. A later final bill and cancellation update the actual stay to three nights and the recognized amount to USD 140.00. This demonstrates reconciliation, not real-mail extraction speed or completeness.

Start with a known trip after checking desktop installation and your authorized Gmail connection. You can also provide a small set of documents. Once setup is complete, try:

> Use Travel Records to organize hotels, flights and dining from my emails sent in 2026. Search only 2026 mail. Keep source references and review items, and report the search scope, documents read and remaining work.

Mail-year scope can exclude bookings or bills sent in other years. Explicitly expanding the years lets new evidence update the existing records.

The skill reads and reconciles evidence; it does not authorize sending, deleting or modifying mail. Installation does not grant Gmail access. The host's authorized connector retrieves mail, the agent processes it, and local scripts reconcile and save results. Data handling depends on the client, connected services and account settings. Keep originals and outputs private; share only redacted feedback.

This private desktop prototype is not in the public plugin directory. Web, mobile and unattended continuation remain unverified. Larger runs may need further processing. Real-mail validation is limited and mainly covers hotel documents; flight and dining workflows need more real-world evaluation. Review the stated scope and unresolved items against the originals. FotoNest v1 file import is currently available only in Debug builds.
