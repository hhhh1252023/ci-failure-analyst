"""日志预解析（确定性正则层）：提取测试结果、断言、Traceback，供报告与 LLM 归因使用。"""

import re


def _strip_line(line):
    # 去掉 GitHub Actions 时间戳前缀（如 2026-08-23T15:48:32.6520241Z）
    s = re.sub(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z\s*", "", line)
    # 去掉日志乱码图标前缀
    s = re.sub(r"^[\u00e2\u0080-\u00a0\s]+", "", s)
    return s.strip()


def extract_log_errors(log_text):
    """从日志中提取关键错误片段和测试用例结果（不调 AI，做预截取）"""
    lines = log_text.split("\n")
    result = {"assertions": [], "tracebacks": [], "final_result": "", "failed_tests": [], "all_tests": []}

    # 同一 job 内对 (name, status) 去重
    seen_tests = set()

    def add_test(name, status):
        if not name or len(name) > 120:
            return
        key = (name, status)
        if key not in seen_tests:
            seen_tests.add(key)
            result["all_tests"].append({"name": name, "status": status})

    for line in lines:
        if "AssertionError" in line:
            result["assertions"].append(line.strip()[:300])
        if "FAILED (failures=" in line or "FAILED (errors=" in line:
            result["final_result"] = line.strip()
        if "Accuracy:" in line:
            result["final_result"] += " | " + line.strip()

        s = _strip_line(line)
        if not s:
            continue

        # 1) [server-test] PASSED/FAILED diffusion testcase: <name>
        m = re.match(r"\[server-test\]\s+(PASSED|FAILED)\s+diffusion\s+testcase:\s*(\S+)", s)
        if m:
            add_test(m.group(2), m.group(1))
            if m.group(1) == "FAILED":
                result["failed_tests"].append(m.group(2))
            continue

        # 2) [Consistency Check] <name>: PASSED/FAILED
        m = re.match(r"\[Consistency Check\]\s+(\S+?):\s*(PASSED|FAILED)", s)
        if m:
            add_test(m.group(1), m.group(2))
            if m.group(2) == "FAILED":
                result["failed_tests"].append(m.group(1))
            continue

        # 3) pytest 形式：PASSED/FAILED <path>.py::<Class>::<method>[<param>]
        m = re.match(r"^(PASSED|FAILED):?\s+(.+?\.py)::(\S+)", s)
        if m:
            full = m.group(3).rstrip(" -")
            pm = re.search(r"\[([^\]]+)\]$", full)
            name = pm.group(1) if (pm and pm.group(1)) else full
            add_test(name, m.group(1))
            if m.group(1) == "FAILED":
                result["failed_tests"].append(name)
            continue

        # 4) perf/acc 形式：FAILED: <.../test_npu_<case>
        m = re.match(r"^FAILED:\s+(\S+)", s)
        if m:
            path = m.group(1).replace("\\", "/").rstrip("/")
            name = path.rsplit("/", 1)[-1]
            if name.startswith("test_"):
                name = name[5:]
            add_test(name, "FAILED")
            result["failed_tests"].append(name)

    # 找最后一个 Traceback（保留前 15 行）
    in_tb = False
    tb_lines = []
    for line in lines:
        if "Traceback (most recent call last)" in line:
            tb_lines = [line.strip()]
            in_tb = True
        elif in_tb:
            tb_lines.append(line.strip())
            if len(tb_lines) > 15:
                break
    if tb_lines:
        result["tracebacks"] = tb_lines

    return result
