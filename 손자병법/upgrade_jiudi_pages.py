#!/usr/bin/env python3
"""구지편 2~8구절 기존 본문을 최신 공통 형식으로 기계 정리한다."""

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parent

META = {
    "02": {
        "quote": "유리한 자리를 남보다 늦게 확인하고 뒤늦게 다투면 재수가 없다.",
        "modern": "쟁지는 먼저 도착한 사실보다 **어떤 정보가 결정적 자원인지 먼저 알아차리는 상황인식**과 연결된다. 2025년 상황인식 체계적 문헌고찰은 사람·도구·과업환경의 상호작용을 함께 보아야 한다고 정리한다. 다만 빠른 판단만 강조하면 성급한 확신이 되므로, 선점 전에 반대 증거와 철수 기준을 함께 정해야 한다.",
        "prob": "게티즈버그에서 리는 이전 승리의 표본을 일반화해 북군이 다시 무너질 가능성을 높게 보았고, 미드는 고지와 내선을 확보해 방어 성공 확률을 높였다. 장평에서 조괄은 진군의 유인 가능성을 낮게 보았고, 백기는 퇴로·보급로 절단을 겹쳐 조군 붕괴 가능성을 높였다.",
        "bias": "리의 반복 공격은 과신과 확증편향, 조괄의 추격은 대표성 휴리스틱이 작동한 것으로 볼 수 있다.",
        "life": "인수인계 직후 결정적 정보와 담당 업무를 먼저 확인하지 않으면 작은 누락이 뒤늦은 정면 충돌로 커진다. 전씨가 복잡한 조치에서 흥분해 설명을 충분히 듣지 않는 행동이 나타날 때는 먼저 사실·담당·보고 시각을 적어 쟁지를 선점해야 한다.",
    },
    "03": {
        "quote": "동료가 합의 없이 선을 넘는 조짐을 보고도 바로 역할을 정리하지 않으면 재수가 없다.",
        "modern": "교지·구지는 개인 능력보다 **공유된 이해와 횡적 조정**이 중요하다. 미 육군 임무형 지휘도 상호 신뢰·공유된 이해·명확한 의도를 핵심으로 둔다. 다만 합의가 많다고 좋은 것은 아니며, 결정권과 중단 조건이 분명해야 한다.",
        "prob": "브라이텐펠트에서 틸리는 파펜하임의 반복 돌격과 작센 붕괴가 전체 전선을 무너뜨릴 위험을 충분히 통제하지 못했고, 구스타브는 예비대와 유연한 전환으로 회복 확률을 높였다. 필 전투에서 진군 지휘부는 선곡의 독단 행동이 전군을 끌고 갈 위험을 낮게 보았고, 초 장왕 측은 그 분열을 집중 타격했다.",
        "bias": "틸리의 기존 전술 고수에는 매몰비용과 과신, 진군 지휘부의 지연에는 정상성 편향이 작동한 것으로 볼 수 있다.",
        "life": "최씨처럼 정해진 역할을 수행하지 않는 행동이 반복될 때 기대만 유지하면 업무 공백이 다른 근무자에게 전가된다. 비난보다 모니터링·기록·조치의 담당과 확인 시각을 즉시 다시 정해 교지의 연결을 복구해야 한다.",
    },
    "04": {
        "quote": "일을 쌓아놓고 미루거나 빠져나오기 어려운 일에 오래 머물면 재수가 없다.",
        "modern": "중지·비지는 피로와 인지부하가 누적될수록 판단이 약해지는 환경이다. 최근 상황인식 연구는 환경 정보뿐 아니라 작업부하와 도구 설계가 위험 예측에 영향을 준다고 본다. 따라서 버티는 의지보다 체류시간·보급·철수 기준을 외부화해야 한다.",
        "prob": "바루스는 익숙한 행군 경험을 안전의 근거로 일반화해 반복 매복 가능성을 낮게 보았고, 아르미니우스는 지형·날씨·행군대형을 겹쳐 로마군 분절 가능성을 높였다. 심하전투에서 조명 연합군은 상호 지원 지연의 위험을 낮게 보았고, 후금군은 분산된 적을 순차 타격할 확률을 높였다.",
        "bias": "바루스의 신뢰와 행군 지속에는 정상성 편향, 연합군의 분진합격에는 계획 오류와 과신이 작동한 것으로 볼 수 있다.",
        "life": "복잡한 에러에서 전씨가 예민해지거나 설명을 듣지 않는 행동이 나타나면 같은 방식으로 오래 버티지 말고, 조치 단계를 끊어 상위 보고와 교대를 준비해야 한다. 체류시간을 정하지 않으면 비지가 위지로 변한다.",
    },
    "05": {
        "quote": "퇴로가 꼬인 상태에서 보고 없이 혼자 버티면 재수가 없다.",
        "modern": "위지·사지는 스트레스가 주의를 좁히고 대안 탐색을 줄이는 **터널 시야**와 연결된다. 상황인식 연구가 지각·이해·예측을 구분하는 이유도 눈앞의 위협만 보는 오류를 줄이기 위해서다. 즉시 행동하되 제3자의 확인과 퇴로 계산을 함께 두어야 한다.",
        "prob": "칸나에에서 바로는 수적 우세가 중앙 돌파로 이어질 가능성을 과대평가했고, 한니발은 이중 포위가 성립하도록 중앙 후퇴·강·기병 우세를 겹쳤다. 거록에서 진군은 제후군이 결집할 가능성을 낮게 보았고, 항우는 파부침주와 신속한 집중으로 결전 성공 가능성을 높였다.",
        "bias": "바로의 밀집 돌파에는 과신, 진군의 적 지원 가능성 무시에는 기저율 무시가 작동한 것으로 볼 수 있다.",
        "life": "설비 이상을 혼자 붙잡고 있으면 확인자와 지원자가 없어져 위지가 된다. 발견 즉시 사실·현재 조치·다음 보고 시각을 남기고, 일정 시간 안에 해결되지 않으면 상위 보고로 전환해야 한다.",
    },
    "06": {
        "quote": "상황이 바뀌었는데도 처음 세운 대응 원칙을 그대로 고집하면 재수가 없다.",
        "modern": "아홉 지형별 처방은 **적응적 전문성**과 닮았다. 숙련자는 규칙을 빠르게 적용하는 데서 끝나지 않고 조건이 바뀌면 규칙을 수정한다. 다만 유연성을 핑계로 절차를 매번 바꾸면 협업이 무너지므로 변경 이유와 새 기준을 공유해야 한다.",
        "prob": "만인대는 지휘부 상실 이후에도 이동·교섭·약탈·결전을 상황별로 바꾸어 생존 확률을 높였다. 가정에서 마속은 고지 점거의 이익만 보고 수원 차단 위험을 낮게 평가했고, 장합은 그 취약점을 이용해 직접 공격보다 포위 성공 확률을 높였다.",
        "bias": "마속이 병서의 고지 원칙을 현재 지형에 그대로 적용한 판단에는 확증편향과 과신이 작동한 것으로 볼 수 있다.",
        "life": "근무조의 인력과 집중도가 달라졌는데 기존 분담을 유지하면 공백이 생긴다. 최씨의 모니터링 누락이 반복되는 상황에서는 중요한 기록과 감시 역할을 재배치하고 변경 사실을 남겨야 한다.",
    },
    "07": {
        "quote": "앞뒤와 상하가 서로 구할 수 없는 상태로 일을 벌이면 재수가 없다.",
        "modern": "부대 분리는 팀 상황인식과 공유 정신모형 연구에 직접 연결된다. 구성원이 목표·역할·현재 상태를 함께 이해할수록 다음 행동을 예측하기 쉽다. 그러나 모두가 같은 오판을 공유할 수도 있으므로 독립 확인과 반대 의견 통로가 필요하다.",
        "prob": "아우스터리츠에서 연합군은 나폴레옹의 약한 우익 연출을 실제 약점으로 일반화했고, 나폴레옹은 중앙 고지가 비는 시간대를 골라 분단 성공 확률을 높였다. 이릉에서 유비는 긴 진영선의 동시 지원 가능성을 높게 보았고, 육손은 건조·피로·분산이 겹치는 때를 기다렸다.",
        "bias": "연합군의 남진에는 확증편향, 유비의 장기 진영 유지에는 매몰비용과 계획 오류가 작동한 것으로 볼 수 있다.",
        "life": "전씨가 복잡한 상황에서 말을 끊거나 흥분하고 최씨가 모니터링을 놓치는 행동이 겹치면 상하와 전후가 동시에 끊긴다. 사용자는 확인자·조치자·보고 시각을 한 줄로 남기고 독립 확인자를 한 명 지정해야 한다.",
    },
    "08": {
        "quote": "에러가 났는데 확인자·조치자·다음 보고 시점을 한 문장으로 맞추지 않으면 재수가 없다.",
        "modern": "",
        "prob": "",
        "bias": "",
        "life": "",
    },
}


def upgrade(number: str) -> None:
    src = Path(f"/tmp/jiudi_{number}_current.md")
    text = src.read_text(encoding="utf-8")
    meta = META[number]

    text = re.sub(r"^>\s*⚠️\s*\*\*재수 없는 행동\*\*:\s*", "> ", text)
    if text.startswith("> "):
        text = re.sub(r"^>.*$", f"> {meta['quote']}", text, count=1, flags=re.MULTILINE)
    else:
        text = f"> {meta['quote']}\n---\n" + text

    text = re.sub(r"^## ([1-5])\)", r"## \1.", text, flags=re.MULTILINE)
    text = re.sub(r"^### Codex판 전략지형도 \(재제작\)\s*$\n?", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\*전략지형도 — Codex판.*$\n?", "", text, flags=re.MULTILINE)

    # 제작한 Codex 지도만 전투 제목 바로 아래로 이동한다. 기존 참고 이미지는 보존한다.
    maps = re.findall(r"^!\[[^\]]*\]\([^\n]*_codex_map\.png\)\s*$", text, flags=re.MULTILINE)
    text = re.sub(r"^!\[[^\]]*\]\([^\n]*_codex_map\.png\)\s*$\n?", "", text, flags=re.MULTILINE)
    battle_heads = list(re.finditer(r"^### (?:서양|동양).*$", text, flags=re.MULTILINE))
    for heading, image in reversed(list(zip(battle_heads, maps))):
        pos = heading.end()
        text = text[:pos] + "\n" + image + text[pos:]

    for real, anon in {
        "전창완": "전씨",
        "이의준": "이씨",
        "안재윤": "안씨",
    }.items():
        text = text.replace(real, anon)

    if number != "08" and "⑤ 현대 심리학·군사학 연구" not in text:
        insert = (
            f"- **⑤ 현대 심리학·군사학 연구**: {meta['modern']}\n"
            "\t- [2025년 상황인식 체계적 문헌고찰](https://pubmed.ncbi.nlm.nih.gov/40619647/)\n"
            "\t- [미 육군 임무형 지휘와 공유된 이해](https://www.armyupress.army.mil/Journals/NCO-Journal/Archives/2020/May/Mission-Command/)\n"
        )
        text = re.sub(
            r"(?=^(?:## 4[\.\)]|<summary>4\.))",
            insert + "---\n",
            text,
            count=1,
            flags=re.MULTILINE,
        )

    if number != "08" and "최신 天·확률·편향 보완" not in text:
        probability_sentences = [
            sentence.strip()
            for sentence in re.split(r"(?<=[.!?])\s+", meta["prob"])
            if sentence.strip()
        ]
        while len(probability_sentences) < 2:
            probability_sentences.append(probability_sentences[-1])
        bias_parts = [part.strip() for part in meta["bias"].split(",") if part.strip()]
        while len(bias_parts) < 2:
            bias_parts.append(bias_parts[-1])
        block = (
            "\n### 최신 天·확률·편향 보완\n"
            f"- **서양 패군 — 확률 관점:** {probability_sentences[0]}\n"
            f"- **서양 승군 — 확률 관점:** 같은 조건에서 승군은 지형·예비대·퇴로를 겹쳐 패군보다 유리한 결과의 가능성을 높였다.\n"
            f"- **직관·편향 한 줄:** {bias_parts[0]}\n"
            f"- **동양 패군 — 확률 관점:** {probability_sentences[1]}\n"
            f"- **동양 승군 — 확률 관점:** 같은 조건에서 승군은 적의 분산과 시간차를 이용해 순차 격파 가능성을 높였다.\n"
            f"- **직관·편향 한 줄:** {bias_parts[1]}\n"
        )
        text = re.sub(
            r"(?=^(?:## 5[\.\)]|<summary>5\.))",
            block + "---\n",
            text,
            count=1,
            flags=re.MULTILINE,
        )

    if number != "08":
        start = re.search(r"^## 5[\.\)].*$", text, flags=re.MULTILINE)
        if start:
            text = text[: start.start()] + (
                "## 5. 핵심 통찰 + 실생활 적용 + 생활루틴\n"
                "**핵심 통찰**\n\n"
                "구지는 고정된 성격표가 아니라 상황이 바뀔 때 행동 원칙도 바꾸기 위한 진단 체계다. "
                "빠른 행동보다 먼저 현재의 퇴로·시간·연결·보급·이해관계를 정확히 분류해야 한다.\n\n"
                "**실생활 적용**\n\n"
                f"{meta['life']}\n\n"
                "**추천 문구**\n\n"
                f"{meta['quote']}\n\n"
                "**이유**\n\n"
                "작은 분류 오류를 방치하면 담당 누락·보고 지연·감정 충돌이 연쇄되어 선택지가 줄어든다. "
                "현재 국면과 중단 기준을 먼저 공유하는 것이 불패지지를 만드는 행동이다.\n"
            )
        else:
            summary_five = re.search(
                r"(<summary>5\.[^\n]*</summary>)(.*?)(?=</details>)",
                text,
                flags=re.DOTALL,
            )
            if summary_five:
                replacement = (
                    summary_five.group(1)
                    + "\n\n**핵심 통찰**\n\n"
                    + "구지는 고정된 성격표가 아니라 상황이 바뀔 때 행동 원칙도 바꾸기 위한 진단 체계다. "
                    + "현재의 퇴로·시간·연결·보급·이해관계를 먼저 분류해야 한다.\n\n"
                    + "**실생활 적용**\n\n"
                    + meta["life"]
                    + "\n\n**추천 문구**\n\n"
                    + meta["quote"]
                    + "\n\n**이유**\n\n"
                    + "담당·확인자·보고 시각을 먼저 공유해야 작은 누락이 선택지를 없애는 연쇄로 번지는 것을 막을 수 있다.\n"
                )
                text = text[: summary_five.start()] + replacement + text[summary_five.end() :]

    out = ROOT / "notion_drafts" / f"jiudi_{number}.md"
    if number == "05" and "3a632a1eae808150834eea5f44e9de9a" not in text:
        text += (
            '\n<page url="https://app.notion.com/p/'
            '3a632a1eae808150834eea5f44e9de9a">test-delete-me</page>\n'
        )
    out.write_text(text.strip() + "\n", encoding="utf-8")


def main() -> None:
    for number in META:
        upgrade(number)


if __name__ == "__main__":
    main()
