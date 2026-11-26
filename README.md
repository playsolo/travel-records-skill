# Travel Records

[简体中文](README_ZH.md) · [Download preview](https://github.com/playsolo/travel-records-skill/releases)

Recover your travel history from old emails, hotel bills, and other documents. Review hotel stays, flight segments, dining reservations, spending, and the evidence behind each result. The review works on its own and can also produce a FotoNest import file.

| Synthetic input | Reconciled result |
| --- | --- |
| Two independent bookings for the same hotel and two nights, plus one forwarded copy | Two bookings, two counted nights, USD 200 |
| The final bill shows one room stayed for three nights, and the other room was cancelled | Three counted nights, USD 140, with the cancellation retained in history |

## Install for Codex

From the project where you want to use the skill, run:

```bash
npx skills add playsolo/travel-records-skill --skill travel-records --agent codex
```

The install command requires Node.js and npx. The local reconciliation scripts require Python 3.9 or newer and `jsonschema`. Start with a few emails or files and ask:

> Use travel-records to organize these hotel bookings and bills. Show check-in and checkout dates, counted nights, amounts, and the source behind each result. Flag anything I should verify.

## Try the demo

Use Python 3.9 or newer. From this folder:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install jsonschema
python scripts/demo.py
```

The final command runs locally with synthetic, pre-extracted evidence. No mailbox login, AI service or FotoNest installation is needed. It models this sequence:

| Stage | Orders in review | Counted nights | Recognized amount | Awaiting import |
| --- | ---: | ---: | ---: | ---: |
| Two independent reservations and a forwarded copy | 2 | 2 | USD 200.00 | 2 |
| One simulated save, followed by a corrected final bill and a cancellation | 2 | 3 | USD 140.00 | 1 |
| Resume with the same evidence | 2 | 3 | USD 140.00 | 1 |
| Simulate saving the remaining record | 2 | 3 | USD 140.00 | 0 |

The cancellation remains in history. If a record was already saved, it appears as an update to review. The command prints the local folder containing the checkpoint, review files and v1 export files.

## Use the Skill

[Gmail acceptance test (Chinese)](docs/gmail-acceptance.zh-CN.md)

Point your agent at [SKILL.md](SKILL.md), or install the full repository folder as a skill named `travel-records`. Your agent discovers and interprets material from the sources you authorize. The bundled scripts normalize mail and reconcile evidence locally.

For a conversation using a repository link, first have the agent confirm it read the full entrypoint and the references needed for the task. If GitHub page/raw access fails, try the [complete ZIP](https://codeload.github.com/playsolo/travel-records-skill/zip/refs/heads/main), or supply the complete folder through the host's supported file mechanism. A link alone does not confirm loading. If the required files still cannot be read, stop the skill-based run and report the access error. Check a writable private output directory and the available file-delivery route before a long mailbox run; see [loading and delivery](references/execution-and-delivery.md).

The reconciliation manifest links to a review JSON with the travel records, spending by currency, and source history. You can review it directly or map the reviewed fields to another tool's format.

If you use FotoNest, the same workflow can also produce [FotoNest v1 import files](references/travel-import-v1.schema.json). The file-import entry is currently available in Debug builds.

- [Mail and attachment workflow](references/extraction-workflow.md)
- [Resume an import and confirm which records were saved](references/evidence-workflow.md)
- [Booking channels and receipts](references/mailbox-and-receipts.md)

## Public preview

- Verified on a limited real-mail sample covering Chinese Ctrip hotel statements and invoice PDFs, Fliggy hotel vouchers, one Ctrip message with an explicit Booking.com partner reference, and a two-room SLH confirmation. Two independent provider emails for the same Ctrip/Booking.com order were not available in that sample.
- Schema.org JSON-LD is supported for a documented subset and was verified with synthetic hotel, flight and dining examples.
- Keep mailbox evidence, session files and import results outside the checkout. This repository ships synthetic examples.

## License

[MIT](LICENSE)
