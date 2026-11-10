"""손자병법 역사 전투를 상태 기반 턴제 지휘 게임으로 제공한다."""
from copy import deepcopy
import json
import os
from pathlib import Path

STAT_LABELS = {"troops":"병력","morale":"사기","supply":"보급","intelligence":"정보","initiative":"주도권","damage":"피해","time":"시간"}

PROBE_ORDER = ("策", "作", "形", "角")
PROBE_META = {
 "策":{"key":"chaek","title":"策 · 오사칠계","focus":"도·천·지·장·법을 적아에 교지이계해 득실을 판단한다","cost":"시간 -1","effects":{"time":-1,"intelligence":1}},
 "作":{"key":"jak","title":"作 · 동정","focus":"적을 자극해 무엇에 움직이고 멈추는지 확인한다","cost":"주도권 -1","effects":{"initiative":-1,"intelligence":1}},
 "形":{"key":"hyeong","title":"形 · 생사지","focus":"적의 형체를 드러내게 해 살 길과 죽을 곳을 가른다","cost":"사기 -2","effects":{"morale":-2,"intelligence":1}},
 "角":{"key":"gak","title":"角 · 유여부족","focus":"제한적으로 겨루어 어느 부분이 남고 부족한지 가른다","cost":"병력 -3 · 피해 +2","effects":{"troops":-3,"damage":2,"intelligence":1}},
}

PROBE_DEFAULT_ANALYSIS = {
 "策":{
  "finding":"오사칠계로 적아의 방책을 비교해 득실을 판단했습니다.",
  "gains":["적아의 목표·시간·지형·지휘·조직을 같은 기준으로 비교할 수 있습니다."],
  "losses":["계산과 교차 확인에 시간을 쓰며, 그 동안 기회의 창이 줄어듭니다."],
  "unknowns":["적이 실제로 같은 방책을 지속할지는 자극과 관찰로 검증해야 합니다."],
  "assessment":"계산은 출발 가설입니다. 作·形·角으로 검증하기 전에는 확정하지 않습니다.",
  "comparison":[
   {"factor":"道","label":"목표·결속","ours":"아군의 목표와 결심을 점검","enemy":"적 지휘부와 병력의 결속은 추가 확인 필요","edge":"판단 보류"},
   {"factor":"天","label":"시간·시기","ours":"움직일 수 있는 시간창을 계산","enemy":"적이 준비할 때까지의 시간을 계산","edge":"판단 보류"},
   {"factor":"地","label":"거리·지형","ours":"접근로·보급로·퇴로를 점검","enemy":"적의 상호지원 거리는 추가 확인 필요","edge":"판단 보류"},
   {"factor":"將","label":"지휘·판단","ours":"아군 지휘관의 판단과 신뢰를 점검","enemy":"적 지휘부의 반응 원칙은 추가 확인 필요","edge":"판단 보류"},
   {"factor":"法","label":"편제·보급","ours":"명령·편제·보급의 지속력을 점검","enemy":"적의 명령과 보급의 단일 실패점을 탐색","edge":"판단 보류"},
  ],
 },
 "作":{
  "finding":"제한된 자극으로 적의 움직임과 멈춤의 조건을 관찰했습니다.",
  "gains":["적이 무엇을 보호하고 어떤 신호에 반응하는지 단서를 얻었습니다."],
  "losses":["자극을 위해 주도권을 일부 양보하고 아군의 관심을 노출했습니다."],
  "unknowns":["보인 반응이 지속적인 원칙인지 한 번의 기만인지는 아직 모릅니다."],
  "assessment":"동정의 규칙을 가설로 얻었으며, 형을 더 드러내게 해 검증해야 합니다.",
 },
 "形":{
  "finding":"적의 형체를 드러내게 해 생지와 사지를 가렸습니다.",
  "gains":["적이 강화한 곳과 그 때문에 빈 곳을 함께 확인했습니다."],
  "losses":["적의 형을 끌어내기 위해 아군의 의도와 사기를 일부 건습니다."],
  "unknowns":["드러난 취약점에 예비대가 숨어 있는지는 아직 확정할 수 없습니다."],
  "assessment":"움직일 곳과 피할 곳이 드러났지만, 국지 교전으로 유여부족을 확인해야 합니다.",
 },
 "角":{
  "finding":"제한 교전으로 적아의 유여부족을 확인했습니다.",
  "gains":["병력·보급·사기·지휘 중 어느 부분이 버틸 수 있는지 실증했습니다."],
  "losses":["실증을 위해 병력을 소모하고 피해를 감수했습니다."],
  "unknowns":["적이 아직 투입하지 않은 예비대의 규모와 의도는 남아 있습니다."],
  "assessment":"계산·동정·생사지·유여부족을 합쳐 종합 형세를 판단할 수 있습니다.",
 },
}

PROBE_RESULTS = {
 "jingxing":{
  "策":"조군의 목적은 협로 봉쇄보다 한군 주력을 평야로 끌어내 정면에서 압도하는 데 있음을 계산했습니다.",
  "作":"선봉을 협로 입구에 보이자 조군 기병만 전진하고 본영 보병은 움직이지 않았습니다.",
  "形":"도하 준비를 노출하자 조군이 강가 전면을 강화해, 본영과 후방 길이 상대적으로 비었습니다.",
  "角":"측면을 짧게 쳐 보니 조군의 지원은 늦고 본영 예비대가 적다는 사실이 확인됐습니다.",
 },
 "cannae":{
  "策":"로마군은 병력 우세로 중앙을 분쇄하는 것을 승리 조건으로 삼고 있음을 계산했습니다.",
  "作":"누미디아 기병의 도발에 로마 전열이 속도를 높이며 중앙 앞으로 몰렸습니다.",
  "形":"카르타고 중앙을 얕게 내밀자 로마군이 양익보다 중앙 돌파에 병력을 집중했습니다.",
  "角":"기병 접전으로 로마 우익 기병의 지원력이 약하고 보병 뒤가 비기 쉬움을 확인했습니다.",
 },
 "austerlitz":{
  "策":"연합군은 프라첸 고지보다 프랑스군 우익과 퇴로 차단을 우선하려 함을 계산했습니다.",
  "作":"우익의 불안한 움직임을 보이자 연합군 선두가 남쪽으로 내려가기 시작했습니다.",
  "形":"퇴각 준비처럼 진형을 보이자 프라첸 고지의 중앙 예비대까지 남쪽으로 이동했습니다.",
  "角":"국지 접전으로 고지 중앙의 지원 간격과 북·남익 사이의 끊어진 연결을 확인했습니다.",
 },
}

FIVE_FACTORS = (("道", "목표·결속"), ("天", "시간·시기"), ("地", "거리·지형"),
                ("將", "지휘·판단"), ("法", "편제·보급"))
FIVE_SPY_TYPES = (("鄉間", "향간", "현지의 사람과 지형에서 얻는 정보"),
                  ("內間", "내간", "상대 조직 내부에서 얻는 정보"),
                  ("反間", "반간", "상대의 정보망을 전환해 얻는 정보"),
                  ("死間", "사간", "적에게 보이도록 노출한 정보와 그 반응"),
                  ("生間", "생간", "적지를 보고 돌아온 사람의 보고"))


def _list(value, fallback):
    if isinstance(value, list) and value:
        return [str(item) for item in value if str(item).strip()]
    return list(fallback)


def _probe_analysis(battle_id, symbol):
    """전투별 교계 결과를 표준 구조로 보정한다.

    이전에 저장된 단순 조사 기록도 새 UI에서 득·실·미확인을 보여 주도록
    항상 완전한 폴백을 만든다.
    """
    battle = BATTLES.get(battle_id, {})
    base = deepcopy(PROBE_DEFAULT_ANALYSIS[symbol])
    custom = battle.get("probe_analysis", {}).get(symbol, {})
    if not isinstance(custom, dict):
        custom = {}
    for key in ("finding", "assessment"):
        if custom.get(key):
            base[key] = str(custom[key])
    for key in ("gains", "losses", "unknowns"):
        base[key] = _list(custom.get(key), base[key])
    if symbol == "策" and isinstance(custom.get("comparison"), list) and custom["comparison"]:
        base["comparison"] = deepcopy(custom["comparison"])
    evidence = (custom.get("evidence")
                or battle.get("probe_results", {}).get(symbol)
                or PROBE_RESULTS.get(battle_id, {}).get(symbol)
                or base["finding"])
    base["evidence"] = str(evidence)
    return base


def probe_synthesis(battle_id, state):
    done = state.get("probes", {})
    if not all(symbol in done for symbol in PROBE_ORDER):
        return {"complete": False, "completed": len(done), "total": len(PROBE_ORDER)}
    battle = BATTLES.get(battle_id, {})
    custom = battle.get("probe_synthesis", {})
    rows = []
    labels = {"策": "득실의 계", "作": "동정의 리", "形": "생사의 지", "角": "유여부족의 처"}
    for symbol in PROBE_ORDER:
        analysis = _probe_analysis(battle_id, symbol)
        rows.append({"symbol": symbol, "label": labels[symbol],
                     "finding": done.get(symbol, {}).get("finding") or analysis["finding"]})
    return {
        "complete": True,
        "title": custom.get("title") or "이해·득실·형세 종합",
        "rows": rows,
        "understanding": custom.get("understanding") or "적의 방책·반응·취약지·여력을 하나의 판단 구조로 엮었습니다.",
        "situation": custom.get("situation") or "단일 정보가 아니라 네 가지 검증 결과가 같은 방향을 가리킬 때만 형세를 확정합니다.",
        "conclusion": custom.get("conclusion") or "유리한 곳에서만 움직이고, 남은 미확인 정보가 결론을 뒤집을 수 있는지 계속 감시하십시오.",
    }


def intelligence_dashboard(battle_id, state):
    """출전 전에도 볼 수 있는 적아·오간 정보판.

    사료에 성명이 없으면 추정하지 않고 `미상`과 미확인 사유를 노출한다.
    """
    battle = BATTLES.get(battle_id, {})
    custom = battle.get("intelligence_dashboard", {})
    ours = custom.get("ours") if isinstance(custom.get("ours"), dict) else {}
    enemy = custom.get("enemy") if isinstance(custom.get("enemy"), dict) else {}
    agents = custom.get("agents") if isinstance(custom.get("agents"), list) else []
    comparison = _probe_analysis(battle_id, "策").get("comparison", [])
    default_ours = [{"label": row.get("factor", ""), "name": row.get("label", ""),
                     "value": row.get("ours", "미확인"), "confidence": "계산"}
                    for row in comparison]
    people = enemy.get("people") if isinstance(enemy.get("people"), list) else []
    if not people:
        people = [
            {"role":"左右", "name":"미상", "function":"지휘관 가까이서 결심을 돕는 측근", "confidence":"미확인"},
            {"role":"謁者", "name":"미상", "function":"보고와 면담이 안으로 들어가는 통로", "confidence":"미확인"},
            {"role":"門者", "name":"미상", "function":"출입과 경계를 통제하는 사람", "confidence":"미확인"},
            {"role":"舍人", "name":"미상", "function":"거처·문서·일상의 변화를 가까이서 보는 사람", "confidence":"미확인"},
        ]
    agent_rows = []
    custom_agents = {str(item.get("type")): item for item in agents if isinstance(item, dict)}
    for hanja, label, function in FIVE_SPY_TYPES:
        item = custom_agents.get(hanja) or custom_agents.get(label) or {}
        agent_rows.append({"type": hanja, "label": label, "function": function,
                           "source": item.get("source", "확보된 정보원 없음"),
                           "report": item.get("report", "아직 도착한 보고가 없습니다."),
                           "confidence": item.get("confidence", "미확인"),
                           "caveat": item.get("caveat", "새 정보가 들어오면 시점과 독립 출처를 붙여야 합니다.")})
    return {
        "ours":{"title":ours.get("title", "아군 오사 상태"),
                "summary":ours.get("summary", battle.get("briefing", "")),
                "rows":ours.get("rows") if isinstance(ours.get("rows"), list) else default_ours},
        "enemy":{"title":enemy.get("title", "적 중추 인물망"),
                 "summary":enemy.get("summary", "성명·역할·시점·출처를 분리해 확인합니다."),
                 "people":people},
        "agents":{"title":"오간 정보판", "rows":agent_rows},
        "known_count":sum(1 for person in people if person.get("name") not in (None, "", "미상")),
        "probe_count":len(state.get("probes", {})),
    }

def C(text, result, score=0, effects=None, flags=None, requires=None, reason="조건이 부족합니다", principle="", ratings=None):
    return {"text":text,"result":result,"score":score,"effects":effects or {},"flags":flags or {},
            "requires":requires or {},"locked_reason":reason,"principle":principle,"ratings":ratings or {}}

JINGXING = [
 {"title":"정찰","prompt":"조군이 협로와 보급로에 매복했는지 먼저 확인해야 합니다.","choices":[
  C("척후와 포로 심문으로 적의 배치를 교차 확인한다","보급로 차단대가 없고 조군이 정면 결전을 준비 중임을 확인했습니다.",3,{"intelligence":2,"time":-1},{"route_safe":True},principle="知彼知己",ratings={"information":3,"preservation":1,"doctrine":2}),
  C("현지 주민에게 우회로와 조군의 이동 흔적을 묻는다","안전한 여울과 기병 이동로를 찾았지만 적 본영의 상태는 모릅니다.",2,{"intelligence":1,"initiative":1},{"ford_known":True},principle="因地制流",ratings={"information":2,"logistics":1,"speed":1}),
  C("시간을 아끼기 위해 즉시 협로로 진군한다","선두가 매복 가능 지점에서 혼란을 겪어 피해가 발생했습니다.",0,{"initiative":2,"troops":-7,"damage":8,"morale":-4},principle="不知彼",ratings={"speed":2,"preservation":-2,"doctrine":-1})]},
 {"title":"도하와 보급","prompt":"협로를 지난 군을 어떤 순서로 강가에 전개할까요?","choices":[
  C("보급대를 중앙에 두고 도하로를 확보한 뒤 주력을 전개한다","보급로가 안정돼 장기전에도 진형을 유지할 수 있습니다.",3,{"supply":12,"time":-1,"initiative":-1},{"supply_line":True},principle="軍無輜重則亡",ratings={"logistics":3,"preservation":1}),
  C("주력을 먼저 건너 주도권을 잡고 보급대는 뒤따르게 한다","전개는 빨랐지만 후방이 길게 늘어졌습니다.",1,{"initiative":2,"supply":-8,"damage":3},principle="兵貴神速",ratings={"speed":2,"logistics":-1}),
  C("정찰한 얕은 여울로 병력을 나누어 동시에 건넌다","분산 도하가 성공해 조군의 관측을 피했습니다.",3,{"initiative":2,"supply":4},{"hidden_crossing":True},{"ford_known":True},"1턴에 여울을 확인해야 합니다","出其不意",{"information":1,"speed":2,"doctrine":2})]},
 {"title":"배수진","prompt":"수적으로 열세인 주력을 어디에, 어떤 임무로 세울까요?","choices":[
  C("강을 등지되 퇴각 금지 신호와 버틸 시간을 명확히 한다","별동대가 움직일 때까지 버틴다는 공동 목표가 생겼습니다.",3,{"morale":18,"supply":-4},{"backwater":True},principle="陷之死地而後生",ratings={"doctrine":3,"preservation":1}),
  C("강가에 세우고 무조건 죽을 때까지 싸우라고 명한다","목적 없는 절박함이 공황으로 변했습니다.",0,{"morale":-15,"troops":-8,"damage":10},{"reckless_backwater":True},principle="形似而實異",ratings={"doctrine":-2,"preservation":-2}),
  C("높은 산 위에 진을 쳐 안전을 우선한다","조군은 물과 보급이 끊기기를 기다립니다.",1,{"supply":-18,"initiative":-2,"time":-1},principle="絶地無留",ratings={"logistics":-2,"speed":-1})]},
 {"title":"유인","prompt":"조군 주력을 본영 밖으로 끌어낼 후속 명령이 필요합니다.","choices":[
  C("경기병의 거짓 패주로 조군을 강가까지 깊게 유인한다","조군은 한군이 붕괴한다고 믿고 본영을 비운 채 추격합니다.",3,{"initiative":2,"morale":-3},{"enemy_lured":True},{"backwater":True},"통제된 배수진이 있어야 합니다","利而誘之",{"information":1,"speed":2,"doctrine":3}),
  C("정면에서 제한 공격을 반복해 조군의 추격심을 자극한다","조군 일부가 전진했지만 본영 경계병은 남아 있습니다.",2,{"troops":-5,"damage":6,"initiative":1},{"enemy_partly_lured":True},principle="怒而撓之",ratings={"speed":1,"preservation":-1,"doctrine":1}),
  C("진지를 굳히고 조군이 먼저 움직일 때까지 기다린다","양군 모두 움직이지 않아 보급과 시간이 먼저 줄어듭니다.",0,{"supply":-14,"time":-2,"morale":-5},principle="久則鈍兵挫銳",ratings={"logistics":-2,"speed":-2})]},
 {"title":"별동대","prompt":"조군 본영을 흔들 병력을 얼마나 보낼까요?","choices":[
  C("확인한 길에 경기병 2천을 보내 본영의 깃발을 바꾼다","별동대가 빈 본영에 잠입해 한군 깃발을 세웠습니다.",4,{"troops":-3,"initiative":3},{"camp_seized":True},{"intelligence":2},"정보가 2 이상이어야 안전한 길을 압니다","攻其無備 出其不意",{"information":3,"preservation":1,"doctrine":3}),
  C("소규모 별동대로 본영 주변에 연기와 소음을 낸다","조군은 본영이 공격받는다고 오인했지만 아직 빼앗기지는 않았습니다.",2,{"initiative":1},{"camp_threatened":True},principle="兵者詭道也",ratings={"information":1,"doctrine":2}),
  C("별동대 없이 전 병력을 정면에 집중한다","정면은 버티지만 조군의 본영과 지휘 체계는 온전합니다.",0,{"morale":4,"troops":-9,"damage":10},principle="無奇正之變",ratings={"preservation":-2,"doctrine":-2})]},
 {"title":"결전","prompt":"조군의 대열이 흔들립니다. 승리를 완성할 마지막 명령은?","choices":[
  C("본영의 한군 깃발을 신호로 배수진과 별동대가 동시에 협공한다","조군은 앞뒤에서 한군을 보고 지휘 체계를 잃었습니다. 정형의 포위가 완성됩니다.",4,{"morale":10,"initiative":3,"troops":-3,"damage":2},{"decisive_victory":True},{"camp_seized":True,"enemy_lured":True},"본영 점령과 완전한 유인이 모두 필요합니다","奇正相生",{"preservation":2,"speed":2,"doctrine":3}),
  C("흔들리는 조군 중앙에 예비대를 투입해 퇴로를 압박한다","조군을 전장에서 밀어냈습니다. 결정적 포위는 아니지만 주도권을 확보했습니다.",2,{"troops":-7,"damage":7,"initiative":1},{"field_victory":True},principle="乘人之不及",ratings={"speed":1,"preservation":-1,"doctrine":1}),
  C("피해를 막기 위해 질서 있게 강 건너로 철수한다","군은 보존했지만 조군은 본영을 수습해 작전 목표를 달성하지 못했습니다.",0,{"morale":-10,"initiative":-3},{"withdrew":True},principle="知可以戰與不可以戰",ratings={"preservation":2,"speed":-2})]}
]

def legacy(title,year,commander,verse,meaning,map_path,briefing,phases):
    return {"title":title,"year":year,"commander":commander,"verse":verse,"verse_meaning":meaning,"map":map_path,
            "briefing":briefing,"initial_state":{"troops":100,"morale":55,"supply":70,"intelligence":1,"initiative":1,"damage":0,"time":len(phases)},"phases":phases}

BATTLES={
 "jingxing":legacy("정형 전투","BCE 205","한신","陷之死地而後生","사지에 빠뜨린 뒤에야 산다","/battle-sim/static/jingxing_codex_map_wide_v2.png?v=20261006","정찰·보급·배수진·유인·본영 기습을 하나의 작전으로 연결하세요.",JINGXING),
 "cannae":legacy("칸나에 전투","BCE 216","한니발","形人而我無形","적은 드러나게 하고 나는 형체를 감춘다","/battle-sim/static/cannae_codex_map.png?v=20261006","중앙의 통제 후퇴와 양익·기병을 연결하세요.",[
  {"title":"유인","prompt":"로마군의 돌진을 어디로 끌어들일까?","choices":[C("얕게 돌출한 중앙으로 유인한다","로마군이 중앙 안쪽으로 깊게 들어왔습니다.",2,{"initiative":2}),C("전 전선을 일직선으로 고정한다","정면 힘겨루기에서 병력 열세가 드러났습니다.",0,{"troops":-10,"damage":10})]},
  {"title":"통제 후퇴","prompt":"중앙 보병이 밀리기 시작했다. 어떻게 통제할까?","choices":[C("계획된 곡선 후퇴로 바꾸되 양익은 자리를 지킨다","중앙은 포위의 안쪽 면이 됐습니다.",2,{"morale":8}),C("모든 예비대를 중앙에 넣는다","양익의 포위력이 사라졌습니다.",0,{"troops":-8,"damage":8})]},
 {"title":"봉쇄","prompt":"기병이 로마 기병을 몰아냈다. 다음 목표는?","choices":[C("후방으로 돌아 로마 보병의 퇴로를 닫는다","이중 포위가 완성됐습니다.",2,{"initiative":3},{"decisive_victory":True},{"probe_gak":True},"角 단계로 로마군 후방의 부족을 확인해야 합니다"),C("달아나는 기병을 끝까지 추격한다","후방 봉쇄 전력이 전장을 떠났습니다.",0,{"initiative":-2})]}]),
 "austerlitz":legacy("아우스터리츠 전투","1805","나폴레옹","能愚士卒之耳目","아군의 눈과 귀도 통제해 의도를 감춘다","/battle-sim/static/austerlitz_codex_map.png?v=20261006","약한 우익을 연출해 고지를 비우게 만든 뒤 중앙을 가릅니다.",[
  {"title":"기만","prompt":"연합군이 공격하도록 어떤 인상을 줄까?","choices":[C("우익이 약하고 퇴각을 고민하는 듯 보인다","연합군이 남쪽으로 병력을 옮겼습니다.",2,{"intelligence":2},{"enemy_lured":True}),C("전 병력을 고지 위에 과시한다","연합군이 중앙을 강화했습니다.",0,{"initiative":-2})]},
  {"title":"중앙 돌파","prompt":"프라첸 고지가 비기 시작했다. 언제 공격할까?","choices":[C("적 주력이 남하하고 안개가 걷힐 때 중앙을 친다","연합군을 둘로 나눴습니다.",2,{"initiative":3},requires={"probe_hyeong":True},reason="形 단계로 프라첸 고지가 비었음을 확인해야 합니다"),C("첫 움직임이 보이자 즉시 전군을 투입한다","적이 배치를 되돌렸습니다.",0,{"troops":-8,"damage":8})]},
  {"title":"분단","prompt":"분리된 연합군에 무엇을 우선할까?","choices":[C("중앙 고지를 장악해 북·남익 연결을 끊는다","작전 전체의 승리로 이어졌습니다.",2,{"initiative":2},{"decisive_victory":True}),C("후퇴하는 소부대의 포획 숫자를 늘린다","적 주력이 재결합했습니다.",0,{"initiative":-2})]}])}

# 구절 페이지에서는 키워드 유사도보다 해당 구절에 실린 역사적 실증 사례를 먼저 연다.
BATTLES["jingxing"].update({"source_verse_ids": [1, 35], "source_kind": "historical_case"})
BATTLES["cannae"].update({"source_verse_ids": [5], "source_kind": "historical_case"})
BATTLES["austerlitz"].update({"source_verse_ids": [7], "source_kind": "historical_case"})

BATTLES["jingxing"]["introduction"] = {
 "eyebrow":"초한쟁패 · 정형구 전야",
 "title":"눈을 뜨니, 그대는 한신이었다",
 "hero_image":"/battle-sim/static/jingxing_intro_terrain_v1.png?v=20261006",
 "hero_alt":"정형구의 좁은 산길을 따라 한군과 보급 수레가 진군하고, 계곡 너머 조군 진영이 보이는 전경",
 "lead":"때는 기원전 205~204년 무렵. 항우와 유방이 천하를 놓고 다투던 초한쟁패의 한복판이다. 위나라를 평정한 한신과 장이는 태행산맥의 정형구를 넘어 조나라를 치기 위해 동쪽으로 진군한다.",
 "story":[
  "정형구는 산이 깎아지는 좁은 통로다. 한군이 긴 행군대로 들어오면 조군은 앞을 막고 뒤의 보급로를 끊을 수 있다. 조의 이좌거는 바로 이 계책을 성안군 진여에게 올렸지만, 진여는 정면 결전을 택했다.",
  "그대의 곁에는 조 지역의 정세에 밝고 훗날 조왕이 되는 장이가 있다. 선봉은 협로를 열고, 중군은 결전을 버티며, 후군은 보급과 퇴로를 유지해야 한다. 그리고 그대는 기병 2천을 정예 별동대로 골라 조군 본영을 노린다."
 ],
 "commanders":[
  {"side":"한군 · 대장군","names":"한신","image":"/battle-sim/static/portrait_hanxin_v1.png?v=20261006","role":"전체 작전과 신호를 통제하고, 배수진과 기병 별동대를 하나의 계책으로 엮는다."},
  {"side":"한군 · 조력 지휘관","names":"장이","image":"/battle-sim/static/portrait_zhanger_v1.png?v=20261006","role":"조 지역의 정세를 바탕으로 한군 주력을 함께 지휘하고 정형구 돌파를 돕는다."},
  {"side":"조군 · 군주","names":"조왕 헐","image":"/battle-sim/static/portrait_zhaoxie_v1.png?v=20261006","role":"조나라의 군주. 성안군 진여에게 군 지휘를 맡기고 한군의 침공을 막는다."},
  {"side":"조군 · 모사","names":"이좌거","image":"/battle-sim/static/portrait_lizuo_che_v1.png?v=20261006","role":"정형구에서 한군의 보급로를 끊는 협공책을 진여에게 건의한 노련한 병법가다."}
 ],
 "forces":[
  {"label":"한군 주력","value":"정확한 총병력은 사료마다 해석이 다름","note":"게임에서는 선봉·중군·후군으로 작전적 복원"},
  {"label":"기병 별동대","value":"2,000명","note":"『사기』에 기록된 정예 경기병"},
  {"label":"조군","value":"20만 대군으로 기록","note":"수치는 고대 사료의 관례적 과장 가능성을 함께 고려"},
  {"label":"보급 편제","value":"군량·수레·짐승의 후방 행렬","note":"세부 편제는 남아 있지 않아 당시 군제를 바탕으로 복원"}
 ],
 "mission":"조군이 수적 우세를 확신하게 만들고 본영을 비우게 한 뒤, 정면 주력과 별동대를 한 번에 연결하라.",
 "source_note":"사실 골격은 『사기』〈회음후열전〉에 따르며, 세부 편제·배치는 지휘 플레이를 위한 복원이다."
}

GENERATED_BATTLES_DIR = Path(os.environ.get(
    "SUNZI_GENERATED_BATTLES_DIR",
    str(Path(__file__).with_name("generated_battles")),
))
_GENERATED_BATTLE_IDS = set()


def _valid_generated_battle(battle):
    if not isinstance(battle, dict):
        return False
    required = ("title", "year", "commander", "verse", "verse_meaning", "briefing", "initial_state", "phases", "source_verse_ids")
    if any(not battle.get(key) for key in required):
        return False
    phases = battle.get("phases")
    source_verse_ids = battle.get("source_verse_ids")
    if not isinstance(source_verse_ids, list) or any(not isinstance(item, int) or item < 1 for item in source_verse_ids):
        return False
    if not isinstance(phases, list) or not 3 <= len(phases) <= 8:
        return False
    for phase in phases:
        choices = phase.get("choices") if isinstance(phase, dict) else None
        if not phase.get("title") or not phase.get("prompt") or not isinstance(choices, list) or len(choices) < 2:
            return False
        if any(not isinstance(choice, dict) or not choice.get("text") or not choice.get("result") for choice in choices):
            return False
    return True


def refresh_generated_battles():
    """자동 보강이 만든 선언형 JSON만 읽는다. Python 코드는 실행하지 않는다."""
    global _GENERATED_BATTLE_IDS
    for battle_id in _GENERATED_BATTLE_IDS:
        BATTLES.pop(battle_id, None)
    loaded = set()
    try:
        paths = sorted(GENERATED_BATTLES_DIR.glob("*.json"))
    except OSError:
        paths = []
    for path in paths:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            continue
        battle_id = str(payload.get("id") or path.stem).strip()
        battle = payload.get("battle") if isinstance(payload.get("battle"), dict) else payload
        if not battle_id.replace("-", "").replace("_", "").isalnum() or not _valid_generated_battle(battle):
            continue
        BATTLES[battle_id] = battle
        loaded.add(battle_id)
    _GENERATED_BATTLE_IDS = loaded
    return loaded

def initial_state(battle):
    s=deepcopy(battle["initial_state"]);s["flags"]={};s["ratings"]={k:0 for k in ("information","preservation","logistics","speed","doctrine")};s["probes"]={};return s

def probe_options(battle_id,state):
    done=state.get("probes",{})
    options=[]
    for index,symbol in enumerate(PROBE_ORDER):
        meta=PROBE_META[symbol]
        analysis=_probe_analysis(battle_id,symbol)
        saved=done.get(symbol,{}) if isinstance(done.get(symbol,{}),dict) else {}
        previous=PROBE_ORDER[index-1] if index else None
        locked=bool(previous and previous not in done)
        options.append({"symbol":symbol,"key":meta["key"],"title":meta["title"],"focus":meta["focus"],"cost":meta["cost"],
                        "done":symbol in done,"locked":locked,
                        "locked_reason":f"먼저 {previous} 단계를 실행해야 합니다" if locked else "",
                        "result":saved.get("result","") or (analysis["finding"] if symbol in done else ""),
                        "finding":saved.get("finding","") or analysis["finding"],
                        "gains":_list(saved.get("gains"),analysis["gains"]),
                        "losses":_list(saved.get("losses"),analysis["losses"]),
                        "unknowns":_list(saved.get("unknowns"),analysis["unknowns"]),
                        "assessment":saved.get("assessment","") or analysis["assessment"],
                        "evidence":saved.get("evidence","") or analysis["evidence"],
                        "comparison":saved.get("comparison") or analysis.get("comparison",[]),
                        "changes":saved.get("changes",[])})
    return options

def apply_probe(battle_id,state,symbol):
    if symbol not in PROBE_ORDER: raise ValueError("올바르지 않은 조사 단계입니다")
    s=deepcopy(state);done=s.setdefault("probes",{})
    if symbol in done: raise ValueError("이미 실행한 조사입니다")
    index=PROBE_ORDER.index(symbol)
    if index and PROBE_ORDER[index-1] not in done: raise ValueError(f"먼저 {PROBE_ORDER[index-1]} 단계를 실행해야 합니다")
    meta=PROBE_META[symbol]
    analysis=_probe_analysis(battle_id,symbol)
    for key,value in meta["effects"].items(): s[key]=s.get(key,0)+value
    for key in ("troops","morale","supply"): s[key]=max(0,min(100,s.get(key,0)))
    s["intelligence"]=max(0,min(5,s.get("intelligence",0)));s["initiative"]=max(-5,min(10,s.get("initiative",0)));s["damage"]=max(0,min(100,s.get("damage",0)));s["time"]=max(0,s.get("time",0))
    result=analysis["evidence"]
    changes=[{"key":key,"label":STAT_LABELS.get(key,key),"value":value}
             for key,value in meta["effects"].items() if value]
    done[symbol]={"title":meta["title"],"focus":meta["focus"],"result":result,"cost":meta["cost"],
                  "finding":analysis["finding"],"gains":analysis["gains"],"losses":analysis["losses"],
                  "unknowns":analysis["unknowns"],"assessment":analysis["assessment"],
                  "evidence":analysis["evidence"],"comparison":analysis.get("comparison",[]),
                  "changes":changes}
    s.setdefault("flags",{})[f"probe_{meta['key']}"]=True
    s.setdefault("ratings",{})["information"]=s.setdefault("ratings",{}).get("information",0)+1
    s.setdefault("ratings",{})["doctrine"]=s.setdefault("ratings",{}).get("doctrine",0)+1
    return s,result

def choice_available(choice,state):
    flags=state.get("flags",{})
    for key,want in choice.get("requires",{}).items():
        got=flags.get(key) if key in flags else state.get(key,0)
        if isinstance(want,(int,float)) and not isinstance(want,bool):
            if got<want:return False
        elif got!=want:return False
    return True

def choice_preview(choice):
    return [{"key":k,"label":STAT_LABELS.get(k,k),"value":v} for k,v in choice.get("effects",{}).items() if v]

def apply_choice(state,choice):
    s=deepcopy(state)
    for k,v in choice.get("effects",{}).items():s[k]=s.get(k,0)+v
    for k in ("troops","morale","supply"):s[k]=max(0,min(100,s.get(k,0)))
    s["intelligence"]=max(0,min(5,s.get("intelligence",0)));s["initiative"]=max(-5,min(10,s.get("initiative",0)));s["damage"]=max(0,min(100,s.get("damage",0)));s["time"]=max(0,s.get("time",0))
    s.setdefault("flags",{}).update(choice.get("flags",{}))
    for k,v in choice.get("ratings",{}).items():s.setdefault("ratings",{})[k]=s.get("ratings",{}).get(k,0)+v
    return s

def map_scene(battle_id,phase,state):
    if battle_id!="jingxing":return {"stage":phase,"units":[],"arrows":[]}
    # 말판처럼 선봉·중군·후군·보급을 따로 보여주고, 적은 정보가 쌓여야 실제 배치를 공개한다.
    ally=[
      {"label":"선봉","formation":"개척대","strength":"3,000","kind":"vanguard","x":22,"y":45,"side":"ally"},
      {"label":"중군","formation":"주력군","strength":"주력","kind":"main","x":30,"y":62,"side":"ally"},
      {"label":"후군","formation":"예비대","strength":"예비","kind":"reserve","x":16,"y":63,"side":"ally"},
      {"label":"보급","formation":"치중대","strength":"군량·수레","kind":"supply","x":9,"y":70,"side":"supply"},
    ]
    revealed=state.get("intelligence",0)>=2 or len(state.get("probes",{}))>=2 or phase>=1
    enemy=([
      {"label":"조군 좌군","formation":"보병진","strength":"정찰됨","kind":"enemy-wing","x":58,"y":28,"side":"enemy"},
      {"label":"조군 중군","formation":"본대","strength":"대군","kind":"enemy-main","x":72,"y":35,"side":"enemy"},
      {"label":"조군 우군","formation":"기병대","strength":"정찰됨","kind":"enemy-wing","x":83,"y":47,"side":"enemy"},
      {"label":"조군 본영","formation":"지휘소","strength":"진여","kind":"camp","x":87,"y":20,"side":"enemy"},
    ] if revealed else [
      {"label":"적 예상 지역","formation":"정찰 필요","strength":"?","kind":"unknown","x":75,"y":32,"side":"unknown"}
    ])
    # 턴별 재배치. 좌표를 넓게 벌리고 선택한 명령의 결과를 실제 진형에 반영한다.
    positions=[
      {},
      {"vanguard":(28,43),"main":(31,61),"reserve":(16,64),"supply":(9,70)},
      {"vanguard":(39,44),"main":(38,58),"reserve":(22,65),"supply":(29,69)},
      {"vanguard":(46,45),"main":(48,65),"reserve":(28,61),"supply":(34,70)},
      {"vanguard":(50,43),"main":(50,65),"reserve":(29,60),"supply":(34,70)},
      {"vanguard":(55,42),"main":(50,65),"reserve":(30,59),"supply":(34,70)},
      {"vanguard":(61,42),"main":(57,58),"reserve":(40,61),"supply":(34,70)},
    ][min(phase,6)]
    if state.get("flags",{}).get("supply_line") and phase>=2:
        positions["supply"]=(34,70)
        ally[3]["formation"]="중앙 보급거점"
        ally[3]["strength"]="군량·수레 보호"
    if state.get("flags",{}).get("backwater") and phase>=3:
        positions["main"]=(50,65)
        ally[1]["formation"]="배수진"
        ally[1]["strength"]="강을 등진 주력"
    for unit in ally:
        if unit["kind"] in positions:unit["x"],unit["y"]=positions[unit["kind"]]
    if phase>=4 and revealed:
        enemy[0]["x"],enemy[0]["y"]=59,42;enemy[1]["x"],enemy[1]["y"]=66,48;enemy[2]["x"],enemy[2]["y"]=76,43
    if phase>=5:
        ally.append({"label":"별동대","formation":"기병","strength":"2,000","kind":"detachment","x":82,"y":23,"side":"ally"})
    arrows_by_phase=[[],[(22,45,28,43,"ally","협로 정찰")],[(31,61,38,58,"ally","주력 전개")],[(38,58,50,65,"ally","강을 등진 배수진")],[(72,35,66,48,"enemy","한군 추격")],[(42,48,82,23,"ally","별동대 기습")],[(57,58,66,48,"ally","정면 반격"),(82,23,72,40,"ally","후방 협공")]]
    arrows=list(arrows_by_phase[min(phase,6)])
    if state.get("flags",{}).get("supply_line") and phase>=2:
        arrows.append((9,70,34,70,"supply","보급 중앙 이동"))
    if state.get("flags",{}).get("backwater") and phase>=3:
        arrows.append((38,58,50,65,"ally","강을 등진 배수진"))
    stage_titles=["진군 전 배치","정찰선 전진","도하·보급 재편","배수진 전개","조군 유인","본영 기습","전면 협공"]
    return {"stage":phase,"fog_of_war":not revealed,"units":ally+enemy,
            "stage_title":stage_titles[min(phase,6)],
            "terrain_labels":[{"label":"정형구 협로","x":16,"y":27},{"label":"한군 배후의 강","x":55,"y":79},{"label":"조군 평야","x":76,"y":60}],
            "arrows":[{"x1":a,"y1":b,"x2":c,"y2":d,"side":e,"label":label} for a,b,c,d,e,label in arrows]}

def commander_counsel(battle,choice,state):
    """선택 즉시 표시하고 툴파챗 한신 대화방에도 남길 짧은 현장 조언."""
    good=choice.get("score",0)>=3
    opening="좋은 결단이오." if good else "의도는 알겠으나, 다음 명령이 더 중요하오."
    principle=choice.get("principle") or battle.get("verse","")
    warning=("정보를 신뢰하되 보급과 퇴로를 함께 보시오." if state.get("supply",0)<55 else
             "적이 우리의 의도를 알지 못하게 다음 명령의 신호를 하나로 맞추시오.")
    return {"sender":battle.get("commander","지휘관"),"text":f"{opening} {choice['result']} 「{principle}」을 기억하시오. {warning}"}

def _grade(v):return "S" if v>=6 else "A" if v>=4 else "B" if v>=2 else "C" if v>=0 else "D"

def battle_summary(battle,score,state=None):
    state=state or initial_state(battle);ratings=state.get("ratings",{});decisive=state.get("flags",{}).get("decisive_victory");total=score+max(0,state.get("troops",0)-65)//5+max(0,state.get("supply",0)-40)//10
    rank,grade=("대승","S") if decisive or total>=20 else (("승리","A") if total>=12 else (("고전","B") if total>=7 else ("패배","C")))
    labels={"information":"정보 활용","preservation":"병력 보존","logistics":"보급 관리","speed":"결단 속도","doctrine":"손자병법 적용"};best=max(ratings,key=ratings.get) if ratings else "doctrine";styles={"information":"정보 지휘관","preservation":"불패의 수호자","logistics":"철벽 보급관","speed":"속전속결가","doctrine":"기만 전술가"}
    return {"rank":rank,"grade":grade,"style":styles.get(best,"야전 지휘관"),"lesson":f"{battle['verse']}의 조건을 명령의 연쇄로 얼마나 구현했는지 복기하세요.","categories":[{"key":k,"label":v,"grade":_grade(ratings.get(k,0))} for k,v in labels.items()],"reward_xp":max(10,score*2+(15 if decisive else 0)),"contributions":{"전투력":max(2,score//2),"집중":max(0,ratings.get("information",0)),"유대":max(0,ratings.get("preservation",0)),"준비":max(0,ratings.get("logistics",0))}}
