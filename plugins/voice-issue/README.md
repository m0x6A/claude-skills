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

`/voice-issue setup` checks for a recorder and a logged-in `gh`, installs faster-whisper
if it is missing, and downloads the speech model once, so your first recording does not wait on the
download. Anything it cannot install itself is listed with the command to run.

| | Linux | macOS |
|---|---|---|
| Recorder | `pw-record` (PipeWire; Fedora: `sudo dnf install pipewire-utils`) | `rec` from SoX: `brew install sox` |
| GitHub CLI | `gh`, then `gh auth login` | `brew install gh`, then `gh auth login` |
| uv (recommended) | see [uv](https://docs.astral.sh/uv/) | `brew install uv` |

On macOS the first recording triggers a microphone prompt for your terminal app (Terminal, iTerm,
VS Code…). If you dismissed it, notes come out empty: allow the app under System Settings → Privacy &
Security → Microphone and restart it. Transcription runs on the CPU (int8), which is fast on Apple
Silicon.

faster-whisper goes into its own venv, `${XDG_DATA_HOME:-~/.local/share}/voice-issue/venv`, created
with [uv](https://docs.astral.sh/uv/) on Python 3.13. uv downloads that Python if you don't have it.
The venv keeps transcription working when your system Python is newer than the packages' wheels
(onnxruntime is usually the last to catch up). Without uv, setup falls back to
`pip install --user` on the system `python3`.

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
