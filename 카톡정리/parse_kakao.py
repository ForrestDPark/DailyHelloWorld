#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""카카오톡 대화 내보내기(.txt) 파서 + Q&A 후보 추출기.

사용법:
    python3 parse_kakao.py "<Talk_*.txt 경로>" [--outdir DIR]

출력 (outdir, 기본값: txt파일과 같은 폴더):
    messages.json      전체 메시지(입퇴장/봇 공지 제외), [{date, sender, text}, ...]
    admin_posts.json    운영진(설정한 이름 포함) 발신 장문 메시지만
    qa_candidates.json  물음표/의문형 종결어미로 끝나는 "질문 후보" 메시지 +
                         그 뒤 이어지는 대화 맥락(기본 20줄)을 함께 묶어서 저장.
                         이 파일을 사람이(=세션의 Claude가) 직접 읽고 실제
                         Q&A인지 판단 + 중복 질문 병합 + 답변 통합을 해야 한다.
                         (규칙 기반으로는 잡담/수사의문문과 진짜 질문을 구분 못함)
"""
import argparse
import json
import re
from pathlib import Path

MSG_RE = re.compile(r'^(\d{1,2}/\d{1,2}/\d{2}) (오전|오후) (\d{1,2}):(\d{2}), ([^:]+) : (.*)$')
SYS_RE = re.compile(r'^\d{1,2}/\d{1,2}/\d{2} (오전|오후) \d{1,2}:\d{2}: ')
DATE_RE = re.compile(r'^\d{4}년 \d{1,2}월 \d{1,2}일')
QUESTION_ENDINGS = ('나요', '까요', '건가요', '인가요', '되나요', '될까요', '됐나요', '있나요', '없나요')


def parse_file(path):
    with open(path, encoding='utf-8') as f:
        lines = f.readlines()

    messages = []
    cur = None
    for line in lines:
        line = line.rstrip('\n')
        m = MSG_RE.match(line)
        if m:
            if cur:
                messages.append(cur)
            date, ampm, h, mi, sender, text = m.groups()
            cur = {'date': date, 'time': f'{ampm} {h}:{mi}', 'sender': sender.strip(), 'text': text}
        elif SYS_RE.match(line) or DATE_RE.match(line):
            if cur:
                messages.append(cur)
                cur = None
        else:
            if cur:
                cur['text'] += '\n' + line
    if cur:
        messages.append(cur)
    return messages


def is_question(text):
    t = text.strip()
    if not t:
        return False
    if '?' in t:
        return True
    return t.endswith(QUESTION_ENDINGS)


def extract_qa_candidates(messages, context_window=20):
    candidates = []
    for i, m in enumerate(messages):
        if is_question(m['text']):
            context = messages[i:i + context_window]
            candidates.append({'question': m, 'context': context})
    return candidates


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('txt_path')
    ap.add_argument('--outdir', default=None)
    ap.add_argument('--admin-names', nargs='*', default=[],
                     help='운영진으로 취급할 발신자 이름(부분 일치). 지정 시 admin_posts.json에 반영.')
    ap.add_argument('--context-window', type=int, default=20)
    args = ap.parse_args()

    txt_path = Path(args.txt_path)
    outdir = Path(args.outdir) if args.outdir else txt_path.parent

    messages = parse_file(txt_path)
    with open(outdir / 'messages.json', 'w', encoding='utf-8') as f:
        json.dump(messages, f, ensure_ascii=False, indent=1)

    if args.admin_names:
        admin_posts = [m for m in messages
                        if any(a in m['sender'] for a in args.admin_names) and len(m['text']) > 60]
        with open(outdir / 'admin_posts.json', 'w', encoding='utf-8') as f:
            json.dump(admin_posts, f, ensure_ascii=False, indent=1)

    qa_candidates = extract_qa_candidates(messages, args.context_window)
    with open(outdir / 'qa_candidates.json', 'w', encoding='utf-8') as f:
        json.dump(qa_candidates, f, ensure_ascii=False, indent=1)

    print(f'총 메시지 {len(messages)}개, 질문 후보 {len(qa_candidates)}개 -> {outdir}')


if __name__ == '__main__':
    main()
