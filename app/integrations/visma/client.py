import requests


class VismaClient:
    def __init__(
        self,
        access_token: str,
        api_url: str = "https://eaccountingapi.vismaonline.com/v2",
    ):
        self.access_token = access_token
        self.api_url = api_url.rstrip("/")

    def _headers(self) -> dict:
        return {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Bearer {self.access_token}",
        }

    def _get(self, path: str) -> dict:
        response = requests.get(
            f"{self.api_url}/{path.lstrip('/')}",
            headers=self._headers(),
            timeout=30,
        )
        response.raise_for_status()
        return response.json()

    def _post(self, path: str, payload: dict) -> dict:
        response = requests.post(
            f"{self.api_url}/{path.lstrip('/')}",
            json=payload,
            headers=self._headers(),
            timeout=30,
        )
        response.raise_for_status()
        return response.json()

    def get_company(self) -> dict:
        return self._get("company")

    def create_customer(self, customer: dict) -> dict:
        return self._post("customers", customer)

    def create_customer_invoice(self, invoice: dict) -> dict:
        return self._post("customerinvoices", invoice)