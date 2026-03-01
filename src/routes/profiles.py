from datetime import datetime, timezone, date

from fastapi import APIRouter, status, Depends, HTTPException, Header, Form, UploadFile, File
from sqlalchemy import select, cast
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_s3_storage_client
from database import UserModel, RefreshTokenModel, UserGroupEnum, UserProfileModel
from database import get_db
from schemas.profiles import ProfileResponseSchema, profile_sсhema, ProfileSchema
from storages import S3StorageInterface
from validation import validate_image

router = APIRouter()


async def get_current_user(authorization: str = Header(None), db: AsyncSession = Depends(get_db)):
    if not authorization:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authorization header is missing")

    bearer = authorization.split()[0]
    if bearer != "Bearer" or len(bearer) != 2:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Authorization header format. Expected 'Bearer <token>'")

    stmt = select(RefreshTokenModel).where(RefreshTokenModel.token == bearer[1])
    result = await db.execute(stmt)
    token_result = result.scalars().first()

    now_utc = datetime.now(timezone.utc)
    if not token_result or cast(datetime, token_result.expires_at).replace(tzinfo=timezone.utc) < now_utc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired."
        )

    stmt = select(UserModel).where(UserModel.id == token_result.user_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or not active."
        )

    return user



@router.post(
    "/users/{user_id}/profile/",
    response_model=ProfileResponseSchema,
    status_code=status.HTTP_201_CREATED,
    responses={
        401: {
            "description": "Unauthorized",
            "content": {
                "application/json": {
                    "examples": {
                        "missing_token": {
                            "summary": "Authorization header is missing",
                            "value": {"detail": "Authorization header is missing"}
                        },
                        "invalid_token": {
                            "summary": "Invalid Authorization header format. Expected 'Bearer <token>'",
                            "value": {"detail": "Invalid Authorization header format. Expected 'Bearer <token>'"}
                        },
                        "expired_token": {
                            "summary": "Token has expired.",
                            "value": {"detail": "Token has expired."}
                        },
                        "user_created_expired": {
                            "summary": "User not found or not active.",
                            "value": {"detail": "User not found or not active."}
                        },
                    },
                }
            }
        },
        403: {
            "description": "Forbidden",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "You don't have permission to edit this profile.",
                    }
                }
            }
        },
        400: {
            "description": "Bad Request",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "User already has a profile.",
                    }
                }
            }
        },
        500: {
            "description": "Failed",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Failed to upload avatar. Please try again later.",
                    }
                }
            }
        },
    }
)
async def create_user(
        user_id: int,
        current_user: UserModel = Depends(get_current_user),
        first_name: str = Form(...),
        last_name: str = Form(...),
        gender: str = Form(...),
        date_of_birth: date = Form(...),
        info: str = Form(...),
        avatar: UploadFile = File(...),
        data = Depends(profile_sсhema),
        db: AsyncSession = Depends(get_db),
        s3_client: S3StorageInterface = Depends(get_s3_storage_client),
):
    if current_user.id != user_id and not current_user.has_group(UserGroupEnum.ADMIN):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to edit this profile."
        )

    stmt = select(UserModel).where(UserModel.id == user_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or not active."
        )

    if user.profile:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User already has a profile."
        )

    profile_data = ProfileSchema(
        first_name=first_name,
        last_name=last_name,
        gender=gender,
        date_of_birth=date_of_birth,
        info=info
    )

    validate_image(avatar)
    try:
        file_name = f"{user_id}_avatar.jpg"
        avatar_url = await s3_client.upload_file(
            file=avatar.file,
            file_name=file_name,
            content_type=avatar.content_type,
        )
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to upload avatar. Please try again later."
        )

    new_profile = UserProfileModel(
        user_id=user_id,
        first_name=profile_data.first_name,
        last_name=profile_data.last_name,
        gender=profile_data.gender,
        date_of_birth=profile_data.date_of_birth,
        info=profile_data.info,
        avatar=avatar_url,
    )

    db.add(new_profile)
    await db.commit()
    await db.refresh(new_profile)

    return new_profile
