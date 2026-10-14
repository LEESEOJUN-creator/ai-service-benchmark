# 테스트 자료 등록

현재 등록된 파일은 없습니다. 이미지·PDF 테스트는 자료 검토와 정답 작성 전까지 비활성화 상태입니다.

사용자의 파일 중 공개 자료 또는 비개인 업무 자료를 선정합니다. 민감정보·기밀·개인 사진·개인 의료/금융/학생 기록은 제외합니다. 이전 대화에 붙인 의료·생활기록부 예시는 테스트 영역의 참고이며 실제 개인 자료 업로드 허가는 아닙니다.

후보는 프로젝트의 `fixtures/local/`에 복사해 사용하고 원본은 수정하지 않습니다. 복사와 선정은 추후 자료 확인 단계에서 합니다. 실제 파일과 경로를 담은 manifest는 `local/`에 두고 로컬 설정에서 참조하는 방식도 가능합니다.

각 항목의 필수 필드:

```json
{
  "id": "public-table-image",
  "path": "fixtures/local/selected-table.png",
  "sha256": "실제 파일 SHA256",
  "classification": "public",
  "review_status": "approved",
  "review_note": "출처와 내용 검토 근거: 개인/기밀 정보 없음",
  "allowed_services": ["monogpt", "timely", "works-ai"]
}
```

`classification`은 `public` 또는 `nonpersonal_work`만 허용합니다. 라벨 자체가 안전을 보장하지 않으므로 내용과 출처를 실제 검토해야 합니다. 신규 서비스 추가 시 그 서비스에 대한 업로드 범위도 재확인합니다. 파일 해시가 바뀌면 다시 검토합니다.
