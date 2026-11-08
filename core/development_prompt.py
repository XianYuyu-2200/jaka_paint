"""Helpers for loading the reusable development prompt from its Markdown guide."""


def extract_prompt(markdown: str) -> str:
    """Return only the reusable prompt block, excluding the task template."""
    marker = "```text\n"
    start = markdown.find(marker)
    if start < 0:
        raise ValueError("提示词文件中缺少 text 代码块")

    start += len(marker)
    end = markdown.find("\n```", start)
    if end < 0:
        raise ValueError("提示词代码块没有正确结束")

    prompt = markdown[start:end].strip()
    if not prompt:
        raise ValueError("提示词代码块为空")
    return prompt
