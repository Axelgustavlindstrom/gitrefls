# gitrefls

Inspect Git reflog activity, branch drift, and reachability summaries.

## Installation

```bash
pip install gitrefls
```

## Usage

```bash
gitrefls status --repo /path/to/repo
gitrefls show --repo /path/to/repo refs/heads/main
```

## Features

- Inspect current ref targets and recent reflog activity
- Summarize branch, tag, and remote ref counts
- Export reflog activity as JSON for downstream tooling

## Development

```bash
git clone https://github.com/Axelgustavlindstrom/gitrefls.git
cd gitrefls
python -m venv .venv
source .venv/bin/activate
pip install -e .
pytest
```

## License

MIT
