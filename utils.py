import os
import re
import time
import json

from config import OUTPUT_DIR

DOUYIN_PATTERNS = [
    r'v\.douyin\.com', r'vm\.douyin\.com', r'vt\.douyin\.com',
    r'www\.douyin\.com', r'm\.douyin\.com', r'douyin\.com', r'iesdouyin\.com',
]


def is_douyin_url(url):
    return any(re.search(p, url) for p in DOUYIN_PATTERNS)


def extract_url(text):
    match = re.search(r'https?://[^\s]+', text)
    return match.group(0) if match else text.strip()


def extract_all_urls(text):
    urls = re.findall(r'https?://[^\s,;，；\n]+', text)
    cleaned = []
    for url in urls:
        url = url.rstrip('.,;:!?。，；：！？)）"\'')
        if url:
            cleaned.append(url)
    return list(dict.fromkeys(cleaned))


def sanitize_filename(name):
    return re.sub(r'[\\/*?:"<>|]', '_', name).strip().rstrip('.')


def format_duration(seconds):
    seconds = max(0, int(seconds))
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def get_user_friendly_error(error_msg):
    """返回 (中文提示, 修复动作标识|None)"""
    msg = str(error_msg).lower()
    if "401" in msg or ("invalid" in msg and "key" in msg):
        return "API 调用失败：请检查 API Key 是否正确", None
    if "429" in msg:
        return "API 请求过于频繁，请稍后再试", None
    if "timeout" in msg or "timed out" in msg:
        return "网络请求超时，请检查网络连接", None
    if "connection" in msg and ("error" in msg or "refused" in msg):
        return "网络连接失败，请检查网络设置", None
    if "ffmpeg" in msg and ("not found" in msg or "不是内部" in msg):
        return "FFmpeg 未安装，无法转换视频格式", "install_ffmpeg"
    if "whisper" in msg or "openai-whisper" in msg:
        return "语音识别模型加载失败，请检查网络或磁盘空间", "install_whisper"
    if "f2" in msg and "not found" in msg:
        return "f2 下载工具未安装", "install_f2"
    if "fpdf" in msg:
        return "PDF 导出依赖未安装", "install_fpdf"
    if "python-docx" in msg or "docx" in msg:
        return "Word 导出依赖未安装", "install_docx"
    if "opencc" in msg:
        return "繁简转换模块未安装", "install_opencc"
    if "ssl" in msg or "certificate" in msg:
        return "SSL 证书验证失败，请检查网络或更新证书", None
    if "permission" in msg or ("access" in msg and "denied" in msg):
        return "文件访问被拒绝，请检查文件权限或关闭占用程序", None
    if "disk" in msg and "space" in msg:
        return "磁盘空间不足，请清理磁盘后重试", None
    if "memory" in msg or "oom" in msg:
        return "内存不足，请关闭其他程序后重试", None
    if "rate" in msg and "limit" in msg:
        return "API 速率限制，请稍后再试", None
    if "model" in msg and "not found" in msg:
        return "AI 模型名称不正确，请在设置中检查", None
    if "no such file" in msg or "找不到" in msg:
        return "文件不存在，可能已被移动或删除", None
    return str(error_msg), None


def mask_key(key):
    if not key:
        return ""
    if len(key) <= 7:
        return "*" * len(key)
    return key[:7] + "*" * (len(key) - 7)


def clean_title_for_folder(title):
    cleaned = re.sub(r'#[\w\u4e00-\u9fff]+', '', title)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    cleaned = cleaned.rstrip(' .,;:!?。，；：！？')
    if not cleaned:
        cleaned = re.sub(r'\s+', ' ', title).strip()
    return cleaned


def find_matching_folders(clean_title):
    if not os.path.exists(OUTPUT_DIR):
        return []
    sanitized_target = sanitize_filename(clean_title)
    matches = []
    for name in os.listdir(OUTPUT_DIR):
        full_path = os.path.join(OUTPUT_DIR, name)
        if not os.path.isdir(full_path):
            continue
        parts = name.rsplit(' ', 1)
        if len(parts) == 2 and re.match(r'^\d{8}$', parts[1]):
            folder_title = parts[0]
        else:
            folder_title = name
        if folder_title == sanitized_target:
            matches.append((name, full_path))
    matches.sort(key=lambda x: x[0], reverse=True)
    return matches


def check_folder_status(folder_path):
    try:
        files = os.listdir(folder_path)
    except OSError:
        return 'empty', None
    for name in ['文稿.docx', '文稿.pdf', '文稿.md']:
        if name in files:
            return 'completed', os.path.join(folder_path, name)
    if 'raw.txt' in files:
        return 'need_polish', folder_path
    if 'audio.mp3' in files:
        return 'need_transcribe', folder_path
    for f in files:
        if f.endswith(('.mp4', '.webm')):
            return 'need_convert', folder_path
    return 'empty', folder_path


def retry_operation(func, max_retries=3, delay=0.5):
    last_error = None
    for attempt in range(max_retries):
        try:
            return func()
        except (OSError, PermissionError) as e:
            last_error = e
            if attempt < max_retries - 1:
                time.sleep(delay * (attempt + 1))
    raise last_error


def write_text_file(path, content):
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def write_json_file(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
