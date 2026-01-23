from s2sphere import CellId, LatLng

S2_LEVEL = 9


def shard_id_for_lat_lng(lat: float, lng: float) -> int:
    lat_lng = LatLng.from_degrees(lat, lng)
    return int(CellId.from_lat_lng(lat_lng).parent(S2_LEVEL).id())
