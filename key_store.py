"""Saves the user's Anthropic API key for the desktop app.

On Windows the key is encrypted with DPAPI, so only the same Windows user on the
same machine can read the file. Elsewhere (source checkouts on macOS/Linux) the
key is stored in a file readable only by the current user.

The key is never returned by the HTTP API and never written to the log.
"""

import base64
import ctypes
import os
import sys
from ctypes import wintypes
from pathlib import Path

from paths import user_data_dir

_KEY_FILE = "api_key.dat"


def _key_path() -> Path:
    return user_data_dir() / _KEY_FILE


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _blob_from_bytes(data: bytes):
    buf = ctypes.create_string_buffer(data, len(data))
    return _DataBlob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char))), buf


def _dpapi(data: bytes, protect: bool) -> bytes:
    in_blob, _keepalive = _blob_from_bytes(data)
    out_blob = _DataBlob()
    crypt32, kernel32 = ctypes.windll.crypt32, ctypes.windll.kernel32
    fn = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
    args = (ctypes.byref(in_blob), None, None, None, None, 0, ctypes.byref(out_blob))
    if not fn(*args):
        raise OSError("Windows data protection call failed")
    try:
        return ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        kernel32.LocalFree(out_blob.pbData)


def save_key(api_key: str) -> None:
    raw = api_key.strip().encode("utf-8")
    if sys.platform == "win32":
        payload = b"dpapi:" + base64.b64encode(_dpapi(raw, protect=True))
    else:
        payload = b"plain:" + base64.b64encode(raw)
    path = _key_path()
    path.write_bytes(payload)
    if sys.platform != "win32":
        os.chmod(path, 0o600)


def load_key() -> str:
    """Return the saved key, or "" if none is saved or it cannot be decrypted."""
    path = _key_path()
    if not path.exists():
        return ""
    try:
        scheme, _, body = path.read_bytes().partition(b":")
        raw = base64.b64decode(body)
        if scheme == b"dpapi" and sys.platform == "win32":
            raw = _dpapi(raw, protect=False)
        elif scheme != b"plain":
            return ""
        return raw.decode("utf-8").strip()
    except Exception:
        return ""


def delete_key() -> None:
    path = _key_path()
    if path.exists():
        path.unlink()
