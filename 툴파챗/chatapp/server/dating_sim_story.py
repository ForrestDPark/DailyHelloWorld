"""미연시(연애 시뮬레이션) 미니게임의 스토리 데이터.

★ 2026-09-15: "미연시 시스템 하나 만들어봤으면 좋겠어" 요청 — 데이터만 담는
모듈이다. 엔진 로직(선택 검증·호감도 계산·엔딩 판정)은 server/app.py의
/api/dating-sim/* 엔드포인트에 있다. 캐릭터를 늘리거나 이야기를 바꿀 때는
이 파일만 고치면 된다.

대사는 humanize-korean 스킬(light 경로, run_dir=_workspace/2026-09-15-001)로
한 차례 다듬은 결과다 — 의미·선택지 호감도 부호는 원안과 동일하고 말투만
자연스럽게 손봤다.
"""

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
