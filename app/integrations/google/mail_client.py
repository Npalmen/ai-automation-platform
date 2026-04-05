# app/integrations/google/mail_client.py

import requests


class GoogleMailClient:
    def __init__(
        self,
        access_token: str,
        api_url: str = "https://gmail.googleapis.com/gmail/v1",
    ):
        self.access_token = access_token
        self.api_url = api_url.rstrip("/")

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def get_profile(self, user_id: str = "me") -> dict:
        response = requests.get(
            f"{self.api_url}/users/{user_id}/profile",
            headers=self._headers(),
            timeout=30,
        )
        response.raise_for_status()
        return response.json()

    def send_message(self, raw_message_base64: str, user_id: str = "me") -> dict:
        response = requests.post(
            f"{self.api_url}/users/{user_id}/messages/send",
            headers=self._headers(),
            json={"raw": raw_message_base64},
            timeout=30,
        )
        response.raise_for_status()
        return response.json()