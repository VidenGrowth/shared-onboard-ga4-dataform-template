#!/usr/bin/env bash
# Clone or update shared-onboard-ga4-dataform-template and
# template-shared-ga4-dataform side by side. Missing repos are cloned; existing
# ones are pulled with --ff-only. With --force, a repo whose pull fails is reset
# to its origin default branch (drops local commits and changes).
#
#   ./sync_repos.sh                 # clone/pull into the parent folder of this repo
#   ./sync_repos.sh --dir ~/code    # clone/pull into another folder
#   ./sync_repos.sh --force         # if a pull fails, reset to origin
set -euo pipefail

REPOS=(
  "https://github.com/VidenGrowth/shared-onboard-ga4-dataform-template.git"
  "https://github.com/VidenGrowth/template-shared-ga4-dataform.git"
)

DIR="$(cd "$(dirname "$0")/.." && pwd)"
FORCE=0

usage() {
  sed -n '2,9p' "$0" | sed 's/^# \{0,1\}//'
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dir) DIR="${2:?--dir needs a path}"; shift 2 ;;
    --force|-f) FORCE=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

mkdir -p "$DIR"

# Hard-reset the repo to its remote default branch. Drops local commits and
# uncommitted changes to tracked files and removes untracked files (ignored
# files such as node_modules are kept).
force_sync() {
  # Explicit && chain: set -e is ignored inside functions called from `||`.
  local path="$1" branch
  git -C "$path" fetch --prune origin &&
    git -C "$path" remote set-head origin --auto >/dev/null &&
    branch="$(git -C "$path" symbolic-ref --short refs/remotes/origin/HEAD)" &&
    branch="${branch#origin/}" &&
    git -C "$path" checkout -f -B "$branch" "origin/$branch" &&
    git -C "$path" reset --hard "origin/$branch" &&
    git -C "$path" clean -fd
}

sync_repo() {
  local url="$1" name path
  name="$(basename "$url" .git)"
  path="$DIR/$name"

  echo "==> $name"
  if [[ ! -e "$path" ]]; then
    git clone "$url" "$path"
    return
  fi

  if ! git -C "$path" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    echo "    $path exists but is not a git repo; move it away and rerun." >&2
    return 1
  fi

  if git -C "$path" pull --ff-only --prune; then
    return
  fi

  if [[ $FORCE -eq 1 ]]; then
    echo "    Pull failed, resetting to origin (--force)."
    force_sync "$path"
  else
    echo "    Pull failed. Fix it manually, or rerun with --force to reset to origin" >&2
    echo "    (this drops local commits and uncommitted changes)." >&2
    return 1
  fi
}

failed=()
for url in "${REPOS[@]}"; do
  sync_repo "$url" || failed+=("$(basename "$url" .git)")
done

if [[ ${#failed[@]} -gt 0 ]]; then
  echo "Failed: ${failed[*]}" >&2
  exit 1
fi
echo "All repos are up to date in $DIR"
