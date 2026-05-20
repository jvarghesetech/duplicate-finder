import sys
import hashlib
from pathlib import Path
from collections import defaultdict

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich import box
except ImportError:
    print("Run: pip install rich")
    sys.exit(1)

console = Console()


def file_hash(path, chunk_size=8192):
    h = hashlib.md5()
    try:
        with open(path, "rb") as f:
            while chunk := f.read(chunk_size):
                h.update(chunk)
        return h.hexdigest()
    except (PermissionError, OSError):
        return None


def human_size(size):
    for unit in ["B", "KB", "MB", "GB"]:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def find_duplicates(directory, min_size=1):
    path = Path(directory)
    if not path.exists():
        console.print(f"[red]Directory not found: {directory}[/red]")
        sys.exit(1)

    console.print(f"[cyan]Scanning[/cyan] {path.resolve()}...")

    by_size = defaultdict(list)
    total = 0

    with console.status("Indexing files..."):
        for f in path.rglob("*"):
            if f.is_file():
                try:
                    size = f.stat().st_size
                    if size >= min_size:
                        by_size[size].append(f)
                        total += 1
                except OSError:
                    pass

    console.print(f"Found [bold]{total}[/bold] files. Checking for duplicates...\n")

    by_hash = defaultdict(list)
    candidates = [files for files in by_size.values() if len(files) > 1]

    with console.status("Hashing files..."):
        for files in candidates:
            for f in files:
                h = file_hash(f)
                if h:
                    by_hash[h].append(f)

    return {h: files for h, files in by_hash.items() if len(files) > 1}


def show(duplicates):
    if not duplicates:
        console.print("[green]No duplicate files found![/green]")
        return []

    groups = sorted(
        duplicates.values(),
        key=lambda fs: fs[0].stat().st_size * (len(fs) - 1),
        reverse=True,
    )
    total_wasted = 0

    for i, files in enumerate(groups, 1):
        size = files[0].stat().st_size
        wasted = size * (len(files) - 1)
        total_wasted += wasted

        table = Table(
            title=f"Group {i} — {len(files)} files — {human_size(size)} each — [red]{human_size(wasted)} wasted[/red]",
            box=box.SIMPLE,
            header_style="bold",
        )
        table.add_column("#", width=4)
        table.add_column("Path")
        table.add_column("Size", justify="right", width=10)

        for j, f in enumerate(files):
            table.add_row(str(j + 1), str(f), human_size(size))

        console.print(table)

    console.print(Panel(
        f"[bold red]{len(duplicates)} duplicate group(s)[/bold red]   "
        f"Wasted space: [bold red]{human_size(total_wasted)}[/bold red]",
        title="Summary",
    ))

    return groups


def delete_interactive(groups):
    console.print("\n[bold yellow]Interactive Cleanup[/bold yellow]")
    console.print("For each group, keep the FIRST file and delete the rest.\n")

    deleted = 0
    freed = 0

    for i, files in enumerate(groups, 1):
        size = files[0].stat().st_size
        console.print(f"[bold]Group {i}:[/bold] Keep [green]{files[0].name}[/green], delete {len(files) - 1} duplicate(s)?")
        ans = input("  (y/n/s to skip all): ").strip().lower()

        if ans == "s":
            break
        if ans == "y":
            for f in files[1:]:
                try:
                    f.unlink()
                    deleted += 1
                    freed += size
                    console.print(f"  [red]Deleted:[/red] {f}")
                except OSError as e:
                    console.print(f"  [red]Error deleting {f}: {e}[/red]")

    if deleted:
        console.print(f"\n[green]Deleted {deleted} file(s), freed {human_size(freed)}[/green]")
    else:
        console.print("[dim]Nothing deleted.[/dim]")


def main():
    args = sys.argv[1:]
    if not args:
        console.print("Usage: dupefind <directory> [--delete]")
        console.print("  --delete    Interactive cleanup mode")
        sys.exit(1)

    directory = args[0]
    do_delete = "--delete" in args

    duplicates = find_duplicates(directory)
    groups = show(duplicates)

    if do_delete and groups:
        delete_interactive(groups)


if __name__ == "__main__":
    main()
