"""报告发布：clone/fetch 报告仓库，提交并推送 Markdown 报告。"""

import subprocess
from datetime import datetime

from config import REPORTS_DIR, REPORT_REMOTE, REPORT_BRANCH, SCRIPT_DIR


def _git(args, cwd):
    subprocess.run(["git"] + args, check=True, cwd=str(cwd))


def ensure_report_repo():
    """确保报告仓库存在并是最新的"""
    if not REPORTS_DIR.exists():
        print(f"[git] 克隆报告仓库 {REPORT_REMOTE}...")
        _git(["clone", "-b", REPORT_BRANCH, REPORT_REMOTE, str(REPORTS_DIR)], SCRIPT_DIR)
    else:
        print("[git] 拉取最新...")
        _git(["fetch", "origin", REPORT_BRANCH], REPORTS_DIR)
        _git(["checkout", REPORT_BRANCH], REPORTS_DIR)
        _git(["reset", "--hard", f"origin/{REPORT_BRANCH}"], REPORTS_DIR)


def commit_and_push(report_text: str):
    """提交并推送 ci_report.md"""
    ensure_report_repo()

    now = datetime.now()
    dirname = now.strftime("%Y%m%d_%H%M")
    report_dir = REPORTS_DIR / "report" / dirname
    report_dir.mkdir(parents=True, exist_ok=True)

    (report_dir / "ci_report.md").write_text(report_text, encoding="utf-8")

    msg = f"[CI] NPU CI 监控 {now.strftime('%Y-%m-%d %H:%M')} - 更新 CI 执行报告"
    print(f"[git] 提交: {msg}")
    _git(["add", f"report/{dirname}/ci_report.md"], REPORTS_DIR)
    _git(["commit", "-m", msg], REPORTS_DIR)
    _git(["push", "origin", REPORT_BRANCH], REPORTS_DIR)
    print("[git] 推送成功")
