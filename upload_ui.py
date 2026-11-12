import json
import tkinter as tk
from tkinter import filedialog

chosen = []


def pick():
    global chosen
    chosen = list(filedialog.askopenfilenames(
        parent=root,
        title="Choose documents",
        filetypes=[("Documents", "*.pdf *.docx *.txt *.md"), ("All files", "*.*")],
    ))
    root.destroy()


root = tk.Tk()
root.title("Ultron")
root.geometry("240x110")
root.resizable(False, False)
root.attributes("-topmost", True)
tk.Button(root, text="Upload", font=("Segoe UI", 14), command=pick).pack(
    expand=True, fill="both", padx=20, pady=20)
root.mainloop()
print(json.dumps(chosen))