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

    def _get(self, path: str, params: dict | None = None) -> dict:
        response = requests.get(
            f"{self.api_url}/{path.lstrip('/')}",
            headers=self._headers(),
            params=params,
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

    # ------------------------------------------------------------------
    # Read-only methods
    # ------------------------------------------------------------------

    def get_company_information(self) -> dict:
        return self._get("companyinformation")

    def get_customers(self, limit: int = 50) -> list[dict]:
        """Return a list of customer objects from Fortnox."""
        data = self._get("customers", params={"limit": limit})
        return (data.get("Customers") or data.get("customers") or [])

    def get_articles(self, limit: int = 50) -> list[dict]:
        """Return a list of article objects from Fortnox."""
        data = self._get("articles", params={"limit": limit})
        return (data.get("Articles") or data.get("articles") or [])

    def get_invoices(self, limit: int = 50) -> list[dict]:
        """Return a list of invoice objects from Fortnox."""
        data = self._get("invoices", params={"limit": limit})
        return (data.get("Invoices") or data.get("invoices") or [])

    def find_customer_by_email(self, email: str) -> dict | None:
        """Return the first customer matching email, or None."""
        customers = self.get_customers(limit=500)
        for c in customers:
            if (c.get("Email") or c.get("email") or "").lower() == email.lower():
                return c
        return None

    def find_customer_by_name(self, name: str) -> dict | None:
        """Return the first customer whose name contains name (case-insensitive), or None."""
        needle = name.lower()
        customers = self.get_customers(limit=500)
        for c in customers:
            cname = (c.get("Name") or c.get("name") or "").lower()
            if needle in cname:
                return c
        return None

    def find_recent_invoices_by_customer(self, customer_number: str, limit: int = 10) -> list[dict]:
        """Return recent invoices for a customer number."""
        data = self._get("invoices", params={"customernumber": customer_number, "limit": limit})
        return (data.get("Invoices") or data.get("invoices") or [])

    def find_invoice_by_document_number(self, document_number: str) -> dict | None:
        """Return a single invoice by document number, or None."""
        try:
            data = self._get(f"invoices/{document_number}")
            return data.get("Invoice") or data.get("invoice") or None
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code == 404:
                return None
            raise

    # ------------------------------------------------------------------
    # Write methods
    # ------------------------------------------------------------------

    def create_customer(self, customer: dict) -> dict:
        return self._post("customers", {"Customer": customer})

    def create_invoice(self, invoice: dict) -> dict:
        return self._post("invoices", {"Invoice": invoice})