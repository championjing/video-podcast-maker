# Subtitle Generator for Video Podcast Maker

This tool generates SRT or LRC subtitle files directly from text scripts without requiring TTS (Text-to-Speech) processing. It's designed for scenarios where you only need text subtitles instead of audio narration.

## Features

- Generate SRT or LRC subtitle files from text scripts
- Preserves section markers from the original script
- Creates timing.json for Remotion synchronization
- Configurable reading speed (characters per second)
- Handles multi-section scripts with [SECTION:name] markers

## Usage

```bash
# Generate SRT subtitles
python3 generate_subtitles_only.py --input podcast.txt --format srt --output-dir ./videos/my_video/

# Generate LRC subtitles
python3 generate_subtitles_only.py --input podcast.txt --format lrc --output-dir ./videos/my_video/

# Customize reading speed (default is 5 chars/sec)
python3 generate_subtitles_only.py --input podcast.txt --format srt --chars-per-second 4 --output-dir ./videos/my_video/
```

## Parameters

- `--input` or `-i`: Input script file (default: podcast.txt)
- `--output-dir` or `-o`: Output directory (default: current directory)
- `--format` or `-f`: Output format - either "srt" or "lrc" (default: srt)
- `--chars-per-second` or `-cps`: Average character reading speed for calculating durations (default: 5.0 chars/sec)

## Output Files

- `podcast_subtitles.srt` or `podcast_subtitles.lrc`: The generated subtitle file
- `timing.json`: Timing information for Remotion video synchronization

## Integration with Video Podcast Maker

This script integrates seamlessly with the video podcast maker workflow:

1. When you have a script in `podcast.txt` format with `[SECTION:...]` markers
2. Use this tool instead of TTS generation if you only need subtitles
3. The generated timing.json can be used by Remotion compositions for synchronization
4. The subtitles can be overlaid on your video content

## Example

Given a script with sections like:

```
[SECTION:intro]
Welcome to our video about artificial intelligence...

[SECTION:history]
AI began in the 1950s...
```

The tool will generate appropriate timing and subtitles while preserving the section structure.