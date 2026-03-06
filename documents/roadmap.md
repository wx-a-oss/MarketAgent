# Roadmap

## Feature Backlog (Ranked by Execution Order)

Completed items are tracked in [implemented_features.md](./implemented_features.md). This backlog focuses on remaining work.

### 1) Company Stories Warm-Up and Lifecycle
- `[partial]` Refine story deep-dive Q&A workflow so users can ask questions, get an LLM response, and explicitly decide whether to merge that question and answer into the current story; it should never be merged automatically by the LLM.


### 3) Earnings Report Module
- `[todo]` Add earnings report module:
  - pull earnings data/transcripts/estimates (where available),
  - generate company-level earnings summary and impact analysis.

### 4) Government Document and Report Module
- `[todo]` Add government document/report module:
  - ingest government releases relevant to companies/markets (policy, regulation, macro reports),
  - map documents to impacted companies/themes.

### 5) Company Status and Price Intelligence
- `[todo]` Build company status v2:
  - combine narrative stories with multi-year price context and moving averages.
- `[partial]` Improve “explain price move” intelligence:
  - link critical price points to company news + macro market context.

### 6) Trade System (Later Stage)
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
- `[todo]` Solve real-time high-value news ingestion:
  - ingest valuable breaking news and viewpoints from X/Twitter and other fast-moving sources,
  - distinguish high-signal items from noise in real time,
  - make this feed reliable enough to support future fast-decision and trading workflows.

### 7) Strategy & Plan Board (User Workspace)
- `[todo]` Add a top-level **Plan Board** tab for users to write and track their own trading plans.
- `[todo]` Support flexible plan formats:
  - vague/idea-stage plans,
  - rule-based plans with specific price levels, triggers, and time windows,
  - short-term and long-term strategy plans.
- `[todo]` Add LLM evaluation workflow for each plan:
  - evaluate from multiple perspectives (thesis quality, risk, timing, scenario coverage, execution realism),
  - return confidence bands / estimated win-probability ranges with explicit assumptions.
- `[todo]` Add plan lifecycle tracking:
  - draft -> active -> closed/canceled,
  - version history and update notes,
  - user-friendly timeline view of plan changes and outcomes.
- `[todo]` Add post-trade review loop:
  - compare plan vs. actual outcome,
  - capture lessons learned and strategy adjustments.

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
