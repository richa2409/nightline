from pydantic import BaseModel, EmailStr, Field


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    interests_text: str = Field(default="", max_length=1000)


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: str
    anon_handle: str
    interests_text: str

    class Config:
        from_attributes = True


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class InterestsUpdate(BaseModel):
    interests_text: str = Field(max_length=1000)


class MatchResult(BaseModel):
    room_id: str
    partner_handle: str
    match_score: float


class MessageOut(BaseModel):
    id: str
    sender_handle: str
    content: str
    created_at: str
