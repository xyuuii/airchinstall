# Architecture

Airchinstall wraps a real Bash PTY with tmux; it does not emulate a terminal or execute installation commands for the user.

```text
tmux install window
├── Bash PTY ── preexec/precmd + pipe-pane ──┐
├── Mentor Textual client ────────────────────┤ Unix socket JSONL
└── Wiki Textual client ──────────────────────┘
                                               │
                                      Session daemon
                                      ├── AssistantSession
                                      ├── read-only probes
                                      ├── redacted transcript
                                      └── OpenAI-compatible tutor
```

## Runtime flow

1. Bash emits `command.started`; `pipe-pane` streams `output.chunk`; Bash emits `command.finished` with the exit code.
2. The daemon recognizes trusted Operations, runs only the Operation's registered read-only Probe and updates Facts.
3. A natural-language Goal plus current Facts and available Operation metadata are sent to the cloud tutor. Metadata includes only catalog-owned IDs, canonical commands, impacts, risks and Wiki references.
4. The structured Advice response must contain two or three distinct feasible Operation IDs when the catalog has enough choices; unknown or unavailable IDs are rejected.
5. All clients receive a complete Session Snapshot, so reconnects do not reconstruct state from UI history.

Each state change advances a session revision. A slower AI response from an older Goal or Observation is discarded, so cloud latency cannot roll Advice back to stale context.

The Mentor renders catalog-owned commands and risks; AI text never becomes a copyable command authority. `Ctrl+D` toggles catalog details. The Wiki client identifies the exact page, section, source URL and locally installed `arch-wiki-lite` package version.

The socket protocol is versioned with `v: 1`. Internal producer and UI subcommands are not public interfaces.
