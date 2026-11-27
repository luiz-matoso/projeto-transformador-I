from pydantic import BaseModel, ConfigDict, Field, SecretStr


class LoginInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=1, max_length=200)
    password: SecretStr = Field(min_length=1, max_length=1024)


class TokenOutput(BaseModel):
    access_token: str
    token_type: str
    expires_in: int
