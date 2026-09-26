#!/usr/bin/env python3
"""Generate and package every standalone Skill Studio submodule."""
import argparse
import json
import shutil
import tempfile
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
ENVELOPE = {
    "type": "object",
    "required": ["ok"],
    "properties": {
        "ok": {"type": "boolean"},
        "data": {"type": "object"},
        "error": {
            "type": "object",
            "required": ["code", "message"],
            "properties": {"code": {"type": "string"}, "message": {"type": "string"}},
        },
    },
}
TOOLS = [
    {"name": "gf-service-kv-get", "version": None},
    {"name": "gf-service-kv-set", "version": None},
]

SPECS = {
    "kugou": {
        "display": "酷狗音乐搜索与播放地址解析",
        "description": "搜索酷狗音乐歌曲和歌单、读取个人或公开歌单、解析短期播放地址并检查 Cookie。",
        "kv": "kugou-cookie",
        "actions": ("search", "playlist_search", "playlist_tracks", "playlist_mine", "playurl", "check"),
    },
    "netease": {
        "display": "网易云音乐搜索与播放地址解析",
        "description": "搜索网易云音乐歌曲和歌单、读取歌单曲目、解析短期播放地址并检查 MUSIC_U。",
        "kv": "netease-cookie",
        "actions": ("search", "playlist_search", "playlist_tracks", "playlist_mine", "playurl", "check"),
    },
    "qq": {
        "display": "QQ 音乐搜索与播放地址解析",
        "description": "搜索 QQ 音乐歌曲和歌单、读取个人或公开歌单、解析短期播放地址并检查 Cookie。",
        "kv": "qqmusic-cookie",
        "actions": ("search", "playlist_search", "playlist_tracks", "playlist_mine", "playurl", "check"),
    },
    "qishui": {
        "display": "汽水音乐搜索与播放地址解析",
        "description": "搜索汽水音乐歌曲和歌单、读取个人歌单、解析 track_id 播放地址并检查 Cookie。",
        "kv": "qishui-cookie",
        "actions": ("search", "playlist_search", "playlist_tracks", "playlist_mine", "playurl", "check"),
    },
    "spotify": {
        "display": "Spotify 元数据与官方播放",
        "description": "通过 Spotify 官方 API 搜索歌曲和歌单、读取账号歌单、检查 OAuth 并返回官方播放方式。",
        "kv": "spotify-credentials",
        "actions": ("search", "playlist_search", "playlist_tracks", "playlist_mine", "playurl", "check"),
    },
    "youtube": {
        "display": "YouTube 音频与播放列表",
        "description": "使用 yt-dlp 搜索 YouTube 视频和播放列表，并解析短期 M4A 或 MP3 音频地址。",
        "kv": "youtube-cookies / youtube-po-tokens",
        "actions": ("search", "playlist_search", "playlist_tracks", "playurl", "check"),
        "dependencies": ["yt-dlp"],
    },
}

CAPABILITY_NAMES = {
    "search": "search-songs",
    "playlist_search": "search-playlists",
    "playlist_tracks": "list-playlist-tracks",
    "playlist_mine": "list-my-playlists",
    "playurl": "resolve-play-url",
    "check": "check-credentials",
}


def capability_id(provider, action):
    return f"{provider}-{CAPABILITY_NAMES[action]}"


def credential_schema(provider):
    if provider == "spotify":
        return {"type": ["object", "string"], "writeOnly": True}
    if provider == "youtube":
        return None
    return {"type": "string", "maxLength": 32768, "writeOnly": True}


def input_schema(provider, action):
    properties = {"action": {"const": action}}
    required = ["action"]
    if action in ("search", "playlist_search"):
        search_limits = {"qq": 10, "spotify": 10, "youtube": 50}
        playlist_limits = {"spotify": 10}
        max_limit = (search_limits if action == "search" else playlist_limits).get(provider, 30)
        search_offsets = {"qq": 0, "qishui": 30, "spotify": 1000, "youtube": 50}
        max_offset = search_offsets.get(provider, 100000) if action == "search" else 100000
        properties.update({
            "query": {"type": "string", "minLength": 1},
            "limit": {"type": "integer", "minimum": 1, "maximum": max_limit, "default": 10},
            "offset": {"type": "integer", "minimum": 0, "maximum": max_offset, "default": 0},
        })
        required.append("query")
    elif action == "playlist_tracks":
        max_limit = {"kugou": 100, "netease": 100, "spotify": 50}.get(provider, 200)
        properties.update({
            "id": {"type": "string", "minLength": 1},
            "limit": {"type": "integer", "minimum": 1, "maximum": max_limit, "default": 50},
            "offset": {"type": "integer", "minimum": 0, "maximum": 100000, "default": 0},
        })
        required.append("id")
    elif action == "playlist_mine":
        properties.update({
            "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 30},
            "offset": {"type": "integer", "minimum": 0, "maximum": 100000, "default": 0},
        })
    elif action == "playurl":
        properties["id"] = {"type": "string", "minLength": 1}
        required.append("id")
        if provider == "kugou":
            properties.update({
                "quality": {"type": "string"},
                "albumId": {"type": ["string", "integer"]},
                "albumAudioId": {"type": ["string", "integer"]},
            })
        elif provider == "qq":
            properties.update({"quality": {"type": "string"}, "mediaMid": {"type": "string"}})
        elif provider == "qishui":
            pass
        elif provider == "spotify":
            pass
        else:
            properties["quality"] = {"type": "string"}
    properties["timeout"] = {"type": "number", "minimum": 1, "maximum": 300}
    cred = credential_schema(provider)
    if cred:
        properties["credentials" if provider == "spotify" else "cookie"] = cred
    if provider == "youtube":
        properties["cookies"] = {"type": "string", "maxLength": 1048576, "writeOnly": True}
        properties["poTokens"] = {"type": ["string", "array"], "writeOnly": True}
    credential_required = (
        (provider in ("kugou", "netease", "qq", "qishui") and action in ("playlist_mine", "check"))
        or (provider == "spotify" and action != "playurl")
    )
    if credential_required:
        required.append("credentials" if provider == "spotify" else "cookie")
    return {"type": "object", "additionalProperties": False, "required": required, "properties": properties}


def capability_dependencies(provider, action):
    needs_get = (
        action in ("playlist_mine", "check")
        or provider == "spotify" and action != "playurl"
    )
    items = []
    if needs_get:
        items.append({"kind": "tool", "binding": "gf-service-kv-get"})
    if action == "check":
        items.append({"kind": "tool", "binding": "gf-service-kv-set"})
    items.append({"kind": "code"})
    return items


def action_description(provider, action):
    names = {
        "search": "公开搜索歌曲或视频。",
        "playlist_search": "公开搜索歌单或播放列表。",
        "playlist_tracks": "读取指定歌单或播放列表的曲目。",
        "playlist_mine": "读取当前账号的歌单。",
        "playurl": "解析播放结果或官方播放方式。",
        "check": "检查当前平台凭据。",
    }
    return names[action] + f" 入口 scripts/runtime.py，action={action}。"


def metadata(provider, version):
    spec = SPECS[provider]
    caps = []
    for action in spec["actions"]:
        caps.append({
            "capabilityId": capability_id(provider, action),
            "dependencies": capability_dependencies(provider, action),
            "description": action_description(provider, action),
            "inputSchema": input_schema(provider, action),
            "outputSchema": ENVELOPE,
        })
    first = capability_id(provider, spec["actions"][0])
    generated = {
        "capability": first,
        "credentialRefs": [],
        "dependencies": spec.get("dependencies", []),
        "entrypointPath": "scripts/runtime.py",
        "language": "python",
        "network": "forbidden",
        "runtimeVersion": "3.13",
    }
    contract = {
        "activation": {
            "examples": [f"搜索{spec['display']}中的歌曲", "搜索歌单并列出曲目", "解析播放地址", "检查凭据"],
            "notWhen": ["非当前平台的搜索或播放"],
            "when": spec["description"],
        },
        "capabilities": caps,
        "capability_contract": {
            "depends_on_skills": [],
            "depends_on_tools": TOOLS,
            "generated_capabilities": [{"entrypoint": "scripts/runtime.py", "name": first}],
        },
        "identity": {"display_name": spec["display"], "name": f"playurl-{provider}", "visibility": "public"},
        "runtime_contract": {
            "generated_code": [generated],
            "runtime_context": {
                "device_id": {"runtime_key": "deviceId", "source": "runtime_context"},
                "session_id": {"runtime_key": "sessionId", "source": "runtime_context"},
                "user_id": {"runtime_key": "userId", "source": "runtime_context"},
            },
        },
        "schema_version": "skill-studio-create/submission-v1",
        "verification_contract": {"cases": [], "cases_uri": "cases/verification.cases.json"},
    }
    runtime = {"generated_code": [generated], "runtime_context": contract["runtime_contract"]["runtime_context"]}
    dependencies = {
        "adapters": [], "assets": [], "credentials": [], "depends_on_skills": [],
        "depends_on_tools": TOOLS,
        "generated_code": [{"entrypoint": "scripts/runtime.py", "name": first}],
    }
    generated_code = {"generatedCode": [{
        "capability": first, "command": ["python", "scripts/runtime.py"], "credentialBindings": [],
        "dependencies": spec.get("dependencies", []), "entrypoint": "scripts/runtime.py",
        "inputSchema": {}, "language": "python", "network": False, "outputSchema": {}, "provider": None,
    }]}
    implementation = {"schemaVersion": 1, "codeEntrypoints": [
        {"capabilityId": capability_id(provider, action), "entrypointPath": "scripts/runtime.py"}
        for action in spec["actions"]
    ]}
    manifest = {
        "display_name": spec["display"], "generated_by": "local-skillstudio-completion",
        "profile": "skill-studio-create/submission-v1", "skill_name": f"playurl-{provider}", "version": version,
    }
    skill_metadata = {
        "capability_boundary": "\n".join(item["description"] for item in caps),
        "description": spec["description"], "display_name": spec["display"],
        "out_of_scope_boundary": "非当前平台的搜索或播放", "skill_name": f"playurl-{provider}",
        "test_cases": [], "tools": [item["name"] for item in TOOLS], "version": version,
    }
    return {
        ".skill-studio/contract.json": contract,
        ".skill-studio/dependencies.json": dependencies,
        ".skill-studio/generated-code.json": generated_code,
        ".skill-studio/generation-report.json": {
            "generated_by": "local-skillstudio-completion", "profile": "skill-studio-create/submission-v1", "status": "authored",
        },
        ".skill-studio/manifest.json": manifest,
        ".skill-studio/runtime.json": runtime,
        "implementation.json": implementation,
        "skill-metadata.json": skill_metadata,
        "cases/verification.cases.json": {"cases": []},
    }


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def current_version(provider):
    path = HERE / provider / "skill-metadata.json"
    if path.is_file():
        try:
            value = json.loads(path.read_text(encoding="utf-8")).get("version")
            if isinstance(value, str) and value.strip():
                return value.strip()
        except (OSError, ValueError):
            pass
    return "0.0.0"


def sync(provider, version=None):
    package = HERE / provider
    for relative, value in metadata(provider, version or current_version(provider)).items():
        write_json(package / relative, value)
    agents = package / "agents" / "openai.yaml"
    agents.parent.mkdir(parents=True, exist_ok=True)
    spec = SPECS[provider]
    agents.write_text(
        f"name: playurl-{provider}\n"
        f"description: {spec['description']}\n"
        "system_prompt: >-\n"
        "  读取 SKILL.md 后按其中的能力边界和 JSON Code 入口执行；不要泄露 KV 凭据。\n",
        encoding="utf-8",
    )
    return package


def add_file(archive, path, relative):
    info = zipfile.ZipInfo(relative.as_posix(), date_time=(2026, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = (0o755 if path.suffix == ".py" else 0o644) << 16
    archive.writestr(info, path.read_bytes())


def archive_filename(provider, version=None):
    return f"skill-studio-{provider}-{version}.zip" if version else f"skill-studio-{provider}.zip"


def build(provider, output=None, version=None):
    package = sync(provider)
    output = (output or ROOT / "dist" / archive_filename(provider, version)).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f"playurl-{provider}-skillstudio-") as temporary:
        stage = Path(temporary)
        for path in package.rglob("*"):
            if path.is_file() and path.name != "build.py" and "tests" not in path.parts:
                target = stage / path.relative_to(package)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, target)
        if version:
            for relative, value in metadata(provider, version).items():
                write_json(stage / relative, value)
        scripts = stage / "scripts"
        for name in ("search.py", "playlist.py", "playurl.py", "check.py"):
            shutil.copy2(ROOT / provider / name, scripts / name)
        with zipfile.ZipFile(output, "w") as archive:
            for path in sorted(item for item in stage.rglob("*") if item.is_file()):
                add_file(archive, path, path.relative_to(stage))
    return output


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("provider", choices=tuple(SPECS) + ("all",), default="all", nargs="?")
    parser.add_argument("--version", default="", help="append a release version to ZIP filenames")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "dist")
    args = parser.parse_args()
    providers = SPECS if args.provider == "all" else (args.provider,)
    for provider in providers:
        filename = archive_filename(provider, args.version or None)
        print(build(provider, args.output_dir / filename, args.version or None))


if __name__ == "__main__":
    main()
