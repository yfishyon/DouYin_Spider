import hashlib
import json
import sys
import time
from collections.abc import Callable
from pathlib import Path
from threading import Event, Lock, Thread
from typing import Any
from urllib.parse import urlparse

import websocket
from websocket import WebSocketApp

try:
    import lz4.block
except ImportError:
    lz4 = None

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from .douyin_api import DouyinAPI
    from builder.auth import DouyinAuth
    from builder.header import HeaderBuilder
    from builder.params import Params
    from builder.proto import ProtoBuilder
    from static import Live_pb2, Request_pb2, Response_pb2
    from utils.common_util import load_env
    from utils.request_util import get_proxy_config
except ImportError:
    from dy_apis.douyin_api import DouyinAPI
    from dy_apis.douyin_api import protobuf_to_dict
    from builder.auth import DouyinAuth
    from builder.header import HeaderBuilder
    from builder.params import Params
    from builder.proto import ProtoBuilder
    from static import Live_pb2, Request_pb2, Response_pb2
    from utils.common_util import load_env
    from utils.request_util import get_proxy_config
else:
    from .douyin_api import protobuf_to_dict


class DouyinIMClient:
    appKey = "e1bd35ec9db7b8d846de66ed140b1ad9"
    fpId = '9'
    SUPPORTED_PROXY_TYPES = {"http", "socks4", "socks4a", "socks5", "socks5h"}

    def __init__(self, auth: DouyinAuth, auto_reconnect=True, on_new_message: Callable[[dict[str, Any]], None] | None = None):
        self.auto_reconnect = auto_reconnect
        self.auth = auth
        self.ws = None
        self.on_new_message_callback = on_new_message
        self._my_uid: int | None = None
        self._conversation_cache: dict[str, dict[str, Any]] = {}
        self._user_info_cache: dict[str, dict[str, Any]] = {}
        self._pending_requests: dict[int, dict[str, Any]] = {}
        self._pending_lock = Lock()
        self.debug_wss_fields = False
        self.auth.require_cookie_keys(["sessionid"])
        self.device_id = DouyinAPI.get_device_id(auth=self.auth)
        accessKey = f'{self.fpId + self.appKey + self.device_id}f8a69f1719916z'
        accessKey = hashlib.md5(accessKey.encode(encoding='UTF-8')).hexdigest()
        params = Params()
        (params
         .add_param("aid", "6383")
         .add_param("device_platform", "douyin_pc")
         .add_param("fpid", self.fpId)
         .add_param("device_id", self.device_id)
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
        if proxy_type not in DouyinIMClient.SUPPORTED_PROXY_TYPES:
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

    def set_message_handler(self, handler: Callable[[dict[str, Any]], None] | None):
        self.on_new_message_callback = handler
        return self

    def get_my_uid(self) -> int:
        if self._my_uid is None:
            self._my_uid = int(self.auth.get_uid())
        return self._my_uid

    def _get_cached_conversation(self, conversation_id: str) -> dict[str, Any]:
        return self._conversation_cache.get(conversation_id, {}).copy()

    @staticmethod
    def _deep_get(container: Any, *keys, default=None):
        current = container
        for key in keys:
            if isinstance(current, dict):
                if key not in current:
                    return default
                current = current[key]
                continue
            if isinstance(current, list) and isinstance(key, int):
                if key < 0 or key >= len(current):
                    return default
                current = current[key]
                continue
            return default
        return current

    @staticmethod
    def _avatar_url(user_info: dict[str, Any]) -> str:
        return (
            DouyinIMClient._deep_get(user_info, "avatar_thumb", "url_list", 0, default="")
            or DouyinIMClient._deep_get(user_info, "avatar_small", "url_list", 0, default="")
            or DouyinIMClient._deep_get(user_info, "avatar_medium", "url_list", 0, default="")
            or ""
        )

    def _get_peer_participant(self, conversation_info: dict[str, Any]) -> dict[str, Any] | None:
        participants = self._deep_get(conversation_info, "first_page_participants", "participants", default=None)
        if participants is None:
            participants = conversation_info.get("participants") or []
        if not isinstance(participants, list) or not participants:
            return None

        my_uid = self.get_my_uid()
        for participant in participants:
            if not isinstance(participant, dict):
                continue
            try:
                if int(participant.get("user_id") or 0) != my_uid:
                    return participant
            except (TypeError, ValueError):
                return participant
        return participants[0] if isinstance(participants[0], dict) else None

    def _get_user_info_by_sec_uid(self, sec_uid: str) -> dict[str, Any]:
        sec_uid = str(sec_uid or "").strip()
        if not sec_uid:
            return {}
        if sec_uid not in self._user_info_cache:
            try:
                payload = DouyinAPI.get_user_info(self.auth, f"https://www.douyin.com/user/{sec_uid}")
                user_info = payload.get("user") if isinstance(payload, dict) else {}
                self._user_info_cache[sec_uid] = user_info if isinstance(user_info, dict) else {}
            except Exception as exc:
                print(f"[IM] 获取用户 {sec_uid} 信息失败: {exc}")
                self._user_info_cache[sec_uid] = {}
        return self._user_info_cache.get(sec_uid, {})

    def _enrich_single_conversation_name(self, conversation_info: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(conversation_info, dict):
            return conversation_info
        if int(conversation_info.get("conversation_type") or 0) != 1:
            return conversation_info

        current_name = (
            conversation_info.get("name")
            or self._deep_get(conversation_info, "conversation_core_info", "name", default="")
        )
        if current_name:
            conversation_info.setdefault("display_name", str(current_name))
            return conversation_info

        peer = self._get_peer_participant(conversation_info)
        if not isinstance(peer, dict):
            return conversation_info

        user_info = self._get_user_info_by_sec_uid(peer.get("sec_uid", ""))
        nickname = user_info.get("nickname") or peer.get("alias") or user_info.get("unique_id") or user_info.get("short_id") or ""
        remark_name = user_info.get("remark_name") or ""
        display_name = remark_name or nickname or ""
        if not display_name:
            return conversation_info

        conversation_info["display_name"] = str(display_name)
        conversation_info["user_info_detail"] = user_info
        if nickname:
            conversation_info["nickname"] = str(nickname)
        if remark_name:
            conversation_info["remark_name"] = str(remark_name)
        core_info = conversation_info.setdefault("conversation_core_info", {})
        if isinstance(core_info, dict):
            avatar = self._avatar_url(user_info)
            if avatar and not core_info.get("icon"):
                core_info["icon"] = avatar
        return conversation_info

    def _cache_conversation_info(self, conversation_info: dict[str, Any]):
        conversation_id = str(conversation_info.get("conversation_id") or "")
        if not conversation_id:
            return
        cached = self._conversation_cache.setdefault(conversation_id, {})
        for key in ("conversation_id", "conversation_short_id", "conversation_type", "ticket", "sender", "participants", "nickname", "remark_name", "display_name", "user_info_detail"):
            value = conversation_info.get(key)
            if value not in (None, "", 0, []):
                cached[key] = value
        if conversation_info.get("name") not in (None, ""):
            cached["name"] = conversation_info.get("name")
        if conversation_info.get("conversation_core_info") not in (None, ""):
            cached["conversation_core_info"] = conversation_info.get("conversation_core_info")

    def _cache_message_by_init_response(self, response_body):
        messages = getattr(response_body, 'messages', [])
        for item in messages:
            conversation = protobuf_to_dict(getattr(item, 'conversations', None))
            if isinstance(conversation, dict):
                self._cache_conversation_info(conversation)

    def _cache_get_user_message_response(self, response_body):
        messages_body = getattr(response_body, 'messages', None)
        recent_messages = getattr(messages_body, 'messages', []) if messages_body else []
        for item in recent_messages:
            conversation = protobuf_to_dict(getattr(item, 'conversation', None))
            if isinstance(conversation, dict):
                self._cache_conversation_info(conversation)

    def warm_conversation_cache(self, page: int = 0) -> int:
        conversation_list = self.get_message_by_init_wss(page=page)
        if conversation_list is None:
            conversation_list = DouyinAPI.get_conversation_list(self.auth, page, enrich_user_info=True)
        warmed = 0
        for conversation_info in conversation_list:
            if isinstance(conversation_info, dict):
                self._cache_conversation_info(conversation_info)
                if conversation_info.get("ticket"):
                    warmed += 1
        return warmed or len(conversation_list)

    def _resolve_conversation_info(self, message_info: dict[str, Any]) -> dict[str, Any]:
        conversation_id = str(message_info.get("conversation_id") or "")
        if not conversation_id:
            raise ValueError("缺少 conversation_id")

        merged_info = self._get_cached_conversation(conversation_id)
        merged_info.update({k: v for k, v in message_info.items() if v not in (None, "", 0)})

        conversation_short_id = merged_info.get("conversation_short_id")
        ticket = str(merged_info.get("ticket") or "")
        sender = merged_info.get("sender")

        if conversation_short_id and ticket:
            self._cache_conversation_info(merged_info)
            return merged_info

        conversation_list = []
        if conversation_short_id:
            conversation_list = DouyinAPI.get_conversation_info(
                self.auth,
                int(conversation_short_id),
                conversation_id=conversation_id,
            )
        if not conversation_list and sender is not None:
            conversation_list = DouyinAPI.get_conversation_info(
                self.auth,
                0,
                conversation_id=conversation_id,
                to_user_id=int(sender),
            )
        if conversation_list:
            merged_info.update(conversation_list[0])
            merged_info["sender"] = sender

        if not merged_info.get("ticket") and conversation_id:
            cached_info = self._get_cached_conversation(conversation_id)
            if cached_info.get("ticket"):
                merged_info.update(cached_info)

        self._cache_conversation_info(merged_info)
        return merged_info

    def _is_ws_open(self) -> bool:
        return bool(self.ws and getattr(self.ws, "sock", None) and self.ws.sock and self.ws.sock.connected)

    def _build_wss_frame(self, request: Any):
        frame_cls = getattr(Live_pb2, 'PushFrame', None)
        if frame_cls is None:
            raise RuntimeError('static.Live_pb2 缺少 PushFrame，请重新生成 protobuf 文件')
        frame = frame_cls()
        frame.seqId = int(request.sequence_id)
        frame.logId = int(time.time() * 1000)
        frame.service = 5
        frame.method = 1
        frame.payloadType = 'pb'
        frame.payload = request.SerializeToString()
        for key, value in request.headers.items():
            header = frame.headersList.add()
            header.key = str(key)
            header.value = str(value)
        return frame

    @staticmethod
    def _decode_frame_payload(frame) -> bytes:
        payload = frame.payload
        if frame.payloadEncoding != '__lz4':
            return payload
        if lz4 is None:
            raise RuntimeError("WSS 返回 __lz4 压缩 payload，请先安装 lz4")
        try:
            return lz4.block.decompress(payload, uncompressed_size=len(payload) * 10)
        except Exception:
            return lz4.block.decompress(payload, uncompressed_size=1024 * 1024)

    def send_wss_request(self, request: Any, timeout: float = 5.0):
        if not self._is_ws_open():
            return None
        waiter = {"event": Event(), "response": None}
        seq_id = int(request.sequence_id)
        with self._pending_lock:
            self._pending_requests[seq_id] = waiter
        try:
            frame = self._build_wss_frame(request)
            ws = self.ws
            if ws is None:
                return None
            ws.send(frame.SerializeToString(), opcode=websocket.ABNF.OPCODE_BINARY)
            if not waiter["event"].wait(timeout):
                return None
            return waiter["response"]
        finally:
            with self._pending_lock:
                self._pending_requests.pop(seq_id, None)

    def get_message_by_init_wss(self, page: int = 0, enrich_user_info: bool = True) -> list[dict[str, Any]] | None:
        request = ProtoBuilder.build_message_by_init_request(self.auth, page=page)
        response = self.send_wss_request(request)
        if not response or not response.body.HasField('message_by_init'):
            return None
        body = response.body.message_by_init
        self._cache_message_by_init_response(body)
        conversation_list = []
        for item in getattr(body, 'messages', []):
            conversation = protobuf_to_dict(getattr(item, 'conversations', None))
            if isinstance(conversation, dict):
                if enrich_user_info:
                    conversation = self._enrich_single_conversation_name(conversation)
                self._cache_conversation_info(conversation)
                conversation_list.append(conversation)
        return conversation_list

    def get_conversation_list_wss(self, cursor: int = 0, enrich_user_info: bool = True) -> list[dict[str, Any]] | None:
        return self.get_message_by_init_wss(page=cursor, enrich_user_info=enrich_user_info)

    def get_user_message_wss(self) -> dict[str, Any] | None:
        request = ProtoBuilder.build_get_user_message_request(self.auth, source='douyin_web')
        response = self.send_wss_request(request)
        if not response or not response.body.HasField('get_user_message'):
            return None
        body = response.body.get_user_message
        self._cache_get_user_message_response(body)
        return protobuf_to_dict(body)

    def send_text_wss(self, conversation_info: dict[str, Any], content: str) -> dict[str, Any] | None:
        conversation_id = str(conversation_info.get("conversation_id") or "")
        conversation_short_id = conversation_info.get("conversation_short_id")
        conversation_type = int(conversation_info.get("conversation_type") or 1)
        ticket = str(conversation_info.get("ticket") or "")

        if not conversation_id or not conversation_short_id or not ticket:
            return None

        request = ProtoBuilder.build_send_message_request(
            self.auth,
            conversation_id=conversation_id,
            conversation_short_id=int(conversation_short_id),
            ticket=ticket,
            message=content,
        )
        request.body.send_message_body.conversation_type = conversation_type
        response = self.send_wss_request(request)
        if not response or not response.body.HasField('send_message_body'):
            return None

        body = response.body.send_message_body
        result = protobuf_to_dict(body)
        result["status_code"] = getattr(response, "status_code", 0)
        result["error_desc"] = getattr(response, "error_desc", "")
        if "status" not in result and result.get("server_message_id"):
            result["status"] = 0
        return result

    def reply_text(self, message_info: dict[str, Any], content: str) -> bool:
        conversation_info = self._resolve_conversation_info(message_info)
        conversation_id = str(conversation_info.get("conversation_id") or "")
        conversation_short_id = conversation_info.get("conversation_short_id")
        ticket = str(conversation_info.get("ticket") or "")

        if not conversation_short_id or not ticket:
            raise ValueError("reply_text 缺少 conversation_short_id 或 ticket，无法发送回复")

        wss_result = self.send_text_wss(conversation_info, content)
        if isinstance(wss_result, dict):
            if int(wss_result.get("status") or 0) == 0 and int(wss_result.get("status_code") or 0) == 0:
                return True
            check_message = wss_result.get("check_message") or wss_result.get("error_desc") or ""
            if check_message:
                print(f"WSS 发送失败，将回退 HTTP: {check_message}")

        return DouyinAPI.send_msg(
            self.auth,
            conversation_id=conversation_id,
            conversation_short_id=int(conversation_short_id),
            ticket=ticket,
            content=content,
        )

    def _build_message_info(self, msg, content: dict[str, Any], msg_type: int) -> dict[str, Any]:
        conversation_id = getattr(msg, 'conversation_id', '')
        message_info = {
            "conversation_id": conversation_id,
            "conversation_short_id": getattr(msg, 'conversation_short_id', 0),
            "conversation_type": getattr(msg, 'conversation_type', 0),
            "server_message_id": getattr(msg, 'server_message_id', 0),
            "sender": getattr(msg, 'sender', ''),
            "message_type": msg_type,
            "index_in_conversation": getattr(msg, 'index_in_conversation', 0),
            "content": content,
            "text": content.get("text", "") if isinstance(content, dict) else "",
            "ticket": "",
        }
        self._cache_conversation_info(message_info)
        return message_info

    def _emit_new_message(self, message_info: dict[str, Any]):
        handler = self.on_new_message_callback
        if not handler:
            return

        def _run_handler():
            try:
                handler(message_info)
            except Exception as exc:
                print(f"消息回调执行失败: {exc}")

        Thread(target=_run_handler, daemon=True).start()

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

    def _heartbeat_loop(self):
        first_success = True
        my_ws = self.ws
        while True:
            time.sleep(20)
            try:
                if self.ws is not my_ws:
                    return
                if my_ws and getattr(my_ws, "sock", None):
                    my_ws.send('hi')
                    if first_success:
                        print("[心跳] 连接保持中")
                        first_success = False
            except Exception:
                if self.auto_reconnect:
                    print("[心跳] 连接断开，准备重连")
                    self.start()
                return

    def on_open(self, ws):
        print("WebSocket connection open.")
        Thread(target=self._heartbeat_loop, daemon=True).start()

    def on_message(self, ws, message):
        if isinstance(message, bytes) and message.strip() == b'hi':
            return
        if isinstance(message, str) and message.strip() == 'hi':
            return
        frame = getattr(Live_pb2, 'PushFrame', None)
        if frame is None:
            raise RuntimeError('static.Live_pb2 缺少 PushFrame，请重新生成 protobuf 文件')
        frame = frame()
        frame.ParseFromString(message)
        if self.debug_wss_fields:
            print(
                f"[WSS][frame] seqId={frame.seqId} logId={frame.logId} "
                f"service={frame.service} method={frame.method} "
                f"payloadType={frame.payloadType} payloadEncoding={frame.payloadEncoding} "
                f"payloadBytes={len(frame.payload)}"
            )
        if frame.payloadType == 'pb':
            response_cls = getattr(Response_pb2, 'Response', None)
            if response_cls is None:
                raise RuntimeError('static.Response_pb2 缺少 Response，请重新生成 protobuf 文件')
            response = response_cls()
            payload = self._decode_frame_payload(frame)
            try:
                response.ParseFromString(payload)
            except Exception as exc:
                if self.debug_wss_fields:
                    print(f"[WSS][response-parse-error] {exc} payload_hex={payload[:160].hex()}")
                raise
            if self.debug_wss_fields:
                print(
                    f"[WSS][response] cmd={response.cmd} sequence_id={response.sequence_id} "
                    f"status_code={getattr(response, 'status_code', 0)} "
                    f"inbox_type={response.inbox_type} body={response.body.WhichOneof('body')} "
                    f"error_desc={response.error_desc}"
                )
            sequence_id = int(getattr(response, 'sequence_id', 0) or 0)
            if sequence_id:
                with self._pending_lock:
                    waiter = self._pending_requests.get(sequence_id)
                if waiter:
                    waiter["response"] = response
                    waiter["event"].set()
                    return
            if response.body.HasField('message_by_init'):
                self._cache_message_by_init_response(response.body.message_by_init)
            if response.body.HasField('get_user_message'):
                self._cache_get_user_message_response(response.body.get_user_message)
            if not response.body.HasField('new_message_notify'):
                return
            msg = response.body.new_message_notify.message
            sender = getattr(msg, 'sender', '')
            content = getattr(msg, 'content', '')
            msg_type = getattr(msg, 'message_type', 0)
            conversation_id = getattr(msg, 'conversation_id', '')
            index = getattr(msg, 'index_in_conversation', 0)
            content = self._ensure_dict(content)
            message_info = self._build_message_info(msg, content, msg_type)
            if msg_type in (7, 10001):
                print(f'【消息编号:{index}】【聊天室ID:{conversation_id}】【来自:{sender}】文本消息:{content.get("text", "")}')
                self._emit_new_message(message_info)
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
        except Exception:
            self.ws.close()

if __name__ == '__main__':
    # websocket.enableTrace(True)
    auth_ = load_env()
    douyin_msg = DouyinIMClient(auth_)
    douyin_msg.start()
