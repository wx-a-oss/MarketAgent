# Roadmap

## Feature Backlog (Priority Ranked)

### P0 (Now / Core Product)
1. `[todo]` Company stories warm-up + daily incremental pipeline (60+ day bootstrapping).
2. `[done]` Company daily report pipeline from raw news (batch-level analysis, not per-news manual flow).
3. `[done]` Company weekly report pipeline built from daily reports.
4. `[done]` Ensure Finnhub fetch always runs filter pass before downstream analysis.
5. `[partial]` Fix and stabilize company page tabs/anchors so refresh keeps current sub-tab state.
6. `[partial]` Improve analyzed-content rendering in UI (structured bullets/layers, not single-line blocks).
7. `[partial]` Market page default behavior:
   - default date handling,
   - consistent timezone handling (PT),
   - no empty initial state for today.
8. `[done]` Market daily price snapshot persistence:
   - load from DB first,
   - live fallback only when snapshot missing.
9. `[partial]` Stock chart usability baseline:
   - readable chart height,
   - clearer series separation for price/volume,
   - support added ranges (6M, 8M, 2Y, 3Y).

### P1 (Near Term)
1. `[todo]` Market historical date picker + “has report” visibility by day.
2. `[done]` Market summary compare flow across providers (OpenAI / Gemini / Perplexity) with persisted outputs.
3. `[done]` Market single-news “investigate” analysis and persistence.
4. `[partial]` Source expansion for market news (Finnhub + Yahoo feed) with correct source tags on cards.
5. `[done]` Weekend behavior split:
   - prices use last trading day snapshot,
   - news remains selected calendar day.
6. `[partial]` Company stories UX evolution:
   - story-first browsing,
   - drill-down by story,
   - evidence/recent changes/update history quality fixes.
7. `[done]` Stock/indicators information architecture refactor:
   - “Stock” nested under Company,
   - “Indicators” tab and consistent navigation hierarchy.
8. `[partial]` Unified typography/style system across Market/Company/Person pages (including CJK font fallback).

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

## Detailed Plan Draft: Company Story Warm-Up + Daily Pipeline

### Summary
Build a two-stage company story system where first subscription runs a **60+ day warm-up** that hydrates Daily News raw data and initializes stories.
Then ongoing daily jobs keep stories current.
Warm-up must integrate with Daily News storage (no duplicate fetch path) and cleanup remains low priority but planned.

### Priority-Ordered TODO Backlog

1. `P0` Warm-up integrated with Daily News raw storage
2. `P0` New story timeline/event tables + story discovery/expansion flow
3. `P0` Daily incremental story update contract (1 run/day/company)
4. `P1` Cloud scheduler jobs for daily fetch + daily report + weekly report + story refresh
5. `P2` Cleanup subsystem (raw news retention): **both TTL-based and story-aware delete**

### Scope (This plan)
- Define implementation for warm-up + story pipeline + storage model.
- Define scheduler behavior for cloud migration.
- Define cleanup policy design and order (low priority implementation).
- Keep local/dev mode manual-trigger first; no mandatory background thread in dev.

### Out of Scope (for first delivery)
- Full production orchestration stack (K8s/Celery/etc.) implementation.
- Full UI redesign of story timelines.
- Multi-provider scheduling policy differences.

### Data Model / Interface Additions

#### Database tables (new)
1. `company_story_event`
- Purpose: immutable timeline events per story.
- Fields:
  - `id`
  - `company_name`
  - `story_key`
  - `event_date`
  - `event_type` (`discovery|update|milestone|resolution|risk_change`)
  - `event_title`
  - `event_summary`
  - `impact_text`
  - `evidence_json` (source links, news ids)
  - `provider`, `model`, `prompt_style`, `output_language`
  - `created_at`
- Indexes:
  - `(company_name, story_key, event_date desc)`
  - `(company_name, event_date desc)`

2. `company_story_job_state`
- Purpose: track warm-up and daily run status.
- Fields:
  - `company_name` (PK)
  - `is_warmed_up` (bool)
  - `warmup_started_at`, `warmup_completed_at`
  - `last_story_refresh_at`
  - `last_refresh_status` (`ok|partial|failed`)
  - `last_error`
  - `updated_at`

#### Existing table usage changes
- `company_news_raw` becomes canonical raw store for warm-up + daily.
- `company_news_daily_report` stays report output store.
- `company_story_state` remains latest state snapshot.
- `company_story_update` remains per-run output record.
- `company_story_qa` unchanged.

#### API behavior changes
1. First subscribe / warm-up trigger path
- Reuse existing company refresh endpoint with `warmup=true` mode.
- Behavior:
  - fetch news for last 60 days minimum
  - write all raw news into `company_news_raw`
  - skip daily report generation during warm-up fetch step
  - run story discovery + expansion using warmed raw data
  - set `company_story_job_state.is_warmed_up=true`

2. Story refresh endpoint
- Keep endpoint signature; add response fields:
  - `warmup_used`, `input_news_count`, `active_story_count`, `new_story_count`, `updated_story_count`

3. Daily pipeline endpoints/jobs
- Fetch latest day raw news and upsert to `company_news_raw`.
- Generate daily report once/day/company.
- Generate weekly report at configured weekly cadence.
- Run story incremental update once/day/company.

### Processing Design

### Stage 1: Story Discovery (high recall)
- Input: raw news from 60-day window during warm-up; then recent delta window daily.
- Output: normalized active stories with stable `story_key`.
- Rules:
  - maximize coverage of distinct active narratives
  - merge near-duplicates
  - require evidence references for each story
  - produce confidence and importance ranking

### Stage 2: Story Expansion (depth)
- Per discovered/active story:
  - `Past` (origin + milestones)
  - `Now` (current state + latest changes)
  - `Next` (forward catalysts/decision points)
  - event timeline append/update in `company_story_event`

### Warm-up flow (first subscription)
1. Resolve ticker/profile.
2. Fetch 60-day news from Finnhub in date slices; upsert into `company_news_raw`.
3. Apply existing filter pipeline.
4. Run discovery over warmed raw corpus.
5. Run expansion for each active story.
6. Persist:
  - `company_story_state` current active set
  - `company_story_event` timeline events
  - `company_story_update` run artifact
  - `company_story_job_state` warm-up completion

### Daily incremental flow (post warm-up)
1. Fetch latest raw news delta.
2. Filter + upsert raw.
3. Generate daily report.
4. Weekly report generation on weekly schedule.
5. Story discovery incremental (new/merged stories).
6. Story expansion incremental (state transitions + new events).
7. Mark job state with run outcome.

### Cleanup Plan (P2, low priority)

Chosen policy: **both time-based and story-aware delete**

1. TTL delete
- Default: remove `company_news_raw` rows older than 365 days.

2. Story-aware cleanup
- For stories marked resolved/closed:
  - optional targeted raw-news pruning linked to those stories after grace window.
- Keep:
  - `company_story_event`, `company_story_state` history artifacts
  - daily/weekly report outputs for long-term context

3. Safety controls
- dry-run mode
- per-company retention overrides
- max-delete-per-run cap
- audit log for cleanup jobs

### Scheduler Plan (Cloud migration)

Daily jobs per subscribed company:
1. raw fetch + filter
2. daily report
3. story update

Weekly jobs:
1. weekly report generation
2. optional story consolidation pass

Operational requirements:
- timezone-aware schedules
- retry/backoff
- idempotent upserts
- run metrics/logs
- failure alerting

### Testing and Acceptance

#### Unit tests
1. Warm-up writes 60-day raw news into `company_news_raw`.
2. Warm-up creates non-empty `company_story_state` when relevant news exists.
3. Warm-up creates `company_story_event` rows.
4. Incremental run updates existing stories without duplicating keys.
5. Discovery merge behavior for duplicate narratives.
6. TTL cleanup removes old raw rows only.
7. Story-aware cleanup removes only eligible raw rows for resolved stories.

#### Integration tests
1. Subscribe new company -> warm-up completes -> Daily News timeline includes warmed dates.
2. Next-day run -> only delta fetch required -> story update succeeds.
3. Weekly roll -> weekly report generated and visible.
4. Failure injection -> job state marks failure and retries without data corruption.

#### Acceptance criteria
1. First subscription yields initial active stories from ~60-day context.
2. Daily news page shows warm-up-loaded historical raw news without refetching same history.
3. Story refresh remains at least daily in cloud mode.
4. Story timeline events are queryable and ordered.
5. Cleanup can run safely with dry-run and capped deletion.

### Assumptions and Defaults
1. Warm-up window default is 60 days.
2. Story update cadence is once per day per subscribed company.
3. Local development stays manual-triggered by default.
4. Cleanup defaults:
  - TTL: 365 days raw news
  - story-aware delete enabled with grace period (default 30 days after story closure).
5. Story UI will prioritize active stories; closed stories remain available in history views.
