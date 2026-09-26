#!/usr/bin/env python3
"""Skill Studio JSON stdin/stdout entrypoint for Kugou Music."""
import importlib.util
import json
import sys
from pathlib import Path

PROVIDER = "kugou"
HERE = Path(__file__).resolve().parent
MAX_INPUT_BYTES = 1024 * 1024
MAX_COOKIE_CHARS = 32768
ACTIONS = (
    "search",
    "playlist_search",
    "playlist_tracks",
    "playlist_mine",
    "playurl",
    "check",
)
_MODULES = {}


class InputError(ValueError):
    pass


def load_module(name):
    if name not in _MODULES:
        spec = importlib.util.spec_from_file_location(f"skillstudio_kugou_{name}", HERE / f"{name}.py")
        if spec is None or spec.loader is None:
            raise RuntimeError(f"cannot load {name}.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        _MODULES[name] = module
    return _MODULES[name]


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


def int_alias_value(payload, names, default, minimum=0, maximum=1000):
    name = next((item for item in names if item in payload), names[0])
    return int_value({name: payload.get(name, default)}, name, default, minimum, maximum)


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


def cookie_value(payload):
    value = payload.get("cookie", "")
    if value is None:
        return ""
    if not isinstance(value, str):
        raise InputError("cookie must be a string")
    value = value.strip()
    if len(value) > MAX_COOKIE_CHARS:
        raise InputError("cookie is too large")
    return value


def configure_module(name, payload):
    module = load_module(name)
    cookie = cookie_value(payload)
    if hasattr(module, "load_cookie"):
        module.load_cookie = lambda: cookie
    if name == "playurl" and hasattr(module, "ensure_device"):
        # Skill Studio does not ship device.py or install cryptography.
        module.ensure_device = lambda current_cookie, auth: (current_cookie, auth)
    return module


def dispatch(payload):
    action = text_value(payload, "action", required=True).lower().replace("-", "_")
    if action == "search":
        rows = load_module("search").search(
            text_value(payload, "query", "keywords", required=True),
            int_value(payload, "limit", 10, 1, 30),
            int_value(payload, "offset", 0, 0, 100000),
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
        result = configure_module("playlist", payload).tracks(
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
        return module.resolve(
            text_value(payload, "id", "hash", required=True),
            text_value(payload, "albumId", "album_id"),
            int_alias_value(payload, ("albumAudioId", "album_audio_id"), 0, 0, 2**63 - 1),
            text_value(payload, "quality", default=module.QUALITY) or module.QUALITY,
            timeout_value(payload, 8),
        )
    if action == "check":
        return configure_module("check", payload).check(timeout_value(payload, 12))[0]
    raise InputError("action must be one of: " + ", ".join(ACTIONS))


def emit(stream, body):
    stream.write(json.dumps(body, ensure_ascii=False, indent=2) + "\n")
    stream.flush()


def safe_message(exc, payload):
    message = str(exc)
    cookie = payload.get("cookie") if isinstance(payload, dict) else None
    if isinstance(cookie, str) and cookie:
        message = message.replace(cookie, "[redacted]")
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
