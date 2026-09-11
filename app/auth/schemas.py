from pydantic import BaseModel, ConfigDict, Field, SecretStr


class LoginRequest(BaseModel):
    # 拒绝额外的 role/user_id 等字段，也不把数字等自动转换为字符串。
    model_config = ConfigDict(extra="forbid", strict=True)

    username: str = Field(min_length=1, max_length=50)
    password: SecretStr = Field(min_length=1, max_length=128)


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    role: str
