"""Shift Alarm 메뉴바 타이틀 전용의 작은 순수 포맷 함수."""

import re


_EMOJI_RE = re.compile(
    "["
    "\U0001F1E6-\U0001F1FF"  # flags
    "\U0001F300-\U0001FAFF"  # pictographs, symbols, supplemental emoji
    "\u2300-\u23FF"
    "\u2600-\u27BF"
    "]"
)
_EMOJI_JOINERS_RE = re.compile(r"[\u200d\ufe0e\ufe0f\U0001F3FB-\U0001F3FF]")
_REMINDER_TOKEN_TEXT = {
    "☕": "카페", "💬": "학원연락", "🚿": "배수점검", "💇": "이발",
    "📚": "독서", "🎉": "동주휴무", "🪒": "코털", "💅": "손발톱",
    "🎧": "충전", "🧹": "카톡정리", "🛍️": "아울렛", "🚶": "2만보",
    "🧺": "빨래", "🗺️": "나들이", "🥩": "소고기", "🛢️": "엔진오일",
}
_PET_ACTIONS = {
    "엄마": "엄마에게 전화하기", "민준": "민준에게 전화하기",
    "동생": "동생에게 전화하기", "동찬": "동찬이 형에게 전화하기",
    "동주": "동주에게 전화하기", "카페": "카페에서 공부하기",
    "학원연락": "코딩학원에 연락하기", "배수점검": "화장실 배수 점검하기",
    "이발": "머리 깎기", "독서": "에이전틱 코딩 읽기",
    "동주휴무": "동주 휴무 확인하기", "코털": "코털 정리하기",
    "손발톱": "손발톱 정리하기", "충전": "이어폰 충전하기",
    "카톡정리": "카톡 정리하기", "아울렛": "아울렛 다녀오기",
    "2만보": "2만보 걷기", "빨래": "빨래 돌리기", "나들이": "나들이하기",
    "소고기": "소고기 구워 먹기", "엔진오일": "엔진오일 교체하기",
    "주간정리": "주간 마지막 루틴 하기",
}


def sanitize_menubar_reminder_token(token):
    """리마인더 의미 텍스트는 남기고 emoji/VS/ZWJ만 제거한다."""
    original = str(token).strip()
    text = _EMOJI_RE.sub("", original)
    text = _EMOJI_JOINERS_RE.sub("", text)
    text = " ".join(text.split())
    return text or _REMINDER_TOKEN_TEXT.get(original, "")


def friendly_pet_reminder_actions(tokens):
    """짧은 메뉴 토큰을 Pet이 말할 자연스러운 동작 표현으로 바꾼다."""
    actions = []
    for token in tokens:
        text = sanitize_menubar_reminder_token(token)
        if text:
            actions.append(_PET_ACTIONS.get(text, text))
    return actions


def format_menubar_storage_gb(value):
    """메뉴바 저장공간을 짧은 정수+G 형태로 표시한다."""
    if value is None:
        return ""
    return f"{int(round(float(value)))}G"


def menubar_status_tokens(shift, storage, codex, claude, thermal=""):
    """리마인더를 받지 않는 메뉴바 핵심 상태 토큰 순서를 고정한다."""
    return tuple(token for token in (shift, storage, codex, claude, thermal) if token)


def shared_emoji_semantic_token(label, cafe_label, day_last_label):
    """첫 이모지가 같은 ☕ 리마인더를 원문 identity로 구분한다."""
    if label == cafe_label:
        return "카페"
    if label == day_last_label:
        return "주간정리"
    return None


def build_pet_cards(
    shift_text, weather_icon, storage_gb, reminder_tokens, codex_token,
    claude_token, low_storage_gb, thermal_token="",
):
    """말풍선 폭에 맞춘 짧고 친절한 Alarm Pet 카드 문구를 만든다."""
    shift_code = str(shift_text).split("-", 1)[0]
    weather_line = {
        "雨": "비가 올 수 있어요. 우산 챙겨요!",
        "曇": "오늘은 흐릴 수 있어요.",
        "晴": "오늘은 맑을 예정이에요!",
    }.get(weather_icon, "날씨를 확인하고 있어요.")

    if storage_gb is None:
        storage_line = "남은 공간을 확인하고 있어요."
    elif storage_gb <= low_storage_gb:
        storage_line = f"공간이 {storage_gb}GB뿐이에요. 정리할까요?"
    else:
        storage_line = f"지금 {storage_gb}GB 남았어요."

    reminder_actions = friendly_pet_reminder_actions(reminder_tokens)
    if not reminder_actions:
        reminder_line = "오늘 리마인더는 모두 마쳤어요!"
    elif len(reminder_actions) <= 2:
        reminder_line = f"{' · '.join(reminder_actions)}가 남아 있어요."
    else:
        reminder_line = (
            f"{' · '.join(reminder_actions[:2])} 외 {len(reminder_actions) - 2}개가 남았어요."
        )

    ai_line = (
        f"Codex {codex_token or '-'}, Claude {claude_token or '-'} 사용했어요."
    )
    cards = [
        (f"오늘은 {shift_code} 근무예요", weather_line),
        ("💾 저장공간 알려드릴게요", storage_line),
        ("오늘의 리마인더 인지하셨나요?", reminder_line),
        ("🤖 AI 사용량이에요", ai_line),
    ]
    if thermal_token:
        cards.append(("🌡️ 잠깐 쉬어갈까요?", f"지금 열 상태는 {thermal_token}예요."))
    return cards
