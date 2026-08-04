from __future__ import annotations

import re
from pathlib import Path
from typing import Any


DOCUMENT_NUMBER_PATTERN = re.compile(r"^\s*(\d{4})\s+-")

TITLE_REPLACEMENTS = (
    (
        re.compile(
            r"\bIT Asset Endpoint Management Policy\b",
            flags=re.IGNORECASE,
        ),
        "IT Asset & Endpoint Management Policy",
    ),
)


def extract_document_number(document_name: str) -> str | None:
    match = DOCUMENT_NUMBER_PATTERN.match(document_name or "")
    return match.group(1) if match else None


def normalize_source_title(document_name: str) -> str:
    title = Path(document_name or "Unknown policy").stem
    title = re.sub(r"\s+", " ", title).strip()

    for pattern, replacement in TITLE_REPLACEMENTS:
        title = pattern.sub(replacement, title)

    return title or "Unknown policy"


def source_title_without_number(document_name: str) -> str:
    title = normalize_source_title(document_name)
    return re.sub(r"^\d{4}\s+-\s*", "", title).strip() or title


def source_dedup_key(
    *,
    document_name: str,
    document_number: str | None,
    page_number: int | None,
) -> tuple[str, int | None]:
    normalized_name = normalize_source_title(document_name).lower()
    return (
        (document_number or normalized_name).lower(),
        page_number,
    )


def source_document_key(
    *,
    document_name: str,
    document_number: str | None,
) -> str:
    normalized_name = normalize_source_title(document_name).lower()
    return (document_number or normalized_name).lower()


def format_source_line(
    *,
    document_name: str,
    page_number: int | None = None,
    pages: list[int] | None = None,
) -> str:
    unique_pages = sorted(
        {
            page
            for page in (pages or [])
            if isinstance(page, int) and page > 0
        }
    )

    if unique_pages:
        page_label = (
            f"Page {unique_pages[0]}"
            if len(unique_pages) == 1
            else "Pages " + ", ".join(str(page) for page in unique_pages)
        )
    else:
        page_label = (
            f"Page {page_number}"
            if page_number
            else "Page unavailable"
        )

    return f"• {normalize_source_title(document_name)} — {page_label}"


def safe_int(value: Any) -> int | None:
    try:
        converted = int(value)
    except (TypeError, ValueError):
        return None

    return converted if converted > 0 else None
