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

## 사용 흐름 (캐러셀 형식)

게시물은 사진 1장이 아니라 **캐러셀(여러 장 슬라이드)** 로 올라간다. 캡션 톤도 캐주얼+정보성
("오늘의 p!ck ✷" 스타일 후킹 문구 + 번호 매긴 짧은 팁)으로 통일했다.

1. `content_bank.json`에서 다음에 쓰고 싶은 콘텐츠(예: `lighting-001`)를 정한다. 각 항목의
   `image_files` 배열에 필요한 이미지 장수(보통 2~4장)와 파일명이 정해져 있다.
2. 그 배열에 적힌 파일명과 **똑같은 이름**으로 이미지를 `images/inbox/`에 전부 올리고 커밋·푸시한다.
   일부만 올리면 스크립트가 해당 항목을 건너뛴다(캐러셀은 이미지가 다 모여야 게시 가능).
   (Instagram Graph API는 로컬 파일을 못 읽고, 인터넷에서 접근 가능한 URL이 있어야 이미지를 가져갈 수 있어서
   이 퍼블릭 저장소의 `raw.githubusercontent.com` 주소를 이미지 URL로 사용합니다.)
3. `scripts/post_to_instagram.py`가 실행되면 `used=false`이면서 `image_files`가 전부 준비된 첫 항목을
   찾아 캐러셀 자식 컨테이너를 하나씩 만들고(각각 처리 완료 대기) → 부모 캐러셀 컨테이너 생성 → 발행한다.
   완료 후 `used=true` 처리 + 이미지 전부를 `images/posted/`로 이동 + 로그 기록 후 자동 commit/push합니다.
4. 캐러셀용 이미지 세트가 다 갖춰진 항목이 하나도 없으면 에러 없이 "게시할 콘텐츠 없음"으로 조용히
   스킵합니다 (무인 실행 중 죽지 않도록).

## Phase 2 — Meta 개발자 앱 / 액세스 토큰 준비 (완료됨, 2026-08-11)

`sweet.studio_official`에는 연결된 Facebook 페이지가 없어서, 표준 "Facebook 로그인" 방식(Graph API Explorer의
페이지 액세스 토큰) 대신 **"Instagram 로그인이 포함된 API" (Business Login for Instagram)** 방식을 사용했다.
실제로 밟은 절차:

- [x] [Meta for Developers](https://developers.facebook.com/apps)에서 "SweetStudio Content Publisher" 앱 생성
- [x] 이용 사례에 **Instagram API** 추가 (Instagram 로그인 포함된 API 설정 탭)
- [x] 앱 역할 → **Instagram 테스터**로 `sweet.studio_official` 추가 → 계정 소유자가 Instagram 웹
      (설정 → 앱 및 웹사이트 → 테스터 초대)에서 수락
- [x] 권한 및 기능 페이지에서 `instagram_content_publish` 권한 추가 ("테스트 준비 완료" 상태 확인)
- [x] Instagram API 설정 페이지 2단계 "액세스 토큰 생성" → 계정 행의 "토큰 생성" 클릭 → 팝업에서 로그인 및
      권한 승인 → 표시된 토큰을 복사 (이 팝업은 자동으로 닫히므로, 닫히기 전에 값을 복사해야 함)
- [x] 토큰 유효성 확인: `GET https://graph.instagram.com/v21.0/me?fields=id,username,account_type`
      → `sweet.studio_official`, BUSINESS 계정, ID `27597615366577081` 확인됨

**중요:** 이 방식으로 발급된 토큰은 **이미 60일짜리 장기 토큰**이라 별도의
`fb_exchange_token`/`ig_exchange_token` 교환이 필요 없다 (오히려 교환을 시도하면
"Session key invalid" 에러가 난다 — 옛 Instagram Basic Display API용 엔드포인트라서 이 토큰 타입과 호환되지 않음).
API 호출은 반드시 `graph.instagram.com`을 사용해야 하며(`graph.facebook.com` 아님), 확보한 값은:

- `IG_ACCESS_TOKEN` = Instagram 로그인 방식으로 발급받은 토큰
- `IG_BUSINESS_ACCOUNT_ID` = `27597615366577081`

> 60일 후 토큰이 만료되면 Meta 개발자 콘솔의 같은 "토큰 생성" 버튼을 다시 눌러 재발급해야 한다.
> 만료 임박 알림이 필요하면 별도 예약 루틴으로 만들 수 있다.

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
