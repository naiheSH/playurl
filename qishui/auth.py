"""Reusable, browser-free Qishui Passport QR authentication.

This module uses only the Python standard library.  It intentionally keeps
the HTTP session, cookies, device identity, throttling and MFA state together:

    client = QishuiAuthClient()
    login = client.create_qr_login()
    print(login.scan_url)
    result = login.poll()

Callers may render ``login.qr_png`` directly.  When ``result["mfa"]`` asks for
SMS verification, call ``login.send_mfa_sms()`` and then
``login.validate_mfa_sms(code)``.  On success ``login.cookie`` contains the
complete cookie string; treat it like a password.

Protocol behavior is derived from LuoYe17/ly-music-source, revision bcba7fb
(GPL-3.0-only).  See THIRD_PARTY_NOTICES.md.
"""

from __future__ import annotations

import base64
import http.cookiejar
import json
import os
import re
import secrets
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Mapping, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPCookieProcessor, Request, build_opener


QISHUI_API = "https://api.qishui.com"
QISHUI_AID = "386088"
QISHUI_VERSION = "3.5.2"
PASSPORT_JSSDK_VERSION = "2.4.13"
LUNA_UA = "LunaPC/3.5.2(412998333)"
BOOTSTRAP_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) SodaMusic/3.5.1 "
    "Chrome/136.0.7103.59 Electron/36.4.0-rs.29.release.main.0 "
    "TTElectron/36.4.0-rs.29.release.main.0 Safari/537.36"
)
SESSION_COOKIE_NAMES = {"sessionid", "sessionid_ss", "sid_guard", "sid_tt"}
VERIFY_PARAM_NAMES = {
    "passport_mfa_retry_tag",
    "std_verify_flow_id",
    "std_verify_scene",
    "std_verify_template",
    "std_verify_token",
    "std_verify_type",
    "std_verify_way",
}


class QishuiAuthError(RuntimeError):
    """Authentication or protocol failure with a stable category."""

    def __init__(self, message: str, category: str = "platform") -> None:
        super().__init__(message)
        self.category = category


def _random_digit_id(length: int = 16) -> str:
    value = "".join(str(secrets.randbelow(10)) for _ in range(length))
    if value[0] == "0":
        value = "3" + value[1:]
    return value


def _atomic_write(path: Path, data: bytes, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _normalize_key(value: str) -> str:
    return value.lower().replace("_", "").replace("-", "")


def _find_json_string(value: Any, field_name: str) -> str:
    wanted = _normalize_key(field_name)
    if isinstance(value, Mapping):
        for key, child in value.items():
            if _normalize_key(str(key)) == wanted and child is not None:
                if isinstance(child, (str, int, float)) and str(child).strip():
                    return str(child).strip()
            found = _find_json_string(child, field_name)
            if found:
                return found
    elif isinstance(value, list):
        for child in value:
            found = _find_json_string(child, field_name)
            if found:
                return found
    elif isinstance(value, str) and value.lstrip().startswith("{"):
        try:
            return _find_json_string(json.loads(value), field_name)
        except (TypeError, ValueError):
            pass
    return ""


def _collect_verify_params(value: Any, output: Dict[str, str]) -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            name = str(key)
            if name in VERIFY_PARAM_NAMES and child is not None and str(child).strip():
                output[name] = str(child).strip()
            _collect_verify_params(child, output)
        return
    if isinstance(value, list):
        for child in value:
            _collect_verify_params(child, output)
        return
    if not isinstance(value, str):
        return
    text = value.strip()
    if text.startswith("{"):
        try:
            _collect_verify_params(json.loads(text), output)
        except (TypeError, ValueError):
            pass
    if "std_verify_" in text or "passport_mfa_retry_tag" in text:
        query = text.split("?", 1)[-1]
        from urllib.parse import parse_qsl

        for key, item in parse_qsl(query, keep_blank_values=False):
            if key in VERIFY_PARAM_NAMES and item:
                output[key] = item


def mix_mode_encode(value: str) -> str:
    """Encode Passport mix_mode fields (UTF-8 byte XOR 0x05, hexadecimal)."""

    return bytes(byte ^ 0x05 for byte in value.encode("utf-8")).hex()


def decode_qr_png(value: Any) -> bytes:
    """Decode an upstream PNG data URL/base64 payload, or return ``b''``."""

    text = str(value or "").strip()
    if text.startswith("data:image/png;base64,"):
        text = text.split(",", 1)[1]
    if not text or not re.fullmatch(r"[A-Za-z0-9+/=\s]+", text):
        return b""
    try:
        payload = base64.b64decode(re.sub(r"\s+", "", text), validate=True)
    except (ValueError, TypeError):
        return b""
    return payload if payload.startswith(b"\x89PNG\r\n\x1a\n") else b""


@dataclass
class DeviceIdentity:
    device_id: str
    install_id: str
    biz_trace_id: str
    verify_portrait_id: str


@dataclass
class LoginState:
    status: str = "waiting"
    message: str = "等待扫码"
    last_poll_at: float = 0.0
    backoff_until: float = 0.0
    phone_confirmed: bool = False
    mfa: Dict[str, Any] = field(default_factory=dict)


class _CookieStore:
    def __init__(self) -> None:
        self.jar = http.cookiejar.CookieJar()
        self.values: Dict[str, str] = {}
        self.opener = build_opener(HTTPCookieProcessor(self.jar))

    def merge_response(self, headers: Any) -> None:
        lines = headers.get_all("Set-Cookie") if headers is not None else []
        for line in lines or []:
            pair = str(line).split(";", 1)[0]
            if "=" in pair:
                name, value = pair.split("=", 1)
                if name.strip() and value.strip():
                    self.values[name.strip()] = value.strip()
        for item in self.jar:
            if item.name and item.value:
                self.values[item.name] = item.value

    def header(self) -> str:
        return "; ".join(f"{key}={self.values[key]}" for key in sorted(self.values))

    def has_session(self) -> bool:
        return any(self.values.get(name) for name in SESSION_COOKIE_NAMES)


Transport = Callable[[str, str, Mapping[str, str], Optional[bytes], float, _CookieStore], Tuple[Any, Any]]


class QishuiAuthClient:
    """Factory for isolated Qishui QR-login sessions.

    ``transport`` is an optional test hook.  Production callers should omit it.
    """

    def __init__(
        self,
        timeout: float = 30.0,
        state_file: Optional[os.PathLike[str] | str] = None,
        transport: Optional[Transport] = None,
    ) -> None:
        self.timeout = max(5.0, float(timeout))
        self.state_file = Path(state_file) if state_file else Path(__file__).with_name(
            ".qishui-state"
        ) / "passport-device.json"
        self.transport = transport or self._network_transport
        self.identity = self._load_identity()
        self.global_backoff_until = 0.0

    def _load_identity(self) -> DeviceIdentity:
        try:
            parsed = json.loads(self.state_file.read_text("utf-8"))
        except (OSError, ValueError, TypeError):
            parsed = {}
        identity = DeviceIdentity(
            device_id=str(parsed.get("device_id") or _random_digit_id()),
            install_id=str(parsed.get("install_id") or _random_digit_id()),
            biz_trace_id=secrets.token_hex(4),
            verify_portrait_id=str(
                parsed.get("verify_portrait_id") or f"{uuid.uuid4()}.login"
            ),
        )
        payload = json.dumps(
            {
                "device_id": identity.device_id,
                "install_id": identity.install_id,
                "verify_portrait_id": identity.verify_portrait_id,
            },
            ensure_ascii=False,
            indent=2,
        ).encode()
        try:
            _atomic_write(self.state_file, payload, 0o600)
        except OSError:
            pass
        return identity

    @staticmethod
    def _network_transport(
        method: str,
        url: str,
        headers: Mapping[str, str],
        body: Optional[bytes],
        timeout: float,
        cookies: _CookieStore,
    ) -> Tuple[Any, Any]:
        request = Request(url, data=body, headers=dict(headers), method=method)
        try:
            with cookies.opener.open(request, timeout=timeout) as response:
                raw = response.read()
                cookies.merge_response(response.headers)
                try:
                    return json.loads(raw.decode("utf-8")), response.headers
                except (UnicodeDecodeError, ValueError) as exc:
                    raise QishuiAuthError("汽水接口返回了无效 JSON") from exc
        except HTTPError as exc:
            raw = exc.read().decode("utf-8", "replace")
            cookies.merge_response(exc.headers)
            raise QishuiAuthError(f"汽水接口 HTTP {exc.code}: {raw[:200]}", "network") from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise QishuiAuthError(f"汽水网络请求失败：{exc}", "network") from exc

    def _bootstrap_cookies(self, cookies: _CookieStore) -> None:
        body = json.dumps(
            {
                "region": "cn",
                "aid": int(QISHUI_AID),
                "needFid": False,
                "service": "www.qishui.com",
                "migrate_info": {"ticket": "", "source": "python"},
                "cbUrlProtocol": "https",
                "union": True,
            },
            separators=(",", ":"),
        ).encode()
        headers = {
            "User-Agent": BOOTSTRAP_UA,
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
            "Origin": "https://www.qishui.com",
            "Referer": "https://www.qishui.com/",
        }
        try:
            payload, _ = self.transport(
                "POST",
                "https://ttwid.bytedance.com/ttwid/union/register/",
                headers,
                body,
                self.timeout,
                cookies,
            )
            ttwid = (
                payload.get("ttwid")
                or (payload.get("data") or {}).get("ttwid")
                or ""
            ) if isinstance(payload, Mapping) else ""
            if ttwid:
                cookies.values.setdefault("ttwid", str(ttwid))
        except QishuiAuthError:
            # Warm-up is best effort; get_qrcode may still return the cookie.
            pass

    def _headers(self, cookies: _CookieStore) -> Dict[str, str]:
        headers = {
            "User-Agent": LUNA_UA,
            "Accept": "application/json, text/javascript",
            "Content-Type": "application/x-www-form-urlencoded",
            "Referer": "https://api.qishui.com/",
        }
        cookie = cookies.header()
        if cookie:
            headers["Cookie"] = cookie
        return headers

    def _create_query(self) -> str:
        return urlencode(
            [
                ("passport_jssdk_version", PASSPORT_JSSDK_VERSION),
                ("passport_jssdk_type", "normal"),
                ("is_from_ttaccountsdk", "1"),
                ("aid", QISHUI_AID),
                ("next", QISHUI_API),
                ("need_logo", "false"),
                ("need_short_url", "false"),
                ("is_new_login", "1"),
            ]
        )

    def _check_query(self) -> str:
        identity = self.identity
        return urlencode(
            [
                ("passport_jssdk_version", PASSPORT_JSSDK_VERSION),
                ("passport_jssdk_type", "normal"),
                ("is_from_ttaccountsdk", "1"),
                ("aid", QISHUI_AID),
                ("language", "zh"),
                ("account_sdk_source", "web"),
                ("device_id", identity.device_id),
                ("install_id", identity.install_id),
                ("did", identity.device_id),
                ("iid", identity.install_id),
                ("device_platform", "PC"),
                ("version_code", QISHUI_VERSION),
            ]
        )

    def _lite_query(self) -> str:
        identity = self.identity
        return urlencode(
            [
                ("aid", QISHUI_AID),
                ("passport_jssdk_version", "5.1.2"),
                ("passport_jssdk_type", "lite"),
                ("is_from_ttaccountsdk", "1"),
                ("language", "zh"),
                ("is_new_login", "1"),
                ("is_from_iesaccountsaas", "1"),
                ("device_id", identity.device_id),
                ("install_id", identity.install_id),
                ("did", identity.device_id),
                ("iid", identity.install_id),
                ("device_platform", "PC"),
                ("version_code", QISHUI_VERSION),
                ("new_authn_sdk_version", "1.0.0.404-web"),
                ("account_app_language", "zh-CN"),
            ]
        )

    def create_qr_login(self) -> "QishuiLoginSession":
        if self.global_backoff_until > time.monotonic():
            remaining = int(self.global_backoff_until - time.monotonic()) + 1
            raise QishuiAuthError(f"登录接口仍在冷却，请约 {remaining} 秒后重试", "rate_limit")
        self.identity.biz_trace_id = secrets.token_hex(4)
        cookies = _CookieStore()
        self._bootstrap_cookies(cookies)
        url = f"{QISHUI_API}/passport/web/get_qrcode/?{self._create_query()}"
        payload, _ = self.transport(
            "GET", url, self._headers(cookies), None, self.timeout, cookies
        )
        data = payload.get("data") or payload
        token = str(data.get("token") or "")
        scan_url = str(data.get("qrcode_index_url") or data.get("web_url") or "")
        error_code = int(data.get("error_code") or payload.get("error_code") or 0)
        if error_code and not token:
            raise QishuiAuthError(_error_message(payload, data, f"二维码创建失败：{error_code}"))
        if not token or not scan_url.startswith("https://bff-pc.qishui.com/"):
            raise QishuiAuthError("汽水没有返回有效的二维码会话")
        cookies.values.setdefault("passport_csrf_token", secrets.token_hex(16))
        cookies.values.setdefault(
            "passport_csrf_token_default", cookies.values["passport_csrf_token"]
        )
        return QishuiLoginSession(
            client=self,
            token=token,
            scan_url=scan_url,
            qr_png=decode_qr_png(data.get("qrcode")),
            expire_time=int(data.get("expire_time") or 0),
            _cookies=cookies,
        )


@dataclass
class QishuiLoginSession:
    client: QishuiAuthClient
    token: str
    scan_url: str
    qr_png: bytes = b""
    expire_time: int = 0
    state: LoginState = field(default_factory=LoginState)
    _cookies: _CookieStore = field(default_factory=_CookieStore, repr=False)

    @property
    def cookie(self) -> str:
        return self._cookies.header() if self._cookies.has_session() else ""

    @staticmethod
    def _check_body(token: str, extra: Optional[Mapping[str, str]] = None) -> bytes:
        values = [
            ("need_logo", "false"),
            ("need_short_url", "false"),
            ("is_frontier", "true"),
            ("token", token),
            ("is_new_login", "1"),
            ("next", QISHUI_API),
        ]
        for key, value in (extra or {}).items():
            if value is not None:
                values.append((str(key), str(value)))
        return urlencode(values).encode()

    def _session_result(self) -> Dict[str, Any]:
        return {
            "status": "confirmed",
            "message": "登录成功",
            "cookie": self.cookie,
            "mfa": self.state.mfa or None,
        }

    def _request_check(self, extra: Optional[Mapping[str, str]] = None) -> Tuple[Any, Any]:
        body = self._check_body(self.token, extra)
        url = f"{QISHUI_API}/passport/web/check_qrconnect/?{self.client._check_query()}"
        return self.client.transport(
            "POST",
            url,
            self.client._headers(self._cookies),
            body,
            self.client.timeout,
            self._cookies,
        )

    def poll(self, force: bool = False) -> Dict[str, Any]:
        now = time.monotonic()
        minimum = 6.0 if self.state.status == "scanned" else 7.5
        if not force and self.state.backoff_until > now:
            retry = int(self.state.backoff_until - now) + 1
            return {
                "status": self.state.status,
                "message": self.state.message,
                "mfa": self.state.mfa or None,
                "retryAfterSec": retry,
                "throttled": True,
            }
        if not force and self.state.last_poll_at and now - self.state.last_poll_at < minimum:
            retry = int(minimum - (now - self.state.last_poll_at)) + 1
            return {
                "status": self.state.status,
                "message": self.state.message,
                "mfa": self.state.mfa or None,
                "retryAfterSec": retry,
                "throttled": True,
            }
        self.state.last_poll_at = now
        payload, _ = self._request_check()
        data = payload.get("data") or {}
        if self._cookies.has_session():
            self.state.status = "confirmed"
            self.state.message = "登录成功"
            return self._session_result()

        raw_status = str(data.get("status") or "").lower()
        error_code = int(data.get("error_code") or payload.get("error_code") or 0)
        account_flow = str(data.get("account_flow") or "").lower()
        description = str(
            data.get("description") or payload.get("description") or payload.get("message") or ""
        )
        if (
            error_code in {7, 2156}
            or "太频繁" in description
            or "稍后再试" in description
            or "系统繁忙" in description
        ):
            self.state.backoff_until = now + 90.0
            self.client.global_backoff_until = self.state.backoff_until
            if self.state.phone_confirmed or self.state.status == "scanned" or "scan" in raw_status:
                self.state.status = "scanned"
            self.state.message = (
                "已扫码，登录接口正在冷却，请勿刷新"
                if self.state.status == "scanned"
                else "访问稍频繁，登录接口正在冷却"
            )
            return {
                "status": self.state.status,
                "message": self.state.message,
                "mfa": self.state.mfa or None,
                "retryAfterSec": 90,
                "throttled": True,
            }

        if account_flow == "verify" or error_code == 2046:
            self.state.phone_confirmed = True
            self.state.status = "scanned"
            self.state.mfa = _extract_mfa(payload, self._cookies.values)
            self.state.message = (
                "扫码已确认，平台要求短信二次验证"
                if self.state.mfa.get("needSms")
                else description or "扫码已确认，需要额外验证"
            )
            return {
                "status": "scanned",
                "message": self.state.message,
                "mfa": self.state.mfa,
            }

        if self.state.mfa.get("needSms"):
            return {
                "status": "scanned",
                "message": self.state.message or "请完成短信验证",
                "mfa": self.state.mfa,
            }

        if raw_status == "scanned" or "scan" in raw_status:
            self.state.status = "scanned"
            self.state.message = "已扫码，请在手机上确认"
            return {"status": "scanned", "message": self.state.message, "retryAfterSec": 6}

        if raw_status == "confirmed" or "confirm" in raw_status:
            self.state.phone_confirmed = True
            self.state.status = "scanned"
            self.state.message = "手机已确认，正在获取登录 Cookie"
            redirect_url = str(data.get("redirect_url") or data.get("redirect") or "")
            if redirect_url.startswith("http"):
                try:
                    self.client.transport(
                        "GET",
                        redirect_url,
                        self.client._headers(self._cookies),
                        None,
                        self.client.timeout,
                        self._cookies,
                    )
                except QishuiAuthError:
                    pass
                if self._cookies.has_session():
                    return self._session_result()
            return {"status": "scanned", "message": self.state.message, "retryAfterSec": 6}

        if raw_status in {"expired", "timeout", "cancel", "refuse"} or error_code == 5:
            self.state.status = "expired"
            self.state.message = description or "二维码已过期"
            return {"status": "expired", "message": self.state.message}
        if raw_status in {"error", "failed"}:
            self.state.status = "failed"
            self.state.message = description or f"登录失败（{error_code or raw_status}）"
            return {"status": "failed", "message": self.state.message}

        self.state.status = "waiting"
        self.state.message = (
            "等待扫码"
            if raw_status in {"", "new", "waiting", "wait"}
            else description or raw_status
        )
        return {"status": "waiting", "message": self.state.message}

    def send_mfa_sms(self) -> Dict[str, Any]:
        mfa = self.state.mfa
        encrypt_uid = str(mfa.get("encryptUid") or "")
        if not encrypt_uid:
            return {"ok": False, "message": "缺少短信验证参数 encrypt_uid，请重新扫码"}
        values = [
            ("mix_mode", "1"),
            ("type", mix_mode_encode("22")),
            ("encrypt_uid", encrypt_uid),
            ("verify_ticket", ""),
            ("copywriting_key", "qr_connect"),
            ("ies_safety_diversion_tag", "mfa"),
            ("new_verify_flow", ""),
        ]
        values.extend((key, value) for key, value in mfa.get("verifyParams", {}).items())
        values.extend(
            [
                ("std_verify_way", "mobile_sms_verify"),
                ("is6Digits", "1"),
                ("aid", QISHUI_AID),
                ("new_authn_sdk_version", "1.0.0.404-web"),
            ]
        )
        body = urlencode(_dedupe_pairs(values)).encode()
        headers = self.client._headers(self._cookies)
        headers["Accept"] = "application/json, text/plain, */*"
        csrf = self._cookies.values.get("passport_csrf_token") or self._cookies.values.get(
            "passport_csrf_token_default"
        )
        if csrf:
            headers["x-tt-passport-csrf-token"] = csrf
        url = f"{QISHUI_API}/passport/web/send_code/?{self.client._lite_query()}"
        payload, _ = self.client.transport(
            "POST", url, headers, body, self.client.timeout, self._cookies
        )
        data = payload.get("data") or {}
        error_code = int(data.get("error_code") or 0)
        mobile = str(data.get("mobile") or mfa.get("mobile") or "")
        if payload.get("message") == "success" or error_code == 0:
            message = f"验证码已发送至 {mobile}" if mobile else "验证码已发送"
            self.state.message = message
            return {
                "ok": True,
                "message": message,
                "mobile": mobile,
                "retryTime": int(data.get("retry_time") or 60),
            }
        return {"ok": False, "message": _error_message(payload, data, "验证码发送失败")}

    def validate_mfa_sms(self, code: str) -> Dict[str, Any]:
        digits = re.sub(r"\D", "", str(code))
        if not 4 <= len(digits) <= 8:
            return {"ok": False, "message": "验证码格式不正确"}
        mfa = self.state.mfa
        encrypt_uid = str(mfa.get("encryptUid") or "")
        if not encrypt_uid:
            return {"ok": False, "message": "缺少短信验证参数，请重新扫码"}
        values = [
            ("mix_mode", "1"),
            ("type", mix_mode_encode("22")),
            ("encrypt_uid", encrypt_uid),
            ("verify_ticket", ""),
            ("copywriting_key", "qr_connect"),
            ("ies_safety_diversion_tag", "mfa"),
            ("new_verify_flow", ""),
        ]
        values.extend((key, value) for key, value in mfa.get("verifyParams", {}).items())
        values.extend(
            [
                ("std_verify_way", "mobile_sms_verify"),
                ("code", mix_mode_encode(digits)),
                ("aid", QISHUI_AID),
                ("new_authn_sdk_version", "1.0.0.404-web"),
            ]
        )
        body = urlencode(_dedupe_pairs(values)).encode()
        headers = self.client._headers(self._cookies)
        headers["Accept"] = "application/json, text/plain, */*"
        csrf = self._cookies.values.get("passport_csrf_token") or self._cookies.values.get(
            "passport_csrf_token_default"
        )
        if csrf:
            headers["x-tt-passport-csrf-token"] = csrf
        url = f"{QISHUI_API}/passport/web/validate_code/?{self.client._lite_query()}"
        payload, _ = self.client.transport(
            "POST", url, headers, body, self.client.timeout, self._cookies
        )
        data = payload.get("data") or {}
        error_code = int(data.get("error_code") or 0)
        ticket = str(data.get("ticket") or "")
        if not ticket and payload.get("message") != "success" and error_code:
            return {"ok": False, "message": _error_message(payload, data, "验证码错误")}
        self._request_check(mfa.get("verifyParams", {}))
        if self._cookies.has_session():
            self.state.status = "confirmed"
            return {"ok": True, "message": "登录成功", **self._session_result()}
        polled = self.poll(force=True)
        if polled.get("status") == "confirmed":
            return {"ok": True, **polled}
        return {
            "ok": False,
            "message": polled.get("message") or "验证码已通过，但没有取得登录 Cookie",
        }

    def save_cookie(self, path: os.PathLike[str] | str) -> Path:
        if not self.cookie:
            raise QishuiAuthError("当前二维码会话还没有登录 Cookie")
        target = Path(path)
        _atomic_write(target, f"{self.cookie}\n".encode(), 0o600)
        return target


def _extract_mfa(payload: Any, cookies: Mapping[str, str]) -> Dict[str, Any]:
    verify_params: Dict[str, str] = {}
    _collect_verify_params(payload, verify_params)
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    encrypt_uid = _find_json_string(payload, "encrypt_uid")
    mobile = _find_json_string(payload, "mobile")
    up_mobile = _find_json_string(payload, "channel_mobile")
    up_content = _find_json_string(payload, "sms_content")
    has_sms_way = '"verify_way":"mobile_sms_verify"' in raw
    need_sms = bool(
        encrypt_uid
        or verify_params
        or cookies.get("passport_mfa_token")
        or has_sms_way
    )
    return {
        "needSms": need_sms,
        "encryptUid": encrypt_uid or None,
        "verifyParams": verify_params,
        "mobile": mobile or None,
        "upSmsMobile": up_mobile or None,
        "upSmsContent": up_content or None,
        "smsMode": "sms" if has_sms_way or encrypt_uid else ("up" if up_mobile or up_content else ""),
    }


def _dedupe_pairs(values: list[tuple[str, str]]) -> list[tuple[str, str]]:
    result: list[tuple[str, str]] = []
    positions: Dict[str, int] = {}
    for key, value in values:
        if key in positions:
            result[positions[key]] = (key, value)
        else:
            positions[key] = len(result)
            result.append((key, value))
    return result


def _error_message(payload: Mapping[str, Any], data: Mapping[str, Any], fallback: str) -> str:
    code = int(data.get("error_code") or payload.get("error_code") or 0)
    description = str(
        data.get("description") or payload.get("description") or payload.get("message") or ""
    ).strip()
    if code == 2156 or "系统繁忙" in description:
        return description or "系统繁忙（2156），请稍后重试"
    if code == 7 or "太频繁" in description or "稍后再试" in description:
        return description or "访问太频繁，请稍后重试"
    if description:
        return f"{description}（{code}）" if code else description
    return fallback


__all__ = [
    "QishuiAuthClient",
    "QishuiLoginSession",
    "QishuiAuthError",
    "decode_qr_png",
    "mix_mode_encode",
]
