export type Phase =
  | 'idle'
  | 'setup'
  | 'recording'
  | 'transcribing'
  | 'drafting'
  | 'review'
  | 'creating'
  | 'done'
  | 'error'

export type Draft = { title: string; body: string; labels: string[] }

export type Session = {
  phase: Phase
  repo: string | null
  transcript: string
  draft: Draft | null
  url: string | null
  error: string | null
  setupLog: string[]
  isSetupDone: boolean
}

declare module 'claude-code' {
  interface PluginState {
    'voice-issue': { session: Shaped<Session> }
  }
}
