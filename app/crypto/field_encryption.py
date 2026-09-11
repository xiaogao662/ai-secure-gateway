import secrets

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class ContentAccessError(Exception):
    """已通过授权但无法提供正文；只携带固定错误代号，不携带秘密。"""

    def __init__(self, reason_code: str):
        self.reason_code = reason_code
        super().__init__(reason_code)


def associated_data(application_id: int, owner_id: int) -> bytes:
    # AAD 不加密，但参加完整性校验；把密文绑定到记录、归属和字段版本。
    return f"ai-secure:personal-statement:v1:{application_id}:{owner_id}".encode("ascii")


class FieldEncryption:
    def __init__(self, key: bytes):
        if not isinstance(key, bytes) or len(key) != 32:
            raise ValueError("AES-256-GCM requires a 32-byte key")
        self._cipher = AESGCM(key)

    def encrypt(self, plaintext: str, *, application_id: int, owner_id: int) -> tuple[bytes, bytes]:
        # 每次重新生成 96 位随机 nonce；同一密钥下不得复用。
        nonce = secrets.token_bytes(12)
        ciphertext = self._cipher.encrypt(
            nonce, plaintext.encode("utf-8"), associated_data(application_id, owner_id),
        )
        return nonce, ciphertext

    def decrypt(self, nonce: bytes, ciphertext: bytes, *, application_id: int, owner_id: int) -> str:
        try:
            if len(nonce) != 12:
                raise ValueError("Invalid nonce length")
            plaintext = self._cipher.decrypt(nonce, ciphertext, associated_data(application_id, owner_id))
            return plaintext.decode("utf-8")
        except (InvalidTag, ValueError) as error:
            # 密钥、nonce、AAD 错误或密文篡改都不会返回部分正文。
            raise ContentAccessError("DECRYPTION_FAILED") from error
