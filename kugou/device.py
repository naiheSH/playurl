"""Kugou device registration used by the standalone login flow."""
import base64
import hashlib
import json
import secrets
import string
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen

APPID = 1005
CLIENTVER = 20489
ANDROID_SALT = "OIlwieks28dk2k092lksi2UIkp"
UA = "Android15-1070-11083-46-0-DiscoveryDRADProtocol-wifi"
PUBLIC_KEY = b"""-----BEGIN PUBLIC KEY-----
MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQDIAG7QOELSYoIJvTFJhMpe1s/gbjDJX51HBNnEl5HXqTW6lQ7LC8jr9fWZTwusknp+sVGzwd40MwP6U5yDE27M/X1+UR4tvOGOqp94TJtQ1EPnWGWXngpeIW5GxoQGao1rmYWAu6oi1z9XkChrsUdC6DJE5E221wf/4WLFxwAtRQIDAQAB
-----END PUBLIC KEY-----"""


def md5(data):
    raw = data if isinstance(data, bytes) else str(data).encode()
    return hashlib.md5(raw).hexdigest()


def aes_material(seed):
    digest = md5(seed)
    return digest[:16].encode(), digest[16:32].encode()


def aes_encrypt(data, seed):
    try:
        from cryptography.hazmat.primitives import padding
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    except ImportError as exc:
        raise RuntimeError("酷狗设备注册缺少 cryptography，请安装同目录 requirements.txt") from exc
    key, iv = aes_material(seed)
    padder = padding.PKCS7(128).padder()
    padded = padder.update(data) + padder.finalize()
    encryptor = Cipher(algorithms.AES(key), modes.CBC(iv)).encryptor()
    return encryptor.update(padded) + encryptor.finalize()


def aes_decrypt(data, seed):
    from cryptography.hazmat.primitives import padding
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    key, iv = aes_material(seed)
    decryptor = Cipher(algorithms.AES(key), modes.CBC(iv)).decryptor()
    padded = decryptor.update(data) + decryptor.finalize()
    unpadder = padding.PKCS7(128).unpadder()
    return unpadder.update(padded) + unpadder.finalize()


def rsa_encrypt(data):
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import padding
    except ImportError as exc:
        raise RuntimeError("酷狗设备注册缺少 cryptography，请安装同目录 requirements.txt") from exc
    key = serialization.load_pem_public_key(PUBLIC_KEY)
    return key.encrypt(data, padding.PKCS1v15()).hex()


def signature(params, body):
    values = "".join(f"{key}={params[key]}" for key in sorted(params))
    return md5(ANDROID_SALT + values + body + ANDROID_SALT)


def register_device(userid, token, mid, guid, timeout=20):
    userid = int(userid)
    seed = "".join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(6))
    device = {
        "availableRamSize": 4983533568,
        "availableRomSize": 48114719,
        "availableSDSize": 48114717,
        "basebandVer": "",
        "batteryLevel": 100,
        "batteryStatus": 3,
        "brand": "Redmi",
        "buildSerial": "unknown",
        "device": "marble",
        "imei": guid,
        "imsi": "",
        "manufacturer": "Xiaomi",
        "uuid": guid,
        "accelerometer": False,
        "accelerometerValue": "",
        "gravity": False,
        "gravityValue": "",
        "gyroscope": False,
        "gyroscopeValue": "",
        "light": False,
        "lightValue": "",
        "magnetic": False,
        "magneticValue": "",
        "orientation": False,
        "orientationValue": "",
        "pressure": False,
        "pressureValue": "",
        "step_counter": False,
        "step_counterValue": "",
        "temperature": False,
        "temperatureValue": "",
    }
    plain = json.dumps(device, ensure_ascii=False, separators=(",", ":")).encode()
    body = base64.b64encode(aes_encrypt(plain, seed)).decode()
    portrait = json.dumps({"aes": seed, "uid": userid, "token": token}, separators=(",", ":")).encode()
    now = int(time.time())
    params = {
        "dfid": "-",
        "mid": str(mid),
        "uuid": "-",
        "appid": APPID,
        "clientver": CLIENTVER,
        "clienttime": now,
        "token": token,
        "userid": userid,
        "part": 1,
        "platid": 1,
        "p": rsa_encrypt(portrait),
    }
    params["signature"] = signature(params, body)
    request = Request(
        "https://userservice.kugou.com/risk/v2/r_register_dev?" + urlencode(params),
        data=body.encode(),
        method="POST",
        headers={
            "User-Agent": UA,
            "Content-Type": "application/x-www-form-urlencoded",
            "dfid": "-",
            "mid": str(mid),
            "clienttime": str(now),
            "kg-rc": "1",
            "kg-thash": "5d816a0",
            "kg-rec": "1",
            "kg-rf": "B9EDA08A64250DEFFBCADDEE00F8F25F",
        },
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            decoded = aes_decrypt(response.read(), seed)
            payload = json.loads(decoded.decode("utf-8"))
    except (OSError, ValueError, KeyError) as exc:
        raise RuntimeError("酷狗设备注册失败") from exc
    data = payload.get("data") if isinstance(payload, dict) else {}
    dfid = str((data or {}).get("dfid") or "").strip()
    if int(payload.get("status") or 0) != 1 or not dfid:
        raise RuntimeError("酷狗设备注册没有返回 dfid")
    return dfid
