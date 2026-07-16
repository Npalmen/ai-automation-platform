import requests

# Read-only company context for the authorized OAuth token (Visma eAccounting API v2).
COMPANY_SETTINGS_PATH = "companysettings"


def build_api_url(api_url: str, path: str) -> str:
    """Join API base URL and resource path without duplicating version segments."""
    return f"{api_url.rstrip('/')}/{path.lstrip('/')}"


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
            build_api_url(self.api_url, path),
            headers=self._headers(),
            timeout=30,
        )
        response.raise_for_status()
        return response.json()

    def _post(self, path: str, payload: dict) -> dict:
        response = requests.post(
            build_api_url(self.api_url, path),
            json=payload,
            headers=self._headers(),
            timeout=30,
        )
        response.raise_for_status()
        return response.json()

    def get_company(self) -> dict:
        """Return company settings for the token-authorized company."""
        return self._get(COMPANY_SETTINGS_PATH)

    def get_fiscal_years(self) -> list[dict]:
        result = self._get("fiscalyears")
        if isinstance(result, list):
            return result
        if isinstance(result, dict):
            return list(result.get("Data") or result.get("data") or [])
        return []

    def get_terms_of_payment(self) -> list[dict]:
        result = self._get("termsofpayments")
        if isinstance(result, list):
            return result
        if isinstance(result, dict):
            return list(result.get("Data") or result.get("data") or [])
        return []

    def get_articles(self, *, page_size: int = 10) -> list[dict]:
        result = self._get(f"articles?$pagesize={page_size}")
        if isinstance(result, list):
            return result
        if isinstance(result, dict):
            return list(result.get("Data") or result.get("data") or [])
        return []

    def find_customers_by_name_contains(self, name_fragment: str, *, page_size: int = 5) -> list[dict]:
        fragment = (name_fragment or "").replace("'", "''")
        if not fragment:
            return []
        path = f"customers?$filter=contains(Name,'{fragment}')&$pagesize={page_size}"
        result = self._get(path)
        if isinstance(result, list):
            return result
        if isinstance(result, dict):
            return list(result.get("Data") or result.get("data") or [])
        return []

    def create_customer(self, customer: dict) -> dict:
        return self._post("customers", customer)

    def create_customer_invoice(self, invoice: dict) -> dict:
        return self._post("customerinvoices", invoice)