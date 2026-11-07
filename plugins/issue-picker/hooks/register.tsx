import { atom, read, update } from 'claude-code'
import type { EngineInterface as Engine, Register } from 'claude-code'

import type { Detail, Issue, Picker } from '../types'

const PANE = 'issue-picker'
const TITLE = 'Open issues'

const EMPTY: Picker = {
  phase: 'idle',
  provider: null,
  repo: null,
  issues: [],
  filter: '',
  detail: null,
  isTmux: false,
  error: null,
}

// Bump the tag when Picker's fields change: it declines what an earlier version stored.
const picker = atom({ plugin: 'issue-picker', key: 'picker' } as const, EMPTY, {
  shape: 'picker-1',
})

// One issue tracker. GitHub is the only one today. Adding Azure DevOps, Jira or GitLab means
// one more entry in PROVIDERS and one more case in detectRepo, listIssues and viewIssue; the
// pane and the start actions only see Issue and Detail.
type ProviderId = 'github'
type Provider = {
  id: ProviderId
  label: string
  // What the started Claude session is told to run to read the issue.
  readCommand: (repo: string, number: number) => string
}

const PROVIDERS: Provider[] = [
  {
    id: 'github',
    label: 'GitHub',
    readCommand: (repo, number) => `gh issue view ${number} --repo ${repo} --comments`,
  },
]

type Ran = { exitCode: number; stdout: string; stderr: string }

// Runs a command and never rejects: a command that cannot start reads as exit code 127.
async function tryRun($: Engine, argv: string[], timeoutMs = 30_000): Promise<Ran> {
  try {
    return await $.process.run(argv, { timeoutMs })
  } catch (err) {
    return { exitCode: 127, stdout: '', stderr: String(err) }
  }
}

function lastLine(text: string) {
  return text.trim().split('\n').pop() ?? ''
}

let limit = 200
let tmuxTarget = 'window'

// The repository (or project) of the current folder on that tracker, or null when it has none.
async function detectRepo($: Engine, id: ProviderId): Promise<string | null> {
  switch (id) {
    case 'github': {
      const r = await tryRun($, ['gh', 'repo', 'view', '--json', 'nameWithOwner', '-q', '.nameWithOwner'])
      return r.exitCode === 0 && r.stdout.trim() ? r.stdout.trim() : null
    }
  }
}

async function listIssues($: Engine, id: ProviderId, repo: string): Promise<Issue[]> {
  switch (id) {
    case 'github': {
      const r = await tryRun($, [
        'gh', 'issue', 'list', '--repo', repo, '--state', 'open', '--limit', String(limit),
        '--json', 'number,title,labels,author,updatedAt',
      ])
      if (r.exitCode !== 0) throw new Error(`gh issue list failed: ${lastLine(r.stderr)}`)
      const raw = JSON.parse(r.stdout) as Array<{
        number: number
        title: string
        labels: Array<{ name: string }>
        author: { login: string } | null
        updatedAt: string
      }>
      return raw.map(i => ({
        number: i.number,
        title: i.title,
        labels: i.labels.map(l => l.name),
        author: i.author?.login ?? '',
        updatedAt: i.updatedAt,
      }))
    }
  }
}

async function viewIssue($: Engine, id: ProviderId, repo: string, number: number): Promise<Detail> {
  switch (id) {
    case 'github': {
      const r = await tryRun($, [
        'gh', 'issue', 'view', String(number), '--repo', repo, '--json', 'number,title,body,url,comments',
      ])
      if (r.exitCode !== 0) throw new Error(`gh issue view failed: ${lastLine(r.stderr)}`)
      const raw = JSON.parse(r.stdout) as { number: number; title: string; body: string; url: string; comments: unknown[] }
      return { number: raw.number, title: raw.title, body: raw.body, url: raw.url, comments: raw.comments.length }
    }
  }
}

function set($: Engine, patch: Partial<Picker>) {
  return update($, picker, s => ({ ...s, ...patch }))
}

function providerOf(s: Picker) {
  return PROVIDERS.find(p => p.id === s.provider) ?? null
}

async function load($: Engine) {
  await set($, { ...EMPTY, phase: 'loading', isTmux: Boolean(await $.env.get('TMUX')) })
  for (const p of PROVIDERS) {
    const repo = await detectRepo($, p.id)
    if (!repo) continue
    await set($, { provider: p.id, repo })
    try {
      const issues = await listIssues($, p.id, repo)
      return set($, { phase: 'list', issues })
    } catch (err) {
      return set($, { phase: 'error', error: (err as Error).message })
    }
  }
  const names = PROVIDERS.map(p => p.label).join(', ')
  await set($, {
    phase: 'error',
    error: `This folder is not a repository on a supported tracker (${names}). For GitHub, check that gh is installed and logged in (gh auth status).`,
  })
}

async function pick($: Engine, number: number) {
  const s = await read($, picker)
  const p = providerOf(s)
  if (!p || !s.repo) return
  const known = s.issues.find(i => i.number === number)
  await set($, {
    phase: 'detail',
    detail: { number, title: known?.title ?? `#${number}`, body: '', url: '', comments: 0 },
  })
  try {
    await set($, { detail: await viewIssue($, p.id, s.repo, number) })
  } catch (err) {
    await set($, { phase: 'error', error: (err as Error).message })
  }
}

function startPrompt(s: Picker, d: Detail) {
  const p = providerOf(s)
  const how = p && s.repo ? ` Read it first with \`${p.readCommand(s.repo, d.number)}\`,` : ' Read it first,'
  return `Work on issue #${d.number} in ${s.repo}: "${d.title}".${how} then make a plan and check it with me before you change any code.`
}

async function startHere($: Engine) {
  const s = await read($, picker)
  if (!s.detail) return
  await $.ui.close({ id: PANE })
  void $.prompt.submit({ text: startPrompt(s, s.detail) })
}

async function fillPrompt($: Engine) {
  const s = await read($, picker)
  if (!s.detail) return
  const filled = await $.prompt.fill({ text: startPrompt(s, s.detail) })
  if (filled.isFilled) await $.ui.close({ id: PANE })
  else $.ui.toast('The prompt box is not available right now.')
}

// Starts a new Claude CLI session on the issue in a tmux window or split, in this folder.
async function startInTmux($: Engine) {
  const s = await read($, picker)
  const d = s.detail
  if (!d) return
  const cwd = await $.session.cwd()
  const where =
    tmuxTarget === 'split-right'
      ? ['split-window', '-h']
      : tmuxTarget === 'split-below'
        ? ['split-window', '-v']
        : ['new-window', '-n', `#${d.number}`]
  // Several arguments after the options: tmux runs claude directly, with no shell to quote for.
  const r = await tryRun($, ['tmux', ...where, '-c', cwd, 'claude', startPrompt(s, d)])
  if (r.exitCode !== 0) {
    $.ui.toast(`tmux could not start Claude: ${lastLine(r.stderr) || `exit ${r.exitCode}`}`)
    return
  }
  $.ui.toast(`Claude started on #${d.number} in a new tmux ${tmuxTarget === 'window' ? 'window' : 'pane'}.`)
}

function matches(issue: Issue, filter: string) {
  const f = filter.trim().toLowerCase().replace(/^#/, '')
  if (!f) return true
  return (
    String(issue.number).startsWith(f) ||
    issue.title.toLowerCase().includes(f) ||
    issue.labels.some(l => l.toLowerCase().includes(f))
  )
}

function clip(text: string, width: number) {
  return text.length > width ? `${text.slice(0, Math.max(1, width - 1))}…` : text
}

export const register: Register = (on, options) => {
  limit = Math.max(1, Math.min(1000, Number(options.limit ?? 200)))
  tmuxTarget = String(options.tmuxTarget ?? 'window')

  on('session.start', async ($, e, next) => {
    await $.command.register({
      name: 'issues',
      description: 'List the open issues of this repository and start Claude on one',
      argumentHint: '[filter | number]',
    })
    return next(e)
  })

  on('command.run', { command: 'issues' }, async ($, e) => {
    await $.ui.open({ id: PANE, title: TITLE, focus: true })
    const arg = e.args.trim()
    await load($)
    const s = await read($, picker)
    if (s.phase !== 'list') return { text: s.error ?? 'Could not list issues.' }
    if (/^#?\d+$/.test(arg)) {
      void pick($, Number(arg.replace('#', '')))
      return { text: `Showing issue ${arg} in the Open issues pane.` }
    }
    if (arg) await set($, { filter: arg })
    const count = s.issues.length === 1 ? '1 open issue' : `${s.issues.length} open issues`
    return { text: `${count} in ${s.repo}; pick one in the Open issues pane.` }
  })

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const { Box, Text, Button, Input, Markdown, Link } = $.ui.resolve(e)
    const s = await read($, picker)
    const width = Math.max(20, (e.viewport?.columns ?? 80) - 4)
    const rows = Math.max(3, (e.viewport?.rows ?? 24) - 8)
    const provider = providerOf(s)
    const header = s.repo ? (
      <Text dimColor>
        {provider?.label ?? ''} · {s.repo}
      </Text>
    ) : null

    switch (s.phase) {
      case 'idle':
        return <Button key="load" label="Load open issues" hotkey="l" variant="primary" autoFocus onPress={() => void load($)} />
      case 'loading':
        return <Text dimColor>Fetching open issues…</Text>
      case 'error':
        return (
          <Box flexDirection="column" gap={1}>
            <Text color="red">{s.error}</Text>
            <Button key="retry" label="Try again" hotkey="r" autoFocus onPress={() => void load($)} />
          </Box>
        )
      case 'list': {
        const shown = s.issues.filter(i => matches(i, s.filter))
        return (
          <Box flexDirection="column" gap={1}>
            {header}
            <Input
              key="filter"
              label="Filter"
              placeholder="number, words in the title, or a label"
              value={s.filter}
              onInput={text => void set($, { filter: text })}
              onSubmit={() => {
                const only = shown.length === 1 ? shown[0] : undefined
                if (only) void pick($, only.number)
              }}
            />
            <Box flexDirection="column">
              {s.issues.length === 0 && <Text dimColor>No open issues. 🎉</Text>}
              {s.issues.length > 0 && shown.length === 0 && <Text dimColor>Nothing matches “{s.filter}”.</Text>}
              {shown.slice(0, rows).map((issue, i) => {
                const tags = issue.labels.length ? `  [${issue.labels.join(', ')}]` : ''
                const label = clip(`#${issue.number}  ${issue.title}${tags}`, width)
                return (
                  <Button
                    key={`issue-${issue.number}`}
                    label={label}
                    plain
                    autoFocus={i === 0 ? true : undefined}
                    onPress={() => void pick($, issue.number)}
                  />
                )
              })}
              {shown.length > rows && <Text dimColor>…and {shown.length - rows} more; type to filter.</Text>}
            </Box>
            <Button key="refresh" label="Refresh" hotkey="r" onPress={() => void load($)} />
          </Box>
        )
      }
      case 'detail': {
        const d = s.detail
        if (!d) return <Text dimColor>No issue selected.</Text>
        const isLoading = !d.url
        return (
          <Box flexDirection="column" gap={1}>
            {header}
            <Text bold>
              #{d.number} {d.title}
            </Text>
            {isLoading ? (
              <Text dimColor>Loading the issue…</Text>
            ) : (
              <Box flexDirection="column" gap={1}>
                <Link href={d.url} label={d.url} />
                {d.comments > 0 && <Text dimColor>{d.comments} comment{d.comments === 1 ? '' : 's'}</Text>}
                <Markdown text={d.body.trim() || '_No description._'} />
              </Box>
            )}
            <Box gap={2}>
              {s.isTmux && (
                <Button key="tmux" label="Start in tmux" hotkey="t" variant="primary" autoFocus onPress={() => void startInTmux($)} />
              )}
              <Button
                key="here"
                label="Start here"
                hotkey="s"
                variant={s.isTmux ? undefined : 'primary'}
                autoFocus={s.isTmux ? undefined : true}
                onPress={() => void startHere($)}
              />
              <Button key="fill" label="Put in prompt" hotkey="p" onPress={() => void fillPrompt($)} />
              <Button key="back" label="Back" hotkey="b" onPress={() => void set($, { phase: 'list', detail: null })} />
            </Box>
          </Box>
        )
      }
    }
  })
}
