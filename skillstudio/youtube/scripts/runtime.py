#!/usr/bin/env python3
"""Agent Runtime JSON stdin/stdout adapter for YouTube audio and playlists."""
import importlib.util
import json
import os
import sys
import tempfile
import time
from pathlib import Path

PROVIDER = "youtube"
HERE = Path(__file__).resolve().parent
MAX_INPUT_BYTES = 1024 * 1024
MAX_CREDENTIAL_CHARS = 1024 * 1024
AVAILABLE_ACTIONS = ("search", "playlist_search", "playlist_tracks", "playurl", "check")
_MODULES = {}
_TEMP_PATHS = []


class InputError(ValueError):
    pass


def load_module(name):
    if name not in _MODULES:
        spec = importlib.util.spec_from_file_location(f"playurl_{PROVIDER}_{name}", HERE / f"{name}.py")
        if spec is None or spec.loader is None:
            raise RuntimeError(f"cannot load {name}.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        _MODULES[name] = module
    return _MODULES[name]


def text_value(payload, *names, required=False, default=""):
    value = next((payload[name] for name in names if name in payload), default)
    if value is None:
        value = default
    if not isinstance(value, (str, int)) or isinstance(value, bool):
        raise InputError(f"{names[0]} must be a string")
    value = str(value).strip()
    if required and not value:
        raise InputError(f"missing {names[0]}")
    return value


def int_value(payload, name, default, minimum=0, maximum=1000):
    value = payload.get(name, default)
    if isinstance(value, bool):
        raise InputError(f"{name} must be an integer")
    try:
        value = int(value)
    except (TypeError, ValueError) as exc:
        raise InputError(f"{name} must be an integer") from exc
    if not minimum <= value <= maximum:
        raise InputError(f"{name} must be between {minimum} and {maximum}")
    return value


def timeout_value(payload, default):
    if isinstance(payload.get("timeout", default), bool):
        raise InputError("timeout must be a number")
    try:
        value = float(payload.get("timeout", default))
    except (TypeError, ValueError) as exc:
        raise InputError("timeout must be a number") from exc
    if not 1 <= value <= 300:
        raise InputError("timeout must be between 1 and 300")
    return value


def credential_values(payload):
    cookies = payload.get("cookies", "")
    if cookies is None:
        cookies = ""
    if not isinstance(cookies, str):
        raise InputError("cookies must be a string")
    if len(cookies) > MAX_CREDENTIAL_CHARS:
        raise InputError("cookies are too large")
    tokens = payload.get("poTokens", payload.get("po_tokens", []))
    if tokens is None or tokens == "":
        tokens = []
    if isinstance(tokens, str):
        tokens = [line.strip() for line in tokens.splitlines() if line.strip() and not line.lstrip().startswith("#")]
    if not isinstance(tokens, list) or any(not isinstance(item, str) for item in tokens):
        raise InputError("poTokens must be a string or array of strings")
    normalized = []
    for item in tokens:
        item = item.strip()
        if item:
            normalized.append(item if "." in item.split("+", 1)[0] else "mweb.gvs+" + item)
    if sum(len(item) for item in normalized) > MAX_CREDENTIAL_CHARS:
        raise InputError("poTokens are too large")
    return cookies.strip(), normalized


def netscape_values(raw):
    values = {}
    expired = False
    now = int(time.time())
    for line in raw.splitlines():
        line = line.strip()
        if line.startswith("#HttpOnly_"):
            line = line[len("#HttpOnly_"):]
        elif not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 7:
            continue
        domain, _, _, _, expires, name, value = parts[:7]
        if "youtube.com" not in domain and "google.com" not in domain:
            continue
        try:
            if int(expires or 0) and int(expires) <= now:
                expired = True
                continue
        except ValueError:
            pass
        if name and value:
            values[name] = value
    return values, expired


def configure_module(name, payload):
    module = load_module(name)
    cookies, tokens = credential_values(payload)
    cookie_path = ""
    if cookies:
        handle = tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", suffix=".txt", delete=False)
        try:
            handle.write(cookies)
        finally:
            handle.close()
        cookie_path = handle.name
        _TEMP_PATHS.append(cookie_path)
    if hasattr(module, "cookie_args"):
        module.cookie_args = lambda: ["--cookies", cookie_path] if cookie_path else []
    if hasattr(module, "token_args"):
        module.token_args = lambda: [
            "--extractor-args",
            "youtube:player-client=default,mweb;po_token=" + ",".join(tokens),
        ] if tokens else []
    if name == "check":
        module.netscape_cookies = lambda: netscape_values(cookies)
        module.token_values = lambda: list(tokens)
    return module, bool(cookies)


def cleanup_temp_files():
    while _TEMP_PATHS:
        path = _TEMP_PATHS.pop()
        try:
            os.unlink(path)
        except OSError:
            pass


def read_request(stream):
    raw = stream.read(MAX_INPUT_BYTES + 1)
    if len(raw.encode("utf-8")) > MAX_INPUT_BYTES:
        raise InputError("input JSON is too large")
    if not raw.strip():
        raise InputError("stdin must contain one JSON object")
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError) as exc:
        raise InputError("stdin is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise InputError("stdin JSON must be an object")
    return payload


def dispatch(payload):
    action = text_value(payload, "action", required=True).lower().replace("-", "_")
    if action == "search":
        module, _ = configure_module("search", payload)
        rows = module.search(
            text_value(payload, "query", "keywords", required=True),
            int_value(payload, "limit", 10, 1, 50),
            int_value(payload, "offset", 0, 0, 50), timeout_value(payload, 30),
        )
        return {"provider": PROVIDER, "songs": rows}
    if action == "playlist_search":
        module, _ = configure_module("playlist", payload)
        rows = module.search(
            text_value(payload, "query", "keywords", required=True),
            int_value(payload, "limit", 10, 1, 30),
            int_value(payload, "offset", 0, 0, 100), timeout_value(payload, 45),
        )
        return {"provider": PROVIDER, "playlists": rows}
    if action == "playlist_tracks":
        module, _ = configure_module("playlist", payload)
        result = module.tracks(
            text_value(payload, "id", "playlistId", "playlist_id", "url", required=True),
            int_value(payload, "limit", 50, 1, 200),
            int_value(payload, "offset", 0, 0, 100000), timeout_value(payload, 45),
        )
        return {"provider": PROVIDER, **result}
    if action == "playurl":
        module, logged_in = configure_module("playurl", payload)
        quality = text_value(payload, "quality", default=module.QUALITY) or module.QUALITY
        if quality not in module.LEVELS:
            raise InputError("quality must be high or standard")
        result = module.resolve(
            text_value(payload, "id", "videoId", "video_id", "url", required=True),
            quality, timeout_value(payload, 45),
        )
        result["loggedIn"] = logged_in
        return result
    if action == "check":
        module, _ = configure_module("check", payload)
        return module.check(timeout_value(payload, 35))[0]
    raise InputError("action must be one of: " + ", ".join(AVAILABLE_ACTIONS))


def emit(stream, body):
    stream.write(json.dumps(body, ensure_ascii=False, indent=2) + "\n")
    stream.flush()


def safe_message(exc, payload):
    message = str(exc)
    if isinstance(payload, dict):
        for name in ("cookies", "poTokens", "po_tokens"):
            raw = payload.get(name)
            values = raw if isinstance(raw, list) else [raw]
            for value in values:
                if isinstance(value, str) and value:
                    message = message.replace(value, "[redacted]")
    return message


def main(input_stream=None, output_stream=None):
    input_stream = sys.stdin if input_stream is None else input_stream
    output_stream = sys.stdout if output_stream is None else output_stream
    payload = {}
    try:
        payload = read_request(input_stream)
        result = dispatch(payload)
    except (InputError, ValueError) as exc:
        cleanup_temp_files()
        emit(output_stream, {"ok": False, "error": {"code": "invalid_input", "message": safe_message(exc, payload)}})
        return 2
    except Exception as exc:
        cleanup_temp_files()
        emit(output_stream, {"ok": False, "error": {"code": "execution_failed", "message": safe_message(exc, payload)}})
        return 1
    cleanup_temp_files()
    emit(output_stream, {"ok": True, "data": result})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
