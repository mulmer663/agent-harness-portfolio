"""review_gate.py 테스트 — 합성한 세션 기록으로 판정을 확인한다.

실행: python3 -m unittest examples/hooks/test_review_gate.py
"""
import io
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
import review_gate  # noqa: E402


def tool_use(name, **inp):
    return {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": name, "input": inp}]}}


REVIEW = tool_use("Agent", subagent_type="reviewer", prompt="diff 리뷰")
COMMIT = tool_use("Bash", command="git commit -m 'fix' -- a.py")
OTHER = tool_use("Bash", command="ls")


class ReviewGateTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.log = os.path.join(self.tmp.name, "gate.log")
        patcher = mock.patch.object(review_gate, "LOG_PATH", self.log)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.tmp.cleanup)

    def transcript(self, *records):
        path = os.path.join(self.tmp.name, "session.jsonl")
        with open(path, "w", encoding="utf-8") as f:
            f.write('{"type":"user","message":{"content":"시작"}}\n')
            f.write("깨진 줄\n")
            for r in records:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        return path

    def run_gate(self, command, records=(), branch="main", tool="Bash"):
        payload = {"tool_name": tool, "tool_input": {"command": command},
                   "transcript_path": self.transcript(*records), "cwd": self.tmp.name}
        with mock.patch("sys.stderr", new_callable=io.StringIO) as err:
            code = review_gate.decide(payload, branch_of=lambda cwd: branch)
        return code, err.getvalue()

    def log_text(self):
        if not os.path.exists(self.log):
            return ""
        with open(self.log, encoding="utf-8") as f:
            return f.read()

    def test_merge_without_review_is_blocked(self):
        code, err = self.run_gate("git merge feature/x", [OTHER])
        self.assertEqual(code, 2)
        self.assertIn("reviewer", err)

    def test_merge_after_review_passes(self):
        code, _ = self.run_gate("git merge feature/x", [COMMIT, REVIEW, OTHER])
        self.assertEqual(code, 0)

    def test_commit_after_review_is_blocked(self):
        code, err = self.run_gate("git merge feature/x", [REVIEW, COMMIT])
        self.assertEqual(code, 2)
        self.assertIn("1번", err)

    def test_second_review_resets_the_count(self):
        code, _ = self.run_gate("git merge feature/x", [REVIEW, COMMIT, REVIEW])
        self.assertEqual(code, 0)

    def test_feature_branch_is_not_gated(self):
        code, _ = self.run_gate("git merge main", [OTHER], branch="feature/x")
        self.assertEqual(code, 0)

    def test_non_merge_and_non_bash_pass(self):
        self.assertEqual(self.run_gate("git status")[0], 0)
        self.assertEqual(self.run_gate("git merge x", tool="Edit")[0], 0)

    def test_merge_inside_compound_command_is_seen(self):
        code, _ = self.run_gate("cd repo && git -C . merge feature/x", [OTHER])
        self.assertEqual(code, 2)

    def test_merge_lookalikes_are_not_merges(self):
        for cmd in ("git merge-base main HEAD", "git merge-tree a b", "git merge --abort", "git merge --continue"):
            self.assertEqual(self.run_gate(cmd, [OTHER])[0], 0, cmd)

    def test_separators_and_prefixes_are_parsed(self):
        for cmd in ("ls\ngit merge f", "  git merge f", "(cd repo && git merge f)", "env A=1 git merge f",
                    "git -c core.pager=cat merge f", "git --no-pager merge f", "echo a | git merge f"):
            self.assertEqual(self.run_gate(cmd, [OTHER])[0], 2, cmd)

    def test_dash_c_path_is_used_for_branch(self):
        seen = []
        payload = {"tool_name": "Bash", "tool_input": {"command": "git -C ../other merge f"},
                   "transcript_path": self.transcript(OTHER), "cwd": self.tmp.name}
        review_gate.decide(payload, branch_of=lambda cwd: seen.append(cwd) or "feature/x")
        self.assertEqual(seen, [os.path.join(self.tmp.name, "../other")])

    def test_switch_before_merge_sets_target_branch(self):
        code, _ = self.run_gate("git switch main && git merge f", [OTHER], branch="feature/x")
        self.assertEqual(code, 2)
        code, _ = self.run_gate("git checkout feature/y && git merge main", [OTHER], branch="main")
        self.assertEqual(code, 0)

    def test_quoted_merge_word_is_not_a_merge(self):
        self.assertEqual(self.run_gate('git commit -m "merge 준비"', [OTHER])[0], 0)
        self.assertEqual(self.run_gate('echo "git merge f"', [OTHER])[0], 0)

    def test_wrapped_merge_passes_and_is_logged(self):
        self.assertEqual(self.run_gate('bash -c "git merge f"', [OTHER])[0], 0)
        self.assertIn("판정 못 함", self.log_text())

    def test_unclosed_quote_fails_open(self):
        self.assertEqual(self.run_gate('git merge "f', [OTHER])[0], 0)
        self.assertIn("해석하지 못해", self.log_text())

    def test_commit_with_global_options_counts(self):
        commit = tool_use("Bash", command="git -C repo -c user.name=x commit -m 'fix'")
        code, _ = self.run_gate("git merge f", [REVIEW, commit])
        self.assertEqual(code, 2)

    def test_bypass_passes_and_is_logged(self):
        code, _ = self.run_gate("SKIP_REVIEW_GATE=1 git merge feature/x", [OTHER])
        self.assertEqual(code, 0)
        self.assertIn("우회", self.log_text())

    def test_unknown_branch_fails_open(self):
        code, _ = self.run_gate("git merge feature/x", [OTHER], branch=None)
        self.assertEqual(code, 0)
        self.assertIn("브랜치", self.log_text())

    def test_missing_transcript_fails_open(self):
        payload = {"tool_name": "Bash", "tool_input": {"command": "git merge x"},
                   "transcript_path": os.path.join(self.tmp.name, "없음.jsonl")}
        self.assertEqual(review_gate.decide(payload, branch_of=lambda cwd: "main"), 0)
        self.assertIn("세션 기록", self.log_text())

    def test_broken_stdin_fails_open(self):
        with mock.patch("sys.stdin", io.StringIO("{not json")):
            self.assertEqual(review_gate.main(), 0)
        self.assertIn("입력", self.log_text())

    def test_internal_error_fails_open(self):
        with mock.patch("sys.stdin", io.StringIO(json.dumps({"tool_name": "Bash"}))), \
             mock.patch.object(review_gate, "decide", side_effect=RuntimeError("boom")):
            self.assertEqual(review_gate.main(), 0)
        self.assertIn("내부 오류", self.log_text())


if __name__ == "__main__":
    unittest.main()
