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

## 3) Run Web App (Dev)

From project root:

```bash
uvicorn frontend.web.server:app --reload --log-level info
```

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
