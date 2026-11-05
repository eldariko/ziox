"""
Summary Reporter for zioX Pipeline.
Generates comprehensive visual Markdown execution reports for GitHub Actions Job Summaries
($GITHUB_STEP_SUMMARY) and local audit inspection.
"""

import os
import re
import html
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from config.settings import Settings
from database.repository import Repository
from engine.telegram_dispatcher import mask_chat_id_for_display
from engine.link_validator import LinkValidator

logger = logging.getLogger(__name__)


class SummaryReporter:
    """Generates rich, visual Markdown summaries for GitHub Actions and admin auditing."""

    @classmethod
    def generate_markdown(
        cls,
        run_report: Dict[str, Any],
        settings: Settings,
        repository: Repository,
    ) -> str:
        """Generate a complete GitHub Flavored Markdown dashboard of the run."""
        sections: List[str] = []

        # 1. Header & Badges
        sections.append(cls._build_header_section(run_report, settings, repository))

        # 2. Key Metrics Cards
        sections.append(cls._build_metrics_cards(run_report))

        # 3. Parameters & Dynamic Sizing
        sections.append(cls._build_parameters_section(run_report, settings, repository))

        # 4. Radar Funnel & Search Queries
        sections.append(cls._build_radar_section(run_report, settings))

        # 5. Queue State & AI Fact-Checking Decisions
        sections.append(cls._build_queue_decisions_section(run_report))

        # 6. Telegram Community Dispatch Matrix
        sections.append(cls._build_dispatches_section(run_report, repository))

        # 7. Link Health & Whitelist Audit
        sections.append(cls._build_link_audit_section())

        return "\n\n".join(sections) + "\n"

    @classmethod
    def _build_header_section(
        cls,
        run_report: Dict[str, Any],
        settings: Settings,
        repository: Repository,
    ) -> str:
        status = run_report.get("status", "SUCCESS")
        status_icons = {
            "SUCCESS": "🟢 **SUCCESS**",
            "IDLE": "🟡 **IDLE**",
            "QUOTA_EXCEEDED": "🛑 **QUOTA EXCEEDED**",
            "SCANNER_COOLDOWN": "⚠️ **SCANNER COOLDOWN**",
            "RADAR_ERROR": "🔴 **RADAR ERROR**",
            "EMPTY_QUEUE": "⚪ **EMPTY QUEUE**",
        }
        status_badge = status_icons.get(status, f"🔵 **{status}**")
        now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

        mode = "Dry-Run" if settings.dry_run else "Live"
        provider_name = settings.twitter_provider
        db_label = "Turso Cloud" if settings.turso_database_url else "Local SQLite"
        monthly_count = repository.get_monthly_reply_count() if hasattr(repository, "get_monthly_reply_count") else 0
        monthly_quota = f"{monthly_count} / {settings.monthly_max_replies}"

        return (
            f"# 📊 zioX Pipeline Execution Report\n\n"
            f"> Status: {status_badge} | 🕒 **Timestamp:** `{now_utc}` | "
            f"⚙️ **Mode:** `{mode}` | 🐦 **Provider:** `{provider_name}` | "
            f"🗄️ **Database:** `{db_label}` | 📈 **Monthly Usage:** `{monthly_quota}`"
        )

    @classmethod
    def _build_metrics_cards(cls, run_report: Dict[str, Any]) -> str:
        discovered = run_report.get("discovered_count", 0)
        processed = run_report.get("processed", 0)
        dispatched_waves = run_report.get("replies_sent", 0)
        subscribers_served = run_report.get("subscribers_served", 0)
        pending_after = run_report.get("pending_after_count", 0)

        return (
            "| 📡 Discovered Tweets | ⚙️ Tweets Evaluated | 🚀 Dispatched Waves | 👥 Subscribers Served | 🗄️ Preserved in Queue |\n"
            "| :---: | :---: | :---: | :---: | :---: |\n"
            f"| **`{discovered}`** | **`{processed}`** | **`{dispatched_waves}`** | **`{subscribers_served}`** | **`{pending_after}`** |"
        )

    @classmethod
    def _build_parameters_section(
        cls,
        run_report: Dict[str, Any],
        settings: Settings,
        repository: Repository,
    ) -> str:
        demand = run_report.get("demand") or (
            repository.get_available_subscriber_demand()
            if hasattr(repository, "get_available_subscriber_demand")
            else {"total": 0, "en": 0, "ar": 0}
        )
        total_demand = demand.get("total", 0)
        en_demand = demand.get("en", 0)
        ar_demand = demand.get("ar", 0)

        cohort_size = max(1, getattr(settings, "target_cohort_size_per_tweet", 25))
        base_cap = getattr(settings, "telegram_tweets_per_cycle", 10)
        import math
        needed_waves = max(base_cap, math.ceil(total_demand / cohort_size))
        dynamic_limit = max(15, min(50, needed_waves * 2))

        lines = [
            "### 🎛️ 1. Execution Parameters & Dynamic Sizing",
            "",
            "| Parameter | Active Value | Dynamic Logic & Formulation |",
            "| :--- | :---: | :--- |",
            f"| **Available Demand** | `{total_demand}` (`EN: {en_demand}` \\| `AR: {ar_demand}`) | Ready subscribers with daily quota remaining today |",
            f"| **Dynamic Search Limit** | `{dynamic_limit}` / query | `max(15, min(50, needed_waves * 2))` scaled to demand |",
            f"| **Max Processing Waves** | `{needed_waves}` waves | `max(base_cap, ceil(demand / cohort_size))` |",
            f"| **Target Cohort Size** | `{cohort_size}` subscribers | Horizontal sharding per tweet wave |",
            f"| **Virality Threshold** | `{settings.virality_threshold}` | Velocity score cutoff `(likes + RT*3 + replies*2) / age^1.2` |",
            f"| **Max Tweet Age** | `{settings.max_tweet_age_hours}h` | Posts older than 24h discarded before scoring |",
            f"| **Linkless Ratio** | `{int(getattr(settings, 'no_link_variation_ratio', 0.4) * 100)}%` | Proportion of linkless variations in cohorts |",
            f"| **Link Cooldown** | `{settings.link_cooldown_minutes}m` | Proof URL reuse throttle window |",
            f"| **Monthly Reply Ceiling** | `{settings.monthly_max_replies}` | Hard safety stop for replies per calendar month |",
        ]
        return "\n".join(lines)

    @classmethod
    def _build_radar_section(cls, run_report: Dict[str, Any], settings: Settings) -> str:
        radar_stats = run_report.get("radar_scan_stats")
        lines = [
            "### 📡 2. Radar Discovery & Ingestion Funnel",
            "",
        ]

        if not radar_stats or not radar_stats.get("queries"):
            discovered = run_report.get("discovered_count", 0)
            lines.append(f"> Discovery Radar reported **{discovered}** enqueued candidate tweets.")
            return "\n".join(lines)

        total_raw = radar_stats.get("total_raw", 0)
        total_skipped_age = radar_stats.get("total_skipped_age", 0)
        total_skipped_db = radar_stats.get("total_skipped_already_processed", 0)
        total_skipped_virality = radar_stats.get("total_skipped_low_virality", 0)
        total_enqueued = radar_stats.get("total_enqueued", 0)

        # Mermaid Funnel
        lines.append("```mermaid")
        lines.append("flowchart LR")
        lines.append(f'    A["Raw X Posts<br/><b>{total_raw}</b>"] --> B["Age / DB Filtered<br/><b>{total_skipped_age + total_skipped_db}</b>"]')
        lines.append(f'    B --> C["Virality Qualified<br/><b>{total_enqueued}</b>"]')
        lines.append(f'    C --> D["Enqueued to Queue<br/><b>{total_enqueued}</b>"]')
        lines.append("```")
        lines.append("")

        # Breakdown Table
        lines.append("| # | Search Query / Consolidated Boolean OR | Raw Results | Filtered (>24h) | Already in DB | Below Score (<5.0) | Enqueued (DISCOVERED) |")
        lines.append("| :-: | :--- | :-: | :-: | :-: | :-: | :-: |")

        for idx, q in enumerate(radar_stats.get("queries", []), 1):
            q_text = q.get("query", "").replace("|", "\\|")
            lines.append(
                f"| {idx} | `{q_text}` | {q.get('raw_count', 0)} | {q.get('skipped_age', 0)} | "
                f"{q.get('skipped_already_processed', 0)} | {q.get('skipped_low_virality', 0)} | **{q.get('enqueued_count', 0)}** |"
            )

        lines.append(
            f"| **Σ** | **Total Ingestion Across Queries** | **{total_raw}** | **{total_skipped_age}** | "
            f"**{total_skipped_db}** | **{total_skipped_virality}** | **{total_enqueued}** |"
        )

        return "\n".join(lines)

    @classmethod
    def _build_queue_decisions_section(cls, run_report: Dict[str, Any]) -> str:
        evaluations = run_report.get("evaluations") or []
        pending_after = run_report.get("pending_after_items") or []
        pending_before_cnt = run_report.get("pending_before_count", len(evaluations) + len(pending_after))
        processed_cnt = run_report.get("processed", len(evaluations))

        lines = [
            "### 🧠 3. Queue State & AI Fact-Checking Decisions",
            "",
            f"- 📥 **Queue Before Run:** `{pending_before_cnt}` candidate tweets",
            f"- ⚙️ **Evaluated in This Run:** `{processed_cnt}` tweets (sorted by Virality Momentum)",
            f"- 🗄️ **Preserved in Queue:** `{len(pending_after)}` candidate tweets awaiting next cron cycle",
            "",
        ]

        if not evaluations:
            # Fallback to results if evaluations list was not populated
            evaluations = [
                {
                    "tweet_id": r["tweet_id"],
                    "author": r.get("author", "unknown"),
                    "virality_score": r.get("virality_score", 0.0),
                    "tier": "Viral",
                    "decision": "APPROVED",
                    "reason": None,
                    "claim": r.get("claim"),
                    "status": r.get("status", "DISPATCHED_TELEGRAM"),
                    "link": None,
                }
                for r in run_report.get("results", [])
            ]

        if evaluations:
            lines.append("| Tweet ID & Author | Score | AI Grounding Decision | Claim Flagged / Skip Reason | Link Status | DB Status |")
            lines.append("| :--- | :---: | :---: | :--- | :--- | :---: |")

            for item in evaluations:
                tid = item.get("tweet_id", "")
                author = item.get("author", "unknown").lstrip("@")
                score = float(item.get("virality_score", 0.0))
                tier = item.get("tier", "Viral")
                decision = item.get("decision", "APPROVED")
                db_status = item.get("status", "DISPATCHED_TELEGRAM")

                tweet_link = f"[{tid}](https://x.com/{author}/status/{tid})" if tid else "N/A"
                author_display = f"@{author}" if author else "Unknown"

                if decision == "APPROVED":
                    decision_badge = "✅ **Approved**"
                    claim = html.escape(str(item.get("claim") or "Identified factual assertion"))
                    claim_text = f"<i>\"{claim[:120]}...\"</i>" if len(claim) > 120 else f"<i>\"{claim}\"</i>"
                    facts = item.get("facts") or []
                    if facts:
                        facts_preview = html.escape(facts[0][:90] + ("..." if len(facts[0]) > 90 else ""))
                        claim_text += f"<br/>📌 <b>Fact:</b> {facts_preview}"
                    link_val = item.get("link")
                    link_status = f"`{html.escape(link_val[:35])}...`" if link_val else "Linkless / Whitelist"
                else:
                    decision_badge = "❌ **Skipped**"
                    reason = html.escape(str(item.get("reason") or "Factual claim missing or unsupported"))
                    claim_text = f"⚠️ {reason}"
                    link_status = "—"

                lines.append(
                    f"| {tweet_link}<br/>{author_display} | `{score:.1f}` [{tier}] | {decision_badge} | "
                    f"{claim_text} | {link_status} | `{db_status}` |"
                )
            lines.append("")

        if pending_after:
            lines.append(f"<details>")
            lines.append(f"<summary><b>📋 {len(pending_after)} Candidate Tweets Preserved in Queue for Next Run (Click to expand)</b></summary>\n")
            lines.append("| Tweet ID & Author | Virality Score | Tweet Snippet |")
            lines.append("| :--- | :---: | :--- |")
            for p in pending_after[:15]:
                p_id = p.get("tweet_id", "")
                p_author = p.get("author_handle", "unknown").lstrip("@")
                p_score = float(p.get("virality_score", 0.0))
                p_text = html.escape(p.get("tweet_text", "")[:120] + ("..." if len(p.get("tweet_text", "")) > 120 else ""))
                p_link = f"[{p_id}](https://x.com/{p_author}/status/{p_id})" if p_id else "N/A"
                lines.append(f"| {p_link}<br/>@{p_author} | `{p_score:.1f}` | \"{p_text}\" |")
            if len(pending_after) > 15:
                lines.append(f"| *...and {len(pending_after) - 15} more* | | |")
            lines.append("</details>\n")

        return "\n".join(lines)

    @classmethod
    def _build_dispatches_section(cls, run_report: Dict[str, Any], repository: Repository) -> str:
        dispatches = run_report.get("dispatches") or []
        lines = [
            "### 📬 4. Telegram Community Dispatch Matrix (Who Received What)",
            "",
        ]

        if not dispatches:
            lines.append("> No Telegram review cards were dispatched in this run.")
            return "\n".join(lines)

        lines.append("| Recipient | Language | Daily Quota | Target Tweet & Author | Variation Style | Proposed Reply Draft | Delivery Mode |")
        lines.append("| :--- | :---: | :---: | :--- | :---: | :--- | :---: |")

        for d in dispatches:
            cid = str(d.get("chat_id", ""))
            uname = d.get("username", "")
            tier = d.get("tier", "free")
            display_name = mask_chat_id_for_display(cid, username=uname, tier=tier)

            lang = d.get("preferred_lang", "en")
            # Query quota if repository is available
            sub = repository.get_subscriber(cid) if hasattr(repository, "get_subscriber") else None
            today_cnt = repository.get_subscriber_daily_count(cid) if hasattr(repository, "get_subscriber_daily_count") else "?"
            limit = sub.get("daily_limit", 5) if sub else 5
            quota_display = f"`{today_cnt}/{limit}`"

            tid = d.get("tweet_id", "")
            author = d.get("author_handle", "unknown").lstrip("@")
            tweet_link = f"[{tid}](https://x.com/{author}/status/{tid})" if tid else "N/A"

            style = d.get("style", "factual")
            style_emojis = {
                "factual": "🎯 `factual`",
                "sharp": "⚡ `sharp`",
                "historical_legal": "📜 `historical_legal`",
                "rhetorical_question": "❓ `rhetorical_question`",
                "direct_data": "📊 `direct_data`",
                "empathetic": "🤝 `empathetic`",
                "socratic": "🤔 `socratic`",
            }
            style_badge = style_emojis.get(style, f"`{style}`")

            draft = html.escape(d.get("draft_reply", ""))
            draft_snippet = f"<code>{draft[:100]}...</code>" if len(draft) > 100 else f"<code>{draft}</code>"

            mode = "🛡️ Admin Fallback" if d.get("is_fallback") else "👥 Cohort Sharding"

            lines.append(
                f"| **{display_name}** | `{lang}` | {quota_display} | "
                f"@{author}<br/>{tweet_link} | {style_badge} | {draft_snippet} | {mode} |"
            )

        return "\n".join(lines)

    @classmethod
    def _build_link_audit_section(cls) -> str:
        cache = LinkValidator.get_cache() if hasattr(LinkValidator, "get_cache") else {}
        lines = [
            "### 🌐 5. Link Health & Whitelist Audit",
            "",
        ]

        if not cache:
            lines.append("> No external links were evaluated during this run.")
            return "\n".join(lines)

        lines.append("| Verified Proof URL | HTTP Status | Health Verdict |")
        lines.append("| :--- | :---: | :---: |")

        for url, (is_healthy, status_code) in cache.items():
            safe_url = html.escape(url)
            code_str = f"HTTP {status_code}" if status_code > 0 else "Network / DNS / SSL Error"
            verdict = "✅ **Healthy (Substantive Article)**" if is_healthy else "❌ **Inaccessible / Fallback Triggered**"
            lines.append(f"| `{safe_url}` | `{code_str}` | {verdict} |")

        return "\n".join(lines)

    @classmethod
    def write_step_summary(
        cls,
        markdown_text: str,
        target_file: Optional[str] = None
    ) -> Optional[str]:
        """
        Write markdown to GITHUB_STEP_SUMMARY environment file (if running in GitHub Actions)
        or target_file (if specified).
        Returns the path written to, or None if neither target is configured.
        """
        out_path = target_file or os.environ.get("GITHUB_STEP_SUMMARY")
        if not out_path:
            return None

        try:
            with open(out_path, "a", encoding="utf-8") as f:
                f.write(markdown_text + "\n")
            logger.info(f"[SummaryReporter] Successfully wrote pipeline summary to: {out_path}")
            return out_path
        except Exception as e:
            logger.error(f"[SummaryReporter] Failed writing step summary to {out_path}: {e}")
            return None

    @classmethod
    def generate_and_publish(
        cls,
        run_report: Dict[str, Any],
        settings: Settings,
        repository: Repository,
        target_file: Optional[str] = None
    ) -> Optional[str]:
        """Convenience method to generate markdown and write to summary targets."""
        md = cls.generate_markdown(run_report, settings, repository)
        return cls.write_step_summary(md, target_file=target_file)
