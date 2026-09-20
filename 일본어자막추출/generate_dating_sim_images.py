#!/usr/bin/env python3
"""작품별 미연시 이미지 에이전트.

시나리오를 읽고 시각적으로 겹치지 않는 장면을 고른 뒤 대표 초상화와 장면
이미지를 생성한다. 작업 상태를 manifest.json에 매 장 저장하므로 중단 뒤에도
이어갈 수 있다. 이 스크립트의 쓰기 범위는 해당 작품의 dating_sim_images 폴더뿐이다.
"""
from __future__ import annotations

import argparse
import base64
import gc
import hashlib
import json
import math
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path


VERSION = 1
DEFAULT_MAX_SCENES = 12
IMAGE_DIR_NAME = "dating_sim_images"
MANIFEST_NAME = "manifest.json"
LOCATIONS = ("first", "walk", "quiet")
_LOCAL_PIPELINE = None
_LOCAL_PIPELINE_EDIT = None


def _clean(text, limit=700):
    text = re.sub(r"\[[^|\]]+\|([^\]]+)\]", r"\1", str(text or ""))
    text = re.sub(r"\s+", " ", text).strip()
    # 원작의 성인 대사를 이미지 서비스로 그대로 보내지 않는다. 시각적 맥락만 쓴다.
    text = re.sub(r"(?i)(sex|nude|explicit|성관계|나체|강간|임신|사정)", "private conversation", text)
    return text[:limit]


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
        f"Source work identifier: {_clean(title, 100)}. "
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


def _local_generate(prompt, target, reference=None):
    global _LOCAL_PIPELINE, _LOCAL_PIPELINE_EDIT
    import torch
    from diffusers import StableDiffusionImg2ImgPipeline, StableDiffusionPipeline
    from PIL import Image, ImageOps
    model = os.environ.get("CHATAPP_LOCAL_IMAGE_MODEL", "stable-diffusion-v1-5/stable-diffusion-v1-5")
    klass = StableDiffusionImg2ImgPipeline if reference and reference.is_file() else StableDiffusionPipeline
    edit = bool(reference and reference.is_file())
    if _LOCAL_PIPELINE is None or _LOCAL_PIPELINE_EDIT != edit:
        if _LOCAL_PIPELINE is not None:
            del _LOCAL_PIPELINE
            gc.collect()
            if torch.backends.mps.is_available():
                torch.mps.empty_cache()
        _LOCAL_PIPELINE = klass.from_pretrained(model, torch_dtype=torch.float32, use_safetensors=True)
        _LOCAL_PIPELINE.enable_attention_slicing()
        _LOCAL_PIPELINE = _LOCAL_PIPELINE.to("mps")
        _LOCAL_PIPELINE_EDIT = edit
    pipe = _LOCAL_PIPELINE
    seed = int.from_bytes(hashlib.sha256(prompt.encode()).digest()[:4], "big")
    kwargs = dict(prompt=prompt, negative_prompt="low quality, blurry, distorted, text, watermark, child",
                  num_inference_steps=24, guidance_scale=7.0,
                  generator=torch.Generator(device="cpu").manual_seed(seed))
    if reference and reference.is_file():
        with Image.open(reference) as image:
            kwargs["image"] = ImageOps.fit(image.convert("RGB"), (512, 512), Image.Resampling.LANCZOS)
        kwargs["strength"] = 0.65
    pipe(**kwargs).images[0].save(target, format="PNG", optimize=True)


def _generate(prompt, target, reference=None):
    try:
        _openai_generate(prompt, target, reference)
        return "openai"
    except Exception as openai_error:
        print(f"⚠️ OpenAI 이미지 실패, 로컬 Diffusers로 전환: {openai_error}", flush=True)
        try:
            _local_generate(prompt, target, reference)
            return "diffusers"
        except Exception as local_error:
            raise RuntimeError(f"OpenAI 실패({openai_error}) / Diffusers 실패({local_error})") from local_error


def run_agent(work_dir, max_scenes=DEFAULT_MAX_SCENES, force=False, generator=_generate):
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
    cover_reference = next((path for name in ("cover.jpg", "cover.png", "cover.webp")
                            if (path := work_dir / name).is_file()), None)
    if force or not portrait.is_file():
        manifest["portrait_provider"] = generator(_prompt(work_dir.name), portrait, cover_reference)
        manifest["portrait_reference"] = cover_reference.name if cover_reference else None
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    for scene in plan["selected"]:
        filename = _image_filename(scene["key"])
        target = output / filename
        try:
            if force or not target.is_file():
                provider = generator(_prompt(work_dir.name, scene), target, portrait)
            else:
                provider = manifest.get("scenes", {}).get(scene["key"], {}).get("provider", "existing")
            manifest["scenes"][scene["key"]] = {"file": filename, "provider": provider,
                                                     "day": scene["day"], "location": scene["location"],
                                                     "prompt": _prompt(work_dir.name, scene)}
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
