"""CLI entrypoint for scheduled company update runs."""

from __future__ import annotations

import argparse
import json
import logging
from datetime import date, datetime
from typing import Optional
from zoneinfo import ZoneInfo

from market_agent.app import run_daily_updates_for_watchlist


def _parse_date(value: str) -> date:
    return datetime.fromisoformat(value).date()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run scheduled company news/story updates.")
    parser.add_argument("--date", dest="target_date", type=_parse_date, default=None)
    parser.add_argument("--source", default="finnhub")
    parser.add_argument("--provider", default="openai")
    parser.add_argument("--model", default="gpt-5.2")
    parser.add_argument("--prompt-style", default="simple")
    parser.add_argument("--output-language", default="zh-CN")
    parser.add_argument("--story-window-days", type=int, default=21)
    parser.add_argument("--timezone", default="America/Los_Angeles")
    parser.add_argument("--company", action="append", dest="companies", default=None)
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    args = build_parser().parse_args(argv)
    target_date = args.target_date
    if target_date is None:
        target_date = datetime.now(ZoneInfo(args.timezone)).date()
    results = run_daily_updates_for_watchlist(
        target_date=target_date,
        source_name=args.source,
        provider_name=args.provider,
        model=args.model,
        prompt_style=args.prompt_style,
        output_language=args.output_language,
        story_window_days=args.story_window_days,
        companies=args.companies,
    )
    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0 if all(result.get("ok", False) for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
