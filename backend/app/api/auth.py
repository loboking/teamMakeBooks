"""인증 API — register / login / logout / me."""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel

from ..db import get_db_path

router = APIRouter(prefix="/auth", tags=["auth"])
_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
_bearer = HTTPBearer(auto_error=False)

JWT_SECRET = os.getenv("JWT_SECRET", "changeme-secret")
JWT_ALG = "HS256"
JWT_EXP_HOURS = 24 * 7  # 7일


class RegisterBody(BaseModel):
    email: str
    password: str


class LoginBody(BaseModel):
    email: str
    password: str


def _make_token(user_id: int) -> str:
    exp = datetime.now(timezone.utc) + timedelta(hours=JWT_EXP_HOURS)
    return jwt.encode({"sub": str(user_id), "exp": exp}, JWT_SECRET, algorithm=JWT_ALG)


async def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> dict:
    if not creds:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(creds.credentials, JWT_SECRET, algorithms=[JWT_ALG])
        user_id = int(payload["sub"])
    except (JWTError, KeyError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid token")

    async with aiosqlite.connect(get_db_path()) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT id, email, created_at FROM users WHERE id=?", (user_id,)) as cur:
            row = await cur.fetchone()
    if not row:
        raise HTTPException(status_code=401, detail="User not found")
    return dict(row)


@router.post("/register", status_code=201)
async def register(body: RegisterBody):
    pw_hash = _pwd.hash(body.password)
    try:
        async with aiosqlite.connect(get_db_path()) as db:
            cur = await db.execute(
                "INSERT INTO users (email, password_hash) VALUES (?, ?)",
                (body.email, pw_hash),
            )
            await db.commit()
            user_id = cur.lastrowid
    except Exception:
        raise HTTPException(status_code=409, detail="Email already exists")
    return {"token": _make_token(user_id), "user_id": user_id, "email": body.email}


@router.post("/login")
async def login(body: LoginBody):
    async with aiosqlite.connect(get_db_path()) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT id, password_hash FROM users WHERE email=?", (body.email,)) as cur:
            row = await cur.fetchone()
    if not row or not _pwd.verify(body.password, row["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return {"token": _make_token(row["id"]), "user_id": row["id"], "email": body.email}


@router.post("/logout")
async def logout():
    # JWT는 stateless — 클라이언트가 토큰 삭제
    return {"ok": True}


@router.get("/me")
async def me(user: dict = Depends(get_current_user)):
    return user
