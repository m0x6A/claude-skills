# dotnet-messaging

Rules that keep a .NET microservice system on MassTransit and EF Core boring in production.

- **masstransit-consumer**: choose the delivery guarantee (transactional outbox and inbox, attached to
  the endpoint, or idempotent by key), use additive contracts, keep consumers stateless across replicas,
  respond on every path for request/response but never for published messages, rethrow, forward
  cancellation, add health checks, and write a redelivery test.
- **bff-gateway-endpoint**: a thin gateway over request clients, with an explicit timeout policy,
  cancellation forwarded, faults mapped by type to 504/404/409/403/503/429/500 as RFC 7807 problems,
  and tests for every mapped outcome.
- **ef-core-migration**: generate and review migrations, never edit merged ones, roll out destructive
  changes in steps, use lock-aware DDL on hot PostgreSQL tables, a migrate-only runner the hosts wait
  for, retry-enabled registration, and tests against a real database.

## Setup

Put your solution's specifics (the shared registration helper, which host runs which tier, the
timeout table, the auth policies, the data and startup project for each context) in `AGENTS.md` or
`CLAUDE.md`; the skills read them from there.
