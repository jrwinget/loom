"""tests for shared graph utility functions."""

from loom.services.graph_utils import connected_components


def test_simple_pairs() -> None:
    """two connected pairs form one component."""
    pairs = [(0, 1), (1, 2)]
    result = connected_components(pairs, 3)
    assert len(result) == 1
    assert sorted(result[0]) == [0, 1, 2]


def test_empty_input() -> None:
    """no pairs with zero nodes returns empty."""
    result = connected_components([], 0)
    assert result == []


def test_empty_pairs_with_nodes() -> None:
    """no pairs but nodes exist returns singletons."""
    result = connected_components([], 3)
    assert len(result) == 3
    # each component is a single node
    sizes = sorted(len(c) for c in result)
    assert sizes == [1, 1, 1]


def test_disjoint_groups() -> None:
    """separate pairs form separate components."""
    pairs = [(0, 1), (2, 3)]
    result = connected_components(pairs, 4)
    # should have at least 2 components for the pairs
    groups = [sorted(c) for c in result]
    groups.sort()
    assert [0, 1] in groups
    assert [2, 3] in groups


def test_single_large_component() -> None:
    """chain of pairs forms one large component."""
    pairs = [(0, 1), (1, 2), (2, 3), (3, 4)]
    result = connected_components(pairs, 5)
    assert len(result) == 1
    assert sorted(result[0]) == [0, 1, 2, 3, 4]


def test_triangle() -> None:
    """fully connected triangle is one component."""
    pairs = [(0, 1), (1, 2), (0, 2)]
    result = connected_components(pairs, 3)
    assert len(result) == 1
    assert sorted(result[0]) == [0, 1, 2]
