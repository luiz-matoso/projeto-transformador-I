import base64
import json
import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from datetime import datetime, timedelta, timezone
from io import BytesIO
from unittest.mock import patch

import numpy as np
from fastapi.testclient import TestClient

from api.config import Settings
from api.main import create_app
from ml.pipeline import apply_profile
from PIL import Image


def image_bytes(size=(24, 16), format="PNG"):
    buffer = BytesIO()
    Image.new("RGB", size, "gray").save(buffer, format=format)
    return buffer.getvalue()


def metadata(date=None):
    return {"profiles": [{"minimum_passage_width": "adequate", "surface_tolerance": "minor_problems",
                          "level_change_tolerance": "minor", "accepts_partial_obstruction": True}],
            "observation": {"source": "test", "observed_at": date or datetime.now(timezone.utc).isoformat()}}


class APITests(unittest.TestCase):
    def setUp(self):
        self.app = create_app(Settings(cors_origins=("https://mobiliza.example",)))
        self.components = (None, None, None, None, "cpu", {})
        self.load = patch("api.main.load_components", return_value=self.components).start()
        self.addCleanup(patch.stopall)
        self.vision = patch("api.routes.transitability.observe_scene", side_effect=self.scene).start()
        self.client = TestClient(self.app)
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)

    def scene(self, image, *, observation, components):
        self.assertIs(components, self.components)
        return {"mask": np.ones((image.height, image.width), dtype=np.uint8),
                "features": {"passage_width": "adequate", "obstruction": "partial", "surface_condition": "regular",
                             "level_change": "none", "path_continuity": "continuous", "obstacle_type": ["pole"]},
                "predictions": {}, "observation": observation, "not_modeled": {}, "inactive_features": ["slope"]}

    def post(self, payload=None, content=None, content_type="image/png"):
        return self.client.post("/transitability", data={"metadata": json.dumps(payload or metadata())},
                                files={"image": ("scene.png", content if content is not None else image_bytes(), content_type)})

    def test_health_and_single_startup(self):
        self.assertEqual(self.client.get("/health").json(), {"status": "ready", "models_loaded": True, "device": "cpu"})
        self.client.get("/health")
        self.assertEqual(self.load.call_count, 1)

    def test_multi_profile_one_inference_and_mask(self):
        payload = metadata()
        payload["profiles"].append({**payload["profiles"][0], "minimum_passage_width": "wide"})
        response = self.post(payload)
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual([item["classification"] for item in body["assessments"]], ["partially_transitable", "non_transitable"])
        self.assertIn("poste", body["assessments"][0]["reasons"][0]["message"])
        with Image.open(BytesIO(base64.b64decode(body["mask"]["data"]))) as mask:
            self.assertEqual(mask.size, (24, 16))
            self.assertEqual(set(np.asarray(mask).ravel()), {255})
        self.assertEqual(self.vision.call_count, 1)

    def test_invalid_temporal_metadata_skips_inference(self):
        for date in ("bad-date", (datetime.now(timezone.utc)-timedelta(days=2)).isoformat(),
                     (datetime.now(timezone.utc)+timedelta(days=1)).isoformat()):
            response = self.post(metadata(date))
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()["assessments"][0]["classification"], "undetermined")
            self.assertIsNone(response.json()["mask"])
        payload = metadata()
        payload["observation"]["observed_at"] = None
        self.assertEqual(self.post(payload).json()["observation"]["code"], "observation_date_missing")
        self.vision.assert_not_called()

    def test_bad_inputs(self):
        self.assertEqual(self.post(content=b"not an image").status_code, 422)
        self.assertEqual(self.post(content_type="image/gif").status_code, 415)
        self.assertEqual(self.post(content_type="image/jpeg").status_code, 415)
        payload = metadata(); payload["profiles"][0]["minimum_passage_width"] = "90cm"
        self.assertEqual(self.post(payload).status_code, 422)
        payload = metadata(); payload["profiles"] *= 9
        self.assertEqual(self.post(payload).status_code, 422)
        self.assertEqual(self.client.post("/transitability").status_code, 422)

    def test_image_limits(self):
        self.app.state.settings = Settings(max_pixels=10)
        self.assertEqual(self.post().status_code, 413)
        self.app.state.settings = Settings(max_dimension=10)
        self.assertEqual(self.post().status_code, 413)
        self.app.state.settings = Settings(max_image_bytes=10)
        self.assertEqual(self.post().status_code, 413)

    def test_busy_and_unavailable(self):
        self.app.state.gate = __import__("asyncio").Semaphore(0)
        self.assertEqual(self.post().status_code, 503)
        self.app.state.gate = __import__("asyncio").Semaphore(1)
        self.app.state.components = None
        self.assertEqual(self.client.get("/health").status_code, 503)
        self.assertEqual(self.post().status_code, 503)

    def test_failure_is_controlled_and_cors_openapi(self):
        self.vision.side_effect = RuntimeError("private model path")
        with self.assertLogs("api.routes.transitability", level="ERROR"):
            response = self.post()
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("private model path", response.text)
        response = self.client.options("/transitability", headers={"Origin": "https://mobiliza.example", "Access-Control-Request-Method": "POST"})
        self.assertEqual(response.headers["access-control-allow-origin"], "https://mobiliza.example")
        schema = self.client.get("/openapi.json").json()
        self.assertIn("TransitabilityInput", schema["components"]["schemas"])

    def test_total_body_limit_and_gate_release(self):
        payload = metadata(); payload["observation"]["source"] = "x" * (9 * 1024 * 1024)
        self.assertEqual(self.post(payload).status_code, 413)
        self.assertEqual(self.post().status_code, 200)

    def test_startup_failure_remains_observable(self):
        self.load.side_effect = FileNotFoundError("missing checkpoint")
        with self.assertLogs("api.main", level="ERROR"), TestClient(create_app()) as client:
            self.assertEqual(client.get("/health").status_code, 503)
            self.assertFalse(client.get("/health").json()["models_loaded"])

    def test_inference_does_not_block_health_and_rejects_overload(self):
        started, release = Event(), Event()
        def slow_scene(*args, **kwargs):
            started.set()
            if not release.wait(5):
                raise RuntimeError("Teste não liberou inferência")
            return self.scene(*args, **kwargs)
        self.vision.side_effect = slow_scene
        with ThreadPoolExecutor(max_workers=1) as executor:
            pending = executor.submit(self.post)
            try:
                self.assertTrue(started.wait(3))
                self.assertEqual(self.client.get("/health").status_code, 200)
                self.assertEqual(self.post().status_code, 503)
            finally:
                release.set()
            self.assertEqual(pending.result(timeout=5).status_code, 200)


@unittest.skipUnless(os.getenv("MOBILIZA_RUN_REAL_API_TEST") == "1", "Integração real opt-in requer checkpoints")
class RealAPIIntegrationTests(unittest.TestCase):
    def test_modal_bundle_cpu_offline(self):
        from pathlib import Path
        from time import perf_counter
        bundle = Path(".modal-models")
        if not bundle.exists():
            self.skipTest("Execute deploy/prepare_models.py antes de validar o pacote")
        settings = Settings(segformer_checkpoint=bundle / "segformer/best_segformer.pt",
                            dino_checkpoint=bundle / "dinov2/best_dinov2_v2.pt", device="cpu")
        image = Path("data/annotation-pilot/images/curb_ramp/gsv-amsterdam-18384-CurbRamp.png")
        started = perf_counter()
        with patch.dict(os.environ, {"HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1"}), \
             patch("transformers.AutoModel.from_pretrained", side_effect=AssertionError("Pesos-base não devem ser carregados")), \
             TestClient(create_app(settings)) as client:
            self.assertEqual(client.get("/health").json()["device"], "cpu")
            with image.open("rb") as handle:
                response = client.post("/transitability", data={"metadata": json.dumps(metadata())},
                                       files={"image": (image.name, handle, "image/png")})
            self.assertEqual(response.status_code, 200, response.text)
            result = response.json()
            self.assertTrue(result["observation"]["is_valid"])
            self.assertIsNotNone(result["mask"])
        output = Path("artifacts/api-integration/modal-cpu-offline.json")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps({"cpu_offline": True, "elapsed_seconds": perf_counter() - started,
                                     "classification": result["assessments"][0]["classification"],
                                     "timestamp_simulated": True}, indent=2), encoding="utf-8")

    def test_real_pipeline_request(self):
        from pathlib import Path
        from hashlib import sha256
        from ml.pipeline import SEGFORMER_CHECKPOINT, DINO_CHECKPOINT
        hashes = {path: sha256(path.read_bytes()).hexdigest() for path in (SEGFORMER_CHECKPOINT, DINO_CHECKPOINT)}
        image = Path("data/annotation-pilot/images/curb_ramp/gsv-amsterdam-18384-CurbRamp.png")
        payload = metadata()
        payload["profiles"].append({**payload["profiles"][0], "minimum_passage_width": "wide"})
        with TestClient(create_app()) as client, image.open("rb") as handle:
            self.assertEqual(client.get("/health").status_code, 200)
            response = client.post("/transitability", data={"metadata": json.dumps(payload)}, files={"image": (image.name, handle, "image/png")})
            self.assertEqual(response.status_code, 200, response.text)
            result = response.json()
            self.assertEqual(len(result["assessments"]), 2)
            self.assertTrue(result["observation"]["is_valid"])
            self.assertTrue(result["mask"]["data"])
            for index, profile in enumerate(payload["profiles"]):
                from ml.mobility_profile import MobilityProfile
                expected = apply_profile({"features": result["features"], "observation": payload["observation"]}, MobilityProfile(**profile))
                self.assertEqual(result["assessments"][index]["classification"], expected["classification"])
            # O horário identifica o cenário de integração, não a captura real da imagem do dataset.
            output = Path("artifacts/api-integration")
            output.mkdir(parents=True, exist_ok=True)
            (output / "response.json").write_text(json.dumps({**result, "mask": {**result["mask"], "data": "<PNG omitted>"}, "timestamp_simulated": True}, indent=2, ensure_ascii=False), encoding="utf-8")
        self.assertEqual(hashes, {path: sha256(path.read_bytes()).hexdigest() for path in hashes})


if __name__ == "__main__":
    unittest.main()
