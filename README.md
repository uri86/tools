# Tools

## What is it?
This is a collection of CLI tools I’ve written for my computer.
Each tool includes a Bash script to automatically install its dependencies.

## How to make a symlink on mac?

After giving permission to the correct files via the chmod command, we'll use the ln command.

```bash
cd /path/to/my/bin/folder/
ln -s /path/to/file name
```

**Note:**

- Every Python-based tool in this project creates its own virtual environment to keep the host system clean.

- All tools have been tested on macOS only; they may behave differently on other systems.

- This project is intended for UNIX-like systems and is not designed for Windows.