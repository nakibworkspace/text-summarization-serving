from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sqlalchemy import TextSummary
from app.models.pydantic import SummaryPayloadSchema, SummaryUpdatePayloadSchema


async def post(payload: SummaryPayloadSchema, session: AsyncSession) -> int:
    summary = TextSummary(url=str(payload.url), summary="")
    session.add(summary)
    await session.commit()
    await session.refresh(summary)
    return summary.id


async def get(id: int, session: AsyncSession) -> dict | None:
    result = await session.execute(select(TextSummary).filter(TextSummary.id == id))
    summary = result.scalar_one_or_none()
    
    if summary:
        return {
            "id": summary.id,
            "url": summary.url,
            "summary": summary.summary,
            "created_at": summary.created_at
        }
    return None


async def get_all(session: AsyncSession) -> list:
    result = await session.execute(select(TextSummary))
    summaries = result.scalars().all()
    
    return [
        {
            "id": s.id,
            "url": s.url,
            "summary": s.summary,
            "created_at": s.created_at
        }
        for s in summaries
    ]


async def put(id: int, payload: SummaryUpdatePayloadSchema, session: AsyncSession) -> dict | None:
    result = await session.execute(select(TextSummary).filter(TextSummary.id == id))
    summary = result.scalar_one_or_none()
    
    if summary:
        summary.url = str(payload.url)
        summary.summary = payload.summary
        await session.commit()
        await session.refresh(summary)
        
        return {
            "id": summary.id,
            "url": summary.url,
            "summary": summary.summary,
            "created_at": summary.created_at
        }
    return None


async def delete(id: int, session: AsyncSession) -> int:
    result = await session.execute(select(TextSummary).filter(TextSummary.id == id))
    summary = result.scalar_one_or_none()
    
    if summary:
        await session.delete(summary)
        await session.commit()
        return id
    return None