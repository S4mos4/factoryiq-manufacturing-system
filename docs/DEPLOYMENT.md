# Development and deployment

## Docker Compose

From the repo root run `sh scripts/init-local-env.sh` and `docker compose up --build --wait`. The app is bound to loopback on port 8000 by default. Set `FACTORYIQ_HOST_PORT` in `.env` to select another local port. The database is reachable inside the Compose network. Seed data persists in the named volume across restarts.

```sh
docker compose exec app python -m factoryiq.seed
docker compose exec database psql -U factoryiq -d factoryiq
docker compose down
```

## Native development

Use Python 3.15, Node 24 and PostgreSQL 17. Create a local PostgreSQL database and supply its connection URL as `DATABASE_URL` with the `postgresql+psycopg://` scheme. Use a UTC database session. Export `FACTORYIQ_DEMO_READS=true` for an isolated synthetic database and a random `FACTORYIQ_OPERATOR_TOKEN` of at least 24 characters to enable authorized writes.

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r backend/requirements.txt
alembic -c backend/alembic.ini upgrade head
PYTHONPATH=backend python -m factoryiq.seed
PYTHONPATH=backend uvicorn factoryiq.main:app --host 127.0.0.1 --port 8000
```

In a second terminal, run `cd frontend && npm ci && npm run dev`. Vite proxies API requests to port 8000. To serve the production bundle from FastAPI, run `npm run build` in `frontend`, then set `FACTORYIQ_STATIC_DIR` to the absolute path of `frontend/dist` before starting Uvicorn.

## Test and capture

Set `FACTORYIQ_TEST_DATABASE_URL` to a disposable PostgreSQL database and run `PYTHONPATH=backend pytest backend/tests -q`. Pytest creates and drops a unique schema. For browser tests, start a dedicated seeded, writable test instance and export its `FACTORYIQ_OPERATOR_TOKEN` and loopback origin as `FACTORYIQ_E2E_URL`. Then run:

```sh
cd frontend
npm ci
npx playwright install chromium
npm test
```

The Chromium capture script reads a separate clean demo instance from `FACTORYIQ_DEMO_URL`. Run `node capture-demo.mjs` from `frontend`. It saves screenshots to `docs/screenshots/` and a WebM tour under `work/demo-video/`.

## Public demo option

A Render Free Docker web service and an isolated Render Free PostgreSQL instance are one possible short-lived deployment. Free web services can reach Render PostgreSQL over the private network. Disable all external access to PostgreSQL before loading any records. Render free web services idle after 15 minutes and its free databases expire after 30 days. Confirm the free tier and network restrictions before provisioning. [Render free services](https://render.com/docs/free) · [Render private network](https://render.com/docs/private-network)
1. Create a dedicated synthetic PostgreSQL database with no external IP allowlist entries. Run migrations and seed once through a database owner connection inside the private network.
2. Use a runtime role with SELECT only on the app schema, and include TLS verification for managed PostgreSQL.
3. Use the repo Dockerfile. Configure the health check at `/health` and set the service hostname via `FACTORYIQ_ALLOWED_HOSTS`.
4. Configure `FACTORYIQ_DEMO_READS=true`, `FACTORYIQ_READ_ONLY=true`, `FACTORYIQ_DISABLE_DOCS=true`, `FACTORYIQ_BOOTSTRAP=false` and `FACTORYIQ_SEED=false`. Leave the operator token unset. Set secrets through the host’s secret settings.
5. Smoke-test the dashboard, filters, a report download and a rejected write through HTTPS. Only share the service URL after verification.

The public release includes a recorded walkthrough and dashboard screenshots. Use Docker Compose for the interactive local demo.
