---
name: ef-core-migration
description: Add an EF Core database migration safely — the right data and startup projects, reviewing the generated code, never editing or reordering merged migrations, multi-step rollout for destructive changes, lock-aware DDL on hot PostgreSQL tables, a migrate-only migration runner that the hosts wait for, retry-on-failure registration, and testing against a real database. Use when entity models or a DbContext change and the schema must follow.
---

# EF Core migration

Project facts (the data/startup project per context, the migration runner, the registration helper)
belong in the project's database-migrations doc or guidance file. Read it first.

1. **Generate** from the repository root:
   ```bash
   dotnet ef migrations add <MigrationName> \
     --project <path to the Data project that owns the DbContext> \
     --startup-project <path to the migration runner or host>
   ```
   Use a name that says what changes (`AddMerchantLogoUrl`), not `Update3`.
2. **Read the generated code.** Check that it does only what you meant: no unintended drops, renames
   shown as drop-and-add (fix with `RenameColumn`), or type changes. **Never edit, reorder or rename
   a migration that has merged.** Write a new one. Check the model snapshot diff too.
3. **Destructive changes roll out in steps**: stop using the column or table, deploy, then drop it in a
   later migration. Rename = add, dual-write, backfill, switch reads, drop.
4. **Hot tables (PostgreSQL)**: adding a nullable column without a volatile default is cheap;
   adding an index on a large table needs `CREATE INDEX CONCURRENTLY` (via `migrationBuilder.Sql`,
   with the migration's transaction suppressed); a type change that rewrites the table takes an
   exclusive lock, so plan a maintenance window or an expand/contract pattern. Backfills run as
   paged, resumable background work, not inside the migration.
5. **Runner.** Apply migrations with `Database.MigrateAsync()` in a dedicated runner (a job or an
   init container), never with `EnsureCreatedAsync` (it bypasses migrations and breaks a fresh
   database's history). Hosts wait for the runner to complete before they start (for example
   `WaitForCompletion` in .NET Aspire, or a job dependency in the platform).
6. **Registration.** Register the DbContext through one shared helper that enables retry on
   transient failure (`EnableRetryOnFailure`). No `OnConfiguring` fallback to a hard-coded
   connection string.
7. **The 3 am question.** Ask: *if I were on call at 3 am and this migration had stalled or failed,
   what would I need to solve it?* The runner logs each migration's name at start and end with the
   elapsed time, and fails loudly (non-zero exit, a failed job the platform alerts on) rather than
   letting hosts start against a half-applied schema. A host that waits for the runner logs what it
   is waiting for. A migration that can hold a lock logs before it takes it, and the lock wait is
   visible (statement or lock timeout set, so it fails rather than hangs). A backfill reports
   progress (rows done, last key) as a log or metric, so on-call can tell slow from stuck and
   resume from the last key. Know the one query that shows what is applied
   (`SELECT "MigrationId" FROM "__EFMigrationsHistory" ORDER BY 1 DESC LIMIT 5`).
8. **Test against a real database** (Testcontainers PostgreSQL, or the local Aspire database):
   apply the migration from the previous release's schema, run the affected tests, and roll back
   if you have a down path.
9. **Ship.** Bump the runner's version, and that of every deployable that compiles the Data project.
   Sensitive tables (credentials, audit logs, PII) get a second reviewer.
