#!/bin/bash
# 공개 전 금칙어 전수 검사.
#   금칙어 목록은 scripts/banned.local.txt(.gitignore 대상, 한 줄 한 ERE, 대소문자 무시)에 둔다 —
#   회사·제품명을 이 공개 스크립트에 적으면 그 자체가 유출이기 때문이다.
#   스크립트에는 일반 패턴(사설 IP·이메일)만 둔다.
# 검사 대상: ① 작업 트리(추적+미추적, .gitignore 제외) 내용 ② 파일 이름 ③ git 커밋 메타데이터·메시지
#           ④ 도달 가능한 모든 커밋의 트리 내용.
# 종료 코드: 0 = 0건, 1 = 걸린 것 있음, 2 = 목록 파일 없음.
set -u
cd "$(git rev-parse --show-toplevel)" || exit 2
LIST=scripts/banned.local.txt
[ -f "$LIST" ] || { echo "금칙어 목록이 없다: $LIST"; exit 2; }

PAT=$(mktemp); trap 'rm -f "$PAT"' EXIT
grep -v -e '^#' -e '^[[:space:]]*$' "$LIST" > "$PAT"
# 일반 패턴 — 사설 IPv4(10/8, 172.16/12, 192.168/16), 이메일 주소(공개용 noreply 는 허용)
cat >> "$PAT" <<'P'
(^|[^0-9.])10\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}
(^|[^0-9.])172\.(1[6-9]|2[0-9]|3[01])\.[0-9]{1,3}\.[0-9]{1,3}
(^|[^0-9.])192\.168\.[0-9]{1,3}\.[0-9]{1,3}
[A-Za-z0-9._%+-]+@(?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,}
P
# 마지막 줄은 PCRE 문법이라 ERE 용으로 바꾼다
sed -i '' 's/(?:/(/' "$PAT"

hits=0
echo "① 내용 (git grep --untracked -a -i -E)"
if out=$(git grep --untracked -a -n -i -I -E -f "$PAT" -- . ':!*.png' 2>/dev/null | grep -v -i -E 'users\.noreply\.github\.com|noreply@anthropic\.com'); [ -n "$out" ]; then
  echo "$out"; hits=$((hits + $(printf '%s\n' "$out" | wc -l)))
fi
echo "② 파일 이름"
if out=$( { git ls-files; git ls-files -o --exclude-standard; } | grep -i -E -f "$PAT"); [ -n "$out" ]; then
  echo "$out"; hits=$((hits + $(printf '%s\n' "$out" | wc -l)))
fi
echo "③ 커밋 메타데이터·메시지"
if git rev-parse -q --verify HEAD >/dev/null; then
  if out=$(git log --all --format='%h %an <%ae> %cn <%ce>%n%B' | grep -i -E -f "$PAT" | grep -v -i -E 'users\.noreply\.github\.com|noreply@anthropic\.com'); [ -n "$out" ]; then
    echo "$out"; hits=$((hits + $(printf '%s\n' "$out" | wc -l)))
  fi
fi
echo "④ 도달 가능한 모든 커밋의 트리 (지운 문구도 push 하면 이력에 남는다)"
if git rev-parse -q --verify HEAD >/dev/null; then
  if out=$(git grep -a -n -i -I -E -f "$PAT" $(git rev-list --all) -- . ':!*.png' 2>/dev/null | grep -v -i -E 'users\.noreply\.github\.com|noreply@anthropic\.com'); [ -n "$out" ]; then
    echo "$out"; hits=$((hits + $(printf '%s\n' "$out" | wc -l)))
  fi
fi
echo "PNG 등 바이너리는 내용 검사에서 빠진다 — 차트는 SVG(텍스트)로만 둔다: $(git ls-files -co --exclude-standard | grep -c -i -E '\.(png|jpe?g|gif|pdf)$') 개"
echo "금칙 패턴 $(wc -l < "$PAT" | tr -d ' ')개, 걸린 줄 ${hits}건"
[ "$hits" -eq 0 ]
