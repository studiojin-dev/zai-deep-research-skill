#!/bin/sh
set -eu

SKILL_NAME="zai-deep-research"
DEFAULT_REPO="studiojin-dev/zai-deep-research-skill"
SCOPE="user"
LAYOUT="shared"
SOURCE_DIR=""
REPO="$DEFAULT_REPO"
REF="main"
FORCE="0"
DRY_RUN="0"

usage() {
  cat <<'EOF'
Usage:
  sh install.sh [--scope user|project] [--layout shared|gemini] [--source-dir <path>] [--repo <owner/repo>] [--ref <git-ref>] [--force] [--dry-run]

Options:
  --scope <user|project>   Install to ~/.agents/skills or ./.agents/skills
  --layout <shared|gemini> Choose shared Agent Skills layout or Gemini native layout
  --source-dir <path>      Install from an existing local skill directory
  --repo <owner/repo>      Download the skill from GitHub before installing
  --ref <git-ref>          Git ref used with --repo (default: main)
  --force                  Replace an existing installation at the destination
  --dry-run                Print the resolved install plan without copying files

Examples:
  sh install.sh --source-dir ./zai-deep-research --scope user
  sh install.sh --source-dir ./zai-deep-research --scope project
  sh install.sh --source-dir ./zai-deep-research --scope project --dry-run
  curl -fsSL https://raw.githubusercontent.com/studiojin-dev/zai-deep-research-skill/main/zai-deep-research/scripts/install.sh | sh -s -- --scope user

Exit codes:
  0  success
  1  invalid arguments or install failure
EOF
}

fail() {
  printf 'Error: %s\n' "$1" >&2
  exit 1
}

while [ $# -gt 0 ]; do
  case "$1" in
    --scope)
      [ $# -ge 2 ] || fail "--scope requires a value"
      SCOPE="$2"
      shift 2
      ;;
    --layout)
      [ $# -ge 2 ] || fail "--layout requires a value"
      LAYOUT="$2"
      shift 2
      ;;
    --client)
      [ $# -ge 2 ] || fail "--client requires a value"
      case "$2" in
        agents|shared)
          LAYOUT="shared"
          ;;
        gemini)
          LAYOUT="gemini"
          ;;
        *)
          fail "--client $2 is no longer inferred to a native path; use --layout shared or install manually"
          ;;
      esac
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
    --dry-run)
      DRY_RUN="1"
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

  case "$LAYOUT" in
    shared)
      printf '%s/.agents/skills\n' "$base"
      ;;
    gemini)
      printf '%s/.gemini/skills\n' "$base"
      ;;
    *)
      fail "--layout must be either shared or gemini"
      ;;
  esac
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
    [ -e "$SOURCE_DIR" ] || fail "source directory does not exist: $SOURCE_DIR"
    [ -d "$SOURCE_DIR" ] || fail "source directory is not a directory: $SOURCE_DIR"
    resolved="$(cd "$SOURCE_DIR" && pwd)"
    [ -f "$resolved/SKILL.md" ] || fail "source directory does not look like a skill: $resolved"
    printf '%s\n' "$resolved"
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

print_install_plan() {
  source_path="$1"
  dest_root="$2"
  dest_path="$3"
  action="install"
  if [ -e "$dest_path" ]; then
    if [ "$FORCE" = "1" ]; then
      action="replace"
    else
      action="blocked"
    fi
  fi

  printf 'Skill: %s\n' "$SKILL_NAME"
  printf 'Source: %s\n' "$source_path"
  printf 'Destination root: %s\n' "$dest_root"
  printf 'Destination path: %s\n' "$dest_path"
  printf 'Scope: %s\n' "$SCOPE"
  printf 'Layout: %s\n' "$LAYOUT"
  printf 'Action: %s\n' "$action"
}

SOURCE_PATH="$(resolve_source_dir)"

DEST_ROOT="$(resolve_destination_root)"
DEST_PATH="$DEST_ROOT/$SKILL_NAME"

if [ "$DRY_RUN" = "1" ]; then
  print_install_plan "$SOURCE_PATH" "$DEST_ROOT" "$DEST_PATH"
  exit 0
fi

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
printf 'Recommended next step: python %s/scripts/run.py --validate --client <codex|claude|opencode|gemini>\n' "$DEST_PATH"
