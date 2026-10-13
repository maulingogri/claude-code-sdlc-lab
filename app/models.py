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
    # Opts into receiving a random, admin-approved Jain-principle vow each
    # morning alongside the daily broadcast (see Vow/VowAssignment below).
    vow_opt_in: Mapped[bool] = mapped_column(Boolean, default=False)
    # Admin-assigned role (Users tab): this user receives the separate
    # Group broadcast (community update, no individual fasting/vow detail)
    # so they can manually relay it into the real Sangh WhatsApp group —
    # the WhatsApp Business API has no way to post into a group chat
    # directly, so a human relay is the only option. Independent of
    # broadcast_opt_in: being the relay is an assigned role, not a
    # personal content preference.
    is_group_relay: Mapped[bool] = mapped_column(Boolean, default=False)
    # Not in the CLAUDE.md schema; added because the daily broadcast needs a
    # name to display for users who opt into fasting recognition.
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    onboarding_step: Mapped[str] = mapped_column(String(64), default="greeting")
    # Tracks an in-progress multi-turn post-onboarding conversation (logging
    # a fast, a reflection, or a family member's fast/reflection). None
    # means idle.
    active_flow: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # The specific FastingLog/Reflection row this flow is attaching a note
    # to — looking up "the user's most recent row" instead once
    # misattached a note to the wrong record if the user started a second
    # entry while the first was still mid-flow.
    active_flow_row_id: Mapped[int | None] = mapped_column(nullable=True)
    # Which Dependent a family-member logging flow is currently for (see
    # Dependent below) — separate from active_flow_row_id, which tracks
    # the FastingLog/Reflection row itself once one exists.
    active_flow_dependent_id: Mapped[int | None] = mapped_column(nullable=True)
    # When active_flow was last set — lets us expire a flow the user
    # abandoned instead of silently treating an unrelated later message as
    # its answer indefinitely.
    active_flow_started_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime, nullable=True
    )
    timezone: Mapped[str] = mapped_column(String(64), default="America/New_York")
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.utcnow
    )

    fasting_logs: Mapped[list["FastingLog"]] = relationship(back_populates="user")
    reflections: Mapped[list["Reflection"]] = relationship(back_populates="user")
    escalations: Mapped[list["Escalation"]] = relationship(back_populates="user")
    dependents: Mapped[list["Dependent"]] = relationship(back_populates="guardian")

    @property
    def onboarding_complete(self) -> bool:
        return self.onboarding_step == "complete"


class Dependent(Base):
    """A family member (young child, elder, etc.) who doesn't message the
    bot directly — their guardian logs fasts/reflections on their behalf.
    Never has their own phone/opt-ins; recognition visibility follows the
    guardian's own public_recognition_optin."""

    __tablename__ = "dependents"

    id: Mapped[int] = mapped_column(primary_key=True)
    guardian_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.utcnow
    )

    guardian: Mapped["User"] = relationship(back_populates="dependents")
    fasting_logs: Mapped[list["FastingLog"]] = relationship(back_populates="dependent")
    reflections: Mapped[list["Reflection"]] = relationship(back_populates="dependent")


class FastingLog(Base):
    __tablename__ = "fasting_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    # Set when this log is for a family member rather than the user
    # themselves (see Dependent above); None means it's the user's own.
    dependent_id: Mapped[int | None] = mapped_column(ForeignKey("dependents.id"), nullable=True)
    date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    fast_type: Mapped[str] = mapped_column(String(64), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    user: Mapped["User"] = relationship(back_populates="fasting_logs")
    dependent: Mapped["Dependent | None"] = relationship(back_populates="fasting_logs")


class Reflection(Base):
    __tablename__ = "reflections"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    dependent_id: Mapped[int | None] = mapped_column(ForeignKey("dependents.id"), nullable=True)
    date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)

    user: Mapped["User"] = relationship(back_populates="reflections")
    dependent: Mapped["Dependent | None"] = relationship(back_populates="reflections")


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


class Vow(Base):
    """A candidate Jain-principle daily vow. Nothing is ever sent to a user
    until an admin sets approved=True in the dashboard (Content tab)."""

    __tablename__ = "vows"

    id: Mapped[int] = mapped_column(primary_key=True)
    text_en: Mapped[str] = mapped_column(Text, nullable=False)
    text_gu: Mapped[str] = mapped_column(Text, nullable=False)
    approved: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.utcnow
    )


class VowAssignment(Base):
    """Records that `vow_id` was sent to `user_id` on `date` — used to
    avoid repeating the same vow for the same person while unused
    approved vows remain."""

    __tablename__ = "vow_assignments"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    vow_id: Mapped[int] = mapped_column(ForeignKey("vows.id"), nullable=False)
    date: Mapped[datetime.date] = mapped_column(Date, nullable=False)


class TranslationCache(Base):
    """Persistent cache for app/translation.py's Google Translate calls —
    avoids re-translating (and re-billing for) identical English strings,
    and keeps repeated messages consistently worded."""

    __tablename__ = "translation_cache"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_text: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    translated_text: Mapped[str] = mapped_column(Text, nullable=False)


class Broadcast(Base):
    """One row per Paryushan day, holding two independently-drafted
    English messages — Gujarati is auto-drafted via Google Translate at
    send time (app/translation.py), same as vows and the ad-hoc group
    message, rather than hand-curated per entry.

    - individual_message_en: the fixed intro every opted-in user gets;
      the recognition list, that user's own/family fasting activity, and
      their daily vow are appended automatically per recipient — they
      can't be part of one static draft (see app/broadcast.py).
    - group_message_en: sent as-is (plus its Gujarati translation) to
      whoever is flagged the group relay (User.is_group_relay), for
      manual reposting into the real Sangh WhatsApp group.
    """

    __tablename__ = "broadcasts"

    id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[datetime.date] = mapped_column(Date, nullable=False, unique=True)
    day_number: Mapped[int] = mapped_column(nullable=False)
    individual_message_en: Mapped[str] = mapped_column(Text, default="")
    group_message_en: Mapped[str] = mapped_column(Text, default="")
    message_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    sent_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
