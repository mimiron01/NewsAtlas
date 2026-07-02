# NewsAtlas
Automated News aggregator for ProAir, industry-specific news

Ingests news about your target companies, summarizes it with AI (Mistral) in the
context of your own product/service offering, and surfaces the result as
actionable sales signals — in a web dashboard and as a daily email digest with
ready-to-use outreach snippets.

See [`docs/planning.html`](docs/planning.html) for the full architecture and
roadmap.

## Project layout

- `backend/` — FastAPI + PostgreSQL API (auth, settings, target companies; news
  ingestion, AI summarization, and email digest land in later phases)
- `frontend/` — React + TypeScript SPA (login, company profile, target
  companies, signals feed)
- `docker-compose.yml` — Postgres + backend + frontend for local/self-hosted use

## Running locally

### With Docker Compose

```bash
cp .env.example .env   # fill in NewsAPI/Mistral/SMTP keys when you have them
docker compose up --build
```

- Backend API: http://localhost:8000 (docs at `/docs`)
- Frontend: http://localhost:4173

### Without Docker (for active development)

Backend:

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

Backend tests:

```bash
cd backend
pytest
```
