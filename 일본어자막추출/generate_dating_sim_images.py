#!/usr/bin/env python3
"""작품별 미연시 이미지 에이전트.

시나리오를 읽고 시각적으로 겹치지 않는 장면을 고른 뒤 대표 초상화와 장면
이미지를 생성한다. 작업 상태를 manifest.json에 매 장 저장하므로 중단 뒤에도
이어갈 수 있다. 이 스크립트의 쓰기 범위는 해당 작품의 dating_sim_images 폴더뿐이다.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import math
import os
import re
import shutil
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ai_exec import run_ai_exec  # noqa: E402


VERSION = 1
DEFAULT_MAX_SCENES = 12
IMAGE_DIR_NAME = "dating_sim_images"
DEFAULT_CIVITAI_CHECKPOINT = "majicmixRealistic_v7.safetensors"
DEFAULT_CIVITAI_VAE = "vaeFtMse840000EmaPruned_vaeFtMse840k.safetensors"
MANIFEST_NAME = "manifest.json"
LOCATIONS = ("first", "walk", "quiet")
_OPENAI_DISABLED_REASON = None
_LAST_GENERATION_META = {}
_FACE_CASCADES = {}


def _original_scene_images(work_dir):
    """EPUB 제작 과정에서 추출된 원작 장면 이미지를 읽기 순서로 돌려준다.

    `images/partN_sceneNNN[_pageNN].jpg`는 EPUB에 실제 수록되는 원본 장면이다.
    dating_sim_images 아래의 생성물은 의도적으로 제외한다.
    """
    image_dir = work_dir / "images"
    allowed = {".jpg", ".jpeg", ".png", ".webp"}
    return sorted(
        (path for path in image_dir.glob("**/*") if path.is_file() and path.suffix.lower() in allowed),
        key=lambda path: tuple(
            int(piece) if piece.isdigit() else piece.casefold()
            for piece in re.split(r"(\d+)", path.name)
        ),
    )


# 얼굴 면적이 피부 전체 면적의 이 비율보다 작으면 "얼굴 대비 노출된 몸이
# 넓은" 컷으로 보고 고정 인물 레퍼런스 후보에서 뺀다(아래 _face_reference_metrics
# 참고). 실측: 전신 노출 장면은 0.01~0.06대, 정장·사복 차림 얼굴 위주 컷은
# 0.1~0.3대로 뚜렷하게 갈린다.
_MIN_FACE_TO_SKIN_RATIO = 0.08
# 전체 프레임에서 피부색 픽셀이 이 비율을 넘으면 후보에서 뺀다. 실측(40장
# 무작위 표본 + 직접 육안 확인): 옷을 입은 장면은 대체로 0.05~0.45대,
# 노출이 심한 장면은 대체로 0.6대 이상이었다 — 사이(0.45~0.6)는 애매해서
# 안전하게 보수적인 값(0.4)을 썼다. 완벽한 판별은 아니라서(얼굴만 크게
# 잡힌 노출 장면은 통과할 수 있음) 얼굴/피부 비율과 같이 써서 서로 보완한다.
_MAX_FULL_FRAME_SKIN_RATIO = 0.4


def _face_reference_metrics(path):
    """OpenCV Haar cascade(정면+측면)로 가장 큰 얼굴의 넓이를, YCrCb 피부색
    임계값(학술적으로 흔히 쓰이는 간단한 피부색 검출법)으로 전체 피부 픽셀
    수를 잰다. 반환값은 (얼굴 넓이, 얼굴/피부 비율, 프레임 전체 대비 피부
    비율) — AI API를 전혀 안 쓰고 완전히 로컬에서 처리하므로 토큰이 들지
    않는다.

    ★ 2026-09-23: "인물 나온 사진만 추출하는것도 토큰안쓰고 가능할까" 요청으로
    얼굴 검출부터 만들었는데, 실제로 이 원작(성인 영상 스크린샷) 중 "얼굴이
    가장 크게 잡힌 컷"을 그냥 골랐더니 노출이 심한 장면이 뽑히는 걸 실측으로
    확인했다(심지어 얼굴/피부 비율만으로도 못 걸러지는 클로즈업 노출 장면이
    있었다) — 얼굴 크기 하나만 보지 않고, 얼굴/전체피부 비율과 프레임 전체
    피부 비율 두 신호를 같이 써서 노출이 심한 컷을 걸러낸다. 참고: 이건
    완벽한 NSFW 판별기가 아니라 색상·크기 기반 근사치라 오탐/누락이 있을 수
    있다 — 결과 파일(manifest.json의 portrait_reference)은 사용 전에 한 번
    눈으로 확인하는 걸 권장."""
    try:
        import cv2
    except ImportError:
        return 0, 0.0, 1.0
    image = cv2.imread(str(path))
    if image is None:
        return 0, 0.0, 1.0
    height, width = image.shape[:2]
    ycrcb = cv2.cvtColor(image, cv2.COLOR_BGR2YCrCb)
    skin_pixels = float(cv2.inRange(ycrcb, (0, 133, 77), (255, 173, 127)).sum()) / 255.0
    full_frame_ratio = skin_pixels / (height * width) if height * width > 0 else 1.0
    gray = cv2.equalizeHist(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY))
    best_face = 0
    for cascade_name in ("haarcascade_frontalface_alt2.xml", "haarcascade_profileface.xml"):
        cascade = _FACE_CASCADES.get(cascade_name)
        if cascade is None:
            cascade = cv2.CascadeClassifier(cv2.data.haarcascades + cascade_name)
            _FACE_CASCADES[cascade_name] = cascade
        for (_, _, w, h) in cascade.detectMultiScale(gray, scaleFactor=1.05, minNeighbors=4, minSize=(50, 50)):
            best_face = max(best_face, w * h)
    if best_face == 0:
        return 0, 0.0, full_frame_ratio
    face_to_skin_ratio = (best_face / skin_pixels) if skin_pixels > 0 else 0.0
    return best_face, face_to_skin_ratio, full_frame_ratio


def _select_fixed_reference(originals):
    """원작 컷 중 얼굴이 크고 뚜렷하면서 노출이 심하지 않은(두 가지 피부 비율
    신호로 판단) 한 장을 골라, 모든 장면이 공유할 "고정 인물" 레퍼런스로
    삼는다.

    ★ 2026-09-23: "얼굴이 한 인물로 고정되면 좋겠어" 요청 — 예전 _scene_reference()는
    장면마다 원작의 다른 컷을 순환시켜 참조로 썼는데, 그게 바로 장면마다 얼굴이
    조금씩 달라 보이던 원인이었다(매번 다른 사진을 참조하니 당연히 다른 얼굴이
    섞여 들어감). 이제 처음부터 얼굴이 잘 나온 사진 딱 하나만 골라 portrait와
    모든 장면이 동일하게 참조하게 한다. 적당한 후보가 없으면(전부 노출 위주인
    작품 등) None을 돌려주고 호출부가 예전 기본값(첫 원작 컷)으로 대체한다."""
    best_path, best_score = None, 0
    for path in originals:
        face_area, face_ratio, full_frame_ratio = _face_reference_metrics(path)
        if face_area <= 0 or face_ratio < _MIN_FACE_TO_SKIN_RATIO:
            continue
        if full_frame_ratio > _MAX_FULL_FRAME_SKIN_RATIO:
            continue
        score = face_area * face_ratio
        if score > best_score:
            best_path, best_score = path, score
    return best_path


def _copy_reference(source, output, key):
    if not source:
        return None
    suffix = source.suffix.lower() if source.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"} else ".jpg"
    filename = "reference-" + hashlib.sha256(key.encode()).hexdigest()[:12] + suffix
    target = output / filename
    if not target.is_file() or target.stat().st_size != source.stat().st_size:
        shutil.copy2(source, target)
    return filename


def _clean(text, limit=700):
    text = re.sub(r"\[[^|\]]+\|([^\]]+)\]", r"\1", str(text or ""))
    text = re.sub(r"\s+", " ", text).strip()
    # 원작의 성인 대사를 이미지 서비스로 그대로 보내지 않는다. 시각적 맥락만 쓴다.
    text = re.sub(r"(?i)(sex|nude|explicit|성관계|나체|강간|임신|사정)", "private conversation", text)
    return text[:limit]


def _ascii_only(text):
    """이미지 프롬프트에 섞여 들어가는 한글·일본어 문자를 지운다. ComfyUI 쪽
    SD1.5 계열 체크포인트의 CLIP 텍스트 인코더는 영어 위주로 학습돼 있어
    비영어 토큰은 뜻있는 신호가 아니라 노이즈로만 작용한다(★ 2026-09-23
    "프롬프트 영어랑 일본어랑 한글섞여있던데 영어로 통일해줘" 요청)."""
    text = re.sub(r"[^\x00-\x7f]+", " ", str(text or ""))
    return re.sub(r"\s+", " ", text).strip()


def _scene_signature(day, location, text):
    buckets = []
    groups = {
        "rain": ("雨", "비", "우산"), "night": ("夜", "밤", "달", "月"),
        "message": ("메시지", "電話", "휴대폰", "スマホ"),
        "work": ("회사", "仕事", "office", "회의"),
        "travel": ("여행", "電車", "역", "출장"),
        "festival": ("祭", "축제", "불꽃"), "meal": ("料理", "식사", "카페", "茶"),
        "conflict": ("갈등", "다툼", "오해", "謝"), "warm": ("웃", "미소", "嬉"),
    }
    for name, words in groups.items():
        if any(word.casefold() in text.casefold() for word in words):
            buckets.append(name)
    return (location, day // 3, tuple(buckets[:3]))


def build_plan(scenario, max_scenes=DEFAULT_MAX_SCENES):
    candidates = []
    for day_text, day_data in sorted(scenario.get("days", {}).items(), key=lambda item: int(item[0])):
        day = int(day_text)
        narration = _clean(day_data.get("narration"))
        for location, scene in (day_data.get("scenes") or {}).items():
            lines = " ".join(_clean(line, 240) for line in (scene.get("lines") or [])[:3])
            text = _clean(f"{narration} {lines}")
            key = f"{day}:{location}"
            candidates.append({"key": key, "day": day, "location": location,
                               "text": text, "signature": _scene_signature(day, location, text)})
    if not candidates:
        return {"selected": [], "assignments": {}}
    desired = min(max_scenes, max(4, math.ceil(math.sqrt(len(candidates))) + 2), len(candidates))
    selected, signatures = [], set()
    # 첫 만남과 각 장소를 먼저 확보한다.
    for candidate in candidates:
        if candidate["day"] == 1 or not any(x["location"] == candidate["location"] for x in selected):
            selected.append(candidate)
            signatures.add(candidate["signature"])
        if len(selected) >= desired:
            break
    # 시간대·사건·감정의 새로움과 기존 선택일에서의 거리를 함께 보아 작품
    # 초반에만 몰리지 않게 한다.
    remaining = [c for c in candidates if c not in selected]
    while remaining and len(selected) < desired:
        def diversity_score(candidate):
            day_distance = min(abs(candidate["day"] - chosen["day"]) for chosen in selected)
            new_signature = candidate["signature"] not in signatures
            same_location_distance = min(
                (abs(candidate["day"] - chosen["day"]) for chosen in selected
                 if chosen["location"] == candidate["location"]), default=99)
            return (int(new_signature), day_distance, same_location_distance, candidate["day"])
        candidate = max(remaining, key=diversity_score)
        selected.append(candidate)
        signatures.add(candidate["signature"])
        remaining.remove(candidate)
    selected.sort(key=lambda c: (c["day"], c["location"]))
    assignments = {}
    for candidate in candidates:
        closest = min(selected, key=lambda chosen: (
            chosen["location"] != candidate["location"],
            abs(chosen["day"] - candidate["day"]),
        ))
        assignments[candidate["key"]] = closest["key"]
    return {"selected": selected, "assignments": assignments}


def _image_filename(scene_key):
    return "scene-" + hashlib.sha256(scene_key.encode()).hexdigest()[:12] + ".png"


def _prompt(title, scene=None):
    common = (
        "Photorealistic Japanese romance visual novel still, adult Japanese woman age 25 or older, "
        "natural facial anatomy, cinematic available light, coherent recurring character identity, "
        "tasteful contemporary clothing, non-explicit, no text, no watermark. "
        f"Source work identifier: {_ascii_only(_clean(title, 100))}. "
    )
    if scene is None:
        return common + (
            "Consistent waist-up character reference portrait, neutral background, approachable expression. "
            "If a reference cover is supplied, preserve only the adult woman's recognizable face, hair and general styling; "
            "replace the source setting and clothing with a tasteful non-explicit visual-novel portrait."
        )
    return common + (
        f"Story day {scene['day']}, setting category {scene['location']}. "
        f"Visualize this specific narrative beat rather than a generic pose: {scene['text']}. "
        "Vary location, time of day, camera distance, posture, expression and activity to match the beat."
    )


def _visual_prompt_from_scene_text(scene, work_dir):
    """scene['text'](한국어·일본어가 섞인 대사·나레이션)를 영어 시각 묘사
    한 줄로 바꾼다. 대사에 표정·배경 묘사가 없으면 스토리 흐름에 맞는
    표정·배경을 직접 골라 채운다.

    ★ 2026-09-23: "대사에 배경이나 얼굴표정이 어떻다든가 하는게 없으면
    알아서 스토리에맞춰서 표정이랑 배경 적절한거로 만들게끔" 요청 — 확산
    모델(ComfyUI/SD)은 "없으면 알아서 채워라" 같은 조건부 지시를 못 따르므로,
    이 스크립트가 먼저 문장으로 결정해서 넘겨야 한다. 이 저장소 다른 곳(
    generate_summary.py 등)과 같은 ai_exec.run_ai_exec()로 Codex/Claude
    비대화형 호출을 재사용한다 — 실패하면 예전처럼 원문을 그대로 쓴다(폴백)."""
    prompt = (
        "You are writing ONE English sentence for an AI image generator, describing a still "
        "from a Japanese romance visual novel scene.\n\n"
        f"Scene narrative (Korean/Japanese, story day {scene['day']}, "
        f"setting category {scene['location']}):\n{scene['text']}\n\n"
        "Describe: the location/background, the woman's posture, and especially her facial "
        "expression. If the narrative does not explicitly state a facial expression or "
        "background, infer one specific and fitting choice from the emotional beat of the "
        "story — never default to a blank/neutral placeholder. "
        "Output ONLY the sentence (max 40 words), no quotes, no preamble, no Japanese or "
        "Korean characters."
    )
    try:
        stdout, _engine = run_ai_exec(prompt, str(work_dir), timeout=90)
    except Exception:
        return _clean(scene["text"], 180)
    line = _ascii_only(stdout)[:220]
    return line or _clean(scene["text"], 180)


def _openai_generate(prompt, target, reference=None):
    key = os.environ.get("OPENAI_API_KEY", "")
    if not key:
        raise RuntimeError("OPENAI_API_KEY가 설정되지 않았습니다")
    model = os.environ.get("CHATAPP_IMAGE_MODEL", "gpt-image-2")
    headers = {"Authorization": f"Bearer {key}"}
    if reference and reference.is_file():
        boundary = "----jpdating" + hashlib.sha1(str(time.time()).encode()).hexdigest()
        fields = {"model": model, "prompt": prompt, "size": "1024x1024", "quality": "medium"}
        chunks = []
        for name, value in fields.items():
            chunks.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n".encode())
        chunks.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"image\"; filename=\"portrait.png\"\r\nContent-Type: image/png\r\n\r\n".encode())
        chunks.extend((reference.read_bytes(), f"\r\n--{boundary}--\r\n".encode()))
        data = b"".join(chunks)
        headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
        url = "https://api.openai.com/v1/images/edits"
    else:
        headers["Content-Type"] = "application/json"
        data = json.dumps({"model": model, "prompt": prompt, "size": "1024x1024", "quality": "medium"}).encode()
        url = "https://api.openai.com/v1/images/generations"
    request = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=240) as response:
            payload = json.loads(response.read())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        try:
            message = json.loads(body).get("error", {}).get("message")
        except ValueError:
            message = None
        raise RuntimeError(message or f"OpenAI Images HTTP {exc.code}") from exc
    target.write_bytes(base64.b64decode(payload["data"][0]["b64_json"]))


def _comfy_base_url():
    return os.environ.get("JP_COMFYUI_URL", "http://127.0.0.1:8188").rstrip("/")


def _comfy_request(path, data=None, timeout=20):
    headers = {"Content-Type": "application/json"} if data is not None else {}
    request = urllib.request.Request(
        _comfy_base_url() + path,
        data=json.dumps(data).encode("utf-8") if data is not None else None,
        headers=headers,
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read()
    return json.loads(body) if body else {}


def _comfy_model_spec():
    configured = os.environ.get("JP_COMFYUI_CHECKPOINT", "").strip()
    if configured:
        return "CheckpointLoaderSimple", configured
    try:
        models = _comfy_request("/models/checkpoints")
    except Exception:
        models = []
    if isinstance(models, list) and models:
        # 서버에 실제로 있는 모델을 골라 하드코딩된 파일명으로 인한
        # prompt validation 실패를 피한다.
        if DEFAULT_CIVITAI_CHECKPOINT in models:
            return "CheckpointLoaderSimple", DEFAULT_CIVITAI_CHECKPOINT
        return "CheckpointLoaderSimple", sorted(str(model) for model in models)[0]
    configured_diffusers = os.environ.get("JP_COMFYUI_DIFFUSERS_MODEL", "").strip()
    try:
        diffusers_models = _comfy_request("/models/diffusers")
    except Exception:
        diffusers_models = []
    if not diffusers_models:
        try:
            node_info = _comfy_request("/object_info/DiffusersLoader")
            model_input = node_info["DiffusersLoader"]["input"]["required"]["model_path"]
            diffusers_models = model_input[0] if model_input else []
        except (KeyError, IndexError, TypeError, urllib.error.URLError):
            diffusers_models = []
    if configured_diffusers:
        return "DiffusersLoader", configured_diffusers
    if isinstance(diffusers_models, list) and diffusers_models:
        return "DiffusersLoader", sorted(str(model) for model in diffusers_models)[0]
    raise RuntimeError(
        "ComfyUI 로컬 모델을 찾지 못했습니다. JP_COMFYUI_CHECKPOINT 또는 "
        "JP_COMFYUI_DIFFUSERS_MODEL을 설정하거나 ComfyUI models 폴더에 모델을 넣으세요"
    )


def _comfy_vae_name():
    configured = os.environ.get("JP_COMFYUI_VAE", "").strip()
    try:
        models = _comfy_request("/models/vae")
    except Exception:
        models = []
    if configured:
        if isinstance(models, list) and models and configured not in models:
            raise RuntimeError(f"설정한 ComfyUI VAE를 찾을 수 없습니다: {configured}")
        return configured
    if isinstance(models, list) and DEFAULT_CIVITAI_VAE in models:
        return DEFAULT_CIVITAI_VAE
    return ""


def _build_comfy_workflow(
    prompt, model_name, seed, reference_name=None,
    loader="CheckpointLoaderSimple", vae_name="",
):
    # 추가 커스텀 노드 없이 새 ComfyUI에서도 동작하는 API 형식이다.
    # 레퍼런스가 있으면 VAE img2img로 구도·인물성을 유지한다.
    camera_directions = (
        "wide environmental composition, full body in motion, strong location context",
        "medium candid shot, eye-level three-quarter view, natural hand activity",
        "over-the-shoulder composition, layered foreground and background depth",
        "side-profile composition, off-center subject, visible surrounding activity",
        "high-angle seated composition, expressive posture, environmental storytelling",
        "low-angle dynamic composition, walking action, dramatic leading lines",
    )
    camera_direction = camera_directions[int.from_bytes(hashlib.sha256(prompt.encode()).digest()[:2], "big") % len(camera_directions)]
    local_prompt = (
        "photorealistic adult Japanese woman age 25, fully clothed, tasteful romance scene, "
        "natural face and hands, detailed skin, sharp focus, no text, "
        "shot on Canon EOS R5, 85mm f/1.4, golden hour lighting, "
        + camera_direction + ", "
        + _clean(prompt.split("Visualize this specific narrative beat rather than a generic pose:")[-1], 180)
    )
    workflow = {
        "3": {"class_type": "KSampler", "inputs": {
            "seed": seed, "steps": 25, "cfg": 7.0, "sampler_name": "dpmpp_2m",
            "scheduler": "karras", "denoise": 0.48 if reference_name else 1.0,
            "model": ["4", 0], "positive": ["6", 0], "negative": ["7", 0],
            "latent_image": ["14", 0] if reference_name else ["5", 0],
        }},
        "4": {"class_type": loader, "inputs": {
            "ckpt_name" if loader == "CheckpointLoaderSimple" else "model_path": model_name
        }},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"text": local_prompt, "clip": ["4", 1]}},
        "7": {"class_type": "CLIPTextEncode", "inputs": {
            "text": "nsfw, nude, child, low quality, blurry, distorted, deformed, bad hands, text, watermark",
            "clip": ["4", 1],
        }},
        "8": {"class_type": "VAEDecode", "inputs": {"samples": ["3", 0], "vae": ["12", 0] if vae_name else ["4", 2]}},
        "9": {"class_type": "SaveImage", "inputs": {"filename_prefix": "tulpachat/dating", "images": ["8", 0]}},
    }
    if vae_name:
        workflow["12"] = {"class_type": "VAELoader", "inputs": {"vae_name": vae_name}}
    if reference_name:
        workflow["10"] = {"class_type": "LoadImage", "inputs": {"image": reference_name}}
        workflow["11"] = {"class_type": "VAEEncode", "inputs": {
            "pixels": ["10", 0], "vae": ["12", 0] if vae_name else ["4", 2]
        }}
        # 먼저 텍스트만으로 장면의 구도 latent를 만든 뒤, 고정 인물 레퍼런스의
        # latent를 80% 섞고 최종 img2img 패스를 수행한다. ComfyUI LatentBlend는
        # samples1*blend_factor + samples2*(1-blend_factor)이고 samples1=텍스트
        # (13번), samples2=레퍼런스(11번)라 레퍼런스 비중 80%를 얻으려면
        # blend_factor를 0.20으로 낮춰야 한다(전에는 0.78 = 레퍼런스 22%였음).
        # ★ 2026-09-23: "레퍼런스로 80%비율로 해서 이미지 뽑은다음 고정 인물로
        # 정한뒤에" 요청 — 얼굴을 강하게 고정하는 대신 자세·배경은 프롬프트가
        # 담당(camera_direction 회전 + 장면별 영어 묘사)한다.
        workflow["5"] = {"class_type": "EmptyLatentImage", "inputs": {
            "width": 512, "height": 768, "batch_size": 1
        }}
        workflow["13"] = {"class_type": "KSampler", "inputs": {
            "seed": seed + 1, "steps": 12, "cfg": 7.0, "sampler_name": "dpmpp_2m",
            "scheduler": "karras", "denoise": 1.0, "model": ["4", 0],
            "positive": ["6", 0], "negative": ["7", 0], "latent_image": ["5", 0],
        }}
        workflow["14"] = {"class_type": "LatentBlend", "inputs": {
            "samples1": ["13", 0], "samples2": ["11", 0], "blend_factor": 0.20,
        }}
    else:
        workflow["5"] = {"class_type": "EmptyLatentImage", "inputs": {"width": 512, "height": 768, "batch_size": 1}}
    return workflow


def _comfy_upload(reference):
    from PIL import Image, ImageOps

    boundary = "----jpcomfy" + hashlib.sha1(str(time.time_ns()).encode()).hexdigest()
    source = reference.read_bytes()
    filename = "dating-reference-" + hashlib.sha1(source).hexdigest()[:12] + ".png"
    with Image.open(io.BytesIO(source)) as image:
        normalized = ImageOps.fit(image.convert("RGB"), (512, 768), Image.Resampling.LANCZOS)
        payload = io.BytesIO()
        normalized.save(payload, format="PNG", optimize=True)
        image_bytes = payload.getvalue()
    body = b"".join((
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"image\"; filename=\"{filename}\"\r\n"
        "Content-Type: image/png\r\n\r\n".encode(),
        image_bytes,
        f"\r\n--{boundary}\r\nContent-Disposition: form-data; name=\"overwrite\"\r\n\r\ntrue\r\n"
        f"--{boundary}--\r\n".encode(),
    ))
    request = urllib.request.Request(
        _comfy_base_url() + "/upload/image", data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"}, method="POST",
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        payload = json.loads(response.read())
    return payload.get("name") or filename


def _comfy_wait_image(prompt_id, timeout):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        history = _comfy_request(f"/history/{urllib.parse.quote(prompt_id)}", timeout=15)
        record = history.get(prompt_id, {})
        for output in record.get("outputs", {}).values():
            images = output.get("images") or []
            if images:
                return images[0]
        status = record.get("status", {})
        if status.get("status_str") == "error":
            messages = status.get("messages") or []
            raise RuntimeError(f"ComfyUI 실행 실패: {messages[-1] if messages else status}")
        time.sleep(1)
    raise RuntimeError(f"ComfyUI 생성이 {timeout}초 안에 완료되지 않았습니다")


def _local_generate(prompt, target, reference=None):
    global _LAST_GENERATION_META
    try:
        _comfy_request("/system_stats", timeout=5)
    except Exception as exc:
        raise RuntimeError(f"ComfyUI 서버({_comfy_base_url()})에 연결할 수 없습니다: {exc}") from exc
    loader, model_name = _comfy_model_spec()
    vae_name = _comfy_vae_name() if loader == "CheckpointLoaderSimple" else ""
    reference_name = _comfy_upload(reference) if reference and reference.is_file() else None
    base_seed = int.from_bytes(hashlib.sha256(prompt.encode()).digest()[:8], "big") & ((1 << 63) - 1)
    timeout = int(os.environ.get("JP_COMFYUI_TIMEOUT", "600"))
    for attempt in range(4):
        seed = base_seed + attempt * 104729
        workflow = _build_comfy_workflow(
            prompt, model_name, seed, reference_name, loader=loader, vae_name=vae_name
        )
        queued = _comfy_request("/prompt", {"prompt": workflow}, timeout=30)
        if queued.get("node_errors"):
            raise RuntimeError(f"ComfyUI 워크플로 검증 실패: {queued['node_errors']}")
        prompt_id = queued.get("prompt_id")
        if not prompt_id:
            raise RuntimeError(f"ComfyUI가 prompt_id를 반환하지 않았습니다: {queued}")
        image = _comfy_wait_image(prompt_id, timeout)
        query = urllib.parse.urlencode({
            "filename": image["filename"], "subfolder": image.get("subfolder", ""), "type": image.get("type", "output")
        })
        with urllib.request.urlopen(_comfy_base_url() + "/view?" + query, timeout=60) as response:
            target.write_bytes(response.read())
        if _valid_image(target):
            sampler = workflow["3"]["inputs"]
            _LAST_GENERATION_META = {
                "effective_prompt": workflow["6"]["inputs"]["text"],
                "generation_settings": {
                    "model": model_name, "loader": loader, "vae": vae_name or "checkpoint embedded",
                    "width": 512, "height": 768,
                    "steps": sampler["steps"], "cfg": sampler["cfg"],
                    "sampler": sampler["sampler_name"], "scheduler": sampler["scheduler"],
                    "denoise": sampler["denoise"], "base_seed": base_seed,
                    "used_seed": seed, "attempt": attempt + 1,
                    "composition_pass": "txt2img 12 steps + 20% text/80% reference latent + img2img",
                },
            }
            return
    raise RuntimeError("ComfyUI가 검은 또는 손상된 이미지를 반복 반환했습니다")


def _valid_image(path):
    if not path.is_file() or path.stat().st_size < 1024:
        return False
    try:
        from PIL import Image, ImageStat
        with Image.open(path) as image:
            stats = ImageStat.Stat(image.convert("RGB").resize((64, 64)))
        return sum(stats.mean) / 3 > 4 and sum(stats.stddev) / 3 > 2
    except (OSError, ImportError):
        return True


def _generate(prompt, target, reference=None):
    global _OPENAI_DISABLED_REASON
    provider = os.environ.get("JP_DATING_IMAGE_PROVIDER", "comfyui").strip().lower()
    if provider != "openai":
        _local_generate(prompt, target, reference)
        return "comfyui"
    try:
        if _OPENAI_DISABLED_REASON:
            raise RuntimeError(_OPENAI_DISABLED_REASON)
        _openai_generate(prompt, target, reference)
        return "openai"
    except Exception as openai_error:
        if "no credits remaining" in str(openai_error).lower() or "quota" in str(openai_error).lower():
            _OPENAI_DISABLED_REASON = str(openai_error)
        print(f"⚠️ OpenAI 이미지 실패, 로컬 ComfyUI로 전환: {openai_error}", flush=True)
        try:
            _local_generate(prompt, target, reference)
            return "comfyui"
        except Exception as local_error:
            raise RuntimeError(f"OpenAI 실패({openai_error}) / ComfyUI 실패({local_error})") from local_error


def run_agent(work_dir, max_scenes=DEFAULT_MAX_SCENES, force=False, generator=_generate,
              translator=_visual_prompt_from_scene_text):
    scenario_path = work_dir / "dating_sim_scenario.json"
    if not scenario_path.is_file():
        raise RuntimeError("dating_sim_scenario.json이 없어 이미지 장면을 고를 수 없습니다")
    scenario = json.loads(scenario_path.read_text(encoding="utf-8"))
    plan = build_plan(scenario, max_scenes=max_scenes)
    output = work_dir / IMAGE_DIR_NAME
    output.mkdir(parents=True, exist_ok=True)
    manifest_path = output / MANIFEST_NAME
    manifest = {}
    if manifest_path.is_file() and not force:
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            manifest = {}
    manifest.update({"version": VERSION, "status": "running", "title": work_dir.name,
                     "portrait": "portrait.png", "selected_count": len(plan["selected"]),
                     "scene_limit": max_scenes, "assignments": {}, "scenes": manifest.get("scenes", {}),
                     "errors": []})
    portrait = output / "portrait.png"
    originals = _original_scene_images(work_dir)
    # ★ 2026-09-23: "인물 얼굴이나온사진만 추출... 고정 인물로 정한뒤에" 요청 —
    # 예전엔 장면마다 원작의 다른 컷을 순환 참조해서 얼굴이 흔들렸다. 이제
    # 얼굴이 가장 잘 나온 사진 한 장만 OpenCV로 골라(토큰 없음) portrait를
    # 만들고, 아래 장면 루프도 전부 그 portrait 하나만 공유 참조한다.
    face_reference = _select_fixed_reference(originals)
    cover_reference = face_reference or (originals[0] if originals else next((
        path for name in ("cover.jpg", "cover.png", "cover.webp")
        if (path := work_dir / name).is_file()
    ), None))
    portrait_reference_file = _copy_reference(cover_reference, output, "portrait")
    manifest["portrait_prompt"] = _prompt(work_dir.name)
    manifest["portrait_reference"] = portrait_reference_file
    manifest["reference_source"] = (
        "face_detected_fixed" if face_reference else ("original_epub_scene" if originals else "cover_fallback")
    )
    if force or not _valid_image(portrait):
        manifest["portrait_provider"] = generator(manifest["portrait_prompt"], portrait, cover_reference)
        if manifest["portrait_provider"] == "comfyui":
            manifest["portrait_effective_prompt"] = _LAST_GENERATION_META.get("effective_prompt", "")
            manifest["portrait_generation_settings"] = _LAST_GENERATION_META.get("generation_settings", {})
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    # 이후 모든 장면은 portrait.png(없으면 위에서 고른 얼굴 사진)를 동일하게
    # 참조한다 — 장면마다 다른 원작 컷을 쓰지 않는다.
    fixed_reference_path = portrait if _valid_image(portrait) else cover_reference
    fixed_reference_file = "portrait.png" if _valid_image(portrait) else portrait_reference_file
    for scene in plan["selected"]:
        filename = _image_filename(scene["key"])
        target = output / filename
        try:
            if force or not _valid_image(target):
                # 영어 통일 + 표정·배경 자동 보완(★ 2026-09-23 요청)은 실제로
                # 새로 생성할 때만 호출한다 — 이미 만든 장면을 재실행할 때마다
                # 다시 부르지 않는다.
                visual_text = translator(scene, work_dir)
                scene_prompt = _prompt(work_dir.name, {**scene, "text": visual_text})
                provider = generator(scene_prompt, target, fixed_reference_path)
            else:
                existing = manifest.get("scenes", {}).get(scene["key"], {})
                provider = existing.get("provider", "existing")
                scene_prompt = existing.get("prompt") or _prompt(work_dir.name, scene)
            manifest["scenes"][scene["key"]] = {"file": filename, "provider": provider,
                                                     "day": scene["day"], "location": scene["location"],
                                                     "prompt": scene_prompt,
                                                     "reference_file": fixed_reference_file,
                                                     "reference_source": "portrait.png (fixed character)"}
            if provider == "comfyui" and _LAST_GENERATION_META:
                manifest["scenes"][scene["key"]].update(_LAST_GENERATION_META)
        except Exception as exc:
            manifest["errors"].append({"scene": scene["key"], "error": str(exc)[:500]})
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    for scene_key, selected_key in plan["assignments"].items():
        record = manifest["scenes"].get(selected_key)
        if record and (output / record["file"]).is_file():
            manifest["assignments"][scene_key] = record["file"]
    manifest["status"] = "complete" if not manifest["errors"] else "partial"
    manifest["updated_at"] = int(time.time())
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("work_dir")
    parser.add_argument("--max-scenes", type=int, default=int(os.environ.get("JP_DATING_IMAGE_MAX_SCENES", DEFAULT_MAX_SCENES)))
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    manifest = run_agent(Path(args.work_dir).resolve(), max(4, min(args.max_scenes, 30)), args.force)
    print(f"🖼️ 작품 이미지 에이전트: {manifest['status']} · 장면 {len(manifest['scenes'])}/{manifest['selected_count']}장")
    return 0 if manifest["status"] == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
