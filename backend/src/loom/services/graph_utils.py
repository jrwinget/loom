"""shared graph utility functions."""


def connected_components(
    pairs: list[tuple[int, int]],
    n: int,
) -> list[list[int]]:
    """build connected components from edge pairs.

    uses union-find over integer node indices [0, n).
    returns list of components, each a sorted list of ints.
    """
    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for a, b in pairs:
        union(a, b)

    groups: dict[int, list[int]] = {}
    for node in range(n):
        root = find(node)
        groups.setdefault(root, []).append(node)

    return [sorted(g) for g in groups.values()]
