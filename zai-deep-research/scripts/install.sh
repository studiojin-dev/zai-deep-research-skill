#!/bin/sh
set -eu

SKILL_NAME="zai-deep-research"
DEFAULT_REPO="studiojin-dev/zai-deep-research-skill"
SCOPE="user"
LAYOUT="shared"
LAYOUT_EXPLICIT="0"
SOURCE_DIR=""
REPO="$DEFAULT_REPO"
REF="main"
FORCE="0"
DRY_RUN="0"

usage() {
  cat <<'EOF'
Usage:
  sh install.sh [--scope user|project] [--layout shared|codex|opencode|gemini|claude] [--source-dir <path>] [--repo <owner/repo>] [--ref <git-ref>] [--force] [--dry-run]

Options:
  --scope <user|project>   Shared layout supports user/project scope; native client layouts are user-scope only
  --layout <...>           Install only to the specified layout instead of prompting for each target
  --source-dir <path>      Install from an existing local skill directory
  --repo <owner/repo>      Download the skill from GitHub before installing
  --ref <git-ref>          Git ref used with --repo (default: main)
  --force                  Replace an existing installation at the destination
  --dry-run                Print the resolved install plan without copying files

Examples:
  sh install.sh --source-dir ./zai-deep-research --scope user
  sh install.sh --source-dir ./zai-deep-research --layout codex
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
      LAYOUT_EXPLICIT="1"
      shift 2
      ;;
    --client)
      [ $# -ge 2 ] || fail "--client requires a value"
      case "$2" in
        agents|shared)
          LAYOUT="shared"
          ;;
        codex)
          LAYOUT="codex"
          ;;
        opencode)
          LAYOUT="opencode"
          ;;
        gemini)
          LAYOUT="gemini"
          ;;
        claude|claude-code|claude_code)
          LAYOUT="claude"
          ;;
        *)
          fail "--client $2 is not supported; use --layout shared|codex|opencode|gemini|claude"
          ;;
      esac
      LAYOUT_EXPLICIT="1"
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
  case "$LAYOUT" in
    shared)
      if [ "$SCOPE" = "user" ]; then
        base="$HOME"
      elif [ "$SCOPE" = "project" ]; then
        base="$(pwd)"
      else
        fail "--scope must be either user or project"
      fi
      printf '%s/.agents/skills\n' "$base"
      ;;
    codex)
      [ "$SCOPE" = "user" ] || fail "--scope project is only supported for --layout shared"
      printf '%s/.codex/skills\n' "$HOME"
      ;;
    opencode)
      [ "$SCOPE" = "user" ] || fail "--scope project is only supported for --layout shared"
      printf '%s/.config/opencode/skills\n' "$HOME"
      ;;
    gemini)
      [ "$SCOPE" = "user" ] || fail "--scope project is only supported for --layout shared"
      printf '%s/.gemini/skills\n' "$HOME"
      ;;
    claude)
      [ "$SCOPE" = "user" ] || fail "--scope project is only supported for --layout shared"
      printf '%s/.claude/skills\n' "$HOME"
      ;;
    *)
      fail "--layout must be one of shared, codex, opencode, gemini, claude"
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

layout_label() {
  case "$1" in
    shared)
      printf '.agents shared skills'
      ;;
    codex)
      printf 'Codex'
      ;;
    opencode)
      printf 'OpenCode'
      ;;
    gemini)
      printf 'Gemini'
      ;;
    claude)
      printf 'Claude Code'
      ;;
    *)
      printf '%s' "$1"
      ;;
  esac
}

confirm_install() {
  layout_name="$1"
  if [ ! -t 0 ]; then
    return 0
  fi

  while true; do
    printf 'Install to %s? [y/N] ' "$(layout_label "$layout_name")"
    IFS= read -r answer || return 1
    case "$answer" in
      y|Y|yes|YES)
        return 0
        ;;
      n|N|no|NO|'')
        return 1
        ;;
      *)
        printf 'Please answer y or n.\n' >&2
        ;;
    esac
  done
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

install_single_target() {
  layout_name="$1"
  LAYOUT="$layout_name"
  dest_root="$(resolve_destination_root)"
  dest_path="$dest_root/$SKILL_NAME"

  if [ "$DRY_RUN" = "1" ]; then
    print_install_plan "$SOURCE_PATH" "$dest_root" "$dest_path"
    return 0
  fi

  mkdir -p "$dest_root"

  if [ -e "$dest_path" ]; then
    if [ "$FORCE" = "1" ]; then
      rm -rf "$dest_path"
    else
      fail "destination already exists: $dest_path (use --force to replace)"
    fi
  fi

  cp -R "$SOURCE_PATH" "$dest_path"
  cleanup_generated_files "$dest_path"

  printf 'Installed %s to %s\n' "$SKILL_NAME" "$dest_path"
}

install_interactive_targets() {
  selected_count="0"
  for layout_name in shared codex opencode gemini claude; do
    if confirm_install "$layout_name"; then
      install_single_target "$layout_name"
      selected_count=$((selected_count + 1))
    fi
  done

  if [ "$selected_count" -eq 0 ]; then
    printf 'No installation targets selected.\n'
    return 0
  fi

  printf 'Recommended next step: validate one installed target, for example:\n'
  printf '  python ~/.codex/skills/%s/scripts/run.py --validate --client codex\n' "$SKILL_NAME"
}

SOURCE_PATH="$(resolve_source_dir)"

if [ "$LAYOUT_EXPLICIT" = "1" ]; then
  install_single_target "$LAYOUT"
  DEST_ROOT="$(resolve_destination_root)"
  DEST_PATH="$DEST_ROOT/$SKILL_NAME"
  if [ "$DRY_RUN" = "0" ]; then
    printf 'Recommended next step: python %s/scripts/run.py --validate --client <codex|claude|opencode|gemini>\n' "$DEST_PATH"
  fi
  exit 0
fi

install_interactive_targets
