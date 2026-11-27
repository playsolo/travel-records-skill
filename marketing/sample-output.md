# Synthetic reconciliation example / 合成核对样例

## 中文

以下全部为虚构数据，不含真实旅客、酒店、邮箱或订单。日期沿用现有演示的 2024 年，不是 2026 年真实邮箱测试结果。输入是预先提取的合成证据，不演示 AI 识别邮件正文或 PDF 的能力。

### 输入资料

| 资料标识 | 内容 |
| --- | --- |
| source-a | Example Bay Hotel，订单 DEMO-A，2024-02-01 至 02-03，一间房，报价 USD 100.00 |
| source-b | 同酒店同日期的独立订单 DEMO-B，一间房，报价 USD 100.00 |
| source-copy | DEMO-A 原确认函的转发件 |
| source-bill | DEMO-A 最终账单，实际入住 2024-02-01 至 02-04，总额及付款 USD 140.00，余额 USD 0.00 |
| source-cancel | DEMO-B 已取消，取消费 USD 0.00，DEMO-A 不受影响 |

### 便于阅读的结果摘要

这是核对报告的编辑摘要，不是软件截图或 CSV 字段的逐字展示。

| 订单 | 状态 | 日期 | 实际住宿晚数 | 采信金额 | 主要依据 |
| --- | --- | --- | ---: | --- | --- |
| DEMO-A | 有实际住宿证据 | 2024-02-01 → 02-04 | 3 | USD 140.00 | source-a、source-copy、source-bill；采用最终账单 |
| DEMO-B | 已取消 | 原预订 2024-02-01 → 02-03 | 0 | USD 0.00 | source-b、source-cancel；保留取消历史 |

**合计：实际住宿 3 晚，采信金额 USD 140.00，保留 2 份订单历史。** 转发件不会新增订单，两间房同一日期的晚数也不直接相加。初始报价 USD 200.00 不再当作最终消费。

只有预订确认的第一阶段，可以说明“两份订单、计划日期覆盖 2 晚、报价合计 USD 200.00”，不能称为已经实际住了 2 晚。样例最终账单明确列出付款；真实场景不能仅因存在账单就断言已付款。

### 复现

按 [演示运行说明](../README.md#try-the-demo)运行 `scripts/demo.py`。现有脚本还模拟导入回执和已保存记录的更新；这些回执是演示生成的，不代表真实 FotoNest 导入成功。已发现材料处理完成也不代表搜全真实邮箱。

## English

All names, accounts and orders are synthetic. The dates retain the existing demo's 2024 scenario; this is not a 2026 mailbox test. Inputs are pre-extracted evidence, so the example does not evaluate AI email or PDF extraction.

DEMO-A and DEMO-B initially reserve separate rooms at Example Bay Hotel for February 1–3, 2024, at USD 100.00 each. A forwarded copy belongs to DEMO-A. A later final bill establishes DEMO-A's actual February 1–4 stay, USD 140.00 paid and zero balance. DEMO-B is cancelled without a fee.

| Order | Final review | Actual nights | Recognized amount | Evidence |
| --- | --- | ---: | --- | --- |
| DEMO-A | Actual stay supported, February 1–4 | 3 | USD 140.00 | source-a, source-copy, source-bill |
| DEMO-B | Cancelled; original booking retained | 0 | USD 0.00 | source-b, source-cancel |

This is an editorial summary of the review report, not a screenshot or exact CSV layout. The final result retains two orders, counts three actual nights and recognizes USD 140.00. Forwarded mail does not add an order; overlapping room nights are not added together. The initial USD 200.00 quote is superseded.

At the reservation-only stage, describe two orders covering two planned nights and USD 200.00 in quoted prices, without claiming a completed stay. The final bill explicitly confirms payment in this fixture; real bills do not always do so.

Follow [Try the demo](../README.md#try-the-demo) to run `scripts/demo.py`. Its import receipts are simulated and do not prove a real FotoNest import. Processing all registered evidence also does not prove complete mailbox discovery.
