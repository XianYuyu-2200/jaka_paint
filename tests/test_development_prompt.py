from pathlib import Path
import unittest

from core.development_prompt import extract_prompt


ROOT = Path(__file__).resolve().parents[1]


class DevelopmentPromptTest(unittest.TestCase):
    def test_extracted_prompt_excludes_task_template(self):
        markdown = (ROOT / "AI_DEVELOPMENT_PROMPT.md").read_text(encoding="utf-8")
        prompt = extract_prompt(markdown)

        self.assertIn("【开发阶段】", prompt)
        self.assertIn("【安全与质量红线】", prompt)
        self.assertNotIn("当前任务模板", prompt)
        self.assertNotIn("【阶段编号】", prompt)

    def test_malformed_prompt_block_is_rejected(self):
        with self.assertRaises(ValueError):
            extract_prompt("```text\nunfinished")


if __name__ == "__main__":
    unittest.main()
