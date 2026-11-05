"""Rows as the stages see them, for tests that feed the stages text directly."""

from hypothesis import strategies as st

from ats_parser.extraction import Line

# Any one size will do: these rows only stand for plain body text, all of it alike.
BODY_SIZE = 10.0


def plain(texts: list[str]) -> list[Line]:
    """Rows of plain body text: not bold, all the same size."""
    return [Line(text=text, bold=False, size=BODY_SIZE) for text in texts]


# What separates two sections of a kind: a row with nothing but whitespace on it, of any kind, or none at all.
WHITESPACE = [char for char in map(chr, range(0x110000)) if char.isspace()]
SECTION_BREAKS = st.text(alphabet=st.sampled_from(WHITESPACE), max_size=4)
