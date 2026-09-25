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
    def test_quality_report_rejects_multiple_distinct_faces(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "candidate.png"
            target.write_bytes(b"fake-png" * 256)
            with patch.object(images, "_valid_image", return_value=True), \
                 patch.object(images, "_detect_face_boxes", return_value=[
                     (10, 10, 80, 80), (250, 20, 75, 75),
                 ]):
                report = images.image_quality_report(target)
        self.assertFalse(report["passed"])
        self.assertEqual(report["face_count"], 2)
        self.assertIn("겹침", report["reasons"][0])

    def test_quality_report_accepts_single_or_undetected_face(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "candidate.png"
            target.write_bytes(b"fake-png" * 256)
            with patch.object(images, "_valid_image", return_value=True), \
                 patch.object(images, "_detect_face_boxes", return_value=[(10, 10, 80, 80)]):
                self.assertTrue(images.image_quality_report(target)["passed"])
            with patch.object(images, "_valid_image", return_value=True), \
                 patch.object(images, "_detect_face_boxes", return_value=[]):
                self.assertTrue(images.image_quality_report(target)["passed"])

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
                self.assertEqual(normalized.size, (images.IMAGE_WIDTH, images.IMAGE_HEIGHT))

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
        # 11번)*(1-blend_factor)라, 레퍼런스 비중 65%를 얻으려면 blend_factor는
        # 0.35여야 한다(★ 2026-09-23 "비율 65%로 낮춰줘" 재요청 — 처음엔 80%로
        # 시작했는데 얼굴이 부자연스럽다는 피드백으로 낮춤).
        self.assertEqual(edit_workflow["14"]["inputs"]["blend_factor"], 0.35)

    def test_comfy_workflow_averages_multiple_reference_images_equally(self):
        # ★ 2026-09-23: "얼굴이 나오는 사진은 되도록 많이 참조해서 정확도를
        # 올리게끔" 요청 — 레퍼런스 여러 장을 LatentBlend 사슬로 동일 가중치
        # 평균 내는지 직접 계산으로 검증한다.
        workflow = images._build_comfy_workflow(
            "a quiet cafe scene", "model.safetensors", 42,
            ["ref-a.png", "ref-b.png", "ref-c.png"],
        )
        # 첫 장은 예전 단일 레퍼런스와 같은 노드 ID(10/11)를 그대로 쓴다.
        self.assertEqual(workflow["10"]["inputs"]["image"], "ref-a.png")
        self.assertEqual(workflow["110"]["inputs"]["image"], "ref-b.png")
        self.assertEqual(workflow["120"]["inputs"]["image"], "ref-c.png")
        # 2번째 사진을 더할 때 blend_factor=1/2(두 장을 절반씩), 3번째를 더할
        # 때 blend_factor=2/3(지금까지의 평균 2/3 + 새 사진 1/3) — 풀어보면
        # 세 장이 각각 1/3씩 동일한 비중을 갖는 평균이 된다.
        self.assertEqual(workflow["152"]["inputs"], {
            "samples1": ["11", 0], "samples2": ["111", 0], "blend_factor": 1 / 2,
        })
        self.assertEqual(workflow["153"]["inputs"], {
            "samples1": ["152", 0], "samples2": ["121", 0], "blend_factor": 2 / 3,
        })
        # 최종 블렌드(텍스트 20%/레퍼런스 평균 80%)는 3장 평균 latent(153)를 본다.
        self.assertEqual(workflow["14"]["inputs"]["samples2"], ["153", 0])

        # 한 장뿐이면 예전과 완전히 동일하게 동작한다(체인 블렌드 노드 없음).
        single = images._build_comfy_workflow(
            "a quiet cafe scene", "model.safetensors", 42, ["ref-a.png"],
        )
        self.assertNotIn("152", single)
        self.assertEqual(single["14"]["inputs"]["samples2"], ["11", 0])

    def test_comfy_workflow_uses_ipadapter_faceid_when_requested(self):
        # ★ 2026-09-23: "인물고정법도 있을건데 그거참고해서" 요청 —
        # IP-Adapter FaceID(얼굴 임베딩 기반) 경로는 img2img/LatentBlend를
        # 전혀 쓰지 않고, 순수 txt2img latent에 얼굴 임베딩으로 패치한
        # 모델을 그대로 물린다는 걸 검증한다.
        workflow = images._build_comfy_workflow(
            "a quiet cafe scene", "model.safetensors", 42,
            ["ref-a.png", "ref-b.png"], use_ipadapter_faceid=True,
        )
        self.assertEqual(workflow["20"]["class_type"], "IPAdapterUnifiedLoaderFaceID")
        self.assertEqual(workflow["20"]["inputs"]["preset"], "FACEID PLUS V2")
        self.assertEqual(workflow["21"]["class_type"], "ImageBatch")
        self.assertEqual(workflow["21"]["inputs"], {"image1": ["10", 0], "image2": ["110", 0]})
        self.assertEqual(workflow["22"]["class_type"], "IPAdapterFaceID")
        self.assertEqual(workflow["22"]["inputs"]["model"], ["20", 0])
        self.assertEqual(workflow["22"]["inputs"]["ipadapter"], ["20", 1])
        self.assertEqual(workflow["22"]["inputs"]["image"], ["21", 0])
        self.assertEqual(workflow["22"]["inputs"]["weight"], 0.65)
        # img2img 전용 노드(VAEEncode/LatentBlend)는 전혀 만들어지지 않는다.
        self.assertNotIn("11", workflow)
        self.assertNotIn("14", workflow)
        self.assertEqual(workflow["3"]["inputs"]["model"], ["22", 0])
        self.assertEqual(workflow["3"]["inputs"]["latent_image"], ["5", 0])
        self.assertEqual(workflow["3"]["inputs"]["denoise"], 1.0)

        # 레퍼런스가 한 장뿐이면 ImageBatch 없이 그 한 장을 그대로 물린다.
        single = images._build_comfy_workflow(
            "a quiet cafe scene", "model.safetensors", 42,
            ["ref-a.png"], use_ipadapter_faceid=True,
        )
        self.assertNotIn("21", single)
        self.assertEqual(single["22"]["inputs"]["image"], ["10", 0])

        # use_ipadapter_faceid=False(기본값)면 예전 img2img 경로 그대로 유지.
        fallback = images._build_comfy_workflow(
            "a quiet cafe scene", "model.safetensors", 42, ["ref-a.png"],
        )
        self.assertNotIn("20", fallback)
        self.assertEqual(fallback["3"]["inputs"]["model"], ["4", 0])

    def test_local_generate_detects_when_ipadapter_node_missing(self):
        with patch.object(images, "_comfy_request", side_effect=lambda path, *a, **k: {}):
            self.assertFalse(images._comfy_supports_ipadapter_faceid())
        with patch.object(images, "_comfy_request", side_effect=lambda path, *a, **k: (
            {"IPAdapterUnifiedLoaderFaceID": {}} if "IPAdapterUnifiedLoaderFaceID" in path else {}
        )):
            self.assertTrue(images._comfy_supports_ipadapter_faceid())

    def test_local_generate_drops_reference_instead_of_blending_when_faceid_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            reference = Path(tmp) / "face.jpg"
            reference.write_bytes(b"face")
            target = Path(tmp) / "out.png"
            workflows = []
            waits = 0

            def fake_comfy_request(path, data=None, timeout=20):
                if path == "/system_stats": return {}
                if "IPAdapterUnifiedLoaderFaceID" in path: return {"IPAdapterUnifiedLoaderFaceID": {}}
                if path == "/prompt":
                    workflows.append(data["prompt"])
                    return {"prompt_id": str(len(workflows))}
                return {}

            def fake_wait_image(prompt_id, timeout):
                nonlocal waits
                waits += 1
                if waits == 1:
                    raise RuntimeError("ComfyUI 실행 실패: No face detected.")
                return {"filename": "result.png", "subfolder": "", "type": "output"}

            class FakeResponse:
                def __enter__(self): return self
                def __exit__(self, *args): return False
                def read(self): return b"png" * 500

            with patch.object(images, "_comfy_request", side_effect=fake_comfy_request), \
                 patch.object(images, "_comfy_model_spec", return_value=("CheckpointLoaderSimple", "model.safetensors")), \
                 patch.object(images, "_comfy_vae_name", return_value=""), \
                 patch.object(images, "_comfy_upload", return_value="face.png"), \
                 patch.object(images, "_comfy_wait_image", side_effect=fake_wait_image), \
                 patch.object(images.urllib.request, "urlopen", return_value=FakeResponse()), \
                 patch.object(images, "_valid_image", return_value=True):
                images._local_generate("portrait", target, reference)

        self.assertIn("22", workflows[0])
        self.assertNotIn("22", workflows[1])
        self.assertNotIn("14", workflows[1])
        self.assertEqual(images._LAST_GENERATION_META["generation_settings"]["reference_count"], 0)
        self.assertEqual(images._LAST_GENERATION_META["generation_settings"]["composition_pass"], "txt2img (얼굴 참고 제외)")

    def test_local_generate_retries_with_fewer_references_before_falling_back(self):
        # ★ 2026-09-23: "생성된 이미지 표정이 전부 일편적인데 다양하게" 요청 —
        # 원인은 여러 장을 ImageBatch로 묶었을 때 한 장이라도 얼굴 인식에
        # 실패하면 전체가 img2img(표정까지 레퍼런스에 고정됨)로 떨어지는
        # 것이었다. 레퍼런스를 한 장으로 줄여 IP-Adapter를 한 번 더 시도한
        # 뒤에야 img2img로 넘어가는지 검증한다.
        with tempfile.TemporaryDirectory() as tmp:
            ref_a, ref_b = Path(tmp) / "a.jpg", Path(tmp) / "b.jpg"
            ref_a.write_bytes(b"a")
            ref_b.write_bytes(b"b")
            target = Path(tmp) / "out.png"
            wait_calls = []

            def fake_comfy_request(path, data=None, timeout=20):
                if path == "/system_stats":
                    return {}
                if "IPAdapterUnifiedLoaderFaceID" in path:
                    return {"IPAdapterUnifiedLoaderFaceID": {}}
                if path == "/prompt":
                    return {"prompt_id": f"id-{len(wait_calls)}"}
                return {}

            def fake_wait_image(prompt_id, timeout):
                wait_calls.append(prompt_id)
                if len(wait_calls) == 1:
                    raise RuntimeError("ComfyUI 실행 실패: No face detected.")
                return {"filename": "result.png", "subfolder": "tulpachat", "type": "output"}

            class FakeResponse:
                def __enter__(self): return self
                def __exit__(self, *args): return False
                def read(self): return b"fake-png-bytes" * 100

            with patch.object(images, "_comfy_request", side_effect=fake_comfy_request), \
                 patch.object(images, "_comfy_model_spec", return_value=("CheckpointLoaderSimple", "model.safetensors")), \
                 patch.object(images, "_comfy_vae_name", return_value=""), \
                 patch.object(images, "_comfy_upload", side_effect=["ref-a.png", "ref-b.png"]), \
                 patch.object(images, "_comfy_wait_image", side_effect=fake_wait_image), \
                 patch.object(images.urllib.request, "urlopen", return_value=FakeResponse()), \
                 patch.object(images, "_valid_image", return_value=True):
                images._local_generate("a prompt", target, [ref_a, ref_b])
        self.assertEqual(len(wait_calls), 2)
        settings = images._LAST_GENERATION_META["generation_settings"]
        self.assertIn("IP-Adapter FaceID", settings["composition_pass"])
        self.assertEqual(settings["reference_count"], 1)

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
        # _select_fixed_references(얼굴이 잘 나온 사진을 점수순으로 최대
        # MAX_REFERENCE_IMAGES장 고정)로 바꿨다. 얼굴 사진 없이는 결정론적으로
        # 재현 가능한 얼굴 검출 테스트를 만들 수 없으므로, 여기서는 얼굴이
        # 없는 이미지에서 크래시 없이 빈 리스트를 돌려주는 안전한 폴백
        # 경로만 검증한다(실측 검증은 README 기록 참고).
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
            self.assertEqual(images._select_fixed_references(originals), [])

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
            self.assertEqual(first["quality_status"], "passed")
            self.assertEqual(first["job_progress"]["percent"], 100)
            self.assertEqual(first["job_progress"]["done"], first["job_progress"]["total"])
            first_call_count = len(calls)
            second = images.run_agent(work, max_scenes=5, generator=fake_generator, translator=fake_translator)
            self.assertEqual(second["status"], "complete")
            self.assertEqual(len(calls), first_call_count)
            self.assertTrue(second["assignments"])

    def test_agent_does_not_use_cover_when_no_face_reference_qualifies(self):
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Pillow not installed")
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp) / "TEST-NO-FACE"
            (work / "images").mkdir(parents=True)
            (work / "dating_sim_scenario.json").write_text(json.dumps(scenario(1)), encoding="utf-8")
            Image.new("RGB", (400, 300), "gray").save(work / "cover.jpg")
            Image.new("RGB", (400, 300), "gray").save(work / "images" / "part1_scene001.jpg")
            portrait_references = []

            def fake_generator(prompt, target, reference=None):
                if target.name == "portrait.png":
                    portrait_references.append(reference)
                target.write_bytes(b"fake-png" * 256)
                return "test"

            result = images.run_agent(
                work, max_scenes=1, generator=fake_generator,
                translator=lambda scene, work_dir: scene["text"],
            )
            self.assertEqual(portrait_references, [[]])
            self.assertEqual(result["reference_source"], "text_only_no_qualified_face")
            self.assertIsNone(result["portrait_reference"])

    def test_force_keys_regenerates_only_the_selected_image(self):
        # ★ 2026-09-23: "이미지 재생성 버튼... 전체재생성도 있고 사진눌렀을때
        # 이사진만 재생성하기 버튼있게해줘" 요청 — force_keys에 담긴 키
        # (portrait 또는 특정 장면 키)만 다시 만들고 나머지는 그대로
        # 재사용하는지 검증한다.
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp) / "TEST-002"
            work.mkdir()
            (work / "dating_sim_scenario.json").write_text(json.dumps(scenario(3)), encoding="utf-8")
            calls = []
            def fake_generator(prompt, target, reference=None):
                calls.append(target.name)
                target.write_bytes(b"fake-png" * 256)
                return "test"
            fake_translator = lambda scene, work_dir: scene["text"]
            first = images.run_agent(work, max_scenes=5, generator=fake_generator, translator=fake_translator)
            self.assertEqual(first["status"], "complete")
            scene_key = next(iter(first["scenes"]))
            calls.clear()

            images.run_agent(work, max_scenes=5, generator=fake_generator, translator=fake_translator,
                              force_keys={"portrait"})
            self.assertEqual(calls, ["portrait.png"])
            manifest = json.loads((work / "dating_sim_images" / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["job_progress"], {
                "done": 1, "total": 1, "percent": 100, "current": "생성 완료",
            })
            calls.clear()

            images.run_agent(work, max_scenes=5, generator=fake_generator, translator=fake_translator,
                              force_keys={scene_key})
            self.assertEqual(calls, [images._image_filename(scene_key)])


if __name__ == "__main__":
    unittest.main()
