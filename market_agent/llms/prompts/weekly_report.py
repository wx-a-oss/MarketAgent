"""Prompt builder for weekly company news reports."""

from __future__ import annotations

from typing import Any, Dict, Iterable

from .common import dump_items_json


def build_weekly_report_prompt(
    company_name: str,
    start_date: str,
    end_date: str,
    articles: Iterable[Dict[str, Any]],
    output_language: str = "en",
) -> str:
    language_line = ""
    normalized_lang = str(output_language or "en").strip().lower()
    if normalized_lang in {"zh", "zh-cn", "zh_hans", "chinese", "simplified chinese"}:
        language_line = "Write all content in Simplified Chinese. Keep company names, tickers, and numbers in English.\n"
    return (
        "You are a senior equity research analyst writing a weekly intelligence brief for {company} "
        "({start} to {end}).\n\n"
        "Your goal is NOT to list every fact — it's to provide INSIGHT and RANKING so the reader "
        "can quickly understand what matters most and what storylines are evolving.\n\n"
        "{language_line}"
        "Return a JSON object with these sections (each is an array of bullet-point strings):\n\n"
        "1. **summary** (3-5 bullets): The most important takeaways of the week, ranked by impact. "
        "Each bullet should be a complete insight, not just a fact. Start with what moved the stock "
        "or changed the narrative.\n\n"
        "2. **key_storylines** (2-4 bullets): Evolving narratives/themes that are developing across "
        "multiple days or weeks. For each, describe: what's the storyline, how it evolved this week, "
        "and what to watch next. Think like a journalist tracking a developing story.\n\n"
        "3. **catalysts_and_risks** (3-6 bullets): Upcoming events, decisions, or developments that "
        "could materially move the stock. Rank by proximity and potential impact. Include the specific "
        "date if known.\n\n"
        "4. **facts** (top 10 only): The 10 most material facts from the week, ranked by importance "
        "(NOT chronologically). Each must include the date. Skip routine/repetitive news — only include "
        "facts that change the investment thesis or market perception.\n\n"
        "5. **sentiment** (2-3 bullets): Market tone and positioning. Include: analyst actions "
        "(upgrades/downgrades with targets), institutional flow signals, and whether sentiment is "
        "shifting or confirming the existing trend.\n\n"
        "6. **viewpoint** (2-3 bullets): Your analytical perspective — what does this week tell us "
        "about where the company is heading? What's the market missing or overweighting?\n\n"
        "7. **reasoning** (2-3 bullets): The investment logic — if X happens, then Y follows. "
        "Conditional reasoning about scenarios ahead.\n\n"
        "8. **trends** (2-3 bullets): Multi-week or structural trends that this week's data "
        "confirms or challenges.\n\n"
        "Rules:\n"
        "- RANK by importance within each section — most impactful first\n"
        "- Be CONCISE — each bullet should be 1-2 sentences max\n"
        "- DEDUPLICATE — if the same event was reported multiple days, mention it once\n"
        "- Add [HIGH IMPACT] tag to any bullet with outsized significance\n"
        "- Focus on WHAT CHANGED this week, not what stayed the same\n\n"
        "News items JSON:\n{items}\n"
    ).format(
        company=company_name,
        start=start_date,
        end=end_date,
        language_line=language_line,
        items=dump_items_json(articles),
    )
