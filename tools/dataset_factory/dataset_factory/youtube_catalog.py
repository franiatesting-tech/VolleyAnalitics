"""Catalog public YouTube metadata through the official Data API.

This intentionally never downloads media. It inventories the channel's
upload playlist and records each video's declared YouTube license so a
human can perform the separate rights review required by source_rights.py.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

API_BASE = "https://www.googleapis.com/youtube/v3"


def _get_json(resource: str, *, api_key: str, **params) -> dict:
    query = urlencode({**params, "key": api_key})
    with urlopen(f"{API_BASE}/{resource}?{query}", timeout=30) as response:  # noqa: S310
        return json.load(response)


def _chunks(values: list[str], size: int) -> list[list[str]]:
    return [values[index : index + size] for index in range(0, len(values), size)]


def catalog_channel(channel_id: str, *, api_key: str) -> dict:
    channel_response = _get_json(
        "channels", api_key=api_key, part="snippet,contentDetails", id=channel_id
    )
    channels = channel_response.get("items", [])
    if not channels:
        raise ValueError(f"YouTube channel not found: {channel_id}")
    channel = channels[0]
    uploads_playlist = channel["contentDetails"]["relatedPlaylists"]["uploads"]

    video_ids: list[str] = []
    page_token: str | None = None
    while True:
        params = {
            "part": "contentDetails",
            "playlistId": uploads_playlist,
            "maxResults": 50,
        }
        if page_token:
            params["pageToken"] = page_token
        page = _get_json("playlistItems", api_key=api_key, **params)
        video_ids.extend(item["contentDetails"]["videoId"] for item in page.get("items", []))
        page_token = page.get("nextPageToken")
        if not page_token:
            break

    videos: list[dict] = []
    for batch in _chunks(video_ids, 50):
        response = _get_json(
            "videos",
            api_key=api_key,
            part="snippet,contentDetails,status",
            id=",".join(batch),
        )
        for item in response.get("items", []):
            status = item.get("status", {})
            snippet = item.get("snippet", {})
            content = item.get("contentDetails", {})
            videos.append(
                {
                    "video_id": item["id"],
                    "url": f"https://www.youtube.com/watch?v={item['id']}",
                    "title": snippet.get("title"),
                    "published_at": snippet.get("publishedAt"),
                    "duration": content.get("duration"),
                    "definition": content.get("definition"),
                    "declared_license": status.get("license"),
                    "privacy_status": status.get("privacyStatus"),
                    "training_eligible": False,
                    "rights_review": "pending_permission_and_authorized_delivery",
                }
            )

    return {
        "provider": "youtube-data-api-v3",
        "channel_id": channel_id,
        "channel_title": channel.get("snippet", {}).get("title"),
        "channel_url": f"https://www.youtube.com/channel/{channel_id}",
        "uploads_playlist_id": uploads_playlist,
        "video_count": len(videos),
        "media_downloaded": False,
        "videos": videos,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--channel-id", required=True)
    parser.add_argument("--api-key-env", default="YOUTUBE_API_KEY")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    api_key = os.environ.get(args.api_key_env)
    if not api_key:
        parser.error(f"environment variable {args.api_key_env!r} is not set")
    catalog = catalog_channel(args.channel_id, api_key=api_key)
    args.out.write_text(json.dumps(catalog, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Cataloged {catalog['video_count']} public video(s) to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
