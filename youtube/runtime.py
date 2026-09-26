#!/usr/bin/env python3
"""Agent Runtime JSON stdin/stdout adapter for YouTube audio and playlists."""
import importlib.util
import json
import sys
from pathlib import Path

PROVIDER = "youtube"
HERE = Path(__file__).resolve().parent
MAX_INPUT_BYTES = 1024 * 1024
AVAILABLE_ACTIONS = ("search", "playlist_search", "playlist_tracks", "playurl", "check")
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
    if isinstance(payload.get("timeout", default), bool):
        raise InputError("timeout must be a number")
    try:
        value = float(payload.get("timeout", default))
    except (TypeError, ValueError) as exc:
        raise InputError("timeout must be a number") from exc
    if not 1 <= value <= 300:
        raise InputError("timeout must be between 1 and 300")
    return value


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
            int_value(payload, "limit", 10, 1, 50),
            int_value(payload, "offset", 0, 0, 50), timeout_value(payload, 30),
        )
        return {"provider": PROVIDER, "songs": rows}
    if action == "playlist_search":
        rows = load_module("playlist").search(
            text_value(payload, "query", "keywords", required=True),
            int_value(payload, "limit", 10, 1, 30),
            int_value(payload, "offset", 0, 0, 100), timeout_value(payload, 45),
        )
        return {"provider": PROVIDER, "playlists": rows}
    if action == "playlist_tracks":
        result = load_module("playlist").tracks(
            text_value(payload, "id", "playlistId", "playlist_id", "url", required=True),
            int_value(payload, "limit", 50, 1, 200),
            int_value(payload, "offset", 0, 0, 100000), timeout_value(payload, 45),
        )
        return {"provider": PROVIDER, **result}
    if action == "playurl":
        module = load_module("playurl")
        quality = text_value(payload, "quality", default=module.QUALITY) or module.QUALITY
        if quality not in module.LEVELS:
            raise InputError("quality must be high or standard")
        return module.resolve(
            text_value(payload, "id", "videoId", "video_id", "url", required=True),
            quality, timeout_value(payload, 45),
        )
    if action == "check":
        return load_module("check").check(timeout_value(payload, 35))[0]
    raise InputError("action must be one of: " + ", ".join(AVAILABLE_ACTIONS))


def emit(stream, body):
    stream.write(json.dumps(body, ensure_ascii=False, indent=2) + "\n")
    stream.flush()


def main(input_stream=None, output_stream=None):
    input_stream = sys.stdin if input_stream is None else input_stream
    output_stream = sys.stdout if output_stream is None else output_stream
    try:
        result = dispatch(read_request(input_stream))
    except (InputError, ValueError) as exc:
        emit(output_stream, {"ok": False, "error": {"code": "invalid_input", "message": str(exc)}})
        return 2
    except Exception as exc:
        emit(output_stream, {"ok": False, "error": {"code": "execution_failed", "message": str(exc)}})
        return 1
    emit(output_stream, {"ok": True, "data": result})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
