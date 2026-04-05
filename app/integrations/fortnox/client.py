import requests


class FortnoxClient:
    def __init__(
        self,
        access_token: str,
        client_secret: str,
        api_url: str = "https://api.fortnox.se/3",
    ):
        self.access_token = access_token
        self.client_secret = client_secret
        self.api_url = api_url.rstrip("/")

    def _headers(self) -> dict:
        return {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Access-Token": self.access_token,
            "Client-Secret": self.client_secret,
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

    def get_company_information(self) -> dict:
        return self._get("companyinformation")

    def create_customer(self, customer: dict) -> dict:
        return self._post("customers", {"Customer": customer})

    def create_invoice(self, invoice: dict) -> dict:
        return self._post("invoices", {"Invoice": invoice})