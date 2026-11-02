import json
import os
import re
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import List, Literal

import docker
import psutil
import psycopg2
import requests
from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from google import genai
from google.genai import types
from psycopg2.extras import RealDictCursor
from pydantic import BaseModel, Field

# --- Environment Configuration ---
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "postgres_db")
POSTGRES_DB = os.getenv("POSTGRES_DB", "postgres")
POSTGRES_USER = os.getenv("POSTGRES_USER", "postgres")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
DISCORD_WEBHOOK_URL = os.getenv("OPS_DISCORD_WEBHOOK", "")
UI_URL = os.getenv("OPS_UI_URL", "http://192.168.4.55:8005")
AUDIT_HOUR = int(os.getenv("AUDIT_HOUR", "7"))  # 7:00 AM daily

# <--- UPDATED: Exclude noisy containers (e.g., ADS-B feeders) from scanning
EXCLUDED_CONTAINERS = {
    c.strip()
    for c in os.getenv("EXCLUDED_CONTAINERS", "ultrafeeder,fr24feed,piaware").split(",")
    if c.strip()
}


# --- Pydantic Schemas for Gemini Structured Output ---
class DetectedIssue(BaseModel):
    fingerprint: str = Field(
        description="Unique slug combining container_name and short issue key, e.g., 'weather_api:influx_connection_timeout'"
    )
    container_name: str = Field(
        description="Name of the container or 'host' for system-level issues"
    )
    severity: Literal["Critical", "Warning", "Info"]
    title: str = Field(description="Concise summary of the problem")
    evidence: str = Field(
        description="Specific log lines or metric values proving the issue"
    )
    remediation_steps: str = Field(
        description="Step-by-step actionable instructions to fix the issue"
    )


class FixEvaluation(BaseModel):
    fingerprint: str = Field(
        description="The exact fingerprint of the 'Fix Deployed' issue being checked"
    )
    still_occurring: bool = Field(
        description="True if the error/problem is still present in current logs/stats, False if resolved"
    )
    notes: str = Field(
        description="Brief explanation of why it is considered verified or still failing"
    )


class DailyAuditReport(BaseModel):
    new_issues: List[DetectedIssue]
    fix_evaluations: List[FixEvaluation]


# <--- ADDED: Flat types.Schema definition (avoids Pydantic $defs / $ref validation error)
AUDIT_RESPONSE_SCHEMA = types.Schema(
    type=types.Type.OBJECT,
    required=["new_issues", "fix_evaluations"],
    properties={
        "new_issues": types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(
                type=types.Type.OBJECT,
                required=[
                    "fingerprint",
                    "container_name",
                    "severity",
                    "title",
                    "evidence",
                    "remediation_steps",
                ],
                properties={
                    "fingerprint": types.Schema(
                        type=types.Type.STRING,
                        description="Unique slug combining container_name and short issue key, e.g., 'weather_api:influx_connection_timeout'",
                    ),
                    "container_name": types.Schema(
                        type=types.Type.STRING,
                        description="Name of the container or 'host' for system-level issues",
                    ),
                    "severity": types.Schema(
                        type=types.Type.STRING,
                        enum=["Critical", "Warning", "Info"],
                    ),
                    "title": types.Schema(
                        type=types.Type.STRING,
                        description="Concise summary of the problem",
                    ),
                    "evidence": types.Schema(
                        type=types.Type.STRING,
                        description="Specific log lines or metric values proving the issue",
                    ),
                    "remediation_steps": types.Schema(
                        type=types.Type.STRING,
                        description="Step-by-step actionable instructions to fix the issue",
                    ),
                },
            ),
        ),
        "fix_evaluations": types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(
                type=types.Type.OBJECT,
                required=["fingerprint", "still_occurring", "notes"],
                properties={
                    "fingerprint": types.Schema(
                        type=types.Type.STRING,
                        description="The exact fingerprint of the 'Fix Deployed' issue being checked",
                    ),
                    "still_occurring": types.Schema(
                        type=types.Type.BOOLEAN,
                        description="True if the error/problem is still present in current logs/stats, False if resolved",
                    ),
                    "notes": types.Schema(
                        type=types.Type.STRING,
                        description="Brief explanation of why it is considered verified or still failing",
                    ),
                },
            ),
        ),
    },
)


# --- Database Helpers ---
def get_db_conn():
    return psycopg2.connect(
        host=POSTGRES_HOST,
        database=POSTGRES_DB,
        user=POSTGRES_USER,
        password=POSTGRES_PASSWORD,
        cursor_factory=RealDictCursor,
    )


def init_db():
    with get_db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS system_issues (
                    id SERIAL PRIMARY KEY,
                    fingerprint TEXT UNIQUE NOT NULL,
                    container_name TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    title TEXT NOT NULL,
                    evidence TEXT NOT NULL,
                    remediation_steps TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'New',
                    first_seen TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    last_seen TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    fix_deployed_at TIMESTAMPTZ,
                    verified_at TIMESTAMPTZ
                );
            """)
        conn.commit()


# --- Telemetry & Log Collection ---
LOG_ERROR_PATTERN = re.compile(
    r"(error|exception|traceback|critical|fatal|oom|killed|failed|timeout|refused|unhealthy)",
    re.IGNORECASE,
)


def collect_system_snapshot(since_hours: int = 24) -> dict:
    client = docker.from_env()
    containers = client.containers.list(all=True)
    since_dt = datetime.now(timezone.utc) - timedelta(hours=since_hours)

    host_metrics = {
        "cpu_percent": psutil.cpu_percent(interval=1),
        "memory_percent": psutil.virtual_memory().percent,
        "memory_available_mb": round(
            psutil.virtual_memory().available / (1024 * 1024), 1
        ),
        "swap_percent": psutil.swap_memory().percent,
        "disk_percent": psutil.disk_usage("/").percent,
    }

    container_reports = []
    for c in containers:
        # <--- UPDATED: Skip excluded noisy containers completely
        if c.name in EXCLUDED_CONTAINERS:
            continue

        c_info = {
            "name": c.name,
            "status": c.status,
            "restart_count": c.attrs.get("RestartCount", 0),
            "oom_killed": c.attrs.get("State", {}).get("OOMKilled", False),
            "cpu_percent": 0.0,
            "mem_usage_mb": 0.0,
            "mem_percent": 0.0,
            "error_logs": [],
        }

        if c.status == "running":
            try:
                stats = c.stats(stream=False)
                mem_usage = stats.get("memory_stats", {}).get("usage", 0)
                mem_limit = stats.get("memory_stats", {}).get("limit", 1)
                c_info["mem_usage_mb"] = round(mem_usage / (1024 * 1024), 1)
                c_info["mem_percent"] = round((mem_usage / mem_limit) * 100, 2)

                cpu_delta = (
                    stats["cpu_stats"]["cpu_usage"]["total_usage"]
                    - stats["precpu_stats"]["cpu_usage"]["total_usage"]
                )
                system_delta = stats["cpu_stats"].get("system_cpu_usage", 0) - stats[
                    "precpu_stats"
                ].get("system_cpu_usage", 0)
                online_cpus = stats["cpu_stats"].get("online_cpus", 4)
                if system_delta > 0 and cpu_delta > 0:
                    c_info["cpu_percent"] = round(
                        (cpu_delta / system_delta) * online_cpus * 100.0, 2
                    )
            except Exception as e:
                c_info["error_logs"].append(f"Stats collection failed: {str(e)}")

        try:
            raw_logs = c.logs(
                since=int(since_dt.timestamp()), timestamps=True, tail=400
            ).decode("utf-8", errors="replace")
            matched_lines = [
                line for line in raw_logs.splitlines() if LOG_ERROR_PATTERN.search(line)
            ]
            c_info["error_logs"] = matched_lines[-25:]
        except Exception as e:
            c_info["error_logs"].append(f"Log retrieval failed: {str(e)}")

        container_reports.append(c_info)

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "host_metrics": host_metrics,
        "containers": container_reports,
    }


# --- Core Daily Audit Logic ---
def run_daily_audit():
    snapshot = collect_system_snapshot(since_hours=24)

    with get_db_conn() as conn:
        with conn.cursor() as cur:
            # <--- UPDATED: Include 'Fix Failed' alongside 'New' and 'Fix Deployed'
            cur.execute(
                "SELECT * FROM system_issues WHERE status IN ('New', 'Fix Failed', 'Fix Deployed')"
            )
            open_issues = cur.fetchall()

    # <--- UPDATED: Both 'New' and 'Fix Failed' are treated as known unfixed issues so they aren't re-alerted
    known_unfixed = [
        {
            "fingerprint": i["fingerprint"],
            "container": i["container_name"],
            "title": i["title"],
            "status": i["status"],
        }
        for i in open_issues
        if i["status"] in ("New", "Fix Failed")
    ]
    fix_deployed_list = [
        {
            "fingerprint": i["fingerprint"],
            "container": i["container_name"],
            "title": i["title"],
            "evidence": i["evidence"],
            "fix_deployed_at": i["fix_deployed_at"].isoformat()
            if i["fix_deployed_at"]
            else None,
        }
        for i in open_issues
        if i["status"] == "Fix Deployed"
    ]
    # Check if any container has error logs, high resource usage, or stopped/restarting status
    has_container_problems = any(
        c["error_logs"]
        or c["status"] != "running"
        or c["oom_killed"]
        or c["cpu_percent"] > 80
        or c["mem_percent"] > 80
        for c in snapshot["containers"]
    )
    has_host_problems = (
        snapshot["host_metrics"]["cpu_percent"] > 85
        or snapshot["host_metrics"]["memory_percent"] > 85
        or snapshot["host_metrics"]["disk_percent"] > 85
    )

    # Skip the Gemini API call completely (0 requests / 0 tokens used) if the system is clean
    if not has_container_problems and not has_host_problems and not fix_deployed_list:
        send_discord_summary([], [], [], len(known_unfixed), snapshot["host_metrics"])
        return {
            "new_issues_count": 0,
            "verified_count": 0,
            "fix_failed_count": 0,
            "skipped_open_count": len(known_unfixed),
            "api_call_skipped": True,
        }
    prompt = f"""
You are the automated reliability engineer for a Raspberry Pi 5 Docker home lab ('Piccolo').
Analyze the following 24-hour system telemetry and container error logs.

1. KNOWN UNFIXED ISSUES ('New' or 'Fix Failed' - DO NOT report these again in new_issues):
{json.dumps(known_unfixed, indent=2)}

2. 'Fix Deployed' ISSUES TO VERIFY (Check if the problem still appears in logs/metrics AFTER fix_deployed_at):
{json.dumps(fix_deployed_list, indent=2)}

3. CURRENT SYSTEM SNAPSHOT & 24H LOGS:
{json.dumps(snapshot, indent=2)}

Instructions:
- For every item in 'Fix Deployed' ISSUES TO VERIFY, return an entry in `fix_evaluations` indicating whether `still_occurring` is True or False.
- Identify genuine new issues (crashes, high memory/CPU usage, repeated exceptions, database/network failures) NOT already listed in KNOWN UNFIXED ISSUES.
- Provide clear, specific `remediation_steps` for each new issue.
"""

    ai_client = genai.Client(api_key=GEMINI_API_KEY)
    response = ai_client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=AUDIT_RESPONSE_SCHEMA,  # <--- UPDATED: Use flat schema instead of DailyAuditReport
            temperature=0.1,
        ),
    )

    # <--- UPDATED: Parse JSON string directly into the Pydantic model
    report: DailyAuditReport = DailyAuditReport.model_validate_json(response.text)

    added_issues = []
    verified_fixes = []
    failed_fixes = []  # <--- UPDATED: Tracks issues transitioning to 'Fix Failed'

    with get_db_conn() as conn:
        with conn.cursor() as cur:
            # 1. Process Fix Deployed evaluations
            for eval_item in report.fix_evaluations:
                if not eval_item.still_occurring:
                    cur.execute(
                        """
                        UPDATE system_issues
                        SET status = 'Fix Verified', verified_at = NOW(), last_seen = NOW()
                        WHERE fingerprint = %s AND status = 'Fix Deployed'
                        RETURNING title, container_name;
                    """,
                        (eval_item.fingerprint,),
                    )
                    row = cur.fetchone()
                    if row:
                        verified_fixes.append(row)
                else:
                    # <--- UPDATED: Move to 'Fix Failed' instead of 'New'
                    cur.execute(
                        """
                        UPDATE system_issues
                        SET status = 'Fix Failed', last_seen = NOW()
                        WHERE fingerprint = %s AND status = 'Fix Deployed'
                        RETURNING title, container_name;
                    """,
                        (eval_item.fingerprint,),
                    )
                    row = cur.fetchone()
                    if row:
                        failed_fixes.append(row)

            # 2. Insert New Issues (skipping any that already exist as 'New' or 'Fix Failed')
            for issue in report.new_issues:
                cur.execute(
                    "SELECT id, status FROM system_issues WHERE fingerprint = %s",
                    (issue.fingerprint,),
                )
                existing = cur.fetchone()

                # <--- UPDATED: Do not duplicate or re-alert if already 'New' or 'Fix Failed'
                if existing and existing["status"] in ("New", "Fix Failed"):
                    cur.execute(
                        "UPDATE system_issues SET last_seen = NOW() WHERE id = %s",
                        (existing["id"],),
                    )
                elif existing and existing["status"] == "Fix Verified":
                    # Issue regressed after previously being verified
                    cur.execute(
                        """
                        UPDATE system_issues
                        SET status = 'New', severity = %s, evidence = %s, remediation_steps = %s, last_seen = NOW()
                        WHERE id = %s
                    """,
                        (
                            issue.severity,
                            issue.evidence,
                            issue.remediation_steps,
                            existing["id"],
                        ),
                    )
                    added_issues.append(issue)
                elif not existing:
                    cur.execute(
                        """
                        INSERT INTO system_issues (fingerprint, container_name, severity, title, evidence, remediation_steps, status)
                        VALUES (%s, %s, %s, %s, %s, %s, 'New')
                    """,
                        (
                            issue.fingerprint,
                            issue.container_name,
                            issue.severity,
                            issue.title,
                            issue.evidence,
                            issue.remediation_steps,
                        ),
                    )
                    added_issues.append(issue)
        conn.commit()

    send_discord_summary(
        added_issues,
        verified_fixes,
        failed_fixes,
        len(known_unfixed),
        snapshot["host_metrics"],
    )
    return {
        "new_issues_count": len(added_issues),
        "verified_count": len(verified_fixes),
        "fix_failed_count": len(failed_fixes),  # <--- UPDATED
        "skipped_open_count": len(known_unfixed),
    }


def send_discord_summary(
    added_issues, verified_fixes, failed_fixes, skipped_count, host_metrics
):
    if not DISCORD_WEBHOOK_URL:
        return

    lines = [
        f"**Host Snapshot:** CPU `{host_metrics['cpu_percent']}%` | RAM `{host_metrics['memory_percent']}%` | Disk `{host_metrics['disk_percent']}%`\n"
    ]

    if added_issues:
        lines.append("🚨 **New Issues Detected:**")
        for i in added_issues:
            lines.append(
                f"• **[{i.severity}] `{i.container_name}`** — {i.title}\n  *Fix:* {i.remediation_steps[:180]}..."
            )
        lines.append("")

    # <--- UPDATED: Distinct 'Fix Failed' section in Discord alert
    if failed_fixes:
        lines.append("❌ **Fixes Failed (Moved to Fix Failed):**")
        for r in failed_fixes:
            lines.append(f"• `{r['container_name']}` — {r['title']}")
        lines.append("")

    if verified_fixes:
        lines.append("✅ **Fixes Verified (24h Clean):**")
        for v in verified_fixes:
            lines.append(f"• `{v['container_name']}` — {v['title']}")
        lines.append("")

    if not added_issues and not failed_fixes and not verified_fixes:
        lines.append("✨ **No new issues detected in the last 24 hours.**\n")

    lines.append(
        f"📌 *Skipped {skipped_count} existing unfixed ('New' / 'Fix Failed') issue(s).*"
    )
    lines.append(f"🔗 [Open Ops Issue Tracker]({UI_URL})")

    color = 15158332 if (added_issues or failed_fixes) else 3066993
    payload = {
        "embeds": [
            {
                "title": "🩺 Piccolo Daily Ops & Log Audit",
                "color": color,
                "description": "\n".join(lines),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        ]
    }
    try:
        requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
    except Exception as e:
        print(f"Discord webhook error: {e}")


# --- FastAPI Lifecycle & Endpoints ---
scheduler = BackgroundScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    scheduler.add_job(
        run_daily_audit,
        "cron",
        hour=AUDIT_HOUR,
        minute=0,
        id="daily_ops_audit",
        replace_existing=True,
    )
    scheduler.start()
    yield
    scheduler.shutdown()


app = FastAPI(lifespan=lifespan)


@app.get("/", response_class=HTMLResponse)
def serve_ui():
    with open("index.html", "r", encoding="utf-8") as f:
        return f.read()


@app.get("/api/issues")
def list_issues(status: str = None):
    with get_db_conn() as conn:
        with conn.cursor() as cur:
            if status:
                cur.execute(
                    "SELECT * FROM system_issues WHERE status = %s ORDER BY last_seen DESC",
                    (status,),
                )
            else:
                # <--- UPDATED: Sort 'Fix Failed' and 'New' at the top
                cur.execute("""
                    SELECT * FROM system_issues
                    ORDER BY CASE status
                        WHEN 'Fix Failed' THEN 1
                        WHEN 'New' THEN 2
                        WHEN 'Fix Deployed' THEN 3
                        WHEN 'Fix Verified' THEN 4
                    END, last_seen DESC
                """)
            return cur.fetchall()


# <--- UPDATED: Added 'Fix Failed' to allowed status transitions
class StatusUpdate(BaseModel):
    status: Literal["New", "Fix Deployed", "Fix Failed", "Fix Verified"]


@app.patch("/api/issues/{issue_id}/status")
def update_issue_status(issue_id: int, body: StatusUpdate):
    with get_db_conn() as conn:
        with conn.cursor() as cur:
            if body.status == "Fix Deployed":
                cur.execute(
                    """
                    UPDATE system_issues
                    SET status = 'Fix Deployed', fix_deployed_at = NOW()
                    WHERE id = %s RETURNING *;
                """,
                    (issue_id,),
                )
            elif body.status == "Fix Verified":
                cur.execute(
                    """
                    UPDATE system_issues
                    SET status = 'Fix Verified', verified_at = NOW()
                    WHERE id = %s RETURNING *;
                """,
                    (issue_id,),
                )
            else:
                # Handles both 'New' and 'Fix Failed'
                cur.execute(
                    """
                    UPDATE system_issues
                    SET status = %s
                    WHERE id = %s RETURNING *;
                """,
                    (body.status, issue_id),
                )
            updated = cur.fetchone()
            if not updated:
                raise HTTPException(status_code=404, detail="Issue not found")
        conn.commit()
    return updated


@app.post("/api/audit/run")
def trigger_manual_audit():
    return run_daily_audit()
