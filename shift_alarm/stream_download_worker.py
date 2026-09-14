#!/usr/bin/env python3
"""Shift Alarm owner-approved video downloader.

The web server writes one mode-0600 request file. This deterministic worker reads
that request, runs yt-dlp with fixed safety limits, and hands the finished file to
the existing iCloudSync.app. It never receives commands from an AI model.
"""
from __future__ import annotations

import argparse
import datetime as dt
import ipaddress
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

STATE_DIR = Path(os.path.expanduser("~/.tulpachat/video_downloads"))
STATE_FILE = STATE_DIR / "status.json"
LOCK_FILE = STATE_DIR / "active.lock"
STAGING_DIR = STATE_DIR / "staging"
ICLOUD_DIR = Path(os.path.expanduser(
    "~/Library/Mobile Documents/com~apple~CloudDocs/Shift Alarm Downloads"
))
ICLOUD_HELPER = Path(__file__).resolve().parent / "iCloudSync.app"
ICLOUD_MANIFEST_DIR = Path(os.path.expanduser("~/.shift_alarm_icloud_sync"))
YTDLP = "/opt/homebrew/bin/yt-dlp"
MAX_FILESIZE = "5G"


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def write_state(**changes) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        state = {}
    state.update(changes, updated_at=now(), pid=os.getpid())
    temporary = STATE_FILE.with_suffix(f".{os.getpid()}.tmp")
    temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    os.chmod(temporary, 0o600)
    temporary.replace(STATE_FILE)


def validate_public_https_url(value: str) -> str:
    if len(value) > 2048 or any(char in value for char in "\r\n\t"):
        raise ValueError("주소 형식이 올바르지 않습니다")
    parsed = urllib.parse.urlsplit(value)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("공개 HTTPS 주소만 사용할 수 있습니다")
    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(parsed.hostname, parsed.port or 443)}
    except socket.gaierror as exc:
        raise ValueError("사이트 주소를 찾을 수 없습니다") from exc
    for address in addresses:
        ip = ipaddress.ip_address(address)
        if not ip.is_global:
            raise ValueError("내부망 또는 로컬 주소는 사용할 수 없습니다")
    return value


def safe_filename(path: Path) -> str:
    name = re.sub(r"[\x00-\x1f/:]", "_", path.name).strip(" .")
    return (name[:220] or f"video-{uuid.uuid4().hex[:8]}.mp4")


def queue_icloud_copy(source: Path) -> tuple[Path, Path]:
    ICLOUD_MANIFEST_DIR.mkdir(parents=True, exist_ok=True)
    destination = ICLOUD_DIR / safe_filename(source)
    manifest = ICLOUD_MANIFEST_DIR / f"manifest_{uuid.uuid4().hex}.txt"
    manifest.write_text(f"{source}\t{destination}\n", encoding="utf-8")
    os.chmod(manifest, 0o600)
    subprocess.run(["/usr/bin/open", "-na", str(ICLOUD_HELPER)], check=False, timeout=15)
    return destination, manifest


def notify_owner(filename: str) -> None:
    token = os.environ.get("WORKER_TOKEN", "")
    if not token:
        return
    payload = json.dumps({
        "title": "영상 다운로드 완료",
        "body": f"{filename}\niPhone 파일 앱에서 nPlayer/루틴으로 이동해주세요.",
        "url": "/shift-alarm/",
    }).encode()
    request = urllib.request.Request(
        "http://127.0.0.1:8000/api/worker/mobile_notification", data=payload,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
        method="POST",
    )
    try:
        urllib.request.urlopen(request, timeout=10).read()
    except Exception:
        pass


def run(request_path: Path) -> int:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    STAGING_DIR.mkdir(parents=True, exist_ok=True)
    lock_fd = None
    try:
        lock_fd = os.open(LOCK_FILE, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.write(lock_fd, str(os.getpid()).encode())
    except FileExistsError:
        write_state(state="failed", stage="다른 다운로드가 이미 실행 중입니다", error="busy")
        return 2
    try:
        request = json.loads(request_path.read_text(encoding="utf-8"))
        url = validate_public_https_url(str(request.get("url", "")).strip())
        job_id = str(request.get("job_id", ""))
        job_dir = STAGING_DIR / job_id
        job_dir.mkdir(parents=True, exist_ok=False)
        write_state(job_id=job_id, state="running", stage="영상 정보를 확인하는 중", progress=1, error=None)
        command = [
            YTDLP, "--no-playlist", "--no-part", "--no-overwrites", "--newline",
            "--max-filesize", MAX_FILESIZE, "--merge-output-format", "mp4",
            "--output", str(job_dir / "%(title).120B [%(id)s].%(ext)s"),
            "--progress-template", "download:PROGRESS:%(progress._percent_str)s",
            "--print", "after_move:RESULT:%(filepath)s", url,
        ]
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        result_path = None
        assert process.stdout is not None
        for line in process.stdout:
            line = line.strip()
            if line.startswith("PROGRESS:"):
                match = re.search(r"([0-9]+(?:\.[0-9]+)?)%", line)
                if match:
                    if sum(path.stat().st_size for path in job_dir.iterdir() if path.is_file()) > 5 * 1024 ** 3:
                        process.terminate()
                        raise RuntimeError("다운로드가 5GB 제한을 넘었습니다")
                    write_state(state="running", stage="영상을 다운로드하는 중", progress=min(94, float(match.group(1)) * .93))
            elif line.startswith("RESULT:"):
                result_path = Path(line[7:])
        return_code = process.wait()
        if return_code != 0 or not result_path or not result_path.is_file():
            raise RuntimeError("영상을 내려받지 못했습니다. 로그인·DRM·만료된 주소 여부를 확인해주세요")
        if result_path.stat().st_size > 5 * 1024 ** 3:
            raise RuntimeError("완성된 파일이 5GB 제한을 넘었습니다")
        write_state(state="syncing", stage="iCloud Drive로 보내는 중", progress=96, filename=result_path.name)
        destination, _manifest = queue_icloud_copy(result_path)
        copied = False
        for _ in range(120):
            try:
                if destination.is_file() and destination.stat().st_size == result_path.stat().st_size:
                    copied = True
                    break
            except OSError:
                pass
            time.sleep(1)
        if copied:
            result_path.unlink(missing_ok=True)
            try:
                job_dir.rmdir()
            except OSError:
                pass
        write_state(
            state="complete", stage=("iCloud Drive 저장 완료" if copied else "iCloud Drive 전송 요청 완료 · 파일 앱에서 동기화를 확인해주세요"), progress=100,
            filename=destination.name, destination="iCloud Drive/Shift Alarm Downloads",
            completed_at=now(),
        )
        notify_owner(destination.name)
        return 0
    except Exception as exc:
        if "job_dir" in locals():
            shutil.rmtree(job_dir, ignore_errors=True)
        write_state(state="failed", stage=str(exc)[:240], progress=0, error=type(exc).__name__)
        return 1
    finally:
        try:
            request_path.unlink()
        except OSError:
            pass
        if lock_fd is not None:
            os.close(lock_fd)
        try:
            LOCK_FILE.unlink()
        except OSError:
            pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", required=True, type=Path)
    sys.exit(run(parser.parse_args().request))
