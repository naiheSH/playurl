#!/usr/bin/env python3
"""Describe Spotify's official playback options without inventing an audio URL."""
import json
import re
import sys


def resolve(track_id):
    track_id = str(track_id or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9]{22}", track_id):
        raise ValueError("invalid Spotify track id")
    return {
        "provider": "spotify",
        "id": track_id,
        "url": "",
        "level": "",
        "trial": False,
        "playable": False,
        "loggedIn": False,
        "spotifyUri": "spotify:track:" + track_id,
        "spotifyUrl": "https://open.spotify.com/track/" + track_id,
        "embedUrl": "https://open.spotify.com/embed/track/" + track_id,
        "supportedPlayback": ["spotify_embed", "spotify_web_playback_sdk"],
        "restriction": {
            "category": "provider_limited",
            "message": "Spotify 官方接口不提供可交给通用音频播放器的直链；请使用 Embed 或 Web Playback SDK。",
        },
    }


def main(argv):
    if len(argv) < 2 or argv[1] in ("-h", "--help"):
        print("usage: playurl.py <spotify_track_id> [--json]", file=sys.stderr)
        return 2
    if len(argv) > 3 or (len(argv) == 3 and argv[2] != "--json"):
        print("playurl.py: invalid arguments", file=sys.stderr)
        return 2
    try:
        result = resolve(argv[1])
    except ValueError:
        print("playurl.py: invalid Spotify track id", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
