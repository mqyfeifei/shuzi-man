#coding=utf-8
'''
requires Python 3.6 or later
pip install requests
基于你提供的官方demo模板改造，批量测试3个中文 + 3个英文语音音色
英文自动携带language=en参数解决 code:3011 unsupported language 报错
'''
import base64
import json
import uuid
import requests
import os
from pathlib import Path

# ==================== 你的原始鉴权配置，保持不变 ====================
appid = "6498312213"
access_token= "jJAZSJ4-20rrcTW7zQXRBcb6YAPhH5SE"
cluster = "volcano_tts"
host = "openspeech.bytedance.com"
api_url = f"https://{host}/api/v1/tts"
header = {"Authorization": f"Bearer;{access_token}"}

# 音频输出文件夹
OUTPUT_DIR = Path("./tts_output")
OUTPUT_DIR.mkdir(exist_ok=True)

# 测试文本
TEXT_CN = "Welcome to this scenic spot, it has beautiful scenery and a long history, enjoy your visit.。"
TEXT_EN = "Welcome to this scenic spot, it has beautiful scenery and a long history, enjoy your visit."

# 全部音色定义（匹配你给的音色信息）
VOICE_LIST = [
    {
        "voice_type": "zh_female_tianmeixiaoyuan_uranus_bigtts",
        "name": "双快思思",
        "lang": "zh",
        "desc": "温柔亲和、多情感，通用景区讲解（推荐）"
    },
    # 英文音色
    # {
    #     "voice_type": "en_female_dacey_uranus_bigtts",
    #     "name": "Dacey",
    #     "lang": "en",
    #     "desc": "Warm & Affectionate, Rich Emotion, General Scenic Spot Introduction (Recommended)"
    # },
    # {
    #     "voice_type": "en_female_stokie_uranus_bigtts",
    #     "name": "Stokie",
    #     "lang": "en",
    #     "desc": "Standard Intellectual Tone, General Broadcast"
    # },
    # {
    #     "voice_type": "en_female_ava_uranus_bigtts",
    #     "name": "Ava",
    #     "lang": "en",
    #     "desc": "Cold & Elegant, Cultural Travel Documentary"
    # }
]


def tts_generate(voice_info):
    voice_type = voice_info["voice_type"]
    voice_name = voice_info["name"]
    lang = voice_info["lang"]
    text = TEXT_EN if lang == "en" else TEXT_CN

    # 完全复刻你原来的请求体结构
    request_json = {
        "app": {
            "appid": appid,
            "token": access_token,
            "cluster": cluster
        },
        "user": {
            "uid": "388808087185088"
        },
        "audio": {
            "voice_type": voice_type,
            "encoding": "mp3",
            "speed_ratio": 1.0,
            "volume_ratio": 1.0,
            "pitch_ratio": 1.0,
        },
        "request": {
            "reqid": str(uuid.uuid4()),
            "text": text,
            "text_type": "plain",
            "operation": "query",
            "with_frontend": 1,
            "frontend_type": "unitTson"
        }
    }

    # 英文音色强制添加language=en，解决3011报错
    if lang == "en":
        request_json["audio"]["language"] = "en"

    print(f"\n==== 正在合成音色：{voice_name} | {voice_type} ====")
    try:
        resp = requests.post(api_url, json.dumps(request_json), headers=header, timeout=30)
        resp_data = resp.json()
        # print(f"接口返回：{json.dumps(resp_data, ensure_ascii=False, indent=2)}")

        if "data" in resp_data:
            audio_bin = base64.b64decode(resp_data["data"])
            save_file = OUTPUT_DIR / f"{lang}_{voice_name}.mp3"
            with open(save_file, "wb") as f:
                f.write(audio_bin)
            print(f"✅ 合成成功，保存路径：{save_file.resolve()}")
            return True
        else:
            print(f"❌ 合成失败，无音频数据")
            return False
    except Exception as e:
        print(f"❌ 请求异常：{e}")
        return False


if __name__ == '__main__':
    success_count = 0
    fail_count = 0
    for voice in VOICE_LIST:
        if tts_generate(voice):
            success_count += 1
        else:
            fail_count += 1

    print("\n==================== 测试完成汇总 ====================")
    print(f"总音色数：{len(VOICE_LIST)}")
    print(f"成功：{success_count}")
    print(f"失败：{fail_count}")
    print(f"音频存放目录：{OUTPUT_DIR.resolve()}")