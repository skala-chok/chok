"""Guarded, mockable YouTube search tools."""

from typing import Any, Dict, List, Optional

from langchain_core.tools import tool

from .client import YouTubeSearchClient

client = YouTubeSearchClient()


def _video_items(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Normalize search and playlist responses into one video contract."""
    videos = []
    for item in data.get("items", []):
        if not isinstance(item, dict):
            continue
        identifier = item.get("id", {})
        content = item.get("contentDetails", {})
        snippet = item.get("snippet", {})
        identifier = identifier if isinstance(identifier, dict) else {}
        content = content if isinstance(content, dict) else {}
        snippet = snippet if isinstance(snippet, dict) else {}
        video_id = identifier.get("videoId", content.get("videoId", ""))
        videos.append(
            {
                "video_id": video_id,
                "title": snippet.get("title", ""),
                "description": snippet.get("description", ""),
                "channel_name": snippet.get("channelTitle", ""),
                "published_at": snippet.get("publishedAt", content.get("videoPublishedAt", "")),
                "url": f"https://www.youtube.com/watch?v={video_id}",
            }
        )
    return videos


@tool
def find_youtube_channel(company_name: str) -> List[Dict[str, Any]]:
    """Find candidate YouTube channels for a company; official status requires verification."""
    return [
        {"channel_id": item.get("id", {}).get("channelId", ""), "channel_name": item.get("snippet", {}).get("title", ""),
         "description": item.get("snippet", {}).get("description", ""),
         "url": f"https://www.youtube.com/channel/{item.get('id', {}).get('channelId', '')}"}
        for item in client.find_channels(company_name).get("items", [])
    ]


@tool
def get_channel_details(channel_id: str) -> Dict[str, Any]:
    """Get public metadata and statistics for a candidate channel ID."""
    items = client.get_channel_details(channel_id).get("items", [])
    if not items:
        return {"found": False, "channel_id": channel_id, "error": "채널을 찾을 수 없습니다."}
    item = items[0]
    snippet, statistics = item.get("snippet", {}), item.get("statistics", {})
    return {"found": True, "channel_id": item.get("id", channel_id), "channel_name": snippet.get("title"),
            "description": snippet.get("description", ""), "subscriber_count": None if statistics.get("hiddenSubscriberCount") else int(statistics.get("subscriberCount", 0)),
            "total_views": int(statistics.get("viewCount", 0)), "video_count": int(statistics.get("videoCount", 0)),
            "channel_url": f"https://www.youtube.com/channel/{item.get('id', channel_id)}",
            "official_status_note": "API 정보만으로 공식 채널을 확정할 수 없습니다."}


@tool
def get_channel_videos(channel_id: str, published_after: str, published_before: Optional[str] = None, keyword: Optional[str] = None, max_results: int = 20) -> List[Dict[str, Any]]:
    """Get channel videos inside an ISO-8601 UTC date range; optional keyword narrows candidates."""
    return _video_items(client.search_videos(keyword or "", min(max_results, 50), channel_id, published_after, published_before))


@tool
def get_competitor_recent_uploads(channel_id: str, published_after: Optional[str] = None, max_results: int = 20) -> List[Dict[str, Any]]:
    """Get recent uploads via channels.list then playlistItems.list, optionally filtering by date."""
    videos = _video_items(client.get_recent_uploads(channel_id, min(max_results, 50)))
    return [video for video in videos if not published_after or video["published_at"] >= published_after]
