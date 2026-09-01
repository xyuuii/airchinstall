# Security invariants

- The first milestone accepts only these Live contexts: official Arch x86_64 ISO in QEMU/KVM, or an Archboot AArch64 ISO in Parallels on Apple Silicon. The Parallels launcher verifies the ISO's detached signature against Tobias Powalowski's pinned Arch developer fingerprint before attaching it. Physical hardware and all other combinations are rejected.
- The Parallels launcher creates only a virtual disk and disables host disk, folder, clipboard and cloud-drive sharing before the Live ISO is started.
- AI never executes commands, chooses a disk, creates a Fact or bypasses a risk decision.
- Copyable recommendations resolve from the bundled trusted Operation Catalog; model-generated command text is never trusted.
- Only registered read-only Probes run automatically. Catalog data cannot contain arbitrary verifier shell commands.
- API Key, base URL and model live under `/run/airchinstall`; Key mode is `0600` and no value is exported into the learner's Shell.
- ANSI is removed and key/token/password/passphrase/PSK assignments, common secret CLI flags, bearer headers and OpenAI-style keys are redacted before transcript or AI use. The daemon repeats this sanitization for every protocol entry and every Probe value instead of trusting a client-side adapter.
- The cloud tutor receives Goal, verified Facts, sanitized command/exit metadata and trusted Operation metadata—not raw terminal output, Wi-Fi credentials, passwords, disk encryption secrets or `/etc/shadow`.
- Transcript is volatile by default. Export is explicit, re-redacts content and writes mode `0600`.
- The dedicated learner Bash keeps history only in process memory (`HISTFILE=/dev/null`); raw commands are never written to a second history file.
- AI failure blocks guided Advice but never removes the ordinary Arch rescue Shell.
- `airchinstall start` runs the same environment and cloud preflight as `doctor`; tmux is not created after a failed preflight.
