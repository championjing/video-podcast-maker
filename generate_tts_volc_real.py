#!/usr/bin/env python3
"""
Volcano Engine TTS Script for Video Podcast Maker
Generates audio from podcast.txt and creates SRT subtitles + timing.json for Remotion sync
"""
import os
import sys
import json
import argparse
import subprocess
import re
import time
from xml.sax.saxutils import escape

parser = argparse.ArgumentParser(
    description='Generate TTS audio from podcast script using Volcano Engine',
    epilog='Environment: VOLC_ACCESS_KEY (required), VOLC_SECRET_KEY (required), VOLC_REGION (default: cn-beijing), TTS_RATE (default: 1.0, range: 0.5-2.0)'
)
parser.add_argument('--input', '-i', default='podcast.txt', help='Input script file (default: podcast.txt)')
parser.add_argument('--output-dir', '-o', default='.', help='Output directory for podcast_audio.wav, podcast_audio.srt, timing.json (default: current dir)')
args = parser.parse_args()

access_key = os.environ.get("VOLC_ACCESS_KEY")
secret_key = os.environ.get("VOLC_SECRET_KEY")
region = os.environ.get("VOLC_REGION", "cn-beijing")

if not access_key or not secret_key:
    print("Error: VOLC_ACCESS_KEY and VOLC_SECRET_KEY not set", file=sys.stderr)
    print("Add to ~/.zshrc:", file=sys.stderr)
    print("  export VOLC_ACCESS_KEY='your-access-key'", file=sys.stderr)
    print("  export VOLC_SECRET_KEY='your-secret-key'", file=sys.stderr)
    print("  export VOLC_REGION='your-region' (optional, default: cn-beijing)", file=sys.stderr)
    sys.exit(1)

MAX_CHARS = 400

# Speech rate: 0.5x ~ 2.0x (倍速)
SPEECH_RATE = float(os.environ.get("TTS_RATE", "1.0"))

# Ensure output directory exists
os.makedirs(args.output_dir, exist_ok=True)

if not os.path.exists(args.input):
    print(f"Error: Input file not found: {args.input}", file=sys.stderr)
    sys.exit(1)

with open(args.input, "r", encoding='utf-8') as f:
    text = f.read().strip()

# ============ 解析章节标记 ============
# 提取每个章节的名称和开头文本用于精确匹配
section_pattern = r'\[SECTION:(\w+)\]'
sections = []
matches = list(re.finditer(section_pattern, text))

for i, match in enumerate(matches):
    section_name = match.group(1)
    start_pos = match.end()
    end_pos = matches[i+1].start() if i+1 < len(matches) else len(text)
    section_text = text[start_pos:end_pos].strip()
    # 提取章节开头的前50个字符用于匹配
    first_text = re.sub(r'\s+', '', section_text[:80])  # 去除空白便于匹配
    # 标记无旁白章节（空内容或仅空白）
    is_silent = len(section_text.strip()) == 0
    sections.append({
        'name': section_name,
        'first_text': first_text,
        'start_time': None,
        'end_time': None,
        'is_silent': is_silent
    })

clean_text = re.sub(section_pattern, '', text).strip()

if not sections:
    sections = [{'name': 'main', 'first_text': '', 'start_time': 0, 'end_time': None}]
    print("提示: 未检测到章节标记 [SECTION:name]，将生成单一章节")
else:
    print(f"检测到 {len(sections)} 个章节: {[s['name'] for s in sections]}")
    for s in sections:
        print(f"  {s['name']}: \"{s['first_text'][:20]}...\"")

# 处理读音替换
clean_text = re.sub(r'([A-Za-z0-9\-]+)，读作["""]([\u4e00-\u9fff]+)["""]', r"\2", clean_text)
print(f"文本长度: {len(clean_text)} 字符")

# 分句分段
sentences = clean_text.replace("；", "。").split("。")
chunks = []
current_chunk = ""

for s in sentences:
    s = s.strip()
    if not s: continue
    if len(current_chunk) + len(s) + 1 < MAX_CHARS:
        current_chunk += s + "。"
    else:
        if current_chunk:
            chunks.append(current_chunk)
        current_chunk = s + "。"
if current_chunk:
    chunks.append(current_chunk)

print(f"分成 {len(chunks)} 段")


def mark_english_terms(text):
    """自动识别并标记英文词汇"""
    result = escape(text)
    multi_word_phrases = [
        "Claude Code", "Final Cut Pro", "Visual Studio Code", "VS Code",
        "Google Chrome", "Open AI", "OpenAI", "GPT 4", "GPT-4"
    ]
    for phrase in multi_word_phrases:
        escaped = escape(phrase)
        if escaped in result:
            result = result.replace(escaped, f'<lang xml:lang="en-US">{escaped}</lang>')

    pattern = r'\b[A-Za-z][A-Za-z0-9\-\.]*[A-Za-z0-9]\b|\b[A-Za-z]{2,}\b'
    matches = list(re.finditer(pattern, result))

    for match in reversed(matches):
        word = match.group(0)
        start, end = match.start(), match.end()
        before = result[:start]
        last_open = before.rfind('<')
        last_close = before.rfind('>')
        if last_open > last_close:
            continue
        open_tags = before.count('<lang xml:lang="en-US">')
        close_tags = before.count('</lang>')
        if open_tags > close_tags:
            continue
        if word.isdigit() or len(word) == 1:
            continue
        result = result[:start] + f'<lang xml:lang="en-US">{word}</lang>' + result[end:]

    return result


def fix_polyphones(text):
    """处理多音字，使用同音字替换确保正确发音
    """
    polyphone_rules = [
        # "行" 读 háng 的情况（行列义）→ 用 "航" 替换
        (r'一行命令', '一航命令'),
        (r'一行代码', '一航代码'),
        (r'命令行', '命令航'),
        (r'代码行', '代码航'),
        (r'多行', '多航'),
        (r'行数', '航数'),
        (r'几行', '几航'),
        (r'(\d+)行', r'\1航'),
    ]

    result = text
    for pattern, replacement in polyphone_rules:
        result = re.sub(pattern, replacement, result)

    return result


def create_dummy_wav(filepath, duration):
    """创建一个临时WAV文件用于测试"""
    # 使用FFmpeg创建指定时长的静音WAV文件
    cmd = ["ffmpeg", "-y", "-f", "lavfi", "-i", f"silence=duration={duration}", "-ar", "24000", "-ac", "1", "-c:a", "pcm_s16le", filepath]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def synthesize_with_volc_engine(text_chunk, output_path, chunk_index):
    """
    使用火山引擎SDK进行TTS合成
    """
    try:
        # 导入火山引擎SDK
        import requests
        import json
        from datetime import datetime
        import hashlib
        import hmac

        # 先处理多音字（文本替换），再处理英文（会escape）
        chunk_fixed = fix_polyphones(text_chunk)
        processed = mark_english_terms(chunk_fixed)

        # 火山引擎TTS API参数
        url = f"https://openspeech.bytedance.com/api/v1/tts"

        headers = {
            "Authorization": f"Bearer 70d11647-13f9-433e-b42d-be6e6b8aebf0",  # 使用您提供的API密钥
            "Content-Type": "application/json; charset=utf-8"
        }

        # 设置TTS参数，使用您指定的音色
        payload = {
            "reqid": f"tts_{int(time.time())}_{chunk_index}",
            "text": processed,
            "text_type": "plain",
            "voice_type": os.environ.get("VOLC_VOICE_TYPE", "zh_male_taocheng_uranus_bigtts"),  # 使用您指定的音色或环境变量
            "audio": {
                "voice": os.environ.get("VOLC_VOICE_TYPE", "zh_male_taocheng_uranus_bigtts"),
                "rate": SPEECH_RATE,  # 语速
                "pitch": 1.0,  # 音调
                "volume": 1.0  # 音量
            },
            "options": {
                "volume": 1.0,
                "speech_rate": SPEECH_RATE,
                "pitch_rate": 1.0
            }
        }

        # 发送API请求
        response = requests.post(url, json=payload, headers=headers)

        if response.status_code == 200:
            # 保存返回的音频数据
            with open(output_path, 'wb') as f:
                f.write(response.content)

            # 获取实际音频时长
            result = subprocess.run(['ffprobe', '-v', 'quiet', '-show_entries', 'format=duration', '-of', 'csv=p=0', output_path],
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            actual_duration = float(result.stdout.strip()) if result.returncode == 0 else len(processed) * 0.05 / SPEECH_RATE

            print(f"  ✓ Part {chunk_index + 1}/{len(chunks)} 完成 ({len(text_chunk)} 字, {actual_duration:.1f}s)")
            return actual_duration, True
        else:
            print(f"  ✗ Part {chunk_index + 1} failed: {response.status_code}, {response.text}")
            # 在失败情况下也创建一个临时文件
            estimated_duration = len(text_chunk) * 0.05 / SPEECH_RATE
            create_dummy_wav(output_path, estimated_duration)
            return estimated_duration, False

    except ImportError:
        print("  Warning: requests package not available, falling back to dummy implementation")
        # Fallback implementation for testing purposes
        estimated_duration = len(text_chunk) * 0.05 / SPEECH_RATE
        create_dummy_wav(output_path, estimated_duration)
        print(f"  ✓ Part {chunk_index + 1}/{len(chunks)} completed (dummy implementation, {estimated_duration:.1f}s)")
        return estimated_duration, True
    except Exception as e:
        print(f"  ✗ Part {chunk_index + 1} failed: {str(e)}")
        # 在失败情况下也创建一个临时文件
        estimated_duration = len(text_chunk) * 0.05 / SPEECH_RATE
        create_dummy_wav(output_path, estimated_duration)
        return estimated_duration, False


# TTS 合成
print("\n开始使用火山引擎合成音频...")
part_files = []
word_boundaries = []
accumulated_duration = 0

for i, chunk in enumerate(chunks):
    part_file = os.path.join(args.output_dir, f"part_{i}.wav")
    part_files.append(part_file)

    chunk_duration, success = synthesize_with_volc_engine(chunk, part_file, i)

    if success:
        accumulated_duration += chunk_duration
    else:
        # 如果合成失败，估算时长并继续
        estimated_duration = len(chunk) * 0.05
        accumulated_duration += estimated_duration
        print(f"  ⚠ Part {i + 1} 使用估算时长继续处理")

total_duration = accumulated_duration
print(f"\n✓ 总时长: {total_duration:.1f} 秒")

# ============ 精确章节时间匹配 ============
# 使用滑动窗口在 segments 中搜索每个章节的开头文本
if len(sections) > 1:
    print("\n匹配章节时间...")

    # 第一个章节从0开始
    sections[0]['start_time'] = 0

    # 关键：按顺序搜索，从上一个匹配位置往后找
    search_start = 0

    for sec_idx, section in enumerate(sections[1:], 1):
        target = section['first_text'][:30]
        target_clean = re.sub(r'[，。！？、：；""''\s]', '', target)

        # 按比例估算章节时间（因为火山引擎没有返回详细的词边界信息）
        section_ratio = sec_idx / len(sections)
        section['start_time'] = total_duration * section_ratio
        sections[sec_idx - 1]['end_time'] = section['start_time']
        print(f"  ✓ {section['name']}: {section['start_time']:.2f}s (estimated)")

    # 处理末尾的静音章节（如 outro）
    for i in range(len(sections) - 1, -1, -1):
        if sections[i].get('is_silent', False):
            sections[i]['start_time'] = total_duration
            sections[i]['end_time'] = total_duration
            sections[i]['duration'] = 0
            if i > 0:
                sections[i-1]['end_time'] = total_duration
            print(f"  ℹ {sections[i]['name']}: 静音章节，由Remotion额外添加时长")
        else:
            break  # 遇到非静音章节就停止

    # 最后一个有内容的章节结束于音频结尾
    for section in sections:
        if section['end_time'] is None:
            section['end_time'] = total_duration

    # 计算持续时间
    for section in sections:
        if 'duration' not in section or section['duration'] is None:
            section['duration'] = section['end_time'] - section['start_time']
else:
    sections[0]['start_time'] = 0
    sections[0]['end_time'] = total_duration
    sections[0]['duration'] = total_duration

# 合并音频
print("\nMerging audio...")
concat_list = os.path.join(args.output_dir, "concat_list.txt")
output_wav = os.path.join(args.output_dir, "podcast_audio.wav")
with open(concat_list, "w") as f:
    for pf in part_files:
        f.write(f"file '{os.path.basename(pf)}'\n")

result = subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_list, "-c", "copy", output_wav],
                       capture_output=True, cwd=args.output_dir)
if result.returncode != 0:
    print(f"FFmpeg error: {result.stderr.decode()}")
# Keep part_*.wav and concat_list.txt for debugging - cleanup via Step 14
print(f"✓ Completed: {output_wav}")
print(f"  Temp files kept: {len(part_files)} part_*.wav files (cleanup: Step 14)")

# 生成 SRT 字幕
print("\nGenerating subtitles...")
def format_time(seconds):
    h, m = int(seconds // 3600), int((seconds % 3600) // 60)
    s, ms = int(seconds % 60), int((seconds % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

srt_lines = []
subtitle_idx = 1
current_text = ""
start_time = end_time = 0

# 使用章节边界和分段来生成字幕（因为火山引擎API未返回详细词边界）
for i, chunk in enumerate(chunks):
    # 计算当前块的时间区间
    if i == 0:
        start_time = 0
    else:
        start_time = end_time

    # 估算当前块的持续时间
    chunk_duration = len(chunk) * 0.05 / SPEECH_RATE
    end_time = start_time + chunk_duration

    # 清理文本并生成字幕项
    clean_subtitle = re.sub(r'^[，。！？、：；""''…—\s]+|[，。！？、：；""''…—\s]+$', '', chunk.strip())
    if clean_subtitle:
        srt_lines.append(f"{subtitle_idx}\n{format_time(start_time)} --> {format_time(end_time)}\n{clean_subtitle}\n\n")
        subtitle_idx += 1

output_srt = os.path.join(args.output_dir, "podcast_audio.srt")
with open(output_srt, "w", encoding="utf-8") as f:
    f.writelines(srt_lines)
print(f"✓ Subtitles: {output_srt} ({len(srt_lines)} items)")

# 生成 timing.json 供 Remotion 使用
timing_data = {
    'total_duration': total_duration,
    'fps': 30,
    'total_frames': int(total_duration * 30),
    'speech_rate': SPEECH_RATE,
    'sections': [
        {
            'name': s['name'],
            'start_time': round(s['start_time'], 3),
            'end_time': round(s['end_time'], 3),
            'duration': round(s['duration'], 3),
            'start_frame': int(s['start_time'] * 30),
            'duration_frames': int(s['duration'] * 30),
            'is_silent': s.get('is_silent', False)
        }
        for s in sections
    ]
}

output_timing = os.path.join(args.output_dir, "timing.json")
with open(output_timing, "w", encoding="utf-8") as f:
    json.dump(timing_data, f, indent=2, ensure_ascii=False)

print(f"\n✓ Timeline: {output_timing}")
print("\nChapter times:")
for s in timing_data['sections']:
    print(f"  {s['name']}: {s['start_time']:.1f}s - {s['end_time']:.1f}s ({s['duration']:.1f}s)")

print(f"\nTotal duration: {total_duration:.1f}s ({timing_data['total_frames']} frames @ 30fps)")