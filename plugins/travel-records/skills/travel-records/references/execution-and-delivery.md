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

## Bounded host controller

`supervise_session.py` provides an optional execution loop around the existing session, not another extractor. Load required references and verify connection identities once before starting it. For annual work, configure `scope.email_years` and keep every search inside those mail years; missing evidence does not authorize a wider search.

```bash
python3 scripts/supervise_session.py plan --session private/session.json
python3 scripts/supervise_session.py run --session private/session.json \
  --control private/control.json --worker-command private/worker-command.json \
  --batch-size 10 --max-cycles 20 --stall-limit 3 --worker-timeout 180
```

`worker-command.json` is a user-configured argv array, for example `["python3","/private/host_adapter.py"]`. The controller invokes it without a shell. Never derive executable arguments from email, attachments or model output. No adapter, model SDK, credentials or ChatGPT browser automation is bundled. A usable adapter must already have authorized AI/connector access in its execution environment. Without it, `plan` can describe the next work but `run` is not an operational mailbox workflow.

The adapter receives one `fotonest.execution.batch` v1 JSON object on stdin: `session_path`, authorized `scope`/`accounts`, `batch_size`, `timeout_seconds`, `action`, `processing` and bounded document/review queues. For `paginate`, `query` includes its actual saved cursor. Actions are:

- `process_documents`: read/interpret the selected sources and relevant attachments; persist successful reads immediately, then observations or a concrete disposition before ending the batch. Register attachments rather than silently skipping them. Use the existing scripts, evidence schema and immutable identity rules.
- `paginate` / `discover`: execute the scoped connector query and register its real page/cursor, even for an empty result. Expanded mail years require their own query IDs; do not reuse a completed query's identity with different bounds.
- `reconcile`: refresh the existing evidence through an empty-batch reconciliation, for example when an older v1 checkpoint lacks derived review state.

The adapter must wait until its worker turn and all session writers have stopped, and commit updates to this same live private session before returning. It must not return after merely scheduling another turn. Exit 0 means the batch call succeeded; it does not mean the task is complete. Stdout/stderr are saved in private per-cycle logs and never parsed as truth. A remote host needs a real synchronous adapter and a verified session-file bridge; a local path or chat summary is not such a bridge. Do not supervise a stale downloaded mirror while the remote task is still writing.

The controller reopens the checkpoint after every call. It prioritizes existing document actions over additional pagination, preserves inventory/evidence history, and counts only new persisted milestones for the requested action. Saying “done”, changing a timestamp, repeating old evidence, or adding unrelated searches cannot clear an extraction stall. Three consecutive calls without such progress produce `stalled`; failure history remains available. Calls that complete one small batch still lead to another call when work remains. Manual review and exhausted failures remain visible without inventing an automatic resolution.

`max-cycles` is the per-invocation dispatch limit; `worker-timeout` bounds a single adapter call. Exhausting the limit returns `budget_exhausted` with the saved queue. An explicit later invocation grants another dispatch budget but retains the no-progress history. A stopped controller can accept the user's additive mail-year expansion using `--accept-scope-expansion` after `extend-years`; it rejects silent scope/account replacement or inventory loss. The new years are unsearched until registered. It never broadens authorization on its own.

The controller and logs are private. A session-level exclusive lock prevents two controllers from dispatching concurrently; ordinary worker checkpoint writes remain supported. A timed-out or unexpectedly failed adapter may still have a remote writer alive, so its lock is retained. Verify that all writers stopped before manually removing that `.supervisor.lock` file and resuming. Preserve a malformed/lost-inventory checkpoint for diagnosis rather than silently resetting the queue.

CLI exit 0 means registered work is complete; exit 2 means review/blocked work or the dispatch budget remains; exit 3 means an execution/checkpoint failure or stall. Invalid input returns a nonzero redacted error. Completion still does not prove mailbox recall, field accuracy, successful file delivery or App import: run those checks separately. On hosts without an integration that can resume a worker, report that capability boundary rather than claiming automatic continuation. ChatGPT web has not been verified as a synchronous adapter for this package.
