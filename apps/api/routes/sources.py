from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException
from packages.db.models import SourceDocument
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.deps import get_db

router = APIRouter(tags=["sources"])


class SourceDetail(BaseModel):
    source_id: str
    source_authority: str
    source_type: str
    source_url: str | None = None
    document_title: str | None = None
    publication_date: date | None = None
    retrieved_at: datetime
    content_sha256: str | None = None
    collector_name: str | None = None
    collector_version: str | None = None
    parser_version: str | None = None
    git_commit_sha: str | None = None
    extraction_method: str | None = None
    extraction_confidence: str | None = None
    verification_status: str


@router.get("/sources/{source_id}", response_model=SourceDetail)
def get_source(source_id: str, db: Session = Depends(get_db)) -> SourceDetail:
    source = db.scalars(select(SourceDocument).where(SourceDocument.source_id == source_id)).first()
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found")
    return SourceDetail(
        source_id=source.source_id,
        source_authority=source.source_authority,
        source_type=source.source_type,
        source_url=source.source_url,
        document_title=source.document_title,
        publication_date=source.publication_date,
        retrieved_at=source.retrieved_at,
        content_sha256=source.content_sha256,
        collector_name=source.collector_name,
        collector_version=source.collector_version,
        parser_version=source.parser_version,
        git_commit_sha=source.git_commit_sha,
        extraction_method=source.extraction_method,
        extraction_confidence=source.extraction_confidence,
        verification_status=source.verification_status,
    )
