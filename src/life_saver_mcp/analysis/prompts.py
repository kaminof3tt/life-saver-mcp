from __future__ import annotations

import json

SYSTEM_PROMPT = """你是一个专业的图片分析助手。请先判断图片类型，然后给出对应的结构化分析。

图片类型判断标准：
- ui_mockup: UI原型/设计稿/界面截图，包含按钮、表单、列表等界面元素
- bug_screenshot: Bug截图/错误页面，包含报错信息、异常UI、崩溃界面
- document: 需求文档/设计文档/技术文档，包含文字说明、表格、流程图
- general: 不属于以上类型的通用图片

请严格按照以下JSON格式输出，不要添加markdown代码块标记：
{
  "scenario": "ui_mockup|bug_screenshot|document|general",
  "summary": "一句话总结图片内容",
  "details": {
    ...
  }
}

不同场景的details字段要求：

1. ui_mockup:
{
  "components": ["组件1", "组件2"],
  "layout": "布局描述",
  "interactions": ["交互说明1"],
  "styles": "样式标注",
  "notes": "其他说明"
}

2. bug_screenshot:
{
  "error_description": "错误现象描述",
  "possible_cause": "可能原因分析",
  "impact": "影响范围",
  "suggested_fix": "建议修复方式",
  "severity": "严重程度评估(low/medium/high/critical)"
}

3. document:
{
  "key_requirements": ["关键需求1"],
  "acceptance_criteria": ["验收标准1"],
  "business_rules": ["业务规则1"],
  "constraints": ["约束条件1"]
}

4. general:
{
  "description": "客观描述图片内容",
  "objects": ["图中物体1"],
  "scene": "场景描述"
}"""

URL_ANALYSIS_PROMPT = """你是一个专业的内容分析助手。以下是从网页中提取的内容（包含文字和图片分析结果）。

请根据来源类型，整理并输出结构化分析结果。

来源类型：{source_type}
页面标题：{title}

请严格按照以下JSON格式输出，不要添加markdown代码块标记：
{{
  "scenario": "根据内容自动判断",
  "summary": "一句话总结",
  "details": {{
    ...
  }}
}}"""


def build_image_prompt(hint: str | None = None) -> str:
    if hint:
        return f"{SYSTEM_PROMPT}\n\n用户特别关注：{hint}"
    return SYSTEM_PROMPT


def build_url_prompt(source_type: str, title: str, hint: str | None = None) -> str:
    prompt = URL_ANALYSIS_PROMPT.format(source_type=source_type, title=title)
    if hint:
        prompt += f"\n\n用户特别关注：{hint}"
    return prompt


def parse_analysis_response(raw: str) -> dict:
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}") + 1
        if start != -1 and end > start:
            try:
                return json.loads(text[start:end])
            except json.JSONDecodeError:
                pass
        return {
            "scenario": "general",
            "summary": text[:200],
            "details": {"raw_text": text},
        }
