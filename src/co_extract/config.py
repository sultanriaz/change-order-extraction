"""Runtime settings, strict environment handling and illustrative token-cost assumptions."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    model: str = "gemini-3.8-flash"
    cache_dir: Path = Path('.cache/llm')
    rpm: int = 20
    concurrency: int = 2
    review_threshold: float = 0.90
    input_usd_per_m: float = 0.50
    output_usd_per_m: float = 3.0
    max_retries: int = 2

    @classmethod
    def from_env(cls) -> 'Settings':
        """Load settings; token price defaults are assumptions, not official price quotes."""
        return cls(
            model=os.getenv('EXTRACTION_MODEL', 'gemini-3.8-flash'),
            cache_dir=Path(os.getenv('CO_CACHE_DIR', '.cache/llm')),
            rpm=max(1, int(os.getenv('CO_REQUESTS_PER_MIN', '20'))),
            concurrency=max(1, int(os.getenv('CO_CONCURRENCY', '2'))),
            review_threshold=float(os.getenv('CO_REVIEW_THRESHOLD', '0.9')),
            input_usd_per_m=float(os.getenv('CO_INPUT_USD_PER_M', '0.5')),
            output_usd_per_m=float(os.getenv('CO_OUTPUT_USD_PER_M', '3.0')),
        )
