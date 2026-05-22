"""
浏览器数据包捕获引擎（CDP 直连）
- 使用 Chrome DevTools Protocol 直接监听网络事件
- 不拦截任何请求 —— 页面加载零影响
- 完整获取：URL、headers（含 Cookie）、post_data、响应体
"""

import json
import time
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable
from dataclasses import dataclass, field, asdict
from urllib.parse import urlparse

from playwright.sync_api import (
    sync_playwright, Browser, BrowserContext, Page, CDPSession,
)

USER_DATA_DIR = Path(__file__).parent / "browser_data"
STORAGE_STATE_PATH = USER_DATA_DIR / "state.json"


@dataclass
class CapturedPacket:
    id: str = ""
    timestamp: str = ""
    method: str = ""
    url: str = ""
    host: str = ""
    path: str = ""
    request_headers: dict = field(default_factory=dict)
    request_body: str = ""
    response_status: int = 0
    response_headers: dict = field(default_factory=dict)
    response_body: str = ""
    matched_keyword: str = ""

    def to_dict(self):
        return asdict(self)


class CDPCaptureServer:

    def __init__(self, display_num: int = 99, on_packet_captured: Optional[Callable] = None):
        self.display_num = display_num
        self.keyword_filter: str = ""
        self.is_running = False
        self.last_error: str = ""
        self.username: str = ""
        self.password: str = ""
        self._playwright = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._cdp_sessions: dict[str, CDPSession] = {}
        self._thread: Optional[threading.Thread] = None
        self._captured_packets: list[CapturedPacket] = []
        self._pending_requests: dict[str, dict] = {}
        self._on_packet_captured = on_packet_captured
        self._lock = threading.Lock()
        self._req_counter = 0

    def set_keyword(self, keyword: str): self.keyword_filter = keyword.strip()
    def get_captured_packets(self) -> list[dict]:
        with self._lock: return [p.to_dict() for p in self._captured_packets]
    def clear_packets(self):
        with self._lock:
            self._captured_packets.clear()
            self._pending_requests.clear()

    def start_async(self):
        self.is_running = True; self.last_error = ""
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self): self.is_running = False

    def _run(self):
        try: self._run_impl()
        except Exception as e:
            import traceback
            self.last_error = f"{type(e).__name__}: {e}"
            self.is_running = False
            print(f"[CDP] FATAL: {e}"); traceback.print_exc()

    def _run_impl(self):
        import os as _os
        _os.environ["DISPLAY"] = f":{self.display_num}"

        USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
        self._playwright = sync_playwright().start()

        print(f"[CDP] launching browser on display=:{self.display_num} (headless=False)...")
        self._browser = self._playwright.chromium.launch(
            headless=False,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-first-run",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
        )
        print(f"[CDP] browser OK ({self._browser.version})")

        ctx_opts: dict = {"viewport": {"width": 1400, "height": 900}, "ignore_https_errors": True}
        if STORAGE_STATE_PATH.exists():
            try:
                ctx_opts["storage_state"] = str(STORAGE_STATE_PATH)
                print("[CDP] storage_state loaded")
            except Exception: pass

        self._context = self._browser.new_context(**ctx_opts)
        self._context.on("page", self._on_page_created)
        for p in self._context.pages: self._on_page_created(p)

        page = self._context.pages[0] if self._context.pages else self._context.new_page()
        self._on_page_created(page)

        print("[CDP] navigating...")
        try:
            page.goto("https://antaios-op.100credit.com", timeout=30000, wait_until="commit")
            print("[CDP] navigation OK")
        except Exception as e:
            print(f"[CDP] nav warning: {e}")
            self.last_error = f"nav: {e}"

        # 自动登录（如果提供了账号密码）
        if self.username and self.password:
            try:
                self._auto_login(page)
            except Exception as e:
                print(f"[CDP] auto-login error: {e}")

        print(f"[CDP] ready, keyword='{self.keyword_filter}'")
        while self.is_running:
            # 关键：必须用 Playwright 的 wait_for_timeout 而不是 time.sleep
            # time.sleep 不会泵送 CDP 事件，导致回调永远不会被调用
            try:
                if self._context.pages:
                    self._context.pages[0].wait_for_timeout(500)
                else:
                    time.sleep(0.5)
            except Exception:
                time.sleep(0.5)
        self._cleanup()

    def _auto_login(self, page: Page):
        """自动填写登录表单并点击登录"""
        import time as _t
        print("[CDP] attempting auto-login...")
        _t.sleep(4)  # 等页面完全加载

        current_url = page.url
        print(f"[CDP] current URL: {current_url}")

        # 选择器（多套兜底）
        user_sel = 'input[placeholder*="用户名"], input[type="text"][placeholder*="账号"]'
        pwd_sel = 'input[type="password"]'
        captcha_sel = 'input[placeholder*="验证码"], input[type="text"][placeholder*="验证"]'
        login_btn_sel = 'button:has-text("登录"):not(:has-text("注册")), button[type="submit"], .submit-btn, .login-btn'

        # 等待用户名输入框可见（最多 15 秒）
        try:
            page.wait_for_selector(user_sel, state="visible", timeout=15000)
            print("[CDP] login form detected")
        except Exception:
            print("[CDP] no login form found (already logged in?)")
            return

        # 截图留存（调试用）
        try:
            page.screenshot(path="/tmp/login_before.png")
            print("[CDP] screenshot saved: /tmp/login_before.png")
        except Exception:
            pass

        # 填写用户名
        try:
            inp = page.locator(user_sel).first
            inp.click(); _t.sleep(0.3)
            inp.fill(self.username)
            _t.sleep(0.2)
            print(f"[CDP] username filled: {self.username[:3]}***")
            # 验证填写成功
            val = inp.input_value()
            print(f"[CDP]   verify username value: '{val[:3]}***'")
        except Exception as e:
            print(f"[CDP] username fill error: {e}")

        # 填写密码
        try:
            inp = page.locator(pwd_sel).first
            inp.click(); _t.sleep(0.3)
            inp.fill(self.password)
            _t.sleep(0.2)
            print("[CDP] password filled")
            print(f"[CDP]   verify password length: {len(inp.input_value())}")
        except Exception as e:
            print(f"[CDP] password fill error: {e}")

        # 填写验证码
        try:
            inp = page.locator(captcha_sel).first
            if inp.is_visible():
                inp.click(); _t.sleep(0.3)
                inp.fill('1111')
                _t.sleep(0.2)
                val = inp.input_value()
                print(f"[CDP] captcha filled, verify value: '{val}'")
            else:
                print("[CDP] captcha input not visible, skipping")
        except Exception as e:
            print(f"[CDP] captcha fill error: {e}")

        # 截图验证码填写后
        try:
            page.screenshot(path="/tmp/login_after_fill.png")
            print("[CDP] screenshot saved: /tmp/login_after_fill.png")
        except Exception:
            pass

        # 点击登录按钮
        try:
            btn = page.locator(login_btn_sel).first
            if btn.is_visible():
                print("[CDP] clicking login button...")
                btn.click()
                _t.sleep(1)
                # 等待页面跳转（最多 15 秒）
                try:
                    page.wait_for_load_state("networkidle", timeout=15000)
                except Exception:
                    pass
                _t.sleep(2)
                print(f"[CDP] after login URL: {page.url}")
                # 截图登录后
                try:
                    page.screenshot(path="/tmp/login_after.png")
                    print("[CDP] screenshot saved: /tmp/login_after.png")
                except Exception:
                    pass
            else:
                # 备用：按回车提交
                print("[CDP] button not visible, pressing Enter...")
                page.keyboard.press("Enter")
                _t.sleep(3)
                print(f"[CDP] after Enter URL: {page.url}")
        except Exception as e:
            print(f"[CDP] login click error: {e}")
            # 最后尝试按回车
            try:
                page.keyboard.press("Enter")
                _t.sleep(3)
                print(f"[CDP] after Enter URL: {page.url}")
            except Exception:
                pass

    def _on_page_created(self, page: Page):
        """为每个页面创建 CDP 会话（去重）"""
        page_id = str(id(page))
        if page_id in self._cdp_sessions:
            return  # 已有 CDP 会话

        try:
            cdp = page.context.new_cdp_session(page)
            self._cdp_sessions[page_id] = cdp

            cdp.send("Network.enable", {
                "maxTotalBufferSize": 10000000,
                "maxResourceBufferSize": 5000000,
            })
            cdp.on("Network.requestWillBeSent", lambda params, p=page: self._on_cdp_request(p, params))
            cdp.on("Network.responseReceived", lambda params, p=page: self._on_cdp_response(p, params))
            print(f"[CDP] CDP session created")
        except Exception as e:
            print(f"[CDP] CDP session error: {e}")

    def _on_cdp_request(self, page: Page, params: dict):
        """CDP Network.requestWillBeSent —— 完整请求数据"""
        try:
            request = params.get("request", {})
            url = request.get("url", "")
            kw = self.keyword_filter

            # 调试：打印前 10 个 CDP 事件确认事件流正常
            if not hasattr(self, '_debug_event_count'):
                self._debug_event_count = 0
            if self._debug_event_count < 10:
                self._debug_event_count += 1
                print(f"[CDP] DEBUG #{self._debug_event_count}: {request.get('method','')} {url[:120]}")

            if not kw or kw.lower() not in url.lower():
                return

            self._req_counter += 1
            method = request.get("method", "")
            headers = {k.lower(): v for k, v in request.get("headers", {}).items()}
            post_data = request.get("postData", "")

            # 额外的 Cookie 兜底
            if "cookie" not in headers:
                try:
                    cookies = self._context.cookies(url)
                    cs = '; '.join(f"{c['name']}={c['value']}" for c in cookies)
                    if cs: headers["cookie"] = cs
                except Exception: pass

            request_id = params.get("requestId", "")

            print(f"[CDP] #{self._req_counter} {method} {url[:150]}")
            print(f"[CDP]   post_data: {'YES ('+str(len(post_data))+' chars)' if post_data else 'EMPTY'}")
            print(f"[CDP]   cookie: {'YES ('+str(len(headers.get('cookie','')))+' chars)' if headers.get('cookie') else 'NO'}")
            if post_data: print(f"[CDP]   body: {post_data[:200]}")

            with self._lock:
                self._pending_requests[request_id] = {
                    "method": method, "url": url,
                    "headers": headers, "post_data": post_data,
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
                }
        except Exception as e:
            print(f"[CDP] request handler error: {e}")

    def _on_cdp_response(self, page: Page, params: dict):
        """CDP Network.responseReceived —— 响应元数据"""
        try:
            request_id = params.get("requestId", "")
            with self._lock:
                info = self._pending_requests.pop(request_id, None)

            if info is None:
                return  # 不是我们关心的请求

            response = params.get("response", {})
            url = response.get("url", info["url"])
            status = response.get("status", 0)
            resp_headers = {k.lower(): v for k, v in response.get("headers", {}).items()}

            parsed = urlparse(url)

            # 获取响应体 —— key 必须与存储时一致 (str(id(page)))
            resp_body = ""
            try:
                cdp = self._cdp_sessions.get(str(id(page)))
                if cdp:
                    result = cdp.send("Network.getResponseBody", {"requestId": request_id})
                    resp_body = result.get("body", "")
                    if not resp_body:
                        # 可能 base64 编码
                        base64_body = result.get("base64Encoded", False)
                        if base64_body:
                            import base64
                            resp_body = base64.b64decode(resp_body).decode("utf-8", errors="replace")
            except Exception:
                pass  # 响应体可能还不可用

            pkt = CapturedPacket(
                id=f"pkt_{int(time.time() * 1000)}",
                timestamp=info["timestamp"], method=info["method"],
                url=url, host=parsed.hostname or "", path=parsed.path or "/",
                request_headers=info["headers"], request_body=info["post_data"],
                response_status=status, response_headers=resp_headers,
                response_body=resp_body[:50000],
                matched_keyword=self.keyword_filter,
            )

            with self._lock:
                self._captured_packets.append(pkt)
            if self._on_packet_captured:
                self._on_packet_captured(pkt.to_dict())

            print(f"[CDP] CAPTURED {info['method']} {url[:120]} -> {status}"
                  f" | post_data={'YES' if info['post_data'] else 'NO'}"
                  f" | cookie={'YES' if info['headers'].get('cookie') else 'NO'}"
                  f" | resp_body={len(resp_body)} chars")
        except Exception as e:
            print(f"[CDP] response handler error: {e}")

    def _cleanup(self):
        print("[CDP] cleaning up...")
        if self._context:
            try:
                USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
                self._context.storage_state(path=str(STORAGE_STATE_PATH))
                print("[CDP] storage_state saved")
            except Exception as e: print(f"[CDP] save state: {e}")
            try: self._context.close()
            except Exception: pass
        if self._browser:
            try: self._browser.close()
            except Exception: pass
        if self._playwright:
            try: self._playwright.stop()
            except Exception: pass
        print("[CDP] closed")
