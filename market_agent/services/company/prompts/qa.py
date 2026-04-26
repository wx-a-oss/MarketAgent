from __future__ import annotations

import json
from typing import Any, Dict, List

from .common import _build_output_language_line


def _build_company_story_qa_prompt(
    *,
    company_name: str,
    output_language: str,
    story: Dict[str, Any],
    recent_updates: List[Dict[str, Any]],
    question: str,
) -> str:
    language_line = _build_output_language_line(output_language)
    payload_json = json.dumps(
        {"story": story, "recent_updates": recent_updates},
        ensure_ascii=False,
        indent=2,
    )
    return (
        f"You are answering a deep-dive question for company {company_name}.\n"
        "Use the story state and recent updates as the primary context.\n"
        "If evidence is insufficient, say what is missing.\n"
        "Use concise layered structure.\n"
        f"{language_line}"
        f"Question:\n{question}\n\n"
        f"Context JSON:\n{payload_json}\n"
    )


def _build_company_story_qa_merge_prompt(
    *,
    company_name: str,
    output_language: str,
    story: Dict[str, Any],
    recent_updates: List[Dict[str, Any]],
    qa_row: Dict[str, Any],
) -> str:
    language_line = _build_output_language_line(output_language)
    payload_json = json.dumps(
        {
            "story": story,
            "recent_updates": recent_updates,
            "qa": qa_row,
        },
        ensure_ascii=False,
        indent=2,
    )
    return (
        f"You are merging a story deep-dive answer back into the live story state for {company_name}.\n"
        "Use the existing story as the base.\n"
        "Use the Q&A answer only if it adds material clarification, context, or updated understanding.\n"
        "Do not drift away from the current storyline.\n"
        "Keep the same story_key.\n"
        "Past and Now should remain bullet-oriented.\n"
        "Next should remain concise bullet lines including scenario, impact, probability/confidence, and sentiment.\n"
        "Return JSON only with key story.\n"
        f"{language_line}"
        "Output JSON schema:\n"
        "{\n"
        '  "story": {\n'
        '    "story_key": "same_existing_key",\n'
        '    "story_title": "short title",\n'
        '    "importance_rank": 1,\n'
        '    "story_status": "stable|rising|fading|resolved|finished|closed",\n'
        '    "happened_text": "- ...",\n'
        '    "happening_text": "- ...",\n'
        '    "next_text": "- Scenario: ... | Impact: ... | Probability: ... | Sentiment: ...",\n'
        '    "open_questions": ["..."],\n'
        '    "evidence": [{"news_title": "...", "news_date_time": "...", "news_source_link": "..."}],\n'
        '    "change_log": ["Merged clarification from story Q&A ..."]\n'
        "  }\n"
        "}\n"
        f"Context JSON:\n{payload_json}\n"
    )
