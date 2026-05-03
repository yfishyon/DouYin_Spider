import base64
import json

from typing import Iterable

from dy_apis.douyin_api import DouyinAPI
from utils.dy_util import trans_cookies, generate_msToken


class DouyinAuth:
    def __init__(self):
        self.cookie = None
        self.cookie_str = None
        self.private_key = None
        self.ticket = None
        self.ts_sign = None
        self.client_cert = None
        self.ree_public_key = None
        self.uid = None
        self.msToken = None

    def perepare_auth(self, cookieStr: str, web_protect_: str = "", keys_: str = ""):
        self.cookie = trans_cookies(cookieStr)
        self.cookie_str = cookieStr.strip()
        self.msToken = self.cookie["msToken"] if "msToken" in self.cookie else generate_msToken()
        self.cookie["msToken"] = self.msToken
        self.cookie_str = "; ".join([f"{k}={v}" for k, v in self.cookie.items()])
        if web_protect_ != "":
            web_protect_ = _loads_nested_json(web_protect_)
            self.ticket = web_protect_['ticket']
            self.ts_sign = web_protect_['ts_sign']
            self.client_cert = web_protect_['client_cert']
        if keys_ != "":
            keys_ = _loads_nested_json(keys_)
            self.private_key = keys_['ec_privateKey']
            self.ree_public_key = base64.b64encode(self.private_key.encode()).decode()

    def require_cookie_keys(self, keys: Iterable[str]):
        missing = [key for key in keys if key not in self.cookie or not self.cookie.get(key)]
        if missing:
            raise ValueError(f'缺少必要 Cookie 字段: {", ".join(missing)}')
        return True


    def get_uid(self):
        if self.uid is None:
            self.uid = DouyinAPI.get_my_uid(self)
        return self.uid


def _loads_nested_json(raw: str):
    outer = json.loads(raw)
    if 'data' not in outer:
        raise ValueError('认证 JSON 缺少 data 字段')
    inner = outer['data']
    try:
        return json.loads(inner)
    except json.JSONDecodeError:
        return json.loads(inner.replace('\n', '\\n').replace('\r', '\\r'))
