
from typing import NamedTuple, Optional

class Node(NamedTuple):
    id: int
    x: float
    y: float
    shard_id: int

class Edge(NamedTuple):
    u: int
    v: int
    weight: float



