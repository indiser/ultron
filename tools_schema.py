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
                "Never use when the user asks for research or deep research."
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
                "Always use when the user says research or deep research. Also for detail, comparison, or lists. "
                "Set save_to only to save a numbered a ranked list or year/event timeline from one page to a file."
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
    {
        "type": "function",
        "function": {
            "name": "set_browser_mode",
            "description": (
                "Switch the browser between visible and headless. "
                "visible opens a real window the user can watch. headless is fast and invisible. "
                "Page state is lost on switch."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "mode": {"type": "string", "enum": ["headless", "visible"],
                             "description": "visible or headless."}
                },
                "required": ["mode"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_docs",
            "description": (
                "Search the user's indexed documents (pdf, docx, web pages). "
                "Returns top passages with file name and page. "
                "Use for any specific question about a document."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Specific question or keywords, 3-12 words."},
                    "source": {"type": "string", "description": "Optional exact file name from list_docs to restrict search."},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_doc",
            "description": (
                "Read one part of an indexed document in order, about 2700 chars per part. "
                "Use for summaries, overviews, and whole-document tasks. "
                "Part 1 first, then 2, 3. Result header shows total parts."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "source": {"type": "string", "description": "Exact file name from list_docs."},
                    "part": {"type": "integer", "description": "Part number, starting at 1."},
                },
                "required": ["source"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_docs",
            "description": "List indexed documents with chunk and part counts.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ingest_doc",
            "description": "Index a file already in the workspace (pdf, docx, txt, md) so it can be searched. Returns chunk count.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {"type": "string", "description": "Exact workspace file name, e.g. 'paper.pdf'."}
                },
                "required": ["filename"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "upload_doc",
            "description": (
                "Open a small window with an Upload button so the user can pick documents "
                "(pdf, docx, txt, md). Files are copied to the workspace and indexed. "
                "Call when the user wants to add, upload, or attach a document. "
                "Not for web links."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ingest_url",
            "description": (
                "Download a web page or PDF link and index it so it can be searched. "
                "Call when the user gives a URL to add as a document. Returns chunk count."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "Full http or https link."}
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "remove_doc",
            "description": "Remove one indexed document by exact file name from list_docs.",
            "parameters": {
                "type": "object",
                "properties": {
                    "source": {"type": "string", "description": "Exact file name from list_docs."}
                },
                "required": ["source"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ocr_image",
            "description": (
                "Read text from an image file in the workspace (png, jpg, jpeg, webp, bmp). "
                "Saves text to <name>.ocr.md and indexes it. Returns a short preview only. "
                "Then use search_docs or read_doc for details. Cannot describe photos."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {"type": "string", "description": "File name copied exactly from list_files output."}
                },
                "required": ["filename"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_file",
            "description": (
                "Permanently delete one file in the workspace. User must approve each call. "
                "Call only when the user asks to delete a file. Cannot delete folders. "
                "Also removes the file from the document index. Returns 'deleted: <filename>' on success."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {"type": "string", "description": "File name copied exactly from list_files output."}
                },
                "required": ["filename"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": (
                "Current weather and daily forecast, up to 7 days. "
                "Leave location empty to use the user's saved location. "
                "Set location only when the user names another place. "
                "Use for any weather, temperature, rain, or forecast question. Not web_search."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {"type": "string", "description": "City name the user said. Empty = saved location."},
                    "days": {"type": "integer", "description": "Forecast days, 1 to 7. Default 3."},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_places",
            "description": (
                "Find nearby places by category: restaurants, cafes, hospitals, pharmacies, ATMs, hotels, "
                "parks, museums, fuel, airports, stations. Sorted by distance. "
                "Leave near empty to use the user's saved location. Set near only when the user names another place. "
                "No ratings or reviews."
                "Default attraction. Use attraction for interesting places, sights, things to see."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {"type": "string", "enum": ["restaurant", "cafe", "fast_food", "bar", "hospital",
                                 "pharmacy", "atm", "bank", "fuel", "hotel", "museum", "attraction", "park",
                                 "supermarket", "airport", "railway_station", "bus_station"]},
                    "near": {"type": "string", "description": "City or area the user named. Empty = saved location."},
                    "radius_km": {"type": "number", "description": "Search radius in km, 0.2 to 100. Default 10."},
                    "limit": {"type": "integer", "description": "Results, 1 to 15. Default 10."},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "use_skill",
            "description": "Activate an installed skill by exact name from the Skills list. Its instructions then appear in the system prompt.",
            "parameters": {
                "type": "object",
                "properties": {"name": {"type": "string", "description": "Skill name copied exactly from the Skills list."}},
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "install_skill",
            "description": (
                "Install an agent skill from GitHub when the user gives a link or owner/repo. "
                "Shows the user the skill and asks approval. Copy source exactly from the user's message. "
                "Never install on your own."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "source": {"type": "string", "description": "owner/repo, owner/repo/path, or github.com link, copied from the user."}
                },
                "required": ["source"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculate",
            "description": "Evaluate exact arithmetic, percentages, powers (**), trig (sin/sind), logs, factorials, and combinatorics safely.",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "Math expression, e.g. '(1450 * 1.18) - 200' or 'sqrt(144) + comb(10, 3)'",
                    }
                },
                "required": ["expression"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "system_status",
            "description": "Check local machine CPU, RAM, swap, disk usage, battery, GPU, uptime, and Ultron RAM usage.",
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
            "name": "recall",
            "description": "Search earlier conversations with the user: what they asked or you answered in past sessions. Not documents (search_docs), not saved facts (memory).",
            "parameters": {
                "type": "object", "properties": {
                "query": {"type": "string", "description": "Topic or words to look for in past chats."},
                "days_back": {"type": "integer", "description": "Optional. Only the last N days."}},
                "required": ["query"]
            }
        }
    },
    {
        "type": "function", 
        "function": {
            "name": "github",
            "description": "Read-only GitHub. repo = the github.com link the user pasted, exactly, or owner/name. Actions: repo (summary), tree (folders), read (file text), item (PR or issue), my_prs, review_requests, my_issues, notifications.",
            "parameters": {
                "type": "object", 
                "properties": {
                    "action": {"type": "string", "enum": ["repo", "tree", "read", "item", "my_prs", "review_requests", "my_issues", "notifications"]},
                    "repo": {"type": "string", "description": "Pasted github.com link, or owner/name. Optional for my_* actions."},
                    "path": {"type": "string", "description": "File or folder inside the repo. Optional."},
                    "number": {"type": "integer", "description": "PR or issue number. Only for item."},
                    "part": {"type": "integer", "description": "Page of a long file, starting at 1. Optional."}},
                    "required": ["action"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "convert_currency",
            "description": "Convert money between currencies using live or historical ECB rates via Frankfurter API.",
            "parameters": {
                "type": "object",
                "properties": {
                    "amount": {
                        "type": "number",
                        "description": "Amount to convert, e.g. 100",
                    },
                    "from_currency": {
                        "type": "string",
                        "description": "Source 3-letter ISO currency code, e.g. USD, EUR, INR",
                    },
                    "to_currency": {
                        "type": "string",
                        "description": "Target 3-letter ISO currency code, e.g. INR, USD, JPY",
                    },
                    "date": {
                        "type": "string",
                        "description": "Optional historical date YYYY-MM-DD. Leave empty for latest rate.",
                    },
                },
                "required": ["amount", "from_currency", "to_currency"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "manage_schedule",
            "description": "Create, list, pause, run, or delete voice reminders and recurring cron jobs (spoken alerts or background proactive checks).",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["add_reminder", "add_cron", "list", "remove", "toggle", "run_now"],
                        "description": "Schedule operation.",
                    },
                    "task": {
                        "type": "string",
                        "description": "Required for add_reminder/add_cron: exact message to speak or check, e.g. 'Check the oven'.",
                    },
                    "when": {
                        "type": "string",
                        "description": "Required for add_reminder: duration ('20s', '15m', '2h'), time ('18:30'), or 'YYYY-MM-DD HH:MM'.",
                    },
                    "cron": {
                        "type": "string",
                        "description": "Required for add_cron: 5-field cron 'min hour day month weekday' (e.g. '0 9 * * 1-5') or @hourly/@daily.",
                    },
                    "name": {
                        "type": "string",
                        "description": "Optional short label, e.g. 'Oven timer'.",
                    },
                    "mode": {
                        "type": "string",
                        "enum": ["notify", "agent"],
                        "description": "'notify' speaks task directly; 'agent' runs silent tool check and speaks only if alert needed.",
                    },
                    "job_id": {
                        "type": "string",
                        "description": "6-char job ID for remove, toggle, or run_now.",
                    },
                },
                "required": ["action"],
            },
        },
    },
    {
        "type": "function", 
        "function": {
                "name": "air_quality",
                "description": "Air quality now (US AQI, PM2.5, PM10, ozone) plus today's and tomorrow's worst and best hours. Empty location = the user's saved location.",
                "parameters": {"type": "object", "properties": {
                "location": {"type": "string", "description": "City name. Optional."}}, "required": []
            }
        }
    },
    {"type": "function", "function": {
  "name": "sun_times",
  "description": "Sunrise, sunset, daylight length, first and last light, time until sunset, moon phase. Empty location = the user's saved location.",
  "parameters": {"type": "object", "properties": {
    "location": {"type": "string", "description": "City name. Optional."},
    "days": {"type": "integer", "description": "1 to 7. Default 2."}}, "required": []}}},
    {
        "type": "function",
        "function": {
            "name": "youtube_transcript",
            "description": "Fetch YouTube video transcript locally, save to workspace, and index for summary or Q&A.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "Full YouTube video URL or 11-char video ID."},
                    "lang": {"type": "string", "description": "Preferred ISO language code, default en."},
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_telegram",
            "description": "Send a Telegram message to the user's configured Telegram chat.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Message text to send to user on Telegram."},
                },
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_telegram",
            "description": "Read recent incoming messages received from the user's Telegram chat.",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "Number of recent messages to return (1-20, default 5)."},
                },
                "required": [],
            },
        },
    },
]