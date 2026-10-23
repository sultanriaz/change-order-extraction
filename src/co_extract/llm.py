"""Gemini SDK adapter, typed failures, shared throttling, retries and content-addressed cache."""
from __future__ import annotations

import hashlib
import json
import os
import random
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from co_extract.config import Settings
from co_extract.prompts import SYSTEM_PROMPT, PROMPT_VERSION
from co_extract.schema import LLMOutput


class ModelError(Exception):
    """Typed recoverable call/format error."""


class ModelBlocked(ModelError):
    """Blocked or empty provider output."""


@dataclass
class LLMResponse:
    text: str
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: int = 0
    cache_hit: bool = False


class LLMClient(Protocol):
    """Minimum interface shared by real and offline LLM implementations."""
    model_id: str

    def complete(self, contents: str, *, source_hash: str, temperature: float = 0.0,
                 feedback: str = '', use_cache: bool = True, pdf_bytes: bytes | None = None,
                 structured: bool = True) -> LLMResponse:
        """Return generated JSON text or typed error."""
        ...


class TokenBucket:
    """Thread-safe simple token bucket throttling outgoing calls per minute."""
    def __init__(self, rpm: int):
        self.capacity = float(rpm)
        self.tokens = float(rpm)
        self.refill = float(rpm) / 60.0
        self.clock = time.monotonic()
        self.lock = threading.Lock()

    def acquire(self) -> None:
        """Wait until one request can be sent."""
        while True:
            with self.lock:
                now = time.monotonic()
                self.tokens = min(self.capacity, self.tokens + (now - self.clock)*self.refill)
                self.clock = now
                if self.tokens >= 1:
                    self.tokens -= 1
                    return
                delay = (1 - self.tokens) / self.refill
            time.sleep(min(delay, 5.0))


class GeminiClient:
    """Use google-genai with Pydantic output schemas, fallback and bounded retries."""
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or Settings.from_env()
        key = os.getenv('GEMINI_API_KEY', '').strip()
        if not key:
            raise ModelError('GEMINI_API_KEY missing; set it for live Gemini or use --mock')
        try:
            from google import genai
        except ImportError as exc:
            raise ModelError('Install pinned google-genai SDK from requirements.txt') from exc
        self.client = genai.Client(api_key=key)
        self.model_id = self.settings.model
        self.bucket = TokenBucket(self.settings.rpm)
        self.settings.cache_dir.mkdir(parents=True, exist_ok=True)

    def complete(self, contents: str, *, source_hash: str, temperature: float = 0.0,
                 feedback: str = '', use_cache: bool = True, pdf_bytes: bytes | None = None,
                 structured: bool = True) -> LLMResponse:
        """Cache by source, prompt, model, temperature and request content; never cache secrets."""
        from google.genai import types
        digest = hashlib.sha256(json.dumps({
            'source_hash': source_hash, 'prompt': PROMPT_VERSION, 'model': self.model_id,
            'temperature': temperature, 'contents_hash': hashlib.sha256(contents.encode()).hexdigest(),
            'feedback': feedback, 'pdf_hash': hashlib.sha256(pdf_bytes).hexdigest() if pdf_bytes else None,
            'structured': structured,
        }, sort_keys=True).encode()).hexdigest()
        cache_path = self.settings.cache_dir / (digest + '.json')
        if use_cache and cache_path.exists():
            try:
                value = LLMResponse(**json.loads(cache_path.read_text()))
                value.cache_hit = True
                return value
            except (ValueError, TypeError):
                cache_path.unlink(missing_ok=True)
        inputs: list = [contents + ('\n\nVALIDATION ERRORS TO CORRECT:\n' + feedback if feedback else '')]
        if pdf_bytes is not None:
            inputs.append(types.Part.from_bytes(data=pdf_bytes, mime_type='application/pdf'))
        start = time.perf_counter()
        for attempt in range(4):
            self.bucket.acquire()
            try:
                config = types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    response_mime_type='application/json',
                    response_schema=LLMOutput if structured else None,
                    temperature=temperature,
                )
                response = self.client.models.generate_content(model=self.model_id, contents=inputs, config=config)
                content = response.text
                if not content or not content.strip():
                    raise ModelBlocked(f'Gemini returned empty/blocked output; feedback={response.prompt_feedback}')
                usage = getattr(response, 'usage_metadata', None)
                result = LLMResponse(text=content,
                                     input_tokens=int(getattr(usage, 'prompt_token_count', 0) or 0),
                                     output_tokens=int(getattr(usage, 'candidates_token_count', 0) or 0),
                                     latency_ms=round((time.perf_counter() - start)*1000))
                if use_cache:
                    cache_path.write_text(json.dumps(result.__dict__), encoding='utf-8')
                return result
            except ModelBlocked:
                raise
            except Exception as exc:
                message = str(exc)
                if '404' in message or 'not found' in message.lower():
                    raise ModelError(f'Model {self.model_id!r} not accepted. Verify its exact ID in Google AI Studio: {message[:200]}') from exc
                transient = any(code in message for code in ('429', '500', '502', '503', '504', 'RESOURCE_EXHAUSTED', 'UNAVAILABLE'))
                if not transient or attempt == 3:
                    raise ModelError(f'Gemini call failed ({type(exc).__name__}): {message[:250]}') from exc
                time.sleep(min(12, 2**attempt + random.uniform(0, .5)))
        raise ModelError('Retries exhausted')


class MockLLM:
    """Offline *heuristic* test double, not evidence of Gemini accuracy."""
    model_id = 'mock-regex-v1'

    def complete(self, contents: str, *, source_hash: str, temperature: float = 0.0,
                 feedback: str = '', use_cache: bool = True, pdf_bytes: bytes | None = None,
                 structured: bool = True) -> LLMResponse:
        """Extract from delimited page text using fixed regex rules, without a network call."""
        import re
        from co_extract.ingest import Page
        from co_extract.baseline_regex import baseline
        pages = []
        for match in re.finditer(r'<document page="(\d+)">\n(.*?)\n</document>', contents, re.S):
            pages.append(Page(num=int(match.group(1)), text=match.group(2)))
        return LLMResponse(text=baseline(pages).model_dump_json(), latency_ms=0)
