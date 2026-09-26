#!/usr/bin/env python3
"""Search Spotify metadata through the official Web API. No audio URL is returned."""
import base64
import json
import os
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

HERE = Path(__file__).resolve().parent
API = "https://api.spotify.com/v1"
TOKEN = "https://accounts.spotify.com/api/token"
UA = "Mineradio-PlayUrl/1.0"


def config():
    value = {}
    path = HERE / "credentials"
    if path.is_file():
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise RuntimeError("invalid Spotify credentials file: %s" % exc) from exc
    if not isinstance(value, dict):
        raise RuntimeError("Spotify credentials must be a JSON object")
    return {
        "client_id": os.environ.get("SPOTIFY_CLIENT_ID") or value.get("client_id") or "",
        "client_secret": os.environ.get("SPOTIFY_CLIENT_SECRET") or value.get("client_secret") or "",
        "access_token": os.environ.get("SPOTIFY_ACCESS_TOKEN") or value.get("access_token") or "",
        "market": os.environ.get("SPOTIFY_MARKET") or value.get("market") or "",
    }


def access_token(settings, user=False, timeout=12):
    if settings["access_token"]:
        return settings["access_token"]
    if user:
        raise RuntimeError("Spotify mine requires SPOTIFY_ACCESS_TOKEN or credentials.access_token")
    if not settings["client_id"] or not settings["client_secret"]:
        raise RuntimeError("Spotify credentials missing client_id/client_secret")
    basic = base64.b64encode((settings["client_id"] + ":" + settings["client_secret"]).encode()).decode()
    req = Request(TOKEN, data=b"grant_type=client_credentials", method="POST", headers={
        "Authorization": "Basic " + basic,
        "Content-Type": "application/x-www-form-urlencoded",
        "User-Agent": UA,
    })
    try:
        with urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (HTTPError, URLError, OSError, ValueError) as exc:
        raise RuntimeError("Spotify token request failed: %s" % exc) from exc
    token = str(payload.get("access_token") or "")
    if not token:
        raise RuntimeError("Spotify token response was empty")
    return token


def api_get(path, query, token, timeout=12):
    url = API + path + ("?" + urlencode(query) if query else "")
    req = Request(url, headers={"Authorization": "Bearer " + token, "User-Agent": UA})
    try:
        with urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (HTTPError, URLError, OSError, ValueError) as exc:
        raise RuntimeError("Spotify API request failed: %s" % exc) from exc


def song_row(track):
    artists = track.get("artists") or []
    album = track.get("album") or {}
    return {
        "provider": "spotify",
        "id": track.get("id") or "",
        "name": track.get("name") or "",
        "artist": " / ".join(item.get("name") or "" for item in artists if isinstance(item, dict)),
        "album": album.get("name") or "" if isinstance(album, dict) else "",
        "playable": False,
        "playbackMode": "spotify_official_player",
    }


def search(keywords, limit=10, offset=0, timeout=12):
    keywords = str(keywords or "").strip()
    if not keywords:
        raise ValueError("missing keywords")
    limit = max(1, min(int(limit or 10), 10))
    offset = max(0, min(int(offset or 0), 1000))
    settings = config()
    query = {"q": keywords, "type": "track", "limit": limit, "offset": offset}
    if settings["market"]:
        query["market"] = settings["market"]
    payload = api_get("/search", query, access_token(settings, timeout=timeout), timeout)
    return [song_row(item) for item in ((payload.get("tracks") or {}).get("items") or []) if item.get("id")]


def main(argv):
    if len(argv) < 2 or argv[1] in ("-h", "--help"):
        print("usage: search.py <keywords> [limit] [offset]", file=sys.stderr)
        return 2
    if len(argv) > 4:
        print("search.py: too many arguments", file=sys.stderr)
        return 2
    try:
        songs = search(argv[1], argv[2] if len(argv) > 2 else 10, argv[3] if len(argv) > 3 else 0)
    except ValueError as exc:
        print("search.py: %s" % exc, file=sys.stderr)
        return 2
    except RuntimeError as exc:
        print(json.dumps({"provider": "spotify", "error": str(exc), "songs": []}, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps({"provider": "spotify", "songs": songs}, ensure_ascii=False, indent=2))
    return 0 if songs else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
