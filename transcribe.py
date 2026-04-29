import time
import subprocess
import threading

from config import WHISPER_MODEL_NAME
from history import write_log

_whisper_model = None
_whisper_lock = threading.Lock()
_whisper_last_fail = 0
_WHISPER_RETRY_COOLDOWN = 60  # 失败后 60 秒再重试


def get_whisper_model():
    """加载 Whisper 模型，失败返回 None（不崩溃），冷却后自动重试"""
    global _whisper_model, _whisper_last_fail
    with _whisper_lock:
        if _whisper_model is not None:
            return _whisper_model
        # 冷却期内不重试
        if _whisper_last_fail > 0 and (time.time() - _whisper_last_fail) < _WHISPER_RETRY_COOLDOWN:
            return None
        try:
            import whisper
        except ImportError:
            _whisper_last_fail = time.time()
            write_log("[Whisper] openai-whisper 未安装")
            return None
        try:
            _whisper_model = whisper.load_model(WHISPER_MODEL_NAME)
            _whisper_last_fail = 0
            write_log("[Whisper] 模型加载成功")
            return _whisper_model
        except Exception as e:
            _whisper_last_fail = time.time()
            write_log(f"[Whisper] 模型加载失败: {e}")
            return None


def video_to_mp3(video_path, mp3_path, log):
    log("🔄 正在转换为 MP3...")
    write_log(f"[转换] {video_path} → {mp3_path}")
    r = subprocess.run(
        ["ffmpeg", "-y", "-i", video_path, "-vn",
         "-acodec", "libmp3lame", "-ar", "16000", "-ac", "1", "-q:a", "2", mp3_path],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise Exception(f"转换失败: {r.stderr}")
    log(f"✅ MP3 已生成: {mp3_path}")
    write_log("[转换] MP3 已生成")
    return mp3_path


def transcribe(mp3_path, log):
    log("🎙️ 正在识别语音...")
    write_log(f"[识别] 开始识别: {mp3_path}")
    model = get_whisper_model()
    if model is None:
        raise Exception(
            "语音识别模型未加载。请确认已安装 openai-whisper（pip install openai-whisper），"
            "然后重启程序重试。如果已安装，请检查网络连接或磁盘空间。"
        )
    result = model.transcribe(
        mp3_path,
        language="zh",
        verbose=False,
        initial_prompt="以下是一段简体中文的语音内容。"
    )
    text = result["text"]
    segments = result.get("segments", [])
    try:
        from opencc import OpenCC
        cc = OpenCC('t2s')
        text = cc.convert(text)
        for seg in segments:
            if seg.get("text"):
                seg["text"] = cc.convert(seg["text"])
        log("📝 已自动将繁体转换为简体")
        write_log("[识别] 已自动将繁体转换为简体")
    except ImportError:
        log("⚠️ opencc 未安装，跳过繁简转换（pip install opencc-python-reimplemented）")
        write_log("[识别] opencc 未安装，跳过繁简转换")
    log(f"✅ 识别完成，共 {len(text)} 字")
    write_log(f"[识别] 识别完成，共 {len(text)} 字")
    return text, segments
