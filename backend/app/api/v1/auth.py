import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.security.jwt import (
    create_access_token,
    create_refresh_token,
    decode_token,
)
from app.db.models.user import User
from app.db.session import get_db
from app.schemas.user_schema import (
    RefreshTokenRequest,
    Token,
    UserCreate,
    UserLogin,
    UserOut,
)
from app.services import user_service

router = APIRouter(prefix="/auth", tags=["认证"])


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(user_in: UserCreate, db: Session = Depends(get_db)):
    if user_service.get_user_by_username(db, user_in.username):
        raise HTTPException(status_code=400, detail="用户名已存在")
    user = user_service.create_user(db, user_in)
    return user


@router.post("/login", response_model=Token)
def login(user_in: UserLogin, db: Session = Depends(get_db)):
    # 故意不区分「用户不存在」与「密码错误」：分开提示等于给出了枚举有效用户名的途径
    user = user_service.authenticate_user(db, user_in.username, user_in.password)
    if not user:
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    access_token = create_access_token(user.user_id)
    refresh_token = create_refresh_token(user.user_id)
    return Token(access_token=access_token, refresh_token=refresh_token)


@router.get("/me", response_model=UserOut)
def read_me(current_user: User = Depends(get_current_user)):
    return current_user


@router.post("/refresh", response_model=Token)
def refresh(body: RefreshTokenRequest, db: Session = Depends(get_db)):
    try:
        payload = decode_token(body.refresh_token)
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="无效或过期的 Refresh Token")

    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Token 类型错误")

    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(status_code=401, detail="Token 缺少用户信息")

    user = db.query(User).filter(User.user_id == int(user_id)).first()
    if not user:
        raise HTTPException(status_code=401, detail="用户不存在")

    new_access = create_access_token(user.user_id)
    new_refresh = create_refresh_token(user.user_id)
    return Token(access_token=new_access, refresh_token=new_refresh)