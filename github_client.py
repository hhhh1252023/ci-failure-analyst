"""GitHub REST API 薄封装：认证、workflow runs、jobs、日志下载、PR 反查。"""

import requests

from config import GITHUB_TOKEN, TARGET_OWNER, TARGET_REPO
from net import request_kwargs

API_BASE = "https://api.github.com"


def github_headers():
    headers = {"Accept": "application/vnd.github+json"}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    return headers


def api_get(url, params=None):
    resp = requests.get(url, headers=github_headers(), params=params, **request_kwargs())
    resp.raise_for_status()
    return resp.json()


def fetch_pr_by_sha(sha):
    """通过 commit SHA 搜索对应的 PR"""
    url = f"{API_BASE}/search/issues"
    params = {"q": f"repo:{TARGET_OWNER}/{TARGET_REPO} type:pr sha:{sha}", "per_page": 1}
    try:
        data = api_get(url, params=params)
        items = data.get("items", [])
        if items:
            pr = items[0]
            return {"number": pr["number"], "title": pr["title"], "html_url": pr["html_url"]}
    except Exception:
        pass
    return None


def fetch_workflow_runs(workflow_file, params):
    url = f"{API_BASE}/repos/{TARGET_OWNER}/{TARGET_REPO}/actions/workflows/{workflow_file}/runs"
    return api_get(url, params=params)


def fetch_run_jobs(run_id):
    url = f"{API_BASE}/repos/{TARGET_OWNER}/{TARGET_REPO}/actions/runs/{run_id}/jobs"
    resp = requests.get(url, params={"per_page": 30}, headers=github_headers(), **request_kwargs())
    resp.raise_for_status()
    return resp.json().get("jobs", [])


def download_job_log(job_id):
    url = f"{API_BASE}/repos/{TARGET_OWNER}/{TARGET_REPO}/actions/jobs/{job_id}/logs"
    resp = requests.get(url, headers=github_headers(), allow_redirects=True, stream=True, **request_kwargs())
    return resp.text
