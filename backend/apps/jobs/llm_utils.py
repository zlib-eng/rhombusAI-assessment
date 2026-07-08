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


class TransformationSpecError(Exception):
    """
    Base class for any permanent, non-retryable failure when turning a
    natural language prompt into a transformation spec — bad regex,
    disallowed format operation, etc. tasks.py catches this ONE base
    class regardless of which transformation type raised it, so adding
    a future transformation type's own error subclass never requires
    a new except clause in tasks.py.
    """
    pass


class RegexGenerationError(TransformationSpecError):
    pass


class FormatOperationError(TransformationSpecError):
    pass


# ── Shared cache helpers ─────────────────────────────────────────────

def _cache_key(prompt, namespace):
    """
    namespace separates different KINDS of LLM spec-generation from
    each other (regex vs format-operation) so they can never collide.
    It is intentionally NOT the job's transformation_type — FIND_REPLACE
    and EXTRACT both generate a regex pattern via an identical process,
    so they correctly SHARE the same "regex" cache namespace and the
    same LLM call for an identical prompt. Only STANDARDIZE_FORMAT,
    which generates something structurally different (a fixed-choice
    operation, not a regex), gets its own "format" namespace.
    """
    normalized = f"{namespace}:{prompt.strip().lower()}"
    digest = hashlib.sha256(normalized.encode()).hexdigest()
    return f"llm_cache:{digest}"


# ── Regex generation (used by FIND_REPLACE and EXTRACT) ─────────────

REGEX_SYSTEM_PROMPT = (
    "You convert natural language descriptions into a single regular expression. "
    "Respond with ONLY the raw regex pattern. "
    "No explanation, no markdown formatting, no code fences, no quotation marks "
    "around it, no leading text like 'Pattern:'. "
    "Output nothing except the pattern itself."
)


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


def _call_llm_for_regex(prompt):
    logger.info(f"Calling LLM (regex) for prompt: {prompt!r}")

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=f"Natural language description: {prompt}",
        config=types.GenerateContentConfig(
            system_instruction=REGEX_SYSTEM_PROMPT,
            max_output_tokens=200,
            temperature=0.0,
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        ),
    )

    raw_text = (response.text or "").strip()
    logger.info(f"Raw LLM regex response: {raw_text!r}")

    raw_text = raw_text.strip('`').strip()
    for prefix in ('regex:', 'pattern:'):
        if raw_text.lower().startswith(prefix):
            raw_text = raw_text[len(prefix):].strip()

    return raw_text


def get_regex_pattern(prompt):
    key = _cache_key(prompt, "regex")

    cached_pattern = cache.get(key)
    if cached_pattern is not None:
        logger.info(f"Cache HIT (regex) for prompt: {prompt!r}")
        return cached_pattern

    logger.info(f"Cache MISS (regex) for prompt: {prompt!r} — calling LLM")

    raw_pattern = _call_llm_for_regex(prompt)
    validated_pattern = validate_regex(raw_pattern)

    cache.set(key, validated_pattern, timeout=CACHE_TTL_SECONDS)
    logger.info(f"Cached (regex) '{prompt}' -> '{validated_pattern}'")

    return validated_pattern


# ── Format operation (used by STANDARDIZE_FORMAT) ────────────────────

ALLOWED_FORMAT_OPERATIONS = {"UPPER", "LOWER", "INITCAP", "TRIM"}

FORMAT_SYSTEM_PROMPT = (
    "You choose exactly one text formatting operation matching the user's "
    "description. Respond with ONLY one of these exact words, nothing else: "
    "UPPER, LOWER, INITCAP, TRIM, NONE. "
    "UPPER means convert to uppercase. LOWER means convert to lowercase. "
    "INITCAP means capitalize the first letter of each word (title case). "
    "TRIM means remove leading and trailing whitespace. "
    "NONE means the user's request does not match any of the four operations "
    "above — when in doubt, or when the request asks for anything else "
    "(colors, styling, translation, etc.), respond NONE. "
    "Respond with nothing but the single matching word, in uppercase."
)

def validate_format_operation(operation):
    if not operation:
        raise FormatOperationError("LLM returned an empty operation")

    operation = operation.strip().upper()

    if operation == "NONE":
        raise FormatOperationError(
            "The request doesn't match any supported formatting operation. "
            "Supported operations: uppercase, lowercase, title case, "
            "trim whitespace."
        )

    if operation not in ALLOWED_FORMAT_OPERATIONS:
        raise FormatOperationError(
            f"LLM returned an unrecognized operation '{operation}'. "
            f"Allowed operations: {', '.join(sorted(ALLOWED_FORMAT_OPERATIONS))}"
        )

    return operation


def _call_llm_for_format(prompt):
    logger.info(f"Calling LLM (format) for prompt: {prompt!r}")

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=f"Natural language description: {prompt}",
        config=types.GenerateContentConfig(
            system_instruction=FORMAT_SYSTEM_PROMPT,
            max_output_tokens=20,
            temperature=0.0,
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        ),
    )

    raw_text = (response.text or "").strip()
    logger.info(f"Raw LLM format response: {raw_text!r}")
    return raw_text


def get_format_operation(prompt):
    key = _cache_key(prompt, "format")

    cached_operation = cache.get(key)
    if cached_operation is not None:
        logger.info(f"Cache HIT (format) for prompt: {prompt!r}")
        return cached_operation

    logger.info(f"Cache MISS (format) for prompt: {prompt!r} — calling LLM")

    raw_operation = _call_llm_for_format(prompt)
    validated_operation = validate_format_operation(raw_operation)

    cache.set(key, validated_operation, timeout=CACHE_TTL_SECONDS)
    logger.info(f"Cached (format) '{prompt}' -> '{validated_operation}'")

    return validated_operation