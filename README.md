# MarketAgent (Development)

## 0) Clone

```bash
git clone https://github.com/wx-a-oss/MarketAgent.git
cd MarketAgent
```

## 1) Environment Setup

```bash
# create once (if needed)
conda create -n market_agent_env python=3.13 -y
conda activate market_agent_env
pip install -e .
```

Required env vars:

```bash
export FINNHUB_API_KEY="YOUR_FINNHUB_KEY"
export OPENAI_API_KEY="YOUR_OPENAI_KEY"
```

Optional DB env vars (defaults are used if omitted):

```bash
export PGHOST=localhost
export PGPORT=5432
export PGUSER=market_agent
export PGPASSWORD=market_agent_password
export PGDATABASE=market_agent
```

Notes:
- These DB defaults are hardcoded in `market_agent/analysis/company/news/db.py` (`_build_dsn()`).
- Exported env vars (or `DATABASE_URL`) override the hardcoded defaults.

## 2) Database Setup (Postgres)

```bash
cd postgres
docker compose up -d
cd ..
bash postgres/init_db.sh
```

Schema notes:
- `postgres/init.sql` defines base schema for local setup.
- `postgres/migrations/*.sql` contains incremental migrations (also applied by `postgres/init_db.sh`).
- `market_agent/schema_fields.py` is the central registry for newly added DB field/table names used in Python code.

Current tables in use:
- `company_news_raw`: raw news records per company.
- `company_news_analyzed`: analyzed news content per company/model.
- `company_news_daily_report`: daily company report snapshots (provider/prompt-specific).
- `company_status_snapshot`: rolling company status snapshots built from daily/weekly reports.
- `company_news_dropped`: archived/dropped news with drop metadata.
- `company_watchlist`: tracked companies for company page.
- `company_profile`: company metadata (ticker/profile fields).
- `news_report`: weekly company news report payloads.
- `market_news_daily_summary`: Market tab daily summary history (LLM input/output + provider/model/prompt style).
- `market_news_item_analysis`: per-market-news single-item analysis cache (by date/url/model/language).
- `market_price_daily_snapshot`: end-of-day market price snapshots (sectioned JSON for indexes/bonds/commodities/crypto and future extensions).
- `company_price_daily`: cached daily OHLCV price history per company/ticker for stock chart ranges (with catch-up backfill on access).

## 3) Run Web App (Dev)

From project root:

```bash
uvicorn frontend.web.server:app --reload --log-level info
```

Market tab behavior:
- On `/market`, summaries are loaded from `market_news_daily_summary` for today first.
- If no summary exists for today, the app auto-generates one in real time and stores it.

Open:

```text
http://127.0.0.1:8000
```

## 4) Development Commands

```bash
# quick syntax check for key modules
python3 -m py_compile frontend/web/server.py market_agent/analysis/company/news/service.py

# run tests (if pytest installed)
pytest -q
```

## 5) Roadmap

See [roadmap.md](./roadmap.md) for roadmap and future work.
