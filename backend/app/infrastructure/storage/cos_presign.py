from __future__ import annotations

import hashlib
import hmac
import time
from dataclasses import dataclass
from urllib.parse import quote, urlparse


@dataclass(frozen=True)
class PresignedUpload:
    url: str
    headers: dict[str, str]


def create_cos_put_presign(
    *,
    endpoint: str,
    bucket: str,
    object_key: str,
    content_type: str,
    expires_in: int,
    secret_id: str | None,
    secret_key: str | None,
) -> PresignedUpload:
    url = _build_object_url(endpoint=endpoint, bucket=bucket, object_key=object_key)
    headers = {"Content-Type": content_type}
    if secret_id and secret_key:
        headers["Authorization"] = _create_cos_authorization(
            method="put",
            url=url,
            secret_id=secret_id,
            secret_key=secret_key,
            expires_in=expires_in,
        )
    return PresignedUpload(url=url, headers=headers)


def _create_cos_authorization(
    *,
    method: str,
    url: str,
    secret_id: str,
    secret_key: str,
    expires_in: int,
) -> str:
    parsed = urlparse(url)
    now = int(time.time())
    key_time = f"{now};{now + expires_in}"
    sign_key = hmac.new(
        secret_key.encode("utf-8"),
        key_time.encode("utf-8"),
        hashlib.sha1,
    ).hexdigest()

    path = parsed.path or "/"
    host = parsed.netloc
    header_list = "host"
    http_string = f"{method.lower()}\n{path}\n\nhost={host}\n"
    string_to_sign = (
        "sha1\n"
        f"{key_time}\n"
        f"{hashlib.sha1(http_string.encode('utf-8')).hexdigest()}\n"
    )
    signature = hmac.new(
        sign_key.encode("utf-8"),
        string_to_sign.encode("utf-8"),
        hashlib.sha1,
    ).hexdigest()
    return (
        "q-sign-algorithm=sha1"
        f"&q-ak={secret_id}"
        f"&q-sign-time={key_time}"
        f"&q-key-time={key_time}"
        f"&q-header-list={header_list}"
        "&q-url-param-list="
        f"&q-signature={signature}"
    )


def _build_object_url(*, endpoint: str, bucket: str, object_key: str) -> str:
    endpoint = endpoint.rstrip("/")
    quoted_key = "/".join(quote(part) for part in object_key.split("/"))
    host_contains_bucket = f"//{bucket}." in endpoint or endpoint.endswith(f"/{bucket}")
    if host_contains_bucket:
        return f"{endpoint}/{quoted_key}"
    return f"{endpoint}/{bucket}/{quoted_key}"
