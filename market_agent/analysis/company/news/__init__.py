"""News data access and fetching utilities."""

from .service import (
    add_company_to_watchlist,
    delete_company_news,
    get_company_news,
    get_company_profile,
    generate_weekly_report,
    get_news_report,
    ensure_company_profile,
    list_watchlist_company_rows,
    list_watchlist_companies,
    refresh_company_news_for_range,
    refresh_company_news_if_needed,
    remove_company_from_watchlist,
    set_company_ticker,
    summarize_company_news_item,
)

__all__ = [
    "add_company_to_watchlist",
    "delete_company_news",
    "remove_company_from_watchlist",
    "list_watchlist_company_rows",
    "list_watchlist_companies",
    "get_company_news",
    "get_company_profile",
    "set_company_ticker",
    "generate_weekly_report",
    "get_news_report",
    "ensure_company_profile",
    "refresh_company_news_for_range",
    "refresh_company_news_if_needed",
    "summarize_company_news_item",
]
