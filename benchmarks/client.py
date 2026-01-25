"""HTTP client for interacting with the routing API."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

import requests


@dataclass
class RouteResult:
    """Result from a routing request."""

    success: bool
    latency_ms: float
    path_found: bool
    segments_count: int
    distance_m: float
    error: Optional[str] = None
    response_data: Optional[Dict[str, Any]] = None


class RoutingClient:
    """Client for the distributed graph routing API.
    
    Thread-safe: uses thread-local sessions for concurrent requests.
    """

    def __init__(self, base_url: str, timeout: float = 60.0):
        """
        Initialize the routing client.

        Args:
            base_url: Base URL of the routing API (e.g., "http://localhost:8080")
            timeout: Request timeout in seconds
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._local = threading.local()

    def _get_session(self) -> requests.Session:
        """Get thread-local session, creating one if needed."""
        if not hasattr(self._local, "session"):
            self._local.session = requests.Session()
        return self._local.session

    def route(self, start_lat: float, start_lng: float, end_lat: float, end_lng: float) -> RouteResult:
        """
        Request a route from start to end coordinates.

        Args:
            start_lat: Starting latitude
            start_lng: Starting longitude
            end_lat: Ending latitude
            end_lng: Ending longitude

        Returns:
            RouteResult with timing and response data
        """
        url = f"{self.base_url}/v1/route"
        payload = {
            "start": {"lat": start_lat, "lng": start_lng},
            "end": {"lat": end_lat, "lng": end_lng},
        }

        start_time = time.perf_counter()
        try:
            response = self._get_session().post(url, json=payload, timeout=self.timeout)
            latency_ms = (time.perf_counter() - start_time) * 1000

            if response.status_code != 200:
                return RouteResult(
                    success=False,
                    latency_ms=latency_ms,
                    path_found=False,
                    segments_count=0,
                    distance_m=0,
                    error=f"HTTP {response.status_code}: {response.text[:200]}",
                )

            data = response.json()
            return RouteResult(
                success=True,
                latency_ms=latency_ms,
                path_found=data.get("path_found", False),
                segments_count=data.get("summary", {}).get("segments_count", 0),
                distance_m=data.get("summary", {}).get("distance_m", 0),
                response_data=data,
            )

        except requests.exceptions.Timeout:
            latency_ms = (time.perf_counter() - start_time) * 1000
            return RouteResult(
                success=False,
                latency_ms=latency_ms,
                path_found=False,
                segments_count=0,
                distance_m=0,
                error="Request timed out",
            )
        except requests.exceptions.ConnectionError as e:
            latency_ms = (time.perf_counter() - start_time) * 1000
            return RouteResult(
                success=False,
                latency_ms=latency_ms,
                path_found=False,
                segments_count=0,
                distance_m=0,
                error=f"Connection error: {str(e)[:100]}",
            )
        except Exception as e:
            latency_ms = (time.perf_counter() - start_time) * 1000
            return RouteResult(
                success=False,
                latency_ms=latency_ms,
                path_found=False,
                segments_count=0,
                distance_m=0,
                error=f"Unexpected error: {str(e)[:100]}",
            )

    def health_check(self) -> bool:
        """Check if the API is reachable."""
        try:
            response = self._get_session().get(f"{self.base_url}/healthz", timeout=5.0)
            return response.status_code == 200
        except Exception:
            return False

    def close(self) -> None:
        """Close thread-local sessions (call from each thread if needed)."""
        if hasattr(self._local, "session"):
            self._local.session.close()
