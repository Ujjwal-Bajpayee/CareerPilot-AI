from datetime import datetime
from typing import List, Optional
from sqlalchemy import BigInteger, Integer, String, ForeignKey, Boolean, DateTime, text
from sqlalchemy.dialects.mysql import JSON, LONGTEXT
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = "users"

    tg_user_id: Mapped[int] = mapped_column(
        BigInteger, 
        primary_key=True, 
        autoincrement=False
    )
    username: Mapped[Optional[str]] = mapped_column(
        String(255), 
        nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, 
        nullable=False, 
        default=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP")
    )

    resumes: Mapped[List["Resume"]] = relationship(
        "Resume", 
        back_populates="user", 
        cascade="all, delete-orphan"
    )
    matches: Mapped[List["JobMatch"]] = relationship(
        "JobMatch", 
        back_populates="user", 
        cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<User tg_user_id={self.tg_user_id} username='{self.username}'>"

class Resume(Base):
    __tablename__ = "resumes"

    resume_id: Mapped[int] = mapped_column(
        Integer, 
        primary_key=True, 
        autoincrement=True
    )
    tg_user_id: Mapped[int] = mapped_column(
        BigInteger, 
        ForeignKey("users.tg_user_id", ondelete="CASCADE"), 
        nullable=False
    )
    raw_text: Mapped[str] = mapped_column(
        LONGTEXT, 
        nullable=False
    )
    parsed_skills: Mapped[dict] = mapped_column(
        JSON, 
        nullable=False, 
        default=dict
    )

    user: Mapped["User"] = relationship("User", back_populates="resumes")

    def __repr__(self) -> str:
        return f"<Resume resume_id={self.resume_id} tg_user_id={self.tg_user_id}>"

class JobListing(Base):
    __tablename__ = "job_listings"

    job_id: Mapped[int] = mapped_column(
        Integer, 
        primary_key=True, 
        autoincrement=True
    )
    company: Mapped[str] = mapped_column(
        String(255), 
        nullable=False
    )
    title: Mapped[str] = mapped_column(
        String(255), 
        nullable=False
    )
    url: Mapped[str] = mapped_column(
        String(2048), 
        nullable=False
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, 
        default=True, 
        server_default=text("1"),
        nullable=False
    )

    matches: Mapped[List["JobMatch"]] = relationship(
        "JobMatch", 
        back_populates="job", 
        cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<JobListing job_id={self.job_id} company='{self.company}' title='{self.title}' is_active={self.is_active}>"

class JobMatch(Base):
    __tablename__ = "job_matches"

    match_id: Mapped[int] = mapped_column(
        Integer, 
        primary_key=True, 
        autoincrement=True
    )
    tg_user_id: Mapped[int] = mapped_column(
        BigInteger, 
        ForeignKey("users.tg_user_id", ondelete="CASCADE"), 
        nullable=False
    )
    job_id: Mapped[int] = mapped_column(
        Integer, 
        ForeignKey("job_listings.job_id", ondelete="CASCADE"), 
        nullable=False
    )
    match_score: Mapped[int] = mapped_column(
        Integer, 
        nullable=False
    )
    skill_gaps: Mapped[dict] = mapped_column(
        JSON, 
        nullable=False, 
        default=dict
    )
    explanation: Mapped[str] = mapped_column(
        LONGTEXT, 
        nullable=False
    )

    user: Mapped["User"] = relationship("User", back_populates="matches")
    job: Mapped["JobListing"] = relationship("JobListing", back_populates="matches")

    def __repr__(self) -> str:
        return f"<JobMatch match_id={self.match_id} tg_user_id={self.tg_user_id} job_id={self.job_id} score={self.match_score}>"
