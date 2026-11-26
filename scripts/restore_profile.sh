#!/bin/sh
# 新規セッション用: 保管済みのプロファイルをCL公式の設定パスへ復元する(既存があれば上書きしない)
D="$HOME/.claude/plugins/config/claude-for-legal"; S="$(cd "$(dirname "$0")/../profile" && pwd)"
mkdir -p "$D/commercial-legal"
[ -f "$D/commercial-legal/CLAUDE.md" ] || cp "$S/CLAUDE.md" "$D/commercial-legal/CLAUDE.md"
[ -f "$D/company-profile.md" ] || cp "$S/company-profile.md" "$D/company-profile.md"
echo "restored/checked: $D"
