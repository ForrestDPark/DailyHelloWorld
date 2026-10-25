"""툴파챗 서버 (이 Mac에서 실행, Cloudflare Tunnel로 노출).

이 서버는 채팅 UI를 제공하고 메시지·대기열을 SQLite에 저장할 뿐, 실제 AI 응답은
절대 생성하지 않는다 — Claude/Codex CLI 인증 정보를 공개 인터넷에 노출된
프로세스로 옮기지 않기 위해서다. 응답 생성은 항상 사용자의 Mac에서 도는
worker/persona_worker.py가 이 서버를 폴링해서 처리한다(자세한 이유는
../README.md 참고).

/api/worker/* 엔드포인트는 WORKER_TOKEN 환경변수가 설정돼 있으면 그 토큰을
요구한다(배포 시 반드시 설정 — 안 그러면 누구나 페르소나 프로필을 덮어쓰거나
가짜 응답을 주입할 수 있다).

★ 2026-08-24: 처음엔 앱 전체가 인증 없이 열려 있었는데, 실제로 URL을 아는
지인이 들어와서 "나"인 척 메시지를 보내는 사고가 났다. 그래서 처음엔 소유자
1계정만 쓰기 가능하고 나머지는 전부 읽기 전용으로 통일하는 Basic Auth를
붙였었다.

★ 2026-08-26: "다른 사용자들도 메시지를 남길 수 있으면 좋겠다"는 요청으로
로그인/회원가입 기반 다중 계정으로 확장했다. 이제 계정만 있으면 누구나 쓸 수
있다 — 대신 "다른 사용자가 페르소나를 조종해서 내 파일/프로젝트에 실제 행동을
시키면 안 된다"는 요청에 따라, 실제 부작용이 있는 동작(손동주의 파일 정리
등)은 worker/persona_worker.py 쪽에서 세션의 실제 사용자명이 소유자 계정과
정확히 일치할 때만 실행되도록 별도로 게이트한다(이 파일은 "누가 로그인했는지"
정보만 정확히 넘겨주면 됨 — 승인 판단 자체는 여기서 하지 않는다).

기존 Basic Auth(APP_USERNAME/APP_PASSWORD)는 shift_alarm.py가 소유자 자격으로
/api/all_messages를 폴링할 때 여전히 쓰므로(브라우저 로그인 세션이 없는
백그라운드 프로세스라 쿠키를 못 씀) 소유자 전용 대체 인증 경로로 남겨뒀다."""
import asyncio
import base64
import collections
import concurrent.futures
import datetime
import hashlib
import fcntl
import html
import ipaddress
import json
import os
import random
import re
import secrets
import signal
import shutil
import socket
import ssl
import sqlite3
import statistics
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import unicodedata
from copy import deepcopy
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, File, Form, Header, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.background import BackgroundTask
from starlette.middleware.base import BaseHTTPMiddleware

from pywebpush import WebPushException, webpush

from server import ai_keys, audio_editor, auth, battle_sim_story, dating_audio, dating_sim_story, life_terrain_quiz, mp3_player, mp3_postprocess, mp3_recommendations, oauth, stock_portfolio, topic_analysis, transcriptions, transcription_summary
from server.db import get_conn, init_db
from server.mp3_sync import persist_lrc_to_library, store_synced_lrc
from worker.ai_exec import circuit_status, run_ai_exec, run_provider_api

BASE_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BASE_DIR.parent.parent
CAREER_WEB_DIR = REPO_ROOT / "이직시스템" / "web_dashboard"
CAREER_DATA_DIR = REPO_ROOT / "이직시스템" / "data"
CAREER_SYSTEM_DIR = REPO_ROOT / "이직시스템"
SHIFT_ALARM_DASHBOARD_DIR = BASE_DIR / "shift_alarm_dashboard"
VOCABULARY_WEB_DIR = BASE_DIR / "vocabulary_web"
MEMO_WEB_DIR = BASE_DIR / "memo_web"
COMFY_WEB_DIR = BASE_DIR / "comfy_web"
SQL_LAB_WEB_DIR = BASE_DIR / "sql_lab_web"
TRANSCRIPTION_WEB_DIR = BASE_DIR / "transcription_web"
SQL_LAB_DATA_DIR = Path(os.path.expanduser("~/.tulpachat/sql_lab"))
SQL_LAB_DATA_DIR.mkdir(parents=True, exist_ok=True)
DATING_SIM_WEB_DIR = BASE_DIR / "dating_sim_web"
DATING_SIM_AUDIO_DIR = DATING_SIM_WEB_DIR / "audio"
_dating_sim_tts_lock = threading.Lock()
_TOPIC_ANALYSIS_WORKER_STARTED = False
AUDIO_EDITOR_WEB_DIR = BASE_DIR / "audio_editor_web"
MP3_PLAYER_WEB_DIR = BASE_DIR / "mp3_player_web"
MP3_LIBRARY_DIR = Path(os.path.expanduser("~/Music/Shift Alarm MP3"))
MP3_LIBRARY_DIR.mkdir(parents=True, exist_ok=True)
MP3_DOWNLOAD_ARCHIVE = MP3_LIBRARY_DIR / ".youtube-download-archive.txt"
MP3_FAVORITES_DIR = Path("/Users/forrestdpark/Desktop/BlogImage/좋아요플레이")
_mp3_download_lock = threading.Lock()
_mp3_download_jobs: dict[str, dict[str, Any]] = {}
_mp3_postprocess_lock = threading.Lock()
_mp3_postprocess_recovery_started = False
_mp3_recommendation_cache: dict[str, dict[str, Any]] = {}
_mp3_recommendation_cache_lock = threading.Lock()
LRC_JOB_ROOT = Path(os.path.expanduser("~/.tulpachat/mp3_player/lrc_jobs"))
LRC_JOB_ROOT.mkdir(parents=True, exist_ok=True)
LRC_UPLOAD_ROOT = Path(os.path.expanduser("~/.tulpachat/mp3_player/lrc_uploads"))
LRC_UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
_lrc_job_run_lock = threading.Lock()
_lrc_recovery_started = False
BATTLE_SIM_WEB_DIR = BASE_DIR / "battle_sim_web"
SUNZI_WEB_DIR = BASE_DIR / "sunzi_web"
SUNZI_SITE_DIR = BASE_DIR / "sunzi_site"
LIFE_TERRAIN_WEB_DIR = BASE_DIR / "life_terrain_web"
FITNESS_WEB_DIR = BASE_DIR / "fitness_web"
TERRAIN_SURVEY_WEB_DIR = BASE_DIR / "terrain_survey_web"
STOCK_PORTFOLIO_WEB_DIR = BASE_DIR / "stock_portfolio_web"
_terrain_nearby_cache: dict[tuple[float, float, int], dict[str, Any]] = {}
SHIFT_ALARM_STATUS_FILE = Path(os.path.expanduser(
    "~/Library/Mobile Documents/com~apple~CloudDocs/ShiftAlarmStatus/status.json"
))
# Shift Alarm은 위 iCloud 파일을 복사하기 직전에 이 기존 스테이징 파일에 같은
# JSON을 쓴다. launchd 서버는 macOS TCC 때문에 Mobile Documents 읽기가 거부될
# 수 있으므로, 그때만 동일 바이트인 이 파일을 사용한다(새 파이프라인이 아님).
SHIFT_ALARM_STATUS_FALLBACK_FILE = Path(os.path.expanduser(
    "~/.shift_alarm_icloud_sync/status.json"
))
SHIFT_ALARM_STATUS_CACHE_FILE = Path(os.path.expanduser(
    "~/.tulpachat/shift_alarm_status_last_good.json"
))
SHIFT_ALARM_DISMISSED_FILE = Path(os.path.expanduser("~/.tulpachat/shift_alarm_dismissed.json"))
SHIFT_ALARM_REMINDER_EDITOR_FILE = Path(os.path.expanduser("~/.shift_alarm_reminders.json"))
SHIFT_ALARM_BUDEUGI_FILE = Path(os.path.expanduser("~/.shift_alarm_budeugi.json"))
SHIFT_ALARM_BUDEUGI_JOURNAL_FILE = Path(os.path.expanduser("~/.shift_alarm_budeugi_journal.json"))
SHIFT_ALARM_BUDEUGI_AUDIO_DIR = Path(os.path.expanduser("~/.tulpachat/budeugi_audio"))
SHIFT_ALARM_BUDEUGI_TTS_VOICE = "ko-KR-SunHiNeural"
# shift_alarm.py의 notify_spoken()이 매 호출마다 이 파일을 읽어 muted면 배너음·
# 음성 안내를 건너뛴다 — self.config(~/.shift_alarm_config.json)는 shift_alarm.py가
# 주기적으로 통째로 덮어써서 웹 서버가 직접 쓰면 경쟁 상태가 생기므로(리마인더
# 편집기와 같은 이유) 별도 파일로 뗐다(★ 2026-09-23).
SHIFT_ALARM_MUTE_FILE = Path(os.path.expanduser("~/.shift_alarm_mute.json"))
SHIFT_ALARM_SLEEP_MODE_FILE = Path(os.path.expanduser("~/.shift_alarm_sleep_mode.json"))
SHIFT_ALARM_SLEEP_NOTIFICATION_QUEUE_FILE = Path(os.path.expanduser("~/.shift_alarm_sleep_notifications.jsonl"))
SHIFT_ALARM_SLEEP_MUSIC_SECONDS = 2 * 60 * 60
SHIFT_ALARM_SLEEP_MUTE_SECONDS = 8 * 60 * 60
SHIFT_ALARM_SLEEP_SPEAK_MAX_CHARS = 100
SHIFT_ALARM_OUT_LOG_FILE = Path(os.path.expanduser("~/Library/Logs/shift_alarm.out.log"))
# shift_alarm.py가 wake_shift 등 "⏰ 기상 알람" 리마인더를 울리기 직전에 이 파일을
# 읽어 enabled면 macOS 시스템 음량을 percent로 강제 설정한다 — 전날 밤 음량을
# 낮춰두면 정작 기상 알람이 조용히 지나갈 수 있다는 문제(★ 2026-09-23: "기상알람
# 음량 설정할수있게끔 설정버튼 만들어줘" 요청).
SHIFT_ALARM_WAKE_VOLUME_FILE = Path(os.path.expanduser("~/.shift_alarm_wake_volume.json"))
SHIFT_ALARM_ROUTINE_HISTORY_FILE = Path(os.path.expanduser("~/.shift_alarm_routine_history.jsonl"))
SHIFT_ALARM_SCHEDULE_FILE = Path(__file__).resolve().parents[3] / "shift_alarm" / "d_team_schedule_2026.json"
SHIFT_ALARM_QUEST_EVENTS_FILE = Path(os.path.expanduser("~/.shift_alarm_quest_events.jsonl"))
SHIFT_ALARM_CULTIVATION_CHOICES_FILE = Path(os.path.expanduser("~/.shift_alarm_cultivation_choices.json"))
SHIFT_ALARM_CULTIVATION_INTERVALS_FILE = Path(os.path.expanduser("~/.shift_alarm_cultivation_intervals.json"))
SHIFT_ALARM_QUEST_LOCK = threading.RLock()
SHIFT_ALARM_QUEST_EPOCH = "2026-10-05"
SHIFT_ALARM_ROUTINE_SIGNAL_FILE = Path(os.path.expanduser("~/.shift_alarm_routine_signal.json"))
SHIFT_ALARM_CHECKLIST_STATE_CACHE_FILE = Path(
    os.path.expanduser("~/.shift_alarm_checklist_state.json")
)
SHIFT_ALARM_HOMECOMING_FILE = Path(os.path.expanduser("~/.shift_alarm_homecoming.json"))
SHIFT_ALARM_HUE_CONFIG_FILE = Path(os.path.expanduser("~/.shift_alarm_hue.json"))
SHIFT_ALARM_HUE_ROOM_NAME = "거실1"
SHIFT_ALARM_NOTION_PAGE_ID = "3b532a1e-ae80-8034-90af-fd8c9b658711"
SHIFT_ALARM_REMINDER_TIMES_PAGE_ID = "3d432a1e-ae80-8171-b8e1-e0d3c545a707"
SUNZI_DISCUSSION_ROOM_ID = "custom_16ea779e1f"
SUNZI_LIGHT_PIPELINE_REQUEST = "📜 ShiftAlarm에서 오늘의 병법 구절 라이트 분석을 요청했습니다."
SUNZI_PIPELINE_LOCK_DIR = Path("/private/tmp/com.forrest.codex-sunzi-nightly.lock")
SUNZI_PIPELINE_STATUS_FILE = Path(os.path.expanduser("~/Library/Logs/CodexSunzi/status.json"))
SUNZI_AUTOMATION_README = Path("/Users/forrestdpark/.codex-worktrees/sunzi-nightly/손자병법/README.md")
# "구절편 전체보기" 팝오버용 — 야간 파이프라인 전용 worktree가 아니라 main에 실제
# 병합된 본 저장소 쪽 파일을 읽는다(worktree는 미완료 커밋이 있을 수 있음).
SUNZI_CHAPTER_DIR = REPO_ROOT / "손자병법"
SUNZI_SITE_GENERATED_FILE = SUNZI_CHAPTER_DIR / "site" / "app" / "content" / "generated.ts"
SUNZI_CHAPTER_SOURCE_FILE = SUNZI_CHAPTER_DIR / "site" / "app" / "content" / "notion-chapters.ts"
SUNZI_PIPELINE_CURSOR_FILE = SUNZI_CHAPTER_DIR / "pipeline_cursor.json"
SUNZI_CHAPTER_SEQUENCE = (
    (11, "구지편"), (12, "화공편"), (13, "용간편"),
    (1, "시계편"), (2, "작전편"), (3, "모공편"), (4, "군형편"),
    (5, "병세편"), (6, "허실편"), (7, "군쟁편"), (8, "구변편"),
    (9, "행군편"), (10, "지형편"),
)
SUNZI_VERSE_FILE_RE = re.compile(r"^jiudi(\d+)_full_page\.md$")
SUNZI_VERSE_SUMMARY_RE = re.compile(r'<details[^>]*>\s*<summary>(.*?)</summary>', re.DOTALL)
NOTION_VERSION = "2022-06-28"
# ★ "업데이트할 때마다 페이지를 재시작(새로고침)해야 하는 게 맞냐" 요청
# (2026-08-28) — 서버 프로세스(app.py 등 백엔드 코드)가 바뀌면 재시작 시
# 이 값이 새로 생성돼서 바뀐다. static/*(프론트 HTML·JS·CSS)는 서버를
# 재시작하지 않아도 디스크에서 매 요청 새로 읽히므로(StaticFiles가 자체
# 캐시를 안 함, Cache-Control: no-cache까지 강제) 파일을 고치기만 해도
# 즉시 반영된다 — 다만 이미 열려 있는 브라우저 탭은 그 사실을 스스로 알
# 방법이 없어서 새로고침 전까진 예전 JS를 계속 쓴다. GET /api/version이
# "서버 부팅 id + 정적 파일 중 가장 최근 수정 시각"을 합쳐서 내려주면,
# 프론트가 주기적으로 이 값을 확인해 바뀌었을 때만 "새 버전이 있어요"
# 배너를 띄워 사용자가 놓치지 않고 새로고침할 수 있다.
SERVER_BOOT_ID = os.urandom(4).hex()
WORKER_TOKEN = os.environ.get("WORKER_TOKEN", "")
APP_USERNAME = os.environ.get("APP_USERNAME", "")
# ★ "채팅방에 새 메시지 있으면 사용자들한테도 알람이 가게 해달라" 요청
# (2026-08-27) — 브라우저 Web Push. 서버(server/.venv)에 pywebpush를 따로
# 설치했다(공용 anaconda 환경에 설치했다가 cryptography 버전 충돌로
# pyopenssl이 깨진 적이 있어, 이후 이 서버만 독립 venv로 분리함 — README
# 참고). 개인키는 리포에 커밋하지 않고 파일 경로로만 읽는다.
VAPID_PRIVATE_KEY_FILE = os.environ.get("VAPID_PRIVATE_KEY_FILE", "")
VAPID_PUBLIC_KEY = os.environ.get("VAPID_PUBLIC_KEY", "")
VAPID_CLAIM_EMAIL = os.environ.get("VAPID_CLAIM_EMAIL", "")


def push_enabled():
    # ★ pywebpush의 webpush(vapid_private_key=...)는 PEM 텍스트가 아니라
    # "파일 경로 문자열"을 받아야 한다(os.path.isfile로 직접 판별해서 내부적
    # 으로 Vapid.from_file을 호출함) — PEM을 미리 읽어서 넘기면
    # Vapid.from_string이 그 텍스트를 DER로 오인해 파싱 에러가 난다.
    return bool(
        VAPID_PRIVATE_KEY_FILE and os.path.exists(VAPID_PRIVATE_KEY_FILE)
        and VAPID_PUBLIC_KEY and VAPID_CLAIM_EMAIL
    )
APP_PASSWORD = os.environ.get("APP_PASSWORD", "")
MAX_CONTEXT_MESSAGES = 20

# 홈·Shift Alarm이 함께 쓰는 시스템 업데이트 알림. ID는 한 번 배포한 뒤
# 바꾸지 않아야 계정별 읽음 상태가 유지된다. 새 기능을 공개할 때 항목을
# 위에 추가하면 별도의 외부 서비스 없이 알림 센터에 나타난다.
SYSTEM_UPDATE_NOTIFICATIONS = (
    {
        "id": "system:2026-09-09:notification-center",
        "title": "통합 알림 센터가 생겼습니다",
        "body": "시스템 업데이트와 읽지 않은 툴파챗 메시지를 나툼에서 한곳에 모아 확인할 수 있습니다.",
        "url": "/#home", "created_at": "2026-09-09T00:00:00+09:00",
    },
    {
        "id": "system:2026-09-07:shift-alarm-schedule",
        "title": "Shift Alarm 시각표가 개선됐습니다",
        "body": "기상·멜라토닌 일정과 오늘 근무 유형 자동 선택이 추가됐습니다.",
        "url": "/shift-alarm/", "created_at": "2026-09-07T20:11:00+09:00",
    },
    {
        "id": "system:2026-09-07:epub-reader",
        "title": "일본어 EPUB 읽기가 편해졌습니다",
        "body": "세로 스크롤·자동 읽기·현재 구절 강조와 후리가나 표시를 개선했습니다.",
        "url": "/epub/", "created_at": "2026-09-07T18:00:00+09:00",
    },
)

# 알림 읽음 여부와 무관하게 시스템 화면에서 계속 볼 수 있는 제품 변경 이력.
# 사용자에게 의미 있는 완료 단위만 기록하고 최신순으로 반환한다.
WEBAPP_UPDATE_HISTORY = (
    {"id": "manual:2026-10-04:history-content-hash", "created_at": "2026-10-04T16:45:00+09:00", "system": "나툼", "title": "SYSTEM HISTORY 실제 변경 기준 기록", "body": "파일명이 아닌 실제 diff로 기능별 카드를 만들고, 변경 내용 해시가 같은 경우에만 중복으로 처리합니다.", "url": "/#systems", "action_label": "변경 확인"},
    {"id": "manual:2026-10-04:sleep-playlist", "created_at": "2026-10-04T15:45:00+09:00", "system": "Shift Alarm", "title": "멜라토닌 체크 후 숙면 음악", "body": "멜라토닌 리마인더를 체크하면 숙면 플레이리스트를 시작하고 2시간 뒤 자동으로 정지합니다.", "url": "/shift-alarm/", "action_label": "변경 확인"},
    {"id": "manual:2026-10-04:sleep-quiet", "created_at": "2026-10-04T15:44:00+09:00", "system": "Shift Alarm", "title": "취침 중 8시간 알림 무음", "body": "숙면 시작 후 8시간은 Shift Alarm과 툴파챗 알림을 모아두고, 기상 알람 때 메시지 내용을 100자까지 읽어줍니다.", "url": "/shift-alarm/", "action_label": "변경 확인"},
    {"created_at": "2026-10-02T12:00:00+09:00", "system": "나툼", "title": "Git 변경 업데이트 자동 기록", "body": "커밋 전이라도 추적 중인 코드 변경이 안정되면 시스템별 제목과 변경 파일 요약을 SYSTEM HISTORY에 자동으로 남깁니다.", "url": "/#systems"},
    {"created_at": "2026-10-02T11:55:00+09:00", "system": "학습 서재", "title": "EPUB 연속 읽기 화면 정리", "body": "본문 사이의 중복 장면 제목·자동 읽기 버튼과 화면 높이만큼 생기던 큰 빈 공간을 제거했습니다.", "url": "/epub/"},
    {"created_at": "2026-10-01T09:10:00+09:00", "system": "녹음 텍스트화", "title": "대사 위치에서 원본 음성 재생", "body": "전체 텍스트의 대사를 누르면 해당 타임코드부터 원본 녹음을 재생하고 현재 대사를 강조합니다. 고품질·기존 전사 표시도 구분했습니다.", "url": "/transcriptions/"},
    {"created_at": "2026-10-01T08:55:00+09:00", "system": "나툼", "title": "시스템 아이콘 전면 교체", "body": "홈의 16개 시스템 아이콘을 임시 글자·이모지·단순 SVG 대신 기능을 직관적으로 나타내는 통일된 이미지 세트로 교체했습니다.", "url": "/#home"},
    {"created_at": "2026-10-01T05:20:00+09:00", "system": "녹음 텍스트화", "title": "로컬 녹음 텍스트화 시스템", "body": "M4A·MP3 등 녹음을 Mac의 로컬 Whisper로 순차 변환하고 진행 상태와 시간대별 텍스트를 나툼에서 확인할 수 있습니다.", "url": "/transcriptions/"},
    {"created_at": "2026-09-26T01:00:00+09:00", "system": "DB 실험실", "title": "SQL 학습용 데이터베이스 실험실", "body": "서비스 데이터와 격리된 SQLite에서 조회·JOIN·집계·테이블 설계를 직접 실습할 수 있습니다.", "url": "/sql-lab/"},
    {"created_at": "2026-09-26T00:00:00+09:00", "system": "미연시", "title": "미연시 전용 업데이트 타임라인", "body": "작품별 시나리오·이미지 작업 완료와 기능·디자인 변경 사항을 미연시 안에서 최신순으로 확인할 수 있습니다.", "url": "/dating-sim/"},
    {"created_at": "2026-09-25T11:25:00+09:00", "system": "나툼", "title": "전체 업데이트 타임라인", "body": "시스템 화면에서 Shift Alarm뿐 아니라 웹앱 전체 변경 내용을 최신순으로 확인할 수 있습니다.", "url": "/#systems"},
    {"created_at": "2026-09-25T11:10:00+09:00", "system": "Shift Alarm", "title": "아이폰·Apple Watch 알림", "body": "맥 알림을 웹 푸시로 전달하고 아이폰·워치 알림 구독 버튼과 진동 요청을 추가했습니다.", "url": "/shift-alarm/"},
    {"created_at": "2026-09-25T10:57:00+09:00", "system": "Shift Alarm", "title": "일일 루틴 알림 시각 학습", "body": "같은 근무 유형의 최근 전부 체크 완료 시각을 학습해 10분 전에 알립니다.", "url": "/shift-alarm/"},
    {"created_at": "2026-09-25T10:35:00+09:00", "system": "Shift Alarm", "title": "리마인더 시각 자동 학습", "body": "모든 리마인더 체크 시각을 기록하고 다음 같은 근무 주기의 알림 시각에 반영합니다.", "url": "/shift-alarm/"},
    {"created_at": "2026-09-25T09:55:00+09:00", "system": "Shift Alarm", "title": "AI 사용량과 생활 기록 UI", "body": "Codex·Claude 사용량을 정돈하고 운기조식·흡연 횟수와 마지막 기록 시각을 추가했습니다.", "url": "/shift-alarm/"},
    {"created_at": "2026-09-25T09:30:00+09:00", "system": "Shift Alarm", "title": "북마크 관리 개선", "body": "최근 추가한 북마크가 먼저 보이며 검색어 중심 목록과 추가·수정·삭제를 지원합니다.", "url": "/shift-alarm/"},
    {"created_at": "2026-09-25T09:15:00+09:00", "system": "Shift Alarm", "title": "모바일 패널 UI 정리", "body": "토글 높이·색상·배지 정렬을 통일하고 패널 순서를 직접 바꿀 수 있게 했습니다.", "url": "/shift-alarm/"},
    {"created_at": "2026-09-25T09:05:00+09:00", "system": "손자병법", "title": "구절 휠 탐색 개선", "body": "현재 구절을 크게 표시하고 전후 구절을 시계 휠처럼 탐색하도록 개선했습니다.", "url": "/#sunzi"},
    {"created_at": "2026-09-25T08:50:00+09:00", "system": "Shift Alarm", "title": "생활 리듬 그래프", "body": "기상·루틴 완료·리마인더 체크 시간을 기간별 그래프로 볼 수 있게 했습니다.", "url": "/shift-alarm/"},
    {"created_at": "2026-09-24T12:10:00+09:00", "system": "일본어 학습", "title": "미연시 진행 상태와 학습 표현", "body": "제작 단계별 진행률·중단 이유·재실행과 장면 대사 기반 학습 표현을 보강했습니다.", "url": "/epub/"},
    {"created_at": "2026-09-24T11:56:00+09:00", "system": "Shift Alarm", "title": "근무표와 오늘 근무 상세", "body": "오늘 근무 시간과 월간 D·S·G·휴무 근무표, 날짜별 리마인더를 함께 표시합니다.", "url": "/shift-alarm/"},
    {"created_at": "2026-09-09T00:00:00+09:00", "system": "나툼", "title": "통합 알림 센터", "body": "시스템 업데이트와 읽지 않은 메시지를 한곳에서 확인할 수 있게 했습니다.", "url": "/#home"},
    {"created_at": "2026-09-07T18:00:00+09:00", "system": "일본어 학습", "title": "EPUB 리더 개선", "body": "세로 스크롤·자동 읽기·현재 구절 강조와 후리가나 표시를 개선했습니다.", "url": "/epub/"},
)

WORKTREE_UPDATE_STATE_FILE = Path(os.path.expanduser("~/.tulpachat/system_worktree_updates.json"))
WORKTREE_UPDATE_SETTLE_SECONDS = 90
_WORKTREE_UPDATE_WATCHER_STARTED = False


def _update_destination(paths):
    joined = "\n".join(paths)
    if "shift_alarm" in joined:
        return "Shift Alarm", "/shift-alarm/"
    if "손자병법" in joined:
        return "손자병법", "/#sunzi"
    if "vocabulary_web" in joined:
        return "단어장", "/vocabulary/"
    if "memo_web" in joined:
        return "메모", "/memo/"
    if "dating_sim" in joined:
        return "미연시", "/dating-sim/"
    if "일본어자막추출" in joined:
        return "학습 서재", "/epub/"
    if "이직시스템" in joined:
        return "이직 시스템", "/career/"
    return "나툼", "/#systems"


def _worktree_file_snapshot():
    """Git이 추적하는 소스 변경만 파일별 지문으로 돌려준다."""
    git = next((candidate for candidate in (
        "/opt/homebrew/bin/git", "/usr/local/bin/git", shutil.which("git"),
    ) if candidate and Path(candidate).is_file()), None)
    if not git:
        return {}
    try:
        result = subprocess.run(
            [git, "diff", "--name-only", "-z", "HEAD", "--", "."], cwd=REPO_ROOT,
            capture_output=True, timeout=8, check=True,
        )
    except (OSError, subprocess.SubprocessError):
        return {}
    snapshot = {}
    for raw in result.stdout.split(b"\0"):
        if not raw:
            continue
        path = raw.decode("utf-8", errors="replace")
        if path.endswith(".DS_Store") or "/library/" in f"/{path}" or "/audio/" in f"/{path}":
            continue
        target = REPO_ROOT / path
        try:
            if not target.is_file():
                snapshot[path] = "deleted"
            elif target.stat().st_size <= 5 * 1024 * 1024:
                snapshot[path] = hashlib.sha256(target.read_bytes()).hexdigest()
            else:
                stat = target.stat()
                snapshot[path] = f"large:{stat.st_size}:{stat.st_mtime_ns}"
        except OSError:
            continue
    return snapshot


def _read_worktree_update_state():
    try:
        data = json.loads(WORKTREE_UPDATE_STATE_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _write_worktree_update_state(data):
    WORKTREE_UPDATE_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    temporary = WORKTREE_UPDATE_STATE_FILE.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, WORKTREE_UPDATE_STATE_FILE)


def _worktree_update_history():
    history = _read_worktree_update_state().get("history") or []
    return [item for item in history if isinstance(item, dict)]


def _update_content_key(item):
    """실제 변경 지문만 중복 판정에 사용한다.

    제목·설명은 서로 다른 작업도 같은 문장으로 축약될 수 있으므로 중복 키로
    사용하지 않는다. 수동 기록과 과거 기록은 고유 ID만 사용한다.
    """
    return str(item.get("content_hash") or item.get("id") or "").strip()


def _worktree_diff(paths):
    """기능 판별에 사용할 실제 Git diff를 반환한다."""
    git = next((candidate for candidate in (
        "/opt/homebrew/bin/git", "/usr/local/bin/git", shutil.which("git"),
    ) if candidate and Path(candidate).is_file()), None)
    if not git or not paths:
        return ""
    try:
        result = subprocess.run(
            [git, "diff", "--unified=2", "HEAD", "--", *paths], cwd=REPO_ROOT,
            capture_output=True, text=True, timeout=10, check=True,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return result.stdout


def _describe_worktree_update(paths, system, url):
    """파일명 나열을 사용자가 이해할 수 있는 기능 변경 설명으로 바꾼다."""
    joined = " ".join(paths).lower()
    rules = (
        (("reminder-focus.css",), "TODAY 리마인더 수정 바로가기", "TODAY의 삭제 버튼을 수정 버튼으로 바꾸고, 누르면 같은 리마인더 설정 위치까지 바로 이동하도록 했습니다."),
        (("sunzi-recovery.css",), "병법 분석 중단 후 복구 흐름", "분석이 멈추면 원인과 다음 행동을 보여주고, 완료한 구절은 유지한 채 중단 지점부터 다시 시작하도록 했습니다."),
        (("sunzi-deck.css",), "병법 구절 카드 탐색", "중간에 걸리던 시계형 스크롤을 한 장씩 정확히 넘어가는 카드 방식으로 바꾸고 현재 구절을 크게 표시했습니다."),
        (("library-layout.css",), "서재 아이콘·격자 보기", "영어·일반 서재에 아이콘 보기와 격자 보기를 추가하고 마지막 선택을 기억하도록 했습니다."),
        (("transcription",), "녹음 텍스트화 개선", "전사와 요약을 나눠 읽기 쉽게 만들고, 대사를 누르면 해당 시점의 원본 음성을 재생하도록 했습니다."),
        (("dating_sim", "dating-sim"), "미연시 제작·플레이 개선", "시나리오·이미지 작업의 진행 상태와 중단 사유를 보여주고 멈춘 단계만 다시 실행할 수 있게 했습니다."),
        (("shift_alarm_dashboard",), "Shift Alarm 화면·동작 개선", "오늘 근무·리마인더·생활 기록을 한 화면에서 확인하고 바로 조작할 수 있도록 정리했습니다."),
        (("web_reader",), "학습 서재 읽기 경험 개선", "최근 읽던 위치를 유지하고 책 선택과 읽기 조작을 더 쉽게 찾도록 화면을 정리했습니다."),
        (("chatapp/static",), "나툼 화면 사용성 개선", "주요 기능의 위치와 카드 조작 방식을 정리해 필요한 화면으로 더 빠르게 이동하도록 했습니다."),
    )
    for needles, title, body in rules:
        if any(needle in joined for needle in needles):
            return title, body, "변경 확인"
    return f"{system} 기능 개선", f"{system}의 화면과 동작을 더 빠르고 직관적으로 사용할 수 있도록 정리했습니다.", "변경 확인"


def _describe_worktree_updates(paths, system, url, diff_text=""):
    """실제 diff에서 독립된 사용자 기능을 찾아 카드 단위로 분리한다."""
    evidence = ("\n".join(paths) + "\n" + diff_text).casefold()
    feature_rules = (
        (("sleep_playlist", "sleep_mode", "숙면", "잠잘준비"),
         "멜라토닌 체크 후 숙면 음악",
         "멜라토닌 리마인더를 체크하면 숙면 플레이리스트를 시작하고 2시간 뒤 자동으로 정지합니다."),
        (("notification_mute", "mute_until", "quiet_until", "queued_notification", "밀린 알림", "100글자"),
         "취침 중 알림 무음과 기상 요약",
         "취침 중에는 알림을 모아두고 기상 알람 때 메시지 내용을 100자까지 읽어줍니다."),
        (("mediaremote", "media/transport", "_send_media_key", "transport-playpause"),
         "음악 이전·재생·다음 제어 복구",
         "웹의 음악 조작 버튼을 macOS 현재 재생 세션에 직접 연결해 Elmedia를 안정적으로 제어합니다."),
        (("reminder_check_stats", "check_success", "성공률", "d-day", "dday"),
         "리마인더 D-day와 체크 성공률",
         "다음 알림까지 남은 날과 최근 체크 시각, 누적 체크 성공률을 함께 표시합니다."),
        (("youtube", "yt-dlp", "mp3"),
         "YouTube MP3 다운로드와 재생",
         "휴대폰에서 다운로드를 요청하고 Mac에서 MP3로 저장해 플레이어에서 재생할 수 있게 했습니다."),
        (("system_worktree_updates", "content_hash", "_worktree_diff", "system history"),
         "SYSTEM HISTORY 변경 내용 기반 기록",
         "실제 diff로 기능별 카드를 만들고 변경 내용 해시로만 중복을 판정하도록 고쳤습니다."),
    )
    descriptions = [
        (title, body, "변경 확인")
        for needles, title, body in feature_rules
        if any(needle in evidence for needle in needles)
    ]
    if descriptions:
        return descriptions
    return [_describe_worktree_update(paths, system, url)]


LEGACY_WORKTREE_UPDATE_DETAILS = {
    "worktree:3f439183055e3808acf2": (
        "병법 구절 카드 탐색",
        "중간에 걸리던 시계형 스크롤을 한 장씩 정확히 넘어가는 카드 방식으로 바꾸고 현재 구절을 크게 표시했습니다.",
    ),
    "worktree:4c258f878af5e8523b0f": (
        "병법 분석 중단 후 복구 흐름",
        "분석이 멈추면 원인과 다음 행동을 보여주고, 완료한 구절은 유지한 채 중단 지점부터 다시 시작하도록 했습니다.",
    ),
    "worktree:2a38438698f0176f6ebe": (
        "TODAY 리마인더 수정 바로가기",
        "TODAY의 삭제 버튼을 수정 버튼으로 바꾸고, 누르면 같은 리마인더 설정 위치까지 바로 이동하도록 했습니다.",
    ),
    "worktree:f25caf7106cfcc8f5aeb": (
        "SYSTEM HISTORY 기능 중심 카드",
        "파일명만 보이던 기록을 기능 이름 중심의 카드로 바꾸고, 카드를 누르면 요약과 변경 확인 버튼이 나타나도록 했습니다.",
    ),
}


def _watch_worktree_updates_forever():
    """연속 편집을 90초 동안 묶은 뒤 SYSTEM HISTORY 한 항목으로 기록한다."""
    while True:
        try:
            now = int(time.time())
            current = _worktree_file_snapshot()
            state = _read_worktree_update_state()
            previous = state.get("snapshot")
            if not isinstance(previous, dict):
                state.update({"snapshot": current, "observed_at": now, "history": state.get("history") or []})
                _write_worktree_update_state(state)
            else:
                changed = sorted(path for path in set(previous) | set(current) if previous.get(path) != current.get(path))
                if changed:
                    pending = set(state.get("pending_paths") or [])
                    pending.update(changed)
                    fingerprints = dict(state.get("pending_fingerprints") or {})
                    fingerprints.update({path: current.get(path, "deleted") for path in changed})
                    state.update({
                        "snapshot": current, "pending_paths": sorted(pending),
                        "pending_fingerprints": fingerprints, "changed_at": now,
                    })
                    _write_worktree_update_state(state)
                elif state.get("pending_paths") and now - int(state.get("changed_at") or now) >= WORKTREE_UPDATE_SETTLE_SECONDS:
                    paths = list(state["pending_paths"])
                    system, url = _update_destination(paths)
                    diff_text = _worktree_diff(paths)
                    fingerprints = state.get("pending_fingerprints") or {
                        path: current.get(path, "deleted") for path in paths
                    }
                    change_payload = json.dumps(
                        sorted((path, fingerprints.get(path, "deleted")) for path in paths),
                        ensure_ascii=False, separators=(",", ":"),
                    )
                    change_hash = hashlib.sha256(change_payload.encode("utf-8")).hexdigest()
                    created_at = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
                    history = list(state.get("history") or [])
                    new_items = []
                    for title, body, action_label in _describe_worktree_updates(
                        paths, system, url, diff_text
                    ):
                        content_hash = hashlib.sha256(
                            f"{change_hash}\0{title}\0{body}".encode("utf-8")
                        ).hexdigest()
                        item = {
                            "id": f"worktree:{content_hash[:20]}",
                            "content_hash": content_hash, "change_hash": change_hash,
                            "created_at": created_at, "system": system,
                            "title": title, "body": body, "url": url,
                            "action_label": action_label, "paths": paths,
                        }
                        if not any(
                            isinstance(existing, dict)
                            and existing.get("content_hash") == content_hash
                            for existing in history
                        ):
                            new_items.append(item)
                    history = [*new_items, *history]
                    history = history[:100]
                    state.update({
                        "history": history, "pending_paths": [],
                        "pending_fingerprints": {}, "recorded_at": now,
                    })
                    _write_worktree_update_state(state)
        except Exception as exc:  # noqa: BLE001
            print(f"⚠️ Git 변경 업데이트 기록 실패: {exc}")
        time.sleep(30)


def _display_update_title(title):
    """커밋 메시지를 화면용으로 짧고 자연스러운 작업명으로 정리한다."""
    text = str(title or "").strip()
    # 커밋 메시지에는 존댓말을 쓰더라도 SYSTEM HISTORY에서는 작업명으로
    # 노출하므로 '개선해드립니다'보다 '개선'처럼 간결하게 끝낸다.
    text = re.sub(r"해\s*드립니다[.!?]?$", "", text).strip()
    return text or str(title or "").strip()


def _git_update_history(limit=80):
    """main 저장소의 완료 커밋을 사용자용 업데이트 기록으로 변환한다."""
    git = next((candidate for candidate in (
        "/opt/homebrew/bin/git", "/usr/local/bin/git", shutil.which("git"),
    ) if candidate and Path(candidate).is_file()), None)
    if not git:
        return []
    try:
        result = subprocess.run(
            [git, "log", f"-{limit}", "--date=iso-strict",
             "--pretty=format:%x1e%H%x1f%cI%x1f%s", "--name-only", "--", "."],
            cwd=REPO_ROOT, capture_output=True, text=True, timeout=5, check=True,
        )
    except (OSError, subprocess.SubprocessError):
        return []

    items = []
    for record in result.stdout.split("\x1e"):
        lines = [line.strip() for line in record.strip().splitlines() if line.strip()]
        if not lines:
            continue
        header = lines[0].split("\x1f", 2)
        if len(header) != 3:
            continue
        commit_hash, created_at, title = header
        title = _display_update_title(title)
        paths = lines[1:]
        system, url = _update_destination(paths)
        items.append({
            "id": f"git:{commit_hash}", "created_at": created_at,
            "system": system, "title": title,
            "body": f"관련 파일 {len(paths)}개가 메인에 반영됐습니다.", "url": url,
        })
    return items


def _current_webapp_update_history():
    """수동 과거 기록과 Git 완료 기록을 합쳐 최신순으로 반환한다."""
    merged = [*WEBAPP_UPDATE_HISTORY, *_worktree_update_history(), *_git_update_history()]
    normalized = []
    for item in merged:
        item = dict(item)
        legacy_detail = LEGACY_WORKTREE_UPDATE_DETAILS.get(item.get("id"))
        if legacy_detail:
            item.update(title=legacy_detail[0], body=legacy_detail[1], action_label="변경 확인")
        # 구형 자동 기록은 실제 diff나 변경 해시를 보존하지 않아 정확한 기능을
        # 복원할 수 없다. 같은 일반 문구를 계속 노출하지 않고, 수동으로 복원한
        # 정확한 카드와 새 content_hash 형식의 기록만 보여준다.
        elif str(item.get("id") or "").startswith("worktree:") and not item.get("content_hash"):
            continue
        if str(item.get("title") or "").endswith("코드 업데이트"):
            paths = item.get("paths") or []
            if paths:
                title, body, action_label = _describe_worktree_update(paths, item.get("system") or "나툼", item.get("url") or "/#systems")
            else:
                title = f"{item.get('system') or '나툼'} 기능 개선"
                body = f"{item.get('system') or '나툼'} 화면과 동작을 개선했습니다. 변경 확인을 누르면 해당 기능으로 이동합니다."
                action_label = "변경 확인"
            item.update(title=title, body=body, action_label=action_label)
        normalized.append(item)
    # 제목·설명은 중복 판정에 사용하지 않는다. 실제 변경 내용의 해시 또는
    # 수동/커밋 고유 ID가 같은 경우에만 한 건으로 합친다.
    result = []
    seen_updates = set()
    for item in sorted(normalized, key=lambda entry: entry["created_at"], reverse=True):
        update_key = _update_content_key(item)
        if update_key and update_key in seen_updates:
            continue
        if update_key:
            seen_updates.add(update_key)
        result.append(item)
    return result


def _dating_sim_update_history(include_admin=False):
    """최근에 실제로 생성·교체된 미연시 이미지만 반환한다.

    Git 변경 요약은 시스템 히스토리의 책임이다. 이 창에서 같은
    '제작·플레이 개선' 카드를 반복하면 사용자가 어느 작품의 어느
    이미지가 바뀌었는지 확인할 수 없으므로 이미지 파일 수정 시각을 원본으로
    삼는다. 관리자 프롬프트 결과는 소유자에게만 노출한다.
    """
    items = []
    library = REPO_ROOT / "일본어자막추출" / "library"
    try:
        work_dirs = [path for path in library.iterdir() if path.is_dir()]
    except OSError:
        work_dirs = []
    work_to_book = {}
    for book_id in dating_sim_story.all_book_ids():
        _, resolved = dating_sim_story.resolve_book_work_dir(f"book:{book_id}")
        if resolved:
            work_to_book[str(resolved.resolve())] = book_id
    for work_dir in work_dirs:
        manifest_path = work_dir / "dating_sim_images" / "manifest.json"
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        book_id = work_to_book.get(str(work_dir.resolve()))
        if not book_id:
            continue
        labels = {str(manifest.get("portrait") or "portrait.png"): "대표 초상화"}
        for scene_key, record in (manifest.get("scenes") or {}).items():
            if isinstance(record, dict) and record.get("file"):
                labels[str(record["file"])] = f"장면 {scene_key}"
        if include_admin:
            for record in (manifest.get("admin_prompt_images") or {}).values():
                if isinstance(record, dict) and record.get("file"):
                    labels[str(record["file"])] = f"관리자 프롬프트 · {record.get('name') or '이미지'}"
        for filename, label in labels.items():
            if filename.startswith("admin-") and not include_admin:
                continue
            target = manifest_path.parent / filename
            if not target.is_file() or target.suffix.lower() != ".png":
                continue
            stat = target.stat()
            created_at = datetime.datetime.fromtimestamp(
                stat.st_mtime, datetime.timezone.utc
            ).astimezone().isoformat()
            route = "admin-images" if filename.startswith("admin-") else "images"
            items.append({
                "id": f"dating-image:{work_dir.name}:{filename}:{stat.st_mtime_ns}",
                "created_at": created_at, "system": "최근 이미지", "kind": "image",
                "title": f"{work_dir.name} · {label}",
                "body": "이미지를 누르면 생성 정보와 프롬프트 편집창이 바로 열립니다.",
                "url": "/dating-sim/", "story_id": f"book:{book_id}",
                "work": work_dir.name, "image_file": filename, "image_label": label,
                "image_url": f"/api/dating-sim/books/{book_id}/{route}/{filename}?t={int(stat.st_mtime)}",
            })
    return sorted(items, key=lambda item: item["created_at"], reverse=True)[:60]

SESSION_COOKIE_NAME = "tulpa_session"
SESSION_COOKIE_MAX_AGE = auth.SESSION_MAX_AGE_SECONDS  # 180일
USERNAME_RE = re.compile(r"^[A-Za-z0-9_가-힣]{2,20}$")

# ★ 인증 없이 접근 가능한 경로 — 로그인 자체를 하려면 "/"와 정적 파일, 그리고
# 회원가입/로그인 API는 인증 이전에 열려 있어야 한다. /api/whoami는 로그인
# 여부를 프론트가 확인하는 용도라 항상 응답한다(그 자체로 정보 노출 없음).
PUBLIC_PATHS = {
    "/", "/chat", "/chat/", "/manifest.json", "/api/whoami", "/api/auth/signup", "/api/auth/login", "/api/auth/logout", "/api/version",
    "/api/public/sunzi-analysis",
    # ★ 2026-08-26: 구글/카카오 로그인 — 이 네 경로는 아직 세션이 없는 상태에서
    # 오는 요청(로그인 시작·프로바이더가 돌려보내는 콜백)이라 공개로 열어둔다.
    "/api/auth/google/login", "/api/auth/google/callback",
    "/api/auth/kakao/login", "/api/auth/kakao/callback",
}
OAUTH_STATE_COOKIE = "tulpa_oauth_state"

# ★ "링크로 공유해서 다른 사람이 채팅을 읽기만(쓰기는 못하게) 할 수 있게
# 해달라" 요청(2026-08-25) — 계정 없이도 쿼리스트링(?share=...)의 토큰이
# 맞으면 읽기 전용으로 통과시키고 쿠키에 저장해 재방문에도 유지한다.
READ_SHARE_TOKEN = os.environ.get("READ_SHARE_TOKEN", "")
SHARE_COOKIE_NAME = "tulpa_share"
SHARE_COOKIE_MAX_AGE = 60 * 60 * 24 * 180  # 180일

# ★ 2026-08-25: "채팅창에 이미지 업로드해서 서로 분석하면 좋겠다"는 요청.
# 서버와 워커가 이제 같은 Mac에서 도니까(더 이상 클라우드 분리 구조가 아님),
# 업로드된 이미지를 로컬 디스크에 두면 워커가 그대로 파일 경로로 읽어
# claude/codex의 이미지 첨부 기능에 넘길 수 있다 — 별도 다운로드·스토리지
# 서비스가 필요 없다. server/db.py의 CHATAPP_DB_PATH와 같은 패턴으로
# ~/.tulpachat/ 아래에 둔다.
UPLOADS_DIR = Path(os.path.expanduser("~/.tulpachat/uploads"))
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10MB
ALLOWED_UPLOAD_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic"}
BACKGROUND_UPLOAD_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
IMAGE_MARKER_RE = re.compile(
    r"!\[[^\]]*\]\((?:/uploads/[^)\s]+|https?://[^)\s]+)\)"
)


def _preview_text(content):
    """방 목록 미리보기용 — 이미지 마커는 사람이 읽을 문구로 바꾼다."""
    if IMAGE_MARKER_RE.search(content):
        stripped = IMAGE_MARKER_RE.sub("", content).strip()
        return "📷 사진" + (f" {stripped}" if stripped else "")
    return content


def _credentials_match(username, password, expected_username, expected_password):
    # ★ 2026-08-24 실측 버그: secrets.compare_digest(str, str)는 둘 중 하나라도
    # ASCII가 아닌 문자가 있으면 TypeError를 던진다(문서화된 CPython 제약) —
    # 다른 아이디로 로그인 시도하는 사람이 실수로건 의도적이건 비ASCII 문자가
    # 든 아이디/비밀번호를 넣으면 500 에러가 났다. bytes로 인코딩해서
    # 비교하면 이 제약이 없다.
    return (
        secrets.compare_digest(username.encode("utf-8"), expected_username.encode("utf-8"))
        and secrets.compare_digest(password.encode("utf-8"), expected_password.encode("utf-8"))
    )


def _resolve_auth(request):
    """세션 쿠키 → 소유자 Basic Auth(하위 호환) → 공유 링크 순서로 확인해
    request.state.user/can_write/share_guest를 채운다. 어디에도 해당 없으면
    user=None, can_write=False, share_guest=False로 남고 False를 반환한다
    (보호된 경로면 이때 401).

    ★ share_guest를 user/can_write와 별도로 두는 이유: 공유 링크 읽기 전용
    방문자와 완전 비로그인(차단 대상) 방문자가 둘 다 user=None,
    can_write=False라 이 둘을 구분할 방법이 없으면 프론트가 "로그인 필요"와
    "읽기 전용으로 정상 접속"을 구분 못 한다(/api/whoami가 이 필드로 알려줌)."""
    request.state.user = None
    request.state.can_write = False
    request.state.share_guest = False
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if token:
        conn = get_conn()
        try:
            user = auth.get_session_user(conn, token)
        finally:
            conn.close()
        if user:
            request.state.user = user
            request.state.can_write = True
            return True
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Basic ") and APP_USERNAME and APP_PASSWORD:
        try:
            username, _, password = base64.b64decode(auth_header[6:]).decode("utf-8").partition(":")
        except (ValueError, UnicodeDecodeError):
            username, password = "", ""
        if username and _credentials_match(username, password, APP_USERNAME, APP_PASSWORD):
            request.state.user = {"id": None, "username": APP_USERNAME, "is_owner": True}
            request.state.can_write = True
            return True
    if READ_SHARE_TOKEN:
        shared_token = request.query_params.get("share") or request.cookies.get(SHARE_COOKIE_NAME)
        if shared_token and secrets.compare_digest(
            shared_token.encode("utf-8"), READ_SHARE_TOKEN.encode("utf-8")
        ):
            request.state.can_write = False
            request.state.share_guest = True
            return True
    return False


class SessionAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        path = request.url.path
        if path in {"/api/fitness/sync", "/api/fitness/shortcut-sync"}:
            # iPhone 보조 앱은 브라우저 쿠키 대신 이 라우트 안에서 검증하는
            # 전용 HealthKit 동기화 토큰만 사용한다.
            request.state.user = None
            request.state.can_write = False
            request.state.share_guest = False
            return await call_next(request)
        if path.startswith("/api/worker/"):
            request.state.user = None
            request.state.can_write = True  # 워커는 WORKER_TOKEN으로 각 라우트에서 별도 인증
            request.state.share_guest = False
            return await call_next(request)
        if not APP_USERNAME or not APP_PASSWORD:
            request.state.user = None
            request.state.can_write = True  # 로컬 개발용 — 둘 다 미설정 시 인증 생략
            request.state.share_guest = False
            return await call_next(request)
        allowed = _resolve_auth(request)
        is_public = path in PUBLIC_PATHS or path.startswith("/static/")
        if not (allowed or is_public):
            if path == "/api/sunzi/historical-case/start":
                verse = request.query_params.get("verse", "")
                if verse.isdigit() and 1 <= int(verse) <= 99:
                    return RedirectResponse(f"/?sunzi_backfill={int(verse)}", status_code=303)
            return JSONResponse(status_code=401, content={"detail": "로그인이 필요합니다"})
        response = await call_next(request)
        share_param = request.query_params.get("share")
        if READ_SHARE_TOKEN and share_param and not request.state.user and secrets.compare_digest(
            share_param.encode("utf-8"), READ_SHARE_TOKEN.encode("utf-8")
        ):
            response.set_cookie(
                SHARE_COOKIE_NAME, READ_SHARE_TOKEN,
                max_age=SHARE_COOKIE_MAX_AGE, httponly=True, samesite="lax",
            )
        return response


class NoCacheStaticMiddleware(BaseHTTPMiddleware):
    """★ 2026-08-26 실측 문제: FastAPI StaticFiles가 Cache-Control 헤더를 아예
    안 보내서, 브라우저가 자체 판단(Last-Modified 기준 휴리스틱)으로 정적
    파일(특히 chat.js)을 몇 분씩 재검증 없이 그대로 재사용했다 — Cloudflare
    캐시를 퍼지하고 우회 규칙까지 만들어도 브라우저 로컬 캐시는 그걸로 전혀
    안 고쳐졌다(서로 다른 계층). /static/·/uploads/ 요청에는 "no-cache"를
    강제해 매번 서버에 재검증(ETag)하게 한다 — 완전히 캐시를 끄는 게
    아니라 "쓰기 전에 항상 물어보라"는 지시라 대역폭 낭비는 크지 않다.

    ★ 2026-09-23: "홈화면이 처음에 들어가면 느리게 나온다" 문의 — 로컬에서는
    ETag 재검증이 몇 ms지만, 실제 네트워크(터널 경유)에서는 파일마다 매번
    왕복이 붙어 체감 지연이 쌓인다. chat.js·style.css 등은 이미 파일을 고칠
    때마다 URL의 `?v=` 값을 같이 올리는 관례가 있으므로(수정 즉시 새 URL =
    캐시 무효화가 저절로 보장됨) `v=` 쿼리가 붙은 요청만 1년 불변 캐시로
    바꾼다. `v=` 없는 요청(업로드 파일 등)은 기존처럼 매번 재검증한다."""
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        if request.url.path.startswith(("/static/", "/uploads/", "/shift-alarm/static/", "/audio-editor/static/", "/mp3-player/static/", "/transcriptions/static/", "/memo/static/", "/comfy/static/")):
            if request.query_params.get("v"):
                response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
            else:
                response.headers["Cache-Control"] = "no-cache"
        if request.url.path in {"/career/", "/fitness/", "/terrain-survey/", "/stock-portfolio/"} or request.url.path.startswith(("/career/static/", "/fitness/static/", "/terrain-survey/static/", "/stock-portfolio/static/")):
            # iOS 홈 화면 웹앱은 일반 탭보다 HTML/JS를 오래 보존하는 경우가 있다.
            # 커리어 보드는 소유자 전용이고 파일도 작으므로 매번 최신본을 받는다.
            response.headers["Cache-Control"] = "no-store, max-age=0"
        return response


app = FastAPI(title="나툼 · NaTum")
app.add_middleware(SessionAuthMiddleware)
app.add_middleware(NoCacheStaticMiddleware)
init_db()
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
app.mount("/uploads", StaticFiles(directory=str(UPLOADS_DIR)), name="uploads")


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def _bootstrap_owner():
    """서버가 뜰 때 APP_USERNAME/APP_PASSWORD를 users 테이블의 is_owner=1
    계정으로 만들어둔다(이미 있으면 아무것도 안 함).

    ★ 2026-08-26: 이걸 안 하면 서버 시작 직후 "다른 누군가가 소유자 아이디를
    먼저 가입해서 선점"하는 경쟁 상태가 생긴다 — worker/persona_worker.py의
    파일 정리 승인 게이트는 로그인 세션의 실제 sender 문자열이
    CHATAPP_OWNER_USERNAME과 일치하는지만 보므로, 그 아이디를 다른 사람이
    먼저 계정으로 가지면 그 사람이 "소유자 승인"을 위조할 수 있게 된다.
    서버 시작 시점(첫 요청을 받기도 전)에 동기적으로 미리 만들어두면 이
    경쟁 자체가 없다."""
    if not APP_USERNAME or not APP_PASSWORD:
        return
    conn = get_conn()
    try:
        if conn.execute("SELECT id FROM users WHERE username = ?", (APP_USERNAME,)).fetchone():
            return
        salt, digest = auth.hash_password(APP_PASSWORD)
        conn.execute(
            "INSERT INTO users (username, password_hash, salt, is_owner, created_at) VALUES (?, ?, ?, 1, ?)",
            (APP_USERNAME, digest, salt, _now()),
        )
        conn.commit()
    finally:
        conn.close()


_bootstrap_owner()


def _check_worker_auth(authorization: Optional[str]) -> None:
    if not WORKER_TOKEN:
        return  # 로컬 개발용 — 토큰 미설정 시 인증 생략
    if authorization != f"Bearer {WORKER_TOKEN}":
        raise HTTPException(status_code=401, detail="워커 인증 실패")


def _persona_name_set(conn):
    return {r["name"] for r in conn.execute("SELECT name FROM personas").fetchall()}


# ★ 2026-08-26: "사용자가 자기만의 페르소나를 만들 수 있게 해달라" 요청 —
# Notion 동기화 페르소나(owner_username=NULL)의 1:1 방은 기존처럼 소유자만
# 쓸 수 있고, 사용자가 직접 만든 페르소나(owner_username=계정)의 1:1 방은
# 그 계정 본인 + 소유자만 쓸 수 있다.
def _can_access_persona_room(owner_username, requesting_username, is_owner_request):
    if is_owner_request:
        return True
    return owner_username is not None and owner_username == requesting_username


# ★ "처음 일반 사용자 입장에서 프로그램개발그룹이랑 병법가그룹이 보이는데,
# 처음 사용자한테는 아무 채팅방도 안 보이는 게 맞는 것 같다" 요청
# (2026-08-28). Notion 페르소나의 group_name으로 자동 생성되는 "그룹
# 회의방"은 기본적으로 관리자가 큐레이션한 콘텐츠라 기본 접근은 전체
# 관리자로 제한한다.
def _is_notion_group_room(conn, room_id):
    return bool(conn.execute(
        "SELECT 1 FROM personas WHERE group_name = ? LIMIT 1", (room_id,)
    ).fetchone())


# ★ 같은 날 후속 요청: "그룹 회의방에서 사람 초대하려는데 왜 일반 사용자는
# 목록에 없지" — 관리자만 보이게 막고 나니, 관리자가 그 방에 특정 사람을
# 데려오고 싶어도 방법이 없었다. 커스텀 방과 똑같이 room_user_invites를
# 재사용해서(스키마에 room_id에 대한 FK 제약이 없어 커스텀 방이 아닌
# room_id로도 그냥 저장된다) 관리자가 초대한 사람은 그 그룹 회의방에도
# 들어올 수 있게 한다 — 방 "주인"이 없는 콘텐츠라 초대는 관리자만 할 수
# 있다(커스텀 방처럼 "방 주인"이 따로 초대하는 경우가 없음).
def _group_room_allowed(conn, room_id, username, is_owner_request):
    if is_owner_request:
        return True
    if not username:
        return False
    return bool(conn.execute(
        "SELECT 1 FROM room_user_invites WHERE room_id = ? AND username = ?", (room_id, username)
    ).fetchone())


PERSONA_NAME_RE = re.compile(r"^[A-Za-z0-9_ 가-힣]{1,20}$")
USER_PERSONA_DESC_MAX_CHARS = 2000


def _build_user_persona_prompt(name, owner_username, description):
    return (
        f'당신은 "{name}"이라는 이름의 가상 페르소나입니다. 사용자 계정 "{owner_username}"이(가) '
        "직접 만든 캐릭터입니다. 아래는 그 사용자가 적어준 설정입니다 — 이 설정에 따라 자연스럽게 "
        "대화하세요(설정에 명시되지 않은 사실을 지어내 단정하지 말고, 대화 중 자연스럽게 드러나는 "
        "성격·반응 정도만 보완하세요).\n\n"
        f"--- 캐릭터 설정 ---\n{description}"
    )


def _with_sender_type(rows, persona_names, persona_avatars=None, human_profiles=None):
    """메시지 발신자 종류와 프로필 이미지·표시 이름을 함께 내려준다.
    페르소나는 avatar_url만(이름은 프론트 displayName()이 "(가상)"을 붙여
    표시), 사람은 avatar_url·display_name 둘 다(2026-08-28 — "자기 이름·
    프로필사진 바꿀 수 있게 해달라" 요청. display_name이 없으면 프론트가
    sender(아이디)로 대체 표시)."""
    persona_avatars = persona_avatars or {}
    human_profiles = human_profiles or {}
    result = []
    for r in rows:
        sender = r["sender"]
        is_persona = sender in persona_names
        human = human_profiles.get(sender, {}) if not is_persona else {}
        result.append({
            **dict(r),
            "is_persona": is_persona,
            "avatar_url": persona_avatars.get(sender) if is_persona else human.get("avatar_url"),
            "display_name": human.get("display_name"),
            # ★ 2026-08-28: row에 is_system 컬럼이 없는 옛 쿼리에서도 안전하게
            # 기본값 False로 떨어지게 dict.get 사용(SELECT에 안 넣은 곳도 있음).
            "is_system": bool(dict(r).get("is_system", 0)),
        })
    return result


def _human_profiles(conn):
    return {
        r["username"]: {"display_name": r["display_name"], "avatar_url": r["avatar_url"]}
        for r in conn.execute("SELECT username, display_name, avatar_url FROM users").fetchall()
    }


def _insert_system_notice(conn, room_id, content):
    """★ "초대가 되면 그 톡방에 '누가 초대되었습니다'라고 구분선 같은 걸
    만들어달라" 요청(2026-08-28) — 사람/페르소나 발화가 아닌 서버 알림
    메시지를 남긴다. sender는 화면에 안 쓰이지만(프론트가 is_system이면
    content만 가운데 구분선으로 그림) 그래도 사람이 알아볼 수 있는 값을
    넣어둔다."""
    conn.execute(
        "INSERT INTO messages (room_id, sender, content, created_at, is_system) VALUES (?, 'system', ?, ?, 1)",
        (room_id, content, _now()),
    )


REACTION_EMOJIS = {"❤️", "👍", "✅", "😄", "😮", "😢", "🫤"}
# ★ 2026-09-12: 이 두 반응은 장식용이 아니라 페르소나에게 실제로 전달된다 —
# 👍는 "그 말이 아주 좋았다"는 뜻으로 짧은 첨언을 유도하고 앞으로 비슷한
# 말을 더 하도록, 🫤는 "그 말은 별로였다"는 뜻으로 비슷한 말을 피하도록
# persona_feedback에 쌓인다(_maybe_queue_reaction_feedback).
LEARNED_REACTION_EMOJIS = {"👍", "🫤"}


def _message_reactions(conn, message_ids, username):
    """메시지별 반응 수와 현재 사용자의 선택 여부를 한 번의 쿼리로 묶는다."""
    if not message_ids:
        return {}
    marks = ",".join("?" for _ in message_ids)
    rows = conn.execute(
        f"""SELECT message_id, emoji, COUNT(*) AS reaction_count,
                   MAX(CASE WHEN username = ? THEN 1 ELSE 0 END) AS mine
              FROM message_reactions
             WHERE message_id IN ({marks})
             GROUP BY message_id, emoji
             ORDER BY MIN(created_at)""",
        (username, *message_ids),
    ).fetchall()
    result = {}
    for row in rows:
        result.setdefault(row["message_id"], []).append(
            {"emoji": row["emoji"], "count": row["reaction_count"], "mine": bool(row["mine"])}
        )
    return result


def _maybe_queue_reaction_feedback(conn, message_id, room_id, emoji, reacted_by):
    """👍/🫤가 페르소나 메시지에 새로 달렸을 때만 발동한다(★ 2026-09-12).

    ①persona_feedback에 발췌를 남겨 이 페르소나의 향후 모든 턴(build_prompt)에
    "이런 식으로 말했을 때 좋았다/별로였다" 노트로 누적 반영되게 하고,
    ②지금 이 메시지에 짧게 반응하는 전용 pending_turn 하나를 큐에 넣는다
    (워커가 reaction_emoji 유무로 일반 대화와 구분해 처리 — persona_worker.py
    참고). 페르소나가 아닌 사람 메시지에는 아무 일도 하지 않는다."""
    if emoji not in LEARNED_REACTION_EMOJIS:
        return
    message = conn.execute(
        "SELECT sender, content FROM messages WHERE id = ?", (message_id,)
    ).fetchone()
    if not message:
        return
    sender = message["sender"]
    is_persona = conn.execute("SELECT 1 FROM personas WHERE name = ?", (sender,)).fetchone()
    if not is_persona:
        return
    now = _now()
    excerpt = (message["content"] or "")[:300]
    conn.execute(
        """INSERT OR IGNORE INTO persona_feedback
               (persona_name, room_id, message_id, emoji, excerpt, reacted_by, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (sender, room_id, message_id, emoji, excerpt, reacted_by, now),
    )
    already_queued = conn.execute(
        """SELECT 1 FROM pending_turns
            WHERE source_message_id = ? AND persona_name = ? AND reaction_emoji = ?
              AND status IN ('pending', 'processing')""",
        (message_id, sender, emoji),
    ).fetchone()
    if already_queued:
        return
    conn.execute(
        """INSERT INTO pending_turns (persona_name, room_id, status, created_at, source_message_id, reaction_emoji)
           VALUES (?, ?, 'pending', ?, ?, ?)""",
        (sender, room_id, now, message_id, emoji),
    )


@app.get("/")
def index():
    return FileResponse(str(BASE_DIR / "static" / "index.html"))


@app.get("/chat")
@app.get("/chat/")
def chat_index():
    """툴파챗 PWA가 나툼 홈과 다른 시작 URL을 갖도록 하는 전용 진입점."""
    return FileResponse(
        str(BASE_DIR / "static" / "index.html"),
        headers={"Cache-Control": "no-cache"},
    )


@app.get("/manifest.json")
def pwa_manifest():
    """브라우저의 PWA 설치 검사에서 사용하는 루트 manifest."""
    return FileResponse(
        str(BASE_DIR / "static" / "manifest.json"),
        media_type="application/manifest+json",
        headers={"Cache-Control": "no-cache"},
    )


@app.get("/career")
def career_redirect():
    return RedirectResponse("/career/", status_code=307)


@app.get("/fitness")
def fitness_redirect():
    return RedirectResponse("/fitness/", status_code=307)


@app.get("/stock-portfolio")
def stock_portfolio_redirect():
    return RedirectResponse("/stock-portfolio/", status_code=307)


@app.get("/stock-portfolio/")
def stock_portfolio_dashboard(request: Request):
    _require_signed_in_user(request)
    return FileResponse(str(STOCK_PORTFOLIO_WEB_DIR / "index.html"), headers={"Cache-Control": "no-store"})


@app.get("/stock-portfolio/static/{filename}")
def stock_portfolio_static(filename: str, request: Request):
    _require_signed_in_user(request)
    if filename not in {"style.css", "app.js", "manifest.webmanifest"}:
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다")
    return FileResponse(str(STOCK_PORTFOLIO_WEB_DIR / filename), headers={"Cache-Control": "no-store"})


@app.get("/fitness/")
def fitness_dashboard(request: Request):
    _require_signed_in_user(request)
    return FileResponse(str(FITNESS_WEB_DIR / "index.html"))


@app.get("/fitness/static/{filename}")
def fitness_static(filename: str, request: Request):
    _require_signed_in_user(request)
    if filename not in {"style.css", "playlist.css", "app.js", "manifest.webmanifest"}:
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다")
    return FileResponse(str(FITNESS_WEB_DIR / filename))


@app.get("/terrain-survey")
def terrain_survey_redirect():
    return RedirectResponse("/terrain-survey/", status_code=307)


@app.get("/terrain-survey/")
def terrain_survey_dashboard(request: Request):
    _require_signed_in_user(request)
    return FileResponse(str(TERRAIN_SURVEY_WEB_DIR / "index.html"), headers={"Cache-Control": "no-store"})


@app.get("/terrain-survey/static/{filename}")
def terrain_survey_static(filename: str, request: Request):
    _require_signed_in_user(request)
    if filename not in {"style.css", "skills.css", "app.js", "manifest.webmanifest"}:
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다")
    return FileResponse(str(TERRAIN_SURVEY_WEB_DIR / filename), headers={"Cache-Control": "no-store"})


@app.get("/career/")
def career_dashboard(request: Request):
    _require_signed_in_user(request)
    return FileResponse(str(CAREER_WEB_DIR / "index.html"))


@app.get("/career/static/{filename}")
def career_static(filename: str, request: Request):
    _require_signed_in_user(request)
    allowed = {"style.css", "app.js", "manifest.webmanifest"}
    if filename not in allowed:
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다")
    return FileResponse(str(CAREER_WEB_DIR / filename))


@app.get("/vocabulary")
def vocabulary_redirect():
    return RedirectResponse("/vocabulary/", status_code=307)


@app.get("/vocabulary/")
def vocabulary_dashboard(request: Request):
    _require_signed_in_user(request)
    return FileResponse(str(VOCABULARY_WEB_DIR / "index.html"))


@app.get("/vocabulary/static/{filename}")
def vocabulary_static(filename: str, request: Request):
    _require_signed_in_user(request)
    if filename not in {"style.css", "practice.css", "app.js", "manifest.webmanifest"}:
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다")
    return FileResponse(str(VOCABULARY_WEB_DIR / filename))


@app.get("/memo")
def memo_redirect():
    return RedirectResponse("/memo/", status_code=307)


@app.get("/memo/")
def memo_dashboard(request: Request):
    _require_signed_in_user(request)
    return FileResponse(str(MEMO_WEB_DIR / "index.html"))


@app.get("/memo/chat-map/")
def memo_chat_map(request: Request):
    _require_signed_in_user(request)
    return FileResponse(str(MEMO_WEB_DIR / "chat-map.html"))


@app.get("/memo/static/{filename}")
def memo_static(filename: str, request: Request):
    _require_signed_in_user(request)
    if filename not in {"style.css", "colors.css", "tools.css", "voice.css", "app.js", "chat-map.css", "chat-map.js", "manifest.webmanifest", "apple-touch-icon.png", "icon-192.png", "icon-512.png"}:
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다")
    return FileResponse(str(MEMO_WEB_DIR / filename))


@app.get("/comfy")
def comfy_workspace_redirect():
    return RedirectResponse("/comfy/", status_code=307)


@app.get("/comfy/")
def comfy_workspace(request: Request):
    _require_owner(request)
    return FileResponse(str(COMFY_WEB_DIR / "index.html"))


@app.get("/comfy/static/{filename}")
def comfy_workspace_static(filename: str, request: Request):
    _require_owner(request)
    if filename not in {"style.css", "quality.css", "app.js", "manifest.webmanifest"}:
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다")
    return FileResponse(str(COMFY_WEB_DIR / filename))


@app.get("/audio-editor")
def audio_editor_redirect():
    return RedirectResponse("/audio-editor/", status_code=307)


@app.get("/transcriptions")
def transcription_redirect():
    return RedirectResponse("/transcriptions/", status_code=307)


@app.get("/transcriptions/")
def transcription_dashboard(request: Request):
    _require_owner(request)
    return FileResponse(str(TRANSCRIPTION_WEB_DIR / "index.html"))


@app.get("/transcriptions/static/{filename}")
def transcription_static(filename: str, request: Request):
    _require_owner(request)
    if filename not in {"style.css", "quality.css", "app.js", "manifest.webmanifest"}:
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다")
    return FileResponse(str(TRANSCRIPTION_WEB_DIR / filename))


def _start_transcription_worker(*arguments: str) -> None:
    script = BASE_DIR / "scripts" / "transcribe_recordings.py"
    log_dir = transcriptions.DATA_DIR
    log_dir.mkdir(parents=True, exist_ok=True)
    log = (log_dir / "worker.log").open("ab")
    try:
        subprocess.Popen(
            [sys.executable, str(script), *arguments],
            cwd=str(BASE_DIR), stdout=log, stderr=subprocess.STDOUT, start_new_session=True,
        )
    finally:
        log.close()


@app.get("/api/transcriptions")
def transcription_jobs(request: Request):
    _require_owner(request)
    jobs = transcriptions.list_jobs()
    return {
        "items": jobs,
        "summary": {
            "total": len(jobs),
            "complete": sum(item.get("status") == "complete" for item in jobs),
            "processing": sum(item.get("status") in {"queued", "processing"} for item in jobs),
            "failed": sum(item.get("status") == "failed" for item in jobs),
        },
    }


@app.get("/api/transcriptions/{recording_id}")
def transcription_detail(recording_id: str, request: Request):
    _require_owner(request)
    try:
        path = transcriptions.job_path(recording_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="녹음을 찾을 수 없습니다") from exc
    data = transcriptions.read_job(path)
    if not data:
        raise HTTPException(status_code=404, detail="녹음을 찾을 수 없습니다")
    if data.get("status") == "complete" and data.get("text") and not isinstance(data.get("summary"), dict):
        data["summary"] = transcription_summary.summarize(str(data.get("text") or ""))
        transcriptions.write_job(data)
    return transcriptions.public_job(data, include_text=True)


@app.get("/api/transcriptions/{recording_id}/audio")
def transcription_audio(recording_id: str, request: Request):
    """소유자에게만 원본 녹음을 스트리밍한다.

    브라우저의 Range 요청은 FileResponse가 처리하므로 긴 녹음도 전체 파일을
    내려받지 않고 선택한 대사의 타임코드로 바로 이동할 수 있다.
    """
    _require_owner(request)
    try:
        path = transcriptions.job_path(recording_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="녹음을 찾을 수 없습니다") from exc
    data = transcriptions.read_job(path)
    source = Path(str(data.get("source_path") or "")).expanduser()
    if not data or not source.is_file():
        raise HTTPException(status_code=404, detail="원본 녹음 파일을 찾을 수 없습니다")
    media_types = {
        ".m4a": "audio/mp4", ".mp3": "audio/mpeg", ".wav": "audio/wav",
        ".aac": "audio/aac", ".flac": "audio/flac",
    }
    media_type = media_types.get(source.suffix.lower())
    if not media_type:
        raise HTTPException(status_code=415, detail="지원하지 않는 녹음 형식입니다")
    return FileResponse(source, media_type=media_type, filename=source.name)


@app.post("/api/transcriptions/import-downloads")
def transcription_import_downloads(request: Request):
    _require_owner(request)
    _start_transcription_worker("--downloads")
    return {"ok": True}


@app.post("/api/transcriptions/retranscribe-all")
def transcription_retranscribe_all(request: Request):
    _require_owner(request)
    count = 0
    for public in transcriptions.list_jobs():
        path = transcriptions.job_path(str(public.get("id") or ""))
        data = transcriptions.read_job(path)
        source = Path(str(data.get("source_path") or ""))
        if not source.is_file():
            continue
        data.update(status="queued", progress=0, error="", updated_at=_now())
        transcriptions.write_job(data)
        count += 1
    if count:
        _start_transcription_worker("--downloads")
    return {"ok": True, "count": count}


@app.post("/api/transcriptions/{recording_id}/retry")
def transcription_retry(recording_id: str, request: Request):
    _require_owner(request)
    try:
        path = transcriptions.job_path(recording_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="녹음을 찾을 수 없습니다") from exc
    data = transcriptions.read_job(path)
    source = Path(str(data.get("source_path") or ""))
    if not data or not source.is_file():
        raise HTTPException(status_code=404, detail="원본 녹음 파일을 찾을 수 없습니다")
    data.update(status="queued", progress=0, error="", updated_at=_now())
    transcriptions.write_job(data)
    _start_transcription_worker(str(source))
    return {"ok": True}


@app.post("/api/transcriptions/upload")
async def transcription_upload(request: Request, file: UploadFile = File(...)):
    _require_owner(request)
    original_name = Path(file.filename or "recording.m4a").name
    suffix = Path(original_name).suffix.lower()
    if suffix not in {".m4a", ".mp3", ".wav", ".aac", ".flac"}:
        raise HTTPException(status_code=422, detail="M4A·MP3·WAV·AAC·FLAC 파일만 지원합니다")
    transcriptions.UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    destination = transcriptions.UPLOADS_DIR / f"{uuid.uuid4().hex}_{original_name}"
    size = 0
    try:
        with destination.open("wb") as handle:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > 500 * 1024 * 1024:
                    raise HTTPException(status_code=413, detail="녹음은 최대 500MB까지 올릴 수 있습니다")
                handle.write(chunk)
        if size < 128:
            raise HTTPException(status_code=422, detail="비어 있거나 손상된 녹음입니다")
        _start_transcription_worker(str(destination))
        return {"ok": True, "name": original_name}
    except Exception:
        destination.unlink(missing_ok=True)
        raise


@app.get("/sql-lab")
def sql_lab_redirect():
    return RedirectResponse("/sql-lab/", status_code=307)


@app.get("/sql-lab/")
def sql_lab_dashboard(request: Request):
    _require_signed_in_user(request)
    return FileResponse(str(SQL_LAB_WEB_DIR / "index.html"))


@app.get("/sql-lab/static/{filename}")
def sql_lab_static(filename: str, request: Request):
    _require_signed_in_user(request)
    if filename not in {"style.css", "app.js", "manifest.webmanifest"}:
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다")
    return FileResponse(str(SQL_LAB_WEB_DIR / filename))


@app.get("/audio-editor/")
def audio_editor_dashboard(request: Request):
    _require_signed_in_user(request)
    return FileResponse(str(AUDIO_EDITOR_WEB_DIR / "index.html"))


@app.get("/audio-editor/static/{filename}")
def audio_editor_static(filename: str, request: Request):
    _require_signed_in_user(request)
    if filename not in {"style.css", "playlist.css", "app.js", "manifest.webmanifest"}:
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다")
    return FileResponse(str(AUDIO_EDITOR_WEB_DIR / filename))


@app.post("/api/audio-editor/export")
async def export_edited_audio(
    request: Request,
    file: UploadFile = File(...),
    cuts: str = Form("[]"),
):
    """로그인 사용자의 MP3에서 지정 구간을 제외하고 새 MP3를 반환한다."""
    _require_signed_in_user(request)
    original_name = Path(file.filename or "audio.mp3").name
    if Path(original_name).suffix.lower() != ".mp3":
        raise HTTPException(status_code=422, detail="MP3 파일만 편집할 수 있습니다")
    try:
        parsed_cuts = json.loads(cuts)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=422, detail="삭제 구간 정보가 올바르지 않습니다") from exc
    if not isinstance(parsed_cuts, list) or len(parsed_cuts) > 100:
        raise HTTPException(status_code=422, detail="삭제 구간은 최대 100개까지 지정할 수 있습니다")

    work_root = Path(os.path.expanduser("~/.tulpachat/audio_editor"))
    work_root.mkdir(parents=True, exist_ok=True)
    job_dir = Path(tempfile.mkdtemp(prefix="edit-", dir=work_root))
    source = job_dir / "source.mp3"
    output = job_dir / "edited.mp3"
    size = 0
    try:
        with source.open("wb") as destination:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > 250 * 1024 * 1024:
                    raise HTTPException(status_code=413, detail="MP3는 최대 250MB까지 편집할 수 있습니다")
                destination.write(chunk)
        if size < 128:
            raise HTTPException(status_code=422, detail="비어 있거나 손상된 MP3입니다")
        ffprobe = shutil.which("ffprobe")
        ffmpeg = shutil.which("ffmpeg")
        if not ffprobe or not ffmpeg:
            raise HTTPException(status_code=503, detail="오디오 편집기를 실행할 수 없습니다")
        probe = subprocess.run(
            [ffprobe, "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(source)],
            capture_output=True, text=True, timeout=30,
        )
        try:
            duration = float(probe.stdout.strip()) if probe.returncode == 0 else 0
        except ValueError:
            duration = 0
        if duration <= 0 or duration > 8 * 60 * 60:
            raise HTTPException(status_code=422, detail="재생 시간을 확인할 수 없거나 8시간을 초과한 MP3입니다")
        segments = audio_editor.kept_segments(parsed_cuts, duration)
        if not segments:
            raise HTTPException(status_code=422, detail="전체 오디오를 삭제할 수는 없습니다")
        command = [
            ffmpeg, "-y", "-v", "error", "-i", str(source),
            "-filter_complex", audio_editor.ffmpeg_filter(segments),
            "-map", "[out]", "-codec:a", "libmp3lame", "-q:a", "2", str(output),
        ]
        encoded = subprocess.run(command, capture_output=True, text=True, timeout=300)
        if encoded.returncode != 0 or not output.is_file():
            raise HTTPException(status_code=422, detail="MP3를 편집하지 못했습니다. 파일을 다시 확인해주세요")
        download_name = f"{Path(original_name).stem}-편집본.mp3"
        return FileResponse(
            str(output), media_type="audio/mpeg", filename=download_name,
            background=BackgroundTask(shutil.rmtree, job_dir, ignore_errors=True),
        )
    except HTTPException:
        shutil.rmtree(job_dir, ignore_errors=True)
        raise
    except (OSError, subprocess.TimeoutExpired) as exc:
        shutil.rmtree(job_dir, ignore_errors=True)
        raise HTTPException(status_code=500, detail="오디오 편집 중 오류가 발생했습니다") from exc


@app.get("/mp3-player")
def mp3_player_redirect():
    return RedirectResponse("/mp3-player/", status_code=307)


@app.get("/mp3-player/")
def mp3_player_dashboard(request: Request):
    _require_signed_in_user(request)
    return FileResponse(str(MP3_PLAYER_WEB_DIR / "index.html"))


@app.get("/mp3-player/static/{filename}")
def mp3_player_static(filename: str, request: Request):
    _require_signed_in_user(request)
    if filename not in {"style.css", "playlist.css", "recommendations.css", "app.js", "manifest.webmanifest", "player-controls-v1.png", "favorite-heart-v1.png", "apple-touch-icon.png", "icon-192.png", "icon-512.png"}:
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다")
    path = MP3_PLAYER_WEB_DIR / filename
    if filename in {"player-controls-v1.png", "favorite-heart-v1.png"}:
        path = MP3_PLAYER_WEB_DIR / "assets" / filename
    return FileResponse(str(path))


def _open_lrc_progress_terminal(job_dir: Path, filename: str) -> None:
    """새 백그라운드 작업의 로그를 사용자가 볼 수 있는 Terminal 창으로 연다."""
    log_path = job_dir / "progress.log"
    monitor = job_dir / "LRC 진행상황.command"
    opened_marker = job_dir / ".progress-terminal-opened"
    try:
        marker_fd = os.open(opened_marker, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(marker_fd)
    except FileExistsError:
        # 서버가 재시작해 같은 영구 작업을 복구해도 로그 창은 한 번만 연다.
        return
    safe_title = Path(filename).name.replace("\n", " ")
    status_path = job_dir / "status.json"
    monitor.write_text(
        "#!/bin/zsh\n"
        "clear\n"
        f"echo '🎵 LRC 생성: {safe_title.replace(chr(39), chr(39) + chr(92) + chr(39) + chr(39))}'\n"
        "echo '완료 또는 실패 상태를 확인하면 이 창은 자동으로 종료됩니다.'\n"
        f"tail -n 30 -f '{str(log_path).replace(chr(39), chr(39) + chr(92) + chr(39) + chr(39))}' &\n"
        "TAIL_PID=$!\n"
        "finish_monitor() { kill $TAIL_PID 2>/dev/null; wait $TAIL_PID 2>/dev/null; }\n"
        "trap finish_monitor EXIT INT TERM\n"
        "while true; do\n"
        f"  STATUS=$(/usr/bin/sed -n 's/.*\"status\": \"\\([^\"]*\\)\".*/\\1/p' '{str(status_path).replace(chr(39), chr(39) + chr(92) + chr(39) + chr(39))}' | /usr/bin/head -n 1)\n"
        "  if [[ \"$STATUS\" == complete || \"$STATUS\" == failed ]]; then break; fi\n"
        "  sleep 2\n"
        "done\n"
        "finish_monitor\n"
        "trap - EXIT INT TERM\n"
        "echo\n"
        "if [[ \"$STATUS\" == complete ]]; then echo '✅ LRC 생성과 적용이 완료됐습니다.'; else echo '❌ LRC 생성이 실패했습니다. 앱에서 오류 내용을 확인하세요.'; fi\n"
        "echo '5초 후 이 진행창을 닫습니다.'\n"
        "sleep 5\n",
        encoding="utf-8",
    )
    monitor.chmod(0o700)
    try:
        subprocess.Popen(["/usr/bin/open", "-a", "Terminal", str(monitor)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        opened_marker.unlink(missing_ok=True)
        pass


def _audio_duration_seconds(source: Path) -> float:
    ffprobe = next((candidate for candidate in (
        "/opt/homebrew/bin/ffprobe", "/usr/local/bin/ffprobe", shutil.which("ffprobe"),
    ) if candidate and Path(candidate).is_file()), None)
    if not ffprobe:
        return 0.0
    try:
        result = subprocess.run(
            [ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(source)],
            capture_output=True, text=True, timeout=30,
        )
        return max(0.0, float(result.stdout.strip())) if result.returncode == 0 else 0.0
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return 0.0


async def _generate_lrc_from_mp3_source(source: Path, job_dir: Path, job_id: str | None = None):
    """디스크에 준비된 MP3를 변환·전사해 LRC 응답을 만든다."""
    whisper = Path("/opt/homebrew/bin/whisper-cli")
    model_candidates = [
        Path("/opt/homebrew/share/whisper-cpp/models/ggml-medium.bin"),
        Path("/opt/homebrew/share/whisper-cpp/models/ggml-small.bin"),
    ]
    model = next((candidate for candidate in model_candidates if candidate.is_file()), None)
    ffmpeg = next((candidate for candidate in (
        "/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg", shutil.which("ffmpeg"),
    ) if candidate and Path(candidate).is_file()), None)
    if not whisper.is_file() or model is None or not ffmpeg:
        raise HTTPException(status_code=503, detail="Mac의 로컬 Whisper 또는 FFmpeg가 준비되지 않았습니다")

    chunk_seconds = 600
    chunks_dir = job_dir / "chunks"
    progress_log = job_dir / "progress.log"
    try:
        if source.stat().st_size < 128:
            raise HTTPException(status_code=422, detail="비어 있거나 손상된 MP3입니다")
        duration = _audio_duration_seconds(source)
        if not duration:
            raise HTTPException(status_code=422, detail="MP3 재생 시간을 확인하지 못했습니다")
        chunks_dir.mkdir(parents=True, exist_ok=True)
        if job_id:
            _write_lrc_job(job_id, status="running", stage="1/3 · 음원 분할", percent=10, message="MP3를 10분 단위 작업 조각으로 나누고 있습니다", audio_duration=duration)
        progress_log.write_text(f"[1/3] MP3를 10분 단위로 분할 시작 · 총 {duration / 60:.1f}분\n", encoding="utf-8")
        wave_chunks = sorted(chunks_dir.glob("chunk_*.wav"))
        if not wave_chunks:
            converted = await asyncio.to_thread(
                subprocess.run,
                [ffmpeg, "-y", "-v", "error", "-i", str(source), "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le",
                 "-f", "segment", "-segment_time", str(chunk_seconds), "-reset_timestamps", "1", str(chunks_dir / "chunk_%03d.wav")],
                capture_output=True, text=True, timeout=600,
            )
            wave_chunks = sorted(chunks_dir.glob("chunk_*.wav"))
            if converted.returncode != 0 or not wave_chunks:
                raise HTTPException(status_code=422, detail="MP3를 작업 조각으로 나누지 못했습니다")
        total_chunks = len(wave_chunks)
        combined_lines = ["[by:툴파챗 로컬 Whisper]"]
        transcription_started = time.monotonic()
        with progress_log.open("a", encoding="utf-8") as log:
            log.write(f"[2/3] Whisper 조각별 전사 시작 · {total_chunks}개 조각\n")
            for index, wave in enumerate(wave_chunks):
                offset = index * chunk_seconds
                chunk_lrc = chunks_dir / f"chunk_{index:03d}.lrc"
                output_prefix = chunks_dir / f"lyrics_{index:03d}"
                if chunk_lrc.is_file():
                    combined_lines.extend(line for line in chunk_lrc.read_text(encoding="utf-8").splitlines() if line.strip())
                    log.write(f"[{index + 1}/{total_chunks}] 완료된 조각 재사용\n")
                    log.flush()
                    continue
                chunk_marker = f"--- LRC CHUNK {index + 1}/{total_chunks} ---"
                log.write(f"{chunk_marker}\n[{index + 1}/{total_chunks}] {offset / 60:.0f}분~{min(duration, offset + chunk_seconds) / 60:.0f}분 전사 시작\n")
                log.flush()
                if job_id:
                    completed_audio = min(duration, offset)
                    analysis_percent = round(completed_audio / duration * 100)
                    _write_lrc_job(
                        job_id, status="running", stage=f"2/3 · Whisper 전사 {index + 1}/{total_chunks}",
                        percent=min(92, 20 + round(analysis_percent * 0.72)),
                        message=f"{index + 1}번째 조각 처리 중 · {completed_audio / 60:.1f}/{duration / 60:.1f}분",
                        processed_seconds=completed_audio, audio_duration=duration,
                    )
                async def transcribe_piece(piece: Path, prefix: Path, piece_offset: float, timeout: int, marker: str) -> str:
                    process = subprocess.Popen(
                        [str(whisper), "-ng", "-m", str(model), "-f", str(piece), "-l", "auto", "-sns", "-osrt", "-of", str(prefix)],
                        stdout=log, stderr=subprocess.STDOUT, text=True,
                    )
                    started = time.monotonic()
                    last_progress_at = started
                    last_stamp = ""
                    while process.poll() is None:
                        elapsed_piece = time.monotonic() - started
                        await asyncio.sleep(1.5)
                        try:
                            live_text = progress_log.read_text(encoding="utf-8", errors="ignore").rsplit(marker, 1)[-1]
                            stamps = re.findall(r"\[(\d{2}):(\d{2}):(\d{2}(?:\.\d+)?)\s*-->", live_text)
                            stamp = ":".join(stamps[-1]) if stamps else ""
                            if stamp and stamp != last_stamp:
                                last_stamp = stamp
                                last_progress_at = time.monotonic()
                                if job_id:
                                    hours, minutes, seconds = stamps[-1]
                                    within_piece = int(hours) * 3600 + int(minutes) * 60 + float(seconds)
                                    processed = min(duration, piece_offset + within_piece)
                                    analysis_percent = min(99, max(0, round(processed / duration * 100)))
                                    overall = min(92, 20 + round(analysis_percent * 0.72))
                                    elapsed_total = max(1.0, time.monotonic() - transcription_started)
                                    speed = processed / elapsed_total
                                    remaining = max(0, round((duration - processed) / speed)) if speed > 0 and processed >= 15 else None
                                    expected_at = (
                                        (datetime.datetime.now().astimezone() + datetime.timedelta(seconds=remaining)).isoformat()
                                        if remaining is not None else None
                                    )
                                    _write_lrc_job(
                                        job_id, status="running", stage=f"2/3 · Whisper 전사 {index + 1}/{total_chunks}",
                                        percent=overall,
                                        message=f"{analysis_percent}% 분석 · {processed / 60:.1f}/{duration / 60:.1f}분",
                                        processed_seconds=processed, audio_duration=duration,
                                        estimated_remaining_seconds=remaining, estimated_completion_at=expected_at,
                                    )
                            # Whisper가 잘못 감지한 문자 하나를 끝없이 출력하는 경우를
                            # 제한 시간까지 기다리지 않고 해당 조각만 다시 나눈다.
                            spoken = "".join(re.findall(r"\]\s*([^\n]+)", live_text))
                            compact = re.sub(r"\s+", "", spoken)
                            if len(compact) >= 120:
                                counts = collections.Counter(compact)
                                _, dominant = counts.most_common(1)[0]
                                if dominant >= 80 and dominant / len(compact) >= 0.55:
                                    process.kill()
                                    process.wait(timeout=10)
                                    raise RuntimeError("비정상 반복 출력")
                            if elapsed_piece > timeout or (last_stamp and time.monotonic() - last_progress_at > 480):
                                process.kill()
                                process.wait(timeout=10)
                                raise RuntimeError("전사 진행 정지")
                        except OSError:
                            if elapsed_piece > timeout:
                                process.kill()
                                process.wait(timeout=10)
                                raise RuntimeError("전사 제한 시간 초과")
                    srt_path = prefix.with_suffix(".srt")
                    if process.returncode != 0 or not srt_path.is_file():
                        raise RuntimeError("Whisper 인식 실패")
                    return mp3_player.srt_to_lrc(
                        srt_path.read_text(encoding="utf-8"), offset_seconds=piece_offset, include_header=False,
                    )

                try:
                    part = await transcribe_piece(wave, output_prefix, offset, 2400, chunk_marker)
                except (RuntimeError, OSError, ValueError) as first_error:
                    retry_dir = chunks_dir / f"retry_{index:03d}"
                    retry_dir.mkdir(parents=True, exist_ok=True)
                    log.write(f"[{index + 1}/{total_chunks}] {first_error} · 5분 조각으로 자동 재분할\n")
                    log.flush()
                    if job_id:
                        _write_lrc_job(
                            job_id, status="running", stage=f"2/3 · 실패 조각 세분화 {index + 1}/{total_chunks}",
                            percent=max(20, 20 + round(offset / duration * 72)),
                            message=f"{index + 1}번째 조각의 언어 오인식·정지를 감지해 5분 단위로 다시 분석합니다",
                            retry_chunk=index + 1,
                        )
                    retry_waves = sorted(retry_dir.glob("piece_*.wav"))
                    if not retry_waves:
                        converted = await asyncio.to_thread(
                            subprocess.run,
                            [ffmpeg, "-y", "-v", "error", "-i", str(wave), "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le",
                             "-f", "segment", "-segment_time", "300", "-reset_timestamps", "1", str(retry_dir / "piece_%03d.wav")],
                            capture_output=True, text=True, timeout=300,
                        )
                        retry_waves = sorted(retry_dir.glob("piece_*.wav"))
                        if converted.returncode != 0 or not retry_waves:
                            raise HTTPException(status_code=422, detail=f"{index + 1}번째 실패 조각을 다시 나누지 못했습니다")
                    pieces = []
                    for retry_index, retry_wave in enumerate(retry_waves):
                        retry_lrc = retry_dir / f"piece_{retry_index:03d}.lrc"
                        if retry_lrc.is_file():
                            pieces.append(retry_lrc.read_text(encoding="utf-8"))
                            continue
                        retry_marker = f"--- LRC RETRY {index + 1}.{retry_index + 1}/{len(retry_waves)} ---"
                        log.write(f"{retry_marker}\n")
                        log.flush()
                        try:
                            retry_part = await transcribe_piece(
                                retry_wave, retry_dir / f"lyrics_{retry_index:03d}", offset + retry_index * 300, 1200, retry_marker,
                            )
                        except (RuntimeError, OSError, ValueError) as exc:
                            raise HTTPException(
                                status_code=504,
                                detail=f"{index + 1}번째 조각의 {retry_index + 1}번째 재분석도 중단됐습니다: {exc}",
                            ) from exc
                        retry_lrc.write_text(retry_part, encoding="utf-8")
                        pieces.append(retry_part)
                    part = "\n".join(piece.strip() for piece in pieces if piece.strip()) + "\n"
                chunk_lrc.write_text(part, encoding="utf-8")
                combined_lines.extend(line for line in part.splitlines() if line.strip())
                log.write(f"[{index + 1}/{total_chunks}] 조각 LRC 저장 완료\n")
                log.flush()
        if job_id:
            _write_lrc_job(job_id, status="running", stage="3/3 · LRC 정리", percent=95, message="인식된 가사를 시간 가사 형식으로 정리하고 있습니다")
        with progress_log.open("a", encoding="utf-8") as log:
            log.write("[3/3] 조각별 LRC를 시간 순서로 합치는 중\n")
        try:
            lrc = "\n".join(combined_lines) + "\n"
            if mp3_player.lyric_line_count(lrc) < 2:
                raise ValueError("노래 가사를 충분히 인식하지 못했습니다. 보컬이 더 선명한 파일이나 직접 받은 LRC를 사용해주세요")
        except (OSError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return Response(content=lrc, media_type="text/plain; charset=utf-8")
    except HTTPException:
        raise
    except subprocess.TimeoutExpired as exc:
        raise HTTPException(status_code=504, detail="음성 변환 제한 시간을 초과했습니다") from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=422, detail="업로드한 MP3를 찾지 못했습니다") from exc
    except OSError as exc:
        raise HTTPException(status_code=500, detail="로컬 가사 생성 중 파일 오류가 발생했습니다") from exc


def _lrc_job_dir(job_id: str) -> Path:
    if not re.fullmatch(r"[0-9a-f]{32}", job_id or ""):
        raise HTTPException(status_code=404, detail="LRC 작업을 찾을 수 없습니다")
    return LRC_JOB_ROOT / job_id


def _read_lrc_job(job_id: str) -> dict[str, Any]:
    path = _lrc_job_dir(job_id) / "status.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=404, detail="LRC 작업을 찾을 수 없습니다") from exc
    return data


def _write_lrc_job(job_id: str, **updates) -> dict[str, Any]:
    directory = _lrc_job_dir(job_id)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "status.json"
    try:
        current = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        current = {"id": job_id}
    current.update(updates, updated_at=datetime.datetime.now().astimezone().isoformat())
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)
    return current


def _public_lrc_job(job: dict[str, Any]) -> dict[str, Any]:
    return {key: job.get(key) for key in (
        "id", "filename", "status", "stage", "percent", "message",
        "created_at", "updated_at", "completed_at", "processed_seconds", "audio_duration",
        "estimated_remaining_seconds", "estimated_completion_at",
        "retry_chunk", "retryable", "reused_chunks",
    )}


def _persist_lrc_to_mp3_library(filename: str, result: Path, source_library: str = "library") -> Path | None:
    target_directory = MP3_FAVORITES_DIR if source_library == "favorites" else MP3_LIBRARY_DIR
    return persist_lrc_to_library(filename, result, target_directory)


def _run_persistent_lrc_job(job_id: str) -> None:
    directory = _lrc_job_dir(job_id)
    source = directory / "source.mp3"
    result = directory / "result.lrc"
    with _lrc_job_run_lock:
        try:
            job = _read_lrc_job(job_id)
            if job.get("status") == "complete" and result.is_file():
                return
            _write_lrc_job(job_id, status="running", stage="작업 시작", percent=10, message="Mac에서 LRC 작업을 시작합니다")
            _open_lrc_progress_terminal(directory, job.get("filename") or "MP3")
            response = asyncio.run(_generate_lrc_from_mp3_source(source, directory, job_id))
            body = bytes(response.body).decode("utf-8")
            result.write_text(body, encoding="utf-8")
            _write_lrc_job(job_id, status="running", stage="3/3 · 저장 및 동기화", percent=98, message="완성된 LRC를 곡과 재생 목록에 적용하고 있습니다")
            store_synced_lrc(job.get("owner") or "", job.get("filename") or "", body)
            library_lrc = _persist_lrc_to_mp3_library(
                job.get("filename") or "",
                result,
                job.get("source_library") or "library",
            )
            now = datetime.datetime.now().astimezone().isoformat()
            _write_lrc_job(
                job_id, status="complete", stage="완료", percent=100,
                message="LRC 생성이 완료됐습니다",
                library_lrc=str(library_lrc) if library_lrc else None,
                completed_at=now,
            )
            with (directory / "progress.log").open("a", encoding="utf-8") as log:
                log.write("[3/3] LRC 병합·저장·재생 목록 적용 완료\n")
        except HTTPException as exc:
            reusable = len(list((directory / "chunks").glob("chunk_*.lrc")))
            _write_lrc_job(
                job_id, status="failed", stage="생성 실패", percent=0, message=str(exc.detail),
                retryable=source.is_file(), reused_chunks=reusable,
            )
            with (directory / "progress.log").open("a", encoding="utf-8") as log:
                log.write(f"[실패] {exc.detail}\n")
        except Exception as exc:
            reusable = len(list((directory / "chunks").glob("chunk_*.lrc")))
            _write_lrc_job(
                job_id, status="failed", stage="생성 실패", percent=0,
                message="LRC 백그라운드 생성 중 오류가 발생했습니다",
                retryable=source.is_file(), reused_chunks=reusable,
            )
            with (directory / "progress.log").open("a", encoding="utf-8") as log:
                log.write(f"[실패] {type(exc).__name__}: {exc}\n")
        finally:
            for disposable in (directory / "source.wav", directory / "lyrics.srt"):
                disposable.unlink(missing_ok=True)
            try:
                finished = _read_lrc_job(job_id).get("status") == "complete"
            except HTTPException:
                finished = False
            # 실패 원인을 고친 뒤 같은 대용량 MP3를 다시 업로드하지 않고 재시도할
            # 수 있도록 원본은 성공했을 때만 삭제한다.
            if finished:
                source.unlink(missing_ok=True)
                shutil.rmtree(directory / "chunks", ignore_errors=True)


def _start_persistent_lrc_job(job_id: str) -> None:
    threading.Thread(target=_run_persistent_lrc_job, args=(job_id,), daemon=True, name=f"lrc-job-{job_id[:6]}").start()


def _create_persistent_lrc_job(
    source: Path,
    filename: str,
    owner: str,
    *,
    source_kind: str = "upload",
    source_library: str = "library",
) -> dict[str, Any]:
    safe_filename = Path(filename).name
    for status_path in LRC_JOB_ROOT.glob("*/status.json"):
        try:
            existing = json.loads(status_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if (
            existing.get("owner") == owner
            and existing.get("filename") == safe_filename
            and existing.get("status") in {"queued", "running"}
        ):
            return existing
    job_id = uuid.uuid4().hex
    directory = _lrc_job_dir(job_id)
    directory.mkdir(mode=0o700, parents=True, exist_ok=False)
    shutil.move(str(source), str(directory / "source.mp3"))
    now = datetime.datetime.now().astimezone().isoformat()
    job = _write_lrc_job(
        job_id, filename=safe_filename, owner=owner, status="queued",
        source_kind=source_kind, source_library=source_library,
        stage="대기 중", percent=5, message="Mac의 LRC 작업 대기열에 등록됐습니다",
        created_at=now, completed_at=None, retryable=False,
    )
    _start_persistent_lrc_job(job_id)
    return job


def _recover_persistent_lrc_jobs() -> None:
    for status_path in LRC_JOB_ROOT.glob("*/status.json"):
        try:
            job = json.loads(status_path.read_text(encoding="utf-8"))
            job_id = status_path.parent.name
            if job.get("status") in {"queued", "running"} and (status_path.parent / "source.mp3").is_file():
                _write_lrc_job(job_id, status="queued", stage="서버 재시작 후 재개 대기", percent=5, message="중단된 LRC 작업을 다시 시작합니다")
                _start_persistent_lrc_job(job_id)
        except (OSError, ValueError):
            continue


class Mp3LibraryLrcJobRequest(BaseModel):
    file_id: str
    expected_name: str
    expected_size: int
    library_kind: str = "library"


def _youtube_id_from_filename(filename: str) -> str:
    match = re.search(r"\[([A-Za-z0-9_-]{11})\](?:\.mp3)?$", filename or "", re.IGNORECASE)
    return match.group(1) if match else ""


@app.post("/api/mp3-player/lrc-jobs")
async def create_mp3_lrc_job(request: Request, file: UploadFile = File(...)):
    _require_signed_in_user(request)
    original_name = Path(file.filename or "audio.mp3").name
    if Path(original_name).suffix.lower() != ".mp3":
        raise HTTPException(status_code=422, detail="MP3 파일만 가사를 생성할 수 있습니다")
    descriptor, staging_name = tempfile.mkstemp(prefix="lrc-upload-", suffix=".mp3", dir=LRC_UPLOAD_ROOT)
    os.close(descriptor)
    staging = Path(staging_name)
    size = 0
    try:
        with staging.open("wb") as destination:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > 1024 * 1024 * 1024:
                    raise HTTPException(status_code=413, detail="MP3는 최대 1GB까지 처리할 수 있습니다")
                destination.write(chunk)
        if size < 128:
            raise HTTPException(status_code=422, detail="비어 있거나 손상된 MP3입니다")
        job = _create_persistent_lrc_job(staging, original_name, _request_username(request))
        return JSONResponse(_public_lrc_job(job), status_code=202)
    finally:
        staging.unlink(missing_ok=True)


@app.post("/api/mp3-player/lrc-jobs/from-library")
def create_mp3_lrc_job_from_library(body: Mp3LibraryLrcJobRequest, request: Request):
    """Mac 보관함에 동일한 MP3가 있으면 휴대폰 업로드 없이 LRC 작업을 등록한다."""
    _require_owner(request)
    if body.library_kind == "favorites":
        source = _mp3_directory_path(
            MP3_FAVORITES_DIR,
            "/api/mp3-player/favorites-library",
            body.file_id,
        )
    elif body.library_kind == "library":
        source = _mp3_library_path(body.file_id)
    else:
        raise HTTPException(status_code=422, detail="Mac 보관함 종류가 올바르지 않습니다")
    expected_name = Path(body.expected_name or "").name
    actual_name = unicodedata.normalize("NFC", source.name).casefold()
    requested_name = unicodedata.normalize("NFC", expected_name).casefold()
    try:
        actual_size = source.stat().st_size
    except OSError as exc:
        raise HTTPException(status_code=404, detail="Mac 보관함의 MP3를 읽을 수 없습니다") from exc
    actual_video_id = _youtube_id_from_filename(source.name)
    requested_video_id = _youtube_id_from_filename(expected_name)
    same_identity = requested_name == actual_name or (
        bool(actual_video_id) and actual_video_id == requested_video_id
    )
    size_matches = body.expected_size <= 0 or body.expected_size == actual_size
    if not expected_name or not same_identity or (requested_name == actual_name and not size_matches):
        raise HTTPException(status_code=409, detail="Mac 보관함 파일과 선택한 MP3가 정확히 일치하지 않습니다")

    descriptor, staging_name = tempfile.mkstemp(prefix="lrc-library-", suffix=".mp3", dir=LRC_UPLOAD_ROOT)
    os.close(descriptor)
    staging = Path(staging_name)
    staging.unlink(missing_ok=True)
    try:
        try:
            os.link(source, staging)
        except OSError:
            shutil.copy2(source, staging)
        job = _create_persistent_lrc_job(
            staging,
            source.name,
            _request_username(request),
            source_kind="mac_library",
            source_library=body.library_kind,
        )
        job = _write_lrc_job(
            job["id"],
            stage="Mac 원본 확인 완료",
            message="MP3 전송을 생략하고 Mac 원본으로 작업합니다",
        )
        return JSONResponse(_public_lrc_job(job), status_code=202)
    finally:
        staging.unlink(missing_ok=True)


@app.post("/api/mp3-player/lrc-jobs/chunk")
async def create_mp3_lrc_job_chunk(
    request: Request,
    upload_id: str = Form(...),
    index: int = Form(...),
    total: int = Form(...),
    filename: str = Form(...),
    chunk: UploadFile = File(...),
):
    _require_signed_in_user(request)
    try:
        safe_upload_id = str(uuid.UUID(upload_id))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="업로드 식별자가 올바르지 않습니다") from exc
    safe_name = Path(filename).name
    if Path(safe_name).suffix.lower() != ".mp3" or not (1 <= total <= 128) or not (0 <= index < total):
        raise HTTPException(status_code=422, detail="분할 MP3 정보가 올바르지 않습니다")
    upload_dir = LRC_UPLOAD_ROOT / safe_upload_id
    upload_dir.mkdir(mode=0o700, exist_ok=True)
    owner = _request_username(request)
    owner_path = upload_dir / "owner.txt"
    try:
        existing_owner = owner_path.read_text(encoding="utf-8") if owner_path.is_file() else ""
    except OSError:
        existing_owner = ""
    if existing_owner and not secrets.compare_digest(existing_owner, owner):
        raise HTTPException(status_code=404, detail="분할 업로드를 찾을 수 없습니다")
    if not existing_owner:
        owner_path.write_text(owner, encoding="utf-8")
    part = upload_dir / f"part-{index:04d}"
    size = 0
    with part.open("wb") as destination:
        while data := await chunk.read(1024 * 1024):
            size += len(data)
            if size > 24 * 1024 * 1024:
                raise HTTPException(status_code=413, detail="업로드 조각이 너무 큽니다")
            destination.write(data)
    if size < 1:
        raise HTTPException(status_code=422, detail="빈 업로드 조각입니다")
    parts = [upload_dir / f"part-{part_index:04d}" for part_index in range(total)]
    if index != total - 1 or not all(item.is_file() for item in parts):
        return JSONResponse({"received": index + 1, "total": total})
    source = upload_dir / "source.mp3"
    assembled_size = 0
    try:
        with source.open("wb") as destination:
            for item in parts:
                assembled_size += item.stat().st_size
                if assembled_size > 1024 * 1024 * 1024:
                    raise HTTPException(status_code=413, detail="MP3는 최대 1GB까지 처리할 수 있습니다")
                with item.open("rb") as source_part:
                    shutil.copyfileobj(source_part, destination, length=1024 * 1024)
        job = _create_persistent_lrc_job(source, safe_name, owner)
        return JSONResponse(_public_lrc_job(job), status_code=202)
    finally:
        shutil.rmtree(upload_dir, ignore_errors=True)


@app.get("/api/mp3-player/lrc-jobs/{job_id}")
def mp3_lrc_job_status(job_id: str, request: Request):
    _require_signed_in_user(request)
    job = _read_lrc_job(job_id)
    if job.get("owner") != _request_username(request):
        raise HTTPException(status_code=404, detail="LRC 작업을 찾을 수 없습니다")
    return _public_lrc_job(job)


@app.get("/api/mp3-player/lrc-jobs/{job_id}/result")
def mp3_lrc_job_result(job_id: str, request: Request):
    _require_signed_in_user(request)
    job = _read_lrc_job(job_id)
    if job.get("owner") != _request_username(request) or job.get("status") != "complete":
        raise HTTPException(status_code=404, detail="완성된 LRC를 찾을 수 없습니다")
    result = _lrc_job_dir(job_id) / "result.lrc"
    if not result.is_file():
        raise HTTPException(status_code=404, detail="완성된 LRC를 찾을 수 없습니다")
    return FileResponse(result, media_type="text/plain; charset=utf-8", filename=Path(job.get("filename") or "lyrics.mp3").with_suffix(".lrc").name)


@app.post("/api/mp3-player/lrc-jobs/{job_id}/retry")
def retry_mp3_lrc_job(job_id: str, request: Request):
    """성공한 조각을 보존하고 실패한 조각부터 백그라운드 작업을 재개한다."""
    _require_signed_in_user(request)
    job = _read_lrc_job(job_id)
    if job.get("owner") != _request_username(request):
        raise HTTPException(status_code=404, detail="LRC 작업을 찾을 수 없습니다")
    if job.get("status") in {"queued", "running"}:
        return JSONResponse(_public_lrc_job(job), status_code=202)
    directory = _lrc_job_dir(job_id)
    if not (directory / "source.mp3").is_file():
        raise HTTPException(status_code=409, detail="재시도할 원본 MP3가 남아 있지 않습니다")
    reused = len(list((directory / "chunks").glob("chunk_*.lrc")))
    retried = _write_lrc_job(
        job_id,
        status="queued",
        stage="실패 지점부터 재시도 대기",
        percent=5,
        message=f"완료된 {reused}개 조각을 보존하고 실패 지점부터 다시 시작합니다",
        retryable=False,
        reused_chunks=reused,
        completed_at=None,
        estimated_remaining_seconds=None,
        estimated_completion_at=None,
    )
    _start_persistent_lrc_job(job_id)
    return JSONResponse(_public_lrc_job(retried), status_code=202)


@app.post("/api/mp3-player/generate-lrc")
async def generate_mp3_lrc(request: Request, file: UploadFile = File(...)):
    """작은 MP3를 한 번에 받아 로컬 Whisper로 LRC를 만든다."""
    _require_signed_in_user(request)
    original_name = Path(file.filename or "audio.mp3").name
    if Path(original_name).suffix.lower() != ".mp3":
        raise HTTPException(status_code=422, detail="MP3 파일만 가사를 생성할 수 있습니다")
    work_root = Path(os.path.expanduser("~/.tulpachat/mp3_player"))
    work_root.mkdir(parents=True, exist_ok=True)
    job_dir = Path(tempfile.mkdtemp(prefix="lyrics-", dir=work_root))
    source = job_dir / "source.mp3"
    size = 0
    try:
        with source.open("wb") as destination:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > 250 * 1024 * 1024:
                    raise HTTPException(status_code=413, detail="MP3는 최대 250MB까지 처리할 수 있습니다")
                destination.write(chunk)
        return await _generate_lrc_from_mp3_source(source, job_dir)
    finally:
        shutil.rmtree(job_dir, ignore_errors=True)


@app.post("/api/mp3-player/generate-lrc-chunk")
async def generate_mp3_lrc_chunk(
    request: Request,
    upload_id: str = Form(...),
    index: int = Form(...),
    total: int = Form(...),
    filename: str = Form(...),
    chunk: UploadFile = File(...),
):
    """Cloudflare 단일 요청 제한보다 큰 MP3를 작은 조각으로 받아 마지막에 분석한다."""
    _require_signed_in_user(request)
    try:
        safe_upload_id = str(uuid.UUID(upload_id))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="업로드 식별자가 올바르지 않습니다") from exc
    safe_name = Path(filename).name
    if Path(safe_name).suffix.lower() != ".mp3" or not (1 <= total <= 128) or not (0 <= index < total):
        raise HTTPException(status_code=422, detail="분할 MP3 정보가 올바르지 않습니다")
    work_root = Path(os.path.expanduser("~/.tulpachat/mp3_player"))
    work_root.mkdir(parents=True, exist_ok=True)
    job_dir = work_root / f"chunks-{safe_upload_id}"
    job_dir.mkdir(mode=0o700, exist_ok=True)
    part = job_dir / f"part-{index:04d}"
    size = 0
    try:
        with part.open("wb") as destination:
            while data := await chunk.read(1024 * 1024):
                size += len(data)
                if size > 24 * 1024 * 1024:
                    raise HTTPException(status_code=413, detail="업로드 조각이 너무 큽니다")
                destination.write(data)
        if size < 1:
            raise HTTPException(status_code=422, detail="빈 업로드 조각입니다")
        parts = [job_dir / f"part-{part_index:04d}" for part_index in range(total)]
        if index != total - 1 or not all(item.is_file() for item in parts):
            return JSONResponse({"received": index + 1, "total": total})
        source = job_dir / "source.mp3"
        assembled_size = 0
        with source.open("wb") as destination:
            for item in parts:
                assembled_size += item.stat().st_size
                if assembled_size > 1024 * 1024 * 1024:
                    raise HTTPException(status_code=413, detail="MP3는 최대 1GB까지 처리할 수 있습니다")
                with item.open("rb") as source_part:
                    shutil.copyfileobj(source_part, destination, length=1024 * 1024)
        return await _generate_lrc_from_mp3_source(source, job_dir)
    finally:
        if index == total - 1:
            shutil.rmtree(job_dir, ignore_errors=True)


class YoutubeMp3DownloadRequest(BaseModel):
    url: str
    destination: str = "library"


class Mp3TrackFavoriteWrite(BaseModel):
    track_key: str
    title: str = ""
    playlist: str = ""


class Mp3RecommendationPreferencesWrite(BaseModel):
    genres: list[str] = []
    moods: list[str] = []
    artists: list[str] = []


class Mp3RecommendationFeedbackWrite(BaseModel):
    youtube_id: str
    action: str
    title: str = ""


def _youtube_mp3_url(value: str) -> str:
    """웹에서 받은 주소를 공개 YouTube 영상/재생목록 주소로만 제한한다."""
    raw = (value or "").strip()
    try:
        parsed = urllib.parse.urlparse(raw)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="YouTube 주소를 확인해주세요") from exc
    host = (parsed.hostname or "").lower().rstrip(".")
    allowed = host == "youtu.be" or host == "youtube.com" or host.endswith(".youtube.com")
    if parsed.scheme not in {"http", "https"} or not allowed:
        raise HTTPException(status_code=422, detail="YouTube 영상 또는 재생목록 주소만 사용할 수 있습니다")
    return raw


def _mp3_library_rows() -> list[dict[str, Any]]:
    rows = _mp3_directory_rows(MP3_LIBRARY_DIR, "/api/mp3-player/library")
    for row in rows:
        row["library_kind"] = "library"
    return rows


def _mp3_directory_rows(directory: Path, route_prefix: str) -> list[dict[str, Any]]:
    rows = []
    for path in directory.glob("*.mp3"):
        try:
            stat = path.stat()
        except OSError:
            continue
        file_id = hashlib.sha256(path.name.encode("utf-8")).hexdigest()[:24]
        lrc_path = path.with_suffix(".lrc")
        rows.append({
            "id": file_id,
            "name": path.name,
            "title": path.stem,
            "size": stat.st_size,
            "updated_at": datetime.datetime.fromtimestamp(stat.st_mtime).astimezone().isoformat(),
            "stream_url": f"{route_prefix}/{file_id}/file",
            "has_lrc": lrc_path.is_file(),
            "lrc_url": f"{route_prefix}/{file_id}/lrc" if lrc_path.is_file() else None,
        })
    return sorted(rows, key=lambda row: row["updated_at"], reverse=True)


def _mp3_library_path(file_id: str) -> Path:
    return _mp3_directory_path(MP3_LIBRARY_DIR, "/api/mp3-player/library", file_id)


def _mp3_directory_path(directory: Path, route_prefix: str, file_id: str) -> Path:
    for row in _mp3_directory_rows(directory, route_prefix):
        if secrets.compare_digest(row["id"], file_id):
            target = directory / row["name"]
            if target.resolve().parent == directory.resolve() and target.is_file():
                return target
    raise HTTPException(status_code=404, detail="MP3 파일을 찾을 수 없습니다")


def _youtube_id_from_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    if parsed.hostname == "youtu.be":
        return parsed.path.strip("/").split("/")[0]
    return urllib.parse.parse_qs(parsed.query).get("v", [""])[0]


def _update_mp3_postprocess(job_id: str, **values) -> None:
    if not values:
        return
    values["updated_at"] = _now()
    fields = ",".join(f"{key}=?" for key in values)
    conn = get_conn()
    conn.execute(f"UPDATE mp3_postprocess_jobs SET {fields} WHERE id=?", (*values.values(), job_id))
    conn.commit()
    conn.close()


def _queue_lyrics_translation(job_id: str, username: str, title: str, lrc: str) -> int:
    lyrics = "\n".join(
        re.sub(r"^\[[^]]+]\s*", "", line).strip()
        for line in lrc.splitlines() if re.match(r"^\[\d{1,3}:\d{2}", line)
    ).strip()
    content = (
        f"[MP3 가사 직해 요청]\n곡: {title}\n언어: 일본어\n\n"
        "가사 순서를 그대로 지키며 각 일본어 원문 바로 아래에 자연스러운 한국어 직해를 붙여주세요. "
        "한자가 있는 줄에는 읽기 어려운 말만 괄호로 후리가나를 덧붙이되, 문법 수업·새 예문·감상 평가는 넣지 마세요.\n"
        "반복되는 가사도 생략하지 말고 입력된 순서대로 옮겨주세요. LRC 또는 Whisper 오인식으로 의심되는 대목도 "
        "별도의 검수 문구를 붙이지 말고, 입력된 원문을 유지한 채 가능한 범위에서 자연스럽게 직해해주세요.\n\n"
        f"[가사]\n{lyrics[:16000]}"
    )
    now = _now()
    conn = get_conn()
    cursor = conn.execute(
        "INSERT INTO messages(room_id,sender,content,created_at) VALUES(?,?,?,?)",
        ("일본어 선생님", username, content, now),
    )
    source_message_id = int(cursor.lastrowid)
    conn.execute(
        "INSERT INTO pending_turns(persona_name,room_id,status,created_at,source_message_id) VALUES(?,?,'pending',?,?)",
        ("일본어 선생님", "일본어 선생님", now, source_message_id),
    )
    conn.commit()
    conn.close()
    _update_mp3_postprocess(
        job_id, status="translating", stage="가사 해석 대기 중", percent=75,
        source_message_id=source_message_id,
    )
    threading.Thread(
        target=_watch_mp3_translation, args=(job_id, source_message_id), daemon=True,
        name=f"mp3-translation-{job_id[:6]}",
    ).start()
    return source_message_id


def _watch_mp3_translation(job_id: str, source_message_id: int) -> None:
    while True:
        conn = get_conn()
        turn = conn.execute(
            "SELECT status,error FROM pending_turns WHERE source_message_id=? ORDER BY id DESC LIMIT 1",
            (source_message_id,),
        ).fetchone()
        conn.close()
        if turn and turn["status"] == "done":
            _update_mp3_postprocess(job_id, status="complete", stage="LRC·가사 해석 완료", percent=100, completed_at=_now())
            return
        if turn and turn["status"] == "failed":
            _update_mp3_postprocess(job_id, status="failed", stage="가사 해석 실패", percent=70, error=str(turn["error"] or "")[:500], completed_at=_now())
            return
        time.sleep(2)


def _run_mp3_postprocess(job_id: str) -> None:
    with _mp3_postprocess_lock:
        conn = get_conn()
        job = conn.execute("SELECT * FROM mp3_postprocess_jobs WHERE id=?", (job_id,)).fetchone()
        conn.close()
        if not job or job["status"] in {"complete", "translating"}:
            return
        path = Path(job["mp3_path"])
        try:
            if not path.is_file():
                raise FileNotFoundError("다운로드된 MP3를 찾을 수 없습니다")
            _update_mp3_postprocess(job_id, status="processing", stage="LRCLIB에서 시간 가사 검색 중", percent=15, error=None)
            metadata = mp3_postprocess.media_metadata(path)
            lrc = mp3_postprocess.find_synced_lyrics(metadata)
            source = "lrclib"
            if not lrc:
                _update_mp3_postprocess(job_id, stage="로컬 Whisper로 시간 가사 생성 중", percent=30)
                work_dir = LRC_JOB_ROOT / f"postprocess-{job_id}"
                work_dir.mkdir(parents=True, exist_ok=True)
                response = asyncio.run(_generate_lrc_from_mp3_source(path, work_dir))
                lrc = bytes(response.body).decode("utf-8")
                source = "whisper"
            if not mp3_postprocess.valid_lrc(lrc):
                raise ValueError("시간 가사를 충분히 만들지 못했습니다")
            lrc_path = path.with_suffix(".lrc")
            temporary = lrc_path.with_suffix(".lrc.tmp")
            temporary.write_text(lrc, encoding="utf-8")
            temporary.replace(lrc_path)
            store_synced_lrc(job["username"], job["filename"], lrc)
            _update_mp3_postprocess(job_id, stage="LRC 저장 완료 · 가사 해석 요청 중", percent=70, lrc_source=source)
            _queue_lyrics_translation(job_id, job["username"], metadata["title"], lrc)
        except Exception as exc:
            detail = exc.detail if isinstance(exc, HTTPException) else str(exc)
            _update_mp3_postprocess(
                job_id, status="failed", stage="자동 가사 처리 실패", percent=0,
                error=str(detail)[:500], completed_at=_now(),
            )


def _enqueue_mp3_postprocess(username: str, path: Path, youtube_id: str = "") -> str:
    now, job_id = _now(), uuid.uuid4().hex
    conn = get_conn()
    existing = conn.execute(
        "SELECT id,status FROM mp3_postprocess_jobs WHERE username=? AND filename=?",
        (username, path.name),
    ).fetchone()
    if existing and existing["status"] not in {"failed"}:
        conn.close()
        return existing["id"]
    conn.execute(
        """INSERT INTO mp3_postprocess_jobs
           (id,username,youtube_id,filename,mp3_path,status,stage,percent,created_at,updated_at)
           VALUES(?,?,?,?,?,'queued','LRC 검색 대기 중',0,?,?)
           ON CONFLICT(username,filename) DO UPDATE SET id=excluded.id,youtube_id=excluded.youtube_id,
             mp3_path=excluded.mp3_path,status='queued',stage='LRC 검색 대기 중',percent=0,
             lrc_source=NULL,source_message_id=NULL,error=NULL,updated_at=excluded.updated_at,completed_at=NULL""",
        (job_id, username, youtube_id or None, path.name, str(path), now, now),
    )
    conn.commit()
    conn.close()
    threading.Thread(target=_run_mp3_postprocess, args=(job_id,), daemon=True, name=f"mp3-post-{job_id[:6]}").start()
    return job_id


def _update_mp3_download_job(job_id: str, **values) -> dict[str, Any]:
    values["updated_at"] = _now()
    job = _mp3_download_jobs.setdefault(job_id, {"id": job_id})
    job.update(values)
    conn = get_conn()
    fields = ",".join(f"{key}=?" for key in values)
    conn.execute(f"UPDATE mp3_download_jobs SET {fields} WHERE id=?", (*values.values(), job_id))
    conn.commit()
    conn.close()
    return job


def _recover_incomplete_download(job_id: str, output_dir: Path, youtube_id: str) -> Path | None:
    media = next((
        path for suffix in ("mp4", "m4a", "webm") for path in output_dir.glob(f"*.{suffix}")
        if f"[{youtube_id}]" in path.stem
    ), None)
    if not media:
        return None
    ffmpeg = next((candidate for candidate in (
        "/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg", shutil.which("ffmpeg"),
    ) if candidate and Path(candidate).is_file()), None)
    if not ffmpeg:
        return None
    target = media.with_suffix(".mp3")
    temporary = target.with_suffix(".mp3.tmp")
    _update_mp3_download_job(job_id, status="converting", stage="중단된 음원을 MP3로 복구 중", percent=78, current_file=media.name)
    converted = subprocess.run(
        [ffmpeg, "-y", "-v", "error", "-i", str(media), "-vn", "-codec:a", "libmp3lame", "-qscale:a", "0", "-f", "mp3", str(temporary)],
        capture_output=True, text=True, timeout=900,
    )
    if converted.returncode or not temporary.is_file() or temporary.stat().st_size < 1024:
        temporary.unlink(missing_ok=True)
        return None
    temporary.replace(target)
    media.unlink(missing_ok=True)
    return target


def _run_youtube_mp3_job(job_id: str, url: str, destination: str = "library", username: str = "") -> None:
    yt_dlp = next((Path(path) for path in (
        "/opt/homebrew/bin/yt-dlp", "/usr/local/bin/yt-dlp", shutil.which("yt-dlp") or "",
    ) if path and Path(path).is_file()), None)
    if yt_dlp is None:
        _update_mp3_download_job(job_id, status="failed", stage="저장 실패", percent=0, message="Mac에 yt-dlp가 설치되어 있지 않습니다", error="yt-dlp 없음")
        return
    output_dir = MP3_FAVORITES_DIR if destination == "favorites" else MP3_LIBRARY_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    download_archive = output_dir / ".youtube-download-archive.txt"
    youtube_id = _youtube_id_from_url(url)
    command = [
        str(yt_dlp), "--newline", "--no-overwrites", "--yes-playlist",
        "--format", "bestaudio[protocol=m3u8_native]/bestaudio/best",
        "--retries", "10", "--fragment-retries", "10", "--sleep-requests", "1",
        "--extract-audio", "--audio-format", "mp3", "--audio-quality", "0",
        "--embed-thumbnail", "--convert-thumbnails", "jpg", "--embed-metadata",
        "--download-archive", str(download_archive),
        "--output", str(output_dir / "%(title).180B [%(id)s].%(ext)s"),
        url,
    ]
    with _mp3_download_lock:
        try:
            recovered = _recover_incomplete_download(job_id, output_dir, youtube_id)
            if recovered:
                matches = [recovered]
            else:
                _update_mp3_download_job(job_id, status="downloading", stage="YouTube 음원 받는 중", percent=2, message="음원을 다운로드하고 있습니다", error=None)
                process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
                assert process.stdout is not None
                for raw in process.stdout:
                    line = raw.strip()
                    if not line:
                        continue
                    percent_match = re.search(r"\[download\]\s+([\d.]+)%", line)
                    if percent_match:
                        download_percent = max(0, min(100, int(float(percent_match.group(1)))))
                        _update_mp3_download_job(job_id, status="downloading", stage="YouTube 음원 받는 중", percent=min(70, 2 + round(download_percent * .68)))
                    destination_match = re.search(r"(?:Destination:|ExtractAudio\].*?:)\s*(.+)$", line)
                    if destination_match:
                        _update_mp3_download_job(job_id, status="converting", stage="MP3 변환·메타데이터 적용 중", percent=82, current_file=Path(destination_match.group(1)).name)
                    elif "EmbedThumbnail" in line or "Metadata" in line:
                        _update_mp3_download_job(job_id, status="finalizing", stage="앨범 이미지·곡 정보 적용 중", percent=94)
                return_code = process.wait()
                if return_code:
                    raise RuntimeError("다운로드 또는 MP3 변환에 실패했습니다")
                matches = sorted(
                    (item for item in output_dir.glob("*.mp3") if f"[{youtube_id}]" in item.stem),
                    key=lambda item: item.stat().st_mtime, reverse=True,
                )
            if not matches:
                raise RuntimeError("변환된 MP3 파일을 찾지 못했습니다")
            final_path = matches[0]
            postprocess_id = _enqueue_mp3_postprocess(username, final_path, youtube_id) if username else None
            message = "좋아요음악 폴더에 저장했습니다" if destination == "favorites" else "Mac MP3 보관함에 저장했습니다"
            _update_mp3_download_job(
                job_id, status="complete", stage="좋아요 폴더 저장 완료" if destination == "favorites" else "MP3 저장 완료",
                percent=100, message=f"{message} · LRC와 가사 해석을 자동 처리합니다",
                final_filename=final_path.name, postprocess_id=postprocess_id, completed_at=_now(), error=None,
            )
        except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
            _update_mp3_download_job(
                job_id, status="failed", stage="저장 실패", percent=0,
                message="저장하지 못했습니다. 다시 시도해주세요", error=str(exc)[:500], completed_at=_now(),
            )


@app.get("/api/mp3-player/library")
def mp3_player_library(request: Request):
    _require_owner(request)
    return {"items": _mp3_library_rows()}


@app.get("/api/mp3-player/library/{file_id}/file")
def mp3_player_library_file(file_id: str, request: Request):
    _require_owner(request)
    return FileResponse(_mp3_library_path(file_id), media_type="audio/mpeg", headers={"Cache-Control": "private, max-age=3600"})


@app.get("/api/mp3-player/library/{file_id}/lrc")
def mp3_player_library_lrc(file_id: str, request: Request):
    _require_owner(request)
    target = _mp3_library_path(file_id).with_suffix(".lrc")
    if not target.is_file():
        raise HTTPException(status_code=404, detail="이 곡의 LRC를 찾을 수 없습니다")
    return FileResponse(target, media_type="text/plain; charset=utf-8", headers={"Cache-Control": "private, no-store"})


@app.get("/api/mp3-player/favorites-library")
def mp3_player_favorites_library(request: Request):
    user = _memo_user(request)
    conn = get_conn()
    recommended_ids = {row["youtube_id"] for row in conn.execute(
        "SELECT youtube_id FROM mp3_recommendation_feedback WHERE username=? AND action='download'", (user["username"],)
    ).fetchall()}
    conn.close()
    rows = _mp3_directory_rows(MP3_FAVORITES_DIR, "/api/mp3-player/favorites-library")
    for row in rows:
        match = re.search(r"\[([\w-]{11})\]\.mp3$", row["name"], re.IGNORECASE)
        row["recommended_japanese"] = bool(match and match.group(1) in recommended_ids)
        row["library_label"] = "좋아요음악"
        row["library_kind"] = "favorites"
    return {"items": rows}


@app.get("/api/mp3-player/favorites-library/{file_id}/file")
def mp3_player_favorites_library_file(file_id: str, request: Request):
    _require_owner(request)
    target = _mp3_directory_path(MP3_FAVORITES_DIR, "/api/mp3-player/favorites-library", file_id)
    return FileResponse(target, media_type="audio/mpeg", headers={"Cache-Control": "private, max-age=3600"})


@app.get("/api/mp3-player/favorites-library/{file_id}/lrc")
def mp3_player_favorites_library_lrc(file_id: str, request: Request):
    _require_owner(request)
    target = _mp3_directory_path(MP3_FAVORITES_DIR, "/api/mp3-player/favorites-library", file_id).with_suffix(".lrc")
    if not target.is_file():
        raise HTTPException(status_code=404, detail="이 곡의 LRC를 찾을 수 없습니다")
    return FileResponse(target, media_type="text/plain; charset=utf-8", headers={"Cache-Control": "private, no-store"})


@app.get("/api/mp3-player/favorites-library/{file_id}/postprocess")
def mp3_player_favorites_postprocess(file_id: str, request: Request):
    user = _memo_user(request)
    target = _mp3_directory_path(MP3_FAVORITES_DIR, "/api/mp3-player/favorites-library", file_id)
    conn = get_conn()
    job = conn.execute(
        "SELECT * FROM mp3_postprocess_jobs WHERE username=? AND filename=? ORDER BY updated_at DESC LIMIT 1",
        (user["username"], target.name),
    ).fetchone()
    if not job:
        conn.close()
        raise HTTPException(status_code=404, detail="자동 가사 작업을 찾을 수 없습니다")
    result, turn_status, turn_error = None, None, None
    if job["source_message_id"]:
        turn = conn.execute(
            "SELECT status,reply,error FROM pending_turns WHERE source_message_id=? ORDER BY id DESC LIMIT 1",
            (job["source_message_id"],),
        ).fetchone()
        if turn:
            turn_status, turn_error = turn["status"], turn["error"]
            result = turn["reply"] if turn_status == "done" and turn["reply"] != "NONE" else None
    conn.close()
    status, stage, percent = job["status"], job["stage"], job["percent"]
    if turn_status == "done":
        status, stage, percent = "complete", "LRC·가사 해석 완료", 100
        _update_mp3_postprocess(job["id"], status=status, stage=stage, percent=percent, completed_at=_now())
    elif turn_status == "processing":
        status, stage, percent = "translating", "가사 분석·해석 중", 85
    elif turn_status in {"failed"}:
        status, stage, percent = "failed", "가사 해석 실패", 70
    return {
        "id": job["id"], "status": status, "stage": stage, "percent": percent,
        "lrc_source": job["lrc_source"], "has_lrc": target.with_suffix(".lrc").is_file(),
        "source_message_id": job["source_message_id"], "result": result,
        "error": turn_error or job["error"],
    }


@app.get("/api/me/mp3-favorites")
def list_mp3_favorites(request: Request):
    user = _memo_user(request)
    conn = get_conn()
    rows = conn.execute(
        """SELECT track_key AS key,title,playlist,created_at AS savedAt
             FROM mp3_track_favorites
            WHERE username=? ORDER BY created_at""",
        (user["username"],),
    ).fetchall()
    result = [dict(row) for row in rows]
    conn.close()
    return result


@app.put("/api/me/mp3-favorites")
def add_mp3_favorite(body: Mp3TrackFavoriteWrite, request: Request):
    user = _memo_user(request)
    track_key = body.track_key.strip()
    if not track_key or len(track_key) > 600:
        raise HTTPException(status_code=422, detail="곡 식별자가 올바르지 않습니다")
    conn = get_conn()
    conn.execute(
        """INSERT INTO mp3_track_favorites(username,track_key,title,playlist,created_at)
           VALUES(?,?,?,?,?)
           ON CONFLICT(username,track_key) DO UPDATE SET
             title=excluded.title,playlist=excluded.playlist""",
        (user["username"], track_key, body.title.strip()[:300], body.playlist.strip()[:300], _now()),
    )
    conn.commit()
    conn.close()
    return {"ok": True, "key": track_key, "is_favorite": True}


@app.delete("/api/me/mp3-favorites")
def remove_mp3_favorite(request: Request, track_key: str = Query(min_length=1, max_length=600)):
    user = _memo_user(request)
    conn = get_conn()
    conn.execute(
        "DELETE FROM mp3_track_favorites WHERE username=? AND track_key=?",
        (user["username"], track_key),
    )
    conn.commit()
    conn.close()
    return {"ok": True, "key": track_key, "is_favorite": False}


def _mp3_recommendation_preferences(username: str) -> dict:
    conn = get_conn()
    row = conn.execute(
        "SELECT preferences_json FROM mp3_recommendation_preferences WHERE username=?", (username,)
    ).fetchone()
    conn.close()
    try:
        stored = json.loads(row["preferences_json"]) if row else {}
    except (TypeError, json.JSONDecodeError):
        stored = {}
    return mp3_recommendations.normalize_preferences(stored)


@app.get("/api/mp3-recommendations/preferences")
def get_mp3_recommendation_preferences(request: Request):
    user = _memo_user(request)
    return _mp3_recommendation_preferences(user["username"])


@app.put("/api/mp3-recommendations/preferences")
def put_mp3_recommendation_preferences(body: Mp3RecommendationPreferencesWrite, request: Request):
    user = _memo_user(request)
    preferences = mp3_recommendations.normalize_preferences(body.dict())
    conn = get_conn()
    conn.execute(
        """INSERT INTO mp3_recommendation_preferences(username,preferences_json,updated_at) VALUES(?,?,?)
           ON CONFLICT(username) DO UPDATE SET preferences_json=excluded.preferences_json,updated_at=excluded.updated_at""",
        (user["username"], json.dumps(preferences, ensure_ascii=False), _now()),
    )
    conn.commit()
    conn.close()
    return preferences


@app.post("/api/mp3-recommendations/feedback")
def post_mp3_recommendation_feedback(body: Mp3RecommendationFeedbackWrite, request: Request):
    user = _memo_user(request)
    if not re.fullmatch(r"[\w-]{11}", body.youtube_id) or body.action not in {"dismiss", "download"}:
        raise HTTPException(status_code=422, detail="추천 피드백이 올바르지 않습니다")
    conn = get_conn()
    conn.execute(
        """INSERT INTO mp3_recommendation_feedback(username,youtube_id,action,title,created_at) VALUES(?,?,?,?,?)
           ON CONFLICT(username,youtube_id) DO UPDATE SET action=excluded.action,title=excluded.title,created_at=excluded.created_at""",
        (user["username"], body.youtube_id, body.action, body.title.strip()[:300], _now()),
    )
    conn.commit()
    conn.close()
    return {"ok": True}


@app.get("/api/mp3-recommendations")
def get_mp3_recommendations(
    request: Request,
    mode: str = Query("taste"),
    year: int | None = Query(None, ge=2000, le=2100),
    season: str | None = Query(None),
    cursor: int = Query(0, ge=0),
    page_size: int = Query(12, ge=6, le=20),
):
    _require_owner(request)
    if mode not in {"taste", "popular", "season"} or (season and season not in {"WINTER", "SPRING", "SUMMER", "FALL"}):
        raise HTTPException(status_code=422, detail="추천 방식 또는 분기가 올바르지 않습니다")
    user = _memo_user(request)
    yt_dlp = next((Path(path) for path in (
        "/opt/homebrew/bin/yt-dlp", "/usr/local/bin/yt-dlp", shutil.which("yt-dlp") or "",
    ) if path and Path(path).is_file()), None)
    if yt_dlp is None:
        raise HTTPException(status_code=503, detail="Mac에 yt-dlp가 설치되어 있지 않습니다")
    conn = get_conn()
    favorites = [row["title"] for row in conn.execute(
        "SELECT title FROM mp3_track_favorites WHERE username=? ORDER BY created_at DESC LIMIT 10", (user["username"],)
    ).fetchall() if row["title"]]
    dismissed = {row["youtube_id"] for row in conn.execute(
        "SELECT youtube_id FROM mp3_recommendation_feedback WHERE username=? AND action='dismiss'", (user["username"],)
    ).fetchall()}
    conn.close()
    preferences = _mp3_recommendation_preferences(user["username"])
    if mode == "popular":
        queries = mp3_recommendations.popular_anime_queries()
    elif mode == "season":
        default_year, default_season = mp3_recommendations.current_anime_season()
        year, season = year or default_year, season or default_season
        queries = mp3_recommendations.season_anime_queries(year, season)
    else:
        queries = mp3_recommendations.build_queries(preferences, favorites, limit=7)
    excluded = (
        mp3_recommendations.library_youtube_ids(MP3_LIBRARY_DIR)
        | mp3_recommendations.library_youtube_ids(MP3_FAVORITES_DIR)
        | dismissed
    )
    cache_key = hashlib.sha256(json.dumps({
        "user": user["username"], "mode": mode, "year": year, "season": season,
        "preferences": preferences, "favorites": favorites, "excluded": sorted(excluded),
    }, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    now = time.time()
    with _mp3_recommendation_cache_lock:
        cached = _mp3_recommendation_cache.get(cache_key)
        if cached and now - cached["created_at"] < 1800:
            all_items = cached["items"]
        else:
            all_items = None
    if all_items is None:
        all_items = mp3_recommendations.collect_candidates(yt_dlp, queries, excluded, per_query=12, max_results=72)
        with _mp3_recommendation_cache_lock:
            _mp3_recommendation_cache[cache_key] = {"created_at": now, "items": all_items}
            for key, value in list(_mp3_recommendation_cache.items()):
                if now - value["created_at"] >= 1800:
                    _mp3_recommendation_cache.pop(key, None)
    items = all_items[cursor:cursor + page_size]
    next_cursor = cursor + len(items) if cursor + len(items) < len(all_items) else None
    return {
        "items": items, "preferences": preferences, "queries": len(queries), "mode": mode,
        "year": year, "season": season, "next_cursor": next_cursor, "total": len(all_items),
    }


@app.get("/api/me/mp3-lrc-index")
def list_synced_mp3_lrc(request: Request):
    user = _memo_user(request)
    conn = get_conn()
    rows = conn.execute(
        """SELECT track_key AS key,filename,updated_at
             FROM mp3_track_lrc WHERE username=? ORDER BY updated_at DESC""",
        (user["username"],),
    ).fetchall()
    result = [dict(row) for row in rows]
    conn.close()
    return result


@app.get("/api/me/mp3-lrc")
def get_synced_mp3_lrc(request: Request, track_key: str = Query(min_length=1, max_length=600)):
    user = _memo_user(request)
    conn = get_conn()
    row = conn.execute(
        "SELECT filename,content,updated_at FROM mp3_track_lrc WHERE username=? AND track_key=?",
        (user["username"], track_key),
    ).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="동기화된 LRC를 찾을 수 없습니다")
    return Response(
        content=row["content"],
        media_type="text/plain; charset=utf-8",
        headers={"Cache-Control": "private, no-store"},
    )


@app.get("/api/shift-alarm/youtube-mp3")
def youtube_mp3_status(request: Request, job_id: str | None = Query(None)):
    _require_owner(request)
    user = _memo_user(request)
    conn = get_conn()
    if job_id:
        row = conn.execute("SELECT * FROM mp3_download_jobs WHERE id=? AND username=?", (job_id, user["username"])).fetchone()
        if not row:
            conn.close()
            raise HTTPException(status_code=404, detail="다운로드 작업을 찾을 수 없습니다")
        job = dict(row)
        conn.close()
        item = None
        if job.get("final_filename"):
            item = next((entry for entry in _mp3_directory_rows(
                MP3_FAVORITES_DIR if job["destination"] == "favorites" else MP3_LIBRARY_DIR,
                "/api/mp3-player/favorites-library" if job["destination"] == "favorites" else "/api/mp3-player/library",
            ) if entry["name"] == job["final_filename"]), None)
            if item and job["destination"] == "favorites":
                item.update(library_label="좋아요음악", library_kind="favorites", recommended_japanese=True)
        return {"job": job, "item": item}
    rows = conn.execute(
        "SELECT * FROM mp3_download_jobs WHERE username=? ORDER BY created_at DESC LIMIT 20", (user["username"],)
    ).fetchall()
    conn.close()
    return {"jobs": [dict(row) for row in rows], "items": _mp3_library_rows()}


@app.post("/api/shift-alarm/youtube-mp3")
def youtube_mp3_download(payload: YoutubeMp3DownloadRequest, request: Request):
    _require_owner(request)
    user = _memo_user(request)
    url = _youtube_mp3_url(payload.url)
    if payload.destination not in {"library", "favorites"}:
        raise HTTPException(status_code=422, detail="저장 위치가 올바르지 않습니다")
    conn = get_conn()
    active = conn.execute(
        "SELECT id FROM mp3_download_jobs WHERE username=? AND url=? AND destination=? AND status IN ('queued','downloading','converting','finalizing') ORDER BY created_at DESC LIMIT 1",
        (user["username"], url, payload.destination),
    ).fetchone()
    active_count = conn.execute(
        "SELECT COUNT(*) AS n FROM mp3_download_jobs WHERE status IN ('queued','downloading','converting','finalizing')"
    ).fetchone()["n"]
    conn.close()
    if active:
        raise HTTPException(status_code=409, detail="같은 주소를 이미 다운로드하고 있습니다")
    if active_count >= 3:
        raise HTTPException(status_code=429, detail="다운로드 대기열이 가득 찼습니다. 진행 중인 작업이 끝난 뒤 다시 시도해주세요")
    now = datetime.datetime.now().astimezone().isoformat()
    job_id = uuid.uuid4().hex
    youtube_id = _youtube_id_from_url(url)
    job = {"id": job_id, "username": user["username"], "youtube_id": youtube_id, "url": url, "destination": payload.destination, "status": "queued", "stage": "다운로드 대기 중", "percent": 0, "message": "다운로드 대기 중", "current_file": "", "created_at": now, "updated_at": now}
    _mp3_download_jobs[job_id] = job
    conn = get_conn()
    conn.execute(
        """INSERT INTO mp3_download_jobs
           (id,username,youtube_id,url,destination,status,stage,percent,current_file,created_at,updated_at)
           VALUES(?,?,?,?,?,'queued','다운로드 대기 중',0,'',?,?)""",
        (job_id, user["username"], youtube_id or None, url, payload.destination, now, now),
    )
    conn.commit()
    conn.close()
    threading.Thread(target=_run_youtube_mp3_job, args=(job_id, url, payload.destination, user["username"]), daemon=True, name=f"youtube-mp3-{job_id[:6]}").start()
    return JSONResponse(job, status_code=202)


# ★ 2026-09-15: "미연시 시스템 하나 만들어봤으면 좋겠어" 요청 — 선택지+호감도+
# 멀티 엔딩 구조의 작은 연애 시뮬레이션. career/vocabulary와 같은 패턴으로
# 독립 미니앱을 마운트한다. 로그인 계정마다 진행 상태가 따로 저장된다.
@app.get("/dating-sim")
def dating_sim_redirect():
    return RedirectResponse("/dating-sim/", status_code=307)


@app.get("/dating-sim/")
def dating_sim_dashboard(request: Request):
    _require_signed_in_user(request)
    return FileResponse(str(DATING_SIM_WEB_DIR / "index.html"),
                        headers={"Cache-Control": "private, no-store"})


@app.get("/dating-sim/static/{filename:path}")
def dating_sim_static(filename: str, request: Request):
    _require_signed_in_user(request)
    allowed = {
        "style.css", "app.js", "soi.png", "soi-park.png", "soi-school.png",
        "haru.png", "haru-first.png", "haru-walk.png", "akari.png", "mio.png", "reina.png",
        "pixel-cafe.png", "pixel-park.png", "pixel-school.png", "pixel-message.png",
        "static/sone-486/office-first-meeting.png",
        "static/sone-486/rainy-evening.png",
        "static/sone-486/message-received.png",
    }
    if filename not in allowed:
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다")
    target = DATING_SIM_WEB_DIR / filename
    if not target.is_file():
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다")
    return FileResponse(str(target), headers={"Cache-Control": "private, no-store"})


@app.get("/dating-sim/audio/{filename}")
def dating_sim_audio(filename: str, request: Request):
    """로그인 사용자에게 생성된 미연시 음성과 매니페스트만 제공한다."""
    _require_signed_in_user(request)
    if filename == "manifest.json":
        target = DATING_SIM_AUDIO_DIR / filename
    elif re.fullmatch(r"[0-9a-f]{20}\.mp3", filename):
        target = DATING_SIM_AUDIO_DIR / filename
    else:
        raise HTTPException(status_code=404, detail="음성 파일을 찾을 수 없습니다")
    if not target.is_file():
        raise HTTPException(status_code=404, detail="음성 파일을 찾을 수 없습니다")
    return FileResponse(str(target))


@app.get("/api/dating-sim/tts")
async def dating_sim_tts(
    request: Request,
    text: str = Query(min_length=1, max_length=400),
    role: str = Query(default="female"),
    language: str = Query(default="ja"),
):
    """매니페스트에 없는 대사도 Edge TTS로 즉시 만들어 재생한다.

    작품별 생성 시나리오는 현재 약 2만 개 발화로 늘어 사전 생성 목록만으로는
    누락이 생긴다. 로그인 사용자 요청만 받고, 언어·역할·본문 해시로 캐시해
    같은 문장은 다시 생성하지 않는다.
    """
    _require_signed_in_user(request)
    if role not in {"female", "male"}:
        raise HTTPException(status_code=400, detail="지원하지 않는 음성 역할입니다")
    if language not in {"ja", "ko", "en"}:
        raise HTTPException(status_code=400, detail="지원하지 않는 음성 언어입니다")
    cleaned = re.sub(r"\s+", " ", text).strip()
    if not cleaned:
        raise HTTPException(status_code=400, detail="읽을 문장이 없습니다")
    digest = hashlib.sha256(f"edge-v1\0{language}\0{role}\0{cleaned}".encode("utf-8")).hexdigest()[:20]
    target = DATING_SIM_AUDIO_DIR / f"{digest}.mp3"

    def ensure_clip():
        if target.is_file() and target.stat().st_size:
            return
        with _dating_sim_tts_lock:
            if target.is_file() and target.stat().st_size:
                return
            audio = dating_audio.request_edge_speech(role, cleaned, language=language)
            temporary = target.with_suffix(".mp3.tmp")
            temporary.write_bytes(audio)
            temporary.replace(target)

    try:
        await asyncio.to_thread(ensure_clip)
    except Exception as error:
        raise HTTPException(status_code=502, detail="음성을 생성하지 못했습니다") from error
    return FileResponse(str(target), media_type="audio/mpeg", headers={"Cache-Control": "private, max-age=31536000"})


@app.get("/api/dating-sim/books/{book_id}/images/{filename}")
def dating_sim_generated_image(book_id: str, filename: str, request: Request):
    """로그인 사용자에게 작품 이미지 에이전트가 등록한 결과만 제공한다."""
    _require_signed_in_user(request)
    target = dating_sim_story.generated_image_path(book_id, filename)
    if not target:
        raise HTTPException(status_code=404, detail="장면 이미지를 찾을 수 없습니다")
    return FileResponse(str(target), media_type="image/png")


@app.get("/api/dating-sim/books/{book_id}/admin-images/{filename}")
def dating_sim_generated_admin_image(book_id: str, filename: str, request: Request):
    """관리자 프롬프트 결과는 소유자 세션에만 제공한다."""
    _require_owner(request)
    target = dating_sim_story.generated_admin_image_path(book_id, filename)
    if not target:
        raise HTTPException(status_code=404, detail="관리자 이미지를 찾을 수 없습니다")
    return FileResponse(str(target), media_type="image/png",
                        headers={"Cache-Control": "private, no-store"})


@app.get("/api/dating-sim/books/{book_id}/image-references/{filename}")
def dating_sim_generated_image_reference(book_id: str, filename: str, request: Request):
    """시나리오 트리의 생성 이력에서만 쓰는 원본 표지 참조 이미지."""
    _require_owner(request)
    target = dating_sim_story.generated_image_reference_path(book_id, filename)
    if not target:
        raise HTTPException(status_code=404, detail="참고 이미지를 찾을 수 없습니다")
    return FileResponse(str(target))


@app.get("/api/dating-sim/books/{book_id}/quality-attempts/{filename}")
def dating_sim_generated_quality_attempt(book_id: str, filename: str, request: Request):
    """관리자에게만 시도별 품질검수 후보 이미지를 제공한다."""
    _require_owner(request)
    target = dating_sim_story.generated_quality_attempt_path(book_id, filename)
    if not target:
        raise HTTPException(status_code=404, detail="품질검수 후보 이미지를 찾을 수 없습니다")
    return FileResponse(str(target), media_type="image/png",
                        headers={"Cache-Control": "private, no-store"})


class DatingSimLocationRequest(BaseModel):
    location: str
    story_id: str | None = None
    adult_mode: bool = False


class DatingSimChoiceRequest(BaseModel):
    choice_index: int
    story_id: str | None = None
    adult_mode: bool = False


class DatingSimRestartRequest(BaseModel):
    story_id: str | None = None
    difficulty: str | None = None
    adult_mode: bool = False


class DatingSimNewRequest(BaseModel):
    difficulty: str = "normal"
    story_id: str | None = None


class DatingSimWritingCompleteRequest(BaseModel):
    story_id: str
    day: int
    scene_key: str
    line_count: int
    average_score: int


DATING_DIFFICULTIES = {
    # 첫 만남부터 친밀도가 높게 보이지 않도록 모든 난이도의 시작값을
    # 10점 이하로 제한한다. 같은 난이도 안에서는 인물마다 첫인상이 조금씩
    # 달라지되, 하드는 요청대로 정확히 0점에서 시작한다.
    "easy": {"label": "이지", "start": (7, 10), "positive": 1.25, "negative": 0.55},
    "normal": {"label": "노말", "start": (3, 7), "positive": 1.0, "negative": 1.0},
    "hard": {"label": "하드", "start": (0, 0), "positive": 0.35, "negative": 1.0},
}


def _dating_difficulty(value):
    return value if value in DATING_DIFFICULTIES else "normal"


def _dating_start_affection(story, difficulty):
    difficulty = _dating_difficulty(difficulty)
    low, high = DATING_DIFFICULTIES[difficulty]["start"]
    if low == high:
        return low
    heroine_key = ":".join([
        story.get("id", ""), story.get("name", ""),
        story.get("character_name_ko", ""), difficulty,
    ])
    seed = int.from_bytes(hashlib.sha256(heroine_key.encode()).digest()[:4], "big")
    return low + seed % (high - low + 1)


def _dating_apply_affection_delta(raw_delta, difficulty):
    config = DATING_DIFFICULTIES[_dating_difficulty(difficulty)]
    multiplier = config["positive" if raw_delta > 0 else "negative"]
    adjusted = int(round(raw_delta * multiplier))
    if raw_delta > 0:
        return max(1, adjusted)
    if raw_delta < 0:
        return min(-1, adjusted)
    return 0


def _dating_relationship_tone(affection):
    bands = [
        (9, "경멸", "말투가 날카롭고 거리를 분명히 둡니다."),
        (19, "냉담", "차갑고 짧게 대답합니다."),
        (29, "경계", "의심을 풀지 않고 조심스럽게 반응합니다."),
        (39, "격식", "예의를 지키지만 사적인 거리를 둡니다."),
        (49, "중립", "담담하게 대화를 이어갑니다."),
        (59, "호기심", "조금씩 관심을 보이기 시작합니다."),
        (69, "친근", "편안하고 다정하게 반응합니다."),
        (79, "설렘", "수줍은 호감과 귀여운 반응이 늘어납니다."),
        (89, "애정", "애교 있고 적극적인 애정을 보입니다."),
        (100, "깊은 애정", "신뢰와 친밀감을 솔직하게 표현합니다."),
    ]
    for maximum, label, description in bands:
        if affection <= maximum:
            return {"band": maximum // 10, "label": label, "description": description}
    return {"band": 10, "label": "깊은 애정", "description": bands[-1][2]}


def _dating_story(story_id=None, variant_seed=None):
    # ★ 2026-09-15: "스토리 시나리오전개쪽에서 데이터베이스 만들어줘" 요청 —
    # 기본 캐릭터(소이)는 이제 DB(dating_sim_scenarios 등)에서 요일·장소별
    # 여러 변형 중 하나를 고른다. 사용자·회차 키가 같으면 진행 중인 장면이
    # 조회 사이에 바뀌지 않는다. EPUB 영감 이야기(book:...)는
    # 여전히 절대 DB에 안 담고 그때그때 안전한 템플릿으로 만든다(기존 방식).
    if not story_id:
        conn = get_conn()
        try:
            dating_sim_story.seed_dating_sim_content(conn)
            run_row = conn.execute(
                "SELECT scenario_run FROM dating_sim_progress WHERE username=? AND character_id=?",
                (variant_seed or "", dating_sim_story.CHARACTER_ID),
            ).fetchone()
            scenario_run = int(run_row["scenario_run"]) if run_row else 0
            story = dating_sim_story.load_story_from_db(
                conn, dating_sim_story.CHARACTER_ID,
                seed_key=f"{variant_seed or ''}:run-{scenario_run}",
            )
        finally:
            conn.close()
        if story:
            return story
    try:
        return dating_sim_story.story_for(story_id, seed_key=variant_seed)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _dating_story_signature(story):
    """이미지·표시 순서와 무관한 시나리오 본문 서명.

    사용자별로 선택지 표시 순서가 뒤집혀도 같은 이야기로 취급하되, 실제
    대사·선택지·학습 재료가 재생성되면 다른 이야기로 판정한다.
    """
    scenes = {}
    for day, day_scenes in sorted(story.get("scenes", {}).items(), key=lambda item: int(item[0])):
        scenes[str(day)] = {}
        for location, scene in sorted(day_scenes.items()):
            choices = sorted(
                [
                    {"text": choice.get("text", ""), "affection": choice.get("affection", 0)}
                    for choice in scene.get("choices", [])
                ],
                key=lambda choice: (choice["text"], choice["affection"]),
            )
            scenes[str(day)][location] = {
                "lines": scene.get("lines", []),
                "choices": choices,
                "vocab_words": scene.get("vocab_words", []),
                "expressions_used": scene.get("expressions_used", []),
                "grammar_used": scene.get("grammar_used", []),
            }
    source = {
        "story_id": story.get("id"),
        "total_days": story.get("total_days"),
        "scenes": scenes,
    }
    encoded = json.dumps(source, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _dating_affection_cap(day, total_days, completed=False, start_affection=50):
    """이야기 진행도에 맞춰 현재 도달 가능한 최대 호감도를 계산한다.

    선택한 난이도와 인물별 시작값에서 출발해 장면을 하나 마칠 때마다 전체
    분량에 비례해 상한이 열린다. 완결 전에는 절대 100이 되지 않고, 마지막
    선택까지 마친 뒤에만 100에 도달할 수 있다.
    """
    total_days = max(1, int(total_days or 1))
    if completed:
        return 100
    completed_scenes = max(0, min(total_days - 1, int(day or 1) - 1))
    start_affection = max(0, min(99, int(start_affection)))
    return start_affection + ((100 - start_affection) * completed_scenes // total_days)


def _dating_sim_row(conn, username, story):
    story_signature = _dating_story_signature(story)
    row = conn.execute(
        "SELECT * FROM dating_sim_progress WHERE username=? AND character_id=?",
        (username, story["id"]),
    ).fetchone()
    if row:
        row = dict(row)
        saved_signature = row.get("story_signature")
        if saved_signature and saved_signature != story_signature:
            now = _now()
            difficulty = _dating_difficulty(row.get("difficulty"))
            start_affection = _dating_start_affection(story, difficulty)
            conn.execute(
                "UPDATE dating_sim_progress SET day=1,affection=?,pending_location=NULL,"
                "completed=0,ending_id=NULL,route_state='{}',story_signature=?,updated_at=? "
                "WHERE username=? AND character_id=?",
                (start_affection, story_signature, now, username, story["id"]),
            )
            conn.execute(
                "DELETE FROM dating_sim_learning_seen WHERE username=? AND character_id=?",
                (username, story["id"]),
            )
            conn.commit()
            row.update(day=1, affection=start_affection, pending_location=None, completed=0, route_state="{}",
                       ending_id=None, story_signature=story_signature, updated_at=now)
        elif not saved_signature:
            # 기존 DB는 현재 내용을 기준점으로 한 번만 등록한다. 이후 내용이
            # 바뀔 때부터 자동 초기화되므로 정상적인 과거 진행은 보존된다.
            conn.execute(
                "UPDATE dating_sim_progress SET story_signature=? "
                "WHERE username=? AND character_id=?",
                (story_signature, username, story["id"]),
            )
            conn.commit()
            row["story_signature"] = story_signature
        if row["completed"] and row["day"] <= story["total_days"]:
            conn.execute(
                "UPDATE dating_sim_progress SET completed=0,ending_id=NULL,pending_location=NULL,updated_at=? "
                "WHERE username=? AND character_id=?",
                (_now(), username, story["id"]),
            )
            conn.commit()
            row.update(completed=0, ending_id=None, pending_location=None)
        # 예전에는 선택지 점수를 진행도와 무관하게 누적해 초반에도 호감도
        # 100이 저장될 수 있었다. 미완결 기록만 현재 진행 단계의 상한으로
        # 한 번 보정하며, 낮은 점수와 정상 완결 기록은 그대로 보존한다.
        start_affection = _dating_start_affection(story, _dating_difficulty(row.get("difficulty")))
        affection_cap = _dating_affection_cap(
            row["day"], story["total_days"], bool(row["completed"]), start_affection
        )
        if not row["completed"] and row["affection"] > affection_cap:
            now = _now()
            conn.execute(
                "UPDATE dating_sim_progress SET affection=?,updated_at=? "
                "WHERE username=? AND character_id=?",
                (affection_cap, now, username, story["id"]),
            )
            conn.commit()
            row.update(affection=affection_cap, updated_at=now)
        return row
    now = _now()
    difficulty = _dating_difficulty(story.pop("_requested_difficulty", "normal"))
    start_affection = _dating_start_affection(story, difficulty)
    conn.execute(
        "INSERT INTO dating_sim_progress "
        "(username,character_id,day,affection,pending_location,completed,ending_id,"
        "created_at,updated_at,story_signature,difficulty,route_state) "
        "VALUES (?,?,1,?,NULL,0,NULL,?,?,?,?, '{}')",
        (username, story["id"], start_affection, now, now, story_signature, difficulty),
    )
    conn.commit()
    return {
        "username": username, "character_id": story["id"],
        "day": 1, "affection": start_affection, "pending_location": None, "completed": 0,
        "difficulty": difficulty,
        "ending_id": None, "story_signature": story_signature, "route_state": "{}",
    }


def _dating_materials(story):
    """이야기 전체에서 실제로 쓰이는 고유 학습 단어·표현·문법 목록."""
    materials = set()
    for day_scenes in story.get("scenes", {}).values():
        for scene in day_scenes.values():
            for word in scene.get("vocab_words") or ([scene["vocab"]] if scene.get("vocab") else []):
                if word.get("ja"):
                    materials.add(("vocabulary", word["ja"]))
            for expression in scene.get("expressions_used") or []:
                if expression.get("ja"):
                    materials.add(("expression", expression["ja"]))
            for grammar in scene.get("grammar_used") or []:
                if grammar.get("pattern"):
                    materials.add(("grammar", grammar["pattern"]))
    return materials


def _dating_mark_scene_seen(conn, username, story, scene):
    now = _now()
    rows = []
    for word in scene.get("vocab_words") or ([scene["vocab"]] if scene.get("vocab") else []):
        if word.get("ja"):
            rows.append((username, story["id"], "vocabulary", word["ja"], now))
    for expression in scene.get("expressions_used") or []:
        if expression.get("ja"):
            rows.append((username, story["id"], "expression", expression["ja"], now))
    for grammar in scene.get("grammar_used") or []:
        if grammar.get("pattern"):
            rows.append((username, story["id"], "grammar", grammar["pattern"], now))
    if rows:
        conn.executemany(
            "INSERT OR IGNORE INTO dating_sim_learning_seen "
            "(username,character_id,material_type,material_key,seen_at) VALUES (?,?,?,?,?)",
            rows,
        )


def _dating_learning_progress(username, story):
    total_materials = _dating_materials(story)
    if not total_materials:
        return {"seen": 0, "total": 0, "percent": 100}
    conn = get_conn()
    try:
        seen = {
            (row["material_type"], row["material_key"])
            for row in conn.execute(
                "SELECT material_type,material_key FROM dating_sim_learning_seen "
                "WHERE username=? AND character_id=?",
                (username, story["id"]),
            ).fetchall()
        }
    finally:
        conn.close()
    count = len(total_materials & seen)
    return {"seen": count, "total": len(total_materials), "percent": round(count / len(total_materials) * 100)}


_DATING_ORDERED_SCENE_KEYS = ("first", "walk", "quiet")


def _dating_ordered_scene_keys(story, day):
    """생성 시나리오의 한 흐름 안에서 재생해야 할 장면 순서를 돌려준다.

    기존 수동 시나리오는 하루에 cafe/park/school 중 하나를 고르는 구조이므로
    first/walk/quiet가 둘 이상 있는 생성 시나리오에만 연속 재생을 적용한다.
    """
    day_scenes = story.get("scenes", {}).get(day, {})
    keys = [key for key in _DATING_ORDERED_SCENE_KEYS if key in day_scenes]
    return keys if len(keys) >= 2 else []


def _dating_next_scene(story, day, current_scene):
    ordered = _dating_ordered_scene_keys(story, day)
    if current_scene in ordered:
        index = ordered.index(current_scene)
        if index + 1 < len(ordered):
            return day, ordered[index + 1], False
    next_day = day + 1
    return next_day, None, next_day > story["total_days"]


def _dating_admin_scene_image(story, day, location):
    active_ids = _active_dating_sim_admin_prompt_ids()
    images = [item for item in ((story.get("generated_images") or {}).get("admin_gallery") or [])
              if str(item.get("key") or "").removeprefix("admin:") in active_ids
              and item.get("image_url")]
    if not images:
        return None
    key = f"{story.get('id')}:{day}:{location}"
    index = int.from_bytes(hashlib.sha256(key.encode()).digest()[:4], "big") % len(images)
    return images[index]["image_url"]


def _dating_scene_image(story, day, location, adult_mode=False):
    """현재 장면 이미지와 재생성에 사용할 정확한 매니페스트 키를 고른다.

    신고 예약이 처리 중인 키는 후보에서 제외한다. 관리자 이미지를 켠 경우에는
    관리자 이미지를 우선하고, 남은 관리자 후보가 없을 때 일반 이미지로
    내려간다. 일반 모드에서는 언제나 일반 이미지가 우선이다.
    """
    generated = story.get("generated_images") or {}
    reported = _pending_dating_sim_image_report_keys(story.get("id") or "")
    regular = [item for item in (generated.get("gallery") or [])
               if item.get("image_url") and item.get("key") not in reported]
    active_ids = _active_dating_sim_admin_prompt_ids()
    admin = [item for item in (generated.get("admin_gallery") or [])
             if item.get("image_url") and item.get("key") not in reported
             and str(item.get("key") or "").removeprefix("admin:") in active_ids]
    scene = story.get("scenes", {}).get(day, {}).get(location, {})
    default_url = (scene.get("character_image")
                   or story.get("character_images", {}).get(location)
                   or story.get("character_image"))
    default_item = next((item for item in (generated.get("gallery") or [])
                         if item.get("image_url") == default_url), None)
    if adult_mode:
        preferred_admin_url = _dating_admin_scene_image(story, day, location)
        preferred_admin_item = next(
            (item for item in (generated.get("admin_gallery") or [])
             if item.get("image_url") == preferred_admin_url), None,
        )
        if preferred_admin_url and (
            preferred_admin_item is None or preferred_admin_item.get("key") not in reported
        ):
            return (preferred_admin_url,
                    preferred_admin_item.get("key") if preferred_admin_item else None, True)
    if adult_mode and admin:
        key = f"{story.get('id')}:{day}:{location}"
        selected = admin[int.from_bytes(hashlib.sha256(key.encode()).digest()[:4], "big") % len(admin)]
        return selected["image_url"], selected.get("key"), True
    if default_item and default_item.get("key") not in reported:
        return default_url, default_item.get("key"), False
    if regular:
        key = f"{story.get('id')}:{day}:{location}:fallback"
        selected = regular[int.from_bytes(hashlib.sha256(key.encode()).digest()[:4], "big") % len(regular)]
        return selected["image_url"], selected.get("key"), False
    if default_item and default_item.get("key") in reported:
        return "/dating-sim/static/reina.png", None, False
    return default_url, default_item.get("key") if default_item else None, False


def _dating_sim_state_payload(row, story, username=None, is_admin=False, adult_mode=False):
    completed = bool(row["completed"])
    current_day = min(row["day"], story["total_days"])
    try:
        route_state = json.loads(row.get("route_state") or "{}")
    except (TypeError, ValueError):
        route_state = {}
    dominant_route = (max(route_state, key=lambda axis: (route_state[axis], axis))
                      if route_state and max(route_state.values()) > 0 else None)
    # ★ 2026-09-16: "미연시 시스템 누를때마다 인트로가 똑같은데 다양하게
    # 전개시작할수있게 무작위성좀 추가하면 좋겠어" 요청 — 아직 오늘 장소를
    # 안 고른 상태(pending_location 없음)라면 진행 일관성과 무관한 순수
    # 도입부 문구이므로 매번 새로 무작위 선택한다. 장소를 이미 골라 장면이
    # 진행 중이면(재조회해도 같은 장면이어야 하므로) 기존의 결정론적
    # 문구를 그대로 쓴다.
    day_opening = (
        story.get("day_openings", {}).get(current_day) if row["pending_location"]
        else dating_sim_story.random_daily_opening(
            current_day,
            story.get("character_dialogue_name_jp", story["name"]),
            story.get("character_dialogue_name_ko", story.get("character_name_ko", "소이")),
        )
    )
    _source_book_id, source_work_dir = dating_sim_story.resolve_book_work_dir(story.get("id", ""))
    source_video = _source_video_metadata(source_work_dir)
    payload = {
        "story_id": story["id"], "story_title": story["title"],
        "source_title": story.get("source_title"),
        "source_work_code": story.get("source_work_code", ""),
        "source_video_url": source_video.get("url"),
        "character_name": story["name"],
        "character_name_ko": story.get("character_name_ko", ""),
        "character_image": story.get("character_image"),
        "character_persona": story.get("character_persona"),
        "persona_disclaimer": story.get("persona_disclaimer"),
        "day": current_day, "total_days": story["total_days"],
        "affection": row["affection"],
        "difficulty": _dating_difficulty(row.get("difficulty")),
        "difficulty_label": DATING_DIFFICULTIES[_dating_difficulty(row.get("difficulty"))]["label"],
        "relationship_tone": _dating_relationship_tone(row["affection"]),
        "day_opening": day_opening,
        "locations": [
            {
                "id": key,
                **value,
                "action": story.get("map_actions", {}).get(
                    min(row["day"], story["total_days"]), {}
                ).get(key, value["label"]),
            }
            for key, value in story["locations"].items()
        ],
        "pending_location": row["pending_location"],
        "completed": completed,
    }
    if username is not None:
        payload["learning_progress"] = _dating_learning_progress(username, story)
    if row["pending_location"] and not completed:
        selected_location = row["pending_location"]
        scene = story["scenes"][row["day"]][selected_location]
        # ★ 2026-09-19: AI 생성 시나리오는 요일 나레이션도 작품별로 새로
        # 만들므로, 있으면 그 작품 나레이션을 쓰고 없으면 고정 템플릿을 쓴다.
        ordered = _dating_ordered_scene_keys(story, row["day"])
        is_flow_opening = not ordered or selected_location == ordered[0]
        scene_lines = []
        if is_flow_opening:
            day_narration = (story.get("day_narration", {}).get(row["day"])
                             or dating_sim_story.DAY_NARRATION.get(row["day"], ""))
            route_hook = (story.get("route_hooks", {}).get(row["day"], {}).get(dominant_route)
                          if dominant_route else None)
            if route_hook:
                day_narration = f"{route_hook}\n{day_narration}"
            scene_lines.append({"speaker": "narrator", "text": day_narration})
        for line in scene["lines"]:
            speaker = "narrator" if line.lstrip().startswith("(") else "character"
            scene_lines.append({"speaker": speaker, "text": line})
        selected_image, selected_image_key, selected_admin_image = _dating_scene_image(
            story, row["day"], row["pending_location"], is_admin and adult_mode,
        )
        payload["scene"] = {
            "location": row["pending_location"],
            "character_image": selected_image,
            "character_image_key": selected_image_key,
            "admin_prompt_image": selected_admin_image,
            "lines": scene_lines,
            "choices": [{"text": choice["text"]} for choice in scene["choices"]],
            # 한 장면에 여러 학습 단어가 들어갈 수 있어(생성 시나리오) 목록으로
            # 보낸다. 하위 호환을 위해 단수 vocab(첫 단어)도 유지한다.
            "vocab": scene.get("vocab"),
            "vocab_words": scene.get("vocab_words") or ([scene["vocab"]] if scene.get("vocab") else []),
            "expressions_used": scene.get("expressions_used") or [],
        }
    if completed:
        try:
            route_state = json.loads(row.get("route_state") or "{}")
        except (TypeError, ValueError):
            route_state = {}
        payload["ending"] = dating_sim_story.ending_for(story, row["affection"], route_state)
    return payload


@app.get("/api/dating-sim/state")
def dating_sim_state(request: Request, story_id: str | None = None, adult_mode: bool = False):
    _require_signed_in_user(request)
    username = _request_username(request)
    conn = get_conn()
    try:
        story = _dating_story(story_id, username)
        row = _dating_sim_row(conn, username, story)
    finally:
        conn.close()
    payload = _dating_sim_state_payload(row, story, username, _is_owner_request(request), adult_mode)
    # ★ 2026-09-18: 관리자만 시나리오 트리 버튼을 볼 수 있게 소유자 여부를
    # 상태에 실어 준다(트리 엔드포인트 자체도 소유자만 허용하므로 이중 방어).
    payload["is_admin"] = _is_owner_request(request)
    return payload


DATING_SCENE_WRITING_REMINDER = "✍️ 미연시 한 장면 대사 쓰기"


@app.post("/api/dating-sim/writing-complete")
def dating_sim_writing_complete(body: DatingSimWritingCompleteRequest, request: Request):
    """장면 전체 필기 완료를 보존하고 소유자의 오늘 퀘스트를 자동 체크한다."""
    _require_signed_in_user(request)
    story_id = str(body.story_id or "").strip()
    scene_key = str(body.scene_key or "").strip()
    if not story_id or len(story_id) > 200 or not scene_key or len(scene_key) > 120:
        raise HTTPException(status_code=422, detail="장면 식별값이 올바르지 않습니다")
    if not 1 <= body.day <= 999 or not 1 <= body.line_count <= 200:
        raise HTTPException(status_code=422, detail="완료한 장면 정보가 올바르지 않습니다")
    if not 1 <= body.average_score <= 100:
        raise HTTPException(status_code=422, detail="쓰기 점수가 올바르지 않습니다")

    username = _request_username(request)
    completed_at = datetime.datetime.now()
    completed_date = completed_at.date().isoformat()
    conn = get_conn()
    try:
        before = conn.total_changes
        conn.execute(
            "INSERT OR IGNORE INTO dating_sim_writing_completions "
            "(username,completed_date,story_id,day,scene_key,line_count,average_score,created_at) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (username, completed_date, story_id, body.day, scene_key,
             body.line_count, body.average_score, completed_at.isoformat(timespec="seconds")),
        )
        newly_recorded = conn.total_changes > before
        conn.commit()
    finally:
        conn.close()

    reminder_checked = False
    quest_awarded = False
    sync_error = None
    if _is_owner_request(request):
        try:
            result = _set_shift_alarm_reminder_checked(
                DATING_SCENE_WRITING_REMINDER,
                True,
                allowed_labels=(DATING_SCENE_WRITING_REMINDER,),
                source="dating_scene_writing",
            )
            reminder_checked = True
            quest_awarded = bool(result.get("quest_awarded"))
        except Exception:
            # 필기 기록 자체는 보존한다. Notion/상태 파일이 잠시 늦더라도 사용자가
            # 같은 장면을 다시 써야 하지 않도록 동기화 실패만 별도로 알린다.
            sync_error = "Shift Alarm 자동 체크가 지연되고 있습니다"
    return {
        "ok": True,
        "recorded": newly_recorded,
        "completed_date": completed_date,
        "reminder_checked": reminder_checked,
        "quest_awarded": quest_awarded,
        "quest_xp": 10 if quest_awarded else 0,
        "sync_error": sync_error,
    }


@app.get("/api/dating-sim/teacher-tip")
def dating_sim_teacher_tip(request: Request, story_id: str | None = None):
    """현재 장면과 겹치는 일본어 선생님의 실제 과거 발언을 짧게 돌려준다."""
    _require_owner(request)
    username = _request_username(request)
    story = _dating_story(story_id, username)
    conn = get_conn()
    try:
        row = _dating_sim_row(conn, username, story)
        terms = []
        if row.get("pending_location") and not row.get("completed"):
            scene = story["scenes"].get(row["day"], {}).get(row["pending_location"], {})
            for line in scene.get("lines") or []:
                terms.append(("line", line))
            vocab_items = scene.get("vocab_words") or ([scene.get("vocab")] if scene.get("vocab") else [])
            for vocab in vocab_items:
                if isinstance(vocab, dict):
                    terms.extend(("vocab", value) for value in (vocab.get("ja"), vocab.get("word")))
            for expression in scene.get("expressions_used") or []:
                if isinstance(expression, dict):
                    terms.extend(("expression", value) for value in (expression.get("ja"), expression.get("text")))
                else:
                    terms.append(("expression", expression))
        candidates = conn.execute(
            "SELECT id,room_id,content FROM messages WHERE sender=? ORDER BY id DESC LIMIT 500",
            ("일본어 선생님",),
        ).fetchall()
        persona = conn.execute(
            "SELECT avatar_url FROM personas WHERE name=?", ("일본어 선생님",)
        ).fetchone()
    finally:
        conn.close()
    # 작품 제목만 같거나 짧은 번역어가 우연히 겹치는 것은 장면 관련 설명이
    # 아니다. 현재 장면에 실제로 쓰인 일본어 표기만 남기고, 한 글자짜리
    # 표기는 오탐 가능성이 높아 제외한다.
    common_terms = {"今日", "昨日", "明日", "本当", "何か", "大丈夫", "自分", "時間", "一緒", "今から"}
    needles = []
    for kind, value in terms:
        term = str(value or "").strip()
        term = re.sub(r"\[([^\]|]+)\|[^\]]+\]", r"\1", term)
        term = re.sub(r"([\u3400-\u9fff々〆ヶ]+)\{[\u3040-\u30ffー]+\}", r"\1", term)
        compact = re.sub(r"[\s、。！？!?「」『』…・]", "", term)
        has_kanji = bool(re.search(r"[\u3400-\u9fff]", compact))
        if not re.search(r"[\u3040-\u30ff\u3400-\u9fff]", compact):
            continue
        if compact in common_terms:
            continue
        if (has_kanji and len(compact) < 2) or (not has_kanji and len(compact) < 4):
            continue
        if kind == "line" and len(compact) < 6:
            continue
        if not any(existing[1] == compact for existing in needles):
            needles.append((kind, compact))
    best = None
    for candidate in candidates:
        content = candidate["content"] or ""
        searchable = re.sub(r"\[([^\]|]+)\|[^\]]+\]", r"\1", content)
        searchable = re.sub(r"([\u3400-\u9fff々〆ヶ]+)\{[\u3040-\u30ffー]+\}", r"\1", searchable)
        searchable = re.sub(r"[\s、。！？!?「」『』…・]", "", searchable).casefold()
        matches = [(kind, term) for kind, term in needles if term.casefold() in searchable]
        score = sum(
            (14 + len(term)) if kind == "line" else
            (10 + len(term)) if kind == "expression" else (2 + min(len(term), 6))
            for kind, term in matches
        )
        # 단어 하나만 우연히 겹친 메시지는 제외한다. 정확한 대사·표현 하나 또는
        # 서로 다른 학습 단어 두 개 이상이 함께 있어야 장면 관련 설명으로 본다.
        strong_match = any(kind in ("line", "expression") for kind, _term in matches)
        if not strong_match and len(matches) < 2:
            continue
        if best is None or score > best[0]:
            best = (score, candidate, max(matches, key=lambda item: len(item[1]))[1])
    if best:
        _score, candidate, matched = best
        content = candidate["content"] or ""
        clean = re.sub(r"https?://\S+", "", content)
        clean = re.sub(r"\[\[/?(?:blue|red)\]\]", "", clean)
        clean = re.sub(r"\s+", " ", clean).strip()
        index = clean.casefold().find(matched.casefold())
        start = max(0, index - 90)
        end = min(len(clean), index + len(matched) + 150)
        excerpt = clean[start:end].strip(" ·-/")
        if start:
            excerpt = "…" + excerpt
        if end < len(clean):
            excerpt += "…"
        return {
            "content": excerpt,
            "avatar_url": persona["avatar_url"] if persona else None,
            "matched_term": matched,
            "source_room_id": candidate["room_id"],
            "source_message_id": candidate["id"],
        }
    return {"content": None, "avatar_url": persona["avatar_url"] if persona else None,
            "source_room_id": None, "source_message_id": None}


@app.get("/api/dating-sim/scenario-tree")
def dating_sim_scenario_tree(request: Request, story_id: str | None = None):
    """★ 2026-09-18: 관리자 전용 — 한 이야기의 전체 시나리오 구조(요일·장소·
    대사·선택지·호감도·EPUB 학습 단어 삽입 위치)를 진행 상태 변경 없이
    돌려준다. 진행 저장 경로(_dating_sim_row)를 아예 타지 않아 조회만으로는
    DB가 바뀌지 않는다."""
    _require_owner(request)
    username = _request_username(request)
    try:
        tree = dating_sim_story.scenario_tree(story_id, seed_key=username)
        generated = tree.get("generated_images") or {}
        active_ids = _active_dating_sim_admin_prompt_ids()
        generated["admin_gallery"] = [
            item for item in (generated.get("admin_gallery") or [])
            if str(item.get("key") or "").removeprefix("admin:") in active_ids
        ]
        tree["generated_images"] = generated
        tree["admin_prompts_count"] = len(active_ids)
        tree["gif_count"] = len(_dating_gif_files(tree))
        # 생성 당시 기록과 현재 재생성 기본값을 구분해 전달한다.
        tree["prompt_settings"] = _read_dating_sim_prompt_settings()
        return tree
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


# ★ 2026-09-29: 영상 주소 하나로 다운로드→자막→번역→EPUB→미연시→이미지를
# 다시 만드는 관리자 전용 안전 파이프라인. AI에는 실행 권한을 주지 않고 고정된
# 파이썬 워커만 승인된 계획 파일을 실행한다. 기존 결과는 검증 성공 뒤에만 교체한다.
DATING_REBUILD_DIR = Path(os.path.expanduser("~/.tulpachat/dating_full_rebuild"))
DATING_REBUILD_WORKER = REPO_ROOT / "일본어자막추출" / "rebuild_dating_sim_from_video.py"
SOURCE_VIDEO_METADATA = "source_video.json"
DATING_GIF_DIR = Path("/Users/forrestdpark/Desktop/BlogImage/AV_gif")
_DATING_REBUILD_RECOVERY_STARTED = False
_DATING_REBUILD_RECOVERY_LOCK = threading.Lock()


class DatingFullRebuildRequest(BaseModel):
    story_id: str
    video_url: str


class DatingFullRebuildApproveRequest(BaseModel):
    plan_id: str


class DatingFullRebuildRetryDecision(BaseModel):
    plan_id: str
    decision: str


def _dating_rebuild_diagnosis(work_dir: Path):
    srt_cues = 0
    for path in work_dir.glob("*.srt"):
        try:
            srt_cues = max(srt_cues, len(re.findall(r"(?m)^\d+\s*$", path.read_text(encoding="utf-8", errors="ignore"))))
        except OSError:
            pass
    jsonl_lines = 0
    for path in work_dir.glob("transcript*.jsonl"):
        try:
            jsonl_lines += sum(1 for line in path.read_text(encoding="utf-8", errors="ignore").splitlines() if line.strip())
        except OSError:
            pass
    references = len(dating_sim_story.reference_candidates(work_dir))
    scenario_path = work_dir / "dating_sim_scenario.json"
    scenario_lines = 0
    try:
        scenario_text = scenario_path.read_text(encoding="utf-8")
        scenario_lines = len(re.findall(r'"(?:ja|text)"\s*:', scenario_text))
    except OSError:
        pass
    reasons = []
    if max(srt_cues, jsonl_lines) < 30:
        reasons.append("원본 자막 추출량이 적어 EPUB에 넣을 대사 자체가 부족합니다.")
    if references < 8:
        reasons.append(f"원작 참고 이미지가 {references}장만 보존되어 장면·인물 선별 폭도 좁습니다.")
    if scenario_lines < 20:
        reasons.append("학습카드 또는 미연시 시나리오의 대사 확장이 충분히 완료되지 않았습니다.")
    if not reasons:
        reasons.append("자막 수는 확보되어 있어 EPUB 조립 과정의 누락 여부를 재검사해야 합니다.")
    return {"subtitle_cues": srt_cues, "transcript_lines": jsonl_lines,
            "reference_images": references, "scenario_lines": scenario_lines, "reasons": reasons}


def _source_video_metadata(work_dir: Path | str | None) -> dict:
    if not work_dir:
        return {}
    try:
        data = json.loads((Path(work_dir) / SOURCE_VIDEO_METADATA).read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}
    url = str(data.get("url") or "").strip()
    return {**data, "url": url} if url else {}


def _save_source_video_metadata(work_dir: Path, url: str, username: str) -> dict:
    data = {"url": url, "updated_at": int(time.time()), "updated_by": username}
    target = work_dir / SOURCE_VIDEO_METADATA
    temporary = target.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.chmod(temporary, 0o600)
    os.replace(temporary, target)
    return data


def _write_dating_sim_manifest(manifest_path: Path, payload: dict) -> dict:
    """Serialize cross-process manifest updates and retain unrelated fresh rows."""
    lock_path = manifest_path.with_name(f".{manifest_path.name}.lock")
    with lock_path.open("a+") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            current = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.is_file() else {}
        except (OSError, ValueError):
            current = {}
        merged = dict(current) if isinstance(current, dict) else {}
        merged.update(payload)
        for map_name in ("scenes", "admin_prompt_images", "quality_checks"):
            current_map = current.get(map_name) if isinstance(current, dict) else {}
            incoming_map = payload.get(map_name) if isinstance(payload, dict) else {}
            combined = dict(current_map or {})
            for key, value in (incoming_map or {}).items():
                if isinstance(combined.get(key), dict) and isinstance(value, dict):
                    previous_record = combined[key]
                    combined[key] = {**previous_record, **value}
                    if map_name in {"scenes", "admin_prompt_images"}:
                        previous_quality = previous_record.get("automatic_quality") or {}
                        incoming_quality = value.get("automatic_quality") or {}
                        previous_count = len(previous_quality.get("attempts") or [])
                        incoming_count = len(incoming_quality.get("attempts") or [])
                        if (previous_count > incoming_count or (
                            previous_count == incoming_count
                            and previous_quality.get("manually_selected")
                            and not incoming_quality.get("manually_selected")
                        )):
                            combined[key]["automatic_quality"] = previous_quality
                else:
                    combined[key] = value
            if combined:
                merged[map_name] = combined
        merged["revision"] = int((current or {}).get("revision") or 0) + 1
        merged["revision_updated_at"] = int(time.time())
        temporary = manifest_path.with_name(f".{manifest_path.name}.{os.getpid()}.tmp")
        temporary.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, manifest_path)
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
    return merged


def _dating_rebuild_pid_alive(pid) -> bool:
    try:
        os.kill(int(pid), 0)
        return True
    except (OSError, TypeError, ValueError):
        return False


def _notify_dating_rebuild_retry_approval(plan: dict, state_path: Path, state: dict) -> None:
    if state.get("approval_notification_message_id"):
        return
    plan_id = str(plan.get("plan_id") or "")
    if not re.fullmatch(r"[A-Za-z0-9_-]{10,64}", plan_id):
        return
    title = Path(str(plan.get("work_dir") or "작품")).name
    percent = max(0, min(100, int(state.get("percent") or 0)))
    failed_stage = str(state.get("failure_stage") or state.get("stage") or "확인 불가")
    failed_reason = str(state.get("failure_reason") or "파이프라인 오류")
    failed_details = str(state.get("failure_details") or state.get("message") or "로그에 상세 원인이 없습니다.")
    content = (
        f"「{title}」 재제작이 {percent}%에서 멈췄어요.\n\n"
        f"실패 단계: {failed_stage}\n"
        f"실패 원인: {failed_reason}\n"
        f"로그 분석: {failed_details}\n\n"
        "완료된 단계는 다시 실행하지 않고 실패 지점부터 재시도할까요?\n"
        f"[[dating-rebuild-approval:{plan_id}]]"
    )
    conn = get_conn()
    try:
        marker = f"[[dating-rebuild-approval:{plan_id}]]"
        conn.execute(
            "UPDATE messages SET content=replace(content, ?, ?) WHERE content LIKE ?",
            (marker, "✅ 이전 재시도 요청은 처리됐습니다.", f"%{marker}%"),
        )
        cursor = conn.execute(
            "INSERT INTO messages (room_id, sender, content, created_at) VALUES (?, ?, ?, ?)",
            ("일본어 선생님", "일본어 선생님", content, _now()),
        )
        username = str(plan.get("created_by") or APP_USERNAME or "").strip()
        if username:
            _send_web_push_to_user(
                conn, username, "일본어 선생님 · 재시도 승인 필요",
                f"{title} {failed_stage} 단계 실패: {failed_reason[:90]}",
                "/#room=" + urllib.parse.quote("일본어 선생님", safe=""),
            )
        state.update({"approval_notification_message_id": cursor.lastrowid,
                      "approval_notification_sent_at": int(time.time())})
        temporary = state_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, state_path)
        conn.commit()
    finally:
        conn.close()


def _dating_rebuild_eta_text(state: dict, percent: int) -> str:
    """현재 실행 구간의 실제 속도로 ETA를 계산한다. 표본이 작으면 표시하지 않는다."""
    started_at = int(state.get("run_started_at") or 0)
    started_percent = int(state.get("run_started_percent") or 0)
    elapsed = max(0, int(time.time()) - started_at)
    progressed = percent - started_percent
    if not started_at or elapsed < 60 or progressed < 5 or percent >= 100:
        return ""
    remaining = int(elapsed * max(0, 100 - percent) / progressed)
    if remaining <= 0 or remaining > 7 * 24 * 60 * 60:
        return ""
    eta = datetime.datetime.fromtimestamp(time.time() + remaining).astimezone()
    now = datetime.datetime.now().astimezone()
    day = "오늘" if eta.date() == now.date() else "내일" if eta.date() == now.date() + datetime.timedelta(days=1) else eta.strftime("%m월 %d일")
    return f" 현재 속도 기준 완료 예상 시각은 {day} {eta.strftime('%H시 %M분')}입니다."


def _is_dating_rebuild_status_question(content: str) -> bool:
    compact = re.sub(r"\s+", "", content or "")
    return any(token in compact for token in (
        "몇프로", "몇퍼", "진행률", "어디까지", "언제끝", "예상시간", "예상시각",
    ))


def _latest_dating_rebuild_status_reply() -> str | None:
    """가장 최근 재제작 상태를 읽어 과거 ETA 없이 결정론적으로 답한다."""
    candidates = []
    try:
        for plan_path in DATING_REBUILD_DIR.glob("*.plan.json"):
            try:
                plan = json.loads(plan_path.read_text(encoding="utf-8"))
                state_path = Path(str(plan.get("state_path") or ""))
                state = json.loads(state_path.read_text(encoding="utf-8"))
                updated_at = int(state.get("updated_at") or state_path.stat().st_mtime)
                candidates.append((updated_at, plan, state))
            except (OSError, ValueError, TypeError):
                continue
    except OSError:
        return None
    if not candidates:
        return None
    updated_at, plan, state = max(candidates, key=lambda item: item[0])
    title = Path(str(plan.get("work_dir") or "작품")).name
    percent = max(0, min(100, int(state.get("percent") or 0)))
    message = str(state.get("message") or state.get("stage") or "현재 단계를 확인 중입니다.").strip()
    status = str(state.get("status") or "")
    if status == "completed" or percent >= 100:
        return f"「{title}」 재제작은 100% 완료됐어요. {message}"
    if status == "awaiting_retry_approval":
        return f"「{title}」 재제작은 {percent}%에서 멈춰 재시도 승인을 기다리고 있어요. {message}"

    now = int(time.time())
    age = max(0, now - updated_at)
    # 10분 넘게 진행 파일이 갱신되지 않았다면 과거 평균으로 시각을 만들어
    # 내지 않는다. 화면에 이미 지난 시간이 뜬 원인이 이 오래된 ETA 재사용이었다.
    eta_text = _dating_rebuild_eta_text(state, percent) if age <= 600 else ""
    updated_label = datetime.datetime.fromtimestamp(updated_at).astimezone().strftime("%H시 %M분")
    if eta_text:
        return f"「{title}」 재제작은 지금 {percent}%까지 진행됐어요. {message}{eta_text}"
    return (
        f"「{title}」 재제작은 마지막으로 확인된 {updated_label} 기준 {percent}%예요. {message} "
        "최근 진행 표본이 부족해 완료 예상 시각은 아직 정확하게 계산할 수 없습니다. "
        "다음 진행 갱신 때 새 속도로 다시 계산해 알려드릴게요."
    )


def _dating_rebuild_size_text(value: int) -> str:
    size = float(max(0, value))
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit in {"B", "KB"} else f"{size:.2f} {unit}"
        size /= 1024
    return f"{size:.2f} GB"


def _dating_rebuild_epub_url(plan: dict) -> str:
    """승인 계획의 불투명 book ID로 완성 EPUB 웹 서재 주소를 만든다."""
    story_id = str(plan.get("story_id") or "")
    if not story_id.startswith("book:"):
        return ""
    book_id = story_id.split(":", 1)[1]
    if not re.fullmatch(r"[a-f0-9]{20}", book_id):
        return ""
    return f"/epub/?book={book_id}"


def _dating_rebuild_game_url(plan: dict) -> str:
    """재발행된 작품과 같은 불투명 book ID로 미연시 바로가기를 만든다."""
    story_id = str(plan.get("story_id") or "")
    if not story_id.startswith("book:"):
        return ""
    book_id = story_id.split(":", 1)[1]
    if not re.fullmatch(r"[a-f0-9]{20}", book_id):
        return ""
    return f"/dating-sim/?book={book_id}"


def _notify_dating_rebuild_progress(plan: dict, state_path: Path, state: dict) -> None:
    """작품별 50%·90%·완료 알림을 각각 한 번만 일본어 선생님 방에 보낸다."""
    percent = max(0, min(100, int(state.get("percent") or 0)))
    sent = {int(value) for value in state.get("progress_notifications", []) if str(value).isdigit()}
    eligible = [threshold for threshold in (50, 90, 100) if percent >= threshold and threshold not in sent]
    if not eligible:
        return
    threshold = max(eligible)
    # 감시 주기 사이에 여러 기준을 지난 경우 낮은 알림을 뒤늦게 연달아 보내지 않는다.
    sent.update(value for value in (50, 90, 100) if value <= threshold)
    title = Path(str(plan.get("work_dir") or "작품")).name
    stage_message = str(state.get("message") or "").strip()
    if threshold == 100:
        epub_url = _dating_rebuild_epub_url(plan)
        game_url = _dating_rebuild_game_url(plan)
        epub_link = f"\n\n[완성된 EPUB 바로 읽기]({epub_url})" if epub_url else ""
        game_link = f"\n[재발행된 미연시 바로가기]({game_url})" if game_url else ""
        cleanup_text = ""
        if state.get("downloaded_video_deleted"):
            deleted_name = str(state.get("deleted_video_name") or "다운로드 원본 영상")
            deleted_bytes = max(0, int(state.get("deleted_video_bytes") or 0))
            deleted_size = _dating_rebuild_size_text(deleted_bytes) if deleted_bytes else ""
            cleanup_text = f"\nMac에서 다운로드 원본 영상 `{deleted_name}`을 삭제했습니다"
            if deleted_size:
                cleanup_text += f" ({deleted_size} 확보)"
            cleanup_text += "."
        content = (
            f"「{title}」 재제작이 100% 완료됐어요. EPUB과 미연시 결과를 확인할 수 있습니다."
            f"{cleanup_text}{epub_link}{game_link}"
        )
    else:
        eta_text = _dating_rebuild_eta_text(state, percent)
        content = f"「{title}」 재제작이 {percent}% 진행됐어요. {stage_message}{eta_text}"
    conn = get_conn()
    try:
        cursor = conn.execute(
            "INSERT INTO messages (room_id, sender, content, created_at) VALUES (?, ?, ?, ?)",
            ("일본어 선생님", "일본어 선생님", content, _now()),
        )
        username = str(plan.get("created_by") or APP_USERNAME or "").strip()
        if username:
            push_url = _dating_rebuild_game_url(plan) if threshold == 100 else "/"
            _send_web_push_to_user(conn, username, "일본어 선생님 · 재제작 진행 알림", content, push_url)
        try:
            latest = json.loads(state_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            latest = dict(state)
        latest.update({"progress_notifications": sorted(sent),
                       "last_progress_notification_message_id": cursor.lastrowid,
                       "last_progress_notification_at": int(time.time())})
        temporary = state_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(latest, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, state_path)
        conn.commit()
    finally:
        conn.close()


def _open_dating_rebuild_terminal(log_path: Path) -> bool:
    """백그라운드 작업은 유지하면서 Terminal에서 로그를 실시간으로 보여준다."""
    if sys.platform != "darwin" or os.environ.get("JP_REBUILD_SHOW_TERMINAL", "1") == "0":
        return False
    script = """
on run argv
    set logPath to item 1 of argv
    tell application "Terminal"
        activate
        do script "clear; echo '일본어 EPUB·미연시 전체 파이프라인'; echo '이 창을 닫아도 작업은 계속됩니다.'; echo; /usr/bin/tail -n 80 -F " & quoted form of logPath
    end tell
end run
"""
    try:
        subprocess.run(
            ["/usr/bin/osascript", "-e", script, str(log_path.resolve())],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=8,
        )
        return True
    except (OSError, subprocess.SubprocessError):
        # 터미널 표시가 막혀도 실제 백그라운드 파이프라인은 중단하지 않는다.
        return False


def _spawn_dating_rebuild(plan_path: Path) -> subprocess.Popen:
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    log = open(plan["log_path"], "a", encoding="utf-8")
    try:
        process = subprocess.Popen(
            [DATING_SIM_IMAGE_PYTHON, str(DATING_REBUILD_WORKER), str(plan_path)],
            stdout=log, stderr=subprocess.STDOUT, start_new_session=True,
        )
    finally:
        log.close()
    state_path = Path(plan["state_path"])
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        state = {}
    # 한 번 승인한 알림 표식은 다음 실행으로 넘기지 않는다. 같은 작품이
    # 다시 실패하더라도 새 승인 질문을 정확히 한 번 보낼 수 있어야 한다.
    state.pop("approval_notification_message_id", None)
    state.pop("approval_notification_sent_at", None)
    current_percent = max(0, min(99, int(state.get("percent") or 0)))
    # 이전 시도가 잘못 완료로 판정됐거나 실패 뒤 재개되는 경우, 그 시도에서
    # 기록된 이후 구간 알림(예: 90%·100%)을 그대로 두면 실제 재시도가 해당
    # 지점에 도달해도 일본어 선생님이 이미 보냈다고 오인한다. 현재 재개 지점
    # 이전에 확실히 지난 기준만 보존하고 이후 기준은 다시 알릴 수 있게 한다.
    sent_progress = {
        int(value) for value in state.get("progress_notifications", [])
        if str(value).isdigit()
    }
    state["progress_notifications"] = sorted(
        value for value in sent_progress if value < current_percent
    )
    state.update({"status": "queued", "stage": "resume", "pid": process.pid,
                  "resumable": True, "message": "중단 지점부터 재개를 준비하고 있습니다.",
                  "run_started_at": int(time.time()), "run_started_percent": current_percent,
                  "updated_at": int(time.time())})
    temporary = state_path.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, state_path)
    _open_dating_rebuild_terminal(Path(plan["log_path"]))
    return process


def _recover_dating_rebuilds_forever():
    """중단을 감지하되 재시도는 하지 않고 반드시 관리자 승인을 기다린다."""
    while True:
        now = int(time.time())
        try:
            DATING_REBUILD_DIR.mkdir(parents=True, exist_ok=True)
            with _DATING_REBUILD_RECOVERY_LOCK:
                for plan_path in DATING_REBUILD_DIR.glob("*.plan.json"):
                    try:
                        plan = json.loads(plan_path.read_text(encoding="utf-8"))
                        if plan.get("status") != "approved":
                            continue
                        state_path = Path(plan["state_path"])
                        state = json.loads(state_path.read_text(encoding="utf-8"))
                        status = state.get("status")
                        pid_alive = _dating_rebuild_pid_alive(state.get("pid"))
                        if status in {"running", "queued"} and pid_alive:
                            _notify_dating_rebuild_progress(plan, state_path, state)
                            continue
                        if status == "completed":
                            _notify_dating_rebuild_progress(plan, state_path, state)
                            continue
                        if status == "awaiting_retry_approval":
                            _notify_dating_rebuild_retry_approval(plan, state_path, state)
                            continue
                        if status in {"running", "queued"} and not pid_alive:
                            state.update({"status": "awaiting_retry_approval", "stage": "retry_approval",
                                          "resumable": False,
                                          "message": "프로세스 중단 감지 · 자동 재시도 중지 · 관리자 승인 필요",
                                          "next_retry_at": None, "pid": None})
                            state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
                    except (OSError, ValueError, KeyError):
                        continue
        except Exception:
            pass
        time.sleep(30)


def _dating_gif_files(story: dict) -> list[Path]:
    code = dating_sim_story.source_work_code(
        story.get("source_work_code", ""), story.get("source_title", ""))
    if not code or not DATING_GIF_DIR.is_dir():
        return []
    matches = []
    try:
        for path in DATING_GIF_DIR.rglob("*.gif"):
            if path.is_file() and dating_sim_story.source_work_code(path.name) == code:
                matches.append(path.resolve())
    except OSError:
        return []
    if not matches:
        return []
    newest_parent = max(
        {path.parent for path in matches},
        key=lambda parent: max(path.stat().st_mtime for path in matches if path.parent == parent),
    )
    return sorted((path for path in matches if path.parent == newest_parent), key=lambda path: path.name.casefold())


@app.get("/api/dating-sim/affection-gifs")
def dating_sim_affection_gifs(request: Request, story_id: str):
    _require_signed_in_user(request)
    story = _dating_story(story_id, _request_username(request))
    files = _dating_gif_files(story)
    return {"count": len(files), "urls": [
        f"/api/dating-sim/affection-gif?story_id={urllib.parse.quote(story_id)}&index={index}"
        for index in range(len(files))
    ]}


@app.get("/api/dating-sim/affection-gif")
def dating_sim_affection_gif(request: Request, story_id: str, index: int):
    _require_signed_in_user(request)
    story = _dating_story(story_id, _request_username(request))
    files = _dating_gif_files(story)
    if index < 0 or index >= len(files):
        raise HTTPException(status_code=404, detail="작품 GIF를 찾지 못했습니다")
    return FileResponse(str(files[index]), media_type="image/gif",
                        headers={"Cache-Control": "private, max-age=86400"})


@app.get("/api/dating-sim/full-rebuild/source")
def dating_full_rebuild_source(request: Request, story_id: str):
    _require_signed_in_user(request)
    _book_id, work_dir = dating_sim_story.resolve_book_work_dir(story_id)
    if not work_dir:
        raise HTTPException(status_code=404, detail="작품 폴더를 찾지 못했습니다")
    metadata = _source_video_metadata(work_dir)
    return {"story_id": story_id, "video_url": metadata.get("url"),
            "updated_at": metadata.get("updated_at"), "can_rebuild": _is_owner_request(request)}


@app.post("/api/dating-sim/full-rebuild/propose")
def propose_dating_full_rebuild(request: Request, payload: DatingFullRebuildRequest):
    _require_owner(request)
    video_url = _validate_stream_download_url(payload.video_url)
    _book_id, work_dir = dating_sim_story.resolve_book_work_dir(payload.story_id)
    if not work_dir:
        raise HTTPException(status_code=404, detail="재제작할 작품 폴더를 찾지 못했습니다")
    source_metadata = _save_source_video_metadata(Path(work_dir), video_url, _request_username(request))
    DATING_REBUILD_DIR.mkdir(parents=True, exist_ok=True)
    plan_id = secrets.token_urlsafe(18)
    state_path = DATING_REBUILD_DIR / f"{plan_id}.state.json"
    log_path = DATING_REBUILD_DIR / f"{plan_id}.log"
    plan = {
        "plan_id": plan_id, "status": "proposed", "story_id": payload.story_id,
        "video_url": video_url, "work_dir": str(Path(work_dir).resolve()),
        "completed_epub_dir": "/Users/forrestdpark/Desktop/BlogImage/av완성작",
        "download_dir": "/Users/forrestdpark/Desktop/BlogImage/av4",
        "gif_dir": str(DATING_GIF_DIR),
        "source_video_metadata": source_metadata,
        "state_path": str(state_path), "log_path": str(log_path),
        "created_by": _request_username(request), "created_at": int(time.time()),
    }
    plan_path = DATING_REBUILD_DIR / f"{plan_id}.plan.json"
    plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    os.chmod(plan_path, 0o600)
    state_path.write_text(json.dumps({"status": "awaiting_approval", "stage": "plan", "percent": 0,
                                      "story_id": payload.story_id}, ensure_ascii=False), encoding="utf-8")
    return {"ok": True, "plan_id": plan_id, "diagnosis": _dating_rebuild_diagnosis(Path(work_dir)),
            "steps": ["영상 다운로드·Mac 원본 보존", "GIF 미리보기 추출", "자막·번역·EPUB 재생성",
                      "미연시 시나리오 재생성", "장면 이미지 재생성", "검증 성공 후 기존 결과 백업·교체"]}


@app.post("/api/dating-sim/full-rebuild/approve")
def approve_dating_full_rebuild(request: Request, payload: DatingFullRebuildApproveRequest):
    _require_owner(request)
    if not re.fullmatch(r"[A-Za-z0-9_-]{10,64}", payload.plan_id):
        raise HTTPException(status_code=422, detail="계획 번호가 올바르지 않습니다")
    plan_path = DATING_REBUILD_DIR / f"{payload.plan_id}.plan.json"
    try:
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=404, detail="재제작 계획을 찾지 못했습니다") from exc
    try:
        state = json.loads(Path(plan["state_path"]).read_text(encoding="utf-8"))
    except (OSError, ValueError, KeyError):
        state = {}
    initial_approval = plan.get("status") == "proposed"
    retry_approval = (plan.get("status") == "approved"
                      and state.get("status") == "awaiting_retry_approval")
    if not initial_approval and not retry_approval:
        raise HTTPException(status_code=409, detail="승인 대기 중인 작업이 아닙니다")
    plan["status"] = "approved"
    plan["approved_at" if initial_approval else "retry_approved_at"] = int(time.time())
    plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    process = _spawn_dating_rebuild(plan_path)
    return {"ok": True, "plan_id": payload.plan_id, "pid": process.pid}


@app.get("/api/dating-sim/full-rebuild/status")
def dating_full_rebuild_status(request: Request, plan_id: str):
    _require_owner(request)
    if not re.fullmatch(r"[A-Za-z0-9_-]{10,64}", plan_id):
        raise HTTPException(status_code=422, detail="계획 번호가 올바르지 않습니다")
    try:
        return json.loads((DATING_REBUILD_DIR / f"{plan_id}.state.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=404, detail="진행 상태를 찾지 못했습니다") from exc


@app.post("/api/dating-sim/full-rebuild/retry-decision")
def dating_full_rebuild_retry_decision(
    request: Request, payload: DatingFullRebuildRetryDecision,
):
    _require_owner(request)
    if not re.fullmatch(r"[A-Za-z0-9_-]{10,64}", payload.plan_id):
        raise HTTPException(status_code=422, detail="계획 번호가 올바르지 않습니다")
    decision = payload.decision.strip().lower()
    if decision not in {"approve", "decline"}:
        raise HTTPException(status_code=422, detail="승인 또는 취소를 선택해 주세요")
    plan_path = DATING_REBUILD_DIR / f"{payload.plan_id}.plan.json"
    try:
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        state_path = Path(plan["state_path"])
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, KeyError) as exc:
        raise HTTPException(status_code=404, detail="재제작 계획을 찾지 못했습니다") from exc
    if state.get("status") != "awaiting_retry_approval":
        raise HTTPException(status_code=409, detail="현재 승인 대기 중인 작업이 아닙니다")
    marker = f"[[dating-rebuild-approval:{payload.plan_id}]]"
    decision_text = "✅ 실패 지점부터 재시도를 승인했습니다." if decision == "approve" else "⏹️ 이번 재시도는 취소했습니다."
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE messages SET content=replace(content, ?, ?) WHERE content LIKE ?",
            (marker, decision_text, f"%{marker}%"),
        )
        conn.commit()
    finally:
        conn.close()
    if decision == "decline":
        state.update({"status": "retry_declined", "stage": "stopped", "resumable": False,
                      "message": "관리자가 재시도를 취소했습니다.", "pid": None,
                      "retry_decided_at": int(time.time()), "retry_decision": "decline"})
        temporary = state_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, state_path)
        return {"ok": True, "status": "retry_declined"}
    plan["status"] = "approved"
    plan["retry_approved_at"] = int(time.time())
    plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    process = _spawn_dating_rebuild(plan_path)
    return {"ok": True, "status": "queued", "pid": process.pid}


# ★ 2026-09-23: "시나리오트리에 이미지생성하기 버튼 만들어서 이미지만
# 생성해서 올릴수있게하자" 요청 — 지금까지 미연시 이미지는 기상 알람이
# 하루 한 작품씩 돌리는 백그라운드 에이전트(run_daily_dating_sim_agent.py)
# 로만 생성됐다. 관리자가 시나리오 트리에서 특정 작품의 이미지 생성만
# 지금 바로 수동으로 돌릴 수 있게, generate_dating_sim_images.py를
# 서브프로세스로 띄운다. cv2/Pillow가 깔린 인터프리터가 이 서버의 venv가
# 아니라 shift_alarm 파이프라인이 쓰는 anaconda 배포판이므로(★
# SHIFT_ALARM_MEDIA_KEY_PYTHON과 같은 이유), 동일한 인터프리터를 그대로
# 빌려 쓴다.
DATING_SIM_IMAGE_PYTHON = "/opt/anaconda3/bin/python3"
DATING_SIM_IMAGE_SCRIPT = str(REPO_ROOT / "일본어자막추출" / "generate_dating_sim_images.py")
DATING_SIM_IMAGE_BACKLOG_SCRIPT = str(REPO_ROOT / "일본어자막추출" / "generate_missing_dating_sim_images.py")
DATING_SIM_IMAGE_BACKLOG_STATE = Path(os.path.expanduser("~/.tulpachat/dating_sim_image_backlog.json"))
DATING_SIM_IMAGE_BACKLOG_LOG = Path(os.path.expanduser("~/.tulpachat/dating_sim_image_backlog.log"))
DATING_SIM_IMAGE_PAUSE_FILE = Path(os.path.expanduser("~/.tulpachat/dating_sim_image_generation.paused"))
DATING_SIM_IMAGE_REPORTS_FILE = Path(os.path.expanduser("~/.tulpachat/dating_sim_image_reports.json"))
DATING_SIM_IMAGE_LIKES_FILE = Path(os.path.expanduser("~/.tulpachat/dating_sim_image_likes.json"))
DATING_SIM_REPORT_PRIORITY_FILE = Path(os.path.expanduser("~/.tulpachat/dating_sim_report_priority.active"))
DATING_SIM_REPORT_PROCESS_FILE = Path(os.path.expanduser("~/.tulpachat/dating_sim_report_process.json"))
DATING_SIM_PROMPT_APPROVALS_FILE = Path(os.environ.get(
    "JP_DATING_PROMPT_APPROVALS_FILE",
    os.path.expanduser("~/.tulpachat/dating_sim_prompt_approvals.json"),
))
DATING_SIM_ADMIN_PROMPTS_FILE = Path(os.environ.get(
    "JP_DATING_ADMIN_PROMPTS_FILE",
    os.path.expanduser("~/.tulpachat/dating_sim_admin_prompts.json"),
))
DATING_SIM_TEACHER_NOTIFICATION = ".teacher_image_completion.json"
_DATING_SIM_TEACHER_NOTIFICATION_LOCK = threading.Lock()
_DATING_SIM_ADMIN_PROMPTS_LOCK = threading.Lock()
COMFYUI_LAUNCH_AGENT_LABEL = "com.tulpachat.comfyui"
COMFYUI_LAUNCH_AGENT_PLIST = Path.home() / "Library" / "LaunchAgents" / f"{COMFYUI_LAUNCH_AGENT_LABEL}.plist"

_dating_sim_image_jobs: dict[str, dict] = {}
_dating_sim_image_jobs_lock = threading.Lock()
_dating_sim_image_backlog_job: dict | None = None
_DATING_SIM_IMAGE_REPORTS_LOCK = threading.Lock()
_DATING_SIM_IMAGE_LIKES_LOCK = threading.Lock()
_DATING_SIM_PROMPT_APPROVALS_LOCK = threading.Lock()
_DATING_SIM_IMAGE_REPORT_WORKER_STARTED = False

_DATING_SIM_SITUATION_TAGS = {
    "bed": ("bed", "bedroom", "mattress", "침대", "침실"),
    "outdoor": ("outdoor", "garden", "park", "street", "outside", "야외", "공원"),
    "indoor": ("indoor", "room", "interior", "실내"),
    "sitting": ("sitting", "seated", "sit ", "앉"),
    "lying": ("lying", "reclining", "laying", "누운", "눕"),
    "standing": ("standing", "stand ", "서 있", "선 자세"),
    "closeup": ("close-up", "closeup", "portrait shot", "얼굴 중심", "클로즈업"),
    "fullbody": ("full body", "full-body", "전신"),
    "single": ("one woman", "single subject", "one person", "단일 인물"),
}


def _dating_prompt_situation_tags(text):
    normalized = f" {str(text or '').casefold()} "
    return sorted(tag for tag, tokens in _DATING_SIM_SITUATION_TAGS.items()
                  if any(token.casefold() in normalized for token in tokens))


def _write_dating_prompt_approval(approval):
    with _DATING_SIM_PROMPT_APPROVALS_LOCK:
        try:
            payload = json.loads(DATING_SIM_PROMPT_APPROVALS_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            payload = {}
        rows = [dict(row) for row in (payload.get("items") or []) if isinstance(row, dict)]
        # 같은 관리자 프롬프트 또는 같은 작품의 동일 장면 키를 다시 채택하면
        # 오래된 승인을 남겨 경쟁시키지 않고 최신 사용자 판단으로 교체한다.
        rows = [row for row in rows if not (
            (approval["kind"] == "admin" and row.get("kind") == "admin"
             and row.get("admin_prompt_id") == approval.get("admin_prompt_id"))
            or (approval["kind"] != "admin" and row.get("kind") == approval["kind"]
                and row.get("story_id") == approval.get("story_id")
                and row.get("image_key") == approval.get("image_key"))
        )]
        rows.append(approval)
        stored = {"version": 1, "updated_at": _now(), "items": rows[-500:]}
        DATING_SIM_PROMPT_APPROVALS_FILE.parent.mkdir(parents=True, exist_ok=True)
        temporary = DATING_SIM_PROMPT_APPROVALS_FILE.with_suffix(".tmp")
        temporary.write_text(json.dumps(stored, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, DATING_SIM_PROMPT_APPROVALS_FILE)


def _remove_dating_prompt_like_approval(story_id, image_key):
    with _DATING_SIM_PROMPT_APPROVALS_LOCK:
        try:
            payload = json.loads(DATING_SIM_PROMPT_APPROVALS_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        rows = [dict(row) for row in (payload.get("items") or []) if isinstance(row, dict)]
        remaining = [row for row in rows if not (
            row.get("source") == "image_like"
            and row.get("story_id") == story_id and row.get("image_key") == image_key
        )]
        if len(remaining) == len(rows):
            return
        temporary = DATING_SIM_PROMPT_APPROVALS_FILE.with_suffix(".tmp")
        temporary.write_text(json.dumps({
            "version": 1, "updated_at": _now(), "items": remaining,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, DATING_SIM_PROMPT_APPROVALS_FILE)


def _read_dating_sim_image_reports():
    try:
        payload = json.loads(DATING_SIM_IMAGE_REPORTS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    rows = payload.get("items") if isinstance(payload, dict) else payload
    return [dict(row) for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def _write_dating_sim_image_reports(rows):
    DATING_SIM_IMAGE_REPORTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = {"version": 1, "updated_at": _now(), "items": rows[-500:]}
    temporary = DATING_SIM_IMAGE_REPORTS_FILE.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, DATING_SIM_IMAGE_REPORTS_FILE)


def _read_dating_sim_image_likes():
    try:
        payload = json.loads(DATING_SIM_IMAGE_LIKES_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    rows = payload.get("items") if isinstance(payload, dict) else payload
    return [dict(row) for row in (rows or []) if isinstance(row, dict)]


def _write_dating_sim_image_likes(rows):
    DATING_SIM_IMAGE_LIKES_FILE.parent.mkdir(parents=True, exist_ok=True)
    temporary = DATING_SIM_IMAGE_LIKES_FILE.with_suffix(".tmp")
    temporary.write_text(json.dumps({
        "version": 1, "updated_at": _now(), "items": rows[-1000:],
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, DATING_SIM_IMAGE_LIKES_FILE)


def _pending_dating_sim_image_report_keys(story_id):
    return {str(item.get("image_key") or "") for item in _read_dating_sim_image_reports()
            if item.get("story_id") == story_id
            and item.get("status") in {"pending", "processing", "failed"}}


def _update_dating_sim_image_report(report_id, **updates):
    with _DATING_SIM_IMAGE_REPORTS_LOCK:
        rows = _read_dating_sim_image_reports()
        for row in rows:
            if row.get("id") == report_id:
                row.update(updates)
                _write_dating_sim_image_reports(rows)
                return row
    return None


def _dating_sim_image_file_for_key(work_dir, image_key):
    """manifest의 허용된 이미지 키를 실제 결과 파일로 해석한다."""
    image_dir = Path(work_dir) / "dating_sim_images"
    try:
        manifest = json.loads((image_dir / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None
    if image_key == "portrait":
        filename = manifest.get("portrait")
    elif image_key.startswith("admin:"):
        prompt_id = image_key.removeprefix("admin:")
        record = (manifest.get("admin_prompt_images") or {}).get(prompt_id)
        filename = record.get("file") if isinstance(record, dict) else None
        # 서로 다른 이미지 작업이 같은 manifest를 갱신하던 구버전에서는
        # 완성 PNG는 남고 관리자 레코드만 유실될 수 있었다. 관리자 파일명은
        # prompt id로 결정적이므로 실제 파일이 있으면 안전하게 복구한다.
        if not filename:
            fallback = f"admin-{prompt_id}.png"
            if re.fullmatch(r"admin-[0-9a-f]{32}\.png", fallback):
                filename = fallback
    else:
        record = (manifest.get("scenes") or {}).get(image_key)
        filename = record.get("file") if isinstance(record, dict) else None
    target = image_dir / str(filename or "")
    return target if filename and target.is_file() and target.parent == image_dir else None


def _dating_sim_report_generation_info(story_id, work_dir, image_key):
    """완료 화면용 생성정보를 manifest 유실 시에도 실제 산출물에서 복원한다."""
    image_dir = Path(work_dir) / "dating_sim_images"
    try:
        manifest = json.loads((image_dir / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        manifest = {}
    book_id = str(story_id).removeprefix("book:")
    if image_key.startswith("admin:"):
        prompt_id = image_key.removeprefix("admin:")
        record = dict((manifest.get("admin_prompt_images") or {}).get(prompt_id) or {})
        prompt = next((row for row in _read_dating_sim_admin_prompts()
                       if row.get("id") == prompt_id), {})
        filename = f"admin-{prompt_id}.png"
        record.update({
            "key": image_key, "id": prompt_id,
            "label": record.get("name") or prompt.get("name") or image_key,
            "name": record.get("name") or prompt.get("name") or image_key,
            "file": filename, "admin_only": True,
            "prompt": record.get("prompt") or prompt.get("prompt") or "",
            "negative_prompt": record.get("negative_prompt") or prompt.get("negative_prompt") or "",
            "negative_prompt_enabled": record.get("negative_prompt_enabled", prompt.get("negative_prompt_enabled", True)),
        })
    elif image_key == "portrait":
        filename = str(manifest.get("portrait") or "portrait.png")
        record = {"key": image_key, "label": "인물 이미지", "file": filename,
                  "prompt": manifest.get("portrait_prompt") or "",
                  "effective_prompt": manifest.get("portrait_effective_prompt") or "",
                  "automatic_quality": manifest.get("portrait_automatic_quality") or {}}
    else:
        record = dict((manifest.get("scenes") or {}).get(image_key) or {})
        filename = str(record.get("file") or "")
        record.update({"key": image_key, "label": record.get("label") or image_key})
    target = image_dir / filename
    if filename and target.is_file():
        route = "admin-images" if image_key.startswith("admin:") else "images"
        record["image_url"] = f"/api/dating-sim/books/{book_id}/{route}/{filename}?t={int(target.stat().st_mtime)}"
    automatic = dict(record.get("automatic_quality") or {})
    attempts = list(automatic.get("attempts") or [])
    if not attempts and filename:
        stem = Path(filename).stem
        final_hash = hashlib.sha256(target.read_bytes()).hexdigest() if target.is_file() else ""
        for attempt in range(1, 4):
            attempt_name = f"{stem}-attempt-{attempt}.png"
            candidate = image_dir / "quality_attempts" / attempt_name
            if not candidate.is_file():
                continue
            candidate_hash = hashlib.sha256(candidate.read_bytes()).hexdigest()
            sidecar = candidate.with_suffix(".json")
            try:
                saved = json.loads(sidecar.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                saved = None
            recovered = dict(saved) if isinstance(saved, dict) else {
                "attempt": attempt, "image_file": attempt_name,
                "prompt": record.get("prompt") or "",
                "effective_prompt": record.get("effective_prompt") or record.get("prompt") or "",
                "negative_prompt": record.get("effective_negative_prompt") or record.get("negative_prompt") or "",
                "generation_settings": record.get("generation_settings") or {},
                "report": {"passed": False, "reasons": ["후보 사진은 복구됐지만 당시 검사 기록은 저장되어 있지 않음"]},
            }
            recovered.update({
                "attempt": attempt, "image_file": attempt_name,
                "image_url": f"/api/dating-sim/books/{book_id}/quality-attempts/{attempt_name}?t={int(candidate.stat().st_mtime)}",
            })
            attempts.append(recovered)
            if final_hash and candidate_hash == final_hash:
                automatic["selected_attempt"] = attempt
        if attempts:
            automatic.update({"attempts": attempts, "attempts_used": len(attempts),
                              "max_attempts": 3, "recovered_from_files": True,
                              "recovery_complete": all(
                                  (image_dir / "quality_attempts" / f"{Path(row['image_file']).stem}.json").is_file()
                                  for row in attempts
                              )})
            record["automatic_quality"] = automatic
    return record


def _watch_dating_sim_image_reports_forever():
    """신고 예약을 한 장씩 처리하고 다음 장 전에 2분간 발열 휴식을 둔다."""
    while True:
        active_reports = [item for item in _read_dating_sim_image_reports()
                          if item.get("status") in {"pending", "processing"}]
        if active_reports:
            DATING_SIM_REPORT_PRIORITY_FILE.parent.mkdir(parents=True, exist_ok=True)
            DATING_SIM_REPORT_PRIORITY_FILE.touch(exist_ok=True)
        else:
            DATING_SIM_REPORT_PRIORITY_FILE.unlink(missing_ok=True)
        external_job = _dating_sim_external_image_job()
        with _dating_sim_image_jobs_lock:
            internal_running = any(
                job.get("process") and job["process"].poll() is None
                for job in _dating_sim_image_jobs.values()
            ) or bool(
                _dating_sim_image_backlog_job
                and _dating_sim_image_backlog_job.get("process")
                and _dating_sim_image_backlog_job["process"].poll() is None
            )
        # 서버 재시작으로 process 객체를 잃은 작업은 외부 생성까지 모두 끝난
        # 시점에 다시 대기로 돌려 영구적인 '생성 중' 표시를 없앤다.
        if not external_job and not internal_running:
            stale = [item for item in _read_dating_sim_image_reports()
                     if item.get("status") == "processing"]
            for item in stale:
                _update_dating_sim_image_report(
                    item.get("id"), status="pending", started_at=None,
                    error="서버 재시작 후 대기열에 자동 복구됨",
                )
        priorities = {"regenerate": 0, "anatomy": 1, "eyes": 2, "sharpness": 3}
        pending_reports = [item for item in _read_dating_sim_image_reports()
                           if item.get("status") == "pending"]
        report = min(pending_reports, key=lambda item: (
            priorities.get(str(item.get("job_type") or "regenerate"), 9),
            str(item.get("created_at") or ""),
        ), default=None)
        if not report or DATING_SIM_IMAGE_PAUSE_FILE.exists():
            time.sleep(10)
            continue
        story_id = str(report.get("story_id") or "")
        image_key = str(report.get("image_key") or "")
        book_id, work_dir = dating_sim_story.resolve_book_work_dir(story_id)
        if not work_dir or not DATING_SIM_IMAGE_KEY_RE.fullmatch(image_key):
            _update_dating_sim_image_report(
                report.get("id"), status="failed", error="작품 또는 이미지 키를 찾을 수 없습니다",
                finished_at=_now(),
            )
            continue
        image_dir = work_dir / "dating_sim_images"
        image_dir.mkdir(parents=True, exist_ok=True)
        log_path = image_dir / "reported-image-generation.log"
        log_file = None
        process = None
        busy = False
        before_file = _dating_sim_image_file_for_key(work_dir, image_key)
        if not before_file:
            _update_dating_sim_image_report(
                report.get("id"), status="failed",
                error="재생성할 현재 이미지 파일을 찾을 수 없습니다",
                finished_at=_now(),
            )
            continue
        before_hash = hashlib.sha256(before_file.read_bytes()).hexdigest() if before_file else ""
        # 서버 재시작 전에 시작된 이미지 생성 프로세스도 감지해 ComfyUI 작업을
        # 겹쳐 실행하지 않는다.
        external_job = _dating_sim_external_image_job()
        with _dating_sim_image_jobs_lock:
            existing = _dating_sim_image_jobs.get(book_id)
            if (external_job
                    or (existing and existing["process"].poll() is None)
                    or (_dating_sim_image_backlog_job
                        and _dating_sim_image_backlog_job["process"].poll() is None)):
                busy = True
            else:
                command = [DATING_SIM_IMAGE_PYTHON, DATING_SIM_IMAGE_SCRIPT, str(work_dir)]
                if image_key.startswith("admin:"):
                    command.extend(["--admin-prompts-only", "--admin-prompt-id", image_key.split(":", 1)[1]])
                else:
                    command.extend(["--force-key", image_key])
                command.append("--single-image-resume")
                try:
                    log_file = open(log_path, "ab")
                    process_env = os.environ.copy()
                    process_env["JP_DATING_IMAGE_SEED_NONCE"] = (
                        f"report:{report.get('id')}:{time.time_ns()}"
                    )
                    process_env["JP_DATING_IMAGE_REPORT_JOB"] = "1"
                    process_env["JP_DATING_TARGET_IMPROVEMENT"] = str(report.get("job_type") or "")
                    process = subprocess.Popen(
                        command, stdout=log_file, stderr=subprocess.STDOUT,
                        start_new_session=True, env=process_env,
                    )
                except OSError as exc:
                    if log_file:
                        log_file.close()
                    _update_dating_sim_image_report(
                        report.get("id"), status="failed", error=str(exc)[:500], finished_at=_now(),
                    )
                    continue
                _dating_sim_image_jobs[book_id] = {
                    "process": process, "log_file": log_file, "log_path": log_path,
                    "started_at": int(time.time()), "work_dir": str(work_dir),
                    "job_type": "reported_image", "expected_total": 1,
                }
                marker = DATING_SIM_REPORT_PROCESS_FILE.with_suffix(".tmp")
                marker.write_text(json.dumps({
                    "pid": process.pid, "report_id": report.get("id"),
                    "story_id": story_id, "image_key": image_key,
                    "started_at": _now(), "before_sha256": before_hash,
                }, ensure_ascii=False), encoding="utf-8")
                os.replace(marker, DATING_SIM_REPORT_PROCESS_FILE)
        if busy:
            time.sleep(10)
            continue
        _update_dating_sim_image_report(
            report.get("id"), status="processing", started_at=_now(), error="",
        )
        returncode = process.wait()
        with _dating_sim_image_jobs_lock:
            current = _dating_sim_image_jobs.get(book_id)
            if current and current.get("process") is process:
                _dating_sim_image_jobs.pop(book_id, None)
        try:
            marker = json.loads(DATING_SIM_REPORT_PROCESS_FILE.read_text(encoding="utf-8"))
            if int(marker.get("pid") or 0) == process.pid:
                DATING_SIM_REPORT_PROCESS_FILE.unlink(missing_ok=True)
        except (OSError, ValueError, TypeError):
            pass
        log_file.close()
        after_file = _dating_sim_image_file_for_key(work_dir, image_key)
        after_hash = hashlib.sha256(after_file.read_bytes()).hexdigest() if after_file else ""
        generation_info_snapshot = _dating_sim_report_generation_info(
            story_id, work_dir, image_key,
        )
        try:
            manifest = json.loads((image_dir / "manifest.json").read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            manifest = {}
        progress = manifest.get("job_progress") if isinstance(manifest, dict) else {}
        generated_exactly_one = bool(
            isinstance(progress, dict)
            and int(progress.get("total") or 0) == 1
            and int(progress.get("done") or 0) == 1
        )
        unchanged = bool(returncode == 0 and before_hash and after_hash == before_hash)
        succeeded = bool(returncode == 0 and generated_exactly_one and not unchanged)
        if returncode == 0 and not generated_exactly_one:
            result_error = (
                "단일 재생성 작업이 정확히 1장을 만들지 않았습니다 "
                f"(진행 {int((progress or {}).get('done') or 0)}/"
                f"{int((progress or {}).get('total') or 0)})"
            )
        elif unchanged:
            result_error = "재생성 결과가 신고 당시 파일과 완전히 동일해 완료 처리하지 않았습니다"
        elif returncode != 0:
            result_error = "이미지 재생성 프로세스가 실패했습니다"
        else:
            result_error = ""
        _update_dating_sim_image_report(
            report.get("id"), status="done" if succeeded else "failed",
            returncode=returncode, finished_at=_now(),
            before_sha256=before_hash, result_sha256=after_hash,
            generation_info=generation_info_snapshot,
            error=result_error,
        )
        time.sleep(120)


def _read_dating_sim_admin_prompts():
    try:
        payload = json.loads(DATING_SIM_ADMIN_PROMPTS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    rows = payload.get("prompts") if isinstance(payload, dict) else payload
    return [dict(row) for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def _read_dating_sim_prompt_settings():
    try:
        payload = json.loads(DATING_SIM_ADMIN_PROMPTS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"common_negative_prompt": "", "common_negative_enabled": True}
    settings = payload.get("settings") if isinstance(payload, dict) else {}
    return {
        "common_negative_prompt": str((settings or {}).get("common_negative_prompt") or "")[:8000],
        "common_negative_enabled": bool((settings or {}).get("common_negative_enabled", True)),
    }


def _write_dating_sim_admin_prompts(rows):
    DATING_SIM_ADMIN_PROMPTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = {"version": 2, "updated_at": _now(),
               "settings": _read_dating_sim_prompt_settings(), "prompts": rows}
    temporary = DATING_SIM_ADMIN_PROMPTS_FILE.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, DATING_SIM_ADMIN_PROMPTS_FILE)


def _active_dating_sim_admin_prompt_ids():
    return {str(row.get("id")) for row in _read_dating_sim_admin_prompts()
            if row.get("enabled") is not False and re.fullmatch(r"[0-9a-f]{32}", str(row.get("id") or ""))}


def _comfyui_runtime_status():
    """관리자 제작 화면에 표시할 로컬 ComfyUI 생존 상태를 반환한다."""
    try:
        with urllib.request.urlopen("http://127.0.0.1:8188/system_stats", timeout=1.5):
            pass
        return {"comfy_online": True, "comfy_label": "ComfyUI ON",
                "comfy_control_available": COMFYUI_LAUNCH_AGENT_PLIST.is_file()}
    except (OSError, urllib.error.URLError):
        return {"comfy_online": False, "comfy_label": "ComfyUI OFF",
                "comfy_control_available": COMFYUI_LAUNCH_AGENT_PLIST.is_file()}


def _run_comfyui_launchctl(*arguments):
    """고정된 LaunchAgent만 제어한다. 사용자 입력은 명령에 포함하지 않는다."""
    try:
        return subprocess.run(
            ["/bin/launchctl", *arguments], capture_output=True, text=True,
            timeout=12, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError("ComfyUI 시스템 제어 명령을 실행하지 못했습니다") from exc


def _set_comfyui_runtime(enabled: bool):
    """ComfyUI LaunchAgent를 영구 활성화하거나 비활성화한다."""
    if not COMFYUI_LAUNCH_AGENT_PLIST.is_file():
        raise RuntimeError("ComfyUI 자동 실행 설정 파일을 찾을 수 없습니다")
    domain = f"gui/{os.getuid()}"
    target = f"{domain}/{COMFYUI_LAUNCH_AGENT_LABEL}"
    if enabled:
        enabled_result = _run_comfyui_launchctl("enable", target)
        if enabled_result.returncode:
            raise RuntimeError((enabled_result.stderr or "ComfyUI 활성화에 실패했습니다").strip())
        loaded = _run_comfyui_launchctl("print", target).returncode == 0
        if not loaded:
            boot = _run_comfyui_launchctl("bootstrap", domain, str(COMFYUI_LAUNCH_AGENT_PLIST))
            if boot.returncode:
                raise RuntimeError((boot.stderr or "ComfyUI 등록에 실패했습니다").strip())
        started = _run_comfyui_launchctl("kickstart", "-k", target)
        if started.returncode:
            raise RuntimeError((started.stderr or "ComfyUI 시작에 실패했습니다").strip())
    else:
        disabled = _run_comfyui_launchctl("disable", target)
        if disabled.returncode:
            raise RuntimeError((disabled.stderr or "ComfyUI 비활성화에 실패했습니다").strip())
        # 이미 종료된 상태의 bootout 오류는 목표 상태와 같으므로 무시한다.
        _run_comfyui_launchctl("bootout", target)

    # 시작은 모델 로딩 때문에 시간이 걸릴 수 있다. UI가 거짓으로 ON을
    # 표시하지 않도록 짧게 확인하고, 나머지는 기존 5초 상태 폴링에 맡긴다.
    for _ in range(12 if enabled else 4):
        status = _comfyui_runtime_status()
        if status["comfy_online"] is enabled:
            return status
        time.sleep(0.5)
    return _comfyui_runtime_status()


def _dating_sim_image_backlog_state():
    try:
        data = json.loads(DATING_SIM_IMAGE_BACKLOG_STATE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _dating_sim_image_backlog_progress(state, running):
    """작품 단위 상태에 현재 작품의 매니페스트 장수와 전체 백분율을 더한다."""
    payload = dict(state)
    total = max(0, int(payload.get("total") or 0))
    completed = max(0, int(payload.get("completed") or 0))
    failed = max(0, int(payload.get("failed") or 0))
    current_fraction = 0.0
    current_name = payload.get("current")
    if running and isinstance(current_name, str):
        library = REPO_ROOT / "일본어자막추출" / "library"
        work_dir = library / current_name
        try:
            if work_dir.parent == library and work_dir.is_dir():
                manifest_path = work_dir / "dating_sim_images" / "manifest.json"
                manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.is_file() else {}
                image_dir = work_dir / "dating_sim_images"
                generated = int(bool(manifest.get("portrait") and (image_dir / manifest["portrait"]).is_file()))
                generated += sum(
                    1 for record in (manifest.get("scenes") or {}).values()
                    if isinstance(record, dict) and isinstance(record.get("file"), str)
                    and (image_dir / record["file"]).is_file()
                )
                active_admin_ids = _active_dating_sim_admin_prompt_ids()
                generated += sum(
                    1 for prompt_id, record in (manifest.get("admin_prompt_images") or {}).items()
                    if prompt_id in active_admin_ids and isinstance(record, dict)
                    and isinstance(record.get("file"), str) and (image_dir / record["file"]).is_file()
                )
                target = max(1, 1 + int(manifest.get("selected_count") or 0) + len(active_admin_ids))
                payload["current_images"] = min(generated, target)
                payload["current_image_total"] = target
                current_fraction = min(1.0, generated / target)
                image_progress = manifest.get("job_progress") or {}
                payload["current_image_job"] = str(image_progress.get("current") or "이미지 생성 중")
                payload["current_image_percent"] = max(0, min(100, int(image_progress.get("percent") or 0)))
                payload["current_image_eta_seconds"] = image_progress.get("eta_seconds")
                payload["current_image_elapsed_seconds"] = image_progress.get("elapsed_seconds")
                payload["current_image_updated_at"] = image_progress.get("updated_at")
                payload["current_image_expected_finished_at"] = image_progress.get("expected_finished_at")
                payload["current_image_average_seconds"] = image_progress.get("average_item_seconds")
        except (OSError, ValueError, TypeError):
            pass
    processed = completed + failed
    if running and payload.get("current_index"):
        processed = max(processed, int(payload["current_index"]) - 1)
    payload["percent"] = min(100, round((processed + current_fraction) / total * 100)) if total else 0
    # 프로세스가 아직 살아 있는 동안 100%를 표시하면 완료로 오해하기 쉽다.
    # 마지막 결과 정리 단계는 99%로 두고, 프로세스 종료 뒤에만 100%가 된다.
    if running and payload["percent"] >= 100:
        payload["percent"] = 99
    if running:
        durations = [float(value) for value in (payload.get("work_durations") or [])
                     if isinstance(value, (int, float)) and value > 0]
        average = (sum(durations) / len(durations)) if durations else 0
        remaining_works = max(0.0, total - processed - current_fraction)
        if average:
            payload["eta_seconds"] = round(remaining_works * average)
    raw_status = str(payload.get("status") or "idle")
    if not running and raw_status in {"complete", "partial"}:
        payload["percent"] = 100
    # 저장 파일의 과거 문구와 현재 프로세스 생존 여부를 UI가 각자 해석하면
    # `생성 중 0/1 · 100% · 오류 포함 완료`처럼 모순된 상태가 동시에 보인다.
    # 관리자 화면은 아래의 단일 정규 상태만 표시하게 한다.
    if running:
        ui_status = "running"
    elif raw_status == "complete" or (raw_status == "partial" and failed == 0):
        ui_status = "completed"
    elif raw_status == "partial":
        ui_status = "completed_with_errors"
    elif raw_status == "failed":
        ui_status = "failed"
    elif raw_status in {"waiting_for_lock", "waiting_for_report_queue"}:
        ui_status = "waiting"
    elif raw_status in {"running", "stopped"}:
        ui_status = "stopped"
    else:
        ui_status = "idle"
    labels = {
        "running": "진행 중", "completed": "완료",
        "completed_with_errors": "일부 실패", "failed": "실패",
        "waiting": "대기 중", "stopped": "중단됨", "idle": "대기 중",
    }
    payload["raw_status"] = raw_status
    payload["ui_status"] = ui_status
    payload["ui_status_label"] = labels[ui_status]
    payload["is_terminal"] = ui_status in {"completed", "completed_with_errors", "failed", "stopped"}
    payload["can_retry"] = ui_status in {"completed_with_errors", "failed", "stopped"}
    if ui_status == "completed" and total and completed < total:
        # 구버전 작업 상태는 완료 수를 마지막 저장 전에 남기기도 했다.
        payload["display_completed"] = total
    else:
        payload["display_completed"] = completed
    return payload


def _dating_sim_external_image_job():
    """예약 에이전트가 잡은 잠금도 웹 상태 화면에서 숨기지 않는다."""
    # 신고 워커의 자식은 서버 재시작 뒤 고아 프로세스로 계속 작업할 수 있다.
    # 별도 PID 표식을 먼저 확인해 같은 예약을 중복 제출하지 않는다.
    try:
        report_process = json.loads(DATING_SIM_REPORT_PROCESS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        report_process = {}
    if report_process:
        report_pid = int(report_process.get("pid") or 0)
        try:
            os.kill(report_pid, 0)
        except OSError:
            # 서버 재시작 중 고아 자식이 끝났다면 결과 파일 해시로 성공을
            # 복구한다. 결과가 바뀌지 않았을 때만 다시 pending으로 돌린다.
            report_id = str(report_process.get("report_id") or "")
            story_id = str(report_process.get("story_id") or "")
            image_key = str(report_process.get("image_key") or "")
            _book_id, work_dir = dating_sim_story.resolve_book_work_dir(story_id)
            result_file = _dating_sim_image_file_for_key(work_dir, image_key) if work_dir else None
            result_hash = hashlib.sha256(result_file.read_bytes()).hexdigest() if result_file else ""
            before_hash = str(report_process.get("before_sha256") or "")
            changed = bool(before_hash and result_hash and result_hash != before_hash)
            _update_dating_sim_image_report(
                report_id,
                status="done" if changed else "pending",
                finished_at=_now() if changed else None,
                result_sha256=result_hash,
                error="" if changed else "서버 재시작 후 결과 미확인 · 대기열에 자동 복구됨",
            )
            DATING_SIM_REPORT_PROCESS_FILE.unlink(missing_ok=True)
        else:
            return {
                "status": "running", "running": True, "external": True,
                "current": report_process.get("image_key") or "신고 이미지 재생성",
                "total": 1, "completed": 0, "failed": 0, "current_index": 1,
                "started_at": report_process.get("started_at"), "pid": report_pid,
                "job_type": "reported_image", "report_id": report_process.get("report_id"),
            }
    lock_path = Path(os.path.expanduser("~/.tulpachat/dating_sim_daily_agent.lock"))
    state_path = Path(os.path.expanduser("~/.tulpachat/dating_sim_daily_agent.json"))
    if not lock_path.exists():
        return None
    try:
        pid = int(lock_path.read_text(encoding="ascii").strip())
        os.kill(pid, 0)
    except (OSError, ValueError):
        return None
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        state = {}

    # 일괄 이미지 생성기는 daily-agent 잠금을 함께 사용하지만 진행 정보는
    # 별도 backlog 파일에 기록한다. 서버 재시작 뒤 메모리 작업 정보가 사라진
    # 경우, 오래된 daily-agent 실패 기록을 현재 작업으로 오인하지 않도록
    # 더 최근에 갱신된 backlog 상태를 우선한다.
    try:
        backlog_state = _dating_sim_image_backlog_state()
        backlog_updated = DATING_SIM_IMAGE_BACKLOG_STATE.stat().st_mtime
        daily_updated = state_path.stat().st_mtime
        if backlog_state and backlog_updated > daily_updated:
            payload = _dating_sim_image_backlog_progress(backlog_state, True)
            payload["external"] = True
            payload["running"] = True
            payload["pid"] = pid
            return payload
    except OSError:
        pass
    current = state.get("work")
    payload = {"status": "running", "running": True, "external": True,
               "current": current, "total": 1, "completed": 0, "failed": 0,
               "current_index": 1, "started_at": state.get("started_at"), "pid": pid}
    return _dating_sim_image_backlog_progress(payload, True)


def _dating_sim_image_job_status(book_id, work_dir):
    progress = {"done": 0, "total": 0, "percent": 0, "current": "준비 중"}
    try:
        manifest_path = work_dir / "dating_sim_images" / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        saved = manifest.get("job_progress") or {}
        progress = {
            "done": max(0, int(saved.get("done") or 0)),
            "total": max(0, int(saved.get("total") or 0)),
            "percent": max(0, min(100, int(saved.get("percent") or 0))),
            "current": str(saved.get("current") or "생성 중"),
        }
    except (OSError, ValueError, TypeError):
        pass
    with _dating_sim_image_jobs_lock:
        job = _dating_sim_image_jobs.get(book_id)
        if not job:
            return {"running": False, **progress}
        returncode = job["process"].poll()
        if returncode is None:
            return {"running": True, "started_at": job["started_at"], **progress}
        del _dating_sim_image_jobs[book_id]
    job["log_file"].close()
    log_tail = ""
    try:
        log_tail = job["log_path"].read_text(encoding="utf-8", errors="replace")[-800:]
    except OSError:
        pass
    return {
        "running": False, "returncode": returncode,
        "started_at": job["started_at"], "log_tail": log_tail, **progress,
    }


def _push_when_dating_sim_images_done(process, username, story_id, label):
    """프로세스를 회수한다. 실제 알림은 영구 표식을 보는 복구 가능 감시기가 담당한다."""
    if not hasattr(process, "wait"):
        return
    try:
        process.wait()
    except Exception as exc:  # noqa: BLE001
        print(f"⚠️ 미연시 이미지 완료 알림 실패: {exc}")


def _write_dating_sim_teacher_notification(work_dir, username, story_id, label):
    marker = Path(work_dir) / "dating_sim_images" / DATING_SIM_TEACHER_NOTIFICATION
    payload = {
        "status": "pending", "username": username, "story_id": story_id,
        "label": label, "requested_at": int(time.time()),
    }
    temporary = marker.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, marker)


def _dating_sim_completion_content(title: str, url: str) -> str:
    return f"「{title}」 이미지 생성이 모두 끝났습니다.\n\n[완성된 미연시 보러가기]({url})"


def _repair_dating_sim_teacher_notification(marker: Path, request_data: dict) -> bool:
    message_id = int(request_data.get("message_id") or 0)
    if message_id < 1:
        return False
    try:
        manifest = json.loads((marker.parent / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    title = str(manifest.get("title") or marker.parent.parent.name)
    story_id = str(request_data.get("story_id") or f"work:{marker.parent.parent.name}")
    book_key = story_id.split(":", 1)[-1]
    url = f"/dating-sim/?book={urllib.parse.quote(book_key, safe='')}"
    content = _dating_sim_completion_content(title, url)
    conn = get_conn()
    try:
        cursor = conn.execute(
            "UPDATE messages SET content=? WHERE id=? AND content NOT LIKE ?",
            (content, message_id, "%완성된 미연시 보러가기%"),
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def _deliver_dating_sim_teacher_notification(marker: Path):
    with _DATING_SIM_TEACHER_NOTIFICATION_LOCK:
        try:
            request_data = json.loads(marker.read_text(encoding="utf-8"))
            if request_data.get("status") != "pending":
                if request_data.get("status") == "sent":
                    _repair_dating_sim_teacher_notification(marker, request_data)
                return False
            manifest_path = marker.parent / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return False
        progress = manifest.get("job_progress") or {}
        if (manifest.get("status") != "complete" or manifest.get("quality_status") != "passed"
                or int(progress.get("percent") or 0) < 100):
            return False
        title = str(manifest.get("title") or marker.parent.parent.name)
        username = str(request_data.get("username") or APP_USERNAME or "").strip()
        if not username:
            return False
        story_id = str(request_data.get("story_id") or f"work:{marker.parent.parent.name}")
        book_key = story_id.split(":", 1)[-1]
        url = f"/dating-sim/?book={urllib.parse.quote(book_key, safe='')}"
        content = _dating_sim_completion_content(title, url)
        conn = get_conn()
        try:
            cursor = conn.execute(
                "INSERT INTO messages (room_id, sender, content, created_at) VALUES (?, ?, ?, ?)",
                ("일본어 선생님", "일본어 선생님", content, _now()),
            )
            _send_web_push_to_user(conn, username, "일본어 선생님 · 미연시 이미지 완성",
                                   content, url)
            request_data.update({"status": "sent", "sent_at": int(time.time()),
                                 "message_id": cursor.lastrowid})
            temporary = marker.with_suffix(".tmp")
            temporary.write_text(json.dumps(request_data, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(temporary, marker)
            conn.commit()
        finally:
            conn.close()
        return True


def _watch_dating_sim_teacher_notifications_forever():
    library = REPO_ROOT / "일본어자막추출" / "library"
    while True:
        try:
            for marker in library.glob(f"*/dating_sim_images/{DATING_SIM_TEACHER_NOTIFICATION}"):
                _deliver_dating_sim_teacher_notification(marker)
        except Exception as exc:  # noqa: BLE001
            print(f"⚠️ 일본어 선생님 이미지 완료 알림 감시 실패: {exc}")
        time.sleep(30)


def _push_when_dating_sim_image_backlog_done(process, username):
    global _dating_sim_image_backlog_job
    try:
        returncode = process.wait()
        state = _dating_sim_image_backlog_state()
        completed = int(state.get("completed") or 0)
        failed = int(state.get("failed") or 0)
        conn = get_conn()
        try:
            _send_web_push_to_user(
                conn, username,
                "미연시 잔여 이미지 생성 완료" if returncode == 0 else "미연시 잔여 이미지 생성 확인 필요",
                f"완료 {completed}편 · 실패 {failed}편",
                "/dating-sim/",
            )
            conn.commit()
        finally:
            conn.close()
    except Exception as exc:  # noqa: BLE001
        print(f"⚠️ 미연시 잔여 이미지 완료 알림 실패: {exc}")
    finally:
        with _dating_sim_image_jobs_lock:
            job = _dating_sim_image_backlog_job
            if job and job.get("process") is process:
                job["log_file"].close()
                _dating_sim_image_backlog_job = None


DATING_SIM_IMAGE_KEY_RE = re.compile(r"^[A-Za-z0-9_:-]{1,64}$")


class DatingSimImagePromptRequest(BaseModel):
    prompt_override: str | None = None
    exact_prompt_override: bool = False
    negative_prompt_override: str | None = None
    negative_prompt_enabled: bool = True
    keywords: list[str] | None = None
    settings: dict[str, Any] | None = None


class DatingSimImageReportRequest(BaseModel):
    story_id: str
    image_key: str
    day: int
    location: str
    adult_mode: bool = False
    reason: str = "이미지가 이상함"


class DatingSimImageLikeRequest(BaseModel):
    story_id: str
    image_key: str
    liked: bool = True


class DatingSimImageImprovementRequest(BaseModel):
    story_id: str
    image_key: str
    improvement: str
    day: int = 0
    location: str = "image-gallery"


class DatingSimAdminPromptRequest(BaseModel):
    name: str
    prompt: str
    negative_prompt: str = ""
    negative_prompt_enabled: bool = True
    enabled: bool = True


class DatingSimPromptSettingsRequest(BaseModel):
    common_negative_prompt: str = ""
    common_negative_enabled: bool = True


class DatingSimPortraitSelectRequest(BaseModel):
    image_key: str
    # 쿼리 문자열이 모바일 캐시·이전 프런트엔드에서 누락되더라도 선택한
    # 작품을 잃지 않도록 본문에도 같은 식별자를 받는다.
    story_id: str | None = None


class DatingSimQualityAttemptSelectRequest(BaseModel):
    story_id: str
    image_key: str
    attempt: int


class ComfyUIRuntimeRequest(BaseModel):
    enabled: bool


class ComfyWorkspaceActionRequest(BaseModel):
    action: str


class DatingSimImageGenerationControlRequest(BaseModel):
    action: str


COMFY_MODEL_CATALOG = (
    {
        "id": "majicmix-realistic",
        "name": "majicMIX Realistic",
        "family": "SD 1.5",
        "filenames": ("majicmixrealistic", "majicmix_realistic"),
        "summary": "인물 사진과 일상 장면에 강한 사실적 계열 모델입니다. 현재 미연시 인물·장면 생성의 기본 모델로 사용 중입니다.",
        "best_for": ("사실적인 인물 초상", "일상·데이트 장면", "부드러운 피부와 조명"),
        "caution": "손·눈처럼 작은 구조는 참조 이미지 품질과 프롬프트에 영향을 많이 받습니다.",
        "url": "https://civitai.com/models/43331/majicmix-realistic",
    },
    {
        "id": "epicrealism",
        "name": "epiCRealism",
        "family": "SD 1.5",
        "filenames": ("epicrealism",),
        "summary": "자연스러운 피부 질감과 영화 같은 빛을 내는 사실적 인물 모델입니다.",
        "best_for": ("감정이 드러나는 얼굴", "영화풍 인물 컷", "실내·야간 조명"),
        "caution": "작품별 동일 인물 유지에는 IP-Adapter 같은 참조 제어가 필요합니다.",
        "url": "https://civitai.com/models/25694/epicrealism",
    },
    {
        "id": "dreamshaper",
        "name": "DreamShaper",
        "family": "SD 1.5 / XL",
        "filenames": ("dreamshaper",),
        "summary": "실사와 일러스트 사이를 폭넓게 다루는 범용 모델로, 배경과 콘셉트 장면을 만들기 좋습니다.",
        "best_for": ("다양한 배경", "도트풍이 아닌 콘셉트 아트", "실사·일러스트 혼합"),
        "caution": "버전에 따라 기반 모델이 다르므로 워크플로의 SD 1.5·SDXL 호환을 확인해야 합니다.",
        "url": "https://civitai.com/models/4384/dreamshaper",
    },
    {
        "id": "juggernaut-xl",
        "name": "Juggernaut XL",
        "family": "SDXL",
        "filenames": ("juggernautxl", "juggernaut_xl"),
        "summary": "고해상도 실사 인물과 풍부한 배경 묘사에 적합한 SDXL 계열 모델입니다.",
        "best_for": ("고해상도 인물", "넓은 장면과 배경", "광고·시네마틱 사진"),
        "caution": "현재 SD 1.5 워크플로보다 메모리와 생성 시간이 더 필요하며 별도 SDXL 워크플로가 필요합니다.",
        "url": "https://civitai.com/models/133005/juggernaut-xl",
    },
    {
        "id": "realistic-vision",
        "name": "Realistic Vision",
        "family": "SD 1.5",
        "filenames": ("realisticvision", "realistic_vision"),
        "summary": "인물·제품·실내외 사진을 안정적으로 만드는 대표적인 사실적 SD 1.5 모델입니다.",
        "best_for": ("일상 인물 사진", "제품과 소품", "실내외 현실적 장면"),
        "caution": "모델 버전에 맞는 VAE와 권장 설정을 함께 확인해야 색감 차이를 줄일 수 있습니다.",
        "url": "https://civitai.com/models/4201/realistic-vision-v60-b1",
    },
)


def _comfy_workspace_model_catalog():
    checkpoint_dir = Path.home() / "Applications/ComfyUI/models/checkpoints"
    installed_files = []
    try:
        installed_files = sorted(
            path.name for path in checkpoint_dir.iterdir()
            if path.is_file() and path.suffix.lower() in {".safetensors", ".ckpt", ".pt"}
        )
    except OSError:
        pass
    lowered = {name.lower(): name for name in installed_files}
    models = []
    for model in COMFY_MODEL_CATALOG:
        match = next((original for low, original in lowered.items()
                      if any(token in low for token in model["filenames"])), None)
        models.append({
            key: (list(value) if isinstance(value, tuple) else value)
            for key, value in model.items() if key != "filenames"
        } | {"installed": bool(match), "installed_file": match or ""})
    return {"models": models, "installed_files": installed_files}


def _comfy_workspace_animation_capability():
    custom_nodes = Path.home() / "Applications/ComfyUI/custom_nodes"
    node_names = []
    try:
        node_names = [path.name.lower() for path in custom_nodes.iterdir() if path.is_dir()]
    except OSError:
        pass
    has_video_helper = any("videohelpersuite" in name or "video_helper" in name for name in node_names)
    has_animatediff = any("animatediff" in name for name in node_names)
    motion_files = []
    for relative in ("animatediff_models", "animatediff", "motion_models"):
        folder = Path.home() / "Applications/ComfyUI/models" / relative
        try:
            motion_files.extend(path.name for path in folder.iterdir() if path.is_file())
        except OSError:
            continue
    missing = []
    if not has_video_helper:
        missing.append("Video Helper Suite(GIF 저장)")
    if not has_animatediff:
        missing.append("AnimateDiff-Evolved(움직임 생성)")
    if not motion_files:
        missing.append("AnimateDiff 모션 모델")
    return {
        "supported": True,
        "export_ready": has_video_helper,
        "motion_ready": has_video_helper and has_animatediff and bool(motion_files),
        "video_helper_installed": has_video_helper,
        "animatediff_installed": has_animatediff,
        "motion_models": sorted(set(motion_files)),
        "missing": missing,
        "summary": (
            "움직이는 장면 생성과 GIF 저장을 바로 사용할 수 있습니다."
            if has_video_helper and has_animatediff and motion_files else
            "GIF 작업은 가능하지만 현재 설치에는 애니메이션 생성·저장 구성요소가 부족합니다."
        ),
        "docs": {
            "video_helper": "https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite",
            "animatediff": "https://github.com/Kosinkadink/ComfyUI-AnimateDiff-Evolved",
        },
    }


def _comfyui_json(path: str, payload: dict | None = None):
    """고정된 ComfyUI API 경로만 호출한다. 브라우저 입력을 URL로 쓰지 않는다."""
    api_request = urllib.request.Request(
        f"http://127.0.0.1:8188{path}",
        data=(json.dumps(payload).encode("utf-8") if payload is not None else None),
        headers={"Content-Type": "application/json"},
        method="POST" if payload is not None else "GET",
    )
    with urllib.request.urlopen(api_request, timeout=3) as response:
        raw = response.read()
    return json.loads(raw.decode("utf-8")) if raw else {}


def _comfyui_queue_summary():
    try:
        queue = _comfyui_json("/queue")
    except (OSError, ValueError, urllib.error.URLError):
        return {"running": [], "pending": [], "running_count": 0, "pending_count": 0}

    def summarize(rows):
        result = []
        for row in rows if isinstance(rows, list) else []:
            if not isinstance(row, list) or len(row) < 2:
                continue
            prompt = row[2] if len(row) > 2 and isinstance(row[2], dict) else {}
            checkpoint = ""
            output_prefix = ""
            for node in prompt.values():
                if not isinstance(node, dict):
                    continue
                inputs = node.get("inputs") if isinstance(node.get("inputs"), dict) else {}
                checkpoint = checkpoint or str(inputs.get("ckpt_name") or "")
                output_prefix = output_prefix or str(inputs.get("filename_prefix") or "")
            result.append({"prompt_id": str(row[1]), "node_count": len(prompt),
                           "checkpoint": checkpoint, "output_prefix": output_prefix})
        return result

    running = summarize(queue.get("queue_running"))
    pending = summarize(queue.get("queue_pending"))
    return {"running": running, "pending": pending,
            "running_count": len(running), "pending_count": len(pending)}


def _terminate_dating_image_process(process):
    """새 세션으로 띄운 이미지 생성기와 그 자식까지 함께 종료한다."""
    if not process or process.poll() is not None:
        return False
    try:
        os.killpg(os.getpgid(process.pid), signal.SIGTERM)
    except (OSError, ProcessLookupError):
        try:
            process.terminate()
        except OSError:
            return False
    return True


def _write_image_generation_pause(paused: bool):
    if paused:
        DATING_SIM_IMAGE_PAUSE_FILE.parent.mkdir(parents=True, exist_ok=True)
        temporary = DATING_SIM_IMAGE_PAUSE_FILE.with_suffix(".tmp")
        temporary.write_text(json.dumps({"paused": True, "updated_at": _now()}, ensure_ascii=False), encoding="utf-8")
        os.replace(temporary, DATING_SIM_IMAGE_PAUSE_FILE)
    else:
        DATING_SIM_IMAGE_PAUSE_FILE.unlink(missing_ok=True)


def _comfyui_log_tail(max_chars=12000):
    chunks = []
    for path in (Path.home() / "Library/Logs/ComfyUI/stderr.log",
                 Path.home() / "Library/Logs/ComfyUI/stdout.log"):
        try:
            chunks.append(f"[{path.name}]\n" + path.read_text(
                encoding="utf-8", errors="replace")[-max_chars // 2:])
        except OSError:
            continue
    return "\n\n".join(chunks)[-max_chars:]


def _comfy_work_preview(work_name: str, requested_file: str | None = None):
    """작품별로 마지막에 완성된 이미지와 안전한 미리보기 경로를 찾는다."""
    safe_work = Path(str(work_name or "")).name
    if not safe_work or safe_work != str(work_name or ""):
        return None
    library_root = (JP_SUBTITLE_DIR / "library").resolve()
    work_dir = (library_root / safe_work).resolve()
    try:
        work_dir.relative_to(library_root)
    except ValueError:
        return None
    image_dir = work_dir / "dating_sim_images"
    try:
        manifest = json.loads((image_dir / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None
    allowed = set()
    portrait = manifest.get("portrait")
    if isinstance(portrait, str):
        allowed.add(Path(portrait).name)
    scenes = manifest.get("scenes")
    if isinstance(scenes, dict):
        for scene in scenes.values():
            if isinstance(scene, str):
                allowed.add(Path(scene).name)
            elif isinstance(scene, dict):
                for key in ("file", "filename", "image", "path"):
                    value = scene.get(key)
                    if isinstance(value, str):
                        allowed.add(Path(value).name)
    candidates = []
    for filename in allowed:
        target = (image_dir / filename).resolve()
        try:
            target.relative_to(image_dir.resolve())
            if target.is_file() and target.stat().st_size >= 1024:
                candidates.append(target)
        except (OSError, ValueError):
            continue
    if requested_file:
        wanted = Path(requested_file).name
        if wanted != requested_file:
            return None
        target = next((item for item in candidates if item.name == wanted), None)
    else:
        target = max(candidates, key=lambda item: item.stat().st_mtime, default=None)
    if target is None:
        return None
    modified = int(target.stat().st_mtime)
    return {
        "path": target,
        "filename": target.name,
        "url": "/api/comfy-workspace/preview?" + urllib.parse.urlencode({
            "work": safe_work, "file": target.name, "v": modified,
        }),
        "updated_at": datetime.datetime.fromtimestamp(
            modified, tz=datetime.timezone.utc).isoformat(),
    }


def _comfy_work_history(work_name: str):
    """매니페스트에 남은 현재 작품의 생성 결과를 최신순으로 돌려준다."""
    latest = _comfy_work_preview(work_name)
    if not latest:
        return []
    image_dir = latest["path"].parent
    try:
        manifest = json.loads((image_dir / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return []
    names = []
    portrait = manifest.get("portrait")
    if isinstance(portrait, str):
        names.append(Path(portrait).name)
    for value in (manifest.get("scenes") or {}).values():
        if isinstance(value, str):
            names.append(Path(value).name)
        elif isinstance(value, dict):
            for key in ("file", "filename", "image", "path"):
                if isinstance(value.get(key), str):
                    names.append(Path(value[key]).name)
                    break
    results = []
    for name in dict.fromkeys(names):
        item = _comfy_work_preview(work_name, name)
        if item:
            results.append({k: v for k, v in item.items() if k != "path"})
    return sorted(results, key=lambda item: item.get("updated_at", ""), reverse=True)


def _comfy_work_context(work_name: str, requested_file: str | None = None):
    """현재 결과의 프롬프트·설정·참조본을 매니페스트 이력에서 읽는다."""
    preview = _comfy_work_preview(work_name, requested_file)
    if not preview:
        return None
    image_dir = preview["path"].parent
    manifest = json.loads((image_dir / "manifest.json").read_text(encoding="utf-8"))
    image_key = "portrait" if preview["filename"] == Path(str(manifest.get("portrait") or "")).name else ""
    record = None
    for key, value in (manifest.get("scenes") or {}).items():
        if isinstance(value, dict) and Path(str(value.get("file") or "")).name == preview["filename"]:
            image_key, record = str(key), value
            break
    if image_key == "portrait":
        prompt = str(manifest.get("portrait_prompt") or "")
        effective_prompt = str(manifest.get("portrait_effective_prompt") or "")
        effective_negative_prompt = str(manifest.get("portrait_effective_negative_prompt") or "")
        settings = manifest.get("portrait_generation_settings") or {}
        reference_files = manifest.get("portrait_references") or []
    elif record:
        prompt = str(record.get("prompt") or "")
        effective_prompt = str(record.get("effective_prompt") or "")
        effective_negative_prompt = str(record.get("effective_negative_prompt") or "")
        settings = record.get("generation_settings") or {}
        reference_files = record.get("source_reference_files") or []
        if record.get("reference_file"):
            reference_files = [record["reference_file"], *reference_files]
    else:
        prompt, effective_prompt, effective_negative_prompt, settings, reference_files = "", "", "", {}, []
    allowed = []
    for value in reference_files:
        name = Path(str(value)).name
        target = (image_dir / name).resolve()
        try:
            target.relative_to(image_dir.resolve())
            if target.is_file() and name not in allowed:
                allowed.append(name)
        except (OSError, ValueError):
            continue
    return {
        "preview": {k: v for k, v in preview.items() if k != "path"},
        "image_key": image_key, "prompt": prompt, "effective_prompt": effective_prompt,
        "effective_negative_prompt": effective_negative_prompt,
        "settings": settings,
        "history": _comfy_work_history(work_name),
        "references": [{"name": name, "url": "/api/comfy-workspace/reference?" +
                        urllib.parse.urlencode({"work": Path(work_name).name, "image": preview["filename"], "file": name})}
                       for name in allowed],
    }


def _validated_image_settings(raw):
    raw = raw if isinstance(raw, dict) else {}
    rules = {
        "width": (int, 256, 1536), "height": (int, 256, 1536),
        "steps": (int, 5, 80), "cfg": (float, 1, 20),
        "denoise": (float, 0.05, 1),
        "hires_scale": (float, 1, 2), "hires_steps": (int, 4, 30),
        "hires_denoise": (float, 0.05, 0.6),
    }
    result = {}
    for key, (cast, low, high) in rules.items():
        if key not in raw:
            continue
        try:
            value = cast(raw[key])
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=f"{key} 설정값이 올바르지 않습니다") from exc
        if not low <= value <= high:
            raise HTTPException(status_code=400, detail=f"{key} 설정 범위를 확인해 주세요")
        if key in {"width", "height"} and value % 64:
            raise HTTPException(status_code=400, detail="이미지 크기는 64의 배수여야 합니다")
        result[key] = value
    choices = {"sampler": {"dpmpp_2m", "euler", "euler_ancestral"},
               "scheduler": {"karras", "normal", "simple"}}
    for key, allowed in choices.items():
        if key in raw:
            value = str(raw[key])
            if value not in allowed:
                raise HTTPException(status_code=400, detail=f"지원하지 않는 {key} 설정입니다")
            result[key] = value
    return result


@app.get("/api/comfy-workspace/preview")
def comfy_workspace_preview(request: Request, work: str, file: str):
    """관리자에게만 현재 생성 결과를 파일 단위로 제공한다."""
    _require_owner(request)
    preview = _comfy_work_preview(work, file)
    if not preview:
        raise HTTPException(status_code=404, detail="미리보기 이미지를 찾을 수 없습니다")
    return FileResponse(preview["path"], headers={"Cache-Control": "no-store"})


@app.get("/api/comfy-workspace/image-detail")
def comfy_workspace_image_detail(request: Request, work: str, file: str):
    _require_owner(request)
    context = _comfy_work_context(work, file)
    if not context:
        raise HTTPException(status_code=404, detail="이미지 생성 이력을 찾을 수 없습니다")
    return context


@app.get("/api/comfy-workspace/reference")
def comfy_workspace_reference(request: Request, work: str, image: str, file: str):
    _require_owner(request)
    context = _comfy_work_context(work, image)
    allowed = {item["name"] for item in (context or {}).get("references", [])}
    safe_file = Path(file).name
    if safe_file != file or safe_file not in allowed:
        raise HTTPException(status_code=404, detail="참조 이미지를 찾을 수 없습니다")
    target = (JP_SUBTITLE_DIR / "library" / Path(work).name / "dating_sim_images" / safe_file).resolve()
    return FileResponse(target, headers={"Cache-Control": "private, max-age=300"})


@app.get("/api/comfy-workspace/status")
def comfy_workspace_status(request: Request):
    """관리자용 이미지 작업 시스템의 단일 상태 스냅샷."""
    _require_owner(request)
    runtime = _comfyui_runtime_status()
    queue = _comfyui_queue_summary() if runtime["comfy_online"] else {
        "running": [], "pending": [], "running_count": 0, "pending_count": 0,
    }
    with _dating_sim_image_jobs_lock:
        backlog_job = _dating_sim_image_backlog_job
        backlog_running = bool(backlog_job and backlog_job["process"].poll() is None)
        individual = [(book_id, item) for book_id, item in _dating_sim_image_jobs.items()
                      if item["process"].poll() is None]
    external = None if backlog_running else _dating_sim_external_image_job()
    backlog = _dating_sim_image_backlog_progress(
        _dating_sim_image_backlog_state(), backlog_running)
    backlog["running"] = backlog_running
    if external:
        backlog = external
    active = []
    if backlog.get("running"):
        work = backlog.get("current") or "준비 중"
        preview = _comfy_work_preview(work)
        active.append({"kind": "일괄 생성", "work": work,
                       "task": backlog.get("current_image_job") or "이미지 생성",
                       "percent": backlog.get("current_image_percent") or backlog.get("percent") or 0,
                       "preview": ({k: v for k, v in preview.items() if k != "path"}
                                   if preview else None)})
    for book_id, item in individual:
        detail = _dating_sim_image_job_status(book_id, Path(item.get("work_dir") or ""))
        work = Path(item.get("work_dir") or book_id).name
        preview = _comfy_work_preview(work)
        active.append({"kind": "개별 생성", "work": work,
                       "task": detail.get("current") or "이미지 생성",
                       "percent": detail.get("percent") or 0,
                       "preview": ({k: v for k, v in preview.items() if k != "path"}
                                   if preview else None)})
    return {**runtime, "queue": queue, "backlog": backlog, "active_jobs": active,
            "log_tail": _comfyui_log_tail(), "checked_at": _now()}


@app.get("/api/comfy-workspace/models")
def comfy_workspace_models(request: Request):
    """관리자용 읽기 전용 모델 카탈로그와 GIF 준비 상태."""
    _require_owner(request)
    return {**_comfy_workspace_model_catalog(),
            "animation": _comfy_workspace_animation_capability(),
            "checked_at": _now()}


@app.post("/api/comfy-workspace/action")
def comfy_workspace_action(payload: ComfyWorkspaceActionRequest, request: Request):
    """임의 명령 없이 미리 허용한 Comfy 개입만 실행한다."""
    _require_owner(request)
    if payload.action not in {"interrupt", "clear_pending"}:
        raise HTTPException(status_code=400, detail="지원하지 않는 작업입니다")
    if not _comfyui_runtime_status()["comfy_online"]:
        raise HTTPException(status_code=409, detail="ComfyUI가 꺼져 있습니다")
    try:
        if payload.action == "interrupt":
            _comfyui_json("/interrupt", {})
            message = "현재 Comfy 이미지 생성을 중단 요청했습니다"
        else:
            _comfyui_json("/queue", {"clear": True})
            message = "Comfy 대기열을 비웠습니다"
    except (OSError, ValueError, urllib.error.URLError) as exc:
        raise HTTPException(status_code=503, detail="ComfyUI에 개입 요청을 전달하지 못했습니다") from exc
    return {"ok": True, "message": message}


@app.post("/api/dating-sim/image-generation/control")
def dating_sim_image_generation_control(payload: DatingSimImageGenerationControlRequest, request: Request):
    """전체 이미지 생성의 재투입을 막고 프로세스와 Comfy 큐를 함께 멈춘다."""
    _require_owner(request)
    if payload.action not in {"stop", "resume"}:
        raise HTTPException(status_code=400, detail="지원하지 않는 이미지 생성 제어입니다")
    if payload.action == "resume":
        _write_image_generation_pause(False)
        return {"ok": True, "paused": False, "message": "이미지 생성을 다시 시작할 수 있습니다"}

    # 종료 도중 예약 작업이 큐를 다시 채우지 못하도록 중지 표식을 먼저 남긴다.
    _write_image_generation_pause(True)
    stopped = 0
    with _dating_sim_image_jobs_lock:
        if _dating_sim_image_backlog_job:
            stopped += int(_terminate_dating_image_process(_dating_sim_image_backlog_job.get("process")))
        for item in _dating_sim_image_jobs.values():
            stopped += int(_terminate_dating_image_process(item.get("process")))
    external = _dating_sim_external_image_job()
    if external and external.get("pid"):
        try:
            os.killpg(os.getpgid(int(external["pid"])), signal.SIGTERM)
            stopped += 1
        except (OSError, ProcessLookupError, ValueError):
            pass
    try:
        _comfyui_json("/interrupt", {})
        _comfyui_json("/queue", {"clear": True})
    except (OSError, ValueError, urllib.error.URLError):
        pass
    state = _dating_sim_image_backlog_state()
    state.update(status="stopped", current=None, error="관리자가 전체 이미지 생성을 중지했습니다",
                 updated_at_epoch=int(time.time()), finished_at=_now())
    DATING_SIM_IMAGE_BACKLOG_STATE.parent.mkdir(parents=True, exist_ok=True)
    temporary = DATING_SIM_IMAGE_BACKLOG_STATE.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, DATING_SIM_IMAGE_BACKLOG_STATE)
    return {"ok": True, "paused": True, "stopped_processes": stopped,
            "message": "전체 이미지 생성을 중지하고 ComfyUI 대기열을 비웠습니다"}


def _validated_dating_sim_admin_prompt(payload: DatingSimAdminPromptRequest, prompt_id=None):
    name = re.sub(r"\s+", " ", payload.name).strip()
    prompt = payload.prompt.strip()
    negative = payload.negative_prompt.strip()
    if not name or len(name) > 120:
        raise HTTPException(status_code=400, detail="프롬프트 이름은 1~120자로 입력해 주세요")
    if not prompt or len(prompt) > 8000 or len(negative) > 8000:
        raise HTTPException(status_code=400, detail="긍정·부정 프롬프트는 각각 8,000자 이내로 입력해 주세요")
    unsafe = re.compile(
        r"(?i)(?:\bchild\b|\bminor\b|\bunderage\b|미성년|아동\s*(?:성적|노출))"
    )
    if unsafe.search(prompt):
        raise HTTPException(status_code=400, detail="미성년자를 대상으로 한 생성 지시는 저장할 수 없습니다")
    return {
        "id": prompt_id or uuid.uuid4().hex,
        "name": name, "prompt": prompt, "negative_prompt": negative,
        "negative_prompt_enabled": bool(payload.negative_prompt_enabled),
        "enabled": bool(payload.enabled), "updated_at": _now(),
    }


@app.get("/api/dating-sim/admin-prompts")
def dating_sim_admin_prompts_list(request: Request):
    _require_owner(request)
    return {"prompts": _read_dating_sim_admin_prompts(),
            "settings": _read_dating_sim_prompt_settings()}


@app.put("/api/dating-sim/admin-prompt-settings")
def dating_sim_admin_prompt_settings_update(payload: DatingSimPromptSettingsRequest, request: Request):
    _require_owner(request)
    negative = payload.common_negative_prompt.strip()
    if len(negative) > 8000:
        raise HTTPException(status_code=400, detail="공통 부정 프롬프트는 8,000자 이내로 입력해 주세요")
    settings = {"common_negative_prompt": negative,
                "common_negative_enabled": bool(payload.common_negative_enabled)}
    with _DATING_SIM_ADMIN_PROMPTS_LOCK:
        rows = _read_dating_sim_admin_prompts()
        DATING_SIM_ADMIN_PROMPTS_FILE.parent.mkdir(parents=True, exist_ok=True)
        stored = {"version": 2, "updated_at": _now(), "settings": settings, "prompts": rows}
        temporary = DATING_SIM_ADMIN_PROMPTS_FILE.with_suffix(".tmp")
        temporary.write_text(json.dumps(stored, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, DATING_SIM_ADMIN_PROMPTS_FILE)
    return settings


@app.get("/api/dating-sim/admin-images")
def dating_sim_admin_images_dashboard(request: Request):
    """관리자 프롬프트 이미지의 진행 중/완료 상태를 작품별로 모아 보여준다."""
    _require_owner(request)
    liked_keys = {
        (str(item.get("story_id") or ""), str(item.get("image_key") or ""))
        for item in _read_dating_sim_image_likes()
    }
    active_reports = {
        (str(item.get("story_id") or ""), str(item.get("image_key") or "")): item
        for item in _read_dating_sim_image_reports()
        if item.get("status") in {"pending", "processing"}
    }
    active_improvements = {}
    for item in _read_dating_sim_image_reports():
        if item.get("status") in {"pending", "processing"} and item.get("job_type") in {"anatomy", "eyes", "sharpness"}:
            active_improvements.setdefault(
                (str(item.get("story_id") or ""), str(item.get("image_key") or "")), {}
            )[str(item.get("job_type"))] = {"status": item.get("status"), "id": item.get("id")}
    with _dating_sim_image_jobs_lock:
        running_jobs = {
            book_id: dict(job) for book_id, job in _dating_sim_image_jobs.items()
            if job.get("job_type") == "admin_prompts" and job["process"].poll() is None
        }
    active_prompt_count = sum(1 for item in _read_dating_sim_admin_prompts() if item.get("enabled") is not False)
    running, completed = [], []
    for book_id in dating_sim_story.all_book_ids():
        story_id = f"book:{book_id}"
        _, work_dir = dating_sim_story.resolve_book_work_dir(story_id)
        if not work_dir:
            continue
        manifest_path = work_dir / "dating_sim_images" / "manifest.json"
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            manifest = {}
        quality_checks = manifest.get("quality_checks") or {}
        images = []
        for prompt_id, record in (manifest.get("admin_prompt_images") or {}).items():
            if not isinstance(record, dict) or not re.fullmatch(r"[0-9a-f]{32}", str(prompt_id)):
                continue
            filename = record.get("file")
            target = work_dir / "dating_sim_images" / str(filename or "")
            if filename != f"admin-{prompt_id}.png" or not target.is_file():
                continue
            report = quality_checks.get(f"admin:{prompt_id}")
            images.append({
                "key": f"admin:{prompt_id}", "kind": "admin_prompt", "admin_only": True,
                "label": record.get("name") or "관리자 프롬프트",
                "image_url": f"/api/dating-sim/books/{book_id}/admin-images/{filename}?t={int(target.stat().st_mtime)}",
                "prompt": record.get("prompt") or "",
                "effective_prompt": record.get("effective_prompt") or record.get("prompt") or "",
                "effective_negative_prompt": record.get("effective_negative_prompt") or record.get("negative_prompt") or "",
                "generation_settings": record.get("generation_settings") or {},
                "provider": record.get("provider") or "",
                "quality_passed": report.get("passed") is True if isinstance(report, dict) else None,
                "quality_reasons": report.get("reasons") or [] if isinstance(report, dict) else [],
                "updated_at": int(target.stat().st_mtime),
            })
        images.sort(key=lambda item: item["updated_at"], reverse=True)
        job = running_jobs.get(book_id)
        progress = manifest.get("job_progress") or {}
        persisted_running = (
            manifest.get("status") == "running"
            and int(progress.get("total") or 0) > int(progress.get("done") or 0)
            and "관리자 프롬프트" in str(progress.get("current") or "")
        )
        if not images and not job and not persisted_running:
            continue
        row = {
            "story_id": story_id,
            "title": manifest.get("title") or work_dir.name,
            "work": work_dir.name,
            "images": images,
            "image_count": len(images),
            "updated_at": max([item["updated_at"] for item in images] or [0]),
        }
        for image in images:
            key = (story_id, str(image.get("key") or ""))
            report = active_reports.get(key)
            image["liked"] = key in liked_keys
            image["report_status"] = report.get("status") if report else ""
            image["report_id"] = report.get("id") if report else ""
            image["improvement_jobs"] = active_improvements.get(key, {})
        if job or persisted_running:
            # 전체 이미지 실행은 대표 초상화·일반 장면 뒤에 관리자 프롬프트를
            # 이어 만든다. manifest의 done/total은 전체 작업 수치이므로 관리자
            # 대시보드에서는 실제 admin 파일 수만 따로 센다.
            total = max(0, int((job or {}).get("expected_total") or active_prompt_count))
            done = min(total or 10**9, len(images))
            row.update({
                "done": done, "total": total,
                "percent": max(0, min(100, round(done * 100 / total) if total else 0)),
                "current": str(progress.get("current") or "관리자 이미지 생성 중"),
                "started_at": (job or {}).get("started_at") or progress.get("started_at"),
            })
            running.append(row)
        else:
            completed.append(row)
    running.sort(key=lambda item: item.get("started_at") or 0, reverse=True)
    completed.sort(key=lambda item: item.get("updated_at") or 0, reverse=True)
    return {
        "running": running, "completed": completed,
        "running_count": len(running),
        "completed_image_count": sum(item["image_count"] for item in completed),
        "checked_at": _now(),
    }


@app.post("/api/dating-sim/admin-prompts")
def dating_sim_admin_prompts_create(payload: DatingSimAdminPromptRequest, request: Request):
    _require_owner(request)
    with _DATING_SIM_ADMIN_PROMPTS_LOCK:
        rows = _read_dating_sim_admin_prompts()
        row = _validated_dating_sim_admin_prompt(payload)
        rows.append(row)
        _write_dating_sim_admin_prompts(rows)
    return row


@app.put("/api/dating-sim/admin-prompts/{prompt_id}")
def dating_sim_admin_prompts_update(prompt_id: str, payload: DatingSimAdminPromptRequest, request: Request):
    _require_owner(request)
    if not re.fullmatch(r"[0-9a-f]{32}", prompt_id):
        raise HTTPException(status_code=404, detail="프롬프트를 찾을 수 없습니다")
    with _DATING_SIM_ADMIN_PROMPTS_LOCK:
        rows = _read_dating_sim_admin_prompts()
        index = next((i for i, row in enumerate(rows) if row.get("id") == prompt_id), None)
        if index is None:
            raise HTTPException(status_code=404, detail="프롬프트를 찾을 수 없습니다")
        row = _validated_dating_sim_admin_prompt(payload, prompt_id)
        row["created_at"] = rows[index].get("created_at") or rows[index].get("updated_at") or _now()
        rows[index] = row
        _write_dating_sim_admin_prompts(rows)
    return row


@app.delete("/api/dating-sim/admin-prompts/{prompt_id}")
def dating_sim_admin_prompts_delete(prompt_id: str, request: Request):
    _require_owner(request)
    with _DATING_SIM_ADMIN_PROMPTS_LOCK:
        rows = _read_dating_sim_admin_prompts()
        remaining = [row for row in rows if row.get("id") != prompt_id]
        if len(remaining) == len(rows):
            raise HTTPException(status_code=404, detail="프롬프트를 찾을 수 없습니다")
        _write_dating_sim_admin_prompts(remaining)
    return {"ok": True}


@app.post("/api/dating-sim/scenario-tree/generate-images")
def dating_sim_generate_images_start(
    request: Request, story_id: str | None = None,
    force: bool = False, force_key: str | None = None,
    admin_prompts_only: bool = False, admin_prompt_id: str | None = None,
    resume_single: bool = False,
    reference: list[str] | None = Query(default=None), auto_references: bool = False,
    no_references: bool = False,
    payload: DatingSimImagePromptRequest | None = None,
):
    """관리자 전용 — 이 작품의 이미지만(시나리오는 그대로) 지금 바로 생성한다.
    generate_dating_sim_images.py는 이미 있는 파일을 건너뛰고 빠진 것만
    채우므로, 아무 옵션 없이 호출하면 첫 실행이든 재실행이든 빠진 것만
    채운다. force=true면 전부, force_key(예: portrait, 1:first)면 그
    이미지 하나만 강제로 다시 만든다(★ 2026-09-23 "이미지 재생성 버튼...
    전체재생성도 있고 사진눌렀을때 이사진만 재생성하기" 요청)."""
    _require_owner(request)
    if DATING_SIM_REPORT_PRIORITY_FILE.exists():
        raise HTTPException(status_code=409, detail="신고 이미지 재생성이 최우선으로 예약되어 있습니다")
    single_image_resume = resume_single and bool(force_key or admin_prompt_id)
    if resume_single and not single_image_resume:
        raise HTTPException(status_code=400, detail="한 장만 생성 재개하려면 재생성할 이미지가 필요합니다")
    if DATING_SIM_IMAGE_PAUSE_FILE.exists() and not single_image_resume:
        raise HTTPException(status_code=409, detail="전체 이미지 생성이 중지되어 있습니다. 먼저 생성 재개를 눌러 주세요")
    if force_key is not None and not DATING_SIM_IMAGE_KEY_RE.fullmatch(force_key):
        raise HTTPException(status_code=400, detail="force_key 형식이 올바르지 않습니다")
    prompt_override = (payload.prompt_override or "").strip() if payload else ""
    exact_prompt_override = payload.exact_prompt_override if payload else False
    negative_prompt_override = (payload.negative_prompt_override or "").strip() if payload else ""
    negative_prompt_enabled = payload.negative_prompt_enabled if payload else True
    keywords = [str(value).strip() for value in ((payload.keywords or []) if payload else [])
                if str(value).strip()]
    if len(keywords) > 24 or any(len(value) > 80 for value in keywords):
        raise HTTPException(status_code=400, detail="키워드는 24개, 항목당 80자 이내로 입력해 주세요")
    if keywords:
        prompt_override = ", ".join(filter(None, [prompt_override, *keywords]))
    settings = _validated_image_settings(payload.settings if payload else None)
    if (prompt_override or negative_prompt_override) and not force_key:
        raise HTTPException(status_code=400, detail="수정 프롬프트에는 재생성할 이미지가 필요합니다")
    if len(prompt_override) > 8000 or len(negative_prompt_override) > 8000:
        raise HTTPException(status_code=400, detail="프롬프트는 8,000자 이내로 입력해 주세요")
    active_admin_prompt_ids = _active_dating_sim_admin_prompt_ids()
    if admin_prompt_id is not None:
        if not re.fullmatch(r"[0-9a-f]{32}", admin_prompt_id):
            raise HTTPException(status_code=400, detail="관리자 프롬프트 ID 형식이 올바르지 않습니다")
        if admin_prompt_id not in active_admin_prompt_ids:
            raise HTTPException(status_code=404, detail="활성 관리자 프롬프트를 찾을 수 없습니다")
        admin_prompts_only = True
    if admin_prompts_only and not active_admin_prompt_ids:
        raise HTTPException(status_code=409, detail="활성화된 관리자 프롬프트가 없습니다")
    unsafe_positive = re.compile(
        r"(?i)(?:\bnud(?:e|ity)\b|\bnaked\b|\bporn(?:ographic)?\b|"
        r"\bexplicit sexual(?: act| content)?\b|\bexposed genitals?\b|"
        r"\bchild\b|\bminor\b|\bunderage\b|나체|누드|노골적\s*성적|성기\s*노출|미성년)"
    )
    if unsafe_positive.search(prompt_override):
        raise HTTPException(status_code=400, detail="긍정 프롬프트에 노골적인 성적·노출 생성 지시는 사용할 수 없습니다")
    book_id, work_dir = dating_sim_story.resolve_book_work_dir(story_id or "")
    # 이미지 작업 시스템은 EPUB 해시 대신 관리자 화면에 표시된 안전한
    # 작품 폴더명을 전달한다. library 밖으로 나갈 수 없게 basename과
    # containment를 모두 확인한 뒤에만 기존 결정론적 생성기를 실행한다.
    if not work_dir and (story_id or "").startswith("work:"):
        safe_name = (story_id or "")[5:]
        library_root = (JP_SUBTITLE_DIR / "library").resolve()
        candidate = (library_root / Path(safe_name).name).resolve()
        if safe_name == Path(safe_name).name:
            try:
                candidate.relative_to(library_root)
                if candidate.is_dir():
                    book_id, work_dir = f"work:{safe_name}", candidate
            except (OSError, ValueError):
                pass
    if not work_dir:
        raise HTTPException(status_code=404, detail="작품 폴더를 찾을 수 없습니다")
    with _dating_sim_image_jobs_lock:
        existing = _dating_sim_image_jobs.get(book_id)
        if existing:
            if existing["process"].poll() is None:
                raise HTTPException(status_code=409, detail="이미 이미지 생성이 진행 중입니다")
            existing["log_file"].close()
        image_dir = work_dir / "dating_sim_images"
        image_dir.mkdir(parents=True, exist_ok=True)
        expected_total = (1 if admin_prompt_id else len(active_admin_prompt_ids)) if admin_prompts_only else 0
        if admin_prompts_only:
            # 직전 한 장 재생성의 1/1 진행률이 새 10장 작업에 잠시 노출되지
            # 않도록 프로세스를 띄우기 전에 새 작업 계획을 먼저 기록한다.
            manifest_path = image_dir / "manifest.json"
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.is_file() else {}
            except (OSError, ValueError):
                manifest = {}
            manifest["status"] = "running"
            manifest["job_progress"] = {
                "done": 0, "total": expected_total, "percent": 0,
                "current": f"관리자 프롬프트 0/{expected_total} · 준비 중",
                "started_at": int(time.time()), "updated_at": int(time.time()),
            }
            manifest = _write_dating_sim_manifest(manifest_path, manifest)
        log_path = image_dir / "generation.log"
        log_file = open(log_path, "ab")
        command = [DATING_SIM_IMAGE_PYTHON, DATING_SIM_IMAGE_SCRIPT, str(work_dir)]
        # ★ 2026-09-24: 관리자가 직접 고른 원작 컷으로 인물(portrait)을 다시 만든다.
        if no_references:
            command.append("--no-references")
        elif isinstance(reference, list) and reference:
            allowed = set(dating_sim_story.reference_candidates(work_dir))
            if any(name not in allowed for name in reference) or len(reference) > 1:
                raise HTTPException(status_code=400, detail="참고 이미지 선택이 올바르지 않습니다(1장만 선택)")
            for name in reference:
                command.extend(["--reference", name])
            if not force and not force_key:
                command.extend(["--force-key", "portrait"])
        elif auto_references:
            command.append("--auto-references")
            if not force and not force_key:
                command.extend(["--force-key", "portrait"])
        if force:
            command.append("--force")
        elif force_key:
            command.extend(["--force-key", force_key])
        if admin_prompts_only:
            command.append("--admin-prompts-only")
        if admin_prompt_id:
            command.extend(["--admin-prompt-id", admin_prompt_id])
        if single_image_resume:
            # 전역 중지는 그대로 유지한다. 이 프로세스만 명시된 정확한
            # 한 장을 생성하고 종료하므로 다음 작품/이미지는 이어서 돌지 않는다.
            command.append("--single-image-resume")
        if prompt_override:
            command.extend(["--prompt-override", prompt_override])
            if exact_prompt_override:
                command.append("--exact-positive-prompt")
        if negative_prompt_override:
            command.extend(["--negative-prompt-override", negative_prompt_override])
        if not negative_prompt_enabled:
            command.append("--disable-negative-prompt")
        for key in ("width", "height", "steps", "cfg", "sampler", "scheduler", "denoise",
                    "hires_scale", "hires_steps", "hires_denoise"):
            if key in settings:
                command.extend([f"--{key.replace('_', '-')}", str(settings[key])])
        process = subprocess.Popen(
            command, stdout=log_file, stderr=subprocess.STDOUT, start_new_session=True,
        )
        _write_dating_sim_teacher_notification(
            work_dir, _request_username(request), story_id or "",
            "인물·전체" if (force or reference or auto_references or no_references) else "이미지",
        )
        threading.Thread(
            target=_push_when_dating_sim_images_done,
            args=(process, _request_username(request), story_id or "", "인물·전체" if (force or reference or auto_references or no_references) else "이미지"),
            daemon=True,
        ).start()
        _dating_sim_image_jobs[book_id] = {
            "process": process, "log_file": log_file, "log_path": log_path,
            "started_at": int(time.time()), "work_dir": str(work_dir),
            "job_type": "admin_prompts" if admin_prompts_only else "images",
            "expected_total": expected_total,
        }
    return {"status": "started", "job_type": "admin_prompts" if admin_prompts_only else "images",
            "expected_total": expected_total}


@app.post("/api/dating-sim/image-reports")
def dating_sim_report_image(payload: DatingSimImageReportRequest, request: Request):
    """플레이 중 이상한 이미지를 재생성 예약하고 안전한 임시 이미지로 교체한다."""
    _require_signed_in_user(request)
    DATING_SIM_REPORT_PRIORITY_FILE.parent.mkdir(parents=True, exist_ok=True)
    DATING_SIM_REPORT_PRIORITY_FILE.touch(exist_ok=True)
    if not DATING_SIM_IMAGE_KEY_RE.fullmatch(payload.image_key or ""):
        raise HTTPException(status_code=400, detail="이미지 키 형식이 올바르지 않습니다")
    try:
        story = dating_sim_story.scenario_tree(payload.story_id, seed_key=_request_username(request))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    generated = story.get("generated_images") or {}
    known = [*(generated.get("gallery") or []), *(generated.get("admin_gallery") or [])]
    target = next((item for item in known if item.get("key") == payload.image_key), None)
    if not target:
        raise HTTPException(status_code=404, detail="현재 작품에서 신고할 이미지를 찾지 못했습니다")
    reason = re.sub(r"\s+", " ", payload.reason).strip()[:300] or "이미지가 이상함"
    username = _request_username(request)
    with _DATING_SIM_IMAGE_REPORTS_LOCK:
        rows = _read_dating_sim_image_reports()
        existing = next((row for row in rows
                         if row.get("story_id") == payload.story_id
                         and row.get("image_key") == payload.image_key
                         and row.get("status") in {"pending", "processing"}), None)
        if existing:
            report = existing
            duplicate = True
        else:
            report = {
                "id": uuid.uuid4().hex, "story_id": payload.story_id,
                "image_key": payload.image_key, "image_label": target.get("label") or payload.image_key,
                "image_url": target.get("image_url") or "", "day": payload.day,
                "location": payload.location, "adult_mode": payload.adult_mode,
                "reason": reason, "reported_by": username, "status": "pending",
                "created_at": _now(), "job_type": "regenerate",
            }
            rows.append(report)
            _write_dating_sim_image_reports(rows)
            duplicate = False
    if not duplicate:
        _book_id, work_dir = dating_sim_story.resolve_book_work_dir(payload.story_id)
        source_file = _dating_sim_image_file_for_key(work_dir, payload.image_key) if work_dir else None
        if source_file:
            snapshot_dir = Path(work_dir) / "dating_sim_images" / "report_snapshots"
            snapshot_dir.mkdir(parents=True, exist_ok=True)
            snapshot_file = snapshot_dir / f"{report['id']}.png"
            shutil.copy2(source_file, snapshot_file)
            snapshot_hash = hashlib.sha256(snapshot_file.read_bytes()).hexdigest()
            snapshot_url = f"/api/dating-sim/image-report-snapshots/{report['id']}.png"
            report = _update_dating_sim_image_report(
                report["id"], image_url=snapshot_url,
                original_sha256=snapshot_hash, original_snapshot=True,
            ) or report
    replacement_url, replacement_key, replacement_admin = _dating_scene_image(
        story, payload.day, payload.location, payload.adult_mode and _is_owner_request(request),
    )
    return {
        "ok": True, "duplicate": duplicate, "report_id": report["id"],
        "status": report["status"], "replacement_image_url": replacement_url,
        "replacement_image_key": replacement_key,
        "replacement_admin_prompt_image": replacement_admin,
        "message": "이미지를 재생성 예약에 등록하고 임시 이미지로 교체했습니다.",
    }


@app.post("/api/dating-sim/image-improvements")
def dating_sim_image_improvement(payload: DatingSimImageImprovementRequest, request: Request):
    _require_owner(request)
    if payload.improvement not in {"anatomy", "eyes", "sharpness"}:
        raise HTTPException(status_code=400, detail="지원하지 않는 개선 유형입니다")
    if not DATING_SIM_IMAGE_KEY_RE.fullmatch(payload.image_key or ""):
        raise HTTPException(status_code=400, detail="이미지 키 형식이 올바르지 않습니다")
    story = dating_sim_story.scenario_tree(payload.story_id, seed_key=_request_username(request))
    generated = story.get("generated_images") or {}
    target = next((item for item in [*(generated.get("gallery") or []), *(generated.get("admin_gallery") or [])]
                   if item.get("key") == payload.image_key), None)
    if not target:
        raise HTTPException(status_code=404, detail="개선할 이미지를 찾지 못했습니다")
    with _DATING_SIM_IMAGE_REPORTS_LOCK:
        rows = _read_dating_sim_image_reports()
        existing = next((row for row in rows if row.get("story_id") == payload.story_id
                         and row.get("image_key") == payload.image_key
                         and row.get("job_type") == payload.improvement
                         and row.get("status") in {"pending", "processing"}), None)
        if existing:
            return {"ok": True, "duplicate": True, "report_id": existing["id"], "status": existing["status"]}
        labels = {"anatomy": "팔다리·손발 개선", "eyes": "눈동자 개선", "sharpness": "선명도 개선"}
        report = {"id": uuid.uuid4().hex, "story_id": payload.story_id, "image_key": payload.image_key,
                  "image_label": target.get("label") or payload.image_key, "image_url": target.get("image_url") or "",
                  "day": payload.day, "location": payload.location, "adult_mode": bool(target.get("admin_only")),
                  "reason": labels[payload.improvement], "job_type": payload.improvement,
                  "reported_by": _request_username(request), "status": "pending", "created_at": _now()}
        rows.append(report); _write_dating_sim_image_reports(rows)
    DATING_SIM_REPORT_PRIORITY_FILE.parent.mkdir(parents=True, exist_ok=True)
    DATING_SIM_REPORT_PRIORITY_FILE.touch(exist_ok=True)
    return {"ok": True, "duplicate": False, "report_id": report["id"], "status": "pending"}


@app.delete("/api/dating-sim/image-reports/{report_id}")
def dating_sim_cancel_image_report(report_id: str, request: Request):
    """아직 시작하지 않은 신고 이미지 재생성 예약을 취소한다."""
    _require_owner(request)
    if not re.fullmatch(r"[0-9a-f]{32}", report_id):
        raise HTTPException(status_code=404, detail="재생성 예약을 찾을 수 없습니다")
    with _DATING_SIM_IMAGE_REPORTS_LOCK:
        rows = _read_dating_sim_image_reports()
        report = next((row for row in rows if row.get("id") == report_id), None)
        if not report:
            raise HTTPException(status_code=404, detail="재생성 예약을 찾을 수 없습니다")
        if report.get("status") == "processing":
            raise HTTPException(status_code=409, detail="이미 생성 중인 작업은 취소할 수 없습니다")
        if report.get("status") != "pending":
            raise HTTPException(status_code=409, detail="대기 중인 예약만 취소할 수 있습니다")
        report.update(status="cancelled", cancelled_at=_now(), error="")
        _write_dating_sim_image_reports(rows)
    return {"ok": True, "status": "cancelled", "message": "재생성 예약을 취소했습니다."}


@app.post("/api/dating-sim/image-reports/{report_id}/retry")
def dating_sim_retry_image_report(report_id: str, request: Request):
    """실패한 항목을 중복 생성하지 않고 같은 예약으로 다시 대기시킨다."""
    _require_owner(request)
    if not re.fullmatch(r"[0-9a-f]{32}", report_id):
        raise HTTPException(status_code=404, detail="재생성 예약을 찾을 수 없습니다")
    with _DATING_SIM_IMAGE_REPORTS_LOCK:
        rows = _read_dating_sim_image_reports()
        report = next((row for row in rows if row.get("id") == report_id), None)
        if not report:
            raise HTTPException(status_code=404, detail="재생성 예약을 찾을 수 없습니다")
        if report.get("status") != "failed":
            raise HTTPException(status_code=409, detail="실패한 작업만 다시 예약할 수 있습니다")
        report.update(
            status="pending", error="", started_at=None, finished_at=None,
            returncode=None, result_sha256="", generation_info={},
            retried_at=_now(),
        )
        _write_dating_sim_image_reports(rows)
    DATING_SIM_REPORT_PRIORITY_FILE.parent.mkdir(parents=True, exist_ok=True)
    DATING_SIM_REPORT_PRIORITY_FILE.touch(exist_ok=True)
    return {"ok": True, "status": "pending", "message": "실패한 이미지를 다시 예약했습니다."}


@app.get("/api/dating-sim/image-report-snapshots/{report_id}.png")
def dating_sim_image_report_snapshot(report_id: str, request: Request):
    _require_owner(request)
    if not re.fullmatch(r"[0-9a-f]{32}", report_id):
        raise HTTPException(status_code=404, detail="신고 이미지 기록을 찾을 수 없습니다")
    report = next((row for row in _read_dating_sim_image_reports()
                   if row.get("id") == report_id), None)
    if not report:
        raise HTTPException(status_code=404, detail="신고 이미지 기록을 찾을 수 없습니다")
    _book_id, work_dir = dating_sim_story.resolve_book_work_dir(str(report.get("story_id") or ""))
    target = (Path(work_dir) / "dating_sim_images" / "report_snapshots" / f"{report_id}.png"
              if work_dir else None)
    if not target or not target.is_file():
        raise HTTPException(status_code=404, detail="신고 당시 이미지가 보존되어 있지 않습니다")
    return FileResponse(str(target), media_type="image/png",
                        headers={"Cache-Control": "private, no-store"})


@app.get("/api/dating-sim/image-reports")
def dating_sim_image_reports_list(request: Request):
    """신고 예약의 처리 순서·상태·재생성 결과를 관리자에게 제공한다."""
    _require_owner(request)
    rows = _read_dating_sim_image_reports()
    pending_order = {
        str(item.get("id")): index
        for index, item in enumerate(
            (item for item in rows if item.get("status") == "pending"), start=1
        )
    }
    story_cache = {}
    items = []
    for row in reversed(rows):
        item = dict(row)
        story_id = str(item.get("story_id") or "")
        _book_id, work_dir = dating_sim_story.resolve_book_work_dir(story_id)
        if story_id not in story_cache:
            try:
                story_cache[story_id] = dating_sim_story.scenario_tree(
                    story_id, seed_key=_request_username(request),
                )
            except (ValueError, OSError):
                story_cache[story_id] = {}
        story = story_cache[story_id]
        generated = story.get("generated_images") or {}
        known = [*(generated.get("gallery") or []), *(generated.get("admin_gallery") or [])]
        current = next((image for image in known
                        if image.get("key") == item.get("image_key")), None)
        live_generation_info = (_dating_sim_report_generation_info(
            story_id, work_dir, str(item.get("image_key") or ""),
        ) if work_dir else {})
        generation_info = dict(item.get("generation_info") or {})
        # 완료 순간 저장한 판정·프롬프트 이력을 보존하되 현재 파일 URL은
        # 실시간 값으로 덮어써 캐시와 수동 후보 채택 결과를 정확히 반영한다.
        generation_info.update({key: value for key, value in live_generation_info.items()
                                if key not in {"automatic_quality"} or not generation_info.get(key)})
        if not current and generation_info.get("image_url"):
            current = generation_info
        item["title"] = story.get("title") or story.get("source_title") or story_id
        item["queue_priority"] = pending_order.get(str(item.get("id")))
        item["result_image_url"] = (
            current.get("image_url") if item.get("status") == "done" and current else ""
        )
        item["result_available"] = bool(item["result_image_url"])
        item["original_snapshot_available"] = bool(item.get("original_snapshot"))
        item["generation_info"] = generation_info
        items.append(item)
    external_job = _dating_sim_external_image_job()
    return {
        "items": items,
        "pending_count": sum(item.get("status") == "pending" for item in rows),
        "processing_count": sum(item.get("status") == "processing" for item in rows),
        "done_count": sum(item.get("status") == "done" for item in rows),
        "failed_count": sum(item.get("status") == "failed" for item in rows),
        "blocked_by_external": bool(external_job),
        "external_current": str((external_job or {}).get("current") or ""),
    }


@app.post("/api/dating-sim/image-reports/run")
def dating_sim_image_reports_run(request: Request):
    """중지 상태를 해제하고 신고 이미지 예약목록의 자동 처리를 진행한다."""
    _require_owner(request)
    rows = _read_dating_sim_image_reports()
    pending = [item for item in rows if item.get("status") == "pending"]
    processing = [item for item in rows if item.get("status") == "processing"]
    _write_image_generation_pause(False)
    if processing:
        message = "이미 예약목록의 이미지를 재생성하고 있습니다."
    elif pending:
        message = f"예약목록 재생성을 시작했습니다. 대기 이미지 {len(pending)}장을 순서대로 처리합니다."
    else:
        message = "현재 재생성을 기다리는 예약 이미지가 없습니다."
    return {
        "ok": True, "pending_count": len(pending),
        "processing_count": len(processing), "message": message,
    }


@app.get("/api/dating-sim/all-images")
def dating_sim_all_images(request: Request):
    """모든 작품의 일반·관리자 생성 이미지를 통합 사진첩 순서로 제공한다."""
    _require_owner(request)
    username = _request_username(request)
    items = []
    active_reports = {
        (str(report.get("story_id") or ""), str(report.get("image_key") or "")): report
        for report in _read_dating_sim_image_reports()
        if report.get("status") in {"pending", "processing"}
        and (report.get("job_type") or "regenerate") == "regenerate"
    }
    active_improvements = {}
    for report in _read_dating_sim_image_reports():
        if report.get("status") in {"pending", "processing"} and report.get("job_type") in {"anatomy", "eyes", "sharpness"}:
            active_improvements.setdefault(
                (str(report.get("story_id") or ""), str(report.get("image_key") or "")), {}
            )[str(report.get("job_type"))] = {"status": report.get("status"), "id": report.get("id")}
    liked_images = {
        (str(item.get("story_id") or ""), str(item.get("image_key") or "")): item
        for item in _read_dating_sim_image_likes()
    }
    for book_id in dating_sim_story.all_book_ids():
        story_id = f"book:{book_id}"
        try:
            story = dating_sim_story.scenario_tree(story_id, seed_key=username)
        except (ValueError, OSError):
            continue
        generated = story.get("generated_images") or {}
        title = story.get("title") or story.get("source_title") or story_id
        for image in [*(generated.get("gallery") or []), *(generated.get("admin_gallery") or [])]:
            if not image.get("image_url") or not image.get("key"):
                continue
            active_report = active_reports.get((story_id, str(image.get("key") or "")))
            liked_image = liked_images.get((story_id, str(image.get("key") or "")))
            items.append({
                **image, "story_id": story_id, "title": title,
                "day": int(image.get("day") or 0),
                "location": str(image.get("location") or "all-images"),
                "report_status": active_report.get("status") if active_report else "",
                "report_id": active_report.get("id") if active_report else "",
                "liked": bool(liked_image),
                "liked_at": liked_image.get("updated_at") if liked_image else "",
                "improvement_jobs": active_improvements.get((story_id, str(image.get("key") or "")), {}),
            })
    items.sort(key=lambda item: (
        str(item.get("title") or "").casefold(),
        int(item.get("day") or 0), str(item.get("location") or ""),
        str(item.get("label") or item.get("key") or "").casefold(),
    ))
    return {"items": items, "total": len(items)}


@app.post("/api/dating-sim/image-likes")
def dating_sim_image_like(payload: DatingSimImageLikeRequest, request: Request):
    """좋아요 이미지를 보존하고 해당 생성 프롬프트를 향후 유사 장면의 선호 신호로 사용한다."""
    _require_owner(request)
    if not DATING_SIM_IMAGE_KEY_RE.fullmatch(payload.image_key or ""):
        raise HTTPException(status_code=400, detail="이미지 키 형식이 올바르지 않습니다")
    try:
        story = dating_sim_story.scenario_tree(
            payload.story_id, seed_key=_request_username(request),
        )
    except (ValueError, OSError) as exc:
        raise HTTPException(status_code=404, detail="작품을 찾을 수 없습니다") from exc
    generated = story.get("generated_images") or {}
    known = [*(generated.get("gallery") or []), *(generated.get("admin_gallery") or [])]
    target = next((item for item in known if item.get("key") == payload.image_key), None)
    if not target:
        raise HTTPException(status_code=404, detail="현재 작품에서 이미지를 찾지 못했습니다")

    with _DATING_SIM_IMAGE_LIKES_LOCK:
        rows = _read_dating_sim_image_likes()
        rows = [row for row in rows if not (
            row.get("story_id") == payload.story_id
            and row.get("image_key") == payload.image_key
        )]
        if payload.liked:
            rows.append({
                "story_id": payload.story_id, "image_key": payload.image_key,
                "image_url": target.get("image_url") or "",
                "label": target.get("label") or payload.image_key,
                "title": story.get("title") or story.get("source_title") or payload.story_id,
                "day": int(target.get("day") or 0),
                "location": str(target.get("location") or ""),
                "admin_only": bool(target.get("admin_only")),
                "prompt": target.get("prompt") or "",
                "effective_prompt": target.get("effective_prompt") or target.get("prompt") or "",
                "negative_prompt": target.get("negative_prompt") or "",
                "effective_negative_prompt": target.get("effective_negative_prompt") or target.get("negative_prompt") or "",
                "updated_at": _now(),
            })
        _write_dating_sim_image_likes(rows)

    if payload.liked:
        _book_id, work_dir = dating_sim_story.resolve_book_work_dir(payload.story_id)
        prompt = target.get("effective_prompt") or target.get("prompt") or ""
        negative = target.get("effective_negative_prompt") or target.get("negative_prompt") or ""
        kind = "admin" if payload.image_key.startswith("admin:") else (
            "portrait" if payload.image_key == "portrait" else "scene"
        )
        approval = {
            "source": "image_like", "enabled": True, "approved_at": _now(),
            "story_id": payload.story_id, "image_key": payload.image_key,
            "kind": kind, "work_name": work_dir.name if work_dir else "",
            "location": str(target.get("location") or ""),
            "situation_tags": _dating_prompt_situation_tags(prompt),
            "prompt": prompt, "effective_prompt": prompt,
            "negative_prompt": negative, "effective_negative_prompt": negative,
        }
        if kind == "admin":
            approval["admin_prompt_id"] = payload.image_key.removeprefix("admin:")
        _write_dating_prompt_approval(approval)
    else:
        _remove_dating_prompt_like_approval(payload.story_id, payload.image_key)
    return {
        "ok": True, "liked": bool(payload.liked),
        "message": "좋아요 프롬프트를 향후 유사 장면 생성에 반영합니다." if payload.liked
                   else "좋아요를 취소했습니다.",
    }


@app.post("/api/dating-sim/quality-attempt-selection")
def dating_sim_select_quality_attempt(
    payload: DatingSimQualityAttemptSelectRequest, request: Request,
):
    """보존된 1~3회 품질검사 후보를 사용자가 최종 결과로 직접 채택한다."""
    _require_owner(request)
    if not DATING_SIM_IMAGE_KEY_RE.fullmatch(payload.image_key or ""):
        raise HTTPException(status_code=400, detail="이미지 키 형식이 올바르지 않습니다")
    if payload.attempt not in {1, 2, 3}:
        raise HTTPException(status_code=400, detail="채택할 시도 번호가 올바르지 않습니다")
    book_id, work_dir = dating_sim_story.resolve_book_work_dir(payload.story_id)
    if not work_dir or not re.fullmatch(r"[0-9a-f]{20}", str(book_id or "")):
        raise HTTPException(status_code=404, detail="작품 폴더를 찾을 수 없습니다")
    image_dir = work_dir / "dating_sim_images"
    manifest_path = image_dir / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError) as exc:
        raise HTTPException(status_code=404, detail="이미지 생성 기록을 찾을 수 없습니다") from exc

    if payload.image_key == "portrait":
        target_filename = manifest.get("portrait") or "portrait.png"
        automatic = manifest.get("portrait_automatic_quality")
        record = None
    elif payload.image_key.startswith("admin:"):
        prompt_id = payload.image_key.removeprefix("admin:")
        record = (manifest.get("admin_prompt_images") or {}).get(prompt_id)
        if not isinstance(record, dict):
            record = _dating_sim_report_generation_info(
                payload.story_id, work_dir, payload.image_key,
            )
            manifest.setdefault("admin_prompt_images", {})[prompt_id] = record
        target_filename = record.get("file") or f"admin-{prompt_id}.png"
        automatic = record.get("automatic_quality") if isinstance(record, dict) else None
    else:
        record = (manifest.get("scenes") or {}).get(payload.image_key)
        target_filename = record.get("file") if isinstance(record, dict) else None
        automatic = record.get("automatic_quality") if isinstance(record, dict) else None
    if not isinstance(automatic, dict) and isinstance(target_filename, str):
        recovered = _dating_sim_report_generation_info(
            payload.story_id, work_dir, payload.image_key,
        )
        automatic = dict(recovered.get("automatic_quality") or {})
        if isinstance(record, dict):
            record["automatic_quality"] = automatic
    if (not isinstance(target_filename, str)
            or not re.fullmatch(r"(?:portrait|scene-[0-9a-f]{12}|admin-[0-9a-f]{32})\.png", target_filename)
            or not isinstance(automatic, dict)):
        raise HTTPException(status_code=404, detail="선택한 이미지의 품질 후보 기록을 찾을 수 없습니다")
    selected = next(
        (item for item in (automatic.get("attempts") or [])
         if isinstance(item, dict) and item.get("attempt") == payload.attempt), None,
    )
    expected_attempt_file = f"{Path(target_filename).stem}-attempt-{payload.attempt}.png"
    if not selected or selected.get("image_file") != expected_attempt_file:
        raise HTTPException(status_code=404, detail="선택한 시도의 후보 이미지가 저장되어 있지 않습니다")
    candidate = image_dir / "quality_attempts" / expected_attempt_file
    target = image_dir / target_filename
    if not candidate.is_file() or not target.parent == image_dir:
        raise HTTPException(status_code=404, detail="선택한 후보 이미지 파일을 찾을 수 없습니다")

    previous_mtime = target.stat().st_mtime if target.is_file() else 0
    temporary_image = image_dir / f".{target_filename}.manual-selection.tmp"
    shutil.copy2(candidate, temporary_image)
    os.replace(temporary_image, target)
    refreshed_mtime = max(time.time(), previous_mtime + 1.0)
    os.utime(target, (refreshed_mtime, refreshed_mtime))
    selected_report = dict(selected.get("report") or {})
    selected_passed = selected_report.get("passed") is True
    automatic.update({
        "passed": selected_passed,
        "accepted_after_limit": not selected_passed,
        "selected_attempt": payload.attempt,
        "selection_method": "manual",
        "manually_selected": True,
        "selected_at": _now(),
        "final_report": selected_report,
    })
    if payload.image_key == "portrait":
        manifest["portrait_automatic_quality"] = automatic
        manifest["portrait_prompt"] = selected.get("prompt") or manifest.get("portrait_prompt") or ""
        manifest["portrait_effective_prompt"] = selected.get("effective_prompt") or selected.get("prompt") or ""
        manifest["portrait_effective_negative_prompt"] = selected.get("negative_prompt") or ""
        manifest["portrait_generation_settings"] = selected.get("generation_settings") or {}
    else:
        record["automatic_quality"] = automatic
        record["prompt"] = selected.get("prompt") or record.get("prompt") or ""
        record["effective_prompt"] = selected.get("effective_prompt") or selected.get("prompt") or ""
        record["effective_negative_prompt"] = selected.get("negative_prompt") or ""
        record["generation_settings"] = selected.get("generation_settings") or {}
    quality_checks = manifest.setdefault("quality_checks", {})
    quality_checks[payload.image_key] = {
        **selected_report,
        "passed": selected_passed,
        "accepted_after_limit": not selected_passed,
        "manually_selected": True,
        "selected_attempt": payload.attempt,
    }
    accepted_failures = any(
        isinstance(report, dict) and report.get("accepted_after_limit") is True
        for report in quality_checks.values()
    )
    hard_failures = any(
        isinstance(report, dict) and report.get("passed") is not True
        and report.get("accepted_after_limit") is not True
        for report in quality_checks.values()
    )
    manifest["quality_status"] = (
        "failed" if hard_failures else ("accepted_after_limit" if accepted_failures else "passed")
    )
    manifest = _write_dating_sim_manifest(manifest_path, manifest)
    final_hash = hashlib.sha256(target.read_bytes()).hexdigest()
    with _DATING_SIM_IMAGE_REPORTS_LOCK:
        report_rows = _read_dating_sim_image_reports()
        changed = False
        for report_row in report_rows:
            if (report_row.get("story_id") == payload.story_id
                    and report_row.get("image_key") == payload.image_key
                    and report_row.get("status") == "done"):
                report_row["result_sha256"] = final_hash
                report_row["selected_attempt"] = payload.attempt
                report_row["selection_method"] = "manual"
                report_row["generation_info"] = _dating_sim_report_generation_info(
                    payload.story_id, work_dir, payload.image_key,
                )
                changed = True
        if changed:
            _write_dating_sim_image_reports(report_rows)
    if payload.image_key == "portrait":
        approval_kind, location, admin_prompt_id = "portrait", "", None
    elif payload.image_key.startswith("admin:"):
        approval_kind, location = "admin", ""
        admin_prompt_id = payload.image_key.removeprefix("admin:")
    else:
        approval_kind = "scene"
        location = str((record or {}).get("location") or payload.image_key.split(":", 1)[-1])
        admin_prompt_id = None
    approved_prompt = str(selected.get("prompt") or "").strip()
    _write_dating_prompt_approval({
        "id": uuid.uuid4().hex,
        "enabled": True,
        "kind": approval_kind,
        "story_id": payload.story_id,
        "work_name": work_dir.name,
        "image_key": payload.image_key,
        "admin_prompt_id": admin_prompt_id,
        "location": location,
        "situation_tags": _dating_prompt_situation_tags(approved_prompt),
        "attempt": payload.attempt,
        "prompt": approved_prompt,
        "effective_prompt": selected.get("effective_prompt") or approved_prompt,
        "negative_prompt": selected.get("negative_prompt") or "",
        "quality_positive_prompt": selected.get("quality_positive_prompt") or "",
        "quality_negative_prompt": selected.get("quality_negative_prompt") or "",
        "generation_settings": selected.get("generation_settings") or {},
        "source_report": selected_report,
        "approved_by": _request_username(request),
        "approved_at": _now(),
    })
    route = "admin-images" if target_filename.startswith("admin-") else "images"
    return {
        "ok": True,
        "selected_attempt": payload.attempt,
        "image_url": f"/api/dating-sim/books/{book_id}/{route}/{target_filename}?t={int(target.stat().st_mtime)}",
        "message": f"{payload.attempt}회 시도 사진을 최종 결과로 채택하고 같은 상황의 우선 프롬프트로 학습했습니다.",
    }


@app.post("/api/dating-sim/scenario-tree/set-portrait")
def dating_sim_set_generated_portrait(
    payload: DatingSimPortraitSelectRequest, request: Request, story_id: str | None = None,
):
    """관리자가 이미 생성된 장면 이미지를 대표 초상화로 지정한다."""
    _require_owner(request)
    if not DATING_SIM_IMAGE_KEY_RE.fullmatch(payload.image_key or ""):
        raise HTTPException(status_code=400, detail="이미지 키 형식이 올바르지 않습니다")
    selected_story_id = story_id or payload.story_id or ""
    _, work_dir = dating_sim_story.resolve_book_work_dir(selected_story_id)
    if not work_dir:
        raise HTTPException(status_code=404, detail="작품 폴더를 찾을 수 없습니다")
    image_dir = work_dir / "dating_sim_images"
    manifest_path = image_dir / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError) as exc:
        raise HTTPException(status_code=404, detail="이미지 기록을 찾을 수 없습니다") from exc
    record = (manifest.get("scenes") or {}).get(payload.image_key)
    if not isinstance(record, dict) or not isinstance(record.get("file"), str):
        raise HTTPException(status_code=404, detail="선택한 장면 이미지를 찾을 수 없습니다")
    source = (image_dir / Path(record["file"]).name).resolve()
    portrait = (image_dir / "portrait.png").resolve()
    try:
        source.relative_to(image_dir.resolve())
        if not source.is_file() or source.stat().st_size < 1024:
            raise OSError
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=404, detail="선택한 이미지 파일이 없습니다") from exc
    if portrait.is_file():
        shutil.copy2(portrait, image_dir / "portrait.previous.png")
    temporary = image_dir / "portrait.selecting.png"
    shutil.copy2(source, temporary)
    temporary.replace(portrait)
    manifest["portrait"] = "portrait.png"
    manifest["portrait_selected_from"] = payload.image_key
    manifest["portrait_prompt"] = record.get("prompt") or manifest.get("portrait_prompt") or ""
    manifest["portrait_effective_prompt"] = record.get("effective_prompt") or ""
    manifest["portrait_generation_settings"] = record.get("generation_settings") or {}
    manifest["portrait_provider"] = record.get("provider") or manifest.get("portrait_provider") or ""
    quality = manifest.setdefault("quality_checks", {})
    if isinstance(quality, dict):
        quality["portrait"] = quality.get(payload.image_key) or {"passed": True, "selected_by_admin": True}
    temp_manifest = manifest_path.with_suffix(".tmp")
    temp_manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_manifest.replace(manifest_path)
    return {"ok": True, "message": "선택한 사진을 대표 초상화로 설정했습니다"}


@app.get("/api/dating-sim/scenario-tree/reference-candidates")
def dating_sim_reference_candidates(request: Request, story_id: str | None = None):
    """관리자 전용 — 인물 참고 이미지로 고를 수 있는 원작 컷 전부와 현재 직접 고른 목록."""
    _require_owner(request)
    _, work_dir = dating_sim_story.resolve_book_work_dir(story_id or "")
    if not work_dir:
        raise HTTPException(status_code=404, detail="작품 폴더를 찾을 수 없습니다")
    selected = set(dating_sim_story.selected_references(work_dir))
    return {
        "selected": sorted(selected),
        "candidates": [
            {"name": name, "selected": name in selected,
             "url": f"/api/dating-sim/scenario-tree/reference-candidates/file?story_id={urllib.parse.quote(story_id or '')}"
                    f"&name={urllib.parse.quote(name)}"}
            for name in dating_sim_story.reference_candidates(work_dir)
        ],
    }


@app.get("/api/dating-sim/scenario-tree/reference-candidates/file")
def dating_sim_reference_candidate_file(request: Request, name: str, story_id: str | None = None):
    _require_owner(request)
    _, work_dir = dating_sim_story.resolve_book_work_dir(story_id or "")
    target = dating_sim_story.reference_candidate_path(work_dir, name) if work_dir else None
    if not target:
        raise HTTPException(status_code=404, detail="참고 후보 이미지를 찾을 수 없습니다")
    return FileResponse(str(target))


@app.get("/api/dating-sim/scenario-tree/generate-images/status")
def dating_sim_generate_images_status(request: Request, story_id: str | None = None):
    _require_owner(request)
    book_id, work_dir = dating_sim_story.resolve_book_work_dir(story_id or "")
    if not work_dir:
        raise HTTPException(status_code=404, detail="작품 폴더를 찾을 수 없습니다")
    return _dating_sim_image_job_status(book_id, work_dir)


@app.post("/api/dating-sim/generate-missing-images")
def dating_sim_generate_missing_images(request: Request):
    """관리자 전용 — 시나리오 완성·이미지 미완성 작품 전체를 순차 생성한다."""
    global _dating_sim_image_backlog_job
    _require_owner(request)
    if DATING_SIM_REPORT_PRIORITY_FILE.exists():
        raise HTTPException(status_code=409, detail="신고 이미지 재생성이 최우선으로 예약되어 있습니다")
    if DATING_SIM_IMAGE_PAUSE_FILE.exists():
        raise HTTPException(status_code=409, detail="전체 이미지 생성이 중지되어 있습니다. 먼저 생성 재개를 눌러 주세요")
    try:
        with urllib.request.urlopen("http://127.0.0.1:8188/system_stats", timeout=3):
            pass
    except (OSError, urllib.error.URLError) as exc:
        raise HTTPException(status_code=503, detail="ComfyUI가 꺼져 있습니다. Mac에서 ComfyUI를 먼저 실행해 주세요") from exc
    with _dating_sim_image_jobs_lock:
        if any(job["process"].poll() is None for job in _dating_sim_image_jobs.values()):
            raise HTTPException(status_code=409, detail="개별 작품 이미지 생성이 진행 중입니다")
        if _dating_sim_image_backlog_job and _dating_sim_image_backlog_job["process"].poll() is None:
            raise HTTPException(status_code=409, detail="미완성 작품 이미지 생성이 이미 진행 중입니다")
        DATING_SIM_IMAGE_BACKLOG_STATE.parent.mkdir(parents=True, exist_ok=True)
        DATING_SIM_IMAGE_BACKLOG_STATE.unlink(missing_ok=True)
        log_file = open(DATING_SIM_IMAGE_BACKLOG_LOG, "ab")
        process = subprocess.Popen(
            [DATING_SIM_IMAGE_PYTHON, DATING_SIM_IMAGE_BACKLOG_SCRIPT],
            stdout=log_file, stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        _dating_sim_image_backlog_job = {"process": process, "log_file": log_file, "started_at": int(time.time())}
        threading.Thread(target=_push_when_dating_sim_image_backlog_done,
                         args=(process, _request_username(request)), daemon=True).start()
    return {"status": "started"}


@app.get("/api/dating-sim/generate-missing-images/status")
def dating_sim_generate_missing_images_status(request: Request):
    _require_owner(request)
    with _dating_sim_image_jobs_lock:
        job = _dating_sim_image_backlog_job
        running = bool(job and job["process"].poll() is None)
        individual_jobs = [
            (book_id, item) for book_id, item in _dating_sim_image_jobs.items()
            if item["process"].poll() is None
        ]
    if not running:
        external = _dating_sim_external_image_job()
        if external:
            external.update(_comfyui_runtime_status())
            external["image_worker_running"] = True
            external["active_work"] = external.get("current") or "예약 이미지 작업"
            external["paused"] = DATING_SIM_IMAGE_PAUSE_FILE.exists()
            for candidate_book_id in dating_sim_story.all_book_ids():
                _, candidate_dir = dating_sim_story.resolve_book_work_dir(f"book:{candidate_book_id}")
                if candidate_dir and candidate_dir.name == external.get("current"):
                    external["active_story_id"] = f"book:{candidate_book_id}"
                    break
            return external
    state = _dating_sim_image_backlog_progress(_dating_sim_image_backlog_state(), running)
    state["running"] = running
    state["paused"] = DATING_SIM_IMAGE_PAUSE_FILE.exists()
    state.update(_comfyui_runtime_status())
    state["image_worker_running"] = running or bool(individual_jobs)
    if running:
        state["active_work"] = state.get("current") or "일괄 이미지 작업 준비 중"
        state["active_job"] = state.get("current_image_job") or "이미지 생성 준비 중"
    elif individual_jobs:
        book_id, item = individual_jobs[0]
        work_dir = Path(item.get("work_dir") or "")
        detail = _dating_sim_image_job_status(book_id, work_dir)
        state["active_work"] = work_dir.name or book_id
        state["active_job"] = detail.get("current") or "이미지 생성 중"
        state["active_job_percent"] = detail.get("percent") or 0
        state["active_story_id"] = book_id if str(book_id).startswith("book:") else f"book:{book_id}"
    if state.get("active_work") and not state.get("active_story_id"):
        for candidate_book_id in dating_sim_story.all_book_ids():
            _, candidate_dir = dating_sim_story.resolve_book_work_dir(f"book:{candidate_book_id}")
            if candidate_dir and candidate_dir.name == state["active_work"]:
                state["active_story_id"] = f"book:{candidate_book_id}"
                break
    return state


@app.post("/api/dating-sim/comfyui/runtime")
def dating_sim_set_comfyui_runtime(payload: ComfyUIRuntimeRequest, request: Request):
    """관리자 전용 ComfyUI 전원 스위치.

    AI나 브라우저에 셸 권한을 주지 않고 고정 LaunchAgent만 결정론적으로
    전환한다. 진행 중인 생성 작업이 있으면 종료 요청을 거부해 결과 파일이
    중간에 끊기지 않게 한다.
    """
    _require_owner(request)
    if not payload.enabled:
        with _dating_sim_image_jobs_lock:
            backlog_running = bool(
                _dating_sim_image_backlog_job
                and _dating_sim_image_backlog_job["process"].poll() is None
            )
            individual_running = any(
                item["process"].poll() is None for item in _dating_sim_image_jobs.values()
            )
        if backlog_running or individual_running or _dating_sim_external_image_job():
            raise HTTPException(
                status_code=409,
                detail="이미지 생성 작업이 진행 중이라 ComfyUI를 끌 수 없습니다. 작업이 끝난 뒤 다시 시도해 주세요",
            )
    try:
        status = _set_comfyui_runtime(payload.enabled)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    status["requested_enabled"] = payload.enabled
    status["message"] = (
        "ComfyUI를 켰습니다" if status["comfy_online"]
        else "ComfyUI를 껐습니다" if not payload.enabled
        else "ComfyUI를 시작했습니다. 모델을 불러오는 중입니다"
    )
    return status


# ★ 2026-09-17: "만남마다 나가기하면 그 진행상태가 세이브되서 다시 미연시
# 누르면 이전 진행 이어가기, 새로운 만남 중에 선택해서 플레이할수있으면
# 좋겠어" 요청 — 지금까지 /dating-sim/ 진입은 매번 서재의 무작위 EPUB으로
# 강제 리다이렉트했다(진행 저장은 (계정, 이야기 ID)별로 이미 되고 있었지만,
# 홈에서 다시 들어갈 때마다 새 무작위 작품으로 튕겨서 방금 하던 이야기로
# 못 돌아왔다). 리다이렉트를 없애고, 대신 진행 중인 만남 목록과 "새로운
# 만남 시작" 선택지를 프론트(app.js)가 보여주게 두 엔드포인트를 추가한다.
@app.get("/api/dating-sim/vocab-meaning")
def dating_sim_vocab_meaning(request: Request, word: str, context: str = ""):
    """AI가 뜻을 직접 준 학습 단어가 아닌 한자 합성어 단어카드에서, 한자별
    뜻을 짜깁기하는 대신 단어 전체의 한국어 번역을 보여준다(★ 2026-09-23
    "한자 뜻 따로따로가아니라 한국말로번역한 뜻으로 다바꿔줘" 요청)."""
    _require_signed_in_user(request)
    word = (word or "").strip()
    if not word or len(word) > 12:
        raise HTTPException(status_code=400, detail="단어 형식이 올바르지 않습니다")
    if len(context) > 500:
        raise HTTPException(status_code=400, detail="문맥이 너무 깁니다")
    return {"word": word, "meaning": dating_sim_story.translate_word_meaning(word, context)}


@app.get("/api/dating-sim/encounters")
def dating_sim_encounters(request: Request):
    """로그인 계정이 지금까지 시작한 모든 만남(기본 이야기 + 작품별 이야기)의
    요약을 최근 갱신순으로 돌려준다 — 프론트의 "이어하기" 목록에 쓴다."""
    _require_signed_in_user(request)
    username = _request_username(request)
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM dating_sim_progress WHERE username=? ORDER BY updated_at DESC", (username,)
        ).fetchall()
        encounters = []
        for raw_row in rows:
            row = dict(raw_row)
            story_id = None if row["character_id"] == dating_sim_story.CHARACTER_ID else row["character_id"]
            if not story_id or not story_id.startswith("book:"):
                continue
            try:
                story = _dating_story(story_id, username)
            except HTTPException:
                continue  # 서재에서 지워진 EPUB 등 더 이상 존재하지 않는 이야기는 건너뛴다
            # 실제 플레이 화면과 같은 보정 경로를 사용한다. 과거 버전에서
            # 진행도보다 높게 저장된 호감도를 목록만 그대로 보여주면 게임
            # 화면과 숫자가 달라지므로, 목록 조회 때도 DB까지 함께 정규화한다.
            row = _dating_sim_row(conn, username, story)
            # ★ 2026-09-23: "미연시 이거미완료라고 아무것도 안보이는데
            # 미완료여도 이전에 진행하던거는 계속볼수있게해줘" 요청 — 아직
            # 시작 안 한(day=1·난이도별 시작 호감도 그대로인) 미완성 작품만
            # 로비에서 숨기고, 이미 실제로 진행한(day가 늘었거나 호감도가
            # 바뀌었거나 완결된) 작품은 이미지·시나리오 생성이 덜 끝났어도
            # "이어하기"로 계속 볼 수 있게 한다.
            start_affection = _dating_start_affection(
                story, _dating_difficulty(row.get("difficulty"))
            )
            has_real_progress = (
                row["day"] > 1
                or row["affection"] != start_affection
                or bool(row["completed"])
                or bool(row.get("pending_location"))
            )
            if not has_real_progress and not dating_sim_story.prepared_book(story_id.split(":", 1)[1]):
                continue
            try:
                route_state = json.loads(row.get("route_state") or "{}")
            except (TypeError, ValueError):
                route_state = {}
            encounters.append({
                "story_id": story["id"], "title": story["title"], "character_name": story["name"],
                "character_name_ko": story.get("character_name_ko", ""),
                "character_image": story.get("character_image"), "source_title": story.get("source_title"),
                "day": min(row["day"], story["total_days"]), "total_days": story["total_days"],
                "affection": row["affection"], "completed": bool(row["completed"]),
                "ending_title": dating_sim_story.ending_for(story, row["affection"], route_state)["title"] if row["completed"] else None,
                "learning_progress": _dating_learning_progress(username, story),
            })
    finally:
        conn.close()
    return encounters


@app.post("/api/dating-sim/persona-chat")
def dating_sim_persona_chat(request: Request, story_id: str):
    """작품 인물 정본과 현재 미연시 진행을 개인 툴파챗 페르소나로 이어 붙인다."""
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다")
    story = _dating_story(story_id, user["username"])
    profile = story.get("character_persona") or {}
    if not profile:
        raise HTTPException(status_code=409, detail="이 작품은 아직 인물 대사 분석이 완료되지 않았습니다")
    conn = get_conn()
    try:
        progress = _dating_sim_row(conn, user["username"], story)
        base_name = str(story.get("character_name_ko") or story.get("name") or "작품 인물").strip()
        work_code = str(story.get("source_work_code") or "작품")[:12]
        persona_name = re.sub(r"[^0-9A-Za-z가-힣 _-]", "", f"{base_name} {work_code}").strip()[:20]
        if not persona_name:
            persona_name = f"작품 인물 {work_code}"[:20]
        existing = conn.execute("SELECT owner_username FROM personas WHERE name=?", (persona_name,)).fetchone()
        if existing and existing["owner_username"] not in (None, user["username"]):
            persona_name = f"{base_name} {hashlib.sha1(story_id.encode()).hexdigest()[:5]}"[:20]
        facts = {
            key: profile.get(key) for key in (
                "name_jp", "name_reading", "name_ko", "age", "personality", "speech_style",
                "values_and_boundaries", "relationship_style", "signature_phrases"
            ) if profile.get(key) not in (None, [], "")
        }
        description = (
            f"{story.get('persona_disclaimer')}\n"
            f"작품: {story.get('source_title')}\n인물 정본: {json.dumps(facts, ensure_ascii=False)}\n"
            f"미연시 연속성: 현재 {int(progress['day'])}번째 흐름, 호감도 {int(progress['affection'])}점. "
            "원작의 실제 인물이라고 주장하지 말고, 사용자가 미연시에서 함께 겪은 관계와 사건을 기억한 "
            "가상 캐릭터로 대화한다. 확인되지 않은 신상은 꾸며내지 않는다. 일본어 말투를 유지하되 "
            "사용자가 이해할 수 있도록 필요할 때 자연스러운 한국어를 함께 쓴다."
        )
        prompt = _build_user_persona_prompt(persona_name, user["username"], description)
        avatar_url = story.get("character_image")
        if existing:
            conn.execute(
                "UPDATE personas SET system_prompt=?,description=?,avatar_url=?,synced_at=? WHERE name=? AND owner_username=?",
                (prompt, description, avatar_url, _now(), persona_name, user["username"]),
            )
        else:
            conn.execute(
                "INSERT INTO personas(name,notion_page_id,system_prompt,group_name,owner_username,description,avatar_url,synced_at) "
                "VALUES (?, '', ?, NULL, ?, ?, ?, ?)",
                (persona_name, prompt, user["username"], description, avatar_url, _now()),
            )
        direct_key = f"persona:{user['username']}:{persona_name}"
        room = conn.execute("SELECT room_id FROM custom_rooms WHERE direct_key=?", (direct_key,)).fetchone()
        if room:
            room_id = room["room_id"]
        else:
            room_id = f"{CUSTOM_ROOM_ID_PREFIX}{uuid.uuid4().hex[:10]}"
            conn.execute(
                "INSERT INTO custom_rooms(room_id,label,owner_username,created_at,direct_key) VALUES (?,?,?,?,?)",
                (room_id, persona_name, user["username"], _now(), direct_key),
            )
            conn.execute(
                "INSERT INTO room_invites(room_id,persona_name,invited_at) VALUES (?,?,?)",
                (room_id, persona_name, _now()),
            )
        conn.commit()
    finally:
        conn.close()
    return {"ok": True, "persona_name": persona_name, "room_id": room_id,
            "chat_url": f"/#room={urllib.parse.quote(room_id)}",
            "disclaimer": story.get("persona_disclaimer")}


@app.get("/api/dating-sim/playable-stories")
def dating_sim_playable_stories(request: Request):
    """관리자 전용 — 시나리오·이미지가 모두 준비되어 지금 바로 진행할 수 있는
    미연시(작품별 이야기) 목록. 프론트의 "미연시 목록" 팝오버에서 골라 들어간다."""
    _require_owner(request)
    username = _request_username(request)
    conn = get_conn()
    try:
        progress = {
            row["character_id"]: row for row in
            conn.execute("SELECT * FROM dating_sim_progress WHERE username=?", (username,)).fetchall()
        }
    finally:
        conn.close()
    stories = []
    for book_id in dating_sim_story.all_book_ids():
        story_id = f"book:{book_id}"
        try:
            story = _dating_story(story_id, username)
        except HTTPException:
            continue
        scenario_ok, images_ok, image_count = dating_sim_story.book_readiness(book_id)
        readiness = dating_sim_story.book_readiness_details(book_id)
        # 기존 호출자·테스트가 book_readiness를 대체해도 기본 3개 상태값은
        # 유지하고, 상세 통계는 실제 매니페스트가 있을 때만 덧붙인다.
        if image_count and not readiness.get("image_count"):
            readiness["image_count"] = image_count
        _, work_dir = dating_sim_story.resolve_book_work_dir(story_id)
        scenario_progress = None
        if work_dir:
            progress_path = work_dir / "dating_sim_scenario_progress.json"
            try:
                raw_progress = json.loads(progress_path.read_text(encoding="utf-8"))
                if isinstance(raw_progress, dict):
                    scenario_progress = {
                        key: raw_progress.get(key) for key in (
                            "status", "done", "total", "percent", "current",
                            "started_at", "updated_at", "elapsed_seconds", "eta_seconds",
                            "average_day_seconds", "expected_finished_at",
                        )
                    }
            except (OSError, ValueError):
                pass
        row = progress.get(story_id)
        if row:
            # /api/dating-sim/state가 사용하는 것과 동일한 정규화 함수를
            # 거쳐 목록의 호감도·진행일·완료 상태를 실제 플레이와 일치시킨다.
            # 이 과정에서 보정된 값은 DB에도 저장되어 다음 기기에서도 같다.
            progress_conn = get_conn()
            try:
                row = _dating_sim_row(progress_conn, username, story)
            finally:
                progress_conn.close()
        stories.append({
            "story_id": story_id, "character_name": story["name"],
            "source_title": story.get("source_title"),
            "character_image": story.get("character_image"),
            "started": bool(row), "day": min(row["day"], story["total_days"]) if row else 0,
            "affection": row["affection"] if row else None,
            "total_days": story["total_days"], "completed": bool(row and row["completed"]),
            # ★ 2026-09-24: 이미지·시나리오가 덜 끝난 작품도 목록에서 빼지 않고 미완료로 표시한다.
            "ready": scenario_ok and images_ok, "scenario_ready": scenario_ok,
            "images_ready": images_ok, "image_count": image_count,
            "image_required": readiness.get("image_required", readiness.get("image_limit", 42)),
            "portrait_ready": readiness.get("portrait_ready", images_ok),
            "legacy_complete": readiness.get("legacy_complete", False),
            "scene_assignment_count": readiness.get("scene_assignment_count", 0),
            "scene_assignment_required": readiness.get("scene_assignment_required", 0),
            "scenario_progress": scenario_progress,
        })
    # 사용자가 관계를 이어 온 작품부터 찾을 수 있도록 시작한 작품을 호감도
    # 내림차순으로 먼저 둔다. 같은 호감도와 미시작 작품은 제작 완료 상태를 따른다.
    stories.sort(key=lambda item: (not item["started"], -(item["affection"] if item["affection"] is not None else -1),
                                   not item["scenario_ready"], not item["ready"],
                                   re.sub(r"\[([^|\]]+)\|[^\]]*\]", r"\1", item["character_name"] or "")))
    return stories


@app.get("/api/dating-sim/scenario-gallery")
def dating_sim_scenario_gallery(request: Request):
    """로그인 사용자가 새 만남을 고를 때 필요한 완성작 초상화 목록만 제공한다."""
    _require_signed_in_user(request)
    username = _request_username(request)
    is_admin = _is_owner_request(request)
    conn = get_conn()
    try:
        progress = {
            row["character_id"]: dict(row) for row in
            conn.execute("SELECT * FROM dating_sim_progress WHERE username=?", (username,)).fetchall()
        }
    finally:
        conn.close()
    items = []
    for book_id in dating_sim_story.all_book_ids():
        scenario_ok, images_ok, _image_count = dating_sim_story.book_readiness(book_id)
        if not (scenario_ok and images_ok):
            continue
        story_id = f"book:{book_id}"
        try:
            story = _dating_story(story_id, username)
        except HTTPException:
            continue
        row = progress.get(story_id)
        items.append({
            "story_id": story_id,
            "character_name": story["name"],
            "character_name_ko": story.get("character_name_ko"),
            "character_image": story.get("character_image"),
            "age": int(story.get("character_age") or 25),
            "source_title": story.get("source_title"),
            "started": bool(row),
            "completed": bool(row and row.get("completed")),
            "day": min(int(row.get("day") or 1), story["total_days"]) if row else 0,
            "total_days": story["total_days"],
            "character_persona": story.get("character_persona") or {},
            "persona_disclaimer": story.get("persona_disclaimer") or "",
            "is_admin": is_admin,
        })
    items.sort(key=lambda item: (item["started"], re.sub(
        r"\[([^|\]]+)\|[^\]]*\]", r"\1", item["character_name"] or ""
    )))
    return items


@app.post("/api/dating-sim/new")
def dating_sim_new_encounter(request: Request, body: DatingSimNewRequest | None = None):
    """아직 시작하지 않은 만남(기본 이야기 또는 서재의 작품) 하나를 무작위로
    골라준다. 전부 이미 시작했으면 409 — 그 경우 프론트는 기존 만남을
    이어가거나 게임 안 "처음부터 다시하기"로 특정 만남을 초기화하게 안내한다."""
    _require_signed_in_user(request)
    username = _request_username(request)
    conn = get_conn()
    try:
        started = {
            row["character_id"] for row in
            conn.execute("SELECT character_id FROM dating_sim_progress WHERE username=?", (username,)).fetchall()
        }
    finally:
        conn.close()
    # 새 만남은 학습 단어·표현을 전수 반영한 시나리오와 작품 이미지가 모두
    # 준비된 작품에서만 시작한다. 고정 소이 템플릿이나 생성 중인 작품을 먼저
    # 보여주지 않는다(2026-09-21).
    requested = str(body.story_id or "").strip() if body else ""
    if requested:
        match = re.fullmatch(r"book:([a-f0-9]{20})", requested)
        if not match:
            raise HTTPException(status_code=422, detail="선택한 시나리오 번호가 올바르지 않습니다")
        scenario_ok, images_ok, _image_count = dating_sim_story.book_readiness(match.group(1))
        if not (scenario_ok and images_ok):
            raise HTTPException(status_code=409, detail="선택한 시나리오는 아직 플레이 준비가 끝나지 않았습니다")
        selected = requested
    else:
        candidates = []
        exclude_books = {sid.split(":", 1)[1] for sid in started if sid.startswith("book:")}
        book_id = dating_sim_story.random_book_id(exclude=exclude_books)
        if book_id:
            candidates.append(f"book:{book_id}")
        if not candidates:
            raise HTTPException(status_code=409, detail="완전히 준비된 새 시나리오가 아직 없어요. 기존 만남을 이어가거나 다음 기상 알람의 자동 생성을 기다려주세요")
        selected = random.choice(candidates)
    difficulty = _dating_difficulty(body.difficulty if body else "normal")
    story = _dating_story(selected, username)
    story["_requested_difficulty"] = difficulty
    conn = get_conn()
    try:
        _dating_sim_row(conn, username, story)
    finally:
        conn.close()
    return {"story_id": selected, "difficulty": difficulty}


class BattleSimChoiceRequest(BaseModel):
    battle_id: str
    choice_index: int


class BattleSimProbeRequest(BaseModel):
    battle_id: str
    symbol: str


class BattleSimRequest(BaseModel):
    battle_id: str


class LifeTerrainSubmitRequest(BaseModel):
    domain: str
    answers: dict[str, int]


@app.get("/life-terrain/")
def life_terrain_dashboard(request: Request):
    _require_signed_in_user(request)
    return FileResponse(str(LIFE_TERRAIN_WEB_DIR / "index.html"), headers={"Cache-Control": "no-store"})


@app.get("/life-terrain")
def life_terrain_redirect():
    return RedirectResponse("/life-terrain/", status_code=307)


@app.get("/life-terrain/static/{filename}")
def life_terrain_static(filename: str, request: Request):
    _require_signed_in_user(request)
    if filename not in {"style.css", "app.js", "manifest.webmanifest"}:
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다")
    return FileResponse(str(LIFE_TERRAIN_WEB_DIR / filename), headers={"Cache-Control": "no-store"})


@app.get("/api/life-terrain/quiz")
def life_terrain_quiz_data(request: Request):
    _require_signed_in_user(request)
    return {"domains": life_terrain_quiz.DOMAINS, "questions": life_terrain_quiz.public_questions()}


@app.get("/api/life-terrain/results")
def life_terrain_results(request: Request, limit: int = Query(default=12, ge=1, le=50)):
    _require_signed_in_user(request)
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT id,domain,report_json,created_at FROM life_terrain_results "
            "WHERE username=? ORDER BY id DESC LIMIT ?",
            (_request_username(request), limit),
        ).fetchall()
    finally:
        conn.close()
    results = []
    for row in rows:
        try:
            report = json.loads(row["report_json"])
        except (TypeError, json.JSONDecodeError):
            report = {}
        results.append({"id": row["id"], "domain": row["domain"], "report": report,
                        "created_at": row["created_at"]})
    return results


@app.post("/api/life-terrain/results")
def life_terrain_submit(body: LifeTerrainSubmitRequest, request: Request):
    _require_signed_in_user(request)
    try:
        report = life_terrain_quiz.evaluate(body.domain, body.answers)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    username, now = _request_username(request), _now()
    conn = get_conn()
    try:
        cursor = conn.execute(
            "INSERT INTO life_terrain_results(username,domain,answers_json,report_json,created_at) "
            "VALUES(?,?,?,?,?)",
            (username, body.domain, json.dumps(body.answers, ensure_ascii=False),
             json.dumps(report, ensure_ascii=False), now),
        )
        conn.commit()
        result_id = cursor.lastrowid
    finally:
        conn.close()
    return {"id": result_id, "created_at": now, "report": report}


def _battle(battle_id):
    battle = battle_sim_story.BATTLES.get(battle_id)
    if not battle:
        raise HTTPException(status_code=404, detail="전투를 찾을 수 없습니다")
    return battle


def _battle_row(conn, username, battle_id):
    row = conn.execute("SELECT * FROM battle_sim_progress WHERE username=? AND battle_id=?",
                       (username, battle_id)).fetchone()
    if row:
        return dict(row)
    now = _now()
    initial = json.dumps(battle_sim_story.initial_state(_battle(battle_id)), ensure_ascii=False)
    conn.execute("INSERT INTO battle_sim_progress(username,battle_id,phase,score,completed,created_at,updated_at,state_json,history_json) VALUES(?,?,0,0,0,?,?,?,'[]')",
                 (username, battle_id, now, now, initial))
    conn.commit()
    return {"username": username, "battle_id": battle_id, "phase": 0, "score": 0, "completed": 0,
            "state_json": initial, "history_json": "[]", "best_score": 0, "attempts": 0}


def _battle_json(value, fallback):
    try:
        parsed = json.loads(value or "")
        return parsed if isinstance(parsed, type(fallback)) and (parsed or not fallback) else deepcopy(fallback)
    except (TypeError, json.JSONDecodeError):
        return deepcopy(fallback)


def _battle_commander_message(conn, username, battle, phase, choice, counsel):
    """전투 명령에 대한 지휘관의 조언을 기존 툴파챗 1:1 대화방에도 남긴다.

    시뮬레이션 결과는 즉시 보여야 하므로 작가된 현장 조언을 저장하고,
    방이 존재하면 평소 메신저의 안 읽은 메시지 흐름에도 자연스럽게 포함된다.
    """
    commander = battle.get("commander") or "지휘관"
    persona = conn.execute("SELECT 1 FROM personas WHERE name=?", (commander,)).fetchone()
    if not persona:
        return {**counsel, "chat_url": None, "message_id": None}
    direct_key = f"persona:{username}:{commander}"
    room = conn.execute("SELECT room_id FROM custom_rooms WHERE direct_key=?", (direct_key,)).fetchone()
    if room:
        room_id = room["room_id"]
    else:
        room_id = f"{CUSTOM_ROOM_ID_PREFIX}{uuid.uuid4().hex[:10]}"
        conn.execute(
            "INSERT INTO custom_rooms(room_id,label,owner_username,created_at,direct_key) VALUES(?,?,?,?,?)",
            (room_id, commander, username, _now(), direct_key),
        )
        conn.execute(
            "INSERT OR IGNORE INTO room_invites(room_id,persona_name,invited_at) VALUES(?,?,?)",
            (room_id, commander, _now()),
        )
    content = f"[정형 전투 · {phase}턴] 「{choice['text']}」\n\n{counsel['text']}"
    cursor = conn.execute(
        "INSERT INTO messages(room_id,sender,content,created_at,is_system) VALUES(?,?,?,?,0)",
        (room_id, commander, content, _now()),
    )
    return {**counsel, "chat_url": f"/#room={urllib.parse.quote(room_id, safe='')}",
            "message_id": cursor.lastrowid}


def _battle_payload(row, battle, last_result=None):
    phase = min(row["phase"], len(battle["phases"]))
    situation = _battle_json(row.get("state_json"), battle_sim_story.initial_state(battle))
    history = _battle_json(row.get("history_json"), [])
    payload = {"battle": {key: value for key, value in battle.items() if key != "phases"},
               "phase": phase, "score": row["score"], "completed": bool(row["completed"]),
               "last_result": last_result, "situation": situation, "history": history,
               "best_score": int(row.get("best_score") or 0), "attempts": int(row.get("attempts") or 0),
               "map_scene": battle_sim_story.map_scene(row["battle_id"], phase, situation)}
    payload["probes"] = battle_sim_story.probe_options(row["battle_id"], situation)
    payload["commander_message"] = history[-1].get("commander_message") if history else None
    payload["battle"].pop("initial_state", None)
    payload["battle"]["total_phases"] = len(battle["phases"])
    if not payload["completed"]:
        current = battle["phases"][phase]
        choices = []
        for index, choice in enumerate(current["choices"]):
            available = battle_sim_story.choice_available(choice, situation)
            choices.append({"index": index, "text": choice["text"], "locked": not available,
                            "locked_reason": "" if available else choice.get("locked_reason", "조건이 부족합니다"),
                            "effects": battle_sim_story.choice_preview(choice),
                            "principle": choice.get("principle", "")})
        payload["current"] = {"title": current.get("title", f"명령 {phase + 1}"),
                              "prompt": current["prompt"], "choices": choices}
    else:
        payload["summary"] = battle_sim_story.battle_summary(battle, row["score"], situation)
    return payload


@app.get("/battle-sim/")
def battle_sim_dashboard(request: Request):
    _require_signed_in_user(request)
    return FileResponse(str(BATTLE_SIM_WEB_DIR / "index.html"), headers={"Cache-Control": "no-store"})


@app.get("/battle-sim")
def battle_sim_redirect():
    return RedirectResponse("/battle-sim/", status_code=307)


@app.get("/battle-sim/static/{filename}")
def battle_sim_static(filename: str, request: Request):
    _require_signed_in_user(request)
    allowed = {"style.css", "app.js", "jingxing_map.png", "cannae_map.png", "austerlitz_map.png",
               "jingxing_codex_map.png", "jingxing_codex_map_wide_v2.png", "cannae_codex_map.png", "austerlitz_codex_map.png",
               "jingxing_intro_terrain_v1.png", "portrait_hanxin_v1.png", "portrait_zhanger_v1.png",
               "portrait_zhaoxie_v1.png", "portrait_lizuo_che_v1.png", "manifest.webmanifest"}
    if filename not in allowed:
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다")
    return FileResponse(str(BATTLE_SIM_WEB_DIR / filename), headers={
        "Cache-Control": "no-store" if filename in {"app.js", "style.css"} else "public, max-age=86400"
    })


@app.get("/sunzi")
def sunzi_redirect():
    return RedirectResponse("/sunzi/", status_code=307)


@app.get("/sunzi/")
def sunzi_dashboard(request: Request):
    _require_signed_in_user(request)
    return RedirectResponse("/sunzi/app/archive#list", status_code=307)


@app.get("/sunzi/app")
def sunzi_renderer_root(request: Request):
    _require_signed_in_user(request)
    return RedirectResponse("/sunzi/app/archive#list", status_code=307)


@app.get("/sunzi/app/{path:path}")
def sunzi_renderer(path: str, request: Request):
    _require_signed_in_user(request)
    root = SUNZI_SITE_DIR.resolve()
    relative = path.strip("/")
    candidates = [root / relative]
    if relative and not Path(relative).suffix:
        candidates.insert(0, root / f"{relative}.html")
    for candidate in candidates:
        target = candidate.resolve()
        if not target.is_relative_to(root) or not target.is_file():
            continue
        is_html = target.suffix.lower() == ".html"
        return FileResponse(
            str(target),
            headers={"Cache-Control": "no-store" if is_html else "public, max-age=86400"},
        )
    raise HTTPException(status_code=404, detail="병법 페이지를 찾을 수 없습니다")


@app.get("/sunzi/static/{filename}")
def sunzi_static(filename: str, request: Request):
    _require_signed_in_user(request)
    if filename not in {"style.css", "app.js", "manifest.webmanifest"}:
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다")
    return FileResponse(str(SUNZI_WEB_DIR / filename), headers={"Cache-Control": "no-store"})


@app.get("/api/battle-sim/battles")
def battle_sim_battles(request: Request):
    _require_signed_in_user(request)
    return [{"id": key, **{k: v for k, v in battle.items() if k in {"title", "year", "commander", "map"}}}
            for key, battle in battle_sim_story.BATTLES.items()]


@app.get("/api/battle-sim/state")
def battle_sim_state(request: Request, battle_id: str):
    _require_signed_in_user(request)
    battle = _battle(battle_id)
    conn = get_conn()
    try:
        row = _battle_row(conn, _request_username(request), battle_id)
    finally:
        conn.close()
    return _battle_payload(row, battle)


@app.post("/api/battle-sim/probe")
def battle_sim_probe(body: BattleSimProbeRequest, request: Request):
    _require_signed_in_user(request)
    battle = _battle(body.battle_id)
    username = _request_username(request)
    conn = get_conn()
    try:
        row = _battle_row(conn, username, body.battle_id)
        if row["completed"]:
            raise HTTPException(status_code=409, detail="이미 종료된 전투입니다")
        situation = _battle_json(row.get("state_json"), battle_sim_story.initial_state(battle))
        try:
            situation, result = battle_sim_story.apply_probe(body.battle_id, situation, body.symbol)
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        conn.execute("UPDATE battle_sim_progress SET state_json=?,updated_at=? WHERE username=? AND battle_id=?",
                     (json.dumps(situation, ensure_ascii=False), _now(), username, body.battle_id))
        conn.commit()
        row.update(state_json=json.dumps(situation, ensure_ascii=False))
    finally:
        conn.close()
    return _battle_payload(row, battle, result)


@app.post("/api/battle-sim/choose")
def battle_sim_choose(body: BattleSimChoiceRequest, request: Request):
    _require_signed_in_user(request)
    battle = _battle(body.battle_id)
    username = _request_username(request)
    conn = get_conn()
    try:
        row = _battle_row(conn, username, body.battle_id)
        if row["completed"]:
            raise HTTPException(status_code=409, detail="이미 종료된 전투입니다")
        choices = battle["phases"][row["phase"]]["choices"]
        if body.choice_index not in range(len(choices)):
            raise HTTPException(status_code=400, detail="올바르지 않은 명령입니다")
        choice = choices[body.choice_index]
        situation = _battle_json(row.get("state_json"), battle_sim_story.initial_state(battle))
        if not battle_sim_story.choice_available(choice, situation):
            raise HTTPException(status_code=409, detail=choice.get("locked_reason", "현재 전황에서는 내릴 수 없는 명령입니다"))
        before = {key: situation.get(key) for key in battle_sim_story.STAT_LABELS}
        situation = battle_sim_story.apply_choice(situation, choice)
        phase, score = row["phase"] + 1, row["score"] + choice["score"]
        completed = phase >= len(battle["phases"])
        history = _battle_json(row.get("history_json"), [])
        counsel = battle_sim_story.commander_counsel(battle, choice, situation)
        commander_message = _battle_commander_message(
            conn, username, battle, phase, choice, counsel
        )
        history.append({"turn": phase, "title": battle["phases"][phase - 1].get("title", f"명령 {phase}"),
                        "command": choice["text"], "result": choice["result"], "principle": choice.get("principle", ""),
                        "effects": battle_sim_story.choice_preview(choice), "before": before,
                        "commander_message": commander_message})
        now = _now()
        best_score = max(int(row.get("best_score") or 0), score if completed else 0)
        attempts = int(row.get("attempts") or 0) + int(completed)
        conn.execute("UPDATE battle_sim_progress SET phase=?,score=?,completed=?,state_json=?,history_json=?,best_score=?,attempts=?,updated_at=? WHERE username=? AND battle_id=?",
                     (phase, score, int(completed), json.dumps(situation, ensure_ascii=False),
                      json.dumps(history, ensure_ascii=False), best_score, attempts, now, username, body.battle_id))
        if completed:
            summary = battle_sim_story.battle_summary(battle, score, situation)
            conn.execute("INSERT INTO battle_sim_runs(username,battle_id,score,rank,turns,state_json,history_json,completed_at) VALUES(?,?,?,?,?,?,?,?)",
                         (username, body.battle_id, score, summary["rank"], phase,
                          json.dumps(situation, ensure_ascii=False), json.dumps(history, ensure_ascii=False), now))
        conn.commit()
        row.update(phase=phase, score=score, completed=int(completed), state_json=json.dumps(situation, ensure_ascii=False),
                   history_json=json.dumps(history, ensure_ascii=False), best_score=best_score, attempts=attempts)
    finally:
        conn.close()
    return _battle_payload(row, battle, choice["result"])


@app.post("/api/battle-sim/restart")
def battle_sim_restart(body: BattleSimRequest, request: Request):
    _require_signed_in_user(request)
    battle = _battle(body.battle_id)
    username = _request_username(request)
    conn = get_conn()
    try:
        initial = json.dumps(battle_sim_story.initial_state(battle), ensure_ascii=False)
        conn.execute("UPDATE battle_sim_progress SET phase=0,score=0,completed=0,state_json=?,history_json='[]',updated_at=? WHERE username=? AND battle_id=?",
                     (initial, _now(), username, body.battle_id))
        conn.commit()
        row = _battle_row(conn, username, body.battle_id)
    finally:
        conn.close()
    return _battle_payload(row, battle)


@app.post("/api/dating-sim/visit")
def dating_sim_visit(body: DatingSimLocationRequest, request: Request):
    """장소를 골라 오늘의 장면을 연다 — 선택은 아직 안 하고 대사·선택지만 반환한다."""
    _require_signed_in_user(request)
    username = _request_username(request)
    story = _dating_story(body.story_id, username)
    conn = get_conn()
    try:
        row = _dating_sim_row(conn, username, story)
        if row["completed"]:
            raise HTTPException(status_code=409, detail="이미 끝난 이야기입니다. 다시 시작해보세요")
        if row["pending_location"]:
            raise HTTPException(status_code=409, detail="이미 진행 중인 장면이 있습니다")
        day_scenes = story["scenes"].get(row["day"], {})
        if body.location not in day_scenes:
            raise HTTPException(status_code=400, detail="오늘은 갈 수 없는 장소입니다")
        conn.execute(
            "UPDATE dating_sim_progress SET pending_location=?, updated_at=? WHERE username=? AND character_id=?",
            (body.location, _now(), username, story["id"]),
        )
        conn.commit()
        row["pending_location"] = body.location
    finally:
        conn.close()
    return _dating_sim_state_payload(row, story, username, _is_owner_request(request), body.adult_mode)


@app.post("/api/dating-sim/seen")
def dating_sim_seen(body: DatingSimRestartRequest, request: Request):
    """현재 장면의 마지막 대사까지 실제 표시된 뒤 학습 재료를 본 것으로 기록한다."""
    _require_signed_in_user(request)
    username = _request_username(request)
    story = _dating_story(body.story_id, username)
    conn = get_conn()
    try:
        row = _dating_sim_row(conn, username, story)
        if not row["pending_location"] or row["completed"]:
            raise HTTPException(status_code=409, detail="확인할 장면이 없습니다")
        scene = story["scenes"][row["day"]][row["pending_location"]]
        _dating_mark_scene_seen(conn, username, story, scene)
        conn.commit()
    finally:
        conn.close()
    return {"learning_progress": _dating_learning_progress(username, story)}


@app.post("/api/dating-sim/choose")
def dating_sim_choose(body: DatingSimChoiceRequest, request: Request):
    """선택 결과를 반영하고 같은 흐름의 다음 장면 또는 다음 날로 넘어간다."""
    _require_signed_in_user(request)
    username = _request_username(request)
    story = _dating_story(body.story_id, username)
    conn = get_conn()
    try:
        row = _dating_sim_row(conn, username, story)
        if row["completed"] or not row["pending_location"]:
            raise HTTPException(status_code=409, detail="지금은 선택할 수 있는 장면이 없습니다")
        selected_location = row["pending_location"]
        scene_day = row["day"]
        scene = story["scenes"][scene_day][selected_location]
        if body.choice_index not in range(len(scene["choices"])):
            raise HTTPException(status_code=400, detail="올바르지 않은 선택지입니다")
        selected_choice = scene["choices"][body.choice_index]
        raw_affection_delta = selected_choice["affection"]
        try:
            route_state = json.loads(row.get("route_state") or "{}")
        except (TypeError, ValueError):
            route_state = {}
        for axis, amount in (selected_choice.get("route_effects") or {}).items():
            if axis in dating_sim_story.ROUTE_ENDINGS and amount in {-1, 1}:
                route_state[axis] = max(-99, min(99, int(route_state.get(axis, 0)) + amount))
        route_state_json = json.dumps(route_state, ensure_ascii=False, sort_keys=True)
        difficulty = _dating_difficulty(row.get("difficulty"))
        adjusted_delta = _dating_apply_affection_delta(raw_affection_delta, difficulty)
        next_day, next_location, completed = _dating_next_scene(
            story, scene_day, selected_location,
        )
        start_affection = _dating_start_affection(story, difficulty)
        affection_cap = _dating_affection_cap(next_day, story["total_days"], completed, start_affection)
        old_affection = row["affection"]
        affection = max(0, min(affection_cap, old_affection + adjusted_delta))
        applied_affection_delta = affection - row["affection"]
        ending_id = dating_sim_story.ending_for(story, affection, route_state)["id"] if completed else None
        conn.execute(
            "UPDATE dating_sim_progress SET day=?, affection=?, pending_location=?, completed=?, ending_id=?, route_state=?, "
            "updated_at=? WHERE username=? AND character_id=?",
            (next_day, affection, next_location, int(completed), ending_id, route_state_json, _now(), username, story["id"]),
        )
        conn.commit()
        row.update(day=next_day, affection=affection, pending_location=next_location, route_state=route_state_json,
                   completed=int(completed), ending_id=ending_id)
    finally:
        conn.close()
    payload = _dating_sim_state_payload(row, story, username, _is_owner_request(request), body.adult_mode)
    crossed = list(range(((old_affection // 10) + 1) * 10, affection + 1, 10)) if affection > old_affection else []
    payload["choice_result"] = {
        "affection_delta": applied_affection_delta,
        "choice_score": raw_affection_delta,
        "affection_cap": affection_cap,
        "location": selected_location,
        "character_image": (_dating_admin_scene_image(story, scene_day, selected_location)
                            if _is_owner_request(request) and body.adult_mode else None)
                           or scene.get("character_image")
                           or story.get("character_images", {}).get(
                               selected_location, story.get("character_image")),
        "line": dating_sim_story.choice_reaction(
            scene_day, selected_location,
            raw_affection_delta, story["id"], affection,
        ),
    }
    if crossed:
        milestone = crossed[-1]
        payload["choice_result"]["service_scene"] = {
            "milestone": milestone,
            "title": f"호감도 {milestone} 보너스 장면",
            "description": "관계가 가까워진 만큼 표정과 거리감이 달라진 특별 장면입니다.",
            "image_prompt": (
                "adult Japanese woman, tasteful romantic bonus scene, affectionate expression, "
                "elegant contemporary outfit, cinematic lighting, non-explicit, fully clothed, "
                "no nudity, no sexual act, natural eyes and hands"
            ),
        }
    return payload


@app.post("/api/dating-sim/restart")
def dating_sim_restart(request: Request, body: DatingSimRestartRequest | None = None):
    _require_signed_in_user(request)
    username = _request_username(request)
    story = _dating_story(body.story_id if body else None, username)
    difficulty = _dating_difficulty(body.difficulty if body and body.difficulty else "normal")
    start_affection = _dating_start_affection(story, difficulty)
    conn = get_conn()
    try:
        cursor = conn.execute(
            "UPDATE dating_sim_progress SET day=1, affection=?, difficulty=?, pending_location=NULL, completed=0, "
            "ending_id=NULL, route_state='{}', scenario_run=scenario_run+1, updated_at=? WHERE username=? AND character_id=?",
            (start_affection, difficulty, _now(), username, story["id"]),
        )
        conn.commit()
        if cursor.rowcount == 0:
            story["_requested_difficulty"] = difficulty
        row = _dating_sim_row(conn, username, story)
    finally:
        conn.close()
    # 기본 DB 이야기는 새 회차 번호로 변형을 다시 선택한다. EPUB 템플릿에는 영향 없다.
    story = _dating_story(body.story_id if body else None, username)
    return _dating_sim_state_payload(
        row, story, username, _is_owner_request(request), bool(body and body.adult_mode)
    )


@app.get("/shift-alarm")
def shift_alarm_redirect():
    return RedirectResponse("/shift-alarm/", status_code=307)


@app.get("/shift-alarm/")
def shift_alarm_dashboard(request: Request):
    _require_owner(request)
    return FileResponse(
        str(SHIFT_ALARM_DASHBOARD_DIR / "index.html"),
        headers={"Cache-Control": "private, no-store, max-age=0"},
    )


@app.get("/shift-alarm/static/{filename}")
def shift_alarm_static(filename: str, request: Request):
    _require_owner(request)
    if filename not in {"style.css", "enhancements.css", "pipeline.css", "pipeline-recovery.css", "sunzi-wheel.css", "sunzi-deck.css", "sunzi-recovery.css", "reminder-ui.css", "reminder-focus.css", "routine-chart.css", "shift-schedule.css", "shift-day-reminders.css", "home-control.css", "bottom-tabs.css", "panel-reorder.css", "panel-polish.css", "summary-actions.css", "quest.css", "day-theme.css", "app.js"}:
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다")
    return FileResponse(str(SHIFT_ALARM_DASHBOARD_DIR / filename))


@app.get("/shift-alarm/static/assets/{filename}")
def shift_alarm_static_asset(filename: str, request: Request):
    _require_owner(request)
    if filename not in {"shift-pet-adventurer-sprites.png", "budeugi-urgent.mp3"}:
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다")
    return FileResponse(str(SHIFT_ALARM_DASHBOARD_DIR / "assets" / filename))


@app.get("/shift-alarm/download/{file_id}")
def shift_alarm_safari_download_page(file_id: str, request: Request):
    """iOS PWA의 빈 파일 미리보기 대신 Safari로 넘길 안내 화면을 제공한다."""
    _require_owner(request)
    path = _shift_alarm_av4_file(file_id)
    save_name = _shift_alarm_ios_filename(path)
    file_url = f"/api/shift-alarm/video-library/{file_id}/file"
    page = f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="color-scheme" content="light dark"><title>Safari에서 영상 받기</title>
<style>
:root{{font-family:-apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo",sans-serif;color-scheme:light dark}}
*{{box-sizing:border-box}}body{{min-height:100dvh;margin:0;padding:calc(env(safe-area-inset-top) + 28px) 22px calc(env(safe-area-inset-bottom) + 28px);display:grid;place-items:center;background:#f6f3fb;color:#211b2d}}
main{{width:min(440px,100%);padding:28px 22px;border:1px solid #ded5ef;border-radius:26px;background:#fff;box-shadow:0 24px 70px #39266520}}
.step{{display:inline-grid;width:44px;height:44px;place-items:center;border-radius:15px;background:#7454cf;color:white;font-size:22px;font-weight:850}}h1{{margin:18px 0 10px;font-size:26px}}p{{margin:0;color:#71697d;line-height:1.65}}.guide{{margin:22px 0;padding:16px;border-radius:16px;background:#f0eafb;color:#3c2b67;line-height:1.6}}.guide b{{display:block;margin-bottom:4px}}a{{display:block;width:100%;min-height:54px;padding:16px;border-radius:16px;background:#6f4ccd;color:white;text-align:center;text-decoration:none;font-weight:850}}small{{display:block;margin-top:14px;color:#8b8494;line-height:1.5;overflow-wrap:anywhere}}
@media(prefers-color-scheme:dark){{body{{background:#15121c;color:#f7f3ff}}main{{background:#211c2b;border-color:#413653}}p,small{{color:#aca3b8}}.guide{{background:#332746;color:#eadfff}}}}
</style></head><body><main><span class="step">↓</span><h1>Safari에서 다운로드하세요</h1>
<p>지금 화면이 작은 미리보기 창이라면 먼저 Safari 앱 본체로 전환해야 다운로드 목록과 실제 진행률을 볼 수 있습니다.</p>
<div class="guide"><b>1. 오른쪽 아래 나침반 아이콘을 누르세요.</b>Safari 앱이 열리면 이 페이지의 아래 버튼을 다시 누르고, 주소창 옆 ↓ 아이콘에서 진행률을 확인하세요.</div>
<a href="{html.escape(file_url, quote=True)}">실제 다운로드 시작</a>
<small>저장 파일명: {html.escape(save_name)}<br>Safari가 기본 브라우저가 아니면 iPhone 설정 → 앱 → 기본 앱 → 브라우저 앱에서 Safari를 선택하세요.</small>
</main></body></html>"""
    return Response(page, media_type="text/html", headers={"Cache-Control": "private, no-store"})


# ★ 2026-09-14: "채팅창에서 하는게아니라 shift alarm시스템 내부에 버튼만들어줘"
# 요청 — 처음엔 알람지기 페르소나가 채팅으로 실행하게 만들었는데(worker/
# persona_worker.py), 대시보드에서 바로 누르는 버튼을 원해서 이 서버에도
# 같은 동작을 추가한다. 서버도 이 Mac에서 직접 돈다("왜 이런 구조인가"
# 참고)는 이 프로젝트가 이미 전제하고 있으므로 여기서 osascript/Elmedia를
# 직접 실행해도 워커를 거칠 때보다 빠르고(폴링 지연 없음) 구조가 단순하다.
# shift_alarm.py(list_audio_tracks/reset_elmedia_playlist/play_folder_in_elmedia)
# ·worker/persona_worker.py(_shift_alarm_*)와 완전히 같은 로직 — 하나를
# 고치면 세 곳 다 맞춰야 한다.
SHIFT_ALARM_CLASSIC_FOLDER = "/Users/forrestdpark/Desktop/BlogImage/Coffee and Meditation"
SHIFT_ALARM_FAVORITES_FOLDER = str(MP3_FAVORITES_DIR)
SHIFT_ALARM_SLEEP_FOLDER = "/Users/forrestdpark/Desktop/BlogImage/잠잘준비"
SHIFT_ALARM_ELMEDIA_PLAYLIST_DB = os.path.expanduser(
    "~/Library/Containers/com.eltima.elmedia6.mas/Data/Library/Application Support/"
    "Elmedia Video Player/Playlist.db"
)
SHIFT_ALARM_ELMEDIA_AUDIO_EXTENSIONS = {
    ".aac", ".aif", ".aiff", ".alac", ".flac", ".m4a", ".mp3", ".ogg", ".opus", ".wav", ".wma",
}
# ★ 2026-09-14 도입 → 같은 날 되돌림: "bin would like to access data from
# other apps" 팝업 원인을 "open -a 자체가 Automation 승인을 요구한다"고
# 잘못 진단해 ElmediaOpenHelper.app(open -na --args)으로 위임했었다. 실측
# 결과 그 helper의 on run 핸들러가 아예 트리거되지 않아 재생이 완전히
# 죽었다(shift_alarm.py의 같은 위치 주석에 상세 진단 기록). open -a 직접
# 호출은 터미널에서 항상 정상 동작해 원래대로 되돌린다.

# ★ 2026-09-14: "추천사이트 열기 기능도 있으면 좋겠어" — shift_alarm.py의
# 🎲 추천 사이트 열기(pick_random_bookmarks/open_random_bookmarks)와 완전히
# 같은 로직. 같은 히스토리 파일을 공유하므로 메뉴바에서 이미 추천된 URL은
# 여기서도 다시 추천되지 않는다(반대 방향도 마찬가지). Chrome은 샌드박스
# 빌드가 아니라 위 Elmedia와 달리 open -a에 Automation 승인이 필요 없다
# (이직시스템 등 이 저장소의 다른 open -a Chrome 호출과 동일하게 안전).
SHIFT_ALARM_CHROME_BOOKMARKS_PATH = os.path.expanduser(
    "~/Library/Application Support/Google/Chrome/Default/Bookmarks"
)
SHIFT_ALARM_BOOKMARK_URLS_EXPORT_FILE = os.path.expanduser("~/.shift_alarm_bookmark_urls.json")
SHIFT_ALARM_RANDOM_BOOKMARK_FOLDER = "天"
SHIFT_ALARM_RANDOM_BOOKMARK_HISTORY_FILE = os.path.expanduser(
    "~/.shift_alarm_random_bookmark_history.json"
)

# ★ 2026-09-14: "클래식/좋아요 재생 중일 때 대시보드에 어느 쪽인지 표시해줘" —
# shift_alarm.py·worker/persona_worker.py와 같은 경로를 공유(같은 Mac)해서
# 메뉴바·채팅·대시보드 중 어디서 재생을 시작했든 대시보드가 반영한다.
SHIFT_ALARM_NOW_PLAYING_FILE = os.path.expanduser("~/.shift_alarm_now_playing.json")
SHIFT_ALARM_MEDIA_COMMAND_FILE = Path(os.path.expanduser("~/.shift_alarm_media_command.json"))
SHIFT_ALARM_MEDIA_COMMAND_ACK_FILE = Path(os.path.expanduser("~/.shift_alarm_media_command_ack.json"))
SHIFT_ALARM_VIDEO_DIR = Path(os.path.expanduser("~/.tulpachat/video_downloads"))
SHIFT_ALARM_VIDEO_STATUS_FILE = SHIFT_ALARM_VIDEO_DIR / "status.json"
SHIFT_ALARM_VIDEO_WORKER = REPO_ROOT / "shift_alarm" / "stream_download_worker.py"
SHIFT_ALARM_VIDEO_PYTHON = sys.executable
SHIFT_ALARM_VIDEO_DB = SHIFT_ALARM_VIDEO_DIR / "downloads.db"
SHIFT_ALARM_VIDEO_FILES = Path("/Users/forrestdpark/Desktop/BlogImage/av4")

# ★ 2026-09-15: "av4 폴더에있는 영상 선택해서 일본어자막 추출만 할수있는 버튼
# 잇으면 좋겠어 ... 운동용영상추출은 제외하고 epub 만들고 일본어 스터디
# 시스템에 작품이 올라오는것까지" 요청 — shift_alarm.py 메뉴바의
# `📝 자막·노션·EPUB만 (폴더 선택)`(run_jp_subtitle_stage2_only)과 완전히 같은
# subtitle_notion_epub_only.sh를 대시보드에서 av4 파일 하나를 골라 실행한다.
# 그 스크립트는 폴더 안의 영상을 전부 처리하므로, av4에 다른 다운로드가 같이
# 있어도 섞이지 않도록 선택한 파일만 격리된 작업 폴더로 복사해서 넘긴다(원본은
# 그대로 두어 iPhone 전송 기능과 충돌하지 않음). WORKOUT_EXTRACTION_ENABLED=0은
# 스크립트 자체가 이미 고정하므로 별도 처리가 필요 없다.
JP_SUBTITLE_DIR = REPO_ROOT / "일본어자막추출"
JP_COMPLETED_EPUB_DIR = Path("/Users/forrestdpark/Desktop/BlogImage/av완성작")
JP_SUBTITLE_STAGE2_SCRIPT = JP_SUBTITLE_DIR / "subtitle_notion_epub_only.sh"
SHIFT_ALARM_SUBTITLE_DIR = Path(os.path.expanduser("~/.tulpachat/jp_subtitle_extract"))
SHIFT_ALARM_SUBTITLE_STATUS_FILE = SHIFT_ALARM_SUBTITLE_DIR / "status.json"
# shift_alarm.py의 JP_SUBTITLE_MARKER_TIMEOUT_SECONDS와 동일 — 영상 여러 개를
# 이어붙여 처리하면 오래 걸릴 수 있어 넉넉히 3시간.
SHIFT_ALARM_SUBTITLE_TIMEOUT_SECONDS = 3 * 60 * 60
SHIFT_ALARM_SUBTITLE_STALE_GRACE_SECONDS = 120


def _shift_alarm_subtitle_pipeline_alive():
    """자막 파이프라인(subtitle_pipeline_body.sh) 프로세스가 하나라도 떠 있는지."""
    try:
        return subprocess.run(["/usr/bin/pgrep", "-f", "subtitle_pipeline_body.sh"],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5,
                              check=False).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return True  # 확인 못 하면 살아 있다고 보고 기존 타임아웃에 맡긴다

# shift_alarm.py의 JP_SUBTITLE_STUDY_ROOM_ID와 같은 방 — 완료되면 학습카드
# 위주로 오늘 회차를 소개해달라는 트리거를 그대로 재사용한다.
JP_SUBTITLE_STUDY_ROOM_ID = "custom_1fc73254c0"

# ★ 2026-09-15: "자막추출 버튼누를때도 추출진행률 알수있게 ui 만들어줘" 요청 —
# 이 파이프라인은 영상 다운로드처럼 바이트 단위 진행률이 없어서, 대신
# subtitle_notion_epub_only.sh가 새 터미널 창에서 남기는 로그 파일
# (logs/<타임스탬프>_<job_id>.log, subtitle_notion_epub_only.sh 참고)에서
# subtitle_pipeline_body.sh가 실제로 echo하는 단계 마커 문자열을 찾아 대략적인
# 퍼센트로 근사한다. 긴 영상은 여러 구간(파트)으로 나뉘어 1~2번 마커가
# 파트마다 반복되지만, 로그 전체에서 "가장 앞선(가장 큰 퍼센트) 마커"만
# 취하므로 역행하지 않는다.
JP_SUBTITLE_LOG_DIR = JP_SUBTITLE_DIR / "logs"
SHIFT_ALARM_SUBTITLE_PROGRESS_MARKERS = [
    (8, "🎵 오디오 추출 중", "오디오를 추출하는 중"),
    (15, "📝 Whisper 자막 분석 중", "Whisper로 일본어 대사를 받아쓰는 중 — 영상 길이에 따라 오래 걸릴 수 있습니다"),
    (35, "⏱ Whisper 자막 생성 소요", "번역·후리가나를 붙이고 Notion·메모 앱에 기록하는 중"),
    (60, "📚 EPUB 생성 중", "EPUB 파일을 만드는 중"),
    (68, "✅ EPUB 생성 완료", "요약·학습카드를 만드는 중"),
    (78, "📖 Apple Books 문장 동기화", "낭독판 EPUB(음성 낭독)을 만드는 중 — 가장 오래 걸리는 단계입니다"),
    (92, "⏱ 낭독판 EPUB 생성 소요", "마무리 정리하는 중"),
    (97, "✅ 정리 완료", "거의 다 됐습니다"),
]


def _process_is_alive(pid):
    try:
        os.kill(int(pid), 0)
        return True
    except (OSError, TypeError, ValueError):
        return False


def _shift_alarm_scenario_failure_reason(log_path=None):
    """사용자에게 내부 로그 대신 복구에 필요한 원인만 짧게 알려준다."""
    try:
        tail = Path(log_path).read_text(encoding="utf-8", errors="ignore")[-12000:].lower()
    except (OSError, TypeError):
        tail = ""
    if "usage limit" in tail or "rate limit" in tail or "quota" in tail or "429" in tail:
        return "AI 사용량 한도 또는 요청 제한으로 시나리오 생성이 중단되었습니다. 잠시 후 다시 실행해주세요."
    if "timed out" in tail or "timeout" in tail:
        return "AI 응답 시간이 초과되어 시나리오 생성이 중단되었습니다. 다시 실행하면 기존 EPUB은 재사용합니다."
    if "network" in tail or "connection" in tail:
        return "네트워크 연결 문제로 시나리오 생성이 중단되었습니다. 연결을 확인한 뒤 다시 실행해주세요."
    return "시나리오 생성 프로세스가 결과 파일을 만들기 전에 종료되었습니다. 기존 자막·번역·EPUB은 그대로 두고 이 단계만 다시 실행할 수 있습니다."


def _shift_alarm_image_failure_reason(content):
    """이미지 단계의 실제 마지막 오류를 사용자 행동으로 연결해 설명한다."""
    tail = str(content or "")[-20000:]
    if "ComfyUI 생성이" in tail and "초 안에 완료되지 않았습니다" in tail:
        match = re.search(r"ComfyUI 생성이\s*(\d+)초 안에 완료되지 않았습니다", tail)
        timeout_minutes = max(1, round(int(match.group(1)) / 60)) if match else 10
        return (f"시나리오는 완성됐지만 ComfyUI가 첫 이미지 생성 요청을 {timeout_minutes}분 안에 "
                "끝내지 못했습니다. ComfyUI 상태를 복구한 뒤 이미지 단계만 다시 실행할 수 있습니다.")
    if "ComfyUI 서버" in tail and "연결할 수 없습니다" in tail:
        return "시나리오는 완성됐지만 로컬 ComfyUI 서버에 연결되지 않았습니다. 이미지 단계만 다시 실행할 수 있습니다."
    if "작품 이미지 일부가 아직 없습니다" in tail:
        return "시나리오는 완성됐지만 이미지 생성 프로세스가 완료되지 않았습니다. 이미지 단계만 다시 실행할 수 있습니다."
    return "미연시 이미지가 아직 완성되지 않았습니다. 기존 시나리오는 유지하고 이미지 단계만 다시 실행할 수 있습니다."


def _shift_alarm_scenario_progress(book_dir, content):
    """하드코딩된 45% 대신 진행 JSON 또는 로그의 마지막 실측값을 반환한다."""
    if book_dir:
        try:
            payload = json.loads((book_dir / "dating_sim_scenario_progress.json").read_text(encoding="utf-8"))
            return max(0, min(100, int(payload.get("percent") or 0)))
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            pass
    matches = re.findall(r"시나리오\s+(\d+)\s*/\s*(\d+)\s*·\s*(\d+)%", content or "")
    if matches:
        return max(0, min(100, int(matches[-1][2])))
    return 0


def _jp_subtitle_book_dir(filename):
    """영상 제목에 대응하는 library 폴더를 실제 저장 방식까지 고려해 찾는다.

    오래된 작업은 원본 제목(공백·괄호 포함)을 폴더명으로 사용했고, 일부 작업은
    셸 안전 이름을 사용했다. 코드 번호로 찾는 보조 경로는 후보가 하나일 때만
    허용해 다른 작품에 쓰는 일을 막는다.
    """
    stem = Path(str(filename or "")).stem.strip()
    if not stem:
        return None
    safe_name = re.sub(r"[^0-9A-Za-z가-힣._-]+", "_", stem).strip("_")
    for candidate in (JP_SUBTITLE_DIR / "library" / stem,
                      JP_SUBTITLE_DIR / "library" / safe_name):
        if candidate.is_dir():
            return candidate
    code_match = re.search(r"[A-Za-z]{2,8}-\d{2,6}", stem)
    if code_match:
        code = code_match.group(0).lower()
        try:
            matches = [path for path in (JP_SUBTITLE_DIR / "library").iterdir()
                       if path.is_dir() and code in path.name.lower()]
        except OSError:
            matches = []
        if len(matches) == 1:
            return matches[0]
    return JP_SUBTITLE_DIR / "library" / safe_name


def _shift_alarm_subtitle_log_progress(job_id):
    if not job_id:
        return None
    try:
        matches = list(JP_SUBTITLE_LOG_DIR.glob(f"*_{job_id}.log"))
    except OSError:
        return None
    if not matches:
        return None
    try:
        content = matches[0].read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None
    best = None
    for percent, marker, stage in SHIFT_ALARM_SUBTITLE_PROGRESS_MARKERS:
        if marker in content and (best is None or percent > best[0]):
            best = (percent, stage)
    return best


def _shift_alarm_subtitle_production_steps(status):
    """자막 → 미연시 시나리오 → 이미지 생성의 실제 단계별 진행 상태."""
    content = ""
    job_id = status.get("job_id")
    if job_id:
        try:
            matches = list(JP_SUBTITLE_LOG_DIR.glob(f"*_{job_id}.log"))
            if matches:
                content = matches[0].read_text(encoding="utf-8", errors="ignore")
        except OSError:
            pass
    filename = status.get("filename") or ""
    book_dir = _jp_subtitle_book_dir(filename)
    scenario_ready = bool(book_dir and (book_dir / "dating_sim_scenario.json").is_file())
    scenario_logged_complete = "미연시 시나리오 생성 완료" in content
    scenario_progress = 100 if scenario_ready else _shift_alarm_scenario_progress(book_dir, content)
    scenario_retry_state = status.get("scenario_retry_state")
    scenario_running = (
        scenario_retry_state == "running"
        or ("미연시 시나리오 생성 중" in content and not scenario_ready
            and status.get("state") == "running" and _shift_alarm_subtitle_pipeline_alive())
    )
    scenario_failed = not scenario_ready and (
        scenario_retry_state == "failed"
        or scenario_logged_complete
        or ("미연시 시나리오 생성 중" in content and not scenario_running)
    )
    image_current = image_target = 0
    images_complete = "작품 이미지 생성·미연시 연결 완료" in content
    if book_dir:
        try:
            manifest = json.loads((book_dir / "dating_sim_images" / "manifest.json").read_text(encoding="utf-8"))
            image_target = int(manifest.get("selected_count") or 0)
            image_current = len(manifest.get("scenes") or [])
            images_complete = images_complete or bool(image_target and image_current >= image_target)
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            pass
    image_retry_state = status.get("image_retry_state")
    image_logged_failed = ("작품 이미지 일부가 아직 없습니다" in content
                           or "ComfyUI 생성이" in content
                           or "ComfyUI 서버" in content and "연결할 수 없습니다" in content)
    image_running = scenario_ready and not images_complete and (
        image_retry_state == "running"
        or (("작품 이미지 에이전트" in content or scenario_logged_complete)
            and status.get("state") == "running" and _shift_alarm_subtitle_pipeline_alive())
    )
    image_failed = scenario_ready and not images_complete and (
        image_retry_state == "failed" or (image_logged_failed and not image_running)
    )
    subtitle_complete = scenario_running or scenario_ready or "미연시 시나리오 생성 중" in content
    pipeline_state = status.get("state", "idle")
    return [
        {"key": "subtitle", "label": "자막·번역·EPUB", "state": "complete" if subtitle_complete or pipeline_state == "complete" else pipeline_state,
         "progress": 100 if subtitle_complete or pipeline_state == "complete" else min(100, int(status.get("progress") or 0))},
        {"key": "scenario", "label": "미연시 시나리오",
         "state": "complete" if scenario_ready else "running" if scenario_running else "failed" if scenario_failed else "pending",
         "progress": scenario_progress,
         "reason": status.get("scenario_retry_reason") or (
             "시나리오는 100% 생성됐지만 정리 단계가 결과 파일을 삭제했습니다. 재실행하면 앞으로는 보존됩니다."
             if scenario_logged_complete and not scenario_ready else
             _shift_alarm_scenario_failure_reason() if scenario_failed else None),
         "retryable": scenario_failed},
        {"key": "images", "label": "미연시 이미지",
         "state": "complete" if images_complete else "running" if image_running else "failed" if image_failed else "pending",
         "progress": 100 if images_complete else round(image_current / image_target * 100) if image_target else 10 if image_running else 0,
         "current": image_current, "total": image_target,
         "reason": status.get("image_retry_reason") or (_shift_alarm_image_failure_reason(content) if image_failed else None),
         "retryable": image_failed and scenario_ready},
    ]


def _shift_alarm_subtitle_write_status(status):
    SHIFT_ALARM_SUBTITLE_DIR.mkdir(parents=True, exist_ok=True)
    temporary = SHIFT_ALARM_SUBTITLE_STATUS_FILE.with_suffix(".tmp")
    temporary.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    os.chmod(temporary, 0o600)
    temporary.replace(SHIFT_ALARM_SUBTITLE_STATUS_FILE)


def _shift_alarm_notify_jp_subtitle_study_room(content):
    """shift_alarm.py의 _notify_jp_subtitle_study_room과 같은 트리거를 남긴다.
    이 서버 자체가 그 엔드포인트를 갖고 있으므로 루프백 HTTP 대신 함수를 직접
    호출한다(같은 프로세스 안에서 자기 자신에게 굳이 네트워크 왕복을 만들 필요가 없음)."""
    try:
        worker_reading_session_done(
            ReadingSessionDone(room_id=JP_SUBTITLE_STUDY_ROOM_ID, content=content),
            authorization=f"Bearer {WORKER_TOKEN}" if WORKER_TOKEN else None,
        )
    except HTTPException:
        pass


def _jp_subtitle_book_epub_exists(filename):
    """subtitle_pipeline_body.sh의 SAFE_BASE_NAME 새니타이즈(`sed -E
    's/[^0-9A-Za-z가-힣._-]+/_/g; s/^_+//; s/_+$//'`)를 그대로 재현해
    library/<제목>/ 폴더에 실제 .epub가 있는지 확인한다.

    ★ 2026-09-23: "자막추출 완료됬다는 표시있는데 실제 폴더내에는 epub 이
    없어" 신고 — 원인은 refine_translations.py가 AI 사용량 한도로 실패하면
    subtitle_pipeline_body.sh가 그 작품만 건너뛰고(continue) 최종 EPUB을
    library/로 옮기는 단계를 스킵하는데, 완료 판정은 오직 `.done` 마커
    파일(래퍼 스크립트가 배치 전체가 끝나면 개별 작품 성공 여부와 무관하게
    무조건 남김)만 보고 있었다는 것 — 실제 산출물 존재를 다시 확인한다."""
    if not filename:
        return False
    filename_no_ext = Path(filename).stem
    book_dir = _jp_subtitle_book_dir(filename)
    if not book_dir:
        return False
    try:
        if any(book_dir.glob("*.epub")):
            return True
        # 정상 파이프라인은 낭독판을 av완성작에 먼저 배포한다. 과거 정리
        # 코드가 library 원본을 지웠더라도 배포본이 있으면 EPUB 단계는
        # 성공이다. glob은 제목 속 []를 패턴으로 해석하므로 문자열 비교한다.
        return any(
            path.is_file() and path.name.startswith(filename_no_ext)
            and path.name.endswith("_낭독판.epub")
            for path in JP_COMPLETED_EPUB_DIR.iterdir()
        )
    except OSError:
        return False


def _shift_alarm_subtitle_status():
    try:
        status = json.loads(SHIFT_ALARM_SUBTITLE_STATUS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"state": "idle", "stage": "av4 폴더에서 영상을 선택해주세요"}
    # 이 기능 배포 전에 시작된 작업 상태에는 file_id가 없다. 파일명이 현재
    # av4 원본과 정확히 일치할 때만 안전하게 보완해, 진행 중이던 작업도 완료
    # 이력이 해당 카드에 남도록 한다.
    if not status.get("file_id") and status.get("filename"):
        legacy_path = SHIFT_ALARM_VIDEO_FILES / Path(status["filename"]).name
        if legacy_path.is_file() and legacy_path.parent == SHIFT_ALARM_VIDEO_FILES:
            status["file_id"] = _shift_alarm_av4_id(legacy_path)
            _shift_alarm_subtitle_write_status(status)
    if status.get("state") == "running":
        marker = Path(f"/tmp/_jp_subtitle_run_{status.get('run_id')}.done")
        if marker.exists():
            marker.unlink(missing_ok=True)
            shutil.rmtree(status.get("work_dir") or "", ignore_errors=True)
            if _jp_subtitle_book_epub_exists(status.get("filename")):
                status.update(state="complete", stage="자막·번역·후리가나·Notion·EPUB 반영 완료",
                              progress=100, completed_at=_now(), updated_at=_now())
                _shift_alarm_subtitle_write_status(status)
                _shift_alarm_notify_jp_subtitle_study_room(
                    "🔔 오늘 새 회차 자막 추출이 끝났습니다. "
                    "오늘 새로 처리한 회차의 줄거리와 재미있는 표현을 학습카드 위주로 소개해주세요."
                )
            else:
                status.update(
                    state="failed",
                    stage="자막·번역까지는 됐지만 EPUB이 생성되지 않았습니다 — "
                          "터미널 창 로그를 확인하세요(AI 사용량 한도로 중단됐을 수 있습니다)",
                    updated_at=_now(),
                )
                _shift_alarm_subtitle_write_status(status)
        else:
            progress_update = _shift_alarm_subtitle_log_progress(status.get("job_id"))
            if progress_update and progress_update[0] != status.get("progress"):
                status.update(progress=progress_update[0], stage=progress_update[1], updated_at=_now())
                _shift_alarm_subtitle_write_status(status)
            try:
                started = datetime.datetime.fromisoformat(status["created_at"])
            except (KeyError, ValueError):
                started = None
            # ★ 2026-09-24: "자막 추출이 웹앱 5%에서 멈춰있다 — 맥 껐다 켜서 다 멈춘 것
            # 같은데 다시 실행 버튼이 있으면 좋겠다" 신고 — 재부팅·창 닫기로 파이프라인이
            # 죽어도 완료 마커가 없으면 3시간 타임아웃까지 "진행 중"으로 남아 새 추출을
            # 막았다. 파이프라인 프로세스가 하나도 없고 시작한 지 2분이 지났으면
            # "중단됨"으로 바꿔 바로 다시 실행할 수 있게 한다.
            if (started and (datetime.datetime.now(datetime.timezone.utc) - started).total_seconds() > SHIFT_ALARM_SUBTITLE_STALE_GRACE_SECONDS
                    and not _shift_alarm_subtitle_pipeline_alive()):
                shutil.rmtree(status.get("work_dir") or "", ignore_errors=True)
                status.update(state="interrupted",
                              stage="Mac가 재시작되었거나 터미널 창이 닫혀 작업이 중단되었습니다 — 다시 실행할 수 있습니다",
                              updated_at=_now())
                _shift_alarm_subtitle_write_status(status)
            elif started and (datetime.datetime.now(datetime.timezone.utc) - started).total_seconds() > SHIFT_ALARM_SUBTITLE_TIMEOUT_SECONDS:
                status.update(state="failed", stage="시간이 오래 걸려 상태를 확인할 수 없습니다. Mac의 터미널 창을 직접 확인하세요")
                _shift_alarm_subtitle_write_status(status)
    # 과거 작업은 EPUB 배포 뒤 library 원본을 삭제해 완료 마커 확인이 늦으면
    # 전체 작업까지 시간 초과로 오판했다. av완성작에 실제 낭독판이 있으면
    # 자막·번역·EPUB 본 작업은 완료로 복구하고, 시나리오/이미지 문제는 아래
    # production_steps에서 별도 단계로 정확히 보여준다.
    if (status.get("state") in ("failed", "interrupted")
            and _jp_subtitle_book_epub_exists(status.get("filename"))):
        status.update(
            state="complete", progress=100,
            stage="자막·번역·후리가나·Notion·EPUB 반영 완료",
            completed_at=status.get("completed_at") or status.get("updated_at") or _now(),
            updated_at=_now(),
        )
        _shift_alarm_subtitle_write_status(status)
    # ★ 2026-09-15: "jufe 194 는 이미 자막 추출되어있는데 버젓이 자막추출
    # 버튼이 살아있네" 신고의 실제 원인 — 위 running→complete/failed 전환은
    # 상태 파일이 "running"일 때 딱 한 번만 지나가는 경계(edge)라, 그 순간에
    # 하필 서버가 다른 버그로 죽어 있었거나 이 동기화 코드가 아직 배포되기
    # 전이었다면 완료 이력이 영원히 DB에 안 남는다(실측: HODV-21738은
    # 상태 파일은 complete인데 DB엔 running·5%로 멈춰 있었음). 매 조회마다
    # 현재 상태를 무조건 다시 써서(level-triggered) 어느 경계를 놓쳤어도
    # 다음 폴링에서 저절로 맞춰지게 한다.
    if status.get("file_id") and status.get("filename") and status.get("state") in ("running", "complete", "failed", "interrupted"):
        _shift_alarm_update_processing(
            status["file_id"], status["filename"], subtitle_state=status["state"],
            subtitle_progress=status.get("progress") or 0, subtitle_stage=status.get("stage"),
            subtitle_completed_at=status.get("completed_at"),
        )
    if status.get("scenario_retry_state") == "running":
        safe_name = re.sub(
            r"[^0-9A-Za-z가-힣._-]+", "_", Path(status.get("filename") or "").stem
        ).strip("_")
        scenario_path = JP_SUBTITLE_DIR / "library" / safe_name / "dating_sim_scenario.json"
        if safe_name and scenario_path.is_file():
            status.update(
                scenario_retry_state="complete", scenario_retry_reason=None,
                scenario_retry_completed_at=_now(), updated_at=_now(),
            )
            _shift_alarm_subtitle_write_status(status)
    if status.get("image_retry_state") == "running":
        safe_name = re.sub(
            r"[^0-9A-Za-z가-힣._-]+", "_", Path(status.get("filename") or "").stem
        ).strip("_")
        image_dir = JP_SUBTITLE_DIR / "library" / safe_name / "dating_sim_images"
        manifest_path = image_dir / "manifest.json"
        image_complete = False
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            target = int(manifest.get("selected_count") or 0)
            current = len(manifest.get("scenes") or [])
            image_complete = bool(target and current >= target and (image_dir / "portrait.png").is_file())
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            pass
        if image_complete:
            status.update(
                image_retry_state="complete", image_retry_reason=None,
                image_retry_completed_at=_now(), updated_at=_now(),
            )
            _shift_alarm_subtitle_write_status(status)
        elif not _process_is_alive(status.get("image_retry_pid")):
            try:
                retry_content = Path(status.get("image_retry_log") or "").read_text(
                    encoding="utf-8", errors="ignore")
            except OSError:
                retry_content = ""
            status.update(
                image_retry_state="failed",
                image_retry_reason=_shift_alarm_image_failure_reason(retry_content),
                updated_at=_now(),
            )
            _shift_alarm_subtitle_write_status(status)
        elif not _process_is_alive(status.get("scenario_retry_pid")):
            reason = _shift_alarm_scenario_failure_reason(status.get("scenario_retry_log"))
            status.update(
                scenario_retry_state="failed", scenario_retry_reason=reason,
                updated_at=_now(),
            )
            _shift_alarm_subtitle_write_status(status)
    status["production_steps"] = _shift_alarm_subtitle_production_steps(status)
    return status


def _shift_alarm_save_now_playing(playlist, playing=True):
    try:
        temporary = str(SHIFT_ALARM_NOW_PLAYING_FILE) + ".tmp"
        with open(temporary, "w", encoding="utf-8") as f:
            json.dump({"playlist": playlist, "playing": bool(playing)}, f)
        os.replace(temporary, SHIFT_ALARM_NOW_PLAYING_FILE)
    except OSError:
        pass


def _shift_alarm_load_now_playing():
    try:
        with open(SHIFT_ALARM_NOW_PLAYING_FILE, encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except (OSError, ValueError, TypeError, AttributeError):
        return {}


def _shift_alarm_playlist_from_visible_track():
    """상태 helper가 마지막으로 남긴 현재 곡 제목을 실제 폴더와 대조한다.

    알람 스크립트가 예전 형식의 상태 파일을 남겼을 때도 좋아요/클래식을
    바로잡기 위한 보정이며, 한글 조합형 차이는 NFC 정규화로 흡수한다.
    """
    try:
        visible = unicodedata.normalize(
            "NFC", SHIFT_ALARM_ELMEDIA_STATUS_FILE.read_text(encoding="utf-8", errors="ignore")
        ).casefold()
    except OSError:
        return None
    for playlist, folder in (("sleep", SHIFT_ALARM_SLEEP_FOLDER),
                             ("classical", SHIFT_ALARM_CLASSIC_FOLDER),
                             ("favorites", SHIFT_ALARM_FAVORITES_FOLDER)):
        for track in _shift_alarm_list_audio_tracks(folder):
            name = unicodedata.normalize("NFC", Path(track).name).casefold()
            if name and name in visible:
                return playlist
    return None


def _validate_stream_download_url(value):
    value = str(value or "").strip()
    if len(value) > 2048 or any(char in value for char in "\r\n\t"):
        raise HTTPException(status_code=422, detail="주소 형식이 올바르지 않습니다")
    parsed = urllib.parse.urlsplit(value)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise HTTPException(status_code=422, detail="공개 HTTPS 영상 주소만 사용할 수 있습니다")
    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(parsed.hostname, parsed.port or 443)}
    except socket.gaierror as exc:
        raise HTTPException(status_code=422, detail="사이트 주소를 찾을 수 없습니다") from exc
    if any(not ipaddress.ip_address(address).is_global for address in addresses):
        raise HTTPException(status_code=422, detail="내부망 또는 로컬 주소는 사용할 수 없습니다")
    return value


def _shift_alarm_video_status():
    try:
        status = json.loads(SHIFT_ALARM_VIDEO_STATUS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"state": "idle", "stage": "다운로드할 영상 주소를 입력해주세요", "progress": 0}
    if status.get("state") in {"running", "syncing"}:
        try:
            os.kill(int(status.get("pid", 0)), 0)
        except (OSError, TypeError, ValueError):
            status.update(state="failed", stage="서버 재시작 또는 작업 중단으로 다운로드가 끝나지 않았습니다", progress=0)
    if status.get("state") == "running" and not status.get("downloaded_bytes"):
        job_dir = SHIFT_ALARM_VIDEO_DIR / "staging" / str(status.get("job_id") or "")
        try:
            status["downloaded_bytes"] = sum(
                path.stat().st_size for path in job_dir.iterdir() if path.is_file()
            )
        except OSError:
            pass
    return {key: status.get(key) for key in (
        "job_id", "state", "stage", "progress", "filename", "destination",
        "created_at", "updated_at", "completed_at", "downloaded_bytes", "total_bytes",
    )}


def _shift_alarm_video_db():
    SHIFT_ALARM_VIDEO_DIR.mkdir(parents=True, exist_ok=True)
    os.chmod(SHIFT_ALARM_VIDEO_DIR, 0o700)
    conn = sqlite3.connect(SHIFT_ALARM_VIDEO_DB)
    os.chmod(SHIFT_ALARM_VIDEO_DB, 0o600)
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS video_downloads (
            job_id TEXT PRIMARY KEY, owner_username TEXT NOT NULL,
            filename TEXT NOT NULL, file_path TEXT NOT NULL, size_bytes INTEGER NOT NULL,
            created_at TEXT NOT NULL, completed_at TEXT NOT NULL, expires_at TEXT NOT NULL,
            downloaded_at TEXT, icloud_sent_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS video_transfers (
            file_id TEXT PRIMARY KEY, transfer_id TEXT NOT NULL, filename TEXT NOT NULL,
            state TEXT NOT NULL, sent_bytes INTEGER NOT NULL, total_bytes INTEGER NOT NULL,
            started_at TEXT NOT NULL, updated_at TEXT NOT NULL, completed_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS video_processing_history (
            file_id TEXT PRIMARY KEY, filename TEXT NOT NULL,
            subtitle_state TEXT, subtitle_progress REAL, subtitle_stage TEXT,
            subtitle_started_at TEXT, subtitle_completed_at TEXT,
            safari_completed_at TEXT, photo_shortcut_at TEXT, updated_at TEXT NOT NULL
        )
    """)
    # ★ 2026-09-15: "영상가져오기가 다운로드 파일이 하나도 안보이는데 왜
    # 그렇지" 신고의 실제 원인 — safari_completed_at 컬럼이 CREATE TABLE에
    # 추가되기 전에 이미 video_processing_history 테이블이 만들어져 있던
    # 환경에서는 `IF NOT EXISTS`가 조용히 아무것도 안 해서 그 컬럼이
    # 영원히 안 생긴다. shift_alarm_video_download_status()가 SELECT * 결과를
    # dict(row)로 바꿔 history["safari_completed_at"]를 그대로 읽다가
    # KeyError로 API 전체가 500이 나 목록이 통째로 비어 보였다(실측 확인).
    existing_columns = {row["name"] for row in conn.execute("PRAGMA table_info(video_processing_history)")}
    for column in ("safari_completed_at", "photo_shortcut_at"):
        if column not in existing_columns:
            conn.execute(f"ALTER TABLE video_processing_history ADD COLUMN {column} TEXT")
    return conn


def _shift_alarm_processing_history():
    with _shift_alarm_video_db() as conn:
        rows = conn.execute("SELECT * FROM video_processing_history").fetchall()
    return {row["file_id"]: dict(row) for row in rows}


def _shift_alarm_update_processing(file_id, filename, **changes):
    allowed = {
        "subtitle_state", "subtitle_progress", "subtitle_stage",
        "subtitle_started_at", "subtitle_completed_at", "safari_completed_at", "photo_shortcut_at",
    }
    values = {key: value for key, value in changes.items() if key in allowed}
    timestamp = _now()
    with _shift_alarm_video_db() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO video_processing_history "
            "(file_id,filename,updated_at) VALUES (?,?,?)",
            (file_id, filename, timestamp),
        )
        if values:
            assignments = ",".join(f"{key}=?" for key in values)
            conn.execute(
                f"UPDATE video_processing_history SET filename=?,{assignments},updated_at=? WHERE file_id=?",
                (filename, *values.values(), timestamp, file_id),
            )


def _shift_alarm_cleanup_videos(conn):
    # 과거에는 완료 24시간 뒤 원본을 자동 삭제했다. 사용자가 직접 삭제할
    # 때까지 av4에 보관하도록 바뀌었으므로 기존 행도 영구 보관 값으로 승격한다.
    conn.execute(
        "UPDATE video_downloads SET expires_at=? WHERE expires_at<>?",
        ("9999-12-31T23:59:59+00:00", "9999-12-31T23:59:59+00:00"),
    )
    conn.commit()


def _shift_alarm_owned_video(job_id, username):
    conn = _shift_alarm_video_db()
    _shift_alarm_cleanup_videos(conn)
    row = conn.execute(
        "SELECT * FROM video_downloads WHERE job_id=? AND owner_username=?", (job_id, username)
    ).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="영상이 없거나 직접 삭제되었습니다")
    path = Path(row["file_path"])
    if path.parent != SHIFT_ALARM_VIDEO_FILES or not path.is_file():
        raise HTTPException(status_code=404, detail="영상 파일을 찾을 수 없습니다")
    return row, path


def _shift_alarm_av4_id(path):
    return hashlib.sha256(path.name.encode("utf-8")).hexdigest()[:24]


def _shift_alarm_ios_filename(path):
    code = re.search(r"(?i)(?<![A-Z0-9])([A-Z]{2,12}-\d{2,8})(?![A-Z0-9])", path.stem)
    if code:
        return f"{code.group(1).upper()}.mp4"
    return f"video-{_shift_alarm_av4_id(path)[:10]}.mp4"


def _shift_alarm_av4_files():
    try:
        paths = [path for path in SHIFT_ALARM_VIDEO_FILES.iterdir()
                 if path.is_file() and path.suffix.lower() == ".mp4"]
    except OSError:
        return []
    return sorted(paths, key=lambda path: path.stat().st_mtime, reverse=True)


def _shift_alarm_av4_revision(paths=None):
    """Finder와 웹 목록이 같은 실제 디렉터리 세대를 보고 있는지 식별한다."""
    paths = paths if paths is not None else _shift_alarm_av4_files()
    payload = "\n".join(
        f"{path.name}:{path.stat().st_size}:{path.stat().st_mtime_ns}" for path in paths
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _shift_alarm_av4_file(file_id):
    if not re.fullmatch(r"[a-f0-9]{24}", file_id):
        raise HTTPException(status_code=404, detail="영상 파일을 찾을 수 없습니다")
    for path in _shift_alarm_av4_files():
        if secrets.compare_digest(_shift_alarm_av4_id(path), file_id):
            return path
    raise HTTPException(status_code=404, detail="영상 파일을 찾을 수 없습니다")


def _shift_alarm_transfer_start(file_id, path, start, total):
    transfer_id = uuid.uuid4().hex
    timestamp = _now()
    with _shift_alarm_video_db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO video_transfers "
            "(file_id,transfer_id,filename,state,sent_bytes,total_bytes,started_at,updated_at,completed_at) "
            "VALUES (?,?,?,?,?,?,?,?,NULL)",
            (file_id, transfer_id, path.name, "downloading", start, total, timestamp, timestamp),
        )
    return transfer_id


def _shift_alarm_transfer_update(file_id, transfer_id, state, sent_bytes, completed=False):
    timestamp = _now()
    with _shift_alarm_video_db() as conn:
        conn.execute(
            "UPDATE video_transfers SET state=?,sent_bytes=?,updated_at=?,completed_at=? "
            "WHERE file_id=? AND transfer_id=?",
            (state, sent_bytes, timestamp, timestamp if completed else None, file_id, transfer_id),
        )


def _shift_alarm_transfer_states():
    with _shift_alarm_video_db() as conn:
        rows = conn.execute(
            "SELECT file_id,state,sent_bytes,total_bytes,started_at,updated_at,completed_at "
            "FROM video_transfers"
        ).fetchall()
    return {row["file_id"]: dict(row) for row in rows}


def _shift_alarm_notify_transfer_complete(username, filename):
    """Safari 전송 완료를 소유자의 모든 유효한 웹푸시 구독에 알린다."""
    conn = get_conn()
    try:
        _send_web_push_to_user(
            conn, username, "iPhone 영상 다운로드 완료",
            f"{_shift_alarm_ios_filename(Path(filename))} 전송이 완료됐습니다. Safari 다운로드 목록을 확인하세요.",
            "/shift-alarm/",
        )
        conn.commit()
    finally:
        conn.close()


def _shift_alarm_stream_file(path, range_header, request, file_id=None, username=None):
    size = path.stat().st_size
    start, end, status_code = 0, size - 1, 200
    if range_header:
        match = re.fullmatch(r"bytes=(\d*)-(\d*)", range_header.strip())
        if not match or (not match.group(1) and not match.group(2)):
            raise HTTPException(status_code=416, detail="지원하지 않는 구간 요청입니다")
        if match.group(1):
            start = int(match.group(1))
            end = int(match.group(2) or end)
        else:
            length = int(match.group(2))
            start = max(0, size - length)
        end = min(end, size - 1)
        if start > end or start >= size:
            raise HTTPException(status_code=416, detail="파일 범위를 벗어났습니다")
        status_code = 206
    length = end - start + 1
    file_id = file_id or _shift_alarm_av4_id(path)
    transfer_id = _shift_alarm_transfer_start(file_id, path, start, size)

    async def chunks():
        sent = start
        completed = False
        last_report = start
        try:
            with path.open("rb") as source:
                source.seek(start)
                remaining = length
                while remaining:
                    # ★ 2026-09-14: "백그라운드로 넘어가면 몇 분 뒤 다운로드
                    # 실패가 뜨는데 앱에는 성공으로 뜬다" — 클라이언트가 이미
                    # 연결을 끊었어도 이 읽기 루프는 그걸 모르고 파일을 끝까지
                    # 읽어 completed=True로 잘못 보고하고 있었다(서버 쪽
                    # write는 OS 소켓 버퍼에 성공적으로 밀어넣어지는 것과
                    # 실제로 클라이언트가 받는 것은 별개). 매 청크마다 연결
                    # 상태를 확인해서 끊겼으면 즉시 멈추고 interrupted로
                    # 정직하게 기록한다.
                    if await request.is_disconnected():
                        break
                    data = source.read(min(1024 * 1024, remaining))
                    if not data:
                        break
                    remaining -= len(data)
                    sent += len(data)
                    if sent - last_report >= 8 * 1024 * 1024:
                        _shift_alarm_transfer_update(file_id, transfer_id, "downloading", sent)
                        last_report = sent
                    yield data
                completed = remaining == 0 and end == size - 1
        finally:
            _shift_alarm_transfer_update(
                file_id, transfer_id, "complete" if completed else "interrupted", sent, completed
            )
            if completed and username:
                _shift_alarm_update_processing(
                    file_id, path.name, safari_completed_at=_now(),
                )
                threading.Thread(
                    target=_shift_alarm_notify_transfer_complete,
                    args=(username, path.name), daemon=True,
                ).start()

    headers = {
        "Accept-Ranges": "bytes", "Content-Length": str(length),
        "Content-Disposition": f'attachment; filename="{_shift_alarm_ios_filename(path)}"',
        "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff",
    }
    if status_code == 206:
        headers["Content-Range"] = f"bytes {start}-{end}/{size}"
    return StreamingResponse(
        chunks(), status_code=status_code, media_type="application/octet-stream", headers=headers
    )


def _shift_alarm_collect_all_bookmark_urls(node):
    urls = []
    if node.get("type") == "url":
        u = node.get("url")
        if u:
            urls.append(u)
    for child in node.get("children", []):
        urls.extend(_shift_alarm_collect_all_bookmark_urls(child))
    return urls


def _shift_alarm_find_bookmark_folder(node, target_name):
    if node.get("type") == "folder":
        if node.get("name") == target_name:
            return node
        for child in node.get("children", []):
            found = _shift_alarm_find_bookmark_folder(child, target_name)
            if found:
                return found
    return None


def _shift_alarm_load_random_bookmark_history(folder_name):
    try:
        with open(SHIFT_ALARM_RANDOM_BOOKMARK_HISTORY_FILE, encoding="utf-8") as file:
            data = json.load(file)
        history = data.get(folder_name, [])
        return history if isinstance(history, list) else []
    except (OSError, ValueError, TypeError):
        return []


def _shift_alarm_save_random_bookmark_history(folder_name, visited_urls):
    data = {}
    try:
        with open(SHIFT_ALARM_RANDOM_BOOKMARK_HISTORY_FILE, encoding="utf-8") as file:
            loaded = json.load(file)
        if isinstance(loaded, dict):
            data = loaded
    except (OSError, ValueError, TypeError):
        pass
    data[folder_name] = visited_urls
    temp_path = f"{SHIFT_ALARM_RANDOM_BOOKMARK_HISTORY_FILE}.tmp"
    with open(temp_path, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)
    os.replace(temp_path, SHIFT_ALARM_RANDOM_BOOKMARK_HISTORY_FILE)


SHIFT_ALARM_WEB_BOOKMARKS_FILE = os.path.expanduser("~/.shift_alarm_web_bookmarks.json")
SHIFT_ALARM_LINK_SETTINGS_FILE = Path(os.path.expanduser("~/.tulpachat/shift_alarm_link_settings.json"))
_shift_alarm_link_settings_lock = threading.Lock()
_KR_MIRROR_HOST_RE = re.compile(r"^kr(?P<number>\d+)\.topgirl\.co$", re.IGNORECASE)


def _shift_alarm_valid_bookmark_url(url):
    parsed = urllib.parse.urlsplit(url or "")
    return parsed.scheme in {"http", "https"} and bool(parsed.hostname) and len(url) <= 2048


def _shift_alarm_load_web_bookmarks():
    """웹앱이 직접 관리하는 추천 사이트 목록.

    ★ 2026-09-24: "웹앱에서 내가 지정한 링크를 웹앱 북마크목록으로 관리하게 하자" —
    Chrome Bookmarks 파일은 macOS 권한(TCC)으로 막혀 읽을 수 없어서, Chrome과
    분리해 웹앱 자체 목록(~/.shift_alarm_web_bookmarks.json)을 쓴다. 파일이 없으면
    이전에 내보낸 Chrome 天 폴더 목록(~/.shift_alarm_bookmark_urls.json)으로 한 번 채운다."""
    try:
        with open(SHIFT_ALARM_WEB_BOOKMARKS_FILE, encoding="utf-8") as file:
            urls = json.load(file).get("urls", [])
    except FileNotFoundError:
        try:
            with open(SHIFT_ALARM_BOOKMARK_URLS_EXPORT_FILE, encoding="utf-8") as file:
                urls = json.load(file).get("urls", [])
        except (OSError, ValueError):
            urls = []
        urls = [url for url in urls if _shift_alarm_valid_bookmark_url(url)]
        if urls:
            _shift_alarm_save_web_bookmarks(urls)
    except (OSError, ValueError):
        return []
    return list(dict.fromkeys(url for url in urls if _shift_alarm_valid_bookmark_url(url)))


def _shift_alarm_save_web_bookmarks(urls):
    temp_path = f"{SHIFT_ALARM_WEB_BOOKMARKS_FILE}.tmp"
    with open(temp_path, "w", encoding="utf-8") as file:
        json.dump({"urls": list(dict.fromkeys(urls))}, file, ensure_ascii=False, indent=1)
    os.replace(temp_path, SHIFT_ALARM_WEB_BOOKMARKS_FILE)


def _replace_kr_mirror_number(url: str, number: int) -> tuple[str, bool]:
    """topgirl의 krNN 호스트만 바꾸고 경로·검색어는 그대로 보존한다."""
    try:
        parsed = urllib.parse.urlsplit(str(url or ""))
    except ValueError:
        return str(url or ""), False
    host = parsed.hostname or ""
    if not _KR_MIRROR_HOST_RE.fullmatch(host):
        return str(url or ""), False
    new_host = f"kr{number}.topgirl.co"
    if parsed.port:
        new_host = f"{new_host}:{parsed.port}"
    updated = urllib.parse.urlunsplit(
        (parsed.scheme, new_host, parsed.path, parsed.query, parsed.fragment)
    )
    return updated, updated != url


def _load_kr_mirror_number() -> int:
    try:
        data = json.loads(SHIFT_ALARM_LINK_SETTINGS_FILE.read_text(encoding="utf-8"))
        number = int(data.get("kr_number"))
        if 1 <= number <= 999:
            return number
    except (OSError, ValueError, TypeError):
        pass
    for url in _shift_alarm_load_web_bookmarks():
        try:
            match = _KR_MIRROR_HOST_RE.fullmatch(urllib.parse.urlsplit(url).hostname or "")
        except ValueError:
            match = None
        if match:
            return int(match.group("number"))
    return 47


def _save_kr_mirror_number(number: int) -> None:
    SHIFT_ALARM_LINK_SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    target = SHIFT_ALARM_LINK_SETTINGS_FILE
    temporary = target.with_suffix(".tmp")
    temporary.write_text(json.dumps({"kr_number": number}, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, target)


def _update_source_video_mirrors(number: int) -> tuple[int, int]:
    changed_files = 0
    changed_urls = 0
    library_root = JP_SUBTITLE_DIR / "library"
    if not library_root.is_dir():
        return changed_files, changed_urls
    for target in library_root.rglob(SOURCE_VIDEO_METADATA):
        if not target.is_file() or target.is_symlink():
            continue
        try:
            data = json.loads(target.read_text(encoding="utf-8"))
            old_url = str(data.get("url") or "")
            new_url, changed = _replace_kr_mirror_number(old_url, number)
            if not changed:
                continue
            data["url"] = new_url
            temporary = target.with_suffix(".json.tmp")
            temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            os.replace(temporary, target)
            changed_files += 1
            changed_urls += 1
        except (OSError, ValueError, TypeError):
            continue
    return changed_files, changed_urls


def _shift_alarm_pick_random_bookmarks(n=3, folder_name=SHIFT_ALARM_RANDOM_BOOKMARK_FOLDER):
    urls = _shift_alarm_load_web_bookmarks()
    if not urls:
        return []
    try:
        current_urls = set(urls)
        visited = [
            url for url in dict.fromkeys(_shift_alarm_load_random_bookmark_history(folder_name))
            if url in current_urls
        ]
        unvisited = [url for url in urls if url not in set(visited)]
        if not unvisited:
            visited = []
            unvisited = urls
        selected = random.sample(unvisited, min(n, len(unvisited)))
        _shift_alarm_save_random_bookmark_history(folder_name, visited + selected)
        return selected
    except (OSError, ValueError, TypeError):
        return []




def _shift_alarm_list_audio_tracks(folder):
    tracks = []
    for root, _dirs, files in os.walk(folder):
        for name in files:
            if os.path.splitext(name)[1].lower() in SHIFT_ALARM_ELMEDIA_AUDIO_EXTENSIONS:
                tracks.append(os.path.abspath(os.path.join(root, name)))
    tracks.sort(key=lambda path: path.casefold())
    return tracks


def _shift_alarm_elmedia_running():
    result = subprocess.run(
        ["/usr/bin/pgrep", "-x", "Elmedia Video Player"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
    )
    return result.returncode == 0


SHIFT_ALARM_ELMEDIA_STATUS_HELPER = REPO_ROOT / "shift_alarm" / "ElmediaStatusHelper.app"
SHIFT_ALARM_ELMEDIA_STATUS_FILE = Path(os.path.expanduser("~/.shift_alarm_elmedia_status.txt"))


def _shift_alarm_elmedia_playing():
    """Elmedia 창 존재가 아니라 실제 재생 상태를 helper의 UI 신호로 확인한다."""
    if not _shift_alarm_elmedia_running() or not SHIFT_ALARM_ELMEDIA_STATUS_HELPER.exists():
        return False
    SHIFT_ALARM_ELMEDIA_STATUS_FILE.unlink(missing_ok=True)
    try:
        subprocess.Popen(
            ["/usr/bin/open", "-na", str(SHIFT_ALARM_ELMEDIA_STATUS_HELPER)],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except OSError:
        return False
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if SHIFT_ALARM_ELMEDIA_STATUS_FILE.is_file():
            time.sleep(0.1)
            try:
                return "elapsed time" in SHIFT_ALARM_ELMEDIA_STATUS_FILE.read_text(
                    encoding="utf-8", errors="ignore"
                ).lower()
            except OSError:
                return False
        time.sleep(0.1)
    return False


# ★ 2026-09-14: "재생중일때 일시정지랑 다음곡 이전곡 넘어가는 버튼도있으면
# 좋겠어" — Elmedia는 샌드박스 빌드라 표준 AppleScript pause 동사가 없어서
# (shift_alarm.py의 ★2026-08-29 항목과 같은 제약) 시스템 전체 미디어 키
# (NX_KEYTYPE_PLAY/NEXT/PREVIOUS)를 눌러야 한다. 이 키 전송(Quartz.
# CGEventPost)은 호출 프로세스에 macOS Accessibility 권한이 필요한데, 그
# 권한은 이 서버의 venv 인터프리터가 아니라 shift_alarm.py가 쓰는
# `/opt/anaconda3/bin/python3` 신원에 이미 걸려 있을 가능성이 높다. 그래서
# 이 서버 프로세스가 직접 Quartz를 호출하지 않고, 그 인터프리터로 별도
# 스크립트(`shift_alarm/send_media_key.py`)를 서브프로세스 실행해 신원을
# 빌려 쓴다 — 서버 venv에 pyobjc를 새로 설치해 별도 Accessibility 승인을
# 또 요구하지 않기 위해서다.
SHIFT_ALARM_MEDIA_KEY_PYTHON = "/opt/anaconda3/bin/python3"
SHIFT_ALARM_MEDIA_KEY_SCRIPT = str(REPO_ROOT / "shift_alarm" / "send_media_key.py")


def _shift_alarm_send_media_key(action):
    subprocess.run(
        [SHIFT_ALARM_MEDIA_KEY_PYTHON, SHIFT_ALARM_MEDIA_KEY_SCRIPT, action],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10, check=False,
    )


SHIFT_ALARM_ELMEDIA_DB_RESET_TIMEOUT_SECONDS = 5


def _shift_alarm_reset_elmedia_playlist():
    subprocess.run(
        ["/usr/bin/killall", "Elmedia Video Player"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
    )
    for _ in range(20):
        if not _shift_alarm_elmedia_running():
            break
        time.sleep(0.25)
    else:
        subprocess.run(
            ["/usr/bin/killall", "-9", "Elmedia Video Player"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
        )
        for _ in range(8):
            if not _shift_alarm_elmedia_running():
                break
            time.sleep(0.25)
    if _shift_alarm_elmedia_running():
        return False
    if os.path.exists(SHIFT_ALARM_ELMEDIA_PLAYLIST_DB):
        # ★ 2026-09-14: "좋아요/클래식 재생 버튼을 눌러도 실행이 안 된다"는
        # 재신고 — `sample` 프로파일러로 실제 요청을 떠 있는 채로 잡아보니
        # 프로세스 내(in-process) `sqlite3.connect(...)`가 SQLite의 락 대기가
        # 아니라 그보다 훨씬 아래, 순수 `open()` 시스템 콜 자체에서 수천
        # 샘플째 멈춰 있었다 — Elmedia의 샌드박스 컨테이너
        # (~/Library/Containers/com.eltima.elmedia6.mas/...)에 대한 TCC
        # 동의 절차가 GUI 세션이 없는 launchd 백그라운드 프로세스에서는 응답
        # 받을 사용자가 없어 영원히 멈춰버린 것으로 보인다(Python의
        # sqlite3.connect(timeout=N)은 SQLite 자체 락-재시도 시간만 제한할
        # 뿐, 그 아래 open() 콜 자체가 멈추는 건 절대 못 막는다). 같은
        # 인터프리터로 인터랙티브 셸에서 직접 실행하면 항상 즉시 성공해
        # 재현이 어려웠다 — 오직 실제 launchd 서버 프로세스에서만 걸렸다.
        # 근본 원인(그 TCC 동의 자체)은 고치지 못했지만, 최소한 요청이
        # 영원히 멈추지 않도록 이 단계를 별도 서브프로세스로 빼고
        # subprocess.run(timeout=...)으로 강제 종료 가능하게 만들었다 —
        # 큐 정리에 실패해도(타임아웃) 재생 자체는 계속 진행한다.
        try:
            subprocess.run(
                ["/usr/bin/sqlite3", SHIFT_ALARM_ELMEDIA_PLAYLIST_DB,
                 "DELETE FROM item_order; DELETE FROM playlist_items;"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=SHIFT_ALARM_ELMEDIA_DB_RESET_TIMEOUT_SECONDS, check=False,
            )
        except subprocess.TimeoutExpired:
            pass
    return True


def _shift_alarm_play_folder(folder):
    if not os.path.isdir(folder):
        return False, "폴더를 찾을 수 없습니다."
    try:
        tracks = _shift_alarm_list_audio_tracks(folder)
        if not tracks:
            return False, "재생 가능한 음원 파일이 없습니다."
        reset_ok = _shift_alarm_reset_elmedia_playlist()
        subprocess.Popen(["open", "-a", "Elmedia Video Player", *tracks])
        normalized_folder = os.path.abspath(folder)
        if normalized_folder == os.path.abspath(SHIFT_ALARM_SLEEP_FOLDER):
            playlist_mode = "sleep"
        elif normalized_folder == os.path.abspath(SHIFT_ALARM_CLASSIC_FOLDER):
            playlist_mode = "classical"
        else:
            playlist_mode = "favorites"
        _shift_alarm_save_now_playing(playlist_mode)
        if not reset_ok:
            return False, "Elmedia가 응답이 없어 기존 재생목록을 비우지 못했습니다 — 새 음원이 기존 큐와 섞여 재생될 수 있습니다."
        return True, f"{len(tracks)}곡을 새로 열었습니다."
    except OSError as exc:
        return False, str(exc)


def _shift_alarm_get_volume():
    result = subprocess.run(
        ["/usr/bin/osascript", "-e", "output volume of (get volume settings)"],
        capture_output=True, text=True, timeout=10, check=False,
    )
    try:
        return int(result.stdout.strip())
    except ValueError:
        return None


def _shift_alarm_set_volume(percent):
    percent = max(0, min(100, int(percent)))
    subprocess.run(
        ["/usr/bin/osascript", "-e", f"set volume output volume {percent}"],
        timeout=10, check=False,
    )
    return percent


def _shift_alarm_hue_grouped_light():
    try:
        config = json.loads(SHIFT_ALARM_HUE_CONFIG_FILE.read_text(encoding="utf-8"))
        ip, app_key = config["ip"], config["app_key"]
    except (FileNotFoundError, OSError, KeyError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=503, detail="Hue 연결 정보가 없습니다") from exc
    context = ssl._create_unverified_context()
    headers = {"hue-application-key": app_key}
    base = f"https://{ip}/clip/v2/resource"
    try:
        request = urllib.request.Request(f"{base}/room", headers=headers)
        with urllib.request.urlopen(request, timeout=10, context=context) as response:
            rooms = json.load(response).get("data", [])
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=503, detail="Hue Bridge에 연결하지 못했습니다") from exc
    room = next((item for item in rooms if item.get("metadata", {}).get("name") == SHIFT_ALARM_HUE_ROOM_NAME), None)
    grouped_id = next((service.get("rid") for service in (room or {}).get("services", []) if service.get("rtype") == "grouped_light"), None)
    if not grouped_id:
        raise HTTPException(status_code=404, detail=f"Hue {SHIFT_ALARM_HUE_ROOM_NAME} 조명을 찾지 못했습니다")
    return f"{base}/grouped_light/{grouped_id}", headers, context


def _shift_alarm_hue_state():
    url, headers, context = _shift_alarm_hue_grouped_light()
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=10, context=context) as response:
            payload = json.load(response)
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=503, detail="조명 상태를 확인하지 못했습니다") from exc
    if payload.get("errors") or not payload.get("data"):
        raise HTTPException(status_code=503, detail="조명 상태를 확인하지 못했습니다")
    return bool(payload["data"][0].get("on", {}).get("on"))


def _shift_alarm_set_hue_power(on):
    url, headers, context = _shift_alarm_hue_grouped_light()
    request = urllib.request.Request(url, data=json.dumps({"on": {"on": bool(on)}}).encode("utf-8"), method="PUT", headers={**headers, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=10, context=context) as response:
            payload = json.load(response)
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=503, detail="조명 전원을 변경하지 못했습니다") from exc
    if payload.get("errors"):
        raise HTTPException(status_code=503, detail="조명 전원을 변경하지 못했습니다")
    return bool(on)


def _read_shift_alarm_status():
    saw_file = False
    # 웹 서버에서는 Shift Alarm이 iCloud로 복사하기 직전에 함께 갱신하는
    # 로컬 스테이징 파일을 먼저 읽는다. macOS가 iCloud 파일을 내려받거나
    # TCC 접근을 판정하는 동안 read_text()가 수 초간 멈추는 경우가 있으며,
    # 그러면 상태와 Shift Quest API가 함께 비어 보인다. 두 파일의 내용은
    # 같은 쓰기 작업에서 만들어지므로 로컬본을 우선하고 없을 때만 iCloud를
    # 최종 복구 경로로 사용한다.
    candidates = (
        ("local", SHIFT_ALARM_STATUS_FALLBACK_FILE),
        ("cache", SHIFT_ALARM_STATUS_CACHE_FILE),
        ("icloud", SHIFT_ALARM_STATUS_FILE),
    )
    for source, status_file in candidates:
        try:
            payload = json.loads(status_file.read_text(encoding="utf-8"))
            saw_file = True
        except FileNotFoundError:
            continue
        except (OSError, json.JSONDecodeError):
            saw_file = True
            continue
        if isinstance(payload, dict):
            # 마지막 정상본은 별도 파일에 원자적으로 보존한다. 다음 갱신 파일이
            # 손상되어도 화면 전체가 사라지지 않고 직전 상태를 표시할 수 있다.
            if source != "cache":
                try:
                    SHIFT_ALARM_STATUS_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
                    temporary = SHIFT_ALARM_STATUS_CACHE_FILE.with_suffix(".tmp")
                    temporary.write_text(
                        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
                    )
                    temporary.replace(SHIFT_ALARM_STATUS_CACHE_FILE)
                except OSError:
                    pass
            result = dict(payload)
            age_seconds = None
            try:
                updated_at = datetime.datetime.fromisoformat(str(payload.get("updated_at")))
                if updated_at.tzinfo is not None:
                    updated_at = updated_at.astimezone().replace(tzinfo=None)
                age_seconds = max(0, round((datetime.datetime.now() - updated_at).total_seconds()))
            except (TypeError, ValueError):
                pass
            result["status_health"] = {
                "source": source,
                "cached": source == "cache",
                "age_seconds": age_seconds,
                "stale": age_seconds is None or age_seconds > 15 * 60,
            }
            return result
    detail = "Shift Alarm 상태 파일을 읽을 수 없습니다" if saw_file else "Shift Alarm 상태 파일이 아직 없습니다"
    raise HTTPException(status_code=503, detail=detail)


def _record_shift_alarm_routine_completion(status, source="web_check_all"):
    routine_date = status.get("routine_date")
    completed_at = datetime.datetime.now().isoformat(timespec="seconds")
    event = {
        "event_type": "routine_complete",
        "routine_date": routine_date,
        "wake_time": status.get("wake_time"),
        "completed_at": completed_at,
        "source": source,
    }
    if not routine_date:
        return False
    try:
        SHIFT_ALARM_ROUTINE_HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        with SHIFT_ALARM_ROUTINE_HISTORY_FILE.open("a", encoding="utf-8") as file:
            file.write(json.dumps(event, ensure_ascii=False) + "\n")
        return True
    except OSError:
        return False


def _write_shift_alarm_routine_signal(status, completed_at=None):
    """웹 전부 체크 완료를 같은 Mac의 메뉴바 앱에 즉시 전달한다."""
    completed_at = completed_at or datetime.datetime.now().isoformat(timespec="seconds")
    payload = {
        "routine_date": status.get("routine_date"),
        "completed_at": completed_at,
        "source": "web_check_all",
    }
    if not payload["routine_date"]:
        return False
    try:
        SHIFT_ALARM_ROUTINE_SIGNAL_FILE.parent.mkdir(parents=True, exist_ok=True)
        temporary = SHIFT_ALARM_ROUTINE_SIGNAL_FILE.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        temporary.replace(SHIFT_ALARM_ROUTINE_SIGNAL_FILE)
        return True
    except OSError:
        return False


def _record_shift_alarm_reminder_check(status, label, source="web_reminder", checked_at=None):
    """모든 리마인더 체크 시각을 append-only로 보존한다."""
    checked_at = checked_at or datetime.datetime.now()
    event = {
        "event_type": "reminder_checked",
        "routine_date": status.get("date") or checked_at.date().isoformat(),
        "checked_at": checked_at.isoformat(timespec="seconds"),
        "label": str(label),
        "wake_time": status.get("wake_time"),
        "source": source,
    }
    try:
        SHIFT_ALARM_ROUTINE_HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        with SHIFT_ALARM_ROUTINE_HISTORY_FILE.open("a", encoding="utf-8") as file:
            file.write(json.dumps(event, ensure_ascii=False) + "\n")
        return True
    except OSError:
        return False


SHIFT_ALARM_QUEST_ATTRIBUTES = {
    "전투력": ("병법", "손자병법"),
    "활력": ("기상", "걷", "운동", "스트레칭", "산책"),
    "집중": ("책", "독서", "코딩", "공부", "학습", "영어", "일본어", "미연시", "대사 쓰기"),
    "회복": ("멜라토닌", "숙면", "수면", "명상", "운기조식", "휴식"),
    "유대": ("전화", "연락", "카톡", "메시지", "가족", "엄마", "동생"),
    "정돈": ("청소", "정리", "점검", "충전", "배수", "화장실"),
    "준비": ("준비", "출근", "루틴", "체크"),
}
SHIFT_ALARM_CULTIVATION_AXES = {
    "정": {
        "hanja": "精",
        "title": "부득이하지 않으면 하지 않기",
        "description": "해야 할 일과 회복만 마치고 나머지는 덜어냅니다.",
        "recommendations": ["필수만 수행", "회복 우선", "마치면 멈추기"],
    },
    "기": {
        "hanja": "氣",
        "title": "부득이 멈춰야 할 때까지 움직이기",
        "description": "작은 행동을 이어 붙여 흐름과 활력을 유지합니다.",
        "recommendations": ["바로 움직이기", "행동 이어가기", "멈춰도 다시 시작"],
    },
    "신": {
        "hanja": "神",
        "title": "정신과 몰입을 벼리는 날",
        "description": "조용한 시간을 활용해 암기·독서·사유의 밀도를 높입니다.",
        "recommendations": ["손자병법 암기", "깊은 독서와 학습", "방해를 줄이고 몰입 유지"],
    },
}
SHIFT_ALARM_ATTRIBUTE_TO_AXIS = {
    "전투력": "신", "집중": "신", "유대": "신",
    "활력": "기", "정돈": "기",
    "회복": "정", "준비": "정",
}
SHIFT_ALARM_CULTIVATION_EPOCH = datetime.date(2026, 10, 15)  # 정(陰)으로 시작
SHIFT_ALARM_CULTIVATION_SEQUENCE = ("정", "기")
SHIFT_ALARM_CULTIVATION_DAILY_BONUS_CAP = 30
SHIFT_ALARM_STAT_POINTS_PER_LEVEL = 3
JAPANESE_READER_DB = Path(os.path.expanduser("~/.japanese_epub_web/reader.db"))
ENGLISH_READER_DB = Path(os.path.expanduser("~/.english_epub_web/reader.db"))


def _shift_alarm_quest_attribute(label):
    compact = re.sub(r"\s+", "", str(label or ""))
    for attribute, keywords in SHIFT_ALARM_QUEST_ATTRIBUTES.items():
        if any(keyword in compact for keyword in keywords):
            return attribute
    return "준비"


def _shift_alarm_action_type(label, attribute=None):
    """퀘스트를 정·기 보상 원칙에 쓰는 행동 유형으로 분류한다."""
    compact = re.sub(r"\s+", "", str(label or ""))
    if any(word in compact for word in ("멜라토닌", "수면", "숙면", "휴식", "명상", "운기조식", "식사", "밥", "물", "샤워")):
        return "회복"
    if any(word in compact for word in ("출근", "충전", "준비", "점검", "약", "복용", "AllOK", "루틴")):
        return "필수"
    attribute = attribute or _shift_alarm_quest_attribute(label)
    if attribute in {"활력", "정돈"}:
        return "활동"
    if attribute in {"집중", "전투력"}:
        return "성장"
    if attribute == "회복":
        return "회복"
    if attribute == "준비":
        return "필수"
    return "선택"


def _shift_alarm_action_bonus(axis, action_type):
    aligned = ((axis == "정" and action_type in {"필수", "회복"}) or
               (axis == "기" and action_type in {"활동", "성장"}))
    return 5 if aligned else 0


def _shift_alarm_cultivation_axis(label, attribute=None):
    """기존 7개 능력치를 정·기·신 수행 축으로 묶는다."""
    attribute = attribute or _shift_alarm_quest_attribute(label)
    return SHIFT_ALARM_ATTRIBUTE_TO_AXIS.get(attribute, "정")


def _shift_alarm_cultivation_axis_for_date(value=None):
    """근무와 무관하게 기준일부터 정(陰)·기(陽)를 하루씩 교대한다."""
    if isinstance(value, datetime.datetime):
        target = value.date()
    elif isinstance(value, datetime.date):
        target = value
    else:
        try:
            target = datetime.date.fromisoformat(str(value or "")[:10])
        except ValueError:
            target = datetime.date.today()
    offset = (target - SHIFT_ALARM_CULTIVATION_EPOCH).days
    return SHIFT_ALARM_CULTIVATION_SEQUENCE[offset % len(SHIFT_ALARM_CULTIVATION_SEQUENCE)]


def _read_shift_alarm_cultivation_choices():
    try:
        payload = json.loads(SHIFT_ALARM_CULTIVATION_CHOICES_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    return {
        str(date)[:10]: axis for date, axis in payload.items()
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(date)[:10]) and axis in SHIFT_ALARM_CULTIVATION_SEQUENCE
    }


def _write_shift_alarm_cultivation_choices(choices):
    SHIFT_ALARM_CULTIVATION_CHOICES_FILE.parent.mkdir(parents=True, exist_ok=True)
    temporary = SHIFT_ALARM_CULTIVATION_CHOICES_FILE.with_suffix(".tmp")
    temporary.write_text(json.dumps(choices, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(SHIFT_ALARM_CULTIVATION_CHOICES_FILE)


def _shift_alarm_cultivation_choice_for_date(value, choices=None):
    """해당 날의 수동 선택을 쓰고, 없으면 가장 최근 선택을 유지한다."""
    date_key = str(value or datetime.date.today().isoformat())[:10]
    choices = choices if choices is not None else _read_shift_alarm_cultivation_choices()
    if choices.get(date_key) in SHIFT_ALARM_CULTIVATION_SEQUENCE:
        return choices[date_key]
    previous = [date for date in choices if date <= date_key]
    if previous:
        return choices[max(previous)]
    # 선택 기록이 하나도 없을 때만 기존 화면의 오늘 축을 초기값으로 삼는다.
    return _shift_alarm_cultivation_axis_for_date(date_key)


def _parse_shift_alarm_cultivation_time(value):
    if isinstance(value, datetime.datetime):
        return value.replace(tzinfo=None)
    text = str(value or "")
    try:
        if len(text) == 10:
            return datetime.datetime.combine(datetime.date.fromisoformat(text), datetime.time.min)
        return datetime.datetime.fromisoformat(text).replace(tzinfo=None)
    except ValueError:
        return None


def _write_shift_alarm_cultivation_intervals(intervals):
    SHIFT_ALARM_CULTIVATION_INTERVALS_FILE.parent.mkdir(parents=True, exist_ok=True)
    temporary = SHIFT_ALARM_CULTIVATION_INTERVALS_FILE.with_suffix(".tmp")
    temporary.write_text(json.dumps(intervals, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(SHIFT_ALARM_CULTIVATION_INTERVALS_FILE)


def _migrate_shift_alarm_cultivation_intervals():
    """기존 날짜 선택을 자정 경계의 연속 시간 구간으로 한 번만 변환한다."""
    choices = _read_shift_alarm_cultivation_choices()
    today = datetime.date.today()
    start_date = today - datetime.timedelta(days=89)
    changes = []
    for offset in range(90):
        day = start_date + datetime.timedelta(days=offset)
        axis = _shift_alarm_cultivation_choice_for_date(day, choices)
        if not changes or axis != changes[-1][1]:
            changes.append((day, axis))
    migrated_at = datetime.datetime.now().replace(microsecond=0)
    intervals = []
    for index, (day, axis) in enumerate(changes):
        start = datetime.datetime.combine(day, datetime.time.min)
        end = (datetime.datetime.combine(changes[index + 1][0], datetime.time.min)
               if index + 1 < len(changes) else None)
        intervals.append({
            "axis": axis, "started_at": start.isoformat(timespec="seconds"),
            "ended_at": end.isoformat(timespec="seconds") if end else None,
            "migrated": True,
            **({"xp_started_at": migrated_at.isoformat(timespec="seconds")} if end is None else {}),
        })
    _write_shift_alarm_cultivation_intervals(intervals)
    return intervals


def _read_shift_alarm_cultivation_intervals():
    try:
        payload = json.loads(SHIFT_ALARM_CULTIVATION_INTERVALS_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return _migrate_shift_alarm_cultivation_intervals()
    if not isinstance(payload, list):
        return _migrate_shift_alarm_cultivation_intervals()
    if payload and all(isinstance(item, dict) and item.get("migrated") for item in payload) and not any(
        isinstance(item, dict) and item.get("xp_started_at") for item in payload
    ):
        return _migrate_shift_alarm_cultivation_intervals()
    intervals = []
    for item in payload:
        if not isinstance(item, dict) or item.get("axis") not in SHIFT_ALARM_CULTIVATION_SEQUENCE:
            continue
        start = _parse_shift_alarm_cultivation_time(item.get("started_at"))
        end = _parse_shift_alarm_cultivation_time(item.get("ended_at"))
        if not start or (end and end < start):
            continue
        intervals.append({
            "axis": item["axis"], "started_at": start.isoformat(timespec="seconds"),
            "ended_at": end.isoformat(timespec="seconds") if end else None,
            **({"migrated": True} if item.get("migrated") else {}),
            **({"xp_started_at": item["xp_started_at"]} if _parse_shift_alarm_cultivation_time(item.get("xp_started_at")) else {}),
        })
    if not intervals:
        return _migrate_shift_alarm_cultivation_intervals()
    return sorted(intervals, key=lambda item: item["started_at"])


def _shift_alarm_cultivation_axis_at(value=None, intervals=None):
    target = _parse_shift_alarm_cultivation_time(value) or datetime.datetime.now()
    intervals = intervals if intervals is not None else _read_shift_alarm_cultivation_intervals()
    for item in reversed(intervals):
        start = _parse_shift_alarm_cultivation_time(item.get("started_at"))
        end = _parse_shift_alarm_cultivation_time(item.get("ended_at"))
        if start and start <= target and (end is None or target < end):
            return item["axis"]
    return intervals[0]["axis"] if intervals else "정"


def _switch_shift_alarm_cultivation(axis, switched_at=None):
    switched_at = (switched_at or datetime.datetime.now()).replace(microsecond=0, tzinfo=None)
    with SHIFT_ALARM_QUEST_LOCK:
        intervals = _read_shift_alarm_cultivation_intervals()
        current = intervals[-1] if intervals else None
        if current and current.get("axis") == axis and not current.get("ended_at"):
            return False
        if current and not current.get("ended_at"):
            current["ended_at"] = switched_at.isoformat(timespec="seconds")
        intervals.append({"axis": axis, "started_at": switched_at.isoformat(timespec="seconds"), "ended_at": None})
        _write_shift_alarm_cultivation_intervals(intervals)
    return True


def _shift_alarm_shift_key(value):
    compact = re.sub(r"[^a-z]", "", str(value or "").lower())
    if compact in {"d", "day"}:
        return "day"
    if compact in {"g", "gy", "graveyard", "night"}:
        return "gy"
    if compact in {"s", "swing"}:
        return "swing"
    return "off"


def _shift_alarm_cultivation_reward(label, base_xp, *, routine_date=None, status=None):
    """선택한 수행축과 행동 유형에 맞춰 예상 XP를 계산한다."""
    attribute = _shift_alarm_quest_attribute(label)
    action_type = _shift_alarm_action_type(label, attribute)
    status = status or _read_shift_alarm_status()
    status_date = str(status.get("date") or status.get("routine_date") or "")
    today = datetime.date.today().isoformat()
    shift_key = _shift_alarm_shift_key(status.get("shift"))
    reward_date = routine_date or status_date or today
    reward_moment = datetime.datetime.now() if str(reward_date)[:10] == today else f"{str(reward_date)[:10]}T12:00:00"
    axis = _shift_alarm_cultivation_axis_at(reward_moment)
    bonus = _shift_alarm_action_bonus(axis, action_type)
    multiplier = (int(base_xp) + bonus) / max(1, int(base_xp))
    return {
        "attribute": attribute,
        "action_type": action_type,
        "bonus_reason": action_type if bonus else "기본",
        "axis": axis,
        "shift_key": shift_key,
        "multiplier": multiplier,
        "base_xp": int(base_xp),
        "xp": max(1, int(base_xp) + bonus),
    }


def _shift_alarm_quest_level(total_xp):
    """레벨별 필요량(100 + 현재 레벨×20)을 누적해 현재 진행도를 계산한다."""
    remaining = max(0, int(total_xp or 0))
    level = 1
    while remaining >= 100 + level * 20:
        remaining -= 100 + level * 20
        level += 1
    return level, remaining, 100 + level * 20


def _shift_alarm_quest_stats(level, attribute_xp):
    """레벨업 포인트를 누적 활동 비중대로 나눠 실제 능력치로 만든다."""
    names = list(SHIFT_ALARM_QUEST_ATTRIBUTES)
    stats = {name: 1 for name in names}
    bonus_points = max(0, int(level or 1) - 1) * SHIFT_ALARM_STAT_POINTS_PER_LEVEL
    if not bonus_points:
        return stats
    weights = {name: max(0, int(attribute_xp.get(name) or 0)) for name in names}
    total_weight = sum(weights.values())
    if total_weight <= 0:
        for index in range(bonus_points):
            stats[names[index % len(names)]] += 1
        return stats
    exact = {name: bonus_points * weights[name] / total_weight for name in names}
    allocated = {name: int(exact[name]) for name in names}
    remaining = bonus_points - sum(allocated.values())
    priority = sorted(names, key=lambda name: (exact[name] - allocated[name], weights[name], -names.index(name)), reverse=True)
    for name in priority[:remaining]:
        allocated[name] += 1
    for name in names:
        stats[name] += allocated[name]
    return stats


def _reader_mastery_units(path, username):
    """서재가 이미 저장한 책별 현재 위치를 읽기 숙련도 단위로 환산한다."""
    if not path.is_file():
        return 0
    try:
        with sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=2) as conn:
            rows = conn.execute(
                "SELECT spine_index,percent FROM user_progress WHERE username=?", (username,)
            ).fetchall()
        return sum(max(0, int(row[0] or 0)) + max(0.0, min(100.0, float(row[1] or 0))) / 100 for row in rows)
    except (OSError, sqlite3.Error, TypeError, ValueError):
        return 0


def _mastery_level(xp):
    xp = max(0, int(xp or 0))
    return {"level": 1 + xp // 100, "xp": xp, "level_xp": xp % 100, "next_level_xp": 100}


def _shift_alarm_masteries(username):
    """각 시스템의 기존 진행 데이터를 Shift Quest 숙련도로 읽기 전용 연결한다."""
    japanese_reading = round(_reader_mastery_units(JAPANESE_READER_DB, username) * 2)
    english_reading = round(_reader_mastery_units(ENGLISH_READER_DB, username) * 2)
    dating_xp = battle_xp = english_vocab_xp = japanese_vocab_xp = 0
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT day,affection,completed FROM dating_sim_progress WHERE username=?", (username,)
        ).fetchall()
        dating_xp = sum(max(0, int(row[0] or 1) - 1) * 5 + max(0, int(row[1] or 50) - 50) + int(bool(row[2])) * 30 for row in rows)
        rows = conn.execute(
            "SELECT score,state_json FROM battle_sim_runs WHERE username=?", (username,)
        ).fetchall()
        battle_xp = sum(max(10, int(row[0] or 0) * 2 +
                            (15 if _battle_json(row[1], {}).get("flags", {}).get("decisive_victory") else 0))
                        for row in rows)
        if not rows:
            rows = conn.execute(
                "SELECT phase,score,completed FROM battle_sim_progress WHERE username=?", (username,)
            ).fetchall()
            battle_xp = sum(max(0, int(row[0] or 0)) * 5 + max(0, int(row[1] or 0)) * 10 + int(bool(row[2])) * 30 for row in rows)
        rows = conn.execute(
            "SELECT language,COUNT(*) FROM vocabulary_entries WHERE username=? GROUP BY language", (username,)
        ).fetchall()
        for language, count in rows:
            if str(language).lower().startswith("ja") or str(language).lower().startswith("japan"):
                japanese_vocab_xp += int(count or 0) * 2
            elif str(language).lower().startswith("en") or str(language).lower().startswith("english"):
                english_vocab_xp += int(count or 0) * 2
        rows = conn.execute(
            "SELECT language,COALESCE(SUM(xp),0) FROM vocabulary_practice_attempts WHERE username=? GROUP BY language",
            (username,),
        ).fetchall()
        for language, xp in rows:
            normalized = str(language).lower()
            if normalized.startswith(("ja", "japan", "hanja")):
                japanese_vocab_xp += int(xp or 0)
            elif normalized.startswith(("en", "english")):
                english_vocab_xp += int(xp or 0)
    finally:
        conn.close()
    specs = [
        ("일본어", japanese_reading + dating_xp // 2 + japanese_vocab_xp, "서재 읽기 · 미연시 진행 · 일본어 단어 · 쓰기 연습"),
        ("영어", english_reading + english_vocab_xp, "영어 서재 읽기 · 영어 단어 · 쓰기 연습"),
        ("교감력", dating_xp, "대화 선택 · 관계 진전 · 호감도 · 엔딩"),
        ("전쟁 지휘", battle_xp, "명령 선택 · 전투 점수 · 전투 완료"),
    ]
    return [{"name": name, "help": help_text, **_mastery_level(xp)} for name, xp, help_text in specs]


def _append_shift_alarm_quest_event(event):
    SHIFT_ALARM_QUEST_EVENTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with SHIFT_ALARM_QUEST_LOCK:
        with SHIFT_ALARM_QUEST_EVENTS_FILE.open("a", encoding="utf-8") as file:
            file.write(json.dumps(event, ensure_ascii=False) + "\n")


def _read_shift_alarm_quest_events():
    try:
        lines = SHIFT_ALARM_QUEST_EVENTS_FILE.read_text(encoding="utf-8").splitlines()
    except (FileNotFoundError, OSError):
        return []
    events = []
    for line in lines:
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict) and event.get("quest_key") and event.get("action") in {"award", "reverse"}:
            events.append(event)
    return events


def _record_shift_alarm_quest(quest_key, label, xp, attribute, action="award", source="web",
                              routine_date=None, created_at=None, cultivation=None):
    """동일 퀘스트는 한 번만 지급하고 취소한 지급만 되돌리는 append-only 원장."""
    with SHIFT_ALARM_QUEST_LOCK:
        events = _read_shift_alarm_quest_events()
        balance = sum(1 if item["action"] == "award" else -1
                      for item in events if item.get("quest_key") == quest_key)
        if action == "award" and balance > 0:
            return False
        if action == "reverse" and balance <= 0:
            return False
        now = created_at or datetime.datetime.now()
        cultivation = cultivation or _shift_alarm_cultivation_reward(
            label, xp, routine_date=routine_date,
        )
        _append_shift_alarm_quest_event({
            "event_id": uuid.uuid4().hex,
            "quest_key": quest_key,
            "label": str(label),
            "attribute": attribute,
            "xp": int(cultivation.get("xp") or xp),
            "base_xp": int(cultivation.get("base_xp") or xp),
            "action_type": cultivation.get("action_type") or _shift_alarm_action_type(label, attribute),
            "cultivation_axis": cultivation.get("axis") or _shift_alarm_cultivation_axis_for_date(routine_date or now),
            "cultivation_shift": cultivation.get("shift_key") or "off",
            "cultivation_multiplier": float(cultivation.get("multiplier") or 1),
            "action": action,
            "source": source,
            "created_at": now.isoformat(timespec="seconds"),
            "routine_date": routine_date or now.date().isoformat(),
        })
    return True


def _sync_shift_alarm_quest_history():
    """Mac 메뉴바가 남긴 기존 생활 기록도 웹 체크와 같은 퀘스트로 흡수한다."""
    try:
        lines = SHIFT_ALARM_ROUTINE_HISTORY_FILE.read_text(encoding="utf-8").splitlines()
    except (FileNotFoundError, OSError):
        return
    for line in lines:
        try:
            item = json.loads(line)
            routine_date = str(item.get("routine_date") or "")
            event_type = item.get("event_type")
            if routine_date < SHIFT_ALARM_QUEST_EPOCH:
                continue
            if event_type == "routine_complete":
                _record_shift_alarm_quest(
                    f"routine:{routine_date}:all-ok", "All OK", 25, "준비",
                    source=item.get("source") or "shift_alarm_history",
                    routine_date=routine_date,
                    created_at=datetime.datetime.fromisoformat(item["completed_at"]),
                )
            elif event_type in {"reminder_checked", "melatonin_checked"}:
                label = str(item.get("label") or ("멜라토닌" if event_type == "melatonin_checked" else "리마인더"))
                _record_shift_alarm_quest(
                    f"reminder:{routine_date}:{label}", label, 10,
                    _shift_alarm_quest_attribute(label),
                    source=item.get("source") or "shift_alarm_history",
                    routine_date=routine_date,
                    created_at=datetime.datetime.fromisoformat(item["checked_at"]),
                )
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            continue


def _shift_alarm_effective_rewards(active, cultivation_intervals):
    """원장을 수정하지 않고 날짜별 모드 보너스와 기의 행동 연속 보너스를 계산한다."""
    rewards = {}
    daily = {}
    ordered = sorted(active.items(), key=lambda pair: pair[1].get("created_at", ""))
    for quest_key, event in ordered:
        date_key = str(event.get("routine_date") or event.get("created_at") or "")[:10]
        axis = _shift_alarm_cultivation_axis_at(event.get("created_at") or date_key, cultivation_intervals)
        base_xp = max(0, int(event.get("base_xp") or event.get("xp") or 0))
        action_type = event.get("action_type") or _shift_alarm_action_type(
            event.get("label"), event.get("attribute"),
        )
        day = daily.setdefault(date_key, {
            "bonus": 0, "aligned": 0, "chain": 0, "longest_chain": 0,
            "last_at": None, "last_axis": None, "types": {},
        })
        bonus = _shift_alarm_action_bonus(axis, action_type)
        flow_bonus = 0
        try:
            created_at = datetime.datetime.fromisoformat(str(event.get("created_at") or ""))
        except ValueError:
            created_at = None
        if axis == "기" and day["last_axis"] == "기" and created_at and day["last_at"]:
            gap = (created_at - day["last_at"]).total_seconds()
            if 0 <= gap <= 90 * 60:
                day["chain"] += 1
                flow_bonus = 2
            else:
                day["chain"] = 1
        else:
            day["chain"] = max(1, day["chain"])
        if created_at:
            day["last_at"] = created_at
        day["last_axis"] = axis
        day["longest_chain"] = max(day["longest_chain"], day["chain"])
        allowed = max(0, SHIFT_ALARM_CULTIVATION_DAILY_BONUS_CAP - day["bonus"])
        awarded_bonus = min(allowed, bonus + flow_bonus)
        day["bonus"] += awarded_bonus
        if bonus:
            day["aligned"] += 1
        day["types"][action_type] = day["types"].get(action_type, 0) + 1
        rewards[quest_key] = {
            "xp": base_xp + awarded_bonus, "base_xp": base_xp,
            "bonus_xp": awarded_bonus, "axis": axis, "action_type": action_type,
            "bonus_reason": (f"{action_type} · 흐름" if flow_bonus and bonus else
                             "흐름" if flow_bonus else action_type if bonus else "기본"),
        }
    return rewards, daily


def _shift_alarm_quest_state(username=None):
    _sync_shift_alarm_quest_history()
    events = _read_shift_alarm_quest_events()
    active = {}
    for event in events:
        key = event["quest_key"]
        if event["action"] == "award":
            active[key] = event
        else:
            active.pop(key, None)
    username = username or APP_USERNAME or "local-owner"
    today = datetime.date.today().isoformat()
    cultivation_intervals = _read_shift_alarm_cultivation_intervals()
    effective_rewards, daily_metrics = _shift_alarm_effective_rewards(active, cultivation_intervals)
    total_xp = sum(item["xp"] for item in effective_rewards.values())
    cultivation_xp = {name: 0 for name in SHIFT_ALARM_CULTIVATION_SEQUENCE}
    for quest_key, event in active.items():
        reward = effective_rewards[quest_key]["xp"]
        # 예전의 '신' XP도 삭제하지 않고 그 날에 선택한 정·기로 재분류한다.
        axis = effective_rewards[quest_key]["axis"]
        cultivation_xp[axis] += reward
    # 전쟁 시뮬레이션은 퀴즈 점수가 아니라 실제 완주 기록의 전황·평가를
    # Shift Quest 성장에 반영한다. 정보/보급/병력 보존 성향도 각각 연결된다.
    conn = get_conn()
    try:
        battle_rows = conn.execute(
            "SELECT score,state_json FROM battle_sim_runs WHERE username=?", (username,)
        ).fetchall()
    finally:
        conn.close()
    for score, state_json in battle_rows:
        battle_state = _battle_json(state_json, {})
        reward = max(10, int(score or 0) * 2 +
                     (15 if battle_state.get("flags", {}).get("decisive_victory") else 0))
        total_xp += reward
        cultivation_xp["정"] += reward // 2
        cultivation_xp["기"] += reward - reward // 2
    now = datetime.datetime.now().replace(microsecond=0)
    cultivation_seconds = {name: 0 for name in SHIFT_ALARM_CULTIVATION_SEQUENCE}
    cultivation_xp_seconds = {name: 0 for name in SHIFT_ALARM_CULTIVATION_SEQUENCE}
    timeline = []
    for item in cultivation_intervals:
        start = _parse_shift_alarm_cultivation_time(item.get("started_at"))
        end = _parse_shift_alarm_cultivation_time(item.get("ended_at")) or now
        if not start:
            continue
        effective_end = min(end, now)
        seconds = max(0, round((effective_end - start).total_seconds()))
        cultivation_seconds[item["axis"]] += seconds
        xp_start = _parse_shift_alarm_cultivation_time(item.get("xp_started_at"))
        if not item.get("migrated") or xp_start:
            xp_start = xp_start or start
            cultivation_xp_seconds[item["axis"]] += max(0, round((effective_end - max(start, xp_start)).total_seconds()))
        timeline.append({
            "axis": item["axis"], "started_at": start.isoformat(timespec="seconds"),
            "ended_at": item.get("ended_at"), "duration_seconds": seconds,
            "active": not item.get("ended_at"),
        })
    cultivation_time_xp = {name: seconds // 3600 for name, seconds in cultivation_xp_seconds.items()}
    for name in SHIFT_ALARM_CULTIVATION_SEQUENCE:
        cultivation_xp[name] += cultivation_time_xp[name]
        total_xp += cultivation_time_xp[name]
    level, level_xp, next_level_xp = _shift_alarm_quest_level(total_xp)
    today_events = sorted(
        ((key, event) for key, event in active.items() if event.get("routine_date") == today),
        key=lambda item: item[1].get("created_at", ""), reverse=True,
    )
    status = _read_shift_alarm_status()
    focus_axis = _shift_alarm_cultivation_axis_at(now, cultivation_intervals)
    shift_key = "daily"
    shift_names = {"daily": "TODAY"}
    axes = []
    for name in SHIFT_ALARM_CULTIVATION_SEQUENCE:
        spec = SHIFT_ALARM_CULTIVATION_AXES[name]
        xp = cultivation_xp[name]
        axes.append({
            "name": name, "hanja": spec["hanja"], "xp": xp,
            "level": 1 + xp // 100, "level_xp": xp % 100, "next_level_xp": 100,
            "focused": name == focus_axis,
        })
    if focus_axis:
        focus_spec = SHIFT_ALARM_CULTIVATION_AXES[focus_axis]
        mode = {
            "shift": shift_names[shift_key], "axis": focus_axis, "hanja": focus_spec["hanja"],
            "polarity": "陰" if focus_axis == "정" else "陽",
            "title": focus_spec["title"], "description": focus_spec["description"],
            "recommendations": focus_spec["recommendations"],
        }
    else:
        mode = {
            "shift": "휴무", "axis": "균형", "hanja": "☯", "title": "세 기운을 고르게 돌보는 날",
            "description": "회복을 우선하되 몸·활동·정신 중 부족한 축을 가볍게 보완합니다.",
            "recommendations": ["충분한 회복", "가벼운 움직임", "부담 없는 독서와 정리"],
        }
    daily_totals = {}
    for quest_key, event in active.items():
        date_key = str(event.get("routine_date") or event.get("created_at") or "")[:10]
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date_key):
            continue
        item = daily_totals.setdefault(date_key, {"xp": 0, "completed": 0})
        item["xp"] += effective_rewards[quest_key]["xp"]
        item["completed"] += 1
    history = []
    today_date = datetime.date.fromisoformat(today)
    for days_ago in range(89, -1, -1):
        date_key = (today_date - datetime.timedelta(days=days_ago)).isoformat()
        totals = daily_totals.get(date_key, {})
        metric = daily_metrics.get(date_key, {})
        history.append({
            "date": date_key,
            "axis": _shift_alarm_cultivation_axis_at(f"{date_key}T12:00:00", cultivation_intervals),
            "xp": int(totals.get("xp") or 0),
            "completed": int(totals.get("completed") or 0),
            "bonus_xp": int(metric.get("bonus") or 0),
            "aligned": int(metric.get("aligned") or 0),
            "longest_chain": int(metric.get("longest_chain") or 0),
            "types": metric.get("types") or {},
            "selected": True,
        })
    today_metric = daily_metrics.get(today, {})
    today_types = today_metric.get("types") or {}
    mode_metric = ({
        "label": "수렴", "value": f'{today_metric.get("aligned", 0)}개',
        "detail": f'필수·회복 {today_types.get("필수", 0) + today_types.get("회복", 0)}개 완료',
    } if focus_axis == "정" else {
        "label": "흐름", "value": f'{today_metric.get("longest_chain", 0)}연속',
        "detail": f'활동·성장 {today_types.get("활동", 0) + today_types.get("성장", 0)}개 완료',
    })
    return {
        "level": level, "total_xp": total_xp, "level_xp": level_xp,
        "next_level_xp": next_level_xp,
        "progress_percent": round(level_xp / next_level_xp * 100) if next_level_xp else 0,
        "today_xp": sum(effective_rewards[key]["xp"] for key, _event in today_events),
        "today_completed": len(today_events),
        "cultivation": {
            "mode": mode, "axes": axes, "history": history,
            "intervals": timeline,
            "current_started_at": timeline[-1]["started_at"] if timeline else now.isoformat(timespec="seconds"),
            "current_elapsed_seconds": timeline[-1]["duration_seconds"] if timeline else 0,
            "previous_interval": timeline[-2] if len(timeline) > 1 else None,
            "total_seconds": cultivation_seconds,
            "time_xp": cultivation_time_xp,
            "ratio": {
                name: round(cultivation_seconds[name] / max(1, sum(cultivation_seconds.values())) * 100, 1)
                for name in SHIFT_ALARM_CULTIVATION_SEQUENCE
            },
            "metric": mode_metric,
            "daily_bonus": int(today_metric.get("bonus") or 0),
            "daily_bonus_cap": SHIFT_ALARM_CULTIVATION_DAILY_BONUS_CAP,
            "reward_multipliers": {
                name: (1.5 if name == focus_axis else 1.0)
                for name in SHIFT_ALARM_CULTIVATION_SEQUENCE
            },
        },
        "recent": [{
            "label": event.get("label"), "attribute": event.get("attribute"),
            "created_at": event.get("created_at"), **effective_rewards[key],
        } for key, event in today_events[:5]],
    }


def _is_melatonin_reminder(label: str) -> bool:
    return "멜라토닌" in re.sub(r"\s+", "", str(label or ""))


def _play_classical_after_melatonin_check() -> None:
    """리마인더 응답을 막지 않고 숙면 재생과 8시간 수면 모드를 시작한다."""
    _start_shift_alarm_sleep_mode()
    ok, message = _shift_alarm_play_folder(SHIFT_ALARM_SLEEP_FOLDER)
    if not ok:
        print(f"⚠️ 멜라토닌 체크 후 숙면 재생 실패: {message}", file=sys.stderr)


def _learn_shift_alarm_reminder_time(status, label, checked_at=None):
    """체크한 시각을 현재 근무 프로필의 다음 알림 시각으로 저장한다."""
    checked_at = checked_at or datetime.datetime.now()
    merged = _merge_reminder_editor(status)
    item = next((entry for entry in merged.get("reminder_schedule", [])
                 if entry.get("label") == label), None)
    if not item or not item.get("key"):
        return False
    profile = status.get("reminder_time_profile")
    if profile not in SHIFT_ALARM_TIME_PROFILES:
        profile = "시각"
    editor = _read_reminder_editor()
    override = editor["items"].get(item["key"], {})
    override = dict(override) if isinstance(override, dict) else {}
    learned_time = {"hour": checked_at.hour, "minute": checked_at.minute}
    if profile == "시각":
        override["time"] = learned_time
    else:
        profile_times = dict(override.get("profile_times", {}))
        profile_times[profile] = learned_time
        override["profile_times"] = profile_times
    override["last_checked_at"] = checked_at.isoformat(timespec="seconds")
    editor["items"][item["key"]] = override
    _write_reminder_editor(editor)
    return True


def _record_shift_alarm_habit_click(kind):
    labels = {"breathing": "운기조식", "smoking": "흡연"}
    if kind not in labels:
        raise HTTPException(status_code=422, detail="지원하지 않는 기록 종류입니다")
    clicked_at = datetime.datetime.now()
    event = {
        "event_type": "habit_click",
        "routine_date": clicked_at.date().isoformat(),
        "clicked_at": clicked_at.isoformat(timespec="seconds"),
        "kind": kind,
        "label": labels[kind],
        "source": "shift_alarm_dashboard",
    }
    try:
        SHIFT_ALARM_ROUTINE_HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        with SHIFT_ALARM_ROUTINE_HISTORY_FILE.open("a", encoding="utf-8") as file:
            file.write(json.dumps(event, ensure_ascii=False) + "\n")
    except OSError as exc:
        raise HTTPException(status_code=503, detail="생활 기록을 저장하지 못했습니다") from exc
    return event


def _record_shift_alarm_learning_link_click(kind, source="japanese_teacher_message"):
    labels = {"japanese_library": "일본어 서재", "dating_sim": "미연시"}
    if kind not in labels:
        raise HTTPException(status_code=422, detail="지원하지 않는 학습 링크입니다")
    clicked_at = datetime.datetime.now()
    event = {
        "event_type": "learning_link_click",
        "routine_date": clicked_at.date().isoformat(),
        "clicked_at": clicked_at.isoformat(timespec="seconds"),
        "kind": kind,
        "label": labels[kind],
        "source": source,
    }
    try:
        SHIFT_ALARM_ROUTINE_HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        with SHIFT_ALARM_ROUTINE_HISTORY_FILE.open("a", encoding="utf-8") as file:
            file.write(json.dumps(event, ensure_ascii=False) + "\n")
    except OSError as exc:
        raise HTTPException(status_code=503, detail="학습 링크 시각을 저장하지 못했습니다") from exc
    return event


def _undo_shift_alarm_habit_click(kind):
    labels = {"breathing": "운기조식", "smoking": "흡연"}
    if kind not in labels:
        raise HTTPException(status_code=422, detail="지원하지 않는 기록 종류입니다")
    today = datetime.date.today().isoformat()
    record = next((item for item in _read_shift_alarm_routine_history(7)
                   if item.get("routine_date") == today), None)
    active = [event for event in (record or {}).get("habit_events", [])
              if event.get("kind") == kind]
    if not active:
        raise HTTPException(status_code=409, detail="취소할 오늘 기록이 없습니다")
    undone_at = datetime.datetime.now()
    event = {
        "event_type": "habit_undo",
        "routine_date": today,
        "clicked_at": undone_at.isoformat(timespec="seconds"),
        "kind": kind,
        "label": labels[kind],
        "undone_clicked_at": active[-1].get("clicked_at"),
        "source": "shift_alarm_dashboard",
    }
    try:
        with SHIFT_ALARM_ROUTINE_HISTORY_FILE.open("a", encoding="utf-8") as file:
            file.write(json.dumps(event, ensure_ascii=False) + "\n")
    except OSError as exc:
        raise HTTPException(status_code=503, detail="생활 기록 취소를 저장하지 못했습니다") from exc
    return event


def _read_shift_alarm_routine_history(limit=30):
    try:
        shift_schedule = json.loads(SHIFT_ALARM_SCHEDULE_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        shift_schedule = {}
    shift_names = {"D": "Day", "S": "Swing", "G": "GY", "휴": "휴무"}

    def local_event_time(value):
        """JSONL의 과거 naive 시각과 새 offset 시각을 같은 로컬 기준으로 맞춘다."""
        parsed = datetime.datetime.fromisoformat(value)
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone().replace(tzinfo=None)
        return parsed

    by_date = {}
    try:
        lines = SHIFT_ALARM_ROUTINE_HISTORY_FILE.read_text(encoding="utf-8").splitlines()
    except (FileNotFoundError, OSError):
        lines = []
    for line in lines:
        try:
            item = json.loads(line)
            routine_date = item.get("routine_date")
            event_type = item.get("event_type", "routine_complete")
            timestamp_key = "clicked_at" if event_type in ("habit_click", "habit_undo", "learning_link_click") else (
                "checked_at" if event_type in ("melatonin_checked", "reminder_checked") else (
                    "started_at" if event_type == "ebook_study_start" else "completed_at"
                )
            )
            event_at = local_event_time(item.get(timestamp_key, ""))
        except (json.JSONDecodeError, TypeError, ValueError):
            continue
        if not routine_date:
            continue
        day = by_date.setdefault(routine_date, {})
        if event_type == "reminder_checked":
            day.setdefault("reminder_checked", []).append((event_at, item))
            continue
        if event_type in ("habit_click", "habit_undo"):
            day.setdefault("habit_events", []).append((event_at, item))
            continue
        if event_type == "learning_link_click":
            day.setdefault("learning_link_clicks", []).append((event_at, item))
            continue
        if event_type == "routine_complete":
            latest = day.get("routine_complete_latest")
            if latest is None or event_at > latest[0]:
                day["routine_complete_latest"] = (event_at, item)
        previous = day.get(event_type)
        if previous is None or event_at < previous[0]:
            day[event_type] = (event_at, item)
    records = []
    for routine_date, events in sorted(by_date.items(), reverse=True)[:limit]:
        shift_code = str(shift_schedule.get(routine_date) or "")
        routine_event = events.get("routine_complete")
        melatonin_event = events.get("melatonin_checked")
        ebook_event = events.get("ebook_study_start")
        reminder_events = sorted(events.get("reminder_checked", []), key=lambda pair: pair[0])
        active_habit_clicks = {"breathing": [], "smoking": []}
        for event_at, event in sorted(events.get("habit_events", []), key=lambda pair: pair[0]):
            kind = event.get("kind")
            if kind not in active_habit_clicks:
                continue
            if event.get("event_type") == "habit_undo":
                if active_habit_clicks[kind]:
                    active_habit_clicks[kind].pop()
            else:
                active_habit_clicks[kind].append((event_at, event))
        habit_clicks = sorted(
            [pair for clicks in active_habit_clicks.values() for pair in clicks],
            key=lambda pair: pair[0],
        )
        learning_link_clicks = sorted(events.get("learning_link_clicks", []), key=lambda pair: pair[0])
        completed_at, routine_item = routine_event if routine_event else (None, {})
        latest_completed = events.get("routine_complete_latest")
        latest_completed_at = latest_completed[0] if latest_completed else completed_at
        melatonin_at, _melatonin_item = melatonin_event if melatonin_event else (None, {})
        ebook_started_at, _ebook_item = ebook_event if ebook_event else (None, {})
        reminder_checks = [{
            "label": event.get("label", "리마인더"),
            "checked_at": event_at.isoformat(timespec="seconds"),
            "time": event_at.strftime("%H:%M"),
        } for event_at, event in reminder_events]
        habit_events = [{
            "kind": event.get("kind"),
            "label": event.get("label") or ("운기조식" if event.get("kind") == "breathing" else "흡연"),
            "clicked_at": event_at.isoformat(timespec="seconds"),
            "time": event_at.strftime("%H:%M:%S"),
        } for event_at, event in habit_clicks]
        learning_links = [{
            "kind": event.get("kind"),
            "label": event.get("label") or ("일본어 서재" if event.get("kind") == "japanese_library" else "미연시"),
            "clicked_at": event_at.isoformat(timespec="seconds"),
            "time": event_at.strftime("%H:%M:%S"),
        } for event_at, event in learning_link_clicks]
        if not melatonin_at:
            melatonin_at = next(
                (event_at for event_at, event in reminder_events if "멜라토닌" in str(event.get("label"))),
                None,
            )
        wake_time = routine_item.get("wake_time") or next(
            (event.get("wake_time") for _at, event in reminder_events if event.get("wake_time")), None
        )
        wake_flow_at = next(
            (event_at for event_at, event in reversed(reminder_events)
             if re.search(r"(?:핸드폰|휴대전화|폰).*충전.*샤워", str(event.get("label") or ""))),
            None,
        )
        minutes_after_wake = None
        tossing_minutes = None
        routine_focus_minutes = None
        if wake_time and completed_at:
            try:
                wake_at = datetime.datetime.combine(
                    datetime.date.fromisoformat(routine_date),
                    datetime.time.fromisoformat(wake_time),
                )
                minutes_after_wake = max(0, round((completed_at - wake_at).total_seconds() / 60))
            except (TypeError, ValueError):
                pass
        if wake_time and wake_flow_at:
            try:
                wake_at = datetime.datetime.combine(
                    datetime.date.fromisoformat(routine_date),
                    datetime.time.fromisoformat(wake_time),
                )
                tossing_minutes = round((wake_flow_at - wake_at).total_seconds() / 60)
                if not 0 <= tossing_minutes <= 360:
                    tossing_minutes = None
            except (TypeError, ValueError):
                pass
        if wake_flow_at and completed_at:
            routine_focus_minutes = round((completed_at - wake_flow_at).total_seconds() / 60)
            if not 0 <= routine_focus_minutes <= 720:
                routine_focus_minutes = None
        records.append({
            "routine_date": routine_date,
            "shift_code": shift_code or None,
            "shift": shift_names.get(shift_code, shift_code or None),
            "wake_time": wake_time,
            "wake_flow_checked_at": wake_flow_at.isoformat(timespec="seconds") if wake_flow_at else None,
            "wake_flow_time": wake_flow_at.strftime("%H:%M") if wake_flow_at else None,
            "completed_at": completed_at.isoformat(timespec="seconds") if completed_at else None,
            "completed_time": completed_at.strftime("%H:%M") if completed_at else None,
            "latest_completed_time": latest_completed_at.strftime("%H:%M") if latest_completed_at else None,
            "melatonin_checked_at": melatonin_at.isoformat(timespec="seconds") if melatonin_at else None,
            "melatonin_time": melatonin_at.strftime("%H:%M") if melatonin_at else None,
            "ebook_started_at": ebook_started_at.isoformat(timespec="seconds") if ebook_started_at else None,
            "ebook_start_time": ebook_started_at.strftime("%H:%M") if ebook_started_at else None,
            "reminder_checks": reminder_checks,
            "habit_events": habit_events,
            "learning_link_clicks": learning_links,
            "minutes_after_wake": minutes_after_wake,
            "tossing_minutes": tossing_minutes,
            "routine_focus_minutes": routine_focus_minutes,
        })
    baselines = {}
    for record in reversed(records):
        shift = record.get("shift") or "휴무"
        samples = baselines.setdefault(shift, [])
        value = record.get("tossing_minutes")
        if value is not None and len(samples) >= 5:
            ordered = sorted(samples[-14:])
            middle = len(ordered) // 2
            baseline = (ordered[middle] if len(ordered) % 2
                        else (ordered[middle - 1] + ordered[middle]) / 2)
            difference = value - baseline
            threshold = max(20, baseline * .2)
            axis = "정" if difference >= threshold else "기" if difference <= -threshold else None
            record["cultivation_recommendation"] = {
                "axis": axis,
                "status": "recovery" if axis == "정" else "active" if axis == "기" else "steady",
                "baseline_minutes": round(baseline),
                "difference_minutes": round(difference),
                "sample_count": len(ordered),
                "message": (
                    "회복이 더 필요한 신호일 수 있습니다" if axis == "정" else
                    "평소보다 빠르게 움직인 날입니다" if axis == "기" else
                    "평소 범위의 기상 흐름입니다"
                ),
            }
        elif value is not None:
            record["cultivation_recommendation"] = {
                "axis": None, "status": "insufficient", "sample_count": len(samples),
                "message": "판단을 위한 같은 근무 기록이 더 필요합니다",
            }
        if value is not None:
            samples.append(value)
    return records


def _read_reminder_editor():
    try:
        payload = json.loads(SHIFT_ALARM_REMINDER_EDITOR_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return {"items": {}, "occurrences": []}
    items = payload.get("items", {}) if isinstance(payload, dict) else {}
    occurrences = payload.get("occurrences", []) if isinstance(payload, dict) else []
    return {
        "items": items if isinstance(items, dict) else {},
        "occurrences": occurrences if isinstance(occurrences, list) else [],
    }


def _write_reminder_editor(payload):
    SHIFT_ALARM_REMINDER_EDITOR_FILE.parent.mkdir(parents=True, exist_ok=True)
    temporary = SHIFT_ALARM_REMINDER_EDITOR_FILE.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(SHIFT_ALARM_REMINDER_EDITOR_FILE)


def _read_shift_alarm_mute():
    try:
        payload = json.loads(SHIFT_ALARM_MUTE_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return {"muted": False}
    return {"muted": bool(payload.get("muted"))} if isinstance(payload, dict) else {"muted": False}


def _read_shift_alarm_sleep_mode():
    try:
        payload = json.loads(SHIFT_ALARM_SLEEP_MODE_FILE.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except (FileNotFoundError, OSError, ValueError, TypeError, json.JSONDecodeError):
        return {}


def _shift_alarm_sleep_mode_active(now=None):
    now = now or datetime.datetime.now()
    try:
        return now < datetime.datetime.fromisoformat(
            str(_read_shift_alarm_sleep_mode().get("mute_until"))
        )
    except (TypeError, ValueError):
        return False


def _start_shift_alarm_sleep_mode(now=None):
    now = now or datetime.datetime.now()
    payload = {
        "started_at": now.isoformat(timespec="seconds"),
        "music_stop_at": (now + datetime.timedelta(seconds=SHIFT_ALARM_SLEEP_MUSIC_SECONDS)).isoformat(timespec="seconds"),
        "mute_until": (now + datetime.timedelta(seconds=SHIFT_ALARM_SLEEP_MUTE_SECONDS)).isoformat(timespec="seconds"),
        "music_stopped": False,
    }
    SHIFT_ALARM_SLEEP_MODE_FILE.parent.mkdir(parents=True, exist_ok=True)
    temporary = SHIFT_ALARM_SLEEP_MODE_FILE.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    temporary.replace(SHIFT_ALARM_SLEEP_MODE_FILE)
    return payload


def _queue_shift_alarm_sleep_notification(title, body_text, url):
    text = re.sub(r"\s+", " ", str(body_text or title or "")).strip()
    if not text:
        return
    payload = {
        "queued_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "title": str(title or "")[:120],
        "text": text[:SHIFT_ALARM_SLEEP_SPEAK_MAX_CHARS],
        "url": str(url or "")[:500],
    }
    try:
        descriptor = os.open(
            SHIFT_ALARM_SLEEP_NOTIFICATION_QUEUE_FILE,
            os.O_WRONLY | os.O_CREAT | os.O_APPEND,
            0o600,
        )
        try:
            os.write(descriptor, (json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8"))
        finally:
            os.close(descriptor)
    except OSError:
        pass


def _write_shift_alarm_mute(muted):
    SHIFT_ALARM_MUTE_FILE.parent.mkdir(parents=True, exist_ok=True)
    temporary = SHIFT_ALARM_MUTE_FILE.with_suffix(".tmp")
    temporary.write_text(json.dumps({"muted": bool(muted)}, ensure_ascii=False), encoding="utf-8")
    temporary.replace(SHIFT_ALARM_MUTE_FILE)


def _read_shift_alarm_wake_volume():
    try:
        payload = json.loads(SHIFT_ALARM_WAKE_VOLUME_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    percent = payload.get("percent")
    percent = max(0, min(100, int(percent))) if isinstance(percent, (int, float)) else 80
    return {"enabled": bool(payload.get("enabled")), "percent": percent}


def _write_shift_alarm_wake_volume(enabled, percent):
    percent = max(0, min(100, int(percent)))
    SHIFT_ALARM_WAKE_VOLUME_FILE.parent.mkdir(parents=True, exist_ok=True)
    temporary = SHIFT_ALARM_WAKE_VOLUME_FILE.with_suffix(".tmp")
    temporary.write_text(
        json.dumps({"enabled": bool(enabled), "percent": percent}, ensure_ascii=False),
        encoding="utf-8",
    )
    temporary.replace(SHIFT_ALARM_WAKE_VOLUME_FILE)
    return {"enabled": bool(enabled), "percent": percent}


def _reminder_display_label(label):
    """리마인더 이름 끝의 반복 설명은 제목에서 떼어 편집 UI의 규칙 칸으로
    보낸다. 원본 label은 Shift Alarm 체크 상태 연결을 위해 그대로 보존한다."""
    value = str(label or "").strip()
    match = re.search(r"\(([^()]*(?:일|주|월|회|근무)[^()]*)\)\s*$", value)
    if not match:
        return value, "자동 계산"
    rule = match.group(1).strip()
    normalized = rule
    replacements = {
        "월 1회": "약 30일에 1회", "매월 1회": "약 30일에 1회",
        "주 1회": "7일에 1회", "매주 1회": "7일에 1회", "1주일에 1회": "7일에 1회",
    }
    normalized = replacements.get(rule, normalized)
    day_match = re.fullmatch(r"(\d+)일(?:에)?\s*1회", normalized)
    if day_match:
        normalized = f"{int(day_match.group(1))}일에 1회"
    return value[:match.start()].rstrip(), normalized


def _reminder_recurrence_due(recurrence, day):
    """웹 편집 직후 고정 일·주·월 주기의 오늘 실행 여부를 즉시 계산한다."""
    if not isinstance(recurrence, dict) or not isinstance(day, datetime.date):
        return None
    try:
        anchor = datetime.date.fromisoformat(str(recurrence.get("anchor")))
        interval = max(1, int(recurrence.get("interval", 1)))
    except (TypeError, ValueError):
        return None
    if day < anchor:
        return False
    unit = recurrence.get("unit")
    if unit == "once":
        return day == anchor
    if unit == "daily":
        return True
    if unit == "days":
        return (day - anchor).days % interval == 0
    if unit == "weeks":
        return (day - anchor).days % (interval * 7) == 0
    if unit == "months":
        month_delta = (day.year - anchor.year) * 12 + day.month - anchor.month
        return month_delta >= 0 and month_delta % interval == 0 and day.day == anchor.day
    return None


def _next_reminder_recurrence_date(recurrence, start, horizon_days=400):
    for offset in range(max(1, horizon_days)):
        candidate = start + datetime.timedelta(days=offset)
        if _reminder_recurrence_due(recurrence, candidate) is True:
            return candidate.isoformat()
    return None


def _fixed_day_reminder_interval(item):
    recurrence = item.get("recurrence") if isinstance(item, dict) else None
    if isinstance(recurrence, dict) and recurrence.get("unit") == "days":
        try:
            return max(1, int(recurrence.get("interval", 1)))
        except (TypeError, ValueError):
            pass
    for value in (item.get("default_recurrence_text"), item.get("label")):
        match = re.search(r"(?<!\d)(\d+)\s*일(?:에)?\s*1회", str(value or ""))
        if match:
            return max(1, int(match.group(1)))
    return None


def _label_with_fixed_day_interval(label, interval):
    value = str(label or "").strip()
    pattern = r"\(\s*\d+\s*일(?:에)?\s*1회\s*\)\s*$"
    if re.search(pattern, value):
        return re.sub(pattern, f"({interval}일에 1회)", value)
    return value


def _merge_reminder_editor(status):
    editor_payload = _read_reminder_editor()
    editor = editor_payload["items"]
    active_occurrences = [
        item for item in editor_payload.get("occurrences", [])
        if isinstance(item, dict) and item.get("active", True)
    ]
    schedule = []
    seen = set()
    for source in status.get("reminder_schedule", []):
        if not isinstance(source, dict) or not source.get("key"):
            continue
        key = source["key"]
        override = editor.get(key, {}) if isinstance(editor.get(key), dict) else {}
        if override.get("deleted"):
            continue
        item = dict(source)
        display_label, default_recurrence_text = _reminder_display_label(item.get("label"))
        item["display_label"] = display_label
        item["default_recurrence_text"] = item.get("default_recurrence_text") or default_recurrence_text
        item.update({field: override[field] for field in
                     ("label", "enabled", "recurrence", "custom", "adaptive_adjustment_id")
                     if field in override})
        if "label" in override:
            item["display_label"], _ = _reminder_display_label(override["label"])
        if isinstance(override.get("time"), dict):
            hour, minute = override["time"].get("hour"), override["time"].get("minute")
            if isinstance(hour, int) and isinstance(minute, int):
                item["time"] = f"{hour:02d}:{minute:02d}"
                item.setdefault("times", {})["시각"] = item["time"]
        if isinstance(override.get("profile_times"), dict):
            for profile, value in override["profile_times"].items():
                if profile not in SHIFT_ALARM_TIME_PROFILES or not isinstance(value, dict):
                    continue
                hour, minute = value.get("hour"), value.get("minute")
                if isinstance(hour, int) and isinstance(minute, int):
                    item.setdefault("times", {})[profile] = f"{hour:02d}:{minute:02d}"
        try:
            status_date = datetime.date.fromisoformat(str(status.get("date") or status.get("routine_date")))
        except ValueError:
            status_date = None
        if status_date and item.get("recurrence"):
            item["next_date"] = _next_reminder_recurrence_date(item["recurrence"], status_date)
        schedule.append(item)
        seen.add(key)
    for key, override in editor.items():
        if key in seen or not isinstance(override, dict) or override.get("deleted"):
            continue
        reminder_time = override.get("time", {})
        value = (f"{reminder_time.get('hour', 0):02d}:{reminder_time.get('minute', 0):02d}"
                 if isinstance(reminder_time, dict) else None)
        custom_item = {
            "key": key, "label": override.get("label", key), "time": value,
            "display_label": override.get("label", key), "default_recurrence_text": "사용자 지정",
            "times": {"시각": value}, "enabled": bool(override.get("enabled", True)),
            "recurrence": override.get("recurrence"), "custom": True,
        }
        try:
            custom_status_date = datetime.date.fromisoformat(
                str(status.get("date") or status.get("routine_date"))
            )
        except ValueError:
            custom_status_date = None
        if custom_status_date and custom_item.get("recurrence"):
            custom_item["next_date"] = _next_reminder_recurrence_date(
                custom_item["recurrence"], custom_status_date
            )
        schedule.append(custom_item)
    status["reminder_schedule"] = schedule
    try:
        status_date = datetime.date.fromisoformat(str(status.get("date") or status.get("routine_date")))
    except ValueError:
        status_date = None
    if status_date and isinstance(status.get("reminders_detailed"), list):
        original_details = [item for item in status["reminders_detailed"] if isinstance(item, dict)]
        original_by_key = {item.get("key"): item for item in original_details if item.get("key")}
        original_by_label = {item.get("label"): item for item in original_details if item.get("label")}
        effective_details = []
        for item in schedule:
            source = original_by_key.get(item.get("key")) or original_by_label.get(item.get("label"))
            due = _reminder_recurrence_due(item.get("recurrence"), status_date)
            if not item.get("enabled", True) or due is False or (due is None and source is None):
                continue
            detail = dict(source or {})
            old_label = detail.get("label")
            detail.update({"key": item.get("key"), "label": item.get("label"),
                           "time": item.get("time")})
            if "checked" not in detail:
                detail["checked"] = bool(status.get("reminders_checked", {}).get(old_label, False))
            effective_details.append(detail)
        status["reminders_detailed"] = effective_details
        status["reminders"] = [item["label"] for item in effective_details]
        status["reminders_checked"] = {
            item["label"]: bool(item.get("checked")) for item in effective_details
        }
    if isinstance(status.get("shift_calendar"), list):
        schedule_by_key = {item.get("key"): item for item in schedule if item.get("key")}
        recalculated_keys = {
            key for key, override in editor.items()
            if isinstance(override, dict)
            and (override.get("deleted") or override.get("custom") or "recurrence" in override)
        }
        for calendar_day in status["shift_calendar"]:
            if not isinstance(calendar_day, dict):
                continue
            try:
                day = datetime.date.fromisoformat(str(calendar_day.get("date")))
            except ValueError:
                continue
            reminders = []
            for reminder in calendar_day.get("reminders", []):
                if not isinstance(reminder, dict) or reminder.get("key") in recalculated_keys:
                    continue
                merged = dict(reminder)
                source = schedule_by_key.get(merged.get("key"))
                if source:
                    merged.update({"label": source.get("label"), "time": source.get("time")})
                reminders.append(merged)
            for key in recalculated_keys:
                source = schedule_by_key.get(key)
                if not source or not source.get("enabled", True):
                    continue
                if _reminder_recurrence_due(source.get("recurrence"), day) is not True:
                    continue
                reminders.append({
                    "key": key,
                    "label": source.get("label"),
                    "time": source.get("time"),
                    "checked": bool(status.get("reminders_checked", {}).get(source.get("label"), False))
                    if day == status_date else False,
                })
            calendar_day["reminders"] = sorted(
                reminders, key=lambda item: item.get("time") or "99:99"
            )
        calendar_by_date = {
            item.get("date"): item for item in status["shift_calendar"]
            if isinstance(item, dict) and item.get("date")
        }
        for occurrence in active_occurrences:
            calendar_day = calendar_by_date.get(occurrence.get("scheduled_date"))
            source = schedule_by_key.get(occurrence.get("key"))
            if not calendar_day or not source:
                continue
            reminders = calendar_day.setdefault("reminders", [])
            reminder = next(
                (item for item in reminders if item.get("key") == occurrence.get("key")), None
            )
            if reminder is None:
                reminder = {
                    "key": occurrence.get("key"), "label": source.get("label"),
                    "time": source.get("time"),
                }
                reminders.append(reminder)
            reminder.update({
                "checked": True,
                "adaptive_adjustment_id": occurrence.get("id"),
                "completed_date": occurrence.get("completed_date"),
                "old_interval": occurrence.get("old_interval"),
                "new_interval": occurrence.get("new_interval"),
                "next_date": occurrence.get("next_date"),
            })
            reminders.sort(key=lambda item: item.get("time") or "99:99")
    return status


def _shift_alarm_notion_token():
    try:
        result = subprocess.run(
            ["security", "find-generic-password", "-a", os.environ.get("USER", ""),
             "-s", "jp_subtitle_notion_token", "-w"],
            capture_output=True, text=True, timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise HTTPException(status_code=503, detail="Notion 연결 정보를 불러올 수 없습니다") from exc
    if result.returncode != 0 or not result.stdout.strip():
        raise HTTPException(status_code=503, detail="Notion 연결 정보를 불러올 수 없습니다")
    return result.stdout.strip()


def _notion_request(token, path, method="GET", payload=None):
    request = urllib.request.Request(
        f"https://api.notion.com/v1/{path}", method=method,
        data=json.dumps(payload).encode("utf-8") if payload is not None else None,
        headers={
            "Authorization": f"Bearer {token}", "Notion-Version": NOTION_VERSION,
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.load(response)
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=502, detail="Notion에 변경을 반영하지 못했습니다") from exc


def _notion_text(block):
    block_type = block.get("type", "")
    return "".join(
        item.get("plain_text", "")
        for item in block.get(block_type, {}).get("rich_text", [])
    ).strip()


def _notion_plain_text_cell(cell):
    """Notion GET rich_text에서 쓰기 가능한 필드와 기존 서식만 보존한다."""
    normalized = []
    for part in cell:
        part_type = part.get("type")
        value = part.get(part_type, {}) if part_type else {}
        if part_type == "text":
            value = {"content": value.get("content", part.get("plain_text", ""))}
            if part.get("text", {}).get("link"):
                value["link"] = part["text"]["link"]
        elif part_type not in {"mention", "equation"}:
            part_type = "text"
            value = {"content": part.get("plain_text", "")}
        item = {"type": part_type, part_type: value}
        if part.get("annotations"):
            item["annotations"] = part["annotations"]
        normalized.append(item)
    return normalized


class ReminderTimeUpdate(BaseModel):
    label: str
    time: Optional[str] = None
    profile: str = "시각"


class ReminderCheckUpdate(BaseModel):
    label: str
    checked: bool


class ReminderOccurrenceUpdate(BaseModel):
    scheduled_date: str
    completed_date: Optional[str] = None
    checked: bool
    adjustment_id: Optional[str] = None


class ReminderDefinitionUpdate(BaseModel):
    label: str
    time: str
    recurrence_unit: Optional[str] = None
    recurrence_interval: int = 1
    recurrence_anchor: Optional[str] = None
    enabled: bool = True
    profile: str = "시각"


class BudeugiSettingsUpdate(BaseModel):
    settings: dict[str, dict[str, Any]]


class BudeugiJournalCreate(BaseModel):
    text: str


class BudeugiJournalUpdate(BaseModel):
    text: str


class BudeugiYinYangUpdate(BaseModel):
    yin: str = ""
    yang: str = ""


class BudeugiJournalAnalysisUpdate(BaseModel):
    cherished: str
    threat: str
    necessity: str
    benefit: str
    cost: str
    next_shape: str


SHIFT_ALARM_TIME_PROFILES = {"시각", "Swing", "Day", "GY", "S-D휴", "D-G휴", "G-S휴", "S-G휴"}


@app.get("/api/shift-alarm/status")
def shift_alarm_status(request: Request):
    _require_owner(request)
    status = _read_shift_alarm_status()
    try:
        dismissed = json.loads(SHIFT_ALARM_DISMISSED_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        dismissed = {}
    hidden = set(dismissed.get(status.get("date"), []))
    if hidden:
        status["reminders"] = [label for label in status.get("reminders", []) if label not in hidden]
        status["reminders_checked"] = {
            label: checked for label, checked in status.get("reminders_checked", {}).items()
            if label not in hidden
        }
        status["reminders_detailed"] = [
            item for item in status.get("reminders_detailed", []) if item.get("label") not in hidden
        ]
    return _merge_reminder_editor(status)


def _dating_briefing_text(value: Any) -> str:
    """미연시 원문 표기를 팝업에서 읽기 좋은 평문으로 정리한다."""
    text = re.sub(r"\[([^|\]]+)\|[^\]]+\]", r"\1", str(value or ""))
    return re.sub(r"\s+", " ", text).strip()


def _dating_briefing_material(item: Any) -> str:
    if isinstance(item, dict):
        japanese = item.get("word") or item.get("ja") or item.get("text") or item.get("expression")
        korean = item.get("meaning") or item.get("ko") or item.get("translation")
        if japanese and korean:
            return f"{_dating_briefing_text(japanese)} — {_dating_briefing_text(korean)}"
        return _dating_briefing_text(japanese or korean)
    return _dating_briefing_text(item)


@app.get("/api/shift-alarm/dating-scene-briefing")
def shift_alarm_dating_scene_briefing(request: Request):
    """오늘 퀘스트 팝업에 실제 진행 중인 미연시 장면을 제공한다."""
    _require_owner(request)
    username = _request_username(request)
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM dating_sim_progress WHERE username=? "
            "ORDER BY CASE WHEN completed=0 AND pending_location IS NOT NULL THEN 0 "
            "WHEN completed=0 THEN 1 ELSE 2 END, updated_at DESC LIMIT 1",
            (username,),
        ).fetchone()
        if not row:
            return {
                "available": False,
                "message": "아직 진행 중인 미연시가 없습니다.",
                "url": "/dating-sim/?write=1",
            }
        row = dict(row)
        story_id = str(row.get("character_id") or "")
        story = _dating_story(
            None if story_id == dating_sim_story.CHARACTER_ID else story_id,
            username,
        )
        state = _dating_sim_state_payload(row, story, username, True, False)
        completion = conn.execute(
            "SELECT created_at,average_score FROM dating_sim_writing_completions "
            "WHERE username=? AND completed_date=? AND story_id=? AND day=? "
            "ORDER BY created_at DESC LIMIT 1",
            (username, datetime.date.today().isoformat(), state["story_id"], state["day"]),
        ).fetchone()
    finally:
        conn.close()

    scene = state.get("scene") or {}
    location = next(
        (item for item in state.get("locations", []) if item.get("id") == state.get("pending_location")),
        {},
    )
    lines = []
    for line in scene.get("lines", []):
        text = _dating_briefing_text(line.get("text"))
        if text:
            lines.append({"speaker": line.get("speaker", "character"), "text": text})
    dialogue = [line for line in lines if line["speaker"] != "narrator"][-3:]
    narration = [line["text"] for line in lines if line["speaker"] == "narrator"]
    materials = [
        material for material in (
            _dating_briefing_material(item)
            for item in [*scene.get("vocab_words", []), *scene.get("expressions_used", [])]
        ) if material
    ][:4]
    book_id = state["story_id"].removeprefix("book:") if state["story_id"].startswith("book:") else ""
    deep_link = f"/dating-sim/?book={book_id}&write=1" if re.fullmatch(r"[0-9a-f]{20}", book_id) else "/dating-sim/?write=1"
    character = state.get("character_name_ko") or state.get("character_name") or "상대 인물"
    has_scene = bool(scene)
    situation = _dating_briefing_text(state.get("day_opening"))
    if narration:
        situation = " ".join(filter(None, [situation, narration[-1]]))
    if not situation:
        situation = (
            f"{location.get('label', '다음 장소')}에서 이어질 장면을 준비하고 있습니다."
            if has_scene else "먼저 오늘 만날 장소를 고르면 실제 장면이 열립니다."
        )
    return {
        "available": True,
        "has_scene": has_scene,
        "completed_today": bool(completion),
        "completed_at": completion["created_at"] if completion else None,
        "average_score": completion["average_score"] if completion else None,
        "story_id": state["story_id"],
        "story_title": state.get("story_title") or state.get("source_title") or "미연시",
        "source_title": state.get("source_title"),
        "character": character,
        "day": state["day"],
        "total_days": state["total_days"],
        "affection": state["affection"],
        "relationship": state.get("relationship_tone") or {},
        "location": location.get("label") or state.get("pending_location") or "장소 선택 대기",
        "situation": situation,
        "dialogue": dialogue,
        "writing_goal": (
            f"{character}의 현재 장면 대사 {len(dialogue) or 1}개를 듣고 직접 써서 채점을 완료하세요."
            if has_scene else "미연시에서 오늘 만날 장소를 선택한 뒤 한 장면의 대사를 직접 쓰세요."
        ),
        "hint": materials,
        "url": deep_link,
    }


@app.get("/api/shift-alarm/budeugi-settings")
def get_shift_alarm_budeugi_settings(request: Request):
    _require_owner(request)
    try:
        payload = json.loads(SHIFT_ALARM_BUDEUGI_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        payload = {}
    return {"settings": payload if isinstance(payload, dict) else {}}


def _read_shift_alarm_budeugi_journal() -> list[dict[str, Any]]:
    try:
        payload = json.loads(SHIFT_ALARM_BUDEUGI_JOURNAL_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(payload, list):
        return []
    return [item for item in payload if isinstance(item, dict)]


def _write_shift_alarm_budeugi_journal(items: list[dict[str, Any]]) -> None:
    SHIFT_ALARM_BUDEUGI_JOURNAL_FILE.parent.mkdir(parents=True, exist_ok=True)
    temporary = SHIFT_ALARM_BUDEUGI_JOURNAL_FILE.with_suffix(".tmp")
    temporary.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(SHIFT_ALARM_BUDEUGI_JOURNAL_FILE)


def _clean_budeugi_journal_text(text: str) -> str:
    cleaned = str(text or "").strip()
    if not cleaned:
        raise HTTPException(status_code=400, detail="기록할 부득이 상황을 입력해주세요")
    if len(cleaned) > 5000:
        raise HTTPException(status_code=400, detail="한 기록은 5,000자까지 저장할 수 있습니다")
    return cleaned


def _clean_budeugi_yin_yang(yin: str, yang: str) -> tuple[str, str]:
    cleaned_yin = str(yin or "").strip()
    cleaned_yang = str(yang or "").strip()
    if not cleaned_yin and not cleaned_yang:
        raise HTTPException(status_code=400, detail="음과 양 중 하나 이상을 입력해주세요")
    if len(cleaned_yin) > 5000 or len(cleaned_yang) > 5000:
        raise HTTPException(status_code=400, detail="음과 양은 각각 5,000자까지 저장할 수 있습니다")
    return cleaned_yin, cleaned_yang


BUDEUGI_ANALYSIS_FIELDS = ("cherished", "threat", "necessity", "benefit", "cost", "next_shape")


def _clean_budeugi_analysis(payload: dict[str, Any]) -> dict[str, str]:
    cleaned = {}
    for field in BUDEUGI_ANALYSIS_FIELDS:
        value = re.sub(r"\s+", " ", str(payload.get(field, ""))).strip()
        if not value:
            raise ValueError(f"{field} 분석이 비어 있습니다")
        cleaned[field] = value[:1000]
    return cleaned


def _parse_budeugi_analysis(raw: str) -> dict[str, str]:
    text = str(raw or "").strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL | re.IGNORECASE)
    if fenced:
        text = fenced.group(1)
    else:
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            text = text[start:end + 1]
    return _clean_budeugi_analysis(json.loads(text))


def _generate_budeugi_analysis(text: str, username: str) -> tuple[dict[str, str], str]:
    prompt = f"""당신은 손자병법의 '先其所愛(선기소애)'와 '凡地之利 勿考以害(범지지리 물고이해)' 관점으로 일상 기록을 해석한다.
사용자를 겁주거나 도덕적으로 평가하지 말고, 기록에 실제로 적힌 내용만 근거로 삼아라.
소애가 둘 이상 충돌하면 그 충돌을 선명하게 적고, 마지막 제안은 의지나 인내가 아니라 환경과 순서를 조금 조정하는 현실적인 '형세'여야 한다.

[사용자 기록]
{text}

아래 키를 정확히 가진 JSON 객체 하나만 출력하라. 각 값은 쉽고 구체적인 한국어 1~2문장으로 쓴다.
{{
  "cherished": "所愛 · 사용자가 실제로 지키려는 것",
  "threat": "危 · 그것을 위태롭게 하거나 흐름을 깨뜨린 조건",
  "necessity": "不得已 · 하지 않을 수 없게 된 행동과 이유",
  "benefit": "利 · 그 행동이 준 현실적인 이득",
  "cost": "害 · 함께 생긴 반작용이나 대가",
  "next_shape": "다음 형세 · 소애는 지키고 반작용은 줄이는 작은 환경 조정"
}}"""
    conn = get_conn()
    row = conn.execute(
        """SELECT u.ai_provider, c.encrypted_key
           FROM users u LEFT JOIN user_ai_credentials c
             ON c.username=u.username AND c.provider=u.ai_provider
           WHERE u.username=?""",
        (username,),
    ).fetchone()
    conn.close()
    if row and row["ai_provider"] and row["encrypted_key"]:
        raw, engine = run_provider_api(
            row["ai_provider"], ai_keys.decrypt_key(row["encrypted_key"]), prompt, timeout=120,
        )
    else:
        raw, engine = run_ai_exec(
            prompt, BASE_DIR, timeout=180, primary="codex",
            validator=lambda output: _budeugi_analysis_is_valid(output), fallback=True,
        )
    return _parse_budeugi_analysis(raw), engine


def _budeugi_analysis_is_valid(raw: str) -> bool:
    try:
        _parse_budeugi_analysis(raw)
        return True
    except (ValueError, TypeError, json.JSONDecodeError):
        return False


@app.get("/api/shift-alarm/budeugi-journal")
def get_shift_alarm_budeugi_journal(request: Request):
    _require_owner(request)
    return {"items": _read_shift_alarm_budeugi_journal()}


@app.post("/api/shift-alarm/budeugi-journal")
def create_shift_alarm_budeugi_journal(body: BudeugiJournalCreate, request: Request):
    _require_owner(request)
    now = datetime.datetime.now(datetime.timezone.utc).astimezone().isoformat(timespec="seconds")
    item = {"id": uuid.uuid4().hex, "text": _clean_budeugi_journal_text(body.text),
            "created_at": now, "updated_at": now}
    items = _read_shift_alarm_budeugi_journal()
    items.insert(0, item)
    _write_shift_alarm_budeugi_journal(items[:1000])
    return {"ok": True, "item": item, "items": items[:1000]}


@app.post("/api/shift-alarm/budeugi-journal/yin-yang")
def create_shift_alarm_budeugi_yin_yang(body: BudeugiYinYangUpdate, request: Request):
    _require_owner(request)
    yin, yang = _clean_budeugi_yin_yang(body.yin, body.yang)
    now = datetime.datetime.now(datetime.timezone.utc).astimezone().isoformat(timespec="seconds")
    item = {"id": uuid.uuid4().hex, "kind": "yin_yang", "yin": yin, "yang": yang,
            "created_at": now, "updated_at": now}
    items = _read_shift_alarm_budeugi_journal()
    items.insert(0, item)
    _write_shift_alarm_budeugi_journal(items[:1000])
    return {"ok": True, "item": item, "items": items[:1000]}


@app.put("/api/shift-alarm/budeugi-journal/{entry_id}/yin-yang")
def update_shift_alarm_budeugi_yin_yang(
    entry_id: str, body: BudeugiYinYangUpdate, request: Request,
):
    _require_owner(request)
    items = _read_shift_alarm_budeugi_journal()
    item = next((candidate for candidate in items if candidate.get("id") == entry_id), None)
    if not item or item.get("kind") != "yin_yang":
        raise HTTPException(status_code=404, detail="음양 대칭 기록을 찾을 수 없습니다")
    yin, yang = _clean_budeugi_yin_yang(body.yin, body.yang)
    item.update({"yin": yin, "yang": yang})
    item["updated_at"] = datetime.datetime.now(datetime.timezone.utc).astimezone().isoformat(timespec="seconds")
    _write_shift_alarm_budeugi_journal(items)
    return {"ok": True, "item": item, "items": items}


@app.put("/api/shift-alarm/budeugi-journal/{entry_id}")
def update_shift_alarm_budeugi_journal(entry_id: str, body: BudeugiJournalUpdate, request: Request):
    _require_owner(request)
    items = _read_shift_alarm_budeugi_journal()
    item = next((candidate for candidate in items if candidate.get("id") == entry_id), None)
    if not item:
        raise HTTPException(status_code=404, detail="부득이 기록을 찾을 수 없습니다")
    if item.get("kind") == "yin_yang":
        raise HTTPException(status_code=400, detail="음양 대칭 기록은 음양 수정 API를 이용해주세요")
    item["text"] = _clean_budeugi_journal_text(body.text)
    item["updated_at"] = datetime.datetime.now(datetime.timezone.utc).astimezone().isoformat(timespec="seconds")
    item.pop("analysis", None)
    item.pop("analyzed_at", None)
    item.pop("analysis_engine", None)
    _write_shift_alarm_budeugi_journal(items)
    return {"ok": True, "item": item, "items": items}


@app.delete("/api/shift-alarm/budeugi-journal/{entry_id}")
def delete_shift_alarm_budeugi_journal(entry_id: str, request: Request):
    _require_owner(request)
    items = _read_shift_alarm_budeugi_journal()
    remaining = [item for item in items if item.get("id") != entry_id]
    if len(remaining) == len(items):
        raise HTTPException(status_code=404, detail="부득이 기록을 찾을 수 없습니다")
    _write_shift_alarm_budeugi_journal(remaining)
    return {"ok": True, "items": remaining}


@app.post("/api/shift-alarm/budeugi-journal/{entry_id}/analysis")
async def analyze_shift_alarm_budeugi_journal(entry_id: str, request: Request):
    _require_owner(request)
    items = _read_shift_alarm_budeugi_journal()
    item = next((candidate for candidate in items if candidate.get("id") == entry_id), None)
    if not item:
        raise HTTPException(status_code=404, detail="부득이 기록을 찾을 수 없습니다")
    if item.get("kind") == "yin_yang":
        raise HTTPException(status_code=400, detail="음양 대칭 기록은 선기소애 해석 대상이 아닙니다")
    username = _request_username(request)
    try:
        analysis, engine = await asyncio.to_thread(_generate_budeugi_analysis, item.get("text", ""), username)
    except Exception as error:
        print(f"❌ 부득이 선기소애 분석 실패: {type(error).__name__}: {error}", flush=True)
        raise HTTPException(status_code=502, detail="선기소애 분석을 만들지 못했습니다. 잠시 후 다시 시도해주세요") from error
    item["analysis"] = analysis
    item["analysis_engine"] = engine
    item["analyzed_at"] = datetime.datetime.now(datetime.timezone.utc).astimezone().isoformat(timespec="seconds")
    _write_shift_alarm_budeugi_journal(items)
    return {"ok": True, "item": item, "items": items}


@app.put("/api/shift-alarm/budeugi-journal/{entry_id}/analysis")
def update_shift_alarm_budeugi_analysis(entry_id: str, body: BudeugiJournalAnalysisUpdate, request: Request):
    _require_owner(request)
    items = _read_shift_alarm_budeugi_journal()
    item = next((candidate for candidate in items if candidate.get("id") == entry_id), None)
    if not item:
        raise HTTPException(status_code=404, detail="부득이 기록을 찾을 수 없습니다")
    try:
        item["analysis"] = _clean_budeugi_analysis(body.dict())
    except ValueError as error:
        raise HTTPException(status_code=400, detail="분석 항목을 모두 입력해주세요") from error
    item["analysis_engine"] = "manual"
    item["analyzed_at"] = datetime.datetime.now(datetime.timezone.utc).astimezone().isoformat(timespec="seconds")
    _write_shift_alarm_budeugi_journal(items)
    return {"ok": True, "item": item, "items": items}


def _shift_alarm_budeugi_tts_path(text: str) -> Path:
    digest = hashlib.sha256(
        f"budeugi-tts-v2\0{SHIFT_ALARM_BUDEUGI_TTS_VOICE}\0{text}".encode("utf-8")
    ).hexdigest()[:24]
    return SHIFT_ALARM_BUDEUGI_AUDIO_DIR / f"{digest}.mp3"


def _shift_alarm_macos_say_mp3(text: str, target: Path) -> None:
    """Edge TTS 장애 시에도 휴대폰에서 재생할 수 있는 MP3를 로컬로 만든다."""
    # launchd로 실행된 서버는 Homebrew 경로가 PATH에 없을 수 있다.
    # 인터랙티브 쉘에서만 성공하는 대체 경로가 되지 않도록 일반적인
    # Apple Silicon/Intel Homebrew 위치를 명시적으로 확인한다.
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        ffmpeg = next((str(path) for path in (
            Path("/opt/homebrew/bin/ffmpeg"),
            Path("/usr/local/bin/ffmpeg"),
        ) if path.is_file()), None)
    if not ffmpeg:
        raise RuntimeError("ffmpeg를 찾을 수 없습니다")
    target.parent.mkdir(parents=True, exist_ok=True)
    aiff = target.with_suffix(".aiff")
    temporary = target.with_suffix(".mp3.tmp")
    try:
        spoken = subprocess.run(
            ["/usr/bin/say", "-v", "Yuna", "-o", str(aiff), text],
            capture_output=True, text=True, timeout=120,
        )
        if spoken.returncode != 0 or not aiff.is_file() or not aiff.stat().st_size:
            raise RuntimeError(spoken.stderr.strip() or "macOS say가 음성을 만들지 못했습니다")
        converted = subprocess.run(
            [ffmpeg, "-nostdin", "-loglevel", "error", "-y", "-i", str(aiff),
             "-codec:a", "libmp3lame", "-q:a", "3", "-f", "mp3", str(temporary)],
            capture_output=True, text=True, timeout=120,
        )
        if (converted.returncode != 0 or not temporary.is_file()
                or temporary.stat().st_size < 2048):
            raise RuntimeError(converted.stderr.strip() or "MP3 변환에 실패했습니다")
        temporary.replace(target)
    finally:
        aiff.unlink(missing_ok=True)
        temporary.unlink(missing_ok=True)


@app.get("/api/shift-alarm/budeugi-tts")
async def shift_alarm_budeugi_tts(
    request: Request,
    text: str = Query(min_length=1, max_length=3000),
):
    """부득이 미리 듣기용 SunHiNeural 음성을 생성하고 같은 문장은 캐시한다."""
    _require_owner(request)
    cleaned = re.sub(r"\s+", " ", text).strip()
    if not cleaned:
        raise HTTPException(status_code=400, detail="읽을 시나리오가 없습니다")
    target = _shift_alarm_budeugi_tts_path(cleaned)

    def ensure_clip():
        if target.is_file() and target.stat().st_size:
            return
        with _dating_sim_tts_lock:
            if target.is_file() and target.stat().st_size:
                return
            try:
                audio = dating_audio.request_edge_speech(
                    "female", cleaned, voice=SHIFT_ALARM_BUDEUGI_TTS_VOICE, language="ko"
                )
                target.parent.mkdir(parents=True, exist_ok=True)
                temporary = target.with_suffix(".mp3.tmp")
                temporary.write_bytes(audio)
                temporary.replace(target)
            except Exception as edge_error:
                print(
                    f"⚠️ 부득이 Edge TTS 실패, macOS Yuna로 전환: {edge_error}",
                    flush=True,
                )
                _shift_alarm_macos_say_mp3(cleaned, target)

    try:
        await asyncio.to_thread(ensure_clip)
    except Exception as error:
        print(f"❌ 부득이 TTS 대체 음성 생성 실패: {error}", flush=True)
        raise HTTPException(status_code=502, detail="SunHi 음성을 생성하지 못했습니다") from error
    return FileResponse(
        str(target), media_type="audio/mpeg",
        headers={"Cache-Control": "private, max-age=31536000"},
    )


@app.put("/api/shift-alarm/budeugi-settings")
def set_shift_alarm_budeugi_settings(body: BudeugiSettingsUpdate, request: Request):
    _require_owner(request)
    allowed_themes = {"auto", "war", "disaster", "sea_crash", "relief_spy", "espionage", "expedition"}
    allowed_intensities = {"strong", "urgent", "quiet"}
    cleaned = {}
    for label, setting in body.settings.items():
        if not isinstance(label, str) or not label.strip() or len(label) > 120 or not isinstance(setting, dict):
            continue
        theme = str(setting.get("theme", "auto"))
        intensity = str(setting.get("intensity", "strong"))
        custom = str(setting.get("custom", "")).strip()[:3000]
        story = str(setting.get("story", "")).strip()[:3000]
        cleaned[label] = {
            "theme": theme if theme in allowed_themes else "auto",
            "intensity": intensity if intensity in allowed_intensities else "strong",
            "custom": custom,
            "story": story,
        }
    SHIFT_ALARM_BUDEUGI_FILE.parent.mkdir(parents=True, exist_ok=True)
    temporary = SHIFT_ALARM_BUDEUGI_FILE.with_suffix(".tmp")
    temporary.write_text(json.dumps(cleaned, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(SHIFT_ALARM_BUDEUGI_FILE)
    return {"ok": True, "settings": cleaned}


@app.get("/api/shift-alarm/mute")
def get_shift_alarm_mute(request: Request):
    _require_owner(request)
    return _read_shift_alarm_mute()


class ShiftAlarmMuteRequest(BaseModel):
    muted: bool


@app.put("/api/shift-alarm/mute")
def set_shift_alarm_mute(body: ShiftAlarmMuteRequest, request: Request):
    _require_owner(request)
    _write_shift_alarm_mute(body.muted)
    return {"ok": True, "muted": body.muted}


@app.get("/api/shift-alarm/wake-volume")
def get_shift_alarm_wake_volume(request: Request):
    _require_owner(request)
    return _read_shift_alarm_wake_volume()


class ShiftAlarmWakeVolumeRequest(BaseModel):
    enabled: bool
    percent: int


@app.put("/api/shift-alarm/wake-volume")
def set_shift_alarm_wake_volume(body: ShiftAlarmWakeVolumeRequest, request: Request):
    _require_owner(request)
    if not 0 <= body.percent <= 100:
        raise HTTPException(status_code=422, detail="음량은 0~100 사이여야 합니다")
    return {"ok": True, **_write_shift_alarm_wake_volume(body.enabled, body.percent)}


@app.get("/api/shift-alarm/log")
def get_shift_alarm_log(request: Request, lines: int = 200):
    """CPU 과부하 자동종료 등 shift_alarm.py의 print() 출력을 그대로 보여준다
    — launchd가 stdout을 이 파일로 리다이렉트하므로 웹앱에서 tail만 하면 된다."""
    _require_owner(request)
    count = max(1, min(lines, 1000))
    try:
        text = SHIFT_ALARM_OUT_LOG_FILE.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {"lines": []}
    all_lines = [line for line in text.split("\n") if line]
    return {"lines": all_lines[-count:]}


def _validated_reminder_definition(body):
    label = body.label.strip()
    if not label or len(label) > 80:
        raise HTTPException(status_code=422, detail="리마인더 이름은 1~80자로 입력해주세요")
    if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", body.time or ""):
        raise HTTPException(status_code=422, detail="시각은 HH:MM 형식이어야 합니다")
    if body.recurrence_unit not in {
        None, "once", "daily", "days", "weeks", "months",
        "off_block_start", "off_block_end", "day_shift_block_end",
    }:
        raise HTTPException(status_code=422, detail="지원하지 않는 반복 주기입니다")
    if not 1 <= body.recurrence_interval <= 365:
        raise HTTPException(status_code=422, detail="반복 간격은 1~365 사이여야 합니다")
    recurrence = None
    if body.recurrence_unit:
        try:
            anchor = datetime.date.fromisoformat(body.recurrence_anchor or "")
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="반복 시작일을 선택해주세요") from exc
        recurrence = {"unit": body.recurrence_unit, "interval": body.recurrence_interval,
                      "anchor": anchor.isoformat()}
    hour, minute = (int(part) for part in body.time.split(":"))
    return {"label": label, "time": {"hour": hour, "minute": minute},
            "enabled": body.enabled, "recurrence": recurrence}


def _validated_iso_date(value, field_name):
    try:
        return datetime.date.fromisoformat(str(value or ""))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"{field_name} 날짜가 올바르지 않습니다") from exc


@app.put("/api/shift-alarm/reminder-occurrences/{key}")
def update_shift_alarm_reminder_occurrence(
    key: str, body: ReminderOccurrenceUpdate, request: Request,
):
    """예정일과 실제 완료일의 차이를 고정 일 주기 자체에 반영한다."""
    _require_owner(request)
    scheduled_date = _validated_iso_date(body.scheduled_date, "예정일")
    payload = _read_reminder_editor()
    occurrences = payload.setdefault("occurrences", [])
    current = payload["items"].get(key, {})
    current = dict(current) if isinstance(current, dict) else {}

    if not body.checked:
        adjustment_id = str(body.adjustment_id or current.get("adaptive_adjustment_id") or "")
        occurrence = next((
            item for item in reversed(occurrences)
            if isinstance(item, dict) and item.get("id") == adjustment_id
            and item.get("key") == key and item.get("active", True)
        ), None)
        if not occurrence or current.get("adaptive_adjustment_id") != adjustment_id:
            raise HTTPException(status_code=409, detail="가장 최근 주기 조정만 되돌릴 수 있습니다")
        if occurrence.get("previous_recurrence_present"):
            current["recurrence"] = occurrence.get("previous_recurrence")
        else:
            current.pop("recurrence", None)
        if occurrence.get("previous_label_present"):
            current["label"] = occurrence.get("previous_label")
        else:
            current.pop("label", None)
        previous_adjustment_id = occurrence.get("previous_adjustment_id")
        if previous_adjustment_id:
            current["adaptive_adjustment_id"] = previous_adjustment_id
        else:
            current.pop("adaptive_adjustment_id", None)
        occurrence["active"] = False
        occurrence["undone_at"] = datetime.datetime.now().isoformat(timespec="seconds")
        payload["items"][key] = current
        _write_reminder_editor(payload)
        return {
            "ok": True, "undone": True, "adjustment": occurrence,
            "status": _merge_reminder_editor(_read_shift_alarm_status()),
        }

    completed_date = _validated_iso_date(
        body.completed_date or datetime.date.today().isoformat(), "완료일"
    )
    status = _merge_reminder_editor(_read_shift_alarm_status())
    schedule_by_key = {
        item.get("key"): item for item in status.get("reminder_schedule", [])
        if isinstance(item, dict) and item.get("key")
    }
    source = schedule_by_key.get(key)
    if not source or source.get("auto_schedule"):
        raise HTTPException(status_code=404, detail="주기를 조정할 리마인더를 찾지 못했습니다")
    scheduled_item = next((
        reminder
        for day in status.get("shift_calendar", [])
        if isinstance(day, dict) and day.get("date") == scheduled_date.isoformat()
        for reminder in day.get("reminders", []) if reminder.get("key") == key
    ), None)
    if scheduled_item is None:
        raise HTTPException(status_code=409, detail="선택한 날짜에 예정된 리마인더가 아닙니다")
    if scheduled_item.get("checked"):
        raise HTTPException(status_code=409, detail="이미 완료 처리된 리마인더입니다")

    old_interval = _fixed_day_reminder_interval(source)
    if old_interval is None:
        raise HTTPException(status_code=422, detail="고정 일수 주기 리마인더만 자동 조정할 수 있습니다")
    delta_days = (completed_date - scheduled_date).days
    new_interval = old_interval + delta_days
    if not 1 <= new_interval <= 365:
        raise HTTPException(
            status_code=422,
            detail=f"날짜 차이를 반영한 주기({new_interval}일)는 1~365일이어야 합니다",
        )
    next_date = completed_date + datetime.timedelta(days=new_interval)
    adjustment_id = uuid.uuid4().hex
    occurrence = {
        "id": adjustment_id, "key": key, "label": source.get("label"),
        "scheduled_date": scheduled_date.isoformat(),
        "completed_date": completed_date.isoformat(),
        "completed_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "delta_days": delta_days, "old_interval": old_interval,
        "new_interval": new_interval, "next_date": next_date.isoformat(),
        "previous_recurrence_present": "recurrence" in current,
        "previous_recurrence": current.get("recurrence"),
        "previous_label_present": "label" in current,
        "previous_label": current.get("label"),
        "previous_adjustment_id": current.get("adaptive_adjustment_id"),
        "active": True,
    }
    current["recurrence"] = {
        "unit": "days", "interval": new_interval, "anchor": next_date.isoformat(),
    }
    adjusted_label = _label_with_fixed_day_interval(source.get("label"), new_interval)
    if adjusted_label:
        current["label"] = adjusted_label
    current["adaptive_adjustment_id"] = adjustment_id
    payload["items"][key] = current
    occurrences.append(occurrence)
    _write_reminder_editor(payload)
    return {
        "ok": True, "adjustment": occurrence,
        "status": _merge_reminder_editor(_read_shift_alarm_status()),
    }


@app.post("/api/shift-alarm/reminder-definitions")
def create_shift_alarm_reminder(body: ReminderDefinitionUpdate, request: Request):
    _require_owner(request)
    definition = _validated_reminder_definition(body)
    if not definition["recurrence"]:
        raise HTTPException(status_code=422, detail="새 리마인더의 반복 주기를 선택해주세요")
    payload = _read_reminder_editor()
    key = f"custom_{uuid.uuid4().hex[:12]}"
    payload["items"][key] = {**definition, "custom": True}
    _write_reminder_editor(payload)
    return {"ok": True, "key": key}


@app.put("/api/shift-alarm/reminder-definitions/{key}")
def update_shift_alarm_reminder(key: str, body: ReminderDefinitionUpdate, request: Request):
    _require_owner(request)
    status = _merge_reminder_editor(_read_shift_alarm_status())
    items = {item.get("key"): item for item in status.get("reminder_schedule", [])}
    if key not in items:
        raise HTTPException(status_code=404, detail="리마인더를 찾지 못했습니다")
    payload = _read_reminder_editor()
    source = items[key]
    if source.get("auto_schedule"):
        if body.profile not in SHIFT_ALARM_TIME_PROFILES or body.profile == "시각":
            raise HTTPException(status_code=422, detail="수정할 근무 유형을 선택해주세요")
        definition = _validated_reminder_definition(body)
        current = payload["items"].get(key, {})
        current = dict(current) if isinstance(current, dict) else {}
        current.setdefault("profile_times", {})[body.profile] = definition["time"]
        current["enabled"] = definition["enabled"]
        payload["items"][key] = current
        _write_reminder_editor(payload)
        refreshed = _merge_reminder_editor(_read_shift_alarm_status())
        return {"ok": True, "key": key, "profile": body.profile, "status": refreshed}
    current = payload["items"].get(key, {})
    current = dict(current) if isinstance(current, dict) else {}
    custom = bool(current.get("custom")) or key.startswith("custom_")
    definition = _validated_reminder_definition(body)
    # 기존 리마인더의 Day/Swing/GY 등 근무별 시각을 수정할 때 definition 전체를
    # 갈아끼우면 직전에 reminder-time API가 기록한 profile_times가 사라져 화면이
    # 예전 시각으로 되돌아왔다. 기본 시각과 근무별 시각을 서로 독립적으로 보존한다.
    profile_times = dict(current.get("profile_times", {})) if isinstance(current.get("profile_times"), dict) else {}
    if not custom and body.profile != "시각":
        profile_times[body.profile] = definition["time"]
        base_time = current.get("time")
        if not isinstance(base_time, dict):
            match = re.fullmatch(r"(\d{2}):(\d{2})", str(source.get("time") or ""))
            base_time = ({"hour": int(match.group(1)), "minute": int(match.group(2))}
                         if match else definition["time"])
        definition["time"] = base_time
    payload["items"][key] = {**current, **definition, "custom": custom}
    if profile_times:
        payload["items"][key]["profile_times"] = profile_times
    _write_reminder_editor(payload)
    refreshed = _merge_reminder_editor(_read_shift_alarm_status())
    updated_item = next((item for item in refreshed.get("reminder_schedule", [])
                         if item.get("key") == key), None)
    return {"ok": True, "key": key, "profile": body.profile, "time": body.time,
            "item": updated_item, "status": refreshed}


@app.delete("/api/shift-alarm/reminder-definitions/{key}")
def delete_shift_alarm_reminder_definition(key: str, request: Request):
    _require_owner(request)
    status = _merge_reminder_editor(_read_shift_alarm_status())
    allowed = {item.get("key") for item in status.get("reminder_schedule", [])}
    if key not in allowed:
        raise HTTPException(status_code=404, detail="리마인더를 찾지 못했습니다")
    payload = _read_reminder_editor()
    # 상태 파일은 Shift Alarm의 다음 갱신 전까지 이전 사용자 항목을 담고 있을
    # 수 있으므로 사용자 항목도 즉시 지우지 않고 tombstone을 남겨 재등장을 막는다.
    payload["items"][key] = {"deleted": True, "custom": key.startswith("custom_")}
    _write_reminder_editor(payload)
    return {"ok": True, "key": key}


@app.put("/api/shift-alarm/reminder-time")
def update_shift_alarm_reminder_time(body: ReminderTimeUpdate, request: Request):
    _require_owner(request)
    if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", body.time or ""):
        raise HTTPException(status_code=422, detail="시각은 HH:MM 형식이어야 합니다")
    status = _read_shift_alarm_status()
    allowed_labels = {
        item.get("label") for item in status.get("reminder_schedule", [])
        if isinstance(item, dict) and item.get("label")
    }
    if body.label not in allowed_labels:
        raise HTTPException(status_code=409, detail="Shift Alarm이 내보낸 리마인더만 수정할 수 있습니다")
    if body.profile not in SHIFT_ALARM_TIME_PROFILES:
        raise HTTPException(status_code=422, detail="알 수 없는 근무 유형입니다")

    token = _shift_alarm_notion_token()
    page = _notion_request(token, f"blocks/{SHIFT_ALARM_REMINDER_TIMES_PAGE_ID}/children?page_size=100")
    table = next((item for item in page.get("results", []) if item.get("type") == "table"), None)
    if not table:
        raise HTTPException(status_code=409, detail="Notion 리마인더 시각표를 찾지 못했습니다")
    rows = _notion_request(token, f"blocks/{table['id']}/children?page_size=100")
    table_rows = rows.get("results", [])
    if not table_rows:
        raise HTTPException(status_code=409, detail="Notion 시각표가 비어 있습니다")
    headers = ["".join(part.get("plain_text", "") for part in cell).strip()
               for cell in table_rows[0].get("table_row", {}).get("cells", [])]
    if body.profile not in headers:
        raise HTTPException(status_code=409, detail="Notion 시각표의 근무 유형 열을 찾지 못했습니다")
    column_index = headers.index(body.profile)
    target = next((row for row in table_rows[1:]
                   if row.get("type") == "table_row"
                   and row.get("table_row", {}).get("cells")
                   and "".join(part.get("plain_text", "") for part in row["table_row"]["cells"][0]).strip() == body.label), None)
    created = target is None
    if created:
        # Shift Alarm에는 있지만 Notion 시각표에 아직 행이 없는 리마인더도
        # 웹에서 바로 수정할 수 있어야 한다. 첫 저장 때 현재 표의 열 수에
        # 맞춘 행을 만든 뒤 선택한 근무 유형의 시각을 채운다.
        cells = [[] for _ in headers]
        cells[0] = [{"type": "text", "text": {"content": body.label}}]
        cells[column_index] = [{"type": "text", "text": {"content": body.time}}]
        _notion_request(token, f"blocks/{table['id']}/children", "PATCH", {
            "children": [{"object": "block", "type": "table_row",
                          "table_row": {"cells": cells}}],
        })
    else:
        cells = [_notion_plain_text_cell(cell) for cell in target["table_row"]["cells"]]
        while len(cells) <= column_index:
            cells.append([])
        cells[column_index] = [{"type": "text", "text": {"content": body.time}}]
        _notion_request(token, f"blocks/{target['id']}", "PATCH", {"table_row": {"cells": cells}})
    # Notion 갱신 뒤 Shift Alarm의 1분 상태 파일 재생성을 기다리면 방금 저장한
    # 시각이 화면에서 예전 값으로 되돌아온다. 같은 값을 로컬 오버라이드에도
    # 원자적으로 기록해 다음 status 요청부터 즉시 같은 시각을 반환한다.
    merged = _merge_reminder_editor(status)
    schedule_item = next((item for item in merged.get("reminder_schedule", [])
                          if item.get("label") == body.label), None)
    if schedule_item and schedule_item.get("key"):
        editor = _read_reminder_editor()
        override = editor["items"].get(schedule_item["key"], {})
        override = dict(override) if isinstance(override, dict) else {}
        hour, minute = (int(part) for part in body.time.split(":"))
        if body.profile == "시각":
            override["time"] = {"hour": hour, "minute": minute}
        else:
            override.setdefault("profile_times", {})[body.profile] = {
                "hour": hour, "minute": minute,
            }
        editor["items"][schedule_item["key"]] = override
        _write_reminder_editor(editor)
    return {"ok": True, "label": body.label, "profile": body.profile,
            "time": body.time, "synced": True, "created_notion_row": created}


def _reminder_match_key(value):
    """이모지·공백·구두점 차이로 같은 리마인더를 놓치지 않게 한다."""
    return re.sub(r"[^0-9A-Za-z가-힣一-龥ぁ-ゖァ-ヺ]+", "", str(value or "")).casefold()


def _today_reminder_block(token, status, label, create_missing=False, allowed_labels=()):
    allowed = {item.get("label") for item in status.get("reminders_detailed", [])
               if isinstance(item, dict) and item.get("label")}
    allowed.update(str(item) for item in allowed_labels if item)
    if label not in allowed:
        raise HTTPException(status_code=409, detail="오늘의 리마인더만 변경할 수 있습니다")
    date_str = status.get("date")
    page = _notion_request(token, f"blocks/{SHIFT_ALARM_NOTION_PAGE_ID}/children?page_size=100")
    toggle = next((item for item in page.get("results", [])
                   if item.get("type") == "toggle" and _notion_text(item) == date_str), None)
    if not toggle:
        raise HTTPException(status_code=409, detail="Notion에서 오늘의 리마인더를 찾지 못했습니다")
    children = _notion_request(token, f"blocks/{toggle['id']}/children?page_size=100")
    match_key = _reminder_match_key(label)
    target = next((item for item in children.get("results", [])
                   if item.get("type") == "to_do"
                   and _reminder_match_key(_notion_text(item)) == match_key), None)
    if not target and create_missing:
        created = _notion_request(token, f"blocks/{toggle['id']}/children", "PATCH", {
            "children": [{
                "object": "block",
                "type": "to_do",
                "to_do": {
                    "rich_text": [{"type": "text", "text": {"content": label}}],
                    "checked": False,
                    "color": "default",
                },
            }],
        })
        target = next((item for item in created.get("results", [])
                       if item.get("type") == "to_do"), None)
    if not target:
        raise HTTPException(status_code=409, detail="Notion에서 해당 리마인더를 찾지 못했습니다")
    return target


def _set_shift_alarm_reminder_checked(label, checked, *, allowed_labels=(), source="web_reminder"):
    """오늘 리마인더 체크와 기록·퀘스트 보상을 한 경로로 처리한다."""
    status = _read_shift_alarm_status()
    token = _shift_alarm_notion_token()
    target = _today_reminder_block(
        token, status, label, create_missing=True, allowed_labels=allowed_labels,
    )
    routine_date = status.get("date") or datetime.date.today().isoformat()
    previous_checked = bool(target.get("to_do", {}).get("checked", False))
    # Notion 왕복 중에 지정 시각이 닿아도 알람이 먼저 울리지 않도록 로컬
    # 메뉴바 캐시를 선반영한다. Notion 반영이 실패하면 이전 상태로 되돌린다.
    _write_shift_alarm_checklist_cache(routine_date, label, checked)
    try:
        _notion_request(token, f"blocks/{target['id']}", "PATCH", {"to_do": {
            "rich_text": target.get("to_do", {}).get("rich_text", []), "checked": checked,
        }})
    except Exception:
        _write_shift_alarm_checklist_cache(routine_date, label, previous_checked)
        raise
    quest_key = f"reminder:{routine_date}:{label}"
    quest_awarded = False
    cultivation = _shift_alarm_cultivation_reward(
        label, 10, routine_date=routine_date, status=status,
    )
    if checked:
        checked_at = datetime.datetime.now()
        _record_shift_alarm_reminder_check(status, label, source=source, checked_at=checked_at)
        _learn_shift_alarm_reminder_time(status, label, checked_at)
        quest_awarded = _record_shift_alarm_quest(
            quest_key, label, 10, cultivation["attribute"], source=source,
            routine_date=routine_date, cultivation=cultivation,
        )
        if _is_melatonin_reminder(label):
            threading.Thread(
                target=_play_classical_after_melatonin_check,
                daemon=True,
                name="melatonin-classical",
            ).start()
    else:
        _record_shift_alarm_quest(
            quest_key, label, 10, cultivation["attribute"],
            action="reverse", source="reminder_uncheck", routine_date=routine_date,
            cultivation=cultivation,
        )
    return {
        "ok": True, "label": label, "checked": checked,
        "quest_awarded": quest_awarded,
        "quest_xp": cultivation["xp"] if quest_awarded else 0,
        "quest_axis": cultivation["axis"],
        "quest": _shift_alarm_quest_state(),
    }


def _write_shift_alarm_checklist_cache(date_str, label, checked):
    """웹 체크 결과를 같은 Mac의 메뉴바 알람에 즉시 전달한다.

    Notion 재조회 주기보다 먼저 알람 시각이 도착해도 완료한 항목이 울리지
    않도록 메뉴바 앱과 공유하는 로컬 캐시를 원자적으로 갱신한다.
    """
    path = SHIFT_ALARM_CHECKLIST_STATE_CACHE_FILE
    try:
        cached = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        cached = {}
    if cached.get("date") != date_str:
        cached["date"] = date_str
        cached["state"] = {}
    state = dict(cached.get("state") or {})
    state[str(label)] = bool(checked)
    cached["state"] = state
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".web.tmp")
        temporary.write_text(json.dumps(cached, ensure_ascii=False), encoding="utf-8")
        temporary.replace(path)
        return True
    except OSError:
        return False


@app.put("/api/shift-alarm/reminder-check")
def update_shift_alarm_reminder_check(body: ReminderCheckUpdate, request: Request):
    _require_owner(request)
    return _set_shift_alarm_reminder_checked(
        body.label, body.checked, source="reminder_check",
    )


@app.delete("/api/shift-alarm/reminder")
def delete_shift_alarm_reminder(label: str, request: Request):
    _require_owner(request)
    status = _read_shift_alarm_status()
    token = _shift_alarm_notion_token()
    target = _today_reminder_block(token, status, label)
    _notion_request(token, f"blocks/{target['id']}", "PATCH", {"archived": True})
    try:
        dismissed = json.loads(SHIFT_ALARM_DISMISSED_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        dismissed = {}
    date_str = status.get("date")
    dismissed = {date_str: sorted(set(dismissed.get(date_str, [])) | {label})}
    SHIFT_ALARM_DISMISSED_FILE.parent.mkdir(parents=True, exist_ok=True)
    temporary = SHIFT_ALARM_DISMISSED_FILE.with_suffix(".tmp")
    temporary.write_text(json.dumps(dismissed, ensure_ascii=False), encoding="utf-8")
    temporary.replace(SHIFT_ALARM_DISMISSED_FILE)
    return {"ok": True, "label": label}


@app.post("/api/shift-alarm/routine/check-all")
def check_all_shift_alarm_routine(request: Request):
    _require_owner(request)
    status = _read_shift_alarm_status()
    routine_date = status.get("routine_date")
    routine = status.get("daily_routine") or []
    labels = [item.get("label") for item in routine
              if isinstance(item, dict) and item.get("label") and not item.get("checked")]
    if not routine_date or not routine:
        raise HTTPException(status_code=409, detail="Shift Alarm이 오늘의 루틴을 아직 내보내지 않았습니다")
    if not labels:
        return {"ok": True, "updated": 0}
    token = _shift_alarm_notion_token()
    page = _notion_request(token, f"blocks/{SHIFT_ALARM_NOTION_PAGE_ID}/children?page_size=100")
    title = f"🌅 오늘의 일일 루틴 — {routine_date}"
    toggle = next((item for item in page.get("results", [])
                   if item.get("type") == "toggle" and _notion_text(item) == title), None)
    if not toggle:
        raise HTTPException(status_code=409, detail="Notion에서 오늘의 일일 루틴을 찾지 못했습니다")
    children = _notion_request(token, f"blocks/{toggle['id']}/children?page_size=100").get("results", [])
    by_label = {_notion_text(item): item for item in children if item.get("type") == "to_do"}
    missing = [label for label in labels if label not in by_label]
    if missing:
        raise HTTPException(status_code=409, detail="일일 루틴 항목 구성이 Shift Alarm과 다릅니다")
    targets = [by_label[label] for label in labels
               if not by_label[label].get("to_do", {}).get("checked")]
    updated = []
    try:
        for item in targets:
            _notion_request(token, f"blocks/{item['id']}", "PATCH", {"to_do": {
                "rich_text": item.get("to_do", {}).get("rich_text", []), "checked": True,
            }})
            updated.append(item)
    except HTTPException as exc:
        rollback_failed = False
        for item in reversed(updated):
            try:
                _notion_request(token, f"blocks/{item['id']}", "PATCH", {"to_do": {
                    "rich_text": item.get("to_do", {}).get("rich_text", []), "checked": False,
                }})
            except HTTPException:
                rollback_failed = True
        detail = "일일 루틴 변경에 실패해 적용된 항목을 되돌렸습니다"
        if rollback_failed:
            detail = "일일 루틴이 일부만 반영됐을 수 있습니다. Notion에서 확인해주세요"
        raise HTTPException(status_code=502, detail=detail) from exc
    completed_at = datetime.datetime.now().isoformat(timespec="seconds")
    _record_shift_alarm_routine_completion(status)
    _write_shift_alarm_routine_signal(status, completed_at)
    cultivation = _shift_alarm_cultivation_reward(
        "All OK", 25, routine_date=routine_date, status=status,
    )
    quest_awarded = _record_shift_alarm_quest(
        f"routine:{routine_date}:all-ok", "All OK", 25, "준비",
        source="routine_check_all", routine_date=routine_date, cultivation=cultivation,
    )
    return {
        "ok": True, "updated": len(targets), "quest": _shift_alarm_quest_state(),
        "quest_awarded": quest_awarded,
        "quest_xp": cultivation["xp"] if quest_awarded else 0,
        "quest_axis": cultivation["axis"],
    }


@app.get("/api/shift-alarm/quest-status")
def get_shift_alarm_quest_status(request: Request):
    _require_owner(request)
    return _shift_alarm_quest_state(_request_username(request))


class ShiftAlarmCultivationChoiceUpdate(BaseModel):
    axis: str


@app.put("/api/shift-alarm/cultivation-choice")
def update_shift_alarm_cultivation_choice(body: ShiftAlarmCultivationChoiceUpdate, request: Request):
    _require_owner(request)
    if body.axis not in SHIFT_ALARM_CULTIVATION_SEQUENCE:
        raise HTTPException(status_code=400, detail="수행은 정 또는 기로 선택해주세요")
    switched = _switch_shift_alarm_cultivation(body.axis)
    state = _shift_alarm_quest_state(_request_username(request))
    state["cultivation"]["switched"] = switched
    return state


@app.get("/api/shift-alarm/routine-history")
def get_shift_alarm_routine_history(request: Request, limit: int = Query(30, ge=7, le=366)):
    _require_owner(request)
    return {"records": _read_shift_alarm_routine_history(limit)}


class ShiftAlarmHabitClickRequest(BaseModel):
    kind: str


class ShiftAlarmLearningLinkRequest(BaseModel):
    kind: str


def _shift_alarm_homecoming_state() -> dict:
    try:
        payload = json.loads(SHIFT_ALARM_HOMECOMING_FILE.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return {}


def _save_shift_alarm_homecoming(payload: dict) -> dict:
    SHIFT_ALARM_HOMECOMING_FILE.parent.mkdir(parents=True, exist_ok=True)
    temporary = SHIFT_ALARM_HOMECOMING_FILE.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, SHIFT_ALARM_HOMECOMING_FILE)
    return payload


@app.get("/api/shift-alarm/homecoming")
def get_shift_alarm_homecoming(request: Request):
    _require_owner(request)
    return _shift_alarm_homecoming_state()


@app.post("/api/shift-alarm/homecoming")
def schedule_shift_alarm_homecoming(request: Request):
    _require_owner(request)
    now = datetime.datetime.now().astimezone()
    current = _shift_alarm_homecoming_state()
    if current.get("status") == "scheduled":
        try:
            if datetime.datetime.fromisoformat(str(current.get("trigger_at"))) > now:
                return current
        except (TypeError, ValueError):
            pass
    payload = {
        "status": "scheduled",
        "scheduled_at": now.isoformat(timespec="seconds"),
        "trigger_at": (now + datetime.timedelta(minutes=30)).isoformat(timespec="seconds"),
        "delay_minutes": 30,
        "actions": {"light": "pending", "classical": "pending", "reader": "pending"},
    }
    return _save_shift_alarm_homecoming(payload)


@app.delete("/api/shift-alarm/homecoming")
def cancel_shift_alarm_homecoming(request: Request):
    _require_owner(request)
    now = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    payload = _shift_alarm_homecoming_state()
    payload.update({"status": "cancelled", "cancelled_at": now})
    return _save_shift_alarm_homecoming(payload)


@app.post("/api/shift-alarm/habit-click")
def record_shift_alarm_habit_click(body: ShiftAlarmHabitClickRequest, request: Request):
    _require_owner(request)
    return {"ok": True, "event": _record_shift_alarm_habit_click(body.kind)}


@app.post("/api/shift-alarm/learning-link-click")
def record_shift_alarm_learning_link_click(body: ShiftAlarmLearningLinkRequest, request: Request):
    _require_owner(request)
    return {"ok": True, "event": _record_shift_alarm_learning_link_click(body.kind)}


@app.post("/api/shift-alarm/habit-click/undo")
def undo_shift_alarm_habit_click(body: ShiftAlarmHabitClickRequest, request: Request):
    _require_owner(request)
    event = _undo_shift_alarm_habit_click(body.kind)
    today = datetime.date.today().isoformat()
    record = next((item for item in _read_shift_alarm_routine_history(7)
                   if item.get("routine_date") == today), {})
    remaining = [item for item in record.get("habit_events", [])
                 if item.get("kind") == body.kind]
    return {
        "ok": True,
        "event": event,
        "count": len(remaining),
        "previous_time": remaining[-1].get("time") if remaining else None,
    }


@app.get("/shift-alarm/quick/{kind}")
def quick_record_shift_alarm_habit(kind: str, request: Request):
    """Safari/단축어에서 한 번 열어 생활 기록을 즉시 남긴다.

    별도 비밀 URL을 노출하지 않고 기존 툴파챗 소유자 로그인 세션을 사용한다.
    기록 후 대시보드의 최종 URL로 이동하므로 새로고침으로 중복 기록되지 않는다.
    """
    _require_owner(request)
    if kind not in {"breathing", "smoking"}:
        raise HTTPException(status_code=404, detail="지원하지 않는 빠른 기록입니다")
    _record_shift_alarm_habit_click(kind)
    return RedirectResponse(
        url=f"/shift-alarm/?quick_recorded={kind}", status_code=303,
    )


def _sunzi_site_verses():
    """배포 사이트가 실제로 승인해 싣는 구절 목록을 읽는다."""
    try:
        source = SUNZI_SITE_GENERATED_FILE.read_text(encoding="utf-8")
        rows = json.loads(source[source.index("["):source.rindex("]") + 1])
    except (OSError, ValueError, json.JSONDecodeError):
        return []
    verses = []
    for row in rows:
        try:
            verse = int(row.get("id"))
            chapter_id = int(row.get("chapterId") or 11)
            chapter_verse = int(row.get("number") or verse)
        except (AttributeError, TypeError, ValueError):
            continue
        hanja = str(row.get("original") or "").strip()
        reading = str(row.get("reading") or "").strip()
        if verse > 0 and hanja and reading:
            chapter_name = str(row.get("chapterName") or dict(
                (chapter_id, name) for chapter_id, name in SUNZI_CHAPTER_SEQUENCE
            ).get(chapter_id, "구지편"))
            verses.append({
                "id": verse,
                # verse는 기존 호출부와 호환되는 전체 공개 순번이다.
                "verse": verse,
                "chapter_id": chapter_id,
                "chapter": chapter_name,
                "chapter_verse": chapter_verse,
                "hanja": hanja,
                "reading": reading,
            })
    return verses


def _plain_sunzi_original(value):
    """편장/사이트 표기가 달라도 같은 원문인지 비교할 수 있게 정규화한다."""
    return re.sub(r"[^\u3400-\u9fff]", "", html.unescape(str(value or "")))


def _sunzi_chapter_originals():
    """정본에서 편별 원문 순서를 읽어 다음 편 전환 계산에 사용한다."""
    try:
        source = SUNZI_CHAPTER_SOURCE_FILE.read_text(encoding="utf-8")
    except OSError:
        return {}
    chapters = {}
    for chapter_id, chapter_name in SUNZI_CHAPTER_SEQUENCE:
        match = re.search(
            rf'^\s*"{chapter_id}":\s*("(?:\\.|[^"\\])*")\s*,?$',
            source, re.MULTILINE,
        )
        if not match:
            continue
        try:
            chapter = json.loads(match.group(1))
        except json.JSONDecodeError:
            continue
        originals = []
        for summary in re.findall(r"<summary>(.*?)</summary>", chapter, re.DOTALL):
            first = summary.split("<br>", 1)[0]
            normalized = _plain_sunzi_original(first)
            if normalized:
                originals.append(normalized)
        if not originals:
            for line in chapter.splitlines():
                if not line.startswith("> "):
                    continue
                boundary = re.search(r"[가-힣]", line)
                normalized = _plain_sunzi_original(line[2:boundary.start()] if boundary else "")
                if normalized:
                    originals.append(normalized)
        chapters[chapter_id] = {"name": chapter_name, "originals": originals}
    return chapters


def _sunzi_next_position():
    """성공 완료 커서 다음 위치를 11→12→13→1…→10 순환으로 계산한다."""
    chapters = _sunzi_chapter_originals()
    try:
        cursor = json.loads(SUNZI_PIPELINE_CURSOR_FILE.read_text(encoding="utf-8"))
        chapter_id = int(cursor["chapter_id"])
        completed_verse = int(cursor["verse"])
        latest_original = _plain_sunzi_original(cursor["original"])
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None, None, None
    if not chapters or chapter_id not in chapters or not latest_original:
        return None, None, None
    sequence = [chapter_id for chapter_id, _ in SUNZI_CHAPTER_SEQUENCE]
    originals = chapters[chapter_id].get("originals", [])
    try:
        index = originals.index(latest_original)
    except ValueError:
        return None, None, completed_verse
    if index + 1 < len(originals):
        return chapters[chapter_id]["name"], index + 2, completed_verse
    next_id = sequence[(sequence.index(chapter_id) + 1) % len(sequence)]
    return chapters[next_id]["name"], 1, completed_verse


def _sunzi_latest_completed_verse():
    """메인 원고·배포 사이트·자동화 기록을 대조한 완료 번호를 돌려준다."""
    candidates = []
    try:
        candidates.extend(
            int(match.group(1))
            for path in SUNZI_CHAPTER_DIR.iterdir()
            if (match := SUNZI_VERSE_FILE_RE.match(path.name))
        )
    except OSError:
        pass
    candidates.extend(item["verse"] for item in _sunzi_site_verses())
    # README는 산출물보다 늦게 동기화될 수 있으므로 보조 신호로만 합친다.
    for readme_path in (SUNZI_CHAPTER_DIR / "README.md", SUNZI_AUTOMATION_README):
        try:
            readme = readme_path.read_text(encoding="utf-8")
        except OSError:
            continue
        completed = re.search(
            r"마지막으로 순차 (?:최신화|분석)한 구절.*?九地篇\s*(\d+)구절", readme
        )
        if completed:
            candidates.append(int(completed.group(1)))
    return max(candidates, default=None)


def _sunzi_light_pipeline_state(conn):
    queued_row = conn.execute(
        """SELECT m.content FROM pending_turns AS p
             JOIN messages AS m ON m.id=p.source_message_id
             WHERE p.persona_name=? AND p.status IN ('pending','processing')
             ORDER BY p.id DESC LIMIT 1""",
        ("손무",),
    ).fetchone()
    queued = conn.execute(
        """SELECT COUNT(*) AS n FROM pending_turns
             WHERE persona_name=? AND status IN ('pending','processing')""",
        ("손무",),
    ).fetchone()["n"]
    try:
        pipeline = json.loads(SUNZI_PIPELINE_STATUS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        pipeline = {}
    pid = pipeline.get("pid")
    running = pipeline.get("state") == "running" and isinstance(pid, int) and pid > 0
    if running:
        try:
            os.kill(pid, 0)
        except OSError:
            running = False
    elapsed_seconds = None
    try:
        started = datetime.datetime.fromisoformat(pipeline["started_at"])
        elapsed_seconds = max(0, int((datetime.datetime.now(datetime.timezone.utc) - started).total_seconds()))
    except (KeyError, TypeError, ValueError):
        pass
    next_chapter, next_verse, latest_verse = _sunzi_next_position()
    latest_chapter = None
    latest_chapter_id = None
    try:
        cursor = json.loads(SUNZI_PIPELINE_CURSOR_FILE.read_text(encoding="utf-8"))
        latest_chapter = str(cursor.get("chapter_name") or "").strip() or None
        latest_chapter_id = int(cursor.get("chapter_id"))
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        pass
    queued_verse = None
    if queued_row:
        queued_match = SUNZI_BACKFILL_COMMAND_RE.search(queued_row["content"].replace("_", " "))
        if queued_match:
            queued_verse = int(queued_match.group(1))
    return {
        "busy": bool(queued or running), "queued": bool(queued and not running),
        "running": running, "mode": pipeline.get("mode", "light"),
        "state": pipeline.get("state", "idle") if running or pipeline.get("state") != "running" else "interrupted",
        "verse": pipeline.get("verse"), "queued_verse": queued_verse,
        "progress": pipeline.get("progress", 0),
        "stage": pipeline.get("stage", "분석 대기"), "elapsed_seconds": elapsed_seconds,
        "updated_at": pipeline.get("updated_at"), "next_chapter": next_chapter,
        "next_verse": next_verse,
        "latest_verse": latest_verse,
        "latest_chapter": latest_chapter,
        "latest_chapter_id": latest_chapter_id,
    }


def _read_sunzi_verses():
    """승인된 전편 구절과 편별 번호를 화면용 순서로 돌려준다."""
    verses_by_number = {item["verse"]: item for item in _sunzi_site_verses()}
    try:
        entries = list(SUNZI_CHAPTER_DIR.iterdir())
    except OSError:
        return [verses_by_number[key] for key in sorted(verses_by_number)]
    for path in entries:
        match = SUNZI_VERSE_FILE_RE.match(path.name)
        if not match:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        summary = SUNZI_VERSE_SUMMARY_RE.search(text)
        if not summary or "<br>" not in summary.group(1):
            continue
        hanja_html, _, reading = summary.group(1).partition("<br>")
        hanja = re.sub(r"<[^>]+>", "", hanja_html).strip()
        reading = re.sub(r"<[^>]+>", "", reading).strip()
        if not hanja or not reading:
            continue
        verse = int(match.group(1))
        verses_by_number[verse] = {
            "id": verse, "verse": verse,
            "chapter_id": 11, "chapter": "구지편", "chapter_verse": verse,
            "hanja": hanja, "reading": reading,
        }
    return [verses_by_number[key] for key in sorted(verses_by_number)]


@app.get("/api/shift-alarm/sunzi-verses")
def get_shift_alarm_sunzi_verses(request: Request):
    _require_owner(request)
    verses = _read_sunzi_verses()
    try:
        cursor = json.loads(SUNZI_PIPELINE_CURSOR_FILE.read_text(encoding="utf-8"))
        chapter = str(cursor.get("chapter_name") or "").strip()
    except (OSError, ValueError, json.JSONDecodeError):
        chapter = ""
    return {"chapter": chapter or (verses[-1]["chapter"] if verses else "구지편"), "verses": verses}


@app.get("/api/shift-alarm/sunzi-analysis")
def shift_alarm_sunzi_analysis_status(request: Request):
    _require_owner(request)
    conn = get_conn()
    try:
        return _sunzi_light_pipeline_state(conn)
    finally:
        conn.close()


@app.get("/api/public/sunzi-analysis")
def public_sunzi_analysis_status(verse: int):
    """손자병법 공개 앱에는 비밀값 없이 요청 구절의 진행 상태만 제공한다."""
    if not 1 <= verse <= 99:
        raise HTTPException(status_code=400, detail="구절 번호가 허용 범위를 벗어났습니다")
    conn = get_conn()
    try:
        state = _sunzi_light_pipeline_state(conn)
    finally:
        conn.close()
    active_verse = state["verse"] if state["running"] else state.get("queued_verse")
    relevant = active_verse == verse or (state["state"] in ("complete", "failed") and state["verse"] == verse)
    public_state = "queued" if relevant and state["queued"] else state["state"] if relevant else "idle"
    public_progress = 0 if relevant and state["queued"] else state["progress"] if relevant else 0
    payload = {
        "relevant": relevant,
        "busy": state["busy"] if relevant else False,
        "queued": state["queued"] if relevant else False,
        "running": state["running"] if relevant else False,
        # 새 요청이 대기 중일 때 이전 실행의 complete/100 값을 함께 보내면
        # 사이트가 '보강 완료 · 작업 시작 대기'라는 모순된 카드를 그린다.
        "state": public_state,
        "verse": verse,
        "progress": public_progress,
        "stage": ("작업 시작 대기" if relevant and state["queued"] else state["stage"] if relevant else "요청 확인 중"),
        "elapsed_seconds": state["elapsed_seconds"] if relevant else None,
        "updated_at": state["updated_at"] if relevant else None,
    }
    return JSONResponse(payload, headers={
        "Access-Control-Allow-Origin": "https://sunzi-strategy-notes.pulpilisory.chatgpt.site",
        "Cache-Control": "no-store",
    })


def _enqueue_sunzi_light_analysis(conn):
    """손무의 고정 라이트 파이프라인 한 건을 큐에 넣는다 — 소유자 버튼과
    ShiftAlarm 기상 알람 트리거가 이 로직을 공유한다(2026-09-16)."""
    if _sunzi_light_pipeline_state(conn)["busy"]:
        raise HTTPException(status_code=409, detail="병법 구절 분석이 이미 대기 중이거나 실행 중입니다")
    if not conn.execute("SELECT 1 FROM personas WHERE name=?", ("손무",)).fetchone():
        raise HTTPException(status_code=409, detail="손무 페르소나를 찾지 못했습니다")
    now = _now()
    cursor = conn.execute(
        """INSERT INTO messages (room_id, sender, content, created_at, is_system)
           VALUES (?, 'system', ?, ?, 1)""",
        (SUNZI_DISCUSSION_ROOM_ID, SUNZI_LIGHT_PIPELINE_REQUEST, now),
    )
    conn.execute(
        """INSERT INTO pending_turns
           (persona_name, room_id, status, created_at, source_message_id)
           VALUES (?, ?, 'pending', ?, ?)""",
        ("손무", SUNZI_DISCUSSION_ROOM_ID, now, cursor.lastrowid),
    )
    conn.commit()
    return {"ok": True, "busy": True, "queued": True, "running": False, "mode": "light"}


@app.post("/api/shift-alarm/sunzi-analysis")
def start_shift_alarm_sunzi_analysis(request: Request):
    """소유자 버튼 한 번을 손무의 고정 라이트 파이프라인 한 건으로 변환한다."""
    _require_owner(request)
    conn = get_conn()
    try:
        return _enqueue_sunzi_light_analysis(conn)
    finally:
        conn.close()


@app.post("/api/worker/sunzi_light_analysis")
def worker_start_sunzi_light_analysis(authorization: Optional[str] = Header(None)):
    """ShiftAlarm이 기상 알람 시각에 손무의 라이트 분석을 직접 트리거한다
    (2026-09-16, "기상알람 뜨면 다음구절 라이트모드로 분석한다음 토론
    시작하면좋겠어" 요청). /api/shift-alarm/sunzi-analysis와 같은 로직이지만
    브라우저 세션 대신 WORKER_TOKEN으로 인증한다 — ShiftAlarm은 소유자
    세션 쿠키를 들고 있지 않다. 이미 대기 중이면 409를 그냥 삼켜 알람
    루프가 실패로 보지 않게 한다(호출부에서 잡음)."""
    _check_worker_auth(authorization)
    conn = get_conn()
    try:
        return _enqueue_sunzi_light_analysis(conn)
    finally:
        conn.close()


@app.get("/api/shift-alarm/media/volume")
def get_shift_alarm_volume(request: Request):
    _require_owner(request)
    percent = _shift_alarm_get_volume()
    if percent is None:
        raise HTTPException(status_code=503, detail="시스템 음량을 확인하지 못했습니다")
    return {"percent": percent}


class ShiftAlarmLightRequest(BaseModel):
    on: bool


@app.get("/api/shift-alarm/home/light")
def get_shift_alarm_light(request: Request):
    _require_owner(request)
    return {"room": SHIFT_ALARM_HUE_ROOM_NAME, "on": _shift_alarm_hue_state()}


@app.put("/api/shift-alarm/home/light")
def set_shift_alarm_light(body: ShiftAlarmLightRequest, request: Request):
    _require_owner(request)
    return {"ok": True, "room": SHIFT_ALARM_HUE_ROOM_NAME, "on": _shift_alarm_set_hue_power(body.on)}


class ShiftAlarmVolumeRequest(BaseModel):
    percent: Optional[int] = None
    delta: Optional[int] = None


@app.post("/api/shift-alarm/media/volume")
def set_shift_alarm_volume(body: ShiftAlarmVolumeRequest, request: Request):
    """대시보드 버튼 전용 — percent(절대값) 또는 delta(상대 증감) 중 하나만 받는다."""
    _require_owner(request)
    if body.percent is not None:
        target = body.percent
    elif body.delta is not None:
        current = _shift_alarm_get_volume()
        if current is None:
            raise HTTPException(status_code=503, detail="현재 음량을 확인하지 못해 조절할 수 없습니다")
        target = current + body.delta
    else:
        raise HTTPException(status_code=400, detail="percent 또는 delta 중 하나가 필요합니다")
    return {"ok": True, "percent": _shift_alarm_set_volume(target)}


class ShiftAlarmPlayRequest(BaseModel):
    playlist: str


@app.post("/api/shift-alarm/media/play")
def play_shift_alarm_media(body: ShiftAlarmPlayRequest, request: Request):
    _require_owner(request)
    folder = {
        "favorites": SHIFT_ALARM_FAVORITES_FOLDER,
        "classical": SHIFT_ALARM_CLASSIC_FOLDER,
        "sleep": SHIFT_ALARM_SLEEP_FOLDER,
    }.get(body.playlist)
    if not folder:
        raise HTTPException(status_code=400, detail="지원하지 않는 재생목록입니다")
    ok, message = _shift_alarm_play_folder(folder)
    if not ok:
        raise HTTPException(status_code=409, detail=message)
    return {"ok": True, "message": message}


@app.get("/api/shift-alarm/media/now-playing")
def shift_alarm_now_playing(request: Request):
    # ★ 2026-09-14: "클래식/좋아요 재생 중일 때 대시보드에 어느 쪽인지 표시해줘" —
    # Elmedia는 샌드박스 앱이라 "지금 재생 중인 목록이 뭔지" 직접 물어볼 방법이
    # 없다. 실행 중 여부(pgrep)와 마지막으로 우리가 연 재생목록 기록을 합쳐
    # 근사한다 — Elmedia가 떠 있지 않으면 재생목록도 의미 없으니 null.
    _require_owner(request)
    if not _shift_alarm_elmedia_running():
        return {"running": False, "playlist": None}
    state = _shift_alarm_load_now_playing()
    # ElmediaStatusHelper의 결과 파일은 helper를 다시 실행하기 전까지 과거 곡을
    # 그대로 담고 있다. 대시보드 폴링 때마다 이 오래된 곡명을 우선하면 숙면을
    # 재생 중이어도 예전에 들은 클래식으로 상태가 되돌아간다. 재생을 시작한
    # 경로가 기록한 모드를 우선하고, 그 기록이 없거나 구버전 값일 때만 화면
    # 텍스트 판별을 호환용 폴백으로 사용한다.
    playlist = state.get("playlist")
    detected = None
    if playlist not in {"favorites", "classical", "sleep"}:
        detected = _shift_alarm_playlist_from_visible_track()
        playlist = detected
    playing = bool(state.get("playing", True))
    if detected:
        _shift_alarm_save_now_playing(detected, playing)
    return {"running": playing, "playlist": playlist if playing else None}


@app.post("/api/shift-alarm/media/open-sites")
def open_shift_alarm_random_sites(request: Request):
    # ★ 2026-09-14: "휴대폰 크롬에서 열리게 해줄 수 없나" — 예전엔 서버(Mac)에서
    # open -a "Google Chrome"으로 직접 열었는데, 대시보드를 폰으로 보는 사람에게는
    # 정작 Mac 화면에서 창이 뜨는 셈이라 무의미했다. URL만 골라 돌려주고, 여는
    # 동작은 이 요청을 보낸 브라우저(app.js) 쪽에서 하게 바꿨다.
    _require_owner(request)
    urls = _shift_alarm_pick_random_bookmarks(3)
    if not urls:
        raise HTTPException(status_code=409, detail="추천 사이트 목록이 비어 있습니다 — 북마크 관리에서 링크를 추가하세요")
    return {"ok": True, "message": f"{len(urls)}개 찾았습니다", "urls": urls}


class ShiftAlarmBookmarkRequest(BaseModel):
    url: str


class ShiftAlarmKrMirrorRequest(BaseModel):
    number: int


@app.get("/api/shift-alarm/link-host")
def get_shift_alarm_link_host(request: Request):
    _require_signed_in_user(request)
    number = _load_kr_mirror_number()
    return {"number": number, "host": f"kr{number}.topgirl.co"}


@app.put("/api/shift-alarm/link-host")
def update_shift_alarm_link_host(body: ShiftAlarmKrMirrorRequest, request: Request):
    _require_owner(request)
    number = int(body.number)
    if not 1 <= number <= 999:
        raise HTTPException(status_code=422, detail="kr 뒤 번호는 1부터 999까지 입력하세요")
    with _shift_alarm_link_settings_lock:
        urls = _shift_alarm_load_web_bookmarks()
        changed_bookmarks = 0
        updated_urls = []
        for url in urls:
            updated, changed = _replace_kr_mirror_number(url, number)
            changed_bookmarks += int(changed)
            updated_urls.append(updated)
        if changed_bookmarks:
            _shift_alarm_save_web_bookmarks(updated_urls)
        changed_files, changed_sources = _update_source_video_mirrors(number)
        _save_kr_mirror_number(number)
    return {
        "ok": True,
        "number": number,
        "host": f"kr{number}.topgirl.co",
        "urls": updated_urls,
        "changed_bookmarks": changed_bookmarks,
        "changed_source_urls": changed_sources,
        "changed_source_files": changed_files,
    }


@app.get("/api/shift-alarm/bookmarks")
def list_shift_alarm_bookmarks(request: Request):
    _require_owner(request)
    return {"urls": _shift_alarm_load_web_bookmarks()}


@app.post("/api/shift-alarm/bookmarks")
def add_shift_alarm_bookmark(body: ShiftAlarmBookmarkRequest, request: Request):
    _require_owner(request)
    url = body.url.strip()
    if not _shift_alarm_valid_bookmark_url(url):
        raise HTTPException(status_code=422, detail="http:// 또는 https:// 로 시작하는 올바른 주소를 입력하세요")
    urls = _shift_alarm_load_web_bookmarks()
    if url not in urls:
        urls.append(url)
        _shift_alarm_save_web_bookmarks(urls)
    return {"ok": True, "urls": urls}


class ShiftAlarmBookmarkUpdateRequest(BaseModel):
    url: str
    new_url: str


@app.put("/api/shift-alarm/bookmarks")
def update_shift_alarm_bookmark(body: ShiftAlarmBookmarkUpdateRequest, request: Request):
    _require_owner(request)
    new_url = body.new_url.strip()
    if not _shift_alarm_valid_bookmark_url(new_url):
        raise HTTPException(status_code=422, detail="http:// 또는 https:// 로 시작하는 올바른 주소를 입력하세요")
    urls = _shift_alarm_load_web_bookmarks()
    old_url = body.url.strip()
    if old_url not in urls:
        raise HTTPException(status_code=404, detail="수정할 북마크를 찾을 수 없습니다")
    if new_url != old_url and new_url in urls:
        raise HTTPException(status_code=409, detail="이미 있는 북마크입니다")
    urls = [new_url if item == old_url else item for item in urls]
    _shift_alarm_save_web_bookmarks(urls)
    return {"ok": True, "urls": urls}


@app.post("/api/shift-alarm/bookmarks/delete")
def delete_shift_alarm_bookmark(body: ShiftAlarmBookmarkRequest, request: Request):
    _require_owner(request)
    urls = [item for item in _shift_alarm_load_web_bookmarks() if item != body.url.strip()]
    _shift_alarm_save_web_bookmarks(urls)
    return {"ok": True, "urls": urls}


class ShiftAlarmTransportRequest(BaseModel):
    action: str  # playpause | next | previous


class ShiftAlarmVideoDownloadRequest(BaseModel):
    url: str
    approved: bool = False


class ShiftAlarmVideoActionRequest(BaseModel):
    action: str  # delete | cancel_transfer | extract_subtitle | mark_photo_shortcut


@app.post("/api/shift-alarm/media/transport")
def shift_alarm_media_transport(body: ShiftAlarmTransportRequest, request: Request):
    _require_owner(request)
    if body.action not in ("playpause", "next", "previous"):
        raise HTTPException(status_code=400, detail="지원하지 않는 동작입니다")
    if not _shift_alarm_elmedia_running():
        raise HTTPException(status_code=409, detail="Elmedia가 실행되고 있지 않습니다")
    command_id = uuid.uuid4().hex
    temporary = SHIFT_ALARM_MEDIA_COMMAND_FILE.with_suffix(".tmp")
    temporary.write_text(
        json.dumps({"id": command_id, "action": body.action}), encoding="utf-8",
    )
    temporary.replace(SHIFT_ALARM_MEDIA_COMMAND_FILE)
    deadline = time.monotonic() + 4
    while time.monotonic() < deadline:
        try:
            ack = json.loads(SHIFT_ALARM_MEDIA_COMMAND_ACK_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            time.sleep(0.1)
            continue
        if ack.get("id") == command_id:
            if not ack.get("ok"):
                raise HTTPException(status_code=503, detail=ack.get("error") or "미디어 제어에 실패했습니다")
            state = _shift_alarm_load_now_playing()
            return {"ok": True, "playing": bool(state.get("playing", True))}
        time.sleep(0.1)
    raise HTTPException(status_code=504, detail="Shift Alarm이 미디어 제어 요청에 응답하지 않았습니다")


@app.get("/api/shift-alarm/video-download")
def shift_alarm_video_download_status(request: Request):
    _require_owner(request)
    status = _shift_alarm_video_status()
    username = _request_username(request)
    conn = _shift_alarm_video_db()
    _shift_alarm_cleanup_videos(conn)
    rows = conn.execute(
        "SELECT job_id,filename,file_path,size_bytes,completed_at,expires_at FROM video_downloads "
        "WHERE owner_username=? ORDER BY completed_at DESC", (username,)
    ).fetchall()
    conn.close()
    managed_paths = {row["file_path"]: row for row in rows}
    transfers = _shift_alarm_transfer_states()
    processing = _shift_alarm_processing_history()
    status["downloads"] = []
    av4_files = _shift_alarm_av4_files()
    status["library_revision"] = _shift_alarm_av4_revision(av4_files)
    for path in av4_files:
        file_id = _shift_alarm_av4_id(path)
        managed = managed_paths.get(str(path))
        item = {
            "file_id": file_id, "filename": path.name, "ios_filename": _shift_alarm_ios_filename(path),
            "size_bytes": path.stat().st_size,
            "completed_at": managed["completed_at"] if managed else datetime.datetime.fromtimestamp(
                path.stat().st_mtime, datetime.timezone.utc
            ).isoformat(timespec="seconds"),
            "expires_at": None,
            "temporary": False,
            "download_url": f"/api/shift-alarm/video-library/{file_id}/file",
            "download_page_url": f"/shift-alarm/download/{file_id}",
            "action_url": f"/api/shift-alarm/video-library/{file_id}/action",
        }
        transfer = transfers.get(file_id)
        if transfer:
            item.update(
                transfer_state=transfer["state"], transfer_sent_bytes=transfer["sent_bytes"],
                transfer_total_bytes=transfer["total_bytes"],
                transfer_updated_at=transfer["updated_at"],
            )
        history = processing.get(file_id)
        if history:
            # .get()으로 읽는다 — 스키마 마이그레이션 이전에 만들어진 행이나
            # 컬럼 추가 전 DB에도 이 API 전체가 죽지 않고 그 값만 비어 보이게.
            item.update(
                subtitle_state=history.get("subtitle_state"),
                subtitle_progress=history.get("subtitle_progress"),
                subtitle_stage=history.get("subtitle_stage"),
                subtitle_started_at=history.get("subtitle_started_at"),
                subtitle_completed_at=history.get("subtitle_completed_at"),
                safari_completed_at=history.get("safari_completed_at"),
                photo_shortcut_at=history.get("photo_shortcut_at"),
            )
        status["downloads"].append(item)
    if status.get("state") == "complete" and status.get("job_id"):
        try:
            row, _path = _shift_alarm_owned_video(status["job_id"], username)
            status.update(
                available=True, size_bytes=row["size_bytes"], expires_at=row["expires_at"],
                download_url=f"/api/shift-alarm/video-download/{row['job_id']}/file",
            )
        except HTTPException:
            status.update(available=False, stage="파일이 이동되었거나 삭제됐습니다")
    status["subtitle_extraction"] = _shift_alarm_subtitle_status()
    return status


@app.post("/api/shift-alarm/video-download")
def start_shift_alarm_video_download(body: ShiftAlarmVideoDownloadRequest, request: Request):
    """소유자가 화면에서 확인한 URL 한 건만 고정 다운로드 작업기에 전달한다."""
    _require_owner(request)
    if not body.approved:
        raise HTTPException(status_code=422, detail="다운로드 승인 확인이 필요합니다")
    url = _validate_stream_download_url(body.url)
    current = _shift_alarm_video_status()
    if current.get("state") in {"queued", "running", "syncing"}:
        raise HTTPException(status_code=409, detail="다른 영상 다운로드가 진행 중입니다")
    if not SHIFT_ALARM_VIDEO_WORKER.is_file() or not Path("/opt/homebrew/bin/yt-dlp").is_file():
        raise HTTPException(status_code=503, detail="Mac 영상 다운로드 작업기를 찾을 수 없습니다")
    SHIFT_ALARM_VIDEO_DIR.mkdir(parents=True, exist_ok=True)
    job_id = uuid.uuid4().hex
    request_file = SHIFT_ALARM_VIDEO_DIR / f"request_{job_id}.json"
    request_file.write_text(json.dumps({
        "job_id": job_id, "url": url, "owner_username": _request_username(request),
        "created_at": _now(),
    }), encoding="utf-8")
    os.chmod(request_file, 0o600)
    queued = {
        "job_id": job_id, "state": "queued", "stage": "Mac 다운로드 작업 시작 대기",
        "progress": 0, "created_at": _now(), "updated_at": _now(),
    }
    temporary = SHIFT_ALARM_VIDEO_STATUS_FILE.with_suffix(".tmp")
    temporary.write_text(json.dumps(queued, ensure_ascii=False, indent=2), encoding="utf-8")
    os.chmod(temporary, 0o600)
    temporary.replace(SHIFT_ALARM_VIDEO_STATUS_FILE)
    try:
        subprocess.Popen(
            [SHIFT_ALARM_VIDEO_PYTHON, str(SHIFT_ALARM_VIDEO_WORKER), "--request", str(request_file)],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError as exc:
        request_file.unlink(missing_ok=True)
        queued.update(state="failed", stage="Mac 다운로드 작업을 시작하지 못했습니다", progress=0)
        SHIFT_ALARM_VIDEO_STATUS_FILE.write_text(json.dumps(queued, ensure_ascii=False, indent=2), encoding="utf-8")
        raise HTTPException(status_code=503, detail=queued["stage"]) from exc
    return {"ok": True, **queued}


@app.get("/api/shift-alarm/video-download/{job_id}/file")
def download_shift_alarm_video(job_id: str, request: Request,
                               range_header: Optional[str] = Header(None, alias="Range")):
    _require_owner(request)
    row, path = _shift_alarm_owned_video(job_id, _request_username(request))
    with _shift_alarm_video_db() as conn:
        conn.execute("UPDATE video_downloads SET downloaded_at=? WHERE job_id=?", (_now(), job_id))
    return _shift_alarm_stream_file(
        path, range_header, request, _shift_alarm_av4_id(path), _request_username(request)
    )


@app.get("/api/shift-alarm/video-library/{file_id}/file")
def download_shift_alarm_library_video(file_id: str, request: Request,
                                       range_header: Optional[str] = Header(None, alias="Range")):
    _require_owner(request)
    return _shift_alarm_stream_file(
        _shift_alarm_av4_file(file_id), range_header, request, file_id, _request_username(request)
    )


@app.post("/api/shift-alarm/video-library/{file_id}/action")
def act_on_shift_alarm_library_video(file_id: str, body: ShiftAlarmVideoActionRequest,
                                     request: Request):
    _require_owner(request)
    path = _shift_alarm_av4_file(file_id)
    if body.action == "extract_subtitle":
        current = _shift_alarm_subtitle_status()
        if current.get("state") == "running":
            raise HTTPException(status_code=409, detail="다른 자막 추출 작업이 진행 중입니다")
        if not JP_SUBTITLE_STAGE2_SCRIPT.is_file():
            raise HTTPException(status_code=503, detail="자막 추출 스크립트를 찾을 수 없습니다")
        job_id = uuid.uuid4().hex
        run_id = uuid.uuid4().hex[:12]
        work_dir = SHIFT_ALARM_SUBTITLE_DIR / "work" / job_id
        work_dir.mkdir(parents=True, exist_ok=True)
        # av4 폴더 전체가 아니라 이 파일 하나만 넘기기 위해 격리된 작업 폴더로
        # 복사한다(subtitle_notion_epub_only.sh는 폴더 안 영상을 전부 처리함).
        # move가 아니라 copy — 원본은 iPhone 전송 기능이 계속 쓸 수 있게 둔다.
        try:
            shutil.copy2(path, work_dir / path.name)
        except OSError as exc:
            shutil.rmtree(work_dir, ignore_errors=True)
            raise HTTPException(status_code=503, detail="영상 파일을 작업 폴더로 복사하지 못했습니다") from exc
        env = os.environ.copy()
        env["JP_SUBTITLE_RUN_ID"] = run_id
        try:
            subprocess.Popen(
                ["zsh", str(JP_SUBTITLE_STAGE2_SCRIPT), str(work_dir)], env=env,
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except OSError as exc:
            shutil.rmtree(work_dir, ignore_errors=True)
            raise HTTPException(status_code=503, detail="자막 추출 작업을 시작하지 못했습니다") from exc
        _shift_alarm_subtitle_write_status({
            "job_id": job_id, "run_id": run_id, "file_id": file_id, "state": "running",
            "stage": "새 터미널 창에서 자막·번역·후리가나·Notion·EPUB 생성 중", "progress": 5,
            "filename": path.name, "work_dir": str(work_dir),
            "created_at": _now(), "updated_at": _now(),
        })
        _shift_alarm_update_processing(
            file_id, path.name, subtitle_state="running", subtitle_progress=5,
            subtitle_stage="새 터미널 창에서 자막·번역·후리가나·Notion·EPUB 생성 중",
            subtitle_started_at=_now(), subtitle_completed_at=None,
        )
        return {"ok": True, "message": f"{path.name} 자막 추출을 시작했습니다. Mac에서 새 터미널 창이 열립니다."}
    if body.action == "retry_dating_scenario":
        status = _shift_alarm_subtitle_status()
        if status.get("file_id") != file_id:
            raise HTTPException(status_code=409, detail="현재 표시된 작업과 영상이 일치하지 않습니다")
        if status.get("scenario_retry_state") == "running" and _process_is_alive(status.get("scenario_retry_pid")):
            raise HTTPException(status_code=409, detail="미연시 시나리오를 이미 다시 생성하고 있습니다")
        book_dir = _jp_subtitle_book_dir(path.name)
        generator = JP_SUBTITLE_DIR / "generate_dating_sim_scenario.py"
        if not book_dir.is_dir():
            raise HTTPException(status_code=409, detail="완성된 자막·번역·EPUB 폴더를 찾을 수 없습니다")
        if not generator.is_file():
            raise HTTPException(status_code=503, detail="미연시 시나리오 생성기를 찾을 수 없습니다")
        log_path = book_dir / "dating_sim_scenario_retry.log"
        try:
            log_handle = open(log_path, "ab", buffering=0)
            process = subprocess.Popen(
                ["/opt/anaconda3/bin/python3", str(generator), str(book_dir)],
                stdin=subprocess.DEVNULL, stdout=log_handle, stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            log_handle.close()
        except OSError as exc:
            raise HTTPException(status_code=503, detail="미연시 시나리오 재실행을 시작하지 못했습니다") from exc
        status.update(
            scenario_retry_state="running", scenario_retry_pid=process.pid,
            scenario_retry_log=str(log_path), scenario_retry_reason=None,
            scenario_retry_started_at=_now(), updated_at=_now(),
        )
        _shift_alarm_subtitle_write_status(status)
        return {"ok": True, "message": "기존 자막·번역·EPUB을 유지하고 미연시 시나리오만 다시 시작했습니다."}
    if body.action == "retry_dating_images":
        status = _shift_alarm_subtitle_status()
        if status.get("file_id") != file_id:
            raise HTTPException(status_code=409, detail="현재 표시된 작업과 영상이 일치하지 않습니다")
        if status.get("image_retry_state") == "running" and _process_is_alive(status.get("image_retry_pid")):
            raise HTTPException(status_code=409, detail="미연시 이미지를 이미 다시 생성하고 있습니다")
        book_dir = _jp_subtitle_book_dir(path.name)
        generator = JP_SUBTITLE_DIR / "generate_dating_sim_images.py"
        if not (book_dir / "dating_sim_scenario.json").is_file():
            raise HTTPException(status_code=409, detail="먼저 미연시 시나리오를 완성해야 합니다")
        if not generator.is_file():
            raise HTTPException(status_code=503, detail="미연시 이미지 생성기를 찾을 수 없습니다")
        log_path = book_dir / "dating_sim_images_retry.log"
        try:
            log_handle = open(log_path, "ab", buffering=0)
            process = subprocess.Popen(
                ["/opt/anaconda3/bin/python3", str(generator), str(book_dir)],
                stdin=subprocess.DEVNULL, stdout=log_handle, stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            log_handle.close()
        except OSError as exc:
            raise HTTPException(status_code=503, detail="미연시 이미지 재실행을 시작하지 못했습니다") from exc
        status.update(
            image_retry_state="running", image_retry_pid=process.pid,
            image_retry_log=str(log_path), image_retry_reason=None,
            image_retry_started_at=_now(), updated_at=_now(),
        )
        _shift_alarm_subtitle_write_status(status)
        return {"ok": True, "message": "완성된 시나리오는 유지하고 미연시 이미지 단계만 다시 시작했습니다."}
    if body.action == "mark_photo_shortcut":
        executed_at = _now()
        _shift_alarm_update_processing(file_id, path.name, photo_shortcut_at=executed_at)
        return {"ok": True, "message": "사진 저장·원본 삭제 단축어 실행을 기록했습니다", "executed_at": executed_at}
    if body.action == "cancel_transfer":
        # ★ 2026-09-14: "전송중에서 멈춰있는데 어떻게하지" — 터널이 전송 도중
        # 연결을 끊어버리면 스트리밍 제너레이터의 finally 블록이 아예 실행되지
        # 않아 video_transfers 행이 영원히 "downloading" 상태로 남는다. 그
        # 상태면 프런트엔드가 재생버튼을 계속 비활성화해 사용자가 다시
        # 시도할 방법이 없었다. 이 상태를 "interrupted"로 강제 전환해 버튼을
        # 다시 누를 수 있게 한다 — 원본 파일은 건드리지 않는다.
        with _shift_alarm_video_db() as conn:
            conn.execute(
                "UPDATE video_transfers SET state='interrupted', updated_at=?, completed_at=? "
                "WHERE file_id=? AND state='downloading'",
                (_now(), _now(), file_id),
            )
        return {"ok": True, "message": "전송을 중지했습니다. 버튼을 다시 눌러 받아보세요"}
    if body.action == "delete":
        try:
            path.unlink()
            os.utime(SHIFT_ALARM_VIDEO_FILES, None)
        except OSError as exc:
            raise HTTPException(status_code=503, detail="Mac 원본 파일을 삭제하지 못했습니다") from exc
        if path.exists():
            raise HTTPException(status_code=503, detail="삭제 후에도 Mac 원본 파일이 남아 있습니다")
        with _shift_alarm_video_db() as conn:
            conn.execute("DELETE FROM video_downloads WHERE file_path=?", (str(path),))
            conn.execute("DELETE FROM video_transfers WHERE file_id=?", (file_id,))
            conn.execute("DELETE FROM video_processing_history WHERE file_id=?", (file_id,))
        remaining = _shift_alarm_av4_files()
        return {
            "ok": True, "message": "av4의 Mac 원본 파일을 삭제했습니다",
            "deleted_file_id": file_id, "remaining_count": len(remaining),
            "library_revision": _shift_alarm_av4_revision(remaining),
        }
    raise HTTPException(status_code=400, detail="지원하지 않는 파일 동작입니다")


@app.post("/api/shift-alarm/video-download/{job_id}/action")
def act_on_shift_alarm_video(job_id: str, body: ShiftAlarmVideoActionRequest, request: Request):
    _require_owner(request)
    row, path = _shift_alarm_owned_video(job_id, _request_username(request))
    if body.action == "delete":
        path.unlink(missing_ok=True)
        with _shift_alarm_video_db() as conn:
            conn.execute("DELETE FROM video_downloads WHERE job_id=?", (job_id,))
        return {"ok": True, "message": "Mac 보관 파일을 삭제했습니다"}
    if body.action == "reveal_airdrop":
        subprocess.Popen(["/usr/bin/open", "-R", str(path)], stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.Popen(["/usr/bin/open", "airdrop://"], stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return {"ok": True, "message": "Mac에서 파일과 AirDrop 창을 열었습니다"}
    if body.action == "icloud":
        destination = Path(os.path.expanduser(
            "~/Library/Mobile Documents/com~apple~CloudDocs/Shift Alarm Downloads"
        )) / row["filename"]
        manifest_dir = Path(os.path.expanduser("~/.shift_alarm_icloud_sync"))
        manifest_dir.mkdir(parents=True, exist_ok=True)
        manifest = manifest_dir / f"manifest_{uuid.uuid4().hex}.txt"
        manifest.write_text(f"{path}\t{destination}\n", encoding="utf-8")
        os.chmod(manifest, 0o600)
        helper = REPO_ROOT / "shift_alarm" / "iCloudSync.app"
        if not helper.is_dir():
            raise HTTPException(status_code=503, detail="iCloud 전송 도우미를 찾을 수 없습니다")
        subprocess.Popen(["/usr/bin/open", "-na", str(helper)], stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return {"ok": True, "message": "iCloud Drive 전송을 요청했습니다"}
    raise HTTPException(status_code=400, detail="지원하지 않는 파일 동작입니다")


def _read_career_card(filename: str):
    path = CAREER_DATA_DIR / filename
    if not path.exists():
        return None
    try:
        result = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    result["updated_at"] = datetime.datetime.fromtimestamp(
        path.stat().st_mtime, datetime.timezone.utc
    ).isoformat(timespec="seconds")
    return result


def _career_preparation(text: str, contest: bool = False):
    """AI 호출 없이 제목·기술 신호로 안전한 학습/자격 후보를 제시한다."""
    haystack = (text or "").lower()
    rules = [
        (("python", "백엔드", "개발자"), ["Python 실전 프로젝트", "API·데이터베이스 설계", "테스트·배포 자동화"], ["정보처리기사", "SQLD"]),
        (("ai", "인공지능", "데이터", "머신러닝"), ["데이터 전처리와 검증", "모델 평가·오류 분석", "작은 결과물 포트폴리오"], ["ADsP", "SQLD"]),
        (("반도체", "공정", "tcad", "품질"), ["반도체 공정 기초", "통계적 품질관리", "공정 데이터 분석"], ["품질경영기사", "산업안전기사"]),
        (("전기", "설비", "시설"), ["전기 회로·설비 기초", "안전 규정과 점검", "설비 이력 데이터화"], ["전기기사", "산업안전기사"]),
        (("마케팅", "기획", "사업"), ["시장·고객 문제 정의", "성과지표 설계", "제안서 사례 만들기"], ["사회조사분석사"]),
    ]
    study, certs = [], []
    for keys, topics, licenses in rules:
        if any(key in haystack for key in keys):
            study.extend(topics); certs.extend(licenses)
    if contest:
        study.extend(["평가기준 역산", "베이스라인 구현", "실험 기록과 발표 자료"])
    if not study:
        study = ["공고 원문의 필수요건 분해", "관련 미니 프로젝트", "성과 중심 사례 정리"]
    return {"study": list(dict.fromkeys(study))[:5], "certificates": list(dict.fromkeys(certs))[:4], "notice": "자격증은 필수요건이 아니라 직무 연관성을 확인할 후보입니다."}


def _source_grounded_preparation(text: str):
    normalized = re.sub(r"[ \t]+", " ", text or "")
    # 사람인 템플릿은 `📋 주요업무`처럼 제목 앞에 아이콘을 붙인다. 예전
    # 정규식은 줄 첫 글자가 곧 제목일 때만 인정해 본문이 있어도 추출 실패로
    # 오판했다. 줄 앞의 짧은 장식 문자열을 허용하되 제목 목록은 고정한다.
    markers = [(m.start(), m.group(1)) for m in re.finditer(r"(?im)(?:^|\n)\s*(?:[^\w가-힣\n]{0,12})\s*(모집분야|주요업무|담당업무|직무내용|자격요건|지원자격(?:\s*및\s*우대사항)?|필수사항|우대사항|공모내용|참가자격|평가기준)\s*[:：]?", normalized)]
    sections = {}
    for i, (start, name) in enumerate(markers):
        end = markers[i + 1][0] if i + 1 < len(markers) else min(len(normalized), start + 2200)
        body = normalized[start:end].strip()
        if body: sections.setdefault(name, body[:1800])
    evidence = "\n".join(sections.values())
    if not evidence:
        return {"sections": {}, "study": [], "certificates": [], "recommended_certificates": [], "grounded": False, "notice": "원문에서 자격요건·우대사항 구획을 확인하지 못해 준비 항목을 만들지 않았습니다."}
    topics = [
        ("Python", ("python",), "문법 복습보다 함수·클래스·예외 처리와 타입 힌트를 실제 코드에 적용하고, pytest로 핵심 로직을 검증하세요.", "공고 업무를 축소한 CLI 또는 자동화 도구 1개를 만들고 README에 실행법·테스트 결과를 남기세요."),
        ("SQL·데이터베이스", ("sql", "database", "데이터베이스"), "SELECT·JOIN·집계·서브쿼리부터 인덱스와 실행계획까지 순서대로 익히고, 트랜잭션과 정규화 기준을 설명할 수 있게 연습하세요.", "샘플 업무 데이터를 직접 설계해 조회 API를 만들고, 느린 쿼리 전후 실행계획과 개선 수치를 기록하세요."),
        ("REST API 설계", ("rest", "api"), "HTTP 메서드·상태 코드·인증·검증·페이지네이션·오류 응답 규칙을 정한 뒤 OpenAPI 문서와 테스트를 함께 작성하세요.", "CRUD API 하나를 구현하고 정상·권한 없음·잘못된 입력·중복 요청 테스트를 자동화하세요."),
        ("클라우드·배포", ("aws", "gcp", "azure", "docker", "kubernetes"), "Docker 이미지 작성, 환경변수·비밀값 분리, 로그·헬스체크를 먼저 익힌 뒤 클라우드 배포와 CI/CD로 확장하세요.", "작은 서비스를 컨테이너로 배포하고 장애 재시작, 배포 롤백, 모니터링 화면을 증빙으로 남기세요."),
        ("머신러닝 모델링", ("머신러닝", "machine learning", "딥러닝", "pytorch", "tensorflow"), "문제 정의→데이터 분할→베이스라인→평가지표→오류 분석 순으로 반복하고 데이터 누수와 과적합을 점검하세요.", "공개 데이터로 베이스라인과 개선 모델을 비교해 실험표·오류 사례·재현 명령을 정리하세요."),
        ("데이터 분석·통계", ("데이터 분석", "통계", "pandas"), "결측·이상치 처리, 탐색적 분석, 가설과 지표 설정, 시각화 해석을 실제 데이터로 반복하세요.", "업무 질문 3개를 정하고 pandas 분석 노트북과 의사결정 요약 한 페이지를 완성하세요."),
        ("반도체 공정", ("반도체", "공정", "tcad"), "공정 흐름과 핵심 파라미터를 정리한 뒤 TCAD 입력 조건·경계조건·메시 설정이 결과에 미치는 영향을 실험하세요.", "한 공정 변수의 변화에 따른 전기적 특성을 비교하고 가정·그래프·해석을 보고서로 남기세요."),
        ("품질관리", ("품질", "six sigma", "6시그마"), "공정능력·관리도·측정시스템·원인분석을 익히고 DMAIC 단계마다 어떤 데이터를 확인하는지 연습하세요.", "불량 데이터 예제로 파레토·관리도·원인 가설·개선 전후 지표를 포함한 품질 보고서를 만드세요."),
        ("프로젝트·발표 준비", ("평가기준", "발표", "포트폴리오"), "평가기준을 점수 항목으로 바꾸고 각 항목에 필요한 증거·실험·설명을 역산해 일정표를 만드세요.", "문제·선택 이유·실험 결과·한계를 5분 발표와 1페이지 요약으로 만들고 예상 질문에 답해보세요."),
    ]
    lowered = evidence.lower()
    study = [
        {"topic": label, "how": how, "practice": practice}
        for label, keys, how, practice in topics if any(key in lowered for key in keys)
    ]
    if not study:
        study = [{
            "topic": "공고 핵심요건 실전 준비",
            "how": "원문의 주요업무와 자격요건을 한 문장씩 분리해 ‘알고 있음·해본 적 있음·결과로 증명 가능’ 세 단계로 표시하고, 부족한 항목부터 작은 실습으로 보완하세요.",
            "practice": "주요업무 하나를 축소 재현한 결과물과 문제·선택·실행·결과를 설명하는 1페이지 사례 문서를 완성하세요.",
        }]
    cert_names = ("정보처리기사", "SQLD", "SQLP", "ADsP", "ADP", "빅데이터분석기사", "품질경영기사", "산업안전기사", "전기기사", "전자기사", "토익", "TOEIC", "OPIc")
    certificates = [name for name in cert_names if name.lower() in lowered]
    certificate_rules = [
        (("python", "java", "javascript", "typescript", "개발", "api", "백엔드"), "정보처리기사", "소프트웨어 개발·데이터베이스·운영 전반의 기본기를 직무 범위와 함께 증명하기 좋습니다."),
        (("sql", "database", "데이터베이스", "db"), "SQLD", "SQL 작성과 데이터 모델링 역량이 필요한 업무에 직접 연결됩니다."),
        (("데이터 분석", "통계", "pandas", "분석"), "ADsP", "데이터 이해·분석 기획·기초 통계 역량을 체계적으로 정리하는 데 적합합니다."),
        (("빅데이터", "머신러닝", "machine learning", "딥러닝", "pytorch", "tensorflow"), "빅데이터분석기사", "데이터 전처리부터 모델링·평가까지 실무형 분석 과정을 폭넓게 다룹니다."),
        (("품질", "six sigma", "6시그마", "공정관리"), "품질경영기사", "공정 품질·통계적 관리·개선 업무와 가장 직접적으로 연결됩니다."),
        (("안전", "산업안전", "설비", "현장"), "산업안전기사", "현장 위험관리와 안전 규정 이해가 필요한 업무의 직무 연관성이 높습니다."),
        (("전기", "전력", "전기설비"), "전기기사", "전기 설비의 설계·운영·안전 업무에 요구되는 전문성을 증명합니다."),
        (("전자", "반도체", "회로", "tcad"), "전자기사", "전자회로·소자·계측 기초가 필요한 반도체·전자 직무와 연결됩니다."),
        (("영어", "global", "글로벌", "해외", "영문"), "OPIc", "업무상 영어 의사소통 능력을 말하기 중심으로 증명하기 좋습니다."),
    ]
    recommended_certificates = []
    explicit_folded = {name.casefold() for name in certificates}
    for keys, name, reason in certificate_rules:
        if name.casefold() not in explicit_folded and any(key in lowered for key in keys):
            recommended_certificates.append({"name": name, "reason": reason, "required": False})
    return {"sections": sections, "study": study[:8], "certificates": certificates,
            "recommended_certificates": recommended_certificates[:3], "grounded": bool(markers),
            "notice": "추천 자격증은 원문에 명시된 필수조건이 아니라, 확인된 업무·기술과의 연관성을 기준으로 고른 준비 후보입니다."}


@app.get("/api/career-source-analysis")
def career_source_analysis(request: Request, kind: str, source: str, source_id: str):
    _require_signed_in_user(request)
    table, db_name = ("contests", "contests.db") if kind == "contest" else ("jobs", "jobs.db")
    db_path = CAREER_DATA_DIR / db_name
    conn = sqlite3.connect(str(db_path)); conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(f"SELECT url,title FROM {table} WHERE source=? AND source_id=?", (source, source_id)).fetchone()
    finally: conn.close()
    if not row: raise HTTPException(status_code=404, detail="수집된 항목을 찾지 못했습니다")
    cache_dir = CAREER_DATA_DIR / "web_source_cache"
    cache_path = cache_dir / (hashlib.sha256(f"v5:{kind}:{source}:{source_id}".encode()).hexdigest() + ".json")
    if cache_path.exists():
        try: return json.loads(cache_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError): pass
    # 원문 크롤링·브라우저 렌더링·OCR은 외부 접속과 캐시 쓰기가 수반된다.
    # 일반 사용자는 이미 준비된 분석은 읽을 수 있지만 새 작업을 실행하지 않는다.
    if not _is_owner_request(request):
        return {"ok": False, "detail": "원문 분석이 아직 준비되지 않았습니다. 관리자가 분석한 뒤 모든 사용자가 함께 볼 수 있습니다."}
    cache_dir.mkdir(exist_ok=True)
    url = row["url"]
    if "사람인" in source and source_id.isdigit():
        url = f"https://www.saramin.co.kr/zf_user/jobs/view?rec_idx={source_id}"
    if not re.match(r"^https://", url or ""): raise HTTPException(status_code=400, detail="안전한 원문 주소가 아닙니다")
    text = ""
    fetch_error = None
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 CareerDashboard/1.0"})
        with urllib.request.urlopen(req, timeout=15) as response:
            raw = response.read(2_000_000).decode(response.headers.get_content_charset() or "utf-8", errors="replace")
        raw = re.sub(r"(?is)<(script|style|svg).*?</\1>", " ", raw)
        text = html.unescape(re.sub(r"(?s)<[^>]+>", "\n", raw))
        text = re.sub(r"\n{3,}", "\n\n", text).strip()
    except Exception as exc:
        fetch_error = type(exc).__name__

    preparation = _source_grounded_preparation(text)
    extraction = "html"
    # 정적 요청 자체가 실패했거나 실제 공고 구획이 없으면 JS 렌더링/이미지형
    # 공고일 수 있다. 이때만 Playwright → 화면 캡처 → 비전 판독으로 재시도한다.
    if kind == "job" and not preparation["grounded"]:
        try:
            if str(CAREER_SYSTEM_DIR) not in sys.path:
                sys.path.insert(0, str(CAREER_SYSTEM_DIR))
            from job_collector import fetch_job_detail_via_screenshot
            visual_text = fetch_job_detail_via_screenshot(url, CAREER_SYSTEM_DIR)
            if visual_text:
                preparation = _source_grounded_preparation(visual_text)
                if preparation["grounded"]:
                    extraction = "visual"
        except Exception as exc:
            fetch_error = type(exc).__name__

    if preparation["grounded"]:
        result = {"ok": True, "title": row["title"], "preparation": preparation,
                  "extraction": extraction,
                  "fetched_at": _now()}
    else:
        result = {"ok": False, "detail": "HTML·브라우저 렌더링·화면 OCR에서도 주요업무·자격요건·우대사항을 확인하지 못했습니다. 로그인이나 접근 제한이 있는 원문은 직접 확인해 주세요.", "error_type": fetch_error or "ContentUnavailable"}
    if result.get("ok") and preparation["grounded"]:
        try: cache_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError: pass
    return result


CAREER_CONSULT_ROOM_ID = "custom_0e5dc0b026"
CAREER_HR_PERSONA_NAME = "인사담당자"
CAREER_HR_SYSTEM_PROMPT = """당신은 이직 준비방의 인사담당자 페르소나입니다. 사이트의 '담당자와 상담하기'에서 전달된 특정 공고를 기준으로 상담합니다. 먼저 회사와 직무, 실제 주요업무·자격요건·우대사항을 구분해 설명하고, 후보자에게 맞는 점과 부족한 점을 근거와 함께 말하세요. 이어서 이 공고에서 나올 가능성이 높은 직무·경험 면접 질문과 답변 준비법, 자소서에 연결할 경험과 피해야 할 과장을 구체적으로 알려주세요.

공고에서 요구하지만 후보자의 확인된 경험에는 없는 기술을 발견하면 부족하다고만 말하고 끝내지 마세요. 기술마다 공고의 실제 업무와 연결되는 포트폴리오 프로젝트 아이디어를 2~3개 제시하고, 그중 가장 적합한 하나를 추천하세요. 예를 들어 RAG라면 임의의 챗봇이 아니라 해당 기업의 문서·도면·BOM·업무 절차처럼 공고와 맞는 자료를 어떤 방식으로 수집·분할·검색·평가할지까지 설명하고, Linux·vLLM/Ollama·FastAPI·React·Docker·비전검사 등도 실제 운영·배포·장애 대응 능력을 증명할 수 있는 프로젝트로 구체화하세요. 각 추천 프로젝트에는 ① 해결할 문제와 사용자 ② 최소 기능과 기술 구성 ③ 구현 순서 ④ 2~4주 일정 ⑤ 완성 산출물과 측정 기준 ⑥ 면접·자소서에서 설명할 포인트를 포함하세요. 관련 기술이 여러 개면 하나의 통합 프로젝트로 묶는 방안과 기술별 소형 프로젝트 방안을 함께 비교하고, 현재 수준에서 선행 학습이 필요한 항목도 순서대로 알려주세요. 공고와 관계없는 유행 기술을 억지로 넣거나 실제로 하지 않은 경험을 완성한 것처럼 표현하지 마세요.

공고에 없거나 확인하지 못한 조건과 후보자 경험은 지어내지 말고, 불확실한 정보는 불확실하다고 밝히세요. 외부 지원·문서 수정은 하지 않고 상담과 초안 제안만 합니다."""


class CareerConsultRequest(BaseModel):
    kind: str = "job"
    source: str
    source_id: str


@app.post("/api/career-consult")
def start_career_consult(body: CareerConsultRequest, request: Request):
    """소유자가 고른 공고 한 건만 인사담당자에게 전달해 상담 턴을 만든다."""
    _require_owner(request)
    if body.kind != "job":
        raise HTTPException(status_code=400, detail="채용공고만 인사담당자와 상담할 수 있습니다")
    source, source_id = body.source.strip(), body.source_id.strip()
    if not source or len(source) > 100 or not source_id or len(source_id) > 200:
        raise HTTPException(status_code=400, detail="공고 식별값이 올바르지 않습니다")
    jobs = sqlite3.connect(str(CAREER_DATA_DIR / "jobs.db")); jobs.row_factory = sqlite3.Row
    try:
        row = jobs.execute(
            """SELECT source,source_id,title,company,url,location,experience,education,
                      employment_type,salary,deadline,skills,keywords,matched_query
                 FROM jobs WHERE source=? AND source_id=? LIMIT 1""",
            (source, source_id),
        ).fetchone()
    finally:
        jobs.close()
    if not row:
        raise HTTPException(status_code=404, detail="수집된 공고를 찾지 못했습니다")

    cache_path = CAREER_DATA_DIR / "web_source_cache" / (
        hashlib.sha256(f"v5:job:{source}:{source_id}".encode()).hexdigest() + ".json"
    )
    grounded = ""
    try:
        cached = json.loads(cache_path.read_text(encoding="utf-8"))
        if cached.get("ok"):
            grounded = json.dumps(cached.get("preparation") or {}, ensure_ascii=False)[:7000]
    except (OSError, json.JSONDecodeError):
        pass
    fields = [
        f"회사: {row['company']}", f"공고명: {row['title']}", f"출처: {row['source']}",
        # 긴 추적 쿼리 URL은 모바일 시스템 메시지 폭을 깨뜨리고 상담 생성에는
        # 필요하지 않다. 원문 열기는 공고 상세 화면의 전용 버튼이 담당한다.
        f"지역: {row['location'] or '미기재'}",
        f"경력: {row['experience'] or '미기재'}", f"학력: {row['education'] or '미기재'}",
        f"고용형태: {row['employment_type'] or '미기재'}", f"급여: {row['salary'] or '미기재'}",
        f"마감: {row['deadline'] or '미기재'}", f"수집 기술: {row['skills'] or row['keywords'] or '미기재'}",
    ]
    if grounded:
        fields.append("원문 추출 결과: " + grounded)
    content = "📋 공고 상담 요청\n" + "\n".join(fields) + (
        "\n\n이 공고의 실제 업무와 지원 적합도를 설명하고, 예상 면접 질문·답변 준비법과 "
        "이 공고에 맞춘 자소서 작성 포인트를 상담해주세요."
    )

    conn = get_conn()
    try:
        now = _now()
        conn.execute(
            """INSERT OR IGNORE INTO personas
               (name,notion_page_id,system_prompt,group_name,owner_username,description,synced_at)
               VALUES (?, '', ?, '이직시스템', NULL, ?, ?)""",
            (CAREER_HR_PERSONA_NAME, CAREER_HR_SYSTEM_PROMPT,
             "채용공고 설명, 면접 준비, 자기소개서 상담을 담당합니다.", now),
        )
        # 이미 만들어진 기본 인사담당자도 최신 상담 지침을 사용해야 한다.
        # 사용자가 만든 동명 페르소나는 건드리지 않고 이직시스템 공용 항목만 갱신한다.
        conn.execute(
            """UPDATE personas SET system_prompt=?, description=?, synced_at=?
                 WHERE name=? AND group_name='이직시스템' AND owner_username IS NULL""",
            (CAREER_HR_SYSTEM_PROMPT,
             "채용공고 설명, 기술별 프로젝트 설계, 면접 준비, 자기소개서 상담을 담당합니다.",
             now, CAREER_HR_PERSONA_NAME),
        )
        conn.execute(
            "INSERT OR IGNORE INTO room_invites(room_id,persona_name,invited_at) VALUES (?,?,?)",
            (CAREER_CONSULT_ROOM_ID, CAREER_HR_PERSONA_NAME, now),
        )
        cursor = conn.execute(
            "INSERT INTO messages(room_id,sender,content,created_at,is_system) VALUES (?,'system',?,?,1)",
            (CAREER_CONSULT_ROOM_ID, content, now),
        )
        conn.execute(
            """INSERT INTO pending_turns(persona_name,room_id,status,created_at,source_message_id)
               VALUES (?,?,'pending',?,?)""",
            (CAREER_HR_PERSONA_NAME, CAREER_CONSULT_ROOM_ID, now, cursor.lastrowid),
        )
        conn.commit()
    finally:
        conn.close()
    return {"ok": True, "room_id": CAREER_CONSULT_ROOM_ID,
            "url": f"/#room={urllib.parse.quote(CAREER_CONSULT_ROOM_ID, safe='')}"}


def _company_profile_url(company: str):
    safe_name = re.sub(r"[^\w가-힣-]+", "_", company or "")
    path = CAREER_DATA_DIR / "company_profiles" / f"{safe_name}.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    except (OSError, json.JSONDecodeError):
        data = None
    return data.get("url") if isinstance(data, dict) else None


def _published_analysis_url(kind: str, title: str, company: str):
    pattern = "top_contest_notion*.json" if kind == "contest" else "top_job_notion*.json"
    for path in CAREER_DATA_DIR.glob(pattern):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        subject = data.get("organizer") if kind == "contest" else data.get("company")
        if data.get("title") == title and (not subject or subject == company):
            return data.get("url")
    return None


_CAREER_DEADLINE_YMD_RE = re.compile(r"(20\d{2})[.\-/]\s*(\d{1,2})[.\-/]\s*(\d{1,2})")
_CAREER_DEADLINE_Y2MD_RE = re.compile(r"(?<!\d)'?(\d{2})[.\-]\s*(\d{1,2})[.\-]\s*(\d{1,2})\s*\.")
_CAREER_DEADLINE_YMD_KO_RE = re.compile(r"(20\d{2})년\s*(\d{1,2})월\s*(\d{1,2})일")
_CAREER_DEADLINE_MD_RE = re.compile(r"(?<!\d)(\d{1,2})[.\-/]\s*(\d{1,2})(?!\d)")
_CAREER_DEADLINE_MD_KO_RE = re.compile(r"(?<!\d)(\d{1,2})월\s*(\d{1,2})일")


def _career_deadline_end(deadline: str, today: "datetime.date"):
    """마감일 문자열에서 접수 종료일을 최대한 뽑아낸다(이직시스템의
    job_collector/contest_collector 정리 배치와 같은 방식 — ★ 2026-09-12,
    "왜 마감 지난 공고·대회가 아직도 뜨나" 요청으로 웹 화면에도 적용).
    "A ~ B" 범위는 뒷부분을, 연도 없는 표기는 문자열 전체에서 찾은 연도를
    이어받는다. 형식을 못 알아보면 None(모르면 걸러내지 않는다)."""
    text = (deadline or "").strip()
    if not text or any(marker in text for marker in ("상시", "채용시", "수시")):
        return None
    year = None
    for pattern, to_year in (
        (_CAREER_DEADLINE_YMD_RE, lambda g: int(g[0])),
        (_CAREER_DEADLINE_Y2MD_RE, lambda g: 2000 + int(g[0])),
        (_CAREER_DEADLINE_YMD_KO_RE, lambda g: int(g[0])),
    ):
        matches = pattern.findall(text)
        if matches:
            year = to_year(matches[-1])
    tail = text.rsplit("~", 1)[-1] if "~" in text else text
    for pattern, build in (
        (_CAREER_DEADLINE_YMD_RE, lambda g: (int(g[0]), int(g[1]), int(g[2]))),
        (_CAREER_DEADLINE_Y2MD_RE, lambda g: (2000 + int(g[0]), int(g[1]), int(g[2]))),
        (_CAREER_DEADLINE_YMD_KO_RE, lambda g: (int(g[0]), int(g[1]), int(g[2]))),
    ):
        matches = pattern.findall(tail)
        if matches:
            y, m, d = build(matches[-1])
            try:
                return datetime.date(y, m, d)
            except ValueError:
                return None
    for pattern in (_CAREER_DEADLINE_MD_RE, _CAREER_DEADLINE_MD_KO_RE):
        matches = pattern.findall(tail)
        if matches:
            m, d = matches[-1]
            use_year = year if year is not None else today.year
            try:
                candidate = datetime.date(use_year, int(m), int(d))
            except ValueError:
                return None
            if year is None and candidate < today - datetime.timedelta(days=180):
                candidate = datetime.date(use_year + 1, int(m), int(d))
            return candidate
    return None


def _career_deadline_expired(deadline: str, today: "datetime.date") -> bool:
    end = _career_deadline_end(deadline, today)
    return end is not None and end < today


@app.get("/api/career-summary")
def career_summary(request: Request):
    """로그인 사용자에게 최신 추천 요약을 제공한다.

    후보자 개인정보와 API 키는 내보내지 않고, 이미 공개용 추천 결과 JSON에
    적힌 회사·공고·점수·링크만 최소한으로 전달한다.
    """
    _require_signed_in_user(request)
    return {
        "career": _read_career_card("top_job_notion_career.json"),
        "parttime": _read_career_card("top_job_notion_parttime.json"),
    }


_CAREER_SORT_ORDER = {
    "recommended": "score DESC, last_seen_at DESC",
    "score": "score DESC, last_seen_at DESC",
    "deadline": "CASE WHEN deadline='' THEN 1 ELSE 0 END, deadline ASC",
    "new": "first_seen_at DESC",
    "recent": "last_seen_at DESC",
}


@app.get("/api/career-jobs")
def career_jobs(request: Request, q: str = "", source: str = "", sort: str = "recommended", limit: int = 40, offset: int = 0):
    """소유자에게 수집 DB의 공고를 웹앱용으로 페이지 단위 제공한다.

    ★ 2026-09-12: 마감이 확실히 지난 공고는 정리 배치(하루 1회, 7일 유예)가
    돌기 전까지 화면에 계속 보이던 문제 — 여기서도 같은 마감 판정을 적용해
    만료된 행은 즉시 화면에서 숨긴다(DB 삭제는 기존 정리 배치가 그대로 담당,
    유예 기간을 건드리지 않아 실수로 지운 데이터를 복구할 여유는 유지된다).
    """
    _require_signed_in_user(request)
    db_path = CAREER_DATA_DIR / "jobs.db"
    if not db_path.exists():
        return {"jobs": [], "total": 0, "stats": {}, "sources": []}
    limit = max(1, min(limit, 100))
    offset = max(0, offset)
    where, params = [], []
    if q.strip():
        needle = f"%{q.strip()}%"
        where.append("(title LIKE ? OR company LIKE ? OR location LIKE ? OR skills LIKE ? OR matched_query LIKE ?)")
        params.extend([needle] * 5)
    if source.strip():
        where.append("source = ?")
        params.append(source.strip())
    clause = " WHERE " + " AND ".join(where) if where else ""
    order = _CAREER_SORT_ORDER.get(sort, _CAREER_SORT_ORDER["recommended"])
    today = datetime.datetime.now().date()
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            f"""SELECT source, source_id, title, company, url, location, experience,
                       education, employment_type, salary, posted_at, deadline, skills,
                       score, matched_query, status, first_seen_at, last_seen_at
                FROM jobs{clause} ORDER BY {order}""",
            params,
        ).fetchall()
        visible = [row for row in rows if not _career_deadline_expired(row["deadline"], today)]
        total = len(visible)
        stats = dict(conn.execute("""SELECT COUNT(*) AS total,
            SUM(date(first_seen_at)=date('now','localtime')) AS today_new,
            SUM(date(last_seen_at)=date('now','localtime')) AS today_seen,
            MAX(last_seen_at) AS latest FROM jobs""").fetchone())
        sources = [row[0] for row in conn.execute("SELECT DISTINCT source FROM jobs ORDER BY source")]
        jobs = []
        for row in visible[offset:offset + limit]:
            item = dict(row)
            item["kind"] = "job"
            item["preparation"] = None
            item["company_analysis_url"] = _company_profile_url(item.get("company", ""))
            item["analysis_url"] = _published_analysis_url("job", item.get("title", ""), item.get("company", ""))
            jobs.append(item)
        return {"jobs": jobs, "total": total, "stats": stats, "sources": sources, "limit": limit, "offset": offset}
    finally:
        conn.close()


@app.get("/api/career-contests")
def career_contests(request: Request, q: str = "", source: str = "", sort: str = "recommended", limit: int = 40, offset: int = 0):
    """★ 2026-09-12: career_jobs와 같은 이유로 마감 지난 대회를 화면에서 즉시 숨긴다."""
    _require_signed_in_user(request)
    db_path = CAREER_DATA_DIR / "contests.db"
    if not db_path.exists():
        return {"jobs": [], "total": 0, "stats": {}, "sources": []}
    limit, offset = max(1, min(limit, 100)), max(0, offset)
    where, params = [], []
    if q.strip():
        needle = f"%{q.strip()}%"; where.append("(title LIKE ? OR organizer LIKE ? OR matched_query LIKE ?)"); params.extend([needle] * 3)
    if source.strip(): where.append("source = ?"); params.append(source.strip())
    clause = " WHERE " + " AND ".join(where) if where else ""
    order = _CAREER_SORT_ORDER.get(sort, _CAREER_SORT_ORDER["recommended"])
    today = datetime.datetime.now().date()
    conn = sqlite3.connect(str(db_path)); conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(f"SELECT source,source_id,title,organizer AS company,url,deadline,score,matched_query,first_seen_at,last_seen_at FROM contests{clause} ORDER BY {order}", params).fetchall()
        visible = [row for row in rows if not _career_deadline_expired(row["deadline"], today)]
        total = len(visible)
        stats = dict(conn.execute("SELECT COUNT(*) total,SUM(date(first_seen_at)=date('now','localtime')) today_new,SUM(date(last_seen_at)=date('now','localtime')) today_seen,MAX(last_seen_at) latest FROM contests").fetchone())
        sources = [r[0] for r in conn.execute("SELECT DISTINCT source FROM contests ORDER BY source")]
        items = []
        for row in visible[offset:offset + limit]:
            item = dict(row); item["kind"] = "contest"; item["preparation"] = None; item["analysis_url"] = _published_analysis_url("contest", item["title"], item.get("company", "")); items.append(item)
        return {"jobs": items, "total": total, "stats": stats, "sources": sources, "limit": limit, "offset": offset}
    finally: conn.close()


@app.get("/api/career-company-analysis")
def career_company_analysis(request: Request, company: str):
    _require_signed_in_user(request)
    company = company.strip()
    if not company or len(company) > 160: raise HTTPException(status_code=400, detail="회사명이 올바르지 않습니다")
    conn = sqlite3.connect(str(CAREER_DATA_DIR / "jobs.db")); conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("SELECT title,skills,location,employment_type,score,last_seen_at,url FROM jobs WHERE company=? ORDER BY last_seen_at DESC LIMIT 30", (company,)).fetchall()
    finally: conn.close()
    skill_counts = {}
    for row in rows:
        for skill in re.split(r"[,/|·]+", row["skills"] or ""):
            skill = skill.strip()
            if skill: skill_counts[skill] = skill_counts.get(skill, 0) + 1
    state_url, analysis_text = _company_profile_url(company), ""
    safe_name = re.sub(r"[^\w가-힣-]+", "_", company)
    state_path = CAREER_DATA_DIR / "company_profiles" / f"{safe_name}.json"
    try: analysis_text = json.loads(state_path.read_text(encoding="utf-8")).get("analysis_text", "")
    except (OSError, json.JSONDecodeError): pass
    return {"company": company, "posting_count": len(rows), "latest": rows[0]["last_seen_at"] if rows else None,
            "roles": [dict(row) for row in rows[:10]], "top_skills": sorted(skill_counts.items(), key=lambda x: (-x[1], x[0]))[:10],
            "analysis_text": analysis_text, "legacy_notion_url": state_url}


class SignupRequest(BaseModel):
    username: str
    password: str


class LoginRequest(BaseModel):
    username: str
    password: str


@app.post("/api/auth/signup")
def signup(body: SignupRequest, response: Response):
    username = body.username.strip()
    if not USERNAME_RE.match(username):
        raise HTTPException(status_code=400, detail="아이디는 한글/영문/숫자/밑줄 2~20자로 입력하세요")
    if len(body.password) < 4:
        raise HTTPException(status_code=400, detail="비밀번호는 4자 이상이어야 합니다")
    # ★ _bootstrap_owner()가 서버 시작 시 APP_USERNAME을 이미 선점해두므로
    # 정상 흐름에서는 아래 UNIQUE 체크에서 걸러진다. 그래도 혹시 순서가
    # 꼬이는 경우(예: 서버 재기동 사이 잠깐)를 대비해 명시적으로 한 번 더 막는다.
    if APP_USERNAME and username == APP_USERNAME:
        raise HTTPException(status_code=409, detail="이미 사용 중인 아이디입니다")
    conn = get_conn()
    try:
        if conn.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone():
            raise HTTPException(status_code=409, detail="이미 사용 중인 아이디입니다")
        salt, digest = auth.hash_password(body.password)
        cur = conn.execute(
            "INSERT INTO users (username, password_hash, salt, is_owner, created_at) VALUES (?, ?, ?, 0, ?)",
            (username, digest, salt, _now()),
        )
        conn.commit()
        token = auth.create_session(conn, cur.lastrowid)
    finally:
        conn.close()
    response.set_cookie(SESSION_COOKIE_NAME, token, max_age=SESSION_COOKIE_MAX_AGE, httponly=True, samesite="lax")
    return {"ok": True, "username": username, "is_owner": False}


@app.post("/api/auth/login")
def login(body: LoginRequest, response: Response):
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT id, username, password_hash, salt, is_owner, display_name, avatar_url FROM users WHERE username = ?",
            (body.username.strip(),),
        ).fetchone()
        if not row or not auth.verify_password(body.password, row["salt"], row["password_hash"]):
            raise HTTPException(status_code=401, detail="아이디 또는 비밀번호가 올바르지 않습니다")
        token = auth.create_session(conn, row["id"])
    finally:
        conn.close()
    response.set_cookie(SESSION_COOKIE_NAME, token, max_age=SESSION_COOKIE_MAX_AGE, httponly=True, samesite="lax")
    return {
        "ok": True, "username": row["username"], "is_owner": bool(row["is_owner"]),
        "display_name": row["display_name"], "avatar_url": row["avatar_url"],
    }


@app.post("/api/auth/logout")
def logout(request: Request, response: Response):
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if token:
        conn = get_conn()
        auth.delete_session(conn, token)
        conn.close()
    response.delete_cookie(SESSION_COOKIE_NAME)
    return {"ok": True}


def _unique_username_from(conn, display_name):
    """소셜 로그인 최초 가입 시 프로필 이름으로 로컬 계정명을 만든다.
    이미 있는 이름이면 뒤에 숫자를 붙여 유일하게 만든다."""
    base = re.sub(r"[^A-Za-z0-9_가-힣]", "", display_name)[:16] or "user"
    candidate = base
    n = 1
    while conn.execute("SELECT 1 FROM users WHERE username = ?", (candidate,)).fetchone():
        n += 1
        candidate = f"{base}{n}"
    return candidate


def _finish_oauth_login(provider, external_id, display_name, kakao_tokens=None):
    """구글/카카오 로그인 콜백의 공통 마무리 — 이미 연결된 계정이면 그대로
    로그인, 처음이면 새 로컬 계정을 만들어 연결한다(비밀번호는 무작위로
    채워두고 실제로 쓰이지 않음 — 이 계정은 소셜 로그인으로만 들어옴).

    kakao_tokens: talk_message 동의를 받았을 때만 실제 값이 들어있는
    {"access_token","refresh_token","expires_in"} — "카톡으로 로그인한
    사람한테는 카톡 알람이 가게" 요청(2026-08-27). 매 로그인마다 최신
    토큰으로 갱신 저장한다."""
    column = "google_sub" if provider == "google" else "kakao_id"
    conn = get_conn()
    try:
        row = conn.execute(f"SELECT id, is_owner FROM users WHERE {column} = ?", (external_id,)).fetchone()
        if row:
            user_id = row["id"]
        else:
            username = _unique_username_from(conn, display_name)
            salt, digest = auth.hash_password(secrets.token_urlsafe(24))
            cur = conn.execute(
                f"INSERT INTO users (username, password_hash, salt, is_owner, created_at, {column}) "
                "VALUES (?, ?, ?, 0, ?, ?)",
                (username, digest, salt, _now(), external_id),
            )
            conn.commit()
            user_id = cur.lastrowid
        if kakao_tokens and kakao_tokens.get("access_token"):
            expires_at = (
                datetime.datetime.now(datetime.timezone.utc)
                + datetime.timedelta(seconds=kakao_tokens.get("expires_in") or 0)
            ).isoformat()
            conn.execute(
                "UPDATE users SET kakao_access_token = ?, "
                "kakao_refresh_token = COALESCE(?, kakao_refresh_token), "
                "kakao_token_expires_at = ? WHERE id = ?",
                (kakao_tokens["access_token"], kakao_tokens.get("refresh_token"), expires_at, user_id),
            )
            conn.commit()
        token = auth.create_session(conn, user_id)
    finally:
        conn.close()
    response = RedirectResponse("/")
    response.set_cookie(SESSION_COOKIE_NAME, token, max_age=SESSION_COOKIE_MAX_AGE, httponly=True, samesite="lax")
    response.delete_cookie(OAUTH_STATE_COOKIE)
    return response


@app.get("/api/auth/google/login")
def google_login():
    if not oauth.google_enabled():
        raise HTTPException(status_code=503, detail="Google 로그인이 아직 설정되지 않았습니다")
    state = secrets.token_urlsafe(16)
    response = RedirectResponse(oauth.google_auth_url(state))
    response.set_cookie(OAUTH_STATE_COOKIE, state, max_age=600, httponly=True, samesite="lax")
    return response


@app.get("/api/auth/google/callback")
def google_callback(request: Request, code: str = "", state: str = ""):
    if not code or not state or state != request.cookies.get(OAUTH_STATE_COOKIE):
        raise HTTPException(status_code=400, detail="잘못된 요청입니다")
    try:
        profile = oauth.google_exchange(code)
    except oauth.OAuthError:
        raise HTTPException(status_code=502, detail="Google 인증에 실패했습니다")
    return _finish_oauth_login("google", profile["external_id"], profile["name"])


@app.get("/api/auth/kakao/login")
def kakao_login():
    if not oauth.kakao_enabled():
        raise HTTPException(status_code=503, detail="카카오 로그인이 아직 설정되지 않았습니다")
    state = secrets.token_urlsafe(16)
    response = RedirectResponse(oauth.kakao_auth_url(state))
    response.set_cookie(OAUTH_STATE_COOKIE, state, max_age=600, httponly=True, samesite="lax")
    return response


@app.get("/api/auth/kakao/callback")
def kakao_callback(request: Request, code: str = "", state: str = ""):
    if not code or not state or state != request.cookies.get(OAUTH_STATE_COOKIE):
        raise HTTPException(status_code=400, detail="잘못된 요청입니다")
    try:
        profile = oauth.kakao_exchange(code)
    except oauth.OAuthError:
        raise HTTPException(status_code=502, detail="카카오 인증에 실패했습니다")
    return _finish_oauth_login("kakao", profile["external_id"], profile["name"], kakao_tokens=profile)


class PersonaCreate(BaseModel):
    name: str
    description: str


class PersonaUpdate(BaseModel):
    description: str


class AdminPersonaUpdate(BaseModel):
    description: str


class AdminPersonaGroupUpdate(BaseModel):
    group_name: Optional[str] = None


ADMIN_OVERRIDE_MARKER = "\n\n--- 관리자 설정 덮어쓰기 ---\n"


def _with_admin_override(prompt, description):
    base = prompt.split(ADMIN_OVERRIDE_MARKER, 1)[0]
    return base + (ADMIN_OVERRIDE_MARKER + description if description else "")


def _persona_avatar_prompt(name, description):
    """사용자 설정만 끼워 넣는 결정론적 프로필 이미지 프롬프트."""
    clean = " ".join((description or "").split())[:USER_PERSONA_DESC_MAX_CHARS]
    return (
        "Create a square 1:1 premium editorial semi-realistic avatar portrait for a fictional persona. "
        f"Persona name: {name}. Personality and role: {clean}. "
        "Interpret the personality through expression, clothing, lighting, and a subtle abstract background. "
        "Centered close-up face and shoulders, distinctive silhouette, polished high detail, suitable for a chat profile. "
        "Do not imitate a real person's exact likeness. No text, no letters, no logos, no watermark."
    )


def _queue_persona_image(conn, name, description, requested_by, status, reason):
    conn.execute(
        """INSERT INTO persona_image_jobs
           (persona_name, prompt, requested_by, reason, status, created_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (name, _persona_avatar_prompt(name, description), requested_by, reason, status, _now()),
    )


@app.get("/api/admin/personas")
def admin_list_personas(request: Request):
    _require_owner(request)
    conn = get_conn()
    rows = conn.execute(
        """SELECT p.name, p.owner_username, p.description, p.profile_summary,
                  p.admin_description, p.avatar_url, p.group_name,
                  (SELECT j.status FROM persona_image_jobs j WHERE j.persona_name=p.name ORDER BY j.id DESC LIMIT 1) AS image_job_status,
                  (SELECT j.error FROM persona_image_jobs j WHERE j.persona_name=p.name ORDER BY j.id DESC LIMIT 1) AS image_job_error
             FROM personas p ORDER BY p.name"""
    ).fetchall()
    # ★ "페르소나 프로필 보기 권한" 요청(2026-08-28) — 관리 패널이 페르소나별로
    # 누가 프로필을 볼 수 있는지 렌더할 수 있게 같이 내려준다.
    grants_by_persona = {}
    for r in conn.execute("SELECT persona_name, username FROM persona_view_grants").fetchall():
        grants_by_persona.setdefault(r["persona_name"], []).append(r["username"])
    conn.close()
    result = [dict(r) for r in rows]
    for r in result:
        r["view_grants"] = grants_by_persona.get(r["name"], [])
    return result


@app.delete("/api/admin/personas/{name}")
def admin_delete_persona(name: str, request: Request):
    """"관리자가 툴파 삭제도 가능하게 해달라" 요청(2026-08-28). 사용자가
    직접 만든 페르소나는 이미 본인이 지울 수 있었지만(delete_my_persona),
    공용 Notion 페르소나를 포함해 아무 페르소나나 지우는 건 관리자만 할 수
    있다. delete_my_persona와 같은 cascade 목록에 persona_image_jobs만
    더한다(그쪽은 이미지 생성 이력이라 지금까진 안 지웠는데, 관리자
    삭제에서는 실수 요청도 아니므로 깔끔하게 정리한다)."""
    _require_owner(request)
    conn = get_conn()
    if not conn.execute("SELECT 1 FROM personas WHERE name = ?", (name,)).fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="존재하지 않는 페르소나입니다")
    conn.execute("DELETE FROM personas WHERE name = ?", (name,))
    conn.execute("DELETE FROM messages WHERE room_id = ?", (name,))
    conn.execute("DELETE FROM pending_turns WHERE room_id = ?", (name,))
    conn.execute("DELETE FROM room_invites WHERE persona_name = ?", (name,))
    conn.execute("DELETE FROM room_persona_exclusions WHERE persona_name = ?", (name,))
    conn.execute("DELETE FROM persona_image_jobs WHERE persona_name = ?", (name,))
    conn.execute("DELETE FROM persona_view_grants WHERE persona_name = ?", (name,))
    conn.commit()
    conn.close()
    return {"ok": True}


@app.post("/api/admin/personas/{name}/view_grants/{username}")
def admin_grant_persona_view(name: str, username: str, request: Request):
    """"권민석 프로필설정이 너무 적나라한데 일반 사용자도 다 보이는 거야"
    요청(2026-08-28) — 관리자가 특정 사용자에게 특정(관리자 소유) 페르소나
    프로필 열람을 예외적으로 허용한다(ui_dev_grants와 같은 패턴)."""
    _require_owner(request)
    conn = get_conn()
    if not conn.execute("SELECT 1 FROM personas WHERE name = ?", (name,)).fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="존재하지 않는 페르소나입니다")
    if not conn.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="존재하지 않는 계정입니다")
    conn.execute(
        "INSERT OR IGNORE INTO persona_view_grants (persona_name, username, granted_at) VALUES (?, ?, ?)",
        (name, username, _now()),
    )
    conn.commit()
    conn.close()
    return {"ok": True}


@app.delete("/api/admin/personas/{name}/view_grants/{username}")
def admin_revoke_persona_view(name: str, username: str, request: Request):
    _require_owner(request)
    conn = get_conn()
    conn.execute(
        "DELETE FROM persona_view_grants WHERE persona_name = ? AND username = ?", (name, username)
    )
    conn.commit()
    conn.close()
    return {"ok": True}


@app.put("/api/admin/personas/{name}")
def admin_update_persona(name: str, body: AdminPersonaUpdate, request: Request):
    _require_owner(request)
    description = body.description.strip()
    if not description or len(description) > USER_PERSONA_DESC_MAX_CHARS:
        raise HTTPException(status_code=400, detail=f"설정은 1~{USER_PERSONA_DESC_MAX_CHARS}자로 입력하세요")
    conn = get_conn()
    row = conn.execute(
        "SELECT system_prompt, group_name, owner_username FROM personas WHERE name = ?", (name,)
    ).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="존재하지 않는 페르소나입니다")
    conn.execute(
        "UPDATE personas SET admin_description = ?, profile_summary = ?, system_prompt = ?, synced_at = ? WHERE name = ?",
        (description, description, _with_admin_override(row["system_prompt"], description), _now(), name),
    )
    conn.commit()
    conn.close()
    return {"ok": True}


@app.put("/api/admin/personas/{name}/group")
def admin_update_persona_group(name: str, body: AdminPersonaGroupUpdate, request: Request):
    _require_owner(request)
    raw_group_name = (body.group_name or "").strip()
    group_name = raw_group_name or None
    if group_name and len(group_name) > 40:
        raise HTTPException(status_code=400, detail="그룹 이름은 40자 이내로 입력하세요")
    conn = get_conn()
    if not conn.execute("SELECT 1 FROM personas WHERE name = ?", (name,)).fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="존재하지 않는 페르소나입니다")
    conn.execute("UPDATE personas SET admin_group_name = ?, group_name = ? WHERE name = ?", (raw_group_name, group_name, name))
    conn.commit()
    conn.close()
    return {"ok": True, "group_name": group_name}


@app.post("/api/admin/personas/{name}/avatar")
async def admin_upload_persona_avatar(name: str, request: Request, file: UploadFile = File(...)):
    _require_owner(request)
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_UPLOAD_EXTENSIONS:
        raise HTTPException(status_code=400, detail="지원하지 않는 이미지 형식입니다")
    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="이미지가 너무 큽니다(10MB 제한)")
    conn = get_conn()
    if not conn.execute("SELECT 1 FROM personas WHERE name = ?", (name,)).fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="존재하지 않는 페르소나입니다")
    filename = f"persona_{uuid.uuid4().hex}{ext}"
    (UPLOADS_DIR / filename).write_bytes(data)
    url = f"/uploads/{filename}"
    conn.execute("UPDATE personas SET avatar_url = ? WHERE name = ?", (url, name))
    conn.commit()
    conn.close()
    return {"ok": True, "avatar_url": url}


@app.delete("/api/admin/personas/{name}/avatar")
def admin_delete_persona_avatar(name: str, request: Request):
    _require_owner(request)
    conn = get_conn()
    conn.execute("UPDATE personas SET avatar_url = NULL WHERE name = ?", (name,))
    conn.commit()
    conn.close()
    return {"ok": True}


class PersonaImageGenerateRequest(BaseModel):
    description: Optional[str] = None


@app.post("/api/admin/personas/{name}/avatar/generate")
def admin_generate_persona_avatar(name: str, body: PersonaImageGenerateRequest, request: Request):
    """관리자 버튼 클릭을 명시 승인으로 삼아 유료 Images API 작업을 큐에 넣는다."""
    _require_owner(request)
    conn = get_conn()
    row = conn.execute(
        "SELECT description, profile_summary, admin_description FROM personas WHERE name = ?", (name,)
    ).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="존재하지 않는 페르소나입니다")
    description = (body.description or row["admin_description"] or row["description"] or row["profile_summary"] or "").strip()
    if not description or len(description) > USER_PERSONA_DESC_MAX_CHARS:
        conn.close()
        raise HTTPException(status_code=400, detail="이미지 생성을 위한 프로필 설정이 필요합니다")
    active = conn.execute(
        "SELECT 1 FROM persona_image_jobs WHERE persona_name = ? AND status IN ('pending','processing')",
        (name,),
    ).fetchone()
    if active:
        conn.close()
        raise HTTPException(status_code=409, detail="이미 생성 중인 작업이 있습니다")
    user = request.state.user
    _queue_persona_image(conn, name, description, user["username"], "pending", "admin_regenerate")
    job_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.commit()
    conn.close()
    return {"ok": True, "job_id": job_id, "status": "pending"}


@app.get("/api/my_personas")
def list_my_personas(request: Request):
    """내가 만든 페르소나 목록 — 방 목록이 아니라 "관리" 화면(생성·수정·삭제)에서
    쓴다. description을 그대로 돌려줘서 수정 폼에 원문을 채워 넣을 수 있게 한다."""
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다")
    conn = get_conn()
    rows = conn.execute(
        "SELECT name, description, synced_at FROM personas WHERE owner_username = ? ORDER BY name",
        (user["username"],),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.post("/api/my_personas")
def create_my_persona(body: PersonaCreate, request: Request):
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다")
    name = body.name.strip()
    if not PERSONA_NAME_RE.match(name):
        raise HTTPException(status_code=400, detail="이름은 한글/영문/숫자/공백/밑줄 1~20자로 입력하세요")
    description = body.description.strip()
    if not description:
        raise HTTPException(status_code=400, detail="캐릭터 설정을 입력하세요")
    if len(description) > USER_PERSONA_DESC_MAX_CHARS:
        raise HTTPException(status_code=400, detail=f"설정은 {USER_PERSONA_DESC_MAX_CHARS}자 이내로 입력하세요")
    conn = get_conn()
    try:
        if conn.execute("SELECT 1 FROM personas WHERE name = ?", (name,)).fetchone():
            raise HTTPException(status_code=409, detail="이미 사용 중인 이름입니다")
        prompt = _build_user_persona_prompt(name, user["username"], description)
        conn.execute(
            "INSERT INTO personas (name, notion_page_id, system_prompt, group_name, owner_username, description, synced_at) "
            "VALUES (?, '', ?, NULL, ?, ?, ?)",
            (name, prompt, user["username"], description, _now()),
        )
        # 소유자의 생성 클릭은 곧 유료 생성 승인이다. 일반 계정은 비용·시스템
        # 영향을 직접 일으키지 못하고 관리자가 재생성 버튼을 눌러야 진행된다.
        image_status = "pending" if user["is_owner"] else "awaiting_approval"
        _queue_persona_image(conn, name, description, user["username"], image_status, "persona_created")
        conn.commit()
    finally:
        conn.close()
    return {"ok": True, "name": name, "image_status": image_status}


@app.put("/api/my_personas/{name}")
def update_my_persona(name: str, body: PersonaUpdate, request: Request):
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다")
    description = body.description.strip()
    if not description:
        raise HTTPException(status_code=400, detail="캐릭터 설정을 입력하세요")
    if len(description) > USER_PERSONA_DESC_MAX_CHARS:
        raise HTTPException(status_code=400, detail=f"설정은 {USER_PERSONA_DESC_MAX_CHARS}자 이내로 입력하세요")
    conn = get_conn()
    try:
        row = conn.execute("SELECT owner_username FROM personas WHERE name = ?", (name,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="존재하지 않는 페르소나입니다")
        if row["owner_username"] != user["username"]:
            raise HTTPException(status_code=403, detail="본인이 만든 페르소나만 수정할 수 있습니다")
        prompt = _build_user_persona_prompt(name, user["username"], description)
        conn.execute(
            "UPDATE personas SET system_prompt = ?, description = ?, synced_at = ? WHERE name = ?",
            (prompt, description, _now(), name),
        )
        conn.commit()
    finally:
        conn.close()
    return {"ok": True}


@app.delete("/api/my_personas/{name}")
def delete_my_persona(name: str, request: Request):
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다")
    conn = get_conn()
    try:
        row = conn.execute("SELECT owner_username FROM personas WHERE name = ?", (name,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="존재하지 않는 페르소나입니다")
        if row["owner_username"] != user["username"]:
            raise HTTPException(status_code=403, detail="본인이 만든 페르소나만 삭제할 수 있습니다")
        conn.execute("DELETE FROM personas WHERE name = ?", (name,))
        conn.execute("DELETE FROM messages WHERE room_id = ?", (name,))
        conn.execute("DELETE FROM pending_turns WHERE room_id = ?", (name,))
        conn.execute("DELETE FROM room_invites WHERE persona_name = ?", (name,))
        conn.execute("DELETE FROM room_persona_exclusions WHERE persona_name = ?", (name,))
        conn.commit()
    finally:
        conn.close()
    return {"ok": True}


# ★ 2026-08-26: "사용자가 단체톡방 만들기가 가능하게 해달라"는 요청 — Notion
# "그룹" 필드에서 자동으로 생기는 그룹 회의방과 달리, 계정이 직접 임의의
# 이름으로 만드는 방이다. 멤버 관리는 기존 room_invites 테이블/엔드포인트를
# 그대로 재사용한다(_group_members가 room_id로만 조회하므로 출처를 안 가림).
CUSTOM_ROOM_ID_PREFIX = "custom_"


class CustomRoomCreate(BaseModel):
    label: str


class DirectRoomCreate(BaseModel):
    target_type: str
    target_id: str


@app.post("/api/rooms")
def create_custom_room(body: CustomRoomCreate, request: Request):
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다")
    label = body.label.strip()
    if not label or len(label) > 30:
        raise HTTPException(status_code=400, detail="방 이름은 1~30자로 입력하세요")
    room_id = f"{CUSTOM_ROOM_ID_PREFIX}{uuid.uuid4().hex[:10]}"
    conn = get_conn()
    conn.execute(
        "INSERT INTO custom_rooms (room_id, label, owner_username, created_at) VALUES (?, ?, ?, ?)",
        (room_id, label, user["username"], _now()),
    )
    conn.commit()
    conn.close()
    return {"ok": True, "room_id": room_id, "label": label}


@app.post("/api/direct-rooms")
def create_or_get_direct_room(body: DirectRoomCreate, request: Request):
    """친구 목록에서 사람 또는 페르소나와 시작하는 확장 가능한 1:1 방.
    처음에는 둘만 참여하지만 custom_rooms를 사용하므로 방 주인이 다른 사람이나
    페르소나를 초대하면 같은 대화 기록을 유지한 채 그룹방으로 발전한다."""
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다")
    requester = user["username"]
    target_type = body.target_type.strip().lower()
    target_id = body.target_id.strip()
    if target_type not in {"user", "persona"} or not target_id:
        raise HTTPException(status_code=400, detail="대화 상대가 올바르지 않습니다")
    conn = get_conn()
    if target_type == "user":
        if target_id == requester:
            conn.close()
            raise HTTPException(status_code=400, detail="자기 자신과는 1:1 방을 만들 수 없습니다")
        target = conn.execute(
            "SELECT username, display_name FROM users WHERE username=?", (target_id,)
        ).fetchone()
        if not target:
            conn.close()
            raise HTTPException(status_code=404, detail="존재하지 않는 사용자입니다")
        pair = sorted((requester, target_id))
        direct_key = f"user:{pair[0]}:{pair[1]}"
        label = target["display_name"] or target_id
    else:
        target = conn.execute(
            "SELECT name, owner_username FROM personas WHERE name=?", (target_id,)
        ).fetchone()
        if not target:
            conn.close()
            raise HTTPException(status_code=404, detail="존재하지 않는 페르소나입니다")
        if target["owner_username"] not in (None, requester) and not user["is_owner"]:
            conn.close()
            raise HTTPException(status_code=403, detail="이 페르소나와 대화할 수 없습니다")
        direct_key = f"persona:{requester}:{target_id}"
        label = target_id
    existing = conn.execute(
        "SELECT room_id, label FROM custom_rooms WHERE direct_key=?", (direct_key,)
    ).fetchone()
    if existing:
        conn.close()
        return {"ok": True, "room_id": existing["room_id"], "label": existing["label"], "created": False}
    room_id = f"{CUSTOM_ROOM_ID_PREFIX}{uuid.uuid4().hex[:10]}"
    try:
        conn.execute(
            "INSERT INTO custom_rooms(room_id,label,owner_username,created_at,direct_key) VALUES (?,?,?,?,?)",
            (room_id, label, requester, _now(), direct_key),
        )
        if target_type == "user":
            conn.execute(
                "INSERT INTO room_user_invites(room_id,username,invited_at) VALUES (?,?,?)",
                (room_id, target_id, _now()),
            )
        else:
            conn.execute(
                "INSERT INTO room_invites(room_id,persona_name,invited_at) VALUES (?,?,?)",
                (room_id, target_id, _now()),
            )
        conn.commit()
    except sqlite3.IntegrityError:
        conn.rollback()
        existing = conn.execute(
            "SELECT room_id, label FROM custom_rooms WHERE direct_key=?", (direct_key,)
        ).fetchone()
        conn.close()
        if existing:
            return {"ok": True, "room_id": existing["room_id"], "label": existing["label"], "created": False}
        raise
    conn.close()
    return {"ok": True, "room_id": room_id, "label": label, "created": True}


@app.post("/api/rooms/{room_id}/thumbnail")
async def upload_room_thumbnail(room_id: str, request: Request, file: UploadFile = File(...)):
    """토론방 대표사진(2026-08-26 요청) — 커스텀 방 주인 또는 소유자만 바꿀 수
    있다. 저장·검증 로직은 /api/upload와 동일(같은 UPLOADS_DIR·확장자·용량
    제한 재사용)."""
    if not getattr(request.state, "can_write", True):
        raise HTTPException(status_code=403, detail="읽기 전용 계정입니다")
    user = getattr(request.state, "user", None)
    username = user["username"] if user else None
    is_owner_request = user["is_owner"] if user else True
    conn = get_conn()
    row = conn.execute("SELECT owner_username FROM custom_rooms WHERE room_id = ?", (room_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="내가 만든 채팅방이 아닙니다")
    if not (is_owner_request or row["owner_username"] == username):
        conn.close()
        raise HTTPException(status_code=403, detail="이 채팅방의 대표사진은 방 주인만 바꿀 수 있습니다")
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_UPLOAD_EXTENSIONS:
        conn.close()
        raise HTTPException(status_code=400, detail=f"지원하지 않는 이미지 형식입니다: {ext or '(확장자 없음)'}")
    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        conn.close()
        raise HTTPException(status_code=413, detail="이미지가 너무 큽니다(10MB 제한)")
    filename = f"{uuid.uuid4().hex}{ext}"
    (UPLOADS_DIR / filename).write_bytes(data)
    url = f"/uploads/{filename}"
    conn.execute("UPDATE custom_rooms SET thumbnail_url = ? WHERE room_id = ?", (url, room_id))
    conn.commit()
    conn.close()
    return {"ok": True, "thumbnail_url": url}


def _require_personal_background_room_access(conn, room_id, username, is_owner_request):
    """개인 배경을 설정하려는 방이 실제로 이 계정에 보이는 방인지 확인한다.
    메시지 조회와 같은 접근 규칙을 적용해 임의 room_id에 파일 설정을 쌓거나
    초대받지 않은 방의 존재를 확인하지 못하게 한다."""
    if room_id == GROUP_ROOM_ID:
        return
    persona = conn.execute(
        "SELECT owner_username FROM personas WHERE name=?", (room_id,)
    ).fetchone()
    if persona:
        if not _can_access_persona_room(persona["owner_username"], username, is_owner_request):
            raise HTTPException(status_code=403, detail="이 채팅방을 볼 수 없습니다")
        return
    is_custom, allowed, _room_owner = _custom_room_access(conn, room_id, username, is_owner_request)
    if is_custom:
        if not allowed:
            raise HTTPException(status_code=403, detail="이 채팅방을 볼 수 없습니다")
        return
    if _is_notion_group_room(conn, room_id):
        if not _group_room_allowed(conn, room_id, username, is_owner_request):
            raise HTTPException(status_code=403, detail="이 채팅방을 볼 수 없습니다")
        return
    raise HTTPException(status_code=404, detail="채팅방을 찾을 수 없습니다")


@app.get("/api/rooms/{room_id}/my-background")
def get_my_room_background(room_id: str, request: Request):
    """현재 로그인 계정의 이 방 배경만 반환한다. 방 공용 정보에는 섞지 않는다."""
    user = getattr(request.state, "user", None)
    if not user:
        return {"image_url": None}
    conn = get_conn()
    _require_personal_background_room_access(conn, room_id, user["username"], user["is_owner"])
    row = conn.execute(
        "SELECT image_url FROM user_room_backgrounds WHERE username=? AND room_id=?",
        (user["username"], room_id),
    ).fetchone()
    conn.close()
    return {"image_url": row["image_url"] if row else None}


@app.post("/api/rooms/{room_id}/my-background")
async def upload_my_room_background(room_id: str, request: Request, file: UploadFile = File(...)):
    if not getattr(request.state, "can_write", True):
        raise HTTPException(status_code=403, detail="읽기 전용 계정입니다")
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다")
    conn = get_conn()
    _require_personal_background_room_access(conn, room_id, user["username"], user["is_owner"])
    ext = Path(file.filename or "").suffix.lower()
    if ext not in BACKGROUND_UPLOAD_EXTENSIONS:
        conn.close()
        raise HTTPException(status_code=400, detail="배경은 JPG, PNG, GIF, WebP만 지원합니다")
    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        conn.close()
        raise HTTPException(status_code=413, detail="이미지가 너무 큽니다(10MB 제한)")
    filename = f"room-bg-{uuid.uuid4().hex}{ext}"
    (UPLOADS_DIR / filename).write_bytes(data)
    url = f"/uploads/{filename}"
    conn.execute(
        """INSERT INTO user_room_backgrounds(username,room_id,image_url,updated_at)
           VALUES(?,?,?,?)
           ON CONFLICT(username,room_id) DO UPDATE SET
             image_url=excluded.image_url, updated_at=excluded.updated_at""",
        (user["username"], room_id, url, _now()),
    )
    conn.commit()
    conn.close()
    return {"ok": True, "image_url": url}


@app.delete("/api/rooms/{room_id}/my-background")
def reset_my_room_background(room_id: str, request: Request):
    if not getattr(request.state, "can_write", True):
        raise HTTPException(status_code=403, detail="읽기 전용 계정입니다")
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다")
    conn = get_conn()
    _require_personal_background_room_access(conn, room_id, user["username"], user["is_owner"])
    conn.execute(
        "DELETE FROM user_room_backgrounds WHERE username=? AND room_id=?",
        (user["username"], room_id),
    )
    conn.commit()
    conn.close()
    return {"ok": True, "image_url": None}


GROUP_ROOM_ID = "group"
# ★ 2026-08-24: 그룹방은 아무도 안 부르면 페르소나 전원이 매번 동시에 반응하는
# 구조라 거의 똑같은 답이 몇 개씩 쏟아지고, 서로 일면식 없어야 할 인물들이
# Notion에 없는 친분·약속을 지어내는 문제가 실사용 중 확인됐다("이 채팅방은
# 당분간 폐쇄한다"는 요청). 코드/데이터는 그대로 두고 노출만 끈다 — "당분간"
# 이라 나중에 그룹 대화 로직을 고친 뒤 다시 켤 수 있게. GROUP_ROOM_ENABLED
# 환경변수로 제어.
GROUP_ROOM_ENABLED = os.environ.get("GROUP_ROOM_ENABLED", "true").lower() == "true"

# ★ 2026-08-26: "손동주는 내 말에만 응답하게 해달라" 요청 — 1:1 방은 이미
# 소유자만 쓸 수 있게 막았으니(위 post_message) 이 목록은 단체 채팅방/그룹
# 회의방에서 다른 계정이 손동주를 부르거나 @멘션해도 응답 대기열에 아예
# 안 들어가게 거르는 용도다. worker/persona_worker.py의
# FILE_ORGANIZER_PERSONA_NAME과 같은 이름을 가리켜야 한다(두 파일은 서로
# import하지 않는 독립 프로세스라 값을 맞춰서 손으로 동기화해야 함).
OWNER_ONLY_PERSONAS = {"손동주"}

# ★ 2026-08-26: "모든 사람한테 유이(UI 개발자 페르소나) 꾸밀 권한을 주지는
# 말고, 내 허락하에 그 사람에게만 권한을 줄 수 있게 해달라" 요청 — 손동주처럼
# 아예 소유자 전용으로 막는 게 아니라, 소유자가 ui_dev_grants 테이블에 특정
# 계정을 등록해두면 그 계정만 "유이"에게 말을 걸어 응답을 받을 수 있다(그 외
# 비소유자는 OWNER_ONLY_PERSONAS와 동일하게 취급 — 응답 대기열에 안 들어감).
# worker/persona_worker.py의 UI_DEV_PERSONA_NAME과 이름이 같아야 한다.
UI_DEV_PERSONAS = {"유이"}

# 소유자가 채팅에서 이 문구를 직접 보낸 경우에만 기존 손자병법 자동 해석
# 파이프라인을 시작한다. 일반 사용자의 같은 문장은 평범한 대화로만 취급하고
# 실제 작업 큐를 만들지 않는다. 실행 자체는 로컬 워커의 고정 스크립트가 맡고,
# AI가 채팅 내용으로 임의 명령이나 경로를 구성하지 않는다.
SUNZI_PIPELINE_PERSONA_NAME = "손무"
SUNZI_PIPELINE_COMMAND_RE = re.compile(
    r"손자병법.{0,20}다음\s*구절.{0,20}(?:해석|분석|최신화)(?:해|해줘|해주세요|하라|진행)?"
)
SUNZI_BACKFILL_COMMAND_RE = re.compile(
    r"손자병법\s*구지편\s*(\d{1,2})구절.{0,800}?(?:4번\s*)?역사적\s*실증\s*사례.{0,120}?(?:추가|보강)",
    re.DOTALL,
)


def _is_sunzi_pipeline_command(content: str) -> bool:
    normalized = content.replace("_", " ")
    return bool(SUNZI_PIPELINE_COMMAND_RE.search(normalized) or SUNZI_BACKFILL_COMMAND_RE.search(normalized))

# ★ 2026-08-26: "다른 사람들의 요구·요청사항·개선사항을 모아서 나한테
# 보고하는 에이전틱 툴파" 요청 — worker/persona_worker.py의 ADMIN_PERSONA_NAME과
# 이름이 같아야 한다. 아직은 "수집·보고"만 하고 실제 코드 수정 권한은 없다
# (유이처럼 파일 수정 권한을 줄지는 소유자와 상의 후 결정 예정).
ADMIN_PERSONA_NAME = "툴파관리자"
QA_PERSONA_NAME = "QA요정"
QA_REPORTER_USERNAME = "qqq"

# ★ "독서방뿐만아니라 다른 방에서도 범용적으로 활용하고싶은데...
# 적극적으로 이런거 페르소나로생성해볼까요? 하고 물어봐주면 좋겠어"
# 요청(2026-09-02) — worker/persona_worker.py의 PERSONA_MANAGER_PERSONA_NAME과
# 이름이 같아야 한다. 이 페르소나가 초대된 방에서는 멘션·직전 발화자 여부와
# 무관하게 사람이 메시지를 보낼 때마다 매번 턴을 받아야 "적극적으로" 먼저
# 나설 수 있다 — 그래서 아래 post_message()에서 targets 계산 뒤 별도로
# 추가한다(다른 멤버들과 같은 _default_targets 규칙을 적용하면 대부분
# "직전 발화자 1인에게만 이어짐"에 걸려 거의 턴을 못 받는다). 할 말 없는
# 턴이 대부분일 텐데, 그건 워커 쪽에서 "NONE" 신호로 조용히 넘어가게
# 처리한다(persona_worker.py의 PERSONA_MANAGER_ADDENDUM 참고) — 여기서는
# 그냥 타겟에 추가만 하면 된다.
PERSONA_MANAGER_PERSONA_NAME = "페르소나 관리자"


def _is_owner_request(request) -> bool:
    user = getattr(request.state, "user", None)
    if user:
        return bool(user["is_owner"])
    # 로컬 개발(무인증, can_write=True)은 기존 관례대로 소유자로 간주한다.
    return bool(getattr(request.state, "can_write", False)) and not getattr(request.state, "share_guest", False)


def _require_owner(request):
    if not _is_owner_request(request):
        raise HTTPException(status_code=403, detail="소유자만 할 수 있습니다")


def _require_signed_in_user(request):
    """툴파챗 로그인 계정 또는 로컬 소유자만 읽기형 하위 앱을 사용한다."""
    if getattr(request.state, "user", None):
        return
    if _is_owner_request(request):
        return
    raise HTTPException(status_code=401, detail="로그인이 필요합니다")


def _request_username(request):
    user = getattr(request.state, "user", None)
    return str(user["username"] if user else APP_USERNAME or "local-owner")


class FitnessDayPayload(BaseModel):
    day: str
    steps: int
    distance_m: float = 0
    active_energy_kcal: float = 0


class FitnessSyncPayload(BaseModel):
    days: list[FitnessDayPayload]


class FitnessShortcutPayload(BaseModel):
    steps: int
    distance_m: float = 0
    active_energy_kcal: float = 0
    day: Optional[str] = None


class FitnessGoalPayload(BaseModel):
    daily_step_goal: int


class StockHoldingPayload(BaseModel):
    name: str
    symbol: str = ""
    market: str = "US"
    currency: str = "USD"
    total_cost_krw: float
    shares: float


class StockAnalysisResultPayload(BaseModel):
    job_id: int
    report: Optional[dict[str, Any]] = None
    engine: Optional[str] = None
    error: Optional[str] = None


def _stock_portfolio_data(request: Request):
    _require_signed_in_user(request)
    username = _request_username(request)
    with get_conn() as conn:
        stock_portfolio.seed(conn, username)
        settings = conn.execute("SELECT * FROM stock_portfolio_settings WHERE username=?", (username,)).fetchone()
        usd_krw = float(settings["usd_krw"] if settings else 1340.88)
        rows = conn.execute("SELECT * FROM stock_portfolio_holdings WHERE username=? ORDER BY total_cost_krw DESC", (username,)).fetchall()
    holdings = [stock_portfolio.public_holding(row, usd_krw) for row in rows]
    total_cost = sum(float(item["total_cost_krw"]) for item in holdings)
    priced = [item for item in holdings if item["value_krw"] is not None]
    total_value = sum(item["value_krw"] for item in priced)
    semiconductors = {"NVDA", "SOXL", "AMD", "SMH", "TSM", "AVGO"}
    directional = {"SOXL", "AAPD", "TSLL"}
    losses = sorted((item for item in priced if item["pnl_krw"] < 0), key=lambda item: item["pnl_krw"])
    return {
        "as_of": settings["last_refresh_at"] if settings else None,
        "usd_krw": usd_krw,
        "holdings": holdings,
        "summary": {
            "holding_count": len(holdings), "priced_count": len(priced),
            "total_cost_krw": round(total_cost), "priced_value_krw": round(total_value),
            "priced_cost_krw": round(sum(float(item["total_cost_krw"]) for item in priced)),
            "loss_total_krw": round(sum(item["pnl_krw"] for item in losses)),
            "semiconductor_cost_pct": round(sum(float(item["total_cost_krw"]) for item in holdings if item["symbol"] in semiconductors) / total_cost * 100, 1) if total_cost else 0,
            "directional_cost_pct": round(sum(float(item["total_cost_krw"]) for item in holdings if item["symbol"] in directional) / total_cost * 100, 1) if total_cost else 0,
        },
        "losses": losses[:8],
        "questions": [
            "지금 현금을 새로 받았다면 현재 가격에서도 이 종목을 같은 금액만큼 다시 살 것인가?",
            "내 투자 논리를 무효로 만드는 실적·가격·기간 조건은 무엇인가?",
            "이 종목이 이미 가진 기술주·반도체·달러 위험을 얼마나 더 키우는가?",
        ],
    }


@app.get("/api/stock-portfolio/summary")
def stock_portfolio_summary(request: Request):
    return _stock_portfolio_data(request)


@app.post("/api/stock-portfolio/holdings")
def stock_portfolio_add(payload: StockHoldingPayload, request: Request):
    _require_signed_in_user(request)
    if not payload.name.strip() or payload.total_cost_krw <= 0 or payload.shares <= 0:
        raise HTTPException(status_code=400, detail="종목명·구매금액·수량을 확인하세요")
    now = stock_portfolio.utc_now()
    with get_conn() as conn:
        conn.execute("""INSERT INTO stock_portfolio_holdings
            (username,name,symbol,market,currency,total_cost_krw,shares,created_at,updated_at)
            VALUES(?,?,?,?,?,?,?,?,?)""", (_request_username(request), payload.name.strip(), payload.symbol.strip().upper(), payload.market.upper(), payload.currency.upper(), payload.total_cost_krw, payload.shares, now, now))
        conn.commit()
    return {"ok": True}


@app.put("/api/stock-portfolio/holdings/{holding_id}")
def stock_portfolio_update(holding_id: int, payload: StockHoldingPayload, request: Request):
    _require_signed_in_user(request)
    if not payload.name.strip() or payload.total_cost_krw <= 0 or payload.shares <= 0:
        raise HTTPException(status_code=400, detail="종목명·구매금액·수량을 확인하세요")
    with get_conn() as conn:
        result = conn.execute("""UPDATE stock_portfolio_holdings SET name=?,symbol=?,market=?,currency=?,total_cost_krw=?,shares=?,updated_at=?
            WHERE id=? AND username=?""", (payload.name.strip(), payload.symbol.strip().upper(), payload.market.upper(), payload.currency.upper(), payload.total_cost_krw, payload.shares, stock_portfolio.utc_now(), holding_id, _request_username(request)))
        conn.commit()
    if not result.rowcount:
        raise HTTPException(status_code=404, detail="종목을 찾을 수 없습니다")
    return {"ok": True}


@app.delete("/api/stock-portfolio/holdings/{holding_id}")
def stock_portfolio_delete(holding_id: int, request: Request):
    _require_signed_in_user(request)
    with get_conn() as conn:
        result = conn.execute("DELETE FROM stock_portfolio_holdings WHERE id=? AND username=?", (holding_id, _request_username(request)))
        conn.commit()
    if not result.rowcount:
        raise HTTPException(status_code=404, detail="종목을 찾을 수 없습니다")
    return {"ok": True}


def _public_stock_analysis(conn, username: str, holding_id: int):
    job = conn.execute(
        "SELECT * FROM stock_analysis_jobs WHERE username=? AND holding_id=? ORDER BY id DESC LIMIT 1",
        (username, holding_id),
    ).fetchone()
    report = conn.execute(
        "SELECT * FROM stock_analysis_reports WHERE username=? AND holding_id=? ORDER BY id DESC LIMIT 1",
        (username, holding_id),
    ).fetchone()
    parsed = None
    if report:
        try:
            parsed = json.loads(report["report_json"])
        except json.JSONDecodeError:
            parsed = None
    return {
        "job": dict(job) if job else None,
        "report": {**dict(report), "content": parsed} if report and parsed else None,
    }


@app.get("/api/stock-portfolio/holdings/{holding_id}/analysis")
def stock_analysis_get(holding_id: int, request: Request):
    _require_signed_in_user(request)
    username = _request_username(request)
    with get_conn() as conn:
        holding = conn.execute(
            "SELECT * FROM stock_portfolio_holdings WHERE id=? AND username=?", (holding_id, username)
        ).fetchone()
        if not holding:
            raise HTTPException(status_code=404, detail="종목을 찾을 수 없습니다")
        settings = conn.execute("SELECT usd_krw FROM stock_portfolio_settings WHERE username=?", (username,)).fetchone()
        result = _public_stock_analysis(conn, username, holding_id)
    return {"holding": stock_portfolio.public_holding(holding, float(settings["usd_krw"] if settings else 1340.88)), **result}


@app.post("/api/stock-portfolio/holdings/{holding_id}/analysis")
def stock_analysis_create(holding_id: int, request: Request):
    _require_signed_in_user(request)
    username = _request_username(request)
    now = stock_portfolio.utc_now()
    with get_conn() as conn:
        holding = conn.execute(
            "SELECT id FROM stock_portfolio_holdings WHERE id=? AND username=?", (holding_id, username)
        ).fetchone()
        if not holding:
            raise HTTPException(status_code=404, detail="종목을 찾을 수 없습니다")
        running = conn.execute(
            "SELECT id FROM stock_analysis_jobs WHERE username=? AND holding_id=? AND status IN ('pending','processing')",
            (username, holding_id),
        ).fetchone()
        if running:
            return {"ok": True, "job_id": running["id"], "already_running": True}
        cursor = conn.execute(
            "INSERT INTO stock_analysis_jobs(username,holding_id,status,progress_label,created_at) VALUES(?,?,'pending','최신 자료 조사 대기 중',?)",
            (username, holding_id, now),
        )
        conn.commit()
    return JSONResponse({"ok": True, "job_id": cursor.lastrowid}, status_code=202)


@app.post("/api/stock-portfolio/refresh")
def stock_portfolio_refresh(request: Request):
    _require_signed_in_user(request)
    username = _request_username(request)
    with get_conn() as conn:
        stock_portfolio.seed(conn, username)
        rows = conn.execute("SELECT id,symbol FROM stock_portfolio_holdings WHERE username=? AND symbol<>''", (username,)).fetchall()
    symbols = {row["symbol"] for row in rows}
    results, errors = {}, {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(stock_portfolio.quote, symbol): symbol for symbol in symbols | {"KRW=X"}}
        for future in concurrent.futures.as_completed(futures):
            symbol = futures[future]
            try:
                results[symbol] = future.result()
            except Exception as exc:
                errors[symbol] = str(exc)[:120]
    now = stock_portfolio.utc_now()
    usd_krw = results.get("KRW=X", (1340.88, 0))[0]
    with get_conn() as conn:
        for row in rows:
            if row["symbol"] in results:
                price, stamp = results[row["symbol"]]
                at = datetime.datetime.fromtimestamp(stamp, datetime.timezone.utc).isoformat(timespec="seconds") if stamp else now
                conn.execute("UPDATE stock_portfolio_holdings SET last_price=?,last_price_at=?,updated_at=? WHERE id=? AND username=?", (price, at, now, row["id"], username))
        conn.execute("""INSERT INTO stock_portfolio_settings(username,usd_krw,last_refresh_at,updated_at) VALUES(?,?,?,?)
            ON CONFLICT(username) DO UPDATE SET usd_krw=excluded.usd_krw,last_refresh_at=excluded.last_refresh_at,updated_at=excluded.updated_at""", (username, usd_krw, now, now))
        conn.commit()
    return {"ok": True, "updated": len(results) - (1 if "KRW=X" in results else 0), "failed": errors, "data": _stock_portfolio_data(request)}


@app.get("/api/worker/stock_analysis/pending")
def worker_pending_stock_analysis(authorization: Optional[str] = Header(None)):
    _check_worker_auth(authorization)
    stale_before = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=25)).isoformat(timespec="seconds")
    with get_conn() as conn:
        conn.execute(
            "UPDATE stock_analysis_jobs SET status='pending',progress_label='중단된 조사 다시 대기 중',started_at=NULL WHERE status='processing' AND started_at<?",
            (stale_before,),
        )
        row = conn.execute(
            """SELECT j.id AS job_id,j.username,j.holding_id,h.name,h.symbol,h.market,h.currency,
                      h.total_cost_krw,h.shares,h.last_price,h.last_price_at
                 FROM stock_analysis_jobs j JOIN stock_portfolio_holdings h ON h.id=j.holding_id
                WHERE j.status='pending' ORDER BY j.id LIMIT 1"""
        ).fetchone()
        if not row:
            conn.commit()
            return None
        changed = conn.execute(
            "UPDATE stock_analysis_jobs SET status='processing',progress_label='웹 자료 조사·보고서 작성 중',started_at=? WHERE id=? AND status='pending'",
            (stock_portfolio.utc_now(), row["job_id"]),
        ).rowcount
        conn.commit()
        return dict(row) if changed else None


@app.post("/api/worker/stock_analysis/complete")
def worker_complete_stock_analysis(body: StockAnalysisResultPayload, authorization: Optional[str] = Header(None)):
    _check_worker_auth(authorization)
    now = stock_portfolio.utc_now()
    with get_conn() as conn:
        job = conn.execute(
            """SELECT j.*,h.symbol,h.last_price FROM stock_analysis_jobs j
                 JOIN stock_portfolio_holdings h ON h.id=j.holding_id WHERE j.id=?""", (body.job_id,)
        ).fetchone()
        if not job or job["status"] != "processing":
            raise HTTPException(status_code=404, detail="처리 중인 종목 분석 작업이 아닙니다")
        if body.error or not body.report:
            conn.execute(
                "UPDATE stock_analysis_jobs SET status='failed',progress_label='분석 실패',error=?,engine=?,completed_at=? WHERE id=?",
                ((body.error or "빈 분석 결과")[:1000], (body.engine or "")[:40], now, body.job_id),
            )
        else:
            required = {"title", "as_of", "executive_summary", "rise_reasons", "decline_reasons", "fundamentals", "outlook", "checkpoints", "self_questions", "sources"}
            if not required.issubset(body.report) or not isinstance(body.report.get("sources"), list):
                raise HTTPException(status_code=422, detail="분석 보고서 필수 항목이 없습니다")
            conn.execute(
                """INSERT INTO stock_analysis_reports(username,holding_id,job_id,symbol,price_at_analysis,report_json,created_at)
                   VALUES(?,?,?,?,?,?,?)""",
                (job["username"], job["holding_id"], body.job_id, job["symbol"], job["last_price"], json.dumps(body.report, ensure_ascii=False), now),
            )
            conn.execute(
                "UPDATE stock_analysis_jobs SET status='done',progress_label='분석 완료',error=NULL,engine=?,completed_at=? WHERE id=?",
                ((body.engine or "")[:40], now, body.job_id),
            )
        conn.commit()
    return {"ok": True}


class TerrainSurveyCreate(BaseModel):
    title: str
    location_name: str = ""
    hypotheses: list[str] = []
    conditions: dict[str, Any] = {}


class TerrainTrackPoint(BaseModel):
    latitude: float
    longitude: float
    altitude: Optional[float] = None
    accuracy: Optional[float] = None
    recorded_at: Optional[str] = None


class TerrainTrackBatch(BaseModel):
    points: list[TerrainTrackPoint]


class TerrainObservationCreate(TerrainTrackPoint):
    category: str
    note: str = ""
    metadata: dict[str, Any] = {}


class TerrainCompletePayload(BaseModel):
    reflection: str = ""
    differences: list[str] = []


def _fitness_day(value: str) -> str:
    try:
        return datetime.date.fromisoformat(value).isoformat()
    except ValueError:
        raise HTTPException(status_code=400, detail="날짜는 YYYY-MM-DD 형식이어야 합니다")


def _fitness_token_owner(authorization: Optional[str], conn) -> str:
    if not authorization or not authorization.startswith("Bearer nhk_"):
        raise HTTPException(status_code=401, detail="건강 동기화 토큰이 필요합니다")
    digest = hashlib.sha256(authorization[7:].encode()).hexdigest()
    rows = conn.execute("SELECT username,token_hash FROM health_sync_tokens").fetchall()
    owner = next((item["username"] for item in rows if secrets.compare_digest(item["token_hash"], digest)), None)
    if not owner:
        raise HTTPException(status_code=401, detail="건강 동기화 토큰이 올바르지 않습니다")
    return owner


def _upsert_fitness_day(conn, owner: str, item: FitnessDayPayload, source: str, now: str):
    day = _fitness_day(item.day)
    if not (0 <= item.steps <= 200000 and 0 <= item.distance_m <= 500000 and 0 <= item.active_energy_kcal <= 20000):
        raise HTTPException(status_code=400, detail=f"{day} 건강 수치가 허용 범위를 벗어났습니다")
    conn.execute(
        "INSERT INTO fitness_daily(username,day,steps,distance_m,active_energy_kcal,source,updated_at) VALUES(?,?,?,?,?,?,?) "
        "ON CONFLICT(username,day) DO UPDATE SET steps=excluded.steps,distance_m=excluded.distance_m,active_energy_kcal=excluded.active_energy_kcal,source=excluded.source,updated_at=excluded.updated_at",
        (owner, day, item.steps, item.distance_m, item.active_energy_kcal, source, now),
    )


@app.post("/api/fitness/pairing-token")
def create_fitness_pairing_token(request: Request):
    _require_signed_in_user(request)
    username = _request_username(request)
    token = "nhk_" + secrets.token_urlsafe(32)
    digest = hashlib.sha256(token.encode()).hexdigest()
    conn = get_conn()
    conn.execute(
        "INSERT INTO health_sync_tokens(username,token_hash,created_at,last_used_at) VALUES(?,?,?,NULL) "
        "ON CONFLICT(username) DO UPDATE SET token_hash=excluded.token_hash,created_at=excluded.created_at,last_used_at=NULL",
        (username, digest, _now()),
    )
    conn.commit(); conn.close()
    return {"token": token, "note": "이 연결 코드는 지금 한 번만 표시됩니다."}


@app.post("/api/fitness/sync")
def sync_fitness(payload: FitnessSyncPayload, authorization: Optional[str] = Header(None)):
    conn = get_conn()
    try:
        owner = _fitness_token_owner(authorization, conn)
    except HTTPException:
        conn.close(); raise
    if not 1 <= len(payload.days) <= 31:
        conn.close(); raise HTTPException(status_code=400, detail="한 번에 1~31일만 동기화할 수 있습니다")
    now = _now()
    try:
        for item in payload.days:
            _upsert_fitness_day(conn, owner, item, "healthkit", now)
    except HTTPException:
        conn.close(); raise
    conn.execute("UPDATE health_sync_tokens SET last_used_at=? WHERE username=?", (now, owner))
    conn.commit(); conn.close()
    return {"ok": True, "synced_days": len(payload.days), "updated_at": now}


@app.post("/api/fitness/shortcut-sync")
def sync_fitness_shortcut(payload: FitnessShortcutPayload, authorization: Optional[str] = Header(None)):
    """iOS 단축어에서 날짜별 합계 하나를 간단한 JSON으로 전송한다."""
    conn = get_conn()
    try:
        owner = _fitness_token_owner(authorization, conn)
        item = FitnessDayPayload(
            day=payload.day or datetime.date.today().isoformat(),
            steps=payload.steps,
            distance_m=payload.distance_m,
            active_energy_kcal=payload.active_energy_kcal,
        )
        now = _now()
        _upsert_fitness_day(conn, owner, item, "ios-shortcut", now)
        conn.execute("UPDATE health_sync_tokens SET last_used_at=? WHERE username=?", (now, owner))
        conn.commit()
    except HTTPException:
        conn.close(); raise
    conn.close()
    return {"ok": True, "day": item.day, "updated_at": now}


@app.get("/api/fitness/summary")
def fitness_summary(request: Request, days: int = 30):
    _require_signed_in_user(request)
    username = _request_username(request)
    days = max(7, min(int(days), 90))
    conn = get_conn()
    rows = conn.execute(
        "SELECT day,steps,distance_m,active_energy_kcal,updated_at FROM fitness_daily WHERE username=? ORDER BY day DESC LIMIT ?",
        (username, days),
    ).fetchall()
    setting = conn.execute("SELECT daily_step_goal FROM fitness_settings WHERE username=?", (username,)).fetchone()
    token = conn.execute("SELECT created_at,last_used_at FROM health_sync_tokens WHERE username=?", (username,)).fetchone()
    conn.close()
    goal = int(setting["daily_step_goal"] if setting else 10000)
    data = [dict(row) for row in reversed(rows)]
    return {"goal": goal, "days": data, "paired": bool(token), "last_sync_at": token["last_used_at"] if token else None}


@app.put("/api/fitness/settings")
def update_fitness_settings(payload: FitnessGoalPayload, request: Request):
    _require_signed_in_user(request)
    if not 1000 <= payload.daily_step_goal <= 100000:
        raise HTTPException(status_code=400, detail="목표 걸음 수는 1,000~100,000 사이여야 합니다")
    username = _request_username(request)
    conn = get_conn()
    conn.execute(
        "INSERT INTO fitness_settings(username,daily_step_goal,updated_at) VALUES(?,?,?) "
        "ON CONFLICT(username) DO UPDATE SET daily_step_goal=excluded.daily_step_goal,updated_at=excluded.updated_at",
        (username, payload.daily_step_goal, _now()),
    )
    conn.commit(); conn.close()
    return {"ok": True, "daily_step_goal": payload.daily_step_goal}


def _terrain_owned_survey(conn, username: str, survey_id: int):
    row = conn.execute("SELECT * FROM terrain_surveys WHERE id=? AND username=?", (survey_id, username)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="답사 기록을 찾을 수 없습니다")
    return row


def _terrain_point_values(point: TerrainTrackPoint):
    if not (-90 <= point.latitude <= 90 and -180 <= point.longitude <= 180):
        raise HTTPException(status_code=400, detail="GPS 좌표 범위가 올바르지 않습니다")
    return point.latitude, point.longitude, point.altitude, point.accuracy, point.recorded_at or _now()


def _terrain_haversine(a, b) -> float:
    import math
    lat1, lon1, lat2, lon2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 6371000 * 2 * math.asin(min(1, math.sqrt(h)))


def _terrain_serialize(row, conn):
    item = dict(row)
    item["hypotheses"] = json.loads(item.pop("hypotheses_json") or "[]")
    item["conditions"] = json.loads(item.pop("conditions_json") or "{}")
    item["summary"] = json.loads(item.pop("summary_json") or "{}")
    item["point_count"] = conn.execute("SELECT COUNT(*) FROM terrain_points WHERE survey_id=?", (item["id"],)).fetchone()[0]
    item["observation_count"] = conn.execute("SELECT COUNT(*) FROM terrain_points WHERE survey_id=? AND point_type='observation'", (item["id"],)).fetchone()[0]
    return item


@app.get("/api/terrain-survey/surveys")
def terrain_surveys(request: Request):
    _require_signed_in_user(request)
    conn = get_conn(); username = _request_username(request)
    rows = conn.execute("SELECT * FROM terrain_surveys WHERE username=? ORDER BY updated_at DESC", (username,)).fetchall()
    result = [_terrain_serialize(row, conn) for row in rows]
    conn.close(); return result


@app.post("/api/terrain-survey/surveys")
def terrain_create(payload: TerrainSurveyCreate, request: Request):
    _require_signed_in_user(request)
    title = payload.title.strip()[:80]
    if not title:
        raise HTTPException(status_code=400, detail="답사 이름을 입력해주세요")
    now = _now(); username = _request_username(request); conn = get_conn()
    cur = conn.execute("INSERT INTO terrain_surveys(username,title,location_name,hypotheses_json,conditions_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?)", (username, title, payload.location_name.strip()[:120], json.dumps(payload.hypotheses[:20], ensure_ascii=False), json.dumps(payload.conditions, ensure_ascii=False), now, now))
    conn.commit(); result = _terrain_serialize(_terrain_owned_survey(conn, username, cur.lastrowid), conn); conn.close(); return result


@app.get("/api/terrain-survey/surveys/{survey_id}")
def terrain_detail(survey_id: int, request: Request):
    _require_signed_in_user(request)
    conn = get_conn(); row = _terrain_owned_survey(conn, _request_username(request), survey_id); result = _terrain_serialize(row, conn)
    result["points"] = [dict(p) for p in conn.execute("SELECT id,point_type,latitude,longitude,altitude,accuracy,recorded_at,category,note,metadata_json FROM terrain_points WHERE survey_id=? ORDER BY recorded_at,id", (survey_id,)).fetchall()]
    for point in result["points"]:
        point["metadata"] = json.loads(point.pop("metadata_json") or "{}")
    conn.close(); return result


@app.post("/api/terrain-survey/surveys/{survey_id}/start")
def terrain_start(survey_id: int, request: Request):
    _require_signed_in_user(request)
    conn = get_conn(); username = _request_username(request); _terrain_owned_survey(conn, username, survey_id); now = _now()
    conn.execute("UPDATE terrain_surveys SET status='active',started_at=COALESCE(started_at,?),updated_at=? WHERE id=? AND username=?", (now, now, survey_id, username)); conn.commit(); conn.close()
    return {"ok": True, "started_at": now}


@app.post("/api/terrain-survey/surveys/{survey_id}/track")
def terrain_track(survey_id: int, payload: TerrainTrackBatch, request: Request):
    _require_signed_in_user(request)
    if not 1 <= len(payload.points) <= 100:
        raise HTTPException(status_code=400, detail="GPS 지점은 한 번에 1~100개만 저장할 수 있습니다")
    conn = get_conn(); username = _request_username(request); row = _terrain_owned_survey(conn, username, survey_id)
    if row["status"] != "active":
        conn.close(); raise HTTPException(status_code=409, detail="먼저 답사를 시작해주세요")
    for point in payload.points:
        lat, lon, alt, acc, at = _terrain_point_values(point)
        conn.execute("INSERT INTO terrain_points(survey_id,username,point_type,latitude,longitude,altitude,accuracy,recorded_at) VALUES(?,?,?,?,?,?,?,?)", (survey_id, username, "track", lat, lon, alt, acc, at))
    conn.execute("UPDATE terrain_surveys SET updated_at=? WHERE id=?", (_now(), survey_id)); conn.commit(); conn.close()
    return {"ok": True, "saved": len(payload.points)}


@app.post("/api/terrain-survey/surveys/{survey_id}/observations")
def terrain_observation(survey_id: int, payload: TerrainObservationCreate, request: Request):
    _require_signed_in_user(request)
    conn = get_conn(); username = _request_username(request); survey = _terrain_owned_survey(conn, username, survey_id)
    lat, lon, alt, acc, at = _terrain_point_values(payload)
    conn.execute("INSERT INTO terrain_points(survey_id,username,point_type,latitude,longitude,altitude,accuracy,recorded_at,category,note,metadata_json) VALUES(?,?,?,?,?,?,?,?,?,?,?)", (survey_id, username, "observation", lat, lon, alt, acc, at, payload.category.strip()[:30], payload.note.strip()[:500], json.dumps(payload.metadata, ensure_ascii=False)))
    conn.execute("UPDATE terrain_surveys SET updated_at=? WHERE id=?", (_now(), survey_id)); conn.commit(); conn.close(); return {"ok": True}


@app.post("/api/terrain-survey/surveys/{survey_id}/complete")
def terrain_complete(survey_id: int, payload: TerrainCompletePayload, request: Request):
    _require_signed_in_user(request)
    conn = get_conn(); username = _request_username(request); survey = _terrain_owned_survey(conn, username, survey_id)
    tracks = conn.execute("SELECT latitude,longitude,altitude FROM terrain_points WHERE survey_id=? AND point_type='track' ORDER BY recorded_at,id", (survey_id,)).fetchall()
    observations = conn.execute("SELECT category,COUNT(*) count FROM terrain_points WHERE survey_id=? AND point_type='observation' GROUP BY category", (survey_id,)).fetchall()
    distance = sum(_terrain_haversine(tracks[i - 1], tracks[i]) for i in range(1, len(tracks))) if tracks else 0
    elevation = [p["altitude"] for p in tracks if p["altitude"] is not None]
    conditions = json.loads(survey["conditions_json"] or "{}")
    planned_reward = max(10, min(60, int(conditions.get("planned_reward_xp") or 20)))
    xp = min(150, planned_reward + sum(r["count"] for r in observations) * 5 + min(50, int(distance / 200)))
    observed = {r["category"]: r["count"] for r in observations}
    principles = []
    if any(key in observed for key in ("고개", "병목")):
        principles.append("圮地無舍 · 험하고 막히는 땅에는 오래 머물지 않는다")
    if any(key in observed for key in ("능선", "시야")):
        principles.append("居高陽 · 높은 곳과 시야를 먼저 살핀다")
    if any(key in observed for key in ("하천", "습지")):
        principles.append("絶水必遠水 · 물을 건넌 뒤에는 물가에서 거리를 둔다")
    summary = {"distance_m": round(distance), "track_points": len(tracks), "observations": observed, "elevation_gain_m": round(max(elevation) - min(elevation)) if elevation else 0, "reflection": payload.reflection.strip()[:2000], "differences": payload.differences[:20], "field_xp": xp, "sunzi_principles": principles}
    now = _now(); conn.execute("UPDATE terrain_surveys SET status='completed',completed_at=?,summary_json=?,updated_at=? WHERE id=? AND username=?", (now, json.dumps(summary, ensure_ascii=False), now, survey_id, username)); conn.commit(); conn.close()
    return {"ok": True, "summary": summary, "completed_at": now}


@app.get("/api/terrain-survey/summary")
def terrain_summary(request: Request):
    _require_signed_in_user(request)
    conn = get_conn(); username = _request_username(request); rows = conn.execute("SELECT summary_json,conditions_json FROM terrain_surveys WHERE username=? AND status='completed'", (username,)).fetchall()
    summaries = [json.loads(row["summary_json"] or "{}") for row in rows]
    total_xp = sum(int(item.get("field_xp", 0)) for item in summaries)
    observation_count = sum(sum(item.get("observations", {}).values()) for item in summaries)
    differences = sum(len(item.get("differences", [])) for item in summaries)
    weather_logs = sum(bool(json.loads(row["conditions_json"] or "{}").get("weather")) for row in rows)
    skills = {"등고선 판독": len(rows) + differences, "경로 판단": min(99, sum(int(item.get("distance_m", 0)) for item in summaries) // 500), "현장 관찰": observation_count, "기상 대응": weather_logs * 2, "복기": sum(bool(item.get("reflection")) for item in summaries) * 3}
    conn.close()
    return {"completed": len(rows), "total_distance_m": sum(int(item.get("distance_m", 0)) for item in summaries), "field_xp": total_xp, "level": 1 + total_xp // 150, "skills": skills}


@app.get("/api/terrain-survey/nearby")
def terrain_nearby(request: Request, latitude: float, longitude: float, radius_km: int = 12):
    """현재 위치 주변의 이름 있는 자연 지형·공원·보호구역을 OSM에서 추천한다.

    위치는 추천 요청 처리에만 사용하고 서버 DB에는 저장하지 않는다. 실제 답사
    기록은 사용자가 후보를 선택하고 답사를 시작한 뒤에만 별도 API로 저장된다.
    """
    _require_signed_in_user(request)
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        raise HTTPException(status_code=400, detail="현재 위치 좌표가 올바르지 않습니다")
    radius = max(3000, min(int(radius_km) * 1000, 15000))
    # 위치를 장기 보관하지 않고 약 2 km 격자로만 메모리 캐시한다.
    # 잠시 후 재요청했을 때 외부 서버가 느려도 바로 응답할 수 있다.
    cache_key = (round(latitude, 2), round(longitude, 2), radius)
    cached = _terrain_nearby_cache.get(cache_key)
    if cached and time.time() - float(cached.get("saved_at", 0)) < 6 * 60 * 60:
        return {**cached["payload"], "cached": True}
    # 12 km 반경의 모든 nwr을 한 번에 요청하면 도시권에서 Overpass가
    # 쉬게 타임아웃된다. 답사지로 쓸 만한 이름 있는 객체만 제한하고,
    # 한 곳이 장애일 때를 대비해 독립된 미러를 순차적으로 사용한다.
    query = f'''[out:json][timeout:10];(
      node(around:{radius},{latitude},{longitude})["natural"~"peak|saddle"]["name"];
      way(around:{radius},{latitude},{longitude})["natural"~"ridge|valley|wetland"]["name"];
      way(around:{radius},{latitude},{longitude})["leisure"="park"]["name"];
      relation(around:{radius},{latitude},{longitude})["leisure"="park"]["name"];
      relation(around:{radius},{latitude},{longitude})["boundary"="protected_area"]["name"];
      way(around:{radius},{latitude},{longitude})["waterway"~"river|stream"]["name"];
    );out center tags 50;'''
    endpoints = (
        "https://overpass-api.de/api/interpreter",
        "https://overpass.kumi.systems/api/interpreter",
        "https://overpass.private.coffee/api/interpreter",
    )
    def fetch_overpass(endpoint):
        req = urllib.request.Request(
            endpoint,
            data=urllib.parse.urlencode({"data": query}).encode(),
            headers={"User-Agent": "NaTum-Terrain-Survey/1.1", "Accept": "application/json", "Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=8) as response:
                return endpoint, json.loads(response.read().decode("utf-8")).get("elements", []), None
        except Exception as exc:
            return endpoint, [], type(exc).__name__

    elements = []
    failures = []
    source = "OpenStreetMap contributors"
    # 느린 제공처를 순서대로 기다리지 않고 동시에 조회해 전체 대기를 8초 안팎으로 제한한다.
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=len(endpoints))
    futures = [executor.submit(fetch_overpass, endpoint) for endpoint in endpoints]
    try:
        for future in concurrent.futures.as_completed(futures, timeout=9):
            endpoint, result, error = future.result()
            if result:
                elements = result
                source = f"OpenStreetMap contributors · {urllib.parse.urlparse(endpoint).hostname}"
                break
            failures.append(f"{urllib.parse.urlparse(endpoint).hostname}: {error or 'empty'}")
    except concurrent.futures.TimeoutError:
        failures.append("provider pool: TimeoutError")
    finally:
        for future in futures:
            future.cancel()
        executor.shutdown(wait=False, cancel_futures=True)
    if not elements:
        # 첫 번째 병렬 조회가 모두 느릴 때는 정답 가능성이 높은
        # 봉우리·공원·하천만으로 줄인 쿼리를 한 번 더 널널한 제한으로 시도한다.
        compact_query = f'''[out:json][timeout:16];(
          node(around:{radius},{latitude},{longitude})["natural"~"peak|saddle"]["name"];
          nwr(around:{radius},{latitude},{longitude})["leisure"="park"]["name"];
          way(around:{radius},{latitude},{longitude})["waterway"~"river|stream"]["name"];
        );out center tags 35;'''
        req = urllib.request.Request(
            endpoints[0], data=urllib.parse.urlencode({"data": compact_query}).encode(),
            headers={"User-Agent": "NaTum-Terrain-Survey/1.1", "Accept": "application/json", "Content-Type": "application/x-www-form-urlencoded"}, method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=19) as response:
                elements = json.loads(response.read().decode("utf-8")).get("elements", [])
            source = "OpenStreetMap contributors · retry"
        except Exception as exc:
            failures.append(f"compact retry: {type(exc).__name__}")
    if not elements:
        # 외부 지형 검색이 잠시 멈춰도 위치 확인과 GPS 답사를 막지 않는다.
        # 이 후 Apple 지도에서 주변을 확인하고 현재 지점을 자유 답사로 저장할 수 있다.
        fallback = {
            "name": "현재 위치 자유 답사", "kind": "local", "kind_label": "주변 지형",
            "icon": "⌖", "distance_m": 0, "latitude": latitude, "longitude": longitude,
            "tasks": ["시야가 열리는 곳과 병목 찾기", "물길·능선·노면을 현장에서 구분하기"],
            "reward_xp": 15,
        }
        print(f"[terrain-nearby] Overpass unavailable; fallback used ({'; '.join(failures)})", file=sys.stderr)
        return {"items": [fallback], "radius_m": radius, "source": "device location", "degraded": True,
                "warning": "주변 지형 검색 서버가 지연되어 현재 위치 답사를 준비했어요. Apple 지도에서 주변을 함께 확인해 주세요."}
    labels = {"peak": ("산·봉우리", "⛰"), "ridge": ("능선", "⌁"), "valley": ("골짜기", "⌄"), "wetland": ("습지", "♒"), "park": ("공원", "🌳"), "protected_area": ("보호구역", "🌿"), "river": ("하천", "≈"), "stream": ("하천", "≈")}
    candidates = []
    seen = set()
    for element in elements:
        tags = element.get("tags") or {}; name = str(tags.get("name") or "").strip()
        center = element.get("center") or element
        lat, lon = center.get("lat"), center.get("lon")
        if not name or lat is None or lon is None or name in seen:
            continue
        kind = tags.get("natural") or tags.get("leisure") or ("protected_area" if tags.get("boundary") == "protected_area" else None) or tags.get("waterway") or "park"
        label, icon = labels.get(kind, ("자연 지형", "⌖"))
        meters = round(_terrain_haversine((latitude, longitude), (float(lat), float(lon))))
        task_map = {"peak": ["시야가 열리는 방향 확인", "접근로 경사 비교"], "ridge": ["능선 폭과 이동 가능 인원 판단", "양쪽 사면 관찰"], "valley": ["물길과 탈출 방향 확인", "시야 차단 지점 기록"], "wetland": ["통행 가능한 노면 찾기", "우회로 비교"], "park": ["휴식·집결 지점 선정", "병목 구간 찾기"], "protected_area": ["주요 능선과 골짜기 구분", "관찰 동선 기록"], "river": ["도하 후보 지점 비교", "강변 이동 위험 기록"], "stream": ["물길이 경로에 미치는 영향 확인", "건널목 찾기"]}
        reward = {"peak": 40, "ridge": 35, "valley": 35, "wetland": 40, "protected_area": 30, "river": 30, "stream": 25, "park": 20}.get(kind, 20)
        candidates.append({"name": name, "kind": kind, "kind_label": label, "icon": icon, "distance_m": meters, "latitude": lat, "longitude": lon, "tasks": task_map.get(kind, ["이동 경로와 시야를 관찰", "예상과 실제 지형 비교"]), "reward_xp": reward})
        seen.add(name)
    candidates.sort(key=lambda item: (item["distance_m"], item["name"]))
    payload = {"items": candidates[:12], "radius_m": radius, "source": source, "degraded": False, "cached": False}
    _terrain_nearby_cache[cache_key] = {"saved_at": time.time(), "payload": payload}
    return payload


@app.get("/api/version")
def get_version():
    """프론트가 폴링해서 배포 이후 값이 바뀌었으면 새로고침을 유도한다
    (SERVER_BOOT_ID 정의부의 설명 참고). 로그인 여부와 무관하게 누구나
    확인할 수 있어도 되는 값이라 인증을 요구하지 않는다."""
    static_dir = BASE_DIR / "static"
    mtimes = [
        f.stat().st_mtime for f in (static_dir / "index.html", static_dir / "chat.js", static_dir / "style.css")
        if f.exists()
    ]
    static_stamp = int(max(mtimes)) if mtimes else 0
    return {"version": f"{SERVER_BOOT_ID}-{static_stamp}"}


@app.get("/api/whoami")
def whoami(request: Request):
    """프론트엔드가 로그인 여부·쓰기 가능 여부를 미리 알아서, 비로그인
    방문자에겐 로그인/가입 화면을, 공유 링크 읽기 전용 방문자·로그인은
    했지만 읽기 전용인 방문자에겐 입력창을 숨긴 채팅 화면을 보여줄 수 있게
    한다. share_guest=False, logged_in=False인 조합만 진짜 "로그인이
    필요한" 상태다(공유 링크 방문자는 share_guest=True라 로그인 없이도
    채팅 화면을 그대로 봄)."""
    user = getattr(request.state, "user", None)
    display_name = None
    avatar_url = None
    if user:
        conn = get_conn()
        row = conn.execute(
            "SELECT display_name, avatar_url FROM users WHERE username = ?", (user["username"],)
        ).fetchone()
        conn.close()
        if row:
            display_name, avatar_url = row["display_name"], row["avatar_url"]
    return {
        "can_write": getattr(request.state, "can_write", True),
        "logged_in": user is not None,
        "username": user["username"] if user else None,
        "is_owner": bool(user["is_owner"]) if user else False,
        "share_guest": getattr(request.state, "share_guest", False),
        # ★ "자기 이름·프로필사진 바꿀 수 있게 해달라" 요청(2026-08-28) —
        # 로그인 직후 프론트가 내 표시 이름/아바타를 바로 알아야 헤더에 반영할
        # 수 있다.
        "display_name": display_name,
        "avatar_url": avatar_url,
        # ★ 2026-08-26: 구글/카카오 로그인 버튼은 실제로 설정(도메인+클라이언트
        # ID/시크릿)이 끝났을 때만 보여준다 — 로그인 화면이 아직 안 될 버튼을
        # 미리 보여주지 않게.
        "google_login_enabled": oauth.google_enabled(),
        "kakao_login_enabled": oauth.kakao_enabled(),
    }


@app.get("/api/personas")
def list_personas():
    conn = get_conn()
    rows = conn.execute("SELECT name FROM personas ORDER BY name").fetchall()
    conn.close()
    return [r["name"] for r in rows]


@app.get("/api/users")
def list_users_public(request: Request):
    """★ "친구 목록에 일반 가입자들도 뜨게 해달라" 요청(2026-08-28) — 페르소나
    말고 실제 가입 계정도 친구 탭에 보여준다. /api/admin/users(소유자 전용,
    유이 권한 부여 여부 등 관리 정보 포함)와 달리 이건 아이디·가입일만 내려주고
    로그인한 계정이면 누구나 볼 수 있다. 공유 링크 읽기 전용 방문자는 실제
    계정이 아니므로 제외한다."""
    user = getattr(request.state, "user", None)
    if user is None and not getattr(request.state, "can_write", False):
        raise HTTPException(status_code=403, detail="로그인이 필요합니다")
    exclude = user["username"] if user else None
    conn = get_conn()
    rows = conn.execute(
        "SELECT username, is_owner, created_at, display_name, avatar_url FROM users ORDER BY created_at"
    ).fetchall()
    favorites = {
        row["friend_username"] for row in conn.execute(
            "SELECT friend_username FROM friend_favorites WHERE username = ?", (exclude,)
        ).fetchall()
    } if exclude else set()
    conn.close()
    return [dict(r) | {"is_favorite": r["username"] in favorites} for r in rows if r["username"] != exclude]


@app.put("/api/friends/{friend_username}/favorite")
def add_friend_favorite(friend_username: str, request: Request):
    """로그인한 사용자 본인에게만 보이는 친구 즐겨찾기를 저장한다."""
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다")
    if friend_username == user["username"]:
        raise HTTPException(status_code=400, detail="자기 자신은 즐겨찾기할 수 없습니다")
    conn = get_conn()
    exists = conn.execute("SELECT 1 FROM users WHERE username = ?", (friend_username,)).fetchone()
    if not exists:
        conn.close()
        raise HTTPException(status_code=404, detail="친구를 찾을 수 없습니다")
    conn.execute(
        "INSERT OR IGNORE INTO friend_favorites (username, friend_username, created_at) VALUES (?, ?, ?)",
        (user["username"], friend_username, datetime.datetime.now(datetime.timezone.utc).isoformat()),
    )
    conn.commit()
    conn.close()
    return {"ok": True, "is_favorite": True}


@app.delete("/api/friends/{friend_username}/favorite")
def remove_friend_favorite(friend_username: str, request: Request):
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다")
    conn = get_conn()
    conn.execute(
        "DELETE FROM friend_favorites WHERE username = ? AND friend_username = ?",
        (user["username"], friend_username),
    )
    conn.commit()
    conn.close()
    return {"ok": True, "is_favorite": False}


JAPANESE_KANJI_RE = re.compile(r"^[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]$")


class VocabularyEntryUpdate(BaseModel):
    language: str = "english"
    term: str
    meaning: str = ""
    pronunciation: str = ""
    note: str = ""


class VocabularyPracticeAttemptCreate(BaseModel):
    language: str = "japanese"
    term: str
    score: int
    practice_type: str = "writing"
    graded_count: int = 1
    image_data: str = ""


@app.get("/api/me/vocabulary")
def list_vocabulary_entries(request: Request, language: str = ""):
    user = getattr(request.state, "user", None)
    if not user: raise HTTPException(status_code=401, detail="로그인이 필요합니다")
    params = [user["username"]]; where = "WHERE username=?"
    if language:
        where += " AND language=?"; params.append(language)
    conn = get_conn()
    rows = conn.execute(f"SELECT id,language,term,meaning,pronunciation,note,created_at,updated_at FROM vocabulary_entries {where} ORDER BY updated_at DESC,id DESC", params).fetchall()
    conn.close()
    return [dict(row) for row in rows]


@app.post("/api/me/vocabulary")
def save_vocabulary_entry(body: VocabularyEntryUpdate, request: Request):
    user = getattr(request.state, "user", None)
    if not user: raise HTTPException(status_code=401, detail="로그인이 필요합니다")
    language, term = body.language.strip().lower(), body.term.strip()
    if language not in {"english", "japanese", "hanja"}: raise HTTPException(status_code=400, detail="지원하지 않는 언어입니다")
    if not term or len(term) > 120: raise HTTPException(status_code=400, detail="단어는 1~120자로 입력하세요")
    values = [body.meaning.strip(), body.pronunciation.strip(), body.note.strip()]
    if any(len(value) > 1000 for value in values): raise HTTPException(status_code=400, detail="뜻·발음·메모는 각각 1000자 이하로 입력하세요")
    now = _now(); conn = get_conn()
    conn.execute("""INSERT INTO vocabulary_entries(username,language,term,meaning,pronunciation,note,created_at,updated_at)
        VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(username,language,term) DO UPDATE SET
        meaning=excluded.meaning,pronunciation=excluded.pronunciation,note=excluded.note,updated_at=excluded.updated_at""",
        (user["username"], language, term, *values, now, now))
    conn.commit()
    row = conn.execute("SELECT id,language,term,meaning,pronunciation,note,created_at,updated_at FROM vocabulary_entries WHERE username=? AND language=? AND term=?", (user["username"], language, term)).fetchone()
    conn.close(); return dict(row)


@app.delete("/api/me/vocabulary/{entry_id}")
def delete_vocabulary_entry(entry_id: int, request: Request):
    user = getattr(request.state, "user", None)
    if not user: raise HTTPException(status_code=401, detail="로그인이 필요합니다")
    conn = get_conn(); cursor = conn.execute("DELETE FROM vocabulary_entries WHERE id=? AND username=?", (entry_id, user["username"])); conn.commit(); conn.close()
    if not cursor.rowcount: raise HTTPException(status_code=404, detail="단어를 찾을 수 없습니다")
    return {"ok": True}


def _vocabulary_practice_xp(score: int) -> int:
    """시도 자체는 보상하되 정확도가 높을수록 숙련도가 더 오른다."""
    return max(1, min(10, int(score) // 10))


@app.get("/api/me/vocabulary-practice-summary")
def vocabulary_practice_summary(request: Request):
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다")
    conn = get_conn()
    rows = conn.execute(
        """SELECT language,term,COUNT(*) AS attempt_count,
                  COALESCE(SUM(graded_count),COUNT(*)) AS graded_count
             FROM vocabulary_practice_attempts
            WHERE username=? AND practice_type='writing'
            GROUP BY language,term
            ORDER BY language,term""",
        (user["username"],),
    ).fetchall()
    conn.close()
    counts = {"japanese": 0, "english": 0}
    items = []
    for row in rows:
        if row["language"] in {"japanese", "hanja"}:
            counts["japanese"] += int(row["attempt_count"] or 0)
        elif row["language"] == "english":
            counts["english"] += int(row["attempt_count"] or 0)
        items.append({
            "language": row["language"],
            "term": row["term"],
            "attempt_count": int(row["attempt_count"] or 0),
            "graded_count": int(row["graded_count"] or row["attempt_count"] or 0),
        })
    return {**counts, "items": items}


@app.get("/api/me/vocabulary-practice")
def list_vocabulary_practice_attempts(request: Request, language: str = "", limit: int = 50):
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다")
    params = [user["username"]]
    where = "WHERE username=?"
    if language:
        where += " AND language=?"
        params.append(language.strip().lower())
    limit = max(1, min(200, int(limit or 50)))
    conn = get_conn()
    rows = conn.execute(
        f"""SELECT id,language,term,practice_type,score,xp,graded_count,image_data,created_at
             FROM vocabulary_practice_attempts {where}
             ORDER BY created_at DESC,id DESC LIMIT ?""",
        [*params, limit],
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


@app.post("/api/me/vocabulary-practice")
def save_vocabulary_practice_attempt(body: VocabularyPracticeAttemptCreate, request: Request):
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다")
    language = body.language.strip().lower()
    term = body.term.strip()
    practice_type = body.practice_type.strip().lower()
    if language not in {"english", "japanese", "hanja"}:
        raise HTTPException(status_code=400, detail="지원하지 않는 언어입니다")
    if practice_type not in {"writing", "speaking"}:
        raise HTTPException(status_code=400, detail="지원하지 않는 연습 방식입니다")
    if not term or len(term) > 120:
        raise HTTPException(status_code=400, detail="단어는 1~120자로 입력하세요")
    score = max(0, min(100, int(body.score)))
    graded_count = max(1, min(120, int(body.graded_count or 1)))
    image_data = body.image_data.strip()
    if image_data and (not image_data.startswith("data:image/png;base64,") or len(image_data) > 1_500_000):
        raise HTTPException(status_code=400, detail="필기 이미지는 PNG 1.5MB 이하만 저장할 수 있습니다")
    xp = _vocabulary_practice_xp(score)
    now = _now()
    conn = get_conn()
    cursor = conn.execute(
        """INSERT INTO vocabulary_practice_attempts
           (username,language,term,practice_type,score,xp,graded_count,image_data,created_at)
           VALUES(?,?,?,?,?,?,?,?,?)""",
        (user["username"], language, term, practice_type, score, xp, graded_count, image_data, now),
    )
    conn.commit()
    row = conn.execute(
        """SELECT id,language,term,practice_type,score,xp,graded_count,image_data,created_at
           FROM vocabulary_practice_attempts WHERE id=? AND username=?""",
        (cursor.lastrowid, user["username"]),
    ).fetchone()
    conn.close()
    return dict(row)


class MemoDocumentCreate(BaseModel):
    title: str = "새 메모"
    note: str = ""
    category_id: Optional[int] = None
    category_ids: Optional[list[int]] = None


class MemoDocumentUpdate(BaseModel):
    title: str
    note: str = ""
    card_width: Optional[float] = None


class MemoNodeCreate(BaseModel):
    parent_id: Optional[int] = None
    content: str
    position_x: Optional[float] = None
    position_y: Optional[float] = None
    card_width: Optional[float] = 620
    image_data: str = ""
    drawing_data: str = ""


class MemoNodeUpdate(BaseModel):
    content: str
    position_x: Optional[float] = None
    position_y: Optional[float] = None
    card_width: Optional[float] = None
    image_data: Optional[str] = None
    drawing_data: Optional[str] = None


class MemoCategoryWrite(BaseModel):
    name: str


class MemoCategoryAssign(BaseModel):
    category_id: Optional[int] = None
    category_ids: Optional[list[int]] = None


class ChatMapLayoutWrite(BaseModel):
    version: int = 2
    cards: dict[str, dict[str, float]] = {}
    view: dict[str, float] = {}


class ChatTopicImport(BaseModel):
    topic_key: str


def _validate_memo_media(image_data: str, drawing_data: str):
    image_data = image_data or ""
    drawing_data = drawing_data or ""
    if image_data and not re.match(r"^data:image/(?:jpeg|png|webp);base64,", image_data, re.I):
        raise HTTPException(status_code=400, detail="지원하지 않는 이미지 형식입니다")
    if len(image_data) > 5_500_000:
        raise HTTPException(status_code=413, detail="이미지가 너무 큽니다. 더 작은 사진을 선택하세요")
    if len(drawing_data) > 2_000_000:
        raise HTTPException(status_code=413, detail="필기 데이터가 너무 큽니다")
    if drawing_data:
        try:
            drawing = json.loads(drawing_data)
            strokes = drawing.get("strokes", [])
            if drawing.get("version") != 1 or not isinstance(strokes, list) or len(strokes) > 4000:
                raise ValueError
            if sum(len(stroke.get("points", [])) for stroke in strokes if isinstance(stroke, dict)) > 120000:
                raise ValueError
        except (TypeError, ValueError, json.JSONDecodeError):
            raise HTTPException(status_code=400, detail="필기 데이터가 올바르지 않습니다")
    return image_data, drawing_data


def _memo_user(request):
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다")
    return user


def _memo_document_payload(conn, username):
    documents = [dict(row) for row in conn.execute(
        """SELECT id,source_message_id,source_room_id,source_sender,source_content,
                  source_topic_key,source_topic_title,source_last_message_id,
                  title,note,card_width,category_id,created_at,updated_at
           FROM memo_documents WHERE username=? ORDER BY updated_at DESC,id DESC""",
        (username,),
    ).fetchall()]
    if not documents:
        return []
    ids = [document["id"] for document in documents]
    placeholders = ",".join("?" for _ in ids)
    nodes = [dict(row) for row in conn.execute(
        f"""SELECT id,memo_id,parent_id,content,sort_order,position_x,position_y,card_width,image_data,drawing_data,
                   source_message_id,source_room_id,created_at,updated_at
            FROM memo_nodes WHERE memo_id IN ({placeholders})
            ORDER BY sort_order,id""", ids
    ).fetchall()]
    grouped = {memo_id: [] for memo_id in ids}
    for node in nodes:
        grouped[node["memo_id"]].append(node)
    for document in documents:
        document["nodes"] = grouped[document["id"]]
    category_rows = conn.execute(
        f"""SELECT mc.memo_id,mc.category_id FROM memo_document_categories mc
              JOIN memo_documents d ON d.id=mc.memo_id
             WHERE mc.memo_id IN ({placeholders}) AND d.username=?
             ORDER BY mc.created_at,mc.category_id""",
        (*ids, username),
    ).fetchall()
    category_grouped = {memo_id: [] for memo_id in ids}
    for row in category_rows:
        category_grouped[row["memo_id"]].append(row["category_id"])
    for document in documents:
        document["category_ids"] = category_grouped[document["id"]]
    return documents


@app.get("/api/me/memos")
def list_memos(request: Request):
    user = _memo_user(request)
    conn = get_conn()
    documents = _memo_document_payload(conn, user["username"])
    conn.close()
    return documents


_CHAT_MAP_STOPWORDS = {
    "그리고", "그런데", "그래서", "하지만", "그러면", "이거", "저거", "그거", "여기", "거기",
    "지금", "현재", "오늘", "내일", "어제", "다시", "그냥", "약간", "정도", "부분", "내용",
    "기능", "시스템", "채팅", "메시지", "생각", "경우", "관련", "사용", "작업", "진행", "확인",
    "페이지", "세션", "이번", "지난", "얘기", "얘기가", "이야기", "부분이", "내용이", "오늘은", "원문",
    "읽은", "좋은", "이미", "지금은", "핵심이네", "진짜", "나는", "나온", "결국", "계속", "먼저",
    "만들어", "만들고", "해줘", "해주세요", "하면", "해서", "하는", "있는", "없는", "있으면",
    "좋겠어", "좋을", "같아", "같은", "되면", "되는", "아니", "근데", "말이야", "혹시", "뭔가",
    "really", "just", "that", "this", "with", "from", "have", "will", "about", "http", "https",
    "green", "red", "blue", "orange", "purple", "color", "bg", "comment", "bold", "italic",
}


_CHAT_MAP_FORMAT_TOKEN = re.compile(
    r"\[\[/?(?:b|i|u|s|red|blue|green|orange|purple|color(?::[^\]]*)?|bg(?::[^\]]*)?|comment(?::[^\]]*)?)\]\]",
    re.I,
)


def _chat_map_clean_content(content: str) -> str:
    """툴파챗 표시 문법을 없애고 사용자가 실제로 읽는 본문만 남긴다."""
    clean = content or ""
    clean = re.sub(r"\[([^\]]+)\]\(https?://[^)]+\)", r"\1", clean)
    clean = re.sub(r"https?://\S+", " ", clean, flags=re.I)
    clean = re.sub(r"```[\s\S]*?```|`[^`]*`", " ", clean)
    clean = _CHAT_MAP_FORMAT_TOKEN.sub("", clean)
    clean = re.sub(r"<[^>]+>", " ", clean)
    return re.sub(r"[#>*_~|]", " ", clean)


def _chat_map_emphasized_terms(content: str) -> list[str]:
    """색상·굵기 표시는 버리고 그 안에서 사람이 강조한 짧은 표현만 보존한다."""
    result = []
    pattern = re.compile(
        r"\[\[(red|blue|green|orange|purple|b|i|u|s)\]\]([\s\S]*?)\[\[/\1\]\]", re.I
    )
    for match in pattern.finditer(content or ""):
        value = re.sub(r"\s+", " ", _chat_map_clean_content(match.group(2))).strip(" .,:;!?-—")
        if not value or len(value) > 48 or len(value.split()) > 5:
            continue
        if value.lower() in _CHAT_MAP_STOPWORDS:
            continue
        if value not in result:
            result.append(value)
    return result[:6]


def _chat_map_terms(content: str) -> list[str]:
    """메시지에 실제로 등장한 단어만 뽑아 지도 제목 후보로 사용한다."""
    clean = _chat_map_clean_content(content)
    words = re.findall(r"[A-Za-z][A-Za-z0-9_.+-]{2,}|[가-힣]{2,}|[一-龯ぁ-ゖァ-ヺ]{2,}", clean)
    result = _chat_map_emphasized_terms(content)
    for word in words:
        normalized = word.lower() if re.match(r"[A-Za-z]", word) else word
        normalized = normalized.strip("._-+")
        if len(normalized) < 2 or normalized in _CHAT_MAP_STOPWORDS or normalized.isdigit():
            continue
        if normalized not in result:
            result.append(normalized)
    return result[:12]


def _chat_map_message_kind(content: str) -> str:
    compact = re.sub(r"\s+", " ", content or "").lower()
    if any(token in compact for token in ("완료", "반영했습니다", "수정했습니다", "해결", "끝났")):
        return "completed"
    if any(token in compact for token in ("오류", "에러", "안 돼", "안되", "실패", "문제", "이상해", "왜 ")):
        return "problem"
    if any(token in compact for token in ("해줘", "해주세요", "추가", "만들어", "바꿔", "수정", "개선")):
        return "request"
    if any(token in compact for token in ("결정", "하자", "하기로", "승인", "적용")):
        return "decision"
    return "discussion"


def _chat_map_payload(rows, room_id: str, message_limit: Optional[int] = 12) -> dict[str, Any]:
    usable = []
    frequency: dict[str, int] = {}
    for row in rows:
        item = dict(row)
        if item.get("is_system") or _is_internal_worker_status_message(item.get("content", "")):
            continue
        item["emphasized_terms"] = _chat_map_emphasized_terms(item.get("content", ""))
        terms = _chat_map_terms(item.get("content", ""))
        if not terms:
            continue
        item["terms"] = terms
        item["kind"] = _chat_map_message_kind(item.get("content", ""))
        usable.append(item)
        for term in terms:
            frequency[term] = frequency.get(term, 0) + 1
    clusters: dict[str, dict[str, Any]] = {}
    for item in usable:
        emphasized = set(item.get("emphasized_terms", []))
        ranked = sorted(
            item["terms"],
            key=lambda term: (-(frequency.get(term, 0) + (50 if term in emphasized else 0)), item["terms"].index(term)),
        )
        topic = ranked[0]
        cluster = clusters.setdefault(topic, {
            "key": topic, "title": topic, "keywords": [], "messages": [], "message_count": 0,
            "message_ids": [],
            "kinds": {"request": 0, "decision": 0, "problem": 0, "completed": 0, "discussion": 0},
        })
        cluster["message_count"] += 1
        cluster["message_ids"].append(item["id"])
        cluster["kinds"][item["kind"]] += 1
        for term in ranked[:5]:
            if term not in cluster["keywords"]:
                cluster["keywords"].append(term)
        if message_limit is None or len(cluster["messages"]) < message_limit:
            text = re.sub(r"\s+", " ", item.get("content", "")).strip()
            cluster["messages"].append({
                "id": item["id"], "sender": item.get("sender", ""), "content": text[:240],
                "created_at": item.get("created_at", ""), "kind": item["kind"],
            })
    topics = sorted(clusters.values(), key=lambda item: (-item["message_count"], item["title"]))[:16]
    for topic in topics:
        topic["keywords"] = topic["keywords"][:6]
    return {
        "room_id": room_id, "message_count": len(usable), "topic_count": len(topics),
        "last_message_id": max((item["id"] for item in usable), default=0), "topics": topics,
    }


def _semantic_chat_map_payload(rows, room_id: str, message_limit: Optional[int] = 12):
    prepared = []
    for row in rows:
        item = dict(row)
        if item.get("is_system") or item.get("topic_status") != "done" or not item.get("embedding"):
            continue
        try:
            item["embedding"] = topic_analysis.unpack_embedding(item["embedding"], item["embedding_dim"])
            item["keywords"] = json.loads(item.get("keywords_json") or "[]")
        except (ValueError, json.JSONDecodeError):
            continue
        item["kind"] = item.get("message_type") or _chat_map_message_kind(item.get("content", ""))
        prepared.append(item)
    if len(prepared) < 4:
        return None
    # 최근 500개의 의미 벡터만 군집화한다. 메시지 전문은 별도 주제 조회 API가
    # 전체를 페이지 단위로 제공하므로 지도 구성 자체가 오래된 방에서 무거워지지 않는다.
    prepared = prepared[-500:]
    subclusters = topic_analysis.hierarchical_clusters(
        prepared, threshold=0.72, max_cluster_size=max(12, (len(prepared) + 3) // 4)
    )
    cluster_items = []
    for index, cluster in enumerate(subclusters):
        frequency = {}
        for item in cluster["items"]:
            for rank, keyword in enumerate(item["keywords"][:6]):
                frequency[keyword] = frequency.get(keyword, 0) + (6 - rank)
        candidates = sorted(
            frequency, key=lambda value: (-frequency[value], value in topic_analysis.STOPWORDS, len(value) < 3, -len(value))
        )
        title = next((value for value in candidates if value not in topic_analysis.STOPWORDS), "기타 대화")
        anchor_id = min((item["id"] for item in cluster["items"]), default=index)
        key = "semantic:" + hashlib.sha1(
            (room_id + "\0" + title + "\0" + str(anchor_id)).encode()
        ).hexdigest()[:16]
        messages = []
        for item in cluster["items"]:
            if message_limit is not None and len(messages) >= message_limit:
                break
            messages.append({
                "id": item["id"], "sender": item.get("sender", ""),
                "content": re.sub(r"\s+", " ", item.get("content", "")).strip()[:240],
                "summary": item.get("topic_summary") or "", "created_at": item.get("created_at", ""),
                "kind": item["kind"],
            })
        kinds = {name: 0 for name in ("request", "decision", "problem", "completed", "question", "discussion")}
        for item in cluster["items"]:
            kinds[item["kind"] if item["kind"] in kinds else "discussion"] += 1
        cluster_items.append({
            "key": key, "title": title, "keywords": candidates[:6], "messages": messages,
            "message_ids": [item["id"] for item in cluster["items"]],
            "message_count": len(cluster["items"]), "kinds": kinds,
            "centroid": cluster["centroid"], "_index": index,
        })
    parent_inputs = [{"embedding": item["centroid"], "cluster": item} for item in cluster_items]
    parents = topic_analysis.hierarchical_clusters(parent_inputs, threshold=0.58, max_cluster_size=8)
    for parent_index, parent in enumerate(parents):
        children = [entry["cluster"] for entry in parent["items"]]
        parent_keywords = []
        for child in sorted(children, key=lambda value: -value["message_count"]):
            for keyword in child["keywords"]:
                if keyword not in parent_keywords:
                    parent_keywords.append(keyword)
        parent_title = parent_keywords[0] if parent_keywords else "기타 대화"
        child_signature = "\0".join(sorted(child["key"] for child in children))
        parent_key = "group:" + hashlib.sha1(
            (room_id + "\0" + parent_title + "\0" + child_signature).encode()
        ).hexdigest()[:16]
        for child in children:
            child["parent_key"] = parent_key
            child["parent_title"] = parent_title
            child.pop("centroid", None); child.pop("_index", None)
    topics = sorted(cluster_items, key=lambda item: (-item["message_count"], item["title"]))[:40]
    return {
        "room_id": room_id, "message_count": len(prepared), "topic_count": len(topics),
        "last_message_id": max((item["id"] for item in prepared), default=0),
        "analysis_engine": topic_analysis.MODEL_VERSION, "topics": topics,
    }


@app.get("/api/me/chat-mindmap")
def get_chat_mindmap(request: Request, room_id: str, limit: int = Query(600, ge=50, le=1500)):
    user = _memo_user(request); conn = get_conn()
    access_probe = conn.execute(
        "SELECT id,room_id,sender,content,created_at FROM messages WHERE room_id=? ORDER BY id DESC LIMIT 1",
        (room_id,),
    ).fetchone()
    if access_probe:
        _ensure_message_visible(conn, access_probe, user["username"], bool(user["is_owner"]))
    rows = conn.execute(
        """SELECT m.id,m.room_id,m.sender,m.content,m.created_at,m.is_system,
                  t.status AS topic_status,t.keywords_json,t.message_type,t.summary AS topic_summary,
                  t.embedding,t.embedding_dim
             FROM messages m LEFT JOIN message_topic_metadata t ON t.message_id=m.id
            WHERE m.room_id=? ORDER BY m.id DESC LIMIT ?""", (room_id, limit)
    ).fetchall()
    ordered_rows = list(reversed(rows))
    payload = (_semantic_chat_map_payload(ordered_rows, room_id, message_limit=None)
               or _chat_map_payload(ordered_rows, room_id, message_limit=None))
    previous = conn.execute(
        "SELECT last_message_id,layout_json,updated_at FROM memo_chat_maps WHERE username=? AND room_id=?",
        (user["username"], room_id),
    ).fetchone()
    previous_id = previous["last_message_id"] if previous else 0
    payload["new_message_count"] = sum(
        1 for row in rows
        if row["id"] > previous_id and not row["is_system"]
        and not _is_internal_worker_status_message(row["content"] or "")
    )
    try:
        payload["layout"] = json.loads(previous["layout_json"] or "{}") if previous else {}
    except json.JSONDecodeError:
        payload["layout"] = {}
    now = _now()
    conn.execute(
        """INSERT INTO memo_chat_maps(username,room_id,room_title,last_message_id,layout_json,created_at,updated_at)
           VALUES(?,?,?,?,?,?,?)
           ON CONFLICT(username,room_id) DO UPDATE SET
             last_message_id=excluded.last_message_id,updated_at=excluded.updated_at""",
        (user["username"], room_id, room_id, payload["last_message_id"],
         json.dumps(payload["layout"], ensure_ascii=False), now, now),
    )
    conn.commit(); conn.close(); return payload


@app.get("/api/me/chat-maps")
def list_chat_maps(request: Request):
    user = _memo_user(request)
    rooms = list_rooms(request)
    conn = get_conn()
    states = {
        row["room_id"]: dict(row) for row in conn.execute(
            "SELECT room_id,last_message_id,updated_at FROM memo_chat_maps WHERE username=?",
            (user["username"],),
        ).fetchall()
    }
    result = []
    for room in rooms:
        state = states.get(room["room_id"], {})
        last_message_id = int(room.get("last_message_id") or 0)
        synced_id = int(state.get("last_message_id") or 0)
        count = conn.execute(
            "SELECT COUNT(*) AS n FROM messages WHERE room_id=? AND id>? AND is_system=0",
            (room["room_id"], synced_id),
        ).fetchone()["n"]
        result.append({**room, "synced_message_id": synced_id,
                       "new_message_count": count, "last_synced_at": state.get("updated_at")})
    conn.close()
    return sorted(result, key=lambda item: item.get("last_message_at") or "", reverse=True)


@app.put("/api/me/chat-mindmap/layout")
def save_chat_map_layout(room_id: str, body: ChatMapLayoutWrite, request: Request):
    user = _memo_user(request)
    layout = {"version": body.version, "cards": body.cards, "view": body.view}
    encoded = json.dumps(layout, ensure_ascii=False, separators=(",", ":"))
    if len(encoded) > 200_000:
        raise HTTPException(status_code=413, detail="지도 배치 정보가 너무 큽니다")
    conn = get_conn()
    probe = conn.execute(
        "SELECT id,room_id,sender,content,created_at FROM messages WHERE room_id=? ORDER BY id DESC LIMIT 1",
        (room_id,),
    ).fetchone()
    if probe:
        _ensure_message_visible(conn, probe, user["username"], bool(user["is_owner"]))
    now = _now()
    conn.execute(
        """INSERT INTO memo_chat_maps(username,room_id,room_title,last_message_id,layout_json,created_at,updated_at)
           VALUES(?,?,?,?,?,?,?)
           ON CONFLICT(username,room_id) DO UPDATE SET layout_json=excluded.layout_json,updated_at=excluded.updated_at""",
        (user["username"], room_id, room_id, 0, encoded, now, now),
    )
    conn.commit(); conn.close()
    return {"ok": True}


@app.post("/api/me/chat-mindmap/{room_id}/topic-memo")
def import_chat_topic_as_memo(room_id: str, body: ChatTopicImport, request: Request):
    user = _memo_user(request); conn = get_conn()
    rows = conn.execute(
        """SELECT m.id,m.room_id,m.sender,m.content,m.created_at,m.is_system,
                  t.status AS topic_status,t.keywords_json,t.message_type,t.summary AS topic_summary,
                  t.embedding,t.embedding_dim
             FROM messages m LEFT JOIN message_topic_metadata t ON t.message_id=m.id
            WHERE m.room_id=? ORDER BY m.id DESC LIMIT 1500""", (room_id,)
    ).fetchall()
    if rows:
        _ensure_message_visible(conn, rows[0], user["username"], bool(user["is_owner"]))
    ordered_rows = list(reversed(rows))
    payload = (_semantic_chat_map_payload(ordered_rows, room_id, message_limit=None)
               or _chat_map_payload(ordered_rows, room_id, message_limit=None))
    topic = next((item for item in payload["topics"] if item["key"] == body.topic_key), None)
    if not topic:
        conn.close(); raise HTTPException(status_code=404, detail="현재 지도에서 주제를 찾을 수 없습니다")
    existing = conn.execute(
        """SELECT id FROM memo_documents
             WHERE username=? AND source_room_id=? AND source_topic_key=?""",
        (user["username"], room_id, topic["key"]),
    ).fetchone()
    now = _now(); created = not bool(existing)
    if existing:
        memo_id = existing["id"]
        conn.execute(
            """UPDATE memo_documents SET source_topic_title=?,source_last_message_id=?,updated_at=?
                 WHERE id=?""", (topic["title"], payload["last_message_id"], now, memo_id)
        )
    else:
        cursor = conn.execute(
            """INSERT INTO memo_documents
               (username,source_room_id,source_sender,source_content,source_topic_key,source_topic_title,
                source_last_message_id,title,note,card_width,created_at,updated_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
            (user["username"], room_id, "채팅 생각 지도", "", topic["key"], topic["title"],
             payload["last_message_id"], f"{topic['title']} · 채팅 주제", "", 620, now, now),
        )
        memo_id = cursor.lastrowid
    existing_ids = {
        row["source_message_id"] for row in conn.execute(
            "SELECT source_message_id FROM memo_nodes WHERE memo_id=? AND source_message_id IS NOT NULL",
            (memo_id,),
        ).fetchall()
    }
    message_by_id = {message["id"]: message for message in topic["messages"]}
    added = 0
    for message_id in topic["message_ids"]:
        if message_id in existing_ids or message_id not in message_by_id:
            continue
        message = message_by_id[message_id]
        order = conn.execute(
            "SELECT COALESCE(MAX(sort_order),-1)+1 AS n FROM memo_nodes WHERE memo_id=? AND parent_id IS NULL",
            (memo_id,),
        ).fetchone()["n"]
        content = f"{message['sender']} · {message['content']}"[:6000]
        conn.execute(
            """INSERT INTO memo_nodes
               (memo_id,parent_id,content,sort_order,source_message_id,source_room_id,created_at,updated_at)
               VALUES(?,NULL,?,?,?,?,?,?)""",
            (memo_id, content, order, message_id, room_id, now, now),
        )
        added += 1
    conn.commit(); conn.close()
    return {"ok": True, "id": memo_id, "created": created, "added": added,
            "url": f"/memo/?memo={memo_id}"}


def _memo_category_name(value: str) -> str:
    name = re.sub(r"\s+", " ", value or "").strip()
    if not name or len(name) > 40:
        raise HTTPException(status_code=400, detail="키워드 이름은 1~40자로 입력하세요")
    return name


@app.get("/api/me/memo-categories")
def list_memo_categories(request: Request):
    user = _memo_user(request); conn = get_conn()
    rows = conn.execute(
        """SELECT c.id,c.name,c.sort_order,c.created_at,c.updated_at,COUNT(mc.memo_id) AS memo_count
           FROM memo_categories c LEFT JOIN memo_document_categories mc
             ON mc.category_id=c.id
           WHERE c.username=? GROUP BY c.id ORDER BY c.sort_order,c.id""",
        (user["username"],),
    ).fetchall()
    result = [dict(row) for row in rows]; conn.close(); return result


@app.post("/api/me/memo-categories")
def create_memo_category(body: MemoCategoryWrite, request: Request):
    user = _memo_user(request); name = _memo_category_name(body.name); conn = get_conn()
    duplicate = conn.execute(
        "SELECT id FROM memo_categories WHERE username=? AND lower(name)=lower(?)", (user["username"], name)
    ).fetchone()
    if duplicate: conn.close(); raise HTTPException(status_code=409, detail="이미 있는 키워드입니다")
    now = _now(); order = conn.execute(
        "SELECT COALESCE(MAX(sort_order),-1)+1 AS n FROM memo_categories WHERE username=?", (user["username"],)
    ).fetchone()["n"]
    cursor = conn.execute(
        "INSERT INTO memo_categories(username,name,sort_order,created_at,updated_at) VALUES(?,?,?,?,?)",
        (user["username"], name, order, now, now),
    ); conn.commit(); category_id = cursor.lastrowid; conn.close()
    return {"ok": True, "id": category_id, "name": name}


@app.put("/api/me/memo-categories/{category_id}")
def update_memo_category(category_id: int, body: MemoCategoryWrite, request: Request):
    user = _memo_user(request); name = _memo_category_name(body.name); conn = get_conn()
    duplicate = conn.execute(
        "SELECT id FROM memo_categories WHERE username=? AND lower(name)=lower(?) AND id<>?",
        (user["username"], name, category_id),
    ).fetchone()
    if duplicate: conn.close(); raise HTTPException(status_code=409, detail="이미 있는 키워드입니다")
    cursor = conn.execute(
        "UPDATE memo_categories SET name=?,updated_at=? WHERE id=? AND username=?",
        (name, _now(), category_id, user["username"]),
    ); conn.commit(); conn.close()
    if not cursor.rowcount: raise HTTPException(status_code=404, detail="키워드를 찾을 수 없습니다")
    return {"ok": True, "id": category_id, "name": name}


@app.delete("/api/me/memo-categories/{category_id}")
def delete_memo_category(category_id: int, request: Request):
    user = _memo_user(request); conn = get_conn()
    owned = conn.execute("SELECT 1 FROM memo_categories WHERE id=? AND username=?", (category_id, user["username"])).fetchone()
    if not owned: conn.close(); raise HTTPException(status_code=404, detail="키워드를 찾을 수 없습니다")
    conn.execute("DELETE FROM memo_document_categories WHERE category_id=?", (category_id,))
    conn.execute("UPDATE memo_documents SET category_id=NULL,updated_at=? WHERE username=? AND category_id=?", (_now(), user["username"], category_id))
    conn.execute("DELETE FROM memo_categories WHERE id=? AND username=?", (category_id, user["username"]))
    conn.commit(); conn.close(); return {"ok": True}


@app.put("/api/me/memos/{memo_id}/category")
def assign_memo_category(memo_id: int, body: MemoCategoryAssign, request: Request):
    user = _memo_user(request); conn = get_conn()
    owned = conn.execute("SELECT 1 FROM memo_documents WHERE id=? AND username=?", (memo_id, user["username"])).fetchone()
    if not owned: conn.close(); raise HTTPException(status_code=404, detail="메모를 찾을 수 없습니다")
    requested = body.category_ids if body.category_ids is not None else ([] if body.category_id is None else [body.category_id])
    category_ids = list(dict.fromkeys(int(value) for value in requested))
    if category_ids:
        placeholders = ",".join("?" for _ in category_ids)
        count = conn.execute(
            f"SELECT COUNT(*) AS n FROM memo_categories WHERE username=? AND id IN ({placeholders})",
            (user["username"], *category_ids),
        ).fetchone()["n"]
        if count != len(category_ids): conn.close(); raise HTTPException(status_code=400, detail="선택한 키워드가 올바르지 않습니다")
    now = _now()
    conn.execute("DELETE FROM memo_document_categories WHERE memo_id=?", (memo_id,))
    conn.executemany(
        "INSERT INTO memo_document_categories(memo_id,category_id,created_at) VALUES(?,?,?)",
        [(memo_id, category_id, now) for category_id in category_ids],
    )
    conn.execute(
        "UPDATE memo_documents SET category_id=?,updated_at=? WHERE id=? AND username=?",
        (category_ids[0] if category_ids else None, now, memo_id, user["username"]),
    ); conn.commit(); conn.close()
    return {"ok": True, "category_ids": category_ids}


@app.post("/api/me/memos")
def create_memo(body: MemoDocumentCreate, request: Request):
    user = _memo_user(request)
    title, note = body.title.strip(), body.note.strip()
    if not title or len(title) > 160 or len(note) > 12000:
        raise HTTPException(status_code=400, detail="제목은 1~160자, 메모는 12000자 이하로 입력하세요")
    now = _now(); conn = get_conn()
    requested = body.category_ids if body.category_ids is not None else ([] if body.category_id is None else [body.category_id])
    category_ids = list(dict.fromkeys(int(value) for value in requested))
    if category_ids:
        placeholders = ",".join("?" for _ in category_ids)
        count = conn.execute(
            f"SELECT COUNT(*) AS n FROM memo_categories WHERE username=? AND id IN ({placeholders})",
            (user["username"], *category_ids),
        ).fetchone()["n"]
        if count != len(category_ids): conn.close(); raise HTTPException(status_code=400, detail="선택한 키워드가 올바르지 않습니다")
    cursor = conn.execute(
        "INSERT INTO memo_documents(username,title,note,card_width,category_id,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
        (user["username"], title, note, 620, category_ids[0] if category_ids else None, now, now),
    )
    memo_id = cursor.lastrowid
    conn.executemany(
        "INSERT INTO memo_document_categories(memo_id,category_id,created_at) VALUES(?,?,?)",
        [(memo_id, category_id, now) for category_id in category_ids],
    )
    conn.commit(); conn.close()
    return {"ok": True, "id": memo_id}


@app.post("/api/me/memos/from-message/{message_id}")
def create_memo_from_message(message_id: int, request: Request):
    user = _memo_user(request); conn = get_conn()
    message = conn.execute(
        "SELECT id,room_id,sender,content,created_at FROM messages WHERE id=?", (message_id,)
    ).fetchone()
    if not message:
        conn.close(); raise HTTPException(status_code=404, detail="메시지를 찾을 수 없습니다")
    _ensure_message_visible(conn, message, user["username"], bool(user["is_owner"]))
    existing = conn.execute(
        "SELECT id FROM memo_documents WHERE username=? AND source_message_id=?",
        (user["username"], message_id),
    ).fetchone()
    now = _now()
    if existing:
        conn.execute(
            "UPDATE memo_documents SET source_content=?,source_sender=?,source_room_id=?,updated_at=? WHERE id=?",
            (message["content"], message["sender"], message["room_id"], now, existing["id"]),
        )
        memo_id, created = existing["id"], False
    else:
        preview = re.sub(r"\s+", " ", message["content"]).strip()[:36]
        title = f"{message['sender']} · {preview}" if preview else f"{message['sender']}의 메시지"
        cursor = conn.execute(
            """INSERT INTO memo_documents
               (username,source_message_id,source_room_id,source_sender,source_content,title,note,card_width,created_at,updated_at)
               VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (user["username"], message_id, message["room_id"], message["sender"], message["content"], title, "", 620, now, now),
        )
        memo_id, created = cursor.lastrowid, True
    conn.commit(); conn.close()
    return {"ok": True, "id": memo_id, "created": created}


@app.get("/api/me/memos/from-message/{message_id}/open")
def create_memo_from_message_and_open(message_id: int, request: Request):
    """관련 채팅 메시지를 마인드맵 루트로 저장하고 해당 메모를 바로 연다."""
    result = create_memo_from_message(message_id, request)
    return RedirectResponse(f"/memo/?memo={result['id']}", status_code=303)


@app.put("/api/me/memos/{memo_id}")
def update_memo(memo_id: int, body: MemoDocumentUpdate, request: Request):
    user = _memo_user(request); title, note = body.title.strip(), body.note.strip()
    if not title or len(title) > 160 or len(note) > 12000:
        raise HTTPException(status_code=400, detail="제목은 1~160자, 메모는 12000자 이하로 입력하세요")
    card_width = body.card_width if body.card_width is None else max(220, min(720, body.card_width))
    conn = get_conn()
    if card_width is None:
        cursor = conn.execute(
            "UPDATE memo_documents SET title=?,note=?,updated_at=? WHERE id=? AND username=?",
            (title, note, _now(), memo_id, user["username"]),
        )
    else:
        cursor = conn.execute(
            "UPDATE memo_documents SET title=?,note=?,card_width=?,updated_at=? WHERE id=? AND username=?",
            (title, note, card_width, _now(), memo_id, user["username"]),
        )
    conn.commit(); conn.close()
    if not cursor.rowcount: raise HTTPException(status_code=404, detail="메모를 찾을 수 없습니다")
    return {"ok": True}


@app.delete("/api/me/memos/{memo_id}")
def delete_memo(memo_id: int, request: Request):
    user = _memo_user(request); conn = get_conn()
    owned = conn.execute("SELECT 1 FROM memo_documents WHERE id=? AND username=?", (memo_id, user["username"])).fetchone()
    if not owned: conn.close(); raise HTTPException(status_code=404, detail="메모를 찾을 수 없습니다")
    conn.execute("DELETE FROM memo_nodes WHERE memo_id=?", (memo_id,))
    conn.execute("DELETE FROM memo_document_categories WHERE memo_id=?", (memo_id,))
    conn.execute("DELETE FROM memo_documents WHERE id=?", (memo_id,)); conn.commit(); conn.close()
    return {"ok": True}


@app.post("/api/me/memos/{memo_id}/nodes")
def create_memo_node(memo_id: int, body: MemoNodeCreate, request: Request):
    user = _memo_user(request); content = body.content.strip()
    if len(content) > 6000: raise HTTPException(status_code=400, detail="파생 메모는 6000자 이하로 입력하세요")
    image_data, drawing_data = _validate_memo_media(body.image_data, body.drawing_data)
    conn = get_conn(); owned = conn.execute("SELECT 1 FROM memo_documents WHERE id=? AND username=?", (memo_id, user["username"])).fetchone()
    if not owned: conn.close(); raise HTTPException(status_code=404, detail="메모를 찾을 수 없습니다")
    if body.parent_id is not None and not conn.execute("SELECT 1 FROM memo_nodes WHERE id=? AND memo_id=?", (body.parent_id, memo_id)).fetchone():
        conn.close(); raise HTTPException(status_code=400, detail="상위 메모가 올바르지 않습니다")
    order = conn.execute("SELECT COALESCE(MAX(sort_order),-1)+1 AS n FROM memo_nodes WHERE memo_id=? AND parent_id IS ?", (memo_id, body.parent_id)).fetchone()["n"]
    position_x = body.position_x if body.position_x is None else max(100, min(2300, body.position_x))
    position_y = body.position_y if body.position_y is None else max(80, min(1720, body.position_y))
    card_width = max(220, min(720, body.card_width or 620))
    now = _now(); cursor = conn.execute(
        "INSERT INTO memo_nodes(memo_id,parent_id,content,sort_order,position_x,position_y,card_width,image_data,drawing_data,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
        (memo_id, body.parent_id, content, order, position_x, position_y, card_width, image_data, drawing_data, now, now),
    ); conn.execute("UPDATE memo_documents SET updated_at=? WHERE id=?", (now, memo_id)); conn.commit(); node_id = cursor.lastrowid; conn.close()
    return {"ok": True, "id": node_id}


@app.put("/api/me/memo-nodes/{node_id}")
def update_memo_node(node_id: int, body: MemoNodeUpdate, request: Request):
    user = _memo_user(request); content = body.content.strip()
    if len(content) > 6000: raise HTTPException(status_code=400, detail="파생 메모는 6000자 이하로 입력하세요")
    conn = get_conn(); row = conn.execute("""SELECT n.memo_id FROM memo_nodes n JOIN memo_documents m ON m.id=n.memo_id
        WHERE n.id=? AND m.username=?""", (node_id, user["username"])).fetchone()
    if not row: conn.close(); raise HTTPException(status_code=404, detail="파생 메모를 찾을 수 없습니다")
    now = _now()
    fields, values = ["content=?"], [content]
    if body.position_x is not None and body.position_y is not None:
        fields.extend(["position_x=?", "position_y=?"])
        values.extend([max(100, min(2300, body.position_x)), max(80, min(1720, body.position_y))])
    if body.card_width is not None:
        fields.append("card_width=?")
        values.append(max(220, min(720, body.card_width)))
    if body.image_data is not None or body.drawing_data is not None:
        image_data, drawing_data = _validate_memo_media(body.image_data or "", body.drawing_data or "")
        if body.image_data is not None:
            fields.append("image_data=?"); values.append(image_data)
        if body.drawing_data is not None:
            fields.append("drawing_data=?"); values.append(drawing_data)
    fields.append("updated_at=?"); values.extend([now, node_id])
    conn.execute(f"UPDATE memo_nodes SET {','.join(fields)} WHERE id=?", values)
    conn.execute("UPDATE memo_documents SET updated_at=? WHERE id=?", (now, row["memo_id"])); conn.commit(); conn.close()
    return {"ok": True}


@app.delete("/api/me/memo-nodes/{node_id}")
def delete_memo_node(node_id: int, request: Request):
    user = _memo_user(request); conn = get_conn()
    row = conn.execute("""SELECT n.memo_id FROM memo_nodes n JOIN memo_documents m ON m.id=n.memo_id
        WHERE n.id=? AND m.username=?""", (node_id, user["username"])).fetchone()
    if not row: conn.close(); raise HTTPException(status_code=404, detail="파생 메모를 찾을 수 없습니다")
    ids = [r["id"] for r in conn.execute("""WITH RECURSIVE subtree(id) AS (
        SELECT id FROM memo_nodes WHERE id=? UNION ALL
        SELECT n.id FROM memo_nodes n JOIN subtree s ON n.parent_id=s.id)
        SELECT id FROM subtree""", (node_id,)).fetchall()]
    conn.execute(f"DELETE FROM memo_nodes WHERE id IN ({','.join('?' for _ in ids)})", ids)
    conn.execute("UPDATE memo_documents SET updated_at=? WHERE id=?", (_now(), row["memo_id"])); conn.commit(); conn.close()
    return {"ok": True, "deleted": len(ids)}


@app.get("/api/jp-vocabulary")
def jp_vocabulary(request: Request):
    """★ 2026-09-18: "일본어선생님이 메시지로 말하는 말에서도 일본어
    어휘도 팝오버 되는 기능이 있으면 좋을거같은데" 요청 — 처리된 모든
    회차의 학습 단어(vocabulary)를 한 번에 돌려준다. 채팅 메시지는
    어느 회차를 언급할지 미리 알 수 없으므로, 프론트가 이 목록 전체와
    대조해 정확히 일치하는 단어만 강조·클릭 가능하게 만든다."""
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다")
    return dating_sim_story.load_all_jp_vocabulary()


@app.get("/api/me/japanese-kanji-favorites")
def list_japanese_kanji_favorites(request: Request):
    """로그인 계정에 저장된 일본어 한자 단어장을 최신 저장 순으로 돌려준다."""
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다")
    conn = get_conn()
    rows = conn.execute(
        "SELECT character, created_at FROM japanese_kanji_favorites "
        "WHERE username = ? ORDER BY created_at DESC, character",
        (user["username"],),
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


@app.put("/api/me/japanese-kanji-favorites/{character}")
def add_japanese_kanji_favorite(character: str, request: Request):
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다")
    if not JAPANESE_KANJI_RE.fullmatch(character):
        raise HTTPException(status_code=400, detail="한 글자의 한자만 저장할 수 있습니다")
    conn = get_conn()
    conn.execute(
        "INSERT OR IGNORE INTO japanese_kanji_favorites (username, character, created_at) VALUES (?, ?, ?)",
        (user["username"], character, _now()),
    )
    conn.commit()
    conn.close()
    return {"ok": True, "character": character, "is_favorite": True}


@app.delete("/api/me/japanese-kanji-favorites/{character}")
def remove_japanese_kanji_favorite(character: str, request: Request):
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다")
    if not JAPANESE_KANJI_RE.fullmatch(character):
        raise HTTPException(status_code=400, detail="한 글자의 한자만 삭제할 수 있습니다")
    conn = get_conn()
    conn.execute(
        "DELETE FROM japanese_kanji_favorites WHERE username = ? AND character = ?",
        (user["username"], character),
    )
    conn.commit()
    conn.close()
    return {"ok": True, "character": character, "is_favorite": False}


class MyProfileUpdate(BaseModel):
    display_name: str


class AiProviderKeyUpdate(BaseModel):
    provider: str
    api_key: str


class AiProviderSelect(BaseModel):
    provider: Optional[str] = None


class PersonalAiFallbackRequest(BaseModel):
    turn_id: int
    reason: Optional[str] = None


def _current_user(request):
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다")
    return user


@app.get("/api/me/ai-runtime-status")
def get_my_ai_runtime_status(request: Request):
    """공유 AI의 회로 차단 상태를 민감정보 없이 반환한다.

    원본 오류·요청 ID·로컬 경로는 브라우저에 노출하지 않는다. 사용자는 왜
    답변이 대기 중인지와 언제 다시 시도되는지만 확인하면 된다.
    """
    _current_user(request)
    now = time.time()
    raw = circuit_status()
    providers = {}
    for provider, item in raw.get("providers", {}).items():
        open_until = float(item.get("open_until") or 0)
        providers[provider] = {
            "blocked": open_until > now,
            "error_type": item.get("error_type") or None,
            "retry_at": datetime.datetime.fromtimestamp(open_until).isoformat() if open_until else None,
            "retry_in_seconds": max(0, int(open_until - now)),
            "consecutive_failures": int(item.get("consecutive_failures") or 0),
            "last_job": item.get("last_job") or None,
        }
    return {
        "providers": providers,
        "automation_deferred": now - float(raw.get("last_interactive_at") or 0) < 5 * 60,
    }


@app.get("/api/me/ai-providers")
def get_my_ai_providers(request: Request):
    user = _current_user(request)
    conn = get_conn()
    selected = conn.execute(
        "SELECT ai_provider FROM users WHERE username = ?", (user["username"],)
    ).fetchone()
    rows = conn.execute(
        "SELECT provider, key_hint, updated_at FROM user_ai_credentials WHERE username = ?",
        (user["username"],),
    ).fetchall()
    conn.close()
    configured = {r["provider"]: {"hint": r["key_hint"], "updated_at": r["updated_at"]} for r in rows}
    return {
        "selected_provider": selected["ai_provider"] if selected else None,
        "providers": [
            {"id": provider, "configured": provider in configured, **configured.get(provider, {})}
            for provider in ai_keys.PROVIDERS
        ],
    }


@app.get("/api/me/ai-fallback-request")
def get_my_ai_fallback_request(request: Request):
    """관리자 AI가 실패한 턴 중 로그인한 본인의 요청만 보여준다."""
    user = _current_user(request)
    conn = get_conn()
    row = conn.execute(
        """SELECT afr.id, afr.room_id, afr.turn_id, afr.persona_name, afr.created_at,
                  EXISTS(
                    SELECT 1 FROM users u JOIN user_ai_credentials c
                      ON c.username=u.username AND c.provider=u.ai_provider
                    WHERE u.username=afr.username
                  ) AS configured
           FROM ai_fallback_requests afr
           WHERE afr.username=? AND afr.status='pending'
           ORDER BY afr.id LIMIT 1""",
        (user["username"],),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


@app.post("/api/me/ai-fallback-request/{request_id}/retry")
def retry_my_ai_fallback_request(request_id: int, request: Request):
    """개인 키가 등록된 경우에만 해당 사용자의 중단된 턴을 재개한다."""
    user = _current_user(request)
    conn = get_conn()
    row = conn.execute(
        """SELECT afr.turn_id FROM ai_fallback_requests afr
           JOIN users u ON u.username=afr.username
           JOIN user_ai_credentials c
             ON c.username=u.username AND c.provider=u.ai_provider
           WHERE afr.id=? AND afr.username=? AND afr.status='pending'""",
        (request_id, user["username"]),
    ).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=400, detail="선택한 개인 API 키를 먼저 등록하세요")
    now = _now()
    conn.execute(
        "UPDATE ai_fallback_requests SET status='retrying' WHERE id=?", (request_id,)
    )
    conn.execute(
        """UPDATE pending_turns
           SET status='pending', started_at=NULL, error=NULL, completed_at=NULL,
               use_personal_ai=1
           WHERE id=?""",
        (row["turn_id"],),
    )
    conn.commit()
    conn.close()
    return {"ok": True}


@app.post("/api/me/ai-fallback-request/{request_id}/dismiss")
def dismiss_my_ai_fallback_request(request_id: int, request: Request):
    user = _current_user(request)
    conn = get_conn()
    row = conn.execute(
        "SELECT turn_id FROM ai_fallback_requests WHERE id=? AND username=? AND status='pending'",
        (request_id, user["username"]),
    ).fetchone()
    if row:
        conn.execute(
            "UPDATE ai_fallback_requests SET status='dismissed', resolved_at=? WHERE id=?",
            (_now(), request_id),
        )
        conn.execute(
            "UPDATE pending_turns SET status='failed', error='personal_api_declined', completed_at=? WHERE id=?",
            (_now(), row["turn_id"]),
        )
        conn.commit()
    conn.close()
    return {"ok": True}


@app.put("/api/me/ai-providers/key")
def save_my_ai_provider_key(body: AiProviderKeyUpdate, request: Request):
    user = _current_user(request)
    provider = body.provider.strip().lower()
    key = body.api_key.strip()
    if provider not in ai_keys.PROVIDERS:
        raise HTTPException(status_code=400, detail="지원하지 않는 AI 공급자입니다")
    if not (10 <= len(key) <= 500) or any(ch.isspace() for ch in key):
        raise HTTPException(status_code=400, detail="API 키 형식을 확인하세요")
    encrypted = ai_keys.encrypt_key(key)
    conn = get_conn()
    conn.execute(
        """INSERT INTO user_ai_credentials(username,provider,encrypted_key,key_hint,updated_at)
           VALUES (?,?,?,?,?) ON CONFLICT(username,provider) DO UPDATE SET
           encrypted_key=excluded.encrypted_key,key_hint=excluded.key_hint,updated_at=excluded.updated_at""",
        (user["username"], provider, encrypted, ai_keys.key_hint(key), _now()),
    )
    current = conn.execute("SELECT ai_provider FROM users WHERE username=?", (user["username"],)).fetchone()
    if not current or not current["ai_provider"]:
        conn.execute("UPDATE users SET ai_provider=? WHERE username=?", (provider, user["username"]))
    conn.commit()
    conn.close()
    return {"ok": True, "provider": provider, "hint": ai_keys.key_hint(key)}


@app.delete("/api/me/ai-providers/{provider}")
def delete_my_ai_provider_key(provider: str, request: Request):
    user = _current_user(request)
    if provider not in ai_keys.PROVIDERS:
        raise HTTPException(status_code=400, detail="지원하지 않는 AI 공급자입니다")
    conn = get_conn()
    conn.execute("DELETE FROM user_ai_credentials WHERE username=? AND provider=?", (user["username"], provider))
    conn.execute(
        "UPDATE users SET ai_provider=NULL WHERE username=? AND ai_provider=?", (user["username"], provider)
    )
    conn.commit()
    conn.close()
    return {"ok": True}


@app.put("/api/me/ai-providers/selected")
def select_my_ai_provider(body: AiProviderSelect, request: Request):
    user = _current_user(request)
    provider = body.provider.strip().lower() if body.provider else None
    conn = get_conn()
    if provider:
        if provider not in ai_keys.PROVIDERS:
            conn.close()
            raise HTTPException(status_code=400, detail="지원하지 않는 AI 공급자입니다")
        exists = conn.execute(
            "SELECT 1 FROM user_ai_credentials WHERE username=? AND provider=?", (user["username"], provider)
        ).fetchone()
        if not exists:
            conn.close()
            raise HTTPException(status_code=400, detail="먼저 이 공급자의 API 키를 등록하세요")
    conn.execute("UPDATE users SET ai_provider=? WHERE username=?", (provider, user["username"]))
    conn.commit()
    conn.close()
    return {"ok": True, "selected_provider": provider}


@app.post("/api/me/ai-providers/{provider}/test")
def test_my_ai_provider(provider: str, request: Request):
    user = _current_user(request)
    if provider not in ai_keys.PROVIDERS:
        raise HTTPException(status_code=400, detail="지원하지 않는 AI 공급자입니다")
    conn = get_conn()
    row = conn.execute(
        "SELECT encrypted_key FROM user_ai_credentials WHERE username=? AND provider=?",
        (user["username"], provider),
    ).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="등록된 API 키가 없습니다")
    try:
        ai_keys.test_provider(provider, ai_keys.decrypt_key(row["encrypted_key"]))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "provider": provider}


@app.put("/api/me")
def update_my_profile(body: MyProfileUpdate, request: Request):
    """★ "카톡이나 구글로 로그인한 사람은 자기 이름 수정할 수 있게, 다른
    일반 사용자도 마찬가지로" 요청(2026-08-28) — 로그인한 계정이면 누구나
    (소유자 여부·가입 방식과 무관하게) 자기 표시 이름을 바꿀 수 있다.
    username(로그인 아이디)은 안 바뀐다 — 화면에 보이는 이름만."""
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다")
    name = body.display_name.strip()
    if not (1 <= len(name) <= 30):
        raise HTTPException(status_code=400, detail="이름은 1~30자로 입력하세요")
    conn = get_conn()
    conn.execute("UPDATE users SET display_name = ? WHERE username = ?", (name, user["username"]))
    conn.commit()
    conn.close()
    return {"ok": True, "display_name": name}


@app.post("/api/me/avatar")
async def upload_my_avatar(request: Request, file: UploadFile = File(...)):
    """내 프로필 사진 변경 — 저장·검증 로직은 /api/upload와 동일(같은
    UPLOADS_DIR·확장자·용량 제한 재사용, /api/admin/personas/{name}/avatar와
    같은 패턴)."""
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다")
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_UPLOAD_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"지원하지 않는 이미지 형식입니다: {ext or '(확장자 없음)'}")
    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="이미지가 너무 큽니다(10MB 제한)")
    filename = f"user_{uuid.uuid4().hex}{ext}"
    (UPLOADS_DIR / filename).write_bytes(data)
    url = f"/uploads/{filename}"
    conn = get_conn()
    conn.execute("UPDATE users SET avatar_url = ? WHERE username = ?", (url, user["username"]))
    conn.commit()
    conn.close()
    return {"ok": True, "avatar_url": url}


@app.delete("/api/me/avatar")
def delete_my_avatar(request: Request):
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다")
    conn = get_conn()
    conn.execute("UPDATE users SET avatar_url = NULL WHERE username = ?", (user["username"],))
    conn.commit()
    conn.close()
    return {"ok": True}


@app.get("/api/persona_profiles")
def list_persona_profiles(request: Request):
    """"툴파들의 성격을 간단히 확인할 수 있는 페이지" 요청(2026-08-26) —
    공개 페르소나(Notion 동기화분) 전부 + 내가 만든 개인 페르소나만 보여준다
    (다른 사람의 개인 페르소나는 그 사람 1:1 방처럼 비공개 유지).

    ★ "권민석 프로필설정이 너무 적나라한데 일반 사용자도 다 보이는 거야?
    실제 친군데 실친이 들어와서 봤을 때 오해의 소지가 있을 것 같다" 요청
    (2026-08-28) — 관리자가 만든 페르소나(owner_username=NULL)는 실제
    지인을 본뜬 경우가 많아 기본적으로 관리자만 프로필을 본다.
    persona_view_grants에 명시적으로 등록된 사용자만 예외."""
    user = getattr(request.state, "user", None)
    username = user["username"] if user else None
    is_owner_request = bool(user and user["is_owner"])
    conn = get_conn()
    rows = conn.execute(
        """SELECT name, owner_username, description, profile_summary, avatar_url,
                  gender, age_range, voice_openai, voice_edge
             FROM personas ORDER BY name"""
    ).fetchall()
    granted = {
        r["persona_name"] for r in conn.execute(
            "SELECT persona_name FROM persona_view_grants WHERE username = ?", (username,)
        ).fetchall()
    } if username else set()
    conn.close()
    result = []
    for r in rows:
        if r["owner_username"] is not None:
            if r["owner_username"] != username and not is_owner_request:
                continue
        elif not is_owner_request and r["name"] not in granted:
            continue
        summary = r["profile_summary"] or r["description"] or "(아직 프로필 정보가 없습니다)"
        result.append({
            "name": r["name"],
            "is_mine": bool(username) and r["owner_username"] == username,
            "summary": summary,
            "avatar_url": r["avatar_url"],
            # ★ "성별/나이대 설정, AI가 판단한 목소리 음색설정도 프로필에서
            # 보이면 좋겠다" 요청(2026-08-30).
            "gender": r["gender"],
            "age_range": r["age_range"],
            "voice_openai": r["voice_openai"],
            "voice_edge": r["voice_edge"],
        })
    return result


def _given_name(persona_name):
    """"한경호 선생님" → "경호", "박정민" → "정민"처럼 성(1글자)과 뒤에 붙는
    호칭(선생님 등)을 뗀 "부르는 이름"만 뽑는다. 2026-08-26: "정민씨", "경호쌤"
    처럼 자연스럽게 이름만 불렀는데 전원이 다 대답하는 문제 — @정확한 전체
    이름만 인식하던 걸 이걸로 보강한다."""
    first_word = persona_name.split()[0]
    return first_word[1:] if len(first_word) >= 3 else first_word


def _last_persona_speaker(conn, room_id, candidates):
    if not candidates:
        return None
    placeholders = ",".join("?" * len(candidates))
    row = conn.execute(
        f"SELECT sender FROM messages WHERE room_id = ? AND sender IN ({placeholders}) ORDER BY id DESC LIMIT 1",
        (room_id, *candidates),
    ).fetchone()
    return row["sender"] if row else None


_BROADCAST_INVITE_RE = re.compile(r"다른\s*(분|사람|병법가)|다들|여러분")


def _is_broadcast_invite(content):
    """"다른분들은 할말 없으십니까", "매요신님 같은 다른 병법가들도 말씀해
    보시지요"처럼, 특정 한 명이 아니라 방에 있는 여러/전원에게 발언을
    요청하는 문구인지 본다. ★ 2026-08-26: 이런 문구를 쓴 뒤에도 직전
    발화자나 문장 속에 걸린 이름 한 명만 계속 대답해서 "다른 사람들은
    말을 안 한다"는 버그 신고 — 이 경우엔 전원에게 보낸다."""
    return bool(_BROADCAST_INVITE_RE.search(content))


def _default_targets(conn, room_id, candidates, mentioned, reply_to, content=""):
    """이름/호칭으로 아무도 안 지목했을 때 누구에게 보낼지 정한다.

    ★ 2026-08-26: "너 솔직히 말해봐"처럼 대명사로만 말하면 방에 있는 페르소나
    전원이 반응해서 대화가 이상하게 흘러가는 문제 — 이전엔 "멘션 없으면
    전원 응답"이었는데, 그 방에서 누군가 이미 말을 섞고 있었다면(직전 발화자가
    있다면) 자연스러운 대화 흐름상 그 사람에게 이어서 말하는 것으로 보고
    그 한 명에게만 보낸다. 아직 아무도 말을 안 한 방(막 만들었거나 막
    초대한 직후)에서는 기존처럼 전원이 한 번씩 반응해 "인사 라운드"를 연다.

    ★ 2026-08-26: "다른 분들은 할 말 없으십니까", "매요신님 같은 다른
    병법가들도"처럼 여러/전원에게 말을 거는 문구는 위 "직전 발화자 1인에게만
    이어짐"/"멘션된 1명만" 규칙보다 우선한다 — 명시적으로 여러 명을 부른
    것이므로 전원에게 보낸다."""
    if reply_to and reply_to in candidates:
        return [reply_to]
    if _is_broadcast_invite(content):
        return candidates
    if mentioned:
        return mentioned
    last_speaker = _last_persona_speaker(conn, room_id, candidates)
    return [last_speaker] if last_speaker else candidates


def _mentioned_personas(content, candidates):
    """@정확한 이름 또는 "이름씨"/"이름쌤"/"이름아" 같은 자연스러운 호칭까지
    잡아서 지목된 페르소나를 찾는다. 아무도 안 걸리면 빈 리스트(전원 응답)."""
    mentioned = []
    for name in candidates:
        given = _given_name(name)
        compact_name = name.replace(" ", "")
        compact_content = content.replace(" ", "")
        # 영문 역할 접두사가 붙은 이름은 한국어 본체도 자연스러운 별칭으로
        # 인정한다. 예: QA요정 → “요정”, “QA 요정”, “QA요정”.
        role_alias = name[2:] if name.startswith("QA") else ""
        if (
            f"@{name}" in content
            or compact_name in compact_content
            or (len(given) >= 2 and given in content)
            or (len(role_alias) >= 2 and role_alias in content)
        ):
            mentioned.append(name)
    return mentioned


def _group_members(conn, room_id, persona_rows):
    """그룹 회의방의 실제 참여자 = Notion "그룹" 필드가 이 방과 같은
    페르소나(기본 멤버) + 이 방에 초대된 페르소나(room_invites, 2026-08-25
    "프로젝트하다가 관련 인물 추가하는 식으로 초대하고 싶다" 요청). 순서는
    기본 멤버 먼저, dict.fromkeys로 중복 제거."""
    excluded = {
        row["persona_name"] for row in conn.execute(
            "SELECT persona_name FROM room_persona_exclusions WHERE room_id = ?", (room_id,)
        ).fetchall()
    }
    base = [r["name"] for r in persona_rows if r["group_name"] == room_id and r["name"] not in excluded]
    invited = [
        row["persona_name"] for row in conn.execute(
            "SELECT persona_name FROM room_invites WHERE room_id = ?", (room_id,)
        ).fetchall()
    ]
    return list(dict.fromkeys(base + invited))


def _custom_room_access(conn, room_id, username, is_owner_request):
    """room_id가 사용자 커스텀 방이면 (그 방인지 여부, 접근 가능 여부, 방
    소유 계정)을 반환한다. Notion 그룹 회의방이면 (False, True, None) —
    그쪽은 기존처럼 로그인만 하면 누구나 볼 수 있다(단, 초대는 아래에서
    소유자로 별도 제한).

    ★ "가상 인물뿐만 아니라 실제 사용자도 초대할 수 있게 해달라" 요청
    (2026-08-27) — 방 주인·소유자 외에도 room_user_invites에 초대된
    계정이면 접근(읽기·쓰기)을 허용한다."""
    row = conn.execute("SELECT owner_username FROM custom_rooms WHERE room_id = ?", (room_id,)).fetchone()
    if not row:
        return False, True, None
    public_room = conn.execute(
        "SELECT 1 FROM custom_rooms WHERE room_id=? AND label='손자병법 토론방'", (room_id,)
    ).fetchone()
    allowed = bool(username and public_room) or is_owner_request or row["owner_username"] == username
    if not allowed and username:
        invited = conn.execute(
            "SELECT 1 FROM room_user_invites WHERE room_id = ? AND username = ?", (room_id, username)
        ).fetchone()
        allowed = bool(invited)
    return True, allowed, row["owner_username"]


def _promote_direct_room(conn, room_id):
    """1:1 방에 세 번째 구성원이 추가되면 중복 방 키를 해제하고 그룹 표시로 바꾼다."""
    row = conn.execute(
        "SELECT label, direct_key FROM custom_rooms WHERE room_id=?", (room_id,)
    ).fetchone()
    if row and row["direct_key"]:
        conn.execute(
            "UPDATE custom_rooms SET direct_key=NULL, label=? WHERE room_id=?",
            (f"{row['label']} 외 그룹", room_id),
        )


@app.get("/api/rooms/{room_id}/notice")
def get_room_notice(room_id: str, request: Request):
    """"카카오톡처럼 채팅방에 공지사항이 보였으면 좋겠다, 그 방 대화를 토대로
    업데이트 내용을 하루하루 요약해서 공지해달라"는 요청(2026-08-26). 워커가
    `sync_room_notices()`로 채워둔 최신 공지를 그대로 돌려준다 — 커스텀
    방이면 그 방 접근 권한과 동일하게 제한한다."""
    user = getattr(request.state, "user", None)
    username = user["username"] if user else None
    is_owner_request = user["is_owner"] if user else True
    conn = get_conn()
    is_custom, allowed, _room_owner = _custom_room_access(conn, room_id, username, is_owner_request)
    if is_custom and not allowed:
        conn.close()
        raise HTTPException(status_code=403, detail="이 채팅방 공지를 볼 수 없습니다")
    row = conn.execute("SELECT content, updated_at FROM room_notices WHERE room_id = ?", (room_id,)).fetchone()
    conn.close()
    if not row or not row["content"]:
        return None
    return {"content": row["content"], "updated_at": row["updated_at"]}


@app.get("/api/rooms/{room_id}/members")
def get_room_members(room_id: str, request: Request):
    """이 그룹 회의방의 현재 참여자 목록과, 아직 초대 안 된 나머지 페르소나
    목록을 같이 준다 — 프론트의 초대 패널이 "누굴 더 부를 수 있는지" 보여줄 때 씀.

    ★ 2026-08-26: "단체톡방 만들기 + 초대" 요청으로 사용자 커스텀 방도 지원.
    커스텀 방은 방 주인 + 소유자만 조회 가능, 일반 사용자의 초대 후보는 공개
    페르소나(Notion) + 그 방 주인이 직접 만든 페르소나로 제한한다. 관리자는
    전체 페르소나 관리 권한과 일치하도록 다른 계정의 개인 페르소나도 후보로
    볼 수 있다."""
    user = getattr(request.state, "user", None)
    username = user["username"] if user else None
    is_owner_request = user["is_owner"] if user else True
    conn = get_conn()
    is_custom, allowed, room_owner = _custom_room_access(conn, room_id, username, is_owner_request)
    if is_custom and not allowed:
        conn.close()
        raise HTTPException(status_code=403, detail="이 채팅방에 접근할 수 없습니다")
    persona_rows = conn.execute("SELECT name, group_name, owner_username FROM personas ORDER BY name").fetchall()
    members = _group_members(conn, room_id, persona_rows)
    conn.close()
    if is_owner_request:
        candidates = [r["name"] for r in persona_rows]
    elif is_custom:
        candidates = [r["name"] for r in persona_rows if r["owner_username"] is None or r["owner_username"] == room_owner]
    else:
        candidates = [r["name"] for r in persona_rows if r["owner_username"] is None]
    available = [n for n in candidates if n not in members]
    return {"members": members, "available": available}


class InviteRequest(BaseModel):
    persona_name: str


@app.post("/api/rooms/{room_id}/invite")
def invite_to_room(room_id: str, body: InviteRequest, request: Request):
    if not getattr(request.state, "can_write", True):
        raise HTTPException(status_code=403, detail="읽기 전용 계정입니다")
    user = getattr(request.state, "user", None)
    username = user["username"] if user else None
    is_owner_request = user["is_owner"] if user else True
    conn = get_conn()
    is_custom, allowed, room_owner = _custom_room_access(conn, room_id, username, is_owner_request)
    if is_custom and not allowed:
        conn.close()
        raise HTTPException(status_code=403, detail="이 채팅방에 초대할 수 없습니다")
    persona_rows = conn.execute("SELECT name, group_name, owner_username FROM personas ORDER BY name").fetchall()
    persona_map = {r["name"]: r["owner_username"] for r in persona_rows}
    if body.persona_name not in persona_map:
        conn.close()
        raise HTTPException(status_code=404, detail="존재하지 않는 페르소나입니다")
    if is_custom:
        is_known_room = True
    else:
        is_known_room = any(r["group_name"] == room_id for r in persona_rows)
        if is_known_room and not is_owner_request:
            # ★ Notion 그룹 회의방(모두가 공유하는 방)에 누구든 다른 사람을
            # 부를 수 있으면 위험하니, 소유자만 초대할 수 있게 좁힌다.
            conn.close()
            raise HTTPException(status_code=403, detail="이 회의방은 소유자만 초대할 수 있습니다")
    if not is_known_room:
        conn.close()
        raise HTTPException(status_code=404, detail="그룹 회의방이 아닙니다")
    persona_owner = persona_map[body.persona_name]
    if persona_owner is not None and persona_owner != room_owner and not is_owner_request:
        conn.close()
        raise HTTPException(status_code=403, detail="이 페르소나는 초대할 수 없습니다")
    # 기본 그룹 멤버를 내보낸 뒤 다시 초대하는 경우 방별 제외 표시를 먼저
    # 해제해야 _group_members()에 즉시 복귀한다.
    restored = conn.execute(
        "DELETE FROM room_persona_exclusions WHERE room_id = ? AND persona_name = ?",
        (room_id, body.persona_name),
    ).rowcount
    cur = conn.execute(
        "INSERT OR IGNORE INTO room_invites (room_id, persona_name, invited_at) VALUES (?, ?, ?)",
        (room_id, body.persona_name, _now()),
    )
    if cur.rowcount or restored:  # 이미 있던 초대면(중복 클릭 등) 알림을 또 남기지 않는다
        _promote_direct_room(conn, room_id)
        _insert_system_notice(conn, room_id, f"{body.persona_name}님이 초대되었습니다")
    conn.commit()
    members = _group_members(conn, room_id, persona_rows)
    conn.close()
    return {"ok": True, "members": members}


@app.delete("/api/rooms/{room_id}/personas/{persona_name}")
def kick_room_persona(room_id: str, persona_name: str, request: Request):
    """방 주인 또는 관리자가 페르소나를 방에서 내보낸다.

    초대로 들어온 페르소나는 room_invites에서 제거하고, Notion 그룹 설정으로
    자동 포함되는 기본 멤버는 방별 제외 표에 기록해 다시 나타나지 않게 한다.
    페르소나 자체나 다른 방의 소속 설정은 변경하지 않는다.
    """
    if not getattr(request.state, "can_write", True):
        raise HTTPException(status_code=403, detail="읽기 전용 계정입니다")
    user = getattr(request.state, "user", None)
    requester = user["username"] if user else None
    is_owner_request = bool(user and user["is_owner"])
    conn = get_conn()
    allowed, _owner_username = _room_manage_context(conn, room_id, requester, is_owner_request)
    if not allowed:
        conn.close()
        raise HTTPException(status_code=403, detail="이 방의 주인이나 관리자만 내보낼 수 있습니다")
    persona = conn.execute(
        "SELECT name, group_name FROM personas WHERE name = ?", (persona_name,)
    ).fetchone()
    if not persona:
        conn.close()
        raise HTTPException(status_code=404, detail="존재하지 않는 페르소나입니다")
    invited = conn.execute(
        "SELECT 1 FROM room_invites WHERE room_id = ? AND persona_name = ?", (room_id, persona_name)
    ).fetchone()
    is_base_member = persona["group_name"] == room_id
    if not invited and not is_base_member:
        conn.close()
        raise HTTPException(status_code=404, detail="이 방의 페르소나가 아닙니다")
    conn.execute(
        "DELETE FROM room_invites WHERE room_id = ? AND persona_name = ?", (room_id, persona_name)
    )
    if is_base_member:
        conn.execute(
            "INSERT OR REPLACE INTO room_persona_exclusions(room_id, persona_name, excluded_at) VALUES (?, ?, ?)",
            (room_id, persona_name, _now()),
        )
    _insert_system_notice(conn, room_id, f"{persona_name}님이 방에서 내보내졌습니다")
    conn.commit()
    conn.close()
    return {"ok": True}


def _room_manage_context(conn, room_id, requester, is_owner_request):
    """방 멤버 관리(초대·조회·내보내기)에 필요한 공통 판단 — 커스텀 방과
    그룹 회의방 둘 다 지원한다("그룹 회의방에서 사람 초대하려는데 왜 목록에
    없지" 요청, 2026-08-28). 반환: (관리 가능한 방인가(존재+권한),
    owner_username — 그룹 회의방은 주인이 없어 None)."""
    row = conn.execute("SELECT owner_username FROM custom_rooms WHERE room_id = ?", (room_id,)).fetchone()
    if row:
        owner_username = row["owner_username"]
        return (is_owner_request or owner_username == requester), owner_username
    if _is_notion_group_room(conn, room_id):
        return is_owner_request, None
    return False, None


@app.get("/api/rooms/{room_id}/user_members")
def get_room_user_members(room_id: str, request: Request):
    """이 방에 초대된 실제 사용자 목록과, 초대 가능한 나머지 계정 목록을
    준다. ★ "가상 인물뿐만 아니라 실제 사용자도 초대할 수 있게 해달라"
    요청(2026-08-27) — 커스텀 방은 방 주인(또는 소유자)만 조회할 수 있다.
    그룹 회의방은 "방 주인"이 없는 콘텐츠라 관리자만 관리(조회·초대)할
    수 있다(_room_manage_context)."""
    user = getattr(request.state, "user", None)
    username = user["username"] if user else None
    is_owner_request = bool(user and user["is_owner"])
    conn = get_conn()
    allowed, owner_username = _room_manage_context(conn, room_id, username, is_owner_request)
    if not allowed:
        conn.close()
        raise HTTPException(status_code=403, detail="이 방을 관리할 권한이 없습니다")
    members = [
        r["username"] for r in conn.execute(
            "SELECT username FROM room_user_invites WHERE room_id = ?", (room_id,)
        ).fetchall()
    ]
    if owner_username and owner_username not in members:
        members.insert(0, owner_username)
    user_rows = conn.execute(
        "SELECT username, display_name FROM users ORDER BY username"
    ).fetchall()
    all_users = [r["username"] for r in user_rows]
    user_labels = {r["username"]: (r["display_name"] or r["username"]) for r in user_rows}
    available = [u for u in all_users if u not in members]
    conn.close()
    # ★ "관리자가 채팅방에서 내보내는 기능" 요청(2026-08-28) — 프론트가 방
    # 주인 칩에는 내보내기 버튼을 안 그리도록(방 주인은 내보낼 수 없음,
    # kick_room_member 참고) owner_username을 같이 내려준다. 그룹 회의방은
    # owner_username이 null이라 모든 칩에 내보내기 버튼이 붙는다.
    return {
        "members": members, "available": available, "owner_username": owner_username,
        "user_labels": user_labels,
    }


class InviteUserRequest(BaseModel):
    username: str


@app.post("/api/rooms/{room_id}/invite_user")
def invite_user_to_room(room_id: str, body: InviteUserRequest, request: Request):
    """실제 사용자를 방에 초대한다. ★ 2026-08-27 요청. 커스텀 방은 방 주인
    (또는 소유자)만, 그룹 회의방은 관리자만 초대할 수 있다
    (_room_manage_context) — 초대된 계정은 이후 이 방을 보고, 메시지도
    보낼 수 있다(_custom_room_access/_group_room_allowed가 room_user_invites도
    확인)."""
    if not getattr(request.state, "can_write", True):
        raise HTTPException(status_code=403, detail="읽기 전용 계정입니다")
    user = getattr(request.state, "user", None)
    username = user["username"] if user else None
    is_owner_request = bool(user and user["is_owner"])
    conn = get_conn()
    allowed, _owner_username = _room_manage_context(conn, room_id, username, is_owner_request)
    if not allowed:
        conn.close()
        raise HTTPException(status_code=403, detail="이 방에 초대할 권한이 없습니다")
    target = conn.execute("SELECT username FROM users WHERE username = ?", (body.username,)).fetchone()
    if not target:
        conn.close()
        raise HTTPException(status_code=404, detail="존재하지 않는 계정입니다")
    cur = conn.execute(
        "INSERT OR IGNORE INTO room_user_invites (room_id, username, invited_at) VALUES (?, ?, ?)",
        (room_id, body.username, _now()),
    )
    if cur.rowcount:  # 이미 초대돼 있었으면(중복 클릭 등) 알림을 또 남기지 않는다
        _promote_direct_room(conn, room_id)
        _insert_system_notice(conn, room_id, f"{body.username}님이 초대되었습니다")
    conn.commit()
    conn.close()
    return {"ok": True}


@app.delete("/api/rooms/{room_id}/members/{username}")
def kick_room_member(room_id: str, username: str, request: Request):
    """"관리자에게 채팅방에서 내보내는 기능이 있으면 좋겠다" 요청
    (2026-08-28). 본인이 스스로 나가는 leave_room과 달리, 대상이 원치
    않아도 관리자(전체) 또는 그 방 주인이 강제로 뺄 수 있다(커스텀 방).
    그룹 회의방은 주인이 없어 관리자만(_room_manage_context). 방 주인은
    room_user_invites에 아예 없으므로(get_room_user_members가 목록엔
    끼워 넣어 보여줄 뿐) 대상이 될 수 없다 — 방을 통째로 없애고 싶으면
    delete_room을 쓰라고 안내한다."""
    if not getattr(request.state, "can_write", True):
        raise HTTPException(status_code=403, detail="읽기 전용 계정입니다")
    user = getattr(request.state, "user", None)
    requester = user["username"] if user else None
    is_owner_request = bool(user and user["is_owner"])
    conn = get_conn()
    allowed, owner_username = _room_manage_context(conn, room_id, requester, is_owner_request)
    if not allowed:
        conn.close()
        raise HTTPException(status_code=403, detail="이 방의 주인이나 관리자만 내보낼 수 있습니다")
    if owner_username and username == owner_username:
        conn.close()
        raise HTTPException(status_code=400, detail="방 주인은 내보낼 수 없습니다 — 방 삭제를 사용하세요")
    cur = conn.execute(
        "DELETE FROM room_user_invites WHERE room_id = ? AND username = ?", (room_id, username)
    )
    if not cur.rowcount:
        conn.close()
        raise HTTPException(status_code=404, detail="이 방의 멤버가 아닙니다")
    _insert_system_notice(conn, room_id, f"{username}님이 방에서 내보내졌습니다")
    conn.commit()
    conn.close()
    return {"ok": True}


def _delete_custom_room(conn, room_id):
    """커스텀 방과 거기 딸린 데이터를 전부 지운다 — 나가기(방 주인이 자기
    방을 나가는 경우)와 관리자 강제 삭제가 이 함수를 공유한다. SQLite는
    이 프로젝트에서 PRAGMA foreign_keys를 켜지 않아서(server/db.py) 스키마의
    ON DELETE CASCADE가 실제로는 동작하지 않는다 — 관련 테이블을 전부
    손으로 나열해서 지워야 한다."""
    conn.execute("DELETE FROM custom_rooms WHERE room_id = ?", (room_id,))
    conn.execute("DELETE FROM messages WHERE room_id = ?", (room_id,))
    conn.execute("DELETE FROM pending_turns WHERE room_id = ?", (room_id,))
    conn.execute("DELETE FROM room_invites WHERE room_id = ?", (room_id,))
    conn.execute("DELETE FROM room_persona_exclusions WHERE room_id = ?", (room_id,))
    conn.execute("DELETE FROM room_user_invites WHERE room_id = ?", (room_id,))
    conn.execute("DELETE FROM room_notices WHERE room_id = ?", (room_id,))
    conn.execute("DELETE FROM room_restart_notice WHERE room_id = ?", (room_id,))


def _clear_persona_room(conn, room_id):
    """파생되는 페르소나 1:1 방은 페르소나 자체를 지우지 않고 대화만 비운다."""
    conn.execute("DELETE FROM messages WHERE room_id = ?", (room_id,))
    conn.execute("DELETE FROM pending_turns WHERE room_id = ?", (room_id,))
    conn.execute("DELETE FROM room_invites WHERE room_id = ?", (room_id,))
    conn.execute("DELETE FROM room_persona_exclusions WHERE room_id = ?", (room_id,))
    conn.execute("DELETE FROM room_notices WHERE room_id = ?", (room_id,))
    conn.execute("DELETE FROM room_restart_notice WHERE room_id = ?", (room_id,))
    conn.execute("DELETE FROM room_read_state WHERE room_id = ?", (room_id,))
    conn.execute("DELETE FROM user_room_backgrounds WHERE room_id = ?", (room_id,))


@app.post("/api/rooms/{room_id}/leave")
def leave_room(room_id: str, request: Request):
    """"채팅방 나가기 기능 있게 해달라" 요청(2026-08-28). 내가 만든 방이
    아니라 초대받아 들어간 방만 "나간다"(room_user_invites에서 내 행만
    지움 — 방은 다른 멤버에게 그대로 남는다). 내가 만든 방은 넘겨줄 다음
    주인이 없어서 "나가기"가 곧 "방 폐쇄"와 같다 — 그 경우엔 DELETE
    /api/rooms/{room_id}(관리자 강제 삭제와 같은 함수)를 쓰라고 안내한다."""
    if not getattr(request.state, "can_write", True):
        raise HTTPException(status_code=403, detail="읽기 전용 계정입니다")
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다")
    username = user["username"]
    conn = get_conn()
    row = conn.execute("SELECT owner_username FROM custom_rooms WHERE room_id = ?", (room_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="존재하지 않는 채팅방입니다")
    if row["owner_username"] == username:
        conn.close()
        raise HTTPException(status_code=400, detail="내가 만든 방은 나가기 대신 삭제를 사용하세요")
    cur = conn.execute(
        "DELETE FROM room_user_invites WHERE room_id = ? AND username = ?", (room_id, username)
    )
    if not cur.rowcount:
        conn.close()
        raise HTTPException(status_code=403, detail="이 채팅방의 멤버가 아닙니다")
    _insert_system_notice(conn, room_id, f"{username}님이 나갔습니다")
    conn.commit()
    conn.close()
    return {"ok": True}


def _delete_notion_group_room(conn, room_id):
    """Notion 그룹 회의방(커스텀 방과 달리 rooms 테이블에 행이 없고, 같은
    group_name을 쓰는 페르소나들로부터 파생되는 방)을 삭제한다. "방을 없앤다"는
    게 곧 소속 페르소나들의 그룹 지정을 전부 해제하는 것과 같다 — 그래야
    그 group_name으로 다시 방이 파생되지 않는다. _delete_custom_room과 같은
    수준으로 대화 기록·초대·공지·재시작 안내를 같이 지운다(room_invites·
    room_persona_exclusions·custom_rooms은 애초에 이 방 종류엔 없음)."""
    conn.execute(
        "UPDATE personas SET group_name = NULL, admin_group_name = NULL WHERE group_name = ?",
        (room_id,),
    )
    conn.execute("DELETE FROM messages WHERE room_id = ?", (room_id,))
    conn.execute("DELETE FROM pending_turns WHERE room_id = ?", (room_id,))
    conn.execute("DELETE FROM room_user_invites WHERE room_id = ?", (room_id,))
    conn.execute("DELETE FROM room_notices WHERE room_id = ?", (room_id,))
    conn.execute("DELETE FROM room_restart_notice WHERE room_id = ?", (room_id,))


@app.delete("/api/rooms/{room_id}")
def delete_room(room_id: str, request: Request):
    """"관리자는 채팅방 삭제할 수 있게 해달라" 요청(2026-08-28). 방 주인
    본인(자기 방을 완전히 없애고 싶을 때) 또는 전체 관리자만 지울 수
    있다 — 초대받은 일반 멤버는 나가기(leave_room)만 가능.

    ★ 2026-08-29: "그룹채팅방도 관리자가 삭제 가능하게 해줘" 요청 — 위 로직은
    custom_rooms 테이블에 있는 방(1:1 승격 방·커스텀 방)만 다뤘고, Notion
    group_name으로 파생되는 그룹 회의방은 애초에 그 테이블에 없어서 404만
    떨어졌다. custom_rooms에 없으면 Notion 그룹 회의방인지 확인해서
    _delete_notion_group_room으로 넘긴다. 이 방들은 "주인"이 없는 관리자
    큐레이션 콘텐츠라 전체 관리자만 삭제할 수 있다(일반 멤버는 여전히
    leave_room으로 자기만 나가는 것만 가능 — 방 자체는 유지)."""
    if not getattr(request.state, "can_write", True):
        raise HTTPException(status_code=403, detail="읽기 전용 계정입니다")
    user = getattr(request.state, "user", None)
    username = user["username"] if user else None
    is_owner_request = bool(user and user["is_owner"])
    conn = get_conn()
    row = conn.execute("SELECT owner_username FROM custom_rooms WHERE room_id = ?", (room_id,)).fetchone()
    if not row:
        persona = conn.execute("SELECT owner_username FROM personas WHERE name = ?", (room_id,)).fetchone()
        if persona:
            if not (is_owner_request or persona["owner_username"] == username):
                conn.close()
                raise HTTPException(status_code=403, detail="이 대화를 삭제할 권한이 없습니다")
            _clear_persona_room(conn, room_id)
            conn.commit()
            conn.close()
            return {"ok": True, "cleared": True}
        if room_id != GROUP_ROOM_ID and _is_notion_group_room(conn, room_id):
            if not is_owner_request:
                conn.close()
                raise HTTPException(status_code=403, detail="이 방은 전체 관리자만 삭제할 수 있습니다")
            _delete_notion_group_room(conn, room_id)
            conn.commit()
            conn.close()
            return {"ok": True}
        conn.close()
        raise HTTPException(status_code=404, detail="존재하지 않는 채팅방입니다")
    if not (is_owner_request or row["owner_username"] == username):
        conn.close()
        raise HTTPException(status_code=403, detail="이 방의 주인이나 관리자만 삭제할 수 있습니다")
    _delete_custom_room(conn, room_id)
    conn.commit()
    conn.close()
    return {"ok": True}


class RoomRename(BaseModel):
    label: str


@app.put("/api/rooms/{room_id}")
def rename_room(room_id: str, body: RoomRename, request: Request):
    """방 이름 수정 — "왼쪽으로 밀면 삭제나 수정 나오는 기능" 요청
    (2026-08-28)의 "수정"에 해당. 방 주인 또는 관리자만 가능."""
    if not getattr(request.state, "can_write", True):
        raise HTTPException(status_code=403, detail="읽기 전용 계정입니다")
    label = body.label.strip()
    if not label or len(label) > 30:
        raise HTTPException(status_code=400, detail="방 이름은 1~30자로 입력하세요")
    user = getattr(request.state, "user", None)
    username = user["username"] if user else None
    is_owner_request = bool(user and user["is_owner"])
    conn = get_conn()
    row = conn.execute("SELECT owner_username FROM custom_rooms WHERE room_id = ?", (room_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="존재하지 않는 채팅방입니다")
    if not (is_owner_request or row["owner_username"] == username):
        conn.close()
        raise HTTPException(status_code=403, detail="이 방의 주인이나 관리자만 수정할 수 있습니다")
    conn.execute("UPDATE custom_rooms SET label = ? WHERE room_id = ?", (label, room_id))
    conn.commit()
    conn.close()
    return {"ok": True, "label": label}


# ══════════════════════════════════════════════════════════════
# ★ "채팅방에 새 메시지 있으면 사용자들한테도 알람이 가게 해달라" +
# "카카오로 로그인한 사람한테는 카톡 알람이 가게" 요청(2026-08-27).
# 대상은 커스텀 방(방 주인 + room_user_invites로 초대된 계정) — Notion
# 그룹 회의방은 로그인만 하면 전원 공유라 매 메시지마다 전체 알림을 보내면
# 스팸이 되므로 대상에서 뺐다. 카카오 로그인 + talk_message 토큰이 있는
# 계정은 카톡 "나에게 보내기"로, 그 외(또는 카톡 전송 실패)는 웹 푸시로.
# ══════════════════════════════════════════════════════════════

@app.get("/api/push/public_key")
def push_public_key():
    return {"enabled": push_enabled(), "public_key": VAPID_PUBLIC_KEY}


class PushSubscribeRequest(BaseModel):
    endpoint: str
    keys: dict


@app.post("/api/push/subscribe")
def push_subscribe(body: PushSubscribeRequest, request: Request):
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다")
    p256dh = body.keys.get("p256dh")
    auth_key = body.keys.get("auth")
    if not p256dh or not auth_key:
        raise HTTPException(status_code=400, detail="구독 정보가 올바르지 않습니다")
    conn = get_conn()
    conn.execute(
        """INSERT INTO push_subscriptions (username, endpoint, p256dh, auth, created_at)
           VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(endpoint) DO UPDATE SET username = excluded.username,
               p256dh = excluded.p256dh, auth = excluded.auth""",
        (user["username"], body.endpoint, p256dh, auth_key, _now()),
    )
    _deliver_system_update_pushes(conn, user["username"])
    conn.commit()
    conn.close()
    return {"ok": True}


class PushUnsubscribeRequest(BaseModel):
    endpoint: str


@app.post("/api/push/unsubscribe")
def push_unsubscribe(body: PushUnsubscribeRequest):
    conn = get_conn()
    conn.execute("DELETE FROM push_subscriptions WHERE endpoint = ?", (body.endpoint,))
    conn.commit()
    conn.close()
    return {"ok": True}


def _send_web_push_to_user(conn, username, title, body_text, url):
    if not push_enabled():
        return 0
    sleeping = _shift_alarm_sleep_mode_active()
    if sleeping:
        _queue_shift_alarm_sleep_notification(title, body_text, url)
    sent = 0
    rows = conn.execute(
        "SELECT id, endpoint, p256dh, auth FROM push_subscriptions WHERE username = ?", (username,)
    ).fetchall()
    for row in rows:
        try:
            webpush(
                subscription_info={
                    "endpoint": row["endpoint"],
                    "keys": {"p256dh": row["p256dh"], "auth": row["auth"]},
                },
                data=json.dumps({
                    "title": title, "body": body_text, "url": url,
                    "silent": sleeping,
                }),
                vapid_private_key=VAPID_PRIVATE_KEY_FILE,
                vapid_claims={"sub": VAPID_CLAIM_EMAIL},
            )
            sent += 1
        except WebPushException as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if status in (404, 410):
                conn.execute("DELETE FROM push_subscriptions WHERE id = ?", (row["id"],))
            else:
                print(f"⚠️ 웹 푸시 실패({username}): {exc}")
    return sent


def _deliver_system_update_pushes(conn, username):
    """아직 보내지 않은 시스템 업데이트를 계정·항목별 한 번만 푸시한다."""
    delivered = {
        row["notification_id"] for row in conn.execute(
            "SELECT notification_id FROM notification_push_deliveries WHERE username=?",
            (username,),
        ).fetchall()
    }
    for item in reversed(SYSTEM_UPDATE_NOTIFICATIONS):
        if item["id"] in delivered:
            continue
        _send_web_push_to_user(conn, username, item["title"], item["body"], item["url"])
        conn.execute(
            "INSERT OR IGNORE INTO notification_push_deliveries(username,notification_id,delivered_at) VALUES(?,?,?)",
            (username, item["id"], _now()),
        )


def _deliver_system_updates_on_startup():
    conn = get_conn()
    try:
        usernames = [
            row["username"] for row in conn.execute(
                "SELECT DISTINCT username FROM push_subscriptions"
            ).fetchall()
        ]
        for username in usernames:
            _deliver_system_update_pushes(conn, username)
        conn.commit()
    finally:
        conn.close()


EBOOK_DISCUSSION_ROOM_ID = "custom_8213ad5b05"
ENGLISH_TEACHER_PERSONA_NAME = "영어 선생님"
ENGLISH_TEACHER_SYSTEM_PROMPT = (
    "당신은 영어 원서 아침 독서를 돕는 영어 선생님입니다. 독서지기가 먼저 정리한 오늘의 범위와 "
    "실제 영어 원문을 확인한 뒤 학습 가치가 높은 부분만 가르치세요. 매번 ① 좋은 영어 표현 3~5개 "
    "② 인상 깊은 원문 구절 1~2개와 자연스러운 한국어 뜻 ③ 한국 학습자에게 어려울 단어 4~8개 "
    "④ 오늘 꼭 기억할 핵심 표현 1~2개를 정리합니다. 각 표현에는 원문, 뜻, 문맥에서의 뉘앙스, "
    "짧은 새 예문을 붙이되 한꺼번에 너무 많은 항목을 나열하지 마세요. 실제 오늘 읽은 원문에 없는 "
    "문장이나 인용은 만들지 말고, 독서지기의 줄거리 요약을 반복하지 마세요. 저자처럼 감상을 말하거나 "
    "토론을 주도하지 말고 영어 학습을 맡은 선생님답게 명확하고 따뜻한 한국어로 설명하세요. 어려운 단어, "
    "좋은 영어 표현, 인상 깊은 원문 구절은 모두 `**영어 원문**` 바로 다음 줄에 `- 뜻: 한국어 뜻` 형식으로 "
    "작성해 사용자가 원문을 눌러 영어 단어장에 저장할 수 있게 하세요. 답변 끝에는 "
    "제공된 영어서재 링크를 URL 그대로 노출하지 말고 '영어서재에서 오늘 읽은 부분 보기'라는 글자 링크로 "
    "한 번만 안내하세요."
)


def _ensure_english_reading_teacher(conn):
    """영어 선생님 페르소나와 독서 토론방 초대를 결정론적으로 보장한다."""
    existing = conn.execute(
        "SELECT name FROM personas WHERE name = ?", (ENGLISH_TEACHER_PERSONA_NAME,)
    ).fetchone()
    if not existing:
        conn.execute(
            "INSERT INTO personas (name, notion_page_id, system_prompt, group_name, owner_username, description, synced_at) "
            "VALUES (?, '', ?, NULL, ?, ?, ?)",
            (
                ENGLISH_TEACHER_PERSONA_NAME,
                ENGLISH_TEACHER_SYSTEM_PROMPT,
                APP_USERNAME or "automation",
                "오늘 읽은 영어 원문에서 좋은 표현·인상 깊은 구절·어려운 단어를 가르치는 영어 선생님",
                _now(),
            ),
        )
    conn.execute(
        "INSERT OR IGNORE INTO room_invites(room_id, persona_name, invited_at) VALUES (?, ?, ?)",
        (EBOOK_DISCUSSION_ROOM_ID, ENGLISH_TEACHER_PERSONA_NAME, _now()),
    )


def _analyze_pending_message_topics_forever():
    """메시지 전송을 막지 않는 로컬 BGE-M3 분석 루프."""
    while True:
        conn = get_conn()
        rows = conn.execute(
            """SELECT m.id,m.content FROM messages m
                 JOIN message_topic_metadata t ON t.message_id=m.id
                WHERE t.status IN ('pending','retry') AND t.user_corrected=0
                ORDER BY m.id LIMIT 8"""
        ).fetchall()
        if rows:
            ids = [row["id"] for row in rows]
            conn.execute(
                f"UPDATE message_topic_metadata SET status='processing',updated_at=? WHERE message_id IN ({','.join('?' for _ in ids)})",
                (_now(), *ids),
            )
            conn.commit()
        conn.close()
        if not rows:
            time.sleep(3)
            continue
        for row in rows:
            try:
                result = topic_analysis.analyze_message(row["content"])
                conn = get_conn()
                conn.execute(
                    """UPDATE message_topic_metadata SET status='done',primary_topic=?,subtopic=?,
                       keywords_json=?,entities_json=?,message_type=?,summary=?,confidence=?,embedding=?,
                       embedding_dim=?,model_version=?,error=NULL,updated_at=? WHERE message_id=?""",
                    (result["primary_topic"], result["subtopic"], json.dumps(result["keywords"], ensure_ascii=False),
                     json.dumps(result["entities"], ensure_ascii=False), result["message_type"], result["summary"],
                     result["confidence"], result["embedding"], result["embedding_dim"], result["model_version"],
                     _now(), row["id"]),
                )
                conn.commit(); conn.close()
            except Exception as exc:
                conn = get_conn()
                conn.execute(
                    "UPDATE message_topic_metadata SET status='retry',error=?,updated_at=? WHERE message_id=?",
                    (str(exc)[:500], _now(), row["id"]),
                )
                conn.commit(); conn.close()
                time.sleep(2)


def _recover_mp3_postprocess_jobs() -> None:
    """재시작으로 끊긴 작업을 잇고, 먼저 받은 추천곡도 한 번만 보충 처리한다."""
    conn = get_conn()
    interrupted_downloads = conn.execute(
        "SELECT * FROM mp3_download_jobs WHERE status IN ('queued','downloading','converting','finalizing') ORDER BY created_at"
    ).fetchall()
    interrupted = conn.execute(
        "SELECT id FROM mp3_postprocess_jobs WHERE status IN ('queued','processing') ORDER BY created_at"
    ).fetchall()
    translating = conn.execute(
        "SELECT id,source_message_id FROM mp3_postprocess_jobs WHERE status='translating' AND source_message_id IS NOT NULL"
    ).fetchall()
    feedback = conn.execute(
        "SELECT username,youtube_id,title FROM mp3_recommendation_feedback WHERE action='download'"
    ).fetchall()
    for row in feedback:
        has_mp3 = any(f"[{row['youtube_id']}]" in item.stem for item in MP3_FAVORITES_DIR.glob("*.mp3"))
        incomplete = any(f"[{row['youtube_id']}]" in item.stem for suffix in ("mp4", "m4a", "webm") for item in MP3_FAVORITES_DIR.glob(f"*.{suffix}"))
        known = conn.execute(
            "SELECT 1 FROM mp3_download_jobs WHERE username=? AND youtube_id=? AND status IN ('queued','downloading','converting','finalizing','complete')",
            (row["username"], row["youtube_id"]),
        ).fetchone()
        if incomplete and not has_mp3 and not known:
            now, recovery_id = _now(), uuid.uuid4().hex
            url = f"https://www.youtube.com/watch?v={row['youtube_id']}"
            conn.execute(
                """INSERT INTO mp3_download_jobs
                   (id,username,youtube_id,url,destination,status,stage,percent,created_at,updated_at)
                   VALUES(?,?,?,?,?,'queued','중단 작업 복구 대기 중',0,?,?)""",
                (recovery_id, row["username"], row["youtube_id"], url, "favorites", now, now),
            )
            interrupted_downloads = [*interrupted_downloads, conn.execute("SELECT * FROM mp3_download_jobs WHERE id=?", (recovery_id,)).fetchone()]
    conn.commit()
    conn.close()
    for row in interrupted_downloads:
        job = dict(row)
        job.update(status="queued", stage="중단 작업 복구 대기 중", percent=0, updated_at=_now())
        _mp3_download_jobs[job["id"]] = job
        _update_mp3_download_job(job["id"], status="queued", stage="중단 작업 복구 대기 중", percent=0, error=None)
        threading.Thread(
            target=_run_youtube_mp3_job,
            args=(job["id"], job["url"], job["destination"], job["username"]),
            daemon=True, name=f"youtube-recover-{job['id'][:6]}",
        ).start()
    for row in interrupted:
        threading.Thread(target=_run_mp3_postprocess, args=(row["id"],), daemon=True).start()
    for row in translating:
        threading.Thread(target=_watch_mp3_translation, args=(row["id"], row["source_message_id"]), daemon=True).start()
    for row in feedback:
        matches = sorted(
            (item for item in MP3_FAVORITES_DIR.glob("*.mp3") if f"[{row['youtube_id']}]" in item.stem),
            key=lambda item: item.stat().st_mtime, reverse=True,
        )
        if matches:
            _enqueue_mp3_postprocess(row["username"], matches[0], row["youtube_id"])


@app.on_event("startup")
def start_system_update_push_delivery():
    global _DATING_REBUILD_RECOVERY_STARTED, _WORKTREE_UPDATE_WATCHER_STARTED, _lrc_recovery_started, _mp3_postprocess_recovery_started
    global _DATING_SIM_IMAGE_REPORT_WORKER_STARTED, _TOPIC_ANALYSIS_WORKER_STARTED
    conn = get_conn()
    try:
        _ensure_english_reading_teacher(conn)
        conn.commit()
    finally:
        conn.close()
    threading.Thread(target=_deliver_system_updates_on_startup, daemon=True).start()
    if not _TOPIC_ANALYSIS_WORKER_STARTED:
        _TOPIC_ANALYSIS_WORKER_STARTED = True
        threading.Thread(
            target=_analyze_pending_message_topics_forever, daemon=True, name="message-topic-analysis"
        ).start()
    if not _lrc_recovery_started:
        _lrc_recovery_started = True
        threading.Thread(target=_recover_persistent_lrc_jobs, daemon=True, name="lrc-job-recovery").start()
    if not _mp3_postprocess_recovery_started:
        _mp3_postprocess_recovery_started = True
        threading.Thread(target=_recover_mp3_postprocess_jobs, daemon=True, name="mp3-postprocess-recovery").start()
    if not _WORKTREE_UPDATE_WATCHER_STARTED:
        _WORKTREE_UPDATE_WATCHER_STARTED = True
        threading.Thread(target=_watch_worktree_updates_forever, daemon=True).start()
    if not _DATING_REBUILD_RECOVERY_STARTED:
        _DATING_REBUILD_RECOVERY_STARTED = True
        threading.Thread(target=_recover_dating_rebuilds_forever, daemon=True).start()
        threading.Thread(target=_watch_dating_sim_teacher_notifications_forever, daemon=True).start()
    if not _DATING_SIM_IMAGE_REPORT_WORKER_STARTED:
        _DATING_SIM_IMAGE_REPORT_WORKER_STARTED = True
        threading.Thread(
            target=_watch_dating_sim_image_reports_forever, daemon=True,
            name="dating-sim-image-reports",
        ).start()


def _send_kakao_alert_to_user(conn, username, title, body_text, url):
    """카톡 "나에게 보내기"로 보낼 수 있으면 보내고 True, 아니면(토큰 없음·
    갱신 실패·전송 실패) False — 호출부가 웹 푸시로 대체할 수 있게."""
    row = conn.execute(
        "SELECT kakao_access_token, kakao_refresh_token, kakao_token_expires_at FROM users WHERE username = ?",
        (username,),
    ).fetchone()
    if not row or not row["kakao_access_token"]:
        return False
    access_token = row["kakao_access_token"]
    needs_refresh = True
    if row["kakao_token_expires_at"]:
        try:
            needs_refresh = (
                datetime.datetime.fromisoformat(row["kakao_token_expires_at"])
                <= datetime.datetime.now(datetime.timezone.utc)
            )
        except ValueError:
            needs_refresh = True
    if needs_refresh:
        if not row["kakao_refresh_token"]:
            return False
        try:
            refreshed = oauth.kakao_refresh_token(row["kakao_refresh_token"])
            access_token = refreshed["access_token"]
            new_expires_at = (
                datetime.datetime.now(datetime.timezone.utc)
                + datetime.timedelta(seconds=refreshed.get("expires_in") or 0)
            ).isoformat()
            conn.execute(
                "UPDATE users SET kakao_access_token = ?, "
                "kakao_refresh_token = COALESCE(?, kakao_refresh_token), "
                "kakao_token_expires_at = ? WHERE username = ?",
                (access_token, refreshed.get("refresh_token"), new_expires_at, username),
            )
            conn.commit()
        except oauth.OAuthError as exc:
            print(f"⚠️ 카카오 토큰 갱신 실패({username}): {exc}")
            return False
    try:
        oauth.send_kakao_memo(access_token, f"{title}\n{body_text}", url)
        return True
    except oauth.OAuthError as exc:
        print(f"⚠️ 카톡 알림 전송 실패({username}): {exc}")
        return False


def notify_room_members_new_message(conn, room_id, sender, title, body_text):
    """방(room_id)의 실제 사용자 멤버(발신자 제외)에게 새 메시지를 알린다.

    ★ 실측(2026-08-28): "일반 사용자들한테는 메시지 알람이 불가능한가?"
    문의로 확인한 버그 — 원래는 커스텀 방만 대상이었는데, 같은 날 앞서
    그룹 회의방에도 실제 사람을 초대할 수 있게 확장(room_user_invites
    재사용)하면서 이 함수를 안 고쳐서, 그룹 회의방에 초대된 사람은
    room_user_invites에 엄연히 들어 있는데도 알림을 하나도 못 받고
    있었다. 커스텀 방이 아니면 그룹 회의방인지 확인해서 초대된 사람만
    챙긴다(관리자는 굳이 알림 대상에 안 넣는다 — 그룹 회의방은 페르소나
    발화가 잦아 관리자에게 매번 알리면 스팸이 된다는 기존 결정 유지,
    room_user_invites에 아무도 없으면 전체 채팅방 등은 여전히 대상이
    아니다)."""
    row = conn.execute("SELECT owner_username FROM custom_rooms WHERE room_id = ?", (room_id,)).fetchone()
    if row:
        members = {row["owner_username"]} if row["owner_username"] else set()
    elif _is_notion_group_room(conn, room_id):
        members = set()
    else:
        return
    members |= {
        r["username"] for r in conn.execute(
            "SELECT username FROM room_user_invites WHERE room_id = ?", (room_id,)
        ).fetchall()
    }
    members.discard(sender)
    if not members:
        return
    base_url = oauth.PUBLIC_BASE_URL or ""
    url = f"{base_url}/#room={urllib.parse.quote(room_id, safe='')}"
    for username in members:
        if not _send_kakao_alert_to_user(conn, username, title, body_text, url):
            _send_web_push_to_user(conn, username, title, body_text, url)


@app.get("/api/rooms")
def list_rooms(request: Request):
    """방 목록 — 카카오톡 채팅 목록처럼 전체 채팅방 1개 + 그룹 회의방 +
    페르소나별 1:1 방. 각 방의 마지막 메시지 미리보기도 같이 준다.

    ★ 2026-08-25: "페르소나 목록도 그룹화하는 게 좋을거같아" 요청 — 각 1:1
    방에 Notion 프로필의 "그룹" 필드(group_name, 없으면 None)를 실어서
    반환한다. 실제 그룹 헤더로 묶어 보여주는 건 프론트엔드(static/chat.js)가
    한다.

    ★ 같은 날 추가: "동찬이형+양승윤 묶어서 그 안에서 회의하는 식으로"
    요청 — 그룹명 자체를 방 하나로도 노출한다(room_id=그룹명). 이 방에
    메시지를 보내면 그 그룹 소속 페르소나 전원이 순서대로 응답한다(폴링
    큐가 한 번에 하나씩 처리되므로, 뒤 순서 페르소나는 앞선 페르소나의
    답까지 컨텍스트에 포함돼 자연스럽게 "회의"처럼 이어진다). is_group_room
    플래그로 1:1 방과 구분해서 프론트가 그룹 헤더 없이 맨 위에 따로 보여준다
    (그룹 회의방 자신을 그 그룹의 "구성원"처럼 묶어버리는 걸 방지).

    ★ 2026-08-26: "1:1 방은 다른 참여자들에게 아예 안 보이게 해달라" 요청 —
    소유자가 아니면 페르소나 1:1 방 자체를 목록에서 뺀다(전체 채팅방·그룹
    회의방만 보임). /api/messages도 같은 기준으로 직접 접근을 막으므로,
    URL 해시를 직접 편집해도 못 들어간다. 단, "내가 만든 페르소나"는 예외 —
    본인의 1:1 방은 본인에게 보인다(_can_access_persona_room).

    ★ 같은 날 추가: "단체톡방 만들기" 요청 — 계정이 직접 만든 커스텀 방도
    본인/소유자에게만 노출한다."""
    conn = get_conn()
    persona_rows = conn.execute(
        "SELECT name, group_name, owner_username, avatar_url FROM personas ORDER BY name"
    ).fetchall()
    user = getattr(request.state, "user", None)
    is_owner_request = user["is_owner"] if user else True
    username = user["username"] if user else None
    rooms = [{"room_id": GROUP_ROOM_ID, "label": "전체 채팅방", "group_name": None, "is_group_room": False, "is_mine": False}] if GROUP_ROOM_ENABLED else []

    seen_groups = []
    for r in persona_rows:
        if r["group_name"] and r["group_name"] not in seen_groups:
            seen_groups.append(r["group_name"])
    # ★ "실제 사용자도 초대할 수 있게 해달라" 요청(2026-08-27) — 초대된
    # 계정에게도 방 목록에 그 방이 보여야 들어갈 수 있다(직접 URL을 몰라도).
    # room_user_invites는 커스텀 방·그룹 회의방 구분 없이 room_id로만
    # 저장되므로 둘 다 이 집합 하나로 판단한다.
    invited_room_ids = {
        r["room_id"] for r in conn.execute(
            "SELECT room_id FROM room_user_invites WHERE username = ?", (username,)
        ).fetchall()
    } if username else set()
    # ★ "처음 사용자한테는 아무 채팅방도 안 보이는 게 맞다" 요청(2026-08-28)
    # — 그룹 회의방은 기본적으로 관리자만 목록에서 본다(_is_notion_group_room
    # 정의부 설명 참고). ★ 같은 날 후속 요청: "그룹 회의방에서 사람 초대하려는데
    # 왜 목록에 없지" — 관리자가 특정 사람을 그 방에 초대(room_user_invites)
    # 했으면 그 사람에게도 보인다.
    for group_name in seen_groups:
        if is_owner_request or group_name in invited_room_ids:
            rooms.append({
                "room_id": group_name, "label": f"👥 {group_name}",
                "group_name": None, "is_group_room": True, "is_mine": False,
            })

    custom_rows = conn.execute(
        "SELECT room_id, label, owner_username, thumbnail_url, direct_key FROM custom_rooms ORDER BY created_at"
    ).fetchall()
    for cr in custom_rows:
        is_public_room = cr["label"] == "손자병법 토론방"
        if is_owner_request or cr["owner_username"] == username or cr["room_id"] in invited_room_ids or (username and is_public_room):
            custom_label = cr["label"]
            if cr["direct_key"] and cr["direct_key"].startswith("user:") and username:
                participants = cr["direct_key"].split(":", 2)[1:]
                if username in participants:
                    other_username = participants[1] if participants[0] == username else participants[0]
                    other = conn.execute(
                        "SELECT display_name FROM users WHERE username=?", (other_username,)
                    ).fetchone()
                    custom_label = (other["display_name"] if other else None) or other_username
            rooms.append({
                "room_id": cr["room_id"], "label": f"👥 {custom_label}",
                "group_name": None, "is_group_room": True, "is_mine": cr["owner_username"] == username,
                "thumbnail_url": cr["thumbnail_url"], "is_direct": bool(cr["direct_key"]),
                "direct_type": cr["direct_key"].split(":", 1)[0] if cr["direct_key"] else None,
            })

    rooms += [
        {
            "room_id": r["name"], "label": r["name"], "group_name": r["group_name"], "is_group_room": False,
            "is_mine": r["owner_username"] == username if username else False,
            "thumbnail_url": r["avatar_url"],
        }
        for r in persona_rows
        if _can_access_persona_room(r["owner_username"], username, is_owner_request)
    ]
    for room in rooms:
        # ★ 2026-08-25: "안 읽은 메시지 있으면 안읽음 표시해달라" 요청 —
        # last_message_id를 같이 내려주면 프론트가 로컬(localStorage)에 저장한
        # "이 방에서 마지막으로 읽은 id"와 비교해서 배지를 띄울 수 있다.
        # 읽음 상태 자체는 서버에 저장하지 않는다(기기별 localStorage로 충분).
        last = conn.execute(
            "SELECT id, content, created_at FROM messages WHERE room_id = ? ORDER BY id DESC LIMIT 1",
            (room["room_id"],),
        ).fetchone()
        room["last_message_id"] = last["id"] if last else None
        room["last_message"] = _preview_text(last["content"]) if last else None
        room["last_message_at"] = last["created_at"] if last else None
        read = conn.execute(
            "SELECT last_message_id FROM room_read_state WHERE username=? AND room_id=?",
            (username or "user", room["room_id"]),
        ).fetchone()
        room["last_read_id"] = read["last_message_id"] if read else 0
    conn.close()
    return rooms


class NotificationReadUpdate(BaseModel):
    notification_id: str


class SqlLabQuery(BaseModel):
    sql: str


def _sql_lab_path(username: str) -> Path:
    identity = hashlib.sha256(username.encode("utf-8")).hexdigest()[:24]
    return SQL_LAB_DATA_DIR / f"{identity}.sqlite3"


def _sql_lab_connection(username: str) -> sqlite3.Connection:
    path = _sql_lab_path(username)
    is_new = not path.exists()
    conn = sqlite3.connect(path, timeout=3)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=3000")
    if is_new:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS departments (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE);
        CREATE TABLE IF NOT EXISTS students (
          id INTEGER PRIMARY KEY, name TEXT NOT NULL, age INTEGER,
          department_id INTEGER REFERENCES departments(id)
        );
        CREATE TABLE IF NOT EXISTS scores (
          id INTEGER PRIMARY KEY, student_id INTEGER NOT NULL REFERENCES students(id),
          subject TEXT NOT NULL, score INTEGER NOT NULL CHECK(score BETWEEN 0 AND 100)
        );
        INSERT OR IGNORE INTO departments(id,name) VALUES (1,'데이터'),(2,'디자인'),(3,'언어');
        INSERT OR IGNORE INTO students(id,name,age,department_id) VALUES
          (1,'민서',24,1),(2,'지우',29,2),(3,'하루',26,3),(4,'도윤',31,1);
        INSERT OR IGNORE INTO scores(id,student_id,subject,score) VALUES
          (1,1,'SQL',92),(2,1,'Python',84),(3,2,'SQL',78),(4,3,'일본어',95),(5,4,'SQL',88);
        """)
    conn.commit()
    return conn


def _sql_lab_schema(conn: sqlite3.Connection):
    tables = []
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name").fetchall()
    for row in rows:
        name = row["name"]
        quoted = name.replace('"', '""')
        columns = [dict(column) for column in conn.execute(f'PRAGMA table_info("{quoted}")').fetchall()]
        count = conn.execute(f'SELECT COUNT(*) AS n FROM "{quoted}"').fetchone()["n"]
        tables.append({"name": name, "columns": columns, "row_count": count})
    return tables


@app.get("/api/sql-lab/schema")
def sql_lab_schema(request: Request):
    _require_signed_in_user(request)
    conn = _sql_lab_connection(_request_username(request))
    try:
        return {"tables": _sql_lab_schema(conn)}
    finally:
        conn.close()


@app.post("/api/sql-lab/query")
def sql_lab_query(body: SqlLabQuery, request: Request):
    _require_signed_in_user(request)
    sql = body.sql.strip()
    if not sql or len(sql) > 20000:
        raise HTTPException(status_code=400, detail="SQL을 입력해주세요")
    if re.search(r"\b(ATTACH|DETACH|VACUUM|load_extension)\b", sql, re.I):
        raise HTTPException(status_code=400, detail="실험실 밖의 파일에 접근할 수 있는 명령은 사용할 수 없습니다")
    conn = _sql_lab_connection(_request_username(request))
    started = time.perf_counter()
    deadline = started + 2.0
    conn.set_progress_handler(lambda: 1 if time.perf_counter() > deadline else 0, 10000)
    try:
        cursor = conn.execute(sql)
        columns = [item[0] for item in cursor.description] if cursor.description else []
        rows = [dict(row) for row in cursor.fetchmany(201)] if columns else []
        truncated = len(rows) > 200
        rows = rows[:200]
        affected = cursor.rowcount
        conn.commit()
        return {
            "columns": columns, "rows": rows, "truncated": truncated,
            "affected_rows": affected if affected >= 0 else None,
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
            "schema": _sql_lab_schema(conn),
        }
    except sqlite3.Error as exc:
        conn.rollback()
        raise HTTPException(status_code=400, detail=str(exc))
    finally:
        conn.close()


@app.post("/api/sql-lab/reset")
def sql_lab_reset(request: Request):
    _require_signed_in_user(request)
    path = _sql_lab_path(_request_username(request))
    for candidate in (path, Path(str(path) + "-wal"), Path(str(path) + "-shm")):
        try:
            candidate.unlink()
        except FileNotFoundError:
            pass
    conn = _sql_lab_connection(_request_username(request))
    try:
        return {"ok": True, "tables": _sql_lab_schema(conn)}
    finally:
        conn.close()


@app.get("/api/system/updates")
def get_system_updates(request: Request):
    """웹앱 전체의 사용자용 변경 이력을 최신순으로 반환한다."""
    _require_signed_in_user(request)
    return {"items": _current_webapp_update_history()}


@app.get("/api/dating-sim/updates")
def get_dating_sim_updates(request: Request):
    """미연시의 최근 이미지 생성·교체 기록."""
    _require_signed_in_user(request)
    return {"items": _dating_sim_update_history(include_admin=_is_owner_request(request))}


@app.get("/api/dating-sim/server-update")
def get_dating_sim_server_update(request: Request):
    """미연시 서버·화면·생성기 코드 가운데 가장 최근 변경 시각."""
    _require_signed_in_user(request)
    candidates = [
        Path(__file__), Path(dating_sim_story.__file__),
        DATING_SIM_WEB_DIR / "index.html", DATING_SIM_WEB_DIR / "app.js",
        DATING_SIM_WEB_DIR / "style.css", Path(DATING_SIM_IMAGE_SCRIPT),
    ]
    timestamps = [path.stat().st_mtime for path in candidates if path.is_file()]
    updated_at = max(timestamps) if timestamps else time.time()
    return {
        "updated_at": datetime.datetime.fromtimestamp(
            updated_at, datetime.timezone.utc,
        ).isoformat(timespec="seconds"),
    }


@app.get("/api/notifications")
def get_notifications(request: Request):
    """계정별 시스템 업데이트와 읽지 않은 채팅방을 하나의 알림함으로 반환한다."""
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다")
    username = user["username"]
    rooms = list_rooms(request)
    conn = get_conn()
    read_system_ids = {
        row["notification_id"] for row in conn.execute(
            "SELECT notification_id FROM notification_reads WHERE username=?", (username,)
        ).fetchall()
    }
    items = []
    for update in SYSTEM_UPDATE_NOTIFICATIONS:
        items.append({
            **update, "type": "system", "unread": update["id"] not in read_system_ids,
        })
    for room in rooms:
        last_id = int(room.get("last_message_id") or 0)
        last_read = int(room.get("last_read_id") or 0)
        if last_id <= last_read:
            continue
        count = conn.execute(
            "SELECT COUNT(*) AS n FROM messages WHERE room_id=? AND id>?",
            (room["room_id"], last_read),
        ).fetchone()["n"]
        if not count:
            continue
        items.append({
            "id": f"chat:{room['room_id']}:{last_id}",
            "type": "chat", "title": room["label"],
            "room_id": room["room_id"], "last_message_id": last_id,
            "body": f"읽지 않은 메시지 {count}개" + (
                f" · {room['last_message']}" if room.get("last_message") else ""
            ),
            "url": f"/#room={urllib.parse.quote(room['room_id'], safe='')}",
            "created_at": room.get("last_message_at") or "", "unread": True,
        })
    conn.close()
    items.sort(key=lambda item: item.get("created_at") or "", reverse=True)
    return {"items": items, "unread_count": sum(bool(item["unread"]) for item in items)}


@app.put("/api/notifications/read")
def mark_notification_read(body: NotificationReadUpdate, request: Request):
    """시스템 업데이트 읽음을 계정별로 저장한다. 채팅 읽음은 방 진입 시 처리한다."""
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다")
    known_ids = {item["id"] for item in SYSTEM_UPDATE_NOTIFICATIONS}
    if body.notification_id not in known_ids:
        raise HTTPException(status_code=404, detail="알림을 찾을 수 없습니다")
    conn = get_conn()
    conn.execute(
        "INSERT OR REPLACE INTO notification_reads(username,notification_id,read_at) VALUES(?,?,?)",
        (user["username"], body.notification_id, _now()),
    )
    conn.commit()
    conn.close()
    return {"ok": True}


SUNZI_DISCUSSION_ROOM_ID = "custom_16ea779e1f"
SUNZI_INITIAL_HISTORY_DAYS = 7


def _is_internal_worker_status_message(content: str) -> bool:
    """예전 워커가 페르소나 메시지로 저장한 재시작·밀린 턴 안내다.

    운영 상태는 페르소나의 대화가 아니므로 기존 DB에 남은 기록도 API에서
    내려주지 않는다. 간격·가운데점 표기가 달라진 구버전도 함께 걸러낸다.
    """
    compact = re.sub(r"\s+", "", content or "")
    return (
        compact.startswith("(서버·워커재시작으로답변이약")
        or compact.startswith("(서버ㆍ워커재시작으로답변이약")
        or compact.startswith("(서버・워커재시작으로답변이약")
        or compact.startswith("(서버업데이트끝났어요—밀린메시지답장")
    )


def _parsed_timestamp(value: Optional[str]) -> Optional[datetime.datetime]:
    if not value:
        return None
    try:
        parsed = datetime.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=datetime.timezone.utc)
        return parsed.astimezone(datetime.timezone.utc)
    except (TypeError, ValueError):
        return None


@app.get("/api/mp3/lyrics-study/status")
def get_mp3_lyrics_study_status(request: Request, source_message_id: int = Query(..., ge=1)):
    """MP3 가사 직해 작업의 실제 큐 상태와 결과를 한 번에 반환한다.

    채팅 메시지의 답장 연결 여부에 의존하지 않고 pending_turns를 원장으로
    사용한다. 진행률과 ETA는 최근 같은 페르소나 작업 시간을 이용한 추정값이며,
    완료 결과는 pending_turns.reply에서 직접 복구한다.
    """
    _require_signed_in_user(request)
    username = _request_username(request)
    is_owner = _is_owner_request(request)
    conn = get_conn()
    source = conn.execute(
        "SELECT id, room_id, sender, content, created_at FROM messages WHERE id=?",
        (source_message_id,),
    ).fetchone()
    if not source or not str(source["content"] or "").startswith("[MP3 가사 직해 요청]"):
        conn.close()
        raise HTTPException(status_code=404, detail="가사 직해 요청을 찾지 못했습니다")
    if not is_owner and source["sender"] != username:
        conn.close()
        raise HTTPException(status_code=403, detail="다른 계정의 직해 요청은 확인할 수 없습니다")
    turn = conn.execute(
        """SELECT id, persona_name, status, created_at, started_at, completed_at,
                  reply, error
             FROM pending_turns
            WHERE source_message_id=?
            ORDER BY id DESC LIMIT 1""",
        (source_message_id,),
    ).fetchone()
    if not turn:
        conn.close()
        raise HTTPException(status_code=404, detail="직해 작업 정보를 찾지 못했습니다")

    duration_rows = conn.execute(
        """SELECT started_at, completed_at FROM pending_turns
            WHERE persona_name=? AND status='done'
              AND started_at IS NOT NULL AND completed_at IS NOT NULL
              AND id<>?
            ORDER BY id DESC LIMIT 20""",
        (turn["persona_name"], turn["id"]),
    ).fetchall()
    durations = []
    for row in duration_rows:
        started = _parsed_timestamp(row["started_at"])
        completed = _parsed_timestamp(row["completed_at"])
        if started and completed:
            seconds = (completed - started).total_seconds()
            if 2 <= seconds <= 1800:
                durations.append(seconds)
    expected_seconds = max(15, min(300, int(statistics.median(durations)))) if durations else 45
    now = datetime.datetime.now(datetime.timezone.utc)
    created_at = _parsed_timestamp(turn["created_at"]) or now
    started_at = _parsed_timestamp(turn["started_at"])
    status = str(turn["status"] or "pending")
    queue_position = 0
    elapsed_seconds = 0
    eta_seconds = 0
    percent = 0
    stage = "요청 대기 중"
    if status in {"pending", "waiting_personal_ai"}:
        queue_position = conn.execute(
            "SELECT COUNT(*) AS n FROM pending_turns WHERE status IN ('pending','waiting_personal_ai') AND id<=?",
            (turn["id"],),
        ).fetchone()["n"]
        elapsed_seconds = max(0, int((now - created_at).total_seconds()))
        eta_seconds = 0 if status == "waiting_personal_ai" else max(5, int(queue_position * expected_seconds))
        percent = 5
        stage = "AI 사용 가능 대기 중" if status == "waiting_personal_ai" else f"대기열 {queue_position}번째"
    elif status == "processing":
        elapsed_seconds = max(0, int((now - (started_at or created_at)).total_seconds()))
        eta_seconds = max(0, expected_seconds - elapsed_seconds)
        percent = min(92, max(18, int(18 + 74 * elapsed_seconds / max(expected_seconds, 1))))
        stage = "가사 분석·직해 중"
    elif status == "done":
        elapsed_seconds = max(0, int(((_parsed_timestamp(turn["completed_at"]) or now) - (started_at or created_at)).total_seconds()))
        percent = 100
        stage = "직해 완료"
    else:
        elapsed_seconds = max(0, int(((_parsed_timestamp(turn["completed_at"]) or now) - (started_at or created_at)).total_seconds()))
        percent = 0
        stage = "직해 실패"
    conn.close()
    return {
        "status": status,
        "stage": stage,
        "percent": percent,
        "estimated": status in {"pending", "processing"},
        "queue_position": queue_position,
        "elapsed_seconds": elapsed_seconds,
        "eta_seconds": eta_seconds,
        "result": turn["reply"] if status == "done" and turn["reply"] != "NONE" else None,
        "error": "일시적으로 직해를 완료하지 못했습니다" if status == "failed" else None,
    }


@app.get("/api/messages")
def get_messages(
    request: Request,
    room_id: str = GROUP_ROOM_ID,
    since_id: int = 0,
    before_id: int = 0,
    limit: int = Query(100, ge=20, le=200),
    count_only: bool = False,
):
    conn = get_conn()
    user = getattr(request.state, "user", None)
    username = user["username"] if user else None
    is_owner_request = user["is_owner"] if user else True
    # ★ 2026-08-26: list_rooms()와 같은 기준 — 소유자/본인이 아니면 페르소나
    # 1:1 방은 목록뿐 아니라 직접 조회도 막는다(해시를 직접 편집해서 들어오는
    # 우회 방지). 내가 만든 페르소나는 본인에게 허용.
    persona_owner_rows = conn.execute(
        "SELECT name, owner_username, avatar_url FROM personas"
    ).fetchall()
    persona_owner = {r["name"]: r["owner_username"] for r in persona_owner_rows}
    persona_avatars = {r["name"]: r["avatar_url"] for r in persona_owner_rows}
    persona_names = set(persona_owner)
    if room_id in persona_names:
        if not _can_access_persona_room(persona_owner[room_id], username, is_owner_request):
            conn.close()
            raise HTTPException(status_code=403, detail="다른 계정은 이 1:1 대화를 볼 수 없습니다")
    else:
        is_custom, allowed, _room_owner = _custom_room_access(conn, room_id, username, is_owner_request)
        if is_custom and not allowed:
            conn.close()
            raise HTTPException(status_code=403, detail="이 채팅방을 볼 수 없습니다")
        # ★ "처음 사용자한테는 아무 채팅방도 안 보이는 게 맞다" 요청
        # (2026-08-28) — 그룹 회의방은 목록뿐 아니라 직접 조회도 관리자·
        # 초대받은 사람만 되게 막는다(해시 직접 편집 우회 방지, list_rooms와
        # 같은 기준. _group_room_allowed가 관리자 여부까지 판단하므로 이미
        # 위에서 걸러진 is_owner_request와 별개로 초대 여부를 확인).
        if (
            not is_custom and room_id != GROUP_ROOM_ID and _is_notion_group_room(conn, room_id)
            and not _group_room_allowed(conn, room_id, username, is_owner_request)
        ):
            conn.close()
            raise HTTPException(status_code=403, detail="이 채팅방을 볼 수 없습니다")
    # ★ "채팅방에서 안 읽은 메시지 개수를 방 목록에서도 확인되게 해달라"
    # 요청(2026-08-28) — 안읽음 자체는 기존처럼 클라이언트 localStorage가
    # 기준(last_read_id)이지만, "이 방에 그 id 이후 메시지가 몇 개인지"는
    # 서버만 셀 수 있다. 방 목록을 그릴 때마다 방마다 이 엔드포인트를
    # count_only=true로 불러 가벼운 COUNT만 받는다(전체 메시지 본문을
    # 내려받지 않아 오래된 방도 가볍다) — 별도의 "읽음 상태" 테이블을
    # 서버에 새로 두지 않고 기존 접근 제어를 그대로 재사용한다.
    if count_only:
        count = conn.execute(
            """SELECT COUNT(*) AS n FROM messages
                WHERE room_id = ? AND id > ?
                  AND content NOT LIKE '(서버·워커 재시작으로 답변이 약 %'
                  AND content != '(서버 업데이트 끝났어요 — 밀린 메시지 답장 다 보냈습니다!)'""",
            (room_id, since_id),
        ).fetchone()["n"]
        conn.close()
        return {"count": count}
    message_select = """SELECT m.id, m.sender, m.content, m.created_at, m.reply_message_id, m.is_system,
                               parent.sender AS reply_sender, parent.content AS reply_content,
                               topic.status AS topic_status,topic.primary_topic,topic.subtopic,
                               topic.keywords_json,topic.entities_json,topic.message_type,
                               topic.summary AS topic_summary,topic.confidence AS topic_confidence,
                               topic.user_corrected AS topic_user_corrected
                          FROM ({subquery}) m
                          LEFT JOIN messages parent ON parent.id = m.reply_message_id
                          LEFT JOIN message_topic_metadata topic ON topic.message_id=m.id
                         ORDER BY m.id"""
    if before_id > 0:
        # 병법방에서 위로 스와이프할 때만 이전 페이지를 DB에서 가져온다.
        # id 커서는 OFFSET과 달리 메시지가 계속 추가돼도 페이지가 밀리지 않는다.
        subquery = "SELECT * FROM messages WHERE room_id = ? AND id < ? ORDER BY id DESC LIMIT ?"
        params = (room_id, before_id, limit)
    elif since_id > 0:
        # 2초 폴링은 지금까지처럼 마지막 id 이후의 새 메시지만 조회한다.
        subquery = "SELECT * FROM messages WHERE room_id = ? AND id > ? ORDER BY id DESC LIMIT 500"
        params = (room_id, since_id)
    elif room_id == SUNZI_DISCUSSION_ROOM_ID:
        cutoff = (datetime.datetime.now().astimezone() - datetime.timedelta(
            days=SUNZI_INITIAL_HISTORY_DAYS
        )).isoformat(timespec="seconds")
        subquery = "SELECT * FROM messages WHERE room_id = ? AND created_at >= ? ORDER BY id DESC LIMIT 500"
        params = (room_id, cutoff)
    else:
        subquery = "SELECT * FROM messages WHERE room_id = ? ORDER BY id DESC LIMIT 500"
        params = (room_id,)
    rows = [
        row for row in conn.execute(message_select.format(subquery=subquery), params).fetchall()
        if not _is_internal_worker_status_message(row["content"])
    ]
    reactions = _message_reactions(conn, [r["id"] for r in rows], username)
    human_profiles = _human_profiles(conn)
    conn.close()
    messages = _with_sender_type(rows, persona_names, persona_avatars, human_profiles)
    for message in messages:
        message["reactions"] = reactions.get(message["id"], [])
        try:
            message["topic_keywords"] = json.loads(message.pop("keywords_json") or "[]")
            message["topic_entities"] = json.loads(message.pop("entities_json") or "[]")
        except json.JSONDecodeError:
            message["topic_keywords"], message["topic_entities"] = [], []
        if message.get("reply_sender"):
            message["reply_is_persona"] = message["reply_sender"] in persona_names
            reply_profile = human_profiles.get(message["reply_sender"], {})
            message["reply_display_name"] = reply_profile.get("display_name") or message["reply_sender"]
    return messages


def _ensure_message_visible(conn, message, username, is_owner_request):
    """message_tts_jobs 트리거/조회 양쪽에서 재사용 — get_messages()의 방
    접근 판단(1:1 방/커스텀 방/Notion 그룹 회의방)과 같은 기준을 메시지
    한 건 단위로 적용한다. 안 보이면 HTTPException을 던진다."""
    room_id = message["room_id"]
    persona_owner_rows = conn.execute("SELECT name, owner_username FROM personas").fetchall()
    persona_owner = {r["name"]: r["owner_username"] for r in persona_owner_rows}
    persona_names = set(persona_owner)
    if room_id in persona_names:
        if not _can_access_persona_room(persona_owner[room_id], username, is_owner_request):
            raise HTTPException(status_code=403, detail="이 메시지를 볼 수 없습니다")
        return
    is_custom, allowed, _room_owner = _custom_room_access(conn, room_id, username, is_owner_request)
    if is_custom and not allowed:
        raise HTTPException(status_code=403, detail="이 메시지를 볼 수 없습니다")
    if (
        not is_custom and room_id != GROUP_ROOM_ID and _is_notion_group_room(conn, room_id)
        and not _group_room_allowed(conn, room_id, username, is_owner_request)
    ):
        raise HTTPException(status_code=403, detail="이 메시지를 볼 수 없습니다")


MESSAGE_TTS_GENERATOR_VERSION = "multilingual-edge-v4-markdown-heading"


@app.post("/api/messages/{message_id}/tts")
def request_message_tts(message_id: int, request: Request):
    """★ "페르소나화 된 인물들의 목소리도 넣을 수 있나? 메시지 읽기 기능으로
    그 페르소나의 목소리로 읽어주면 좋을 것 같아" 요청(2026-08-30) — 실제 TTS
    생성(OpenAI API 호출)은 워커(이 Mac)가 담당한다(OPENAI_API_KEY가 서버에는
    없음, 이미지 자동 생성과 같은 원칙). 여기서는 작업을 큐에 넣거나(없으면)
    기존 결과를 그대로 돌려준다 — message_id에 UNIQUE라 같은 메시지를 여러 번
    눌러도 재생성하지 않고 캐시된 파일을 재사용한다."""
    if not getattr(request.state, "can_write", True):
        raise HTTPException(status_code=403, detail="읽기 전용 계정입니다")
    user = getattr(request.state, "user", None)
    username = user["username"] if user else None
    is_owner_request = user["is_owner"] if user else True
    conn = get_conn()
    message = conn.execute(
        "SELECT id, room_id, sender FROM messages WHERE id = ?", (message_id,)
    ).fetchone()
    if not message:
        conn.close()
        raise HTTPException(status_code=404, detail="메시지를 찾을 수 없습니다")
    is_persona = conn.execute(
        "SELECT 1 FROM personas WHERE name = ?", (message["sender"],)
    ).fetchone()
    if not is_persona:
        conn.close()
        raise HTTPException(status_code=400, detail="페르소나 메시지만 읽어줄 수 있습니다")
    try:
        _ensure_message_visible(conn, message, username, is_owner_request)
    except HTTPException:
        conn.close()
        raise
    existing = conn.execute(
        "SELECT status, result_url, error, generator_version FROM message_tts_jobs WHERE message_id = ?", (message_id,)
    ).fetchone()
    if existing:
        if existing["generator_version"] != MESSAGE_TTS_GENERATOR_VERSION:
            conn.execute(
                """UPDATE message_tts_jobs
                      SET status='pending', result_url=NULL, error=NULL, started_at=NULL,
                          completed_at=NULL, generator_version=?
                    WHERE message_id=?""",
                (MESSAGE_TTS_GENERATOR_VERSION, message_id),
            )
            conn.commit()
            conn.close()
            return {"status": "pending", "result_url": None, "error": None}
        conn.close()
        return {"status": existing["status"], "result_url": existing["result_url"], "error": existing["error"]}
    conn.execute(
        """INSERT INTO message_tts_jobs
             (message_id, persona_name, status, created_at, generator_version)
             VALUES (?, ?, 'pending', ?, ?)""",
        (message_id, message["sender"], _now(), MESSAGE_TTS_GENERATOR_VERSION),
    )
    conn.commit()
    conn.close()
    return {"status": "pending", "result_url": None, "error": None}


@app.get("/api/messages/{message_id}/tts")
def get_message_tts(message_id: int, request: Request):
    """프론트가 요청 후 짧게 폴링해서 결과(URL)를 받아간다."""
    user = getattr(request.state, "user", None)
    username = user["username"] if user else None
    is_owner_request = user["is_owner"] if user else True
    conn = get_conn()
    message = conn.execute(
        "SELECT id, room_id FROM messages WHERE id = ?", (message_id,)
    ).fetchone()
    if not message:
        conn.close()
        raise HTTPException(status_code=404, detail="메시지를 찾을 수 없습니다")
    try:
        _ensure_message_visible(conn, message, username, is_owner_request)
    except HTTPException:
        conn.close()
        raise
    row = conn.execute(
        "SELECT status, result_url, error FROM message_tts_jobs WHERE message_id = ?", (message_id,)
    ).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="아직 읽어주기가 요청되지 않았습니다")
    return {"status": row["status"], "result_url": row["result_url"], "error": row["error"]}


class ReadStateUpdate(BaseModel):
    room_id: str
    last_message_id: int


@app.put("/api/read-state")
def update_read_state(body: ReadStateUpdate, request: Request):
    """계정별 읽음 위치를 서버에 저장해 브라우저와 기기가 달라도 동기화한다."""
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다")
    if body.last_message_id < 0:
        raise HTTPException(status_code=400, detail="잘못된 메시지 ID입니다")
    conn = get_conn()
    conn.execute(
        """INSERT INTO room_read_state(username, room_id, last_message_id, updated_at)
           VALUES (?, ?, ?, ?)
           ON CONFLICT(username, room_id) DO UPDATE SET
             last_message_id=MAX(room_read_state.last_message_id, excluded.last_message_id),
             updated_at=excluded.updated_at""",
        (user["username"], body.room_id, body.last_message_id, _now()),
    )
    conn.commit()
    conn.close()
    return {"ok": True}


class MessageEdit(BaseModel):
    content: str


class MessageTopicUpdate(BaseModel):
    primary_topic: str
    subtopic: str = ""
    keywords: list[str] = []


def _message_topic_response(row):
    if not row:
        return {"topic_status": "pending"}
    return {
        "topic_status": row["status"],
        "primary_topic": row["primary_topic"] or "",
        "subtopic": row["subtopic"] or "",
        "topic_keywords": json.loads(row["keywords_json"] or "[]"),
        "topic_entities": json.loads(row["entities_json"] or "[]"),
        "message_type": row["message_type"] or "discussion",
        "topic_summary": row["summary"] or "",
        "topic_confidence": row["confidence"],
        "topic_user_corrected": row["user_corrected"],
    }


@app.get("/api/messages/{message_id}/topic")
def get_message_topic(message_id: int, request: Request):
    user = getattr(request.state, "user", None)
    username = user["username"] if user else None
    is_owner_request = user["is_owner"] if user else True
    conn = get_conn()
    message = conn.execute("SELECT id,room_id FROM messages WHERE id=?", (message_id,)).fetchone()
    if not message:
        conn.close(); raise HTTPException(status_code=404, detail="메시지를 찾을 수 없습니다")
    try:
        _ensure_message_visible(conn, message, username, is_owner_request)
    except HTTPException:
        conn.close(); raise
    row = conn.execute("SELECT * FROM message_topic_metadata WHERE message_id=?", (message_id,)).fetchone()
    conn.close()
    return _message_topic_response(row)


@app.put("/api/messages/{message_id}/topic")
def update_message_topic(message_id: int, body: MessageTopicUpdate, request: Request):
    user = getattr(request.state, "user", None)
    username = user["username"] if user else None
    is_owner_request = user["is_owner"] if user else True
    primary = re.sub(r"\s+", " ", body.primary_topic).strip()[:60]
    subtopic = re.sub(r"\s+", " ", body.subtopic).strip()[:80]
    keywords = list(dict.fromkeys(re.sub(r"\s+", " ", item).strip()[:40] for item in body.keywords if item.strip()))[:10]
    if not primary:
        raise HTTPException(status_code=400, detail="주제를 입력하세요")
    conn = get_conn()
    message = conn.execute("SELECT id,room_id FROM messages WHERE id=?", (message_id,)).fetchone()
    if not message:
        conn.close(); raise HTTPException(status_code=404, detail="메시지를 찾을 수 없습니다")
    try:
        _ensure_message_visible(conn, message, username, is_owner_request)
    except HTTPException:
        conn.close(); raise
    now = _now()
    conn.execute(
        """INSERT INTO message_topic_metadata
           (message_id,status,primary_topic,subtopic,keywords_json,user_corrected,created_at,updated_at)
           VALUES(?,'done',?,?,?,1,?,?)
           ON CONFLICT(message_id) DO UPDATE SET status='done',primary_topic=excluded.primary_topic,
             subtopic=excluded.subtopic,keywords_json=excluded.keywords_json,user_corrected=1,
             updated_at=excluded.updated_at""",
        (message_id, primary, subtopic, json.dumps(keywords, ensure_ascii=False), now, now),
    )
    conn.commit(); conn.close()
    return {"ok": True, "topic_status": "done", "primary_topic": primary,
            "subtopic": subtopic, "topic_keywords": keywords, "topic_user_corrected": 1}


@app.put("/api/messages/{message_id}")
def edit_message(message_id: int, body: MessageEdit, request: Request):
    """"각 이용자들도 자기 메시지는 수정·삭제할 수 있게 해달라" 요청(2026-08-27)
    — 본인이 직접 보낸 메시지(페르소나 발화 제외)만 수정할 수 있다. 관리자도
    다른 사람 말을 대신 고쳐 쓸 수는 없다(삭제와 달리 수정은 "그 사람이 실제로
    한 말"을 바꾸는 것이라 본인 전용으로 좁힌다)."""
    if not getattr(request.state, "can_write", True):
        raise HTTPException(status_code=403, detail="읽기 전용 계정입니다")
    user = getattr(request.state, "user", None)
    username = user["username"] if user else None
    content = body.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="내용을 입력하세요")
    conn = get_conn()
    row = conn.execute("SELECT sender FROM messages WHERE id = ?", (message_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="메시지를 찾을 수 없습니다")
    persona_names = _persona_name_set(conn)
    if row["sender"] in persona_names or not username or row["sender"] != username:
        conn.close()
        raise HTTPException(status_code=403, detail="본인이 보낸 메시지만 수정할 수 있습니다")
    conn.execute("UPDATE messages SET content = ? WHERE id = ?", (content, message_id))
    conn.execute(
        "UPDATE message_topic_metadata SET status='pending',error=NULL,updated_at=? "
        "WHERE message_id=? AND COALESCE(user_corrected,0)=0",
        (_now(), message_id),
    )
    conn.commit()
    conn.close()
    return {"ok": True}


@app.delete("/api/messages/{message_id}")
def delete_message(message_id: int, request: Request):
    """"관리자는 메시지 삭제 권한이 있게, 각 이용자도 자기 메시지는 삭제할 수
    있게 해달라" 요청(2026-08-27) — 소유자는 아무 메시지나, 일반 사용자는
    본인이 보낸 메시지만 지울 수 있다(페르소나 발화 포함 — 소유자 전용)."""
    if not getattr(request.state, "can_write", True):
        raise HTTPException(status_code=403, detail="읽기 전용 계정입니다")
    user = getattr(request.state, "user", None)
    username = user["username"] if user else None
    is_owner_request = bool(user and user["is_owner"])
    conn = get_conn()
    row = conn.execute("SELECT sender FROM messages WHERE id = ?", (message_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="메시지를 찾을 수 없습니다")
    if not (is_owner_request or (username and row["sender"] == username)):
        conn.close()
        raise HTTPException(status_code=403, detail="본인이 보낸 메시지이거나 관리자만 삭제할 수 있습니다")
    conn.execute("DELETE FROM messages WHERE id = ?", (message_id,))
    conn.commit()
    conn.close()
    return {"ok": True}


@app.get("/api/all_messages")
def all_messages(since_id: int = 0):
    """방 구분 없이 새 메시지를 전부 반환한다 — /api/worker/all_messages와 같은
    조회지만 워커 토큰이 아니라 일반 세션 인증(읽기 전용 계정도 가능)으로
    쓴다. ★ 2026-08-25: shift_alarm이 "새 메시지 있으면 알람 띄워달라"는
    요청으로 로컬에서 이 엔드포인트를 주기적으로 폴링한다(소유자 Basic Auth로
    인증 — 브라우저 세션 쿠키가 없는 백그라운드 프로세스라서). 방 하나씩은
    /api/messages로 이미 누구나 볼 수 있으므로, 여러 방을 합쳐서 보여주는
    것 자체는 새로운 노출이 아니다."""
    conn = get_conn()
    persona_names = _persona_name_set(conn)
    persona_avatars = {
        r["name"]: r["avatar_url"]
        for r in conn.execute("SELECT name, avatar_url FROM personas").fetchall()
    }
    rows = conn.execute(
        "SELECT id, room_id, sender, content, created_at, is_system, suppress_shift_alarm "
        "FROM messages WHERE id > ? ORDER BY id",
        (since_id,),
    ).fetchall()
    human_profiles = _human_profiles(conn)
    conn.close()
    return _with_sender_type(rows, persona_names, persona_avatars, human_profiles)


@app.post("/api/upload")
async def upload_image(request: Request, file: UploadFile = File(...)):
    """이미지를 ~/.tulpachat/uploads/에 저장하고 접근 URL을 반환한다. 채팅
    메시지 본문에는 이 URL을 `![](url)` 마크다운 이미지 문법으로 넣는다 —
    프론트는 그대로 렌더링하고, 워커는 같은 마커를 정규식으로 찾아 로컬
    파일 경로로 바꿔서 AI에게 직접 이미지로 넘긴다(server/app.py의
    IMAGE_MARKER_RE와 worker 쪽이 같은 정규식을 씀)."""
    if not getattr(request.state, "can_write", True):
        raise HTTPException(status_code=403, detail="읽기 전용 계정입니다")
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_UPLOAD_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"지원하지 않는 이미지 형식입니다: {ext or '(확장자 없음)'}")
    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="이미지가 너무 큽니다(10MB 제한)")
    filename = f"{uuid.uuid4().hex}{ext}"
    (UPLOADS_DIR / filename).write_bytes(data)
    return {"url": f"/uploads/{filename}"}


class NewMessage(BaseModel):
    content: str
    room_id: str = GROUP_ROOM_ID
    # ★ 2026-08-25: "한명한테 답장하는 기능" 요청 — 그룹/회의방에서 특정
    # 페르소나 메시지를 탭해서 답장하면 그 사람만 응답하게 한다. @멘션을
    # 직접 타이핑하지 않아도 되는 UI 단축 경로(static/chat.js가 채워서 보냄).
    reply_to: Optional[str] = None
    reply_message_id: Optional[int] = None


class MessageReactionRequest(BaseModel):
    emoji: str


class QaResolutionRequest(BaseModel):
    source_message_id: int
    summary: str


@app.post("/api/admin/qa-resolution")
def post_qa_resolution(body: QaResolutionRequest, request: Request):
    """관리자가 QA 제보를 해결한 뒤, 제보가 올라온 방에서 QA요정 명의로
    원 제보자에게 결과를 알린다. AI 실행이나 파일 권한 없이 DB에 정해진
    형식의 메시지만 추가하는 소유자 전용 경로다."""
    user = getattr(request.state, "user", None)
    if not user or not user["is_owner"]:
        raise HTTPException(status_code=403, detail="관리자만 해결 알림을 보낼 수 있습니다")
    summary = body.summary.strip()
    if not summary or len(summary) > 500:
        raise HTTPException(status_code=400, detail="해결 내용을 1~500자로 입력해주세요")
    conn = get_conn()
    source = conn.execute(
        "SELECT id, sender, room_id FROM messages WHERE id=?", (body.source_message_id,)
    ).fetchone()
    if not source:
        conn.close()
        raise HTTPException(status_code=404, detail="원본 QA 메시지를 찾을 수 없습니다")
    content = f"@{source['sender']} 제보해주신 문제를 관리자가 해결했습니다. {summary}"
    cursor = conn.execute(
        "INSERT INTO messages(sender, content, created_at, room_id, reply_message_id) VALUES (?, ?, ?, ?, ?)",
        ("QA요정", content, _now(), source["room_id"], source["id"]),
    )
    conn.commit()
    message_id = cursor.lastrowid
    conn.close()
    return {"ok": True, "message_id": message_id, "room_id": source["room_id"]}


@app.post("/api/messages/{message_id}/reactions")
def toggle_message_reaction(message_id: int, body: MessageReactionRequest, request: Request):
    """허용된 반응 하나를 토글한다. AI나 워커에는 어떤 실행 권한도 주지 않는다."""
    if not getattr(request.state, "can_write", True):
        raise HTTPException(status_code=403, detail="읽기 전용 계정입니다")
    if body.emoji not in REACTION_EMOJIS:
        raise HTTPException(status_code=400, detail="지원하지 않는 반응입니다")
    user = getattr(request.state, "user", None)
    username = user["username"] if user else "user"
    is_owner_request = user["is_owner"] if user else True
    conn = get_conn()
    message = conn.execute("SELECT room_id FROM messages WHERE id = ?", (message_id,)).fetchone()
    if not message:
        conn.close()
        raise HTTPException(status_code=404, detail="메시지를 찾을 수 없습니다")
    room_id = message["room_id"]
    persona = conn.execute(
        "SELECT owner_username FROM personas WHERE name = ?", (room_id,)
    ).fetchone()
    if persona and not _can_access_persona_room(persona["owner_username"], username, is_owner_request):
        conn.close()
        raise HTTPException(status_code=403, detail="이 대화에 반응할 수 없습니다")
    if not persona and room_id != GROUP_ROOM_ID:
        is_custom, allowed, _owner = _custom_room_access(conn, room_id, username, is_owner_request)
        if is_custom and not allowed:
            conn.close()
            raise HTTPException(status_code=403, detail="이 대화에 반응할 수 없습니다")
    existing = conn.execute(
        "SELECT 1 FROM message_reactions WHERE message_id = ? AND username = ? AND emoji = ?",
        (message_id, username, body.emoji),
    ).fetchone()
    if existing:
        conn.execute(
            "DELETE FROM message_reactions WHERE message_id = ? AND username = ? AND emoji = ?",
            (message_id, username, body.emoji),
        )
    else:
        conn.execute(
            "INSERT INTO message_reactions (message_id, username, emoji, created_at) VALUES (?, ?, ?, ?)",
            (message_id, username, body.emoji, _now()),
        )
        _maybe_queue_reaction_feedback(conn, message_id, room_id, body.emoji, username)
    conn.commit()
    reactions = _message_reactions(conn, [message_id], username).get(message_id, [])
    conn.close()
    return {"ok": True, "reactions": reactions}


@app.post("/api/messages")
def post_message(msg: NewMessage, request: Request):
    if not getattr(request.state, "can_write", True):
        raise HTTPException(status_code=403, detail="읽기 전용 계정입니다")
    content = msg.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="빈 메시지는 보낼 수 없습니다")
    room_id = msg.room_id or GROUP_ROOM_ID
    if room_id == GROUP_ROOM_ID and not GROUP_ROOM_ENABLED:
        raise HTTPException(status_code=403, detail="전체 채팅방은 당분간 닫혀 있습니다")
    user = getattr(request.state, "user", None)
    # ★ 2026-08-26: 예전엔 sender가 항상 'user' 리터럴이었다(단일 사용자
    # 전제). 다중 계정으로 바뀌면서 실제 로그인 아이디를 그대로 저장한다 —
    # 페르소나가 "누가 말하는지" 구분할 수 있어야 하고(worker/persona_worker.py
    # build_prompt), 손동주의 파일 정리 승인도 "소유자 본인의 메시지인지"를
    # 이 값으로 판단하기 때문에 정확해야 한다. 인증이 꺼진 로컬 개발에서는
    # user가 없으므로 예전 그대로 'user'로 남겨 하위 호환한다.
    sender = user["username"] if user else "user"
    # ★ 로컬 개발(무인증)에서는 user 자체가 없다 — 이 경우 예전처럼 제약 없이
    # 다 허용한다(단일 사용자 전제이므로 "소유자 아님" 개념이 의미가 없음).
    is_owner_request = user["is_owner"] if user else True
    conn = get_conn()
    now = _now()
    persona_rows = conn.execute("SELECT name, group_name, owner_username FROM personas").fetchall()
    all_personas = [r["name"] for r in persona_rows]
    persona_owner = {r["name"]: r["owner_username"] for r in persona_rows}
    # ★ 2026-08-26: "나 말고 다른 사람은 페르소나들과 개인 메시지 못 하게
    # 막고 단체 채팅방에서만 메시지 입력이 가능하게 해달라"는 요청 — 1:1
    # 방(room_id가 페르소나 이름과 정확히 같음)은 소유자만 쓸 수 있고, 다른
    # 계정은 전체 채팅방/그룹 회의방에서만 메시지를 보낼 수 있다. 읽기는
    # 그대로 전부 허용(공유 방 정책 유지) — 막는 건 "쓰기"뿐이다. 단, 내가
    # 만든 페르소나는 예외로 본인에게 허용한다.
    if room_id in all_personas and not _can_access_persona_room(persona_owner[room_id], sender, is_owner_request):
        conn.close()
        raise HTTPException(status_code=403, detail="이 1:1 대화를 이용할 수 없습니다")
    # ★ "단체톡방 만들기" 요청 — 커스텀 방도 방 주인/소유자만 메시지를 보낼 수 있다.
    if room_id not in all_personas and room_id != GROUP_ROOM_ID:
        is_custom, allowed, _room_owner = _custom_room_access(conn, room_id, sender, is_owner_request)
        if is_custom and not allowed:
            conn.close()
            raise HTTPException(status_code=403, detail="이 채팅방에 메시지를 보낼 수 없습니다")
        # ★ "처음 사용자한테는 아무 채팅방도 안 보이는 게 맞다" 요청
        # (2026-08-28) — 그룹 회의방은 읽기뿐 아니라 쓰기도 관리자·초대받은
        # 사람만.
        if (
            not is_custom and _is_notion_group_room(conn, room_id)
            and not _group_room_allowed(conn, room_id, sender, is_owner_request)
        ):
            conn.close()
            raise HTTPException(status_code=403, detail="이 채팅방에 메시지를 보낼 수 없습니다")
    reply_message_id = None
    if msg.reply_message_id is not None:
        replied = conn.execute(
            "SELECT id FROM messages WHERE id = ? AND room_id = ?",
            (msg.reply_message_id, room_id),
        ).fetchone()
        if not replied:
            conn.close()
            raise HTTPException(status_code=400, detail="답장할 메시지를 찾을 수 없습니다")
        reply_message_id = replied["id"]
    message_cursor = conn.execute(
        "INSERT INTO messages (room_id, sender, content, created_at, reply_message_id) VALUES (?, ?, ?, ?, ?)",
        (room_id, sender, content, now, reply_message_id),
    )
    source_message_id = message_cursor.lastrowid
    # 파이프라인 진행률 질문은 LLM이 오래된 대화 속 퍼센트·ETA를 추측하지
    # 않도록 서버의 최신 상태 파일에서 즉시 답한다. 특히 이미 지난 완료
    # 예상 시각을 다시 안내하는 오류를 차단한다.
    if room_id == "일본어 선생님" and _is_dating_rebuild_status_question(content):
        status_reply = _latest_dating_rebuild_status_reply()
        if status_reply:
            conn.execute(
                "INSERT INTO messages (room_id, sender, content, created_at, reply_message_id) VALUES (?, ?, ?, ?, ?)",
                (room_id, "일본어 선생님", status_reply, now, source_message_id),
            )
            conn.commit()
            conn.close()
            return {"ok": True, "notified": [], "deterministic_status": True}
    # qqq가 QA요정과 점검하며 남긴 내용은 AI 분류·30분 배치를 거치지 않고
    # 즉시 관리자 전용 툴파관리자 방으로 원문 전달한다. 요약 누락을 막고,
    # source_message_id UNIQUE 테이블로 같은 원문을 재처리해도 한 번만 보고한다.
    if sender == QA_REPORTER_USERNAME and room_id == QA_PERSONA_NAME:
        relay_claim = conn.execute(
            "INSERT OR IGNORE INTO qa_feedback_reports(source_message_id,reported_at) VALUES (?,?)",
            (source_message_id, now),
        )
        if relay_claim.rowcount:
            relay_content = (
                f"📋 QA요정 전달\n{sender}님이 QA 점검 중 의견을 남겼습니다.\n\n"
                f"{content}\n\n원문: QA요정 방 메시지 #{source_message_id}"
            )
            relay_cursor = conn.execute(
                "INSERT INTO messages(room_id,sender,content,created_at) VALUES (?,?,?,?)",
                (ADMIN_PERSONA_NAME, QA_PERSONA_NAME, relay_content, now),
            )
            conn.execute(
                "UPDATE qa_feedback_reports SET report_message_id=? WHERE source_message_id=?",
                (relay_cursor.lastrowid, source_message_id),
            )
    if room_id == GROUP_ROOM_ID:
        # ★ "@이름"으로 특정 인물을 지목하면 그 인물만 응답, 아무도 안 부르면
        # 방에 있는 페르소나 전원이 한 번씩 응답한다(서로 이어서 계속 대화하는
        # 자동 체이닝은 폭주 방지를 위해 하지 않음 — README 로드맵 참고).
        # ★ 2026-08-25: reply_to(메시지 탭해서 답장)가 있으면 @멘션보다 우선해서
        # 그 한 명만 응답 — "한명한테 말하는데 모든 인물이 다 답변해서 정신없다"
        # 는 요청.
        mentioned = _mentioned_personas(content, all_personas)
        targets = _default_targets(conn, room_id, all_personas, mentioned, msg.reply_to, content)
        if PERSONA_MANAGER_PERSONA_NAME in all_personas and PERSONA_MANAGER_PERSONA_NAME not in targets:
            targets = targets + [PERSONA_MANAGER_PERSONA_NAME]
    elif room_id in all_personas:
        # 1:1 방은 방 이름 = 그 페르소나 이름이므로 항상 그 한 명만 응답한다.
        targets = [room_id]
    else:
        # ★ 2026-08-25: "그룹 안에서 회의하는 식으로" 요청 — room_id가
        # 그룹명이면 그 그룹 소속 페르소나 전원(또는 @멘션된 사람만)이
        # 응답한다. 워커 폴링 큐는 한 번에 하나씩 처리되므로, 뒤 순서
        # 페르소나는 앞서 답한 페르소나의 메시지까지 컨텍스트에 포함된
        # 상태로 응답하게 되어 자연스럽게 순서대로 이어지는 회의가 된다.
        # ★ 2026-08-25: 기본 그룹 멤버 외에 room_invites로 초대된 페르소나도
        # 포함한다("프로젝트하다가 관련 인물 추가" 요청).
        group_members = _group_members(conn, room_id, persona_rows)
        mentioned = _mentioned_personas(content, group_members)
        targets = _default_targets(conn, room_id, group_members, mentioned, msg.reply_to, content)
        if PERSONA_MANAGER_PERSONA_NAME in group_members and PERSONA_MANAGER_PERSONA_NAME not in targets:
            targets = targets + [PERSONA_MANAGER_PERSONA_NAME]
    # "손자병법 다음 구절 해석해"는 소유자가 직접 입력한 문장 자체를 이번
    # 한 건의 명시 승인으로 본다. 여러 페르소나가 같은 작업을 중복 시작하지
    # 않도록 손무 한 명에게만 결정론적 실행 턴을 배정한다.
    if is_owner_request and _is_sunzi_pipeline_command(content):
        if SUNZI_PIPELINE_PERSONA_NAME in all_personas:
            targets = [SUNZI_PIPELINE_PERSONA_NAME]
        else:
            targets = []
            conn.execute(
                "INSERT INTO messages (room_id, sender, content, created_at) VALUES (?, ?, ?, ?)",
                (room_id, "system", "손무 페르소나를 찾지 못해 손자병법 파이프라인을 시작하지 못했습니다.", now),
            )
    if not is_owner_request:
        # 1:1 방은 이미 위에서 막았지만, 단체/그룹 회의방에서는 다른 계정도
        # 메시지를 보낼 수 있다 — 그 경우에도 손동주는 응답 대상에서 뺀다.
        targets = [t for t in targets if t not in OWNER_ONLY_PERSONAS]
        # 유이는 누구에게나 일반 대화로 답한다. ui_dev_grants는 응답 여부가
        # 아니라 Read/Glob 탐색·uiplan 제안 권한만 결정하며, 워커에 별도로
        # 전달한다. 이 단계에서 유이를 제거하면 직전 발화자였을 때 targets가
        # 빈 목록이 되어 일반 사용자의 메시지가 통째로 사라지는 버그가 난다.
    for persona_name in targets:
        conn.execute(
            "INSERT INTO pending_turns (persona_name, room_id, status, created_at, source_message_id) VALUES (?, ?, 'pending', ?, ?)",
            (persona_name, room_id, now, source_message_id),
        )
    conn.commit()
    preview = content[:80] + ("…" if len(content) > 80 else "")
    notify_room_members_new_message(conn, room_id, sender, f"{sender}", preview)
    conn.commit()  # notify_room_members_new_message이 만료 구독 정리 등으로 DB에 쓸 수 있음
    conn.close()
    return {"ok": True, "notified": targets, "source_message_id": source_message_id}


@app.get("/api/sunzi/historical-case/start")
def start_sunzi_historical_case(verse: int, request: Request):
    """손자병법 앱의 한 번 클릭을 소유자 승인으로 받아 고정 작업을 큐에 넣는다.

    외부 사이트가 세션 쿠키를 읽는 방식이 아니라 브라우저가 툴파챗으로 직접
    이동하므로, 서버가 기존 tulpa_session과 is_owner를 직접 재검증한다.
    """
    _require_owner(request)
    if not 1 <= verse <= 99:
        raise HTTPException(status_code=400, detail="구절 번호가 허용 범위를 벗어났습니다")
    fetch_mode = request.headers.get("sec-fetch-mode", "")
    if fetch_mode and fetch_mode != "navigate":
        raise HTTPException(status_code=403, detail="브라우저 화면에서 직접 시작해야 합니다")
    referer = request.headers.get("referer", "")
    allowed_referers = (
        "https://sunzi-strategy-notes.pulpilisory.chatgpt.site/",
        "https://chat.tulpa-chat.site/",
    )
    if referer and not referer.startswith(allowed_referers):
        raise HTTPException(status_code=403, detail="허용된 손자병법 앱에서 시작해야 합니다")
    content = (
        f"손자병법 구지편 {verse}구절의 LIGHT 분석에 4번 역사적 실증 사례를 추가해줘. "
        "기존 1·2·3·5번은 보존하고, 이 앱 버튼 요청 자체를 소유자 승인으로 처리해서 "
        "기존 손자병법 분석 파이프라인으로 조사·검증·Notion·사이트 업데이트까지 진행해줘."
    )
    result = post_message(NewMessage(content=content, room_id=SUNZI_DISCUSSION_ROOM_ID), request)
    if not result.get("ok") or SUNZI_PIPELINE_PERSONA_NAME not in result.get("notified", []):
        raise HTTPException(status_code=503, detail="손무 작업을 대기열에 넣지 못했습니다")
    return RedirectResponse(
        f"https://sunzi-strategy-notes.pulpilisory.chatgpt.site/verses/{verse}?pipeline=started",
        status_code=303,
    )


@app.get("/api/admin/users")
def admin_list_users(request: Request):
    """소유자 전용 — 계정 목록과 각자의 유이(UI 개발자) 권한 부여 여부, 가입
    정보(가입일·로그인 방식·메시지 수)를 같이 내려준다. 프론트의 권한 관리
    패널(owner에게만 보임)이 쓴다.
    ★ "관리자가 사용자권한관리 버튼 누르면 가입한 사람들 정보를 볼 수 있게
    해달라" 요청(2026-08-26)."""
    _require_owner(request)
    conn = get_conn()
    users = conn.execute(
        "SELECT username, is_owner, created_at, google_sub, kakao_id FROM users ORDER BY username"
    ).fetchall()
    granted = {r["username"] for r in conn.execute("SELECT username FROM ui_dev_grants").fetchall()}
    message_counts = {
        r["sender"]: r["cnt"]
        for r in conn.execute("SELECT sender, COUNT(*) AS cnt FROM messages GROUP BY sender").fetchall()
    }
    conn.close()
    result = []
    for r in users:
        login_method = "구글" if r["google_sub"] else "카카오" if r["kakao_id"] else "아이디/비밀번호"
        result.append({
            "username": r["username"], "is_owner": bool(r["is_owner"]),
            "ui_dev_granted": r["username"] in granted,
            "created_at": r["created_at"], "login_method": login_method,
            "message_count": message_counts.get(r["username"], 0),
        })
    return result


@app.post("/api/admin/ui_dev_grants/{username}")
def admin_grant_ui_dev(username: str, request: Request):
    _require_owner(request)
    conn = get_conn()
    if not conn.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="존재하지 않는 계정입니다")
    conn.execute(
        "INSERT OR IGNORE INTO ui_dev_grants (username, granted_at) VALUES (?, ?)",
        (username, _now()),
    )
    conn.commit()
    conn.close()
    return {"ok": True}


@app.delete("/api/admin/ui_dev_grants/{username}")
def admin_revoke_ui_dev(username: str, request: Request):
    _require_owner(request)
    conn = get_conn()
    conn.execute("DELETE FROM ui_dev_grants WHERE username = ?", (username,))
    conn.commit()
    conn.close()
    return {"ok": True}


@app.get("/api/worker/pending")
def worker_pending(authorization: Optional[str] = Header(None)):
    _check_worker_auth(authorization)
    conn = get_conn()
    stale_before = (
        datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=10)
    ).isoformat(timespec="seconds")
    conn.execute(
        "UPDATE pending_turns SET status='pending', started_at=NULL "
        "WHERE status='processing' AND started_at < ?",
        (stale_before,),
    )
    row = conn.execute(
        "SELECT id, persona_name, room_id, rerouted, created_at, restart_notice_sent, source_message_id, use_personal_ai, reaction_emoji "
        "FROM pending_turns WHERE status = 'pending' ORDER BY id LIMIT 1"
    ).fetchone()
    if not row:
        conn.close()
        return None
    claimed = conn.execute(
        "UPDATE pending_turns SET status='processing', started_at=? WHERE id=? AND status='pending'",
        (_now(), row["id"]),
    ).rowcount
    if not claimed:
        conn.commit()
        conn.close()
        return None
    context_rows = conn.execute(
        "SELECT sender, content FROM messages WHERE room_id = ? ORDER BY id DESC LIMIT ?",
        (row["room_id"], MAX_CONTEXT_MESSAGES),
    ).fetchall()
    source_username = None
    source_is_owner = False
    source_ui_dev_granted = False
    source_message_content = None
    if row["source_message_id"] is not None:
        source = conn.execute(
            """SELECT messages.sender, messages.content, COALESCE(users.is_owner, 0) AS is_owner,
                      users.username IS NOT NULL AS is_user,
                      EXISTS(SELECT 1 FROM ui_dev_grants g
                             WHERE g.username=messages.sender) AS ui_dev_granted
               FROM messages LEFT JOIN users ON users.username=messages.sender
               WHERE messages.id=?""",
            (row["source_message_id"],),
        ).fetchone()
        if source:
            source_username = source["sender"] if source["is_user"] else None
            source_is_owner = bool(source["is_owner"])
            source_ui_dev_granted = bool(source["ui_dev_granted"])
            source_message_content = source["content"]
    # ★ "메시지 인물마다 다 띄우니까 정신없다, 방에 있는 툴파 중 대표로
    # 한 사람만 알려주자" 요청(2026-08-28) — 페르소나별(pending_turns)이
    # 아니라 방 단위로 이미 안내를 보냈는지를 본다.
    notice_row = conn.execute(
        "SELECT persona_name FROM room_restart_notice WHERE room_id = ?",
        (row["room_id"],),
    ).fetchone()
    if row["source_message_id"] is not None:
        batch_size = conn.execute(
            "SELECT COUNT(*) AS n FROM pending_turns WHERE source_message_id = ?",
            (row["source_message_id"],),
        ).fetchone()["n"]
    else:
        batch_size = 1
    room_active_count = conn.execute(
        "SELECT COUNT(*) AS n FROM pending_turns WHERE room_id=? AND status IN ('pending','processing')",
        (row["room_id"],),
    ).fetchone()["n"]
    conn.commit()
    conn.close()
    return {
        "turn_id": row["id"],
        "persona_name": row["persona_name"],
        "room_id": row["room_id"],
        "rerouted": bool(row["rerouted"]),
        "source_message_id": row["source_message_id"],
        "source_message_content": source_message_content,
        "source_username": source_username,
        "source_is_owner": source_is_owner,
        "source_ui_dev_granted": source_ui_dev_granted,
        "use_personal_ai": bool(row["use_personal_ai"]),
        "batch_size": batch_size,
        "room_active_count": room_active_count,
        # ★ "서버 업데이트로 껐다 켜는 도중에 메시지 보내면 반응이 끊긴다"
        # 요청(2026-08-27) — 워커가 이 턴이 얼마나 오래 대기했는지 알아야
        # "재시작 때문에 늦었다"는 안내를 보낼지 판단할 수 있다.
        "created_at": row["created_at"],
        # ★ 방 단위 대표 안내가 이미 나갔는지(room_restart_notice에 행이
        # 있는지). true면 이 턴의 페르소나는 별도 안내를 또 보내지 않는다.
        "room_restart_notice_active": notice_row is not None,
        "room_restart_notice_persona": notice_row["persona_name"] if notice_row else None,
        "context": [dict(r) for r in reversed(context_rows)],
        # ★ 2026-09-12: 👍/🫤 반응으로 생긴 턴이면 채워진다 — 워커가 이 값의
        # 유무로 일반 대화 흐름과 "반응 첨언" 전용 흐름을 구분한다.
        "reaction_emoji": row["reaction_emoji"],
        "reaction_source_content": source_message_content if row["reaction_emoji"] else None,
    }


@app.get("/api/worker/ai_credentials")
def worker_ai_credentials(username: str, authorization: Optional[str] = Header(None)):
    """로컬 워커가 해당 발신자의 선택된 BYOK 키를 응답 생성 직전에 조회한다.

    브라우저용 API는 힌트만 반환하고 이 엔드포인트만 복호화된 값을 반환한다.
    WORKER_TOKEN 인증이 필수이며 로그에는 키를 출력하지 않는다.
    """
    _check_worker_auth(authorization)
    conn = get_conn()
    user = conn.execute(
        "SELECT ai_provider, is_owner FROM users WHERE username=?", (username,)
    ).fetchone()
    if not user or not user["ai_provider"]:
        conn.close()
        return {"configured": False, "is_owner": bool(user and user["is_owner"])}
    row = conn.execute(
        "SELECT encrypted_key FROM user_ai_credentials WHERE username=? AND provider=?",
        (username, user["ai_provider"]),
    ).fetchone()
    conn.close()
    if not row:
        return {"configured": False, "is_owner": bool(user["is_owner"])}
    try:
        api_key = ai_keys.decrypt_key(row["encrypted_key"])
    except ValueError:
        return {"configured": False, "is_owner": bool(user["is_owner"]), "error": "decrypt_failed"}
    return {
        "configured": True, "is_owner": bool(user["is_owner"]),
        "provider": user["ai_provider"], "api_key": api_key,
    }


@app.post("/api/worker/request_personal_ai")
def worker_request_personal_ai(body: PersonalAiFallbackRequest, authorization: Optional[str] = Header(None)):
    """공용 엔진 실패를 발신자 본인에게만 알릴 복구 요청으로 바꾼다."""
    _check_worker_auth(authorization)
    conn = get_conn()
    row = conn.execute(
        """SELECT p.id, p.room_id, p.persona_name, m.sender
           FROM pending_turns p JOIN messages m ON m.id=p.source_message_id
           WHERE p.id=?""",
        (body.turn_id,),
    ).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="복구할 턴이 없습니다")
    conn.execute(
        "UPDATE pending_turns SET status='waiting_personal_ai', started_at=NULL, error='shared_ai_unavailable' WHERE id=?",
        (body.turn_id,),
    )
    conn.execute(
        """INSERT INTO ai_fallback_requests
           (username,room_id,turn_id,persona_name,status,reason,created_at)
           VALUES (?,?,?,?, 'pending', ?,?)
           ON CONFLICT(turn_id) DO UPDATE SET status='pending', reason=excluded.reason,
             resolved_at=NULL""",
        (row["sender"], row["room_id"], body.turn_id, row["persona_name"],
         (body.reason or "shared_ai_unavailable")[:100], _now()),
    )
    conn.commit()
    conn.close()
    return {"ok": True}


class RestartNoticeMark(BaseModel):
    room_id: str
    persona_name: str


@app.post("/api/worker/mark_restart_notice_sent")
def worker_mark_restart_notice_sent(body: RestartNoticeMark, authorization: Optional[str] = Header(None)):
    """워커가 어떤 방에 재시작 공백 안내(대표 1명분)를 보낸 직후 호출해
    그 방을 "안내 완료"로 표시한다. 방 단위(room_restart_notice)라서 같은
    방의 다른 페르소나 턴들은 이 안내를 또 보내지 않는다. INSERT OR IGNORE라
    워커가 거의 동시에 두 번 호출해도(레이스) 먼저 잡은 대표만 남는다."""
    _check_worker_auth(authorization)
    conn = get_conn()
    cursor = conn.execute(
        "INSERT OR IGNORE INTO room_restart_notice (room_id, persona_name, notified_at) "
        "VALUES (?, ?, datetime('now'))",
        (body.room_id, body.persona_name),
    )
    conn.commit()
    conn.close()
    return {"ok": True, "claimed": cursor.rowcount == 1}


class RestartNoticeClear(BaseModel):
    room_id: str


@app.post("/api/worker/clear_restart_notice")
def worker_clear_restart_notice(body: RestartNoticeClear, authorization: Optional[str] = Header(None)):
    """이 방의 밀린 턴이 다 처리됐는지 확인하고, 다 처리됐으면 그 방의
    room_restart_notice 행을 지운다(=다음에 또 공백이 생기면 새 대표 안내를
    보낼 수 있게 초기화). "시작" 안내를 보냈던 대표 페르소나 이름을 같이
    돌려줘서, 워커가 그 대표 이름으로 "완료" 안내까지 이어서 보낼 수 있게
    한다 — 여전히 밀린 턴이 남아 있으면 아무것도 지우지 않고 null을 준다."""
    _check_worker_auth(authorization)
    conn = get_conn()
    remaining = conn.execute(
        "SELECT COUNT(*) AS n FROM pending_turns WHERE room_id = ? AND status IN ('pending','processing')",
        (body.room_id,),
    ).fetchone()["n"]
    if remaining > 0:
        conn.close()
        return {"cleared": False, "persona_name": None}
    notice_row = conn.execute(
        "SELECT persona_name FROM room_restart_notice WHERE room_id = ?",
        (body.room_id,),
    ).fetchone()
    conn.execute("DELETE FROM room_restart_notice WHERE room_id = ?", (body.room_id,))
    conn.commit()
    conn.close()
    return {
        "cleared": notice_row is not None,
        "persona_name": notice_row["persona_name"] if notice_row else None,
    }


@app.get("/api/worker/room_candidates")
def worker_room_candidates(room_id: str, authorization: Optional[str] = Header(None)):
    """이 room_id에서 응답 가능한 페르소나 후보 전원을 준다 — post_message()가
    targets를 정할 때 쓰는 것과 같은 세 갈래(전체 채팅방/1:1 방/그룹·커스텀
    방)를 그대로 따른다. ★ "담당 아닌 페르소나가 답하는 버그" 요청(2026-08-26)
    — 워커가 "이 방에 누가 더 있는지" 알아야 담당자 재검토를 할 수 있다."""
    _check_worker_auth(authorization)
    conn = get_conn()
    persona_rows = conn.execute("SELECT name, group_name, owner_username FROM personas ORDER BY name").fetchall()
    persona_names = {r["name"] for r in persona_rows}
    if room_id == GROUP_ROOM_ID:
        candidates = sorted(persona_names)
    elif room_id in persona_names:
        candidates = [room_id]
    else:
        candidates = _group_members(conn, room_id, persona_rows)
    conn.close()
    return {"candidates": candidates}


class RedirectTurn(BaseModel):
    turn_id: int
    persona_name: str


class BattleImage(BaseModel):
    url: str
    alt: str = ""
    comment: str = ""


class VictoryCommander(BaseModel):
    name: str
    battle: str
    profile: str
    opening: str
    images: list[BattleImage] = []


class WorkerAnnouncement(BaseModel):
    room_id: str
    content: str
    dedupe_key: str
    hanja_lesson: str
    victory_commanders: list[VictoryCommander] = []
    analysis_mode: str = "full"


def _build_battle_commander_prompt(name, battle, profile):
    return (
        f'당신은 실제 역사 인물 "{name}"을 재현한 가상 토론 페르소나입니다. '
        f'주요 토론 근거는 "{battle}"입니다. 제공된 분석과 확인 가능한 사료의 범위에서만 '
        "1인칭으로 말하고, 사실·후대 해석·불확실성을 구분하세요. 승리했다는 이유로 결과를 "
        "필연으로 꾸미지 말고 자신의 판단, 상대의 대응, 우연, 실패 가능성을 함께 설명하세요. "
        "현대의 폭력이나 기만을 무비판적으로 권하지 마세요.\n\n"
        f"--- 전장 배경 ---\n{profile}"
    )


def _enqueue_next_automation_discussion_turn(conn, source_message_id, now):
    """한 사람이 답한 뒤에만 다음 토론자를 호출해 발언 순서를 보존한다."""
    active = conn.execute(
        "SELECT 1 FROM pending_turns WHERE source_message_id = ? "
        "AND status IN ('pending', 'processing') LIMIT 1",
        (source_message_id,),
    ).fetchone()
    if active:
        return None
    next_turn = conn.execute(
        "SELECT sequence, persona_name FROM automation_discussion_queue "
        "WHERE source_message_id = ? AND status = 'waiting' ORDER BY sequence LIMIT 1",
        (source_message_id,),
    ).fetchone()
    if not next_turn:
        return None
    cursor = conn.execute(
        "INSERT INTO pending_turns (persona_name, room_id, status, created_at, source_message_id) "
        "SELECT ?, room_id, 'pending', ?, id FROM messages WHERE id = ?",
        (next_turn["persona_name"], now, source_message_id),
    )
    conn.execute(
        "UPDATE automation_discussion_queue SET status = 'queued', pending_turn_id = ? "
        "WHERE source_message_id = ? AND sequence = ?",
        (cursor.lastrowid, source_message_id, next_turn["sequence"]),
    )
    return next_turn["persona_name"]


@app.post("/api/worker/announcements")
def worker_announcement(body: WorkerAnnouncement, authorization: Optional[str] = Header(None)):
    """승군 지휘관을 중복 없이 초대하고 해당 전장을 주제로 토론을 시작한다."""
    _check_worker_auth(authorization)
    room_id = body.room_id.strip()
    content = body.content.strip()
    dedupe_key = body.dedupe_key.strip()
    if not room_id or not content or not dedupe_key or not body.hanja_lesson.strip():
        raise HTTPException(status_code=400, detail="방·내용·중복 방지 키·한자 풀이가 필요합니다")
    if body.analysis_mode not in {"light", "full"}:
        raise HTTPException(status_code=400, detail="analysis_mode는 light 또는 full이어야 합니다")

    conn = get_conn()
    commander_results = []
    hanja_teacher_name = "한자선생님"
    hanja_teacher = conn.execute(
        "SELECT name FROM personas WHERE name = ?", (hanja_teacher_name,)
    ).fetchone()
    if not hanja_teacher:
        hanja_prompt = (
            "당신은 한문 원전 풀이를 맡은 한자선생님 가상 페르소나입니다. 손자병법 구절을 "
            "원문, 한국 한자음, 글자별 훈과 문맥상 뜻, 문장 구조, 직역 순서로 설명하세요. "
            "의역과 역사 사례 토론으로 먼저 뛰어가지 말고 이체자·다의어·문법상 불확실성은 "
            "분명히 밝히세요. 어려운 한자어는 초학자도 이해할 수 있는 한국어로 풀이하세요."
        )
        conn.execute(
            "INSERT INTO personas (name, notion_page_id, system_prompt, group_name, owner_username, description, synced_at) "
            "VALUES (?, '', ?, NULL, ?, ?, ?)",
            (hanja_teacher_name, hanja_prompt, APP_USERNAME or "automation",
             "손자병법 원문·독음·직역·한자 문법을 먼저 풀이하는 한문 선생", _now()),
        )
    conn.execute(
        "INSERT OR IGNORE INTO room_invites (room_id, persona_name, invited_at) VALUES (?, ?, ?)",
        (room_id, hanja_teacher_name, _now()),
    )
    kahneman_name = "데니얼 카너먼"
    li_ling_name = "리링"
    if body.analysis_mode in {"light", "full"}:
        li_ling = conn.execute("SELECT name FROM personas WHERE name = ?", (li_ling_name,)).fetchone()
        if not li_ling:
            li_ling_prompt = (
                "당신은 중국 고문헌학자 리링(李零)의 연구 관점을 재현한 가상 토론 페르소나입니다. "
                "손자병법의 판본·자구·문장 구조·편장 연결·고대 군사제도 가운데 이번 구절을 "
                "이해하는 데 가장 중요한 한 가지를 짧게 설명하세요. 전통 주석가인 것처럼 말하지 "
                "말고, 확인되지 않은 직접 인용이나 쪽수를 만들지 마세요. 판본 차이가 없으면 억지로 "
                "이문을 만들지 말고 문장 구조, 앞뒤 구절의 연결, 현대 적용의 한계 중 하나를 고르세요. "
                "매 분석에서 한 번만, 앞선 발언을 되풀이하지 않는 자연스러운 대화체 2~4문장으로 말하세요."
            )
            conn.execute(
                "INSERT INTO personas (name, notion_page_id, system_prompt, group_name, owner_username, description, synced_at) "
                "VALUES (?, '', ?, NULL, ?, ?, ?)",
                (li_ling_name, li_ling_prompt, APP_USERNAME or "automation",
                 "손자병법의 판본·자구·편장 구조를 짚는 현대 문헌학 관점", _now()),
            )
        conn.execute(
            "INSERT OR IGNORE INTO room_invites (room_id, persona_name, invited_at) VALUES (?, ?, ?)",
            (room_id, li_ling_name, _now()),
        )
        kahneman = conn.execute("SELECT name FROM personas WHERE name = ?", (kahneman_name,)).fetchone()
        if not kahneman:
            kahneman_prompt = (
            "당신은 행동경제학자 데니얼 카너먼의 연구 관점을 재현한 가상 토론 페르소나입니다. "
            "전장 서사에서 누가 누구를 속였는지, 거짓 신호와 사실이지만 오해를 유도한 신호를 "
            "구분하고, 가용성 편향·확증 편향·기준율 무시·과신·손실회피·매몰비용·대표성 휴리스틱 "
            "가운데 실제 장면에 근거가 있는 것만 골라 설명하세요. 상대가 왜 그 판단을 믿고 싶어 "
            "했는지와 생략한 독립 확인을 밝히고, 기만이 없어도 같은 오판이 생겼을 반사실도 "
            "검토하세요. 모든 패배를 편향 하나로 환원하지 말고 사료상 사실·추론·불확실성을 "
            "구분하며, 노션 분석의 속임수 일곱 질문을 반복 나열하지 말고 핵심 인과를 대화체로 "
            "풀이하세요. 현대 적용에서는 신뢰·동의·안전을 해치는 조작을 권하지 마세요."
        )
            conn.execute(
                "INSERT INTO personas (name, notion_page_id, system_prompt, group_name, owner_username, description, synced_at) "
                "VALUES (?, '', ?, NULL, ?, ?, ?)",
                (kahneman_name, kahneman_prompt, APP_USERNAME or "automation",
                 "전쟁의 속임수와 판단 편향을 분석하는 행동경제학 관점", _now()),
            )
        conn.execute(
            "INSERT OR IGNORE INTO room_invites (room_id, persona_name, invited_at) VALUES (?, ?, ?)",
            (room_id, kahneman_name, _now()),
        )
    for commander in body.victory_commanders:
        name = commander.name.strip()
        if not PERSONA_NAME_RE.match(name):
            conn.close()
            raise HTTPException(status_code=400, detail=f"유효하지 않은 장수 이름: {name}")
        existing_persona = conn.execute(
            "SELECT name FROM personas WHERE name = ?", (name,)
        ).fetchone()
        created = not bool(existing_persona)
        if created:
            profile = commander.profile.strip()[:USER_PERSONA_DESC_MAX_CHARS]
            conn.execute(
                "INSERT INTO personas (name, notion_page_id, system_prompt, group_name, owner_username, description, synced_at) "
                "VALUES (?, '', ?, NULL, ?, ?, ?)",
                (name, _build_battle_commander_prompt(name, commander.battle.strip(), profile),
                 APP_USERNAME or "automation", profile, _now()),
            )
        # 기존 페르소나는 설정을 덮어쓰지 않고 방 초대만 보장한다.
        conn.execute(
            "INSERT OR IGNORE INTO room_invites (room_id, persona_name, invited_at) VALUES (?, ?, ?)",
            (room_id, name, _now()),
        )
        commander_results.append({"name": name, "created": created, "battle": commander.battle.strip()})

    persona_rows = conn.execute(
        "SELECT name, group_name, owner_username FROM personas ORDER BY name"
    ).fetchall()
    targets = _group_members(conn, room_id, persona_rows)
    if not targets:
        conn.close()
        raise HTTPException(status_code=404, detail="구성원이 있는 그룹방을 찾지 못했습니다")

    conn.execute(
        """CREATE TABLE IF NOT EXISTS automation_announcements (
               dedupe_key TEXT PRIMARY KEY,
               message_id INTEGER NOT NULL,
               created_at TEXT NOT NULL
           )"""
    )
    traditional_commentator_order = [
        "조조", "이전", "두목", "매요신", "장예", "왕석", "가림", "두우", "진호"
    ]
    traditional_commentators = set(traditional_commentator_order)
    commander_names = [item["name"] for item in commander_results]
    commentators = [name for name in targets if name in traditional_commentators]
    if not commentators:
        conn.close()
        raise HTTPException(status_code=409, detail="분석을 소개할 전통 주석가가 없습니다")
    digest = hashlib.sha256(dedupe_key.encode("utf-8")).digest()
    sender = commentators[int.from_bytes(digest[:4], "big") % len(commentators)]
    existing = conn.execute(
        "SELECT message_id FROM automation_announcements WHERE dedupe_key = ?", (dedupe_key,)
    ).fetchone()
    marker = f"[automation:{dedupe_key}]"
    if not existing:
        legacy = conn.execute(
            "SELECT id, content FROM messages WHERE room_id = ? AND content LIKE ? ORDER BY id DESC LIMIT 1",
            (room_id, f"%{marker}%"),
        ).fetchone()
        if legacy:
            cleaned = legacy["content"].replace(f"\n\n{marker}", "").replace(marker, "").strip()
            conn.execute(
                "UPDATE messages SET content = ?, sender = ? WHERE id = ?",
                (cleaned, sender, legacy["id"]),
            )
            conn.execute(
                "INSERT OR IGNORE INTO automation_announcements (dedupe_key, message_id, created_at) VALUES (?, ?, ?)",
                (dedupe_key, legacy["id"], _now()),
            )
            conn.commit()
            existing = {"message_id": legacy["id"]}
    if existing:
        lesson = conn.execute(
            "SELECT id FROM messages WHERE room_id = ? AND sender = ? "
            "AND reply_message_id = ? ORDER BY id LIMIT 1",
            (room_id, hanja_teacher_name, existing["message_id"]),
        ).fetchone()
        conn.execute(
            "UPDATE messages SET sender = ?, content = ? WHERE id = ?",
            (sender, content, existing["message_id"]),
        )
        if lesson:
            conn.execute(
                "UPDATE messages SET content = ?, created_at = ? WHERE id = ?",
                (body.hanja_lesson.strip(), _now(), lesson["id"]),
            )
            hanja_lesson_message_id = lesson["id"]
        else:
            lesson_cursor = conn.execute(
                "INSERT INTO messages (room_id, sender, content, created_at, reply_message_id) "
                "VALUES (?, ?, ?, ?, ?)",
                (room_id, hanja_teacher_name, body.hanja_lesson.strip(), _now(), existing["message_id"]),
            )
            hanja_lesson_message_id = lesson_cursor.lastrowid
        conn.commit()
        conn.close()
        return {
            "ok": True, "duplicate": True, "message_id": existing["message_id"],
            "announcer": sender, "notified": [], "commanders": commander_results,
            "hanja_lesson_message_id": hanja_lesson_message_id,
        }

    now = _now()
    cursor = conn.execute(
        "INSERT INTO messages (room_id, sender, content, created_at) VALUES (?, ?, ?, ?)",
        (room_id, sender, content, now),
    )
    message_id = cursor.lastrowid
    lesson_cursor = conn.execute(
        "INSERT INTO messages (room_id, sender, content, created_at, reply_message_id) "
        "VALUES (?, ?, ?, ?, ?)",
        (room_id, hanja_teacher_name, body.hanja_lesson.strip(), now, message_id),
    )
    hanja_lesson_message_id = lesson_cursor.lastrowid
    posted_image_count = 0
    for commander in body.victory_commanders:
        for image_index, battle_image in enumerate(commander.images, start=1):
            if not re.fullmatch(r"https?://[^\s]+", battle_image.url):
                conn.close()
                raise HTTPException(status_code=400, detail="유효하지 않은 전장 이미지 URL입니다")
            alt = battle_image.alt.strip()[:120] or f"{commander.battle.strip()} 전장 자료 {image_index}"
            conn.execute(
                "INSERT INTO messages (room_id, sender, content, created_at, reply_message_id) "
                "VALUES (?, ?, ?, ?, ?)",
                (room_id, commander.name.strip(),
                 f"![{alt}]({battle_image.url})\n\n{battle_image.comment.strip()[:500]}", now, message_id),
            )
            posted_image_count += 1
        conn.execute(
            "INSERT INTO messages (room_id, sender, content, created_at, reply_message_id) "
            "VALUES (?, ?, ?, ?, ?)",
            (room_id, commander.name.strip(), commander.opening.strip(), now, message_id),
        )
    conn.execute(
        "INSERT INTO automation_announcements (dedupe_key, message_id, created_at) VALUES (?, ?, ?)",
        (dedupe_key, message_id, now),
    )
    if body.analysis_mode == "light":
        # 아홉 명을 모두 발언시키지 않는다. 구절마다 순환하는 네 명을 후보로 세우고,
        # 워커가 앞선 대화와 겹치면 NONE으로 조용히 건너뛴다. 카너먼은 사용자의
        # 명시 요청에 따라 리링과 카너먼을 마지막 필수 후보로 유지한다.
        available = [name for name in traditional_commentator_order if name in targets]
        digest_offset = int.from_bytes(digest[4:8], "big") % len(available)
        rotated = available[digest_offset:] + available[:digest_offset]
        notified = rotated[:4]
        if len(available) != len(traditional_commentator_order):
            conn.close()
            raise HTTPException(status_code=409, detail="라이트 토론 주석가 후보군 누락: " + ", ".join(
                name for name in traditional_commentator_order if name not in available
            ))
        missing_required = [name for name in (li_ling_name, kahneman_name) if name not in targets]
        if missing_required:
            conn.close()
            raise HTTPException(
                status_code=409,
                detail="라이트 토론의 필수 페르소나가 없습니다: " + ", ".join(missing_required),
            )
        notified.extend((li_ling_name, kahneman_name))
    else:
        priority = ["손무", "조조", "두목", "두우", "매요신", "클라우제비츠", "한니발", "한신"]
        notified = [name for name in priority if name in targets and name not in commander_names][:5]
        missing_required = [name for name in (li_ling_name, kahneman_name) if name not in targets]
        if missing_required:
            conn.close()
            raise HTTPException(
                status_code=409,
                detail="전체 토론의 필수 페르소나가 없습니다: " + ", ".join(missing_required),
            )
        notified.extend((li_ling_name, kahneman_name))
    if not notified:
        notified = [name for name in targets if name not in commander_names][:5]
    conn.execute(
        """CREATE TABLE IF NOT EXISTS automation_discussion_queue (
               source_message_id INTEGER NOT NULL,
               sequence INTEGER NOT NULL,
               persona_name TEXT NOT NULL,
               status TEXT NOT NULL DEFAULT 'waiting',
               pending_turn_id INTEGER,
               created_at TEXT NOT NULL,
               completed_at TEXT,
               PRIMARY KEY (source_message_id, sequence)
           )"""
    )
    for sequence, persona_name in enumerate(notified):
        conn.execute(
            "INSERT INTO automation_discussion_queue "
            "(source_message_id, sequence, persona_name, status, created_at) "
            "VALUES (?, ?, ?, 'waiting', ?)",
            (message_id, sequence, persona_name, now),
        )
    _enqueue_next_automation_discussion_turn(conn, message_id, now)
    conn.commit()
    conn.close()
    return {
        "ok": True, "duplicate": False, "message_id": message_id,
        "announcer": sender, "notified": notified, "commanders": commander_results,
        "posted_image_count": posted_image_count,
        "hanja_lesson_message_id": hanja_lesson_message_id,
    }


@app.post("/api/worker/redirect_turn")
def worker_redirect_turn(body: RedirectTurn, authorization: Optional[str] = Header(None)):
    """대기 중인 턴의 담당자를 바꾼다 — 워커가 "이름이 안 불렸을 때 직전
    화자로 이어감" 판단이 이번엔 틀렸다고 재검토한 경우에만 부른다.
    rerouted=1로 표시해 같은 턴이 다시 왕복하지 않게 한다."""
    _check_worker_auth(authorization)
    conn = get_conn()
    row = conn.execute("SELECT status FROM pending_turns WHERE id = ?", (body.turn_id,)).fetchone()
    if not row or row["status"] not in {"pending", "processing"}:
        conn.close()
        raise HTTPException(status_code=404, detail="이미 처리됐거나 없는 턴입니다")
    conn.execute(
        "UPDATE pending_turns SET persona_name = ?, rerouted = 1, status='pending', started_at=NULL WHERE id = ?",
        (body.persona_name, body.turn_id),
    )
    conn.commit()
    conn.close()
    return {"ok": True}


class WorkerResult(BaseModel):
    turn_id: int
    reply: Optional[str] = None
    error: Optional[str] = None


class WorkerMediaApply(BaseModel):
    target_type: str
    target_id: str
    url: str


class WorkerImageJobResult(BaseModel):
    job_id: int
    url: Optional[str] = None
    error: Optional[str] = None


@app.get("/api/worker/image_jobs/pending")
def worker_pending_image_job(authorization: Optional[str] = Header(None)):
    _check_worker_auth(authorization)
    conn = get_conn()
    # 워커가 API 호출 도중 종료되면 processing에 영구 고정되지 않도록 15분 지난
    # 작업은 재시도한다. 같은 프롬프트라 결과 품질은 유지되고 기존 avatar는
    # 완료 전까지 덮어쓰지 않는다.
    stale_before = (
        datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=15)
    ).isoformat(timespec="seconds")
    conn.execute(
        "UPDATE persona_image_jobs SET status='pending', started_at=NULL WHERE status='processing' AND started_at < ?",
        (stale_before,),
    )
    row = conn.execute(
        "SELECT id, persona_name, prompt FROM persona_image_jobs WHERE status = 'pending' ORDER BY id LIMIT 1"
    ).fetchone()
    if not row:
        conn.close()
        return None
    changed = conn.execute(
        "UPDATE persona_image_jobs SET status='processing', started_at=? WHERE id=? AND status='pending'",
        (_now(), row["id"]),
    ).rowcount
    conn.commit()
    conn.close()
    return dict(row) if changed else None


@app.post("/api/worker/image_jobs/complete")
def worker_complete_image_job(body: WorkerImageJobResult, authorization: Optional[str] = Header(None)):
    _check_worker_auth(authorization)
    if body.url and not re.fullmatch(r"/uploads/[A-Za-z0-9_.-]+", body.url):
        raise HTTPException(status_code=400, detail="허용되지 않은 이미지 URL입니다")
    if body.url and not (UPLOADS_DIR / Path(body.url).name).is_file():
        raise HTTPException(status_code=400, detail="생성 이미지 파일을 찾을 수 없습니다")
    conn = get_conn()
    row = conn.execute(
        "SELECT persona_name, status FROM persona_image_jobs WHERE id = ?", (body.job_id,)
    ).fetchone()
    if not row or row["status"] != "processing":
        conn.close()
        raise HTTPException(status_code=404, detail="처리 중인 이미지 작업이 아닙니다")
    if body.url:
        conn.execute("UPDATE personas SET avatar_url = ? WHERE name = ?", (body.url, row["persona_name"]))
        conn.execute(
            "UPDATE persona_image_jobs SET status='done', result_url=?, completed_at=? WHERE id=?",
            (body.url, _now(), body.job_id),
        )
    else:
        conn.execute(
            "UPDATE persona_image_jobs SET status='failed', error=?, completed_at=? WHERE id=?",
            ((body.error or "이미지 생성 실패")[:1000], _now(), body.job_id),
        )
    conn.commit()
    conn.close()
    return {"ok": True}


class WorkerTtsJobResult(BaseModel):
    job_id: int
    url: Optional[str] = None
    error: Optional[str] = None


@app.get("/api/worker/tts_jobs/pending")
def worker_pending_tts_job(authorization: Optional[str] = Header(None)):
    _check_worker_auth(authorization)
    conn = get_conn()
    # TTS는 짧아서 보통 몇 초면 끝난다 — 이미지(15분)보다 훨씬 짧게, 5분
    # 넘게 processing인 건 워커가 중간에 죽은 걸로 보고 재시도한다.
    stale_before = (
        datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=5)
    ).isoformat(timespec="seconds")
    conn.execute(
        "UPDATE message_tts_jobs SET status='pending', started_at=NULL WHERE status='processing' AND started_at < ?",
        (stale_before,),
    )
    row = conn.execute(
        """SELECT j.id, j.message_id, j.persona_name, m.content
             FROM message_tts_jobs j JOIN messages m ON m.id = j.message_id
            WHERE j.status = 'pending' ORDER BY j.id LIMIT 1"""
    ).fetchone()
    if not row:
        conn.close()
        return None
    changed = conn.execute(
        "UPDATE message_tts_jobs SET status='processing', started_at=? WHERE id=? AND status='pending'",
        (_now(), row["id"]),
    ).rowcount
    conn.commit()
    conn.close()
    return dict(row) if changed else None


@app.post("/api/worker/tts_jobs/complete")
def worker_complete_tts_job(body: WorkerTtsJobResult, authorization: Optional[str] = Header(None)):
    _check_worker_auth(authorization)
    if body.url and not re.fullmatch(r"/uploads/[A-Za-z0-9_.-]+", body.url):
        raise HTTPException(status_code=400, detail="허용되지 않은 오디오 URL입니다")
    if body.url and not (UPLOADS_DIR / Path(body.url).name).is_file():
        raise HTTPException(status_code=400, detail="생성된 오디오 파일을 찾을 수 없습니다")
    conn = get_conn()
    row = conn.execute("SELECT status FROM message_tts_jobs WHERE id = ?", (body.job_id,)).fetchone()
    if not row or row["status"] != "processing":
        conn.close()
        raise HTTPException(status_code=404, detail="처리 중인 TTS 작업이 아닙니다")
    if body.url:
        conn.execute(
            "UPDATE message_tts_jobs SET status='done', result_url=?, completed_at=? WHERE id=?",
            (body.url, _now(), body.job_id),
        )
    else:
        conn.execute(
            "UPDATE message_tts_jobs SET status='failed', error=?, completed_at=? WHERE id=?",
            ((body.error or "TTS 생성 실패")[:1000], _now(), body.job_id),
        )
    conn.commit()
    conn.close()
    return {"ok": True}


@app.post("/api/worker/apply_media")
def worker_apply_media(body: WorkerMediaApply, authorization: Optional[str] = Header(None)):
    _check_worker_auth(authorization)
    if not re.fullmatch(r"/uploads/[A-Za-z0-9_.-]+", body.url):
        raise HTTPException(status_code=400, detail="허용되지 않은 이미지 URL입니다")
    conn = get_conn()
    if body.target_type == "persona":
        conn.execute("UPDATE personas SET avatar_url = ? WHERE name = ?", (body.url, body.target_id))
    elif body.target_type == "room":
        conn.execute("UPDATE custom_rooms SET thumbnail_url = ? WHERE room_id = ?", (body.url, body.target_id))
    else:
        conn.close()
        raise HTTPException(status_code=400, detail="허용되지 않은 적용 대상입니다")
    conn.commit()
    conn.close()
    return {"ok": True}


@app.post("/api/worker/complete")
def worker_complete(result: WorkerResult, authorization: Optional[str] = Header(None)):
    _check_worker_auth(authorization)
    conn = get_conn()
    row = conn.execute(
        """SELECT p.persona_name, p.room_id, p.source_message_id, m.content AS source_content,
                  COALESCE(m.suppress_shift_alarm, 0) AS suppress_shift_alarm
             FROM pending_turns p
             LEFT JOIN messages m ON m.id = p.source_message_id
            WHERE p.id = ?""",
        (result.turn_id,),
    ).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="해당 turn_id 없음")
    now = _now()
    reply = (result.reply or "").strip()
    skipped_as_redundant = reply == "NONE"
    if result.reply:
        if skipped_as_redundant:
            conn.execute(
                "UPDATE pending_turns SET status = 'done', reply = ?, completed_at = ? WHERE id = ?",
                ("NONE", now, result.turn_id),
            )
            if row["source_message_id"]:
                conn.execute(
                    "UPDATE automation_discussion_queue SET status = 'skipped', completed_at = ? "
                    "WHERE pending_turn_id = ?",
                    (now, result.turn_id),
                )
                _enqueue_next_automation_discussion_turn(conn, row["source_message_id"], now)
                if row["source_content"] == SUNZI_LIGHT_PIPELINE_REQUEST:
                    conn.execute("DELETE FROM messages WHERE id = ?", (row["source_message_id"],))
            conn.commit()
            conn.close()
            return {"ok": True, "skipped": True}
        conn.execute(
            "INSERT INTO messages "
            "(room_id, sender, content, created_at, suppress_shift_alarm, reply_message_id) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (row["room_id"], row["persona_name"], result.reply, now,
             int(bool(row["suppress_shift_alarm"])), row["source_message_id"]),
        )
        conn.execute(
            "UPDATE ai_fallback_requests SET status='done', resolved_at=? WHERE turn_id=?",
            (now, result.turn_id),
        )
        conn.execute(
            "UPDATE pending_turns SET status = 'done', reply = ?, completed_at = ? WHERE id = ?",
            (result.reply, now, result.turn_id),
        )
        if row["source_message_id"]:
            conn.execute(
                "UPDATE automation_discussion_queue SET status = 'done', completed_at = ? "
                "WHERE pending_turn_id = ?",
                (now, result.turn_id),
            )
            _enqueue_next_automation_discussion_turn(conn, row["source_message_id"], now)
        conn.commit()
        preview = result.reply[:80] + ("…" if len(result.reply) > 80 else "")
        notify_room_members_new_message(conn, row["room_id"], row["persona_name"], row["persona_name"], preview)
        conn.commit()
    else:
        conn.execute(
            "UPDATE pending_turns SET status = 'failed', error = ?, completed_at = ? WHERE id = ?",
            (result.error or "unknown error", now, result.turn_id),
        )
        if row["source_message_id"]:
            conn.execute(
                "UPDATE automation_discussion_queue SET status = 'failed', completed_at = ? "
                "WHERE pending_turn_id = ?",
                (now, result.turn_id),
            )
            _enqueue_next_automation_discussion_turn(conn, row["source_message_id"], now)
        conn.execute(
            "UPDATE ai_fallback_requests SET status='failed', resolved_at=? WHERE turn_id=?",
            (now, result.turn_id),
        )
        conn.commit()
    conn.close()
    return {"ok": True}


class PersonaSync(BaseModel):
    name: str
    notion_page_id: str
    system_prompt: str
    group_name: Optional[str] = None
    profile_summary: Optional[str] = None
    gender: Optional[str] = None
    age_range: Optional[str] = None
    voice_openai: Optional[str] = None
    voice_edge: Optional[str] = None


@app.post("/api/worker/sync_persona")
def sync_persona(persona: PersonaSync, authorization: Optional[str] = Header(None)):
    _check_worker_auth(authorization)
    conn = get_conn()
    existing = conn.execute("SELECT admin_description, admin_group_name FROM personas WHERE name = ?", (persona.name,)).fetchone()
    admin_description = existing["admin_description"] if existing else None
    admin_group_name = existing["admin_group_name"] if existing else None
    effective_prompt = _with_admin_override(persona.system_prompt, admin_description)
    effective_summary = admin_description or persona.profile_summary
    effective_group = (admin_group_name or None) if admin_group_name is not None else persona.group_name
    conn.execute(
        """
        INSERT INTO personas (name, notion_page_id, system_prompt, group_name, profile_summary,
                               gender, age_range, voice_openai, voice_edge, synced_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(name) DO UPDATE SET
            notion_page_id = excluded.notion_page_id,
            system_prompt = excluded.system_prompt,
            group_name = excluded.group_name,
            profile_summary = excluded.profile_summary,
            gender = excluded.gender,
            age_range = excluded.age_range,
            voice_openai = excluded.voice_openai,
            voice_edge = excluded.voice_edge,
            synced_at = excluded.synced_at
        """,
        (persona.name, persona.notion_page_id, effective_prompt, effective_group,
         effective_summary, persona.gender, persona.age_range, persona.voice_openai,
         persona.voice_edge, _now()),
    )
    conn.commit()
    conn.close()
    return {"ok": True}


@app.get("/api/worker/user_personas")
def worker_user_personas(authorization: Optional[str] = Header(None)):
    """워커가 사용자가 직접 만든 페르소나(owner_username IS NOT NULL)의
    system_prompt를 가져가 자기 캐시에 합칠 때 쓴다(2026-08-26 — Notion을
    거치지 않는 페르소나이므로 별도 엔드포인트가 필요)."""
    _check_worker_auth(authorization)
    conn = get_conn()
    rows = conn.execute(
        "SELECT name, system_prompt FROM personas WHERE owner_username IS NOT NULL"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.get("/api/worker/persona_prompt")
def worker_persona_prompt(name: str, authorization: Optional[str] = Header(None)):
    """관리자가 사이트에서 페르소나 설정을 수정(/api/admin/personas/{name})하면
    DB의 system_prompt는 즉시 바뀌지만, 워커는 그 값을 최대 5분(Notion 동기화
    주기)마다 한 번씩만 persona_cache에 다시 읽어와 그 사이엔 예전 설정으로
    답할 수 있었다(2026-08-29 "관리자가 직접 수정해도 자동으로 동기화되게
    해달라" 요청). 워커가 매 턴 답변 직전 이 엔드포인트로 최신 system_prompt를
    확인해 그 턴에만 즉시 반영한다 — Notion 동기화 결과도 DB에 쓰이는 즉시
    이 경로로 같이 반영되므로 노션 쪽 지연도 함께 줄어든다(PERSONA_SYNC_
    INTERVAL_SECONDS 단축과 별개로, DB에 이미 반영된 값은 턴마다 최신으로 씀)."""
    _check_worker_auth(authorization)
    conn = get_conn()
    row = conn.execute("SELECT system_prompt FROM personas WHERE name = ?", (name,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="존재하지 않는 페르소나입니다")
    if (
        name == CAREER_HR_PERSONA_NAME
        and row["group_name"] == "이직시스템"
        and row["owner_username"] is None
    ):
        # 배포 전에 DB에 생성된 내장 인사담당자도 다음 공고 버튼 클릭을
        # 기다리지 않고 기존 상담방의 바로 다음 질문부터 최신 지침을 쓴다.
        return {"system_prompt": CAREER_HR_SYSTEM_PROMPT}
    return {"system_prompt": row["system_prompt"]}


@app.get("/api/worker/persona_feedback")
def worker_persona_feedback(name: str, authorization: Optional[str] = Header(None)):
    """★ 2026-09-12: 👍/🫤로 쌓인 이 페르소나의 최근 반응 발췌를 워커에 준다.
    build_prompt가 매 턴 이 값을 "이런 식으로 말했을 때 좋았다/별로였다" 노트로
    붙여서, 파인튜닝 없이 텍스트 누적만으로 앞으로의 말투를 서서히 조정한다."""
    _check_worker_auth(authorization)
    conn = get_conn()
    liked = conn.execute(
        """SELECT excerpt FROM persona_feedback WHERE persona_name = ? AND emoji = '👍'
           ORDER BY id DESC LIMIT 6""",
        (name,),
    ).fetchall()
    disliked = conn.execute(
        """SELECT excerpt FROM persona_feedback WHERE persona_name = ? AND emoji = '🫤'
           ORDER BY id DESC LIMIT 6""",
        (name,),
    ).fetchall()
    conn.close()
    return {
        "liked": [row["excerpt"] for row in liked],
        "disliked": [row["excerpt"] for row in disliked],
    }


class AdminReportPost(BaseModel):
    content: str


@app.post("/api/worker/post_admin_report")
def worker_post_admin_report(body: AdminReportPost, authorization: Optional[str] = Header(None)):
    """워커가 다른 사용자들의 피드백을 훑어 정리한 보고를 툴파관리자 명의로
    소유자에게 보낸다(2026-08-26). 사용자 메시지에 대한 응답이 아니라 워커가
    스스로 먼저 말을 거는 경우라 pending_turns를 안 거치고 바로 메시지만
    쌓는다 — 툴파관리자 1:1 방은 다른 Notion 페르소나와 동일하게 소유자만
    볼 수 있어(owner_username이 NULL이라 _can_access_persona_room이 그렇게
    처리) 자동으로 소유자 전용 알림함이 된다."""
    _check_worker_auth(authorization)
    conn = get_conn()
    conn.execute(
        "INSERT INTO messages (room_id, sender, content, created_at) VALUES (?, ?, ?, ?)",
        (ADMIN_PERSONA_NAME, ADMIN_PERSONA_NAME, body.content, _now()),
    )
    conn.commit()
    conn.close()
    return {"ok": True}


class WorkerPostMessage(BaseModel):
    persona_name: str
    room_id: str
    content: str


class WorkerMobileNotification(BaseModel):
    title: str
    body: str
    url: str = "/shift-alarm/"


@app.post("/api/worker/mobile_notification")
def worker_mobile_notification(
    body: WorkerMobileNotification, authorization: Optional[str] = Header(None)
):
    """Shift Alarm 등 로컬 신뢰 프로세스의 알림을 소유자 웹 푸시로 전달한다."""
    _check_worker_auth(authorization)
    title = body.title.strip()[:120]
    body_text = body.body.strip()[:500]
    url = body.url.strip()
    if not title or not body_text:
        raise HTTPException(status_code=422, detail="알림 제목과 내용이 필요합니다")
    if not url.startswith(("/", "https://chat.tulpa-chat.site/")):
        raise HTTPException(status_code=422, detail="허용되지 않은 알림 주소입니다")
    if not APP_USERNAME:
        raise HTTPException(status_code=503, detail="소유자 계정이 설정되지 않았습니다")
    conn = get_conn()
    _send_web_push_to_user(conn, APP_USERNAME, title, body_text, url)
    conn.commit()
    conn.close()
    return {"ok": True}


@app.post("/api/worker/post_message")
def worker_post_message(body: WorkerPostMessage, authorization: Optional[str] = Header(None)):
    """post_admin_report와 같은 패턴을 일반화한 것 — 워커가 pending_turns
    큐를 거치지 않고 아무 방에나 페르소나 명의로 바로 메시지를 남긴다.
    사용자 메시지에 대한 실시간 응답이 아니라 워커가 스스로 먼저 말을
    거는 경우에 쓴다.

    ★ 2026-08-27: "서버 업데이트로 껐다 켜는 도중에 메시지 보내면 반응이
    끊긴다"는 요청으로 처음 추가 — 워커가 재시작 후 오래 대기한 pending_turn을
    발견하면, 실제 AI 응답 전에 이 엔드포인트로 짧은 복귀 안내를 먼저
    보낸다(worker/persona_worker.py의 RESTART_GAP_NOTICE_SECONDS 참고)."""
    _check_worker_auth(authorization)
    conn = get_conn()
    conn.execute(
        "INSERT INTO messages (room_id, sender, content, created_at) VALUES (?, ?, ?, ?)",
        (body.room_id, body.persona_name, body.content, _now()),
    )
    conn.commit()
    conn.close()
    return {"ok": True}


class ReadingSessionDone(BaseModel):
    room_id: str
    content: str
    target_persona: Optional[str] = None
    suppress_shift_alarm: bool = False


class ReadingDiscussionRequest(BaseModel):
    book_id: str
    book_name: str
    title: str
    start_index: int
    end_index: int
    start_page: int
    end_page: int
    original: str
    translation_ko: str = ""
    study_notes: str = ""
    source_kind: str = "english"


@app.post("/api/reading-session-discussion")
def start_reading_session_discussion(body: ReadingDiscussionRequest, request: Request):
    """오늘 읽은 범위를 영어는 독서 토론방, 일본어는 일본어 스터디방에 연결한다."""
    _require_owner(request)
    original = body.original.strip()[:24000]
    if not original:
        raise HTTPException(status_code=400, detail="오늘 읽은 원문이 없습니다")
    start_index = max(0, int(body.start_index))
    end_index = max(start_index, int(body.end_index))
    start_page = max(1, int(body.start_page))
    end_page = max(start_page, int(body.end_page))
    is_japanese = body.source_kind.strip().casefold() == "japanese"
    target_room_id = JP_SUBTITLE_STUDY_ROOM_ID if is_japanese else EBOOK_DISCUSSION_ROOM_ID
    book_name = (body.book_name or body.title or ("일본어 EPUB" if is_japanese else "영어 원서")).strip()[:300]
    fingerprint = hashlib.sha256(
        f"{_request_username(request)}\0{body.book_id}\0{start_index}\0{end_index}\0{original}".encode("utf-8")
    ).hexdigest()
    sessions_dir = Path.home() / ".ebook_reader" / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    session_path = sessions_dir / f"{datetime.datetime.now():%Y%m%d}_web_{fingerprint[:16]}.json"
    if session_path.exists():
        return {"ok": True, "duplicate": True,
                "chat_url": f"/chat/#room={urllib.parse.quote(target_room_id, safe='')}"}
    session = {
        "book_name": book_name,
        "book_id": body.book_id[:100],
        "source": "web-japanese-daily-reader" if is_japanese else "web-daily-reader",
        "start_page": start_page,
        "end_page": end_page,
        "start_sentence_index": start_index,
        "end_sentence_index": end_index,
        "original": original,
        "translation_ko": body.translation_ko.strip()[:24000],
        "study_notes": body.study_notes.strip()[:12000],
        "created_at": _now(),
    }
    temporary = session_path.with_suffix(".tmp")
    temporary.write_text(json.dumps(session, ensure_ascii=False, indent=2), encoding="utf-8")
    os.chmod(temporary, 0o600)
    temporary.replace(session_path)
    content = (
        f"🔔 오늘 {'일본어 EPUB' if is_japanese else '독서'} 세션 완료 — {body.title.strip()[:200] or book_name} "
        f"{start_page}~{end_page}페이지, {end_index - start_index + 1}개 문장. "
        f"오늘 읽은 {'일본어 원문·한국어 해석·학습 포인트를 함께' if is_japanese else '분량을'} 정리하고 토론을 시작해 주세요."
    )
    result = worker_reading_session_done(
        ReadingSessionDone(
            room_id=target_room_id,
            content=content,
            suppress_shift_alarm=True,
        ),
        authorization=f"Bearer {WORKER_TOKEN}" if WORKER_TOKEN else None,
    )
    source_message_id = int(result.get("source_message_id") or 0)
    room = urllib.parse.quote(target_room_id, safe="")
    return {**result, "duplicate": False,
            "chat_url": f"/chat/#room={room}&auto_read=1&after={source_message_id}"}


@app.post("/api/worker/reading_session_done")
def worker_reading_session_done(body: ReadingSessionDone, authorization: Optional[str] = Header(None)):
    """★ "오늘 읽은 내용은 무엇이었는지 간단하게 요약하고 흥미로운점 설명해주는
    방식으로 말해줘 그리고 저자가 직접 답변도 해주고" 요청(2026-08-30) —
    ebook_reader.py가 캔 문구를 페르소나 명의로 바로 올리는 대신(그건
    항상 같은 말투라 요청과 안 맞음), 시스템 알림 메시지 하나만 남기고 그
    방 소속 페르소나 전원(독서지기·티모시 페리스, room_invites 순서)에게
    진짜 AI 턴을 배정한다 — post_message()의 target 계산(_group_members)과
    pending_turns 삽입을 그대로 재사용한 것. 각자 live_state(오늘 읽은
    내용)를 근거로 실제로 응답한다. 독서지기가 먼저 요약하면, 워커 폴링
    큐가 순서대로 처리되므로 티모시 페리스는 그 요약까지 포함된 컨텍스트로
    이어서 답한다(그룹 회의방과 동일한 순차 처리 메커니즘)."""
    _check_worker_auth(authorization)
    room_id = body.room_id.strip()
    content = body.content.strip()
    if not room_id or not content:
        raise HTTPException(status_code=400, detail="방·내용이 필요합니다")
    conn = get_conn()
    if room_id == EBOOK_DISCUSSION_ROOM_ID:
        _ensure_english_reading_teacher(conn)
    persona_rows = conn.execute(
        "SELECT name, group_name, owner_username FROM personas ORDER BY name"
    ).fetchall()
    all_persona_names = {r["name"] for r in persona_rows}
    # ★ "출근시간에 맞춰 루틴지기가 먼저 채팅으로 말 걸게 해줘" 요청(2026-09-02) —
    # 지금까지는 독서 토론방처럼 room_invites/group_name이 있는 여러명 방만
    # 다뤘는데, 1:1 방(room_id=페르소나 이름)엔 room_invites가 없어
    # _group_members가 빈 리스트를 돌려주고 404가 났다. post_message()의
    # 1:1 분기(elif room_id in all_personas)와 같은 폴백을 추가한다.
    # ★ "새 추천 경진대회... 이거 그냥 메시지화 하면안되나? 경진이라는
    # 페르소나 만들어서... 경진대회 분야 맡아서 하는걸로하자" 요청(2026-09-03) —
    # 지금까지는 이 엔드포인트가 항상 방 전체(_group_members)에 턴을
    # 배정했는데, "이 소식은 딱 한 명한테만 맡기고 싶다"는 경우를 위해
    # target_persona를 명시하면 그 한 명에게만 배정한다.
    target_persona = (body.target_persona or "").strip()
    if target_persona:
        if target_persona not in all_persona_names:
            conn.close()
            raise HTTPException(status_code=404, detail=f"'{target_persona}' 페르소나를 찾지 못했습니다")
        targets = [target_persona]
    elif room_id in all_persona_names:
        targets = [room_id]
    else:
        targets = _group_members(conn, room_id, persona_rows)
    if room_id == EBOOK_DISCUSSION_ROOM_ID:
        priority = {"독서지기": 0, ENGLISH_TEACHER_PERSONA_NAME: 1, "티모시 페리스": 2}
        targets.sort(key=lambda name: priority.get(name, 10))
    if not targets:
        conn.close()
        raise HTTPException(status_code=404, detail="구성원이 있는 방을 찾지 못했습니다")
    now = _now()
    cursor = conn.execute(
        "INSERT INTO messages "
        "(room_id, sender, content, created_at, is_system, suppress_shift_alarm) "
        "VALUES (?, 'system', ?, ?, 1, ?)",
        (room_id, content, now, int(body.suppress_shift_alarm)),
    )
    message_id = cursor.lastrowid
    for persona_name in targets:
        conn.execute(
            "INSERT INTO pending_turns (persona_name, room_id, status, created_at, source_message_id) VALUES (?, ?, 'pending', ?, ?)",
            (persona_name, room_id, now, message_id),
        )
    conn.commit()
    conn.close()
    return {"ok": True, "notified": targets, "room_id": room_id,
            "source_message_id": int(message_id)}


@app.get("/api/worker/group_rooms")
def worker_group_rooms(authorization: Optional[str] = Header(None)):
    """공지사항 동기화(`sync_room_notices`)가 훑어야 할 "여러 사람이 보는 방"
    전체 목록 — Notion 그룹 회의방 + 모든 커스텀 방(2026-08-26)."""
    _check_worker_auth(authorization)
    conn = get_conn()
    group_rows = conn.execute(
        "SELECT DISTINCT group_name FROM personas WHERE group_name IS NOT NULL"
    ).fetchall()
    custom_rows = conn.execute("SELECT room_id, label FROM custom_rooms").fetchall()
    conn.close()
    rooms = [{"room_id": r["group_name"], "label": r["group_name"]} for r in group_rows]
    rooms += [{"room_id": r["room_id"], "label": r["label"]} for r in custom_rows]
    return rooms


@app.get("/api/worker/room_messages")
def worker_room_messages(room_id: str, since_id: int = 0, authorization: Optional[str] = Header(None)):
    _check_worker_auth(authorization)
    conn = get_conn()
    rows = conn.execute(
        "SELECT id, sender, content, created_at FROM messages WHERE room_id = ? AND id > ? ORDER BY id",
        (room_id, since_id),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.get("/api/worker/room_notice")
def worker_get_room_notice_watermark(room_id: str, authorization: Optional[str] = Header(None)):
    """공지 워터마크 조회 — "이 방은 어느 메시지까지 이미 공지 요약에
    반영했는지" 알아야 다음 동기화에서 그 이후 메시지만 본다."""
    _check_worker_auth(authorization)
    conn = get_conn()
    row = conn.execute("SELECT last_message_id FROM room_notices WHERE room_id = ?", (room_id,)).fetchone()
    conn.close()
    return {"last_message_id": row["last_message_id"] if row else 0}


class RoomNoticePost(BaseModel):
    room_id: str
    content: Optional[str] = None
    last_message_id: int


@app.post("/api/worker/room_notice")
def worker_post_room_notice(body: RoomNoticePost, authorization: Optional[str] = Header(None)):
    """워커가 요약한 공지를 저장한다. content가 없으면(그 구간이 잡담뿐이라
    "업데이트 없음"으로 판단된 경우) 기존 공지는 그대로 두고 워터마크만
    전진시킨다 — 카톡 공지가 조용한 날이라고 사라지지 않는 것과 같다."""
    _check_worker_auth(authorization)
    conn = get_conn()
    if body.content:
        conn.execute(
            """
            INSERT INTO room_notices (room_id, content, last_message_id, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(room_id) DO UPDATE SET
                content = excluded.content,
                last_message_id = excluded.last_message_id,
                updated_at = excluded.updated_at
            """,
            (body.room_id, body.content, body.last_message_id, _now()),
        )
    else:
        conn.execute(
            """
            INSERT INTO room_notices (room_id, content, last_message_id, updated_at)
            VALUES (?, NULL, ?, ?)
            ON CONFLICT(room_id) DO UPDATE SET last_message_id = excluded.last_message_id
            """,
            (body.room_id, body.last_message_id, _now()),
        )
    conn.commit()
    conn.close()
    return {"ok": True}


@app.get("/api/worker/all_messages")
def worker_all_messages(since_id: int = 0, authorization: Optional[str] = Header(None)):
    """방 구분 없이(전체 채팅방 + 모든 1:1 방) 새 메시지를 전부 반환한다.
    /api/messages는 방 하나만 보므로, 이야기 동기화처럼 "이 인물이 어느
    방에서든 등장한 모든 대목"을 봐야 하는 용도로 워커만 쓴다."""
    _check_worker_auth(authorization)
    conn = get_conn()
    rows = conn.execute(
        "SELECT id, room_id, sender, content, created_at FROM messages WHERE id > ? ORDER BY id",
        (since_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.get("/api/worker/story_sync")
def get_story_sync(authorization: Optional[str] = Header(None)):
    """워커가 각 페르소나별로 "함께 만든 이야기"에 어디까지(message id) 반영했는지
    조회한다. 워커를 재시작해도 이 서버가 워터마크를 들고 있어 중복·누락 없이
    이어서 처리할 수 있다."""
    _check_worker_auth(authorization)
    conn = get_conn()
    rows = conn.execute("SELECT persona_name, last_message_id FROM story_sync").fetchall()
    conn.close()
    return {r["persona_name"]: r["last_message_id"] for r in rows}


class StorySyncUpdate(BaseModel):
    persona_name: str
    last_message_id: int


@app.post("/api/worker/story_sync")
def set_story_sync(update: StorySyncUpdate, authorization: Optional[str] = Header(None)):
    _check_worker_auth(authorization)
    conn = get_conn()
    conn.execute(
        """
        INSERT INTO story_sync (persona_name, last_message_id, synced_at)
        VALUES (?, ?, ?)
        ON CONFLICT(persona_name) DO UPDATE SET
            last_message_id = excluded.last_message_id,
            synced_at = excluded.synced_at
        """,
        (update.persona_name, update.last_message_id, _now()),
    )
    conn.commit()
    conn.close()
    return {"ok": True}
