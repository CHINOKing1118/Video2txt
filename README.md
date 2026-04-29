# Video2txt v2.2

🎬 抖音视频转文字工具 — 一键下载抖音视频并自动转录为文字

## ✨ 功能特点

- 📥 **视频下载** — 支持抖音链接直接下载（yt-dlp + API 多通道）
- 🎙️ **语音转文字** — 使用 OpenAI Whisper 模型本地转录
- ✍️ **AI 润色** — 支持 AI 智能润色、生成短标题
- 📝 **多格式导出** — 支持 Markdown、TXT、SRT 字幕等格式
- 🎨 **深色/浅色主题** — 内置多种主题切换
- 📋 **历史记录** — 自动保存处理历史
- 🖱️ **拖拽支持** — 支持拖拽视频文件直接处理（需安装 windnd）

## 📋 环境要求

- **操作系统**: Windows 10/11
- **Python**: 3.8+
- **FFmpeg**: 需要安装并添加到 PATH（[下载](https://ffmpeg.org/download.html)）
- **yt-dlp**: 需要安装（`pip install yt-dlp`）

## 🚀 安装

```bash
# 克隆仓库
git clone https://github.com/tommycheng1118/Video2txt.git
cd Video2txt

# 安装依赖
pip install openai-whisper requests windnd
```

## 🏃 使用方法

```bash
python main.py
```

1. 粘贴抖音视频链接
2. 点击「开始处理」
3. 等待下载 + 转录完成
4. 查看/导出文字结果

## 📁 项目结构

```
video2txt v2.2/
├── main.py          # 程序入口
├── app.py           # 主界面与业务逻辑
├── config.py        # 配置管理
├── components.py    # UI 组件（进度条、启动画面）
├── dialogs.py       # 设置/历史对话框
├── download.py      # 视频下载（yt-dlp / API）
├── transcribe.py    # Whisper 语音转文字
├── export.py        # 字幕格式化与导出
├── ai_polish.py     # AI 润色与标题生成
├── history.py       # 历史记录管理
├── themes.py        # 主题配置
├── ui_helpers.py    # UI 辅助工具
└── utils.py         # 通用工具函数
```

## ⚙️ 配置

首次运行会自动生成 `video2txt_config.json`，可在设置界面中修改：

- **AI API** — 自定义 API 地址和密钥
- **Whisper 模型** — 默认使用 small 模型
- **输出格式** — Markdown / TXT / SRT
- **浏览器** — 用于 yt-dlp cookie 提取

## 📄 License

MIT License
