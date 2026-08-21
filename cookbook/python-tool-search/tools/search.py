import os

from serpapi import GoogleSearch


def search_web(query: str, limit: int = 5) -> list[dict]:
    results = GoogleSearch(
        {
            "engine": "google",
            "q": query,
            "api_key": os.environ["SERPAPI_API_KEY"],
            "num": limit,
        }
    ).get_dict()
    return [
        {
            "title": result.get("title", ""),
            "snippet": result.get("snippet", ""),
            "link": result.get("link", ""),
        }
        for result in results.get("organic_results", [])[:limit]
    ]
