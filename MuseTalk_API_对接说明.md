# MuseTalk 数字人 API 对接说明

本文档用于前端、后端或第三方系统对接 MuseTalk 数字人视频生成服务。

## 1. 服务地址

```text
BASE_URL=https://u754420-810d-5d42370e.westc.seetacloud.com:8443
```

所有接口都以此地址为前缀。例如健康检查接口为：

```text
https://u754420-810d-5d42370e.westc.seetacloud.com:8443/health
```

> 当前服务支持跨域请求（CORS）。公网地址可能因 AutoDL 实例或端口映射调整而变化，生产环境建议通过配置项或环境变量维护 `BASE_URL`，不要硬编码在业务代码中。

## 2. 推荐调用流程

1. 调用 `GET /health`，确认服务和模型已就绪。
2. 调用 `POST /generate`，上传角色图片/视频和驱动音频。
3. 从响应中取得 `download_url`。
4. 将 `BASE_URL` 与 `download_url` 拼接，下载生成的视频。

## 3. 健康检查

### 请求

```http
GET /health
```

完整地址：

```text
GET https://u754420-810d-5d42370e.westc.seetacloud.com:8443/health
```

### cURL 示例

```bash
curl --fail --show-error \
  "https://u754420-810d-5d42370e.westc.seetacloud.com:8443/health"
```

### 成功响应示例

```json
{
  "status": "healthy",
  "gpu_available": true,
  "gpu_name": "NVIDIA GeForce RTX 4090 D",
  "gpu_memory_gb": 23.52,
  "models_loaded": true,
  "gfpgan_available": true
}
```

字段说明：

- `status`：服务状态；正常时为 `healthy`。
- `gpu_available`：CUDA GPU 是否可用。
- `gpu_name`：GPU 名称。
- `gpu_memory_gb`：GPU 总显存，单位为 GB。
- `models_loaded`：MuseTalk 模型是否已加载。
- `gfpgan_available`：GFPGAN 依赖是否可用。

建议仅在 `status` 为 `healthy`、`gpu_available` 和 `models_loaded` 均为 `true` 时提交生成任务。若需要开启面部增强，还应确认 `gfpgan_available` 为 `true`。

## 4. 生成数字人视频（文件上传模式）

这是公网对接时推荐使用的接口。

### 请求

```http
POST /generate
Content-Type: multipart/form-data
```

> 使用浏览器的 `FormData`、Python `requests` 或 cURL `-F` 时，请勿手动设置 `Content-Type`。客户端会自动生成包含 boundary 的正确请求头。

### 参数

| 参数 | 类型 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `source` | File | 是 | - | 角色图片或基础视频。常用格式：JPG、JPEG、PNG、MP4。 |
| `audio` | File | 是 | - | 驱动音频。常用格式：WAV、MP3。 |
| `enhance` | Boolean | 否 | `false` | 是否使用 GFPGAN 增强生成区域。开启后通常更清晰，但会增加处理时间。 |
| `gfpgan_weight` | Float | 否 | `0.5` | GFPGAN 融合权重，建议范围 `0.0`～`1.0`；`0` 更接近原图，`1` 增强最强。仅在 `enhance=true` 时生效。 |
| `bbox_shift` | Integer | 否 | `0` | 人脸检测框的纵向偏移量，单位为像素。它并非严格意义上的“嘴部动作幅度”；需按素材试调。 |
| `extra_margin` | Integer | 否 | `10` | 下颌区域额外边距，建议范围 `0`～`40`。 |
| `parsing_mode` | String | 否 | `jaw` | 面部融合模式，推荐 `jaw`；底层还支持 `raw`。 |
| `left_cheek_width` | Integer | 否 | `90` | 左脸颊融合区域宽度，建议范围 `20`～`160`。 |
| `right_cheek_width` | Integer | 否 | `90` | 右脸颊融合区域宽度，建议范围 `20`～`160`。 |
| `fps` | Integer | 否 | `25` | 图片输入时的输出帧率，建议范围 `1`～`60`；视频输入时会使用原视频帧率。 |
| `batch_size` | Integer | 否 | `8` | 推理批量大小，建议范围 `1`～`32`。值越大通常越快，但占用显存更多。 |
| `output_name` | String | 否 | 自动生成 | 输出文件名。可传 `demo` 或 `demo.mp4`，服务最终生成 `demo.mp4`。 |

> 注意：以上数值范围是安全的对接建议。当前文件上传接口没有对这些数值逐项执行强制范围校验，调用方应自行校验，避免异常参数导致任务失败或生成效果异常。

### 最简 cURL 示例

```bash
curl --fail --show-error -X POST \
  "https://u754420-810d-5d42370e.westc.seetacloud.com:8443/generate" \
  -F "source=@avatar.jpg" \
  -F "audio=@speech.mp3"
```

### 推荐 cURL 示例

```bash
curl --fail --show-error -X POST \
  "https://u754420-810d-5d42370e.westc.seetacloud.com:8443/generate" \
  -F "source=@avatar.jpg" \
  -F "audio=@speech.mp3" \
  -F "enhance=true" \
  -F "gfpgan_weight=0.5" \
  -F "bbox_shift=0" \
  -F "output_name=my_first_avatar"
```

### 成功响应示例

```json
{
  "status": "success",
  "filename": "my_first_avatar.mp4",
  "download_url": "/download/my_first_avatar.mp4",
  "file_size_bytes": 12345678,
  "processing_time_seconds": 25.4
}
```

`download_url` 是相对路径，不是完整公网地址。完整下载地址应按下面方式拼接：

```text
BASE_URL + download_url
```

例如：

```text
https://u754420-810d-5d42370e.westc.seetacloud.com:8443/download/my_first_avatar.mp4
```

## 5. 下载生成结果

### 请求

```http
GET /download/{filename}
```

该接口返回 `video/mp4` 视频流，并通过 `Content-Disposition` 指示浏览器下载文件。

### cURL 示例

```bash
curl --fail --show-error -L \
  "https://u754420-810d-5d42370e.westc.seetacloud.com:8443/download/my_first_avatar.mp4" \
  --output my_first_avatar.mp4
```

## 6. 前端 JavaScript 示例

```javascript
const BASE_URL =
  "https://u754420-810d-5d42370e.westc.seetacloud.com:8443";

async function generateAvatar(sourceFile, audioFile) {
  const formData = new FormData();
  formData.append("source", sourceFile);
  formData.append("audio", audioFile);
  formData.append("enhance", "true");
  formData.append("gfpgan_weight", "0.5");
  formData.append("bbox_shift", "0");
  formData.append("output_name", `avatar_${Date.now()}`);

  const response = await fetch(`${BASE_URL}/generate`, {
    method: "POST",
    body: formData,
  });

  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.detail || `生成失败（HTTP ${response.status}）`);
  }

  return {
    ...data,
    downloadUrl: new URL(data.download_url, BASE_URL).href,
  };
}
```

生成请求可能耗时较长。前端应展示处理中状态，并避免用户重复提交；网关、反向代理和客户端的请求超时时间也应按实际视频时长合理调大。

## 7. Python 示例

```python
from pathlib import Path
from urllib.parse import urljoin

import requests

BASE_URL = "https://u754420-810d-5d42370e.westc.seetacloud.com:8443"

with open("avatar.jpg", "rb") as source, open("speech.mp3", "rb") as audio:
    response = requests.post(
        f"{BASE_URL}/generate",
        files={
            "source": ("avatar.jpg", source, "image/jpeg"),
            "audio": ("speech.mp3", audio, "audio/mpeg"),
        },
        data={
            "enhance": "true",
            "gfpgan_weight": "0.5",
            "bbox_shift": "0",
            "output_name": "my_first_avatar",
        },
        timeout=None,
    )

response.raise_for_status()
result = response.json()
download_url = urljoin(f"{BASE_URL}/", result["download_url"].lstrip("/"))

with requests.get(download_url, stream=True, timeout=300) as video_response:
    video_response.raise_for_status()
    with Path(result["filename"]).open("wb") as output:
        for chunk in video_response.iter_content(chunk_size=1024 * 1024):
            if chunk:
                output.write(chunk)

print(f"已保存：{result['filename']}")
```

## 8. 错误响应与排查

FastAPI 错误通常使用以下结构：

```json
{
  "detail": "错误说明"
}
```

常见状态码：

| HTTP 状态码 | 含义 | 建议处理方式 |
| --- | --- | --- |
| `200` | 请求成功 | 读取 JSON 或视频流。 |
| `404` | 下载文件不存在 | 检查文件名及 `download_url` 是否正确。 |
| `422` | 请求参数格式错误或缺少必填文件 | 检查字段名、表单类型和必填项。 |
| `500` | 推理或文件处理失败 | 读取响应中的 `detail`，检查输入素材和参数；必要时联系服务端。 |
| `503` | 服务尚未就绪 | 稍后重试，并先检查 `/health`。 |

对接建议：

- 上传前校验文件类型、文件大小和空文件，避免无效任务占用 GPU。
- 每次生成使用唯一的 `output_name`，避免同名结果互相覆盖。
- 不要把用户提供的路径直接作为 `output_name`；建议只使用字母、数字、下划线和短横线。
- 生成接口当前为同步请求：HTTP 响应返回前，连接需要一直保持。
- 视频生成耗时取决于音频长度、素材分辨率、GPU 负载及是否开启 GFPGAN，不能将示例中的处理时间视为固定 SLA。
- 下载地址对应服务端结果文件；重要结果应及时下载并由业务系统自行持久化。

## 9. 仅限服务端本机使用的 JSON 接口

服务还提供：

```http
POST /generate/json
Content-Type: application/json
```

该接口接收的是服务端文件系统路径（`audio_path`、`video_path`），不是客户端电脑上的路径，也不负责上传文件。因此，普通公网前端或第三方系统不应使用它；公网对接请统一使用 `POST /generate`。

## 10. 在线接口文档

FastAPI 自动文档地址：

```text
https://u754420-810d-5d42370e.westc.seetacloud.com:8443/docs
```

可在该页面查看当前服务暴露的接口及字段，并直接发起调试请求。

---

文档核对日期：2026-07-13。当天公网健康检查结果为 `healthy`，GPU、MuseTalk 模型和 GFPGAN 均已就绪。
