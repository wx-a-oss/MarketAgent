"""Prompt templates for comprehensive earnings report extraction via LLM web search."""

from __future__ import annotations


def _language_instruction(output_language: str) -> str:
    if str(output_language or "").lower() == "en":
        return "Output all text fields in English."
    return (
        "LANGUAGE RULES (CRITICAL):\n"
        "- ALL JSON keys, metric names, field labels, section titles, segment names, "
        "and product names MUST be in English. Never use Chinese for these.\n"
        "- Narrative text, analysis, commentary, executive_summary, guidance commentary, "
        "key_highlights, concerns_and_risks, CEO/CFO quotes, and analyst_qa_highlights "
        "should be in Simplified Chinese for readability.\n"
        "- Numbers, percentages, currency codes, and proper nouns stay as-is."
    )


_COMMON_INSTRUCTIONS = """
You are a senior equity research analyst. Your task is to extract a comprehensive,
structured earnings report by searching the web for the earnings call transcript,
press release, and SEC filing.

Return a SINGLE valid JSON object with the following top-level keys.
Do NOT wrap in markdown fences. Do NOT include commentary outside the JSON.

## 1. quarter_info
{
  "fiscal_year": "FY2025",
  "fiscal_quarter": "Q1",
  "quarter_end_date": "2025-03-31",
  "earnings_date": "2025-04-28",
  "reporting_currency": "USD"
}

## 2. financials
All monetary amounts in reporting currency, in millions (unless stated otherwise).
For EACH numeric field, include yoy_change_pct and qoq_change_pct when available.
Use null for any field not disclosed.

Required fields:
- revenue, cost_of_revenue, gross_profit, gross_margin_pct
- operating_income, operating_margin_pct
- net_income, net_margin_pct
- diluted_eps
- capex, depreciation_amortization
- free_cash_flow, operating_cash_flow
- r_and_d_expense, sga_expense
- cash_and_equivalents, total_debt
- shares_outstanding_diluted
- one_time_items: [{"description": "...", "amount": N, "type": "charge"|"gain"}]

## 3. company_specific
This is the MOST IMPORTANT section. Extract ALL business-specific metrics,
segment performance, product updates, and growth indicators discussed in
the earnings call. Do NOT follow a rigid schema — organize the data in
whatever structure best represents THIS company's unique business.

Look for (not limited to):
- Revenue and growth by business segment / product line
- Geographic revenue breakdown if disclosed
- Product-specific KPIs the company emphasizes (subscribers, units shipped,
  cloud ARR, bookings, backlog, etc.)
- Any metric the CEO/CFO specifically highlighted as important
- Market share data, competitive wins or losses mentioned
- New product launches, platform updates, roadmap items
- Customer or partner announcements
- Technology adoption or platform metrics
- R&D milestones or breakthroughs

Return as a list of objects, each with:
  {"title": "section name", "data": {...structured data...}, "commentary": "..."}

## 4. estimates_vs_actuals
{
  "revenue": {"estimated": N, "actual": N, "beat_miss_pct": N},
  "eps": {"estimated": N, "actual": N, "beat_miss_pct": N},
  "consensus_source": "..."
}

## 5. guidance
{
  "next_quarter": {"revenue_range": "...", "eps_range": "...", "commentary": "..."},
  "full_year": {"revenue_range": "...", "eps_range": "...", "commentary": "..."},
  "revised_vs_prior": "...",
  "long_term_targets": ["..."]
}

## 6. management_commentary
{
  "ceo_key_quotes": ["up to 5 most impactful direct quotes"],
  "cfo_key_quotes": ["up to 3 most impactful direct quotes"],
  "tone": "bullish" | "cautious" | "neutral" | "defensive",
  "strategic_priorities": ["list of priorities mentioned"]
}

## 7. analysis
{
  "executive_summary": "3-5 sentence overview of the quarter",
  "key_highlights": ["list of positive takeaways"],
  "concerns_and_risks": ["list of negatives or risks mentioned"],
  "competitive_positioning": "observations about market position",
  "product_updates": ["new products, features, launches mentioned"],
  "capital_allocation": "buybacks, dividends, M&A, debt changes",
  "analyst_qa_highlights": ["key Q&A exchanges that moved the narrative"]
}

## 8. keywords
List of 10-20 most important terms/topics from the call.
Example: ["AI inference", "data center demand", "margin expansion", "cloud migration"]

## 9. price_reaction
{
  "earnings_date_close": N,
  "next_day_close": N,
  "change_pct": N,
  "after_hours_move_pct": N
}
Use null for values you cannot find.
"""


def build_earnings_report_prompt(
    company_name: str,
    ticker: str,
    fiscal_year: str,
    fiscal_quarter: str,
    output_language: str = "zh-CN",
) -> str:
    return (
        f"Search the web for {company_name} ({ticker}) {fiscal_year} {fiscal_quarter} "
        f"earnings call transcript, earnings press release, and SEC filing.\n\n"
        f"{_COMMON_INSTRUCTIONS}\n"
        f"{_language_instruction(output_language)}\n"
    )


def build_latest_earnings_prompt(
    company_name: str,
    ticker: str,
    output_language: str = "zh-CN",
) -> str:
    return (
        f"Search the web for the MOST RECENT earnings call for {company_name} ({ticker}).\n"
        f"Determine which fiscal year and quarter it belongs to, then extract the full report.\n\n"
        f"{_COMMON_INSTRUCTIONS}\n"
        f"{_language_instruction(output_language)}\n"
    )


def build_refresh_earnings_prompt(
    company_name: str,
    ticker: str,
    fiscal_year: str,
    fiscal_quarter: str,
    existing_data: str,
    output_language: str = "zh-CN",
) -> str:
    return (
        f"Search the web for {company_name} ({ticker}) {fiscal_year} {fiscal_quarter} "
        f"earnings call transcript, earnings press release, and SEC filing.\n\n"
        f"IMPORTANT: Below is our EXISTING data for this earnings report. Your job is to:\n"
        f"1. KEEP all existing numeric values that are correct — do NOT drop any metrics.\n"
        f"2. CORRECT any values that are wrong based on your web search findings.\n"
        f"3. ADD any missing metrics, segments, or analysis that we don't have yet.\n"
        f"4. For narrative fields (executive_summary, commentary, highlights, quotes, etc.), "
        f"IMPROVE and EXPAND the existing text — do not shorten or lose information.\n"
        f"5. For company_specific sections, KEEP all existing sections and ADD new ones if found.\n\n"
        f"EXISTING DATA:\n```json\n{existing_data}\n```\n\n"
        f"Return the COMPLETE updated report in the same JSON structure. "
        f"Every field from the existing data must appear in your output — "
        f"if you cannot verify a value, keep the existing one rather than dropping it.\n\n"
        f"{_COMMON_INSTRUCTIONS}\n"
        f"{_language_instruction(output_language)}\n"
    )
