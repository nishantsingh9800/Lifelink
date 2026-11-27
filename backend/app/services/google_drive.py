import json
import time
from pathlib import Path
from typing import Optional

import httpx
import jwt


def _get_drive_access_token(service_account_file: str) -> str:
    """Exchange a Google Service Account JWT for a Drive OAuth2 access token."""
    creds = json.loads(Path(service_account_file).read_text(encoding="utf-8"))
    now = int(time.time())
    assertion = jwt.encode(
        {
            "iss": creds["client_email"],
            "scope": "https://www.googleapis.com/auth/drive.file",
            "aud": creds.get("token_uri", "https://oauth2.googleapis.com/token"),
            "iat": now,
            "exp": now + 3600,
        },
        creds["private_key"],
        algorithm="RS256",
    )
    resp = httpx.post(
        creds.get("token_uri", "https://oauth2.googleapis.com/token"),
        data={
            "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
            "assertion": assertion,
        },
        timeout=20.0,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def upload_bytes_to_drive_folder(
    *,
    service_account_file: str,
    folder_id: str,
    filename: str,
    content_bytes: bytes,
    content_type: str,
) -> str:
    """Upload bytes into the configured Google Drive folder and return the Drive file ID."""
    token = _get_drive_access_token(service_account_file)
    boundary = "lifelink_drive_multipart_boundary"
    metadata = json.dumps({"name": filename, "parents": [folder_id]}).encode("utf-8")

    body = (
        f"--{boundary}\r\n"
        f"Content-Type: application/json; charset=UTF-8\r\n\r\n"
    ).encode("utf-8") + metadata + (
        f"\r\n--{boundary}\r\n"
        f"Content-Type: {content_type}\r\n\r\n"
    ).encode("utf-8") + content_bytes + f"\r\n--{boundary}--\r\n".encode("utf-8")

    resp = httpx.post(
        "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart&fields=id",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": f"multipart/related; boundary={boundary}",
        },
        content=body,
        timeout=30.0,
    )
    resp.raise_for_status()
    return resp.json()["id"]


def download_bytes_from_drive(*, service_account_file: str, file_id: str) -> Optional[bytes]:
    """Download file bytes from Google Drive by file ID."""
    token = _get_drive_access_token(service_account_file)
    resp = httpx.get(
        f"https://www.googleapis.com/drive/v3/files/{file_id}?alt=media",
        headers={"Authorization": f"Bearer {token}"},
        timeout=30.0,
    )
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.content
