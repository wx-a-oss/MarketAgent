"""CLI entrypoint for explicit company warm-up."""

from __future__ import annotations

import argparse
import json
import logging
from typing import Optional

from market_agent.app import start_company_story_warmup
from market_agent.config.models import DEFAULT_OPENAI_MODEL


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Start or resume company story warm-up.")
    parser.add_argument("company_name")
    parser.add_argument("--provider", default="openai")
    parser.add_argument("--model", default=DEFAULT_OPENAI_MODEL)
    parser.add_argument("--prompt-style", default="simple")
    parser.add_argument("--output-language", default="zh-CN")
    parser.add_argument("--warmup-days", type=int, default=10)
    parser.add_argument("--slice-days", type=int, default=10)
    parser.add_argument("--subscribe", action="store_true")
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    args = build_parser().parse_args(argv)
    state = start_company_story_warmup(
        args.company_name,
        provider_name=args.provider,
        model=args.model,
        prompt_style=args.prompt_style,
        output_language=args.output_language,
        warmup_days=args.warmup_days,
        slice_days=args.slice_days,
        subscribe=args.subscribe,
    )
    print(json.dumps(state, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
