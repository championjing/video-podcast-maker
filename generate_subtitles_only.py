#!/usr/bin/env python3
"""
Subtitle Generator Script for Video Podcast Maker
Converts podcast.txt to SRT/LRC subtitles without TTS audio generation
"""
import os
import sys
import json
import argparse
import re
import math


def format_time_srt(seconds):
    """Format seconds to SRT time format (HH:MM:SS,mmm)"""
    h, remainder = divmod(int(seconds), 3600)
    m, s = divmod(remainder, 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def format_time_lrc(seconds):
    """Format seconds to LRC time format ([mm:ss.xx])"""
    m, s = divmod(int(seconds), 60)
    centiseconds = int((seconds % 1) * 100)
    return f"[{m:02d}:{s:02d}.{centiseconds:02d}]"


def generate_subtitles_from_text(text_content, output_format="srt", chars_per_second=5):
    """
    Generate subtitles from plain text

    Args:
        text_content: The input text to convert to subtitles
        output_format: "srt" or "lrc"
        chars_per_second: Average character reading speed (default 5 chars/sec)

    Returns:
        List of subtitle entries
    """
    # Split text into sections by markers
    section_pattern = r'\[SECTION:(\w+)\]'
    sections = []
    matches = list(re.finditer(section_pattern, text_content))

    if not matches:
        # No sections found, treat entire text as one segment
        sections.append({
            'name': 'main',
            'text': re.sub(section_pattern, '', text_content).strip(),
            'start_time': 0,
            'end_time': None
        })
    else:
        for i, match in enumerate(matches):
            section_name = match.group(1)
            start_pos = match.end()
            end_pos = matches[i+1].start() if i+1 < len(matches) else len(text_content)
            section_text = text_content[start_pos:end_pos].strip()

            sections.append({
                'name': section_name,
                'text': section_text,
                'start_time': None,
                'end_time': None
            })

    # Process each section
    subtitles = []
    current_time = 0

    for i, section in enumerate(sections):
        # Split section text into chunks of reasonable length
        section_text = section['text'].strip()

        if not section_text:
            # Handle empty sections
            section['start_time'] = current_time
            section['end_time'] = current_time
            continue

        # Split into sentences
        sentences = re.split(r'[。！？.!?]', section_text)
        sentences = [s.strip() for s in sentences if s.strip()]

        # Group sentences into chunks
        chunks = []
        current_chunk = ""

        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue

            # If adding this sentence would exceed reasonable length, start a new chunk
            if len(current_chunk) + len(sentence) > 100:  # Max ~100 chars per subtitle
                if current_chunk.strip():
                    chunks.append(current_chunk.strip())
                current_chunk = sentence
            else:
                if current_chunk:
                    current_chunk += " " + sentence
                else:
                    current_chunk = sentence

        if current_chunk.strip():
            chunks.append(current_chunk.strip())

        # Generate subtitles for each chunk
        for j, chunk in enumerate(chunks):
            duration = len(chunk) / chars_per_second  # Calculate duration based on text length
            start_time = current_time
            end_time = current_time + duration

            if output_format == "srt":
                subtitles.append({
                    'index': len(subtitles) + 1,
                    'start': format_time_srt(start_time),
                    'end': format_time_srt(end_time),
                    'text': chunk
                })
            elif output_format == "lrc":
                # LRC format typically has one line per timestamp
                lines = chunk.split('\n')
                for line in lines:
                    line = line.strip()
                    if line:
                        subtitles.append({
                            'time': format_time_lrc(start_time),
                            'text': line
                        })

            current_time = end_time

        # Store section times
        if i == 0:
            section['start_time'] = 0
        else:
            section['start_time'] = sections[i-1]['end_time']
        section['end_time'] = current_time

    # Set up the first section if not already set
    if sections and sections[0]['start_time'] is None:
        sections[0]['start_time'] = 0

    return subtitles, sections, current_time


def save_srt_subtitles(subtitles, output_file):
    """Save subtitles in SRT format"""
    with open(output_file, 'w', encoding='utf-8') as f:
        for sub in subtitles:
            f.write(f"{sub['index']}\n")
            f.write(f"{sub['start']} --> {sub['end']}\n")
            f.write(f"{sub['text']}\n")
            f.write("\n")


def save_lrc_subtitles(subtitles, output_file):
    """Save subtitles in LRC format"""
    with open(output_file, 'w', encoding='utf-8') as f:
        for sub in subtitles:
            f.write(f"{sub['time']}{sub['text']}\n")


def save_timing_json(sections, total_duration, output_file, fps=30):
    """Save timing information in JSON format for Remotion synchronization"""
    timing_data = {
        'total_duration': total_duration,
        'fps': fps,
        'total_frames': int(total_duration * fps),
        'sections': [
            {
                'name': s['name'],
                'start_time': round(s['start_time'], 3),
                'end_time': round(s['end_time'], 3),
                'duration': round(s['end_time'] - s['start_time'], 3) if s['start_time'] is not None and s['end_time'] is not None else 0,
                'start_frame': int(s['start_time'] * fps) if s['start_time'] is not None else 0,
                'duration_frames': int((s['end_time'] - s['start_time']) * fps) if s['start_time'] is not None and s['end_time'] is not None else 0,
                'is_silent': len(s['text'].strip()) == 0
            }
            for s in sections if s['start_time'] is not None and s['end_time'] is not None
        ]
    }

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(timing_data, f, indent=2, ensure_ascii=False)


def main():
    parser = argparse.ArgumentParser(
        description='Generate SRT/LRC subtitles from podcast script without TTS',
        epilog='Example: python generate_subtitles_only.py --input podcast.txt --format srt --output-dir ./videos/my_video/'
    )
    parser.add_argument('--input', '-i', default='podcast.txt', help='Input script file (default: podcast.txt)')
    parser.add_argument('--output-dir', '-o', default='.', help='Output directory for subtitle files (default: current dir)')
    parser.add_argument('--format', '-f', choices=['srt', 'lrc'], default='srt', help='Output format: srt or lrc (default: srt)')
    parser.add_argument('--chars-per-second', '-cps', type=float, default=5.0, help='Average character reading speed (default: 5.0 chars/sec)')

    args = parser.parse_args()

    # Ensure output directory exists
    os.makedirs(args.output_dir, exist_ok=True)

    # Check input file
    if not os.path.exists(args.input):
        print(f"Error: Input file not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    # Read input text
    with open(args.input, "r", encoding='utf-8') as f:
        text_content = f.read()

    print(f"Processing: {args.input}")
    print(f"Format: {args.format.upper()}")
    print(f"Reading speed: {args.chars_per_second} chars/sec")

    # Generate subtitles
    subtitles, sections, total_duration = generate_subtitles_from_text(
        text_content,
        output_format=args.format,
        chars_per_second=args.chars_per_second
    )

    # Save subtitles
    if args.format == 'srt':
        output_file = os.path.join(args.output_dir, "podcast_subtitles.srt")
        save_srt_subtitles(subtitles, output_file)
        print(f"✓ Saved SRT subtitles: {output_file} ({len(subtitles)} entries)")
    else:  # lrc
        output_file = os.path.join(args.output_dir, "podcast_subtitles.lrc")
        save_lrc_subtitles(subtitles, output_file)
        print(f"✓ Saved LRC subtitles: {output_file} ({len(subtitles)} entries)")

    # Save timing info for Remotion
    timing_file = os.path.join(args.output_dir, "timing.json")
    save_timing_json(sections, total_duration, timing_file)
    print(f"✓ Saved timing info: {timing_file}")

    # Print summary
    print(f"\nSummary:")
    print(f"- Total duration: {total_duration:.1f} seconds")
    print(f"- {len(subtitles)} subtitle entries generated")
    print(f"- {len(sections)} sections detected")

    if sections:
        print("\nSection times:")
        for section in sections:
            if section['start_time'] is not None and section['end_time'] is not None:
                print(f"  {section['name']}: {section['start_time']:.1f}s - {section['end_time']:.1f}s ({section['end_time']-section['start_time']:.1f}s)")


if __name__ == "__main__":
    main()