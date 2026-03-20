from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    progress: Mapped[list["WatchProgress"]] = relationship("WatchProgress", back_populates="user")
    notes: Mapped[list["Note"]] = relationship("Note", back_populates="user")
    schedule_items: Mapped[list["ScheduleItem"]] = relationship("ScheduleItem", back_populates="user")


class Video(Base):
    __tablename__ = "videos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_message_id: Mapped[int] = mapped_column(Integer, nullable=False)
    telegram_group_id: Mapped[int] = mapped_column(Integer, nullable=False)
    telegram_group_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    title: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    duration: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # segundos
    file_size: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # bytes
    subject: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    course_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    lesson_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    menu_tag: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    filename: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    thumbnail_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    cached_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        UniqueConstraint("telegram_group_id", "telegram_message_id", name="uq_video_group_msg"),
        Index("ix_video_subject", "subject"),
        Index("ix_video_course", "course_name"),
        Index("ix_video_menu_tag", "menu_tag"),
    )

    progress: Mapped[list["WatchProgress"]] = relationship("WatchProgress", back_populates="video")
    notes: Mapped[list["Note"]] = relationship("Note", back_populates="video")


class Material(Base):
    __tablename__ = "materials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_message_id: Mapped[int] = mapped_column(Integer, nullable=False)
    telegram_group_id: Mapped[int] = mapped_column(Integer, nullable=False)
    telegram_group_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    title: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    subject: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    course_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    lesson_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    menu_tag: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    file_name: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    file_ext: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    file_size: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # bytes
    cached_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("telegram_group_id", "telegram_message_id", name="uq_material_group_msg"),
        Index("ix_material_subject", "subject"),
        Index("ix_material_menu_tag", "menu_tag"),
    )


class WatchProgress(Base):
    __tablename__ = "watch_progress"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    video_id: Mapped[int] = mapped_column(Integer, ForeignKey("videos.id", ondelete="CASCADE"), nullable=False)
    current_time: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)  # segundos
    duration: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)  # segundos
    completed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_watched: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("user_id", "video_id", name="uq_progress_user_video"),
    )

    user: Mapped["User"] = relationship("User", back_populates="progress")
    video: Mapped["Video"] = relationship("Video", back_populates="progress")


class Note(Base):
    __tablename__ = "notes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    video_id: Mapped[int] = mapped_column(Integer, ForeignKey("videos.id", ondelete="CASCADE"), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    video_timestamp: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)  # segundos
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    __table_args__ = (
        Index("ix_note_user_video", "user_id", "video_id"),
    )

    user: Mapped["User"] = relationship("User", back_populates="notes")
    video: Mapped["Video"] = relationship("Video", back_populates="notes")


class ScheduleItem(Base):
    __tablename__ = "schedule_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    subject: Mapped[str] = mapped_column(String(100), nullable=False)
    topic: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    scheduled_date: Mapped[str] = mapped_column(String(10), nullable=False)  # YYYY-MM-DD
    scheduled_time: Mapped[Optional[str]] = mapped_column(String(5), nullable=True)  # HH:MM
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    color: Mapped[Optional[str]] = mapped_column(String(7), nullable=True)  # #RRGGBB
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_schedule_user_date", "user_id", "scheduled_date"),
    )

    user: Mapped["User"] = relationship("User", back_populates="schedule_items")


class SyncState(Base):
    __tablename__ = "sync_state"

    group_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    last_message_id: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_sync_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    videos_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
