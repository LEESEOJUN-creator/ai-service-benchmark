# 다른 사용자에게 전달하기

## 새 세션 전달 시 우선 적용

`docs/REPRODUCIBLE-RUN.md`와 `examples/review-example.json`을 함께 읽습니다. 브라우저 UI 조작 외에 측정·원장·출력기를 새로 만들지 않습니다. 영속 timer-start/timer-complete, record 자동 병합, audit 보완, report 공통 출력 경로를 사용합니다. 예시는 가상이며 개인 실측 자료를 공유할 필요가 없습니다.

## 필요한 것

- 공용 파일을 받은 로컬 프로젝트 폴더와 Python 3.9 이상. JS 회귀 검사는 Node가 필요하다. 최종 PDF·XLSX·그래프 PDF 출력에는 `requirements-report.txt` 설치가 필요하다.
- 실제 탭 조회·클릭·업로드가 가능한 Codex 브라우저 연결. 코드만으로 브라우저 권한이 생기지 않는다.
- 사용자 본인의 사이트 계정과 로그인 세션. 계정·비밀번호를 Git이나 공용 프롬프트에 넣지 않는다.
- 비교 모델·추론 조건 확인, 사용자별 요청 수/비용 범위, 검토한 비개인 첨부 파일.

## 시작 방법

1. 받은 프로젝트 폴더를 작업 폴더로 연다.
2. `python3 -m unittest discover -s tests -v`로 로컬 코드를 점검한다. 선택적으로 `node --test tests/browser.test.mjs`를 실행한다.
3. `prompts/start.md` 내용을 새 Codex 대화에 넣는다. 기존 사용자의 대화를 전달할 필요는 없다.
   추론만 다를 때는 기본 자동 참고 비교 정책으로 진행한다. 엄격 전용이거나 의도가 불명확하면 한 번 확인한다. `docs/EXECUTION-RELIABILITY.md`에 따라 정책을 local 설정/init에 저장하고 첫 실제 요청의 시간 기록부터 검증한다. 사이트의 시간 표시가 없다는 이유로 외부 시간 측정을 생략하지 않는다.
4. 에이전트가 브라우저 연결과 사이트 로그인, 모델·추론·검색 설정을 확인한다. 로그인/MFA가 필요하면 해당 환경의 절차로 진행한다.
5. `cases/core.json`의 최종 질문과 사용자별 검토 파일을 사용한다. 빈 공용 파일 manifest를 이전 사용자의 파일 경로로 채워 넣지 않는다.
6. 승인된 범위에서 예약·전송·답변·비용·증거를 기록한다. 성공 답변마다 `assessment`에 기준별 관찰·판단·근거 위치를, 같은 질문의 서비스 간 차이는 `comparison`에 기록하고, 서비스별 `ux` 관찰을 별도로 남긴다. 한도·모델 없음·조건 미확정을 따로 표시한다.
7. `config/credit-rates.example.json`을 `local/credit-rates.json`으로 복사해 본인 계정의 1크레딧당 원화 환산율을 입력한다. `python3 -m pip install -r requirements-report.txt` 후 `python3 -m benchmark report --run <run-id> --rates local/credit-rates.json`으로 날짜가 붙은 상세 PDF·XLSX·그래프 PDF를 만든다. `~/AI-Benchmark-Reports/<run-id>/`에는 세 파일만 생긴다. `--output-dir`로 저장 위치를 지정할 수 있다. 그래프는 범위표 다음에 모델별 비용·품질 페이지와 별도 시간·수치 대조 페이지를 두며 파일 생성/모델 전환은 기능 표로 분리한다. 소요시간은 완료 관측 상한/구간을 표시한다. PDF 글자·페이지·그래프와 XLSX 각 시트·원화 수식·원문을 검증한다. 원본 기록은 자동 삭제되지 않는다.

이번 계정의 Gemini 실측은 MonoGPT 기본 추론과 Timely 보통을 사용자가 지정한 탐색 비교다. 다른 사용자의 기본 설정이나 엄격 동일 추론 사례로 복사하지 않는다. 사이트별 메뉴·빈 대화·사용량·파일 다운로드는 매번 현재 화면에서 확인한다.

## 배포 시 포함/제외

포함: README, AGENTS, benchmark, browser, cases, config의 공용 템플릿, docs, examples의 가상 평가 예시, prompts, sites, tests, 빈 fixtures/manifest.json, .gitignore.

제외: runs, local, .auth, fixtures/local, 계정·쿠키·브라우저 프로필·실제 원문·스크린샷·개인 보고서. 배포 직전에 `git ls-files runs local .auth fixtures/local`이 비어 있는지 확인한다. Git ignore는 이미 추적된 비밀을 자동으로 제거하지 않는다.

현재 키트는 에이전트 실행형이다. 독립 무인 실행기나 모든 계정에서 검증된 설치형 제품은 아니다. 새 복사본의 테스트 통과와 다른 사용자의 실제 계정에서 성공한 것은 별도로 기록한다.
