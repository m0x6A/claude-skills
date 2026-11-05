# voice-issue

Speak a bug, idea or task and get a structured GitHub issue. Run `/voice-issue`. A pane opens and starts
recording from your default microphone. Press `s` to stop. The note is transcribed locally with
faster-whisper (the audio never leaves your machine), and Claude drafts a title, labels chosen from the
repository's existing labels, and a body with Summary, Context, Current/Expected behaviour, Steps,
Proposal, Acceptance criteria and Open questions, using only the sections you gave material for. You
review the draft. Type a correction to revise it, then press `c` to create it with `gh issue create` in
the current repository. The original transcript is kept in a collapsed section of the issue.

Needs: PipeWire (`pw-record`), `pip install --user faster-whisper`, and `gh` logged in.
Options (config menu): `whisperModel` (default `small.en`, English) and `draftModel` (default `sonnet`).

Install:

```text
/plugin marketplace add m0x6A/claude-skills
/plugin install voice-issue@m0x6a
```
