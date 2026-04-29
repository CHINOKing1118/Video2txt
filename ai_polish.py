import os
import re
from datetime import datetime
from openai import OpenAI

from config import OUTPUT_DIR
from utils import sanitize_filename, retry_operation
from history import write_log

TEMPLATE_PROMPTS = {
    "concise": (
        "你是一个精炼的文稿整理助手。今天的日期：{today}。\n"
        "要求：\n"
        "1. 只保留核心观点和关键信息\n"
        "2. 高度精简，去除一切冗余内容\n"
        "3. 用简洁的短句表达\n"
        "4. 开头用一句话总结全文主旨\n"
        "5. 结尾列出 3-5 个核心要点\n"
        "6. 总字数控制在原文的 40% 以内"
    ),
    "notes": (
        "你是一个专业的文稿整理助手。今天的日期：{today}。\n"
        "要求：\n"
        "1. 修正语音识别错误和错别字\n"
        "2. 去除口语化的重复、语气词\n"
        "3. 添加段落分隔和小标题\n"
        "4. 保留原意，不添加原文没有的内容\n"
        "5. 开头生成【核心摘要】（3-5句话）\n"
        "6. 结尾生成【关键要点】列表\n"
        "7. 在要点中提取关键词并用 **加粗** 标注"
    ),
    "subtitle": (
        "你是一个字幕整理助手。今天的日期：{today}。\n"
        "要求：\n"
        "1. 将内容按语义分成短句，每句不超过 20 个字\n"
        "2. 修正明显的语音识别错误\n"
        "3. 去除重复的语气词（嗯、啊、那个等）\n"
        "4. 保留说话的原始语气和风格\n"
        "5. 每个段落用空行分隔\n"
        "6. 不添加标题、摘要或总结\n"
        "7. 保持口语化表达，不做书面化改写"
    ),
}


def polish(raw_text, log, base_url, model, api_key, template="notes"):
    log(f"🤖 正在用 {model} 梳理文稿...")
    write_log(f"[AI] 开始整理文稿，模型: {model}，模板: {template}")
    client = OpenAI(api_key=api_key, base_url=base_url)
    today = datetime.now().strftime("%Y年%m月%d日 %A")
    prompt_tpl = TEMPLATE_PROMPTS.get(template, TEMPLATE_PROMPTS["notes"])
    system_prompt = prompt_tpl.format(today=today)
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user",
             "content": f"以下是抖音视频语音转文字原始内容，请整理成结构清晰的文稿：\n\n{raw_text}"}
        ],
        max_completion_tokens=4096, temperature=0.3, stream=False)
    text = resp.choices[0].message.content
    log("✅ 文稿整理完成")
    write_log("[AI] 文稿整理完成")
    return text


def generate_short_title(raw_text, log, base_url, model, api_key):
    if not api_key or not raw_text or len(raw_text) < 10:
        return None
    log("📝 正在生成短标题...")
    write_log("[AI] 生成短标题")
    try:
        client = OpenAI(api_key=api_key, base_url=base_url)
        sample = raw_text[:3000]
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system",
                 "content": ("根据以下内容生成一个简洁的标题。要求："
                             "不超过25个汉字，准确概括核心内容。"
                             "只输出标题本身，不要加引号、序号或其他任何文字。")},
                {"role": "user", "content": sample}
            ],
            max_tokens=60, temperature=0.3, stream=False)
        short = resp.choices[0].message.content.strip()
        short = short.strip('"\'""''「」『』【】《》()（）')
        if len(short) > 25:
            short = short[:25]
        if not short:
            return None
        log(f"📝 短标题: {short}")
        write_log(f"[AI] 短标题: {short}")
        return short
    except Exception as e:
        log(f"⚠️ 短标题生成失败: {e}")
        write_log(f"[AI] 短标题生成失败: {e}")
        return None


def rename_folder_safe(old_path, new_name_base):
    if not os.path.exists(old_path):
        return old_path
    new_path = os.path.join(OUTPUT_DIR, new_name_base)
    if os.path.abspath(old_path) == os.path.abspath(new_path):
        return old_path
    if not os.path.exists(new_path):
        try:
            retry_operation(lambda: os.rename(old_path, new_path))
            write_log(f"[重命名] {os.path.basename(old_path)} → {new_name_base}")
            return new_path
        except OSError:
            return old_path
    for i in range(2, 100):
        candidate = os.path.join(OUTPUT_DIR, f"{new_name_base} ({i})")
        if not os.path.exists(candidate):
            try:
                retry_operation(lambda c=candidate: os.rename(old_path, c))
                write_log(f"[重命名] {os.path.basename(old_path)} → {os.path.basename(candidate)}")
                return candidate
            except OSError:
                return old_path
    return old_path
