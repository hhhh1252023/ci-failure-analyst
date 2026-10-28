"""报告生成：汇总统计（成功率/耗时 Top/用例失败榜）+ 每个 run 的归因明细，输出 Markdown。"""

from datetime import datetime, timezone


def generate_ci_report(ci_results) -> str:
    """生成 CI 监控报告"""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    all_success_jobs = [
        j for run_entry in ci_results for j in run_entry.get("jobs", [])
        if j.get("conclusion") == "success" and not j.get("alert")
    ]
    all_failed_jobs = [
        j for run_entry in ci_results for j in run_entry.get("jobs", [])
        if j.get("alert")
    ]
    failed_runs = [
        run_entry for run_entry in ci_results
        if any(j.get("alert") for j in run_entry.get("jobs", []))
    ]

    top10_success = sorted(all_success_jobs, key=lambda x: x["duration_min"], reverse=True)[:10]
    top10_failed = sorted(all_failed_jobs, key=lambda x: x["duration_min"], reverse=True)[:10]
    avg_success_dur = (
        sum(j["duration_min"] for j in all_success_jobs) / len(all_success_jobs)
        if all_success_jobs else 0.0
    )

    lines = []
    lines.append("# NPU CI 执行监控")
    lines.append(f"**生成时间**: {now}")
    lines.append(f"**分析 Run 数**: {len(ci_results)}")
    lines.append("")
    lines.append("---")
    lines.append("")

    # 1. 总结区
    lines.append("## 📊 本次执行总结")
    lines.append("")
    lines.append(f"- **成功 Job 数**: {len(all_success_jobs)}")
    lines.append(f"- **失败 Run 数**: {len(failed_runs)}")
    lines.append(f"- **成功 Job 平均耗时**: {avg_success_dur:.1f}min")
    lines.append("")

    if top10_success:
        lines.append("### ✅ 耗时最长的成功 Job（Top 10）")
        lines.append("")
        lines.append("| Job 名称 | 耗时 | 所属 Run | 链接 |")
        lines.append("|----------|------|----------|------|")
        for j in top10_success:
            lines.append(f"| {j['name']} | {j['duration_min']}min | #{j.get('run_id','?')} | [job link]({j['html_url']}) |")
        lines.append("")

    if top10_failed:
        lines.append("### ❌ 耗时最长的失败 Job（Top 10）")
        lines.append("")
        lines.append("| Job 名称 | 耗时 | 所属 Run | 链接 |")
        lines.append("|----------|------|----------|------|")
        for j in top10_failed:
            lines.append(f"| {j['name']} | {j['duration_min']}min | #{j.get('run_id','?')} | [job link]({j['html_url']}) |")
        lines.append("")

    lines.append("---")
    lines.append("")

    # 2. Job 统计
    lines.append("## 📋 各任务执行统计")
    lines.append("")
    job_stats = {}
    for run_entry in ci_results:
        for j in run_entry.get("jobs", []):
            name = j["name"]
            if name not in job_stats:
                job_stats[name] = {"total": 0, "success": 0, "failure": 0, "check_health_failure": 0, "cancelled": 0, "failed_links": []}
            job_stats[name]["total"] += 1
            if j.get("conclusion") == "success":
                job_stats[name]["success"] += 1
            elif j.get("fast_fail"):
                job_stats[name]["check_health_failure"] += 1
            elif j.get("conclusion") == "cancelled":
                job_stats[name]["cancelled"] += 1
            else:
                job_stats[name]["failure"] += 1
                if len(job_stats[name]["failed_links"]) < 5:
                    job_stats[name]["failed_links"].append(j["html_url"])

    job_stats_sorted = sorted(
        [(name, s) for name, s in job_stats.items() if s["failure"] + s["check_health_failure"] > 0],
        key=lambda x: x[1]["failure"] + x[1]["check_health_failure"],
        reverse=True,
    )

    if job_stats_sorted:
        lines.append("| 任务名称 | 执行次数 | 成功 | 执行失败 | 健康检查失败 | 取消 | 失败任务链接 |")
        lines.append("|----------|----------|------|---------|-------------|------|-------------|")
        for name, s in job_stats_sorted:
            if s["failure"] > 0 and s["failed_links"]:
                links_str = "<br>".join(f"[job link {i + 1}]({url})" for i, url in enumerate(s["failed_links"]))
            else:
                links_str = "-"
            lines.append(f"| {name} | {s['total']} | {s['success']} | {s['failure']} | {s['check_health_failure']} | {s['cancelled']} | {links_str} |")
        lines.append("")
    else:
        lines.append("*无执行失败的任务。*")
        lines.append("")

    lines.append("---")
    lines.append("")

    # 3. 用例统计
    lines.append("## 📋 各用例失败统计")
    lines.append("")
    test_case_stats = {}
    for run_entry in ci_results:
        for j in run_entry.get("jobs", []):
            for tc in j.get("errors_extracted", {}).get("all_tests", []):
                name = tc["name"]
                if name not in test_case_stats:
                    test_case_stats[name] = {"total": 0, "passed": 0, "failed": 0, "failed_job_links": []}
                test_case_stats[name]["total"] += 1
                if tc["status"] == "PASSED":
                    test_case_stats[name]["passed"] += 1
                elif tc["status"] == "FAILED":
                    test_case_stats[name]["failed"] += 1
                    job_link = f"[{j['name']}]({j['html_url']})"
                    if job_link not in test_case_stats[name]["failed_job_links"]:
                        if len(test_case_stats[name]["failed_job_links"]) < 3:
                            test_case_stats[name]["failed_job_links"].append(job_link)

    sorted_tcs = sorted(
        [(n, s) for n, s in test_case_stats.items() if s["failed"] > 0],
        key=lambda x: x[1]["failed"], reverse=True,
    )

    if sorted_tcs:
        lines.append("| 用例名称 | 执行次数 | 成功 | 失败 | 失败任务链接 |")
        lines.append("|----------|----------|------|------|-------------|")
        for tc_name, s in sorted_tcs:
            links_str = "<br>".join(s["failed_job_links"]) if s["failed_job_links"] else "-"
            lines.append(f"| `{tc_name}` | {s['total']} | {s['passed']} | {s['failed']} | {links_str} |")
        lines.append("")
    else:
        lines.append("*本次分析未发现失败用例。*")
        lines.append("")

    lines.append("---")
    lines.append("")

    # 4. 失败 CI Run 表格
    if failed_runs:
        lines.append("### ⚠️ 失败的 CI Run")
        lines.append("")
        lines.append("| Run ID | 分支 | 耗时 | 失败任务数 | 失败的任务 | 结论 | 链接 |")
        lines.append("|--------|------|------|-----------|-----------|------|------|")
        for r in sorted(failed_runs, key=lambda x: x["duration_min"], reverse=True):
            real_fail_jobs = [j for j in r.get("jobs", []) if j.get("alert") and not j.get("fast_fail")]
            alert_count = len(real_fail_jobs)
            alert_names = ", ".join(j["name"] for j in real_fail_jobs)
            run_id_str = f"#{r['run_id']}"
            if r.get("pr_number"):
                run_id_str += f"<br>[#{r['pr_number']} {r['pr_title']}]({r['pr_html_url']})"
            lines.append(f"| {run_id_str} | `{r['branch']}` | {r['duration_min']}min | {alert_count} | {alert_names} | {r['conclusion']} | [run link]({r['html_url']}) |")
        lines.append("")

    lines.append("---")
    lines.append("")

    # 5. 每个 run 的明细
    for run_entry in ci_results:
        alert_jobs = [j for j in run_entry.get("jobs", []) if j.get("alert")]
        normal_jobs = [j for j in run_entry.get("jobs", []) if not j.get("alert")]

        lines.append("")
        lines.append(f"## [Run #{run_entry['run_id']}]({run_entry['html_url']})")
        lines.append(f"- **分支**: `{run_entry['branch']}`")
        lines.append(f"- **总耗时**: {run_entry['duration_min']}min | **结论**: {run_entry['conclusion']}")
        lines.append(f"- **workflow 链接**: {run_entry['html_url']}")
        lines.append("")

        if alert_jobs:
            lines.append("### ⚠️ 失败/超时任务")
            lines.append("")
            lines.append("| 任务 | 耗时 | 分类 | AI 分析 | 链接 |")
            lines.append("|------|------|------|---------|------|")
            for j in alert_jobs:
                ai = j.get("ai_analysis", {})
                lines.append(
                    f"| {j['name']} | {j['duration_min']}min | "
                    f"{ai.get('category','?')} | {ai.get('summary','?')} | "
                    f"[job link]({j['html_url']}) |"
                )
            lines.append("")

            for j in alert_jobs:
                ai = j.get("ai_analysis", {})
                if ai.get("detail") or j.get("errors_extracted", {}).get("failed_tests"):
                    lines.append(f"- **{j['name']}**: {ai.get('detail', '')}")
                    failed_tests = j.get("errors_extracted", {}).get("failed_tests", [])
                    if failed_tests:
                        lines.append(f"  - 失败用例: {', '.join(failed_tests[:5])}")
                    lines.append(f"  链接: {j['html_url']}")
                lines.append("")

        if normal_jobs:
            lines.append("### 正常任务")
            lines.append("")
            lines.append("| 任务 | 耗时 | 结果 | 链接 |")
            lines.append("|------|------|------|------|")
            for j in normal_jobs:
                lines.append(
                    f"| {j['name']} | {j['duration_min']}min | {j['conclusion']} | "
                    f"[job link]({j['html_url']}) |"
                )
            lines.append("")

    lines.append("")
    lines.append("---")
    lines.append("*Auto-generated by ci-failure-analyst*")
    return "\n".join(lines)
