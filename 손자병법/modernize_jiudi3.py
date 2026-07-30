#!/usr/bin/env python3
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent
PATH = ROOT / "jiudi3_full_page.md"

SECTION2 = """## 2. 전통 주석 기반 분석 {toggle="true" color="blue"}
	- <span color="blue">**조조(曹操)**</span> — "교지는 네 길이면서 적의 길이기도 하니 방비를 늦추지 마라. 구지에서는 칼보다 먼저 사절과 약속을 보내라."
	- <span color="blue">**이전(李筌)**</span> — "길이 막힘없이 통하는 곳에서는 한쪽의 힘만 보지 마라. 여러 세력의 기운이 모이는 자리를 먼저 붙잡아야 한다."
	- <span color="blue">**두목(杜牧)**</span> — "삼속을 추상적인 말로 넘기지 말고 지도에서 세 나라의 경계가 맞닿는 곳을 찾아라. 그 접점이 누구 편이 되는지가 전장을 바꾼다."
	- <span color="blue">**매요신(梅堯臣)**</span> — "세 나라와 맞닿은 땅에서는 한 나라만 상대한다고 생각하지 마라. 네 행동 하나가 나머지 제후의 선택까지 흔든다."
	- <span color="blue">**장예(張預)**</span> — "교지와 구지를 고정된 지명으로 외우지 마라. 피아의 접근권과 주변국의 관계가 달라질 때 지형의 성격도 달라진다."
	- <span color="blue">**왕석(王晳)**</span> — "먼저 도착했다는 사실만으로는 부족하다. 먼저 신뢰와 이익을 보여 천하의 무리가 스스로 모이게 해야 한다."
	- <span color="blue">**가림(賈林)**</span> — "구지에 들어가면 즉시 인접국과 맹약을 맺어라. 전투가 시작된 뒤 얻으려는 동맹은 이미 늦다."
	- <span color="blue">**두우(杜佑)**</span> — "회맹과 국경의 관행을 살펴 누가 누구와 손잡을 수 있는지 먼저 계산하라. 외교의 길도 병참로처럼 미리 열어야 한다."
	- <span color="blue">**진호(陳皞)**</span> — "교지에서는 드나드는 길을 통제하고, 구지에서는 여러 나라의 마음을 묶어라. 지형과 외교를 따로 보지 마라."
	아홉 주석은 같은 결론으로 모인다. <span color="red">**交地(교지)**</span>에서는 피아 모두가 움직일 수 있으므로 통로·보고·예비대의 연결이 먼저이고, <span color="blue">**衢地(구지)**</span>에서는 제3세력이 누구 편에 설지를 먼저 정하게 만드는 정치적 속도가 먼저다.
---
"""

SECTION3 = """## 3. 교차 설명 {toggle="true" color="green"}
	- **① 손자병법 내 교차 — 通形(통형)과 合交(합교)**

		「지형편」의 `我可以往, 彼可以來, 曰通`(아가이왕, 피가이래, 왈통: 나도 갈 수 있고 적도 올 수 있으면 통형이라 한다)은 이 구절의 交地와 거의 같은 공간을 가리킨다. 같은 길을 양쪽이 쓸 수 있으므로, 길이 열렸다는 사실은 이점이 아니라 **적에게도 열린 위험**이다. 그래서 높은 곳·양지·보급로를 먼저 확보하라는 처방이 붙는다.

		이어지는 `衢地則合交`(구지즉합교: 구지에서는 외교로 연합하라)는 구지의 승부가 점령보다 관계 선점에 있음을 분명히 한다. 교지에서는 전술적 연결을 끊기지 않게 하고, 구지에서는 주변 제후와의 연결을 먼저 묶어야 한다.

	- **② 클라우제비츠 『전쟁론』 — 동맹의 결속도 무게중심이다**

		클라우제비츠의 무게중심은 언제나 적 주력군 하나만 뜻하지 않는다. 연합전에서는 여러 세력을 붙들어두는 공통 이해와 정치적 결속이 무게중심이 될 수 있다. 브라이텐펠트에서 작센의 선택은 병력 추가 이상의 의미를 가졌다. 그 선택이 북독일 신교 세력의 기대와 이동 방향을 바꿨기 때문이다.

		다만 동맹을 얻었다고 마찰이 사라지는 것은 아니다. 작센군이 먼저 붕괴했듯 서로 다른 훈련·명령 체계는 전투 중 틈을 만든다. 구지의 `得天下衆`(득천하중)은 숫자를 모으는 데서 끝나지 않고, 붕괴 뒤에도 공동 목적과 예비대 운용으로 연결을 유지하는 데까지 가야 한다.

	- **③ 미야모토 무사시 『오륜서』 — 먼저 움직인다는 것의 두 층위**

		무사시의 선(先)은 단순히 먼저 칼을 내는 속도가 아니라 상대의 의도가 굳기 전에 박자를 잡는 일이다. 구지의 `先至`(선지: 먼저 도착함)도 같다. 선발대·사절·정보가 먼저 도착해 주변 세력의 판단 기준을 만들면, 뒤늦게 온 대군은 이미 정해진 관계를 뒤집어야 한다.

		그러나 성급함은 선이 아니다. 필 전투에서 선곡은 먼저 황하를 건넜지만, 그것은 전체 지휘와 정나라의 향배를 읽은 선점이 아니라 독단이었다. **먼저 움직이되 전체의 박자를 묶지 못하면 先至가 아니라 분열의 시작**이 된다.

	- **④ 오자병법·육도 — 접경에서는 신의와 정보가 병력보다 먼저 간다**

		『오자병법』은 적의 병력뿐 아니라 제후의 친소와 지원 관계를 함께 살피라고 가르친다. 이는 세 나라의 경계가 맞닿는 구지를 지리와 외교가 결합된 공간으로 보는 관점과 통한다. 전투 개시 전에 누가 중립이고 누가 흔들리는지를 알아야 한다.

		『육도』의 회맹·용간 논리도 같은 방향이다. 약속을 먼저 얻고 사정을 먼저 알면 싸우기 전에 적의 선택지가 줄어든다. 다만 신의를 속임수로만 다루면 단기 동맹은 얻어도 지속되지 않는다. 구지에서 모은 衆은 **공통 이익과 예측 가능한 행동**으로 유지해야 한다.

	- **⑤ 현대 심리학·군사학 연구 — 팀 상황인식과 다자 연합**

		2024년 팀 상황인식 검토는 복잡하고 빠른 업무에서 구성원 모두가 환경 감시·의미 해석·다음 단계 예측에 기여할 때 안전과 수행이 좋아진다고 정리한다. 이는 교지에서 누구나 같은 통로로 들어올 수 있을 때, 각자 보고 있는 단서를 공통 상황판으로 묶어야 한다는 교훈과 닮았다. 하지만 공유된 이해가 틀릴 수도 있으므로 독립 확인과 반대 보고 통로를 남겨야 한다. [연구](https://doi.org/10.1016/j.bja.2023.12.035)

		미 육군의 2025년 Mission Partner Environment 지침은 파트너 간 공유 이해·상호 신뢰·통합된 노력을 만드는 기반을 강조한다. 구지의 합교와 가깝지만, 연결망 자체가 성공을 보장하지는 않는다. 권한·책임·중단 조건이 불명확하면 정보량만 늘고 행동은 갈라진다. 따라서 실무에서는 **담당자·확인자·다음 보고 시각**을 한 문장으로 맞춰야 한다. [미 육군 지침](https://www.army.mil/article/285043/commander_and_staff_guide_to_the_mission_partner_environment_handbook)
---
"""

SECTION5 = """## 5. 핵심 통찰 + 실생활 적용 + 생활루틴
**핵심 통찰**

交地는 모두가 드나들 수 있어 **내가 쓰는 길이 곧 상대의 접근로가 되는 상황**이고, 衢地는 여러 조·부서·책임자의 이해가 한곳에서 만나는 상황이다. 여기서 먼저 해야 할 일은 목소리를 높이는 것이 아니라, 누가 결정하고 누가 확인하며 언제 다시 보고할지를 먼저 연결하는 것이다. `先至而得天下衆`은 물리적으로 먼저 도착하라는 말보다 **다른 사람이 판단할 수 있는 공통 기준을 먼저 제시하라**는 뜻에 가깝다.

**실생활 적용 — 사실 → 형세 → 대응 → 결과 → 다음 행동**

인물관찰 기록의 2026년 7월 31일 장면에서 사용자는 에러 처리 뒤 피로가 쌓인 상태에서 다른 조 책임자에게 핸드폰 운용과 대응 계획을 추궁받았다. 처음에는 존댓말로 행위 중단을 요구하고 자기 조장의 지시였음을 밝혔지만, 모욕적 언행이 이어지자 언성이 높아졌다. 이것이 **사실**이다. 상대의 동기나 성격은 확인되지 않은 추정으로 남겨야 한다.

이 장면은 여러 조의 규칙과 책임선이 겹친 衢地였다. 개인 대 개인의 싸움으로 바뀌는 순간 공통 기준이 사라지고, 피로한 두 사람이 서로의 퇴로를 좁히게 된다. 가장 유리한 **대응**은 `우리 조 지시·현재 에러·확인할 책임자`를 한 문장으로 말한 뒤 각 조장을 같은 대화에 연결하고, 욕설·손가락질 같은 행위에는 짧게 중단을 요구한 다음 기록으로 전환하는 것이다. 그러면 쟁점이 인신공격이 아니라 업무 기준으로 돌아가고, **결과**도 누가 옳은지 소리로 겨루는 대신 책임자가 확인할 수 있는 형태로 남는다.

**다음 행동**

1. 타 조와 충돌 가능성이 생기면 `사실 / 내 조 지시 / 확인 책임자 / 다음 보고 시각`을 먼저 말한다.
2. 모욕적 언행에는 한 번만 구체적으로 중단을 요구하고, 반복되면 대화를 늘리지 말고 조장 호출과 기록으로 옮긴다.
3. 교대 뒤에는 합의된 기준을 짧게 남겨 다음 근무자가 같은 교지에서 다시 충돌하지 않게 한다.

**생활루틴 추천**

> 여러 조의 책임이 겹친 일을 개인끼리 따지기 시작하면 재수가 없다.

**이유**

공통 기준 없이 감정으로 맞서면 누구의 지시를 따라야 하는지 흐려지고, 원래의 에러보다 사람 사이 충돌이 더 큰 문제가 된다. 반대로 책임자와 확인 시각을 먼저 묶으면, 다자 이해관계가 얽힌 구지에서도 **싸우기 전에 관계와 판단 기준을 선점**할 수 있다.
"""

def replace_section(text: str, number: int, replacement: str) -> str:
    start = re.search(rf"^## {number}\..*$", text, re.MULTILINE)
    end = re.search(rf"^## {number + 1}\..*$", text[start.end():], re.MULTILINE)
    if not start or not end:
        raise RuntimeError(f"section {number} not found")
    end_pos = start.end() + end.start()
    return text[:start.start()] + replacement.rstrip() + "\n" + text[end_pos:]

text = PATH.read_text(encoding="utf-8")
text = replace_section(text, 2, SECTION2)
text = replace_section(text, 3, SECTION3)
text = re.sub(r"^## 4\..*$", '## 4. 역사적 실증 사례 {toggle="true" color="purple"}', text, count=1, flags=re.MULTILINE)

image_map = {
    "breitenfeld_commanders.png": "generated/jiudi3/breitenfeld_commanders_v2.png",
    "breitenfeld_command_structure.png": "generated/jiudi3/breitenfeld_command_structure_v2.png",
    "breitenfeld_powermap.png": "generated/jiudi3/breitenfeld_country_map_v2.png",
    "breitenfeld_codex_map.png": "generated/jiudi3/breitenfeld_strategy_map_v2.png",
    "breitenfeld_codex_sequence_map.png": "generated/jiudi3/breitenfeld_sequence_map_v2.png",
    "bi_commanders.png": "generated/jiudi3/bi_commanders_v2.png",
    "bi_command_structure.png": "generated/jiudi3/bi_command_structure_v2.png",
    "bi_powermap.png": "generated/jiudi3/bi_country_map_v2.png",
    "bi_codex_map.png": "generated/jiudi3/bi_strategy_map_v2.png",
    "bi_codex_sequence_map.png": "generated/jiudi3/bi_sequence_map_v2.png",
}
for old, new in image_map.items():
    text = re.sub(rf"(https://raw\.githubusercontent\.com/ForrestDPark/DailyHelloWorld/main/%EC%86%90%EC%9E%90%EB%B3%91%EB%B2%95/)[^)]*{re.escape(old)}", rf"\1{new}", text)

text = text.replace("<td>항목</td>\n<td>분석</td>", "<td>요소</td>\n<td>판단</td>")
five_rows = {
    '<td>🤝 <span color="green">**道 · 지기**</span></td>': '<td color="orange_bg">🤝 **道**</td>',
    '<td>👁️ <span color="blue">**天 · 지피·시기·상황**</span></td>': '<td color="blue_bg">🌤️ **天**</td>',
    '<td>📏 <span color="brown">**地 · 지형·원근·험이·광협·사생**</span></td>': '<td color="green_bg">🧭 **地**</td>',
    '<td>🧠 <span color="purple">**將 · 지신인용엄**</span></td>': '<td color="purple_bg">🎖️ **將**</td>',
}
for old, new in five_rows.items():
    text = text.replace(old, new)
text = text.replace(
    "</tr>\n</table>\n**5. 전력+배치+보급(法)**",
    '</tr>\n<tr>\n<td color="yellow_bg">⚙️ **法**</td>\n<td>아래 곡제·관도·주용 상세 비교에서 편제·지휘·보급이 실제로 어떻게 결합되거나 갈라졌는지 확인한다.</td>\n</tr>\n</table>\n**5. 전력+배치+보급(法)**',
)

west_story = """#### 틸리의 압박이 작센을 적에게 밀어주다
<span color="red">**틸리 백작**</span>은 작센을 굴복시키면 스웨덴의 길을 막을 수 있다고 보았다. 그러나 마그데부르크의 참상과 작센 침공은 중립을 유지하던 작센이 <span color="blue">**구스타브 아돌프**</span>에게 손을 내밀게 만들었다. 구지에서 힘으로 제3세력을 누르려 한 행동이 오히려 상대에게 衆을 건넨 셈이다.

#### 작센 전선이 무너져도 연합군 전체는 끊어지지 않았다
전투가 시작되자 <span color="red">**파펜하임**</span>의 반복 돌격은 스웨덴 우익에 막혔지만 황제군 우익은 작센군을 무너뜨렸다. 여기서 <span color="blue">**구스타브 호른**</span>은 예비대를 돌려 새 측면을 만들었다. 연합 한 축의 붕괴를 전체 붕괴로 번지게 두지 않은 것이 교지의 연결 관리였다.

#### 빼앗은 포와 회전한 전선이 승패를 뒤집다
스웨덴군은 얕은 대형과 기동 포병으로 방향을 바꾸고, 노획한 황제군 포까지 되돌려 썼다. 깊은 테르시오는 새 위협 방향에 늦게 반응했다. 먼저 작센의 동맹을 얻고 전투 중 지휘 연결까지 유지한 연합군이 숫자를 넘어 전장의 방향을 차지했다.

#### 法 한눈 비교 — 곡제·관도·주용
<table fit-page-width="true" header-row="true">
<tr><td>진영</td><td>곡제</td><td>관도</td><td>주용</td></tr>
<tr color="blue"><td>스웨덴·작센 연합군</td><td>얕은 여단·예비대·기동포</td><td>연합 지휘와 현장 전환</td><td>연대포와 탄약 회전</td></tr>
<tr color="red"><td>황제·가톨릭동맹군</td><td>깊은 테르시오·독주 기병</td><td>파펜하임 돌격 통제 실패</td><td>현지 징발과 무거운 포</td></tr>
</table>
"""

east_story = """#### 정나라가 항복한 뒤에 도착한 진군
<span color="blue">**초 장왕**</span>은 정나라를 포위해 항복을 받은 뒤 물러나는 모양을 보였고, 정나라가 다시 등을 돌리자 전장을 선택했다. 반면 <span color="red">**순림보**</span>가 이끄는 진군은 구하려던 정나라의 향배가 이미 바뀐 뒤 도착했다. 先至의 차이는 거리보다 정치적 사실의 차이였다.

#### 철수 명령과 독단 도하가 한 군대를 두 갈래로 찢다
<span color="red">**순림보**</span>는 싸움을 피하려 했지만 <span color="red">**선곡**</span>은 황하를 독단으로 건넜다. 후속 부대는 동료를 버릴 수 없어 따라갔고, 진군은 같은 전장에 있으면서도 서로 다른 명령을 따랐다. 교지에서 왕래는 가능했지만 지휘 연결이 없었다.

#### 하나로 모인 초군이 갈라진 진군을 차례로 치다
<span color="blue">**손숙오**</span>와 <span color="blue">**오참**</span>의 조언 아래 초군은 결전을 선택하고 집중했다. 진군은 황하 퇴로와 상충 명령 때문에 전열을 정리하지 못했다. 초는 정나라라는 구지를 먼저 얻고 군령을 하나로 묶었고, 진은 늦게 도착해 내부까지 갈라졌다.

#### 法 한눈 비교 — 곡제·관도·주용
<table fit-page-width="true" header-row="true">
<tr><td>진영</td><td>곡제</td><td>관도</td><td>주용</td></tr>
<tr color="blue"><td>초나라군</td><td>전차·보병을 결전점에 집중</td><td>초 장왕의 최종 결정 아래 통일</td><td>정나라 굴복으로 현지 지속 기반 확보</td></tr>
<tr color="red"><td>진나라군</td><td>상·중·하군이 도하 과정에서 분리</td><td>순림보 명령과 선곡 독단 충돌</td><td>황하 도하와 퇴로 혼잡으로 지속력 저하</td></tr>
</table>
"""

text = text.replace("**〈틸리 백작 (패)〉**", west_story + "\n**〈틸리 백작 (패)〉**", 1)
text = text.replace("**〈순림보 · 선곡 (패)〉**", east_story + "\n**〈순림보 · 선곡 (패)〉**", 1)

law_west = """##### 法을 압축하지 않고 보기 — 곡제·관도·주용
**곡제 曲制(곡제): 부대를 어떻게 나누고 결합했는가**
<table fit-page-width="true" header-row="true">
<tr><td>진영</td><td>실제 운용</td></tr>
<tr color="blue"><td>스웨덴·작센 연합군</td><td>얕은 여단과 소형 연대포, 기병, 예비대를 결합해 전선이 꺾여도 방향을 바꿀 수 있었다.</td></tr>
<tr color="red"><td>황제·가톨릭동맹군</td><td>깊은 테르시오와 양익 기병을 운용했으나 독립 돌격과 느린 방향 전환이 결합을 깨뜨렸다.</td></tr>
</table>
**관도 官道(관도): 누가 명령하고 어떻게 전달했는가**
<table fit-page-width="true" header-row="true">
<tr><td>진영</td><td>실제 운용</td></tr>
<tr color="blue"><td>스웨덴·작센 연합군</td><td>구스타브 아돌프의 의도 아래 호른이 붕괴 지점에 예비대를 돌렸고, 동맹군의 약점을 즉시 보완했다.</td></tr>
<tr color="red"><td>황제·가톨릭동맹군</td><td>틸리의 전체 계획보다 파펜하임의 반복 돌격이 앞서 지휘 통제가 분산됐다.</td></tr>
</table>
**주용 主用(주용): 군량·장비·전투 지속 능력을 어떻게 썼는가**
<table fit-page-width="true" header-row="true">
<tr><td>진영</td><td>실제 운용</td></tr>
<tr color="blue"><td>스웨덴·작센 연합군</td><td>기동 연대포와 표준화된 탄약 운용으로 전선 전환 뒤에도 화력을 지속했다.</td></tr>
<tr color="red"><td>황제·가톨릭동맹군</td><td>무거운 포와 현지 징발에 기대어 작센 민심과 기동 지속성을 함께 잃었다.</td></tr>
</table>
"""
law_east = """##### 法을 압축하지 않고 보기 — 곡제·관도·주용
**곡제 曲制(곡제): 부대를 어떻게 나누고 결합했는가**
<table fit-page-width="true" header-row="true">
<tr><td>진영</td><td>실제 운용</td></tr>
<tr color="blue"><td>초나라군</td><td>왕의 결전 의도 아래 전차와 보병을 한 공격 축에 집중했다.</td></tr>
<tr color="red"><td>진나라군</td><td>삼군 편제가 황하 도하와 상충 명령으로 시간·공간상 분리됐다.</td></tr>
</table>
**관도 官道(관도): 누가 명령하고 어떻게 전달했는가**
<table fit-page-width="true" header-row="true">
<tr><td>진영</td><td>실제 운용</td></tr>
<tr color="blue"><td>초나라군</td><td>초 장왕이 손숙오·오참의 진언을 듣고 최종 결정을 하나로 통일했다.</td></tr>
<tr color="red"><td>진나라군</td><td>순림보의 철수 판단과 선곡의 독단 도하가 충돌해 예하 부대가 서로 다른 행동을 했다.</td></tr>
</table>
**주용 主用(주용): 군량·장비·전투 지속 능력을 어떻게 썼는가**
<table fit-page-width="true" header-row="true">
<tr><td>진영</td><td>실제 운용</td></tr>
<tr color="blue"><td>초나라군</td><td>정나라를 먼저 굴복시켜 배후의 정치·보급 위험을 줄인 뒤 결전에 집중했다.</td></tr>
<tr color="red"><td>진나라군</td><td>황하를 사이에 둔 도하와 퇴로 혼잡 때문에 전차·보병의 지속 운용이 무너졌다.</td></tr>
</table>
"""
text = text.replace("### 동양 — 필(邲) 전투", law_west + "\n### 동양 — 필(邲) 전투", 1)
text = text.replace("\n### 최신 天·확률·편향 보완", "\n" + law_east + "\n### 최신 天·확률·편향 보완", 1)

text = replace_section(text, 5, SECTION5) if re.search(r"^## 6\.", text, re.MULTILINE) else re.sub(r"^## 5\..*$[\s\S]*$", SECTION5, text, count=1, flags=re.MULTILINE)
PATH.write_text(text.strip() + "\n", encoding="utf-8")
