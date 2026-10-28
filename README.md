# CI Failure Analyst

An autonomous agent that monitors GitHub Actions CI pipelines, triages failure logs
with a hybrid **regex pre-parse + LLM** approach, and publishes daily Markdown
reports — fully unattended.

Originally built to monitor the NPU CI pipelines of a large LLM inference framework
(thousands of jobs/week), it has run unattended in production for 3+ months and
produced 150+ daily reports.

## Why

Active open-source projects run dozens of CI pipelines daily. When they fail,
someone has to download logs, scan thousands of lines, and figure out whether it's
an environment issue, a flaky test, or a real regression. This agent automates
that loop end-to-end.

## How It Works

1. **Collect** — Fetches workflow runs in a *sliding time window* (not just
   "latest N") so long-running jobs are never missed. Analyzed runs are persisted
   to a state file, making each run incremental and idempotent.
2. **Pre-parse** — Deterministic regex extraction first: pytest results,
   tracebacks, assertion errors, per-case PASS/FAIL. Only distilled fragments are
   sent to the LLM (saves tokens, reduces hallucination).
3. **Triage** — LLM classifies each failure into a constrained set:
   `performance regression / accuracy regression / environment / code bug /
   timeout / fast-fail cascade`, returned as structured JSON.
4. **Report** — Generates a Markdown report: success-rate stats, top failing
   cases, slowest jobs, per-run triage details with PR cross-links.
   Auto-committed and pushed to a report branch.

## Project Structure

```
config.py        # all settings via env vars / .env (no secrets in code)
net.py           # shared HTTP kwargs (proxy, SSL, timeout)
github_client.py # GitHub REST API: runs, jobs, logs, PR lookup by SHA
log_parser.py    # deterministic regex pre-parsing
analyzer.py      # LLM triage with JSON-constrained output
collector.py     # time-window fetching + incremental state + job analysis
reporter.py      # Markdown report generation
publisher.py     # git commit & push to report repo
main.py          # orchestration entry point
```

## Quick Start

```bash
pip install -r requirements.txt

cat > .env <<'EOF'
GITHUB_TOKEN=ghp_xxx            # needs repo + actions read scope
AI_API_KEY=sk-xxx               # OpenAI-compatible API key (e.g. DeepSeek)
REPORT_REMOTE=https://github.com/you/your-report-repo.git
EOF

python main.py
```

All knobs are optional env vars — see `.env.example`. Key ones:

| Variable | Default | Description |
|---|---|---|
| `TARGET_OWNER` / `TARGET_REPO` | `sgl-project` / `sglang` | Monitored repository |
| `WORKFLOW_FILE` | `pr-test-npu.yml` | Workflow to monitor |
| `CI_RUN_WINDOW_HOURS` | `24` | Sliding window for run collection |
| `AI_API_BASE` / `AI_MODEL` | DeepSeek | Any OpenAI-compatible endpoint |

## Sample Output

- [Example daily report](https://github.com/hhhh1252023/pass/blob/REPORT/report/20261013_0759/ci_report.md)
- [Full report archive (150+ reports)](https://github.com/hhhh1252023/pass/tree/REPORT/report)

## Design Notes

- **Time window over count-based fetching** — long-running CI jobs are created
  early but complete late; "latest N" queries drop them by the time they finish.
- **Fast-fail cascade detection** — one health-check failure cancels every job in
  a run; counting them as N separate failures would distort statistics, so they
  are classified as a single category.
- **Two-stage parsing** — regex does deterministic extraction, the LLM only does
  judgment. Each layer compensates for the other's weakness.
- **Idempotency via persisted state** — re-running the agent never re-analyzes a
  run or double-charges the LLM API.

## Security

All credentials are read from environment variables (or a gitignored `.env`).
Never commit tokens to the repository — if a key was ever exposed, revoke it
first, then remove it from history.
