import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import transcribe_pro


class FakeAutoModel:
    last_kwargs = None

    def __init__(self, **kwargs):
        type(self).last_kwargs = kwargs


class FunASRProcessorTests(unittest.TestCase):
    def test_sensevoice_uses_stable_pipeline_without_campp(self):
        with (
            patch.object(transcribe_pro, "_try_import_funasr", return_value=FakeAutoModel),
            patch.object(transcribe_pro, "detect_device", return_value="cpu"),
            patch.dict(transcribe_pro.os.environ, {}, clear=False),
        ):
            transcribe_pro.FunASRProcessor("iic/SenseVoiceSmall")

        kwargs = FakeAutoModel.last_kwargs
        self.assertEqual(kwargs["model"], "iic/SenseVoiceSmall")
        self.assertNotIn("spk_model", kwargs)
        self.assertTrue(kwargs["disable_update"])

    def test_existing_modelscope_snapshot_is_preferred(self):
        with tempfile.TemporaryDirectory() as cache_root:
            snapshot = (
                Path(cache_root)
                / "models"
                / "iic--SenseVoiceSmall"
                / "snapshots"
                / "master"
            )
            snapshot.mkdir(parents=True)
            (snapshot / "config.yaml").write_text("model: test", encoding="utf-8")

            with patch.dict(
                transcribe_pro.os.environ,
                {"MODELSCOPE_CACHE": cache_root},
                clear=False,
            ):
                resolved = transcribe_pro._prefer_modelscope_cache(
                    "iic/SenseVoiceSmall"
                )

        self.assertEqual(resolved, str(snapshot))


if __name__ == "__main__":
    unittest.main()