# v0.1에서 v0.2로 옮기기

호환을 깨는 변경이 한꺼번에 들어간다. 설정 위치와 형식, 상태 디렉토리, `repository` 스키마, CLI 하위 명령, 패키지 이름이 모두 바뀐다.

사용자가 한 명이라 자동 마이그레이션 코드는 만들지 않는다. 한 번만 하고 이 문서는 지운다.

## 먼저: 잃을 수 있는 것

`build/history/` 안의 리포트는 사본이 하나뿐이다. `build/` 가 `.gitignore` 에 걸려 있어서 Git에는 없는데, 이 파일이 다음 수집 구간의 시작점을 정하는 유일한 기록이다. 옮기지 않으면 히스토리가 사라지고 수집 구간이 최근 7일로 리셋된다.

`config/config.yaml` 과 `config/template.md` 도 마찬가지로 Git에 없다.

**1번을 하기 전에 아무것도 시작하지 않는다.**

## 절차

### 1. 백업

```
cp -R build ~/weekly-report-backup-build
cp -R config ~/weekly-report-backup-config
```

전환이 끝나고 두 주 정도 돌려본 뒤에 지운다.

### 2. 상태 디렉토리 만들고 파일 옮기기

```
mkdir -p ~/.weekly-report/history
cp build/history/*.md        ~/.weekly-report/history/
cp config/template.md        ~/.weekly-report/template.md
```

`history/` 안의 파일 이름 규칙은 그대로다. `report-<YYYYmmdd-HHMMSS>.md` 를 계속 쓰므로 이름을 고칠 필요가 없다.

### 3. 작업 중이던 리포트 처리

`build/report-<타임스탬프>.md` 가 있고 내용이 채워져 있으면 `~/.weekly-report/report.md` 로 옮긴다. 아직 손대지 않았다면(안내 주석만 있으면) 버린다.

`build/prompt-*.md` 는 버린다. 실행 중간 산물이라 옮길 이유가 없다.

`build/memo.md` 도 버린다. 메모 파일은 없어졌다. 적어둔 내용이 있으면 이번 리포트를 쓸 때 에이전트에 그대로 말해준다.

### 4. 설정 옮기고 `repository` 바꾸기

`config/config.yaml` 을 `~/.weekly-report/config.yaml` 로 옮기고 `repository` 를 객체 목록으로 고친다.

전:

```yaml
author: minjae.kim
lang: korean
repository:
  - /Users/mj/workspace/athena
max_diff_lines: 50
report_history_limit: 5
```

후:

```yaml
author: minjae.kim
lang: korean
repository:
  - path: /Users/mj/workspace/athena
    name: Athena
max_diff_lines: 50
report_history_limit: 5
```

`name` 은 선택이지만 이 기회에 넣는 게 좋다. 예전에는 경로의 마지막 조각이 리포트에 그대로 나왔다. 저장소마다 커밋 이름이 다르면 그 저장소에 `authors` 를 붙인다. `weekly-report authors` 로 확인할 수 있다.

### 5. 검증

```
weekly-report run --dry-run --json
```

확인할 것:

- `period.since_source` 가 `history` 인지. `fallback_7d` 면 2번에서 히스토리가 안 옮겨졌다는 뜻이다
- `period.since` 가 마지막 리포트 날짜와 같은지
- `repositories[].commits` 가 예전 실행과 비슷한지. 0이면 작성자 이름이 안 맞는다는 뜻이다
- `history.count` 가 옮긴 파일 개수와 같은지

`--dry-run` 이라 아무것도 쓰지 않는다. 여기서 틀렸으면 고치고 다시 돌린다.

### 6. 옛 파일 정리

검증이 끝난 뒤에 한다.

- `build/` 와 `config/` 를 지운다
- `.gitignore` 에서 `build/`, `config/config.yaml`, `config/template.md` 줄을 뺀다. `build/` 는 파이썬 빌드 산출물 이름과 겹치니 남겨도 무해하다
- `config/config.yaml.example`, `config/template.md.example` 은 버리지 않고 패키지 안으로 옮긴다. 온보딩이 기본 형식으로 참고한다
- `setup_conf.py` 를 지운다. 예제 파일을 복사하는 스크립트였는데 온보딩이 그 일을 대신한다

## 코드 쪽에서 같이 바뀌는 것

마이그레이션 절차는 아니지만 같은 릴리스에 들어간다.

| 무엇 | 지금 | 바뀔 것 |
| --- | --- | --- |
| 설정/상태 경로 | `Path(__file__).parent.parent` 기준 | `~/.weekly-report/`, `WEEKLY_REPORT_HOME` 으로 변경 가능 |
| 모듈 이름 | `weekly_report_prompt` | `weekly_report` |
| 콘솔 스크립트 | `weekly-report-prompt` | `weekly-report` |
| CLI 형태 | 플래그만 | `run`, `repo`, `authors`, `history` 하위 명령 |
| 출력 | rich 패널과 표 | `--json` 과 사람이 읽는 간단한 요약 |
| 저장소 열기 | `git.Repo(repo_path)` | 저장소 루트를 찾아 올라간다 |
| 작성자 대조 | 전역 `author` 하나와 정확히 일치 | 저장소별 `authors` 목록에 포함되는지 |
| 메모 | `memo.md` 읽고 프롬프트에 끼움 | 없앤다 |
| 의존성 | `rich`, `tiktoken` 포함 | 둘 다 뺀다 |

메모를 없애면서 지울 것: `const.py` 의 `MEMO_BLANK_MESSAGE`, `report_file_manager.py` 의 `fetch_memo()` 와 `ensure_memo_file()`, `prompt_generator.py` 의 메모 섹션, `main.py` 의 호출부. 테스트는 `test_report_file_manager.py`, `test_prompt_generator.py`, `test_main.py`, `test_main_cli.py` 네 개가 걸린다.

경로 기준이 바뀌는 것이 가장 중요하다. 지금은 패키지 디렉토리의 부모를 기준으로 잡아서, 소스에서 실행할 때만 맞고 설치본에서는 `site-packages` 를 가리킨다. uvx로 실행하면 바로 깨진다.

## 순서

```
1. GitHub에서 저장소 이름을 weekly-report 로 바꾼다
2. git remote set-url origin https://github.com/mjkimR/weekly-report
3. git tag v0.1.0 && git push --tags
4. git switch -c feat/agent-skill
5. git mv weekly_report_prompt weekly_report 하고 참조를 고친다
6. 코드 작업
7. 위의 데이터 마이그레이션
8. v0.2.0 태그
```

1번을 `SKILL.md` 작성 전에 해야 한다. 안 그러면 스킬 본문과 문서에 옛 URL이 박힌다. GitHub이 이름 변경 후 옛 URL을 영구 리다이렉트하므로 `v0.1.0` 을 가리키는 참조는 계속 동작한다.

3번의 태그가 되돌아갈 지점이다. 전환이 마음에 안 들면 `uvx --from git+https://github.com/mjkimR/weekly-report@v0.1.0 weekly-report-prompt` 로 예전 도구를 그대로 쓸 수 있다.
