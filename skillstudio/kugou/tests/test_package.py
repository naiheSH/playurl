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

HERE = Path(__file__).resolve().parent
PACKAGE_ROOT = HERE.parent


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class KugouSkillStudioTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runtime = load_module("skillstudio_kugou_runtime_test", PACKAGE_ROOT / "scripts" / "runtime.py")
        cls.builder = load_module("skillstudio_kugou_builder_test", PACKAGE_ROOT / "build.py")

    def invoke(self, payload):
        output = io.StringIO()
        code = self.runtime.main(io.StringIO(json.dumps(payload)), output)
        return code, output.getvalue(), json.loads(output.getvalue())

    def fake_modules(self):
        state = {}
        search = SimpleNamespace(search=lambda *args: [{"id": "HASH", "name": "歌", "artist": "歌手"}])
        playlist = SimpleNamespace(
            load_cookie=lambda: "from-file",
            search=lambda *args: [{"id": "1", "name": "歌单"}],
            tracks=lambda *args: {"songs": [], "total": 0},
            mine=lambda *args: [{"id": "collection_1", "cookieSeen": playlist.load_cookie()}],
        )

        def resolve(*args):
            state["cookie"] = playurl.load_cookie()
            state["device"] = playurl.ensure_device(state["cookie"], {})
            return {"provider": "kugou", "id": args[0], "playable": False, "url": ""}

        playurl = SimpleNamespace(
            QUALITY="exhigh",
            load_cookie=lambda: "from-file",
            ensure_device=lambda *args: (_ for _ in ()).throw(AssertionError("device registration called")),
            resolve=resolve,
        )
        check = SimpleNamespace(
            load_cookie=lambda: "from-file",
            check=lambda *args: ({"provider": "kugou", "status": "valid", "valid": True}, 0),
        )
        return {"search": search, "playlist": playlist, "playurl": playurl, "check": check}, state

    def test_all_actions_return_one_json_envelope(self):
        modules, _ = self.fake_modules()
        requests = (
            {"action": "search", "query": "歌"},
            {"action": "playlist_search", "query": "歌单"},
            {"action": "playlist_tracks", "id": "1"},
            {"action": "playlist_mine", "cookie": "secret"},
            {"action": "playurl", "id": "HASH"},
            {"action": "check", "cookie": "secret"},
        )
        for payload in requests:
            with self.subTest(action=payload["action"]), patch.object(
                self.runtime, "load_module", side_effect=lambda name, values=modules: values[name]
            ):
                code, raw, body = self.invoke(payload)
            self.assertEqual(code, 0)
            self.assertTrue(body["ok"])
            self.assertEqual(body["data"]["provider"], "kugou")
            decoded, end = json.JSONDecoder().raw_decode(raw)
            self.assertEqual(decoded, body)
            self.assertFalse(raw[end:].strip())

    def test_cookie_is_injected_and_device_registration_is_disabled(self):
        modules, state = self.fake_modules()
        with patch.object(self.runtime, "load_module", side_effect=lambda name: modules[name]):
            code, raw, body = self.invoke({"action": "playurl", "id": "HASH", "cookie": "private-cookie"})
        self.assertEqual(code, 0)
        self.assertFalse(body["data"]["playable"])
        self.assertEqual(state["cookie"], "private-cookie")
        self.assertEqual(state["device"], ("private-cookie", {}))
        self.assertNotIn("private-cookie", raw)

    def test_invalid_input_is_json_and_does_not_leak_cookie(self):
        cookie = "private-cookie-value"
        code, raw, body = self.invoke({"action": "unknown", "cookie": cookie})
        self.assertEqual(code, 2)
        self.assertEqual(body["error"]["code"], "invalid_input")
        self.assertNotIn(cookie, raw)

    def test_built_zip_is_complete_and_excludes_local_login(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = self.builder.build(Path(temporary) / "skill.zip")
            with zipfile.ZipFile(output) as archive:
                names = set(archive.namelist())
                self.assertIn("scripts/runtime.py", names)
                self.assertIn("scripts/playurl.py", names)
                self.assertIn(".skill-studio/contract.json", names)
                self.assertNotIn("scripts/login.py", names)
                self.assertNotIn("scripts/device.py", names)
                self.assertFalse(any(Path(name).name == "cookie" for name in names))
                contract = json.loads(archive.read(".skill-studio/contract.json"))
                generated = json.loads(archive.read(".skill-studio/generated-code.json"))
                dependencies = json.loads(archive.read(".skill-studio/dependencies.json"))
                implementation = json.loads(archive.read("implementation.json"))
            expected = {item["capabilityId"] for item in contract["capabilities"]}
            actual = {item["capabilityId"] for item in implementation["codeEntrypoints"]}
            self.assertEqual(expected, actual)
            self.assertEqual(len(generated["generatedCode"]), 1)
            self.assertEqual(generated["generatedCode"][0]["entrypoint"], "scripts/runtime.py")
            tools = {item["name"] for item in dependencies["depends_on_tools"]}
            self.assertEqual(tools, {
                "gf-service-kv-get",
                "gf-service-kv-set",
            })
            self.assertTrue(all(item.get("version") is None for item in dependencies["depends_on_tools"]))


if __name__ == "__main__":
    unittest.main()
