from datetime import date

from fastapi import UploadFile, Form, File
from pydantic import BaseModel, field_validator

from validation import (
    validate_name,
    validate_image,
    validate_gender,
    validate_birth_date
)


class ProfileSchema(BaseModel):
    first_name: str
    last_name: str
    gender: str
    date_of_birth: date
    info: str

    @field_validator("first_name")
    @classmethod
    def check_first_name(cls, v):
        validate_name(v)
        return v

    @field_validator("last_name")
    @classmethod
    def check_last_name(cls, v):
        validate_name(v)
        return v

    @field_validator("gender")
    @classmethod
    def check_gender(cls, v):
        validate_gender(v)
        return v

    @field_validator("date_of_birth")
    @classmethod
    def check_birth_date(cls, v):
        validate_birth_date(v)
        return v

    @field_validator("info")
    @classmethod
    def check_info(cls, v):
        if not v.strip():
            raise ValueError("Info cannot be empty")
        return v


async def profile_schema(
        first_name: str = Form(...),
        last_name: str = Form(...),
        gender: str = Form(...),
        date_of_birth: date = Form(...),
        info: str = Form(...),
        avatar: UploadFile = File(...)
):
    profile = ProfileSchema(
        first_name=first_name,
        last_name=last_name,
        gender=gender,
        date_of_birth=date_of_birth,
        info=info
    )

    validate_image(avatar)

    return profile, avatar


class ProfileResponseSchema(BaseModel):
    id: int
    first_name: str
    last_name: str
    gender: str
    date_of_birth: date
    info: str
    avatar: str
