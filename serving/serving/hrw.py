from __future__ import annotations

import hashlib
from typing import Iterable, Sequence


def _score(key: str, node: str) -> int:
    digest = hashlib.sha256(f"{key}-{node}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big", signed=False)


def pick_node(key: str, nodes: Sequence[str]) -> str:
    if not nodes:
        raise ValueError("nodes must be non-empty")
    best_node = nodes[0]
    best_score = _score(key, best_node)
    for node in nodes[1:]:
        score = _score(key, node)
        if score > best_score:
            best_score = score
            best_node = node
    return best_node
