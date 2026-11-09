import { atom, read, update } from 'claude-code'
import type { EngineInterface as Engine, Register } from 'claude-code'

import type { Draft, Session } from '../types'

const PANE = 'voice-issue'
const TITLE = 'Voice → issue'
const SETUP_HINT = 'Run /voice-issue setup to install what is missing.'

const EMPTY: Session = {
  phase: 'idle',
  repo: null,
  transcript: '',
  draft: null,
  url: null,
  error: null,
  setupLog: [],
  isSetupDone: false,
}

// Bump the tag when Session's fields change: it declines what an earlier version stored.
const session = atom({ plugin: 'voice-issue', key: 'session' } as const, EMPTY, {
  shape: 'session-2',
})

// The resident transcriber. argv: socket path, model name, idle seconds.
// Loads the model once, prints "ready", then answers one WAV path per connection with a
// JSON line. It exits by itself after the idle time, so nothing outlives a crashed session.
// The WAV (16 kHz mono s16) is read with the standard library: no PyAV needed.
const WORKER = `
import json, os, socket, sys, wave
import numpy as np
from faster_whisper import WhisperModel
path, name, idle = sys.argv[1], sys.argv[2], float(sys.argv[3])
model = WhisperModel(name, device="cpu", compute_type="int8")
try:
    os.unlink(path)
except FileNotFoundError:
    pass
server = socket.socket(socket.AF_UNIX)
server.bind(path)
os.chmod(path, 0o600)
server.listen(1)
server.settimeout(idle)
print("ready", flush=True)
try:
    while True:
        try:
            conn, _ = server.accept()
        except socket.timeout:
            break
        with conn:
            wav = conn.makefile().readline().strip()
            try:
                with wave.open(wav) as w:
                    audio = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
                segments, _ = model.transcribe(audio, language="en", vad_filter=True)
                reply = {"text": " ".join(s.text.strip() for s in segments).strip()}
            except Exception as err:
                reply = {"error": str(err)}
            conn.sendall((json.dumps(reply) + "\\n").encode())
finally:
    server.close()
    try:
        os.unlink(path)
    except FileNotFoundError:
        pass
`

// Asks the worker for one transcript. argv: socket path, WAV path. Imports nothing heavy.
const CLIENT = `
import socket, sys
s = socket.socket(socket.AF_UNIX)
s.settimeout(600)
s.connect(sys.argv[1])
s.sendall((sys.argv[2] + "\\n").encode())
print(s.makefile().readline().strip())
`

const SYSTEM = `You turn a spoken voice note into a GitHub issue. The note was transcribed by
speech recognition, so fix obvious mis-hearings of technical words, drop filler and
false starts, and keep every concrete fact the speaker gave (names, paths, numbers,
error text). Never invent facts, steps or requirements the speaker did not say.

Write the issue in English.

Answer with one JSON object and nothing else:
{"title": string, "body": string, "labels": string[]}

- title: imperative or descriptive, under 72 characters, no trailing period.
- body: GitHub Markdown that someone can take straight into planning. Keep it short and
  plain; it is a starting point for a plan, not the plan. Sections, in this order:
  "## Summary" (one or two sentences; always present),
  "## What the change does" (always present: the behaviour after the change, in a few
    bullets; for a bug, what happens now and what should happen instead),
  "## How we'll know it works" (always present: a "- [ ]" checklist of observable
    outcomes someone could check by hand or with a test),
  "## What it must not break" (always present: existing behaviour, users or integrations
    that must keep working),
  "## Context" (optional: why, background, where it happens),
  "## Steps to reproduce" (optional, numbered, for bugs),
  "## Open questions" (optional: things the speaker was unsure about).
  The three middle sections are always present even when the note says nothing for them:
  then write exactly "_Not covered in the note; settle this in planning._" as the section
  body instead of guessing. Only fill them from what the speaker said or what follows
  directly from it; omit the optional sections when the note gives no material for them.
- labels: zero or more names chosen ONLY from the repository's labels listed in the prompt.`

type Running = { wav: string; ended: Promise<void> }
type Worker = { sock: string; ready: Promise<void> }

let whisperModel = 'small.en'
let draftModel = 'sonnet'
let idleMinutes = 10
let recording: Running | null = null
let worker: Worker | null = null
let labels: string[] = []
let python: string | null = null

// faster-whisper lives in its own venv on a Python that has wheels for every dependency
// (onnxruntime trails new Python releases; pip then backtracks into building old PyAV from source).
const VENV_PYTHON_VERSION = '3.13'

async function venvDir($: Engine) {
  const r = await tryRun($, ['sh', '-c', 'printf %s "${XDG_DATA_HOME:-$HOME/.local/share}/voice-issue/venv"'])
  return r.stdout.trim()
}

// The venv's Python when setup has created it, otherwise the system python3 (an earlier
// install with pip --user still works).
async function pythonFor($: Engine) {
  if (python) return python
  const venv = `${await venvDir($)}/bin/python`
  python = (await tryRun($, ['test', '-x', venv])).exitCode === 0 ? venv : 'python3'
  return python
}

function set($: Engine, patch: Partial<Session>) {
  return update($, session, s => ({ ...s, ...patch }))
}

async function fail($: Engine, error: string) {
  await set($, { phase: 'error', error })
}

async function open($: Engine) {
  await $.ui.open({ id: PANE, title: TITLE, focus: true })
}

// Runs a command and never rejects: a command that cannot start reads as exit code 127.
async function tryRun($: Engine, argv: string[], timeoutMs = 30_000) {
  try {
    return await $.process.run(argv, { timeoutMs })
  } catch (err) {
    return { exitCode: 127, stdout: '', stderr: String(err) }
  }
}

function lastLines(text: string, n = 3) {
  return text.trim().split('\n').slice(-n).join('\n')
}

// Starts the resident transcriber unless it is running. Called when recording starts, so
// the model loads while the person speaks.
async function ensureWorker($: Engine): Promise<Worker> {
  if (worker) return worker
  const dir = await tryRun($, ['mktemp', '-d', '--suffix', '.voice-issue'])
  if (dir.exitCode !== 0) throw new Error('Could not create a folder for the transcriber socket.')
  const sock = `${dir.stdout.trim()}/whisper.sock`

  let markReady = () => {}
  let markFailed = (_: Error) => {}
  const ready = new Promise<void>((resolve, reject) => {
    markReady = resolve
    markFailed = reject
  })
  ready.catch(() => {}) // a failure is reported where the transcript is awaited
  const me: Worker = { sock, ready }
  worker = me

  void (async () => {
    let stderr = ''
    let isReady = false
    try {
      const child = $.process.spawn({
        argv: [await pythonFor($), '-P', '-c', WORKER, sock, whisperModel, String(idleMinutes * 60)],
      })
      for await (const { stream, text } of child) {
        if (stream === 'stderr') stderr = (stderr + text).slice(-4000)
        else if (!isReady && text.includes('ready')) {
          isReady = true
          markReady()
        }
      }
    } catch (err) {
      stderr += String(err)
    } finally {
      if (worker === me) worker = null
      if (!isReady) markFailed(new Error(lastLines(stderr) || 'the transcriber exited before it was ready'))
    }
  })()
  return me
}

async function stopWorker($: Engine) {
  const running = worker
  worker = null
  if (running) await tryRun($, ['pkill', '-TERM', '-f', running.sock])
}

async function transcribe($: Engine, wav: string): Promise<string> {
  const w = await ensureWorker($)
  await w.ready
  const r = await tryRun($, [await pythonFor($), '-P', '-c', CLIENT, w.sock, wav], 600_000)
  if (r.exitCode !== 0) throw new Error(lastLines(r.stderr))
  const reply = JSON.parse(r.stdout) as { text?: string; error?: string }
  if (reply.error) throw new Error(reply.error)
  return (reply.text ?? '').trim()
}

async function start($: Engine) {
  if (recording) return
  await set($, { ...EMPTY, phase: 'recording' })

  const repo = await tryRun($, ['gh', 'repo', 'view', '--json', 'nameWithOwner', '-q', '.nameWithOwner'])
  if (repo.exitCode !== 0) {
    return fail($, `This folder is not a GitHub repository gh can see: ${lastLines(repo.stderr)}`)
  }
  await set($, { repo: repo.stdout.trim() })
  void tryRun($, ['gh', 'label', 'list', '--limit', '200', '--json', 'name', '-q', '.[].name']).then(r => {
    labels = r.exitCode === 0 ? r.stdout.split('\n').map(l => l.trim()).filter(Boolean) : []
  })
  void ensureWorker($).catch(() => {})

  const tmp = await tryRun($, ['mktemp', '--suffix', '.voice-issue.wav'])
  if (tmp.exitCode !== 0) return fail($, 'Could not create a temporary file for the recording.')
  const wav = tmp.stdout.trim()

  const ended = (async () => {
    try {
      const child = $.process.spawn({
        argv: ['pw-record', '--rate', '16000', '--channels', '1', '--format', 's16', wav],
      })
      for await (const _ of child) {
        // pw-record writes nothing we need; the loop is the child's life.
      }
    } catch (err) {
      await fail($, `pw-record could not start (${String(err)}). ${SETUP_HINT}`)
    }
  })()
  recording = { wav, ended }
}

async function stop($: Engine) {
  const running = recording
  if (!running) return
  recording = null
  // SIGINT lets pw-record finish the WAV header; the spawn loop then ends by itself.
  await tryRun($, ['pkill', '-INT', '-f', running.wav])
  await running.ended

  await set($, { phase: 'transcribing' })
  let transcript: string
  try {
    transcript = await transcribe($, running.wav)
  } catch (err) {
    return fail($, `Transcription failed:\n${(err as Error).message}\n${SETUP_HINT}`)
  } finally {
    void tryRun($, ['rm', '-f', running.wav])
  }
  if (!transcript) return fail($, 'Nothing was heard. Check the microphone and try again.')

  await set($, { transcript })
  await draft($, transcript, null)
}

async function draft($: Engine, transcript: string, revise: string | null) {
  await set($, { phase: 'drafting' })
  const current = (await read($, session)).draft
  const prompt = [
    `Repository labels: ${labels.length ? labels.join(', ') : '(none; return an empty list)'}`,
    `Voice note transcript:\n"""\n${transcript}\n"""`,
    revise && current
      ? `Current draft:\n${JSON.stringify(current)}\n\nRevise it as asked: ${revise}`
      : '',
  ]
    .filter(Boolean)
    .join('\n\n')

  const reply = await $.model.complete({
    model: draftModel,
    system: SYSTEM,
    prompt,
    maxTokens: 3000,
    effort: 'low',
    timeoutMs: 120_000,
  })
  if (!reply.isAnswered) return fail($, `Drafting failed: ${reply.reason}`)

  const parsed = parseDraft(reply.text, labels)
  if (!parsed) return fail($, `The model did not return a usable issue:\n${reply.text.slice(0, 400)}`)
  await set($, { phase: 'review', draft: parsed })
}

async function create($: Engine) {
  const s = await read($, session)
  if (!s.draft) return
  await set($, { phase: 'creating' })
  const body = `${s.draft.body.trim()}\n\n<details><summary>Original voice note</summary>\n\n${s.transcript}\n\n</details>\n`
  const argv = ['gh', 'issue', 'create', '--title', s.draft.title, '--body-file', '-']
  for (const label of s.draft.labels) argv.push('--label', label)
  const made = await $.process.run(argv, { stdin: body, timeoutMs: 60_000 })
  if (made.exitCode !== 0) return fail($, `gh issue create failed: ${made.stderr.trim()}`)
  const url = made.stdout.trim().split('\n').pop() ?? ''
  await set($, { phase: 'done', url })
  $.ui.toast(`Issue created: ${url}`)
  $.ui.log(`voice-issue: created ${url}`)
}

async function speak($: Engine) {
  await open($)
  await start($)
}

async function note($: Engine, line: string) {
  await update($, session, s => ({ ...s, setupLog: [...s.setupLog, line] }))
}

// Makes sure faster-whisper imports, preferring a uv-managed venv on Python 3.13 and falling
// back to pip install --user on the system python3 when uv is not installed.
async function installWhisper($: Engine): Promise<boolean> {
  const check = ['-P', '-c', 'import faster_whisper, numpy']
  const dir = await venvDir($)
  const venv = `${dir}/bin/python`
  if ((await tryRun($, [venv, ...check])).exitCode === 0) {
    python = venv
    await note($, `✓ faster-whisper installed (${dir})`)
    return true
  }

  if ((await tryRun($, ['uv', '--version'])).exitCode === 0) {
    await note($, `… creating a Python ${VENV_PYTHON_VERSION} venv in ${dir} and installing faster-whisper`)
    const mk = await tryRun($, ['uv', 'venv', '--allow-existing', '--python', VENV_PYTHON_VERSION, dir], 600_000)
    if (mk.exitCode !== 0) {
      await note($, `✗ uv venv failed: ${lastLines(mk.stderr, 2)}`)
      return false
    }
    const pip = await tryRun($, ['uv', 'pip', 'install', '--python', venv, 'faster-whisper'], 600_000)
    if (pip.exitCode !== 0) {
      await note($, `✗ uv pip install failed: ${lastLines(pip.stderr, 2)}`)
      return false
    }
    python = venv
    await note($, '✓ faster-whisper installed')
    return true
  }

  const sys = await tryRun($, ['python3', ...check])
  if (sys.exitCode === 0) {
    python = 'python3'
    await note($, '✓ faster-whisper installed (system python3)')
    return true
  }
  if (sys.exitCode === 127) {
    await note($, '✗ neither uv nor python3 found: install uv (https://docs.astral.sh/uv/)')
    return false
  }
  await note($, '… uv not found; trying pip install --user faster-whisper on the system python3')
  const pip = await tryRun($, ['python3', '-m', 'pip', 'install', '--user', 'faster-whisper'], 600_000)
  if (pip.exitCode === 0) {
    python = 'python3'
    await note($, '✓ faster-whisper installed')
    return true
  }
  await note($, `✗ pip install failed: ${lastLines(pip.stderr, 2)}`)
  await note($, '  If your python3 is very new, its wheels may be missing: install uv and run setup again.')
  return false
}

// Checks every requirement, installs faster-whisper if it is missing and downloads the model,
// so the first recording does not stall on a 500 MB download.
async function setup($: Engine) {
  await set($, { ...EMPTY, phase: 'setup' })
  let isOk = true

  const pw = await tryRun($, ['pw-record', '--version'])
  if (pw.exitCode === 0) await note($, '✓ pw-record (PipeWire) found')
  else {
    isOk = false
    await note($, '✗ pw-record not found: install PipeWire tools (Fedora: sudo dnf install pipewire-utils)')
  }

  const gh = await tryRun($, ['gh', 'auth', 'status'])
  if (gh.exitCode === 0) await note($, '✓ gh is logged in')
  else {
    isOk = false
    await note($, gh.exitCode === 127 ? '✗ gh not found: install the GitHub CLI' : '✗ gh is not logged in: run gh auth login')
  }

  if (!(await installWhisper($))) isOk = false
  const py = await pythonFor($)

  if (isOk) {
    await note($, `… downloading the ${whisperModel} model (once; about 75 MB to 3 GB by size)`)
    const dl = await tryRun(
      $,
      [py, '-P', '-c', 'import sys\nfrom faster_whisper import download_model\ndownload_model(sys.argv[1])', whisperModel],
      600_000,
    )
    if (dl.exitCode === 0) await note($, `✓ ${whisperModel} model ready`)
    else {
      isOk = false
      await note($, `✗ model download failed: ${lastLines(dl.stderr, 2)}`)
    }
  }

  await note($, isOk ? 'All set.' : 'Fix the ✗ lines above, then run /voice-issue setup again.')
  await set($, { isSetupDone: true })
}

export const register: Register = (on, options) => {
  whisperModel = String(options.whisperModel ?? 'small.en')
  draftModel = String(options.draftModel ?? 'sonnet')
  idleMinutes = Math.max(1, Number(options.idleMinutes ?? 10))
  recording = null
  worker = null
  labels = []
  python = null

  on('session.start', async ($, e, next) => {
    await $.command.register({
      name: 'voice-issue',
      description: 'Speak a note and turn it into a structured GitHub issue ("setup" checks and installs what it needs)',
      argumentHint: '[setup]',
    })
    // A reload drops the recorder and the transcriber; clear any step left half done.
    const s = await read($, session)
    if (s.phase !== 'review' && s.phase !== 'done') await set($, EMPTY)
    return next(e)
  })

  on('session.end', async ($, e, next) => {
    await stopWorker($)
    return next(e)
  })

  on('command.run', { command: 'voice-issue' }, async ($, e) => {
    await open($)
    if (e.args.trim() === 'setup') {
      void setup($)
      return { text: 'Checking what voice-issue needs; progress is in the Voice → issue pane.' }
    }
    void start($)
    return { text: 'Recording. Press s in the Voice → issue pane to stop.' }
  })

  // A one-line band above the prompt: the always-there button.
  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    if (e.props.hasSurvey) return next(e)
    const { Box, Text, Button } = $.ui.resolve(e)
    const s = await read($, session)

    if (s.phase === 'recording') {
      return (
        <Box gap={1}>
          <Text color="red">● Recording</Text>
          <Button key="band-stop" label="■ Stop and draft" variant="primary" onPress={() => void stop($)} />
        </Box>
      )
    }
    if (s.phase === 'transcribing' || s.phase === 'drafting' || s.phase === 'creating') {
      return <Text dimColor>🎙 {s.phase}…</Text>
    }
    if (s.phase === 'setup' && !s.isSetupDone) return <Text dimColor>🎙 setting up…</Text>
    if (s.phase === 'review') {
      return (
        <Box gap={1}>
          <Text dimColor>🎙 Draft ready:</Text>
          <Button key="band-review" label="Review issue" onPress={() => void open($)} />
        </Box>
      )
    }
    return <Button key="band-speak" label="🎙 Speak an issue" onPress={() => void speak($)} />
  })

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const { Box, Text, Button, Input, Markdown } = $.ui.resolve(e)
    const s = await read($, session)
    const repo = s.repo ? <Text dimColor>Repository: {s.repo}</Text> : null

    switch (s.phase) {
      case 'idle':
        return (
          <Box flexDirection="column" gap={1}>
            <Text>Speak a bug, idea or task; you review the issue before it is created.</Text>
            <Button key="rec" label="Record" hotkey="r" variant="primary" autoFocus onPress={() => void start($)} />
          </Box>
        )
      case 'setup':
        return (
          <Box flexDirection="column" gap={1}>
            <Box flexDirection="column">
              {s.setupLog.map(line => (
                <Text color={line.startsWith('✗') ? 'red' : undefined} dimColor={line.startsWith('…')}>
                  {line}
                </Text>
              ))}
            </Box>
            {s.isSetupDone && (
              <Button key="rec" label="Record" hotkey="r" variant="primary" autoFocus onPress={() => void start($)} />
            )}
          </Box>
        )
      case 'recording':
        return (
          <Box flexDirection="column" gap={1}>
            {repo}
            <Text color="red">● Recording… speak now.</Text>
            <Button key="stop" label="Stop and draft" hotkey="s" variant="primary" autoFocus onPress={() => void stop($)} />
          </Box>
        )
      case 'transcribing':
        return <Text dimColor>Transcribing locally with faster-whisper ({whisperModel})…</Text>
      case 'drafting':
        return (
          <Box flexDirection="column" gap={1}>
            <Text dimColor>Drafting the issue with {draftModel}…</Text>
            <Text dimColor>Heard: {s.transcript}</Text>
          </Box>
        )
      case 'creating':
        return <Text dimColor>Creating the issue…</Text>
      case 'done':
        return (
          <Box flexDirection="column" gap={1}>
            <Text color="green">Created {s.url}</Text>
            <Button key="again" label="Record another" hotkey="r" autoFocus onPress={() => void start($)} />
          </Box>
        )
      case 'error':
        return (
          <Box flexDirection="column" gap={1}>
            <Text color="red">{s.error}</Text>
            <Box gap={2}>
              <Button key="again" label="Record again" hotkey="r" autoFocus onPress={() => void start($)} />
              <Button key="setup" label="Run setup" hotkey="u" onPress={() => void setup($)} />
            </Box>
          </Box>
        )
      case 'review': {
        const d = s.draft
        if (!d) return <Text dimColor>No draft.</Text>
        return (
          <Box flexDirection="column" gap={1}>
            {repo}
            <Text bold>{d.title}</Text>
            {d.labels.length > 0 && <Text dimColor>Labels: {d.labels.join(', ')}</Text>}
            <Markdown text={d.body} />
            <Input
              key="revise"
              label="Change something"
              placeholder="e.g. it's a bug, not a feature; add that it only fails on Safari"
              submitLabel="Revise"
              onSubmit={text => {
                if (text.trim()) void draft($, s.transcript, text.trim())
              }}
            />
            <Box gap={2}>
              <Button key="create" label="Create issue" hotkey="c" variant="primary" autoFocus onPress={() => void create($)} />
              <Button key="redo" label="Re-record" hotkey="r" onPress={() => void start($)} />
              <Button key="discard" label="Discard" hotkey="d" onPress={() => void set($, EMPTY)} />
            </Box>
          </Box>
        )
      }
    }
  })
}

function parseDraft(text: string, known: readonly string[]): Draft | null {
  const from = text.indexOf('{')
  const to = text.lastIndexOf('}')
  if (from < 0 || to <= from) return null
  try {
    const raw = JSON.parse(text.slice(from, to + 1)) as Partial<Draft>
    if (typeof raw.title !== 'string' || typeof raw.body !== 'string') return null
    const allowed = new Set(known)
    const labels = Array.isArray(raw.labels)
      ? raw.labels.filter((l): l is string => typeof l === 'string' && allowed.has(l))
      : []
    return { title: raw.title.trim().slice(0, 200), body: raw.body, labels }
  } catch {
    return null
  }
}
