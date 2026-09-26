#!/usr/bin/env python3
"""Resolve a short-lived YouTube audio URL through yt-dlp."""
import importlib.util
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse


HERE = Path(__file__).resolve().parent
VIDEO_ID = re.compile(r"[A-Za-z0-9_-]{11}")
LEVELS = ("high", "standard")
QUALITY = "high"
# 默认只选择 M4A/MP3；改为 True 才把 FLAC 纳入候选。
ENABLE_FLAC = False


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


def normalize_video(value):
    value = str(value or "").strip()
    if VIDEO_ID.fullmatch(value):
        return value, "https://www.youtube.com/watch?v=" + value
    if value.startswith(("http://", "https://")):
        parsed = urlparse(value)
        if parsed.netloc.endswith("youtu.be"):
            video_id = parsed.path.strip("/").split("/", 1)[0]
        elif parsed.netloc.endswith("youtube.com") or parsed.netloc.endswith("music.youtube.com"):
            video_id = (parse_qs(parsed.query).get("v") or [""])[0]
            if not video_id and parsed.path.startswith("/shorts/"):
                video_id = parsed.path.split("/", 3)[2]
        else:
            video_id = ""
        if VIDEO_ID.fullmatch(video_id):
            return video_id, "https://www.youtube.com/watch?v=" + video_id
    raise ValueError("invalid YouTube video id or URL")


def run_json(url, quality, timeout=45):
    formats = ("flac", "m4a", "mp3") if ENABLE_FLAC else ("m4a", "mp3")
    if quality == "high":
        selector = "/".join("bestaudio[ext=%s]" % ext for ext in formats)
    else:
        selector = "/".join("bestaudio[ext=%s][abr<=160]" % ext for ext in formats)
    command = yt_dlp_command() + [
        "--ignore-config", "--no-warnings", "--no-playlist", "--skip-download",
        "--format", selector, "--dump-single-json",
    ] + cookie_args() + token_args() + [url]
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError("YouTube playback lookup failed: %s" % exc) from exc
    if completed.returncode != 0:
        message = (completed.stderr or completed.stdout).strip().splitlines()
        raise RuntimeError("YouTube playback lookup failed: %s" % (message[-1] if message else "yt-dlp error"))
    try:
        return json.loads(completed.stdout)
    except (TypeError, ValueError) as exc:
        raise RuntimeError("YouTube playback lookup returned invalid JSON") from exc


def pick_stream(info):
    candidates = []
    for key in ("requested_downloads", "requested_formats"):
        value = info.get(key) if isinstance(info, dict) else None
        if isinstance(value, list):
            candidates.extend(item for item in value if isinstance(item, dict))
    if isinstance(info, dict):
        candidates.append(info)
    audio = [item for item in candidates if str(item.get("url") or "").startswith(("http://", "https://"))
             and item.get("acodec") not in (None, "", "none")]
    audio_only = [item for item in audio if item.get("vcodec") in (None, "", "none")]
    pool = audio_only or audio
    if not pool:
        return None
    return max(pool, key=lambda item: float(item.get("abr") or item.get("tbr") or 0))


def expiry(url):
    raw = (parse_qs(urlparse(url).query).get("expire") or [""])[0]
    try:
        expires_at = int(raw)
    except (TypeError, ValueError):
        return None, None
    return expires_at, max(0, expires_at - int(time.time()))


def resolve(video, quality=QUALITY, timeout=45):
    video_id, webpage_url = normalize_video(video)
    quality = quality if quality in LEVELS else QUALITY
    info = run_json(webpage_url, quality, timeout)
    stream = pick_stream(info)
    if not stream:
        return {
            "provider": "youtube", "id": video_id, "url": "", "requested": quality,
            "level": "", "trial": False, "playable": False,
            "loggedIn": (HERE / "cookies.txt").is_file(),
            "restriction": {"category": "url_unavailable", "message": "yt-dlp did not return a playable audio format."},
        }
    url = str(stream["url"])
    expires_at, expi = expiry(url)
    return {
        "provider": "youtube", "id": video_id, "url": url, "requested": quality,
        "level": stream.get("format_id") or "", "format": stream.get("ext") or "",
        "codec": stream.get("acodec") or "", "bitrate": stream.get("abr") or stream.get("tbr") or 0,
        "duration": info.get("duration") or 0, "title": info.get("title") or "",
        "webpageUrl": webpage_url, "httpHeaders": stream.get("http_headers") or info.get("http_headers") or {},
        "expiresAt": expires_at, "expi": expi, "trial": False, "playable": True,
        "loggedIn": (HERE / "cookies.txt").is_file(), "source": "yt-dlp", "restriction": None,
    }


def main(argv):
    if len(argv) < 2 or argv[1] in ("-h", "--help"):
        print("usage: playurl.py <video_id|url> [high|standard] [--json]", file=sys.stderr)
        return 2
    json_mode = "--json" in argv[2:]
    positional = [item for item in argv[2:] if item != "--json"]
    if len(positional) > 1 or any(item.startswith("--") for item in positional):
        print("playurl.py: invalid arguments", file=sys.stderr)
        return 2
    quality = positional[0] if positional else QUALITY
    if quality not in LEVELS:
        print("playurl.py: quality must be high or standard", file=sys.stderr)
        return 2
    try:
        result = resolve(argv[1], quality)
    except ValueError as exc:
        print("playurl.py: %s" % exc, file=sys.stderr)
        return 2
    except RuntimeError as exc:
        result = {
            "provider": "youtube", "id": argv[1], "url": "", "playable": False,
            "restriction": {"category": "source_unavailable", "message": str(exc)},
        }
    if result.get("playable") and not json_mode:
        print(result["url"])
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("playable") else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
