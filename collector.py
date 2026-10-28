"""采集与分析：时间窗拉取 workflow runs + 增量状态持久化 + 失败 job 归因。"""

import json
from datetime import datetime, timedelta, timezone

from config import (
    CI_STATE_FILE, CI_RUN_WINDOW_HOURS, CI_RUN_MAX_PAGES,
    CI_MIN_RUN_DURATION_MIN, CI_MIN_JOB_DURATION_MIN, WORKFLOW_FILE,
)
from github_client import fetch_workflow_runs, fetch_run_jobs, download_job_log, fetch_pr_by_sha
from log_parser import extract_log_errors
from analyzer import ai_analyze


def load_state():
    if CI_STATE_FILE.exists():
        return json.loads(CI_STATE_FILE.read_text(encoding="utf-8"))
    return {}


def save_state(state):
    CI_STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def _parse_iso(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def fetch_ci_runs():
    """获取 workflow 最近完成的 runs（分页，每次最多 100）。

    用「created_at 时间窗」而非固定条数作为扫描边界：长耗时的 run 会
    created 很早、completed 很晚。若按「最近 N 条(按 created 排序)」取数，
    等它 finally completed 时，其 created_at 早已被挤出窗口而被漏掉。
    这里只保留窗口内创建的 completed run，确保这类 run 不会被遗漏。
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=CI_RUN_WINDOW_HOURS)

    all_runs = []
    page = 1
    while page <= CI_RUN_MAX_PAGES:
        data = fetch_workflow_runs(WORKFLOW_FILE, params={
            "per_page": 100,
            "status": "completed",
            "page": page,
        })
        runs = data.get("workflow_runs", [])
        if not runs:
            break
        all_runs.extend(runs)
        # runs 按 created_at 倒序返回；本页最旧一条已早于窗口下界即可停止
        oldest = None
        for r in runs:
            t = _parse_iso(r.get("created_at"))
            if t and (oldest is None or t < oldest):
                oldest = t
        if oldest and oldest < cutoff:
            break
        page += 1

    return [r for r in all_runs if (t := _parse_iso(r.get("created_at"))) and t >= cutoff]


def _is_fast_fail(job):
    """健康检查步骤失败导致的级联取消，单独归类，避免一次故障统计成 N 个失败"""
    steps = job.get("steps", [])
    failed_step = next((st for st in steps if st.get("conclusion") == "failure"), None)
    return bool(failed_step) and (
        "check-pr-test-health" in (failed_step.get("name") or "")
        or "Check PR test health" in (failed_step.get("name") or "")
    )


def _analyze_job(job, run):
    """单个 job：算耗时、下载日志、提取用例、必要时 LLM 归因"""
    name = job["name"]
    con = job.get("conclusion", "unknown")
    j_dur = 0
    if job.get("started_at") and job.get("completed_at"):
        s = datetime.fromisoformat(job["started_at"].replace("Z", "+00:00"))
        e = datetime.fromisoformat(job["completed_at"].replace("Z", "+00:00"))
        j_dur = (e - s).total_seconds() / 60

    if j_dur < CI_MIN_JOB_DURATION_MIN:
        return None

    job_entry = {
        "name": name,
        "conclusion": con,
        "duration_min": round(j_dur, 1),
        "completed_at": job.get("completed_at", ""),
        "html_url": job.get("html_url", ""),
        "run_id": run["id"],
    }

    if con in ("failure", "timed_out", "cancelled"):
        job_entry["alert"] = True
        if _is_fast_fail(job):
            job_entry["fast_fail"] = True
            job_entry["ai_analysis"] = {
                "category": "健康检查失败",
                "summary": "check-pr-test-health 步骤失败（fast-fail 级联）",
            }
            print(f"    ⏭️ 健康检查失败（fast-fail）: {name}")
        else:
            print(f"    ⚠️ 失败 job: {name} ({j_dur:.1f}min)，下载日志 AI 分析...")
            try:
                log_text = download_job_log(job["id"])
                ai_result = ai_analyze(name, log_text)
                job_entry["ai_analysis"] = ai_result
                errors = extract_log_errors(log_text)
                job_entry["errors_extracted"] = {k: v for k, v in errors.items() if v}
                print(f"      AI 判定: [{ai_result.get('category', '?')}] {ai_result.get('summary', '?')[:60]}")
            except Exception as e:
                job_entry["ai_analysis"] = {"category": "日志下载失败", "summary": str(e)[:100]}
                print(f"      日志下载失败: {e}")
    elif con == "success":
        job_entry["alert"] = False
        print(f"    ✅ 成功 job: {name} ({j_dur:.1f}min)，下载日志提取用例...")
        try:
            log_text = download_job_log(job["id"])
            errors = extract_log_errors(log_text)
            job_entry["errors_extracted"] = {k: v for k, v in errors.items() if v}
        except Exception as e:
            print(f"      日志下载失败: {e}")
    else:
        job_entry["alert"] = False

    return job_entry


def analyze_ci_jobs():
    """主入口：拉取 CI runs，分析各 job 状态，返回结构化结果"""
    print("\n[CI] 获取 NPU CI 执行结果...")
    state = load_state()

    try:
        runs = fetch_ci_runs()
    except Exception as e:
        print(f"  [CI WARN] 获取 CI runs 失败: {e}")
        return None

    print(f"  [CI] 拉取到 {len(runs)} 个 completed runs")

    report_runs = []

    for run in runs:
        run_id = str(run["id"])
        # 跳过已分析过的 run（增量分析，幂等）
        if run_id in state:
            continue

        run_dur = 0
        if run.get("run_started_at") and run.get("updated_at"):
            s = datetime.fromisoformat(run["run_started_at"].replace("Z", "+00:00"))
            e = datetime.fromisoformat(run["updated_at"].replace("Z", "+00:00"))
            run_dur = (e - s).total_seconds() / 60

        if run_dur < CI_MIN_RUN_DURATION_MIN:
            # 快速失败（pr-gate 没过），跳过且不记录，减少报告噪音
            continue

        print(f"  [CI] 分析 Run #{run_id} ({run_dur:.1f}min) branch={run['head_branch']}...")

        try:
            jobs = fetch_run_jobs(run_id)
        except Exception as e:
            print(f"    [CI WARN] 获取 jobs 失败: {e}")
            continue

        run_entry = {
            "run_id": run_id,
            "html_url": run["html_url"],
            "branch": run["head_branch"],
            "conclusion": run["conclusion"],
            "duration_min": round(run_dur, 1),
            "created_at": run["created_at"],
            "head_sha": run.get("head_sha", ""),
            "jobs": [],
        }

        pr_info = fetch_pr_by_sha(run.get("head_sha", ""))
        if pr_info:
            run_entry["pr_number"] = pr_info["number"]
            run_entry["pr_title"] = pr_info["title"]
            run_entry["pr_html_url"] = pr_info["html_url"]
            print(f"    → 关联 PR: #{pr_info['number']} - {pr_info['title']}")

        for job in jobs:
            job_entry = _analyze_job(job, run)
            if job_entry:
                run_entry["jobs"].append(job_entry)

        if run_entry["jobs"]:
            report_runs.append(run_entry)

        state[run_id] = {
            "verdict": run["conclusion"],
            "branch": run["head_branch"],
            "duration_min": round(run_dur, 1),
            "analyzed_at": datetime.now(timezone.utc).isoformat(),
        }

    save_state(state)
    print(f"  [CI] 本次新增分析: {len(report_runs)} 个 run")
    return report_runs
