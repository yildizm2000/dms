import argparse
import time
import re

# Simple color mapping for demonstration
COLORS = {
    '1': '\033[91m',  # red
    '2': '\033[92m',  # green
    '3': '\033[93m',  # yellow
    '4': '\033[94m',  # blue
}
RESET = '\033[0m'

MULTI_TAG_RE = re.compile(r"\[cb(?P<color>\d)\]|\[cb\]", re.IGNORECASE)


def parse_multi_string(message: str):
    """Parse MULTI-style color tags and produce segments with color info."""
    segments = []
    last_end = 0
    current_color = ''
    for match in MULTI_TAG_RE.finditer(message):
        text = message[last_end:match.start()]
        if text:
            segments.append((text, current_color))
        tag = match.group(0)
        if tag.lower() == '[cb]':
            current_color = ''
        else:
            current_color = match.group('color') or ''
        last_end = match.end()
    # remaining text
    if last_end < len(message):
        segments.append((message[last_end:], current_color))
    return segments


def display_message(message: str, delay: float = 0.2, width: int = 20):
    """Simulate scrolling DMS display for a single line."""
    segments = parse_multi_string(message)
    rendered = ''.join(COLORS.get(color, '') + text + RESET for text, color in segments)
    padded = ' ' * width + rendered + ' ' * width
    for i in range(len(rendered) + width + 1):
        window = padded[i:i + width]
        print('\r' + window + ' ', end='', flush=True)
        time.sleep(delay)
    print()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Simulate a simple DMS sign.')
    parser.add_argument('message', help='Message with optional [cbN] color tags and [cb] resets')
    parser.add_argument('--width', type=int, default=20, help='Display width')
    parser.add_argument('--delay', type=float, default=0.2, help='Delay between steps in seconds')
    args = parser.parse_args()
    display_message(args.message, delay=args.delay, width=args.width)
