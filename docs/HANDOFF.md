# 다른 사용자에게 전달하기

이 문서는 준비물과 배포 범위만 다룹니다. 실제 진행 순서는 [실행 안내](REPRODUCIBLE-RUN.md)를 따릅니다.

## 필요한 것

- 공용 저장소를 받은 작업 폴더와 Python 3.9 이상. 출력에는 `requirements-report.txt`, JS 회귀 검사에는 Node가 필요합니다.
- 탭 조회·클릭·업로드가 가능한 브라우저 연결과 사용자 본인의 사이트 로그인. 코드만으로 브라우저 권한이 생기지 않습니다.
- 비교할 모델·조건, 승인할 요청 범위, 서비스별 원/크레딧, 검토할 비개인 첨부 자료. 이전 계정의 설정·파일 경로·승인을 복사하지 않습니다.

## 전달 방법

1. 받은 저장소를 새 세션의 작업 폴더로 엽니다.
2. [시작 프롬프트](../prompts/start.md)를 전달하고 이번 사용자의 정보를 제공합니다. 기존 사용자 대화·개인 보고서는 필요하지 않습니다.
3. 이후 준비·측정·평가·출력은 실행 안내를 따릅니다. 개발 점검이 필요하면 그 문서의 회귀 검사 명령을 사용합니다.

## 배포 시 포함/제외

포함: README, AGENTS, benchmark, browser, cases, config의 공용 템플릿, docs, examples의 가상 평가 예시, prompts, sites, tests, 빈 fixtures/manifest.json, requirements-report.txt, .gitignore.

제외: runs, local, .auth, fixtures/local, 계정·쿠키·브라우저 프로필·실제 답변·스크린샷·개인 보고서. 배포 직전에 `git ls-files runs local .auth fixtures/local`이 비어 있는지 확인합니다. Git ignore는 이미 추적된 비밀을 자동으로 제거하지 않습니다.

독립 무인 실행기나 모든 계정에서 검증된 설치형 제품은 아닙니다. 코드 테스트 통과와 다른 사용자의 실제 계정에서 성공한 것은 별도로 기록합니다.
