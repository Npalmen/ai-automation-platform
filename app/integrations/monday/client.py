# app/integrations/monday/client.py

import json
import requests


class MondayClient:
    def __init__(self, api_key: str, api_url: str = "https://api.monday.com/v2"):
        self.api_key = api_key
        self.api_url = api_url.rstrip("/")

    def _post(self, query: str, variables: dict | None = None) -> dict:
        response = requests.post(
            self.api_url,
            json={
                "query": query,
                "variables": variables or {},
            },
            headers={
                "Authorization": self.api_key,
                "Content-Type": "application/json",
            },
            timeout=20,
        )
        response.raise_for_status()

        data = response.json()

        if "errors" in data and data["errors"]:
            messages = "; ".join(e.get("message", str(e)) for e in data["errors"])
            raise RuntimeError(f"monday API error: {messages}")

        return data

    def get_me(self) -> dict:
        query = """
        query {
          me {
            id
            name
            email
          }
        }
        """
        return self._post(query=query)

    def create_item(
        self,
        board_id: int,
        item_name: str,
        group_id: str | None = None,
        column_values: dict | None = None,
    ) -> dict:
        query = """
        mutation ($board_id: ID!, $item_name: String!, $group_id: String, $column_values: JSON) {
          create_item(
            board_id: $board_id,
            item_name: $item_name,
            group_id: $group_id,
            column_values: $column_values
          ) {
            id
            name
            state
            board {
              id
              name
            }
          }
        }
        """

        # monday GraphQL expects column_values as a JSON string, not a dict.
        if column_values is None:
            cv_str = "{}"
        elif isinstance(column_values, str):
            cv_str = column_values
        else:
            cv_str = json.dumps(column_values)

        variables = {
            "board_id": str(board_id),
            "item_name": item_name,
            "group_id": group_id,
            "column_values": cv_str,
        }

        return self._post(query=query, variables=variables)

    def get_boards(self, limit: int = 50) -> list[dict]:
        """
        Read-only: fetch board structure (id, name, description, groups, columns).
        Does NOT fetch items.  Used by the workflow scanner only.
        """
        query = """
        query ($limit: Int) {
          boards(limit: $limit) {
            id
            name
            description
            groups {
              id
              title
            }
            columns {
              id
              title
              type
            }
          }
        }
        """
        data = self._post(query=query, variables={"limit": limit})
        return data.get("data", {}).get("boards") or []

    def create_update(self, item_id: int, body: str) -> dict:
        query = """
        mutation ($item_id: ID!, $body: String!) {
          create_update(item_id: $item_id, body: $body) {
            id
            body
          }
        }
        """

        variables = {
            "item_id": str(item_id),
            "body": body,
        }

        return self._post(query=query, variables=variables)