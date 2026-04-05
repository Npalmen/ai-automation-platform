import requests


class MicrosoftMailClient:
    def __init__(
        self,
        access_token: str,
        api_url: str = "https://graph.microsoft.com/v1.0",
    ):
        self.access_token = access_token
        self.api_url = api_url.rstrip("/")

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def get_me(self) -> dict:
        response = requests.get(
            f"{self.api_url}/me",
            headers=self._headers(),
            timeout=30,
        )
        response.raise_for_status()
        return response.json()

    def send_mail(self, message: dict, save_to_sent_items: bool = True) -> dict:
        response = requests.post(
            f"{self.api_url}/me/sendMail",
            headers=self._headers(),
            json={
                "message": message,
                "saveToSentItems": save_to_sent_items,
            },
            timeout=30,
        )
        response.raise_for_status()
        return {"status_code": response.status_code, "message": "sent"}