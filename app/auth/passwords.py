from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerificationError


# 使用成熟库的 Argon2id 实现，随机盐由库生成并包含在哈希字符串中。
_password_hasher = PasswordHasher(type=Type.ID)


def hash_password(password: str) -> str:
    """生成用于保存的密码哈希，不保存明文密码。"""
    return _password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """密码错误或保存的哈希损坏时返回 False。"""
    try:
        return _password_hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False
