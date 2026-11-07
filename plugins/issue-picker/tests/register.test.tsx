import { expect, test } from 'claude-code/testing'

const PANE = {
  plugin: 'issue-picker',
  component: 'Pane',
  requestId: 'issue-picker',
  props: {
    title: 'Open issues',
    isFocused: true,
    bodyColumns: 80,
    placement: 'dock',
    scroll: { offset: 0, bodyRows: 30 },
    view: {},
  },
} as const

const ISSUES = [
  { number: 6, title: 'List and select open issues', labels: [{ name: 'enhancement' }], author: { login: 'a' }, updatedAt: '' },
  { number: 4, title: 'Fix the band on narrow terminals', labels: [], author: { login: 'b' }, updatedAt: '' },
]
const ISSUE_6 = { number: 6, title: 'List and select open issues', body: '## Summary\nPick one.', url: 'https://github.com/o/r/issues/6', comments: [] }

type Calls = { argv: string[][]; submitted: string[] }

// Stands for the engine and the outside world: gh answers from the fixtures above, tmux
// succeeds, and TMUX is set or not as the test asks.
function world(on: Parameters<Parameters<typeof test>[1]>[1], tmux: string | undefined): Calls {
  const calls: Calls = { argv: [], submitted: [] }
  on('command.register', () => ({ value: { command: 'issues' } }))
  on('ui.open', () => ({ value: { isPlaced: true } }))
  on('ui.close', () => ({ value: {} }))
  on('ui.toast', () => ({ value: {} }))
  on('session.start', (_, e) => ({ cwd: e.cwd }))
  on('session.cwd', () => ({ value: '/work/repo' }))
  on('env.get', () => ({ value: tmux }))
  on('prompt.submit', (_, e) => {
    calls.submitted.push(e.text)
    return { text: e.text }
  })
  on('process.run', (_, e) => {
    const argv = [...e.argv]
    calls.argv.push(argv)
    const ok = (stdout: string) => ({ value: { exitCode: 0, stdout, stderr: '' } })
    if (argv[0] === 'gh' && argv[1] === 'repo') return ok('o/r\n')
    if (argv[0] === 'gh' && argv[2] === 'list') return ok(JSON.stringify(ISSUES))
    if (argv[0] === 'gh' && argv[2] === 'view') return ok(JSON.stringify(ISSUE_6))
    if (argv[0] === 'tmux') return ok('')
    return { value: { exitCode: 127, stdout: '', stderr: 'not found' } }
  })
  return calls
}

test('lists open issues, filters them and starts a new tmux window on the pick', async ($, on) => {
  const calls = world(on, '/tmp/tmux-1000/default,1,0')
  await $.session.start({ cwd: '/work/repo', surface: 'terminal', isInteractive: true })
  await $.command.run({ command: 'issues', args: '' })

  const ui = await $.ui.mount({ ...PANE, surface: 'terminal' })
  expect(await ui.find({ key: 'issue-6' })).toBeTruthy()
  expect(await ui.find({ key: 'issue-4' })).toBeTruthy()

  await ui.input({ key: 'filter', text: 'band', kind: 'change' })
  expect(await ui.find({ key: 'issue-6' })).toBeFalsy()
  expect(await ui.find({ key: 'issue-4' })).toBeTruthy()

  await ui.input({ key: 'filter', text: '#6', kind: 'change' })
  await ui.press({ key: 'issue-6' })
  expect((await ui.find({ type: 'Text', text: /#6 List and select/ }))).toBeTruthy()

  await ui.press({ key: 'tmux' })
  const tmux = calls.argv.find(a => a[0] === 'tmux')
  expect(tmux?.slice(0, 6)).toEqual(['tmux', 'new-window', '-n', '#6', '-c', '/work/repo'])
  expect(tmux?.[6]).toBe('claude')
  expect(tmux?.[7]).toContain('gh issue view 6 --repo o/r --comments')
  await ui.unmount()
})

test('outside tmux there is no tmux button, and Start here submits the prompt', async ($, on) => {
  const calls = world(on, undefined)
  await $.session.start({ cwd: '/work/repo', surface: 'terminal', isInteractive: true })
  await $.command.run({ command: 'issues', args: '6' })

  const ui = await $.ui.mount({ ...PANE, surface: 'terminal' })
  expect(await ui.find({ key: 'tmux' })).toBeFalsy()
  await ui.press({ key: 'here' })
  expect(calls.submitted[0]).toContain('Work on issue #6 in o/r')
  expect(calls.argv.some(a => a[0] === 'tmux')).toBe(false)
  await ui.unmount()
})
