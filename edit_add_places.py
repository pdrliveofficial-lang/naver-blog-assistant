"""기존 발행글에 장소(네이버 지도) 첨부를 추가하고 수정 발행까지 완료.
사용법: python3 edit_add_places.py <글번호> "장소검색어:주소키워드" ...
예:     python3 edit_add_places.py 224347185173 "북창면옥:종로구" "창창:종로구"
"""
import re
import sys
import time
from pathlib import Path

import yaml
from playwright.sync_api import sync_playwright

BASE = Path(__file__).parent
sys.path.insert(0, str(BASE))
from publisher import (_dismiss_popups, _hide_window, _show_window,  # noqa: E402
                       _keep_awake)

_config = yaml.safe_load((BASE / "config.yaml").read_text(encoding="utf-8"))
BLOG_ID = _config.get("naver_blog_id")
if not BLOG_ID:
    sys.exit("config.yaml에 naver_blog_id를 먼저 입력해주세요.")


def add_place(page, query, addr_keyword):
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
        print(f"⚠️ '{query}' 결과 중 '{addr_keyword}' 포함 항목 없음:")
        for i in range(min(items.count(), 5)):
            print("   -", items.nth(i).inner_text()[:70].replace("\n", " "))
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


def main():
    post_no = sys.argv[1]
    places = [a.split(":", 1) for a in sys.argv[2:]]
    _keep_awake()

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            str(BASE / "browser_profile"), headless=False,
            viewport={"width": 1400, "height": 900},
            args=["--disable-blink-features=AutomationControlled",
                  "--disable-backgrounding-occluded-windows",
                  "--disable-renderer-backgrounding",
                  "--disable-background-timer-throttling"],
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        _hide_window(ctx, page)
        print("🫥 창 숨김 상태로 수정 작업 시작")

        page.goto(f"https://blog.naver.com/{BLOG_ID}/postwrite?logNo={post_no}",
                  wait_until="domcontentloaded")
        page.wait_for_selector(".se-section-documentTitle", timeout=30000)
        time.sleep(3)
        _dismiss_popups(page)
        print("문서:", page.locator(".se-section-documentTitle").first.inner_text()[:50].strip())

        # 커서를 문서 맨 끝으로
        page.locator(".se-section-text").last.click(timeout=8000)
        page.keyboard.press("Meta+ArrowDown")
        time.sleep(0.5)

        # 장소 팝업 열고 전부 추가
        page.locator('button[data-name="map"], button[data-log="dot.map"]').first.click(timeout=8000)
        pop = page.locator(".se-popup-placesMap")
        pop.wait_for(state="visible", timeout=10000)
        time.sleep(2)

        added = sum(add_place(page, q, kw) for q, kw in places)
        if added == 0:
            print("⚠️ 추가된 장소가 없어 중단합니다 (글 변경 없음).")
            ctx.close()
            return

        pop.locator("button.se-popup-button-confirm").first.click(timeout=8000)
        pop.wait_for(state="hidden", timeout=15000)
        time.sleep(2)
        n_map = page.locator('[class*="se-module-map"], [class*="se-section-placesMap"]').count()
        print(f"지도 모듈 확인: {n_map}개 / 장소 {added}곳 추가")

        # ── 발행 (수정 확정)
        _dismiss_popups(page)
        page.locator(
            'button[data-click-area="tpb.publish"], button[class*="publish_btn"]'
        ).first.click(timeout=10000)
        time.sleep(2)

        published = False
        for sel in ['[data-testid="seOnePublishBtn"]',
                    'div[class*="layer"] button:has-text("발행")',
                    'button[class*="confirm_btn"]:has-text("발행")']:
            try:
                btn = page.locator(sel).first
                if btn.is_visible(timeout=2000):
                    btn.click(timeout=3000)
                    published = True
                    print(f"발행 버튼 클릭: {sel}")
                    break
            except Exception:
                continue
        if not published:
            vis = page.evaluate("""() => [...document.querySelectorAll('button')]
                .filter(b => b.offsetParent && (b.textContent||'').includes('발행'))
                .map(b => ({cls:(b.className||'').slice(0,60),
                            t:(b.textContent||'').trim().slice(0,10),
                            testid: b.dataset.testid||null}))""")
            print("⚠️ 발행 확정 버튼을 못 찾음. 후보:", vis)
            _show_window(ctx, page)
            print("창을 띄웠습니다. [발행]을 직접 눌러주세요. (3분 대기)")

        deadline = time.time() + 180
        while time.time() < deadline:
            if re.search(rf"blog\.naver\.com/{BLOG_ID}/\d+", page.url) \
                    and "postwrite" not in page.url:
                print(f"🎉 수정 발행 완료: {page.url.split('?')[0]}")
                break
            time.sleep(1)
        else:
            print("⚠️ 발행 전환이 감지되지 않았습니다. 현재 URL:", page.url)
        ctx.close()


if __name__ == "__main__":
    main()
