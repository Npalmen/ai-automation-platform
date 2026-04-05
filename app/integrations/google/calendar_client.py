import requests


class GoogleCalendarClient:
    def __init__(
        self,
        access_token: str,
        api_url: str = "https://www.googleapis.com/calendar/v3",
    ):
        self.access_token = access_token
        self.api_url = api_url.rstrip("/")

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def get_calendar(self, calendar_id: str = "primary") -> dict:
        response = requests.get(
            f"{self.api_url}/calendars/{calendar_id}",
            headers=self._headers(),
            timeout=30,
        )
        response.raise_for_status()
        return response.json()

    def create_event(self, calendar_id: str, event: dict) -> dict:
        response = requests.post(
            f"{self.api_url}/calendars/{calendar_id}/events",
            headers=self._headers(),
            json=event,
            timeout=30,
        )
        response.raise_for_status()
        return response.json()