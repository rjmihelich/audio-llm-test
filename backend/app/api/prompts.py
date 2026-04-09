"""CRUD API for system prompt library."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.base import get_session
from backend.app.models.prompt import Prompt

router = APIRouter()


class PromptCreate(BaseModel):
    name: str
    content: str
    description: str = ""


class PromptUpdate(BaseModel):
    name: str | None = None
    content: str | None = None
    description: str | None = None


class PromptResponse(BaseModel):
    id: str
    name: str
    content: str
    description: str
    created_at: str
    updated_at: str


def _to_response(p: Prompt) -> PromptResponse:
    return PromptResponse(
        id=str(p.id),
        name=p.name,
        content=p.content,
        description=p.description or "",
        created_at=p.created_at.isoformat(),
        updated_at=p.updated_at.isoformat(),
    )


@router.get("/prompts", response_model=list[PromptResponse])
async def list_prompts(session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(Prompt).order_by(Prompt.created_at.desc()))
    return [_to_response(p) for p in result.scalars().all()]


@router.post("/prompts", response_model=PromptResponse, status_code=201)
async def create_prompt(body: PromptCreate, session: AsyncSession = Depends(get_session)):
    prompt = Prompt(name=body.name, content=body.content, description=body.description or None)
    session.add(prompt)
    await session.commit()
    await session.refresh(prompt)
    return _to_response(prompt)


@router.get("/prompts/{prompt_id}", response_model=PromptResponse)
async def get_prompt(prompt_id: str, session: AsyncSession = Depends(get_session)):
    prompt = await session.get(Prompt, uuid.UUID(prompt_id))
    if not prompt:
        raise HTTPException(404, "Prompt not found")
    return _to_response(prompt)


@router.patch("/prompts/{prompt_id}", response_model=PromptResponse)
async def update_prompt(
    prompt_id: str, body: PromptUpdate, session: AsyncSession = Depends(get_session)
):
    prompt = await session.get(Prompt, uuid.UUID(prompt_id))
    if not prompt:
        raise HTTPException(404, "Prompt not found")
    if body.name is not None:
        prompt.name = body.name
    if body.content is not None:
        prompt.content = body.content
    if body.description is not None:
        prompt.description = body.description or None
    await session.commit()
    await session.refresh(prompt)
    return _to_response(prompt)


@router.delete("/prompts/{prompt_id}", status_code=204)
async def delete_prompt(prompt_id: str, session: AsyncSession = Depends(get_session)):
    prompt = await session.get(Prompt, uuid.UUID(prompt_id))
    if not prompt:
        raise HTTPException(404, "Prompt not found")
    await session.delete(prompt)
    await session.commit()
