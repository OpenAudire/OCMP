"""Shared setup for the AI mapping tests: a framework, a configured provider that answers."""

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models import Faculty, Framework, FrameworkItem, Institution, User
from app.models.framework import FrameworkStatus
from tests.factories import FrameworkFactory, UserFactory
from tests.test_ai_gateway import configure
from tests.test_curriculum_objectives_api import World

USAGE = {"input_tokens": 1000, "output_tokens": 300}


@dataclass
class Library:
    framework: Framework
    communication: FrameworkItem
    heart: FrameworkItem
    hygiene: FrameworkItem
    ethics: FrameworkItem


async def make_library(db: AsyncSession) -> Library:
    """A small active framework. Only the heart item shares words with the cardiac objectives
    of the shared ``world`` ("cardiac", "cycle")."""
    framework = FrameworkFactory(status=FrameworkStatus.ACTIVE, name="Graduate competencies")
    db.add(framework)
    await db.flush()
    items = [
        FrameworkItem(framework_id=framework.id, code=code, title=title, description=text)
        for code, title, text in (
            ("COM1", "Communicate clearly with patients", "Uses plain language."),
            ("HRT1", "Describe the structure of the heart and the cardiac cycle", ""),
            ("HYG1", "Infection control and hand hygiene", "Applies standard precautions."),
            ("ETH1", "Professional ethics", "Acts with integrity."),
        )
    ]
    db.add_all(items)
    await db.flush()
    return Library(framework, *items)


async def institution_of(db: AsyncSession, world: World) -> Institution:
    faculty = await db.get(Faculty, world.programme.faculty_id)
    assert faculty is not None
    institution = await db.get(Institution, faculty.institution_id)
    assert institution is not None
    return institution


async def turn_ai_on(db: AsyncSession, world: World, settings: Settings, **change: Any) -> User:
    """Choose a provider for the world's institution (see ``test_ai_gateway.configure``)."""
    admin = UserFactory.build(display_name="Pat Admin")
    db.add(admin)
    await db.flush()
    await configure(db, await institution_of(db, world), admin, settings, **change)
    return admin


def prompt_of(request: httpx.Request) -> str:
    return str(json.loads(request.content)["messages"][0]["content"])


def offered_codes(prompt: str) -> list[str]:
    block = prompt.split("Candidate framework items (code, then wording):\n", 1)[1]
    block = block.split("\n\n", 1)[0]
    return [line.split(":", 1)[0] for line in block.splitlines() if line]


def objective_of(prompt: str) -> str:
    return re.search(r"^Objective: (.+)$", prompt, re.MULTILINE).group(1)  # type: ignore[union-attr]


def good_answer(prompt: str, *, matches: int = 1) -> str:
    """A valid answer: the first ``matches`` candidates match, quoting the objective's end."""
    objective = objective_of(prompt)
    quote = " ".join(objective.rstrip(".").split()[-2:])
    rows = []
    for position, code in enumerate(offered_codes(prompt)):
        match = position < matches
        rows.append(
            {
                "code": code,
                "is_match": match,
                "coverage": 4 if match else 0,
                "depth_match": "matches" if match else "not_applicable",
                "confidence": 0.9 if match else 0.1,
                "rationale": "It addresses the item." if match else "",
                "evidence_quote": quote if match else "",
            }
        )
    return json.dumps({"candidates": rows})


class Model:
    """A mock Anthropic API. ``answer`` turns the prompt into the text the model returns;
    ``statuses`` can make the first calls fail."""

    def __init__(
        self,
        answer: Callable[[str], str] = good_answer,
        statuses: list[int] | None = None,
    ) -> None:
        self.answer = answer
        self.statuses = list(statuses or [])
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        status = self.statuses.pop(0) if self.statuses else 200
        if status != 200:
            return httpx.Response(status, json={"error": {"message": "overloaded"}})
        body = {
            "content": [{"type": "text", "text": self.answer(prompt_of(request))}],
            "usage": USAGE,
            "model": "claude-sonnet-5-5",
        }
        return httpx.Response(200, json=body)

    @property
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self)

    @property
    def prompts(self) -> list[str]:
        return [prompt_of(r) for r in self.requests]
