"""User API endpoints."""
from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import settings
from app.core.database import get_db
from app.models.user import User
from app.schemas.user import (
    UserCreate,
    UserUpdate,
    UserResponse,
    UserPreferences,
    Token,
    TokenData,
)

users_router = APIRouter()

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# OAuth2 scheme
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/users/token", auto_error=False)

# JWT settings
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 1 week


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Hash a password."""
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT access token."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.secret_key, algorithm=ALGORITHM)
    return encoded_jwt


async def get_current_user(
    token: Optional[str] = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> Optional[User]:
    """Get the current authenticated user, or None if not authenticated."""
    if not token:
        return None

    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            return None
    except JWTError:
        return None

    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def get_current_user_required(
    user: Optional[User] = Depends(get_current_user),
) -> User:
    """Require authentication."""
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


@users_router.post("/register", response_model=UserResponse)
async def register(
    user_create: UserCreate,
    db: AsyncSession = Depends(get_db),
):
    """Register a new user."""
    # Check if email exists
    result = await db.execute(select(User).where(User.email == user_create.email))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    # Create user
    db_user = User(
        email=user_create.email,
        password_hash=get_password_hash(user_create.password),
        name=user_create.name,
        preferences=user_create.preferences.model_dump() if user_create.preferences else {},
    )

    db.add(db_user)
    await db.commit()
    await db.refresh(db_user)

    return UserResponse(
        id=db_user.id,
        email=db_user.email,
        name=db_user.name,
        preferences=UserPreferences(**db_user.preferences),
        created_at=db_user.created_at,
        updated_at=db_user.updated_at,
    )


@users_router.post("/token", response_model=Token)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    """Login and get access token."""
    result = await db.execute(select(User).where(User.email == form_data.username))
    user = result.scalar_one_or_none()

    if not user or not user.password_hash or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": str(user.id)},
        expires_delta=access_token_expires,
    )

    return Token(
        access_token=access_token,
        token_type="bearer",
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@users_router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    user: User = Depends(get_current_user_required),
):
    """Get current user's profile."""
    return UserResponse(
        id=user.id,
        email=user.email,
        name=user.name,
        preferences=UserPreferences(**user.preferences),
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


@users_router.put("/me", response_model=UserResponse)
async def update_current_user(
    update: UserUpdate,
    user: User = Depends(get_current_user_required),
    db: AsyncSession = Depends(get_db),
):
    """Update current user's profile."""
    if update.name is not None:
        user.name = update.name

    if update.preferences is not None:
        user.preferences = update.preferences.model_dump()

    await db.commit()
    await db.refresh(user)

    return UserResponse(
        id=user.id,
        email=user.email,
        name=user.name,
        preferences=UserPreferences(**user.preferences),
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


@users_router.get("/preferences", response_model=UserPreferences)
async def get_preferences(
    user: Optional[User] = Depends(get_current_user),
):
    """Get user preferences (or defaults for anonymous users)."""
    if user:
        return UserPreferences(**user.preferences)
    else:
        return UserPreferences()


@users_router.put("/preferences", response_model=UserPreferences)
async def update_preferences(
    preferences: UserPreferences,
    user: User = Depends(get_current_user_required),
    db: AsyncSession = Depends(get_db),
):
    """Update user preferences."""
    user.preferences = preferences.model_dump()
    await db.commit()
    await db.refresh(user)

    return UserPreferences(**user.preferences)
