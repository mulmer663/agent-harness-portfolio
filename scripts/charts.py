#!/usr/bin/env python3
"""data/*.csv → assets/charts/<이름>-{light,dark}.svg. 표준 라이브러리만 쓴다.

글자는 <text> 로 남긴다(경로로 바꾸지 않는다) — 금칙어 검사가 차트 안 글자까지 읽게 하려는 것이다.
라이트·다크는 같은 색상 순서의 두 단계(검증한 팔레트)로 각각 그리고, README 에서 <picture> 로 고른다.
막대마다 <title> 이 있어 SVG 를 직접 열면 마우스를 올려 값을 볼 수 있다. 표 보기는 data/*.csv 와 각 문서의 표다.
"""
import collections
import csv
import pathlib
from xml.sax.saxutils import escape

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT = ROOT / "assets" / "charts"

THEMES = {
    "light": dict(bg="#ffffff", ink="#1f2328", ink2="#59636e", grid="#d8dee4", gap="#ffffff",
                  series=["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300"]),
    "dark": dict(bg="#0d1117", ink="#e6edf3", ink2="#9198a1", grid="#30363d", gap="#0d1117",
                 series=["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300"]),
}
FONT = "-apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', 'Noto Sans KR', 'Malgun Gothic', sans-serif"
REPO_NAME = {"IAM": "IAM 플랫폼", "LEAK": "유출 계정 탐지", "MFA": "MFA 제품"}
REPOS = ["IAM", "LEAK", "MFA"]


def read(name):
    with open(DATA / name) as f:
        return list(csv.DictReader(f))


class Svg:
    def __init__(self, w, h, theme, title, subtitle):
        self.t = THEMES[theme]
        self.w, self.h = w, h
        self.parts = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" '
            f'font-family="{escape(FONT)}" role="img" aria-label="{escape(title)}">',
            f"<title>{escape(title)}</title>",
            f'<rect width="{w}" height="{h}" fill="{self.t["bg"]}" rx="8"/>',
        ]
        self.text(20, 30, title, size=16, weight=600)
        self.text(20, 50, subtitle, size=12, fill=self.t["ink2"])

    def text(self, x, y, s, size=12, fill=None, anchor="start", weight=400):
        self.parts.append(f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" font-weight="{weight}" '
                          f'fill="{fill or self.t["ink"]}" text-anchor="{anchor}">{escape(str(s))}</text>')

    def line(self, x1, y1, x2, y2, stroke=None, width=1, dash=None):
        d = f' stroke-dasharray="{dash}"' if dash else ""
        self.parts.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
                          f'stroke="{stroke or self.t["grid"]}" stroke-width="{width}"{d}/>')

    def bar(self, x, y, w, h, fill, tip, round_end=None, r=4):
        """막대 하나. round_end 가 'top'·'right' 면 그 끝만 둥글린다(기준선 쪽은 각지게)."""
        if h <= 0 or w <= 0:
            return
        r = min(r, w / 2, h / 2)
        if round_end == "top":
            d = (f"M{x:.1f},{y + h:.1f} L{x:.1f},{y + r:.1f} Q{x:.1f},{y:.1f} {x + r:.1f},{y:.1f} "
                 f"L{x + w - r:.1f},{y:.1f} Q{x + w:.1f},{y:.1f} {x + w:.1f},{y + r:.1f} L{x + w:.1f},{y + h:.1f} Z")
        elif round_end == "right":
            d = (f"M{x:.1f},{y:.1f} L{x + w - r:.1f},{y:.1f} Q{x + w:.1f},{y:.1f} {x + w:.1f},{y + r:.1f} "
                 f"L{x + w:.1f},{y + h - r:.1f} Q{x + w:.1f},{y + h:.1f} {x + w - r:.1f},{y + h:.1f} L{x:.1f},{y + h:.1f} Z")
        else:
            d = f"M{x:.1f},{y:.1f} h{w:.1f} v{h:.1f} h{-w:.1f} Z"
        self.parts.append(f'<path d="{d}" fill="{fill}"><title>{escape(tip)}</title></path>')

    def legend(self, x, y, items):
        for label, color in items:
            self.parts.append(f'<rect x="{x}" y="{y - 9}" width="10" height="10" rx="2" fill="{color}"/>')
            self.text(x + 15, y, label, size=12, fill=self.t["ink2"])
            x += 15 + 7.5 * len(label) + (6 * sum(1 for c in label if ord(c) > 0x3000)) + 18

    def save(self, name, theme):
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / f"{name}-{theme}.svg").write_text("\n".join(self.parts + ["</svg>"]) + "\n")


def ticks(vmax, n=4):
    raw = vmax / n
    mag = 10 ** (len(str(int(raw))) - 1)
    step = next(m * mag for m in (1, 2, 2.5, 5, 10) if m * mag >= raw)
    return [step * i for i in range(n + 2) if step * i <= vmax * 1.05 + step], step


def monthly(theme):
    rows = read("monthly_commits.csv")
    months = sorted({r["month"] for r in rows})
    val = {(r["month"], r["repo"]): int(r["commits_nonmerge"]) for r in rows}
    totals = {m: sum(val.get((m, k), 0) for k in REPOS) for m in months}
    s = Svg(720, 380, theme, "월별 커밋 수 (병합 제외)",
            "통합 브랜치 기준 · 2026-06 과 2026-11 은 부분 월(첫 커밋 06-23, 스냅샷 11-06)")
    x0, y0, pw, ph = 70, 330, 620, 230
    tk, _ = ticks(max(totals.values()))
    top = tk[-1]
    for v in tk:
        y = y0 - ph * v / top
        s.line(x0, y, x0 + pw, y)
        s.text(x0 - 8, y + 4, f"{v:,.0f}", size=11, fill=s.t["ink2"], anchor="end")
    bw = pw / len(months) * 0.56
    for i, m in enumerate(months):
        cx = x0 + pw / len(months) * (i + 0.5)
        y = y0
        present = [k for k in REPOS if val.get((m, k), 0)]
        for j, k in enumerate(REPOS):
            v = val.get((m, k), 0)
            if not v:
                continue
            h = ph * v / top
            is_top = k == present[-1]
            gap = 0 if is_top or h <= 4 else 2  # 4px 이하 조각은 간격을 빼면 사라지므로 간격 없이 그린다
            s.bar(cx - bw / 2, y - h + gap, bw, max(h - gap, 1.5),
                  s.t["series"][REPOS.index(k)], f"{m} {REPO_NAME[k]}: {v:,}", "top" if is_top else None)
            y -= h
        s.text(cx, y - 8, f"{totals[m]:,}", size=12, weight=600, anchor="middle")
        label = m.replace("2026-", "") + "월" + (" (부분)" if m in ("2026-06", "2026-11") else "")
        s.text(cx, y0 + 18, label, size=12, fill=s.t["ink2"], anchor="middle")
    s.line(x0, y0, x0 + pw, y0, stroke=s.t["ink2"])
    s.legend(x0, 76, [(REPO_NAME[k], s.t["series"][i]) for i, k in enumerate(REPOS)])
    s.save("monthly-commits", theme)


def code_scale(theme):
    rows = read("code_lines.csv")
    agg = collections.defaultdict(int)
    for r in rows:
        if r["group"] == "Docs":
            continue
        agg[(r["repo"], r["kind"])] += int(r["nonblank_lines"])
    s = Svg(720, 300, theme, "저장소별 코드 규모 — 제품 코드 대 테스트 코드",
            "스냅샷 트리의 빈 줄 뺀 줄 수 · Java·TS·SQL·스크립트 · 문서·lockfile·빌드 산출물 폴더 제외 · IAM 은 첫 커밋의 초기 코드 9.0만 줄 포함")
    x0, pw = 150, 470
    vmax = max(agg.values())
    tk, _ = ticks(vmax)
    top = tk[-1]
    y_top, y_bot = 90, 270
    for v in tk:
        x = x0 + pw * v / top
        s.line(x, y_top - 6, x, y_bot)
        s.text(x, y_bot + 16, f"{v / 1000:,.0f}k", size=11, fill=s.t["ink2"], anchor="middle")
    bh = 20
    for i, k in enumerate(REPOS):
        yb = y_top + i * 60
        mn, ts = agg[(k, "main")], agg[(k, "test")]
        s.text(x0 - 12, yb + bh + 4, REPO_NAME[k], size=13, anchor="end", weight=600)
        for j, (kind, v) in enumerate((("제품 코드", mn), ("테스트 코드", ts))):
            y = yb + j * (bh + 2)
            w = pw * v / top
            s.bar(x0, y, w, bh, s.t["series"][j], f"{REPO_NAME[k]} {kind}: {v:,}줄", "right")
            s.text(x0 + w + 6, y + 14, f"{v / 1000:,.1f}k", size=11, fill=s.t["ink2"])
        s.text(x0 + pw + 80, yb + bh + 4, f"테스트 비율 {ts / (mn + ts):.0%}", size=12, anchor="end",
               fill=s.t["ink"], weight=600)
    s.line(x0, y_top - 6, x0, y_bot, stroke=s.t["ink2"])
    s.legend(x0, 76, [("제품 코드", s.t["series"][0]), ("테스트 코드", s.t["series"][1])])
    s.save("code-scale", theme)


TYPE_GROUPS = [("feat", ["feat"]), ("fix", ["fix"]), ("test", ["test"]), ("docs", ["docs"]),
               ("refactor·perf", ["refactor", "perf"]),
               ("기타", ["chore", "build", "ci", "style", "revert", "other"])]


def commit_types(theme):
    rows = read("commit_types.csv")
    val = collections.defaultdict(int)
    for r in rows:
        for g, members in TYPE_GROUPS:
            if r["type"] in members:
                val[(r["repo"], g)] += int(r["commits_nonmerge"])
    s = Svg(720, 290, theme, "커밋 유형 비율 (Conventional Commits 접두, 병합 제외)",
            "복합 접두(test+fix 등)는 첫 토큰으로 센다 · 접두가 없거나 낯선 것은 기타")
    x0, pw, y_top, bh = 150, 520, 100, 34
    for i, k in enumerate(REPOS):
        tot = sum(val[(k, g)] for g, _ in TYPE_GROUPS)
        y = y_top + i * 52
        s.text(x0 - 12, y + 16, REPO_NAME[k], size=13, anchor="end", weight=600)
        s.text(x0 - 12, y + 31, f"{tot:,}건", size=11, anchor="end", fill=s.t["ink2"])
        x = x0
        for j, (g, _) in enumerate(TYPE_GROUPS):
            v = val[(k, g)]
            w = pw * v / tot
            last = j == len(TYPE_GROUPS) - 1
            s.bar(x, y, max(w - (0 if last else 2), 0), bh, s.t["series"][j],
                  f"{REPO_NAME[k]} {g}: {v:,}건 ({v / tot:.1%})", "right" if last else None)
            if v / tot >= 0.08:
                s.text(x + w / 2, y + 22, f"{v / tot:.0%}", size=11, anchor="middle",
                       fill="#ffffff" if theme == "light" and j in (0, 1, 5) else ("#0d1117" if theme == "light" else "#ffffff"),
                       weight=600)
            x += w
    s.legend(x0, 80, [(g, s.t["series"][j]) for j, (g, _) in enumerate(TYPE_GROUPS)])
    s.save("commit-types", theme)


def review_share(theme):
    rows = read("review_by_month.csv")
    by = collections.defaultdict(lambda: [0, 0, 0])
    for r in rows:
        b = by[r["month"]]
        b[0] += int(r["commits_nonmerge"])
        b[1] += int(r["review_mention"])
        b[2] += int(r["fix"])
    months = sorted(by)
    s = Svg(720, 360, theme, "리뷰를 언급한 커밋과 fix 커밋의 비율 (세 저장소 합)",
            "커밋 제목 키워드 휴리스틱(리뷰·review·reviewer) · 병합 제외 · 2026-06·11 은 부분 월")
    x0, y0, pw, ph = 70, 310, 600, 210
    for v in (0, 0.1, 0.2, 0.3, 0.4, 0.5):
        y = y0 - ph * v / 0.5
        s.line(x0, y, x0 + pw, y)
        s.text(x0 - 8, y + 4, f"{v:.0%}", size=11, fill=s.t["ink2"], anchor="end")
    xs = [x0 + pw * (i + 0.5) / len(months) for i in range(len(months))]
    for idx, (name, color) in enumerate((("리뷰 언급", s.t["series"][0]), ("fix 커밋", s.t["series"][1]))):
        pts = [(xs[i], y0 - ph * (by[m][1 + idx] / by[m][0]) / 0.5) for i, m in enumerate(months)]
        s.parts.append(f'<polyline points="{" ".join(f"{x:.1f},{y:.1f}" for x, y in pts)}" fill="none" '
                       f'stroke="{color}" stroke-width="2" stroke-linejoin="round"/>')
        for i, (x, y) in enumerate(pts):
            m = months[i]
            v = by[m][1 + idx] / by[m][0]
            s.parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4.5" fill="{color}" stroke="{s.t["bg"]}" '
                           f'stroke-width="2"><title>{m} {name}: {by[m][1 + idx]:,}/{by[m][0]:,} ({v:.1%})</title></circle>')
            if i in (0, len(pts) - 1) or m == "2026-10":
                other = by[m][2 - idx] / by[m][0]
                above = v >= other  # 두 값 중 높은 쪽은 위, 낮은 쪽은 아래 — 같은 달의 두 라벨이 겹치지 않게
                s.text(x, y - 10 if above else y + 20, f"{v:.0%}", size=11, anchor="middle", weight=600)
    for i, m in enumerate(months):
        s.text(xs[i], y0 + 18, m.replace("2026-", "") + "월", size=12, fill=s.t["ink2"], anchor="middle")
    s.line(x0, y0, x0 + pw, y0, stroke=s.t["ink2"])
    s.legend(x0, 76, [("리뷰 언급", s.t["series"][0]), ("fix 커밋", s.t["series"][1])])
    s.save("review-share", theme)


def merge_review(theme):
    rows = [r for r in read("integration_merges_review.csv") if r["repo"] == "IAM"]
    s = Svg(720, 300, theme, "통합 병합 메시지에 리뷰 단어가 든 비율 — IAM 플랫폼",
            "통합 브랜치 first-parent 병합 · 세션 감사(09-29)와 병합 게이트(10-21) 도입일로 가른 구간 · 관측치이며 인과가 아니다")
    x0, pw, y_top, bh, step = 200, 440, 100, 34, 56
    n_rows = len(rows)
    for v in (0, 0.25, 0.5, 0.75, 1.0):
        x = x0 + pw * v
        s.line(x, y_top - 8, x, y_top + n_rows * step)
        s.text(x, y_top + n_rows * step + 16, f"{v:.0%}", size=11, fill=s.t["ink2"], anchor="middle")
    labels = {"p1_to_0928": "~ 09-28", "p2_0929_to_1020": "09-29 ~ 10-20 (감사)",
              "p3_from_1021": "10-21 ~ (감사 + 게이트)"}
    for i, r in enumerate(rows):
        n, rv = int(r["integration_merges"]), int(r["review_word_in_message"])
        y = y_top + i * step
        s.text(x0 - 12, y + 16, labels[r["period"]], size=13, anchor="end", weight=600)
        s.text(x0 - 12, y + 31, f"병합 {n:,}건", size=11, anchor="end", fill=s.t["ink2"])
        w = pw * rv / n
        s.bar(x0, y, w, bh, s.t["series"][0], f"{labels[r['period']]}: {rv:,}/{n:,} ({rv / n:.1%})", "right")
        s.text(x0 + w + 8, y + 22, f"{rv / n:.0%}  ({rv:,}/{n:,})", size=12, weight=600)
    s.line(x0, y_top - 8, x0, y_top + n_rows * step, stroke=s.t["ink2"])
    s.save("merge-review", theme)


AREAS = [("notes", "작업 노트"), ("knowledge", "승격 규칙(30_knowledge)"), ("harness", "하네스 정의"),
         ("audit", "세션 감사"), ("daily", "데일리 요약")]


def wiki_areas(theme):
    rows = read("wiki_commits_by_area.csv")
    val = {(r["month"], r["area"]): int(r["commits"]) for r in rows}
    months = sorted({r["month"] for r in rows})
    s = Svg(720, 360, theme, "지식 저장소 커밋 — 영역별 (월별)",
            "지식 저장소 git 이력은 2026-09-04 시작 · 한 커밋이 여러 영역을 건드리면 영역마다 1 · 11월은 부분 월")
    x0, y0, pw, ph = 70, 310, 620, 200
    tk, _ = ticks(max(val.values()))
    top = tk[-1]
    for v in tk:
        y = y0 - ph * v / top
        s.line(x0, y, x0 + pw, y)
        s.text(x0 - 8, y + 4, f"{v:,.0f}", size=11, fill=s.t["ink2"], anchor="end")
    gw = pw / len(months)
    bw = gw * 0.75 / len(AREAS)
    for i, m in enumerate(months):
        gx = x0 + gw * i + gw * 0.125
        for j, (a, name) in enumerate(AREAS):
            v = val.get((m, a), 0)
            h = ph * v / top
            x = gx + j * bw
            s.bar(x + 1, y0 - h, bw - 2, h, s.t["series"][j], f"{m} {name}: {v}", "top")
            s.text(x + bw / 2, y0 - h - 5, v, size=10, anchor="middle", fill=s.t["ink2"])
        s.text(x0 + gw * (i + 0.5), y0 + 18, m.replace("2026-", "") + "월" + (" (부분)" if m == "2026-11" else ""),
               size=12, fill=s.t["ink2"], anchor="middle")
    s.line(x0, y0, x0 + pw, y0, stroke=s.t["ink2"])
    s.legend(x0, 76, [(name, s.t["series"][j]) for j, (_, name) in enumerate(AREAS)])
    s.save("wiki-areas", theme)


def main():
    for theme in THEMES:
        for f in (monthly, code_scale, commit_types, review_share, merge_review, wiki_areas):
            f(theme)
    print("\n".join(sorted(p.name for p in OUT.glob("*.svg"))))


if __name__ == "__main__":
    main()
