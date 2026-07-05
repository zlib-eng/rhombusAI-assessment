import re
import hashlib
import logging

from django.core.cache import cache
from django.conf import settings
from google import genai
from google.genai import types

logger = logging.getLogger(__name__)

client = genai.Client(api_key=settings.GEMINI_API_KEY)

CACHE_TTL_SECONDS = 60 * 60 * 24 * 7

SYSTEM_PROMPT = (
    "You convert natural language descriptions into a single regular expression. "
    "Respond with ONLY the raw regex pattern. "
    "No explanation, no markdown formatting, no code fences, no quotation marks "
    "around it, no leading text like 'Pattern:'. "
    "Output nothing except the pattern itself."
)


class RegexGenerationError(Exception):
    """
    Raised when the LLM's output is unusable — invalid regex syntax,
    or a pattern that looks dangerous (catastrophic backtracking).
    Treated as a permanent failure, not something worth retrying.
    """
    pass


def _normalize_prompt(prompt):
    return prompt.strip().lower()


def _cache_key(prompt):
    normalized = _normalize_prompt(prompt)
    digest = hashlib.sha256(normalized.encode()).hexdigest()
    return f"regex_cache:{digest}"


def _looks_like_catastrophic_backtracking(pattern):
    danger_signature = r'\([^()]*[+*]\)[+*]'
    return bool(re.search(danger_signature, pattern))


def validate_regex(pattern):
    if not pattern or not pattern.strip():
        raise RegexGenerationError("LLM returned an empty pattern")

    pattern = pattern.strip()

    try:
        re.compile(pattern)
    except re.error as e:
        raise RegexGenerationError(f"Generated pattern is not valid regex: {e}")

    if _looks_like_catastrophic_backtracking(pattern):
        raise RegexGenerationError(
            f"Generated pattern '{pattern}' has nested quantifiers and could "
            "cause catastrophic backtracking. Rejected for safety."
        )

    return pattern


def _call_llm(prompt):
    """
    Calls the Gemini API using the free tier.
    Model: gemini-2.5-flash — confirmed part of Google's free tier,
    1,500 requests/day, no credit card required.
    """
    logger.info(f"Calling LLM for prompt: {prompt!r}")

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=f"Natural language description: {prompt}",
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            max_output_tokens=200,
            temperature=0.0,  # deterministic — we want the same pattern each time
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        ),
    )

    raw_text = response.text.strip()
    # Log the exact raw output before any cleanup — invaluable for
    # debugging if the LLM's formatting ever changes unexpectedly.
    logger.info(f"Raw LLM response: {raw_text!r}")

    # Defensive cleanup — models occasionally wrap output in
    # backticks or add a label even with a strict system prompt.
    raw_text = raw_text.strip('`').strip()
    for prefix in ('regex:', 'pattern:'):
        if raw_text.lower().startswith(prefix):
            raw_text = raw_text[len(prefix):].strip()

    return raw_text


def get_regex_pattern(prompt):
    """
    Main entry point used by the Celery task.
    Checks Redis first. On a miss, calls Gemini, validates, caches.
    """
    key = _cache_key(prompt)

    cached_pattern = cache.get(key)
    if cached_pattern is not None:
        logger.info(f"Cache HIT for prompt: {prompt!r}")
        return cached_pattern

    logger.info(f"Cache MISS for prompt: {prompt!r} — calling LLM")

    raw_pattern = _call_llm(prompt)
    validated_pattern = validate_regex(raw_pattern)

    cache.set(key, validated_pattern, timeout=CACHE_TTL_SECONDS)
    logger.info(f"Cached '{prompt}' -> '{validated_pattern}'")

    return validated_pattern