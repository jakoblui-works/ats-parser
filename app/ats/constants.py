"""The parser's limits and lists, all in one place. Nothing here is imported from settings: the child has none."""

import re

# Judgement calls: CVs are short, so these only stop abuse.
MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_PAGES = 10
PARSE_TIMEOUT_SECONDS = 30

# Well past any real CV. The result is kept in Redis and sent to the browser, and a 5 MB file can inflate far past it.
MAX_TEXT_CHARS = 200_000

# Enough to import the parser and read a real CV. Decompression bombs hit this and become a MemoryError.
MAX_CHILD_MEMORY_BYTES = 512 * 1024 * 1024
# Each child can use all of the above, and the worker runs many tasks at once.
MAX_CONCURRENT_PARSES = 2
# Past anything the text limit allows, escaped and repeated in sections. More means the child isn't behaving.
MAX_CHILD_OUTPUT_BYTES = 8 * 1024 * 1024
# How long a killed child gets to go away before the worker stops waiting for it.
CHILD_EXIT_GRACE_SECONDS = 2

# Lines whose bottom edges are this close read as one row, so a big name beside small text on one baseline stays whole.
ROW_TOLERANCE_POINTS = 3.0

# Below this average, blank pages aside, a document is only partly readable, as when a scan has a typed header.
MIN_READABLE_CHARS_PER_PAGE = 200

# What pdfminer writes for a character whose font has no Unicode mapping: extracted, but nobody can read it.
UNMAPPED_CHARACTER = re.compile(r"\(cid:\d+\)")
