# 景区数字人内容工作台

本地轻量工具，内置灵山景区、敦煌、西湖各 10 条预测问答。可选择公共音色，通过说明文件指定的火山引擎 `/api/v1/tts` 同步接口永久保存 MP3，再把音频和人物图片或无声视频发给 MuseTalk。SQLite 串联问答、所选音色、音频、人物素材和视频。

## 启动

1. 复制 `.env.example` 为 `.env`，填写 `TTS_APP_ID` 和 `TTS_ACCESS_TOKEN`。当前本地 `.env` 已按“语音合成说明”中的 demo 配置。
2. 执行：

```powershell
python -m pip install -r requirements.txt
python -m uvicorn backend.main:app --reload --port 8000
```

3. 打开 `http://127.0.0.1:8000`，接口文档在 `/docs`。

## 永久数据

- 关系数据库：`data/app.db`
- 音频：`data/audio/`
- 人物素材：`data/materials/`
- 数字人成片：`data/videos/`

运行数据默认不提交 Git，但重启后保留。此版 v1 同步接口只接受 `zh_xxx_bigtts` 公共音色，不接受 UUID 复刻音色。MuseTalk 公网地址变化时修改 `MUSETALK_BASE_URL` 即可。Access Token 只由后端读取，不会发送到浏览器。
