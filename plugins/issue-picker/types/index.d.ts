export type Issue = {
  number: number
  title: string
  labels: string[]
  author: string
  updatedAt: string
}

export type Detail = {
  number: number
  title: string
  body: string
  url: string
  comments: number
}

export type Picker = {
  phase: 'idle' | 'loading' | 'list' | 'detail' | 'error'
  provider: string | null
  repo: string | null
  issues: Issue[]
  filter: string
  detail: Detail | null
  isTmux: boolean
  error: string | null
}

declare module 'claude-code' {
  interface PluginState {
    'issue-picker': { picker: Shaped<Picker> }
  }
}
