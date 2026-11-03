from typing import Annotated, Literal

from pydantic import BaseModel, Field

Visibility = Literal["readable", "partial", "invisible"]
SectionKind = Literal["summary", "experience", "education", "skills", "other"]
WarningCode = Literal[
    "no_text_layer",
    "little_text",
    "scrambled_order",
    "missing_contact",
    "missing_sections",
    "unparsed_dates",
]
RejectionReason = Literal["too_many_pages", "encrypted", "corrupt", "timed_out"]


# The result's shape. Field names are the contract (see tests/ats/test_contract.py).
class Contact(BaseModel):
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    location: str | None = None
    links: list[str] = []


class Section(BaseModel):
    kind: SectionKind
    heading: str
    text: str


class Experience(BaseModel):
    title: str | None = None
    company: str | None = None
    start: str | None = None
    end: str | None = None
    months: int | None = None


class Education(BaseModel):
    institution: str | None = None
    qualification: str | None = None
    start: str | None = None
    end: str | None = None


class ParseResult(BaseModel):
    visibility: Visibility
    page_count: int
    character_count: int
    text: str
    contact: Contact = Contact()
    sections: list[Section] = []
    experience: list[Experience] = []
    experience_months: int | None = None
    education: list[Education] = []
    skills: list[str] = []
    warnings: list[WarningCode] = []


class Parsed(BaseModel):
    outcome: Literal["parsed"] = "parsed"
    result: ParseResult


class Rejected(BaseModel):
    outcome: Literal["rejected"] = "rejected"
    reason: RejectionReason


ParseOutcome = Annotated[Parsed | Rejected, Field(discriminator="outcome")]
