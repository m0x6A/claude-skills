# dotnet-messaging

Rules that keep a .NET microservice system on MassTransit and EF Core boring in production. Each skill
asks the 3 am question for what it builds: *if I were on call at 3 am and this broke, what
observability would I need to solve it?*

- **masstransit-consumer**: choose the delivery guarantee (transactional outbox and inbox, attached to
  the endpoint, or idempotent by key), use additive contracts, keep consumers stateless across replicas,
  respond on every path for request/response but never for published messages, rethrow, forward
  cancellation, add health checks, answer the 3 am question (error-queue alert, structured failure logs
  with message id and business key, an unbroken trace), and write a redelivery test.
- **bff-gateway-endpoint**: a thin gateway over request clients, with an explicit timeout policy,
  cancellation forwarded, faults mapped by type to 504/404/409/403/503/429/500 as RFC 7807 problems
  carrying the trace id, structured fault logs, and tests for every mapped outcome.
- **ef-core-migration**: generate and review migrations, never edit merged ones, roll out destructive
  changes in steps, use lock-aware DDL on hot PostgreSQL tables, a migrate-only runner the hosts wait
  for, retry-enabled registration, a runner that logs and fails loudly with backfill progress visible, and
  tests against a real database.

## Install

```
/plugin install dotnet-messaging --marketplace m0x6A/claude-skills
```

## Setup

Put your solution's specifics (the shared registration helper, which host runs which tier, the
timeout table, the auth policies, the data and startup project for each context) in `AGENTS.md` or
`CLAUDE.md`; the skills read them from there.
