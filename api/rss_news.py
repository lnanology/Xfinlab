from fastapi import APIRouter

from services.rss_news_service import get_all_headlines, search_headlines

router = APIRouter()


@router.get("/rss-news")
def rss_news(limit: int = 40):
    """Merged, newest-first financial-news + company-announcement
    headlines across every compliant RSS source configured in
    services/rss_news_service.py. See that module's docstring for exactly
    which sources are used and which were checked and ruled out."""
    return get_all_headlines(limit=limit)


@router.get("/rss-news/search")
def rss_news_search(q: str, limit: int = 20):
    """Keyword filter (company name / ticker) over the merged RSS feed --
    the practical substitute for a per-company IR feed, since none of the
    wires this service uses offer true per-ticker subscriptions."""
    return search_headlines(q, limit=limit)
