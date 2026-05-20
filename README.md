# Duplicate File Finder

Scan any directory for duplicate files using MD5 hashing. Shows wasted space and optionally cleans up.

## Setup

```bash
pip install -r requirements.txt
```

## Usage

```bash
# Find duplicates in a directory
python main.py ~/Downloads

# Find duplicates and interactively delete them
python main.py ~/Downloads --delete
```

## How it works

1. Groups files by size (fast filter — files with unique sizes can't be duplicates)
2. Hashes only files that share a size (MD5)
3. Groups by hash to find exact duplicates
4. Reports wasted space per group and total

In `--delete` mode, keeps the first file in each group and lets you choose which groups to clean.
