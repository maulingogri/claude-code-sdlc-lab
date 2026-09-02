import datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    phone: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)
    language: Mapped[str | None] = mapped_column(String(2), nullable=True)  # "en" | "gu"
    broadcast_opt_in: Mapped[bool] = mapped_column(Boolean, default=False)
    personal_opt_in: Mapped[bool] = mapped_column(Boolean, default=False)
    public_recognition_optin: Mapped[bool] = mapped_column(Boolean, default=False)
    # Not in the CLAUDE.md schema; added because the daily broadcast needs a
    # name to display for users who opt into fasting recognition.
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    onboarding_step: Mapped[str] = mapped_column(String(64), default="greeting")
    # Tracks an in-progress multi-turn post-onboarding conversation (logging a
    # fast, a reflection, or a forgiveness-list entry). None means idle.
    active_flow: Mapped[str | None] = mapped_column(String(64), nullable=True)
    timezone: Mapped[str] = mapped_column(String(64), default="America/New_York")
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.utcnow
    )

    fasting_logs: Mapped[list["FastingLog"]] = relationship(back_populates="user")
    reflections: Mapped[list["Reflection"]] = relationship(back_populates="user")
    forgiveness_entries: Mapped[list["ForgivenessListEntry"]] = relationship(back_populates="user")
    escalations: Mapped[list["Escalation"]] = relationship(back_populates="user")

    @property
    def onboarding_complete(self) -> bool:
        return self.onboarding_step == "complete"


class FastingLog(Base):
    __tablename__ = "fasting_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    fast_type: Mapped[str] = mapped_column(String(64), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    user: Mapped["User"] = relationship(back_populates="fasting_logs")


class Reflection(Base):
    __tablename__ = "reflections"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)

    user: Mapped["User"] = relationship(back_populates="reflections")


class ForgivenessListEntry(Base):
    __tablename__ = "forgiveness_list"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    relationship_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    user: Mapped["User"] = relationship(back_populates="forgiveness_entries")


class Escalation(Base):
    __tablename__ = "escalations"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending | answered
    answer_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    added_to_faq: Mapped[bool] = mapped_column(Boolean, default=False)
    timestamp: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.utcnow
    )

    user: Mapped["User"] = relationship(back_populates="escalations")


class FAQ(Base):
    __tablename__ = "faq"

    id: Mapped[int] = mapped_column(primary_key=True)
    question_en: Mapped[str] = mapped_column(Text, nullable=False)
    question_gu: Mapped[str] = mapped_column(Text, nullable=False)
    answer_en: Mapped[str] = mapped_column(Text, nullable=False)
    answer_gu: Mapped[str] = mapped_column(Text, nullable=False)


class Broadcast(Base):
    __tablename__ = "broadcasts"

    id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[datetime.date] = mapped_column(Date, nullable=False, unique=True)
    day_number: Mapped[int] = mapped_column(nullable=False)
    theme_en: Mapped[str] = mapped_column(String(255), nullable=False)
    theme_gu: Mapped[str] = mapped_column(String(255), nullable=False)
    pratikraman_timing: Mapped[str] = mapped_column(String(64), nullable=False)
    announcements_en: Mapped[str | None] = mapped_column(Text, nullable=True)
    announcements_gu: Mapped[str | None] = mapped_column(Text, nullable=True)
    message_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    sent_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
