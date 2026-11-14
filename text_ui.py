import os

os.system("")  # turns on ANSI colors in Windows 10+ terminals

RESET = "\x1b[0m"

# Edit these. 256-color codes: https://www.ditig.com/256-colors-cheat-sheet
# Format: "38;5;N" = foreground color N. Add "1;" in front for bold, e.g. "1;38;5;81".
COLORS = {
    "you":       "38;5;81",   # your prompt and typed text
    "assistant": "38;5;120",  # final answer
    "think":     "38;5;244",  # [llm] timing, status lines (dim grey)
    "tool":      "38;5;214",  # [tool] calls and approval prompts
    "result":    "38;5;245",  # [result] lines
    "error":     "38;5;203",  # errors
    "info":      "38;5;141",  # banner, cancelled, misc
}

_off = bool(os.environ.get("NO_COLOR"))


def c(kind: str, text: str) -> str:
    return text if _off else f"\x1b[{COLORS[kind]}m{text}{RESET}"


def read_you(label: str = "you: ") -> str:
    """input() where the label and the text you type are both colored."""
    start = "" if _off else f"\x1b[{COLORS['you']}m"
    try:
        return input("\n" + start + label)
    finally:
        if not _off:
            print(RESET, end="", flush=True)