"""Minimal Google Sheets API client.

Uses the same OAuth access token infrastructure as Google Mail.
For unit tests, inject MockGoogleSheetsClient instead of this class.
"""
from __future__ import annotations

import logging
from typing import Any, Protocol

import requests

logger = logging.getLogger(__name__)

_SHEETS_BASE_URL = "https://sheets.googleapis.com/v4/spreadsheets"


class SheetsClientProtocol(Protocol):
    """Interface that both the real client and the mock satisfy."""

    def append_row(
        self,
        spreadsheet_id: str,
        tab_name: str,
        values: list[Any],
    ) -> dict[str, Any]: ...

    def clear_range(
        self,
        spreadsheet_id: str,
        range_notation: str,
    ) -> dict[str, Any]: ...

    def update_values(
        self,
        spreadsheet_id: str,
        range_notation: str,
        values: list[list[Any]],
    ) -> dict[str, Any]: ...

    def ensure_tab(
        self,
        spreadsheet_id: str,
        tab_name: str,
    ) -> None: ...


class GoogleSheetsClient:
    """Real Google Sheets API client.

    Appends rows to a named tab via the Sheets v4 REST API.
    Raises RuntimeError on non-200 responses.
    """

    def __init__(self, access_token: str, timeout_seconds: int = 15):
        self._token = access_token
        self._timeout = timeout_seconds

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
        }

    def append_row(
        self,
        spreadsheet_id: str,
        tab_name: str,
        values: list[Any],
    ) -> dict[str, Any]:
        """Append a single row to *tab_name* in *spreadsheet_id*.

        Uses USER_ENTERED valueInputOption so dates/numbers are parsed.
        Returns the raw Sheets API response as a dict.
        Raises RuntimeError if the API returns a non-200 status.
        """
        # URL-encode the range to handle Swedish chars in sheet names
        range_notation = f"{tab_name}!A:A"
        from urllib.parse import quote
        url = (
            f"{_SHEETS_BASE_URL}/{spreadsheet_id}/values/"
            f"{quote(range_notation)}:append"
            "?valueInputOption=USER_ENTERED&insertDataOption=INSERT_ROWS"
        )
        body = {"values": [values]}
        response = requests.post(
            url,
            json=body,
            headers=self._headers(),
            timeout=self._timeout,
        )
        if response.status_code not in (200, 201):
            raise RuntimeError(
                f"Google Sheets append failed ({response.status_code}): "
                f"{response.text[:300]}"
            )
        logger.info(
            "Google Sheets: appended row to %s / %s",
            spreadsheet_id,
            tab_name,
        )
        return response.json()

    def clear_range(
        self,
        spreadsheet_id: str,
        range_notation: str,
    ) -> dict[str, Any]:
        """Clear values in *range_notation* without removing formatting."""
        from urllib.parse import quote

        url = (
            f"{_SHEETS_BASE_URL}/{spreadsheet_id}/values/"
            f"{quote(range_notation)}:clear"
        )
        response = requests.post(
            url,
            json={},
            headers=self._headers(),
            timeout=self._timeout,
        )
        if response.status_code not in (200, 201):
            raise RuntimeError(
                f"Google Sheets clear failed ({response.status_code}): "
                f"{response.text[:300]}"
            )
        logger.info(
            "Google Sheets: cleared range %s / %s",
            spreadsheet_id,
            range_notation,
        )
        return response.json()

    def update_values(
        self,
        spreadsheet_id: str,
        range_notation: str,
        values: list[list[Any]],
    ) -> dict[str, Any]:
        """Replace values in *range_notation* with *values*."""
        from urllib.parse import quote

        url = (
            f"{_SHEETS_BASE_URL}/{spreadsheet_id}/values/"
            f"{quote(range_notation)}"
            "?valueInputOption=USER_ENTERED"
        )
        response = requests.put(
            url,
            json={"values": values},
            headers=self._headers(),
            timeout=self._timeout,
        )
        if response.status_code not in (200, 201):
            raise RuntimeError(
                f"Google Sheets update failed ({response.status_code}): "
                f"{response.text[:300]}"
            )
        logger.info(
            "Google Sheets: updated range %s / %s (%s rows)",
            spreadsheet_id,
            range_notation,
            len(values),
        )
        return response.json()

    def ensure_tab(self, spreadsheet_id: str, tab_name: str) -> None:
        """Create *tab_name* if it does not already exist."""
        meta_url = f"{_SHEETS_BASE_URL}/{spreadsheet_id}?fields=sheets.properties.title"
        meta_response = requests.get(
            meta_url,
            headers=self._headers(),
            timeout=self._timeout,
        )
        if meta_response.status_code != 200:
            raise RuntimeError(
                f"Google Sheets metadata failed ({meta_response.status_code}): "
                f"{meta_response.text[:300]}"
            )
        titles = [
            sheet.get("properties", {}).get("title")
            for sheet in meta_response.json().get("sheets", [])
        ]
        if tab_name in titles:
            return

        batch_url = f"{_SHEETS_BASE_URL}/{spreadsheet_id}:batchUpdate"
        batch_response = requests.post(
            batch_url,
            json={"requests": [{"addSheet": {"properties": {"title": tab_name}}}]},
            headers=self._headers(),
            timeout=self._timeout,
        )
        if batch_response.status_code not in (200, 201):
            raise RuntimeError(
                f"Google Sheets add tab failed ({batch_response.status_code}): "
                f"{batch_response.text[:300]}"
            )
        logger.info("Google Sheets: created tab %s in %s", tab_name, spreadsheet_id)


class MockGoogleSheetsClient:
    """In-memory mock for unit tests.

    Records every append_row call so tests can assert on exact values.
    """

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.clear_calls: list[dict[str, Any]] = []
        self.update_calls: list[dict[str, Any]] = []
        self.ensure_tab_calls: list[dict[str, Any]] = []
        self.tabs: set[str] = set()

    def append_row(
        self,
        spreadsheet_id: str,
        tab_name: str,
        values: list[Any],
    ) -> dict[str, Any]:
        self.calls.append(
            {
                "spreadsheet_id": spreadsheet_id,
                "tab_name": tab_name,
                "values": values,
            }
        )
        return {
            "spreadsheetId": spreadsheet_id,
            "tableRange": f"{tab_name}!A1:L1",
            "updates": {"updatedRows": 1, "updatedColumns": len(values)},
        }

    def clear_range(
        self,
        spreadsheet_id: str,
        range_notation: str,
    ) -> dict[str, Any]:
        self.clear_calls.append(
            {
                "spreadsheet_id": spreadsheet_id,
                "range_notation": range_notation,
            }
        )
        return {"clearedRange": range_notation}

    def update_values(
        self,
        spreadsheet_id: str,
        range_notation: str,
        values: list[list[Any]],
    ) -> dict[str, Any]:
        self.update_calls.append(
            {
                "spreadsheet_id": spreadsheet_id,
                "range_notation": range_notation,
                "values": values,
            }
        )
        return {
            "spreadsheetId": spreadsheet_id,
            "updatedRange": range_notation,
            "updatedRows": len(values),
            "updatedColumns": max((len(row) for row in values), default=0),
        }

    def ensure_tab(self, spreadsheet_id: str, tab_name: str) -> None:
        self.ensure_tab_calls.append(
            {
                "spreadsheet_id": spreadsheet_id,
                "tab_name": tab_name,
            }
        )
        self.tabs.add(tab_name)
