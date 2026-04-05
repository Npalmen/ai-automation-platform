from pydantic import BaseModel


class IntegrationConnectionConfig(BaseModel):
    enabled: bool = False
    connected: bool = False
    account_name: str | None = None