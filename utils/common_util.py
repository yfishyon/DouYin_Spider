import os
# from loguru import logger
from dotenv import load_dotenv

from utils.request_util import get_proxy_config

dy_auth = None
dy_live_auth = None


def load_env():
    global dy_auth, dy_live_auth
    load_dotenv()
    cookies_dy = os.getenv('DY_COOKIES') or ''
    cookies_live = os.getenv('DY_LIVE_COOKIES') or ''
    web_protect_dy = os.getenv('DY_WEB_PROTECT') or ''
    keys_dy = os.getenv('DY_KEYS') or ''
    from builder.auth import DouyinAuth
    dy_auth = DouyinAuth()
    dy_auth.perepare_auth(cookies_dy, web_protect_dy, keys_dy)
    dy_live_auth = DouyinAuth()
    dy_live_auth.perepare_auth(cookies_live, "", "")
    if not dy_auth.cookie_str:
        raise ValueError('缺少环境变量 DY_COOKIES，请在 .env 中配置抖音网页登录 Cookie')
    if not dy_live_auth.cookie_str:
        raise ValueError('缺少环境变量 DY_LIVE_COOKIES，请在 .env 中配置直播 Cookie')
    return dy_auth

def init():
    media_base_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../datas/media_datas'))
    excel_base_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../datas/excel_datas'))
    for base_path in [media_base_path, excel_base_path]:
        if not os.path.exists(base_path):
            os.makedirs(base_path)
            # logger.info(f'create {base_path}')
    cookies = load_env()
    base_path = {
        'media': media_base_path,
        'excel': excel_base_path,
        'proxies': get_proxy_config(),
    }
    return cookies, base_path
