#!/usr/bin/env python3
"""CI Failure Analyst 配置：所有参数从环境变量（或 .env 文件）读取。"""

import os
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent

# 可选 .env 文件支持（零依赖）：不存在则跳过，不覆盖已有环境变量
_ENV_FILE = SCRIPT_DIR / ".env"
if _ENV_FILE.exists():
    for _line in _ENV_FILE.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _, _v = _line.partition("=")
            os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))

# ---------- 网络 ----------
SSL_VERIFY = os.environ.get("SSL_VERIFY", "true").lower() not in ("false", "0", "no")
HTTP_PROXY = os.environ.get("HTTP_PROXY", "")
HTTPS_PROXY = os.environ.get("HTTPS_PROXY", "")

# ---------- GitHub ----------
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
TARGET_OWNER = os.environ.get("TARGET_OWNER", "sgl-project")
TARGET_REPO = os.environ.get("TARGET_REPO", "sglang")
WORKFLOW_FILE = os.environ.get("WORKFLOW_FILE", "pr-test-npu.yml")

# ---------- 报告仓库 ----------
REPORT_REMOTE = os.environ.get("REPORT_REMOTE", "")
REPORT_BRANCH = os.environ.get("REPORT_BRANCH", "REPORT")
REPORTS_DIR = SCRIPT_DIR / "npu_reports"   # 报告仓库的本地 clone
LOCAL_REPORTS_DIR = SCRIPT_DIR / "reports"  # 本地留存目录

# ---------- LLM ----------
AI_API_KEY = os.environ.get("AI_API_KEY", "")
AI_API_BASE = os.environ.get("AI_API_BASE", "https://api.deepseek.com")
AI_MODEL = os.environ.get("AI_MODEL", "deepseek-chat")

# ---------- 采集与过滤阈值 ----------
CI_STATE_FILE = SCRIPT_DIR / "analyzed_ci_runs.json"
CI_RUN_WINDOW_HOURS = 24         # 仅统计 created_at 距今不超过该时长的 run（覆盖最长耗时 run）
CI_RUN_MAX_PAGES = 20            # 分页安全上限（20 页 × 100 = 2000 条），防止失控
CI_MIN_RUN_DURATION_MIN = 5      # run 总耗时 < 此值视为未跑到测试阶段，跳过
CI_MIN_JOB_DURATION_MIN = 0.5    # job < 此值视为 skip（check-changes/pr-gate 等）
