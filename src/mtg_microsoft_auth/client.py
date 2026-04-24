from __future__ import annotations

import time

import httpx


class GraphClient:
    BASE_URL = "https://graph.microsoft.com/v1.0"

    def __init__(self, auth_session) -> None:
        self.auth_session = auth_session

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.auth_session.acquire_token()}",
            "Accept": "application/json",
        }

    def _request_with_retry(self, method: str, url: str, params: dict | None = None, json: dict | None = None):
        retries = self.auth_session.config.request_retry_count
        base_wait = self.auth_session.config.request_retry_base_seconds
        with httpx.Client(timeout=30.0) as client:
            for attempt in range(retries + 1):
                response = client.request(method, url, headers=self._headers(), params=params, json=json)
                if response.status_code < 400:
                    return response
                if response.status_code == 429 and attempt < retries:
                    retry_after = response.headers.get("Retry-After")
                    wait_seconds = int(retry_after) if retry_after and retry_after.isdigit() else base_wait * (attempt + 1)
                    time.sleep(wait_seconds)
                    continue
                response.raise_for_status()
        raise RuntimeError("Graph request failed after retries")

    def get(self, path: str, params: dict | None = None) -> dict:
        response = self._request_with_retry("GET", f"{self.BASE_URL}{path}", params=params)
        return response.json()

    def get_all(self, path: str, params: dict | None = None) -> dict:
        items = []
        next_url = f"{self.BASE_URL}{path}"
        request_params = params
        while next_url:
            response = self._request_with_retry("GET", next_url, params=request_params)
            payload = response.json()
            items.extend(payload.get("value", []))
            next_url = payload.get("@odata.nextLink")
            request_params = None
        return {"value": items}

    def post(self, path: str, payload: dict) -> dict:
        response = self._request_with_retry("POST", f"{self.BASE_URL}{path}", json=payload)
        return response.json() if response.content else {}

    def patch(self, path: str, payload: dict) -> dict:
        response = self._request_with_retry("PATCH", f"{self.BASE_URL}{path}", json=payload)
        return response.json() if response.content else {}

    def delete(self, path: str) -> None:
        self._request_with_retry("DELETE", f"{self.BASE_URL}{path}")

