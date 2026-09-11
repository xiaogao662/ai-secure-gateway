import base64
import binascii
import os
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


KEY_FILE = Path(__file__).resolve().parents[2] / ".secrets" / "application.key"
KEY_ENVIRONMENT_VARIABLE = "AI_SECURE_DATA_KEY"


class KeyConfigurationError(Exception):
    pass


def decode_key(encoded: str) -> bytes:
    try:
        key = base64.b64decode(encoded.strip(), validate=True)
    except (ValueError, binascii.Error):
        raise KeyConfigurationError("Encryption key must be Base64 for exactly 32 bytes") from None
    if len(key) != 32:
        raise KeyConfigurationError("Encryption key must be Base64 for exactly 32 bytes")
    return key


def load_configured_key(key_file: Path = KEY_FILE) -> bytes | None:
    """显式环境变量优先，格式错误不降级为另一把密钥；不生成或打印密钥。"""
    encoded = os.environ.get(KEY_ENVIRONMENT_VARIABLE)
    if encoded is not None:
        return decode_key(encoded)
    if key_file.exists():
        return decode_key(key_file.read_text(encoding="ascii"))
    return None


def create_local_key(key_file: Path = KEY_FILE) -> bytes:
    """只供显式初始化使用；独占创建文件，已有文件永不覆盖。"""
    key_file.parent.mkdir(parents=True, exist_ok=True)
    key = AESGCM.generate_key(bit_length=256)
    try:
        descriptor = os.open(key_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return decode_key(key_file.read_text(encoding="ascii"))
    with os.fdopen(descriptor, "w", encoding="ascii") as output:
        output.write(base64.b64encode(key).decode("ascii") + "\n")
    return key
