"""CLI entrypoint to send digest emails for a given date without re-running analysis."""

from __future__ import annotations

import argparse
import logging
from datetime import date, datetime
from typing import Optional
from zoneinfo import ZoneInfo

from market_agent.services.company import list_watchlist_company_rows


def _parse_date(value: str) -> date:
    return datetime.fromisoformat(value).date()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Send digest emails for existing reports.")
    parser.add_argument("--date", dest="target_date", type=_parse_date, default=None)
    parser.add_argument("--timezone", default="America/Los_Angeles")
    parser.add_argument("--output-language", default="zh-CN")
    parser.add_argument("--company", action="append", dest="companies", default=None)
    parser.add_argument("--market-only", action="store_true", default=False)
    parser.add_argument("--companies-only", action="store_true", default=False)
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

    from market_agent.services.email import is_email_configured, send_email
    from market_agent.services.digest import build_market_digest_html, build_company_digest_html

    if not is_email_configured():
        print("Email not configured. Set MARKETAGENT_SMTP_USER and MARKETAGENT_SMTP_PASSWORD.")
        return 1

    sent = 0

    if not args.companies_only:
        print(f"Sending market digest for {target_date}...")
        html = build_market_digest_html(target_date, output_language=args.output_language)
        if send_email(f"Market Digest — {target_date.isoformat()}", html):
            sent += 1

    if not args.market_only:
        if args.companies:
            company_names = args.companies
        else:
            company_names = [r["company_name"] for r in list_watchlist_company_rows()]
        for name in company_names:
            print(f"Sending {name} digest for {target_date}...")
            html = build_company_digest_html(name, target_date, output_language=args.output_language)
            if send_email(f"{name} Daily Report — {target_date.isoformat()}", html):
                sent += 1

    print(f"Done — {sent} email(s) sent.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
