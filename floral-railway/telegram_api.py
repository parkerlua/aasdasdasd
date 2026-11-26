import json
from http.client import HTTPException, HTTPSConnection
from time import monotonic
from urllib.error import URLError
from uuid import uuid4


_connection = None
_sticker_sets = {}
STICKER_CACHE_SECONDS = 300
RETRYABLE_READS = {"getMe", "getStickerSet", "getUpdates"}


class TelegramError(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(f"Telegram API error {code}")


def telegram(token, method, **params):
    headers = {"Content-Type": "application/json"}
    photo = params.get("photo")
    if isinstance(photo, bytes):
        boundary = uuid4().hex
        headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
        parts = []
        for key, value in params.items():
            if key == "photo":
                parts.append(
                    f'--{boundary}\r\nContent-Disposition: form-data; name="photo"; filename="profile.png"\r\n'
                    "Content-Type: image/png\r\n\r\n".encode() + value + b"\r\n"
                )
            else:
                field = value if isinstance(value, str) else json.dumps(value)
                parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{field}\r\n'.encode())
        data = b"".join(parts) + f"--{boundary}--\r\n".encode()
    else:
        data = json.dumps(params).encode()
    cache_key = (token, params["name"]) if method == "getStickerSet" and set(params) == {"name"} else None
    if cache_key:
        cached = _sticker_sets.get(cache_key)
        if cached and monotonic() < cached[0]:
            return cached[1]

    result = request_telegram(token, method, data, headers)
    if cache_key:
        _sticker_sets[cache_key] = (monotonic() + STICKER_CACHE_SECONDS, result)
    return result


def request_telegram(token, method, data, headers):
    global _connection
    attempts = 2 if method in RETRYABLE_READS else 1
    for attempt in range(attempts):
        if _connection is None:
            _connection = HTTPSConnection("api.telegram.org", timeout=40)
        try:
            _connection.request("POST", f"/bot{token}/{method}", body=data, headers=headers)
            with _connection.getresponse() as response:
                status = response.status
                payload = response.read()
            break
        except (HTTPException, OSError) as error:
            _connection.close()
            _connection = None
            if attempt + 1 == attempts:
                raise URLError(type(error).__name__) from None
    try:
        response_data = json.loads(payload)
    except ValueError:
        if status >= 400:
            raise TelegramError(status) from None
        raise URLError("Invalid Telegram response") from None
    if status >= 400 or not response_data.get("ok"):
        raise TelegramError(response_data.get("error_code", status))
    return response_data["result"]
