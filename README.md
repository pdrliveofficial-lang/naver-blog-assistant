# 📷 네이버 블로그 포스팅 어시스턴트 (Claude Code)

사진을 폴더에 넣고 "포스팅해줘"라고 말하면, Claude Code가 글을 쓰고
네이버 블로그 에디터에 자동 입력까지 해주는 반자동 포스팅 도구입니다.

- API 크레딧 결제 없이 **Claude 구독(Pro/Max)만으로** 동작합니다.
- 글 생성은 Claude Code가 직접 하고, 네이버 발행만 Playwright 스크립트가 담당합니다.
- 초안을 채팅으로 검수한 뒤 발행하는 구조라 저품질(무검수 대량발행) 위험을 줄였습니다.

## 준비물

- **macOS 또는 Windows**
- Python 3.9+ (Windows는 [python.org](https://www.python.org/downloads/)에서 설치 — "Add python.exe to PATH" 체크 필수)
- [Claude 데스크탑 앱](https://claude.ai/download) 또는 Claude Code CLI
- 네이버 블로그 계정

> Windows 참고: 아이폰 HEIC 사진 변환·영상 썸네일에 ImageMagick/ffmpeg이 있으면 좋지만,
> 없어도 Claude Code가 상황에 맞게 안내해줍니다. 갤럭시/JPG 사진은 아무 준비 없이 바로 됩니다.

## 최초 세팅 (1회)

1. 이 폴더를 원하는 위치에 복사(또는 git clone)합니다.
2. Claude 데스크탑 앱 → Code 탭에서 이 폴더를 엽니다.
   (또는 터미널에서 `cd 이폴더` 후 `claude` 실행)
3. Claude Code에게 이렇게 말하세요:
   > **"세팅해줘"**

   → 알아서 `pip install`과 `playwright install`을 실행하고,
   `config.yaml`의 블로그 아이디도 물어봐서 채워줍니다.

   수동으로 하려면 — macOS: `bash setup.sh` / Windows: `setup.bat` 더블클릭.
   그리고 `config.yaml`의 `naver_blog_id`에 본인 블로그 아이디를 입력하세요.

4. 첫 발행 시 브라우저가 열리면 **네이버 로그인**을 한 번 해주세요.
   (로그인 세션은 `browser_profile/` 폴더에 저장되어 다음부터는 자동입니다)

## 평소 사용법

1. `inbox/` 폴더에 사진·동영상 넣기
   (정확한 가게명·장소 등은 `inbox/memo.txt`에 한 줄로)
2. Claude Code에게: **"포스팅해줘"**
3. 제목·본문·태그를 보여주면 확인 → **"발행해"** → 브라우저가 열리고 자동 입력
4. 네이버 에디터에서 최종 [발행] 버튼만 직접 클릭
   (`config.yaml`에서 `auto_publish: true`로 바꾸면 발행 클릭까지 자동)

말투 수정, 글 재생성, 셀렉터 오류 대응까지 전부 대화로 해결하면 됩니다.

## 커스터마이징

| 파일 | 용도 |
|---|---|
| `CLAUDE.md` | 워크플로우 + **스타일 가이드** (말투 예시를 본인 글로 교체하세요) |
| `SEO_RULES.md` | 글 작성 시 적용되는 네이버 SEO 규칙 |
| `config.yaml` | 블로그 아이디, 카테고리, 자동발행 여부 등 |

## 부가 기능

- **예약 발행**: `python3 publish.py drafts/<폴더> --schedule "2026-07-16 15:00"`
- **장소(지도) 첨부**: 발행된 글에 네이버 지도 붙이기 — 가게 플레이스의 "블로그 리뷰" 탭에 글이 걸립니다.
  ```bash
  python3 edit_add_places.py <글번호> "가게명:주소키워드"
  ```

## 주의사항

- 하루 1~2편, 검수 후 발행을 권장합니다. 무검수 대량 발행은 저품질(검색 누락) 위험이 있습니다.
- 네이버 에디터 UI가 바뀌면 셀렉터가 어긋날 수 있습니다. 에러 메시지를 Claude Code에게 보여주면 `publisher.py`를 직접 고쳐서 재시도합니다.
- `browser_profile/` 폴더에는 네이버 로그인 세션이 저장됩니다. **절대 다른 사람과 공유하거나 git에 올리지 마세요** (.gitignore에 이미 포함).
