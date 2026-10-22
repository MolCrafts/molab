#!/usr/bin/env bash
# CLI command tour — molab workspace, project, experiment, run, asset, config.
#
# Matches ``docs/guide/workspace-architecture.md`` and related CLI docs.
#
# Creates a temporary workspace, runs key CLI commands against it,
# and cleans up. Self-contained — no setup needed.
#
# Run directly::
#
#     bash examples/cli/commands.sh

set -euo pipefail

# ── Temporary workspace ───────────────────────────────────────────────────────
WS=$(mktemp -d 2>/dev/null || mktemp -d -t molab-cli)
cleanup() { rm -rf "$WS"; }
trap cleanup EXIT

echo "Workspace: $WS"

# ── Init ──────────────────────────────────────────────────────────────────────
molab init "$WS" 2>&1

# ── Info ──────────────────────────────────────────────────────────────────────
echo ""
echo "── molab info ────────────────────────────────────────────"
molab info --workspace "$WS" 2>&1 || true

# ── Project create + list ─────────────────────────────────────────────────────
echo ""
echo "── molab project create ──────────────────────────────────"
molab project create --workspace "$WS" "demo" 2>&1 || true

echo ""
echo "── molab project list ────────────────────────────────────"
molab project list --workspace "$WS" 2>&1 || true

# ── Experiment create + list ──────────────────────────────────────────────────
echo ""
echo "── molab experiment create ───────────────────────────────"
molab experiment create --workspace "$WS" --name "baseline" "demo" 2>&1 || true

echo ""
echo "── molab experiment list ─────────────────────────────────"
molab experiment list --workspace "$WS" "demo" 2>&1 || true

# ── Runs ──────────────────────────────────────────────────────────────────────
echo ""
echo "── molab runs list ───────────────────────────────────────"
molab runs list --workspace "$WS" "demo" "baseline" 2>&1 || true

# ── Asset list ────────────────────────────────────────────────────────────────
echo ""
echo "── molab asset list ──────────────────────────────────────"
molab asset list --workspace "$WS" 2>&1 || true

# ── Final info ────────────────────────────────────────────────────────────────
echo ""
echo "── molab info (summary) ──────────────────────────────────"
molab info --workspace "$WS" 2>&1 || true

echo ""
echo "Done — all CLI commands completed."
