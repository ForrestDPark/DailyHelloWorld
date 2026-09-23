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
# ★ 2026-09-23: "가로로길게 생성하게끔 조정해줘" 요청 — 세로로 긴 512×768
# 인물사진이 미연시 화면의 가로로 긴 박스에 눌려 들어가면서 머리·가슴이
# 잘렸다. 생성 자체를 화면 박스와 같은 3:2 가로 비율로 바꾼다.
IMAGE_WIDTH = 768
IMAGE_HEIGHT = 512
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
def _face_reference_metrics(path):
    """OpenCV Haar cascade(정면+측면)로 가장 큰 얼굴의 넓이를, YCrCb 피부색
    임계값(학술적으로 흔히 쓰이는 간단한 피부색 검출법)으로 전체 피부 픽셀
    수를 잰다. 반환값은 (얼굴 넓이, 얼굴/피부 비율) — 후자는 노출 여부
    판단이 아니라 "얼굴이 화면을 얼마나 크게 차지하는 구도인지"를 보는
    순수 품질 신호로만 쓴다(높을수록 얼굴 위주 구도). AI API를 전혀 안 쓰고
    완전히 로컬에서 처리하므로 토큰이 들지 않는다.

    ★ 2026-09-23: 원래는 노출이 심한 장면을 거르는 안전장치(얼굴/피부 비율
    + 프레임 전체 피부 비율 임계값)도 있었지만, "노출장면있는사진을 굳이
    거를필요없어 어차피 얼굴만 따오는거니까 안전장치 제거해도될거같아"
    요청으로 뺐다 — img2img가 실제로는 얼굴만이 아니라 사진 전체(포즈·구도)를
    80% 비중으로 반영한다는 점을 먼저 알렸고, 그래도 제거하기로 확정."""
    try:
        import cv2
    except ImportError:
        return 0, 0.0
    image = cv2.imread(str(path))
    if image is None:
        return 0, 0.0
    ycrcb = cv2.cvtColor(image, cv2.COLOR_BGR2YCrCb)
    skin_pixels = float(cv2.inRange(ycrcb, (0, 133, 77), (255, 173, 127)).sum()) / 255.0
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
        return 0, 0.0
    face_to_skin_ratio = (best_face / skin_pixels) if skin_pixels > 0 else 0.0
    return best_face, face_to_skin_ratio


# 고정 인물 레퍼런스로 최대 이만큼의 사진을 같이 쓴다. 사진 한 장에만
# 의존하면 그 한 장의 각도·조명·표정에 정확도가 좌우되므로(★ 2026-09-23
# "얼굴이 나오는 사진은 되도록 많이 참조해서 정확도를 올리게끔" 요청),
# 자격을 통과한 후보를 점수순으로 여러 장 모아 평균 latent를 만든다.
# ★ 2026-09-23(같은 날 재조정): "얼굴이 전반적으로 좀 이상한데 그냥 제일
# 얼굴 잘나온사진 두개로만 참조해서" — 4장까지 평균 내니 서로 다른 각도·
# 표정이 섞여 오히려 얼굴이 흐트러진다는 피드백으로 2장으로 줄였다.
MAX_REFERENCE_IMAGES = 2


def _select_fixed_references(originals, limit=MAX_REFERENCE_IMAGES):
    """원작 컷 중 얼굴이 크고 뚜렷한 후보를 점수순으로 최대 limit장 골라,
    모든 장면이 공유할 "고정 인물" 레퍼런스 묶음으로 삼는다. 노출 여부는
    거르지 않는다(★ 2026-09-23 "노출장면있는사진을 굳이거를필요없어" 요청).

    ★ 2026-09-23: "얼굴이 한 인물로 고정되면 좋겠어" 요청 — 예전 _scene_reference()는
    장면마다 원작의 다른 컷을 순환시켜 참조로 썼는데, 그게 바로 장면마다 얼굴이
    조금씩 달라 보이던 원인이었다(매번 다른 사진을 참조하니 당연히 다른 얼굴이
    섞여 들어감). 처음에는 가장 잘 나온 사진 한 장만 썼는데, "한 장만 쓰면
    정확도가 떨어지지 않냐"는 후속 요청으로 얼굴이 잘 나온 후보 여러 장을
    함께 골라(호출부가 VAE 인코딩 후 평균 latent를 만드는 데 씀) 한 장의
    각도·조명 편향을 줄인다. 얼굴이 하나도 검출되지 않으면 빈 리스트를
    돌려주고 호출부가 예전 기본값(첫 원작 컷)으로 대체한다."""
    candidates = []
    for path in originals:
        face_area, face_ratio = _face_reference_metrics(path)
        if face_area <= 0:
            continue
        candidates.append((face_area * face_ratio, path))
    candidates.sort(key=lambda item: item[0], reverse=True)
    return [path for _, path in candidates[:limit]]


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
    # ★ 2026-09-23: "초상화에 항상 중국옷 입지말게하고 한국사람이나 일본사람으로
    # 옷 입게 해줘" 요청 — "tasteful contemporary clothing"만으로는 모델이
    # 종종 중국풍 한푸(넓은 소매, 교임깃, 허리띠)로 해석했다. 복장 국적을
    # 명시적으로 지정하고, 부정 프롬프트에서도 중국풍 복식을 뺀다.
    common = (
        "Photorealistic Japanese romance visual novel still, adult Japanese woman age 25 or older, "
        "natural facial anatomy, cinematic available light, coherent recurring character identity, "
        "modern Korean or Japanese everyday fashion (never Chinese hanfu, qipao, or other Chinese "
        "traditional dress), tasteful contemporary clothing, non-explicit, no text, no watermark. "
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
    # OpenAI images/edits는 참조 이미지를 한 장만 받는다 — 여러 장(list)이
    # 오면 점수가 가장 높은(정렬된 목록의 첫) 한 장만 쓴다. 여러 장을
    # 평균 내는 건 ComfyUI(_local_generate) 경로에서만 지원한다.
    if isinstance(reference, (list, tuple)):
        reference = reference[0] if reference else None
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


def _comfy_supports_ipadapter_faceid():
    # ★ 2026-09-23: ComfyUI_IPAdapter_plus 커스텀 노드가 없는 환경(다른 PC로
    # 옮기거나 설치가 아직 안 된 경우)에서도 죽지 않고 예전 img2img+LatentBlend
    # 방식으로 조용히 폴백하도록, 노드 등록 여부를 실행 시점에 확인한다.
    try:
        info = _comfy_request("/object_info/IPAdapterUnifiedLoaderFaceID", timeout=5)
    except Exception:
        return False
    return "IPAdapterUnifiedLoaderFaceID" in info


def _build_comfy_workflow(
    prompt, model_name, seed, reference_names=None,
    loader="CheckpointLoaderSimple", vae_name="",
    use_ipadapter_faceid=False,
):
    # reference_names는 문자열 하나(예전 방식과 호환) 또는 여러 장의 리스트를
    # 받는다. ★ 2026-09-23: "얼굴이 나오는 사진은 되도록 많이 참조해서
    # 정확도를 올리게끔" 요청 — 한 장에만 기대면 그 한 장의 각도·조명·표정
    # 편향이 그대로 인물 정체성에 반영되므로, 자격을 통과한 사진 여러 장을
    # VAE로 각각 인코딩해 동일 가중치로 평균 낸 latent를 레퍼런스로 쓴다.
    if isinstance(reference_names, str):
        reference_names = [reference_names]
    reference_names = [name for name in (reference_names or []) if name]
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
    ipadapter_mode = bool(reference_names) and use_ipadapter_faceid
    blend_mode = bool(reference_names) and not use_ipadapter_faceid
    workflow = {
        "3": {"class_type": "KSampler", "inputs": {
            "seed": seed, "steps": 25, "cfg": 7.0, "sampler_name": "dpmpp_2m",
            "scheduler": "karras", "denoise": 0.48 if blend_mode else 1.0,
            "model": ["22", 0] if ipadapter_mode else ["4", 0],
            "positive": ["6", 0], "negative": ["7", 0],
            "latent_image": ["14", 0] if blend_mode else ["5", 0],
        }},
        "4": {"class_type": loader, "inputs": {
            "ckpt_name" if loader == "CheckpointLoaderSimple" else "model_path": model_name
        }},
        "5": {"class_type": "EmptyLatentImage", "inputs": {"width": IMAGE_WIDTH, "height": IMAGE_HEIGHT, "batch_size": 1}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"text": local_prompt, "clip": ["4", 1]}},
        "7": {"class_type": "CLIPTextEncode", "inputs": {
            "text": (
                "nsfw, nude, child, low quality, blurry, distorted, deformed, bad hands, "
                "text, watermark, caption, subtitle, logo, banner, letters, "
                "chinese hanfu, qipao, cheongsam, chinese traditional dress"
            ),
            "clip": ["4", 1],
        }},
        "8": {"class_type": "VAEDecode", "inputs": {"samples": ["3", 0], "vae": ["12", 0] if vae_name else ["4", 2]}},
        "9": {"class_type": "SaveImage", "inputs": {"filename_prefix": "tulpachat/dating", "images": ["8", 0]}},
    }
    if vae_name:
        workflow["12"] = {"class_type": "VAELoader", "inputs": {"vae_name": vae_name}}
    if ipadapter_mode:
        # ★ 2026-09-23: "인물고정법도 있을건데 그거참고해서 만들면좋겠어" 요청 —
        # IP-Adapter FaceID(InsightFace 얼굴 임베딩으로 모델 자체를 패치)로
        # 바꿨다. img2img+LatentBlend와 달리 레퍼런스 사진의 화면 구도·자막
        # 띠까지 latent로 섞이지 않고 "얼굴 특징"만 반영되므로, 텍스트만으로
        # 만든 순수 txt2img(EmptyLatentImage, denoise=1.0)에 IPAdapterFaceID로
        # 패치한 MODEL을 그대로 물린다. 레퍼런스가 여러 장이면 ImageBatch로
        # 묶어 combine_embeds="average"로 얼굴 임베딩 자체를 평균 낸다 — 픽셀
        # latent를 섞던 예전 방식보다 정체성이 훨씬 안정적으로 유지된다.
        image_ids = []
        for idx, name in enumerate(reference_names):
            load_id = "10" if idx == 0 else f"1{idx}0"
            workflow[load_id] = {"class_type": "LoadImage", "inputs": {"image": name}}
            image_ids.append(load_id)
        if len(image_ids) > 1:
            workflow["21"] = {"class_type": "ImageBatch", "inputs": {
                "image1": [image_ids[0], 0], "image2": [image_ids[1], 0],
            }}
            batched_image = ["21", 0]
        else:
            batched_image = [image_ids[0], 0]
        workflow["20"] = {"class_type": "IPAdapterUnifiedLoaderFaceID", "inputs": {
            "model": ["4", 0], "preset": "FACEID PLUS V2",
            "lora_strength": 0.6, "provider": "CPU",
        }}
        # weight=0.65는 "레퍼런스 비중 65%로" 요청을 이 새 메커니즘에서도
        # 같은 취지(레퍼런스를 과하게 강제하지 않기)로 이어받은 값이다 —
        # img2img blend_factor와 수식은 다르지만 "정체성 반영 강도" 역할은 같다.
        workflow["22"] = {"class_type": "IPAdapterFaceID", "inputs": {
            "model": ["20", 0], "ipadapter": ["20", 1], "image": batched_image,
            "weight": 0.65, "weight_faceidv2": 1.0, "weight_type": "linear",
            "combine_embeds": "average", "start_at": 0.0, "end_at": 1.0,
            "embeds_scaling": "V only",
        }}
    elif blend_mode:
        # 레퍼런스 사진마다 LoadImage+VAEEncode 쌍을 만든다. 첫 장은 예전과
        # 같은 노드 ID(10/11)를 그대로 쓰고, 추가 사진은 "1{idx}0"/"1{idx}1"로
        # 번호를 늘린다(12~14는 이미 VAE/샘플러/최종 블렌드가 쓰고 있어 겹치지
        # 않게 피한다). IP-Adapter FaceID를 못 쓰는 환경(커스텀 노드 미설치
        # 등)을 위한 폴백 경로다.
        encode_ids = []
        for idx, name in enumerate(reference_names):
            load_id, encode_id = ("10", "11") if idx == 0 else (f"1{idx}0", f"1{idx}1")
            workflow[load_id] = {"class_type": "LoadImage", "inputs": {"image": name}}
            workflow[encode_id] = {"class_type": "VAEEncode", "inputs": {
                "pixels": [load_id, 0], "vae": ["12", 0] if vae_name else ["4", 2]
            }}
            encode_ids.append(encode_id)
        # 레퍼런스가 여러 장이면 LatentBlend를 사슬로 이어 동일 가중치 평균을
        # 만든다 — k번째 사진을 더할 때 blend_factor=(k-1)/k로 두면(samples1=
        # 지금까지의 평균, samples2=새 사진) 결과가 항상 "지금까지 더한 사진
        # 전부를 똑같은 비중으로 평균한 값"이 된다(한 장뿐이면 그대로 그 한
        # 장의 latent를 쓴다 — 예전 단일 레퍼런스 동작과 동일).
        combined_id = encode_ids[0]
        for k, encode_id in enumerate(encode_ids[1:], start=2):
            blend_id = f"15{k}"
            workflow[blend_id] = {"class_type": "LatentBlend", "inputs": {
                "samples1": [combined_id, 0], "samples2": [encode_id, 0],
                "blend_factor": (k - 1) / k,
            }}
            combined_id = blend_id
        # 먼저 텍스트만으로 장면의 구도 latent를 만든 뒤, 고정 인물 레퍼런스
        # 평균 latent를 65% 섞고 최종 img2img 패스를 수행한다. ComfyUI
        # LatentBlend는 samples1*blend_factor + samples2*(1-blend_factor)이고
        # samples1=텍스트(13번), samples2=레퍼런스 평균이라 레퍼런스 비중 65%를
        # 얻으려면 blend_factor를 0.35로 둬야 한다.
        workflow["13"] = {"class_type": "KSampler", "inputs": {
            "seed": seed + 1, "steps": 12, "cfg": 7.0, "sampler_name": "dpmpp_2m",
            "scheduler": "karras", "denoise": 1.0, "model": ["4", 0],
            "positive": ["6", 0], "negative": ["7", 0], "latent_image": ["5", 0],
        }}
        workflow["14"] = {"class_type": "LatentBlend", "inputs": {
            "samples1": ["13", 0], "samples2": [combined_id, 0], "blend_factor": 0.35,
        }}
    return workflow


def _largest_face_bbox(rgb_image):
    """PIL RGB 이미지에서 Haar cascade(정면+측면)로 가장 큰 얼굴의 (x, y, w, h)를
    찾는다. IP-Adapter FaceID(InsightFace)는 OpenCV Haar보다 훨씬 엄격해서,
    얼굴이 프레임 경계에서 잘려 있으면 "No face detected"로 실패한다(★
    2026-09-23 277DCV-298 실측 — 원작 클로즈업 컷을 화면 중앙 기준으로만
    자르니 얼굴 절반이 잘려 InsightFace가 인식하지 못했다). 이 bbox는
    `_comfy_upload`가 화면 중앙이 아니라 "얼굴 중앙"을 기준으로 잘라내는 데
    쓰인다."""
    try:
        import cv2
        import numpy as np
    except ImportError:
        return None
    array = cv2.cvtColor(np.array(rgb_image), cv2.COLOR_RGB2BGR)
    gray = cv2.equalizeHist(cv2.cvtColor(array, cv2.COLOR_BGR2GRAY))
    best = None
    for cascade_name in ("haarcascade_frontalface_alt2.xml", "haarcascade_profileface.xml"):
        cascade = _FACE_CASCADES.get(cascade_name)
        if cascade is None:
            cascade = cv2.CascadeClassifier(cv2.data.haarcascades + cascade_name)
            _FACE_CASCADES[cascade_name] = cascade
        for (x, y, w, h) in cascade.detectMultiScale(gray, scaleFactor=1.05, minNeighbors=4, minSize=(50, 50)):
            if best is None or w * h > best[2] * best[3]:
                best = (x, y, w, h)
    return best


def _face_centered_crop(image, target_size):
    """화면 중앙이 아니라 검출된 얼굴 중앙을 기준으로 target_size 비율의
    영역을 최대한 크게 잘라낸다. 얼굴이 검출되지 않으면 기존처럼 화면
    중앙 기준(PIL ImageOps.fit과 동일한 로직)으로 대체한다."""
    from PIL import Image, ImageOps

    target_w, target_h = target_size
    width, height = image.size
    target_ratio = target_w / target_h
    if width / height > target_ratio:
        crop_w, crop_h = height * target_ratio, height
    else:
        crop_w, crop_h = width, width / target_ratio
    bbox = _largest_face_bbox(image)
    if bbox:
        fx, fy, fw, fh = bbox
        center_x, center_y = fx + fw / 2, fy + fh / 2
    else:
        center_x, center_y = width / 2, height / 2
    left = min(max(center_x - crop_w / 2, 0), width - crop_w)
    top = min(max(center_y - crop_h / 2, 0), height - crop_h)
    box = (int(left), int(top), int(left + crop_w), int(top + crop_h))
    return image.resize(target_size, Image.Resampling.LANCZOS, box=box) if bbox else \
        ImageOps.fit(image, target_size, Image.Resampling.LANCZOS)


def _comfy_upload(reference):
    from PIL import Image

    boundary = "----jpcomfy" + hashlib.sha1(str(time.time_ns()).encode()).hexdigest()
    source = reference.read_bytes()
    filename = "dating-reference-" + hashlib.sha1(source).hexdigest()[:12] + ".png"
    with Image.open(io.BytesIO(source)) as image:
        rgb = image.convert("RGB")
        # ★ 2026-09-23: "화면에 글자같은거 안뜨게 해줘" 요청 — 원작 스크린샷은
        # 위(로고·타이틀 배너)·아래(자막 띠)에 텍스트가 거의 항상 박혀 있는데,
        # 이게 레퍼런스 latent에 그대로 인코딩돼 65% 비중으로 섞이면서 생성
        # 이미지에도 뭉개진 가짜 글자 패턴으로 나타났다(부정 프롬프트의
        # "text"만으로는 이미 레퍼런스에 구조로 박힌 내용을 못 지운다). 얼굴은
        # 보통 위쪽 2/3 안에 있으므로 위·아래 자막 띠만 잘라내고 인코딩한다.
        width, height = rgb.size
        top = int(height * 0.10)
        bottom = int(height * 0.82)
        cropped = rgb.crop((0, top, width, bottom)) if bottom > top else rgb
        normalized = _face_centered_crop(cropped, (IMAGE_WIDTH, IMAGE_HEIGHT))
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
    # reference는 단일 Path(예전 방식) 또는 여러 장의 list일 수 있다(★ 2026-09-23
    # "얼굴이 나오는 사진은 되도록 많이 참조해서 정확도를 올리게끔" 요청) —
    # 각각 ComfyUI에 업로드해서 파일명 목록을 만들고, 평균 latent는
    # _build_comfy_workflow가 만든다.
    references = reference if isinstance(reference, (list, tuple)) else ([reference] if reference else [])
    reference_names = [_comfy_upload(ref) for ref in references if ref and ref.is_file()]
    use_ipadapter_faceid = bool(reference_names) and _comfy_supports_ipadapter_faceid()
    base_seed = int.from_bytes(hashlib.sha256(prompt.encode()).digest()[:8], "big") & ((1 << 63) - 1)
    timeout = int(os.environ.get("JP_COMFYUI_TIMEOUT", "600"))
    for attempt in range(4):
        seed = base_seed + attempt * 104729
        workflow = _build_comfy_workflow(
            prompt, model_name, seed, reference_names, loader=loader, vae_name=vae_name,
            use_ipadapter_faceid=use_ipadapter_faceid,
        )
        queued = _comfy_request("/prompt", {"prompt": workflow}, timeout=30)
        if queued.get("node_errors"):
            raise RuntimeError(f"ComfyUI 워크플로 검증 실패: {queued['node_errors']}")
        prompt_id = queued.get("prompt_id")
        if not prompt_id:
            raise RuntimeError(f"ComfyUI가 prompt_id를 반환하지 않았습니다: {queued}")
        try:
            image = _comfy_wait_image(prompt_id, timeout)
        except RuntimeError as exc:
            # ★ 2026-09-23: InsightFace는 OpenCV Haar보다 훨씬 엄격해서, 얼굴
            # 검출용으로 골라둔 레퍼런스 사진이라도 각도·조명에 따라 "No face
            # detected"로 실패할 수 있다(277DCV-298 실측). 이 경우 남은 시도는
            # 예전 img2img+LatentBlend 방식으로 전환해 생성이 아예 실패하지
            # 않도록 한다.
            if use_ipadapter_faceid and "No face detected" in str(exc):
                use_ipadapter_faceid = False
                continue
            raise

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
                    "width": IMAGE_WIDTH, "height": IMAGE_HEIGHT,
                    "steps": sampler["steps"], "cfg": sampler["cfg"],
                    "sampler": sampler["sampler_name"], "scheduler": sampler["scheduler"],
                    "denoise": sampler["denoise"], "base_seed": base_seed,
                    "used_seed": seed, "attempt": attempt + 1,
                    "reference_count": len(reference_names),
                    "composition_pass": (
                        f"IP-Adapter FaceID (얼굴 임베딩 {len(reference_names)}장 평균) + txt2img"
                        if use_ipadapter_faceid else (
                            f"txt2img 12 steps + 35% text/65% reference latent"
                            f"({len(reference_names)}장 평균) + img2img"
                            if len(reference_names) > 1 else
                            "txt2img 12 steps + 35% text/65% reference latent + img2img"
                        )
                    ),
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
              translator=_visual_prompt_from_scene_text, force_keys=None):
    """force=True면 전부, force_keys(문자열 집합)에 담긴 키만이면 그 이미지만
    강제로 다시 만든다(★ 2026-09-23 "이미지 재생성 버튼... 이 사진만
    재생성하기" 요청) — "portrait"는 대표 초상화, 그 외는 장면 키
    (예: "1:first")다. 둘 다 없으면 예전처럼 빠진 파일만 채운다."""
    force_keys = force_keys or set()
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
    # 자격을 통과한 얼굴 사진들만 OpenCV로 골라(토큰 없음) portrait를 만들고,
    # 아래 장면 루프도 전부 그 portrait 하나만 공유 참조한다. 후속 요청
    # "얼굴이 나오는 사진은 되도록 많이 참조해서 정확도를 올리게끔"에 따라
    # 한 장이 아니라 자격을 통과한 후보 전부(최대 MAX_REFERENCE_IMAGES장)를
    # 골라 _local_generate가 평균 latent를 만들게 한다.
    face_references = _select_fixed_references(originals)
    fallback_reference = originals[0] if originals else next((
        path for name in ("cover.jpg", "cover.png", "cover.webp")
        if (path := work_dir / name).is_file()
    ), None)
    reference_pool = face_references or ([fallback_reference] if fallback_reference else [])
    primary_reference = reference_pool[0] if reference_pool else None
    portrait_reference_file = _copy_reference(primary_reference, output, "portrait")
    portrait_reference_files = [portrait_reference_file] + [
        _copy_reference(path, output, f"portrait-{index}")
        for index, path in enumerate(reference_pool[1:], start=1)
    ]
    manifest["portrait_prompt"] = _prompt(work_dir.name)
    manifest["portrait_reference"] = portrait_reference_file
    manifest["portrait_references"] = [name for name in portrait_reference_files if name]
    manifest["reference_source"] = (
        f"face_detected_fixed ({len(face_references)}장 평균)" if face_references
        else ("original_epub_scene" if originals else "cover_fallback")
    )
    if force or "portrait" in force_keys or not _valid_image(portrait):
        manifest["portrait_provider"] = generator(manifest["portrait_prompt"], portrait, reference_pool)
        if manifest["portrait_provider"] == "comfyui":
            manifest["portrait_effective_prompt"] = _LAST_GENERATION_META.get("effective_prompt", "")
            manifest["portrait_generation_settings"] = _LAST_GENERATION_META.get("generation_settings", {})
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    # 이후 모든 장면은 portrait.png(없으면 위에서 고른 얼굴 사진)를 동일하게
    # 참조한다 — 장면마다 다른 원작 컷을 쓰지 않는다.
    fixed_reference_path = portrait if _valid_image(portrait) else primary_reference
    fixed_reference_file = "portrait.png" if _valid_image(portrait) else portrait_reference_file
    for scene in plan["selected"]:
        filename = _image_filename(scene["key"])
        target = output / filename
        try:
            if force or scene["key"] in force_keys or not _valid_image(target):
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
    parser.add_argument("--force-key", action="append", default=[],
                         help="이 키(portrait 또는 예: 1:first)만 강제로 다시 만든다. 여러 번 줄 수 있다.")
    args = parser.parse_args()
    manifest = run_agent(
        Path(args.work_dir).resolve(), max(4, min(args.max_scenes, 30)), args.force,
        force_keys=set(args.force_key) or None,
    )
    print(f"🖼️ 작품 이미지 에이전트: {manifest['status']} · 장면 {len(manifest['scenes'])}/{manifest['selected_count']}장")
    return 0 if manifest["status"] == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
