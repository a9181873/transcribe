import json
import tempfile
import unittest
from pathlib import Path

from transcribe_pro import write_transcription_artifacts


class TranscriptionArtifactTests(unittest.TestCase):
    def test_writes_downloadable_transcript_formats(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            paths = write_transcription_artifacts(
                output_dir,
                "demo",
                "備援逐字稿",
                [
                    {"timestamp": (0.0, 1.25), "speaker": 0, "text": "<|zh|>大家好。"},
                    {"timestamp": (1.25, 3.5), "speaker": 1, "text": "今天討論部署。"},
                ],
            )

            self.assertEqual(set(paths), {"transcript", "json", "srt", "vtt"})
            self.assertIn("說話人 A", paths["transcript"].read_text(encoding="utf-8"))
            self.assertIn(
                "00:00:00,000 --> 00:00:01,250",
                paths["srt"].read_text(encoding="utf-8"),
            )
            self.assertTrue(
                paths["vtt"].read_text(encoding="utf-8").startswith("WEBVTT")
            )
            payload = json.loads(paths["json"].read_text(encoding="utf-8"))
            self.assertEqual(payload["segments"][1]["speaker"], "speaker_1")
            self.assertEqual(payload["segments"][0]["text"], "大家好。")

    def test_falls_back_to_plain_text_when_no_segments(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = write_transcription_artifacts(
                Path(temp_dir), "empty", "只有純文字", []
            )
            self.assertIn(
                "[未知時間] 說話人未知：只有純文字",
                paths["transcript"].read_text(encoding="utf-8"),
            )
            self.assertEqual(
                json.loads(paths["json"].read_text(encoding="utf-8"))["segments"][0][
                    "start"
                ],
                None,
            )
            self.assertEqual(paths["srt"].read_text(encoding="utf-8"), "")


if __name__ == "__main__":
    unittest.main()
