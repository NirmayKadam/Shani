# Runbook: Startup (Single-Container Runtime)

This runbook covers booting the current runtime where one `app` container hosts API + ingestion workers + NLP subscriber.

## 1) Preconditions

- `.env` is present and configured (at minimum DB and News API credentials).
- Docker and Docker Compose are available.
- Ports `8000` (API), `5432` (Postgres internal), and `6379` (Redis internal) are not conflicting in your environment.

## 2) Start services

```bash
docker compose up -d --build
```

**Configuration Note**: Ensure `WATCHLIST` in `.env` is populated with NSE/BSE symbols (e.g., `NIFTY,RELIANCE.NS`) for Indian market tracking.

Expected services:

- `app` (single container with core processes)
- `redis`
- `postgres`

Check status:

```bash
docker compose ps
```

## 3) Initialize schema (first boot or after DB reset)

```bash
docker compose cp scripts/init_schema.sql postgres:/tmp/init_schema.sql
docker compose exec postgres psql -U postgres -d NexusQuantDB -f /tmp/init_schema.sql
```

## 4) Verify health and process startup

### API health

```bash
curl -sS http://localhost:8000/health
```

Expected response shape:

```json
{"status":"ok","version":"2.0.0"}
```

### App process logs

```bash
docker compose logs -f app
```

Look for these startup markers:

- Uvicorn startup log (FastAPI online)
- Celery worker connected to Redis and listening on `ingestion`
- Celery beat scheduler started
- `Starting Sentiment Event Subscriber...`

## 5) Quick functional smoke

Trigger a read path (example symbol):

```bash
curl -sS http://localhost:8000/v1/analyze/NIFTY | head
```

If caches are cold, initial responses may be partial/stale while async refresh paths backfill.

## 6) Shutdown

```bash
docker compose down
```

To also remove persistent volumes:

```bash
docker compose down -v
```
