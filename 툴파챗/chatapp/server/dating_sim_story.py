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
import json
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
CONTENT_VERSION = 5

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
    1: (["あの、とっさに[手|て]を[貸|か]してくれて、ありがとうございました。[初|はじ]めまして、ですよね。\n저기, 얼른 손을 보태줘서 고마웠어요. 우리 처음 만난 거 맞죠?",
         "[私|わたし]はソイです。きちんとお[礼|れい]もしたいので、よかったらお[名前|なまえ]と[連絡先|れんらくさき]を[聞|き]いてもいいですか。\n저는 소이라고 해요. 제대로 답례도 하고 싶어서, 괜찮다면 이름과 연락처를 물어봐도 될까요?"],
        ["[名前|なまえ]と[連絡先|れんらくさき]を[伝|つた]え、「[無事|ぶじ]でよかったです。また[会|あ]えたら、ゆっくり[話|はな]しましょう」と[笑|わら]う。\n이름과 연락처를 알려주고 '무사해서 다행이에요. 다시 만나면 천천히 이야기해요'라고 웃는다.",
         "[名前|なまえ]と[連絡先|れんらくさき]だけを[伝|つた]え、「お[礼|れい]は[気|き]にしなくていいですよ」と[会話|かいわ]を[切|き]り[上|あ]げる。\n이름과 연락처만 알려주고 '답례는 신경 쓰지 않아도 돼요'라며 대화를 마무리한다."]),
    2: (["[昨日|きのう]より[自然|しぜん]に[話|はな]せるようになりましたね。\n어제보다 자연스럽게 이야기할 수 있게 됐네요.",
         "あなたの[好|す]きなもの、もっと[教|おし]えてください。\n당신이 좋아하는 것을 더 알려주세요."],
        ["[少|すこ]し[変|か]わった[自分|じぶん]の[趣味|しゅみ]を[正直|しょうじき]に[話|はな]し、ソイの[反応|はんのう]を[待|ま]つ。\n조금 독특한 내 취미를 솔직하게 말하고 소이의 반응을 기다린다.",
         "ソイの[好|す]きなものに[話|はなし]を[合|あ]わせ、「[僕|ぼく]も[似|に]たものが[好|す]き」と[答|こた]える。\n소이가 좋아하는 것에 맞춰 '나도 비슷한 걸 좋아해요'라고 답한다."]),
    3: (["[急|きゅう]に[雨|あめ]が[降|ふ]ってきましたね。\n갑자기 비가 내리기 시작했네요.",
         "こういう[予定外|よていがい]の[時間|じかん]も、[嫌|きら]いじゃないです。\n이런 예상 밖의 시간도 싫지는 않아요."],
        ["「[狭|せま]くてもよければ」と[聞|き]いてから、[傘|かさ]をソイのほうへ[傾|かたむ]ける。\n'좁아도 괜찮다면요'라고 물은 뒤 우산을 소이 쪽으로 기울인다.",
         "[自分|じぶん]の[傘|かさ]をソイに[渡|わた]し、「[僕|ぼく]はここで[待|ま]つから」と[残|のこ]る。\n내 우산을 소이에게 건네고 '나는 여기서 기다릴게요'라며 남는다."]),
    4: (["[実|じつ]は、[将来|しょうらい]のことで[少|すこ]し[迷|まよ]っているんです。\n사실은 장래 문제로 조금 고민하고 있어요.",
         "こんな[話|はなし]をしても、[困|こま]りませんか。\n이런 이야기를 해도 곤란하지 않아요?"],
        ["すぐに[答|こた]えを[出|だ]さず、「ソイはどうなったら[嬉|うれ]しい？」とひとつだけ[聞|き]く。\n바로 답을 내놓지 않고 '소이는 어떻게 되면 좋겠어요?'라고 한 가지만 묻는다.",
         "[重|おも]くなりすぎないように[冗談|じょうだん]を[交|まじ]え、「[話|はな]したくなったらいつでも」と[伝|つた]える。\n너무 무거워지지 않게 농담을 섞고 '말하고 싶을 때 언제든지요'라고 전한다."]),
    5: (["[次|つぎ]の[休|やす]みも、また[会|あ]えたらいいですね。\n다음 휴일에도 다시 만나면 좋겠네요.",
         "あなたといると、[時間|じかん]が[早|はや]く[過|す]ぎます。\n당신과 있으면 시간이 빨리 지나가요."],
        ["「[土曜日|どようび]なら[空|あ]いてる。[場所|ばしょ]が[決|き]まったらメッセージをください」と[伝|つた]える。\n'토요일이면 비어 있어요. 장소가 정해지면 메시지 주세요'라고 전한다.",
         "「ソイの[都合|つごう]がいい[日|ひ]でいいよ」と、[日時|にちじ]も[場所|ばしょ]もすべてソイに[任|まか]せる。\n'소이가 편한 날이면 돼요'라며 날짜와 장소를 전부 소이에게 맡긴다."]),
    6: (["[昨日|きのう]、[返事|へんじ]がなくて[少|すこ]し[寂|さび]しかったです。\n어제 답장이 없어서 조금 서운했어요.",
         "[責|せ]めたいんじゃなくて、[気持|きも]ちを[知|し]りたかったんです。\n책망하려는 게 아니라 마음을 알고 싶었어요."],
        ["[遅|おそ]くなった[理由|りゆう]を[短|みじか]く[話|はな]し、「でも[待|ま]たせたことは[別|べつ]だ」と[謝|あやま]る。\n늦어진 이유를 짧게 말하고 '그래도 기다리게 한 건 별개예요'라고 사과한다.",
         "[言|い]い[訳|わけ]に[聞|き]こえないよう[理由|りゆう]は[話|はな]さず、ただ[謝|あやま]ってしばらく[距離|きょり]を[置|お]く。\n변명처럼 들리지 않도록 이유는 말하지 않고 사과한 뒤 잠시 거리를 둔다."]),
    7: (["この[七日間|なのかかん]、あなたに[会|あ]うのが[毎日|まいにち][楽|たの]しみでした。\n이 7일 동안 당신을 만나는 것이 매일 기대됐어요.",
         "これからも、あなたの[隣|となり]にいてもいいですか。\n앞으로도 당신 곁에 있어도 될까요?"],
        ["「まだ[分|わ]からないこともあるけど、それでも[隣|となり]にいたい」と[正直|しょうじき]に[伝|つた]える。\n'아직 모르는 것도 있지만 그래도 곁에 있고 싶어요'라고 솔직하게 전한다.",
         "ソイを[急|せ]かさないよう、「これからもゆっくり[知|し]っていけたら」と[答|こた]える。\n소이를 재촉하지 않도록 '앞으로도 천천히 알아가면 좋겠어요'라고 답한다."]),
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

# 장소를 먼저 고르는 메뉴처럼 보이지 않도록, 매일 사건이 먼저 벌어진다.
# 같은 회차에는 고정되고 다시 시작하면 다른 도입이 선택된다.
DAY_OPENINGS = {
    1: [
        "[何|なに]も[起|お]きないはずの[一日|いちにち]だった。けれど、[小|ちい]さな[偶然|ぐうぜん]が[見知|みし]らぬ[彼女|かのじょ]との[距離|きょり]を[変|か]えた。\n아무 일도 없을 하루였다. 하지만 작은 우연 하나가 낯선 그녀와의 거리를 바꿨다.",
        "[何|なに]かに[手|て]を[伸|の]ばしたその[瞬間|しゅんかん]、もうひとつの[手|て]が[同時|どうじ]に[伸|の]びてきた。\n무언가에 손을 뻗은 순간, 다른 손 하나가 동시에 뻗어 왔다.",
    ],
    2: [
        "[知|し]らない[番号|ばんごう]からメッセージが[届|とど]いた。「[昨日|きのう]はありがとう。ソイです」\n모르는 번호로 메시지가 왔다. '어제는 고마웠어요. 소이예요.'",
        "もう[一通|いっつう]、ソイからメッセージが[届|とど]いた。「[昨日|きのう]、ちゃんとお[礼|れい]を[言|い]えなかったから」\n소이에게서 메시지가 하나 더 왔다. '어제 제대로 고맙다고 말하지 못해서요.'",
    ],
    3: [
        "[突然|とつぜん]ソイから[電話|でんわ]がかかってきた。「ごめん、[雨|あめ]で[動|うご]けなくて……」\n갑자기 소이에게 전화가 왔다. '미안해요, 비 때문에 움직일 수가 없어서……'",
        "[空|そら]が[暗|くら]くなった[直後|ちょくご]、ソイから「[傘|かさ]、ある？」と[短|みじか]いメッセージが[届|とど]いた。\n하늘이 어두워진 직후 소이에게서 '우산 있어요?'라는 짧은 메시지가 왔다.",
    ],
    4: [
        "[夜|よる]になって、ソイから「[少|すこ]しだけ[話|はな]せる？」と[着信|ちゃくしん]があった。いつもの[声|こえ]と[違|ちが]う。\n밤이 되자 소이에게서 '잠깐 이야기할 수 있어요?'라는 전화가 왔다. 평소와 다른 목소리다.",
        "[削除|さくじょ]されたメッセージのあとに、「やっぱり[会|あ]って[話|はな]したい」とだけ[届|とど]いた。\n삭제된 메시지 뒤로 '역시 만나서 이야기하고 싶어요'라는 말만 도착했다.",
    ],
    5: [
        "ソイから[一枚|いちまい]の[写真|しゃしん]と「ここ、[一緒|いっしょ]に[行|い]かない？」という[誘|さそ]いが[届|とど]いた。\n소이에게서 사진 한 장과 '여기 같이 가지 않을래요?'라는 제안이 왔다.",
        "[休日|きゅうじつ]の[予定|よてい]を[考|かんが]えていると、ソイから[珍|めずら]しく[先|さき]に[誘|さそ]いがきた。\n휴일 계획을 생각하던 중 소이가 드물게 먼저 만나자고 했다.",
    ],
    6: [
        "[昨夜|さくや]ソイから[届|とど]いていた[待|ま]ち[合|あ]わせ[場所|ばしょ]のメッセージに、[今朝|けさ]ようやく[気|き]づいた。続けて「[今日|きょう]、ちゃんと[話|はな]したい」と[届|とど]く。\n어젯밤 소이가 보낸 약속 장소 메시지를 오늘 아침에야 확인했다. 이어서 '오늘 제대로 이야기하고 싶어요'라는 메시지가 왔다.",
        "[充電|じゅうでん]の[切|き]れていた[携帯|けいたい]をつけると、ソイからのメッセージと[着信|ちゃくしん]が[何件|なんけん]も[残|のこ]っていた。「どこにいるの？」という[声|こえ]が[不安|ふあん]そうだ。\n꺼져 있던 휴대폰을 켜자 소이에게서 온 메시지와 부재중 전화가 여러 건 남아 있었다. '어디예요?'라는 목소리가 불안하게 들린다.",
    ],
    7: [
        "[朝|あさ]、ソイから[場所|ばしょ]だけが[書|か]かれたメッセージが[届|とど]いた。「[今日|きょう]、そこで[待|ま]っています」\n아침에 소이에게서 장소만 적힌 메시지가 왔다. '오늘 거기서 기다릴게요.'",
        "[七日目|なのかめ]の[夕方|ゆうがた]、ソイから「[伝|つた]えたいことがあります」と[電話|でんわ]がかかってきた。\n일곱째 날 저녁, 소이에게서 '전하고 싶은 말이 있어요'라는 전화가 왔다.",
    ],
}

DAY_LOCATION_ACTIONS = {
    1: {"cafe": "카페에서 우연을 마주한다", "park": "날아온 책갈피를 줍는다", "school": "떨어진 공책을 건넨다"},
    2: {
        "cafe": "“지금 잠깐 이야기할래요?”라고 답한다",
        "park": "“기억하고 있어요, 소이 씨”라고 솔직히 답한다",
        "school": "“저야말로 고마웠어요”라고 정중히 답한다",
    },
    3: {"cafe": "가까운 카페로 부른다", "park": "우산을 들고 공원으로 간다", "school": "학교 현관으로 달려간다"},
    4: {"cafe": "조용한 구석 자리를 잡는다", "park": "밤 산책을 제안한다", "school": "사람 없는 곳에서 듣는다"},
    5: {"cafe": "함께 마실 것을 고른다", "park": "사진 속 장소를 찾아간다", "school": "추억이 있는 길로 간다"},
    6: {"cafe": "마주 앉아 이유를 말한다", "park": "걷다가 솔직히 털어놓는다", "school": "약속 장소에서 기다린다"},
    7: {"cafe": "마감 무렵 그녀를 만난다", "park": "가로등 아래로 향한다", "school": "조용한 교실동으로 간다"},
}

BOOK_DAY_LOCATION_ACTIONS = {
    day: {
        "first": DAY_LOCATION_ACTIONS[day]["school"],
        "walk": DAY_LOCATION_ACTIONS[day]["park"],
        "quiet": DAY_LOCATION_ACTIONS[day]["cafe"],
    }
    for day in DAY_LOCATION_ACTIONS
}


def _daily_openings(seed_key, story_id, character_name_jp="ソイ", character_name_ko="소이"):
    selected = {}
    for day, candidates in DAY_OPENINGS.items():
        key = f"{seed_key or ''}:{story_id}:{day}:opening"
        index = int.from_bytes(hashlib.sha256(key.encode("utf-8")).digest()[:4], "big") % len(candidates)
        selected[day] = (
            candidates[index]
            .replace("ソイ", character_name_jp)
            .replace("소이", character_name_ko)
        )
    return selected

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
        1: "([彼女|かのじょ]のトレーからカップが[滑|すべ]り、[床|ゆか]に[落|お]ちる[寸前|すんぜん]であなたが[支|ささ]えた。)\n(그녀의 쟁반에서 컵이 미끄러지자 바닥에 떨어지기 직전 당신이 붙잡았다.)",
        2: "この[豆|まめ]、[実|じつ]は[私|わたし]のお[気|き]に[入|い]りなんです。\n이 원두, 사실 제가 제일 좋아하는 거예요.",
        3: "[軒下|のきした]で[雨宿|あまやど]りする[間|あいだ]、コーヒーでも[飲|の]みましょう。\n처마 밑에서 비 피하는 동안 커피라도 마셔요.",
        4: "この[静|しず]かな[隅|すみ]の[席|せき]、[話|はな]しやすいですよね。\n이 조용한 구석 자리, 이야기하기 편하죠.",
        5: "([同僚|どうりょう]が[冷|ひ]やかすように[笑|わら]う)\n(카페 동료가 짓궂게 웃으며 놀린다)\nもう、からかわないでよ...[今日|きょう]はどこ[行|い]きたいですか。\n아 진짜, 놀리지 좀 마요... 오늘은 어디 가고 싶어요?",
        6: "レジの[向|む]こうから、[素|そ]っ[気|け]なく[注文|ちゅうもん]を[聞|き]く。\n계산대 너머로 무뚝뚝하게 주문을 받는다.",
        7: "[閉店|へいてん]まぎわの[静|しず]かな[店内|てんない]、[二人|ふたり]きりです。\n마감 직전 조용한 가게 안, 우리 둘뿐이에요.",
    },
    "park": {
        1: "([風|かぜ]に[飛|と]ばされた[栞|しおり]をあなたが[追|お]いかけてつかむと、[彼女|かのじょ]が[息|いき]を[切|き]らして[駆|か]けてきた。)\n(바람에 날아간 책갈피를 당신이 쫓아가 붙잡자 그녀가 숨을 헐떡이며 달려왔다.)",
        2: "あそこのベンチ、[二人|ふたり]の[定位置|ていいち]にしませんか。\n저기 벤치, 우리 자리로 정해볼래요?",
        3: "あの[東屋|あずまや]まで[走|はし]りましょう、[濡|ぬ]れる[前|まえ]に。\n저 정자까지 뛰어가요, 젖기 전에.",
        4: "[夜|よる]の[公園|こうえん]は、[本音|ほんね]が[話|はな]しやすい[気|き]がします。\n밤 공원은 왠지 속마음을 말하기 편한 것 같아요.",
        5: "([幼馴染|おさななじみ]らしき[人|ひと]が[手|て]を[振|ふ]って[通|とお]り[過|す]ぎる)\n(소꿉친구인 듯한 사람이 손을 흔들며 지나간다)\n[昔|むかし]からの[知|し]り[合|あ]いなんです、[気|き]にしないでください。\n오래전부터 아는 사이예요, 신경 쓰지 마세요.",
        6: "いつものベンチに、[少|すこ]し[距離|きょり]を[空|あ]けて[座|すわ]る。\n늘 앉던 벤치에 조금 거리를 두고 앉는다.",
        7: "[街灯|がいとう]の[下|した]、いつもより[長|なが]く[立|た]ち[止|ど]まる。\n가로등 아래, 평소보다 오래 멈춰 선다.",
    },
    "school": {
        1: "([校門|こうもん][前|まえ]で[彼女|かのじょ]のノートが[鞄|かばん]から[落|お]ちた。あなたが[拾|ひろ]って[呼|よ]び[止|と]めると、[彼女|かのじょ]が[振|ふ]り[返|かえ]った。)\n(교문 앞에서 그녀의 공책이 가방에서 떨어졌다. 당신이 주워 불러 세우자 그녀가 돌아봤다.)",
        2: "[部活|ぶかつ][帰|がえ]りに[少|すこ]しだけ[話|はな]しませんか。\n동아리 끝나고 잠깐 이야기하지 않을래요?",
        3: "[昇降口|しょうこうぐち]で[雨|あめ]がやむのを[待|ま]ちましょう。\n신발장 앞에서 비 그치는 거 기다려요.",
        4: "[誰|だれ]もいない[教室|きょうしつ]、[少|すこ]しだけ[借|か]りましょう。\n아무도 없는 교실, 잠깐만 빌려요.",
        5: "([後輩|こうはい]がソイに[話|はな]しかけようとして、あなたを[見|み]て[止|と]まる)\n(후배가 소이에게 말 걸려다 당신을 보고 멈칫한다)\nあの[子|こ]、いつも[話|はな]しかけてくるんですよね。\n저 애, 항상 말 걸더라고요.",
        6: "[目|め]を[合|あ]わせずに、[短|みじか]く[挨拶|あいさつ]するだけ。\n눈을 마주치지 않고 짧게 인사만 한다.",
        7: "[夕方|ゆうがた]の[教室棟|きょうしつとう]、[誰|だれ]もいない[静|しず]けさです。\n저녁 교실동, 아무도 없어서 고요해요.",
    },
}


# ★ 2026-09-16: "일본어선생님이 채팅방에서 작품올리고 설명할때 ... 미연시
# 링크도 같이 올리면좋겠어 ... 상황이 똑같지않아도 그작품에서 사용된
# 표현들을 사용한 대사들이 미연시에서 드러났으면 좋겠어" 요청 — EPUB
# 본문(대사 원문)은 여전히 절대 옮기지 않는다는 안전장치는 그대로 두고,
# 이미 학습용으로 추출·정제된 scene_study_cards.json의 vocabulary(개별
# 단어+읽기+뜻)만 재료로 써서 새 문장을 만든다. 문장 자체는 여기서 직접
# 쓴 안전한 템플릿이고, 그 안에 실제 단어 하나만 끼워 넣는 방식이라 원작
# 대사를 그대로 복사하는 것과는 다르다.
JP_SUBTITLE_LIBRARY_DIR = Path(__file__).resolve().parents[3] / "일본어자막추출" / "library"

VOCAB_SENTENCE_TEMPLATES = [
    "「{tag}」について、[少|すこ]し[話|はな]してもいいですか。\n'{ko}'에 대해 잠깐 이야기해도 될까요?",
    "[今日|きょう]は{tag}のことを、なんとなく[考|かんが]えていました。\n오늘은 '{ko}' 생각을 왠지 하고 있었어요.",
    "{tag}という[言葉|ことば]、[最近|さいきん][気|き]になっているんです。\n'{ko}'라는 말이 요즘 신경 쓰여요.",
    "[実|じつ]は{tag}のこと、あなたに[聞|き]いてみたかったんです。\n사실 '{ko}' 얘기, 당신한테 물어보고 싶었어요.",
]


def _find_library_folder(title):
    """일본어자막추출/library/<제목>/ 폴더를 EPUB 제목과 접두 일치로 찾는다
    (persona_worker.py의 _jp_epub_book_id와 반대 방향의 같은 매칭 규칙)."""
    if not title or not JP_SUBTITLE_LIBRARY_DIR.is_dir():
        return None
    title_key = title.casefold()
    for folder in JP_SUBTITLE_LIBRARY_DIR.iterdir():
        if folder.is_dir() and title_key.startswith(folder.name.casefold()):
            return folder
    return None


def _load_work_vocabulary(title):
    """해당 작품의 scene_study_cards.json에서 개별 단어(vocabulary)만
    추린다 — 문장(expressions)은 원본 대사 그대로일 수 있어 쓰지 않는다."""
    folder = _find_library_folder(title)
    if not folder:
        return []
    try:
        cards = json.loads((folder / "scene_study_cards.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    seen = {}
    for scene in cards.values():
        for entry in (scene or {}).get("vocabulary", []) or []:
            ja, reading, ko = entry.get("ja"), entry.get("reading"), entry.get("ko")
            if ja and reading and ko and ja not in seen:
                seen[ja] = (ja, reading, ko)
    return list(seen.values())


def _vocab_highlight_line(word, template_index):
    ja, reading, ko = word
    tag = f"[{ja}|{reading}]"
    template = VOCAB_SENTENCE_TEMPLATES[template_index % len(VOCAB_SENTENCE_TEMPLATES)]
    return template.format(tag=tag, ko=ko)


def _seven_day_scenes(location_lines, character_name_ko="소이", character_name_jp="ソイ", vocab_pool=None):
    """location_lines는 {장소: 대사} 또는 {장소: {일차: 대사}} 둘 다 받는다 —
    후자면 요일마다 다른 활동 대사가, 전자면(예: EPUB 영감 이야기의 임시
    장소 대사) 모든 요일에 같은 대사가 붙는다.

    vocab_pool을 주면(그 작품 학습카드에서 뽑은 단어 목록) 요일마다 단어
    하나를 새 문장 템플릿에 끼워 넣은 "오늘의 표현" 줄을 장면 끝에 덧붙인다
    — 원작 대사 문장은 절대 그대로 옮기지 않고, 안전하게 새로 쓴 문장에
    실제 단어(한자+읽기+뜻)만 넣는다."""
    scenes = {}
    for day, (lines, choices) in DAY_BEATS.items():
        scenes[day] = {}
        vocab_word = vocab_pool[(day - 1) % len(vocab_pool)] if vocab_pool else None
        for location, day_lines in location_lines.items():
            activity = day_lines[day] if isinstance(day_lines, dict) else day_lines
            positive_score, negative_score = choice_scores(day, location, 1)
            beat_intro = lines[0].replace("ソイ", character_name_jp).replace("소이", character_name_ko)
            beat_outro = lines[1].replace("ソイ", character_name_jp).replace("소이", character_name_ko)
            scene_lines = [activity, beat_intro, beat_outro] if day == 1 else [beat_intro, activity, beat_outro]
            if vocab_word:
                scene_lines.append(_vocab_highlight_line(vocab_word, day - 1))
            scene = {"lines": scene_lines, "choices": [
                {"text": choices[0].replace("ソイ", character_name_jp).replace("소이", character_name_ko), "affection": positive_score},
                {"text": choices[1].replace("ソイ", character_name_jp).replace("소이", character_name_ko), "affection": negative_score},
            ]}
            if vocab_word:
                scene["vocab"] = {"ja": vocab_word[0], "reading": vocab_word[1], "ko": vocab_word[2]}
            scenes[day][location] = scene
    return scenes


def choice_scores(day, location_id, variant):
    """장면별로 +7~+11/-2~-6 사이의 일관된 점수를 배정한다."""
    digest = hashlib.sha256(f"score:{day}:{location_id}:{variant}".encode()).digest()
    return 7 + digest[0] % 5, -(2 + digest[1] % 5)


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
        1: "([倒|たお]れそうになったカップをあなたがとっさに[支|ささ]えた。[初対面|しょたいめん]の[二人|ふたり]は、ほっとして[気|き]まずく[笑|わら]った。)\n(쓰러질 뻔한 컵을 당신이 얼른 붙잡았다. 처음 만난 두 사람은 안도하며 어색하게 웃었다.)",
        2: "デザートを[分|わ]けようとして、フォークが[軽|かる]くぶつかる。\n디저트를 나누다가 포크가 살짝 부딪힌다.",
        3: "[濡|ぬ]れた[肩|かた]に[気付|きづ]いて、タオルを[差|さ]し[出|だ]す。\n젖은 어깨를 보고 수건을 건네준다.",
        4: "[昔|むかし]のことを[少|すこ]しだけ[話|はな]し、[表情|ひょうじょう]が[曇|くも]る。\n옛날 이야기를 살짝 꺼내며 표정이 흐려진다.",
        5: "[店長|てんちょう]が[通|とお]りすがりに、からかうように[笑|わら]う。\n사장님이 지나가며 눈치 없이 웃으며 놀린다.",
        6: "いつもより[口数|くちかず]が[少|すこ]なくて、[気|き]になる。\n평소보다 말수가 적어서 신경이 쓰인다.",
        7: "[窓|まど][越|ご]しの[夕焼|ゆうや]けを[一緒|いっしょ]に[見|み]て、[言葉|ことば]がなくなる。\n창밖의 노을을 함께 보다가 말이 없어진다.",
    },
    "park": {
        1: "([彼女|かのじょ]が[落|お]とした[本|ほん]が[水|みず]たまりに[入|はい]る[前|まえ]に、あなたが[拾|ひろ]い[上|あ]げた。)\n(그녀가 떨어뜨린 책이 물웅덩이에 빠지기 전에 당신이 주워 올렸다.)",
        2: "[好|す]きな[歌|うた]を[小声|こごえ]で[口|くち]ずさんでいたのを[聞|き]かれてしまう。\n좋아하는 노래를 작게 흥얼거리다 들켜버린다.",
        3: "[傘|かさ]の[中|なか]で[肩|かた]がぶつかって、[気|き]まずく[笑|わら]う。\n우산 속에서 자꾸 어깨가 부딪혀 어색하게 웃는다.",
        4: "[何|なに]かを[言|い]おうとして、[何度|なんど]もためらう。\n무언가 말하려다 몇 번이고 망설인다.",
        5: "[通|とお]りかかったカップルが、うらやましそうに[見|み]てくる。\n지나가던 커플이 부럽다는 듯 쳐다본다.",
        6: "[目|め]が[合|あ]っても、[先|さき]に[視線|しせん]をそらす。\n눈이 마주쳐도 먼저 시선을 돌린다.",
        7: "[手|て]をつなぎそうで、つながない[時間|じかん]が[続|つづ]く。\n손을 잡을 듯 말 듯한 시간이 이어진다.",
    },
    "school": {
        1: "([風|かぜ]で[散|ち]らばった[彼女|かのじょ]のプリントを、あなたが[走|はし]って[集|あつ]めた。)\n(바람에 흩어진 그녀의 인쇄물을 당신이 뛰어다니며 모았다.)",
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

POSITIVE_REACTIONS = [
    "そう[言|い]ってくれると、なんだか[安心|あんしん]します。\n그렇게 말해주니 왠지 안심이 돼요.",
    "ふふ、あなたらしい[答|こた]えですね。[嬉|うれ]しいです。\n후후, 당신다운 대답이네요. 기뻐요.",
    "[今|いま]の[言葉|ことば]、ちゃんと[覚|おぼ]えておきますね。\n방금 그 말, 제대로 기억해 둘게요.",
    "もう[少|すこ]しだけ、あなたのことを[知|し]りたくなりました。\n당신을 조금 더 알고 싶어졌어요.",
    "[同|おな]じことを[考|かんが]えていたなんて、ちょっと[驚|おどろ]きました。\n같은 생각을 하고 있었다니 조금 놀랐어요.",
    "ありがとう。[今日|きょう]ここに[来|き]てよかったです。\n고마워요. 오늘 여기 오길 잘했어요.",
]
NEGATIVE_REACTIONS = [
    "そうですか……でも、[正直|しょうじき]に[話|はな]してくれてありがとう。\n그렇군요……그래도 솔직하게 말해줘서 고마워요.",
    "[少|すこ]し[意外|いがい]でした。まだお[互|たが]いを[知|し]る[途中|とちゅう]ですものね。\n조금 뜻밖이었어요. 아직 서로 알아가는 중이니까요.",
    "わかりました。[急|いそ]がずにいきましょう。\n알겠어요. 서두르지 말고 천천히 가요.",
    "うん……その[言葉|ことば]の[意味|いみ]、もう[少|すこ]し[考|かんが]えてみます。\n응……그 말의 의미를 조금 더 생각해 볼게요.",
    "ちょっと[寂|さび]しいけれど、[無理|むり]はしてほしくないです。\n조금 쓸쓸하지만 무리하길 바라지는 않아요.",
    "そっか。じゃあ、[次|つぎ]はもう[少|すこ]しうまく[話|はな]せるといいですね。\n그렇구나. 다음에는 조금 더 잘 이야기할 수 있으면 좋겠네요.",
]


def choice_reaction(day, location_id, affection_delta, story_id):
    reactions = POSITIVE_REACTIONS if affection_delta > 0 else NEGATIVE_REACTIONS
    key = f"reaction:{story_id}:{day}:{location_id}:{affection_delta}"
    index = int.from_bytes(hashlib.sha256(key.encode()).digest()[:4], "big") % len(reactions)
    return reactions[index]


def seed_dating_sim_content(conn):
    """CHARACTER_ID 콘텐츠를 버전별로 시드한다. 콘텐츠가 갱신되면 진행 기록은
    보존하고 캐릭터·장소·장면·엔딩 원본만 결정론적으로 교체한다."""
    exists = conn.execute(
        "SELECT content_version FROM dating_sim_characters WHERE character_id=?", (CHARACTER_ID,)
    ).fetchone()
    existing_version = int(exists["content_version"] or 1) if exists else 0
    if exists and existing_version >= CONTENT_VERSION:
        return
    if exists:
        if existing_version < 2:
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
                positive_score, negative_score = choice_scores(day, location_id, variant_number)
                # ★ 2026-09-16: "이전장면에서 서로 연락처교환을안했는데
                # 메시지가 온게 이상해" 신고를 조사하며 발견 — 컬럼에 항상
                # 같은 의미(intro_line=하루 시작 대사, activity_line=장소별로
                # 달라지는 활동 대사, outro_line=마무리 대사)만 담는다. 1일차만
                # 활동을 먼저 보여줘야 하는 순서 문제는 읽는 쪽(load_story_from_db/
                # _seven_day_scenes) 한 곳에서만 처리한다 — 쓰는 쪽에서 컬럼을
                # 미리 뒤바꿔 저장하면 "activity_line인데 실제로는 인트로 대사"
                # 같은 이름과 내용이 어긋나는 컬럼이 생겨, DB를 직접 조회하는
                # 코드(예: 콘텐츠 마이그레이션 테스트)가 엉뚱한 텍스트를 집는다.
                conn.execute(
                    "INSERT INTO dating_sim_scenarios "
                    "(character_id,day,location_id,variant,weight,intro_line,activity_line,outro_line,"
                    "choice_a_text,choice_a_affection,choice_b_text,choice_b_affection) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (CHARACTER_ID, day, location_id, variant_number,
                     weight, beat_lines[0], activity, beat_lines[1],
                     beat_choices[0], positive_score, beat_choices[1], negative_score),
                )
            if day in HIDDEN_EVENTS:
                positive_score, negative_score = choice_scores(day, location_id, 3)
                conn.execute(
                    "INSERT INTO dating_sim_scenarios "
                    "(character_id,day,location_id,variant,weight,intro_line,activity_line,outro_line,"
                    "choice_a_text,choice_a_affection,choice_b_text,choice_b_affection) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (CHARACTER_ID, day, location_id, 3, 1, beat_lines[0], HIDDEN_EVENTS[day], beat_lines[1],
                     beat_choices[0], positive_score, beat_choices[1], negative_score),
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
        choices = [
            {"text": chosen["choice_a_text"], "affection": chosen["choice_a_affection"]},
            {"text": chosen["choice_b_text"], "affection": chosen["choice_b_affection"]},
        ]
        if seed_key is not None:
            order_key = f"{seed_key}:{character_id}:{day}:{location_id}:choice-order"
            if hashlib.sha256(order_key.encode("utf-8")).digest()[0] & 1:
                choices.reverse()
        # 1일차만 사고(활동 대사)가 먼저 나와야 소이의 "고마워요"가 앞뒤가
        # 맞는다 — _seven_day_scenes()(EPUB 영감 경로가 쓰는 폴백)와 똑같은
        # 예외를 여기(실제 플레이가 타는 DB 경로)에도 적용한다. DB 컬럼
        # 자체는 항상 같은 의미(intro/activity/outro)만 담으므로 순서만
        # 여기서 조정하면 되고, 컬럼 값을 미리 뒤바꿔 저장할 필요가 없다.
        ordered_lines = (
            [chosen["activity_line"], chosen["intro_line"], chosen["outro_line"]] if day == 1
            else [chosen["intro_line"], chosen["activity_line"], chosen["outro_line"]]
        )
        scenes.setdefault(day, {})[location_id] = {
            "lines": ordered_lines,
            "choices": choices,
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
        "day_openings": _daily_openings(seed_key, character_id),
        "map_actions": DAY_LOCATION_ACTIONS,
    }


JAPANESE_EPUB_ROOT = Path("/Users/forrestdpark/Desktop/BlogImage/av완성작")
BOOK_STORY_RE = re.compile(r"^book:([0-9a-f]{20})$")
BOOK_CHARACTER_PROFILES = [
    {"jp": "ハル", "ko": "하루", "image": "/dating-sim/static/haru.png"},
    {"jp": "アカリ", "ko": "아카리", "image": "/dating-sim/static/akari.png"},
    {"jp": "ミオ", "ko": "미오", "image": "/dating-sim/static/mio.png"},
    {"jp": "レイナ", "ko": "레이나", "image": "/dating-sim/static/reina.png"},
    {"jp": "ユナ", "ko": "유나", "image": "/dating-sim/static/akari.png"},
    {"jp": "ナナミ", "ko": "나나미", "image": "/dating-sim/static/mio.png"},
    {"jp": "カエデ", "ko": "카에데", "image": "/dating-sim/static/reina.png"},
    {"jp": "サクラ", "ko": "사쿠라", "image": "/dating-sim/static/haru.png"},
]


def book_character_profile(story_id, source_hint=""):
    """작품 메타데이터의 이름을 우선하고, 없으면 작품별 고정 프로필을 배정한다."""
    if re.search(r"츠바키[ _·-]*리카", source_hint, re.IGNORECASE):
        return {"jp": "椿リカ", "ko": "츠바키 리카", "image": "/dating-sim/static/reina.png"}
    digest = hashlib.sha256(story_id.encode("utf-8")).digest()
    return BOOK_CHARACTER_PROFILES[digest[0] % len(BOOK_CHARACTER_PROFILES)]


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


def story_for(story_id=None, seed_key=None):
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
                "scenes": SCENES, "endings": ENDINGS,
                "day_openings": _daily_openings(seed_key, CHARACTER_ID),
                "map_actions": DAY_LOCATION_ACTIONS}
    match = BOOK_STORY_RE.fullmatch(story_id)
    path = _find_book(match.group(1)) if match else None
    if not path:
        raise ValueError("작품을 찾을 수 없습니다")
    source_title = _book_title(path)
    profile = book_character_profile(story_id, f"{source_title} {path.stem}")
    locations = {
        "first": {"label": "우연히 마주친 곳", "emoji": "✨"},
        "walk": {"label": "함께 걷는 길", "emoji": "🌙"},
        "quiet": {"label": "조용한 찻집", "emoji": "🍵"},
    }
    book_location_lines = {
        "first": {
            1: "([本屋|ほんや]で[彼女|かのじょ]が[取|と]ろうとした[本|ほん]が[棚|たな]から[滑|すべ]った。あなたがとっさに[受|う]け[止|と]め、[初|はじ]めて[目|め]が[合|あ]った。)\n(서점에서 그녀가 꺼내려던 책이 선반에서 미끄러졌다. 당신이 얼른 받아 들며 처음 눈이 마주쳤다.)",
            2: "[昨日|きのう]の[本屋|ほんや]で、また[彼女|かのじょ]に[会|あ]った。お[互|たが]いに[驚|おどろ]いて[笑|わら]う。\n어제 그 서점에서 그녀를 다시 만났다. 서로 놀라 웃었다.",
            3: "[店先|みせさき]で[雨|あめ]を[避|さ]けながら、[同|おな]じ[本|ほん]の[感想|かんそう]を[話|はな]す。\n가게 앞에서 비를 피하며 같은 책의 감상을 이야기한다.",
            4: "[静|しず]かな[棚|たな]の[間|あいだ]で、[彼女|かのじょ]が[将来|しょうらい]の[迷|まよ]いを[打|う]ち[明|あ]ける。\n조용한 서가 사이에서 그녀가 장래의 고민을 털어놓는다.",
            5: "[次|つぎ]に[一緒|いっしょ]に[読|よ]む[本|ほん]を[選|えら]ぶ。[約束|やくそく]がひとつ[増|ふ]えた。\n다음에 함께 읽을 책을 고른다. 약속이 하나 늘었다.",
            6: "[返事|へんじ]のすれ[違|ちが]いを、[最初|さいしょ]に[会|あ]った[棚|たな]の[前|まえ]で[話|はな]し[合|あ]う。\n답장이 엇갈린 일을 처음 만난 서가 앞에서 이야기한다.",
            7: "[二人|ふたり]で[選|えら]んだ[本|ほん]を[手|て]に、[彼女|かのじょ]がまっすぐこちらを[見|み]る。\n둘이 고른 책을 들고 그녀가 똑바로 이쪽을 바라본다.",
        },
        "walk": {
            1: "([道|みち]に[迷|まよ]った[彼女|かのじょ]を、あなたは[目的地|もくてきち]が[見|み]える[角|かど]まで[案内|あんない]した。それが[二人|ふたり]の[最初|さいしょ]の[会話|かいわ]だった。)\n(길을 잃은 그녀를 당신이 목적지가 보이는 모퉁이까지 안내했다. 그것이 두 사람의 첫 대화였다.)",
            2: "[同|おな]じ[帰|かえ]り[道|みち]で[再会|さいかい]し、[昨日|きのう]のことを[思|おも]い[出|だ]して[挨拶|あいさつ]する。\n같은 귀갓길에서 다시 만나 어제 일을 떠올리며 인사한다.",
            3: "[一本|いっぽん]の[傘|かさ]で[川沿|かわぞ]いを[歩|ある]き、[少|すこ]しずつ[歩幅|ほはば]が[合|あ]っていく。\n우산 하나로 강변을 걸으며 조금씩 걸음이 맞아 간다.",
            4: "[月明|つきあ]かりの[道|みち]で、[彼女|かのじょ]の[悩|なや]みを[急|せ]かさずに[聞|き]く。\n달빛 비치는 길에서 그녀의 고민을 재촉하지 않고 듣는다.",
            5: "[次|つぎ]の[休日|きゅうじつ]に[歩|ある]きたい[場所|ばしょ]を[二人|ふたり]で[探|さが]す。\n다음 휴일에 걷고 싶은 장소를 둘이 함께 찾는다.",
            6: "[少|すこ]し[離|はな]れて[歩|ある]いていた[二人|ふたり]が、ようやく[足|あし]を[止|と]めて[向|む]き[合|あ]う。\n조금 떨어져 걷던 두 사람이 마침내 걸음을 멈추고 마주 본다.",
            7: "[初|はじ]めて[会|あ]った[角|かど]を[通|とお]り[過|す]ぎても、[二人|ふたり]はまだ[別|わか]れようとしない。\n처음 만난 모퉁이를 지나서도 두 사람은 아직 헤어지려 하지 않는다.",
        },
        "quiet": {
            1: "([満席|まんせき]の[店|みせ]で、あなたは[最後|さいご]の[空|あ]いた[席|せき]を[彼女|かのじょ]に[譲|ゆず]った。そのあと[相席|あいせき]を[勧|すす]められ、[初|はじ]めて[言葉|ことば]を[交|か]わした。)\n(만원인 가게에서 당신이 마지막 빈자리를 그녀에게 양보했다. 뒤이어 합석을 권유받으며 처음 말을 나눴다.)",
            2: "[昨日|きのう]と[同|おな]じ[時間|じかん]、[同|おな]じ[店|みせ]で[再会|さいかい]し、[今度|こんど]は[名前|なまえ]を[呼|よ]び[合|あ]う。\n어제와 같은 시간, 같은 가게에서 다시 만나 이번에는 서로 이름을 부른다.",
            3: "[雨音|あまおと]を[聞|き]きながら、ひとつのポットからお[茶|ちゃ]を[分|わ]ける。\n빗소리를 들으며 찻주전자 하나에서 차를 나눈다.",
            4: "[静|しず]かな[席|せき]で、[普段|ふだん]は[言|い]えない[将来|しょうらい]の[話|はなし]を[聞|き]く。\n조용한 자리에서 평소에는 말하지 못하는 장래 이야기를 듣는다.",
            5: "[次|つぎ]に[会|あ]う[日|ひ]を、カレンダーを[見|み]ながら[一緒|いっしょ]に[決|き]める。\n다음에 만날 날을 달력을 보며 함께 정한다.",
            6: "[冷|さ]めかけたお[茶|ちゃ]を[前|まえ]に、すれ[違|ちが]った[気持|きも]ちをひとつずつ[確|たし]かめる。\n식어 가는 차를 앞에 두고 엇갈린 마음을 하나씩 확인한다.",
            7: "[最初|さいしょ]に[譲|ゆず]り[合|あ]った[席|せき]で、[彼女|かのじょ]が[大切|たいせつ]な[言葉|ことば]を[選|えら]ぶ。\n처음 서로 양보했던 자리에서 그녀가 소중한 말을 고른다.",
        },
    }
    vocab_pool = _load_work_vocabulary(source_title)
    scenes = _seven_day_scenes(book_location_lines, profile["ko"], profile["jp"], vocab_pool=vocab_pool)
    if seed_key is not None:
        for day, day_scenes in scenes.items():
            for location_id, scene in day_scenes.items():
                order_key = f"{seed_key}:{story_id}:{day}:{location_id}:choice-order"
                if hashlib.sha256(order_key.encode("utf-8")).digest()[0] & 1:
                    scene["choices"].reverse()
    endings = ENDINGS
    map_actions = {
        day: {location: action.replace("소이", profile["ko"])
              for location, action in actions.items()}
        for day, actions in BOOK_DAY_LOCATION_ACTIONS.items()
    }
    return {"id": story_id, "name": profile["jp"], "title": f"{source_title}에서 영감받은 7일",
            "character_image": profile["image"],
            "character_images": {"first": profile["image"],
                                 "walk": profile["image"],
                                 "quiet": profile["image"]},
            "source_title": source_title, "total_days": TOTAL_DAYS, "locations": locations,
            "scenes": scenes, "endings": endings,
            "day_openings": _daily_openings(seed_key, story_id, profile["jp"], profile["ko"]),
            "map_actions": map_actions}


def ending_for(story, affection):
    for ending in story["endings"]:
        if affection >= ending["min_affection"]:
            return ending
    return story["endings"][-1]
