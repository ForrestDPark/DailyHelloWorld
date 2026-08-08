#!/usr/bin/env python3
"""자소서·포트폴리오 원문을 비공개 코퍼스로 추출하고 공유 프로필을 검증한다.

원본과 추출 텍스트는 ``data/career_profile/`` 아래에만 두며 Git에 올리지 않는다.
Git에는 연락처·주소 등 개인정보를 뺀 ``candidate_profile.json``만 공유한다.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import unicodedata
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET


DEFAULT_SOURCE_DIRS = [
    Path("/Users/forrestdpark/Desktop/이전 자소서"),
    Path("/Users/forrestdpark/Desktop/자소서"),
]
PRIVATE_DIR = Path(__file__).resolve().parent / "data" / "career_profile"
PROFILE_PATH = Path(__file__).resolve().parent / "candidate_profile.json"
SUPPORTED = {".docx", ".pptx", ".pdf", ".hwp", ".pages"}
SENSITIVE_NAME_MARKERS = {
    "주민등록", "등본", "초본", "신분증", "통장", "건강보험", "성적증명",
    "여권", "프로필사진", "프로필 사진", "흑백", "사이버검사", "훈련진단",
}
PII_PATTERNS = [
    (re.compile(r"\b\d{6}\s*[- ]\s*[1-4]\d{6}\b"), "[주민번호 제거]"),
    (re.compile(r"\b01[016789][ -]?\d{3,4}[ -]?\d{4}\b"), "[전화번호 제거]"),
    (re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"), "[이메일 제거]"),
]


def normalized(value: str) -> str:
    return unicodedata.normalize("NFC", value)


def is_sensitive(path: Path) -> bool:
    name = normalized(str(path))
    return any(marker in name for marker in SENSITIVE_NAME_MARKERS)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def clean_text(text: str) -> str:
    text = unicodedata.normalize("NFC", text).replace("\x00", "")
    for pattern, replacement in PII_PATTERNS:
        text = pattern.sub(replacement, text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_office_xml(path: Path, pattern: re.Pattern[str]) -> str:
    chunks = []
    with zipfile.ZipFile(path) as archive:
        names = sorted(name for name in archive.namelist() if pattern.fullmatch(name))
        for name in names:
            try:
                root = ET.fromstring(archive.read(name))
            except ET.ParseError:
                continue
            texts = [node.text for node in root.iter() if node.tag.endswith("}t") and node.text]
            if texts:
                chunks.append("\n".join(texts))
    return "\n\n".join(chunks)


def extract_docx(path: Path) -> str:
    return extract_office_xml(path, re.compile(r"word/(?:document|header\d+|footer\d+)\.xml"))


def extract_pptx(path: Path) -> str:
    return extract_office_xml(path, re.compile(r"ppt/slides/slide\d+\.xml"))


def extract_pdf(path: Path) -> str:
    result = subprocess.run(
        ["pdftotext", "-layout", str(path), "-"], capture_output=True, text=True
    )
    return result.stdout if result.returncode == 0 else ""


def extract_hwp(path: Path) -> str:
    result = subprocess.run(
        ["textutil", "-convert", "txt", "-stdout", str(path)],
        capture_output=True, text=True,
    )
    return result.stdout if result.returncode == 0 else ""


def extract_pages(path: Path) -> str:
    # Pages 문서는 같은 시기의 docx 사본이 대부분이다. QuickLook PDF가 내장된
    # 경우에만 읽고, IWA 전용 파일은 안전하게 미지원으로 기록한다.
    try:
        with zipfile.ZipFile(path) as archive:
            for candidate in ("QuickLook/Preview.pdf", "preview.pdf"):
                if candidate in archive.namelist():
                    temp = PRIVATE_DIR / "_pages_preview.pdf"
                    temp.write_bytes(archive.read(candidate))
                    try:
                        return extract_pdf(temp)
                    finally:
                        temp.unlink(missing_ok=True)
    except zipfile.BadZipFile:
        pass
    return ""


def extract_text(path: Path) -> str:
    return {
        ".docx": extract_docx,
        ".pptx": extract_pptx,
        ".pdf": extract_pdf,
        ".hwp": extract_hwp,
        ".pages": extract_pages,
    }[path.suffix.lower()](path)


def scan(source_dirs: list[Path]) -> dict:
    PRIVATE_DIR.mkdir(parents=True, exist_ok=True)
    seen_hashes = {}
    documents = []
    corpus_parts = []
    for root in source_dirs:
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in SUPPORTED:
                continue
            record = {"path": str(path), "name": normalized(path.name)}
            if is_sensitive(path):
                record.update(status="excluded_sensitive", chars=0)
                documents.append(record)
                continue
            digest = sha256(path)
            record["sha256"] = digest
            if digest in seen_hashes:
                record.update(status="duplicate", duplicate_of=seen_hashes[digest], chars=0)
                documents.append(record)
                continue
            seen_hashes[digest] = str(path)
            text = clean_text(extract_text(path))
            status = "extracted" if text else "unsupported_or_empty"
            record.update(status=status, chars=len(text))
            documents.append(record)
            if text:
                corpus_parts.append(f"\n\n===== SOURCE: {normalized(path.name)} =====\n{text}")
    index = {"source_dirs": [str(path) for path in source_dirs], "documents": documents}
    (PRIVATE_DIR / "source_index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (PRIVATE_DIR / "career_corpus.txt").write_text(
        "".join(corpus_parts).strip() + "\n", encoding="utf-8"
    )
    return index


def validate_profile(path: Path = PROFILE_PATH) -> dict:
    profile = json.loads(path.read_text(encoding="utf-8"))
    required = {"schema_version", "identity", "target_roles", "skills", "experience", "projects", "story_bank"}
    missing = required - profile.keys()
    if missing:
        raise ValueError(f"공유 프로필 필수 키 누락: {sorted(missing)}")
    serialized = json.dumps(profile, ensure_ascii=False)
    for pattern, _ in PII_PATTERNS:
        if pattern.search(serialized):
            raise ValueError("공유 프로필에 연락처·이메일·주민번호 형태가 포함되어 있습니다.")
    if not profile["projects"] or not profile["story_bank"]:
        raise ValueError("프로젝트와 자소서 사례가 비어 있습니다.")
    return profile


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    scan_parser = sub.add_parser("scan", help="원본을 비공개 텍스트 코퍼스로 추출")
    scan_parser.add_argument("sources", nargs="*", type=Path)
    sub.add_parser("validate", help="Git 공유용 비식별 프로필 검증")
    args = parser.parse_args()
    if args.command == "scan":
        index = scan(args.sources or DEFAULT_SOURCE_DIRS)
        counts = {}
        for record in index["documents"]:
            counts[record["status"]] = counts.get(record["status"], 0) + 1
        print(json.dumps(counts, ensure_ascii=False))
        print(PRIVATE_DIR / "career_corpus.txt")
    else:
        profile = validate_profile()
        print(f"프로필 검증 완료: 프로젝트 {len(profile['projects'])}개, 사례 {len(profile['story_bank'])}개")


if __name__ == "__main__":
    main()
