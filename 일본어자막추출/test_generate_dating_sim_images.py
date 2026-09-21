import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


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
        self.assertNotIn("5", edit_workflow)
        self.assertEqual(edit_workflow["3"]["inputs"]["latent_image"], ["11", 0])
        self.assertEqual(edit_workflow["10"]["class_type"], "LoadImage")
        self.assertEqual(edit_workflow["11"]["class_type"], "VAEEncode")
        self.assertLess(edit_workflow["3"]["inputs"]["denoise"], 1.0)

    def test_plan_is_adaptive_diverse_and_assigns_every_scene(self):
        plan = images.build_plan(scenario(), max_scenes=12)
        self.assertGreater(len(plan["selected"]), 4)
        self.assertLessEqual(len(plan["selected"]), 12)
        self.assertEqual(len(plan["assignments"]), 14 * 3)
        self.assertEqual({item["location"] for item in plan["selected"]}, set(images.LOCATIONS))

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
            first = images.run_agent(work, max_scenes=5, generator=fake_generator)
            self.assertEqual(first["status"], "complete")
            first_call_count = len(calls)
            second = images.run_agent(work, max_scenes=5, generator=fake_generator)
            self.assertEqual(second["status"], "complete")
            self.assertEqual(len(calls), first_call_count)
            self.assertTrue(second["assignments"])


if __name__ == "__main__":
    unittest.main()
