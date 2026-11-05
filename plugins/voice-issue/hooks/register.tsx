import { atom, read, update } from 'claude-code'
import type { EngineInterface as Engine, Register } from 'claude-code'

import type { Draft, Session } from '../types'

const PANE = 'voice-issue'
const TITLE = 'Voice → issue'

const EMPTY: Session = {
  phase: 'idle',
  repo: null,
  transcript: '',
  draft: null,
  url: null,
  error: null,
}

// Bump the tag when Session's fields change: it declines what an earlier version stored.
const session = atom({ plugin: 'voice-issue', key: 'session' } as const, EMPTY, {
  shape: 'session-1',
})

// Runs faster-whisper on CPU and prints the transcript. argv: 16 kHz mono s16 WAV, model name.
// The WAV is read with the standard library, so no audio decoder (PyAV) is needed.
const TRANSCRIBE = `
import sys, wave
import numpy as np
from faster_whisper import WhisperModel
with wave.open(sys.argv[1]) as w:
    audio = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
model = WhisperModel(sys.argv[2], device="cpu", compute_type="int8")
segments, _ = model.transcribe(audio, language="en", vad_filter=True)
print(" ".join(s.text.strip() for s in segments).strip())
`

const SYSTEM = `You turn a spoken voice note into a GitHub issue. The note was transcribed by
speech recognition, so fix obvious mis-hearings of technical words, drop filler and
false starts, and keep every concrete fact the speaker gave (names, paths, numbers,
error text). Never invent facts, steps or requirements the speaker did not say.

Write the issue in English.

Answer with one JSON object and nothing else:
{"title": string, "body": string, "labels": string[]}

- title: imperative or descriptive, under 72 characters, no trailing period.
- body: GitHub Markdown using only the sections the note gives material for, in this order:
  "## Summary" (one or two sentences, always present),
  "## Context" (why, background, where it happens),
  "## Current behaviour" and "## Expected behaviour" (for bugs),
  "## Steps to reproduce" (numbered, for bugs),
  "## Proposal" (for features or changes),
  "## Acceptance criteria" (a "- [ ]" checklist of observable outcomes),
  "## Open questions" (things the speaker was unsure about).
- labels: zero or more names chosen ONLY from the repository's labels listed in the prompt.`

type Running = { wav: string; ended: Promise<void> }

let whisperModel = 'small.en'
let draftModel = 'sonnet'
let recording: Running | null = null
let labels: string[] = []

function set($: Engine, patch: Partial<Session>) {
  return update($, session, s => ({ ...s, ...patch }))
}

async function fail($: Engine, error: string) {
  await set($, { phase: 'error', error })
}

async function open($: Engine) {
  await $.ui.open({ id: PANE, title: TITLE, focus: true })
}

async function start($: Engine) {
  if (recording) return
  await set($, { ...EMPTY, phase: 'recording' })

  const repo = await $.process.run(['gh', 'repo', 'view', '--json', 'nameWithOwner', '-q', '.nameWithOwner'])
  if (repo.exitCode !== 0) {
    return fail($, `This folder is not a GitHub repository gh can see: ${repo.stderr.trim()}`)
  }
  await set($, { repo: repo.stdout.trim() })
  void $.process
    .run(['gh', 'label', 'list', '--limit', '200', '--json', 'name', '-q', '.[].name'])
    .then(r => {
      labels = r.exitCode === 0 ? r.stdout.split('\n').map(l => l.trim()).filter(Boolean) : []
    })

  const tmp = await $.process.run(['mktemp', '--suffix', '.voice-issue.wav'])
  if (tmp.exitCode !== 0) return fail($, 'Could not create a temporary file for the recording.')
  const wav = tmp.stdout.trim()

  const child = $.process.spawn({
    argv: ['pw-record', '--rate', '16000', '--channels', '1', '--format', 's16', wav],
  })
  const ended = (async () => {
    try {
      for await (const _ of child) {
        // pw-record writes nothing we need; the loop is the child's life.
      }
    } catch (err) {
      await fail($, `pw-record could not start: ${String(err)}`)
    }
  })()
  recording = { wav, ended }
}

async function stop($: Engine) {
  const running = recording
  if (!running) return
  recording = null
  // SIGINT lets pw-record finish the WAV header; the spawn loop then ends by itself.
  await $.process.run(['pkill', '-INT', '-f', running.wav])
  await running.ended

  await set($, { phase: 'transcribing' })
  const heard = await $.process.run(['python3', '-P', '-c', TRANSCRIBE, running.wav, whisperModel], {
    timeoutMs: 600_000,
  })
  void $.process.run(['rm', '-f', running.wav])
  if (heard.exitCode !== 0) {
    const tail = heard.stderr.trim().split('\n').slice(-3).join('\n')
    return fail($, `Transcription failed:\n${tail}`)
  }
  const transcript = heard.stdout.trim()
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

export const register: Register = (on, options) => {
  whisperModel = String(options.whisperModel ?? 'small.en')
  draftModel = String(options.draftModel ?? 'sonnet')
  recording = null
  labels = []

  on('session.start', async ($, e, next) => {
    await $.command.register({
      name: 'voice-issue',
      description: 'Speak a note and turn it into a structured GitHub issue',
    })
    // A reload drops the running recorder; clear any step it left half done.
    const s = await read($, session)
    if (s.phase !== 'review' && s.phase !== 'done') await set($, EMPTY)
    return next(e)
  })

  on('command.run', { command: 'voice-issue' }, async $ => {
    await open($)
    await start($)
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
            <Button key="again" label="Record again" hotkey="r" autoFocus onPress={() => void start($)} />
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
