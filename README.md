# SWEET STUDIO 인스타그램 자동 게시 파이프라인

경남 인테리어 스튜디오 `@sweet.studio_official` 계정에 인테리어 트렌드/자재/조명 추천 콘텐츠를
Instagram Graph API로 자동 게시하기 위한 저장소입니다.

## 구조

```
content_bank.json     # 게시할 콘텐츠 아이디어 목록(주제, 캡션, 해시태그, used 여부, media_kind)
images/inbox/          # 캐러셀용 이미지를 넣어두는 곳 (content_bank.json의 image_files와 이름 일치)
images/posted/          # 게시 완료된 이미지가 자동으로 이동되는 곳
videos/inbox/           # 릴스용 영상 (없으면 muapi로 자동 생성됨)
videos/posted/          # 게시 완료된 영상이 자동으로 이동되는 곳
post_log.json          # 게시 성공/실패/스킵 이력
scripts/post_to_instagram.py  # 실제 게시 스크립트 (캐러셀 + 릴스)
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

## 릴스(AI 영상) 흐름 — 완전 자동

`content_bank.json`에서 `media_kind: "reel"`인 항목은 캐러셀과 달리 **사람이 이미지를 준비할 필요가
없다**. `video_file`이 `videos/inbox/`에 이미 있으면 그걸 쓰고, 없으면 `video_prompt`를 그대로
[muapi CLI](https://muapi.ai)에 넘겨 그 자리에서 영상을 생성한 뒤(기본 모델 `kling-master`, 5초,
9:16), 저장소에 커밋·푸시하고 릴스로 발행한다 — 프롬프트만 있으면 생성부터 게시까지 무인으로 끝난다.

사전 준비(1회):
```bash
npm install -g muapi-cli
muapi auth configure --api-key "<muapi.ai에서 발급받은 키>"
```
(muapi.ai는 크레딧 기반 유료 서비스다. 계정 충전은 https://muapi.ai/topup 에서 직접 해야 한다.)

**주의:** `muapi --help`, `--dry-run` 등 rich 콘솔 출력을 쓰는 일부 명령은 한국어 Windows(cp949) 환경에서
`UnicodeEncodeError`로 깨진다 — CLI 자체의 알려진 인코딩 버그. 실제 생성 명령(`muapi video generate ...`)과
에러 메시지 출력은 문제없이 동작하므로 자동화에는 영향 없다. 플래그를 확인해야 하면 결과를 output 파일로
리다이렉트하거나 다른 환경(비-한국어 로케일)에서 `--help`를 실행해서 참고하면 된다.

Instagram 릴스 탭에 실제로 노출되려면 5~90초·9:16 비율이어야 하므로(API 자체는 300MB/15분까지 받아주지만
그 이상은 그냥 "영상 게시물"로만 처리됨), 기본 설정(5초 9:16)을 벗어나지 않는 게 좋다. `is_ai_generated:
true`를 함께 보내 AI 생성 영상임을 인스타그램에 투명하게 알린다.

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

릴스 항목을 새로 생성해야 하는 경우 muapi 인증(`muapi auth configure --api-key ...`)이 로컬에 이미
설정돼 있어야 한다 (CLI가 OS 키체인에 저장하므로 `MUAPI_API_KEY` 환경변수 자체는 스크립트에서 직접
쓰진 않지만, 클라우드 루틴처럼 매번 새 환경일 땐 실행 전에 `muapi auth configure`를 먼저 호출해야 한다).

## Phase 3 — 클라우드 자동 실행

Meta 토큰 준비가 끝나면 Claude Code의 예약 루틴(RemoteTrigger)으로 이 저장소를 소스로 하는
정기 실행 작업을 만들어 완전 자동화합니다 (기본안: 주 3회, 월/수/금 오전 10시).
토큰은 저장소에 커밋하지 않고 루틴 설정에만 안전하게 보관합니다.
