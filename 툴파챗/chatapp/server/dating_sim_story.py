"""미연시(연애 시뮬레이션) 미니게임의 안전한 스토리 데이터.

★ 2026-09-15: "미연시 시스템 하나 만들어봤으면 좋겠어" 요청 — 데이터만 담는
모듈이다. 엔진 로직(선택 검증·호감도 계산·엔딩 판정)은 server/app.py의
/api/dating-sim/* 엔드포인트에 있다. 캐릭터를 늘리거나 이야기를 바꿀 때는
이 파일만 고치면 된다.

대사는 humanize-korean 스킬(light 경로, run_dir=_workspace/2026-09-15-001)로
한 차례 다듬은 결과다 — 의미·선택지 호감도 부호는 원안과 동일하고 말투만
자연스럽게 손봤다.
"""
import datetime
import hashlib
import random
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET


def _now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")

CHARACTER_ID = "soi_cafe"
CHARACTER_NAME = "소이"
TOTAL_DAYS = 3
CONTENT_VERSION = 2

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

# 2026-09-15: 전체 세계관을 일본어 학습형 7일 데이트로 확장했다. 위의 초창기
# 3일 원안은 변경 이력으로 남기고, 실제 엔진에는 아래 장편 데이터를 사용한다.
CHARACTER_NAME = "ソイ"
TOTAL_DAYS = 7
DAY_BEATS = {
    1: (["あの、すみません。さっきは[助|たす]かりました。[初|はじ]めまして、ですよね。\n저기, 아까는 고마웠어요. 우리 처음 만난 거 맞죠?",
         "[私|わたし]はソイです。よかったら、あなたの[名前|なまえ]も[聞|き]いていいですか。\n저는 소이라고 해요. 괜찮다면 당신 이름도 물어봐도 될까요?"],
        ["[自分|じぶん]の[名前|なまえ]を[名乗|なの]って、さっきの[出来事|できごと]について[話|はな]す。\n이름을 소개하고 방금 있었던 일에 관해 이야기한다.",
         "[会釈|えしゃく]だけして、そのまま[立|た]ち[去|さ]る。\n가볍게 목례만 하고 그대로 자리를 떠난다."]),
    2: (["[昨日|きのう]より[自然|しぜん]に[話|はな]せるようになりましたね。\n어제보다 자연스럽게 이야기할 수 있게 됐네요.",
         "あなたの[好|す]きなもの、もっと[教|おし]えてください。\n당신이 좋아하는 것을 더 알려주세요."],
        ["[最近|さいきん][夢中|むちゅう]になっていることを[話|はな]す。\n요즘 빠져 있는 것을 이야기한다.",
         "[特|とく]にないと[答|こた]えて[話題|わだい]を[変|か]える。\n특별히 없다고 답하고 화제를 바꾼다."]),
    3: (["[急|きゅう]に[雨|あめ]が[降|ふ]ってきましたね。\n갑자기 비가 내리기 시작했네요.",
         "こういう[予定外|よていがい]の[時間|じかん]も、[嫌|きら]いじゃないです。\n이런 예상 밖의 시간도 싫지는 않아요."],
        ["[傘|かさ]を[一緒|いっしょ]に[使|つか]おうと[声|こえ]をかける。\n우산을 함께 쓰자고 말한다.",
         "[雨|あめ]がやむまで[別々|べつべつ]に[待|ま]つ。\n비가 그칠 때까지 따로 기다린다."]),
    4: (["[実|じつ]は、[将来|しょうらい]のことで[少|すこ]し[迷|まよ]っているんです。\n사실은 장래 문제로 조금 고민하고 있어요.",
         "こんな[話|はなし]をしても、[困|こま]りませんか。\n이런 이야기를 해도 곤란하지 않아요?"],
        ["[答|こた]えを[急|いそ]がず、ソイの[話|はなし]を[最後|さいご]まで[聞|き]く。\n답을 재촉하지 않고 소이의 이야기를 끝까지 듣는다.",
         "すぐに[自分|じぶん]の[考|かんが]えが[正|ただ]しいと[説得|せっとく]する。\n곧바로 내 생각이 옳다고 설득한다."]),
    5: (["[次|つぎ]の[休|やす]みも、また[会|あ]えたらいいですね。\n다음 휴일에도 다시 만나면 좋겠네요.",
         "あなたといると、[時間|じかん]が[早|はや]く[過|す]ぎます。\n당신과 있으면 시간이 빨리 지나가요."],
        ["[二人|ふたり]で[行|い]きたい[場所|ばしょ]を[一緒|いっしょ]に[決|き]める。\n둘이 가고 싶은 장소를 함께 정한다.",
         "そのうちね、と[曖昧|あいまい]に[答|こた]える。\n언젠가 보자며 애매하게 답한다."]),
    6: (["[昨日|きのう]、[返事|へんじ]がなくて[少|すこ]し[寂|さび]しかったです。\n어제 답장이 없어서 조금 서운했어요.",
         "[責|せ]めたいんじゃなくて、[気持|きも]ちを[知|し]りたかったんです。\n책망하려는 게 아니라 마음을 알고 싶었어요."],
        ["[遅|おそ]くなった[理由|りゆう]を[話|はな]し、[心配|しんぱい]させたことを[謝|あやま]る。\n늦어진 이유를 말하고 걱정하게 한 것을 사과한다.",
         "[忙|いそが]しかったから[仕方|しかた]ないと[話|はなし]を[終|お]える。\n바빴으니 어쩔 수 없다며 이야기를 끝낸다."]),
    7: (["この[七日間|なのかかん]、あなたに[会|あ]うのが[毎日|まいにち][楽|たの]しみでした。\n이 7일 동안 당신을 만나는 것이 매일 기대됐어요.",
         "これからも、あなたの[隣|となり]にいてもいいですか。\n앞으로도 당신 곁에 있어도 될까요?"],
        ["これからも[一緒|いっしょ]にいたいと[伝|つた]える。\n앞으로도 함께 있고 싶다고 말한다.",
         "まだ[友達|ともだち]でいたいと[正直|しょうじき]に[伝|つた]える。\n아직은 친구로 있고 싶다고 솔직하게 말한다."]),
}

DAY_NARRATION = {
    1: "その[日|ひ]、いつもの[道|みち]で[見知|みし]らぬ[女性|じょせい]と[偶然|ぐうぜん][目|め]が[合|あ]った。まだ、お[互|たが]いの[名前|なまえ]さえ[知|し]らない。\n그날 평소 걷던 길에서 낯선 여자와 우연히 눈이 마주쳤다. 아직 서로 이름조차 모른다.",
    2: "[昨日|きのう]の[笑顔|えがお]が[何度|なんど]も[頭|あたま]に[浮|う]かぶ。[今日|きょう]はもう[少|すこ]し[近|ちか]づけるだろうか。\n어제의 미소가 몇 번이나 떠오른다. 오늘은 조금 더 가까워질 수 있을까.",
    3: "[空|そら]が[急|きゅう]に[暗|くら]くなり、[雨|あめ]の[匂|にお]いがした。[予定|よてい]どおりにはいかなそうだ。\n하늘이 갑자기 어두워지고 비 냄새가 났다. 계획대로 흘러가지는 않을 것 같다.",
    4: "いつもより[静|しず]かな[表情|ひょうじょう]だ。[何|なに]か[言|い]いたいことがあるのかもしれない。\n평소보다 조용한 표정이다. 무언가 하고 싶은 말이 있는지도 모른다.",
    5: "[会|あ]うことが[自然|しぜん]な[日課|にっか]になりつつある。それが[嬉|うれ]しかった。\n만나는 일이 자연스러운 일상이 되어 간다. 그 사실이 기뻤다.",
    6: "いつもと[違|ちが]う[距離|きょり]を[感|かん]じる。[逃|に]げずに[話|はな]さなければならない。\n평소와 다른 거리감이 느껴진다. 피하지 않고 이야기해야 한다.",
    7: "[七日間|なのかかん]の[場面|ばめん]がよみがえる。[今日|きょう]の[言葉|ことば]で[二人|ふたり]の[関係|かんけい]が[決|き]まる。\n7일 동안의 장면이 떠오른다. 오늘의 말로 두 사람의 관계가 정해진다.",
}

# ★ 2026-09-15: "미연시 시나리오를 웹에서 검색해서 좀 재밌게 만들수없을까"
# 요청 — 장소별 대사가 요일과 무관하게 3줄 고정이라 카페/공원/학교 중 어디를
# 골라도 그날의 이야기가 똑같이 느껴졌다(선택이 장식일 뿐 서사에 영향이
# 없었음). 웹 검색으로 확인한 고전 미연시 구조(도키메키 메모리얼류의
# 요일별 활동 배분 + 기승전결 — 만남→친밀감→이벤트→고민상담→약속→오해→
# 고백)를 참고해, 요일마다 장소별로 다른 활동 대사를 붙여 21개 조합을 모두
# 다르게 만들었다. 5일차에는 미연시 단골 클리셰인 "라이벌 잠깐 등장"(카페
# 동료·소꿉친구·후배)을 새로 넣어 긴장감을 살짝 얹었다.
LOCATION_LINES = {
    "cafe": {
        1: "[注文|ちゅうもん]を[迷|まよ]っていると、レジの[向|む]こうの[彼女|かのじょ]がそっとおすすめを[教|おし]えてくれた。\n주문을 망설이자 계산대 너머의 그녀가 조심스럽게 추천 메뉴를 알려줬다.",
        2: "この[豆|まめ]、[実|じつ]は[私|わたし]のお[気|き]に[入|い]りなんです。\n이 원두, 사실 제가 제일 좋아하는 거예요.",
        3: "[軒下|のきした]で[雨宿|あまやど]りする[間|あいだ]、コーヒーでも[飲|の]みましょう。\n처마 밑에서 비 피하는 동안 커피라도 마셔요.",
        4: "この[静|しず]かな[隅|すみ]の[席|せき]、[話|はな]しやすいですよね。\n이 조용한 구석 자리, 이야기하기 편하죠.",
        5: "([同僚|どうりょう]が[冷|ひ]やかすように[笑|わら]う)\n(카페 동료가 짓궂게 웃으며 놀린다)\nもう、からかわないでよ...[今日|きょう]はどこ[行|い]きたいですか。\n아 진짜, 놀리지 좀 마요... 오늘은 어디 가고 싶어요?",
        6: "レジの[向|む]こうから、[素|そ]っ[気|け]なく[注文|ちゅうもん]を[聞|き]く。\n계산대 너머로 무뚝뚝하게 주문을 받는다.",
        7: "[閉店|へいてん]まぎわの[静|しず]かな[店内|てんない]、[二人|ふたり]きりです。\n마감 직전 조용한 가게 안, 우리 둘뿐이에요.",
    },
    "park": {
        1: "[風|かぜ]に[飛|と]ばされた[栞|しおり]を[拾|ひろ]うと、[彼女|かのじょ]が[息|いき]を[切|き]らして[駆|か]けてきた。\n바람에 날아온 책갈피를 주우니 그녀가 숨을 헐떡이며 달려왔다.",
        2: "あそこのベンチ、[二人|ふたり]の[定位置|ていいち]にしませんか。\n저기 벤치, 우리 자리로 정해볼래요?",
        3: "あの[東屋|あずまや]まで[走|はし]りましょう、[濡|ぬ]れる[前|まえ]に。\n저 정자까지 뛰어가요, 젖기 전에.",
        4: "[夜|よる]の[公園|こうえん]は、[本音|ほんね]が[話|はな]しやすい[気|き]がします。\n밤 공원은 왠지 속마음을 말하기 편한 것 같아요.",
        5: "([幼馴染|おさななじみ]らしき[人|ひと]が[手|て]を[振|ふ]って[通|とお]り[過|す]ぎる)\n(소꿉친구인 듯한 사람이 손을 흔들며 지나간다)\n[昔|むかし]からの[知|し]り[合|あ]いなんです、[気|き]にしないでください。\n오래전부터 아는 사이예요, 신경 쓰지 마세요.",
        6: "いつものベンチに、[少|すこ]し[距離|きょり]を[空|あ]けて[座|すわ]る。\n늘 앉던 벤치에 조금 거리를 두고 앉는다.",
        7: "[街灯|がいとう]の[下|した]、いつもより[長|なが]く[立|た]ち[止|ど]まる。\n가로등 아래, 평소보다 오래 멈춰 선다.",
    },
    "school": {
        1: "[校門|こうもん][前|まえ]で[落|お]としたノートを[拾|ひろ]うと、[持|も]ち[主|ぬし]らしい[彼女|かのじょ]が[振|ふ]り[返|かえ]った。\n교문 앞에 떨어진 공책을 줍자 주인인 듯한 그녀가 돌아봤다.",
        2: "[部活|ぶかつ][帰|がえ]りに[少|すこ]しだけ[話|はな]しませんか。\n동아리 끝나고 잠깐 이야기하지 않을래요?",
        3: "[昇降口|しょうこうぐち]で[雨|あめ]がやむのを[待|ま]ちましょう。\n신발장 앞에서 비 그치는 거 기다려요.",
        4: "[誰|だれ]もいない[教室|きょうしつ]、[少|すこ]しだけ[借|か]りましょう。\n아무도 없는 교실, 잠깐만 빌려요.",
        5: "([後輩|こうはい]がソイに[話|はな]しかけようとして、あなたを[見|み]て[止|と]まる)\n(후배가 소이에게 말 걸려다 당신을 보고 멈칫한다)\nあの[子|こ]、いつも[話|はな]しかけてくるんですよね。\n저 애, 항상 말 걸더라고요.",
        6: "[目|め]を[合|あ]わせずに、[短|みじか]く[挨拶|あいさつ]するだけ。\n눈을 마주치지 않고 짧게 인사만 한다.",
        7: "[夕方|ゆうがた]の[教室棟|きょうしつとう]、[誰|だれ]もいない[静|しず]けさです。\n저녁 교실동, 아무도 없어서 고요해요.",
    },
}


def _seven_day_scenes(location_lines, character_name_ko="소이", character_name_jp="ソイ"):
    """location_lines는 {장소: 대사} 또는 {장소: {일차: 대사}} 둘 다 받는다 —
    후자면 요일마다 다른 활동 대사가, 전자면(예: EPUB 영감 이야기의 임시
    장소 대사) 모든 요일에 같은 대사가 붙는다."""
    scenes = {}
    for day, (lines, choices) in DAY_BEATS.items():
        scenes[day] = {}
        for location, day_lines in location_lines.items():
            activity = day_lines[day] if isinstance(day_lines, dict) else day_lines
            scene_lines = [
                lines[0].replace("ソイ", character_name_jp),
                activity,
                lines[1].replace("ソイ", character_name_jp),
            ]
            scenes[day][location] = {"lines": scene_lines, "choices": [
                {"text": choices[0].replace("소이", character_name_ko), "affection": 8},
                {"text": choices[1].replace("소이", character_name_ko), "affection": -4},
            ]}
    return scenes


SCENES = _seven_day_scenes(LOCATION_LINES)
ENDINGS = [
    {"id": "best", "min_affection": 98, "title": "ベストエンディング · 함께 쓰는 다음 장", "lines": ["これからは[二人|ふたり]で、この[物語|ものがたり]を[続|つづ]けましょう。\n이제 이 이야기는 우리 둘이 함께 이어가요."]},
    {"id": "good", "min_affection": 74, "title": "グッドエンディング · 다음 약속", "lines": ["[今度|こんど]はもっとゆっくり[話|はな]しましょう。\n다음에는 더 오래 이야기해요."]},
    {"id": "normal", "min_affection": 0, "title": "ノーマルエンディング · 남은 여운", "lines": ["[短|みじか]かったけれど、[温|あたた]かい[思|おも]い[出|で]になりました。\n짧았지만 따뜻한 기억으로 남았어요."]},
]


def resolve_ending(affection):
    for ending in ENDINGS:
        if affection >= ending["min_affection"]:
            return ending
    return ENDINGS[-1]


# ★ 2026-09-15: "스토리 시나리오전개쪽에서 데이터베이스 만들어주고 웹검색해서
# 재밌는 서사와 스토리 대화 등등 에피소드를 다양하게 만드는걸 주력으로"
# 요청 — 요일×장소 조합마다 활동 대사가 하나뿐이라 어느 장소를 고르든
# 그날의 이야기가 똑같이 느껴졌다. 웹 검색으로 확인한 고전 미연시 구조
# (도키메키 메모리얼류의 요일별 이벤트 배분 + "히든 이벤트")를 참고해
# 장면마다 여러 변형을 만들고, DB에서 무작위로 골라 재플레이 다양성을 준다.
# variant 1·2는 매번 나오는 일반 변형(가중치 4:4), variant 3은 확률 낮은
# "히든 이벤트"(가중치 1 — 대략 9번 중 1번)로 5일차(라이벌→깜짝 축제)와
# 7일차(고백 직전→깜짝 선물)에만 넣었다.
VARIANT_2_LOCATION_LINES = {
    "cafe": {
        1: "[倒|たお]れそうになったカップを[同時|どうじ]に[支|ささ]え、[初対面|しょたいめん]の[二人|ふたり]は[気|き]まずく[笑|わら]った。\n쓰러질 뻔한 컵을 동시에 붙잡고, 처음 만난 두 사람은 어색하게 웃었다.",
        2: "デザートを[分|わ]けようとして、フォークが[軽|かる]くぶつかる。\n디저트를 나누다가 포크가 살짝 부딪힌다.",
        3: "[濡|ぬ]れた[肩|かた]に[気付|きづ]いて、タオルを[差|さ]し[出|だ]す。\n젖은 어깨를 보고 수건을 건네준다.",
        4: "[昔|むかし]のことを[少|すこ]しだけ[話|はな]し、[表情|ひょうじょう]が[曇|くも]る。\n옛날 이야기를 살짝 꺼내며 표정이 흐려진다.",
        5: "[店長|てんちょう]が[通|とお]りすがりに、からかうように[笑|わら]う。\n사장님이 지나가며 눈치 없이 웃으며 놀린다.",
        6: "いつもより[口数|くちかず]が[少|すこ]なくて、[気|き]になる。\n평소보다 말수가 적어서 신경이 쓰인다.",
        7: "[窓|まど][越|ご]しの[夕焼|ゆうや]けを[一緒|いっしょ]に[見|み]て、[言葉|ことば]がなくなる。\n창밖의 노을을 함께 보다가 말이 없어진다.",
    },
    "park": {
        1: "[彼女|かのじょ]が[落|お]とした[本|ほん]を[拾|ひろ]おうとして、[二人|ふたり]の[手|て]が[同時|どうじ]に[伸|の]びた。\n그녀가 떨어뜨린 책을 주우려다 두 사람의 손이 동시에 뻗었다.",
        2: "[好|す]きな[歌|うた]を[小声|こごえ]で[口|くち]ずさんでいたのを[聞|き]かれてしまう。\n좋아하는 노래를 작게 흥얼거리다 들켜버린다.",
        3: "[傘|かさ]の[中|なか]で[肩|かた]がぶつかって、[気|き]まずく[笑|わら]う。\n우산 속에서 자꾸 어깨가 부딪혀 어색하게 웃는다.",
        4: "[何|なに]かを[言|い]おうとして、[何度|なんど]もためらう。\n무언가 말하려다 몇 번이고 망설인다.",
        5: "[通|とお]りかかったカップルが、うらやましそうに[見|み]てくる。\n지나가던 커플이 부럽다는 듯 쳐다본다.",
        6: "[目|め]が[合|あ]っても、[先|さき]に[視線|しせん]をそらす。\n눈이 마주쳐도 먼저 시선을 돌린다.",
        7: "[手|て]をつなぎそうで、つながない[時間|じかん]が[続|つづ]く。\n손을 잡을 듯 말 듯한 시간이 이어진다.",
    },
    "school": {
        1: "[散|ち]らばったプリントを[一緒|いっしょ]に[集|あつ]めながら、[初|はじ]めて[言葉|ことば]を[交|か]わす。\n흩어진 인쇄물을 함께 모으며 처음으로 말을 나눈다.",
        2: "ペンを[貸|か]してもらうとき、[指先|ゆびさき]が[触|ふ]れる。\n펜을 빌리다가 손끝이 스친다.",
        3: "[濡|ぬ]れたノートを[一緒|いっしょ]に[乾|かわ]かしながら[時間|じかん]を[過|す]ごす。\n비에 젖은 노트를 함께 말리며 시간을 보낸다.",
        4: "[卒業|そつぎょう]アルバムを[見|み]ながら、[昔|むかし]の[話|はなし]をする。\n졸업 앨범을 보며 옛날이야기를 꺼낸다.",
        5: "[友達|ともだち]がからかうメッセージを、こっそり[見|み]せてくる。\n친구가 놀리는 문자를 몰래 보여준다.",
        6: "[挨拶|あいさつ]をするかどうか、[中途半端|ちゅうとはんぱ]なまま[通|とお]り[過|す]ぎる。\n인사를 할지 말지 애매하게 지나쳐 간다.",
        7: "[教室|きょうしつ]の[窓|まど]から、[星|ほし]が[一|ひと]つ[二|ふた]つ[見|み]え[始|はじ]める。\n교실 창문 너머로 별이 하나둘 보이기 시작한다.",
    },
}

HIDDEN_EVENTS = {
    5: "[遠|とお]くから[小|ちい]さな[花火|はなび][大会|たいかい]の[音|おと]が[聞|き]こえてくる。\n멀리서 작은 불꽃놀이 축제 소리가 들려온다.",
    7: "[恥|は]ずかしそうに、[小|ちい]さな[包|つつ]みを[差|さ]し[出|だ]す。\n부끄러운 듯 작은 선물 꾸러미를 건넨다.",
}


def seed_dating_sim_content(conn):
    """CHARACTER_ID 콘텐츠를 버전별로 시드한다. 콘텐츠가 갱신되면 진행 기록은
    보존하고 캐릭터·장소·장면·엔딩 원본만 결정론적으로 교체한다."""
    exists = conn.execute(
        "SELECT content_version FROM dating_sim_characters WHERE character_id=?", (CHARACTER_ID,)
    ).fetchone()
    if exists and int(exists["content_version"] or 1) >= CONTENT_VERSION:
        return
    if exists:
        conn.execute(
            "UPDATE dating_sim_progress SET day=1, affection=50, pending_location=NULL, "
            "completed=0, ending_id=NULL, scenario_run=scenario_run+1, updated_at=? "
            "WHERE character_id=?",
            (_now(), CHARACTER_ID),
        )
        conn.execute("DELETE FROM dating_sim_scenarios WHERE character_id=?", (CHARACTER_ID,))
        conn.execute("DELETE FROM dating_sim_endings WHERE character_id=?", (CHARACTER_ID,))
        conn.execute("DELETE FROM dating_sim_locations WHERE character_id=?", (CHARACTER_ID,))
        conn.execute("DELETE FROM dating_sim_characters WHERE character_id=?", (CHARACTER_ID,))
    now = _now()
    conn.execute(
        "INSERT INTO dating_sim_characters "
        "(character_id,name,title,total_days,character_image,created_at,content_version) "
        "VALUES (?,?,?,?,?,?,?)",
        (CHARACTER_ID, CHARACTER_NAME, "미연시", TOTAL_DAYS,
         "/dating-sim/static/soi.png", now, CONTENT_VERSION),
    )
    for order, (location_id, meta) in enumerate(LOCATIONS.items()):
        conn.execute(
            "INSERT INTO dating_sim_locations (character_id,location_id,label,emoji,character_image,sort_order) "
            "VALUES (?,?,?,?,?,?)",
            (CHARACTER_ID, location_id, meta["label"], meta["emoji"],
             f"/dating-sim/static/soi-{location_id}.png" if location_id != "cafe" else "/dating-sim/static/soi.png",
             order),
        )
    variants = [(LOCATION_LINES, 4), (VARIANT_2_LOCATION_LINES, 4)]
    for day, (beat_lines, beat_choices) in DAY_BEATS.items():
        for location_id in LOCATIONS:
            for variant_number, (location_lines, weight) in enumerate(variants, start=1):
                activity = location_lines[location_id][day]
                conn.execute(
                    "INSERT INTO dating_sim_scenarios "
                    "(character_id,day,location_id,variant,weight,intro_line,activity_line,outro_line,"
                    "choice_a_text,choice_a_affection,choice_b_text,choice_b_affection) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (CHARACTER_ID, day, location_id, variant_number,
                     weight, beat_lines[0], activity, beat_lines[1],
                     beat_choices[0], 8, beat_choices[1], -4),
                )
            if day in HIDDEN_EVENTS:
                conn.execute(
                    "INSERT INTO dating_sim_scenarios "
                    "(character_id,day,location_id,variant,weight,intro_line,activity_line,outro_line,"
                    "choice_a_text,choice_a_affection,choice_b_text,choice_b_affection) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (CHARACTER_ID, day, location_id, 3, 1, beat_lines[0], HIDDEN_EVENTS[day], beat_lines[1],
                     beat_choices[0], 8, beat_choices[1], -4),
                )
    for order, ending in enumerate(ENDINGS):
        conn.execute(
            "INSERT INTO dating_sim_endings (character_id,ending_id,min_affection,title,line,sort_order) "
            "VALUES (?,?,?,?,?,?)",
            (CHARACTER_ID, ending["id"], ending["min_affection"], ending["title"],
             ending["lines"][0], order),
        )
    conn.commit()


def _stable_weighted_choice(candidates, seed_key):
    """같은 회차·장면은 항상 같은 변형을 고르는 결정론적 가중 선택이다."""
    weights = [max(1, int(row["weight"] or 1)) for row in candidates]
    total = sum(weights)
    point = int.from_bytes(hashlib.sha256(seed_key.encode("utf-8")).digest()[:8], "big") % total
    for row, weight in zip(candidates, weights):
        if point < weight:
            return row
        point -= weight
    return candidates[-1]


def load_story_from_db(conn, character_id, seed_key=None):
    """DB에 시드된 캐릭터를 story_for()와 같은 모양의 dict로 만든다. 장면마다
    variant 중 weight 비례로 하나를 고른다. seed_key가 있으면 같은 사용자·회차의
    장면은 재조회해도 변하지 않고, 생략하면 콘텐츠 테스트용 무작위 선택을 유지한다."""
    character = conn.execute(
        "SELECT * FROM dating_sim_characters WHERE character_id=?", (character_id,)
    ).fetchone()
    if not character:
        return None
    location_rows = conn.execute(
        "SELECT * FROM dating_sim_locations WHERE character_id=? ORDER BY sort_order", (character_id,)
    ).fetchall()
    locations = {row["location_id"]: {"label": row["label"], "emoji": row["emoji"]} for row in location_rows}
    character_images = {
        row["location_id"]: row["character_image"] for row in location_rows if row["character_image"]
    }
    scenario_rows = conn.execute(
        "SELECT * FROM dating_sim_scenarios WHERE character_id=? ORDER BY day, location_id", (character_id,)
    ).fetchall()
    by_slot = {}
    for row in scenario_rows:
        by_slot.setdefault((row["day"], row["location_id"]), []).append(row)
    scenes = {}
    for (day, location_id), candidates in by_slot.items():
        if seed_key is None:
            chosen = random.choices(candidates, weights=[row["weight"] for row in candidates], k=1)[0]
        else:
            chosen = _stable_weighted_choice(
                candidates, f"{seed_key}:{character_id}:{day}:{location_id}"
            )
        scenes.setdefault(day, {})[location_id] = {
            "lines": [chosen["intro_line"], chosen["activity_line"], chosen["outro_line"]],
            "choices": [
                {"text": chosen["choice_a_text"], "affection": chosen["choice_a_affection"]},
                {"text": chosen["choice_b_text"], "affection": chosen["choice_b_affection"]},
            ],
        }
    ending_rows = conn.execute(
        "SELECT * FROM dating_sim_endings WHERE character_id=? ORDER BY sort_order", (character_id,)
    ).fetchall()
    endings = [
        {"id": row["ending_id"], "min_affection": row["min_affection"], "title": row["title"], "lines": [row["line"]]}
        for row in ending_rows
    ]
    return {
        "id": character["character_id"], "name": character["name"], "title": character["title"],
        "character_image": character["character_image"], "character_images": character_images,
        "source_title": None, "total_days": character["total_days"],
        "locations": locations, "scenes": scenes, "endings": endings,
    }


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


def random_book_id():
    """서재에 실제 존재하는 EPUB 하나의 공개 식별자를 무작위로 고른다."""
    if not JAPANESE_EPUB_ROOT.is_dir():
        return None
    books = list(JAPANESE_EPUB_ROOT.rglob("*.epub"))
    return _book_id(random.choice(books)) if books else None


def story_for(story_id=None):
    """정적 소이 이야기 또는 EPUB 제목에서 만든 순화 로맨스를 돌려준다.

    EPUB 본문은 성인 대사를 포함할 수 있어 절대 게임 대사로 복사하지 않는다.
    작품 식별과 제목만 영감 출처로 쓰고 장면은 안전한 고정 템플릿으로 만든다.
    """
    if not story_id:
        return {"id": CHARACTER_ID, "name": CHARACTER_NAME, "title": "미연시",
                "character_image": "/dating-sim/static/soi.png",
                "character_images": {"cafe": "/dating-sim/static/soi.png",
                                     "park": "/dating-sim/static/soi-park.png",
                                     "school": "/dating-sim/static/soi-school.png"},
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
    book_location_lines = {
        "first": {
            1: "[本屋|ほんや]で[同|おな]じ[本|ほん]に[手|て]を[伸|の]ばし、[見知|みし]らぬ[彼女|かのじょ]と[初|はじ]めて[目|め]が[合|あ]った。\n서점에서 같은 책에 손을 뻗다가 낯선 그녀와 처음 눈이 마주쳤다.",
            2: "[昨日|きのう]の[本屋|ほんや]で、また[彼女|かのじょ]に[会|あ]った。お[互|たが]いに[驚|おどろ]いて[笑|わら]う。\n어제 그 서점에서 그녀를 다시 만났다. 서로 놀라 웃었다.",
            3: "[店先|みせさき]で[雨|あめ]を[避|さ]けながら、[同|おな]じ[本|ほん]の[感想|かんそう]を[話|はな]す。\n가게 앞에서 비를 피하며 같은 책의 감상을 이야기한다.",
            4: "[静|しず]かな[棚|たな]の[間|あいだ]で、[彼女|かのじょ]が[将来|しょうらい]の[迷|まよ]いを[打|う]ち[明|あ]ける。\n조용한 서가 사이에서 그녀가 장래의 고민을 털어놓는다.",
            5: "[次|つぎ]に[一緒|いっしょ]に[読|よ]む[本|ほん]を[選|えら]ぶ。[約束|やくそく]がひとつ[増|ふ]えた。\n다음에 함께 읽을 책을 고른다. 약속이 하나 늘었다.",
            6: "[返事|へんじ]のすれ[違|ちが]いを、[最初|さいしょ]に[会|あ]った[棚|たな]の[前|まえ]で[話|はな]し[合|あ]う。\n답장이 엇갈린 일을 처음 만난 서가 앞에서 이야기한다.",
            7: "[二人|ふたり]で[選|えら]んだ[本|ほん]を[手|て]に、[彼女|かのじょ]がまっすぐこちらを[見|み]る。\n둘이 고른 책을 들고 그녀가 똑바로 이쪽을 바라본다.",
        },
        "walk": {
            1: "[道|みち]を[尋|たず]ねられた。それが、まだ[名前|なまえ]も[知|し]らない[彼女|かのじょ]との[最初|さいしょ]の[会話|かいわ]だった。\n길을 묻는 말을 들었다. 그것이 아직 이름도 모르는 그녀와 나눈 첫 대화였다.",
            2: "[同|おな]じ[帰|かえ]り[道|みち]で[再会|さいかい]し、[昨日|きのう]のことを[思|おも]い[出|だ]して[挨拶|あいさつ]する。\n같은 귀갓길에서 다시 만나 어제 일을 떠올리며 인사한다.",
            3: "[一本|いっぽん]の[傘|かさ]で[川沿|かわぞ]いを[歩|ある]き、[少|すこ]しずつ[歩幅|ほはば]が[合|あ]っていく。\n우산 하나로 강변을 걸으며 조금씩 걸음이 맞아 간다.",
            4: "[月明|つきあ]かりの[道|みち]で、[彼女|かのじょ]の[悩|なや]みを[急|せ]かさずに[聞|き]く。\n달빛 비치는 길에서 그녀의 고민을 재촉하지 않고 듣는다.",
            5: "[次|つぎ]の[休日|きゅうじつ]に[歩|ある]きたい[場所|ばしょ]を[二人|ふたり]で[探|さが]す。\n다음 휴일에 걷고 싶은 장소를 둘이 함께 찾는다.",
            6: "[少|すこ]し[離|はな]れて[歩|ある]いていた[二人|ふたり]が、ようやく[足|あし]を[止|と]めて[向|む]き[合|あ]う。\n조금 떨어져 걷던 두 사람이 마침내 걸음을 멈추고 마주 본다.",
            7: "[初|はじ]めて[会|あ]った[角|かど]を[通|とお]り[過|す]ぎても、[二人|ふたり]はまだ[別|わか]れようとしない。\n처음 만난 모퉁이를 지나서도 두 사람은 아직 헤어지려 하지 않는다.",
        },
        "quiet": {
            1: "[空|あ]いている[席|せき]を[譲|ゆず]り[合|あ]って、[知|し]らない[二人|ふたり]が[初|はじ]めて[言葉|ことば]を[交|か]わした。\n빈자리를 서로 양보하다 낯선 두 사람이 처음 말을 나눴다.",
            2: "[昨日|きのう]と[同|おな]じ[時間|じかん]、[同|おな]じ[店|みせ]で[再会|さいかい]し、[今度|こんど]は[名前|なまえ]を[呼|よ]び[合|あ]う。\n어제와 같은 시간, 같은 가게에서 다시 만나 이번에는 서로 이름을 부른다.",
            3: "[雨音|あまおと]を[聞|き]きながら、ひとつのポットからお[茶|ちゃ]を[分|わ]ける。\n빗소리를 들으며 찻주전자 하나에서 차를 나눈다.",
            4: "[静|しず]かな[席|せき]で、[普段|ふだん]は[言|い]えない[将来|しょうらい]の[話|はなし]を[聞|き]く。\n조용한 자리에서 평소에는 말하지 못하는 장래 이야기를 듣는다.",
            5: "[次|つぎ]に[会|あ]う[日|ひ]を、カレンダーを[見|み]ながら[一緒|いっしょ]に[決|き]める。\n다음에 만날 날을 달력을 보며 함께 정한다.",
            6: "[冷|さ]めかけたお[茶|ちゃ]を[前|まえ]に、すれ[違|ちが]った[気持|きも]ちをひとつずつ[確|たし]かめる。\n식어 가는 차를 앞에 두고 엇갈린 마음을 하나씩 확인한다.",
            7: "[最初|さいしょ]に[譲|ゆず]り[合|あ]った[席|せき]で、[彼女|かのじょ]が[大切|たいせつ]な[言葉|ことば]を[選|えら]ぶ。\n처음 서로 양보했던 자리에서 그녀가 소중한 말을 고른다.",
        },
    }
    scenes = _seven_day_scenes(book_location_lines, "하루", "ハル")
    endings = ENDINGS
    return {"id": story_id, "name": "하루", "title": f"{source_title}에서 영감받은 7일",
            "character_image": "/dating-sim/static/haru.png",
            "character_images": {"first": "/dating-sim/static/haru-first.png",
                                 "walk": "/dating-sim/static/haru-walk.png",
                                 "quiet": "/dating-sim/static/haru.png"},
            "source_title": source_title, "total_days": TOTAL_DAYS, "locations": locations,
            "scenes": scenes, "endings": endings}


def ending_for(story, affection):
    for ending in story["endings"]:
        if affection >= ending["min_affection"]:
            return ending
    return story["endings"][-1]
