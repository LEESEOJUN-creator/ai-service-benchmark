# 재사용 실행 절차

이 키트는 **브라우저 도구를 가진 Codex 에이전트가 실행**합니다. Python만 실행하면 사이트가 자동으로 열리는 프로그램이 아닙니다. CLI와 데스크톱 앱은 연결된 도구·권한이 다를 수 있습니다. 실제 환경에서 탭 조회, 클릭, 파일 선택 기능을 확인합니다. 도구가 없으면 중단하고 설치·연결을 안내합니다.

## 시작

1. `AGENTS.md`, `README.md`, `docs/PROTOCOL.md`, `docs/EVALUATION.md`, 대상별 `docs/sites/`를 읽습니다. 최종 보고서는 core-v2 결과만 사용하고 이전 파일럿과 혼합하지 않습니다.
2. 사용자가 각 사이트에 로그인합니다. 이미 로그인했다면 그 세션을 이용합니다. 비밀번호를 Git, 프롬프트 파일, 로그에 저장하지 않습니다. MFA·CAPTCHA·권한 확대는 해당 환경의 승인 절차를 따릅니다.
3. 8개 항목 각 1개인 `cases/core.json`을 사용합니다. 모델별로 제공되는 서비스만 그룹에 넣고 제외 사유를 기록합니다. GPT 그룹은 3사, Gemini/Claude 그룹은 지원되는 2사입니다. 자동 라우팅·고가 최상위 모델은 사용하지 않습니다.
4. 원화 상한을 검증할 수 있으면 `plan`으로 엄격 점검합니다. 가격 상한을 확인할 수 없는 소규모 관측은 그 한계를 사용자에게 알린 뒤 **명시된 요청 수 범위**에서만 실행합니다. 금액 상한을 보장한다고 말하지 않습니다. 기본 재시도 0회, 한 실행의 요청 상한 최대 40회, 자동 충전·추가 결제 없음입니다. 40회는 안전 상한이지 사용자 승인이나 실행 목표가 아닙니다. 작은 배치를 반복해 승인 범위를 우회하지 않습니다.
   - `plan`의 예산·요청당 비용 차단만으로 전체 작업을 종료하지 않습니다. 사용자가 금액 상한 없이 고정 요청 수를 명시적으로 승인했다면 `request_limited_unknown_price` 경로로 진행하고 `authorization_scope`와 `unknown_price_acknowledged=true`를 기록합니다. 사용자가 단지 저장소를 열어 달라고 한 것은 승인으로 보지 않습니다.
   - 활성 질문·모델·서비스·후속 턴을 세어 **실제 계획 요청 수**를 고정합니다. 승인 수가 기본 40회보다 작으면 작은 수를 사용합니다. 모델·추론·첨부 검토 불일치, 로그인 실패, 중복 전송 위험은 금액 승인으로 해제되지 않습니다.
5. 비개인 파일만 내용을 검토하고 `fixtures/local/manifest.json`에 분류·해시·정답·허용 서비스를 기록합니다. 공유용 manifest는 개인 경로 없이 비워 둡니다. `image-01`, `file-01`은 자료 등록 전 비활성입니다.

`plan`은 계정별 근거를 채우기 전의 엄격 점검표입니다. 차단 목록을 그대로 최종 실패로 복사하지 말고 현재 UI에서 확인 가능한 항목을 확인하세요. 실제 백엔드 버전이 공개되지 않은 경우 UI 표시 조건 일치와 백엔드 미검증을 구분합니다. 서비스가 요청별 비용을 제공하지 않으면 `unavailable`/null로 남기고 무료라고 쓰지 않습니다. 비용 미노출만을 이유로 답변·시간·UX 측정을 포기하지는 않습니다. 반대로 서로 다른 모델·추론 수준을 임의로 같다고 간주하지 않습니다.

## 상태 기록 명령

```sh
python3 -m benchmark init --run pilot
python3 -m benchmark record --run pilot --event runs/pilot/reserve.json
# 위 기록이 성공한 뒤 실제 UI 전송 1회
python3 -m benchmark record --run pilot --event runs/pilot/result.json
# 각 성공 답변의 기준별 평가와 서비스별 UX 관찰을 별도 이벤트로 기록
python3 -m benchmark record --run pilot --event runs/pilot/assessment.json
python3 -m benchmark record --run pilot --event runs/pilot/ux.json
python3 -m benchmark status --run pilot
python3 -m pip install -r requirements-report.txt
python3 -m benchmark report --run pilot --rates local/credit-rates.json
```

`init`은 기존 실행을 덮어쓰지 않습니다. `record`는 같은 요청 ID의 재예약과 결과 덮어쓰기를 거부합니다. 정정은 `note` 이벤트로 추가합니다. 미완료 예약은 먼저 사이트 대화·크레딧과 대조하며 재전송하지 않습니다. 예약은 사용자 승인이나 브라우저 사전 검사를 대신하지 않습니다. 한 번에 하나의 기록 프로세스만 사용합니다. 비정상 종료 후 `.writer.lock`이 남으면 작성 프로세스 종료와 JSON 무결성을 확인한 뒤 수동 복구합니다.

### reserve 이벤트

필수 필드: `kind=reserve`, 고유 `request_id`, `service`, 실제 `model`, `reasoning`, `case_id`, 원문 `prompt`, UTF-8 `prompt_sha256`, `ui_evidence`, `authorization_scope`, `request_limit`, `cost_mode=request_limited_unknown_price`, `unknown_price_acknowledged=true`, `comparison_tier`, `feature_settings`, `fixtures`.

같은 모델 묶음의 사이트별 표시명이 다르면 `model_group`에 공통 묶음 이름을 기록합니다. 해당 서비스에서 모델을 실제로 제공하지 않는다고 확인한 경우에만 `excluded_services={"chatgpt":"모델 메뉴에서 확인한 미제공 사유"}`를 넣습니다. 보고서는 명시적 제외 사유가 없으면 `모델 없음` 대신 `기록 없음`으로 표시합니다.

`unknown_price_acknowledged`는 실제 사용자와 합의한 경우에만 true입니다. 지침을 읽었다는 이유로 자동 설정하지 않습니다. `fixtures`는 ID별 `path`, `sha256`, `reviewed=true`, `allowed_services` 객체입니다. 경로는 프로젝트 상대 경로이고 예약 때 바이트를 다시 검사합니다. `comparison_tier=ui_matched`는 표시 조건 일치일 뿐 실제 백엔드가 같다는 의미가 아닙니다. 옵션 미노출은 `reasoning=not_exposed`, `comparison_tier=exploratory`이며 엄격 비교 순위에서 제외합니다. 서로 다른 노출 설정을 억지로 같은 것으로 매핑하지 않습니다. 비대칭 설정은 사용자가 서비스별 값을 명시한 경우에만 비교 범위·사유·요청 상한을 남깁니다.

### result 이벤트

필수: `kind=result`, 같은 `request_id`, `status`, 성공 시 `answer`, `cost_status`. 선택: `cost`, `cost_unit`, `cost_components`, `last_generating_observed_ms`, `first_complete_observed_ms`, `quality_note`, `limitations`, `evidence`.

미확정 비용은 null입니다. `cost_status`는 `ledger_verified`, `balance_observed`, `contaminated`, `pending`, `unavailable` 중 하나입니다. 실패·미지원도 비용이 들 수 있습니다. 미측정을 0으로 채우지 않습니다.

### 원화 환산율 입력

보고서 출력 전에 `config/credit-rates.example.json`을 `local/credit-rates.json`으로 복사하고, 실제 계정에서 적용할 `1크레딧당 원`을 양수로 입력합니다. 예를 들어 사용자가 MonoGPT 1크레딧=1원, Timely AI 1크레딧=2원이라고 정한 실행은 `{"monogpt": 1, "timely": 2}`입니다. 이는 사용자가 제공한 환산 기준이며 실제 청구액·할인·구독료를 자동 검증한 값이 아닙니다. 다른 계정·시점에는 다시 입력하세요. `local/`은 Git에서 제외됩니다.

차감이 크레딧으로 기록된 서비스의 환산율이 없으면 보고서 생성 전에 오류를 내고 임의의 0원이나 기본 요율을 적용하지 않습니다. 원시 단위가 `KRW`/`원`이면 그대로 원화로 사용합니다. 차감 미확정·미노출은 환산하지 않고 `미확정`/`미노출`로 남깁니다. 원시 차감과 환산율은 XLSX `실측 원장`에서 검증할 수 있고, 비교표·상세 PDF·그래프의 비용은 KRW입니다.

### assessment / ux 이벤트

성공 결과마다 `assessment`를 **result 저장 이후** 추가합니다. 필수: `kind=assessment`, 같은 `request_id`, `evaluator`, `blind`(진짜 블라인드 채점일 때만 true), `criteria` 배열. 배열은 해당 질문의 `rubric`과 같은 순서·이름으로 다섯 개를 담고, 각 항목에 `criterion`, 0~4 정수 `score`, 실제로 확인한 `observation`, 점수 판단·감점 이유 `judgement`, 답변 위치나 검사 ID `evidence_ref`를 넣습니다. 평가 없이 최종 PDF·XLSX를 생성하지 않습니다. 확정되지 않은 사실·숫자를 근거로 만들지 마세요.

```json
{
  "kind": "assessment", "request_id": "mono-education-01",
  "evaluator": "평가자 표시명", "blind": false,
  "criteria": [
    {
      "criterion": "질문 rubric의 첫 기준을 그대로 입력",
      "score": 3,
      "observation": "답변에서 실제 확인한 수치·문구",
      "judgement": "무엇을 충족했고 무엇이 빠져 3점인지",
      "evidence_ref": "답변 첫 단락 또는 검사 ID"
    }
  ]
}
```

위 배열은 형식 설명용 1개 항목 예시이며 실제 기록에는 해당 질문의 **5개 기준 모두** 필요합니다. `ux`는 서비스별 한 번 기록하며 `kind=ux`, `service`, `observations=[{"aspect":"모델 선택", "observation":"실제로 본 경로와 상태", "evidence":"화면 또는 기록 위치"}]` 형식입니다. 모델·추론 메뉴, 첨부·소진내역 접근, 설정 유지, 오류 복구, 답변 가독성·시각 요소, 다운로드 성공을 확인한 범위에서 적습니다. UX를 관찰하지 않았다면 미관측으로 둡니다. 평가는 결과를 덮어쓰지 않고 별도 이벤트로 보존합니다.

## 요청별 UI 흐름

새 대화 → 모델 재선택 → 추론/검색/도구 확인 → 첨부 전 잔액 → 업로드 완료 → 전송 전 잔액 → 원문·파일 확인 → 예약 기록 → 전송 1회 → 완료 관측 → 답변 복사 → 생성 파일 다운로드/검증 → 답변 후 잔액/소진 내역 → 결과 기록.

- 새 대화의 기본 모델·추론값을 믿지 않습니다. 자동으로 다른 모델이 선택될 수 있습니다. 이전 답변·복사 버튼이 남아 있지 않은 빈 대화를 확인한 뒤 전송합니다.
- 타임리의 PNG→WebP 같은 서비스 전처리는 원본 동일성과 별도로 기록합니다.
- 입력 중 ‘프롬프트 고도화’를 누르지 않습니다. 실제 제출 문장이 원문과 같은지 다시 확인합니다.
- 비용은 **첨부 비용 + 답변 비용 + 도구 비용 - 할인/환불**을 구분합니다. 공용 잔액이면 내역의 모델·시각·가능한 대화 식별자로 대조합니다. 귀속 불명 내역은 제외하고 불확실성을 표시합니다.
- `browser/observe.mjs`는 이미 확인한 탭·선택자를 주입하는 전송/관측 보조 모듈입니다. 로그인·모델 선택을 자동 추측하지 않습니다. 사이트 UI가 달라지면 최신 화면으로 선택자를 갱신합니다. 처음 사용할 때 소규모 실측으로 확인합니다.
- 완료 관측 중 문서 작성 같은 다른 작업을 끼우지 않습니다. 최대 20초 관측 창을 이어 실행하고 60초 이내 사용자에게 진행 상황을 알립니다. 마지막 생성 중/최초 완료 구간을 기록합니다. 넓은 구간은 속도 순위 제외입니다.
- ChatGPT는 새 대화에도 이전 완료 status가 남을 수 있습니다. 현재 프롬프트·답변 복사 버튼·중지 버튼 소멸을 함께 확인합니다.
- Timely가 캔버스에 답변을 작성하면 캔버스 복사로 원문 전체를 수집합니다. 안내 메시지만 수집하지 않습니다.
- `browser/gpt-medium.mjs`는 현재 한국어 UI에서 검증한 GPT 준비/복사 보조 코드입니다. `browser/batch.mjs`는 질문 객체를 인자로 고정하고 예약 상태를 전송 전에 저장합니다. 배치 전에 예산·동일 조건·자료 승인 검사를 완료해야 하며 이 모듈 자체가 예산 승인을 대신하지 않습니다.
- 배치 호출에는 `preflight={uiVerified:true,conditionsMatch:true,authorizationScope:"실제 승인 범위",maxTotalRequests:승인된_요청수}`가 필요합니다. 이 값을 지침만 보고 자동 승인하지 않습니다. 누적 기록과 새 요청이 승인 수를 넘으면 전송 전에 차단합니다. 원화 비용 상한은 별도 사전 점검 대상입니다.
- 비대칭 추론을 사용자가 지정했다면 `comparisonMode:"exploratory"`, `conditionsMatch:false`, `userAuthorizedMismatch:true`, 구체적 `mismatchNote`를 함께 넘깁니다. 결과에 사이트별 추론 값을 보존하고 엄격 비교 총점에 합치지 않습니다. 예시 구현 `browser/gemini-exploratory.mjs`는 이번 UI를 확인한 보조 코드이며 다른 계정에서는 메뉴·모델명을 다시 확인해야 합니다.
- UI 메뉴가 바뀌거나 타임아웃이 나면 현황을 읽고 중단 지점을 확인합니다. 전송이나 생성 요청을 일괄 재시도하지 않습니다.

## 평가와 제출

정답·지시 준수·출처·환각·사용성은 각각 근거를 남깁니다. 0~4점 평가를 쓸 경우 공통 기준은 0=검증된 중대한 오류, 1=핵심 누락 다수, 2=부분 충족, 3=대체로 충족/경미한 누락, 4=전부 충족입니다. 미실행/판독 실패는 null입니다. [EVALUATION](EVALUATION.md)의 절차대로 **답변마다 5개 기준을 각각 채점하고 실제 문구·수치·파일 검사 결과와 감점 이유를 적습니다.** 서비스명을 가린 원문을 평가하고, 평가자·근거를 기록합니다. 블라인드 없이 관측했다면 블라인드 평가라고 표기하지 않습니다.

코드는 읽기 검토 후 네트워크·개인 파일 접근 없는 제한 실행 환경에서 고정 테스트를 적용합니다. 생성 파일은 다운로드만으로 성공이 아닙니다. 확장자·실제 형식·시트·셀 타입·수식·계산값을 검사하고 결과를 렌더링합니다. 검증 도구가 없으면 미검증으로 남깁니다.

`benchmark/validation.py`는 검토한 주문 집계 함수와 고정 매출 XLSX의 제한 검사입니다. 임의 코드를 안전하게 실행하는 범용 샌드박스가 아니므로 외부 코드를 무검토로 넣지 않습니다. 선택 UI와 사용내역 모델명이 다르면 양쪽 근거를 남기고 동일 모델 비교에서 제외합니다. 도구 한도 실패는 답변 완료와 작업 성공을 분리하며 모델 품질을 0점으로 치환하지 않습니다.

회귀 검사: `python3 -m unittest discover -s tests -v`, `node --test tests/browser.test.mjs`. 테스트는 실제 사이트 로그인이나 결제를 수행하지 않습니다.

`report` 명령은 실제 요청 기록이 하나 이상 있어야 최종 보고서를 만듭니다. 0건에서 `기록된 요청이 없어`가 나오면 생성기 고장이 아니라 아직 비교 결과가 없다는 뜻입니다. `status`로 중단 사유를 보고하고 임의의 성공·예약 이벤트를 만들지 마세요. 기록이 생긴 뒤에는 `requirements-report.txt`를 설치한 환경에서 `~/AI-Benchmark-Reports/<run-id>/`에 날짜가 포함된 상세 PDF·XLSX·그래프 PDF 세 파일을 만듭니다. 같은 이름의 최종 파일은 덮어쓰지 않습니다. 상세 PDF에는 기준별 관찰·판단·근거 위치, XLSX에는 비교표·기준별 평가·실측 원장·답변 원문·사용 경험을 담습니다. 그래프 PDF는 모델별 가로 페이지에 질문별 비용(KRW)·품질(/20)·소요시간(초)의 선그래프 세 개를 배치합니다. 가로축은 같은 질문 순서, 색상은 서비스, 점의 숫자는 실제 값입니다. 미노출 비용·미평가 품질·미관측 시간은 선을 끊으며 0으로 채우지 않습니다. 시간은 성공 답변의 최초 완료 관측 상한을 점으로 표시하고, 마지막 생성 중~최초 완료 구간은 세로선과 구간 숫자로 보존합니다. 상한만 관측했으면 ≤로 표시하며 관측 간격이 넓은 경우 속도 순위를 단정하지 않습니다. 질문이 10개보다 많으면 다음 페이지로 나눕니다. 파일 생성의 도구·라우팅 개입과 탐색적 조건은 명시합니다. `--output-dir "원하는 폴더"`로 저장 위치를 바꿀 수 있으며 완료 시 실제 경로를 안내합니다. 생성된 PDF의 글자·페이지·그래프와 XLSX의 시트·수식·긴 답변을 직접 확인합니다. 원본 `session.json`과 증거는 자동 삭제하지 않으며, 개인별 보관 방침에 따라 최종본 검증 후에만 별도 정리합니다. Git에는 코드·빈 템플릿·공용 지침만 포함합니다. 파일을 공개 전송하기 전 계정 표시·대화 기록·개인정보를 검토합니다. 최종 보고서에는 **모델×서비스×8개 항목 전체 커버리지**와 제외/미실행 이유를 포함합니다. 일부 파일럿을 전체 완료라고 부르지 않습니다.
