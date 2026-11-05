"""`best` picks by features, generically: any candidates, any features and weights."""

from collections.abc import Callable

from hypothesis import given
from hypothesis import strategies as st

from ats_parser.scoring import Feature, best

# A candidate is its place in the list and a key; features look at the key only, so different places can tie.
Candidate = tuple[int, int]

predicates = st.functions(like=lambda key: True, returns=st.booleans(), pure=True)
keys = st.lists(st.integers(min_value=0, max_value=3), max_size=12)
key_features = st.lists(st.tuples(predicates, st.integers(min_value=-20, max_value=20)), max_size=6)


def _on_key(features: list[tuple[Callable[[int], bool], int]]) -> list[Feature[Candidate]]:
    return [(_looks_at_key(has), weight) for has, weight in features]


def _looks_at_key(has: Callable[[int], bool]) -> Callable[[Candidate], bool]:
    return lambda candidate: has(candidate[1])


def _score(candidate: Candidate, features: list[Feature[Candidate]]) -> int:
    return sum(weight for has, weight in features if has(candidate))


@given(keys=keys, features=key_features)
def test_nothing_passing_required_gives_none(
    keys: list[int], features: list[tuple[Callable[[int], bool], int]]
) -> None:
    candidates = list(enumerate(keys))

    assert best(candidates, _on_key(features), lambda candidate: False) is None


@given(keys=keys, features=key_features, required=predicates)
def test_the_winner_passes_required_and_has_the_top_score_and_a_tie_goes_to_the_earliest(
    keys: list[int], features: list[tuple[Callable[[int], bool], int]], required: Callable[[int], bool]
) -> None:
    candidates = list(enumerate(keys))
    scored = _on_key(features)
    passing = [candidate for candidate in candidates if required(candidate[1])]

    winner = best(candidates, scored, lambda candidate: required(candidate[1]))

    if not passing:
        assert winner is None
        return
    assert winner is not None
    assert required(winner[1])
    top = max(_score(candidate, scored) for candidate in passing)
    assert winner == next(candidate for candidate in passing if _score(candidate, scored) == top)


@given(size=st.integers(min_value=2, max_value=10), features=key_features, key=st.integers(min_value=0, max_value=3))
def test_among_alike_candidates_the_first_wins(
    size: int, features: list[tuple[Callable[[int], bool], int]], key: int
) -> None:
    candidates = [(place, key) for place in range(size)]

    assert best(candidates, _on_key(features), lambda candidate: True) == (0, key)


# --- `above`: a winner must score strictly above it ---

thresholds = st.integers(min_value=-130, max_value=130)


@given(keys=keys, features=key_features, required=predicates, above=thresholds)
def test_with_above_only_a_candidate_scoring_above_it_wins_and_a_tie_goes_to_the_earliest(
    keys: list[int], features: list[tuple[Callable[[int], bool], int]], required: Callable[[int], bool], above: int
) -> None:
    candidates = list(enumerate(keys))
    scored = _on_key(features)
    passing = [candidate for candidate in candidates if required(candidate[1])]

    winner = best(candidates, scored, lambda candidate: required(candidate[1]), above=above)

    if not passing or max(_score(candidate, scored) for candidate in passing) <= above:
        assert winner is None
        return
    top = max(_score(candidate, scored) for candidate in passing)
    assert winner == next(candidate for candidate in passing if _score(candidate, scored) == top)


@given(keys=keys.filter(bool), features=key_features)
def test_above_is_strict_the_top_score_itself_gives_none_and_one_below_it_gives_the_usual_winner(
    keys: list[int], features: list[tuple[Callable[[int], bool], int]]
) -> None:
    candidates = list(enumerate(keys))
    scored = _on_key(features)
    top = max(_score(candidate, scored) for candidate in candidates)

    def anything(candidate: Candidate) -> bool:
        return True

    assert best(candidates, scored, anything, above=top) is None
    assert best(candidates, scored, anything, above=top - 1) == best(candidates, scored, anything)


@given(keys=keys, features=key_features, required=predicates)
def test_above_none_is_the_same_as_leaving_it_out(
    keys: list[int], features: list[tuple[Callable[[int], bool], int]], required: Callable[[int], bool]
) -> None:
    candidates = list(enumerate(keys))
    scored = _on_key(features)

    def passes(candidate: Candidate) -> bool:
        return required(candidate[1])

    assert best(candidates, scored, passes, above=None) == best(candidates, scored, passes)
