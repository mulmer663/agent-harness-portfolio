# 예시 정의 파일

실제로 쓰는 하네스 정의를 줄이고 일반화해 새로 쓴 판입니다. 원본을 그대로 옮기지 않았고, 저장소·경로·제품 이름은 뺐습니다.
그대로 복사해 시작점으로 쓸 수 있게 만들었습니다. 왜 이렇게 만들었는지는 [02 하네스](../docs/02-harness.md)에, 시작 순서는 [04 따라 만들기](../docs/04-getting-started.md)에 있습니다.

| 파일 | 무엇 | 넣는 자리 |
|---|---|---|
| [agents/reviewer.md](agents/reviewer.md) | 편집 도구 없이 diff를 비판만 하는 리뷰어 서브에이전트 | `~/.claude/agents/` |
| [commands/feature.md](commands/feature.md) | planner → 구현 → tester → reviewer 순서를 고정한 `/feature` 커맨드 | `~/.claude/commands/` |
| [hooks/review_gate.py](hooks/review_gate.py) | 통합 브랜치로 병합하기 직전에 리뷰 여부를 보는 PreToolUse 훅 뼈대 | `~/.claude/hooks/` |
| [hooks/test_review_gate.py](hooks/test_review_gate.py) | 위 훅의 테스트 20개. 합성한 세션 기록과 명령 문자열로 판정, 명령 해석, fail-open을 확인합니다 | 훅 옆 |
| [hooks/settings.example.json](hooks/settings.example.json) | 훅을 등록하는 `settings.json` 조각 | `~/.claude/settings.json` 에 합침 |
| [knowledge/캐시-복원-통과는-테스트를-돌린-것이-아니다.md](knowledge/캐시-복원-통과는-테스트를-돌린-것이-아니다.md) | 규칙 노트(habit) 한 장. 머리말 필드와 재현 이력의 모양 | 위키의 규칙 노트 폴더 |

```bash
python3 -m unittest examples/hooks/test_review_gate.py   # 훅 테스트
```

훅 뼈대가 하지 않는 것도 적어 둡니다. 실제로 쓰는 판은 리뷰 뒤 커밋이 문서·주석만 바꿨으면 통과시키고, 여러 게이트가 로그 하나를 같이 쓰며, 야간 감사가 그 로그를 사유별로 셉니다.
