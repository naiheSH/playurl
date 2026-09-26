#!/usr/bin/env python3
"""Search YouTube with yt-dlp and print stable video IDs."""
import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent


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


def run_json(args, timeout=30):
    command = yt_dlp_command() + ["--ignore-config", "--no-warnings", "--skip-download"]
    command += cookie_args() + token_args() + args
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError("YouTube search failed: %s" % exc) from exc
    if completed.returncode != 0:
        message = (completed.stderr or completed.stdout).strip().splitlines()
        raise RuntimeError("YouTube search failed: %s" % (message[-1] if message else "yt-dlp error"))
    try:
        return json.loads(completed.stdout)
    except (TypeError, ValueError) as exc:
        raise RuntimeError("YouTube search returned invalid JSON") from exc


def video_row(item):
    if not isinstance(item, dict) or not item.get("id"):
        return None
    video_id = str(item["id"])
    return {
        "provider": "youtube",
        "id": video_id,
        "name": item.get("title") or "",
        "artist": item.get("artist") or item.get("uploader") or item.get("channel") or "",
        "duration": item.get("duration") or 0,
        "webpageUrl": item.get("webpage_url") or "https://www.youtube.com/watch?v=" + video_id,
    }


def search(keywords, limit=10, offset=0, timeout=30):
    keywords = str(keywords or "").strip()
    if not keywords:
        raise ValueError("missing keywords")
    limit = max(1, min(int(limit or 10), 50))
    offset = max(0, int(offset or 0))
    count = min(50, offset + limit)
    if offset >= count:
        return []
    payload = run_json([
        "--flat-playlist", "--dump-single-json", "ytsearch%s:%s" % (count, keywords),
    ], timeout)
    rows = [row for row in (video_row(item) for item in (payload.get("entries") or [])) if row]
    return rows[offset:offset + limit]


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
        print(json.dumps({"provider": "youtube", "error": str(exc), "songs": []}, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps({"provider": "youtube", "songs": songs}, ensure_ascii=False, indent=2))
    return 0 if songs else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
