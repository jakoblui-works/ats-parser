"""Feature scoring, as a basic ATS picks a field: each candidate scores the weights of the features it has."""

from collections.abc import Callable, Sequence

type Feature[T] = tuple[Callable[[T], bool], int]


def best[T](
    candidates: Sequence[T], features: Sequence[Feature[T]], required: Callable[[T], bool], *, above: int | None = None
) -> T | None:
    """The candidate passing `required` with the highest score; a tie goes to the earliest, and none passing to None.
    With `above`, the winner must also score strictly above it, or there is none."""
    winner: T | None = None
    top = 0
    for candidate in candidates:
        if not required(candidate):
            continue
        score = sum(weight for has, weight in features if has(candidate))
        if winner is None or score > top:
            winner, top = candidate, score
    return winner if winner is not None and (above is None or top > above) else None
