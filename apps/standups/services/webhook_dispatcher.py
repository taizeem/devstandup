import json
import logging
from typing import List, Dict, Any
import requests
from apps.teams.models import WebhookFormat, Team
from apps.standups.models import StandupDigest, StandupEntry

logger = logging.getLogger(__name__)

class WebhookDispatchError(Exception):
    pass

class WebhookDispatcher:
    TIMEOUT_SECONDS = 10

    @classmethod
    def send_digest(cls, digest: StandupDigest, entries: List[StandupEntry], missing_members: List[str]) -> bool:
        team = digest.team
        payload = cls._format_digest_payload(
            team=team,
            digest_date=digest.digest_date.strftime("%A, %b %d, %Y"),
            entries=entries,
            missing_members=missing_members,
        )
        return cls._post(team.webhook_url, payload)

    @classmethod
    def send_late_entry(cls, entry: StandupEntry) -> bool:
        team = entry.team
        payload = cls._format_late_entry_payload(entry)
        return cls._post(team.webhook_url, payload)

    @classmethod
    def _post(cls, url: str, payload: Dict[str, Any]) -> bool:
        headers = {"Content-Type": "application/json"}
        try:
            response = requests.post(
                url,
                data=json.dumps(payload,ensure_ascii=False).encode("utf-8"),
                headers=headers,
                timeout=cls.TIMEOUT_SECONDS
            )
            response.raise_for_status()
            return True
        except requests.RequestException as exc:
            logger.error("Webhook dispatch failed to %s: %s", url, exc, exc_info=True)
            raise WebhookDispatchError(f"Webhook dispatch failed: {str(exc)}") from exc

    @classmethod
    def _format_digest_payload(
        cls,
        team: Team,
        digest_date: str,
        entries: List[StandupEntry],
        missing_members: List[str]
    ) -> Dict[str, Any]:
        if team.webhook_format == WebhookFormat.SLACK:
            return cls._slack_digest_payload(team, digest_date, entries, missing_members)
        elif team.webhook_format == WebhookFormat.DISCORD:
            return cls._discord_digest_payload(team, digest_date, entries, missing_members)
        else:
            return cls._generic_markdown_payload(team, digest_date, entries, missing_members)

    @classmethod
    def _slack_digest_payload(
        cls,
        team: Team,
        digest_date: str,
        entries: List[StandupEntry],
        missing_members: List[str]
    ) -> Dict[str, Any]:
        blocks = [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": f"📋 {team.name} Standup Digest - {digest_date}"}
            },
            {"type": "divider"}
        ]

        if entries:
            for entry in entries:
                late_badge = " *(Late)*" if entry.is_late else ""
                blockers_text = entry.blockers.strip() if entry.blockers.strip() else "_None_"
                member_title = f"*{entry.member.display_name}*{late_badge}"
                entry_text = (
                    f"{member_title}\n"
                    f"*Yesterday:* {entry.yesterday}\n"
                    f"*Today:* {entry.today}\n"
                    f"*Blockers:* {blockers_text}"
                )
                blocks.append({
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": entry_text}
                })
        else:
            blocks.append({
                "type": "section",
                "text": {"type": "mrkdwn", "text": "_No standups submitted for this period._"}
            })

        blocks.append({"type": "divider"})

        # Explicitly flag missing submitters
        if missing_members:
            missing_formatted = ", ".join(f"`{name}`" for name in missing_members)
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"⚠️ *Missing Submissions ({len(missing_members)}):*\n{missing_formatted}"
                }
            })
        else:
            blocks.append({
                "type": "context",
                "elements": [{"type": "mrkdwn", "text": "✅ *100% submission rate today! High-five team!*"}]
            })

        return {"blocks": blocks}

    @classmethod
    def _discord_digest_payload(
        cls,
        team: Team,
        digest_date: str,
        entries: List[StandupEntry],
        missing_members: List[str]
    ) -> Dict[str, Any]:
        fields = []
        for entry in entries:
            late_text = " [LATE]" if entry.is_late else ""
            blockers = entry.blockers.strip() or "None"
            value_text = (
                f"**Yesterday:** {entry.yesterday}\n"
                f"**Today:** {entry.today}\n"
                f"**Blockers:** {blockers}"
            )
            # Discord field value max length safeguard
            value_text = value_text[:1024]
            fields.append({
                "name": f"{entry.member.display_name}{late_text}",
                "value": value_text,
                "inline": False
            })

        if missing_members:
            fields.append({
                "name": "⚠️ Missing Submissions",
                "value": ", ".join(missing_members)[:1024],
                "inline": False
            })

        embed = {
            "title": f"📋 {team.name} Standup Digest - {digest_date}",
            "color": 0x3498DB if not missing_members else 0xE67E22,
            "fields": fields
        }
        return {"embeds": [embed]}

    @classmethod
    def _generic_markdown_payload(
        cls,
        team: Team,
        digest_date: str,
        entries: List[StandupEntry],
        missing_members: List[str]
    ) -> Dict[str, Any]:
        lines = [
            f"# 📋 {team.name} Standup Digest - {digest_date}",
            "---",
            "## Submissions:"
        ]
        for entry in entries:
            late_badge = " (LATE)" if entry.is_late else ""
            lines.append(f"### {entry.member.display_name}{late_badge}")
            lines.append(f"- **Yesterday:** {entry.yesterday}")
            lines.append(f"- **Today:** {entry.today}")
            lines.append(f"- **Blockers:** {entry.blockers or 'None'}")
            lines.append("")

        lines.append("---")
        if missing_members:
            lines.append(f"## ⚠️ Missing Submissions ({len(missing_members)}):")
            for m in missing_members:
                lines.append(f"- {m}")
        else:
            lines.append("## ✅ All active team members submitted on time!")

        return {"text": "\n".join(lines)}

    @classmethod
    def _format_late_entry_payload(cls, entry: StandupEntry) -> Dict[str, Any]:
        member_name = entry.member.display_name
        blockers = entry.blockers.strip() or "_None_"
        text = (
            f"⏰ *Late Standup Submission Appended*\n"
            f"*Team:* {entry.team.name}\n"
            f"*Member:* *{member_name}*\n"
            f"*Yesterday:* {entry.yesterday}\n"
            f"*Today:* {entry.today}\n"
            f"*Blockers:* {blockers}"
        )
        if entry.team.webhook_format == WebhookFormat.SLACK:
            return {
                "blocks": [
                    {
                        "type": "section",
                        "text": {"type": "mrkdwn", "text": text}
                    }
                ]
            }
        elif entry.team.webhook_format == WebhookFormat.DISCORD:
            return {
                "embeds": [
                    {
                        "title": f"⏰ Late Standup: {member_name}",
                        "color": 0xF1C40F,
                        "fields": [
                            {"name": "Yesterday", "value": entry.yesterday, "inline": False},
                            {"name": "Today", "value": entry.today, "inline": False},
                            {"name": "Blockers", "value": blockers, "inline": False},
                        ]
                    }
                ]
            }
        return {"text": text}