from dataclasses import dataclass, field
from typing import Literal

Visibility = Literal["readable", "partial", "invisible"]
SectionKind = Literal["summary", "experience", "education", "skills", "other"]
WarningCode = Literal[
    "no_text_layer",
    "little_text",
    "scrambled_order",  # Never produced; see CLAUDE.md.
    "missing_contact",
    "missing_sections",
    "unparsed_dates",  # Never produced; see CLAUDE.md.
]
RejectionReason = Literal["too_many_pages", "encrypted", "corrupt", "timed_out"]


# The outcome's shape. Field names and order are the contract: `schema/parse_outcome.schema.json` is generated from
# these by `scripts/generate_schema.py`. Plain dataclasses: the parser's only runtime dependency is pdfminer.
@dataclass(frozen=True)
class Contact:
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    location: str | None = None
    links: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Section:
    kind: SectionKind
    heading: str
    text: str


@dataclass(frozen=True)
class Experience:
    title: str | None = None
    company: str | None = None
    start: str | None = None
    end: str | None = None
    months: int | None = None


@dataclass(frozen=True)
class Education:
    institution: str | None = None
    qualification: str | None = None
    start: str | None = None
    end: str | None = None


@dataclass(frozen=True)
class ParseResult:
    visibility: Visibility
    page_count: int
    character_count: int
    text: str
    contact: Contact = field(default_factory=Contact)
    sections: list[Section] = field(default_factory=list)
    experience: list[Experience] = field(default_factory=list)
    experience_months: int | None = None
    education: list[Education] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)  # Never filled in; see CLAUDE.md.
    warnings: list[WarningCode] = field(default_factory=list)


# `outcome` comes first in each, with a default, so the required field after it must be keyword-only.
@dataclass(frozen=True, kw_only=True)
class Parsed:
    outcome: Literal["parsed"] = "parsed"
    result: ParseResult


@dataclass(frozen=True, kw_only=True)
class Rejected:
    outcome: Literal["rejected"] = "rejected"
    reason: RejectionReason


ParseOutcome = Parsed | Rejected
