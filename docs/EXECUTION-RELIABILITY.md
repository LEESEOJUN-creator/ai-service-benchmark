# 추론 예외와 선택적 브라우저 보조 코드

기본 진행 순서는 [실행 안내](REPRODUCIBLE-RUN.md)를 따릅니다. 이 문서는 추론 예외 정책과 선택적 Playwright 보조 코드만 설명합니다. 아래 JS 예시는 일반 CLI 측정의 필수 단계가 아닙니다.

## 추론 불일치: 자동 참고 비교 또는 한 번 확인

기본 config의 `reasoning_mismatch_policy`는 `auto_exploratory`입니다. 이는 승인된 테스트 범위 안에서 **추론만** 다르거나 미노출인 경우 참고 비교로 계속하는 정책이며 실행 허가·결제 허가 자체가 아닙니다. 시작 프롬프트에 이 동작을 알리고 실행 설정을 `local/`에 저장합니다. 사용자가 엄격 비교만 원하면 `ask`로 바꿉니다. 이전 실행의 계정별 승인·설정은 공용 Git으로 전달하지 않습니다.

1. 같은 모델/버전·질문·첨부·검색 등 기타 설정을 먼저 확인합니다. 동일 모델을 못 찾으면 임의 모델 대체는 하지 않습니다.
2. 같은 추론 설정을 선택할 수 있으면 엄격 비교를 합니다.
3. 추론만 다르면 `auto_exploratory`에서는 재질문 없이 가능한 낮은/기본 단계로 참고 비교를 합니다. 사용자가 이미 지정한 사이트별 설정이 있으면 그것을 우선합니다. `ask`/의도 불명확일 때는 “이 모델은 A의 기본(미공개), B의 보통으로 참고 비교할까요?”처럼 실제 조건을 한 번 확인합니다. 응답 대기 중 다른 확정 모델은 진행할 수 있습니다.
4. 질문 없이 Gemini를 빼고 최종 완료라고 보고하지 않습니다. 거절/미응답이면 확인 대기/제외 사유를 명시합니다. ChatGPT의 미지원 모델은 모델 없음입니다.

`init --config local/실행설정.json`은 정책을 실행 기록에 고정합니다. 참고 비교의 reserve에는 같은 정규화 `model`/`model_group`, 사이트별 `reasoning`, `comparison_tier:"exploratory"`, 구체적 `mismatch_note`와 기존 `authorization_scope`를 기록합니다. `ask` 정책이면 실제 답변을 `mismatch_authorization`에도 적습니다. 정책은 추론 차이만 허용하며 프롬프트/첨부/기타 설정 차이는 허용하지 않습니다.

### 선택적 Playwright 배치의 설정

`browser/batch.mjs`를 사용하는 경우에만 preflight에 다음을 실제 확인 근거로 입력합니다. 코드가 UI를 대신 검증하지 않습니다.

```js
const preflight = {
  uiVerified: true, conditionsMatch: false,
  sameModelVerified: true, sameInputVerified: true, otherSettingsMatch: true,
  reasoningMismatchPolicy: 'auto_exploratory',
  mismatchNote: '현재 UI에서 확인한 서비스별 추론값과 불일치 이유',
  authorizationScope: '이번 사용자가 승인한 모델·질문·요청 범위',
  maxTotalRequests: 40,
};
```

`browser/batch.mjs`의 `resolveComparison`이 이 조건에서만 참고 비교를 선택합니다. 명시적 확인을 받은 경우 기존 `comparisonMode:'exploratory', userAuthorizedMismatch:true` 경로도 사용 가능합니다. 참고 결과는 비용·품질·시간 그래프와 별도 표시된 요약으로 내며 엄격 비교 평균과 합산하지 않습니다.

## 선택적 Playwright 준비 단계의 클릭 보호

기본 실행은 [공통 브라우저 흐름](BROWSER-FLOW.md)의 관측 → 한 번 조작 → 결과 확인을 따른다. 지원되는 Playwright 도구를 쓰는 경우 `browser/ui-actions.mjs`의 `checkedUI(tab, service, readUrl)`로 준비 단계 클릭을 보호할 수 있다. `readUrl`은 **연결 도구 문서가 제공하는 현재 탭 URL 읽기**에 연결한다. 고정 URL을 반환하거나 지원하지 않는 API를 만들어 쓰지 않는다.

`ui.click(role, exactName, verifyAfter)`는 새 화면과 URL, 정확한 역할/이름, 대상 1개·가시성·활성 상태를 확인하고 딱 한 번 클릭한다. 새 화면으로 `verifyAfter(after, before)`가 `true`를 반환해야 다음 단계로 간다. 검증 실패/타임아웃 후 같은 흐름의 추가 클릭은 막는다. 현재 상태와 전송 여부를 대조해 복구한 후에만 새 흐름을 만든다. 검증 함수는 메뉴가 열림/선택값이 바뀜 등 **현재 UI 근거**를 검사해야 하며 무조건 `true`로 우회하면 안 된다. 비동기 렌더링 때문에 확인에 실패하면 관측만 이어가고 클릭부터 재실행하지 않는다.

`prepareGPTMedium(service, tab, wrapper, {readUrl, verifyReady})`도 이 보호를 사용한다. `verifyReady(snapshot)`는 현재 UI의 선택된 정확한 모델·추론 상태를 검사하는 함수다. 임의로 `[pressed]`나 `[checked]`가 있을 것이라고 가정하지 않는다. 이 두 콜백 없이 실행하면 조작 전에 오류를 반환한다. 메뉴가 달라졌으면 이 과거 한국어 UI 레시피를 강제로 실행하지 말고 공통 흐름으로 현재 화면부터 확인한다.

다른 모델의 기존 `claude-low.mjs`/`gemini-exploratory.mjs`는 과거 UI 참고 레시피이며 자동 보호가 주입된 드라이버가 아니다. 그대로 무관측 일괄 실행하지 않는다. 공통 흐름에 따라 한 단계씩 실행하거나 현재 UI에서 검증한 전후 조건을 `checkedUI`에 연결한다. 이 보조 코드는 유료 전송·업로드·계정 전체 설정·연결 복구를 수행하지 않으며, 해당 단계의 공통 체크리스트를 대체하지 않는다. 지원 API가 다르면 새 드라이버를 만들기보다 기본 도구로 같은 확인 절차를 따른다.

## 선택적 Playwright 시간 측정

사이트에 소요시간 UI가 없어도 측정합니다. 도구가 지원하는 시계를 전송 직전과 완료 확인 직후에 읽습니다. UI 업로드/메뉴 설정은 전송 전에 끝냅니다. 정밀 내부 추론 시간이 아니라 자동화 관측 상한/구간임을 표시합니다.

새 세션의 기본 경로는 `docs/REPRODUCIBLE-RUN.md`의 영속 `timer-start`/`timer-complete`입니다. 브라우저 종류와 무관하게 기존 record에 자동 연결되므로 별도 타이머/기록 프로그램을 만들지 않습니다. 아래 `browser/observe.mjs`는 도구 문서가 해당 API를 지원하는 환경에서만 쓰는 검증된 대체 경로이며 같은 요청에 두 타이머를 혼용하지 않습니다.

```js
const state = await sendOnce({tab, service, prompt, textboxName, persist,
  reservationId: requestId, uiVerified: true});
await observeWindow({tab, state, persist, windowMs: 20000});
// still_observing이면 같은 state로 관측 창만 이어 실행. sendOnce 재호출 금지.
// 완료 후 답변·비용 결과에 시간 필드를 마지막에 병합해 record --event로 저장:
const result = {kind:'result', request_id:requestId, status:'success',
  answer:verifiedAnswer, cost_status:verifiedCostStatus, cost:verifiedCost,
  ...timingResult(state)};
```

- sendOnce는 유료 클릭 전에 예약과 시계 기준을 영속 저장합니다. 완료 신호 확인 **이후**의 시간을 저장합니다. 카멜 표기 관측값에서 보고서의 `first_complete_observed_ms`/`last_generating_observed_ms`로 자동 변환합니다.
- runCase는 한 사이트 전송 직후 관측하고, 아직 생성 중이면 상태를 반환합니다. 같은 case/results/preflight에 `resume:true`로 재개하면 기존 요청의 관측만 이어간 뒤 아직 보내지 않은 사이트로 진행합니다. 완료된 요청은 다시 보내지 않으며 전송 여부 불확실이면 먼저 화면·사용량을 대조합니다. 영속 결과에서 상태를 복원하고 60초 안에 사용자에게 진행 상황을 알립니다.
- 마지막 생성 중 시각을 못 봐도 첫 완료 상한은 유효합니다. `last_generating_observed_ms:null`, `first_complete_observed_ms:N`으로 기록해 `≤N초`로 표시합니다.
- 세션이 재시작되면 저장된 절대 시각을 사용한 관측임을 `timing_method`에 표시합니다. 시계 변경/음수/전송 불확정은 원기록 대조 대상이며 정확한 시간으로 위장하지 않습니다.
- 첫 실제 요청 뒤 `status`의 `timing_missing_do_not_resend`가 비어 있는지 확인합니다. 파일 생성 성공과 측정 성공을 구분합니다. 첫 요청도 계획 횟수에 포함하며 추가 유료 파일럿을 만들지 않습니다.
- 시간이 누락돼도 답변·비용을 버리거나 전체 실행을 막지 않습니다. 원기록이 있으면 근거를 보존해 정정하고, 없으면 `timing_unavailable_reason`을 남깁니다. 시간을 채우려고 유료 요청을 재전송하지 않습니다. **다음 요청의 시계 경로를 고친 뒤 계속**합니다.
- `report` 반환값의 `timing_missing`와 보고서 첫 요약의 누락 건수를 검토합니다. 한 건이라도 누락이면 그 범위를 밝히며 전체 시간 실측 완료라고 하지 않습니다. 전부 누락이면 빈 0~1초 축 대신 측정 미완료 안내가 표시됩니다.

## 완료 점검

[실행 안내의 전달 전 체크리스트](REPRODUCIBLE-RUN.md#4-생성과-완료를-구분한다)를 사용합니다. 형식 테스트 통과를 실제 UI 실측 통과로 바꾸어 말하지 않습니다. 실제 데이터·원본·계정은 Git에 올리지 않습니다.
