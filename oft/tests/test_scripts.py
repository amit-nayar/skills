import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def run_script(name, *args):
    return subprocess.check_output(
        [sys.executable, "-B", str(SCRIPTS / name), *map(str, args)], text=True
    )


class MessageTests(unittest.TestCase):
    def test_flat_preview_separates_header_and_bullet(self):
        with tempfile.TemporaryDirectory() as directory:
            outline = Path(directory) / "outline.md"
            outline.write_text("Out for today:\n- Fixed keyboard handling\n")
            preview = run_script("build_message.py", outline, "U_TEST", "--preview")
        self.assertTrue(preview.startswith("Out for today:\n• Fixed keyboard handling\n"))

    def test_payload_fallback_includes_sections_bullets_and_links(self):
        url = "https://github.com/example/sdk/pull/12345"
        with tempfile.TemporaryDirectory() as directory:
            outline = Path(directory) / "outline.md"
            outline.write_text(
                "Out for today:\n\n## SDK\n"
                f"- Fixed keyboard handling [#12345]({url}) **RTR**\n"
                "  - Found the root cause in `insets`\n\n"
                "## Release\n- Handed the build to QA\n"
            )
            payload = json.loads(run_script("build_message.py", outline, "U_TEST"))
        self.assertEqual(payload["channel"], "U_TEST")
        self.assertEqual(
            payload["text"],
            "Out for today:\n\nSDK\n"
            f"• Fixed keyboard handling #12345 ({url}) RTR\n"
            "    ◦ Found the root cause in insets\n\n"
            "Release\n• Handed the build to QA",
        )
        elements = payload["blocks"][0]["elements"]
        lists = [element for element in elements if element["type"] == "rich_text_list"]
        self.assertEqual([item["indent"] for item in lists], [0, 1, 0])
        inline = lists[0]["elements"][0]["elements"]
        self.assertIn({"type": "link", "url": url, "text": "#12345"}, inline)


class SessionTests(unittest.TestCase):
    def test_digest_keeps_refs_beyond_truncation_and_filters_local_day(self):
        records = [
            {"type": "user", "timestamp": "2026-09-23T22:30:00Z",
             "message": {"content": "Investigate keyboard handling"}},
            {"type": "assistant", "timestamp": "2026-09-24T12:00:00Z",
             "message": {"content": [{"type": "text", "text": "x" * 310 + " #12345 AND-123"}]}},
            {"type": "assistant", "timestamp": "2026-09-24T22:30:00Z",
             "message": {"content": "Next day #54321"}},
        ]
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory) / "project"
            project.mkdir()
            transcript = project / "session.jsonl"
            transcript.write_text("".join(json.dumps(record) + "\n" for record in records))
            # Keep the fixture discoverable regardless of the machine's current date.
            os.utime(transcript, (1800000000, 1800000000))
            digest = run_script(
                "extract_sessions.py", "2026-09-24", "--root", directory,
                "--tz", "Europe/Vienna", "--max-chars", "300",
            )
        self.assertIn("2 msgs on 2026-09-24", digest)
        self.assertIn("refs: #12345 AND-123", digest)
        self.assertIn("x" * 300 + " …", digest)
        self.assertNotIn("x" * 301, digest)
        self.assertNotIn("#54321", digest)


if __name__ == "__main__":
    unittest.main()
