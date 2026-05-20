# Duplicate File Finder

Find and clean up duplicate files using MD5/SHA256 hashing. Supports presets, size filters, auto-cleanup strategies, exports, and more.

## Setup

```bash
pip install -r requirements.txt
pip install .   # global command
```

## Usage

### Basic scan
```bash
dupefind ~/Downloads
dupefind ~/Documents
```

### Filter by type
```bash
dupefind ~/Downloads --preset images    # jpg, png, gif, webp...
dupefind ~/Downloads --preset videos    # mp4, mov, mkv...
dupefind ~/Downloads --preset docs      # pdf, docx, xlsx...
dupefind ~/Downloads --preset audio     # mp3, wav, flac...
dupefind ~/Downloads --preset code      # py, js, go, rs...
dupefind ~/Downloads --ext .py .txt     # custom extensions
```

### Size and algorithm
```bash
dupefind ~/Downloads --min-size 1MB     # skip files under 1MB
dupefind ~/Downloads --min-size 500KB
dupefind ~/Downloads --algo sha256      # use SHA256 instead of MD5
```

### Sort results
```bash
dupefind ~/Downloads --sort wasted      # by wasted space (default)
dupefind ~/Downloads --sort size        # by individual file size
dupefind ~/Downloads --sort count       # by number of copies
```

### Cleanup options
```bash
dupefind ~/Downloads --delete                  # interactive — pick what to keep
dupefind ~/Downloads --auto newest             # auto-keep newest, delete rest
dupefind ~/Downloads --auto oldest             # auto-keep oldest
dupefind ~/Downloads --auto shortest           # auto-keep shortest path
dupefind ~/Downloads --move ~/Duplicates       # move dupes to a folder instead of deleting
```

### Export report
```bash
dupefind ~/Downloads --export report.csv
dupefind ~/Downloads --export report.json
```

### Exclude folders
```bash
dupefind ~/Projects --exclude node_modules --exclude .git
```

## Interactive Mode (`--delete`)

For each group you choose:

| Key | Action |
|-----|--------|
| `1`, `2`, `3`... | Keep that file number |
| `n` | Keep newest |
| `o` | Keep oldest |
| `s` | Keep shortest path |
| `k` | Skip this group |
| `q` | Quit cleanup |

## How it works

1. Indexes all files and groups by size (files with unique sizes can't be duplicates)
2. Hashes only files that share a size — much faster than hashing everything
3. Groups by hash to find exact byte-for-byte duplicates
4. Shows wasted space per group and lets you clean up safely
