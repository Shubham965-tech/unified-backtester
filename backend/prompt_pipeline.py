"""Cost-aware prompt preparation and LangChain Gemini orchestration.

The pipeline intentionally avoids an LLM call for short prompts. Long prompts are
compressed only when their estimated token count exceeds PROMPT_COMPRESS_THRESHOLD.
All generated expressions must still be validated by the engine-facing validator.
"""
from __future__ import annotations

import json
import os
import re
import time
from typing import Any


def estimate_tokens(text: str) -> int:
    """Cheap conservative estimate; use provider token counts for billing-grade data."""
    return max(1, (len(text) + 3) // 4)


def normalize_prompt(text: str) -> str:
    """Deterministic cleanup that does not call an LLM or discard unique constraints."""
    text = text.replace("\x00", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    # Remove exact repeated lines only; preserve order and all distinct instructions.
    seen, lines = set(), []
    for line in text.splitlines():
        normalized = re.sub(r"\s+", " ", line).strip()
        key = normalized.casefold()
        if normalized and key in seen:
            continue
        if normalized:
            seen.add(key)
        lines.append(normalized)
    return "\n".join(lines).strip()


def select_relevant_context(fields: list[str], operators: list[str], idea: str, limit: int = 80) -> tuple[list[str], list[str]]:
    """Reduce registry context using strategy keywords while always retaining operators."""
    terms = set(re.findall(r"[a-z0-9_]+", idea.lower()))
    groups = {
        "momentum": {"momentum", "return", "trend", "performance", "price"},
        "volatility": {"volatility", "risk", "stable", "spike", "variance"},
        "volume": {"volume", "liquidity", "turnover", "surge"},
        "reversal": {"reversal", "mean", "oversold", "overbought", "rsi"},
        "fundamental": {"fundamental", "value", "earnings", "cashflow", "debt", "revenue"},
    }
    active = {name for name, words in groups.items() if terms & words}
    scored = []
    for field in fields:
        lower = field.lower()
        score = sum(2 for group in active if group in lower)
        score += sum(1 for term in terms if len(term) > 3 and term in lower)
        # OHLCV fields are broadly useful and should survive filtering.
        if lower in {"open", "high", "low", "close", "volume", "returns"}:
            score += 1
        scored.append((score, field))
    if not active or not any(score for score, _ in scored):
        selected_fields = fields[:limit]
    else:
        selected_fields = [field for score, field in sorted(scored, key=lambda x: (-x[0], x[1])) if score > 0][:limit]
        if len(selected_fields) < min(15, len(fields)):
            selected_fields += [f for f in fields if f not in selected_fields][:min(15, len(fields))-len(selected_fields)]
    return sorted(set(selected_fields)), sorted(set(operators))


def _langchain_chat(model_name: str, api_key: str, temperature: float = 0.0):
    from langchain_google_genai import ChatGoogleGenerativeAI
    return ChatGoogleGenerativeAI(
        model=model_name,
        google_api_key=api_key,
        temperature=temperature,
        max_retries=1,
    )


def compress_with_langchain(idea: str, model_name: str, api_key: str) -> tuple[str, dict[str, Any]]:
    """Compress a long prompt while preserving every actionable constraint."""
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_core.output_parsers import StrOutputParser

    template = ChatPromptTemplate.from_messages([
        ("system", """You are a loss-aware trading-strategy requirement extractor. Convert the user's long request into a concise, self-contained strategy brief. Preserve every distinct requirement, including market/universe, direction, features, holding horizon, date range, execution assumptions, costs, risk limits, requested metrics, exclusions, and output format. Remove repetition and filler only. Never invent missing values; mark unspecified items as unspecified. Do not generate alpha expressions or results. Output plain text under 180 words."""),
        ("human", "User request:\n{idea}"),
    ])
    chain = template | _langchain_chat(model_name, api_key, 0.0) | StrOutputParser()
    started = time.perf_counter()
    compressed = chain.invoke({"idea": idea}).strip()
    if len(compressed) < 20:
        raise ValueError("Prompt compressor returned an unexpectedly short result")
    return compressed, {
        "compression_model": model_name,
        "compression_input_tokens_est": estimate_tokens(idea),
        "compression_output_tokens_est": estimate_tokens(compressed),
        "compression_elapsed_s": round(time.perf_counter() - started, 3),
    }


def generate_with_langchain(prompt: str, model_name: str, api_key: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """Generate JSON with LangChain; caller owns schema and expression validation."""
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_core.output_parsers import StrOutputParser

    template = ChatPromptTemplate.from_messages([
        ("system", "You are a careful quantitative research assistant. Follow the supplied constraints exactly. Return only a valid JSON object, with no markdown fences. Never claim an alpha was backtested unless a real backtest result was supplied."),
        ("human", "{prompt}"),
    ])
    chain = template | _langchain_chat(model_name, api_key, 0.25) | StrOutputParser()
    started = time.perf_counter()
    output = chain.invoke({"prompt": prompt}).strip()
    # Accommodate providers that wrap JSON in markdown despite instructions.
    output = re.sub(r"^```(?:json)?\s*|\s*```$", "", output, flags=re.IGNORECASE).strip()
    parsed = json.loads(output)
    if not isinstance(parsed, dict):
        raise ValueError("Gemini response must be a JSON object")
    return parsed, {
        "generation_model": model_name,
        "generation_input_tokens_est": estimate_tokens(prompt),
        "generation_output_tokens_est": estimate_tokens(output),
        "generation_elapsed_s": round(time.perf_counter() - started, 3),
    }
