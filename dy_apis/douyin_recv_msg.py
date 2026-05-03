import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import websocket
from websocket import WebSocketApp

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from .douyin_api import DouyinAPI
    from builder.auth import DouyinAuth
    from builder.header import HeaderBuilder
    from builder.params import Params
    from static import Live_pb2, Response_pb2
    from utils.common_util import load_env
    from utils.request_util import get_proxy_config
except ImportError:
    from dy_apis.douyin_api import DouyinAPI
    from builder.auth import DouyinAuth
    from builder.header import HeaderBuilder
    from builder.params import Params
    from static import Live_pb2, Response_pb2
    from utils.common_util import load_env
    from utils.request_util import get_proxy_config


class DouyinRecvMsg:
    appKey = "e1bd35ec9db7b8d846de66ed140b1ad9"
    fpId = '9'
    SUPPORTED_PROXY_TYPES = {"http", "socks4", "socks4a", "socks5", "socks5h"}

    def __init__(self, auth: DouyinAuth, auto_reconnect=True):
        self.auto_reconnect = auto_reconnect
        self.auth = auth
        self.ws = None
        self.auth.require_cookie_keys(["sessionid"])
        deviceId = DouyinAPI.get_device_id(auth=self.auth)
        accessKey = f'{self.fpId + self.appKey + deviceId}f8a69f1719916z'
        accessKey = hashlib.md5(accessKey.encode(encoding='UTF-8')).hexdigest()
        params = Params()
        (params
         .add_param("aid", "6383")
         .add_param("device_platform", "douyin_pc")
         .add_param("fpid", self.fpId)
         .add_param("device_id", deviceId)
         .add_param("token", (self.auth.cookie or {}).get("sessionid", ""))
         .add_param("access_key", accessKey)
         )
        self.url = f"wss://frontier-im.douyin.com/ws/v2?{params.toString()}"

    @staticmethod
    def _get_websocket_proxy_options() -> dict[str, Any]:
        proxies = get_proxy_config()
        if not proxies:
            return {}

        proxy_url = proxies.get("https") or proxies.get("http")
        if not proxy_url:
            return {}

        parsed = urlparse(proxy_url)
        if not parsed.hostname:
            return {}

        proxy_type = (parsed.scheme or "http").lower()
        if proxy_type not in DouyinRecvMsg.SUPPORTED_PROXY_TYPES:
            print(f"未识别的代理协议: {proxy_type}，将直接连接 WebSocket")
            return {}

        proxy_options: dict[str, Any] = {
            "http_proxy_host": parsed.hostname,
            "http_proxy_port": parsed.port,
            "proxy_type": proxy_type,
        }
        if parsed.username or parsed.password:
            proxy_options["http_proxy_auth"] = (
                parsed.username or "",
                parsed.password or "",
            )
        return proxy_options

    @staticmethod
    def _ensure_dict(content: Any) -> dict:
        if isinstance(content, dict):
            return content
        if isinstance(content, str):
            try:
                parsed = json.loads(content)
                return parsed if isinstance(parsed, dict) else {"raw": content}
            except json.JSONDecodeError:
                return {"raw": content}
        return {}

    def on_open(self, ws):
        print("WebSocket connection open.")

    def on_message(self, ws, message):
        frame = getattr(Live_pb2, 'PushFrame', None)
        if frame is None:
            raise RuntimeError('static.Live_pb2 缺少 PushFrame，请重新生成 protobuf 文件')
        frame = frame()
        frame.ParseFromString(message)
        if frame.payloadType == 'pb':
            response_cls = getattr(Response_pb2, 'Response', None)
            if response_cls is None:
                raise RuntimeError('static.Response_pb2 缺少 Response，请重新生成 protobuf 文件')
            response = response_cls()
            response.ParseFromString(frame.payload)
            if not hasattr(response.body, 'new_message_notify'):
                return
            msg = response.body.new_message_notify.message
            sender = getattr(msg, 'sender', '')
            content = getattr(msg, 'content', '')
            msg_type = getattr(msg, 'message_type', 0)
            conversation_id = getattr(msg, 'conversation_id', '')
            index = getattr(msg, 'index_in_conversation', 0)
            content = self._ensure_dict(content)
            if msg_type == 7:
                print(f'【消息编号:{index}】【聊天室ID:{conversation_id}】【来自:{sender}】文本消息:{content.get("text", "")}')
            elif msg_type == 5:
                emoji_url = content.get("url", {}).get("url_list", [""])
                print(f'【消息编号:{index}】【聊天室ID:{conversation_id}】【来自:{sender}】用户表情包消息:{emoji_url[0]}')
            elif msg_type == 17:
                voice_url = content.get("resource_url", {}).get("url_list", [""])
                print(f'【消息编号:{index}】【聊天室ID:{conversation_id}】【来自:{sender}】语音信息:{voice_url[0]}')
            elif msg_type == 27:
                image_url = content.get("resource_url", {}).get("origin_url_list", [""])
                print(f'【消息编号:{index}】【聊天室ID:{conversation_id}】【来自:{sender}】图片信息:{image_url[0]}')
            elif msg_type == 8:
                print(f'【消息编号:{index}】【聊天室ID:{conversation_id}】【来自:{sender}】分享视频信息:视频ID{content.get("itemId", "")}')
            elif msg_type == 50001:
                read_index = content.get("read_index") or content.get("index_in_conversation") or index
                print(f'对方已读，消息标号:{read_index}')
            else:
                print(f'【消息编号:{index}】【聊天室ID:{conversation_id}】【来自:{sender}】未处理消息类型:{msg_type} 内容:{content}')
        elif frame.payloadType == 'text/json':
            try:
                print(json.loads(frame.payload))
            except json.JSONDecodeError:
                print(frame.payload)

    def on_error(self, ws, error):
        print("\033[31m### error ###")
        print(error)
        print("### ===error=== ###\033[m")
        if self.auto_reconnect and (
                isinstance(error, ConnectionRefusedError) or
                isinstance(error, websocket._exceptions.WebSocketConnectionClosedException)):
            time.sleep(3)
            self.start()

    def on_close(self, ws, close_status_code, close_msg):
        print("\033[31m### closed ###")
        print(f"status_code: {close_status_code}, msg: {close_msg}")
        print("### ===closed=== ###\033[m")

    def start(self):
        self.ws = WebSocketApp(
            url=self.url,
            header={
                'Pragma': 'no-cache',
                'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6',
                'User-Agent': HeaderBuilder.ua,
                'Cache-Control': 'no-cache',
                'Sec-WebSocket-Protocol': 'binary, base64, pbbp2',
                'Sec-WebSocket-Extensions': 'permessage-deflate; client_max_window_bits'
            },
            cookie=self.auth.cookie_str,
            on_message=self.on_message,
            on_error=self.on_error,
            on_close=self.on_close,
            on_open=self.on_open
        )
        try:
            self.ws.run_forever(
                origin='https://www.douyin.com',
                **self._get_websocket_proxy_options(),
            )
        except KeyboardInterrupt:
            self.ws.close()
        except:
            self.ws.close()


if __name__ == '__main__':
    # websocket.enableTrace(True)
    auth_ = load_env()
    douyinMsg = DouyinRecvMsg(auth_)
    douyinMsg.start()
