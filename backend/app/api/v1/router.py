"""Gom toàn bộ router của API v1."""

from fastapi import APIRouter

from app.api.v1 import auth, documents, folders

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(folders.router)
api_router.include_router(documents.router)
