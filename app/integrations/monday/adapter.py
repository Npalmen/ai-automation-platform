# app/integrations/monday/adapter.py

from typing import Any
from app.integrations.base import BaseIntegrationAdapter
from app.integrations.monday.client import MondayClient


class MondayAdapter(BaseIntegrationAdapter):
    def __init__(self, connection_config: dict[str, Any] | None = None):
        super().__init__(connection_config=connection_config)

        api_key = self.connection_config.get("api_key")
        api_url = self.connection_config.get("api_url", "https://api.monday.com/v2")
        default_board_id = self.connection_config.get("board_id")

        if not api_key:
            raise ValueError("Missing monday api_key in connection_config.")

        if not default_board_id:
            raise ValueError("Missing monday board_id in connection_config.")

        self.default_board_id = int(default_board_id)

        self.client = MondayClient(
            api_key=api_key,
            api_url=api_url,
        )

    def execute_action(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        if action == "create_item":
            item_name = payload.get("item_name")
            column_values = payload.get("column_values", {})
            group_id = payload.get("group_id")

            if not item_name:
                raise ValueError("Missing 'item_name' for monday create_item action.")

            result = self.client.create_item(
                board_id=self.default_board_id,
                item_name=item_name,
                group_id=group_id,
                column_values=column_values,
            )

            item_id = result["data"]["create_item"]["id"]

            return {
                "status": "success",
                "integration": "monday",
                "action": action,
                "item_id": item_id,
                "result": result,
            }

        if action == "create_update":
            item_id = payload.get("item_id")
            body = payload.get("body")

            if not item_id:
                raise ValueError("Missing 'item_id' for monday create_update action.")
            if not body:
                raise ValueError("Missing 'body' for monday create_update action.")

            result = self.client.create_update(
                item_id=int(item_id),
                body=body,
            )

            return {
                "status": "success",
                "integration": "monday",
                "action": action,
                "result": result,
            }

        raise ValueError(f"Unsupported monday action: {action}")

    def get_status(self) -> dict[str, Any]:
        result = self.client.get_me()

        return {
            "status": "connected",
            "integration": "monday",
            "result": result,
        }