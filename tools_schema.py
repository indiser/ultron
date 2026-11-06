TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": (
                "List all file names in the workspace directory. "
                "Call this first when you don't know which files exist, "
                "or before read_file to get the exact filename. "
                "Returns one filename per line, or '(empty)' if workspace has no files."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": (
                "Read full text content of one file in the workspace. "
                "Use exact filename as returned by list_files, including extension. "
                "Text files only (UTF-8). Returns file content, "
                "or a string starting with 'error:' if file does not exist."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {
                        "type": "string",
                        "description": "Exact name of file to read, e.g. 'notes.txt'. No directory paths.",
                    }
                },
                "required": ["filename"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": (
                "Create a new file in the workspace, or overwrite an existing one. "
                "Writes full contents as UTF-8 text. Existing content is replaced, not appended, "
                "so call read_file first if you need to keep or edit old content. "
                "Use for saving notes, summaries, code, or any text output the user wants stored. "
                "Returns 'wrote: <filename>' on success."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {
                        "type": "string",
                        "description": "Name of file to write, e.g. 'summary.md'. Include extension. No directory paths.",
                    },
                    "contents": {
                        "type": "string",
                        "description": "Full text to write into file. Replaces any existing content.",
                    },
                },
                "required": ["filename", "contents"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_memory",
            "description": (
                "Save one lasting fact about the user to persistent memory, appended to memory.md. "
                "Use for stable info: name, job, preferences, goals, ongoing projects. "
                "Do NOT save temporary info, small talk, or facts already in memory. "
                "Write fact as one short self-contained sentence, e.g. 'User prefers Python over JavaScript.' "
                "Returns 'saved: <fact>' on success."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "fact": {
                        "type": "string",
                        "description": "One short sentence stating the fact about the user.",
                    }
                },
                "required": ["fact"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": (
                "Run one shell command on user's machine and return combined stdout and stderr. "
                "User must approve each command by typing 'y'; if declined, returns a refusal message. "
                "Use only when file tools cannot do job, e.g. run script, install package, check git status. "
                "Timeout 120 seconds. Returns output, or '(no output, exit code N)' if empty."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "Full shell command to run, e.g. 'python script.py'. One command, no interactive prompts.",
                    }
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": (
                "Quick web search, about 2 seconds. Returns 5 results: title, URL, snippet. "
                "Use for single current facts: office holders, prices, dates, scores, latest versions. "
                "Answer from the snippets when they contain the answer."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Short search query, 2-8 words."}
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": (
                "Change one exact piece of text in an existing workspace file. "
                "Use instead of write_file for edits. read_file first and copy old text exactly. "
                "old must appear exactly once."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {"type": "string", "description": "Exact file name, e.g. 'app.py'."},
                    "old": {"type": "string", "description": "Exact existing text to replace."},
                    "new": {"type": "string", "description": "Replacement text."},
                },
                "required": ["filename", "old", "new"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "research",
            "description": (
                "Deep web research. Slow, 30-90 seconds. Opens 5 pages, ranks them, returns best passages and source URL. "
                "Use only when web_search snippets lack the answer, or for detail, comparison, or lists. "
                "Set save_to only to save a numbered list to a file."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Specific search question, 3-10 words."},
                    "save_to": {"type": "string", "description": "Optional filename, e.g. 'list.txt'. Only for saving numbered lists."},
                },
                "required": ["query"],
            },
        },
    },
]