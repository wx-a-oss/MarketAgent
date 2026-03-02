# Roadmap

## Cloud Migration

- Add a scheduled job (cron/worker) to refresh each tracked company story at least once per day.
- Keep current manual refresh flow for local development; do not run background schedulers in dev by default.
- During cloud migration, add:
  - schedule configuration (`daily`, timezone-aware),
  - retry/backoff + failure alerts,
  - run logs/metrics for story refresh jobs.
- Add background jobs for subscribed companies:
  - fetch daily company news,
  - generate daily report,
  - generate weekly report.
- Add story warm-up pipeline on first company subscription:
  - fetch at least last 60 days of company news,
  - run story discovery to build initial active-story map,
  - persist initial story timeline/events before daily incremental updates begin.
- Story lifecycle policy:
  - prioritize active stories; keep closed stories archived,
  - update active stories at least once per day,
  - allow new story creation + existing story extension during each update cycle.
