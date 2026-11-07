#!/usr/bin/env python3
"""git 이력만으로 포트폴리오 지표를 집계해 data/*.csv 로 쓴다. 표준 라이브러리만 쓴다.

입력은 저장소 설정 파일 한 장(기본 scripts/repos.local.txt, .gitignore 대상)이다. 한 줄에 하나씩
    라벨|저장소 경로|ref
ref 는 고정 SHA 를 권한다 — 통합 브랜치는 계속 움직여서 같은 명령이 다른 수를 낸다.
라벨 WIKI 는 지식 저장소(노트·하네스 정의)로 다루고, 나머지는 제품 저장소로 다룬다.

출력에는 경로·브랜치·커밋 메시지 원문·파일 이름을 하나도 남기지 않는다 — 라벨과 수만 남긴다.

집계 정의는 data/README.md 와 같다. 바꾸면 거기도 고친다.
"""
import collections
import csv
import datetime as dt
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA = ROOT / "data"

# 커밋 유형 — Conventional Commits 접두. 복합 접두(test+fix, test/docs(x), fix(ci),test, docs·test)는 첫 토큰을 대표로 쓴다.
TYPE_RE = re.compile(r"^([a-zA-Z]+)(?:\([^)]*\))?(?:\s*[+/,·]\s*[a-zA-Z]+(?:\([^)]*\))?)*!?:")
KNOWN_TYPES = ["feat", "fix", "test", "docs", "refactor", "chore", "perf", "build", "ci", "style", "revert"]
# 리뷰·테스트 역할이 낸 지적을 반영한 커밋 — 휴리스틱(메시지 키워드). data/README.md 에 같은 식을 적는다.
REVIEW_RE = re.compile(r"리뷰|reviewer|review", re.I)
TESTER_RE = re.compile(r"\btester\b", re.I)
AI_TRAILER_RE = re.compile(r"^co-authored-by:\s*claude", re.I | re.M)
# 지식 루프의 장치가 생긴 날(지식 저장소 이력에서 확인) — 구간을 가르는 경계로만 쓴다(인과를 뜻하지 않는다).
#   2026-09-29 세션 감사(결정적 검출) 도입 · 2026-10-21 병합 전 리뷰 게이트 도입
PERIODS = [("p1_to_0928", None, dt.date(2026, 9, 29)),
           ("p2_0929_to_1020", dt.date(2026, 9, 29), dt.date(2026, 10, 21)),
           ("p3_from_1021", dt.date(2026, 10, 21), None)]

CODE_GROUPS = {
    "JVM": (".java", ".kt", ".groovy", ".gradle", ".kts"),
    "Web": (".ts", ".tsx", ".js", ".jsx", ".vue", ".css"),
    "SQL": (".sql",),
    "Script": (".py", ".sh"),
    "Docs": (".md",),
}
EXCLUDE_RE = re.compile(
    r"(^|/)(node_modules|build|dist|\.gradle|gradle/wrapper|vendor)/|"
    r"(pnpm-lock\.yaml|package-lock\.json|yarn\.lock|\.min\.js)$|"
    r"(^|/)docs/deliverables/"
)
TEST_RE = re.compile(
    r"(^|/)src/(test|testFixtures|integrationTest|e2e)[^/]*/|(^|/)(__tests__|tests?|e2e)/|"
    r"\.(test|spec)\.[jt]sx?$|(^|/)test_[^/]+\.py$|_test\.py$"
)


def git(repo, *args):
    return subprocess.run(["git", "-C", repo, *args], check=True, capture_output=True, text=True,
                          errors="replace").stdout


def read_config(path):
    rows = []
    for line in pathlib.Path(path).read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        label, repo, ref = line.split("|")
        rows.append((label, repo, ref))
    return rows


def commits(repo, ref, merges):
    """(작성일, 제목, 본문) 목록. merges=False 면 병합 제외, 'first-parent' 면 통합 브랜치에 들어온 병합만."""
    args = ["log", ref, "--format=%ad%x1f%s%x1f%b%x1e", "--date=short"]
    if merges is False:
        args.append("--no-merges")
    elif merges == "first-parent":
        args += ["--first-parent", "--merges"]
    out = git(repo, *args)
    rows = []
    for rec in out.split("\x1e"):
        rec = rec.strip("\n")
        if not rec:
            continue
        day, subj, body = (rec.split("\x1f") + ["", ""])[:3]
        rows.append((dt.date.fromisoformat(day), subj, body))
    return rows


def classify(subj):
    m = TYPE_RE.match(subj)
    if not m:
        return "other"
    t = m.group(1).lower()
    return t if t in KNOWN_TYPES else "other"


def tree_lines(repo, ref):
    """스냅샷 트리의 (그룹, main|test) → [파일 수, 빈 줄 뺀 줄 수]."""
    names = git(repo, "ls-tree", "-r", "-z", "--name-only", ref).split("\0")
    picked = []
    for n in names:
        if not n or EXCLUDE_RE.search(n):
            continue
        for group, exts in CODE_GROUPS.items():
            if n.endswith(exts):
                picked.append((n, group))
                break
    stats = collections.defaultdict(lambda: [0, 0])
    proc = subprocess.Popen(["git", "-C", repo, "cat-file", "--batch"], stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE)
    for n, group in picked:
        proc.stdin.write(f"{ref}:{n}\n".encode())
        proc.stdin.flush()
        header = proc.stdout.readline().split()
        size = int(header[2])
        blob = proc.stdout.read(size)
        proc.stdout.read(1)
        if b"\0" in blob[:8000]:
            continue  # 바이너리
        kind = "test" if (group != "Docs" and TEST_RE.search(n)) else "main"
        lines = sum(1 for l in blob.decode("utf-8", "replace").splitlines() if l.strip())
        s = stats[(group, kind)]
        s[0] += 1
        s[1] += lines
    proc.stdin.close()
    proc.wait()
    return stats


def write(name, header, rows):
    DATA.mkdir(exist_ok=True)
    with open(DATA / name, "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(header)
        w.writerows(rows)
    print(f"  data/{name}: {len(rows)}행")


def month(d):
    return d.strftime("%Y-%m")


def main():
    cfg = sys.argv[1] if len(sys.argv) > 1 else ROOT / "scripts" / "repos.local.txt"
    repos = read_config(cfg)
    summary, monthly, types, review, lines, merges_rows, baseline = [], [], [], [], [], [], []
    all_months = set()
    for label, repo, ref in repos:
        if label == "WIKI":
            continue
        nm = commits(repo, ref, merges=False)
        fp = commits(repo, ref, merges="first-parent")
        days = sorted({c[0] for c in nm})
        ai = sum(1 for c in nm if AI_TRAILER_RE.search(c[2]))
        rev = sum(1 for c in nm if REVIEW_RE.search(c[1]))
        tst = sum(1 for c in nm if TESTER_RE.search(c[1]))
        summary.append([label, days[0], days[-1], (days[-1] - days[0]).days + 1, len(days), len(nm),
                        len(fp), ai, f"{ai / len(nm):.3f}", rev, tst])
        per_month = collections.Counter(month(c[0]) for c in nm)
        all_months |= set(per_month)
        for m, n in sorted(per_month.items()):
            monthly.append([m, label, n])
        tc = collections.Counter(classify(c[1]) for c in nm)
        for t in KNOWN_TYPES + ["other"]:
            types.append([label, t, tc.get(t, 0)])
        by_m = collections.defaultdict(lambda: [0, 0, 0, 0])
        for d, s, _ in nm:
            r = by_m[month(d)]
            r[0] += 1
            r[1] += classify(s) == "fix"
            r[2] += bool(REVIEW_RE.search(s))
            r[3] += bool(TESTER_RE.search(s))
        for m, (n, fx, rv, ts) in sorted(by_m.items()):
            review.append([m, label, n, fx, rv, ts])
        # 통합 병합(통합 브랜치 first-parent 병합) 메시지에 리뷰 단어가 든 수 — 감사·게이트 도입일로 가른 세 구간
        for name, lo, hi in PERIODS:
            sel = [c for c in fp if (lo is None or c[0] >= lo) and (hi is None or c[0] < hi)]
            rv = sum(1 for c in sel if REVIEW_RE.search(c[1] + "\n" + c[2]))
            merges_rows.append([label, name, len(sel), rv])
        # 첫(루트) 커밋 트리의 규모 — 첫 커밋에 기존 코드가 들어온 저장소는 그 코드가 스냅샷 규모에 들어 있다
        roots = git(repo, "rev-list", "--max-parents=0", ref).split()
        root = min(roots, key=lambda r: git(repo, "log", "-1", "--format=%at", r).strip())
        root_day = git(repo, "log", "-1", "--format=%ad", "--date=short", root).strip()
        rl = collections.defaultdict(int)
        for (group, kind), (files, n) in tree_lines(repo, root).items():
            if group != "Docs":
                rl[kind] += n
        baseline.append([label, root_day, rl["main"], rl["test"]])
        for (group, kind), (files, n) in sorted(tree_lines(repo, ref).items()):
            lines.append([label, group, kind, files, n])

    write("summary.csv", ["repo", "first_commit", "last_commit", "span_days", "active_days",
                          "commits_nonmerge", "integration_merges", "ai_trailer_commits", "ai_trailer_ratio",
                          "review_mention_commits", "tester_mention_commits"], summary)
    write("monthly_commits.csv", ["month", "repo", "commits_nonmerge"], monthly)
    write("commit_types.csv", ["repo", "type", "commits_nonmerge"], types)
    write("review_by_month.csv", ["month", "repo", "commits_nonmerge", "fix", "review_mention", "tester_mention"],
          review)
    write("integration_merges_review.csv", ["repo", "period", "integration_merges", "review_word_in_message"],
          merges_rows)
    write("baseline_lines.csv", ["repo", "root_commit", "code_lines_main", "code_lines_test"], baseline)
    write("code_lines.csv", ["repo", "group", "kind", "files", "nonblank_lines"], lines)

    # 헤드라인 — README 첫 화면의 수는 전부 여기서 나온다(손으로 더하지 않는다)
    code = collections.defaultdict(int)
    for repo_label, group, kind, files, n in lines:
        if group != "Docs":
            code[kind] += n
    nm_total = sum(r[5] for r in summary)
    head = [
        ["first_commit", min(r[1] for r in summary)],
        ["last_commit", max(r[2] for r in summary)],
        ["span_days", (max(r[2] for r in summary) - min(r[1] for r in summary)).days + 1],
        ["products", len(summary)],
        ["commits_nonmerge", nm_total],
        ["ai_trailer_ratio", f"{sum(r[7] for r in summary) / nm_total:.3f}"],
        ["review_mention_ratio", f"{sum(r[9] for r in summary) / nm_total:.3f}"],
        ["code_lines_main", code["main"]],
        ["code_lines_test", code["test"]],
        ["test_line_ratio", f"{code['test'] / (code['main'] + code['test']):.3f}"],
    ]
    write("headline.csv", ["metric", "value"], head)

    # 지식 저장소 — 커밋을 건드린 영역별로 센다(한 커밋이 여러 영역이면 각각 1).
    for label, repo, ref in repos:
        if label != "WIKI":
            continue
        out = git(repo, "log", ref, "--no-merges", "--format=\x1e%ad", "--date=short", "--name-only")
        area_of = [("knowledge", "30_knowledge/"), ("harness", "setup/claude/"), ("audit", "setup/audit/"),
                   ("notes", ("00_inbox/", "20_projects/")), ("daily", "10_daily/")]
        cnt = collections.Counter()
        first = last = None
        total = 0
        for rec in out.split("\x1e"):
            rec = rec.strip()
            if not rec:
                continue
            day, *files = rec.split("\n")
            d = dt.date.fromisoformat(day)
            first = d if first is None or d < first else first
            last = d if last is None or d > last else last
            total += 1
            hit = set()
            for f in files:
                for area, pre in area_of:
                    if f.startswith(pre):
                        hit.add(area)
            for a in hit:
                cnt[(month(d), a)] += 1
        write("wiki_commits_by_area.csv", ["month", "area", "commits"],
              [[m, a, n] for (m, a), n in sorted(cnt.items())])
        write("wiki_summary.csv", ["first_commit", "last_commit", "commits_nonmerge"], [[first, last, total]])
        wiki_tree(repo, ref)


def blobs(repo, ref, paths):
    proc = subprocess.Popen(["git", "-C", repo, "cat-file", "--batch"], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    for n in paths:
        proc.stdin.write(f"{ref}:{n}\n".encode())
        proc.stdin.flush()
        size = int(proc.stdout.readline().split()[2])
        data = proc.stdout.read(size)
        proc.stdout.read(1)
        yield n, data.decode("utf-8", "replace")
    proc.stdin.close()
    proc.wait()


def frontmatter(text):
    if not text.startswith("---"):
        return {}
    fm = text.split("---", 2)[1]
    out = {}
    for key in ("kind", "hits", "date", "mechanize", "source"):
        m = re.search(rf"^{key}:\s*(.*)$", fm, re.M)
        if m:
            out[key] = m.group(1).strip().strip('"')
    return out


def wiki_tree(repo, ref):
    """지식 저장소 스냅샷 트리의 노트 frontmatter 를 센다(이름·본문은 남기지 않는다)."""
    names = [n for n in git(repo, "ls-tree", "-r", "-z", "--name-only", ref).split("\0") if n.endswith(".md")]
    kinds = collections.defaultdict(lambda: [0, 0, 0])  # 노트 수, hits 합(하한), mechanize 가 실제 검사 경로인 수
    knowledge = [n for n in names if n.startswith("30_knowledge/")]
    for _, text in blobs(repo, ref, knowledge):
        fm = frontmatter(text)
        k = kinds[fm.get("kind", "-")]
        k[0] += 1
        h = re.match(r"\d+", fm.get("hits", ""))
        k[1] += int(h.group(0)) if h else 0
        mech = fm.get("mechanize", "")
        k[2] += bool(mech) and not mech.startswith(("불가", "보류", "부분"))
    write("wiki_knowledge_kinds.csv", ["kind", "notes", "hits_sum_lower_bound", "mechanized"],
          [[k, *v] for k, v in sorted(kinds.items())])
    notes = [n for n in names if n.startswith(("20_projects/", "00_inbox/"))]
    by_month = collections.Counter()
    for _, text in blobs(repo, ref, notes):
        d = frontmatter(text).get("date", "")[:7]
        by_month[d or "unknown"] += 1
    write("wiki_notes_by_month.csv", ["month_frontmatter_date", "work_notes"], sorted(by_month.items()))
    harness = {
        "agents": sum(1 for n in names if n.startswith("setup/claude/agents/")),
        "commands": sum(1 for n in names if n.startswith("setup/claude/commands/")),
        "daily_summaries": sum(1 for n in names if n.startswith("10_daily/")),
    }
    py = [n for n in git(repo, "ls-tree", "-r", "-z", "--name-only", ref).split("\0")
          if re.search(r"setup/(claude/hooks|audit)/test_[^/]+\.py$", n)]
    harness["harness_test_functions"] = sum(len(re.findall(r"^\s*def test_", t, re.M)) for _, t in blobs(repo, ref, py))
    write("wiki_harness.csv", ["item", "count"], sorted(harness.items()))


if __name__ == "__main__":
    main()
