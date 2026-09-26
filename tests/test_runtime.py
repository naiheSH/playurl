import importlib.util
import io
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
PROVIDERS = ("netease", "qq", "kugou", "qishui", "spotify", "youtube")


def load(provider):
    name = f"playurl_{provider}_runtime_test"
    spec = importlib.util.spec_from_file_location(name, ROOT / provider / "runtime.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class RuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runtimes = {provider: load(provider) for provider in PROVIDERS}

    def invoke(self, runtime, payload):
        output = io.StringIO()
        code = runtime.main(io.StringIO(json.dumps(payload)), output)
        return code, json.loads(output.getvalue())

    def fake_modules(self, provider):
        search = SimpleNamespace(search=lambda *args: [{"provider": provider, "id": "song"}])
        playlist = SimpleNamespace(
            search=lambda *args: [{"provider": provider, "id": "playlist"}],
            tracks=lambda *args: {
                "playlist": {"provider": provider, "id": "playlist"},
                "songs": [{"provider": provider, "id": "song"}],
                "total": 1,
            },
            mine=lambda *args: [{"provider": provider, "id": "mine"}],
        )
        playurl = SimpleNamespace(
            QUALITY="high" if provider == "youtube" else "exhigh",
            LEVELS=("high", "standard"),
            resolve=lambda *args: {
                "provider": provider,
                "id": str(args[0]),
                "url": "" if provider == "spotify" else "https://example.com/audio.m4a",
                "playable": provider != "spotify",
            },
            decrypt_to=lambda result, output: {"decryptedFile": output, "bytes": 1, "extension": ".m4a"},
        )
        check = SimpleNamespace(check=lambda *args: ({
            "provider": provider, "status": "expired", "valid": False,
        }, 1))
        return {"search": search, "playlist": playlist, "playurl": playurl, "check": check}

    def test_all_actions_use_one_json_request_and_response(self):
        ids = {
            "netease": "123",
            "qq": "002uJqIq4fgN2F",
            "kugou": "ABCDEF",
            "qishui": "456",
            "spotify": "1234567890123456789012",
            "youtube": "jNQXAC9IVRw",
        }
        for provider, runtime in self.runtimes.items():
            modules = self.fake_modules(provider)
            requests = [
                {"action": "search", "query": "test"},
                {"action": "playlist_search", "query": "test"},
                {"action": "playlist_tracks", "id": "playlist"},
                {"action": "playurl", "id": ids[provider]},
                {"action": "check"},
            ]
            if provider != "youtube":
                requests.append({"action": "playlist_mine"})
            for payload in requests:
                with self.subTest(provider=provider, action=payload["action"]), \
                        patch.object(runtime, "load_module", side_effect=lambda name, values=modules: values[name]):
                    code, body = self.invoke(runtime, payload)
                self.assertEqual(code, 0)
                self.assertTrue(body["ok"])
                self.assertEqual(body["data"]["provider"], provider)

    def test_business_limit_is_successful_runtime_result(self):
        runtime = self.runtimes["spotify"]
        modules = self.fake_modules("spotify")
        with patch.object(runtime, "load_module", side_effect=lambda name: modules[name]):
            code, body = self.invoke(runtime, {
                "action": "playurl", "id": "1234567890123456789012",
            })
        self.assertEqual(code, 0)
        self.assertTrue(body["ok"])
        self.assertFalse(body["data"]["playable"])

    def test_qishui_decrypt_output_is_returned_as_json(self):
        runtime = self.runtimes["qishui"]
        modules = self.fake_modules("qishui")
        with patch.object(runtime, "load_module", side_effect=lambda name: modules[name]):
            code, body = self.invoke(runtime, {
                "action": "playurl", "id": "123", "decryptOutput": "song.m4a",
            })
        self.assertEqual(code, 0)
        self.assertEqual(body["data"]["decryptedFile"], "song.m4a")
        self.assertTrue(body["data"]["directPlayable"])

    def test_invalid_json_is_structured_and_exits_two(self):
        for provider, runtime in self.runtimes.items():
            with self.subTest(provider=provider):
                output = io.StringIO()
                code = runtime.main(io.StringIO("not-json"), output)
                body = json.loads(output.getvalue())
                self.assertEqual(code, 2)
                self.assertFalse(body["ok"])
                self.assertEqual(body["error"]["code"], "invalid_input")

    def test_execution_failure_is_structured_and_exits_one(self):
        runtime = self.runtimes["netease"]
        broken = SimpleNamespace(search=lambda *args: (_ for _ in ()).throw(RuntimeError("offline")))
        with patch.object(runtime, "load_module", return_value=broken):
            code, body = self.invoke(runtime, {"action": "search", "query": "test"})
        self.assertEqual(code, 1)
        self.assertFalse(body["ok"])
        self.assertEqual(body["error"]["code"], "execution_failed")

    def test_real_process_protocol_and_legacy_cli_remain_distinct(self):
        track_id = "1234567890123456789012"
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        runtime = subprocess.run(
            [sys.executable, str(ROOT / "spotify" / "runtime.py")],
            input=json.dumps({"action": "playurl", "id": track_id}),
            text=True,
            encoding="utf-8",
            env=env,
            capture_output=True,
            check=False,
        )
        self.assertEqual(runtime.returncode, 0, runtime.stderr)
        self.assertEqual(runtime.stderr, "")
        self.assertTrue(json.loads(runtime.stdout)["ok"])

        legacy = subprocess.run(
            [sys.executable, str(ROOT / "spotify" / "playurl.py"), track_id],
            text=True,
            encoding="utf-8",
            env=env,
            capture_output=True,
            check=False,
        )
        self.assertEqual(legacy.returncode, 1, legacy.stderr)
        self.assertNotIn('"ok"', legacy.stdout)
        self.assertEqual(json.loads(legacy.stdout)["restriction"]["category"], "provider_limited")


if __name__ == "__main__":
    unittest.main()
