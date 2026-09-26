#!/usr/bin/env python3
"""List tracks from a known YouTube playlist with yt-dlp."""
import importlib.util
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse


HERE = Path(__file__).resolve().parent
PLAYLIST_ID = re.compile(r"[A-Za-z0-9_-]{10,100}")


def yt_dlp_command():
    executable = shutil.which("yt-dlp")
    if executable:
        return [executable]
    if importlib.util.find_spec("yt_dlp") is not None:
        return [sys.executable, "-m", "yt_dlp"]
    raise RuntimeError("yt-dlp is required; install the current yt-dlp release first")


def cookie_args():
    path = HERE / "cookies.txt"
    return ["--cookies", str(path)] if path.is_file() else []


def token_args():
    path = HERE / "token"
    if not path.is_file():
        return []
    values = []
    for line in path.read_text(encoding="utf-8").splitlines():
        value = line.strip()
        if not value or value.startswith("#"):
            continue
        values.append(value if "." in value.split("+", 1)[0] else "mweb.gvs+" + value)
    if not values:
        return []
    return ["--extractor-args", "youtube:player-client=default,mweb;po_token=" + ",".join(values)]


def normalize_playlist(value):
    value = str(value or "").strip()
    if value.startswith(("http://", "https://")):
        playlist_id = (parse_qs(urlparse(value).query).get("list") or [""])[0]
    else:
        playlist_id = value
    if not PLAYLIST_ID.fullmatch(playlist_id):
        raise ValueError("invalid YouTube playlist id or URL")
    return playlist_id, "https://www.youtube.com/playlist?list=" + playlist_id


def run_json(args, timeout=45):
    command = yt_dlp_command() + ["--ignore-config", "--no-warnings", "--skip-download"]
    command += cookie_args() + token_args() + args
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError("YouTube playlist failed: %s" % exc) from exc
    if completed.returncode != 0:
        message = (completed.stderr or completed.stdout).strip().splitlines()
        raise RuntimeError("YouTube playlist failed: %s" % (message[-1] if message else "yt-dlp error"))
    try:
        return json.loads(completed.stdout)
    except (TypeError, ValueError) as exc:
        raise RuntimeError("YouTube playlist returned invalid JSON") from exc


def song_row(item):
    if not isinstance(item, dict) or not item.get("id"):
        return None
    video_id = str(item["id"])
    return {
        "provider": "youtube", "id": video_id,
        "name": item.get("title") or "",
        "artist": item.get("artist") or item.get("uploader") or item.get("channel") or "",
        "duration": item.get("duration") or 0,
        "webpageUrl": item.get("webpage_url") or "https://www.youtube.com/watch?v=" + video_id,
    }


def playlist_row(item):
    if not isinstance(item, dict):
        return None
    playlist_id = str(item.get("id") or "")
    url = str(item.get("url") or "")
    if not PLAYLIST_ID.fullmatch(playlist_id) or "playlist?list=" not in url:
        return None
    return {
        "provider": "youtube", "id": playlist_id,
        "name": item.get("title") or "",
        "creator": item.get("uploader") or item.get("channel") or "",
        "trackCount": item.get("playlist_count") or 0,
        "source": "search", "webpageUrl": url,
    }


def search(keywords, limit=10, offset=0, timeout=45):
    keywords = str(keywords or "").strip()
    if not keywords:
        raise ValueError("missing keywords")
    limit = max(1, min(int(limit or 10), 30))
    offset = max(0, int(offset or 0))
    url = "https://www.youtube.com/results?" + urlencode({
        "search_query": keywords, "sp": "EgIQAw%3D%3D",
    })
    payload = run_json([
        "--flat-playlist", "--playlist-end", "100", "--dump-single-json", url,
    ], timeout)
    rows = [row for row in (playlist_row(item) for item in (payload.get("entries") or [])) if row]
    return rows[offset:offset + limit]


def tracks(playlist, limit=50, offset=0, timeout=45):
    playlist_id, url = normalize_playlist(playlist)
    limit = max(1, min(int(limit or 50), 200))
    offset = max(0, int(offset or 0))
    payload = run_json([
        "--flat-playlist", "--dump-single-json",
        "--playlist-start", str(offset + 1), "--playlist-end", str(offset + limit), url,
    ], timeout)
    songs = [row for row in (song_row(item) for item in (payload.get("entries") or [])) if row]
    total = payload.get("playlist_count") or payload.get("n_entries") or len(songs)
    return {
        "provider": "youtube",
        "playlist": {
            "provider": "youtube", "id": playlist_id,
            "name": payload.get("title") or "", "creator": payload.get("uploader") or payload.get("channel") or "",
            "trackCount": total, "source": "detail",
        },
        "songs": songs, "total": total,
    }


def main(argv):
    if len(argv) < 3 or argv[1] in ("-h", "--help"):
        print("usage: playlist.py search <keywords> [limit] [offset] | tracks <playlist_id|url> [limit] [offset]", file=sys.stderr)
        return 2
    if argv[1] not in ("search", "tracks") or len(argv) > 5:
        print("playlist.py: invalid command or arguments", file=sys.stderr)
        return 2
    try:
        if argv[1] == "search":
            rows = search(argv[2], argv[3] if len(argv) > 3 else 10, argv[4] if len(argv) > 4 else 0)
            result = {"provider": "youtube", "playlists": rows}
        else:
            result = tracks(argv[2], argv[3] if len(argv) > 3 else 50, argv[4] if len(argv) > 4 else 0)
    except ValueError as exc:
        print("playlist.py: %s" % exc, file=sys.stderr)
        return 2
    except RuntimeError as exc:
        print(json.dumps({"provider": "youtube", "error": str(exc), "songs": []}, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if (result.get("songs") or result.get("playlists")) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
