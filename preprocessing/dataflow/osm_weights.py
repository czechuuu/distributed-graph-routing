import math
import re
from typing import Optional

EARTH_RADIUS_M = 6_371_000.0

_SPEED_RE = re.compile(r"([0-9]+(?:\\.[0-9]+)?)")
_INVALID_MAXSPEED = {"signals", "walk", "none", "variable", "unposted", "unknown"}

_DEFAULT_SPEED_KPH = {
    "motorway": 110.0,
    "motorway_link": 70.0,
    "trunk": 90.0,
    "trunk_link": 60.0,
    "primary": 80.0,
    "primary_link": 50.0,
    "secondary": 70.0,
    "secondary_link": 50.0,
    "tertiary": 60.0,
    "tertiary_link": 40.0,
    "unclassified": 50.0,
    "residential": 35.0,
    "living_street": 10.0,
    "service": 20.0,
    "road": 40.0,
}

_SURFACE_SPEED_CAP_KPH = {
    "unpaved": 30.0,
    "gravel": 30.0,
    "ground": 25.0,
    "dirt": 20.0,
    "sand": 15.0,
    "mud": 10.0,
}

_TRACKTYPE_SPEED_CAP_KPH = {
    "grade1": 40.0,
    "grade2": 30.0,
    "grade3": 20.0,
    "grade4": 15.0,
    "grade5": 10.0,
}

_SERVICE_SPEED_CAP_KPH = {
    "parking_aisle": 10.0,
    "driveway": 10.0,
    "alley": 15.0,
}


def parse_maxspeed_kph(raw: Optional[str]) -> Optional[float]:
    if not raw:
        return None
    value = raw.strip().lower()
    if not value or value in _INVALID_MAXSPEED:
        return None
    match = _SPEED_RE.search(value)
    if not match:
        return None
    speed = float(match.group(1))
    if "mph" in value:
        return speed * 1.60934
    return speed


def default_speed_kph(
    highway: Optional[str],
    surface: Optional[str],
    tracktype: Optional[str],
    service: Optional[str],
) -> float:
    base = _DEFAULT_SPEED_KPH.get(highway or "", 30.0)
    caps = []
    if surface:
        caps.append(_SURFACE_SPEED_CAP_KPH.get(surface, base))
    if tracktype:
        caps.append(_TRACKTYPE_SPEED_CAP_KPH.get(tracktype, base))
    if service:
        caps.append(_SERVICE_SPEED_CAP_KPH.get(service, base))
    if caps:
        return min([base, *caps])
    return base


def choose_speed_kph(
    highway: Optional[str],
    maxspeed: Optional[str],
    maxspeed_forward: Optional[str],
    maxspeed_backward: Optional[str],
    surface: Optional[str],
    tracktype: Optional[str],
    service: Optional[str],
    direction: int,
) -> float:
    chosen = None
    if direction > 0:
        chosen = parse_maxspeed_kph(maxspeed_forward) or parse_maxspeed_kph(maxspeed)
    elif direction < 0:
        chosen = parse_maxspeed_kph(maxspeed_backward) or parse_maxspeed_kph(maxspeed)
    else:
        chosen = parse_maxspeed_kph(maxspeed)
    if chosen is None:
        return default_speed_kph(highway, surface, tracktype, service)
    cap = default_speed_kph(highway, surface, tracktype, service)
    return min(chosen, cap)


def speed_kph_to_mps(speed_kph: float) -> float:
    return speed_kph * (1000.0 / 3600.0)


def distance_equirectangular_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    lam1 = math.radians(lon1)
    lam2 = math.radians(lon2)
    dphi = phi2 - phi1
    dlam = lam2 - lam1
    mean_phi = (phi1 + phi2) / 2.0
    dx = EARTH_RADIUS_M * dlam * math.cos(mean_phi)
    dy = EARTH_RADIUS_M * dphi
    return math.hypot(dx, dy)


def weight_seconds(length_m: float, speed_kph: float) -> int:
    speed_mps = speed_kph_to_mps(speed_kph)
    if speed_mps <= 0:
        return 0
    return int(round(length_m / speed_mps))
