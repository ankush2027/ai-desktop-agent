# AI Desktop Agent

A modular Python-based desktop automation assistant that executes natural language commands on a local machine. The project is designed with a clean architecture consisting of a parser, executor, and independent action modules, making it easy to extend with new features.

---

## Features

- Open websites
- Open desktop applications
- Open folders
- Open local files
- Google search
- Create files
- Create folders
- Delete files
- Delete folders
- Rename files
- Rename folders
- Copy files
- Move files
- Command logging with timestamps
- Modular and extensible architecture

---

## Project Structure

```
ai-desktop-agent/
│
├── actions/
│   ├── apps.py
│   ├── browser.py
│   ├── copy.py
│   ├── copy_file.py
│   ├── create.py
│   ├── delete.py
│   ├── directories.py
│   ├── exit.py
│   ├── files.py
│   ├── folders.py
│   ├── help.py
│   ├── move.py
│   ├── move_file.py
│   ├── opener.py
│   ├── rename.py
│   ├── search.py
│   └── ...
│
├── logs/
│   └── history.log
│
├── config.py
├── executor.py
├── logger.py
├── main.py
├── parser.py
└── README.md
```

---

## How It Works

```
User Command
      │
      ▼
 Parser
      │
      ▼
 Executor
      │
      ▼
 Action Module
      │
      ▼
 Operating System
```

The parser converts natural language into structured commands.

The executor routes each command to the correct action.

Each action is implemented as an independent module, making the project easy to maintain and extend.

---

## Installation

Clone the repository:

```bash
git clone https://github.com/ankush2027/ai-desktop-agent.git
```

Move into the project directory:

```bash
cd ai-desktop-agent
```

Run the assistant:

```bash
python3 main.py
```

---

## Example Commands

### Open

```
open yt
open chrome
open desktop
open actions/move.py
```

### Search

```
search python decorators
```

### Create

```
create file notes.txt
create folder Projects
```

### Delete

```
delete file notes.txt
delete folder Projects
```

### Rename

```
rename file old.txt new.txt
rename folder OldFolder NewFolder
```

### Copy

```
copy file notes.txt backup.txt
```

### Move

```
move file notes.txt Projects/notes.txt
```

### Help

```
help
```

### Exit

```
exit
```

---

## Logging

Every executed command is stored with a timestamp in:

```
logs/history.log
```

This logging system provides the foundation for future memory and activity tracking features.

---

## Future Scope

Version 2 will introduce:

- AI-powered command understanding
- User memory
- Rule engine
- Context-aware reminders
- Personalized automation
- Voice command support
- Cross-platform support
- Plugin architecture

---

## Technologies Used

- Python 3
- Standard Library
  - os
  - shutil
  - subprocess
  - webbrowser
  - datetime

---

## Author

**Ankush**

Final Year Computer Science Engineering (AI & ML)

This project was built to strengthen software engineering fundamentals, modular application design, and desktop automation using Python.