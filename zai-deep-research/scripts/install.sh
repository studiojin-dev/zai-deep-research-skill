#!/bin/sh
set -eu

SKILL_NAME="zai-deep-research"
DEFAULT_REPO="studiojin-dev/zai-deep-research-skill"
CLIENT="agents"
SCOPE="user"
SOURCE_DIR=""
REPO="$DEFAULT_REPO"
REF="main"
FORCE="0"

usage() {
  cat <<'EOF'
Usage:
  sh install.sh [--client <name>] [--scope user|project] [--source-dir <path>] [--repo <owner/repo>] [--ref <git-ref>] [--force]

Examples:
  sh install.sh --source-dir ./zai-deep-research --client agents --scope user
  curl -fsSL https://raw.githubusercontent.com/studiojin-dev/zai-deep-research-skill/main/zai-deep-research/scripts/install.sh | sh -s -- --client codex --scope user
EOF
}

fail() {
  printf 'Error: %s\n' "$1" >&2
  exit 1
}

while [ $# -gt 0 ]; do
  case "$1" in
    --client)
      [ $# -ge 2 ] || fail "--client requires a value"
      CLIENT="$2"
      shift 2
      ;;
    --scope)
      [ $# -ge 2 ] || fail "--scope requires a value"
      SCOPE="$2"
      shift 2
      ;;
    --source-dir)
      [ $# -ge 2 ] || fail "--source-dir requires a value"
      SOURCE_DIR="$2"
      shift 2
      ;;
    --repo)
      [ $# -ge 2 ] || fail "--repo requires a value"
      REPO="$2"
      shift 2
      ;;
    --ref)
      [ $# -ge 2 ] || fail "--ref requires a value"
      REF="$2"
      shift 2
      ;;
    --force)
      FORCE="1"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      fail "unknown argument: $1"
      ;;
  esac
done

resolve_destination_root() {
  if [ "$SCOPE" = "user" ]; then
    base="$HOME"
  elif [ "$SCOPE" = "project" ]; then
    base="$(pwd)"
  else
    fail "--scope must be either user or project"
  fi

  if [ "$CLIENT" = "agents" ]; then
    printf '%s/.agents/skills\n' "$base"
  else
    printf '%s/.%s/skills\n' "$base" "$CLIENT"
  fi
}

download_source() {
  tmpdir="$(mktemp -d)"
  archive_path="$tmpdir/source.tar.gz"
  archive_url="https://codeload.github.com/$REPO/tar.gz/$REF"

  curl -fsSL "$archive_url" -o "$archive_path"
  tar -xzf "$archive_path" -C "$tmpdir"

  extracted_root="$(find "$tmpdir" -mindepth 1 -maxdepth 1 -type d | head -n 1)"
  [ -n "$extracted_root" ] || fail "could not extract repository archive"

  found="$(find "$extracted_root" -type d -name "$SKILL_NAME" | head -n 1)"
  [ -n "$found" ] || fail "could not find $SKILL_NAME in downloaded repository"
  printf '%s\n' "$found"
}

resolve_source_dir() {
  if [ -n "$SOURCE_DIR" ]; then
    printf '%s\n' "$(cd "$SOURCE_DIR" && pwd)"
    return
  fi

  if [ -n "$REPO" ]; then
    download_source
    return
  fi

  fail "provide either --source-dir or --repo"
}

cleanup_generated_files() {
  target="$1"
  find "$target" \( -name '__pycache__' -o -name '.DS_Store' -o -name '*.pyc' \) -exec rm -rf {} + 2>/dev/null || true
}

SOURCE_PATH="$(resolve_source_dir)"
[ -f "$SOURCE_PATH/SKILL.md" ] || fail "source directory does not look like a skill: $SOURCE_PATH"

DEST_ROOT="$(resolve_destination_root)"
DEST_PATH="$DEST_ROOT/$SKILL_NAME"

mkdir -p "$DEST_ROOT"

if [ -e "$DEST_PATH" ]; then
  if [ "$FORCE" = "1" ]; then
    rm -rf "$DEST_PATH"
  else
    fail "destination already exists: $DEST_PATH (use --force to replace)"
  fi
fi

cp -R "$SOURCE_PATH" "$DEST_PATH"
cleanup_generated_files "$DEST_PATH"

printf 'Installed %s to %s\n' "$SKILL_NAME" "$DEST_PATH"
printf 'Next step: python %s/scripts/run.py --validate\n' "$DEST_PATH"
