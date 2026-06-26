"""HTML report generation for pipeline runs."""

import json
import time
from pathlib import Path
from typing import Optional


def generate_html_report(
    context,
    output_path: str,
) -> str:
    """Generate an HTML metrics report and write it to output_path.

    Returns the path to the generated HTML file.
    """
    metrics = context.metrics
    source_files = list(context.source_code.keys())
    test_passed = context.test_results.get("passed", False)
    coverage = metrics.get("coverage_line", metrics.get("coverage", 0))
    pylint = metrics.get("pylint_score", 0)
    loc = metrics.get("loc", 0)
    attempts = metrics.get("attempts", 1)
    total_time = metrics.get("total_time", 0)
    sec_issues = metrics.get("security_issues", 0)

    status = "PASSED" if context.success else "FAILED"
    status_color = "#22c55e" if context.success else "#ef4444"

    # Build per-file table rows
    per_file_rows = ""
    for entry in metrics.get("per_file", []):
        cov = entry.get("coverage", 0)
        cov_color = "#22c55e" if cov >= 80 else "#f59e0b" if cov > 0 else "#ef4444"
        per_file_rows += f"""
        <tr>
            <td>{entry.get('filename', '')}</td>
            <td>{entry.get('lines', 0)}</td>
            <td style="color:{cov_color}">{cov}%</td>
            <td>{entry.get('issues', 0)}</td>
        </tr>"""

    # Build feedback items rows
    feedback_rows = ""
    for item in context.feedback_items:
        sev_color = {
            "critical": "#ef4444",
            "major": "#f59e0b",
            "minor": "#3b82f6",
            "suggestion": "#6b7280",
        }.get(item.severity, "#6b7280")
        status_text = "Resolved" if item.resolved else "Open"
        feedback_rows += f"""
        <tr>
            <td style="color:{sev_color}">{item.severity.upper()}</td>
            <td>{item.source}</td>
            <td>{item.description[:200]}</td>
            <td>{item.location or ''}</td>
            <td>{status_text}</td>
        </tr>"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Pipeline Report - {context.run_id[:8]}</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; margin: 0; padding: 20px; background: #0f172a; color: #e2e8f0; }}
        h1 {{ color: #38bdf8; }}
        h2 {{ color: #818cf8; margin-top: 2em; }}
        .summary {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; margin: 1em 0; }}
        .card {{ background: #1e293b; border-radius: 8px; padding: 16px; text-align: center; }}
        .card .value {{ font-size: 2em; font-weight: bold; }}
        .card .label {{ color: #94a3b8; font-size: 0.9em; }}
        table {{ width: 100%; border-collapse: collapse; margin: 1em 0; background: #1e293b; border-radius: 8px; overflow: hidden; }}
        th {{ background: #334155; padding: 12px; text-align: left; }}
        td {{ padding: 10px 12px; border-top: 1px solid #334155; }}
        .status-badge {{ display: inline-block; padding: 4px 12px; border-radius: 9999px; font-weight: bold; font-size: 0.9em; }}
    </style>
</head>
<body>
    <h1>Pipeline Report</h1>
    <p>Run ID: <code>{context.run_id}</code> | Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}</p>

    <div class="summary">
        <div class="card">
            <div class="value" style="color:{status_color}">{status}</div>
            <div class="label">Overall Status</div>
        </div>
        <div class="card">
            <div class="value">{len(source_files)}</div>
            <div class="label">Files Generated</div>
        </div>
        <div class="card">
            <div class="value">{loc}</div>
            <div class="label">Lines of Code</div>
        </div>
        <div class="card">
            <div class="value">{coverage}%</div>
            <div class="label">Line Coverage</div>
        </div>
        <div class="card">
            <div class="value">{pylint:.1f}</div>
            <div class="label">Pylint Score</div>
        </div>
        <div class="card">
            <div class="value">{total_time:.1f}s</div>
            <div class="label">Execution Time</div>
        </div>
        <div class="card">
            <div class="value">{sec_issues}</div>
            <div class="label">Security Issues</div>
        </div>
        <div class="card">
            <div class="value">{attempts}</div>
            <div class="label">Attempts</div>
        </div>
    </div>

    <h2>Per-File Metrics</h2>
    <table>
        <thead><tr><th>File</th><th>Lines</th><th>Coverage</th><th>Issues</th></tr></thead>
        <tbody>{per_file_rows or '<tr><td colspan="4" style="text-align:center;color:#94a3b8">No per-file data</td></tr>'}</tbody>
    </table>

    <h2>Feedback Items</h2>
    <table>
        <thead><tr><th>Severity</th><th>Source</th><th>Description</th><th>Location</th><th>Status</th></tr></thead>
        <tbody>{feedback_rows or '<tr><td colspan="5" style="text-align:center;color:#94a3b8">No feedback items</td></tr>'}</tbody>
    </table>

    <h2>Generated Files</h2>
    <ul>
        {''.join(f'<li><code>{f}</code></li>' for f in source_files)}
    </ul>
</body>
</html>"""

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")
    return str(path)
