import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


MODULE_PATH = Path(__file__).with_name("generate_dating_sim_images.py")
SPEC = importlib.util.spec_from_file_location("dating_images", MODULE_PATH)
images = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(images)


def scenario(days=14):
    data = {"days": {}}
    beats = ["비 오는 서점", "야간 산책", "휴대폰 메시지", "회사 회의", "축제 불꽃", "조용한 식사"]
    for day in range(1, days + 1):
        data["days"][str(day)] = {
            "narration": beats[(day - 1) % len(beats)],
            "scenes": {
                loc: {"lines": [f"{beats[(day + index) % len(beats)]} {day} {loc}"], "choices": []}
                for index, loc in enumerate(images.LOCATIONS)
            },
        }
    return data


class DatingImageAgentTests(unittest.TestCase):
    def test_comfy_reference_upload_normalizes_large_image(self):
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Pillow not installed")
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "large.jpg"
            Image.new("RGB", (1600, 900), "white").save(source)
            captured = {}

            class Response:
                def __enter__(self): return self
                def __exit__(self, *args): return False
                def read(self): return b'{"name":"normalized.png"}'

            def fake_urlopen(request, timeout=0):
                captured["body"] = request.data
                return Response()

            with patch.object(images.urllib.request, "urlopen", fake_urlopen):
                self.assertEqual(images._comfy_upload(source), "normalized.png")
            marker = b"Content-Type: image/png\r\n\r\n"
            png = captured["body"].split(marker, 1)[1].split(b"\r\n------jpcomfy", 1)[0]
            with Image.open(images.io.BytesIO(png)) as normalized:
                self.assertEqual(normalized.size, (512, 768))

    def test_comfy_workflow_uses_core_nodes_and_reference_img2img(self):
        text_workflow = images._build_comfy_workflow("a quiet cafe scene", "model.safetensors", 42)
        self.assertEqual(text_workflow["3"]["inputs"]["latent_image"], ["5", 0])
        self.assertEqual(text_workflow["3"]["inputs"]["denoise"], 1.0)
        self.assertEqual(text_workflow["4"]["inputs"]["ckpt_name"], "model.safetensors")
        self.assertEqual(text_workflow["9"]["class_type"], "SaveImage")

        folder_workflow = images._build_comfy_workflow(
            "a quiet cafe scene", "stable-v15", 42, loader="DiffusersLoader"
        )
        self.assertEqual(folder_workflow["4"]["class_type"], "DiffusersLoader")
        self.assertEqual(folder_workflow["4"]["inputs"]["model_path"], "stable-v15")

        edit_workflow = images._build_comfy_workflow(
            "a quiet cafe scene", "model.safetensors", 42, "reference.png"
        )
        self.assertIn("5", edit_workflow)
        self.assertEqual(edit_workflow["10"]["class_type"], "LoadImage")
        self.assertEqual(edit_workflow["11"]["class_type"], "VAEEncode")
        self.assertEqual(edit_workflow["3"]["inputs"]["latent_image"], ["14", 0])
        self.assertLess(edit_workflow["3"]["inputs"]["denoise"], 0.5)
        self.assertEqual(edit_workflow["13"]["class_type"], "KSampler")
        self.assertEqual(edit_workflow["13"]["inputs"]["latent_image"], ["5", 0])
        self.assertEqual(edit_workflow["14"]["class_type"], "LatentBlend")
        # LatentBlend는 samples1(텍스트, 13번)*blend_factor + samples2(레퍼런스,
        # 11번)*(1-blend_factor)라, 레퍼런스 비중 80%를 얻으려면 blend_factor는
        # 0.20이어야 한다(★ 2026-09-23 "레퍼런스로 80%비율로" 요청).
        self.assertEqual(edit_workflow["14"]["inputs"]["blend_factor"], 0.20)

    def test_comfy_workflow_can_use_external_vae(self):
        workflow = images._build_comfy_workflow(
            "a rainy bookshop reunion with a shy smile",
            images.DEFAULT_CIVITAI_CHECKPOINT,
            42,
            "reference.png",
            vae_name=images.DEFAULT_CIVITAI_VAE,
        )
        self.assertEqual(workflow["12"]["class_type"], "VAELoader")
        self.assertEqual(workflow["12"]["inputs"]["vae_name"], images.DEFAULT_CIVITAI_VAE)
        self.assertEqual(workflow["8"]["inputs"]["vae"], ["12", 0])
        self.assertEqual(workflow["11"]["inputs"]["vae"], ["12", 0])
        self.assertIn("rainy bookshop reunion", workflow["6"]["inputs"]["text"])
        self.assertIn("shot on Canon EOS R5, 85mm f/1.4", workflow["6"]["inputs"]["text"])
        self.assertIn("golden hour lighting", workflow["6"]["inputs"]["text"])

    def test_civitai_checkpoint_is_preferred_when_installed(self):
        with patch.object(images, "_comfy_request", side_effect=lambda path: {
            "/models/checkpoints": ["zzz.safetensors", images.DEFAULT_CIVITAI_CHECKPOINT],
        }.get(path, [])):
            self.assertEqual(
                images._comfy_model_spec(),
                ("CheckpointLoaderSimple", images.DEFAULT_CIVITAI_CHECKPOINT),
            )

    def test_plan_is_adaptive_diverse_and_assigns_every_scene(self):
        plan = images.build_plan(scenario(), max_scenes=12)
        self.assertGreater(len(plan["selected"]), 4)
        self.assertLessEqual(len(plan["selected"]), 12)
        self.assertEqual(len(plan["assignments"]), 14 * 3)
        self.assertEqual({item["location"] for item in plan["selected"]}, set(images.LOCATIONS))

    def test_original_epub_scene_images_are_listed_in_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp) / "TEST-001"
            source = work / "images"
            source.mkdir(parents=True)
            for name in ("part1_scene001.jpg", "part1_scene002.jpg", "part1_scene003.jpg"):
                (source / name).write_bytes(name.encode() * 100)
            originals = images._original_scene_images(work)
            self.assertEqual([path.name for path in originals], [
                "part1_scene001.jpg", "part1_scene002.jpg", "part1_scene003.jpg",
            ])

    def test_fixed_reference_selection_skips_faceless_or_undecodable_images(self):
        # ★ 2026-09-23: "얼굴이 한 인물로 고정되면 좋겠어" 요청으로
        # _scene_reference(장면마다 다른 원작 컷 순환)를 없애고
        # _select_fixed_reference(얼굴이 잘 나온 사진 한 장 고정)로 바꿨다.
        # 얼굴 사진 없이는 결정론적으로 재현 가능한 얼굴 검출 테스트를 만들
        # 수 없으므로, 여기서는 얼굴이 없는 이미지에서 크래시 없이 None을
        # 돌려주는 안전한 폴백 경로만 검증한다(실측 검증은 README 기록 참고).
        try:
            import cv2  # noqa: F401
            from PIL import Image
        except ImportError:
            self.skipTest("OpenCV/Pillow not installed")
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp) / "TEST-001"
            source = work / "images"
            source.mkdir(parents=True)
            plain = source / "part1_scene001.jpg"
            Image.new("RGB", (400, 300), (200, 200, 200)).save(plain)
            broken = source / "part1_scene002.jpg"
            broken.write_bytes(b"not a real image")
            originals = images._original_scene_images(work)
            self.assertEqual(images._select_fixed_reference(originals), None)

    def test_comfyui_is_default_and_openai_is_opt_in(self):
        with tempfile.TemporaryDirectory() as tmp, \
             patch.dict(images.os.environ, {}, clear=True), \
             patch.object(images, "_local_generate") as local, \
             patch.object(images, "_openai_generate") as openai:
            result = images._generate("prompt", Path(tmp) / "out.png")
        self.assertEqual(result, "comfyui")
        local.assert_called_once()
        openai.assert_not_called()

    def test_agent_resumes_existing_files_and_writes_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp) / "TEST-001"
            work.mkdir()
            (work / "dating_sim_scenario.json").write_text(json.dumps(scenario(3)), encoding="utf-8")
            calls = []
            def fake_generator(prompt, target, reference=None):
                calls.append(target.name)
                # 테스트 환경에는 Pillow가 없을 수 있으므로 크기 검증을 넘는
                # 가짜 데이터로 재개 시 재호출되지 않는지만 확인한다.
                target.write_bytes(b"fake-png" * 256)
                return "test"
            # translator(영어 통일 + 표정·배경 자동 보완, ★ 2026-09-23)는 실제
            # codex/claude CLI를 호출하므로, 테스트에서는 원문을 그대로
            # 돌려주는 가짜로 바꿔 느려지거나 CLI 부재로 실패하지 않게 한다.
            fake_translator = lambda scene, work_dir: scene["text"]
            first = images.run_agent(work, max_scenes=5, generator=fake_generator, translator=fake_translator)
            self.assertEqual(first["status"], "complete")
            first_call_count = len(calls)
            second = images.run_agent(work, max_scenes=5, generator=fake_generator, translator=fake_translator)
            self.assertEqual(second["status"], "complete")
            self.assertEqual(len(calls), first_call_count)
            self.assertTrue(second["assignments"])


if __name__ == "__main__":
    unittest.main()
