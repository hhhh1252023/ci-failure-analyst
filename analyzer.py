"""LLM 归因：日志关键片段 → 结构化分类 JSON（JSON 约束输出）。"""

import json
import re

import requests

from config import AI_API_KEY, AI_API_BASE, AI_MODEL
from net import request_kwargs


def _clip_log(log_text):
    # 错误通常在末尾：开头 2000 字 + 结尾 5000 字，避免超长日志
    if len(log_text) > 8000:
        return log_text[:2000] + "\n...(中间省略)...\n" + log_text[-5000:]
    return log_text


def ai_analyze(job_name, log_text):
    """将日志片段发给 LLM，返回 {"category", "summary", "detail"}"""
    if not AI_API_KEY:
        return "AI_API_KEY 未配置，跳过分析"

    prompt = f"""你是 sglang NPU CI 调试助手。以下是一个失败的 GitHub Actions 作业的日志。
请用**中文**简要分析失败原因（不超过100字），并给出分类：

作业名称: {job_name}

日志:
{_clip_log(log_text)}

请用JSON格式回答：
{{"category": "性能回归|精度回归|环境问题|代码错误|超时|其他", "summary": "一句话原因（中文）", "detail": "具体说明（中文，100字以内）"}}"""

    try:
        resp = requests.post(
            f"{AI_API_BASE}/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {AI_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": AI_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.1,
                "max_tokens": 300,
            },
            **request_kwargs(),
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"].strip()
        json_match = re.search(r"\{[^{}]*\}", content, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
        return {"category": "未知", "summary": content[:100], "detail": content[:100]}
    except Exception as e:
        return {"category": "AI调用失败", "summary": str(e)[:100], "detail": str(e)[:100]}
