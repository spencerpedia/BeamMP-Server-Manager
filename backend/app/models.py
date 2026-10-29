from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(16), default="viewer")  # admin | operator | viewer
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    grants: Mapped[list["ServerGrant"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class Server(Base):
    __tablename__ = "servers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    port: Mapped[int] = mapped_column(Integer, unique=True)
    version: Mapped[str] = mapped_column(String(32), default="latest")  # "latest" or a release tag
    autostart: Mapped[bool] = mapped_column(Boolean, default=False)
    auto_restart: Mapped[bool] = mapped_column(Boolean, default=True)
    backup_retention: Mapped[int] = mapped_column(Integer, default=10)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    grants: Mapped[list["ServerGrant"]] = relationship(back_populates="server", cascade="all, delete-orphan")
    schedules: Mapped[list["Schedule"]] = relationship(back_populates="server", cascade="all, delete-orphan")
    bans: Mapped[list["Ban"]] = relationship(back_populates="server", cascade="all, delete-orphan")


class ServerGrant(Base):
    """Gives a non-admin user access to one server, at their role's level."""

    __tablename__ = "server_grants"
    __table_args__ = (UniqueConstraint("user_id", "server_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    server_id: Mapped[int] = mapped_column(ForeignKey("servers.id", ondelete="CASCADE"))

    user: Mapped[User] = relationship(back_populates="grants")
    server: Mapped[Server] = relationship(back_populates="grants")


class Schedule(Base):
    __tablename__ = "schedules"

    id: Mapped[int] = mapped_column(primary_key=True)
    server_id: Mapped[int] = mapped_column(ForeignKey("servers.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(128), default="")
    action: Mapped[str] = mapped_column(String(16))  # restart | start | stop | backup | command | update
    cron: Mapped[str] = mapped_column(String(64))  # 5-field crontab
    payload: Mapped[str] = mapped_column(Text, default="")  # console command for action=command
    warn_minutes: Mapped[int] = mapped_column(Integer, default=0)  # in-game countdown before restart/stop/update
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_run: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_result: Mapped[str] = mapped_column(Text, default="")

    server: Mapped[Server] = relationship(back_populates="schedules")


class Ban(Base):
    __tablename__ = "bans"

    id: Mapped[int] = mapped_column(primary_key=True)
    server_id: Mapped[int] = mapped_column(ForeignKey("servers.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(64), default="")
    beammp_id: Mapped[str] = mapped_column(String(32), default="")
    ip: Mapped[str] = mapped_column(String(64), default="")
    reason: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    server: Mapped[Server] = relationship(back_populates="bans")


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    username: Mapped[str] = mapped_column(String(64), default="")
    server_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    action: Mapped[str] = mapped_column(String(64))
    detail: Mapped[str] = mapped_column(Text, default="")


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")
