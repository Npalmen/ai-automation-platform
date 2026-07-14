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


class MockGoogleSheetsClient:
    """In-memory mock for unit tests.

    Records every append_row call so tests can assert on exact values.
    """

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

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
