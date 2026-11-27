# 60-second demo / 60 秒演示脚本

## 中文

**主线：从几份资料到一条有依据的住宿记录。** 成片全程保留“桌面内测 · 合成证据核对演示”角标。使用 [合成样例](sample-output.md)，不展示个人邮箱，不把样例输出包装为真实提取过程。

| 时间 | 画面 | 旁白 |
| --- | --- | --- |
| 0–7 秒 | 摆出两份确认函和一份转发件的合成资料卡 | 同一次旅行，确认函、转发件和账单散在不同地方。最后到底该记几条？ |
| 7–18 秒 | 展示 DEMO-A、DEMO-B 两份订单及转发件归属 | Travel Records 把同一订单的转发归在一起，独立订单分别保留。只有预订时，先保留预订状态。 |
| 18–32 秒 | 加入最终账单和取消邮件，停留在日期、金额与取消费 | 后来，一间房实际住了三晚，最终账单是一百四十美元；另一间取消，取消费为零。 |
| 32–45 秒 | 展示结果摘要，突出 3 晚、USD 140、两份订单历史和来源 | 结果更新为实际住宿三晚、一百四十美元。取消订单仍能回查，每条结果都有依据。 |
| 45–53 秒 | 打开真实生成的核对 JSON；来源标识与样例对照 | 你可以回到资料核对；读取失败或有冲突的项目，会留待复核。 |
| 53–60 秒 | 片尾：桌面内测；先核对一段已知行程；项目地址 | 目前开放桌面内测。先从一段你记得的行程开始，核对自己的旅行记录。 |

### 录制方式

先按 [现有演示说明](../README.md#try-the-demo)生成实际文件，画面只引用对应结果。资料卡及结果摘要标“示意”；脚本运行标“本地合成证据演示”。剪辑等待时间时标注“已剪辑”，不要暗示真实邮箱任务只需一分钟。

只有额外录到真实成功流程后，才加入安装、授权或邮件提取画面。录真实流程时使用已获许可的测试账号，逐帧检查姓名、邮箱、订单号、会员号、金额以外的支付信息、浏览器标签与通知。缺少安装录像时，片尾引导查看安装说明，不展示虚构的一键安装按钮。

片尾显示 `github.com/playsolo/travel-records-skill`，并提示“安装条件见 README”。不要放维护者本机私有市场的 deep link。成片描述链接到项目及合成样例，注明未验收网页、手机和无人值守续跑。

### 配套短说明

Travel Records 桌面内测：把旅行资料整理成能回查依据的清单。这段视频使用合成证据，展示订单去重、最终账单更新和取消处理。真实邮箱整理需另行授权并核对结果。

## English

Keep a “Desktop beta · Synthetic reconciliation demo” label throughout. Use the [synthetic example](sample-output.md). Label source cards and the summary as illustrations, and show actual generated files when opening results.

| Time | Picture | Narration |
| --- | --- | --- |
| 0–7s | Two confirmations and a forwarded copy | Confirmations, forwarded emails and bills: how many travel records should these become? |
| 7–18s | Separate orders A and B; forward attached to A | Travel Records groups copies of the same order and keeps independent bookings separate. A reservation stays a reservation. |
| 18–32s | Add final bill and cancellation | One room was used for three nights. Its final bill is 140 dollars. The other booking was cancelled with no fee. |
| 32–45s | Show three nights, USD 140 and retained history | The review now counts three actual nights and 140 dollars, with both order histories and their evidence retained. |
| 45–53s | Open generated review JSON | Check the result against its sources. Conflicts or unreadable evidence stay visible for review. |
| 53–60s | Desktop beta and project URL | Join the desktop beta. Start by checking a trip you already know. |

Use [the existing demo](../README.md#try-the-demo) to generate files. Mark edited waiting periods; a one-minute video does not establish extraction speed. Add installation, authorization or real-mail footage only after recording a successful flow, using an authorized test account and reviewing every frame for private information.

Show the project URL and refer viewers to README requirements. Do not publish the maintainer's local installation deep link or invent an install button. In the video description, explain that inputs are synthetic and web, mobile and unattended continuation remain unverified.

Suggested caption: “Travel Records desktop beta turns travel documents into a reviewable list. This synthetic example demonstrates duplicate handling, final-bill updates and cancellation history. Real mailbox use requires separate authorization and result review.”
