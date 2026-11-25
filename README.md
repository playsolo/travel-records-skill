# FotoNest Travel Import

A Skill for recovering travel records from authorized email and documents. It prepares hotel stays, flight segments and dining reservations for review, with a separate spending ledger.

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

Point your agent at [SKILL.md](SKILL.md), or install the full repository folder as a skill named `fotonest-travel-import`. Your agent discovers and interprets material from the sources you authorize. The bundled scripts normalize mail, reconcile evidence, and produce [FotoNest v1 exports](references/travel-import-v1.schema.json) locally.

- [Mail and attachment workflow](references/extraction-workflow.md)
- [Resume an import and confirm which records were saved](references/evidence-workflow.md)
- [Booking channels and receipts](references/mailbox-and-receipts.md)

## Public preview

- Verified on a limited real-mail sample covering Chinese Ctrip hotel statements and invoice PDFs, Fliggy hotel vouchers, one Ctrip message with an explicit Booking.com partner reference, and a two-room SLH confirmation. Two independent provider emails for the same Ctrip/Booking.com order were not available in that sample.
- Schema.org JSON-LD is supported for a documented subset and was verified with synthetic hotel, flight and dining examples.
- The FotoNest file-import entry is currently available in Debug builds. Review and export can be tried without the App.
- Keep mailbox evidence, session files and import results outside the checkout. This repository ships synthetic examples.
