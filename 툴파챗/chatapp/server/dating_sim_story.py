"""미연시(연애 시뮬레이션) 미니게임의 안전한 스토리 데이터.

★ 2026-09-15: "미연시 시스템 하나 만들어봤으면 좋겠어" 요청 — 데이터만 담는
모듈이다. 엔진 로직(선택 검증·호감도 계산·엔딩 판정)은 server/app.py의
/api/dating-sim/* 엔드포인트에 있다. 캐릭터를 늘리거나 이야기를 바꿀 때는
이 파일만 고치면 된다.

대사는 humanize-korean 스킬(light 경로, run_dir=_workspace/2026-09-15-001)로
한 차례 다듬은 결과다 — 의미·선택지 호감도 부호는 원안과 동일하고 말투만
자연스럽게 손봤다.
"""
import hashlib
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

CHARACTER_ID = "soi_cafe"
CHARACTER_NAME = "소이"
TOTAL_DAYS = 3

LOCATIONS = {
    "cafe": {"label": "카페", "emoji": "☕"},
    "park": {"label": "공원", "emoji": "🌳"},
    "school": {"label": "학교 앞", "emoji": "🏫"},
}

# scenes[day][location] = {"lines": [...], "choices": [{"text": str, "affection": int}, ...]}
# 선택지는 항상 2개, 순서 고정(0번=호감+, 1번=호감-) — app.py가 인덱스로 검증한다.
SCENES = {
    1: {
        "cafe": {
            "lines": [
                "어서 오세요... 어, 또 왔네요.",
                "아메리카노 맞죠? 이제 안 물어봐도 되겠어요.",
            ],
            "choices": [
                {"text": "네, 저 여기 단골 다 됐나 봐요.", "affection": 10},
                {"text": "그냥 아무거나 시킬게요.", "affection": -5},
            ],
        },
        "park": {
            "lines": [
                "(혼잣말) 날씨 진짜 좋다...",
                "어? 여기서 다 보네요. 산책하는 거예요?",
            ],
            "choices": [
                {"text": "네, 소이 씨도 산책 나온 거예요?", "affection": 10},
                {"text": "그냥 지나가는 길이었어요.", "affection": -5},
            ],
        },
        "school": {
            "lines": [
                "어, 이 시간에 여긴 웬일이에요?",
                "저 지금 알바 끝나고 집 가는 길인데.",
            ],
            "choices": [
                {"text": "혹시 저랑 같은 방향이면 같이 가도 돼요?", "affection": 10},
                {"text": "아, 그냥 지나가다가요.", "affection": -5},
            ],
        },
    },
    2: {
        "cafe": {
            "lines": [
                "오늘도 아메리카노? 취향 확고하네요.",
                "저는 사실 단 거 좋아하는데.",
            ],
            "choices": [
                {"text": "그럼 다음엔 단 것도 하나 시켜볼게요.", "affection": 10},
                {"text": "저는 원래 이런 스타일이라서요.", "affection": -5},
            ],
        },
        "park": {
            "lines": [
                "어제도 여기 있더니 오늘도 있네요.",
                "혹시... 저 보러 온 거예요?",
            ],
            "choices": [
                {"text": "티 났어요? 맞아요.", "affection": 10},
                {"text": "아니요, 그냥 우연이에요.", "affection": -5},
            ],
        },
        "school": {
            "lines": [
                "요즘 자주 마주치네요, 우리.",
                "나쁘지 않은데, 이 우연.",
            ],
            "choices": [
                {"text": "저도 그렇게 생각해요.", "affection": 10},
                {"text": "그런가요, 별생각 없었는데.", "affection": -5},
            ],
        },
    },
    3: {
        "cafe": {
            "lines": [
                "저기, 오늘 알바 끝나고 시간 있어요?",
                "그냥... 같이 뭐 좀 먹을까 해서요.",
            ],
            "choices": [
                {"text": "좋아요, 저도 마침 시간 있어요.", "affection": 10},
                {"text": "오늘은 좀 바빠서요.", "affection": -5},
            ],
        },
        "park": {
            "lines": [
                "매일 여기서 만나니까 이제 우리 산책 친구 같아요.",
                "친구... 그 이상이면 안 되는 거예요?",
            ],
            "choices": [
                {"text": "저도 그 이상이었으면 좋겠어요.", "affection": 10},
                {"text": "그냥 지금처럼 편한 게 좋아요.", "affection": -5},
            ],
        },
        "school": {
            "lines": [
                "그동안 자주 마주쳐서 좋았어요. 진짜로.",
                "이거... 인연이라고 해도 되는 거겠죠?",
            ],
            "choices": [
                {"text": "네, 저도 소이 씨랑 더 가까워지고 싶어요.", "affection": 10},
                {"text": "인연까지는 잘 모르겠지만, 좋은 사람인 건 알겠어요.", "affection": -5},
            ],
        },
    },
}

# affection 시작값 50, 선택당 +10/-5 3회 → 최고 80·최저 35.
# best>=75(전부 +), good>=60(2승1패), 그 외 normal.
ENDINGS = [
    {
        "id": "best", "min_affection": 75, "title": "베스트 엔딩",
        "lines": ["그동안 고마웠어요. 저... 계속 이렇게 지내고 싶어요."],
    },
    {
        "id": "good", "min_affection": 60, "title": "굿 엔딩",
        "lines": ["우리 이제 진짜 친구 같아요. 앞으로도 종종 봐요."],
    },
    {
        "id": "normal", "min_affection": 0, "title": "노멀 엔딩",
        "lines": ["짧았지만 즐거웠어요. 다음에 또 카페 놀러 오세요."],
    },
]


def resolve_ending(affection):
    for ending in ENDINGS:
        if affection >= ending["min_affection"]:
            return ending
    return ENDINGS[-1]


JAPANESE_EPUB_ROOT = Path("/Users/forrestdpark/Desktop/BlogImage/av완성작")
BOOK_STORY_RE = re.compile(r"^book:([0-9a-f]{20})$")


def _book_id(path):
    return hashlib.sha256(str(path.resolve()).encode()).hexdigest()[:20]


def _book_title(path):
    try:
        with zipfile.ZipFile(path) as archive:
            container = ET.fromstring(archive.read("META-INF/container.xml"))
            rootfile = next(node for node in container.iter() if node.tag.endswith("rootfile"))
            package = ET.fromstring(archive.read(rootfile.get("full-path")))
            title = next((node.text or "" for node in package.iter() if node.tag.endswith("title")), "")
            return re.sub(r"\s+", " ", title).strip()[:80] or path.stem[:80]
    except (OSError, KeyError, StopIteration, ET.ParseError, zipfile.BadZipFile):
        return path.stem[:80]


def _find_book(book_id):
    if not re.fullmatch(r"[0-9a-f]{20}", book_id or "") or not JAPANESE_EPUB_ROOT.is_dir():
        return None
    for path in JAPANESE_EPUB_ROOT.rglob("*.epub"):
        if _book_id(path) == book_id:
            return path
    return None


def story_for(story_id=None):
    """정적 소이 이야기 또는 EPUB 제목에서 만든 순화 로맨스를 돌려준다.

    EPUB 본문은 성인 대사를 포함할 수 있어 절대 게임 대사로 복사하지 않는다.
    작품 식별과 제목만 영감 출처로 쓰고 장면은 안전한 고정 템플릿으로 만든다.
    """
    if not story_id:
        return {"id": CHARACTER_ID, "name": CHARACTER_NAME, "title": "소이와의 사흘",
                "character_image": "/dating-sim/static/soi.png",
                "source_title": None, "total_days": TOTAL_DAYS, "locations": LOCATIONS,
                "scenes": SCENES, "endings": ENDINGS}
    match = BOOK_STORY_RE.fullmatch(story_id)
    path = _find_book(match.group(1)) if match else None
    if not path:
        raise ValueError("작품을 찾을 수 없습니다")
    source_title = _book_title(path)
    locations = {
        "first": {"label": "우연히 마주친 곳", "emoji": "✨"},
        "walk": {"label": "함께 걷는 길", "emoji": "🌙"},
        "quiet": {"label": "조용한 찻집", "emoji": "🍵"},
    }
    daily_lines = {
        1: ["今日ここで会えるとは思いませんでした。\n오늘 여기서 만날 줄은 몰랐어요.",
            "これも縁だと思ってもいいですか。\n이것도 인연이라고 생각해도 될까요?"],
        2: ["昨日話したことがずっと心に残っています。\n어제 나눈 이야기가 계속 마음에 남아 있어요.",
            "あなたのことを、もう少し知りたいです。\n당신을 조금 더 알고 싶어요."],
        3: ["短い時間なのに、ずっと覚えていそうです。\n짧은 시간이었는데도 오래 기억날 것 같아요.",
            "私たちの話を、ここで終わらせずに続けませんか。\n우리 이야기를 여기서 끝내지 않고 이어가지 않을래요?"],
    }
    scenes = {}
    for day in range(1, 4):
        scenes[day] = {}
        for location in locations:
            scenes[day][location] = {"lines": daily_lines[day], "choices": [
                {"text": "私も同じ気持ちだと素直に伝える。\n나도 같은 마음이라고 솔직하게 말한다.", "affection": 10},
                {"text": "ゆっくり知っていこうと伝える。\n천천히 알아가자고 말한다.", "affection": -5},
            ]}
    endings = [
        {"id": "best", "min_affection": 75, "title": "함께 쓰는 다음 장", "lines": ["これからは二人で、この物語を続けましょう。\n이제 이 이야기는 우리 둘이 함께 이어가요."]},
        {"id": "good", "min_affection": 60, "title": "다음 만남의 약속", "lines": ["今度はもっとゆっくり話しましょう。\n다음에는 더 오래 이야기해요."]},
        {"id": "normal", "min_affection": 0, "title": "기억에 남은 사흘", "lines": ["短かったけれど、温かい思い出になりました。\n짧았지만 따뜻한 기억으로 남았어요."]},
    ]
    return {"id": story_id, "name": "하루", "title": f"{source_title}에서 영감받은 사흘",
            "character_image": "/dating-sim/static/haru.png",
            "source_title": source_title, "total_days": 3, "locations": locations,
            "scenes": scenes, "endings": endings}


def ending_for(story, affection):
    for ending in story["endings"]:
        if affection >= ending["min_affection"]:
            return ending
    return story["endings"][-1]
