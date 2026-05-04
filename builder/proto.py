#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2024/6/8 下午6:57
# @Author : crush0
# @Description :
import base64
import json
import random

import uuid

import static.Request_pb2 as RequestProto
from builder.header import HeaderBuilder
from utils.dy_util import generate_webid, generate_req_sign, generate_millisecond


class ProtoBuilder:
    @staticmethod
    def build_normal_request(auth, cmd):
        request = RequestProto.Request()
        request.cmd = cmd
        request.sequence_id = random.randint(10000, 11000)
        request.sdk_version = "1.1.3"
        request.token = auth.ticket
        request.refer = 3
        request.inbox_type = 0
        request.build_number = "5fa6ff1:Detached: 5fa6ff1111fd53aafc4c753505d3c93daad74d27"
        request.device_id = '0'
        request.device_platform = 'douyin_pc'
        request.headers['session_aid'] = '6383'
        request.headers['session_did'] = '0'
        request.headers['app_name'] = 'douyin_pc'
        request.headers['priority_region'] = 'cn'
        request.headers['user_agent'] = HeaderBuilder.ua
        request.headers['cookie_enabled'] = 'true'
        request.headers['browser_language'] = 'zh-CN'
        request.headers['browser_platform'] = 'Win32'
        request.headers['browser_name'] = 'Mozilla'
        request.headers['browser_version'] = HeaderBuilder.ua.split('Mozilla/')[-1]
        request.headers['browser_online'] = 'true'
        request.headers['screen_width'] = '1707'
        request.headers['screen_height'] = '960'
        request.headers['referer'] = ''
        request.headers['timezone_name'] = 'Etc/GMT-8'
        request.headers['deviceId'] = '0'
        request.headers['webid'] = generate_webid()
        request.headers['fp'] = auth.cookie['s_v_web_id']
        request.headers['is-retry'] = '0'
        request.auth_type = 4
        request.biz = 'douyin_web'
        request.access = 'web_sdk'
        request.ts_sign = auth.ts_sign
        request.sdk_cert = base64.b64encode(auth.client_cert.encode('utf-8')).decode('utf-8')
        return request

    @staticmethod
    def build_create_conversation_request(auth, toId, myId):
        request = ProtoBuilder.build_normal_request(auth, 609)
        request.body.create_conversation_v2_body.conversation_type = 1
        request.body.create_conversation_v2_body.participants.extend([int(toId), int(myId)])
        reuqest_sign = generate_req_sign({
            "sign_data": f"avatar_url=&idempotent_id=&name=&participants={toId},{myId}",
            "certType": "cookie",
            "scene": "web_protect"
        }, auth.private_key)
        request.reuqest_sign = reuqest_sign
        return request

    @staticmethod
    def build_get_conversation_list_info_request(auth, toId, myId, conversation_short_id):
        request = ProtoBuilder.build_normal_request(auth, 610)
        request.body.get_conversation_info_list_v2_body.data.conversation_id = f"0:1:{myId}:{toId}"
        request.body.get_conversation_info_list_v2_body.data.conversation_short_id = conversation_short_id
        request.body.get_conversation_info_list_v2_body.data.conversation_type = 1
        return request

    @staticmethod
    def build_message_by_init_request(auth, page=0):
        request = RequestProto.Request()
        request.cmd = 2043
        request.sequence_id = random.randint(10000, 11000)
        request.sdk_version = "0.1.6"
        request.token = ""
        request.refer = 3
        request.inbox_type = 1
        request.build_number = "fef1a80:p/lzg/store"
        request.device_id = '0'
        request.device_platform = 'douyin_pc'
        request.version_code = '360000'
        request.auth_type = 1
        request.biz = 'douyin_web'
        request.access = 'web_sdk'

        request.headers['session_aid'] = '6383'
        request.headers['session_did'] = '0'
        request.headers['app_name'] = 'douyin_pc'
        request.headers['priority_region'] = 'cn'
        request.headers['user_agent'] = HeaderBuilder.ua
        request.headers['cookie_enabled'] = 'true'
        request.headers['browser_language'] = 'zh-CN'
        request.headers['browser_platform'] = 'Win32'
        request.headers['browser_name'] = 'Mozilla'
        request.headers['browser_version'] = HeaderBuilder.ua.split('Mozilla/')[-1]
        request.headers['browser_online'] = 'true'
        request.headers['screen_width'] = '1707'
        request.headers['screen_height'] = '960'
        request.headers['referer'] = 'https://www.douyin.com/chat?isPopup=1'
        request.headers['timezone_name'] = 'Etc/GMT-8'
        request.headers['deviceId'] = '0'
        request.headers['webid'] = generate_webid()
        request.headers['fp'] = auth.cookie['s_v_web_id']
        request.headers['is-retry'] = '0'

        request.body.message_by_init.version = 0
        request.body.message_by_init.page = int(page)
        request.body.message_by_init.conv_limit = 30
        request.body.message_by_init.msg_limit = 1
        return request

    @staticmethod
    def build_get_user_message_request(
            auth,
            version: int = 0,
            cmd_index: int = 0,
            stranger_version: int = 0,
            read_version: int = 0,
            source: str = "",
            consult_version: int = 0,
            notify_version: int = 0,
            recent_left_side: int = 0,
            recent_right_side: int = 0,
            recent_direction: int = 1,
    ):
        request = ProtoBuilder.build_normal_request(auth, 2048)
        body = request.body.get_user_message
        body.version = int(version)
        body.cmd_index = int(cmd_index)
        body.stranger_version = int(stranger_version)
        body.read_version = int(read_version)
        body.source = source
        body.consult_version = int(consult_version)
        body.notify_version = int(notify_version)
        body.get_recent_conv_and_msg.left_side = int(recent_left_side)
        body.get_recent_conv_and_msg.right_side = int(recent_right_side)
        body.get_recent_conv_and_msg.direction = int(recent_direction)
        return request

    @staticmethod
    def build_profile_get_info_request(auth, user_id: int = 0, sec_uid: str = ""):
        """
        构建 PROFILE_GET_INFO (cmd=2015) 请求。
        通过 user_id 或 sec_uid 查询用户信息。
        """
        request = RequestProto.Request()
        request.cmd = 2015
        request.sequence_id = random.randint(10000, 11000)
        request.sdk_version = "1.1.3"
        request.token = ""
        request.refer = 3
        request.inbox_type = 0
        request.build_number = "5fa6ff1:Detached: 5fa6ff1111fd53aafc4c753505d3c93daad74d27"
        request.device_id = '0'
        request.device_platform = 'douyin_pc'
        request.version_code = '360000'
        request.auth_type = 1
        request.biz = 'douyin_web'
        request.access = 'web_sdk'

        request.headers['session_aid'] = '6383'
        request.headers['session_did'] = '0'
        request.headers['app_name'] = 'douyin_pc'
        request.headers['priority_region'] = 'cn'
        request.headers['user_agent'] = HeaderBuilder.ua
        request.headers['cookie_enabled'] = 'true'
        request.headers['browser_language'] = 'zh-CN'
        request.headers['browser_platform'] = 'Win32'
        request.headers['browser_name'] = 'Mozilla'
        request.headers['browser_version'] = HeaderBuilder.ua.split('Mozilla/')[-1]
        request.headers['browser_online'] = 'true'
        request.headers['screen_width'] = '1707'
        request.headers['screen_height'] = '960'
        request.headers['referer'] = 'https://www.douyin.com/chat?isPopup=1'
        request.headers['timezone_name'] = 'Etc/GMT-8'
        request.headers['deviceId'] = '0'
        request.headers['webid'] = generate_webid()
        request.headers['fp'] = auth.cookie['s_v_web_id']
        request.headers['is-retry'] = '0'

        if user_id:
            request.body.profile_get_info_body.user_id = user_id
        if sec_uid:
            request.body.profile_get_info_body.sec_uid = sec_uid
        return request

    @staticmethod
    def build_send_message_request(auth, conversation_id, conversation_short_id, ticket, message):
        client_message_id = str(uuid.uuid4())
        request = ProtoBuilder.build_normal_request(auth, 100)
        request.sdk_version = "0.1.6"
        request.token = ""
        request.inbox_type = 1
        request.build_number = "fef1a80:p/lzg/store"
        request.version_code = "360000"
        request.auth_type = 1
        request.headers['referer'] = 'https://www.douyin.com/chat?isPopup=1'
        msg_content = {
            "mention_users": [],
            "aweType": 700,
            "richTextInfos": [],
            "text": message
        }
        content = json.dumps(msg_content, ensure_ascii=False, separators=(',', ':'))
        request.body.send_message_body.conversation_id = conversation_id
        request.body.send_message_body.conversation_type = 1
        request.body.send_message_body.conversation_short_id = conversation_short_id
        request.body.send_message_body.content = content
        request.body.send_message_body.ext.append(
            RequestProto.ExtValue(key='s:client_message_id', value=client_message_id)
        )
        request.body.send_message_body.ext.append(
            RequestProto.ExtValue(key='s:stime', value=str(generate_millisecond()))
        )
        request.body.send_message_body.ext.append(
            RequestProto.ExtValue(key='s:mentioned_users', value='')
        )
        request.body.send_message_body.message_type = 7
        request.body.send_message_body.ticket = ticket
        request.body.send_message_body.client_message_id = client_message_id
        req_sign = generate_req_sign({
            "sign_data": f'content={content}&conversation_id={conversation_id}&conversation_short_id={conversation_short_id}',
            "certType": "cookie",
            "scene": "web_protect"
        }, auth.private_key)
        request.reuqest_sign = req_sign
        return request
