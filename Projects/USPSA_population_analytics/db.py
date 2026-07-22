"""
Database layer: SQLAlchemy 2.0 ORM, star-style schema.

Dimensions: matches, stages
Facts:      competitors (one row per registration in a match),
            stage_scores (one row per shooter per stage)

Engine selection:
    * default        -> SQLite file at data/uspsa.db (zero setup)
    * DATABASE_URL   -> any SQLAlchemy URL, e.g. your existing PostgreSQL:
                        export DATABASE_URL=postgresql+psycopg2://user:pw@localhost/uspsa

Ingestion is idempotent: a match is keyed by `source_key` (derived from its
PractiScore URL). Re-ingesting deletes the old rows for that match and
inserts fresh ones, so re-running the scraper never duplicates data.
"""

from __future__ import annotations

import os
from datetime import date, datetime, timezone

from sqlalchemy import (
    Boolean, Date, DateTime, Float, ForeignKey, Integer, String,
    UniqueConstraint, create_engine, select, func,
)
from sqlalchemy.orm import (
    DeclarativeBase, Mapped, Session, mapped_column, relationship,
)

from config import DATA_DIR, DEFAULT_SQLITE_URL


class Base(DeclarativeBase):
    pass


class Match(Base):
    __tablename__ = "matches"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_key: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    source_url: Mapped[str | None] = mapped_column(String(500))
    name: Mapped[str] = mapped_column(String(300))
    match_date: Mapped[date | None] = mapped_column(Date, index=True)
    club_name: Mapped[str | None] = mapped_column(String(200))
    club_code: Mapped[str | None] = mapped_column(String(50))
    level: Mapped[int | None] = mapped_column(Integer)
    region: Mapped[str | None] = mapped_column(String(30), index=True)
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )

    stages: Mapped[list["Stage"]] = relationship(
        back_populates="match", cascade="all, delete-orphan"
    )
    competitors: Mapped[list["Competitor"]] = relationship(
        back_populates="match", cascade="all, delete-orphan"
    )
    stage_scores: Mapped[list["StageScore"]] = relationship(
        back_populates="match", cascade="all, delete-orphan"
    )


class Stage(Base):
    __tablename__ = "stages"
    __table_args__ = (UniqueConstraint("match_id", "number"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"), index=True)
    number: Mapped[int | None] = mapped_column(Integer)
    name: Mapped[str | None] = mapped_column(String(200))
    scoring: Mapped[str | None] = mapped_column(String(50))
    min_rounds: Mapped[int | None] = mapped_column(Integer)
    max_points: Mapped[int | None] = mapped_column(Integer)
    is_classifier: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    classifier_code: Mapped[str | None] = mapped_column(String(20), index=True)

    match: Mapped[Match] = relationship(back_populates="stages")
    scores: Mapped[list["StageScore"]] = relationship(back_populates="stage")


class Competitor(Base):
    """One registration of a shooter in one match (division/class as entered)."""

    __tablename__ = "competitors"
    __table_args__ = (UniqueConstraint("match_id", "comp_number"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"), index=True)
    comp_number: Mapped[int | None] = mapped_column(Integer)
    member_number: Mapped[str | None] = mapped_column(String(40), index=True)
    first_name: Mapped[str | None] = mapped_column(String(100))
    last_name: Mapped[str | None] = mapped_column(String(100))
    division_raw: Mapped[str | None] = mapped_column(String(60))
    division: Mapped[str] = mapped_column(String(30), index=True)
    classification: Mapped[str] = mapped_column(String(4), index=True)
    power_factor: Mapped[str | None] = mapped_column(String(20))
    dq: Mapped[bool] = mapped_column(Boolean, default=False)
    match_points: Mapped[float | None] = mapped_column(Float)
    place: Mapped[int | None] = mapped_column(Integer)

    match: Mapped[Match] = relationship(back_populates="competitors")
    scores: Mapped[list["StageScore"]] = relationship(back_populates="competitor")


class StageScore(Base):
    __tablename__ = "stage_scores"
    __table_args__ = (UniqueConstraint("stage_id", "competitor_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"), index=True)
    stage_id: Mapped[int] = mapped_column(ForeignKey("stages.id"), index=True)
    competitor_id: Mapped[int] = mapped_column(ForeignKey("competitors.id"), index=True)

    a: Mapped[int | None] = mapped_column(Integer)
    b: Mapped[int | None] = mapped_column(Integer)
    c: Mapped[int | None] = mapped_column(Integer)
    d: Mapped[int | None] = mapped_column(Integer)
    m: Mapped[int | None] = mapped_column(Integer)
    ns: Mapped[int | None] = mapped_column(Integer)
    procedurals: Mapped[int | None] = mapped_column(Integer)
    penalties: Mapped[int | None] = mapped_column(Integer)
    time: Mapped[float | None] = mapped_column(Float)
    total_points: Mapped[int | None] = mapped_column(Integer)
    hit_factor: Mapped[float | None] = mapped_column(Float, index=True)
    stage_points: Mapped[float | None] = mapped_column(Float)
    stage_place: Mapped[int | None] = mapped_column(Integer)
    dq: Mapped[bool] = mapped_column(Boolean, default=False)
    dnf: Mapped[bool] = mapped_column(Boolean, default=False)

    match: Mapped[Match] = relationship(back_populates="stage_scores")
    stage: Mapped[Stage] = relationship(back_populates="scores")
    competitor: Mapped[Competitor] = relationship(back_populates="scores")


# ---------------------------------------------------------------------------
# Engine / session helpers
# ---------------------------------------------------------------------------
def get_engine(echo: bool = False):
    """SQLAlchemy engine for `DATABASE_URL` (Postgres etc.), else the default
    SQLite file at data/uspsa.db."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    url = os.environ.get("DATABASE_URL", DEFAULT_SQLITE_URL)
    return create_engine(url, echo=echo, future=True)


def init_db(engine) -> None:
    """Create any missing tables for the schema (idempotent)."""
    Base.metadata.create_all(engine)


# ---------------------------------------------------------------------------
# Ingestion
# ---------------------------------------------------------------------------
def upsert_match(session: Session, parsed: dict, source_key: str,
                 source_url: str | None = None) -> Match:
    """
    Insert one parsed web report. If `source_key` already exists, the old
    match (and its stages/competitors/scores, via cascade) is replaced.
    """
    existing = session.scalar(select(Match).where(Match.source_key == source_key))
    if existing is not None:
        session.delete(existing)
        session.flush()

    m = parsed["match"]
    match = Match(
        source_key=source_key,
        source_url=source_url,
        name=m["name"],
        match_date=m["match_date"],
        club_name=m["club_name"],
        club_code=m["club_code"],
        level=m["level"],
        region=m.get("region"),
    )
    session.add(match)
    session.flush()  # match.id

    stage_by_number: dict[int, Stage] = {}
    for s in parsed["stages"]:
        # Defensive: never add two stages with the same number in one match
        # (the (match_id, number) unique key would abort the whole ingest).
        # Parsers should number stages uniquely; skip a stray collision so a
        # single odd match can't sink a corpus-wide run.
        if s["number"] is not None and s["number"] in stage_by_number:
            continue
        stage = Stage(match_id=match.id, **s)
        session.add(stage)
        if s["number"] is not None:
            stage_by_number[s["number"]] = stage

    comp_by_number: dict[int, Competitor] = {}
    for c in parsed["competitors"]:
        comp = Competitor(match_id=match.id, **c)
        session.add(comp)
        if c["comp_number"] is not None:
            comp_by_number[c["comp_number"]] = comp
    session.flush()  # ids for stages/competitors

    orphans = 0
    for sc in parsed["scores"]:
        stage = stage_by_number.get(sc["stage_number"])
        comp = comp_by_number.get(sc["comp_number"])
        if stage is None or comp is None:
            orphans += 1
            continue
        row = {k: v for k, v in sc.items()
               if k not in ("stage_number", "comp_number")}
        session.add(StageScore(match_id=match.id, stage_id=stage.id,
                               competitor_id=comp.id, **row))
    if orphans:
        print(f"  [db] {orphans} score rows referenced unknown stage/competitor; skipped.")

    return match


def prune_matches(session: Session, keep_keys) -> int:
    """Delete matches whose source_key is not in `keep_keys` (their stages/
    competitors/scores go too, via cascade). Used by a full rebuild so the
    DB mirrors exactly the reports currently on disk. Returns count removed."""
    keep = set(keep_keys)
    stale = session.scalars(
        select(Match).where(Match.source_key.notin_(keep))).all()
    for m in stale:
        session.delete(m)
    return len(stale)


def summary(engine) -> dict:
    """Corpus counts for the KPI row: matches, entries, scores, classifiers, dates."""
    with Session(engine) as s:
        return {
            "matches": s.scalar(select(func.count(Match.id))) or 0,
            "competitor_entries": s.scalar(select(func.count(Competitor.id))) or 0,
            "stage_scores": s.scalar(select(func.count(StageScore.id))) or 0,
            "classifier_stages": s.scalar(
                select(func.count(Stage.id)).where(Stage.is_classifier)) or 0,
            "date_min": s.scalar(select(func.min(Match.match_date))),
            "date_max": s.scalar(select(func.max(Match.match_date))),
        }


if __name__ == "__main__":
    eng = get_engine()
    init_db(eng)
    print("Database ready:", eng.url)
    print(summary(eng))
