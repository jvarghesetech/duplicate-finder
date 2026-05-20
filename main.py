import sys
import hashlib
import json
import csv
import shutil
from pathlib import Path
from collections import defaultdict
from datetime import datetime

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn
    from rich.prompt import Prompt, Confirm
    from rich import box
except ImportError:
    print("Run: pip install rich")
    sys.exit(1)

console = Console()

SUPPORTED_PRESETS = {
    "images": {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tiff", ".heic"},
    "videos": {".mp4", ".mov", ".avi", ".mkv", ".wmv", ".flv", ".m4v", ".webm"},
    "docs":   {".pdf", ".docx", ".doc", ".xlsx", ".xls", ".pptx", ".ppt", ".txt", ".md"},
    "audio":  {".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a", ".wma"},
    "code":   {".py", ".js", ".ts", ".go", ".rs", ".java", ".c", ".cpp", ".h"},
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def human_size(size):
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} PB"


def file_hash(path, algo="md5", chunk_size=8192):
    h = hashlib.new(algo)
    try:
        with open(path, "rb") as f:
            while chunk := f.read(chunk_size):
                h.update(chunk)
        return h.hexdigest()
    except (PermissionError, OSError):
        return None


def file_modified(path):
    try:
        return datetime.fromtimestamp(Path(path).stat().st_mtime).strftime("%Y-%m-%d")
    except OSError:
        return "N/A"


# ── Core scan ─────────────────────────────────────────────────────────────────

def find_duplicates(directory, min_size=1, extensions=None, algo="md5", exclude_dirs=None):
    path = Path(directory)
    if not path.exists():
        console.print(f"[red]Directory not found: {directory}[/red]")
        sys.exit(1)

    exclude_dirs = set(exclude_dirs or [])

    by_size = defaultdict(list)
    total = 0

    with Progress(
        SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
        transient=True, console=console
    ) as progress:
        task = progress.add_task("Indexing files...", total=None)
        for f in path.rglob("*"):
            if f.is_file():
                if any(excl in f.parts for excl in exclude_dirs):
                    continue
                if extensions and f.suffix.lower() not in extensions:
                    continue
                try:
                    size = f.stat().st_size
                    if size >= min_size:
                        by_size[size].append(f)
                        total += 1
                except OSError:
                    pass
        progress.update(task, description=f"Indexed {total} files")

    console.print(f"Found [bold]{total}[/bold] files. Hashing candidates...\n")

    by_hash = defaultdict(list)
    candidates = [files for files in by_size.values() if len(files) > 1]
    candidate_count = sum(len(f) for f in candidates)

    with Progress(
        SpinnerColumn(), BarColumn(), TextColumn("{task.completed}/{task.total} files"),
        TimeElapsedColumn(), console=console
    ) as progress:
        task = progress.add_task("Hashing...", total=candidate_count)
        for files in candidates:
            for f in files:
                h = file_hash(f, algo)
                if h:
                    by_hash[h].append(f)
                progress.advance(task)

    return {h: files for h, files in by_hash.items() if len(files) > 1}


# ── Display ───────────────────────────────────────────────────────────────────

def show(duplicates, sort_by="wasted"):
    if not duplicates:
        console.print("[green]No duplicate files found![/green]")
        return []

    groups = list(duplicates.values())

    if sort_by == "wasted":
        groups.sort(key=lambda fs: fs[0].stat().st_size * (len(fs) - 1), reverse=True)
    elif sort_by == "size":
        groups.sort(key=lambda fs: fs[0].stat().st_size, reverse=True)
    elif sort_by == "count":
        groups.sort(key=lambda fs: len(fs), reverse=True)

    total_wasted = 0
    total_dupes = 0

    for i, files in enumerate(groups, 1):
        size = files[0].stat().st_size
        wasted = size * (len(files) - 1)
        total_wasted += wasted
        total_dupes += len(files) - 1

        table = Table(
            title=f"Group {i} — {len(files)} copies — {human_size(size)} each — [red]{human_size(wasted)} wasted[/red]",
            box=box.SIMPLE, header_style="bold",
        )
        table.add_column("#", width=4)
        table.add_column("Path", min_width=40)
        table.add_column("Size", justify="right", width=10)
        table.add_column("Modified", width=12)

        for j, f in enumerate(files):
            label = "[green](keep)[/green] " if j == 0 else ""
            table.add_row(str(j + 1), f"{label}{f}", human_size(size), file_modified(f))
        console.print(table)

    console.print(Panel(
        f"[bold red]{len(duplicates)} duplicate group(s)[/bold red]   "
        f"Duplicate files: [bold red]{total_dupes}[/bold red]   "
        f"Wasted space: [bold red]{human_size(total_wasted)}[/bold red]",
        title="Summary",
    ))
    return groups


# ── Export ────────────────────────────────────────────────────────────────────

def export_report(duplicates, output_path):
    out = Path(output_path)
    fmt = "json" if output_path.endswith(".json") else "csv"
    rows = []
    for h, files in duplicates.items():
        size = files[0].stat().st_size
        for i, f in enumerate(files):
            rows.append({
                "hash": h[:12],
                "group": i + 1,
                "path": str(f),
                "size_bytes": size,
                "size_human": human_size(size),
                "modified": file_modified(f),
                "is_original": i == 0,
            })
    if fmt == "json":
        with open(out, "w") as f:
            json.dump(rows, f, indent=2)
    else:
        with open(out, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)
    console.print(f"[green]Report exported to[/green] {out} ({len(rows)} entries)")


# ── Cleanup strategies ────────────────────────────────────────────────────────

def keep_newest(files):
    return sorted(files, key=lambda f: f.stat().st_mtime, reverse=True)[0]


def keep_oldest(files):
    return sorted(files, key=lambda f: f.stat().st_mtime)[0]


def keep_shortest_path(files):
    return sorted(files, key=lambda f: len(str(f)))[0]


def delete_interactive(groups):
    console.print("\n[bold yellow]Interactive Cleanup[/bold yellow]")
    console.print("For each group, choose what to keep. Others will be deleted.\n")

    deleted = 0
    freed = 0

    for i, files in enumerate(groups, 1):
        size = files[0].stat().st_size
        console.print(f"\n[bold]Group {i}[/bold] — {len(files)} files — {human_size(size)} each")
        for j, f in enumerate(files):
            console.print(f"  [{j+1}] {f}")

        console.print(f"  [n] newest  [o] oldest  [s] shortest path  [k] skip  [q] quit")
        ans = Prompt.ask("Keep", default="1").strip().lower()

        if ans == "q":
            break
        if ans == "k":
            continue

        if ans == "n":
            keep = keep_newest(files)
        elif ans == "o":
            keep = keep_oldest(files)
        elif ans == "s":
            keep = keep_shortest_path(files)
        elif ans.isdigit() and 1 <= int(ans) <= len(files):
            keep = files[int(ans) - 1]
        else:
            console.print("[dim]Skipped.[/dim]")
            continue

        for f in files:
            if f != keep:
                try:
                    f.unlink()
                    deleted += 1
                    freed += size
                    console.print(f"  [red]Deleted:[/red] {f}")
                except OSError as e:
                    console.print(f"  [red]Error:[/red] {e}")

    if deleted:
        console.print(f"\n[green]Deleted {deleted} file(s), freed {human_size(freed)}[/green]")
    else:
        console.print("[dim]Nothing deleted.[/dim]")


def delete_auto(groups, strategy="newest"):
    console.print(f"\n[bold yellow]Auto cleanup — keeping {strategy} in each group[/bold yellow]\n")
    deleted = 0
    freed = 0
    for files in groups:
        size = files[0].stat().st_size
        if strategy == "newest":
            keep = keep_newest(files)
        elif strategy == "oldest":
            keep = keep_oldest(files)
        else:
            keep = keep_shortest_path(files)

        console.print(f"[green]Keep:[/green] {keep}")
        for f in files:
            if f != keep:
                try:
                    f.unlink()
                    deleted += 1
                    freed += size
                    console.print(f"  [red]Delete:[/red] {f}")
                except OSError as e:
                    console.print(f"  [red]Error:[/red] {e}")

    console.print(f"\n[green]Deleted {deleted} file(s), freed {human_size(freed)}[/green]")


def move_duplicates(groups, dest_dir):
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    moved = 0
    for files in groups:
        for f in files[1:]:
            target = dest / f.name
            if target.exists():
                target = dest / f"{f.stem}_{moved}{f.suffix}"
            try:
                shutil.move(str(f), str(target))
                console.print(f"[yellow]Moved:[/yellow] {f} → {target}")
                moved += 1
            except OSError as e:
                console.print(f"[red]Error moving {f}: {e}[/red]")
    console.print(f"\n[green]Moved {moved} duplicate(s) to {dest}[/green]")


# ── Usage ─────────────────────────────────────────────────────────────────────

def usage():
    console.print("""
[bold cyan]Duplicate File Finder[/bold cyan]

  [yellow]dupefind[/yellow] <dir>                        Scan for duplicates
  [yellow]dupefind[/yellow] <dir> --delete               Interactive cleanup
  [yellow]dupefind[/yellow] <dir> --auto newest          Auto-keep newest, delete rest
  [yellow]dupefind[/yellow] <dir> --auto oldest          Auto-keep oldest
  [yellow]dupefind[/yellow] <dir> --auto shortest        Auto-keep shortest path
  [yellow]dupefind[/yellow] <dir> --move <dest>          Move duplicates to a folder
  [yellow]dupefind[/yellow] <dir> --export report.csv    Export report to CSV or JSON
  [yellow]dupefind[/yellow] <dir> --preset images        Only scan images
  [yellow]dupefind[/yellow] <dir> --preset videos        Only scan videos
  [yellow]dupefind[/yellow] <dir> --preset docs          Only scan documents
  [yellow]dupefind[/yellow] <dir> --ext .py .txt         Custom extensions
  [yellow]dupefind[/yellow] <dir> --min-size 1MB         Skip files under 1MB
  [yellow]dupefind[/yellow] <dir> --algo sha256          Use SHA256 instead of MD5
  [yellow]dupefind[/yellow] <dir> --sort count           Sort groups by copy count
  [yellow]dupefind[/yellow] <dir> --exclude node_modules Exclude a folder name
  [yellow]dupefind[/yellow] <dir> --no-color             Plain output

Presets: images, videos, docs, audio, code
""")


# ── Main ──────────────────────────────────────────────────────────────────────

def parse_size(s):
    s = s.strip().upper()
    multipliers = {"B": 1, "KB": 1024, "MB": 1024**2, "GB": 1024**3}
    for suffix, mult in multipliers.items():
        if s.endswith(suffix):
            return int(float(s[:-len(suffix)]) * mult)
    return int(s)


def main():
    args = sys.argv[1:]
    if not args or args[0] in ("--help", "-h", "help"):
        usage()
        return

    directory = args[0]
    do_delete = False
    auto_strategy = None
    move_dest = None
    export_path = None
    preset = None
    extensions = None
    min_size = 1
    algo = "md5"
    sort_by = "wasted"
    exclude_dirs = []

    i = 1
    while i < len(args):
        a = args[i]
        if a == "--delete":
            do_delete = True; i += 1
        elif a == "--auto" and i + 1 < len(args):
            auto_strategy = args[i + 1]; i += 2
        elif a == "--move" and i + 1 < len(args):
            move_dest = args[i + 1]; i += 2
        elif a == "--export" and i + 1 < len(args):
            export_path = args[i + 1]; i += 2
        elif a == "--preset" and i + 1 < len(args):
            preset = args[i + 1].lower(); i += 2
        elif a == "--ext":
            extensions = set()
            i += 1
            while i < len(args) and not args[i].startswith("--"):
                extensions.add(args[i].lower() if args[i].startswith(".") else f".{args[i].lower()}")
                i += 1
        elif a == "--min-size" and i + 1 < len(args):
            min_size = parse_size(args[i + 1]); i += 2
        elif a == "--algo" and i + 1 < len(args):
            algo = args[i + 1]; i += 2
        elif a == "--sort" and i + 1 < len(args):
            sort_by = args[i + 1]; i += 2
        elif a == "--exclude" and i + 1 < len(args):
            exclude_dirs.append(args[i + 1]); i += 2
        else:
            i += 1

    if preset and preset in SUPPORTED_PRESETS:
        extensions = SUPPORTED_PRESETS[preset]
        console.print(f"[cyan]Preset:[/cyan] {preset} ({len(extensions)} extensions)\n")

    duplicates = find_duplicates(directory, min_size, extensions, algo, exclude_dirs)
    groups = show(duplicates, sort_by)

    if export_path and duplicates:
        export_report(duplicates, export_path)

    if not groups:
        return

    if auto_strategy:
        delete_auto(groups, auto_strategy)
    elif move_dest:
        move_duplicates(groups, move_dest)
    elif do_delete:
        delete_interactive(groups)


if __name__ == "__main__":
    main()
