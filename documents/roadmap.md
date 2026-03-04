# Roadmap

## Feature Backlog (Priority Ranked)

Completed items are tracked in [implemented_features.md](./implemented_features.md). This backlog focuses on remaining or partially complete work.

### P0 (Now / Core Product)
1. `[todo]` Company stories warm-up + daily incremental pipeline (60+ day bootstrapping).
2. `[partial]` Fix and stabilize company page tabs/anchors so refresh keeps current sub-tab state.
3. `[partial]` Improve analyzed-content rendering in UI (structured bullets/layers, not single-line blocks).
4. `[partial]` Market page default behavior:
   - default date handling,
   - consistent timezone handling (PT),
   - no empty initial state for today.
5. `[partial]` Stock chart usability baseline:
   - readable chart height,
   - clearer series separation for price/volume,
   - support added ranges (6M, 8M, 2Y, 3Y).

### P1 (Near Term)
1. `[todo]` Market historical date picker + “has report” visibility by day.
2. `[partial]` Source expansion for market news (Finnhub + Yahoo feed) with correct source tags on cards.
3. `[todo]` Earnings report module:
   - pull earnings data/transcripts/estimates (where available),
   - generate company-level earnings summary and impact analysis.
4. `[todo]` Government document/report module:
   - ingest government releases relevant to companies/markets (policy, regulation, macro reports),
   - map documents to impacted companies/themes.
5. `[partial]` Company stories UX evolution:
   - story-first browsing,
   - drill-down by story,
   - evidence/recent changes/update history quality fixes.
6. `[partial]` Unified typography/style system across Market/Company/Person pages (including CJK font fallback).

### P2 (Scale / Data Lifecycle)
1. `[todo]` Story lifecycle management:
   - keep active stories hot,
   - archive closed stories,
   - track timeline events/history.
2. `[todo]` Raw-news cleanup subsystem:
   - TTL retention policy,
   - story-aware pruning after closure grace period,
   - dry-run/cap/audit controls.
3. `[partial]` Stock history cache lifecycle:
   - daily catch-up/backfill,
   - stale-window refresh policy.
4. `[todo]` Migration-readiness docs and runbooks for cloud deployment.

### P3 (Future Expansion)
1. `[todo]` Company status v2: combine narrative stories with multi-year price context and moving averages.
2. `[partial]` “Explain price move” intelligence:
   - link critical price points to company news + macro market context.
3. `[partial]` User-guided deep-dive Q&A over company stories with stronger context stitching.
4. `[todo]` International market breadth:
   - broader Asia/Europe coverage strategy and stable data-source policy.
5. `[todo]` Real-time signal pipeline for fast trading (late stage):
   - use low-cost cloud agents (for example OpenClaw + inexpensive LLMs) to ingest real-time news/social streams,
   - build a low-latency path for fetch -> summarize -> signal scoring -> trade decision support,
   - prioritize cost/performance evaluation before implementation.
6. `[todo]` New **Trade** tab (major feature):
   - subscribe to a portfolio of company tickers for decision support,
   - evaluate current price position versus historical ranges and moving averages,
   - generate buy/hold/sell recommendations with confidence and rationale,
   - combine signals from company news, broader market news, and market regime,
   - include capital-flow/rotation signals (large capital moving across sectors and asset classes),
   - add a stock “personality profile” layer (for example: stable vs. volatile behavior, narrative sensitivity, and typical reaction patterns driven by company fundamentals and investor mix such as institutions vs. retail).

## Cloud Migration (Separate Track)

### Goals
- Keep local development simple/manual.
- Add always-on or scheduled automation only in cloud runtime.
- Ensure reliability, observability, and safe retries for periodic jobs.

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

### Platform / Operations TODO
1. `[todo]` Timezone-aware schedule configuration.
2. `[todo]` Retry/backoff policy + failure handling.
3. `[todo]` Run logs + metrics + alerting.
4. `[todo]` Idempotent upserts and replay-safe job design.
5. `[todo]` Cloud deployment runbooks and migration docs.
6. `[todo]` Real-time market-data cost investigation:
   - compare cheapest reliable options for real-time news, X/Twitter-like streams, and public sentiment feeds,
   - define target SLA for ingestion speed, analysis latency, and decision freshness,
   - choose cloud architecture for always-on low-latency processing.


## Detailed Plans

- Company Story Warm-Up + Daily Pipeline: [company_story_warmup_daily_pipeline_plan.md](./company_story_warmup_daily_pipeline_plan.md)
