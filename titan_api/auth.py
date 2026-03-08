"""
Titan Core - Authentication & Authorization
-------------------------------------------

Purpose:
    Handles password hashing, JWT creation, and
    authenticated user retrieval for protected endpoints.

Role in Architecture:
    - Issues signed JWT tokens
    - Validates incoming tokens
    - Retrieves authenticated user from database
    - Provides dependency injection for protected routes

Security Notes:
    - Uses bcrypt for password hashing
    - JWT tokens expire after 12 hours
    - SECRET must be set via environment variable in production
    - Default secret is development-only

Author:
    Ron Wiley
Project:
    Titan AI - Operational Personnel Assistant
"""

import os
import jwt
from datetime import datetime, timedelta
from typing import Optional

from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from .db import get_db
from .models import User


# ---------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------

SECRET = os.getenv("JWT_SECRET", "dev-secret-change-me")
ALGORITHM = "HS256"
TOKEN_EXP_HOURS = 12

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/login")


# ---------------------------------------------------------------------
# Password Utilities
# ---------------------------------------------------------------------

def hash_password(password: str) -> str:
    """Hash plain-text password using bcrypt."""
    return pwd_context.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    """Verify password against stored bcrypt hash."""
    return pwd_context.verify(password, hashed)


# ---------------------------------------------------------------------
# Token Creation
# ---------------------------------------------------------------------

def create_access_token(user: User) -> str:
    """
    Create signed JWT token containing:
        - user id (sub)
        - role
        - expiration
    """

    expiration = datetime.utcnow() + timedelta(hours=TOKEN_EXP_HOURS)

    payload = {
        "sub": str(user.id),
        "role": user.role,
        "exp": expiration,
    }

    return jwt.encode(payload, SECRET, algorithm=ALGORITHM)


# ---------------------------------------------------------------------
# Current Authenticated User Dependency
# ---------------------------------------------------------------------

def get_current_user(
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme),
) -> User:
    """
    FastAPI dependency for retrieving authenticated user.

    Raises:
        401 if token invalid or user not found.
    """

    try:
        payload = jwt.decode(token, SECRET, algorithms=[ALGORITHM])
        user_id: Optional[str] = payload.get("sub")

        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token missing subject",
            )

        user_id = int(user_id)

    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expired",
        )

    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )

    user = db.query(User).filter(User.id == user_id).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    return user