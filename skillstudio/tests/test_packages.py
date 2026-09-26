import importlib.util
import io
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
SKILLSTUDIO = ROOT / "skillstudio"
PROVIDERS = ("kugou", "netease", "qq", "qishui", "spotify", "youtube")
ACTIONS = {
    "kugou": ("search", "playlist_search", "playlist_tracks", "playlist_mine", "playurl", "check"),
    "netease": ("search", "playlist_search", "playlist_tracks", "playlist_mine", "playurl", "check"),
    "qq": ("search", "playlist_search", "playlist_tracks", "playlist_mine", "playurl", "check"),
    "qishui": ("search", "playlist_search", "playlist_tracks", "playlist_mine", "playurl", "check"),
    "spotify": ("search", "playlist_search", "playlist_tracks", "playlist_mine", "playurl", "check"),
    "youtube": ("search", "playlist_search", "playlist_tracks", "playurl", "check"),
}


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class SkillStudioPackageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.builder = load_module("skillstudio_all_builder_test", SKILLSTUDIO / "build_platforms.py")

    def test_all_packages_have_normalized_metadata_and_safe_contents(self):
        with tempfile.TemporaryDirectory() as temporary:
            for provider in PROVIDERS:
                with self.subTest(provider=provider):
                    output = self.builder.build(provider, Path(temporary) / f"{provider}.zip", "9.8.7")
                    with zipfile.ZipFile(output) as archive:
                        names = set(archive.namelist())
                        contract = json.loads(archive.read(".skill-studio/contract.json"))
                        runtime = json.loads(archive.read(".skill-studio/runtime.json"))
                        generated = json.loads(archive.read(".skill-studio/generated-code.json"))
                        dependencies = json.loads(archive.read(".skill-studio/dependencies.json"))
                        implementation = json.loads(archive.read("implementation.json"))
                        manifest = json.loads(archive.read(".skill-studio/manifest.json"))
                        skill_metadata = json.loads(archive.read("skill-metadata.json"))
                    self.assertIn("scripts/runtime.py", names)
                    for name in ("search.py", "playlist.py", "playurl.py", "check.py"):
                        self.assertIn(f"scripts/{name}", names)
                    forbidden = {"login.py", "auth.py", "device.py", "cookie", "token", "request.json"}
                    self.assertFalse(forbidden.intersection({Path(name).name for name in names}))
                    expected = {item["capabilityId"] for item in contract["capabilities"]}
                    mapped = {item["capabilityId"] for item in implementation["codeEntrypoints"]}
                    self.assertEqual(expected, mapped)
                    self.assertTrue(all(item["outputSchema"] for item in contract["capabilities"]))
                    self.assertEqual(len(runtime["generated_code"]), 1)
                    self.assertEqual(len(generated["generatedCode"]), 1)
                    self.assertEqual(runtime["generated_code"][0]["runtimeVersion"], "3.13")
                    self.assertEqual(runtime["generated_code"][0]["network"], "forbidden")
                    self.assertEqual(
                        {item["name"] for item in dependencies["depends_on_tools"]},
                        {"gf-service-kv-get", "gf-service-kv-set"},
                    )
                    self.assertTrue(all(item["version"] is None for item in dependencies["depends_on_tools"]))
                    self.assertEqual(manifest["version"], "9.8.7")
                    self.assertEqual(skill_metadata["version"], "9.8.7")
                    if provider == "youtube":
                        self.assertEqual(generated["generatedCode"][0]["dependencies"], ["yt-dlp"])

    def test_every_runtime_rejects_bad_json_with_one_json_result(self):
        for provider in PROVIDERS:
            with self.subTest(provider=provider):
                runtime = load_module(
                    f"skillstudio_{provider}_bad_json_test",
                    SKILLSTUDIO / provider / "scripts" / "runtime.py",
                )
                output = io.StringIO()
                code = runtime.main(io.StringIO("not-json"), output)
                raw = output.getvalue()
                body, end = json.JSONDecoder().raw_decode(raw)
                self.assertEqual(code, 2)
                self.assertFalse(body["ok"])
                self.assertFalse(raw[end:].strip())

    def test_every_runtime_action_returns_one_json_envelope(self):
        for provider in PROVIDERS[1:]:
            runtime = load_module(
                f"skillstudio_{provider}_all_actions_test",
                SKILLSTUDIO / provider / "scripts" / "runtime.py",
            )
            settings = {"client_id": "id", "client_secret": "secret", "access_token": "token", "market": ""}
            search = SimpleNamespace(search=lambda *args: [{"id": "song", "name": "歌"}], config=lambda: settings)
            playlist = SimpleNamespace(
                search=lambda *args: [{"id": "list", "name": "歌单"}],
                tracks=lambda *args: {"songs": [], "total": 0},
                mine=lambda *args: [{"id": "mine"}],
                load_cookie=lambda: "disk",
                music_u=lambda: "disk",
                config=lambda: settings,
                cookie_args=lambda: [],
                token_args=lambda: [],
            )
            playurl = SimpleNamespace(
                QUALITY="high" if provider == "youtube" else "exhigh",
                LEVELS={"high": {}, "standard": {}} if provider == "youtube" else {},
                resolve=lambda *args: {"provider": provider, "id": str(args[0]), "playable": provider != "spotify"},
                load_cookie=lambda: "disk",
                music_u=lambda: "disk",
                config=lambda: settings,
                cookie_args=lambda: [],
                token_args=lambda: [],
            )
            check = SimpleNamespace(
                check=lambda *args: ({"provider": provider, "status": "valid", "valid": True}, 0),
                load_cookie=lambda: "disk",
                music_u=lambda: ("disk", "file"),
                config=lambda: settings,
                netscape_cookies=lambda: ({}, False),
                token_values=lambda: [],
            )
            modules = {"search": search, "playlist": playlist, "playurl": playurl, "check": check}
            identifier = "123" if provider in ("netease", "qishui") else "A" * 22 if provider == "spotify" else "song"
            requests = {
                "search": {"action": "search", "query": "歌"},
                "playlist_search": {"action": "playlist_search", "query": "歌单"},
                "playlist_tracks": {"action": "playlist_tracks", "id": "A" * 22 if provider == "spotify" else "list"},
                "playlist_mine": {"action": "playlist_mine"},
                "playurl": {"action": "playurl", "id": identifier},
                "check": {"action": "check"},
            }
            if provider in ("netease", "qq", "qishui"):
                requests["playlist_mine"]["cookie"] = "private-cookie"
                requests["check"]["cookie"] = "private-cookie"
            elif provider == "spotify":
                for action in ACTIONS[provider]:
                    if action != "playurl":
                        requests[action]["credentials"] = settings
            for action in ACTIONS[provider]:
                with self.subTest(provider=provider, action=action), patch.object(
                    runtime, "load_module", side_effect=lambda name, values=modules: values[name]
                ):
                    output = io.StringIO()
                    code = runtime.main(io.StringIO(json.dumps(requests[action])), output)
                    raw = output.getvalue()
                    body, end = json.JSONDecoder().raw_decode(raw)
                self.assertEqual(code, 0, raw)
                self.assertTrue(body["ok"])
                self.assertEqual(body["data"]["provider"], provider)
                self.assertFalse(raw[end:].strip())

    def test_metadata_exposes_exact_runtime_actions(self):
        for provider in PROVIDERS:
            with self.subTest(provider=provider):
                contract = json.loads(
                    (SKILLSTUDIO / provider / ".skill-studio" / "contract.json").read_text(encoding="utf-8")
                )
                constants = {item["inputSchema"]["properties"]["action"]["const"] for item in contract["capabilities"]}
                self.assertEqual(constants, set(ACTIONS[provider]))

    def test_domestic_credentials_are_injected_without_leaking(self):
        cases = {
            "netease": ("MUSIC_U=private-value; os=pc", "private-value"),
            "qq": ("uin=private-value", "uin=private-value"),
            "qishui": ("sessionid=private-value", "sessionid=private-value"),
        }
        for provider, (credential, expected) in cases.items():
            with self.subTest(provider=provider):
                runtime = load_module(
                    f"skillstudio_{provider}_credential_test",
                    SKILLSTUDIO / provider / "scripts" / "runtime.py",
                )
                seen = {}
                if provider == "netease":
                    def check(timeout):
                        seen[provider] = module.music_u()[0]
                        return {"provider": provider, "status": "valid"}, 0

                    module = SimpleNamespace(
                        music_u=lambda: "disk",
                        check=check,
                    )
                else:
                    def check(timeout):
                        seen[provider] = module.load_cookie()
                        return {"provider": provider, "status": "valid"}, 0

                    module = SimpleNamespace(
                        load_cookie=lambda: "disk",
                        check=check,
                    )
                output = io.StringIO()
                with patch.object(runtime, "load_module", return_value=module):
                    code = runtime.main(io.StringIO(json.dumps({"action": "check", "cookie": credential})), output)
                body = json.loads(output.getvalue())
                self.assertEqual(code, 0)
                self.assertEqual(seen[provider], expected)
                self.assertNotIn(credential, output.getvalue())

    def test_spotify_credentials_are_injected(self):
        runtime = load_module("skillstudio_spotify_credential_test", SKILLSTUDIO / "spotify" / "scripts" / "runtime.py")
        module = SimpleNamespace(
            config=lambda: {},
            check=lambda timeout: ({"provider": "spotify", "clientId": module.config()["client_id"]}, 0),
        )
        payload = {"action": "check", "credentials": {"client_id": "private-id", "client_secret": "private-secret"}}
        output = io.StringIO()
        with patch.object(runtime, "load_module", return_value=module):
            code = runtime.main(io.StringIO(json.dumps(payload)), output)
        body = json.loads(output.getvalue())
        self.assertEqual(code, 0)
        self.assertEqual(body["data"]["clientId"], "private-id")
        self.assertNotIn("private-secret", output.getvalue())

    def test_youtube_cookie_temp_file_is_removed(self):
        runtime = load_module("skillstudio_youtube_credential_test", SKILLSTUDIO / "youtube" / "scripts" / "runtime.py")
        seen = {}

        def check(timeout):
            seen["cookies"] = module.netscape_cookies()[0]
            seen["tokens"] = module.token_values()
            return {"provider": "youtube", "status": "valid"}, 0

        module = SimpleNamespace(netscape_cookies=lambda: ({}, False), token_values=lambda: [], check=check)
        cookies = ".youtube.com\tTRUE\t/\tTRUE\t4102444800\tSID\tprivate-cookie"
        output = io.StringIO()
        with patch.object(runtime, "load_module", return_value=module):
            code = runtime.main(
                io.StringIO(json.dumps({"action": "check", "cookies": cookies, "poTokens": ["web.gvs+private-token"]})),
                output,
            )
        self.assertEqual(code, 0)
        self.assertEqual(seen["cookies"]["SID"], "private-cookie")
        self.assertEqual(seen["tokens"], ["web.gvs+private-token"])
        self.assertEqual(runtime._TEMP_PATHS, [])
        self.assertNotIn(cookies, output.getvalue())


if __name__ == "__main__":
    unittest.main()
