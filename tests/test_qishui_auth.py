import base64
import importlib.util
import os
import stat
import sys
import tempfile
import unittest
from email.message import Message
from pathlib import Path
from urllib.parse import parse_qs


LOCAL_MODULE = Path(__file__).with_name("auth.py")
MODULE_PATH = (
    LOCAL_MODULE
    if LOCAL_MODULE.exists()
    else Path(__file__).resolve().parents[1] / "qishui" / "auth.py"
)
SPEC = importlib.util.spec_from_file_location("qishui_auth_test_module", MODULE_PATH)
AUTH = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = AUTH
SPEC.loader.exec_module(AUTH)

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


class FakeTransport:
    def __init__(self, mfa=False):
        self.calls = []
        self.mfa = mfa
        self.checks = 0

    def __call__(self, method, url, headers, body, timeout, cookies):
        self.calls.append((method, url, dict(headers), body))
        response_headers = Message()
        if "ttwid/union/register" in url:
            return {"ttwid": "test-ttwid"}, response_headers
        if "/get_qrcode/" in url:
            return {
                "data": {
                    "token": "test-token",
                    "qrcode_index_url": "https://bff-pc.qishui.com/test",
                    "qrcode": "data:image/png;base64," + base64.b64encode(PNG).decode(),
                    "expire_time": 120,
                }
            }, response_headers
        if "/send_code/" in url:
            return {"message": "success", "data": {"error_code": 0, "mobile": "138****0000"}}, response_headers
        if "/validate_code/" in url:
            return {"message": "success", "data": {"error_code": 0, "ticket": "ticket"}}, response_headers
        if "/check_qrconnect/" in url:
            self.checks += 1
            if self.mfa and self.checks == 1:
                return {
                    "data": {
                        "account_flow": "verify",
                        "error_code": 2046,
                        "verify_data": {
                            "encrypt_uid": "encrypted-user",
                            "verify_way": "mobile_sms_verify",
                            "std_verify_token": "verify-token",
                        },
                    }
                }, response_headers
            if self.mfa and self.checks >= 2:
                cookies.values["sessionid"] = "secret-session"
                return {"data": {"status": "confirmed"}}, response_headers
            return {"data": {"status": "new", "error_code": 0}}, response_headers
        raise AssertionError(f"unexpected URL: {url}")


class QishuiAuthTests(unittest.TestCase):
    def make_client(self, transport, directory):
        return AUTH.QishuiAuthClient(
            state_file=Path(directory) / "device.json",
            transport=transport,
        )

    def test_mix_mode_and_png_decode(self):
        self.assertEqual(AUTH.mix_mode_encode("24"), "3731")
        self.assertEqual(AUTH.mix_mode_encode("22"), "3737")
        encoded = "data:image/png;base64," + base64.b64encode(PNG).decode()
        self.assertEqual(AUTH.decode_qr_png(encoded), PNG)

    def test_create_and_waiting_poll_use_pc_profile(self):
        with tempfile.TemporaryDirectory() as directory:
            transport = FakeTransport()
            login = self.make_client(transport, directory).create_qr_login()
            self.assertEqual(login.qr_png, PNG)
            self.assertEqual(login.scan_url, "https://bff-pc.qishui.com/test")
            result = login.poll()
            self.assertEqual(result["status"], "waiting")
            create_call = next(call for call in transport.calls if "/get_qrcode/" in call[1])
            self.assertNotIn("a_bogus", create_call[1])
            self.assertTrue(create_call[2]["User-Agent"].startswith("LunaPC/"))
            self.assertIn("ttwid=test-ttwid", create_call[2]["Cookie"])

    def test_mfa_flow_and_private_cookie_save(self):
        with tempfile.TemporaryDirectory() as directory:
            transport = FakeTransport(mfa=True)
            login = self.make_client(transport, directory).create_qr_login()
            polled = login.poll()
            self.assertEqual(polled["status"], "scanned")
            self.assertTrue(polled["mfa"]["needSms"])
            self.assertEqual(polled["mfa"]["encryptUid"], "encrypted-user")
            sent = login.send_mfa_sms()
            self.assertTrue(sent["ok"])
            verified = login.validate_mfa_sms("123456")
            self.assertTrue(verified["ok"])
            target = Path(directory) / "cookie"
            login.save_cookie(target)
            self.assertIn("sessionid=secret-session", target.read_text())
            if os.name != "nt":
                self.assertEqual(stat.S_IMODE(os.stat(target).st_mode), 0o600)
            validate_call = next(call for call in transport.calls if "/validate_code/" in call[1])
            form = parse_qs(validate_call[3].decode())
            self.assertEqual(form["code"], [AUTH.mix_mode_encode("123456")])
            self.assertEqual(form["std_verify_token"], ["verify-token"])


if __name__ == "__main__":
    unittest.main()
