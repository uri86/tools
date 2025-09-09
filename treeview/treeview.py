import os
import argparse

# Directories to ignore
DEFAULT_IGNORED_DIRS = {
    '.git', '__pycache__', 'node_modules', '.venv',
    '.idea', '.vscode', 'dist', 'build', '.DS_Store'
}

def print_tree(base_path, prefix="", ignored_dirs=None):
    if ignored_dirs is None:
        ignored_dirs = DEFAULT_IGNORED_DIRS

    entries = sorted(os.listdir(base_path))
    entries = [e for e in entries if e not in ignored_dirs]

    for index, entry in enumerate(entries):
        full_path = os.path.join(base_path, entry)
        connector = "└── " if index == len(entries) - 1 else "├── "

        print(prefix + connector + entry)

        if os.path.isdir(full_path):
            extension = "    " if index == len(entries) - 1 else "│   "
            print_tree(full_path, prefix + extension, ignored_dirs)

def main():
    parser = argparse.ArgumentParser(description="Print folder structure as a tree.")
    parser.add_argument("folder", help="Base folder path")
    parser.add_argument(
        "--ignore", nargs="*", default=['.venv', 'node_modules'],
        help="Extra directories to ignore (in addition to common ones)"
    )
    args = parser.parse_args()

    base_folder = os.path.abspath(args.folder)
    extra_ignored = set(args.ignore)
    ignored_dirs = DEFAULT_IGNORED_DIRS.union(extra_ignored)

    print(base_folder)
    print_tree(base_folder, ignored_dirs=ignored_dirs)

if __name__ == "__main__":
    main()
