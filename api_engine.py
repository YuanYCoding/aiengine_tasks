"""
安泰OS AI引擎 - 对话API客户端
流程：初始化对话 → 发送消息 → SSE接收回复
"""

import json
import uuid
import requests
from typing import Optional


class AIApiClient:
    """AI引擎API客户端，封装完整的对话流程"""

    def __init__(
        self,
        base_url: str = "https://antaios-op.100credit.com",
        session_id: str = "",
        voigpt_client_id: str = "",
        cookie_string: str = "",
    ):
        self.base_url = base_url.rstrip("/")
        self.session_id = session_id
        self.voigpt_client_id = voigpt_client_id

        self._common_headers = {
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6,ja;q=0.5,zh-TW;q=0.4",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Pragma": "no-cache",
            "Referer": f"{self.base_url}/",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/148.0.0.0 Safari/537.36 Edg/148.0.0.0"
            ),
            "sec-ch-ua": '"Chromium";v="148", "Microsoft Edge";v="148", "Not/A)Brand";v="99"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "Cookie": cookie_string,
        }

    def update_config(
        self,
        base_url: Optional[str] = None,
        session_id: Optional[str] = None,
        voigpt_client_id: Optional[str] = None,
        cookie_string: Optional[str] = None,
    ):
        """动态更新配置"""
        if base_url:
            self.base_url = base_url.rstrip("/")
        if session_id:
            self.session_id = session_id
        if voigpt_client_id:
            self.voigpt_client_id = voigpt_client_id
        if cookie_string:
            self._common_headers["Cookie"] = cookie_string
            self._common_headers["Referer"] = f"{self.base_url}/"

    def create_dialog(self, process_id: str, variable_node: str = "{}") -> tuple:
        """A接口：POST processId + variableNode → dialogId + 开场白"""
        url = f"{self.base_url}/api/antaios-app-op/train/trainRobotText"
        headers = dict(self._common_headers)
        headers.update({
            "Accept": "application/json, text/plain, */*",
            "AiLanguage": "zh_CN",
            "Content-Type": "application/x-www-form-urlencoded",
            "Origin": self.base_url,
            "sessionId": self.session_id,
            "voigpt-client-id": self.voigpt_client_id,
        })
        payload = {"processId": process_id, "variableNode": variable_node}

        print(f"[API] create_dialog url={url}")
        print(f"[API]   sessionId={self.session_id[:20] if self.session_id else 'EMPTY'}...")
        print(f"[API]   cookie={self._common_headers.get('Cookie','')[:60]}...")

        resp = requests.post(url, headers=headers, data=payload, timeout=30)
        resp.raise_for_status()
        result = resp.json()
        print(f"[API]   response code={result.get('code')}")

        if result.get("code") != "000000":
            raise ValueError(f"初始化对话失败：{result.get('code')} - {result.get('message')}")

        data_str = result.get("data", "{}")
        data = json.loads(data_str) if isinstance(data_str, str) else data_str

        dialog_id = data.get("dialogId")
        if not dialog_id:
            raise ValueError(f"初始化响应中未找到 dialogId，data 内容：{data}")

        opening_msg = data.get("answerMsg", "")
        return dialog_id, opening_msg

    def send_message(self, text: str, dialog_id: str, process_id: str) -> dict:
        """B接口：POST processId + text + dialogId → 响应含 answerMsg/cmd"""
        url = f"{self.base_url}/api/antaios-app-op/train/trainRobotText"
        headers = dict(self._common_headers)  # 拷贝避免线程问题
        headers.update({
            "Accept": "application/json, text/plain, */*",
            "AiLanguage": "zh_CN",
            "Content-Type": "application/x-www-form-urlencoded",
            "Origin": self.base_url,
            "sessionId": self.session_id,
            "voigpt-client-id": self.voigpt_client_id,
        })
        payload = {"processId": process_id, "text": text, "dialogId": dialog_id}

        print(f"[API] send_message url={url}")
        print(f"[API]   payload: processId={process_id}, text={text[:30]}, dialogId={dialog_id}")
        print(f"[API]   sessionId={self.session_id[:20] if self.session_id else 'EMPTY'}...")

        resp = requests.post(url, headers=headers, data=payload, timeout=30)
        resp.raise_for_status()
        print(f"[API]   response status={resp.status_code}")

        try:
            result = resp.json()
            data_str = result.get("data", "{}")
            result["_data"] = json.loads(data_str) if isinstance(data_str, str) else (data_str or {})
            inner = result["_data"]
            intention = inner.get("intention", "")
            result["_intention"] = intention
            print(f"[API]   code={result.get('code')}, cmd={inner.get('cmd')}, intention={intention}, answerMsg_len={len(inner.get('answerMsg','') or '')}")
            return result
        except Exception as e:
            print(f"[API]   parse error: {e}, raw={resp.text[:300]}")
            return {"raw": resp.text}

    def receive_sse(self, dialog_id: str, on_chunk=None) -> str:
        """C接口：GET SSE 流式接收"""
        url = f"{self.base_url}/api/antaios-app-op/sse/createConn"
        headers = dict(self._common_headers)
        headers.update({"accept": "text/event-stream", "sessionId": self.session_id})
        params = {"dialogId": dialog_id, "sessionId": self.session_id}

        print(f"[API] receive_sse url={url}")
        print(f"[API]   dialogId={dialog_id}, sessionId={self.session_id[:20] if self.session_id else 'EMPTY'}...")

        full_reply = []
        with requests.get(url, headers=headers, params=params, stream=True, timeout=120) as resp:
            resp.raise_for_status()
            resp.encoding = "utf-8"
            print(f"[API]   SSE connected, reading stream...")
            line_count = 0
            for raw_line in resp.iter_lines(decode_unicode=True):
                line_count += 1
                if not raw_line: continue
                if not raw_line.startswith("data:"): continue
                data_str = raw_line[5:].strip()
                if not data_str: continue
                try:
                    event = json.loads(data_str)
                except json.JSONDecodeError:
                    continue
                event_type = event.get("type")
                if event_type == 1: continue
                if event_type == 3:
                    print(f"[API]   SSE end signal (type=3) after {line_count} lines")
                    break
                message = event.get("message", "")
                if message:
                    full_reply.append(message)
                    if on_chunk: on_chunk(message)
        print(f"[API]   SSE complete: {len(''.join(full_reply))} chars, {line_count} lines")
        return "".join(full_reply)

    def single_round(self, text: str, dialog_id: str, process_id: str, on_sse_chunk=None) -> dict:
        """单轮对话：B接口 POST → 判断 answerMsg → C接口 SSE"""
        import time as _time
        result = self.send_message(text, dialog_id, process_id)
        data = result.get("_data", {})
        answer_msg = data.get("answerMsg", "") or ""
        cmd = str(data.get("cmd", ""))
        intention = result.get("_intention", "")

        print(f"[API] single_round: cmd={cmd}, answerMsg={'PRESENT' if answer_msg else 'EMPTY'}")

        if answer_msg:
            print(f"[API]   → direct reply ({len(answer_msg)} chars)")
            ai_reply = answer_msg
        else:
            print(f"[API]   → using SSE (cmd={cmd}, answerMsg_empty={not answer_msg})")
            # 短暂延迟让服务端准备好 SSE 流
            _time.sleep(0.6)
            ai_reply = self.receive_sse(dialog_id, on_chunk=on_sse_chunk)
            # 如果第一次 SSE 返回空，重试一次
            if not ai_reply:
                print(f"[API]   SSE returned empty, retrying after 1s...")
                _time.sleep(1.0)
                ai_reply = self.receive_sse(dialog_id, on_chunk=on_sse_chunk)
                print(f"[API]   SSE retry: {'GOT ' + str(len(ai_reply)) + ' chars' if ai_reply else 'STILL EMPTY'}")

        return {"user": text, "ai": ai_reply, "cmd": cmd, "dialog_id": dialog_id, "intention": intention}

    def debug_sse(self, text: str, process_id: str) -> list:
        """调试：发送消息后打印原始SSE数据"""
        dialog_id = str(uuid.uuid4())
        self.send_message(text, dialog_id, process_id)

        url = f"{self.base_url}/api/antaios-app-op/sse/createConn"
        headers = {**self._common_headers, "accept": "text/event-stream", "sessionId": self.session_id}
        params = {"dialogId": dialog_id, "sessionId": self.session_id}

        lines = []
        with requests.get(url, headers=headers, params=params, stream=True, timeout=60) as resp:
            resp.encoding = "utf-8"
            for i, line in enumerate(resp.iter_lines(decode_unicode=True)):
                lines.append({"index": i, "raw": repr(line)})
                if i > 50:
                    break
        return lines
