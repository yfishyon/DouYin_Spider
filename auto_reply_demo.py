from dy_apis.douyin_recv_msg import DouyinRecvMsg
from utils.common_util import load_env


def handle_message(message: dict, client: DouyinRecvMsg):
    sender = int(message.get("sender") or 0)
    if sender == client.get_my_uid():
        return

    text = str(message.get("text") or "").strip()
    if "你好" not in text:
        return

    print(f"命中自动回复，收到消息: {text}")
    ok = client.reply_text(message, "你好")
    print("自动回复结果:", ok)


def main():
    auth = load_env()
    client = DouyinRecvMsg(auth)
    client.set_message_handler(lambda message: handle_message(message, client))
    client.start()


if __name__ == "__main__":
    main()