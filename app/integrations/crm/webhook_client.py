import httpx


class CRMWebhookClient:
    def __init__(self, base_url: str, api_key: str | None = None):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    async def send(self, payload: dict, idempotency_key: str):
        headers = {
            "Content-Type": "application/json",
            "Idempotency-Key": idempotency_key,
        }

        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                f"{self.base_url}/event",
                json=payload,
                headers=headers,
            )

        return response