#!/usr/bin/env python3
"""Agent Runtime JSON stdin/stdout adapter for NetEase Cloud Music."""
import importlib.util
import json
import sys
from pathlib import Path

PROVIDER = "netease"
HERE = Path(__file__).resolve().parent
MAX_INPUT_BYTES = 1024 * 1024
MAX_CREDENTIAL_CHARS = 32768
AVAILABLE_ACTIONS = ("search", "playlist_search", "playlist_tracks", "playlist_mine", "playurl", "check")
_MODULES = {}


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
    value = payload.get("timeout", default)
    if isinstance(value, bool):
        raise InputError("timeout must be a number")
    try:
        value = float(value)
    except (TypeError, ValueError) as exc:
        raise InputError("timeout must be a number") from exc
    if not 1 <= value <= 300:
        raise InputError("timeout must be between 1 and 300")
    return value


def credential_value(payload):
    value = payload.get("cookie", "")
    if value is None:
        return ""
    if not isinstance(value, str):
        raise InputError("cookie must be a string")
    value = value.strip()
    if len(value) > MAX_CREDENTIAL_CHARS:
        raise InputError("cookie is too large")
    if "=" in value:
        pairs = {}
        for part in value.replace("\n", ";").split(";"):
            if "=" in part:
                key, item = part.split("=", 1)
                pairs[key.strip()] = item.strip()
        value = pairs.get("MUSIC_U", "")
    return value


def configure_module(name, payload):
    module = load_module(name)
    token = credential_value(payload)
    if hasattr(module, "music_u"):
        module.music_u = (lambda: (token, "runtime")) if name == "check" else (lambda: token)
    return module


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
        rows = load_module("search").search(
            text_value(payload, "query", "keywords", required=True),
            int_value(payload, "limit", 10, 1, 30),
            int_value(payload, "offset", 0, 0, 1000),
            timeout_value(payload, 12),
        )
        return {"provider": PROVIDER, "songs": rows}
    if action == "playlist_search":
        rows = load_module("playlist").search(
            text_value(payload, "query", "keywords", required=True),
            int_value(payload, "limit", 10, 1, 30),
            int_value(payload, "offset", 0, 0, 100000),
            timeout_value(payload, 12),
        )
        return {"provider": PROVIDER, "playlists": rows}
    if action == "playlist_tracks":
        result = load_module("playlist").tracks(
            text_value(payload, "id", "playlistId", "playlist_id", required=True),
            int_value(payload, "limit", 50, 1, 100),
            int_value(payload, "offset", 0, 0, 100000),
            timeout_value(payload, 12),
        )
        return {"provider": PROVIDER, **result}
    if action == "playlist_mine":
        rows = configure_module("playlist", payload).mine(
            int_value(payload, "limit", 30, 1, 50),
            int_value(payload, "offset", 0, 0, 100000),
            timeout_value(payload, 12),
        )
        return {"provider": PROVIDER, "playlists": rows}
    if action == "playurl":
        module = configure_module("playurl", payload)
        song_id = text_value(payload, "id", "songId", "song_id", required=True)
        if not song_id.isdigit():
            raise InputError("id must be numeric")
        quality = text_value(payload, "quality", default=module.QUALITY) or module.QUALITY
        return module.resolve(song_id, quality, timeout_value(payload, 15))
    if action == "check":
        return configure_module("check", payload).check(timeout_value(payload, 12))[0]
    raise InputError("action must be one of: " + ", ".join(AVAILABLE_ACTIONS))


def emit(stream, body):
    stream.write(json.dumps(body, ensure_ascii=False, indent=2) + "\n")
    stream.flush()


def safe_message(exc, payload):
    message = str(exc)
    credential = payload.get("cookie") if isinstance(payload, dict) else None
    if isinstance(credential, str) and credential:
        message = message.replace(credential, "[redacted]")
    return message


def main(input_stream=None, output_stream=None):
    input_stream = sys.stdin if input_stream is None else input_stream
    output_stream = sys.stdout if output_stream is None else output_stream
    payload = {}
    try:
        payload = read_request(input_stream)
        result = dispatch(payload)
    except (InputError, ValueError) as exc:
        emit(output_stream, {"ok": False, "error": {"code": "invalid_input", "message": safe_message(exc, payload)}})
        return 2
    except Exception as exc:
        emit(output_stream, {"ok": False, "error": {"code": "execution_failed", "message": safe_message(exc, payload)}})
        return 1
    emit(output_stream, {"ok": True, "data": result})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
