"""완성 EPUB 안의 원작 이미지를 미연시 참고 후보로 복원한다."""
from __future__ import annotations

import hashlib
import re
import zipfile
from pathlib import Path


IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}
DEFAULT_COMPLETED_EPUB_ROOT = Path.home() / "Desktop" / "BlogImage" / "av완성작"
WORK_CODE_RE = re.compile(r"(?<![A-Z0-9])(?=[A-Z0-9_-]*[A-Z])[A-Z0-9]{2,12}[-_ ]\d{2,6}(?!\d)", re.I)


def _work_code(value: str) -> str:
    match = WORK_CODE_RE.search(str(value or "").upper())
    return re.sub(r"[_ ]", "-", match.group(0)) if match else ""


def matching_epubs(work_dir: Path, completed_root: Path = DEFAULT_COMPLETED_EPUB_ROOT) -> list[Path]:
    """작업 폴더와 같은 작품 코드의 로컬·완성 EPUB을 모두 찾는다."""
    work_dir = Path(work_dir)
    code = _work_code(work_dir.name)
    candidates = list(work_dir.glob("*.epub"))
    # 작품 코드를 식별하지 못한 임시·테스트 폴더에서 완성 서재 전체를 잘못
    # 같은 작품으로 취급하지 않는다. 외부 서재 검색은 코드가 있을 때만 한다.
    if code and completed_root.is_dir():
        candidates.extend(completed_root.glob("*.epub"))
    unique = {}
    for path in candidates:
        if code and _work_code(path.name) != code:
            continue
        try:
            unique[str(path.resolve())] = path
        except OSError:
            continue
    return sorted(unique.values(), key=lambda path: path.name.casefold())


def restore_epub_images(work_dir: Path, completed_root: Path = DEFAULT_COMPLETED_EPUB_ROOT) -> list[Path]:
    """EPUB의 모든 래스터 이미지를 images/epub_sources에 복원한다.

    기존 images/ 파일과 내용이 같은 것은 SHA-256으로 건너뛴다. ZIP 내부 경로를
    그대로 쓰지 않고 해시가 포함된 안전한 파일명으로 저장한다.
    """
    work_dir = Path(work_dir)
    image_dir = work_dir / "images"
    image_dir.mkdir(parents=True, exist_ok=True)
    target_dir = image_dir / "epub_sources"
    known_hashes = set()
    for path in image_dir.glob("**/*"):
        if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES:
            try:
                known_hashes.add(hashlib.sha256(path.read_bytes()).hexdigest())
            except OSError:
                pass

    restored = []
    for epub in matching_epubs(work_dir, completed_root):
        try:
            with zipfile.ZipFile(epub) as archive:
                members = sorted(
                    (name for name in archive.namelist()
                     if not name.endswith("/") and Path(name).suffix.lower() in IMAGE_SUFFIXES),
                    key=str.casefold,
                )
                for member in members:
                    data = archive.read(member)
                    if not data:
                        continue
                    digest = hashlib.sha256(data).hexdigest()
                    if digest in known_hashes:
                        continue
                    known_hashes.add(digest)
                    safe_stem = re.sub(r"[^0-9A-Za-z._-]+", "_", Path(member).stem).strip("._") or "image"
                    target = target_dir / f"{safe_stem}-{digest[:10]}{Path(member).suffix.lower()}"
                    target_dir.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(data)
                    restored.append(target)
        except (OSError, zipfile.BadZipFile, RuntimeError):
            continue
    return restored
