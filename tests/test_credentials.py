#!/usr/bin/env python3
"""Offline regression tests for provider credential checkers."""

import importlib.util
import json
import os
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch


HERE = Path(__file__).resolve().parent


class Response:
    def __init__(self, payload):
        self.payload = payload if isinstance(payload, bytes) else json.dumps(payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self):
        return self.payload


def load(name):
    staged = HERE / f"{name}_check.py"
    path = staged if staged.is_file() else HERE.parent / name / "check.py"
    spec = importlib.util.spec_from_file_location("check_" + name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@contextmanager
def local_files(module, files=None):
    with tempfile.TemporaryDirectory() as directory:
        old = module.HERE
        module.HERE = Path(directory)
        for name, content in (files or {}).items():
            (module.HERE / name).write_text(content, encoding="utf-8")
        try:
            yield
        finally:
            module.HERE = old


class CredentialChecks(unittest.TestCase):
    def test_netease_valid_and_missing(self):
        module = load("netease")
        with patch.dict(os.environ, {"NETEASE_MUSIC_U": "", "MUSIC_U": ""}, clear=False):
            with local_files(module):
                self.assertEqual(module.check()[1], 1)
            with local_files(module, {"cookie": "MUSIC_U=test"}):
                body, code = module.check(opener=lambda *_args, **_kwargs: Response({"code": 200, "account": {"id": 1}}))
                self.assertEqual((body["status"], code), ("valid", 0))

    def test_qq_valid_and_invalid_shape(self):
        module = load("qq")
        with local_files(module, {"cookie": "uin=123; qm_keyst=test"}):
            body, code = module.check(opener=lambda *_args, **_kwargs: Response({"code": 0, "req_0": {"code": 0, "data": {}}}))
            self.assertEqual((body["valid"], code), (True, 0))
        with local_files(module, {"cookie": "uin=123"}):
            self.assertEqual(module.check()[0]["status"], "invalid")

    def test_kugou_valid_and_expired(self):
        module = load("kugou")
        files = {"cookie": "userid=123; token=test; kg_mid=mid; kg_dfid=dfid"}
        with local_files(module, files):
            body, code = module.check(opener=lambda *_args, **_kwargs: Response({"status": 1}))
            self.assertEqual((body["status"], code), ("valid", 0))
            body, code = module.check(opener=lambda *_args, **_kwargs: Response({"status": 0, "error_code": 20017}))
            self.assertEqual((body["status"], code), ("expired", 1))

    def test_qishui_valid_and_expired(self):
        module = load("qishui")
        with local_files(module, {"cookie": "sessionid=test"}):
            body, code = module.check(opener=lambda *_args, **_kwargs: Response({"status_code": 0, "my_info": {"id": "1"}}))
            self.assertEqual((body["status"], code), ("valid", 0))
            body, code = module.check(opener=lambda *_args, **_kwargs: Response({"status_code": 0, "my_info": {}}))
            self.assertEqual((body["status"], code), ("expired", 1))

    def test_spotify_client_credentials(self):
        module = load("spotify")
        with patch.dict(os.environ, {"SPOTIFY_CLIENT_ID": "", "SPOTIFY_CLIENT_SECRET": "", "SPOTIFY_ACCESS_TOKEN": ""}, clear=False):
            with local_files(module, {"credentials": '{"client_id":"id","client_secret":"secret"}'}):
                body, code = module.check(opener=lambda *_args, **_kwargs: Response({"access_token": "issued"}))
                self.assertEqual((body["status"], code), ("valid", 0))

    def test_youtube_cookie_and_public_mode(self):
        module = load("youtube")
        with local_files(module):
            body, code = module.check()
            self.assertEqual((body["status"], body["publicUsable"], code), ("not_configured", True, 0))
        cookie = "# Netscape HTTP Cookie File\n#HttpOnly_.youtube.com\tTRUE\t/\tTRUE\t0\tSID\ttest\n"
        with local_files(module, {"cookies.txt": cookie}):
            body, code = module.check(opener=lambda *_args, **_kwargs: Response(b'{"LOGGED_IN":true}'))
            self.assertEqual((body["status"], code), ("valid", 0))


if __name__ == "__main__":
    unittest.main()
