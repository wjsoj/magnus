# back_end/server/routers/auth.py
import secrets
import logging
import jwt
import asyncio
import time
from typing import List, Optional, Dict
from dataclasses import dataclass

from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from .. import database
from .. import models
from ..schemas import UserInfo, LoginResponse, FeishuLoginRequest
from .._magnus_config import magnus_config
from .._jwt_signer import jwt_signer
from .._feishu_client import feishu_client


logger = logging.getLogger(__name__)
router = APIRouter()

# [Compatibility] auto_error=False allows us to handle missing headers manually 
# (e.g., checking query params or cookies)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/feishu/login", auto_error=False)


# === 1. Auth Cache Logic (Ported from services.py) ===

@dataclass
class CachedUser:
    id: str
    name: str
    token: str
    expires_at: float

_auth_cache: Dict[str, CachedUser] = {}
AUTH_CACHE_TTL = 60.0  # 1 minute cache

def _get_from_cache(token: str) -> Optional[str]:
    """Returns user_id if cached and valid"""
    if token in _auth_cache:
        cached = _auth_cache[token]
        if time.time() < cached.expires_at:
            return cached.id
        else:
            del _auth_cache[token]
    return None

def _add_to_cache(token: str, user: models.User):
    _auth_cache[token] = CachedUser(
        id=user.id,
        name=user.name,
        token=token,
        expires_at=time.time() + AUTH_CACHE_TTL
    )


# === 2. Core Logic ===

def generate_trust_token() -> str:
    return f"sk-{secrets.token_urlsafe(24)}"


def _upsert_feishu_user_sync(db: Session, feishu_user: dict) -> models.User:
    """同步处理飞书用户的创建或更新"""
    open_id = feishu_user.get("open_id") or feishu_user.get("union_id")
    if not open_id:
        raise HTTPException(status_code=400, detail="Missing OpenID")

    db_user = db.query(models.User).filter(models.User.feishu_open_id == open_id).first()

    if not db_user:
        db_user = models.User(
            feishu_open_id=open_id,
            name=feishu_user.get("name", "Unknown"),
            avatar_url=feishu_user.get("avatar_url"),
            email=feishu_user.get("email"),
            token=generate_trust_token(),
        )
        db.add(db_user)
        db.commit()
        db.refresh(db_user)
    else:
        db_user.name = feishu_user.get("name", db_user.name)
        db_user.avatar_url = feishu_user.get("avatar_url", db_user.avatar_url)
        if not db_user.token:
            db_user.token = generate_trust_token()
        db.commit()
        db.refresh(db_user)
    
    return db_user


def get_current_user(
    request: Request,
    token: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(database.get_db),
) -> models.User:
    """
    [Unified Auth Dependency]
    支持混合鉴权：
    1. Cache Check
    2. SDK Token Check (User.token)
    3. JWT Check (Web Token)
    4. Supports Header/Query/Cookie
    """
    
    # --- Step A: Extract Token String ---
    # 1. Try Authorization Header (via OAuth2 scheme)
    final_token = token

    # 2. Try Query Parameter (common for simple scripts/webhooks)
    if not final_token:
        final_token = request.query_params.get("token")

    # 3. Try Cookie (Fallback)
    if not final_token:
        final_token = request.cookies.get("access_token") or request.cookies.get("token")

    if not final_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # --- Step B: Verify Token (Mixed Mode) ---
    
    user_id_found = None
    
    # 1. Check Cache
    cached_id = _get_from_cache(final_token)
    if cached_id:
        user_id_found = cached_id
    
    # 2. Check DB Token (SDK Trust Token)
    if not user_id_found:
        # User.token is indexed usually, or should be. 
        # Checking this string is fast.
        user_by_token = db.query(models.User).filter(models.User.token == final_token).first()
        if user_by_token:
            user_id_found = user_by_token.id
            _add_to_cache(final_token, user_by_token)

    # 3. Check JWT (Web Session)
    if not user_id_found:
        try:
            payload = jwt.decode(
                final_token,
                magnus_config["server"]["jwt_signer"]["secret_key"],
                algorithms=[magnus_config["server"]["jwt_signer"]["algorithm"]],
            )
            user_id = payload.get("sub")
            if user_id:
                user_id_found = user_id
                # NOTE: We can optionally cache JWTs too, but JWT verification is fast enough.
                # Adding to cache here avoids repeated decoding.
                # We need a dummy user obj or just wait for the DB fetch below to cache it.
        except jwt.PyJWTError:
            pass

    # --- Step C: Finalize & Attach to Session ---
    
    if not user_id_found:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # [Crucial] Fetch User by ID to ensure it is attached to the current DB Session.
    # This prevents 'DetachedInstanceError' when Routers try to access lazy-loaded relationships (e.g. user.jobs).
    user = db.query(models.User).filter(models.User.id == user_id_found).first()
    
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    # Update cache if it was a JWT hit (now we have the full user object)
    if not cached_id:
        _add_to_cache(final_token, user)

    return user


# === 3. Routes ===

@router.post(
    "/auth/feishu/login",
    response_model=LoginResponse,
)
async def feishu_login(
    req: FeishuLoginRequest,
    db: Session = Depends(database.get_db),
):
    # 1. 异步 I/O: 获取飞书信息
    try:
        feishu_user = await feishu_client.get_feishu_user(req.code)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    # 2. 同步 I/O: 数据库 Upsert (移入线程池)
    db_user = await asyncio.to_thread(_upsert_feishu_user_sync, db, feishu_user)

    access_token = jwt_signer.create_access_token(payload={"sub": db_user.id})

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": db_user,
    }


@router.post(
    "/auth/token/refresh",
    response_model=UserInfo,
)
def refresh_trust_token(
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user),
):
    new_token = generate_trust_token()
    current_user.token = new_token

    db.commit()
    db.refresh(current_user)

    logger.info(f"User {current_user.id} ({current_user.name}) refreshed their trust token.")

    return current_user


@router.get(
    "/users",
    response_model=List[UserInfo],
)
def get_users(
    db: Session = Depends(database.get_db),
):
    users = db.query(models.User).order_by(models.User.name).all()
    return users