#!/usr/bin/env python3
"""Search and list Spotify playlists through the official Web API."""
import base64
import json
import os
import re
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
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


def playlist_row(item, source):
    owner = item.get("owner") or {}
    items = item.get("items") or item.get("tracks") or {}
    return {
        "provider": "spotify",
        "id": item.get("id") or "",
        "name": item.get("name") or "",
        "trackCount": items.get("total") or 0,
        "creator": owner.get("display_name") or owner.get("id") or "",
        "source": source,
    }


def song_row(item):
    track = item.get("item") or item.get("track") or item
    if not isinstance(track, dict) or track.get("type", "track") != "track" or not track.get("id"):
        return None
    artists = track.get("artists") or []
    return {
        "provider": "spotify",
        "id": track.get("id"),
        "name": track.get("name") or "",
        "artist": " / ".join(value.get("name") or "" for value in artists if isinstance(value, dict)),
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
    payload = api_get("/search", {"q": keywords, "type": "playlist", "limit": limit, "offset": offset}, access_token(settings, timeout=timeout), timeout)
    return [playlist_row(item, "search") for item in ((payload.get("playlists") or {}).get("items") or []) if isinstance(item, dict) and item.get("id")]


def tracks(playlist_id, limit=50, offset=0, timeout=12):
    playlist_id = str(playlist_id or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9]{22}", playlist_id):
        raise ValueError("invalid Spotify playlist id")
    limit = max(1, min(int(limit or 50), 50))
    offset = max(0, int(offset or 0))
    settings = config()
    query = {"limit": limit, "offset": offset, "additional_types": "track"}
    if settings["market"]:
        query["market"] = settings["market"]
    payload = api_get("/playlists/" + quote(playlist_id, safe="") + "/items", query, access_token(settings, user=True, timeout=timeout), timeout)
    songs = [row for row in (song_row(item) for item in (payload.get("items") or [])) if row]
    return {"playlist": {"provider": "spotify", "id": playlist_id, "source": "detail"}, "songs": songs, "total": payload.get("total") or len(songs)}


def mine(limit=30, offset=0, timeout=12):
    limit = max(1, min(int(limit or 30), 50))
    offset = max(0, int(offset or 0))
    settings = config()
    payload = api_get("/me/playlists", {"limit": limit, "offset": offset}, access_token(settings, user=True, timeout=timeout), timeout)
    return [playlist_row(item, "mine") for item in (payload.get("items") or []) if isinstance(item, dict) and item.get("id")]


def main(argv):
    if len(argv) < 2 or argv[1] in ("-h", "--help"):
        print("usage: playlist.py search <keywords> [limit] [offset]", file=sys.stderr)
        print("       playlist.py tracks <playlist_id> [limit] [offset]", file=sys.stderr)
        print("       playlist.py mine [limit] [offset]", file=sys.stderr)
        return 2
    command = argv[1]
    expected = {"search": (3, 5), "tracks": (3, 5), "mine": (2, 4)}
    if command not in expected:
        print("playlist.py: unknown command", file=sys.stderr)
        return 2
    minimum, maximum = expected[command]
    if not minimum <= len(argv) <= maximum:
        print("playlist.py: invalid arguments for %s" % command, file=sys.stderr)
        return 2
    try:
        if command == "search":
            body = {"provider": "spotify", "playlists": search(argv[2], argv[3] if len(argv) > 3 else 10, argv[4] if len(argv) > 4 else 0)}
        elif command == "tracks":
            body = {"provider": "spotify"}
            body.update(tracks(argv[2], argv[3] if len(argv) > 3 else 50, argv[4] if len(argv) > 4 else 0))
        else:
            body = {"provider": "spotify", "playlists": mine(argv[2] if len(argv) > 2 else 30, argv[3] if len(argv) > 3 else 0)}
    except ValueError as exc:
        print("playlist.py: %s" % exc, file=sys.stderr)
        return 2
    except RuntimeError as exc:
        print(json.dumps({"provider": "spotify", "error": str(exc)}, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps(body, ensure_ascii=False, indent=2))
    rows = body.get("playlists") or body.get("songs") or []
    return 0 if rows else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
