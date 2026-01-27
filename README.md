# MarketAgent

A small but extensible Python project/CLI that fetches **stock** and **company** information using the **Finnhub** API.

## Features (v0.2.0)
- Unified `query_stock` API returning a structured `QueryStockOutput` payload that both CLI and web front-ends can consume.
- FastAPI service surface at `market_agent.api.http:app` with `/stocks/{symbol}` and `/healthz` routes.
- Extensible fetcher architecture (starting with Finnhub) to integrate alternative data providers without changing consumers.
- Dedicated frontend demos (CLI + HTML web) under `frontend/` reusing a shared client for consistent business logic.

### Python usage
```python
from market_agent import query_stock

snapshot = query_stock("AAPL")
print(snapshot.type)         # "stock.query"
print(snapshot.metadata)
print(snapshot.data.metrics)
```

### FastAPI service (optional)
```bash
uvicorn frontend.web.server:app --reload
# GET http://127.0.0.1:8000/stocks/AAPL
```

### Postgres (company news)
1) Start a local Postgres instance with Docker:
   ```bash
   cd postgres
   docker compose up -d
   ```
2) (Optional) Initialize schema against any Postgres instance:
   ```bash
   export PGHOST=localhost PGPORT=5432 PGUSER=market_agent PGDATABASE=market_agent PGPASSWORD=market_agent_password
   bash postgres/init_db.sh
   ```

## Install

1) Make sure you have Python 3.9+
2) Get a **Finnhub API key** (free tier available) and set it:
   ```bash
   export FINNHUB_API_KEY="YOUR_KEY"
   # or create a .env file in the project root with:
   # FINNHUB_API_KEY=YOUR_KEY
   ```
3) Install in editable mode:
   ```bash
   pip install -e .
   ```

## CLI Usage
```bash
marketagent check AAPL
marketagent check MSFT --format json
marketagent check TSLA --raw   # print raw JSON blobs (debug)
```

## Project Layout
```
MarketAgent/
├── market_agent/
│   ├── __init__.py
│   ├── agent.py
│   ├── api/
│   │   ├── __init__.py
│   │   ├── http.py
│   │   └── stocks.py
│   ├── cli/
│   │   └── app.py
│   ├── config.py
│   ├── datasources/
│   │   ├── __init__.py
│   │   └── finnhub/
│   │       ├── __init__.py
│   │       └── finnhub_client.py
│   ├── fetchers/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   └── finnhub.py
│   └── models/
│       ├── __init__.py
│       ├── base.py
│       └── stock.py
├── frontend/
│   ├── common/
│   │   ├── __init__.py
│   │   └── client.py
│   ├── cli/
│   │   ├── __init__.py
│   │   └── main.py
│   └── web/
│       ├── __init__.py
│       └── server.py
├── tests/
│   └── test_smoke.py
├── .env.example
├── pyproject.toml
├── README.md
└── LICENSE
```

### Additional frontends
- CLI demo: `python -m frontend.cli.main stock AAPL`
- Web demo: `uvicorn frontend.web.server:app --reload` (then open `http://127.0.0.1:8000/` and enter a ticker in the form)

## Notes
- This is an initial version with a rich, extendable structure. Add new data sources under `market_agent/datasources/` and new commands in `market_agent/cli/`.
- Respect the Finnhub rate limits.
- For development, run tests with `pytest` (optional).

## License
MIT
