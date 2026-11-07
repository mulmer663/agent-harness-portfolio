# data — 수치의 출처와 재현 명령

이 폴더의 CSV는 전부 [`scripts/collect.py`](../scripts/collect.py)가 만듭니다. 손으로 고친 값은 없습니다.
원본 저장소는 비공개라서 경로와 ref는 저장소 밖 로컬 설정 파일(`scripts/repos.local.txt`, `.gitignore` 대상)에 둡니다.

```text
# scripts/repos.local.txt — 한 줄에 하나: 라벨|저장소 경로|ref
IAM|<IAM 플랫폼 저장소 경로>|<통합 브랜치의 고정 SHA>
LEAK|<유출 계정 탐지 저장소 경로>|<고정 SHA>
MFA|<MFA 제품 저장소 경로>|<고정 SHA>
WIKI|<지식 저장소 경로>|<고정 SHA>
```

```bash
python3 scripts/collect.py      # data/*.csv
python3 scripts/charts.py       # assets/charts/*-{light,dark}.svg
```

## 스냅샷

| 라벨 | 대상 | ref 시점 |
|---|---|---|
| IAM | IAM 플랫폼, 통합 브랜치 | 2026-11-06 |
| LEAK | 유출 계정 탐지 모듈, 통합 브랜치 | 2026-11-06 |
| MFA | MFA 제품, 통합 브랜치 | 2026-11-06 |
| WIKI | 지식 저장소(노트·하네스 정의) | 2026-11-07 |

## 파일과 정의

| 파일 | 내용 | 정의 (같은 결과를 내는 git 명령) |
|---|---|---|
| `headline.csv` | 제품 저장소 세 곳의 합계 수(기간·커밋·트레일러 비율·리뷰 언급 비율·코드 줄 수) | 아래 파일들의 합과 비율. 규칙·노트 수는 `wiki_*.csv` 에 있습니다 |
| `summary.csv` | 저장소별 기간·커밋·트레일러·리뷰 언급 | 아래 행들 |
| ↳ first/last_commit, span_days | 첫·끝 커밋 작성일과 그 사이 일수(양끝 포함) | `git log <ref> --no-merges --format=%ad --date=short` 의 최소·최대 |
| ↳ active_days | 커밋이 있는 날의 수 | 위 날짜의 고유 개수 |
| ↳ commits_nonmerge | 병합 제외 커밋 | `git rev-list --count --no-merges <ref>` |
| ↳ integration_merges | 통합 브랜치에 들어온 병합 | `git rev-list --count --first-parent --merges <ref>` |
| ↳ ai_trailer_commits | 본문에 `Co-Authored-By: Claude` 트레일러가 있는 비병합 커밋 | 정규식 `^co-authored-by:\s*claude` (대소문자 무시, 줄 단위) |
| ↳ review_mention_commits | 제목에 리뷰 키워드가 있는 비병합 커밋 | 정규식 `리뷰` 또는 `reviewer` 또는 `review` (대소문자 무시). 휴리스틱 |
| ↳ tester_mention_commits | 제목에 `tester` 가 있는 비병합 커밋 | 단어 경계 `\btester\b` |
| `monthly_commits.csv` | 월별 비병합 커밋 | 작성일(`%ad`) 기준 월 |
| `commit_types.csv` | Conventional Commits 유형 | 제목 맨 앞 `유형(범위)!:` 의 첫 유형. 복합 접두(`test+fix`, `fix(ci),test`, `docs·test`)는 첫 토큰. 알려진 11개 유형 밖이거나 접두가 없으면 `other` |
| `review_by_month.csv` | 월별 커밋·fix·리뷰 언급·tester 언급 | 위 정의의 월별 집계 |
| `integration_merges_review.csv` | 통합 병합 중 제목·본문에 리뷰 키워드가 있는 수. 세 구간: ~09-28 / 09-29~10-20 / 10-21~ | 09-29는 세션 감사(결정적 검출)를, 10-21은 병합 전 리뷰 게이트를 도입한 날입니다(지식 저장소 이력으로 확인). 게이트는 새로 뜬 세션부터 걸리므로 날짜 경계는 근사입니다. 관측치이며 인과가 아닙니다 |
| `baseline_lines.csv` | 각 저장소 첫(루트) 커밋 트리의 제품·테스트 코드 줄 수 | `git rev-list --max-parents=0 <ref>` 중 가장 이른 커밋에 `code_lines` 와 같은 규칙. IAM 플랫폼은 첫 커밋에 초기 코드 9.0만 줄이 들어 있습니다 |
| `code_lines.csv` | 스냅샷 트리의 그룹별 파일 수·빈 줄 뺀 줄 수 | `git ls-tree -r <ref>` + `git cat-file --batch`. 그룹은 JVM(.java .kt .groovy .gradle .kts) · Web(.ts .tsx .js .jsx .vue .css) · SQL · Script(.py .sh) · Docs(.md). 제외: `node_modules/ build/ dist/ .gradle/ gradle/wrapper/ vendor/`, lockfile, `*.min.js`, 고객 산출물 폴더, 바이너리(앞 8KB에 NUL) |
| ↳ kind=test | 테스트 코드 (문서 그룹 제외) | 경로가 `src/test*/` · `src/testFixtures*/` · `src/integrationTest*/` · `src/e2e*/` · `__tests__/` · `test/` · `tests/` · `e2e/` 아래이거나, 이름이 `*.test.js`·`.jsx`·`.ts`·`.tsx`, `*.spec.js`·`.jsx`·`.ts`·`.tsx`, `test_*.py`, `*_test.py` |
| `wiki_summary.csv` | 지식 저장소의 비병합 커밋 수와 기간 | 지식 저장소의 git 이력은 2026-09-04에 시작합니다. 그 전 노트는 첫 커밋에 함께 들어왔습니다 |
| `wiki_commits_by_area.csv` | 영역별 월별 커밋 | 한 커밋이 건드린 경로 접두로 영역을 정합니다. 여러 영역을 건드리면 각각 1로 셉니다. notes=`00_inbox/`·`20_projects/`, knowledge=`30_knowledge/`, harness=`setup/claude/`, audit=`setup/audit/`, daily=`10_daily/` |
| `wiki_knowledge_kinds.csv` | 승격 노트의 종류별 수, `hits` 합, 기계화된 수 | 스냅샷 트리 `30_knowledge/*.md` 의 frontmatter. `hits` 는 맨 앞 정수(없으면 0), 기계화 = `mechanize` 가 비어 있지 않고 "불가/보류/부분"으로 시작하지 않음 |
| `wiki_notes_by_month.csv` | 작업 노트 수 | `00_inbox/`·`20_projects/` 의 `.md`. 월은 frontmatter `date` 기준입니다(git 날짜가 아님) |
| `wiki_harness.csv` | 에이전트·커맨드 정의 수, 데일리 요약 수, 하네스 테스트 함수 수 | `setup/claude/agents/`, `setup/claude/commands/`, `10_daily/` 파일 수 · `setup/claude/hooks/test_*.py`·`setup/audit/test_*.py` 의 `def test_` 수 |

## 집계 기준

- 기간은 세 제품 저장소의 첫 커밋(2026-06-23)부터 마지막 커밋(2026-11-06)까지, 137일입니다. IAM 플랫폼은 첫 커밋에 초기 코드 9.0만 줄이 함께 들어왔고, 이 코드는 스냅샷 규모에 포함돼 있습니다(`baseline_lines.csv`).
- 병합 커밋은 뺐습니다. 넣으면 IAM 플랫폼 커밋이 4,270에서 6,763이 됩니다.
- 추가·삭제 줄 수 합(numstat)은 쓰지 않았습니다. squash, 생성물, 이동 때문에 실제 규모보다 커집니다. 코드 규모는 스냅샷 트리의 현재 줄 수만 셉니다.
- 트레일러 비율은 작성 비중이 아닙니다. 에이전트가 커밋을 만들었다는 표지일 뿐입니다.
- 2026-06과 2026-11은 부분 월입니다.

## 손으로 대조하는 방법

라벨이 붙은 저장소 하나에서 몇 가지 수를 직접 확인할 수 있습니다.

```bash
REF=<고정 SHA>
git -C <저장소> rev-list --count --no-merges $REF                         # summary.commits_nonmerge
git -C <저장소> rev-list --count --first-parent --merges $REF             # summary.integration_merges
git -C <저장소> log $REF --no-merges --format=%ad --date=short | sort | sed -n '1p;$p'   # 첫·끝 커밋
git -C <저장소> log $REF --no-merges -i -E --grep='^co-authored-by:[[:space:]]*claude' --format=%h | wc -l   # ai_trailer_commits
```
