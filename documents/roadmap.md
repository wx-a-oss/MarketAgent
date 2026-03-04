# Roadmap

## Feature Backlog (Ranked by Execution Order)

Completed items are tracked in [implemented_features.md](./implemented_features.md). This backlog focuses on remaining work.

### 1) Company Stories Warm-Up and Lifecycle
- `[todo]` Build company stories warm-up + daily incremental pipeline (60+ day bootstrapping).
- `[todo]` Add story lifecycle management:
  - keep active stories hot,
  - archive closed stories,
  - track timeline events/history.
- `[partial]` Improve company stories UX:
  - story-first browsing,
  - drill-down by story,
  - evidence/recent changes/update history quality fixes.
- `[partial]` Add stronger deep-dive Q&A context stitching for story follow-up.

### 2) Market History and News Coverage
- `[todo]` Add market historical date picker with “has report” visibility by day.
- `[partial]` Expand/normalize market news sources (Finnhub + Yahoo feed) with reliable source tags on cards.
- `[todo]` Expand international market breadth:
  - broader Asia/Europe coverage strategy,
  - stable data-source policy.

### 3) New Data Modules
- `[todo]` Add earnings report module:
  - pull earnings data/transcripts/estimates (where available),
  - generate company-level earnings summary and impact analysis.
- `[todo]` Add government document/report module:
  - ingest government releases relevant to companies/markets (policy, regulation, macro reports),
  - map documents to impacted companies/themes.

### 4) Company Status and Price Intelligence
- `[todo]` Build company status v2:
  - combine narrative stories with multi-year price context and moving averages.
- `[partial]` Improve “explain price move” intelligence:
  - link critical price points to company news + macro market context.

### 5) Trade System (Later Stage)
- `[todo]` Build a new **Trade** tab (major feature):
  - subscribe to a portfolio of company tickers for decision support,
  - evaluate current price position versus historical ranges and moving averages,
  - generate buy/hold/sell recommendations with confidence and rationale,
  - combine signals from company news, broader market news, and market regime,
  - include capital-flow/rotation signals (large capital moving across sectors and asset classes),
  - add a stock “personality profile” layer (stable/volatile behavior, narrative sensitivity, and typical reaction patterns driven by company fundamentals and investor mix).
- `[todo]` Add real-time signal pipeline for fast trading (late stage):
  - use low-cost cloud agents (for example OpenClaw + inexpensive LLMs) to ingest real-time news/social streams,
  - build a low-latency path for fetch -> summarize -> signal scoring -> trade decision support,
  - prioritize cost/performance validation before implementation.

### Technical Debt and Polish
- `[partial]` Stock history cache lifecycle polish:
  - daily catch-up/backfill,
  - stale-window refresh policy.
- `[partial]` Unified typography/style system across Market/Company/Person pages (including CJK font fallback).

## Cloud Migration (Separate Track)

### Core Migration TODO
1. `[todo]` Scheduled jobs for subscribed companies:
   - daily raw fetch + filter,
   - daily report generation,
   - weekly report generation,
   - story refresh.
2. `[todo]` Warm-up automation on first company subscription:
   - fetch at least last 60 days of company news,
   - discover initial active-story map,
   - persist initial story timeline/events before incremental mode.
3. `[todo]` Story lifecycle automation policy:
   - prioritize active stories,
   - archive closed stories,
   - allow new story creation and existing story extension during updates.

## Detailed Plans

- Company Story Warm-Up + Daily Pipeline: [company_story_warmup_daily_pipeline_plan.md](./company_story_warmup_daily_pipeline_plan.md)
