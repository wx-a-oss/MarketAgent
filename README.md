# MarketAgent

A small but extensible Python project/CLI that fetches **stock** and **company** information using the **Finnhub** API.

## Features (v0.1.0)
- `marketagent check <SYMBOL>`: get a consolidated snapshot with:
  - Real-time quote (open, high, low, current, previous close, change/percent)
  - Company profile (name, industry, IPO, market cap, exchange, website, country, logo)
  - Basic financial metrics (PE, PB, EPS, revenue/share, etc., when available)
  - Recommendation trends and next earnings (if available)
  - Peers

- Python SDK usage:
  ```python
  from market_agent import MarketAgent
  data = MarketAgent().check_stock("AAPL")
  print(data.model_dump())
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
│   ├── config.py
│   ├── models.py
│   ├── utils.py
│   ├── datasources/
│   │   └── finnhub_client.py
│   └── cli/
│       └── app.py
├── tests/
│   └── test_smoke.py
├── .env.example
├── pyproject.toml
├── README.md
└── LICENSE
```

## Notes
- This is an initial version with a rich, extendable structure. Add new data sources under `market_agent/datasources/` and new commands in `market_agent/cli/`.
- Respect the Finnhub rate limits.
- For development, run tests with `pytest` (optional).

## License
MIT