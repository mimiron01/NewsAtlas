# NewsAtlas
Automated News aggregator for ProAir, industry-specific news

Ingests news about your target companies, summarizes it with AI (Mistral) in the
context of your own product/service offering, and surfaces the result as
actionable sales signals — in a web dashboard and as a daily email digest with
ready-to-use outreach snippets.

See [`docs/planning.html`](docs/planning.html) for the full architecture and
roadmap, and [`docs/security-review.html`](docs/security-review.html) for the
security posture and remediation history.

## Project layout

- `backend/` — FastAPI + PostgreSQL API (auth, settings, target companies, news
  ingestion, AI summarization, scheduling, email digest)
- `frontend/` — React + TypeScript SPA (login, company profile, target
  companies, signals feed)
- `Caddyfile` — reverse proxy config: automatic HTTPS, security headers, single
  public origin in front of the backend and frontend containers
- `docker-compose.yml` — Postgres + backend + frontend + Caddy for
  self-hosted/production use

## Running locally (without Docker, for active development)

Backend:

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
# APP_ENV defaults to "development", which allows the insecure built-in
# defaults below — never set APP_ENV=production without also setting
# JWT_SECRET and SIGNUP_INVITE_CODE (see .env.example).
SIGNUP_INVITE_CODE=dev-invite-code uvicorn app.main:app --reload
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

The Vite dev server proxies `/api/*` to `localhost:8000` (see `vite.config.ts`),
so open http://localhost:5173 and sign up using invite code `dev-invite-code`.

Backend tests:

```bash
cd backend
pytest
```

## Deploying with Docker Compose (e.g. a Hetzner VPS)

This is the intended production path: Postgres, the API, and the frontend run
in their own containers, all reachable only through a Caddy reverse proxy that
terminates HTTPS automatically via Let's Encrypt. Nothing else is exposed to
the host.

```bash
cp .env.example .env
```

Then edit `.env` and set, at minimum:

- `APP_ENV=production` — the app refuses to start with insecure defaults once
  this is set (see `docs/security-review.html`, finding H1)
- `DOMAIN` — a real domain pointing at this server's IP (needed for Caddy to
  obtain a certificate; use `localhost` only for local Docker testing)
- `POSTGRES_PASSWORD` — generate with `openssl rand -hex 24`
- `JWT_SECRET` — generate with `openssl rand -hex 32`
- `SIGNUP_INVITE_CODE` — a shared secret you give to teammates you want to
  invite; signup is disabled entirely without this set
- `NEWSAPI_API_KEY`, `MISTRAL_API_KEY`, and the `SMTP_*` variables, once you
  have them

```bash
chmod 600 .env
docker compose up --build -d
```

The app is then served at `https://$DOMAIN` — Caddy proxies `/api/*` to the
backend and everything else to the frontend, so there's a single public
origin and no CORS configuration needed. `docker compose config` will refuse
to run (with a clear error) if `POSTGRES_PASSWORD` isn't set.

Before exposing this to the internet for real, also lock down the VPS itself:
configure the Hetzner Cloud Firewall (or `ufw`) to only allow inbound 80/443
(and SSH), independent of what Docker publishes — see
`docs/security-review.html` for the full reasoning.
