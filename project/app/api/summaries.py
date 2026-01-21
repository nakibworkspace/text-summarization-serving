from fastapi import APIRouter, HTTPException, Path, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import crud
from app.db import get_session
from app.models.pydantic import (
    SummaryPayloadSchema,
    SummaryResponseSchema,
    SummaryUpdatePayloadSchema,
    SummarySchema,
)
from app.summarizer import generate_summary

router = APIRouter()


@router.post("/", response_model=SummaryResponseSchema, status_code=201)
async def create_summary(
    payload: SummaryPayloadSchema,
    session: AsyncSession = Depends(get_session)
) -> SummaryResponseSchema:
    summary_id = await crud.post(payload, session)
    
    # Run summary generation in background
    # You'll need to pass session differently for background tasks
    # For now, generate_summary will need to create its own session
    
    response_object = {"id": summary_id, "url": payload.url}
    return response_object


@router.get("/{id}/", response_model=SummarySchema)
async def read_summary(
    id: int = Path(..., gt=0),
    session: AsyncSession = Depends(get_session)
) -> SummarySchema:
    summary = await crud.get(id, session)
    if not summary:
        raise HTTPException(status_code=404, detail="Summary not found")
    return summary


@router.get("/", response_model=list[SummarySchema])
async def read_all_summaries(
    session: AsyncSession = Depends(get_session)
) -> list[SummarySchema]:
    return await crud.get_all(session)


@router.put("/{id}/", response_model=SummarySchema)
async def update_summary(
    payload: SummaryUpdatePayloadSchema,
    id: int = Path(..., gt=0),
    session: AsyncSession = Depends(get_session)
) -> SummarySchema:
    summary = await crud.put(id, payload, session)
    if not summary:
        raise HTTPException(status_code=404, detail="Summary not found")
    return summary


@router.delete("/{id}/", response_model=SummaryResponseSchema)
async def delete_summary(
    id: int = Path(..., gt=0),
    session: AsyncSession = Depends(get_session)
) -> SummaryResponseSchema:
    summary = await crud.get(id, session)
    if not summary:
        raise HTTPException(status_code=404, detail="Summary not found")
    
    await crud.delete(id, session)
    return summary