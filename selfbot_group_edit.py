import asyncio
import aiohttp
import json
#import random
import zlib as _zlib
import time
import base64
import os

TOKEN = "MTM0NTM0ODA3MDE1MzUyMzI3NQ.G4O8mY.WoQC6GMlWl_h0yihsbk2HKbr1miI0aZgUDgnGs"
MESSAGE = "うんちぶりぶり！w\ndiscord.gg/aa-bot" #Noneでメッセージ送信なし
GROUP_NAME = "うんちぶりぶり！w discord.gg/aa-bot"
#icon.pngを同一ディレクトリーに配置してグループアイコンを設定


GATEWAY_URL = "wss://gateway.discord.gg/?encoding=json&v=9&compress=zlib-stream"
msg_headers={
    "Authorization": TOKEN,
    "Accept-Language": "en-US",
    "X-Discord-Locale": "en-US",
    "X-Discord-Timezone": "Asia/Tokyo",
    "X-Debug-Options": "bugReporterEnabled",
    "User-Agent": "Discord-Android/252111;RNA",
    "Content-Type": "application/json",
    "Accept-Encoding": "gzip, deflate, br"
}
ws_headers={
    "Origin": "discord.com",
    "Upgrade": "websocket",
    "Connection": "Upgrade",
    "Sec-WebSocket-Version": "13",
    "Host": "gateway.discord.gg",
    "Accept-Encoding": "gzip, deflate, br",
    "User-Agent": "okhttp/4.9.2",
}

def load_image_bytes(path: str) -> bytes:
    with open(path, "rb") as f:
        return f.read()


current_dir = os.path.dirname(os.path.abspath(__file__))
image_path = os.path.join(current_dir, "icon.png")
try:
    image_bytes = load_image_bytes(image_path)
    b64 = base64.b64encode(image_bytes).decode("ascii")
    icon_data = f"data:image/png;base64,{b64}"
except:
    image_bytes = None
    icon_data = None


async def edit_icon_and_leave(channel_id: str, new_name: str):
    async with aiohttp.ClientSession(headers=msg_headers) as session:
        if icon_data:
            await session.patch(
                f"https://discord.com/api/v9/channels/{channel_id}",
                json={
                    "name": new_name,
                    "icon": icon_data
                }
            )
        
        else:
            await session.patch(
                f"https://discord.com/api/v9/channels/{channel_id}",
                json={
                    "name": new_name
                }
            )

        await session.delete(
            f"https://discord.com/api/v9/channels/{channel_id}",
            params={"silent": "true"}
        )


async def send_message(content:str,channel_id,mentions:bool=False,message_id:str=None,guild_id:str=None):
    session=aiohttp.ClientSession(headers=msg_headers)
    payload={
        "mobile_network_type":"wifi",
        "content":content,
        #"nonce":"1296855608003133440",
        "tts":False,
        "flags":0,
        "signal_strength":0
    }
    if message_id and guild_id:
        payload["message_reference"] = {
            "guild_id": guild_id,
            "channel_id": channel_id,
            "message_id": message_id
        }

        payload["allowed_mentions"] = {
            "parse": ["users", "roles", "everyone"],
            "replied_user": mentions
        }

    response=await session.post(f"https://discord.com/api/v9/channels/{channel_id}/messages",json=payload)
    await session.close()
    #print(response.text)

async def reactions(emoji:str,channel_id,message_id,delete:bool=False):
    session=aiohttp.ClientSession(headers=msg_headers)
    if delete:
        await session.delete(f"https://discord.com/api/v9/channels/{channel_id}/messages/{message_id}/reactions/{emoji}/0/%40me?location=Message%20Inline%20Button&burst=false")
    else:
        await session.put(f"https://discord.com/api/v9/channels/{channel_id}/messages/{message_id}/reactions/{emoji}/%40me?location=Message%20Reaction%20Picker&type=0")
    await session.close()

async def send_heartbeat(ws, heartbeat_interval):
    while True:
        await asyncio.sleep(heartbeat_interval/1000)
        await ws.send_json({'op': 1, 'd': int(time.time())})

async def connect_discord(zlib:_zlib):
    async with aiohttp.ClientSession() as session:
        async with session.ws_connect(GATEWAY_URL,headers=ws_headers) as ws:
            identified = False

            async for activity in ws:
                try:
                    activity_data=json.loads(zlib.decompress(activity.data).decode("utf-8"))
                except _zlib.error:
                    continue
                if activity_data.get('op') == 10:
                    print(activity_data)
                    heartbeat_interval = activity_data['d']['heartbeat_interval']
                    asyncio.create_task(send_heartbeat(ws, heartbeat_interval))
                    if not identified:
                        await ws.send_json({
                            "op": 2,
                            "d": {
                                "token": TOKEN,
                                "properties": {
                                "os": "Android",
                                "browser": "Discord Android",
                                "device": "SCV38",
                                "system_locale": "en-US",
                                "client_version": "252.11 - rn",
                                "release_channel": "betaRelease",
                                "device_vendor_id": "99007911-5b02-40fd-aa15-838a77d3d0a7",
                                "design_id": 2,
                                "browser_user_agent": "",
                                "browser_version": "",
                                "os_version": "29",
                                "client_build_number": 252111,
                                "client_event_source": None
                                },
                                "capabilities": 30719,
                                "api_code_version": 1,
                                "user_guild_settings_version": 1057,
                                "user_settings_version": 3642
                            }
                        })
                        await ws.send_json({
                            "op":3,
                            "d":{
                                "status":"invisible",
                                "since":0,
                                "activities":[],
                                "afk":False
                            }
                        })
                        identified = True
                    continue
                if activity_data.get('op') == 0:
                    event = activity_data.get('t')
                    if event == 'READY':
                        user_id  = activity_data['d']['user']['id']
                        # 既存グループDMから全退出
                        for ch in activity_data['d'].get('private_channels', []):
                            if ch.get('type') == 3:
                                ch_id = ch['id']
                                print(f"既存グループ退出中: {ch_id}")
                                async with aiohttp.ClientSession(headers=msg_headers) as s:
                                    await s.delete(
                                        f"https://discord.com/api/v9/channels/{ch_id}",
                                        params={"silent": "true"}
                                    )
                                print(f"退出完了: {ch_id}")
                        print("既存グループ全退出完了。新規追加を監視中...")
                if activity_data['t'] == 'MESSAGE_CREATE':#on_message
                    message_content=str(activity_data['d']['content'])
                    try:
                        guild_id=activity_data['d']['guild_id']
                    except:
                        guild_id=None
                    channel_id=activity_data['d']['channel_id']
                    message_id=activity_data['d']['id']
                    message_author_id=activity_data['d']['author']['id']

                if activity_data["t"] == 'CHANNEL_CREATE' and activity_data['d'].get('type') == 3:
                    channel_id = activity_data['d']['id']
                    print(f"グループ追加検知: {channel_id} → 退出中...")
                    async with aiohttp.ClientSession(headers=msg_headers) as s:
                        await s.delete(
                            f"https://discord.com/api/v9/channels/{channel_id}",
                            params={"silent": "true"}
                        )
                    print(f"退出完了: {channel_id}")

for i in range(100):
    try:
       asyncio.run(connect_discord(zlib=_zlib.decompressobj()))
       print("reconnecting...")
    except Exception as e:
        print(e)