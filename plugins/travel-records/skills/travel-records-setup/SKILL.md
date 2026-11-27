---
name: travel-records-setup
description: Set up the installed Travel Records plugin or diagnose its resource, runtime, workspace and Gmail readiness before a travel extraction. Use for first-time setup or a failed Travel Records launch.
---

# Set up Travel Records

Use the plugin's installed resources. Locate the plugin root containing `plugin.json` and its sibling `skills/travel-records/SKILL.md`. Do not download the repository again, treat an arbitrary GitHub URL as installation, or ask the user to upload the plugin ZIP as the normal setup path.

## Check the current host

Choose a private, writable data/workspace directory from this host's documented locations, outside the installed bundle. With an available Python 3.9+ interpreter, run:

```bash
python3 <plugin-root>/skills/travel-records-setup/scripts/check_environment.py --workspace <private-workspace>
```

The JSON describes local helper readiness only. Verify the resource hashes, Python, `jsonschema` and a write/read round trip. Keep the returned `python_executable` for subsequent helper commands. A read-only plugin cache is fine; generated files belong in the private workspace.

If only `jsonschema` is missing and this host permits normal package installation, repeat once with `--prepare`. It creates an owned, isolated runtime in that private workspace and installs wheel packages from PyPI; it never installs globally or compiles native dependencies. Do not change network/security policies to make installation work. If Python is absent or preparation fails, report which capability is unavailable and what was actually attempted. Do not claim full extraction support or make the user run developer commands as the default recovery path. User-requested ordinary document interpretation can remain available, labeled separately.

## Check the chosen source

For mailbox extraction, discover the Gmail tools already available in this conversation. Read their current account choices and verify selected identities with a profile read using the supplied connection arguments. Reuse an existing valid authorization. Do not ask the user for internal connection IDs, passwords or API keys. If Gmail is unavailable, use the host's plugin discovery/connection flow, or report that a connection is required. Installing Travel Records does not itself connect Gmail.

Use the user's existing account/year choices. Ask only for genuinely missing scope. An annual request searches only mail dated in those years; keep trip dates separate. Record the choices in the main skill's session protocol. Uploaded documents do not require a Gmail connection.

Confirm how the host can deliver actual output files. Distinguish a writable path from a verified downloadable result. Check whether this host can continue work after a worker turn; the packaged supervisor is usable only with a real synchronous adapter. Do not invent a stop hook, promise background execution, or imply that installing this plugin enabled automatic continuation.

## Start or resume

Report a short user-facing readiness result: source/account, mail-year scope, file delivery, and any blocking capability. Keep implementation paths and connection IDs out of the normal user flow. When ready and extraction was requested, immediately load the complete sibling `travel-records/SKILL.md` and the references for that task, then start or resume it. Reuse its checkpoint, identities and import rules. A setup check is not proof of complete extraction or successful App import.
