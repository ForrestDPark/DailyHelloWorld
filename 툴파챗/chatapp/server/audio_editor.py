"""오디오 편집기의 결정론적 MP3 잘라내기 도우미."""
import math


def normalize_cuts(cuts, duration):
    """삭제 구간을 범위 안으로 제한하고 겹치는 구간을 합친다."""
    if not isinstance(cuts, list) or not math.isfinite(duration) or duration <= 0:
        return []
    cleaned = []
    for cut in cuts:
        if not isinstance(cut, dict):
            continue
        try:
            start, end = float(cut["start"]), float(cut["end"])
        except (KeyError, TypeError, ValueError):
            continue
        if not math.isfinite(start) or not math.isfinite(end):
            continue
        start, end = max(0.0, start), min(duration, end)
        if end - start >= 0.05:
            cleaned.append([start, end])
    cleaned.sort()
    merged = []
    for start, end in cleaned:
        if merged and start <= merged[-1][1] + 0.001:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return merged


def kept_segments(cuts, duration):
    """삭제 구간의 여집합인 보존 구간을 반환한다."""
    cursor = 0.0
    kept = []
    for start, end in normalize_cuts(cuts, duration):
        if start - cursor >= 0.05:
            kept.append((cursor, start))
        cursor = max(cursor, end)
    if duration - cursor >= 0.05:
        kept.append((cursor, duration))
    return kept


def ffmpeg_filter(segments):
    """한 입력의 보존 구간을 잘라 순서대로 잇는 ffmpeg 필터를 만든다."""
    chains = []
    labels = []
    for index, (start, end) in enumerate(segments):
        label = f"a{index}"
        chains.append(
            f"[0:a]atrim=start={start:.6f}:end={end:.6f},asetpts=PTS-STARTPTS[{label}]"
        )
        labels.append(f"[{label}]")
    chains.append(f"{''.join(labels)}concat=n={len(labels)}:v=0:a=1[out]")
    return ";".join(chains)
