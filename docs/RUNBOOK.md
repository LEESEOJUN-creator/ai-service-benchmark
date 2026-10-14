# 재사용 실행 절차

이 키트는 **브라우저 도구를 가진 Codex 에이전트가 실행**합니다. Python만 실행하면 사이트가 자동으로 열리는 프로그램이 아닙니다. CLI와 데스크톱 앱은 연결된 도구·권한이 다를 수 있습니다. 실제 환경에서 탭 조회, 클릭, 파일 선택 기능을 확인합니다. 도구가 없으면 중단하고 설치·연결을 안내합니다.

## 시작

1. `AGENTS.md`, `README.md`, `docs/PROTOCOL.md`, `docs/EVALUATION.md`, 대상별 `docs/sites/`를 읽습니다. 최종 보고서는 core-v2 결과만 사용하고 이전 파일럿과 혼합하지 않습니다.
2. 사용자가 각 사이트에 로그인합니다. 이미 로그인했다면 그 세션을 이용합니다. 비밀번호를 Git, 프롬프트 파일, 로그에 저장하지 않습니다. MFA·CAPTCHA·권한 확대는 해당 환경의 승인 절차를 따릅니다.
3. 8개 항목 각 1개인 `cases/core.json`을 사용합니다. 모델별로 제공되는 서비스만 그룹에 넣고 제외 사유를 기록합니다. GPT 그룹은 3사, Gemini/Claude 그룹은 지원되는 2사입니다. 자동 라우팅·고가 최상위 모델은 사용하지 않습니다.
4. 원화 상한을 검증할 수 있으면 `plan`으로 엄격 점검합니다. 가격 상한을 확인할 수 없는 소규모 관측은 그 한계를 사용자에게 알린 뒤 **명시된 요청 수 범위**에서만 실행합니다. 금액 상한을 보장한다고 말하지 않습니다. 기본 재시도 0회, 배치 최대 12회, 자동 충전·추가 결제 없음입니다. 작은 배치를 반복해 승인 범위를 우회하지 않습니다.
5. 비개인 파일만 내용을 검토하고 `fixtures/local/manifest.json`에 분류·해시·정답·허용 서비스를 기록합니다. 공유용 manifest는 개인 경로 없이 비워 둡니다. `image-01`, `file-01`은 자료 등록 전 비활성입니다.

## 상태 기록 명령

```sh
python3 -m benchmark init --run pilot
python3 -m benchmark record --run pilot --event runs/pilot/reserve.json
# 위 기록이 성공한 뒤 실제 UI 전송 1회
python3 -m benchmark record --run pilot --event runs/pilot/result.json
python3 -m benchmark status --run pilot
python3 -m benchmark report --run pilot
```

`init`은 기존 실행을 덮어쓰지 않습니다. `record`는 같은 요청 ID의 재예약과 결과 덮어쓰기를 거부합니다. 정정은 `note` 이벤트로 추가합니다. 미완료 예약은 먼저 사이트 대화·크레딧과 대조하며 재전송하지 않습니다. 예약은 사용자 승인이나 브라우저 사전 검사를 대신하지 않습니다. 한 번에 하나의 기록 프로세스만 사용합니다. 비정상 종료 후 `.writer.lock`이 남으면 작성 프로세스 종료와 JSON 무결성을 확인한 뒤 수동 복구합니다.

### reserve 이벤트

필수 필드: `kind=reserve`, 고유 `request_id`, `service`, 실제 `model`, `reasoning`, `case_id`, 원문 `prompt`, UTF-8 `prompt_sha256`, `ui_evidence`, `authorization_scope`, `request_limit`, `cost_mode=request_limited_unknown_price`, `unknown_price_acknowledged=true`, `comparison_tier`, `feature_settings`, `fixtures`.

`unknown_price_acknowledged`는 실제 사용자와 합의한 경우에만 true입니다. 지침을 읽었다는 이유로 자동 설정하지 않습니다. `fixtures`는 ID별 `path`, `sha256`, `reviewed=true`, `allowed_services` 객체입니다. 경로는 프로젝트 상대 경로이고 예약 때 바이트를 다시 검사합니다. `comparison_tier=ui_matched`는 표시 조건 일치일 뿐 실제 백엔드가 같다는 의미가 아닙니다. 옵션 미노출은 `reasoning=not_exposed`, `comparison_tier=exploratory`이며 엄격 비교 순위에서 제외합니다. 서로 다른 노출 설정을 억지로 같은 것으로 매핑하지 않습니다.

### result 이벤트

필수: `kind=result`, 같은 `request_id`, `status`, 성공 시 `answer`, `cost_status`. 선택: `cost`, `cost_unit`, `cost_components`, `last_generating_observed_ms`, `first_complete_observed_ms`, `quality_note`, `limitations`, `evidence`.

미확정 비용은 null입니다. `cost_status`는 `ledger_verified`, `balance_observed`, `contaminated`, `pending`, `unavailable` 중 하나입니다. 실패·미지원도 비용이 들 수 있습니다. 미측정을 0으로 채우지 않습니다.

## 요청별 UI 흐름

새 대화 → 모델 재선택 → 추론/검색/도구 확인 → 첨부 전 잔액 → 업로드 완료 → 전송 전 잔액 → 원문·파일 확인 → 예약 기록 → 전송 1회 → 완료 관측 → 답변 복사 → 생성 파일 다운로드/검증 → 답변 후 잔액/소진 내역 → 결과 기록.

- 새 대화의 기본 모델·추론값을 믿지 않습니다. 자동으로 다른 모델이 선택될 수 있습니다.
- 타임리의 PNG→WebP 같은 서비스 전처리는 원본 동일성과 별도로 기록합니다.
- 입력 중 ‘프롬프트 고도화’를 누르지 않습니다. 실제 제출 문장이 원문과 같은지 다시 확인합니다.
- 비용은 **첨부 비용 + 답변 비용 + 도구 비용 - 할인/환불**을 구분합니다. 공용 잔액이면 내역의 모델·시각·가능한 대화 식별자로 대조합니다. 귀속 불명 내역은 제외하고 불확실성을 표시합니다.
- `browser/observe.mjs`는 이미 확인한 탭·선택자를 주입하는 전송/관측 보조 모듈입니다. 로그인·모델 선택을 자동 추측하지 않습니다. 사이트 UI가 달라지면 최신 화면으로 선택자를 갱신합니다. 처음 사용할 때 소규모 실측으로 확인합니다.
- 완료 관측 중 문서 작성 같은 다른 작업을 끼우지 않습니다. 최대 20초 관측 창을 이어 실행하고 60초 이내 사용자에게 진행 상황을 알립니다. 마지막 생성 중/최초 완료 구간을 기록합니다. 넓은 구간은 속도 순위 제외입니다.
- ChatGPT는 새 대화에도 이전 완료 status가 남을 수 있습니다. 현재 프롬프트·답변 복사 버튼·중지 버튼 소멸을 함께 확인합니다.
- Timely가 캔버스에 답변을 작성하면 캔버스 복사로 원문 전체를 수집합니다. 안내 메시지만 수집하지 않습니다.
- `browser/gpt-medium.mjs`는 현재 한국어 UI에서 검증한 GPT 준비/복사 보조 코드입니다. `browser/batch.mjs`는 질문 객체를 인자로 고정하고 예약 상태를 전송 전에 저장합니다. 배치 전에 예산·동일 조건·자료 승인 검사를 완료해야 하며 이 모듈 자체가 예산 승인을 대신하지 않습니다.
- 배치 호출에는 `preflight={uiVerified:true,conditionsMatch:true,authorizationScope:"실제 승인 범위",maxTotalRequests:승인된_요청수}`가 필요합니다. 이 값을 지침만 보고 자동 승인하지 않습니다. 누적 기록과 새 요청이 승인 수를 넘으면 전송 전에 차단합니다. 원화 비용 상한은 별도 사전 점검 대상입니다.
- UI 메뉴가 바뀌거나 타임아웃이 나면 현황을 읽고 중단 지점을 확인합니다. 전송이나 생성 요청을 일괄 재시도하지 않습니다.

## 평가와 제출

정답·지시 준수·출처·환각·사용성은 각각 근거를 남깁니다. 0~4점 평가를 쓸 경우 공통 기준은 0=검증된 중대한 오류, 1=핵심 누락 다수, 2=부분 충족, 3=대체로 충족/경미한 누락, 4=전부 충족입니다. 미실행/판독 실패는 null입니다. 서비스명을 가린 원문을 평가하고, 평가자·근거를 기록합니다. 블라인드 없이 관측했다면 블라인드 평가라고 표기하지 않습니다.

코드는 읽기 검토 후 네트워크·개인 파일 접근 없는 제한 실행 환경에서 고정 테스트를 적용합니다. 생성 파일은 다운로드만으로 성공이 아닙니다. 확장자·실제 형식·시트·셀 타입·수식·계산값을 검사하고 결과를 렌더링합니다. 검증 도구가 없으면 미검증으로 남깁니다.

`benchmark/validation.py`는 검토한 주문 집계 함수와 고정 매출 XLSX의 제한 검사입니다. 임의 코드를 안전하게 실행하는 범용 샌드박스가 아니므로 외부 코드를 무검토로 넣지 않습니다. 선택 UI와 사용내역 모델명이 다르면 양쪽 근거를 남기고 동일 모델 비교에서 제외합니다. 도구 한도 실패는 답변 완료와 작업 성공을 분리하며 모델 품질을 0점으로 치환하지 않습니다.

회귀 검사: `python3 -m unittest discover -s tests -v`, `node --test tests/browser.test.mjs`. 테스트는 실제 사이트 로그인이나 결제를 수행하지 않습니다.

`report.html`은 오프라인 열람용이며 인쇄로 PDF 저장할 수 있습니다. 실제 원문·스크린샷·XLSX/PDF는 모두 `runs/` 아래입니다. Git에는 코드·빈 템플릿·공용 지침만 포함합니다. 파일을 공개 전송하기 전 계정 표시·대화 기록·개인정보를 검토합니다. 최종 보고서에는 **모델×서비스×8개 항목 전체 커버리지**와 제외/미실행 이유를 포함합니다. 일부 파일럿을 전체 완료라고 부르지 않습니다.
