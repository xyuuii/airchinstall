# Testing

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e '.[test]'
pytest
```

The retained tests exercise behavior at three seams:

- `AssistantSession`: order-independent Facts, free Goals and trusted Advice.
- Unix socket protocol: snapshots, reconnects, command lifecycle and AI failure.
- Public CLI: doctor/start/export behavior and executable bootstrap/QEMU scripts.

Additional integration tests spawn a real interactive Bash PTY, create the tmux daemon/Bash/mentor/Wiki topology, and render Textual clients at narrow CJK widths.

## QEMU acceptance record

Validated on 2026-08-31 with QEMU 11.1.1 on Apple Silicon (TCG) and the official
Arch Linux 2026.08.01 x86_64 ISO. SHA-256:
`4e82dced1c4fd3e498b22a853f8db2a4d262d32b97e7e07d97390d9e425ffe5e`.
The ISO also passed its detached OpenPGP signature check.

- Bootstrap installed only official packages into the Live overlay; `doctor`
  passed QEMU, tmux, kmscon, Pango/fontconfig, CJK font, local Wiki and cloud AI
  checks.
- At 80×24, the compact Bash/Mentor layout and separate Wiki window rendered
  Chinese without missing glyphs. Mentor showed the catalog-owned command,
  impact and read-only risk; Wiki reported the installed local snapshot as
  `arch-wiki-lite 20260702-1`. The 120/80-column layout rules are also covered
  by automated Textual tests.
- The volatile `/run/airchinstall/bin/airchinstall` launcher exposed only
  `start`, `doctor` and `export-transcript`; startup preflight passed before
  tmux was created.
- `disk → UEFI → network` and `network → UEFI → disk` both converged on
  `disks.inventory`, `boot.uefi` and `network.online`.
- The AI key and an explicitly exported transcript both had mode `0600`; the
  exported JSONL did not contain the test key.
- With the OpenAI-compatible test server stopped, `doctor` failed with status 1
  at `Cloud AI`, while the ordinary Arch rescue Shell remained usable.
