# voice-issue

Speak a bug, idea or task and get a structured GitHub issue. Run `/voice-issue`, or press the
**🎙 Speak an issue** button above the prompt. A pane opens and starts recording from your default
microphone. Press `s` to stop. The note is transcribed locally with faster-whisper (the audio never
leaves your machine), and Claude drafts a title, labels chosen from the repository's existing labels,
and a short body you can take straight into planning. Every issue has a Summary and three planning
sections: **What the change does**, **How we'll know it works** (a checklist) and **What it must not
break**. When the note says nothing for one of them, the section says so instead of guessing, so the
gap is visible when you plan. Context, Steps to reproduce and Open questions are added when you gave
material for them. You review the draft. Type a correction
to revise it, then press `c` to create it with `gh issue create` in the current repository. The original
transcript is kept in a collapsed section of the issue.

## Install

```text
/plugin marketplace add m0x6A/claude-skills
/plugin install voice-issue@m0x6a
/voice-issue setup
```

`/voice-issue setup` checks for `pw-record` (PipeWire) and a logged-in `gh`, installs faster-whisper
with `pip install --user` if it is missing, and downloads the speech model once, so your first
recording does not wait on the download. Anything it cannot install itself is listed with the command
to run.

## The transcriber

Whisper is started when you begin recording, so the model loads while you speak. It then stays in
memory, so later notes transcribe in about two seconds instead of five. It stops by itself after
`idleMinutes` without use and when the session ends. Nothing is left running, even if Claude Code
crashes. It listens only on a private socket in a temporary folder that only you can open, never on
a network port.

## Options (config menu)

| Option | Default | What it does |
|---|---|---|
| `whisperModel` | `small.en` | Speech model (`tiny.en` … `medium.en`, `large-v3`). Larger is more accurate and slower. Run setup again after changing it. |
| `draftModel` | `sonnet` | The Claude model that writes the issue (`haiku`, `sonnet`, `opus`). |
| `idleMinutes` | `10` | How long Whisper stays loaded after its last use. |
