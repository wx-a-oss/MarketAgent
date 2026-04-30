"""CLI entrypoint for scheduled company update runs."""

from __future__ import annotations

import argparse
import json
import logging
from datetime import date, datetime
from typing import Optional
from zoneinfo import ZoneInfo

from market_agent.workflows import run_daily_updates_for_watchlist
from market_agent.config.models import DEFAULT_MARKET_OPENAI_MODEL


def _parse_date(value: str) -> date:
    return datetime.fromisoformat(value).date()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run scheduled company news/story updates.")
    parser.add_argument("--date", dest="target_date", type=_parse_date, default=None)
    parser.add_argument("--source", default="finnhub")
    parser.add_argument("--provider", default="openai")
    parser.add_argument("--market-model", default=DEFAULT_MARKET_OPENAI_MODEL)
    parser.add_argument("--company-model", default=None)
    parser.add_argument("--prompt-style", default="simple")
    parser.add_argument("--output-language", default="zh-CN")
    parser.add_argument("--story-window-days", type=int, default=21)
    parser.add_argument("--timezone", default="America/Los_Angeles")
    parser.add_argument("--company", action="append", dest="companies", default=None)
    parser.add_argument("--no-email", action="store_true", default=False, help="Skip sending email digests")
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
        market_model=args.market_model,
        company_model=args.company_model,
        prompt_style=args.prompt_style,
        output_language=args.output_language,
        story_window_days=args.story_window_days,
        companies=args.companies,
    )
    print(json.dumps(results, ensure_ascii=False, indent=2))

    if not args.no_email:
        _send_digest_emails(
            results=results,
            target_date=target_date,
            output_language=args.output_language,
        )

    return 0 if all(result.get("ok", False) for result in results) else 1


def _send_digest_emails(
    *,
    results: list[dict],
    target_date: date,
    output_language: str,
) -> None:
    from market_agent.services.email import is_email_configured, send_email
    from market_agent.services.digest import build_market_digest_html, build_company_digest_html

    if not is_email_configured():
        logging.getLogger(__name__).info("Email not configured — skipping digests")
        return

    try:
        market_html = build_market_digest_html(target_date, output_language=output_language)
        send_email(f"Market Digest — {target_date.isoformat()}", market_html)
    except Exception:
        logging.getLogger(__name__).exception("Failed to send market digest email")

    company_names = [
        r.get("company_name") for r in results
        if r.get("company_name") and r.get("ok")
    ]
    for company_name in company_names:
        try:
            company_html = build_company_digest_html(company_name, target_date, output_language=output_language)
            send_email(f"{company_name} Daily Report — {target_date.isoformat()}", company_html)
        except Exception:
            logging.getLogger(__name__).exception("Failed to send %s digest email", company_name)


if __name__ == "__main__":
    raise SystemExit(main())
