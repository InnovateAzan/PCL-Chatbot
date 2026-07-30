from __future__ import annotations

from backend.app.services.onedesk.base_client import OneDeskListConfig


class OneDeskResponseFormatter:
    def format_records(
        self,
        *,
        config: OneDeskListConfig,
        records: list[dict],
        request_number: str | None,
    ) -> str:
        if not records:
            if request_number:
                return "No matching OneDesk request was found for your account."
            return "No matching OneDesk records were found for your account."

        blocks: list[str] = []
        for record in records[:5]:
            number = record.get(config.request_number_field) or "Not provided"
            status = record.get(config.status_field) or "Not provided"
            assigned = record.get(config.assigned_to_field) or "Not provided"
            updated = record.get(config.updated_field) or "Not provided"
            latest = record.get(config.latest_update_field) or "No latest update."
            title = record.get("Title") or record.get("title") or config.module
            blocks.append(
                f"Ticket: {number}\n"
                f"Issue: {title}\n"
                f"Status: {status}\n"
                f"Assigned To: {assigned}\n"
                f"Last Updated: {updated}\n"
                f"Latest Update: {latest}"
            )

        if len(records) > 1 and not request_number:
            blocks.append("Please provide a ticket or request number for more detail.")

        return "\n\n".join(blocks)
