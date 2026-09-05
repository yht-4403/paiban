from pydantic import BaseModel, Field


class Credentials(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=128)


class Registration(Credentials):
    name: str = Field(min_length=1, max_length=40)
    workspace: str = Field(default='', max_length=80)
    invite: str = Field(default='', max_length=100)


class FixedAccountSelection(BaseModel):
    account_id: str = Field(min_length=1, max_length=80)
