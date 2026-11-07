# issue-picker

List the open issues of the repository you are in, pick one, and start Claude on it. Run `/issues`
(or `/issues <filter>`, or `/issues 6` to jump straight to #6). A pane lists the open issues with
their labels; type in the filter to narrow by number, title or label, and press Enter on one to read
it. From there:

| Key | Action |
|---|---|
| `t` | **Start in tmux**: opens a new tmux window (or split) in this folder running `claude` on the issue. Shown only when Claude Code runs inside tmux. |
| `s` | **Start here**: sends the issue to this session as a prompt. |
| `p` | **Put in prompt**: puts the same prompt in the prompt box so you can edit it first. |
| `b` | Back to the list. |

The started session is told to read the issue with `gh issue view <n> --comments` and to make a plan
and check it with you before it changes any code.

## Requirements

- The Claude Code CLI in a terminal, and `claude` on the `PATH` for the tmux action.
- A logged-in [GitHub CLI](https://cli.github.com/) (`gh auth status`).
- tmux 3.0 or newer for **Start in tmux**.

## Options (config menu)

| Option | Default | What it does |
|---|---|---|
| `tmuxTarget` | `window` | Where **Start in tmux** opens Claude: `window`, `split-right` or `split-below`. |
| `limit` | `200` | How many open issues to fetch. |

## Other trackers

Only GitHub is supported today. Each tracker is an entry in `PROVIDERS` in `hooks/register.tsx`,
with one case each in `detectRepo`, `listIssues` and `viewIssue`; the pane and the start actions
only see the common `Issue` and `Detail` shapes, so Azure DevOps, Jira or GitLab can be added
without touching them.
