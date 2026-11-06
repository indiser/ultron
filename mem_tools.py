from config import MEMORY_FILE

# Load the agent memory
def load_memory() -> str:
    if MEMORY_FILE.is_file():
        return MEMORY_FILE.read_text(encoding="utf-8")
    return "(nothing saved yet)"

# Save agents memory
def save_memory(fact: str) -> str:
    with MEMORY_FILE.open("a", encoding="utf-8") as filp:
        filp.write(f"- {fact}\n")
    return f"saved: {fact}"