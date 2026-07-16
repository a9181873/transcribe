import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import transcribe_pro


class FakeAudioProcessor:
    def transcribe_audio(self, _audio_path):
        return (
            "這是已完成的逐字稿。",
            [
                {
                    "timestamp": (0.0, 1.5),
                    "speaker": None,
                    "text": "這是已完成的逐字稿。",
                }
            ],
        )


class ProcessAudioFileTests(unittest.TestCase):
    def test_writes_transcription_artifacts_before_requesting_summary(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            audio_path = root / "meeting.wav"
            audio_path.write_bytes(b"placeholder")
            config = transcribe_pro.AppConfig(output_dir=root / "output")
            result_dir = config.output_dir / audio_path.stem
            transcript_path = result_dir / "meeting_逐字稿.txt"
            call_order = []

            real_writer = transcribe_pro.write_transcription_artifacts

            def record_artifact_write(*args, **kwargs):
                call_order.append("artifacts")
                return real_writer(*args, **kwargs)

            def summarize_after_artifacts(_text, _config):
                call_order.append("summary")
                self.assertTrue(
                    transcript_path.exists(),
                    "摘要開始前，逐字稿必須已經寫入磁碟。",
                )
                return "測試摘要"

            with (
                patch.object(
                    transcribe_pro,
                    "write_transcription_artifacts",
                    side_effect=record_artifact_write,
                ),
                patch.object(
                    transcribe_pro,
                    "summarize_text",
                    side_effect=summarize_after_artifacts,
                ),
            ):
                artifacts = transcribe_pro.process_audio_file(
                    str(audio_path), FakeAudioProcessor(), config
                )

            self.assertLess(
                call_order.index("artifacts"),
                call_order.index("summary"),
            )
            self.assertIn(
                "這是已完成的逐字稿。",
                artifacts["transcript"].read_text(encoding="utf-8"),
            )

    def test_summary_exception_does_not_remove_transcription_artifacts(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            audio_path = root / "meeting.wav"
            audio_path.write_bytes(b"placeholder")
            config = transcribe_pro.AppConfig(output_dir=root / "output")
            result_dir = config.output_dir / audio_path.stem

            def fail_summary(_text, _config):
                expected_artifacts = [
                    result_dir / "meeting_逐字稿.txt",
                    result_dir / "meeting_逐句.json",
                    result_dir / "meeting_字幕.srt",
                    result_dir / "meeting_字幕.vtt",
                ]
                self.assertTrue(
                    all(path.exists() for path in expected_artifacts),
                    "摘要發生例外前，所有逐字稿 artifacts 都必須已落地。",
                )
                raise RuntimeError("summary service unavailable")

            caught_error = None
            with patch.object(
                transcribe_pro, "summarize_text", side_effect=fail_summary
            ):
                try:
                    transcribe_pro.process_audio_file(
                        str(audio_path), FakeAudioProcessor(), config
                    )
                except RuntimeError as error:
                    caught_error = error

            expected_artifacts = [
                result_dir / "meeting_逐字稿.txt",
                result_dir / "meeting_逐句.json",
                result_dir / "meeting_字幕.srt",
                result_dir / "meeting_字幕.vtt",
            ]
            self.assertTrue(all(path.exists() for path in expected_artifacts))
            if caught_error is not None:
                self.assertEqual(str(caught_error), "summary service unavailable")


if __name__ == "__main__":
    unittest.main()
