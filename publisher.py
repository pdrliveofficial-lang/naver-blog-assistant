"""네이버 스마트에디터 ONE 반자동 발행 (Playwright) — v2

오픈소스(naver-blog-mcp) 실전 셀렉터 노하우 반영:
- 팝업 취소는 정확한 셀렉터만 사용 (has-text("취소")는 '취소선' 버튼 오클릭 버그)
- 도움말 패널이 발행 버튼을 가리는 문제 → JS 강제 숨김
- 발행 버튼은 data-click-area 속성 기준 (클래스명은 해시가 붙어 수시 변경)
- 발행 성공은 URL 전환(PostView)으로 확인
+ 이미지 자동 업로드, 카테고리 자동 선택은 자체 구현

⚠️ UI 변경으로 어긋나면 config.yaml에서 publish_mode: "clipboard"
"""
import os
import subprocess
import sys
import time
from pathlib import Path

PROFILE_DIR = Path(__file__).parent / "browser_profile"


def _keep_awake():
    """작업 중 PC가 잠자기로 전환되면 업로드/입력이 통째로 멈추므로 방지.
    macOS: caffeinate (-w: 이 파이썬 프로세스가 끝나면 자동 종료)
    Windows: SetThreadExecutionState (프로세스 종료 시 자동 해제)"""
    try:
        if sys.platform == "win32":
            import ctypes
            # ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED
            ctypes.windll.kernel32.SetThreadExecutionState(0x80000003)
        else:
            subprocess.Popen(["caffeinate", "-dims", "-w", str(os.getpid())])
        print("☕ 작업 중 잠자기 방지 활성화 (완료 시 자동 해제)")
    except Exception:
        pass


def publish_auto(post: dict, config: dict, schedule: str = None):
    """에디터 자동 입력 → 발행 패널 세팅 → (auto_publish면) 발행 클릭까지.
    schedule: 'YYYY-MM-DD HH:MM' 형식이면 예약 발행으로 설정 (분은 10분 단위)."""
    from playwright.sync_api import sync_playwright

    blog_id = config["naver_blog_id"]
    category = config.get("category") or None
    _keep_awake()

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            str(PROFILE_DIR),
            headless=False,
            viewport={"width": 1400, "height": 900},
            args=[
                "--disable-blink-features=AutomationControlled",
                # 창 최소화 상태에서도 렌더링/타이머가 죽지 않도록 (숨김 작업 모드)
                "--disable-backgrounding-occluded-windows",
                "--disable-renderer-backgrounding",
                "--disable-background-timer-throttling",
            ],
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        # ── 창 숨기기: 실행 즉시 치워서 화면에 뜨는 일이 없게 한다.
        #    로그인이 필요한 경우에만 잠시 보여준다.
        hide = config.get("hide_browser", True)
        if hide:
            print("🫥 브라우저 창을 화면에서 치워둔 채 진행합니다. (입력 완료 시 자동 복원)")
            _hide_window(ctx, page)

        # ── 로그인 확인 (수동 로그인 방식: 캡차/2FA를 사람이 처리, 세션은 프로필에 저장)
        # 판정은 네이버 인증 쿠키(NID_AUT) 존재 여부로 한다.
        # URL/DOM 기반 판정은 로그인 직후 기기등록 안내 등 nid.naver.com 페이지에
        # 머무는 경우 영원히 '미로그인'으로 오판하는 버그가 있었음.
        page.goto("https://blog.naver.com", wait_until="domcontentloaded")
        time.sleep(2)
        if not _has_auth_cookie(ctx):
            _show_window(ctx, page)  # 로그인은 사용자가 직접 해야 하므로 창을 보여준다
            print("\n🔑 브라우저에서 네이버 로그인을 해주세요. (최초 1회만)")
            print("   로그인이 확인되면 자동으로 다음 단계로 넘어갑니다. (최대 10분 대기)")
            page.goto("https://nid.naver.com/nidlogin.login")
            login_deadline = time.time() + 600
            last_dbg = 0.0
            while time.time() < login_deadline:
                time.sleep(3)
                if _has_auth_cookie(ctx):
                    break
                if time.time() - last_dbg > 30:
                    names = sorted({c.get("name", "") for c in ctx.cookies()
                                    if "naver" in c.get("domain", "")})
                    print(f"   ...로그인 대기 중 (naver 쿠키: {', '.join(names) or '없음'})")
                    last_dbg = time.time()
            else:
                print("⚠️ 10분 내 로그인이 확인되지 않아 종료합니다. 다시 실행해주세요.")
                ctx.close()
                return None
            print("✅ 로그인 확인, 에디터로 이동합니다.")
            time.sleep(1)
            if hide:
                _hide_window(ctx, page)

        # ── 에디터 진입 + 준비 대기
        page.goto(f"https://blog.naver.com/{blog_id}/postwrite",
                  wait_until="domcontentloaded")
        try:
            page.wait_for_selector(".se-section-documentTitle", timeout=30000)
            page.wait_for_selector(".se-placeholder", timeout=30000)
        except Exception:
            print("⚠️ 에디터 로딩이 늦습니다. 5초 더 대기...")
        time.sleep(1)

        _dismiss_popups(page)

        # ── 제목
        try:
            page.locator(".se-section-documentTitle").first.click(timeout=5000)
            time.sleep(0.3)
            page.keyboard.type(post["title"], delay=10)
        except Exception:
            print("⚠️ 제목 입력 실패. 직접 입력:", post["title"])

        # ── 본문 (문단 + 사진 순서대로)
        try:
            page.locator(".se-section-text").first.click(timeout=5000)
            time.sleep(0.3)
        except Exception:
            page.keyboard.press("Enter")

        videos = post.get("videos", [])
        for sec in post["sections"]:
            idx = sec.get("image_index")
            if idx is not None and idx < len(post["images"]):
                _insert_image(page, post["images"][idx])
            vidx = sec.get("video_index")
            if vidx is not None and vidx < len(videos):
                if idx is not None:
                    time.sleep(5)  # 같은 섹션에 사진+동영상이 붙으면 업로드 안정화 대기
                _insert_video(page, videos[vidx])
            # ⚠️ 문단 유실 방지: 직전 삽입이 실패해 팝업이 남아 있으면
            # 이후 키보드 입력이 전부 허공에 날아간다 (실제 사고 사례).
            # 텍스트를 치기 전에 반드시 팝업 잔재를 정리한다.
            try:
                stuck = page.evaluate(
                    "() => [...document.querySelectorAll('.se-popup, .se-popup-dim')]"
                    ".some(el => el.offsetParent !== null)")
                if stuck:
                    print("   (팝업 잔재 감지 — 정리 후 본문 입력 계속)")
                    _close_any_popup(page)
            except Exception:
                pass
            for line in sec["text"].split("\n"):
                if line:
                    page.keyboard.type(line, delay=8)
                page.keyboard.press("Enter")
            page.keyboard.press("Enter")

        # ── 장소(지도) 삽입 — post.json의 places (가게 후기라면 기본 포함)
        if post.get("places"):
            _insert_places(page, post["places"])

        # ── 본문 정렬 적용 (config.yaml의 text_align)
        align = (config.get("text_align") or "").strip()
        if align in ("center", "left", "right", "justify"):
            _apply_alignment(page, align)

        # ── 발행 패널 열기 (도움말이 버튼을 가리는 경우 대비 재차 정리)
        _dismiss_popups(page)
        try:
            page.locator(
                'button[data-click-area="tpb.publish"], button[class*="publish_btn"]'
            ).first.click(timeout=10000)
            time.sleep(1.5)
        except Exception:
            print("⚠️ 발행 패널을 열지 못했습니다. 우측 상단 [발행]을 직접 눌러주세요.")

        # ── 카테고리
        if category:
            try:
                page.locator('button:has-text("카테고리")').first.click(timeout=3000)
                page.locator(f'label:has-text("{category}")').first.click(timeout=3000)
            except Exception:
                print(f"⚠️ 카테고리({category}) 자동 선택 실패 — 직접 선택해주세요.")

        # ── 태그
        try:
            tag_input = page.locator(
                '#tag-input, input[placeholder*="태그"], input[id^="tag"]'
            ).first
            for t in post["tags"]:
                tag_input.fill(t)
                tag_input.press("Enter")
        except Exception:
            print("⚠️ 태그 입력 실패. 직접 입력:", ", ".join(post["tags"]))

        # ── 예약 발행 설정 (요청된 경우)
        schedule_ok = True
        if schedule:
            schedule_ok = _set_schedule(page, schedule)
            if not schedule_ok:
                print("⚠️ 예약 설정 실패 — 자동 발행을 멈추고 창을 띄웁니다. 직접 확인해주세요.")
                _show_window(ctx, page)

        # ── 최종 발행: auto_publish면 직접 클릭, 아니면 창을 띄워 사용자에게 맡긴다
        if config.get("auto_publish") and schedule_ok:
            time.sleep(1)
            try:
                page.locator('[data-testid="seOnePublishBtn"]').first.click(timeout=8000)
                print("🚀 자동 발행 클릭 완료 (auto_publish: true)")
            except Exception as e:
                print(f"⚠️ 자동 발행 클릭 실패({e}) — 창을 띄웁니다. [발행]을 직접 눌러주세요.")
                _show_window(ctx, page)
        else:
            _show_window(ctx, page)
            print("\n" + "=" * 50)
            print("✅ 입력 완료! 발행 패널에서 공개설정 확인 후")
            print("   [발행] 버튼을 직접 눌러주세요.")
            print("=" * 50)

        # ── 발행 감지
        #    즉시 발행: URL이 글 주소(blog.naver.com/{id}/{숫자}) 또는 PostView로 전환
        #    예약 발행: 글 주소가 생기지 않으므로 postwrite 화면을 벗어나면 성공으로 판정
        import re
        deadline = time.time() + (300 if schedule else 900)
        post_url = None
        scheduled_done = False
        while time.time() < deadline:
            u = page.url
            if ("PostView" in u or "postView" in u
                    or re.search(rf"blog\.naver\.com/{re.escape(blog_id)}/\d+", u)):
                post_url = u.split("?")[0]
                break
            if schedule and "postwrite" not in u:
                scheduled_done = True
                break
            time.sleep(1)
        if post_url:
            print(f"🎉 발행 확인: {post_url}")
        elif scheduled_done:
            print(f"🎉 예약 발행 등록 완료: {schedule} 에 자동 게시됩니다.")
        else:
            print("⚠️ 발행 전환이 감지되지 않아 브라우저를 닫습니다. 블로그에서 상태를 확인해주세요.")
        ctx.close()
        return post_url


def _has_auth_cookie(ctx) -> bool:
    """네이버 로그인 세션 쿠키(NID_AUT/NID_SES) 존재 여부로 로그인 상태 판정."""
    try:
        names = {c.get("name") for c in ctx.cookies()}
        return bool(names & {"NID_AUT", "NID_SES"})
    except Exception:
        return False


def _dismiss_popups(page):
    """이어쓰기 팝업/도움말 정리.
    주의: 'button:has-text("취소")'는 툴바의 '취소선' 버튼까지 잡으므로 금지."""
    for sel in ["button.se-popup-button-cancel", ".se-popup-button-cancel"]:
        try:
            btn = page.locator(sel).first
            if btn.is_visible(timeout=1000):
                btn.click(timeout=2000)
                time.sleep(0.3)
                break
        except Exception:
            pass
    for sel in ["button.se-help-panel-close-button",
                '.se-help-panel button[class*="close"]',
                'button[aria-label="닫기"]']:
        try:
            btn = page.locator(sel).first
            if btn.is_visible(timeout=500):
                btn.click(timeout=1500)
        except Exception:
            pass
    # 도움말 패널이 발행 버튼을 덮는 케이스 → JS로 강제 숨김
    try:
        page.evaluate("""() => {
            document.querySelectorAll(
                '.se-help-panel, [class*="se-help-panel"]'
            ).forEach(el => el.style.cssText =
                'display:none!important;pointer-events:none!important');
        }""")
    except Exception:
        pass


def _hide_window(ctx, page):
    """창을 완전히 최소화(Dock행)해서 화면에서 치운다.
    백그라운딩 방지 플래그(--disable-backgrounding-occluded-windows 등)와
    함께 쓰면 최소화 상태에서도 업로드가 정상 동작함을 실측으로 확인."""
    try:
        cdp = ctx.new_cdp_session(page)
        wid = cdp.send("Browser.getWindowForTarget")["windowId"]
        cdp.send("Browser.setWindowBounds",
                 {"windowId": wid, "bounds": {"windowState": "minimized"}})
        cdp.detach()
    except Exception as e:
        print(f"(창 숨기기 실패 — 무시하고 계속: {e})")


def _show_window(ctx, page):
    try:
        cdp = ctx.new_cdp_session(page)
        wid = cdp.send("Browser.getWindowForTarget")["windowId"]
        # 최소화 상태에서는 좌표를 함께 못 바꾸므로 normal 복원 후 위치 지정
        cdp.send("Browser.setWindowBounds",
                 {"windowId": wid, "bounds": {"windowState": "normal"}})
        cdp.send("Browser.setWindowBounds", {"windowId": wid, "bounds": {
            "left": 60, "top": 40, "width": 1450, "height": 950}})
        cdp.detach()
    except Exception as e:
        print(f"(창 복원 실패: {e})")
    try:
        page.bring_to_front()
    except Exception:
        pass


def _apply_alignment(page, align: str):
    """본문 전체 선택 후 정렬 적용. 셀렉터는 2026-07 실측:
    드롭다운 열기 button[data-name="align-drop-down-with-justify"] →
    옵션 버튼 같은 data-name + data-value(left/center/right/justify)."""
    try:
        page.locator(".se-section-text").first.click(timeout=5000)
        time.sleep(0.3)
        page.keyboard.press("ControlOrMeta+a")
        time.sleep(0.5)
        page.locator(
            'button[data-name="align-drop-down-with-justify"]:visible'
        ).first.click(timeout=5000)
        time.sleep(0.5)
        page.locator(
            f'button[data-name="align-drop-down-with-justify"][data-value="{align}"]'
        ).first.click(timeout=5000)
        time.sleep(0.5)
        page.keyboard.press("End")
        print(f"   📐 본문 정렬 적용: {align}")
    except Exception as e:
        print(f"⚠️ 정렬 적용 실패({align}): {e} — 에디터에서 직접 적용해주세요.")
        page.keyboard.press("Escape")


def _add_place_search(page, query: str, addr_keyword: str) -> bool:
    """열려 있는 장소 팝업(.se-popup-placesMap)에서 query 검색 후
    주소에 addr_keyword가 포함된 결과를 '추가'한다."""
    si = page.locator('.se-popup-placesMap input[placeholder*="장소"]').first
    si.click()
    si.fill(query)
    si.press("Enter")
    time.sleep(3)
    items = page.locator("li.se-place-map-search-result-item")
    target = None
    for i in range(items.count()):
        if addr_keyword in items.nth(i).inner_text():
            target = items.nth(i)
            break
    if target is None:
        print(f"⚠️ '{query}' 결과 중 '{addr_keyword}' 포함 항목 없음")
        return False
    target.hover()
    time.sleep(0.5)
    try:
        target.locator("text=추가").first.click(timeout=3000)
    except Exception:
        target.click()
        time.sleep(0.5)
        target.locator("text=추가").first.click(timeout=3000)
    time.sleep(1)
    print(f"   📍 장소 추가됨: {query} ({addr_keyword})")
    return True


def _insert_places(page, places: list):
    """본문 끝에 장소(지도) 모듈 삽입. places: [{'query':..., 'addr':...}]"""
    try:
        page.locator('button[data-name="map"], button[data-log="dot.map"]').first.click(timeout=8000)
        pop = page.locator(".se-popup-placesMap")
        pop.wait_for(state="visible", timeout=10000)
        time.sleep(2)
        added = sum(_add_place_search(page, pl["query"], pl["addr"]) for pl in places)
        if added:
            pop.locator("button.se-popup-button-confirm").first.click(timeout=8000)
            pop.wait_for(state="hidden", timeout=15000)
            time.sleep(2)
            print(f"   🗺 장소 지도 삽입 완료 ({added}곳)")
        else:
            print("⚠️ 추가된 장소 없음 — 지도 없이 진행")
            _close_any_popup(page)
    except Exception as e:
        print(f"⚠️ 장소 삽입 실패: {e}")
        _close_any_popup(page)


def _set_schedule(page, when: str) -> bool:
    """발행 패널에서 예약 발행 설정. when: 'YYYY-MM-DD HH:MM' (분은 10분 단위만 가능).
    셀렉터(2026-07 실측): label '예약' 클릭 → input[class*=input_date](readonly, 클릭 시 달력)
    → select[class*=hour_option](00~23) / select[class*=minute_option](00,10,...,50)"""
    from datetime import datetime
    try:
        dt = datetime.strptime(when, "%Y-%m-%d %H:%M")
        if dt.minute % 10:
            print(f"⚠️ 예약 분은 10분 단위만 가능 — {dt.minute}분을 내림 처리")
            dt = dt.replace(minute=dt.minute // 10 * 10)

        page.locator('label:has-text("예약")').first.click(timeout=5000)
        time.sleep(1)

        di = page.locator('input[class*="input_date"]').first
        want = f"{dt.year}. {dt.month:02d}. {dt.day:02d}"
        if di.input_value().strip() != want:
            di.click(timeout=3000)
            time.sleep(1)
            # 달력에서 해당 '일' 클릭 (현재 표시 월 기준, 작은 셀 요소만 대상)
            page.evaluate("""(day) => {
                const els = [...document.querySelectorAll('button, td, a, span')]
                    .filter(e => e.offsetParent !== null
                            && e.textContent.trim() === String(day)
                            && e.getBoundingClientRect().width < 60
                            && e.getBoundingClientRect().height < 60);
                const el = els[els.length - 1];
                if (el) el.click();
            }""", dt.day)
            time.sleep(1)
            if di.input_value().strip() != want:
                print(f"⚠️ 예약 날짜 불일치: 목표 '{want}' / 현재 '{di.input_value()}'")
                return False

        page.locator('select[class*="hour_option"]').first.select_option(f"{dt.hour:02d}")
        page.locator('select[class*="minute_option"]').first.select_option(f"{dt.minute:02d}")
        time.sleep(0.5)
        print(f"⏰ 예약 발행 설정 완료: {dt.strftime('%Y-%m-%d %H:%M')}")
        return True
    except Exception as e:
        print(f"⚠️ 예약 설정 실패: {e}")
        return False


def _close_any_popup(page):
    """열려 있는 업로드 팝업을 정리. 실패한 팝업이 남아 있으면
    이후 모든 클릭/입력이 가로채여 연쇄 실패하므로 삽입 전후에 반드시 호출."""
    for sel in [".se-popup-video-upload button.nvu_btn_close",
                ".se-popup button[class*='close-button']"]:
        try:
            btn = page.locator(sel).first
            if btn.is_visible(timeout=300):
                btn.click(timeout=1500)
                time.sleep(0.3)
        except Exception:
            pass
    try:
        if page.locator(".se-popup-video-upload").first.is_visible(timeout=300):
            page.keyboard.press("Escape")
            time.sleep(0.3)
    except Exception:
        pass
    # 최후 수단: 팝업과 투명 차단막(se-popup-dim)이 남아 모든 클릭을 가로채는
    # 케이스를 JS로 강제 제거 (5차 시도에서 연쇄 실패 원인이었음)
    try:
        page.evaluate("""() => {
            document.querySelectorAll('.se-popup, .se-popup-dim').forEach(el => {
                if (el.offsetParent !== null || el.classList.contains('se-popup-dim')) {
                    el.style.cssText = 'display:none!important;pointer-events:none!important';
                }
            });
        }""")
    except Exception:
        pass


_IMG_SELECTOR_OK = True  # UI 변경으로 삽입확인 셀렉터가 안 맞으면 고정 대기로 폴백


def _insert_image(page, img_path: str):
    global _IMG_SELECTOR_OK
    name = Path(img_path).name
    try:
        _close_any_popup(page)
        before = page.locator(".se-module-image, .se-section-image").count()
        chooser = None
        for attempt in (1, 2):  # 파일선택창 이벤트를 간헐적으로 놓치는 케이스 재시도
            try:
                with page.expect_file_chooser(timeout=8000) as fc:
                    page.locator(
                        'button[data-name="image"], .se-image-toolbar-button, '
                        'button[title*="사진"]'
                    ).first.click()
                chooser = fc.value
                break
            except Exception:
                if attempt == 2:
                    raise
                time.sleep(2)
        chooser.set_files(img_path)
        # 이미지가 본문에 실제로 추가될 때까지 대기.
        # (업로드 중 로딩 오버레이가 다음 클릭을 가로채 연쇄 실패하던 문제 방지)
        if _IMG_SELECTOR_OK:
            try:
                page.wait_for_function(
                    "n => document.querySelectorAll('.se-module-image, .se-section-image').length > n",
                    arg=before, timeout=30000)
            except Exception:
                _IMG_SELECTOR_OK = False
                print("   (이미지 삽입확인 셀렉터 불일치 — 고정 대기로 전환)")
                time.sleep(5)
        else:
            time.sleep(5)
        time.sleep(1)
        page.keyboard.press("End")
    except Exception as e:
        print(f"⚠️ 사진 자동첨부 실패({name}): {e}")
        _close_any_popup(page)


def _insert_video(page, vid_path: str):
    """동영상 업로드 (셀렉터는 2026-07 실측):
    툴바 button[data-name="video"] → 팝업 .se-popup-video-upload
    → button.nvu_btn_local ("동영상 추가") 클릭 시 파일선택창
    → 업로드 완료(.nvu_btn_select에 "업로드 완료" 텍스트) 대기
    → input.nvu_inp에 제목(필수, 최대 40자) 입력 → button.nvu_btn_submit ("완료").
    주의: 툴바 버튼에도 "동영상 추가" 텍스트가 있으므로 반드시 팝업 범위로 한정할 것.
    파일명(확장자 제외)이 동영상 제목으로 들어간다."""
    name = Path(vid_path).name
    try:
        _close_any_popup(page)
        # 이전 실패 처리에서 display:none 처리된 팝업 노드가 재사용될 수 있으므로 원복
        try:
            page.evaluate("""() => document.querySelectorAll(
                '.se-popup, .se-popup-dim').forEach(el => el.style.cssText = '')""")
        except Exception:
            pass
        # 사진 업로드 직후에는 팝업이 안 열리거나 늦게 열리는 경우가 있어 재시도
        pop = page.locator(".se-popup-video-upload")
        opened = False
        for attempt in (1, 2, 3):
            try:
                page.locator('button[data-name="video"]').first.click(timeout=8000)
                pop.wait_for(state="visible", timeout=20000)
                opened = True
                break
            except Exception:
                _close_any_popup(page)
                time.sleep(3)
        if not opened:
            print(f"⚠️ 동영상 팝업 열기 실패({name}) — 건너뜁니다.")
            return
        time.sleep(0.5)
        # 초기 렌더는 nvu_local, 재렌더 후엔 nvu_btn_local 클래스 (실측: 상태별로 다름)
        btn = pop.locator(
            'button.nvu_btn_append:has-text("동영상 추가"), button.nvu_btn_local'
        ).first
        chooser = None
        try:
            with page.expect_file_chooser(timeout=12000) as fc:
                btn.click(timeout=10000)
            chooser = fc.value
        except Exception:
            # 오버레이가 클릭을 가로채는 경우 강제 클릭으로 재시도
            with page.expect_file_chooser(timeout=8000) as fc2:
                btn.click(timeout=5000, force=True)
            chooser = fc2.value
        chooser.set_files(vid_path)

        # 업로드/인코딩 완료 대기 (파일 크기·회선 상태에 따라 수 분까지)
        deadline = time.time() + 480
        done = False
        while time.time() < deadline:
            time.sleep(3)
            try:
                if "업로드 완료" in pop.locator(".nvu_btn_select").first.inner_text(timeout=2000):
                    done = True
                    break
            except Exception:
                pass
        if not done:
            print(f"⚠️ 업로드 완료 대기 시간 초과({name}) — 팝업을 닫고 넘어갑니다.")
            _close_any_popup(page)
            return

        pop.locator("input.nvu_inp").first.fill(Path(vid_path).stem[:40])
        pop.locator("button.nvu_btn_submit").first.click(timeout=5000)
        pop.wait_for(state="hidden", timeout=30000)
        time.sleep(2)
        page.keyboard.press("End")
        print(f"   🎬 동영상 첨부 완료: {name}")
    except Exception as e:
        print(f"⚠️ 동영상 자동첨부 실패({name}): {e}")
        _close_any_popup(page)


def publish_clipboard(post: dict, config: dict):
    """폴백: 글을 클립보드에 복사하고 에디터만 오픈 (100% 안전)"""
    import pyperclip
    import webbrowser

    body = "\n\n".join(s["text"] for s in post["sections"])
    tags = " ".join(f"#{t}" for t in post["tags"])
    pyperclip.copy(f"{post['title']}\n\n{body}\n\n{tags}")
    print("\n📋 제목+본문+태그가 클립보드에 복사되었습니다. Ctrl+V로 붙여넣으세요.")
    print(f"   사진 위치: {Path(post['images'][0]).parent}")
    if post.get("videos"):
        print(f"   동영상 위치: {Path(post['videos'][0]).parent} ({len(post['videos'])}개, 직접 첨부)")
    webbrowser.open(f"https://blog.naver.com/{config['naver_blog_id']}/postwrite")
