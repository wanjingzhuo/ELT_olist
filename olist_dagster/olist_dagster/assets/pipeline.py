import os
import smtplib
import subprocess
from email.mime.text import MIMEText
from pathlib import Path

import dotenv
from dagster import asset, AssetExecutionContext

# Load .env from repo root before any asset runs
_REPO_ROOT = Path(__file__).parent.parent.parent.parent  # ~/ELT_olist
dotenv.load_dotenv(_REPO_ROOT / ".env")

MELTANO_DIR = _REPO_ROOT / "olist_meltano"
DBT_DIR     = _REPO_ROOT / "olist_transform"
GE_DIR      = _REPO_ROOT / "great_expectations"
REPORT_DIR  = _REPO_ROOT / "report"

BQ_PROJECT  = "olist-498903"
BQ_MARTS    = f"{BQ_PROJECT}.olist_transformed_marts"
KEYFILE     = _REPO_ROOT / "olist-498903-e7f8763e517a.json"


def _run(cmd: list, cwd: Path) -> str:
    """Run a subprocess, raise on non-zero exit, return combined stdout+stderr."""
    try:
        return subprocess.check_output(cmd, stderr=subprocess.STDOUT, cwd=str(cwd)).decode()
    except subprocess.CalledProcessError as e:
        raise Exception(e.output.decode())


# ── 1. Extract & Load ─────────────────────────────────────────────────────────

@asset
def meltano_extract_load(context: AssetExecutionContext) -> None:
    """Extract from Supabase Postgres and load to BigQuery olist_raw via Meltano."""
    output = _run(["meltano", "run", "tap-postgres", "target-bigquery"], cwd=MELTANO_DIR)
    context.log.info(output)


# ── 2. GE validation ──────────────────────────────────────────────────────────

@asset(deps=[meltano_extract_load])
def ge_raw_validation(context: AssetExecutionContext) -> None:
    """Run Great Expectations on olist_raw. Non-zero exit halts the pipeline."""
    output = _run(["python", str(GE_DIR / "ge_olist_raw.py")], cwd=_REPO_ROOT)
    context.log.info(output)


# ── 3. dbt staging ───────────────────────────────────────────────────────────

@asset(deps=[ge_raw_validation])
def dbt_staging(context: AssetExecutionContext) -> None:
    """Build dbt staging models (views in olist_transformed_staging)."""
    output = _run(
        ["dbt", "build", "--select", "staging", "--profiles-dir", "."],
        cwd=DBT_DIR,
    )
    context.log.info(output)


# ── 4. dbt snapshot ──────────────────────────────────────────────────────────

@asset(deps=[dbt_staging])
def dbt_snapshot(context: AssetExecutionContext) -> None:
    """Run dbt snapshots for SCD Type 2 (snap_dim_sellers)."""
    output = _run(["dbt", "snapshot", "--profiles-dir", "."], cwd=DBT_DIR)
    context.log.info(output)


# ── 5. dbt marts ─────────────────────────────────────────────────────────────

@asset(deps=[dbt_snapshot])
def dbt_marts(context: AssetExecutionContext) -> None:
    """Build dbt marts models (tables in olist_transformed_marts)."""
    output = _run(
        ["dbt", "build", "--select", "marts", "--profiles-dir", "."],
        cwd=DBT_DIR,
    )
    context.log.info(output)


# ── 6. Dashboard regeneration ─────────────────────────────────────────────────

@asset(deps=[dbt_marts])
def generate_dashboard(context: AssetExecutionContext) -> None:
    """Regenerate docs/index.html from BigQuery mart tables."""
    output = _run(["python", str(REPORT_DIR / "generate_dashboard.py")], cwd=_REPO_ROOT)
    context.log.info(output)


# ── 7. Git push dashboard ─────────────────────────────────────────────────────

@asset(deps=[generate_dashboard])
def git_push_dashboard(context: AssetExecutionContext) -> None:
    """Commit and push the refreshed dashboard HTML to GitHub Pages."""
    _run(["git", "add", "docs/index.html", "docs/customers.json"], cwd=_REPO_ROOT)
    try:
        _run(
            ["git", "commit", "-m", "dashboard: automated data refresh"],
            cwd=_REPO_ROOT,
        )
    except Exception as e:
        if "nothing to commit" in str(e) or "nothing added to commit" in str(e):
            context.log.info("Dashboard unchanged — nothing to commit.")
            return
        raise
    output = _run(["git", "push"], cwd=_REPO_ROOT)
    context.log.info(output)


# ── 8. Declining-seller alert ─────────────────────────────────────────────────

@asset(deps=[dbt_marts])
def alert_declining_sellers(context: AssetExecutionContext) -> None:
    """Email an alert when any seller has trend_status != 'stable' in mart_seller_health."""
    from google.cloud import bigquery

    client = bigquery.Client.from_service_account_json(str(KEYFILE))
    query = f"""
        SELECT seller_id, trend_status
        FROM `{BQ_MARTS}.mart_seller_health`
        WHERE trend_status != 'stable'
        ORDER BY trend_status, seller_id
    """
    rows = list(client.query(query).result())

    if not rows:
        context.log.info("All sellers stable — no alert needed.")
        return

    gmail_address = os.environ["GMAIL_ADDRESS"]
    gmail_password = os.environ["GMAIL_APP_PASSWORD"]
    recipient     = os.environ["ALERT_RECIPIENT"]

    lines = [f"  {r['seller_id']}  —  {r['trend_status']}" for r in rows]
    body  = (
        f"{len(rows)} seller(s) are NOT stable and may need intervention:\n\n"
        + "\n".join(lines)
        + "\n\nCheck the Olist dashboard for details."
    )

    msg = MIMEText(body)
    msg["Subject"] = f"[Olist Alert] {len(rows)} seller(s) not stable"
    msg["From"]    = gmail_address
    msg["To"]      = recipient

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(gmail_address, gmail_password)
        server.sendmail(gmail_address, recipient, msg.as_string())

    context.log.info(f"Alert sent to {recipient} — {len(rows)} seller(s) flagged.")
