"""Pure parsing/formatting logic, independent of Streamlit."""

import re
from typing import Any

from frontend.constants import (
    DIRECTIVE_HEADING_PATTERN,
    DIRECTIVE_HEADINGS,
    FALLBACK_CHARTER,
    FALLBACK_FINAL_ANSWER,
    FALLBACK_QUESTION,
)

_DIRECTIVE_HEADING_RE = re.compile(DIRECTIVE_HEADING_PATTERN, re.IGNORECASE)


def parse_directive(value: Any) -> list[tuple[str, str]]:
    """Parse the final directive into structured (heading, content) sections."""
    sections: list[tuple[str, list[str]]] = []
    current_heading: str | None = None
    current_lines: list[str] = []

    for line in str(value or "").splitlines():
        match = _DIRECTIVE_HEADING_RE.match(line.strip())
        if match:
            if current_heading is not None:
                sections.append((current_heading, current_lines))
            current_heading = next(
                heading
                for heading in DIRECTIVE_HEADINGS
                if heading.lower() == match.group(1).lower()
            )
            current_lines = []
        elif current_heading is not None:
            current_lines.append(line)
        else:
            current_lines.append(line)

    if current_heading is not None:
        sections.append((current_heading, current_lines))

    if not sections:
        return [("Recommendation", str(value or FALLBACK_FINAL_ANSWER))]
    return [
        (heading, "\n".join(lines).strip() or "No details returned.")
        for heading, lines in sections
    ]


def decision_brief_text(result: dict[str, Any], fallback_question: str | None = None) -> str:
    """Generate exportable decision brief text."""
    question = result.get("question") or fallback_question or FALLBACK_QUESTION
    return (
        f"AI COUNCIL | DECISION BRIEF\n{'=' * 32}"
        f"\n\nQUESTION\n{question}"
        f"\n\nDECISION CHARTER\n{result.get('decision_charter', FALLBACK_CHARTER)}"
        f"\n\nFINAL DIRECTIVE\n{result.get('final_answer', FALLBACK_FINAL_ANSWER)}\n"
        + (
            "\nSOURCES\n" + "\n".join(result.get("sources", [])) + "\n"
            if result.get("sources") else ""
        )
    )
