"""Gom toàn bộ router của API v1."""

from fastapi import APIRouter

from app.api.v1 import ai, auth, documents, folders, forms, payments, public_shares, versions

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(folders.router)
api_router.include_router(documents.router)
api_router.include_router(versions.router)
api_router.include_router(ai.router)
api_router.include_router(forms.router)
api_router.include_router(payments.router)
# Public share: prefix /public/... — không dependency CurrentUser (SRS)
api_router.include_router(public_shares.router)
