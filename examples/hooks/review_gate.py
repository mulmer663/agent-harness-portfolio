#!/usr/bin/env python3
"""병합 전 리뷰 게이트 — Claude Code PreToolUse 훅 예시.

통합 브랜치(main·dev 등) 위에서 `git merge` 를 실행하려 할 때, 이 세션의 기록을 읽어
reviewer 서브에이전트를 부른 적이 있는지, 부른 뒤에 커밋을 더 했는지 확인한다.

실제로 쓰는 게이트를 줄여 새로 쓴 뼈대다. 실제 판에는 문서·주석만 바꾼 커밋은 봐주는 판정,
여러 게이트의 공용 로그와 야간 집계가 더 있다.

동작 규칙
- 막을 때: 종료 코드 2 + 이유를 stderr 에 쓴다. Claude Code 는 그 명령을 실행하지 않고 stderr 를 모델에게 돌려준다.
- 그 밖에는 종료 코드 0(통과). 판정할 수 없는 경우(입력이 깨짐, 세션 기록 없음, 내부 오류, 따옴표가 안 닫힌 명령)도
  통과시키고 사유를 로그 파일에 남긴다(fail-open). 이 훅은 모든 세션에 걸리므로, 훅이 고장 나도 작업이 멈추지 않게 한다.
- 우회: 명령 앞에 `SKIP_REVIEW_GATE=1` 을 붙인다. 쓰면 로그에 남는다.

명령 해석
- shlex 로 토큰을 나누고 `;` `&&` `||` `|` `&` 괄호 줄바꿈에서 명령을 끊는다.
- 앞에 붙은 변수 대입과 `env`, git 전역 옵션(`-C <경로>`, `-c k=v`, `--no-pager` 등)을 건너뛴다.
- `merge-base`·`merge-tree` 와 `merge --abort|--continue|--quit|--skip` 은 병합으로 보지 않는다.
- 브랜치는 `-C <경로>` 가 있으면 그 경로에서 읽는다. 같은 명령 안에서 앞서 `git checkout|switch X` 를 했으면 X 로 본다.

못 보는 것(그냥 통과)
- rebase·cherry-pick·push·`gh pr merge` 로 반영하는 경로.
- `bash -c`·`eval`·명령 치환·셸 변수·alias 로 감싼 merge. "merge 비슷한데 판정 못 함"으로 로그만 남긴다.
- 다른 세션이 한 리뷰, reviewer 가 도중에 실패했는지 여부(호출만 있으면 리뷰로 친다).

잘못 막는 것(보수적으로 막는 쪽)
- 실패한 커밋, 다른 저장소에서 한 커밋도 "리뷰 뒤 커밋"으로 센다.
- 리뷰할 변경이 없는 병합(받아 온 통합 브랜치를 그대로 합치는 경우)도 리뷰를 요구한다. 이때는 우회를 쓴다.
"""
import json
import os
import shlex
import subprocess
import sys
import time

INTEGRATION_BRANCHES = {"main", "master", "dev", "develop"}
BYPASS = "SKIP_REVIEW_GATE=1"
LOG_PATH = os.environ.get("REVIEW_GATE_LOG", os.path.expanduser("~/.claude/hook-state/review_gate.log"))
SEPARATORS = {";", "&&", "||", "|", "&", "(", ")", "\n", ";;", "|&"}
NOT_A_MERGE = {"--abort", "--continue", "--quit", "--skip"}
GIT_OPTS_WITH_VALUE = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path"}


class Unparsable(ValueError):
    pass


def tokens(command):
    lex = shlex.shlex(command, posix=True, punctuation_chars="();&|\n")
    lex.whitespace = " \t\r"
    lex.whitespace_split = True
    try:
        return list(lex)
    except ValueError as e:  # 따옴표가 안 닫힘 등
        raise Unparsable(str(e)) from e


def segments(command):
    """명령을 구분자에서 끊어 토큰 목록들로 돌려준다."""
    seg = []
    for tok in tokens(command):
        if tok in SEPARATORS or set(tok) <= set("();&|\n"):
            if seg:
                yield seg
            seg = []
        else:
            seg.append(tok)
    if seg:
        yield seg


def git_call(seg):
    """한 명령이 git 호출이면 (하위 명령, 인자, -C 경로, 앞에 붙은 변수 대입) 을, 아니면 None."""
    i, assigns = 0, []
    while i < len(seg) and (seg[i] == "env" or ("=" in seg[i] and seg[i].split("=", 1)[0].isidentifier())):
        if seg[i] != "env":
            assigns.append(seg[i])
        i += 1
    if i >= len(seg) or seg[i] != "git":
        return None
    i += 1
    path = None
    while i < len(seg) and seg[i].startswith("-"):
        opt = seg[i]
        if opt in GIT_OPTS_WITH_VALUE:
            if opt == "-C" and i + 1 < len(seg):
                path = seg[i + 1] if path is None else os.path.join(path, seg[i + 1])
            i += 2
        else:
            i += 1  # --no-pager, --git-dir=… 처럼 값이 붙은 옵션
    if i >= len(seg):
        return None
    return seg[i], seg[i + 1:], path, assigns


def switched_to(sub, args):
    """`git checkout|switch [-b|-c] X` 의 X. 파일 체크아웃(`--`)이나 옵션만 있으면 None."""
    if sub not in ("checkout", "switch") or "--" in args:
        return None
    names = [a for a in args if not a.startswith("-")]
    return names[0] if names else None


def merges(command):
    """명령 안의 병합마다 (-C 경로, 같은 명령에서 앞서 옮겨 간 브랜치, 우회 여부) 를 돌려준다."""
    found, switched = [], None
    for seg in segments(command):
        call = git_call(seg)
        if call is None:
            continue
        sub, args, path, assigns = call
        target = switched_to(sub, args)
        if target:
            switched = target
        elif sub == "merge" and not NOT_A_MERGE & set(args):
            found.append((path, switched, BYPASS in assigns))
    return found


def is_commit(command):
    try:
        return any((c := git_call(seg)) and c[0] == "commit" for seg in segments(command))
    except Unparsable:
        return False


def note(msg):
    """통과 사유를 남긴다. 종료 코드 0 의 stderr 는 아무에게도 보이지 않으므로 파일에 쓴다."""
    try:
        os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S')} {msg}\n")
    except OSError:
        pass


def current_branch(cwd):
    out = subprocess.run(["git", "-C", cwd or ".", "rev-parse", "--abbrev-ref", "HEAD"],
                         capture_output=True, text=True, timeout=5)
    return out.stdout.strip() if out.returncode == 0 else None


def tool_calls(transcript_path):
    """세션 기록(JSONL)에서 에이전트가 부른 도구를 순서대로 돌려준다: (도구 이름, 입력)."""
    with open(transcript_path, encoding="utf-8") as f:
        for line in f:
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if rec.get("type") != "assistant":
                continue
            content = (rec.get("message") or {}).get("content")
            if not isinstance(content, list):
                continue
            for block in content:
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    yield block.get("name"), block.get("input") or {}


def review_state(calls):
    """(마지막 reviewer 호출이 있었나, 그 뒤 git commit 호출 수)."""
    reviewed, commits_after = False, 0
    for name, inp in calls:
        if name in ("Agent", "Task") and inp.get("subagent_type") == "reviewer":
            reviewed, commits_after = True, 0
        elif name == "Bash" and is_commit(inp.get("command") or ""):
            commits_after += 1
    return reviewed, commits_after


def block(msg):
    print(msg, file=sys.stderr)
    return 2


def decide(payload, branch_of=current_branch):
    if payload.get("tool_name") != "Bash":
        return 0
    command = (payload.get("tool_input") or {}).get("command") or ""
    if "merge" not in command:
        return 0
    try:
        found = merges(command)
    except Unparsable as e:
        note(f"명령을 해석하지 못해 통과: {e} {command[:120]!r}")
        return 0
    if not found:
        if "git" in command:
            note(f"merge 비슷한데 판정 못 함: {command[:120]!r}")
        return 0
    cwd = payload.get("cwd") or "."
    for path, switched, bypass in found:
        if bypass:
            note(f"우회 사용: {command[:120]!r}")
            continue
        branch = switched or branch_of(os.path.join(cwd, path) if path else cwd)
        if branch is None:
            note("현재 브랜치를 읽지 못해 통과")
            continue
        if branch not in INTEGRATION_BRANCHES:
            continue
        code = check_review(payload, branch)
        if code:
            return code
    return 0


def check_review(payload, branch):
    path = payload.get("transcript_path") or ""
    if not os.path.isfile(path):
        note(f"세션 기록이 없어 통과: {path!r}")
        return 0
    reviewed, commits_after = review_state(tool_calls(path))
    if not reviewed:
        return block(f"{branch} 로 병합하기 전에 reviewer 서브에이전트로 변경분을 리뷰하세요. "
                     f"리뷰할 것이 정말 없으면 명령 앞에 {BYPASS} 를 붙이고 사용자에게 알리세요.")
    if commits_after:
        return block(f"마지막 리뷰 뒤에 커밋이 {commits_after}번 더 있었습니다. "
                     "그 커밋까지 다시 리뷰받은 뒤 병합하세요.")
    return 0


def main():
    try:
        payload = json.load(sys.stdin)
    except ValueError as e:
        note(f"입력을 읽지 못해 통과: {e!r}")
        return 0
    try:
        return decide(payload)
    except Exception as e:  # 게이트 고장이 작업을 세우지 않게 한다
        note(f"내부 오류로 통과: {e!r}")
        return 0


if __name__ == "__main__":
    sys.exit(main())
