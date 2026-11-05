export type Phase =
  | 'idle'
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
}

declare module 'claude-code' {
  interface PluginState {
    'voice-issue': { session: Shaped<Session> }
  }
}
