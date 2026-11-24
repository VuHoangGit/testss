"""The `users` table — local profile; identity managed by Supabase Auth.

The join key is `supabase_id` (the `sub` claim of the Supabase access token,
UNIQUE, nullable). Email is NOT unique: the first Supabase sign-in matches an
existing user by email to preserve their documents/folders. The
`google_sub`/`password_hash` columns remain in the historical DB but are no
longer used — auth moved entirely to Supabase.
"""

import uuid
from datetime import datetime

from sqlalchemy import String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UTCDateTime


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    # UNIQUE on a nullable column: multiple NULLs are valid (PG + SQLite) — intended
    supabase_id: Mapped[str | None] = mapped_column(String(64), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(320), index=True)
    name: Mapped[str | None] = mapped_column(String(255), default=None)
    # NULL = the user has not personally chosen a display name yet → the app
    # shows the name-entry screen right after the first sign-in (Google and
    # email alike). A value = chosen, so never ask again, and the name inside
    # the Google token is never overwritten afterwards.
    name_chosen_at: Mapped[datetime | None] = mapped_column(
        UTCDateTime, default=None
    )
    avatar_url: Mapped[str | None] = mapped_column(Text, default=None)
    # AI credits: `credit_free` is the remaining monthly quota of the current
    # plan (lazily reset each "YYYY-MM" period tracked in `credit_period`);
    # `credit_purchased` are legacy prepaid credits — never expire and are
    # spent only after the monthly quota runs out.
    credit_free: Mapped[int] = mapped_column(default=300)
    credit_purchased: Mapped[int] = mapped_column(default=0)
    credit_period: Mapped[str] = mapped_column(String(7), default="")
    # Subscription plan (FREE | PLUS | PRO | MAX), valid until
    # plan_expires_at. Expired plans degrade to FREE at read time — no
    # background job needed. MAX is fair-use unlimited.
    plan_code: Mapped[str] = mapped_column(String(16), default="FREE")
    plan_expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )
