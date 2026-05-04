#!/bin/bash
#
# macOS NTFS 读写挂载工具 - 一键依赖安装脚本
#
# 安装: macFUSE + ntfs-3g
# 用法: bash setup.sh
#
set -euo pipefail

# ── 颜色 ──
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

info()  { echo -e "${CYAN}[INFO]${NC}  $1"; }
ok()    { echo -e "${GREEN}[OK]${NC}    $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $1"; }
err()   { echo -e "${RED}[ERROR]${NC} $1"; }
section() { echo; echo -e "${CYAN}══════════════════════════════════════════════${NC}"; echo -e "${CYAN}  $1${NC}"; echo -e "${CYAN}══════════════════════════════════════════════${NC}"; }


# ── 1. 检测架构 ──

section "系统检测"

ARCH=$(uname -m)
info "系统架构: ${ARCH}"

if [[ "$(uname)" != "Darwin" ]]; then
    err "此脚本仅适用于 macOS。当前系统: $(uname)"
    exit 1
fi

OS_VERSION=$(sw_vers -productVersion 2>/dev/null || echo "unknown")
info "macOS 版本: ${OS_VERSION}"


# ── 2. Homebrew ──

section "检测 Homebrew"

BREW=""
if command -v brew &>/dev/null; then
    BREW="brew"
    ok "Homebrew 已安装 ($(brew --version | head -1))"
else
    warn "Homebrew 未安装"
    info "正在安装 Homebrew..."
    echo
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    echo

    # 重新检测 brew（Apple Silicon 需要 eval）
    if command -v brew &>/dev/null; then
        BREW="brew"
    elif [[ -x /opt/homebrew/bin/brew ]]; then
        eval "$(/opt/homebrew/bin/brew shellenv)"
        BREW="brew"
    elif [[ -x /usr/local/bin/brew ]]; then
        BREW="/usr/local/bin/brew"
    else
        err "Homebrew 安装失败，请手动安装后重试。"
        err "安装命令:"
        err '  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"'
        exit 1
    fi
    ok "Homebrew 安装完成"
fi


# ── 3. macFUSE ──

section "安装 macFUSE"

if pkgutil --pkgs 2>/dev/null | grep -qi 'macfuse'; then
    ok "macFUSE 已安装"
else
    info "正在安装 macFUSE (需要管理员权限)..."

    # macFUSE cask 安装
    if ! $BREW install --cask macfuse 2>/dev/null; then
        warn "Homebrew 安装 macFUSE 失败，尝试手动安装..."
        warn "请访问 https://macfuse.io/ 下载安装"
        warn "或使用: brew install --cask macfuse"
    else
        ok "macFUSE 安装完成"
    fi

    echo
    warn "============================================================"
    warn "  macFUSE 安装后可能需要额外操作:"
    warn "    1. 打开「系统设置 > 隐私与安全性」"
    warn "    2. 点击「允许」以允许 macFUSE 内核扩展"
    warn "    3. 如果提示重启，请重启 Mac"
    warn "============================================================"
fi


# ── 4. ntfs-3g ──

section "安装 ntfs-3g"

if command -v ntfs-3g &>/dev/null; then
    ok "ntfs-3g 已安装 ($(command -v ntfs-3g))"
else
    # 检查常见路径
    NTFS3G=""
    for p in /usr/local/bin/ntfs-3g /opt/homebrew/bin/ntfs-3g; do
        if [[ -x "$p" ]]; then
            NTFS3G="$p"
            break
        fi
    done

    if [[ -n "$NTFS3G" ]]; then
        ok "ntfs-3g 已安装 ($NTFS3G)"
    else
        info "正在安装 ntfs-3g..."
        $BREW install ntfs-3g

        echo
        # 验证安装
        FOUND=""
        for p in /usr/local/bin/ntfs-3g /opt/homebrew/bin/ntfs-3g; do
            if [[ -x "$p" ]]; then
                FOUND="$p"
                break
            fi
        done

        if command -v ntfs-3g &>/dev/null; then
            FOUND="$(command -v ntfs-3g)"
        fi

        if [[ -n "$FOUND" ]]; then
            ok "ntfs-3g 安装完成 ($FOUND)"
        else
            err "ntfs-3g 安装失败，请手动运行: brew install ntfs-3g"
            exit 1
        fi
    fi
fi


# ── 5. 验证 ──

section "验证安装"

NTFS3G_PATH=""
FUSE_OK=false

# 检查 ntfs-3g
for p in /usr/local/bin/ntfs-3g /opt/homebrew/bin/ntfs-3g; do
    if [[ -x "$p" ]]; then
        NTFS3G_PATH="$p"
        break
    fi
done
if command -v ntfs-3g &>/dev/null && [[ -z "$NTFS3G_PATH" ]]; then
    NTFS3G_PATH="$(command -v ntfs-3g)"
fi

if [[ -n "$NTFS3G_PATH" ]]; then
    ok "ntfs-3g: $NTFS3G_PATH"
else
    err "ntfs-3g: 未找到"
fi

# 检查 macFUSE
if pkgutil --pkgs 2>/dev/null | grep -qi 'macfuse'; then
    ok "macFUSE: 已安装 (pkgutil)"
    FUSE_OK=true
elif [[ -d /Library/Filesystems/macfuse.fs ]]; then
    ok "macFUSE: 已安装 (文件系统插件)"
    FUSE_OK=true
else
    err "macFUSE: 未检测到"
fi

echo
echo -e "${CYAN}──────────────────────────────────────────────────────${NC}"
if [[ -n "$NTFS3G_PATH" ]] && $FUSE_OK; then
    echo -e "${GREEN}  所有依赖已就绪！${NC}"
    echo
    echo "  启动工具:"
    echo -e "    ${CYAN}python3 ntfs_mounter.py${NC}"
elif [[ -z "$NTFS3G_PATH" ]]; then
    echo -e "${YELLOW}  ntfs-3g 未安装，请运行: brew install ntfs-3g${NC}"
fi
if ! $FUSE_OK; then
    echo -e "${YELLOW}  macFUSE 未完全就绪，请检查系统设置中是否已允许${NC}"
fi
echo -e "${CYAN}──────────────────────────────────────────────────────${NC}"
echo
