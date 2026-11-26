# Skill loading and file delivery

Use these checks for mailbox extraction and continuing reviews. A supplied screenshot or chat-only interpretation does not need a script workspace unless the requested work uses the helpers.

## Load the requested mode

Read the complete `SKILL.md` and follow its reference links for the requested mode. Mailbox work needs `mailbox-and-receipts.md` and `extraction-workflow.md`; continuing work also needs `evidence-workflow.md`. Read `stay-acceptance.md` when selecting a recognition profile, and the v1 schema when exporting to FotoNest. Identify the actual local package path and the files read; use a commit or archive hash when available to identify a downloaded package. A repository landing page, filename listing or search excerpt is not the file's contents.

If the supplied repository page or raw file cannot be read, try one complete archive download from that same authorized repository, or use an already supplied/installed complete folder. This package's public archive is <https://codeload.github.com/playsolo/travel-records-skill/zip/refs/heads/main>. Keep relative references and scripts together. Loading a package does not authorize changing product, model, account connections or execution permissions. If the current environment cannot read the required files, report the actual failed access and stop the skill-based extraction until the files are available. Do not silently replace its schema with a temporary format. Separately requested ordinary interpretation can still be reported as such.

## Establish a workspace and delivery route

Before a long mailbox run, create a small file in the intended private output directory and read it back. Use the host's documented writable workspace, preserving existing session files. If the requested directory is read-only, use an available private workspace and report the changed location; do not repeatedly write to the failing path or change its permissions. Verify Python and `jsonschema` in the environment that will run the existing validators. Missing execution capabilities must remain visible; schema inspection alone is not an executed validation.

Check whether the host can publish local files as conversation attachments or downloadable outputs. A local workspace path and a successful file write do not themselves establish a download link. Do not invent `sandbox:` links or claim a file was delivered because it exists in another session's workspace.

After validation, read the actual CSV and JSON files back and use the host's available delivery mechanism. If publishing fails, keep the files and report their actual location and the error. For a small result, complete CSV/JSON code blocks are a fallback; label them as file contents, preserve exact values, and do not treat them as downloadable attachments. For a large/private review, retain the checkpoint and report the delivery blocker instead of dumping raw messages or truncating a file while calling it complete. Do not rerun mailbox extraction just to repair file delivery.

## Check coverage before declaring completion

Use the discovery inventory and existing session/checkpoint protocol in `evidence-workflow.md`; do not build the expected document list from successful extractions alone. Preserve each candidate message and relevant attachment, including a discovered source that could not be read. A reading budget may stop processing, but it must not erase the remaining queue or pagination cursor.

Run `audit_coverage.py` using the format in [the extraction workflow](extraction-workflow.md#3-account-for-every-candidate). Report its result alongside unfinished queries, unread documents, needs-review materials and the number of exported records. Its successful exit may include unresolved items; inspect `inventory_fully_resolved` and `needs_review_including_copies`. A pending retrieval with an actual failure can be accounted for as `needs_review`, but is not a successful extraction. Report what the scripts actually checked: coverage audit does not verify mailbox recall, field accuracy or the existence of referenced records, and v1 validation does not prove an App import.

For a resumable session, run `run_session.py assert-complete --session <session.json>` before claiming the registered inventory is fully processed. Inspect its JSON status and exit code, not just the coverage audit's exit code or `latest.json`'s `state=ready`. That manifest state remains the file-publication contract; its separate `processing` field describes remaining work. A schema-valid export with unread sources stays `partial`.

While `next` returns actions within the user's scope and budget, process a batch, checkpoint and continue; a progress update or a successful export is not a stopping condition. Handle the separate blocked/review lists without silently removing them. For a recovered transport error, continue with a smaller batch; for an actual nonrecoverable connector failure or an explicit budget boundary, preserve the checkpoint and report the reason and remaining counts. The helper cannot keep a host alive or automatically start another conversation turn. If host execution stops, its caller must resume this checkpoint; do not promise automatic continuation without that support.

When diagnosing an earlier omission, inspect the original files and saved search/read progress if accessible. Distinguish a prior search hit, a successfully read body/attachment, an extracted observation and an exported record. A message found by a new targeted query cannot establish that the earlier run found or read it. If the original execution history or files are unavailable, state that limit rather than inventing a deduplication or search failure.
