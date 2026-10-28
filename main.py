#!/usr/bin/env python3
"""CI Failure Analyst 入口：采集 → 归因 → 报告 → 发布。"""

from datetime import datetime

from config import TARGET_OWNER, TARGET_REPO, LOCAL_REPORTS_DIR
from collector import analyze_ci_jobs
from reporter import generate_ci_report
from publisher import commit_and_push


def main():
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] NPU CI 监控开始（仅流水线）")
    print(f"  目标仓库: {TARGET_OWNER}/{TARGET_REPO}")

    ci_results = analyze_ci_jobs()
    if not ci_results:
        print("  无新的 CI 结果")
        return

    print("  生成报告...")
    ci_report = generate_ci_report(ci_results)

    dirname = datetime.now().strftime("%Y%m%d_%H%M")
    local_dir = LOCAL_REPORTS_DIR / dirname
    local_dir.mkdir(parents=True, exist_ok=True)
    (local_dir / "ci_report.md").write_text(ci_report, encoding="utf-8")
    print(f"  本地报告: {local_dir}")

    try:
        print("  推送报告到 GitHub...")
        commit_and_push(ci_report)
    except Exception as e:
        print(f"  [ERROR] Git 推送失败: {e}")
        print(f"  报告已保存在本地: {local_dir}")

    alert_count = sum(
        sum(1 for j in run.get("jobs", []) if j.get("alert"))
        for run in ci_results
    )
    print(f"  CI: {len(ci_results)} 个 run, {alert_count} 个失败任务")


if __name__ == "__main__":
    main()
