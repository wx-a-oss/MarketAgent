# Implemented Features

This document tracks features that are already available in the app from a user perspective.

## Market
- View a daily market snapshot page with date selection.
- See major market sections in one place: indexes, rates, commodities, and crypto.
- Refresh market data for a selected day.
- Auto-refresh market data during U.S. market hours.
- On weekends, price snapshots use the latest trading day while news remains on the selected calendar date.
- Switch inside the Market page between Overview, Daily News, and Stories views.
- Read market news aggregated from multiple sources.
- See source tags on market news cards.
- Open original market news links in a new tab.
- Generate and reopen daily market report analysis for a selected day.
- Analyze a single market news item and save the result.
- Reopen prior day summaries from stored history.
- Build daily market news clusters from raw market news.
- Warm up and review market stories split into ongoing and finished sections.
- Store market stories with summary, timeline, future/impact, and priority.
- Manually refresh market stories from the UI.
- Manually close or reopen a market story.
- Manually change market story priority.
- Create a new market story from a market news item.
- Attach a market news item back into an existing market story.
- View a market macro calendar with recent and upcoming macro/government releases.

## Company
- Add and remove companies in a watchlist.
- View and edit company ticker symbols.
- Open a company workspace with sub-tabs: Stories, Daily News, Weekly Report, Earnings, Stock, Indicators.
- Refresh company news by provider and date range.
- Read daily raw company news cards with source and link.
- Generate daily company report for a selected day.
- Generate weekly company report.
- Start company story warm-up automatically after subscribing a company.
- Reuse fetched company raw news in both Stories warm-up and Daily News views.
- View company stories split into ongoing and finished sections.
- Refresh company stories with incremental story updates.
- Ask follow-up questions for a specific story with selectable LLM models.
- Merge a story Q&A answer back into the current story when the answer adds useful context.

## Company Stock
- View company stock chart with multiple time ranges.
- Switch ranges including short and long windows (for example 1D through multi-year ranges).
- Overlay moving averages and volume on the stock chart.
- Generate AI explanation for notable stock moves.
- Cache historical company price data for faster reloads.
- Review a price-intelligence panel that combines company narrative and price context.

## Company Earnings
- Review the latest earnings timeline for a subscribed company.
- See actual vs estimate, surprise, and a short earnings-focused analysis.
- See short-window post-earnings price reaction context alongside the event.

## Company Indicators
- View company indicators snapshot.
- Generate AI-based indicator interpretation.

## Language and Presentation
- Choose analysis output language from a compact global navigation switch.
- View Chinese output for large analysis content when selected.
- Use unified navigation across Market, Company, and Person top tabs.
- Use shared UI styling with CJK-capable font fallback.

## Testing and Validation Support
- Run automated tests for market news, RSS ingestion, and price snapshot flows.
- Run automated tests for company stock history and stock move analysis APIs.
- Run integration-style comparison tests for LLM link-access summarization.

## Maintenance Rule
- Add newly shipped user-facing features to this file when implementation is complete.
