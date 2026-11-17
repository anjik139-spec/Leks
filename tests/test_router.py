"""Tests for the JSON LLM router."""

from datetime import date

import pytest
from bot.llm.base import GenerationResult
from bot.router import (
    RouterError,
    build_retry_text,
    build_system_prompt,
    parse_decision,
    route,
)
from bot.skills import SKILLS


class FakeProvider:
    def __init__(self, text: str) -> None:
        self.text = text
        self.messages = None

    async def generate(self, messages, **kwargs):
        self.messages = messages
        return GenerationResult(
            text=self.text,
            model="fake",
            prompt_tokens=1,
            completion_tokens=1,
            latency_ms=1,
            cost_est=0.0,
        )


def test_prompt_contains_registry_and_date() -> None:
    prompt = build_system_prompt(date(2026, 11, 15))
    assert "leave_doc" in prompt
    assert "report_xlsx" in prompt
    assert "15.11.2026" in prompt


def test_retry_text_keeps_pending_args() -> None:
    text = build_retry_text(
        "на две недели с первого декабря",
        {
            "intent": "leave_doc",
            "args": {"fio": "Иванова Ивана Ивановича"},
            "missing": ["date_from", "date_to"],
        },
    )
    assert "Иванова Ивана Ивановича" in text
    assert "date_from" in text
    assert "на две недели" in text
    assert "не теряй" in text


def test_parse_plain_json() -> None:
    decision = parse_decision(
        '{"intent":"leave_doc","args":{"fio":"Иванов Иван"},'
        '"missing":[],"question":"","confidence":0.9}'
    )
    assert decision.intent == "leave_doc"
    assert decision.args["fio"] == "Иванов Иван"


def test_parse_fenced_json() -> None:
    decision = parse_decision(
        '```json\n{"intent":"general","args":{},"missing":[],"question":"","confidence":0.5}\n```'
    )
    assert decision.intent == "general"


def test_unknown_intent_rejected() -> None:
    with pytest.raises(RouterError):
        parse_decision(
            '{"intent":"hack_bank","args":{},"missing":[],"question":"","confidence":1.0}'
        )


@pytest.mark.asyncio
async def test_route_calls_provider() -> None:
    provider = FakeProvider(
        '{"intent":"report_xlsx","args":{"title":"Отчёт"},'
        '"missing":[],"question":"","confidence":0.8}'
    )
    decision = await route(provider, "сделай отчёт")
    assert decision.intent == "report_xlsx"
    assert provider.messages is not None
    assert "report_xlsx" in provider.messages[0]["content"]
    assert "leave_doc" in SKILLS
