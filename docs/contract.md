# CLI와 스킬 사이의 규약

스킬 본문이 호출하는 인터페이스를 정한다. 스킬은 이 문서에 적힌 것에만 의존하고, 여기 없는 출력 형태에는 기대지 않는다.

플래그 목록의 원본은 `--help` 다. 이 문서는 스킬이 파싱하는 JSON 형태와 종료 코드, 파일 배치처럼 `--help` 에 안 나오는 것을 정한다. 설정 항목의 제약과 그 근거는 `weekly_report/schemas.py` 주석에 있다.

## 파일 배치

```
~/.weekly-report/            # WEEKLY_REPORT_HOME 으로 변경 가능
├── config.yaml              # 온보딩이 만들고, 이후 손으로 또는 repos 스킬로 고침
├── template.md              # 리포트 형식. 온보딩이 만들고 손으로 고침
├── report.md                # 이번 주 작업 파일. 매주 스킬이 새로 만들고 손으로 고침
├── prompt.md                # 실행 중간 산물. 매번 덮어씀. 손댈 일 없음
└── history/
    └── report-<YYYYmmdd-HHMMSS>.md   # 스킬이 넣고 지움. 손댈 일 없음
```

이 도구가 계속 들고 가는 상태는 `history/` 뿐이다. 마지막 리포트 날짜가 다음 수집 구간의 시작점을 정하는데, 그 기록이 다른 어디에도 없다. Git이 추적하지 않으니 백업도 되지 않는다.

파일 이름 규칙은 `history/` 안에서만 쓴다. `report-(\d{8}-\d{6})\.md` 에 맞지 않는 파일은 무시한다.

## 설정

```yaml
author: minjae.kim            # 전역 기본 author. repository[].authors 가 없을 때 쓴다
lang: korean                  # 리포트를 쓸 언어. 프롬프트에 그대로 들어감

repository:
  - path: /Users/mj/workspace/athena
    name: Athena              # 선택. 없으면 path 의 마지막 조각
    authors: [minjae.kim]     # 선택. 없으면 전역 author 하나만

max_diff_lines: 50            # 커밋당 보여줄 diff 줄 수. 0이면 diff를 넣지 않는다
report_history_limit: 5       # history/ 에 남기고 프롬프트에 넣을 리포트 개수. 최소 1
large_prompt_tokens: 150000   # 이 값을 넘으면 경고만 한다. 아무것도 잘리지 않는다
```

이 파일은 `weekly-report-onboard` 가 만든다. 그다음부터는 사용자가 직접 고치거나 `weekly-report-repos` 로 `repository` 항목만 고친다. `repository` 가 빈 목록이면 설정이 끝나지 않은 상태로 본다.

## 명령

### `weekly-report run`

커밋을 모아 프롬프트를 만든다.

| 플래그 | 뜻 |
| --- | --- |
| `--json` | 사람이 읽는 출력 대신 JSON 한 덩어리를 stdout에 낸다 |
| `--dry-run` | 아무것도 쓰지 않는다. 수집 결과만 보고한다 |

스킬은 항상 `--json` 을 붙인다.

`--dry-run` 이 아니면 다음 순서로 파일을 건드린다. 이 순서가 중요하다.

1. `report.md` 가 비어 있지 않으면 `history/report-<날짜>.md` 로 옮긴다. 비어 있으면 지운다
2. `history/` 가 `report_history_limit` 을 넘으면 오래된 것부터 지운다
3. `prompt.md` 를 새로 쓴다
4. 빈 `report.md` 를 만든다

빈 `report.md` 의 첫 줄에는 `[//]: # (weekly-report: created <시각>)` 주석이 들어간다. `report.md` 는 이름이 고정이라 생성 시각이 파일 이름에 남지 않는데, 그 시각이 이 리포트가 덮는 기간의 끝이고 1번의 아카이브 날짜가 된다. 스킬이 리포트를 쓸 때 이 줄을 지우면 안 된다. 지워졌으면 파일 수정 시각으로 대신하고 `warnings` 로 알린다.

수집 구간의 시작점은 아카이브된 리포트와 아직 `report.md` 에 남아 있는 리포트 중 가장 최근 날짜다. 내용이 채워진 `report.md` 는 아카이브되기 전에도 "이미 보고한 기간"으로 센다(날짜는 created 주석). 하나도 없으면 최근 7일을 본다.

최신 히스토리의 첫 줄이 `[//]: # (weekly-report: boundary approximate date-only)` 면 그 시작점은 날짜만 아는 근사 경계다. `run` 은 이 경계를 쓰는 동안 `warnings` 에 아래 온보딩 경고를 넣는다. `--dry-run` 이나 커밋이 없는 실행은 상태를 쓰지 않으므로 경고를 소모하지 않는다. 첫 리포트를 실제로 작성해 정확한 created 경계가 생기면 그 리포트가 최신 경계가 되고 이후 경고는 사라진다.

### `weekly-report repo list | add | remove`

```
weekly-report repo list [--json]
weekly-report repo add <path> [--name <name>] [--author <name>]...
weekly-report repo remove <name-or-path>
```

`add` 는 경로를 정규화해서 저장한다. 추가하기 전에 확인하는 것:

- 그 경로가 Git 저장소인지. 하위 디렉토리를 줬으면 저장소 루트를 찾아 그 경로를 저장한다
- 이미 등록되어 있는지
- `authors` 로 걸리는 커밋이 최근 90일 안에 있는지. 없으면 경고를 낸다. 실패로 처리하지는 않는다

마지막 항목이 "조용히 0건"을 막는다. 저장소마다 커밋 이름이 다른 경우를 등록 시점에 잡는다.

### `weekly-report authors <path>...`

지정한 저장소에서 커밋 author 후보를 뽑는다. 온보딩이 쓴다.

`--json` 을 붙이면 저장소별 후보를 `{name, email, commits}` 형태로 낸다. 최근 180일 커밋 수 기준 내림차순이다. `git config user.name` 값도 같이 담는다. 설정된 이름과 실제 커밋 이름이 어긋난 경우가 여기서 드러난다.

### `weekly-report history import <file>...`

리포트 파일을 `history/` 에 넣는다. 온보딩이 기존 리포트를 심을 때 쓴다.

| 플래그 | 뜻 |
| --- | --- |
| `--date <YYYY-MM-DD>` | 파일 하나에만 쓸 수 있다. 그 날짜로 저장한다 |
| `--weekly-from <YYYY-MM-DD>` | 첫 파일을 이 날짜로 두고 나머지를 7일씩 거슬러 올라간다 |

날짜를 파일 내용에서 추측하지 않는다. 리포트 제목이 `# 7/23` 처럼 연도가 없는 경우가 많고, 틀린 날짜가 들어가면 다음 수집 구간이 조용히 어긋난다. 둘 중 하나는 반드시 준다.

날짜만으로는 리포트의 정확한 cutoff 시각을 알 수 없다. 누락을 막기 위해 저장 시각은 그 날짜의 `00:00:00` 으로 고정하고, 가져온 파일의 첫 줄에 `[//]: # (weekly-report: boundary approximate date-only)` 를 붙인다. 이 bookkeeping 주석은 과거 리포트를 프롬프트에 넣을 때 제거한다.

성공한 import와 이 경계를 사용하는 첫 `run` 은 다음 canonical English warning을 `warnings` 에 넣는다.

> Onboarding only knows the imported report's date, not its exact cutoff time. To avoid missing commits, the first collection includes the entire boundary day (YYYY-MM-DD). Some work may overlap with the imported report, so please review the generated draft for duplicate items.

CLI 문구는 번역하지 않는다. 사용자에게 보여주는 스킬이 최신 요청의 언어로 번역하되 날짜, 파일 경로, 명령, 기술 식별자는 원문 그대로 보존한다.

## JSON 출력

`run --json` 의 출력. 다른 명령의 `--json` 도 `schema_version` 과 `status` 를 같은 자리에 둔다.

```json
{
  "schema_version": 1,
  "status": "ok",
  "dry_run": false,
  "period": {
    "since": "2026-07-23T09:29:52",
    "until": "2026-07-30T14:02:11",
    "since_source": "history"
  },
  "repositories": [
    {
      "name": "Athena",
      "path": "/Users/mj/workspace/athena",
      "commits": 37,
      "insertions": 2841,
      "deletions": 913,
      "files_changed": 64,
      "authors": ["minjae.kim"]
    }
  ],
  "totals": {
    "commits": 37,
    "insertions": 2841,
    "deletions": 913,
    "files_changed": 64
  },
  "history": {
    "count": 5,
    "latest": "2026-07-23T09:29:52"
  },
  "tokens": {
    "estimate": 48210,
    "method": "heuristic",
    "threshold": 150000,
    "over_threshold": false
  },
  "paths": {
    "prompt": "/Users/mj/.weekly-report/prompt.md",
    "report": "/Users/mj/.weekly-report/report.md",
    "home": "/Users/mj/.weekly-report"
  },
  "warnings": []
}
```

`status` 는 `ok`, `no_commits`, `not_configured`, `repo_error` 중 하나다. `ok` 가 아니면 `paths.prompt` 는 `null` 이고, 스킬은 거기서 멈춘다. `repo_error` 는 종료 코드 3과 짝이고, 어느 경로가 문제인지는 `warnings` 에 있다.

`period.since_source` 는 `history` 또는 `fallback_7d` 다. `fallback_7d` 면 이전 리포트를 못 찾았다는 뜻이라, 스킬은 그 구간이 맞는지 사용자에게 물어본다. 온보딩 직후에 이 값이 나오면 히스토리 심기가 빠진 것이다.

`warnings` 는 사람이 읽는 canonical English 문장 배열이다. 등록된 저장소 중 커밋이 하나도 없다거나, 프롬프트가 임계값을 넘었다는 내용이 들어간다. 사용자에게 표시할 때 스킬은 최신 요청의 언어로 번역하고 날짜, 파일 경로, 명령, 기술 식별자는 그대로 둔다. 요청 언어가 불분명하면 영문 원문을 쓴다.

`tokens.method` 는 `heuristic` 이다. `len(text) // 4` 로 계산한 어림값이라는 뜻이고, 정확한 값이 아니라고 사용자에게 말할 때 쓴다.

## 종료 코드

| 코드 | 뜻 | 스킬이 할 일 |
| --- | --- | --- |
| 0 | 성공 | 계속 진행 |
| 1 | 구간 안에 커밋이 없음 | 사용자에게 알리고 멈춘다. 파일은 그대로다 |
| 2 | 설정이 없거나 잘못됨 | `weekly-report-onboard` 를 안내한다 |
| 3 | 저장소를 읽지 못함 | 어느 경로가 문제인지 알리고 `weekly-report-repos` 를 안내한다 |

0이 아닌 코드에서도 `--json` 이면 JSON을 낸다. `status` 와 `warnings` 에 이유가 담긴다.

1번은 실패가 아니라 "이번 주에 커밋이 없었다"는 사실이다. 그래도 0을 주지 않는다. 이때는 파일을 하나도 쓰지 않아서 지난 프롬프트와 리포트가 그대로 남는데, 호출한 쪽이 그걸 알아야 하기 때문이다.

## 실행 방법

```
uvx --from git+https://github.com/mjkimR/weekly-report@v0.2.1 weekly-report <명령>
```

태그는 `SKILL.md` 안에 박는다. 첫 실행에서 uv가 저장소를 받아 휠을 만들고, 그다음부터는 캐시를 쓴다.

`uv` 가 없으면 아무것도 되지 않는다. 스킬은 `command -v uv` 로 먼저 확인하고, 없으면 설치를 안내한 뒤 멈춘다.
