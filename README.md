# SWEET STUDIO 인스타그램 자동 게시 파이프라인

경남 인테리어 스튜디오 `@sweet.studio_official` 계정에 인테리어 트렌드/자재/조명 추천 콘텐츠를
Instagram Graph API로 자동 게시하기 위한 저장소입니다.

## 구조

```
content_bank.json     # 게시할 콘텐츠 아이디어 목록(주제, 캡션, 해시태그, used 여부)
images/inbox/          # 다음에 게시할 이미지를 넣어두는 곳 (content_bank.json의 image_file과 이름 일치)
images/posted/          # 게시 완료된 이미지가 자동으로 이동되는 곳
post_log.json          # 게시 성공/실패/스킵 이력
scripts/post_to_instagram.py  # 실제 게시 스크립트
```

## 사용 흐름

1. `content_bank.json`에서 다음에 쓰고 싶은 콘텐츠(예: `lighting-001`)를 정한다.
2. 그 항목의 `image_file` 값과 **같은 파일명**으로 이미지를 `images/inbox/`에 올리고 커밋·푸시한다.
   (Instagram Graph API는 로컬 파일을 못 읽고, 인터넷에서 접근 가능한 URL이 있어야 이미지를 가져갈 수 있어서
   이 퍼블릭 저장소의 `raw.githubusercontent.com` 주소를 이미지 URL로 사용합니다.)
3. `scripts/post_to_instagram.py`가 실행되면 `used=false`이면서 이미지가 준비된 첫 항목을 찾아 자동 게시하고,
   완료 후 `used=true` 처리 + 이미지를 `images/posted/`로 이동 + 로그 기록 후 자동 commit/push합니다.
4. 준비된 이미지가 하나도 없으면 에러 없이 "게시할 콘텐츠 없음"으로 조용히 스킵합니다 (무인 실행 중 죽지 않도록).

## Phase 2 — Meta 개발자 앱 / 액세스 토큰 준비 체크리스트

실제 자동 게시를 시작하려면 아래 절차가 **한 번** 필요합니다 (본인 Meta/Facebook 로그인이 필요해서
Claude가 대신 클릭할 수 없는 구간입니다. 필요하면 화면 공유하듯 같이 진행할 수 있어요).

- [ ] [Meta for Developers](https://developers.facebook.com/apps)에서 새 앱 생성 (유형: "비즈니스")
- [ ] 앱에 **Instagram Graph API** 제품 추가
- [ ] 이미 연동되어 있는 Facebook 페이지 ↔ Instagram 비즈니스 계정(`sweet.studio_official`) 연결 확인
- [ ] Graph API Explorer 또는 앱 설정에서 아래 권한을 포함한 사용자 액세스 토큰 발급
  - `instagram_basic`, `instagram_content_publish`, `pages_read_engagement`, `pages_show_list`
- [ ] 단기 토큰 → **장기(60일) 토큰**으로 교환 (`/oauth/access_token` with `fb_exchange_token`)
- [ ] `GET /me/accounts` 로 페이지 액세스 토큰 확인 → `GET /{page-id}?fields=instagram_business_account`
      로 **IG 비즈니스 계정 ID** 확인
- [ ] 발급받은 값 2개를 기록해두기: `IG_ACCESS_TOKEN`, `IG_BUSINESS_ACCOUNT_ID`

> 장기 토큰도 60일 후 만료됩니다. 만료 전 재발급 절차를 리마인드 받고 싶다면 알려주세요 —
> 별도 예약 루틴으로 만료 임박 알림도 만들 수 있습니다.

## 로컬 테스트

```bash
python scripts/post_to_instagram.py --dry-run
```

실제 API 호출 없이 어떤 콘텐츠가 다음에 게시될지, 캡션이 어떻게 만들어지는지만 확인합니다.

실제 게시 테스트 시에는 아래 환경변수가 필요합니다.

```bash
export IG_ACCESS_TOKEN="..."
export IG_BUSINESS_ACCOUNT_ID="..."
export GITHUB_REPO="sacradeus21-web/interior-ig-automation"
python scripts/post_to_instagram.py
```

## Phase 3 — 클라우드 자동 실행

Meta 토큰 준비가 끝나면 Claude Code의 예약 루틴(RemoteTrigger)으로 이 저장소를 소스로 하는
정기 실행 작업을 만들어 완전 자동화합니다 (기본안: 주 3회, 월/수/금 오전 10시).
토큰은 저장소에 커밋하지 않고 루틴 설정에만 안전하게 보관합니다.
