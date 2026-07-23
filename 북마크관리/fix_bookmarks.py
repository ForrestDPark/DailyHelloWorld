#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
크롬 북마크 일괄 점검/수정 스크립트

특정 폴더 안의 북마크를 전부 확인해서:
  - 정상(200)  -> 그대로 둠
  - 리다이렉트 -> 최종 주소로 자동 교체 (--apply 줄 때만 실제로 파일에 반영)
  - 깨짐(404 등/타임아웃) -> Wayback Machine(archive.org)에 예전 저장본이
    있는지 확인해서(--archive 줄 때만), 있으면 그 아카이브 주소를 후보로 보여줌
    (이것도 --apply 를 같이 줘야 실제로 반영됨). 아카이브에도 없으면 그냥
    목록으로만 보고하고 자동 수정하지 않음 — 그건 직접 검색해서 새 주소를
    찾아야 함(사이트 개편으로 URL 구조가 바뀐 경우가 많음).

사용법:
  1) 크롬을 완전히 종료한다 (Cmd+Q). 크롬이 켜져 있으면 우리가 고친 걸
     크롬이 다시 열릴 때 덮어써버릴 수 있음.
  2) 먼저 점검만 (파일 변경 없음):
       python3 fix_bookmarks.py "폴더이름" --archive
  3) 결과 확인하고 문제없으면 실제로 적용:
       python3 fix_bookmarks.py "폴더이름" --archive --apply
     (원본은 자동으로 .bak 파일로 백업됨)
  4) 다시 크롬을 연다.

여러 폴더에 같은 이름이 있으면 맨 처음 찾은 걸 사용한다.
--recursive 를 주면 하위 폴더까지 재귀적으로 다 검사한다.
폴더 구분 없이 북마크 전체를 대상으로 하려면 폴더 이름 대신 --all 사용:
  python3 fix_bookmarks.py --all --replace "OLD" "NEW"
"""

import argparse
import json
import shutil
import sys
from pathlib import Path
from urllib.parse import urlparse

import requests

BOOKMARKS_PATH = (
    Path.home()
    / "Library/Application Support/Google/Chrome/Default/Bookmarks"
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}
TIMEOUT = 10


def find_folder(node, target_name):
    if node.get("type") == "folder":
        if node.get("name") == target_name:
            return node
        for child in node.get("children", []):
            found = find_folder(child, target_name)
            if found:
                return found
    return None


def collect_bookmarks(folder, recursive):
    """(bookmark_dict, path_list) 튜플들을 순서대로 뽑아낸다."""
    result = []
    for child in folder.get("children", []):
        if child.get("type") == "url":
            result.append(child)
        elif child.get("type") == "folder" and recursive:
            result.extend(collect_bookmarks(child, recursive))
    return result


def check_url(url):
    """상태를 반환: ('ok', None) / ('redirected', final_url) / ('broken', reason)"""
    try:
        resp = requests.get(
            url, headers=HEADERS, timeout=TIMEOUT,
            allow_redirects=True, stream=True,
        )
        resp.close()
    except requests.RequestException as e:
        return "broken", str(e)

    if 200 <= resp.status_code < 300:
        final = resp.url
        if final.rstrip("/") == url.rstrip("/"):
            return "ok", None
        return "redirected", final
    return "broken", f"HTTP {resp.status_code}"


def wayback_lookup(url):
    """Wayback Machine에 저장된 스냅샷이 있으면 그 주소를 반환, 없으면 None."""
    try:
        resp = requests.get(
            "https://archive.org/wayback/available",
            params={"url": url},
            timeout=TIMEOUT,
        )
        snap = resp.json().get("archived_snapshots", {}).get("closest")
        if snap and snap.get("available"):
            return snap.get("url")
    except (requests.RequestException, ValueError):
        pass
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("folder", nargs="?", default=None, help="점검할 북마크 폴더 이름 (--all 쓰면 생략)")
    ap.add_argument("--all", action="store_true", help="폴더 구분 없이 북마크 전체를 대상으로 함")
    ap.add_argument("--recursive", action="store_true", help="하위 폴더까지 포함 (--all일 때는 항상 전체 포함)")
    ap.add_argument(
        "--replace", nargs=2, metavar=("OLD", "NEW"),
        help="접속 확인 없이, URL 안의 OLD 문자열을 NEW로 그냥 치환 (예: --replace kr43 kr44)",
    )
    ap.add_argument("--archive", action="store_true", help="깨진 링크는 Wayback Machine 저장본 검색")
    ap.add_argument("--apply", action="store_true", help="실제로 Bookmarks 파일에 반영 (기본은 미리보기만)")
    ap.add_argument("--bookmarks-file", default=str(BOOKMARKS_PATH), help="Bookmarks 파일 경로 (다른 프로필 쓸 때)")
    args = ap.parse_args()

    path = Path(args.bookmarks_file)
    if not path.exists():
        sys.exit(f"북마크 파일을 찾을 수 없음: {path}")

    data = json.loads(path.read_text(encoding="utf-8"))
    roots = data.get("roots", {})

    if args.all:
        bookmarks = []
        for key in ("bookmark_bar", "other", "synced"):
            if key in roots:
                bookmarks.extend(collect_bookmarks(roots[key], recursive=True))
        print(f"전체 북마크 대상: {len(bookmarks)}개\n")
    else:
        if not args.folder:
            sys.exit("폴더 이름을 지정하거나 --all 을 사용하세요.")
        folder = None
        for key in ("bookmark_bar", "other", "synced"):
            if key in roots:
                folder = find_folder(roots[key], args.folder)
                if folder:
                    break
        if folder is None:
            sys.exit(f'"{args.folder}" 폴더를 찾을 수 없음')
        bookmarks = collect_bookmarks(folder, args.recursive)

    if args.replace:
        old, new = args.replace
        matches = [bm for bm in bookmarks if old in bm.get("url", "")]
        print(f'"{old}" -> "{new}" : {len(matches)}개 북마크가 대상입니다.\n')
        for bm in matches:
            new_url = bm["url"].replace(old, new)
            print(f"  {bm.get('name','')}\n    {bm['url']}\n -> {new_url}\n")

        if not matches:
            return
        if not args.apply:
            print("미리보기 모드입니다. 실제로 반영하려면 --apply 를 붙여 다시 실행하세요.")
            return

        backup = path.with_suffix(path.suffix + ".bak")
        shutil.copy2(path, backup)
        print(f"원본 백업: {backup}")
        for bm in matches:
            bm["url"] = bm["url"].replace(old, new)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=3), encoding="utf-8")
        print(f"{len(matches)}개 북마크 주소를 치환했습니다. 크롬을 다시 열어서 확인하세요.")
        return

    print(f"{len(bookmarks)}개 북마크 점검 중...\n")

    redirected, archived, dead, ok_count = [], [], [], 0

    for bm in bookmarks:
        name, url = bm.get("name", ""), bm.get("url", "")
        status, info = check_url(url)
        if status == "ok":
            ok_count += 1
        elif status == "redirected":
            redirected.append((bm, url, info))
            print(f"[리다이렉트] {name}\n    {url}\n -> {info}\n")
        else:
            if args.archive:
                snap_url = wayback_lookup(url)
            else:
                snap_url = None
            if snap_url:
                archived.append((bm, url, snap_url))
                print(f"[아카이브 발견] {name}\n    {url}  ({info})\n -> {snap_url}\n")
            else:
                dead.append((name, url, info))
                print(f"[깨짐]      {name}\n    {url}\n    사유: {info}\n")

    print("=" * 60)
    print(
        f"정상 {ok_count}개 / 리다이렉트 {len(redirected)}개 / "
        f"아카이브로 대체 가능 {len(archived)}개 / 완전히 죽음 {len(dead)}개"
    )

    if dead:
        print("\n완전히 죽은 링크 (아카이브도 없음 — 직접 새 주소를 찾아야 함):")
        for name, url, info in dead:
            print(f"  - {name}: {url}  ({info})")

    to_apply = redirected + archived
    if not args.apply:
        if not args.archive and (dead or archived == []):
            print('\n(--archive 를 추가하면 깨진 링크는 Wayback Machine에서 저장본을 찾아봅니다.)')
        print("\n미리보기 모드입니다. 실제로 반영하려면 --apply 를 붙여 다시 실행하세요.")
        return

    if not to_apply:
        print("\n반영할 변경사항이 없습니다.")
        return

    backup = path.with_suffix(path.suffix + ".bak")
    shutil.copy2(path, backup)
    print(f"\n원본 백업: {backup}")

    for bm, old_url, new_url in to_apply:
        bm["url"] = new_url

    path.write_text(json.dumps(data, ensure_ascii=False, indent=3), encoding="utf-8")
    print(f"{len(to_apply)}개 북마크 주소를 갱신했습니다 (리다이렉트 {len(redirected)} + 아카이브 대체 {len(archived)}). 크롬을 다시 열어서 확인하세요.")


if __name__ == "__main__":
    main()
