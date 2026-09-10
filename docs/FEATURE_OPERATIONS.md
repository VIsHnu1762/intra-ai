# Feature operations

Supabase/PostgreSQL is authoritative. AuraDB is the existing evidence projection.
The local PostgreSQL/PostgREST fixtures exercise migrations and transactions;
they do not deploy hosted schema or replace Supabase.

## Environment

Keep service credentials in `backend/.env`. The frontend only needs
`NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_AGORA_APP_ID`, and `NEXT_PUBLIC_APP_ENV`.
Morgan/Taylor session responses supply their separate public Agora project ID.
Never put certificates, service-role credentials, model keys, connector secrets,
or database passwords in `NEXT_PUBLIC_*`. Local credential notes in
`frontend/env_doc.md` are ignored and excluded from container builds.

All four feature model slots reuse `AICREDITS_API_KEY_GEMINI_FLASH_LITE` through
the existing AICredits client. M1 and Standard Interview retain their existing
provider slots and contracts. No new Agora voice sessions are implemented.

## Hosted migrations

An API service-role key does not provide a PostgreSQL connection. Obtain the
project's direct or session-pooler URL from its Connect panel and set
`DATABASE_URL` locally. URL-encode special characters in the password.
See the [Supabase connection documentation](https://supabase.com/docs/guides/database/connecting-to-postgres).

From `backend/`, install `requirements-migrations.txt`, then run:

```bash
python -m app.feature_runtime.deploy_migrations
python -m app.feature_runtime.deploy_migrations --apply
```

The first command only plans. The second applies pending feature migrations
inside transactions, checks the original scripts against the checksum ledger,
validates the core schema and project identity, and refreshes the PostgREST schema.
Use port 5432, not a transaction pooler. Hosted connections require TLS.
The `--local-test` flag permits local PostgreSQL verification only.
Legacy scripts are only newly applied when `--include-legacy` is supplied.
Do not edit an applied migration; add the next dated script.

## Recovery and readiness

Run the API and one recovery worker against the same Supabase project:

```bash
python -m app.feature_runtime.worker
```

The worker schedules GD analysis leases, retries graph delivery, and closes
expired RP/GD sessions with durable domain events. It does not run M1 or route
Standard Interviews. Multiple worker attempts are safe for session expiry and
graph MERGE; graph delivery is at least once. A lost GD analysis lease can be
reclaimed after two minutes. LLM outages leave explicit unevaluated turns;
they do not invent assessment evidence or a ready report.

`/api/v1/health` is liveness. `/api/v1/ready` checks the application and enabled
feature tables plus a fresh healthy worker heartbeat. It does not prove all
external integrations are functioning. Monitor worker degradation, report
generation failures, pending evidence, and external service availability.

## One-host deployment preparation

`docker-compose.production.yml` defines the API, worker, frontend, internal Redis,
and a TLS reverse proxy. Supply `APP_DOMAIN`, `API_DOMAIN`, and optionally
`NEXT_PUBLIC_AGORA_APP_ID` as Compose environment variables. The frontend API URL
is a build argument, because Next.js public variables are compiled into assets.

```bash
docker compose -f docker-compose.production.yml config --quiet
docker compose -f docker-compose.production.yml build
```

These commands prepare containers. They do not authorize or perform an AWS
deployment. Before starting them on an explicitly authorized host, apply the
hosted migrations, point both DNS names at the host, and configure the Agora
callback URLs and credentials. The callback bearer key is distinct from the
Agora NCS webhook signing secret. Legacy arbitrary agent/token/config routes
return 410; use the authenticated scheduled-interview API.

Use strong JWT/invitation/callback secrets and verified HTTPS callbacks. Permit
only required HTTPS ingress and restricted operator access at the EC2 security
group. Supabase, AuraDB, Agora, AICredits, Composio, and email remain external.
Keep backend/worker replicas at the documented single-host topology: existing
Standard Interview session state is process-local and has not been redesigned.
Use database backups and test restoration before production use.

Policy-enabled RP/GD use fixed action wording and exact, dated source excerpts.
Their analyzers receive the pinned candidate-visible policy snapshot. Plain
role-play retains dynamic AICredits persona response generation. Changes to the
protected Standard Interview prompts remain a separate opt-in integration.
