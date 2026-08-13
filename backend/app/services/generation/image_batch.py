"""Bounded retry loop that exposes only accepted image artifacts."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from typing import Any


GenerateAttempt = Callable[[int, str, int, int], Awaitable[dict[str, Any] | None]]


async def generate_accepted_image_batch(
    prompts: Sequence[str],
    seeds: Sequence[int],
    *,
    generate_attempt: GenerateAttempt,
    minimum_accepted: int = 6,
    max_attempts_per_prompt: int = 3,
) -> list[dict[str, Any]]:
    """Generate at most one accepted artifact per prompt with bounded retries."""

    accepted: list[dict[str, Any]] = []
    attempts_per_prompt = max(1, max_attempts_per_prompt)
    for index, prompt in enumerate(prompts):
        seed = seeds[index] if index < len(seeds) else 42 + index
        for attempt in range(attempts_per_prompt):
            artifact = await generate_attempt(index, prompt, seed, attempt)
            if artifact is not None:
                accepted.append(artifact)
                break
    required = min(max(1, minimum_accepted), len(prompts))
    if len(accepted) < required:
        raise RuntimeError(
            f"accepted image count {len(accepted)} is below required {required}"
        )
    return accepted


__all__ = ["generate_accepted_image_batch"]
