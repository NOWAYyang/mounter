#!/usr/bin/env python3
"""
macOS NTFS 读写挂载工具

基于 macFUSE + ntfs-3g，提供图形界面挂载 NTFS 外部硬盘为读写模式。
替代 Paragon NTFS / Tuxera 等商业软件。

用法:
    python3 ntfs_mounter.py

依赖:
    - macFUSE (Homebrew cask)
    - ntfs-3g (Homebrew)
"""

import os
import re
import sys
import subprocess
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
from pathlib import Path
from typing import Any, Optional


# ═══════════════════════════════════════════════════════════════
# 1. 依赖检查模块
# ═══════════════════════════════════════════════════════════════

def find_ntfs3g() -> Optional[str]:
    """查找 ntfs-3g 可执行文件路径"""
    # 常见安装路径（Intel / Apple Silicon / MacPorts）
    candidates = [
        '/usr/local/bin/ntfs-3g',
        '/opt/homebrew/bin/ntfs-3g',
        '/opt/local/bin/ntfs-3g',
        '/usr/local/sbin/ntfs-3g',
        '/opt/homebrew/sbin/ntfs-3g',
    ]
    for p in candidates:
        if os.path.isfile(p) and os.access(p, os.X_OK):
            return p
    # 回退：通过 PATH 查找
    try:
        result = subprocess.run(
            ['which', 'ntfs-3g'],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            path = result.stdout.strip()
            if path:
                return path
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return None


def check_macfuse() -> bool:
    """检查 macFUSE 是否已安装"""
    # 方法 1: pkgutil 查询
    try:
        result = subprocess.run(
            ['pkgutil', '--pkgs'],
            capture_output=True, text=True, timeout=10
        )
        output = result.stdout.lower()
        if any(kw in output for kw in ('io.macfuse', 'com.github.macfuse',
                                        'io.macfuse.macfuse')):
            return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # 方法 2: 检查文件系统插件
    fuse_paths = [
        '/Library/Filesystems/macfuse.fs',
        '/Library/Filesystems/osxfuse.fs',
    ]
    if any(Path(p).exists() for p in fuse_paths):
        return True

    # 方法 3: 检查已加载的内核扩展
    try:
        result = subprocess.run(
            ['kextstat'], capture_output=True, text=True, timeout=5
        )
        if 'macfuse' in result.stdout.lower():
            return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    return False


def check_dependencies() -> tuple[Optional[str], bool]:
    """检查依赖，返回 (ntfs-3g 路径, macFUSE 是否就绪)"""
    return find_ntfs3g(), check_macfuse()


# ═══════════════════════════════════════════════════════════════
# 2. 权限执行模块
# ═══════════════════════════════════════════════════════════════

def run_with_admin(cmd: str) -> tuple[str, str, int]:
    """使用 osascript 弹出 macOS 原生密码框执行命令。

    利用 sudo 的 5 分钟凭证缓存，短时间多次调用无需重复输入密码。

    Args:
        cmd: 需要以管理员权限执行的 shell 命令

    Returns:
        (stdout, stderr, returncode)
        returncode:  0 = 成功, 1 = 命令失败, -1 = 异常/超时, -2 = 用户取消
    """
    # 转义双引号和反斜杠（AppleScript 字符串字面量要求）
    escaped = cmd.replace('\\', '\\\\').replace('"', '\\"')
    script = (
        'do shell script "' + escaped + '" '
        'with administrator privileges '
        'without altering line endings'
    )
    try:
        proc = subprocess.run(
            ['osascript', '-e', script],
            capture_output=True, text=True,
            timeout=120
        )
        stderr_lower = proc.stderr.lower()
        if proc.returncode != 0 and ('cancel' in stderr_lower
                                      or 'authorization' in stderr_lower):
            return proc.stdout, proc.stderr, -2
        return proc.stdout, proc.stderr, proc.returncode
    except subprocess.TimeoutExpired:
        return '', '操作超时（120 秒）', -1
    except FileNotFoundError:
        return '', 'osascript 未找到，macOS 系统异常', -1
    except Exception as e:
        return '', str(e), -1


# ═══════════════════════════════════════════════════════════════
# 3. 磁盘信息模块
# ═══════════════════════════════════════════════════════════════

def get_ntfs_disks() -> list[dict[str, Any]]:
    """扫描外部 NTFS 磁盘。

    解析 diskutil list external 和 diskutil info，
    返回符合以下结构的列表：
        [
            {"identifier": "/dev/disk4s1", "name": "MyDrive",
             "mounted": True, "mount_point": "/Volumes/MyDrive"},
            ...
        ]
    """
    disks: list[dict[str, Any]] = []

    # 获取外部磁盘列表
    try:
        result = subprocess.run(
            ['diskutil', 'list', 'external'],
            capture_output=True, text=True, timeout=15
        )
        if result.returncode != 0:
            return disks
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return disks

    # 扫描每个分区标识符（形如 disk4s1, disk5s2）
    partition_ids: list[str] = []
    for line in result.stdout.splitlines():
        m = re.search(r'\b(disk\d+s\d+)\s*$', line)
        if m:
            partition_ids.append(m.group(1))

    for pid in partition_ids:
        info = _query_disk_info(pid)
        if info is None:
            continue
        if not _is_ntfs(info):
            continue

        disks.append({
            'identifier': '/dev/' + pid,
            'name': info.get('name', pid),
            'mounted': info.get('mounted', False),
            'mount_point': info.get('mount_point', ''),
        })

    return disks


def _query_disk_info(identifier: str) -> Optional[dict[str, Any]]:
    """查询单个分区的详细信息"""
    try:
        result = subprocess.run(
            ['diskutil', 'info', '/dev/' + identifier],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode != 0:
            return None
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None

    text = result.stdout
    info: dict[str, Any] = {}

    # 卷宗名称
    m = re.search(r'Volume Name:\s+(.+)', text)
    if m:
        info['name'] = m.group(1).strip()

    # 文件系统类型
    if re.search(r'File System Personality:\s+NTFS', text,
                 re.IGNORECASE):
        info['fs'] = 'NTFS'
    elif re.search(r'Type \(Bundle\):\s+ntfs', text, re.IGNORECASE):
        info['fs'] = 'NTFS'
    else:
        info['fs'] = 'OTHER'

    # 挂载状态
    info['mounted'] = bool(re.search(r'Mounted:\s+Yes', text))

    # 挂载点
    m = re.search(r'Mount Point:\s+(.+)', text)
    if m:
        info['mount_point'] = m.group(1).strip()

    return info


def _is_ntfs(info: dict[str, Any]) -> bool:
    """判断是否为 NTFS 文件系统"""
    return info.get('fs') == 'NTFS'


# ═══════════════════════════════════════════════════════════════
# 4. 挂载操作模块
# ═══════════════════════════════════════════════════════════════

def unmount_disk(identifier: str) -> tuple[bool, str]:
    """卸载磁盘（解除系统只读挂载）。

    Returns:
        (是否成功, 消息)
    """
    try:
        result = subprocess.run(
            ['diskutil', 'unmount', identifier],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0:
            return True, '卸载成功'
        else:
            return False, result.stderr.strip() or '卸载失败'
    except subprocess.TimeoutExpired:
        return False, '卸载超时'
    except FileNotFoundError:
        return False, 'diskutil 未找到'


def mount_ntfs(
    ntfs3g_path: str,
    identifier: str,
    mount_point: str,
) -> tuple[bool, str]:
    """使用 ntfs-3g 挂载 NTFS 分区为读写模式。

    Args:
        ntfs3g_path: ntfs-3g 可执行文件路径
        identifier:  设备标识符，如 /dev/disk4s1
        mount_point: 挂载点路径，如 /Volumes/MyDrive

    Returns:
        (是否成功, 消息)
    """
    # ntfs-3g 挂载选项：
    #   local        - 本地文件系统
    #   allow_other  - 允许所有用户访问
    #   auto_xattr   - 支持扩展属性
    #   auto_cache   - 自动缓存
    #   volname      - 指定卷名（显示在 Finder 中）
    volname = os.path.basename(mount_point)

    # 将 mkdir 和 mount 合并在一个管理员命令中执行，
    # 避免 /Volumes 目录权限问题
    cmd = (
        f'mkdir -p "{mount_point}" && '
        f'{ntfs3g_path} "{identifier}" "{mount_point}" '
        f'-o local -o allow_other -o auto_xattr '
        f'-o auto_cache -o volname="{volname}"'
    )

    stdout, stderr, rc = run_with_admin(cmd)

    if rc == -2:
        return False, '已取消操作'
    if rc == 0:
        return True, '挂载成功'
    else:
        error_msg = stderr.strip() or stdout.strip() or '未知错误'
        return False, error_msg


# ═══════════════════════════════════════════════════════════════
# 5. GUI 类
# ═══════════════════════════════════════════════════════════════

class NTFSMounter:
    """主窗口 GUI"""

    def __init__(
        self,
        ntfs3g_path: Optional[str],
        macfuse_ok: bool,
    ) -> None:
        self.ntfs3g_path = ntfs3g_path
        self.macfuse_ok = macfuse_ok
        self.disks: list[dict[str, Any]] = []

        self.window = tk.Tk()
        self.window.title('NTFS 读写挂载工具')
        self.window.geometry('700x540')
        self.window.minsize(600, 420)

        # macOS 窗口置前
        if sys.platform == 'darwin':
            self.window.lift()
            self.window.attributes('-topmost', True)
            self.window.after_idle(self.window.attributes, '-topmost', False)

        self._build_ui()
        self._update_dep_status()
        self.refresh_disks()

    # ── 界面构建 ──

    def _build_ui(self) -> None:
        """构建所有界面控件"""
        self._build_header()
        self._build_disk_list()
        self._build_buttons()
        self._build_log_area()
        self._build_status_bar()

    def _build_header(self) -> None:
        header = ttk.Frame(self.window, padding=(12, 10, 12, 4))
        header.pack(fill=tk.X)

        title = ttk.Label(
            header, text='NTFS 读写挂载工具',
            font=('', 16, 'bold'),
        )
        title.pack(side=tk.LEFT)

        subtitle = ttk.Label(
            header, text='基于 macFUSE + ntfs-3g',
            foreground='gray', font=('', 10),
        )
        subtitle.pack(side=tk.LEFT, padx=(8, 0))

    def _build_disk_list(self) -> None:
        list_frame = ttk.Frame(self.window, padding=(12, 4))
        list_frame.pack(fill=tk.BOTH, expand=True)

        columns = ('name', 'identifier', 'mount_point', 'status')
        self.tree = ttk.Treeview(
            list_frame,
            columns=columns,
            show='headings',
            selectmode='browse',
            height=8,
        )
        self.tree.heading('name', text='卷宗名称')
        self.tree.heading('identifier', text='标识符')
        self.tree.heading('mount_point', text='挂载点')
        self.tree.heading('status', text='状态')

        self.tree.column('name', width=180, minwidth=100)
        self.tree.column('identifier', width=110, minwidth=80)
        self.tree.column('mount_point', width=180, minwidth=80)
        self.tree.column('status', width=100, minwidth=60)

        scrollbar = ttk.Scrollbar(
            list_frame, orient=tk.VERTICAL, command=self.tree.yview,
        )
        self.tree.configure(yscrollcommand=scrollbar.set)

        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # 双击挂载
        self.tree.bind('<Double-1>', lambda e: self.mount_selected())

    def _build_buttons(self) -> None:
        btn_frame = ttk.Frame(self.window, padding=(12, 6))
        btn_frame.pack(fill=tk.X)

        self.refresh_btn = ttk.Button(
            btn_frame, text='刷新列表',
            command=self.refresh_disks,
        )
        self.refresh_btn.pack(side=tk.LEFT, padx=(0, 6))

        self.mount_btn = ttk.Button(
            btn_frame, text='挂载选中磁盘',
            command=self.mount_selected,
        )
        self.mount_btn.pack(side=tk.LEFT, padx=6)

        self.open_btn = ttk.Button(
            btn_frame, text='在 Finder 中打开',
            command=self.open_in_finder,
        )
        self.open_btn.pack(side=tk.LEFT, padx=6)

        # 弹性空间
        ttk.Frame(btn_frame).pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.about_btn = ttk.Button(
            btn_frame, text='关于',
            command=self._show_about,
        )
        self.about_btn.pack(side=tk.RIGHT, padx=(6, 0))

    def _build_log_area(self) -> None:
        log_frame = ttk.Frame(self.window, padding=(12, 0, 12, 4))
        log_frame.pack(fill=tk.BOTH, expand=False)

        self.log_text = scrolledtext.ScrolledText(
            log_frame,
            height=7,
            state=tk.DISABLED,
            font=('Menlo', 10),
            wrap=tk.WORD,
            relief=tk.SUNKEN,
            borderwidth=1,
        )
        self.log_text.pack(fill=tk.BOTH, expand=True)

    def _build_status_bar(self) -> None:
        status_frame = ttk.Frame(self.window, padding=(12, 4, 12, 8))
        status_frame.pack(fill=tk.X)

        self.status_label = ttk.Label(
            status_frame, text='就绪',
            font=('', 10),
        )
        self.status_label.pack(side=tk.LEFT)

        self.dep_label = ttk.Label(
            status_frame, text='',
            font=('', 9), foreground='gray',
        )
        self.dep_label.pack(side=tk.RIGHT)

    # ── 状态更新 ──

    def _update_dep_status(self) -> None:
        """更新底部依赖状态指示"""
        ntfs_ok = self.ntfs3g_path is not None
        parts = [
            f'ntfs-3g: {"✓" if ntfs_ok else "✗"}',
            f'macFUSE: {"✓" if self.macfuse_ok else "✗"}',
        ]
        self.dep_label.config(text=' | '.join(parts))

        if not ntfs_ok or not self.macfuse_ok:
            self.mount_btn.config(state=tk.DISABLED)
            self._log(
                '缺少必要依赖，请运行: bash setup.sh'
            )
        else:
            self._log(f'ntfs-3g 路径: {self.ntfs3g_path}')

    def _log(self, message: str) -> None:
        """向日志区域追加消息"""
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, message + '\n')
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)

    def _set_status(self, message: str) -> None:
        """更新状态栏"""
        self.status_label.config(text=message)

    def _show_about(self) -> None:
        messagebox.showinfo(
            '关于',
            'macOS NTFS 读写挂载工具\n'
            '基于 macFUSE + ntfs-3g\n\n'
            '免费开源的 NTFS 读写方案\n'
            '替代 Paragon NTFS / Tuxera 等商业软件',
        )

    # ── 核心功能 ──

    def refresh_disks(self) -> None:
        """刷新磁盘列表"""
        self._set_status('正在扫描 NTFS 磁盘...')
        self._log('扫描外部磁盘...')

        # 清空现有列表
        for item in self.tree.get_children():
            self.tree.delete(item)

        self.disks = get_ntfs_disks()

        if not self.disks:
            self.open_btn.config(state=tk.DISABLED)
            self.tree.insert('', tk.END, values=(
                '未检测到 NTFS 磁盘', '', '',
                '请连接外部硬盘后点击刷新',
            ))
            self._set_status('未检测到 NTFS 磁盘')
            self._log('未检测到 NTFS 格式的外部磁盘')
            self.mount_btn.config(state=tk.DISABLED)
            return

        for disk in self.disks:
            if disk['mounted']:
                status = '已挂载（只读）'
            else:
                status = '未挂载'
            self.tree.insert('', tk.END, values=(
                disk['name'],
                disk['identifier'],
                disk['mount_point'],
                status,
            ))

        self._set_status(f'检测到 {len(self.disks)} 个 NTFS 磁盘')
        self._log(f'检测到 {len(self.disks)} 个 NTFS 磁盘')
        self.mount_btn.config(state=tk.NORMAL)

    def mount_selected(self) -> None:
        """挂载选中的 NTFS 磁盘为读写模式"""
        selection = self.tree.selection()
        if not selection:
            messagebox.showwarning(
                '未选择磁盘',
                '请先在列表中选择一个 NTFS 磁盘。',
            )
            return

        if not self.ntfs3g_path:
            messagebox.showerror(
                '缺少依赖',
                'ntfs-3g 未安装，请运行 bash setup.sh 安装依赖。',
            )
            return

        item = self.tree.item(selection[0])
        values = item['values']
        disk_name = values[0]

        disk = next(
            (d for d in self.disks if d['name'] == disk_name),
            None,
        )
        if not disk:
            messagebox.showerror('错误', '无法获取磁盘信息，请刷新列表。')
            return

        identifier = disk['identifier']
        volume_name = disk['name']
        mount_point = f'/Volumes/{_sanitize_name(volume_name)}'

        self._set_status(f'正在挂载 {volume_name}...')
        self._log(f'开始挂载: {identifier} ({volume_name})')

        # 步骤 1: 如果已挂载，先卸载
        if disk['mounted']:
            self._log(f'正在卸载 {identifier}...')
            ok, msg = unmount_disk(identifier)
            if not ok:
                self._log(f'卸载失败: {msg}')
                self._set_status('卸载失败')
                messagebox.showerror(
                    '卸载失败',
                    f'无法卸载 {identifier}。\n'
                    f'错误: {msg}\n\n'
                    '请确保没有程序正在访问该磁盘（如 Finder 窗口、终端等）。',
                )
                return
            self._log('卸载成功')

        # 步骤 2: 使用 ntfs-3g 挂载为读写模式
        self._log('正在挂载为读写模式...')
        success, msg = mount_ntfs(
            self.ntfs3g_path, identifier, mount_point,
        )

        if success:
            self._set_status(f'{volume_name} 已挂载为读写模式')
            self._log(f'挂载成功！路径: {mount_point}')
            self._log('现在可以对该磁盘进行读写操作。')
            self._log('提示: 完成操作后请在 Finder 中"弹出"以安全卸载。')

            # 打开 Finder
            subprocess.run(
                ['open', mount_point],
                capture_output=True, timeout=5,
            )

            # 刷新列表并启用打开按钮
            self.refresh_disks()
            self.open_btn.config(state=tk.NORMAL)
        else:
            self._set_status('挂载失败')
            self._log(f'挂载失败: {msg}')
            messagebox.showerror(
                '挂载失败',
                f'无法挂载 {volume_name}。\n\n'
                f'错误信息:\n{msg}\n\n'
                f'请检查:\n'
                f'  1. macFUSE 是否已正确安装\n'
                f'  2. 是否已在"系统设置 > 隐私与安全性"中允许 macFUSE\n'
                f'  3. 尝试重新运行: bash setup.sh',
            )

    def open_in_finder(self) -> None:
        """在 Finder 中打开当前选中磁盘的挂载点"""
        selection = self.tree.selection()
        if not selection:
            return
        item = self.tree.item(selection[0])
        values = item['values']
        disk_name = values[0]
        mount_point = f'/Volumes/{_sanitize_name(disk_name)}'

        if os.path.isdir(mount_point):
            subprocess.run(
                ['open', mount_point],
                capture_output=True, timeout=5,
            )
        else:
            # 尝试从 disk info 获取挂载点
            disk = next(
                (d for d in self.disks if d['name'] == disk_name),
                None,
            )
            if disk and disk['mount_point']:
                subprocess.run(
                    ['open', disk['mount_point']],
                    capture_output=True, timeout=5,
                )

    def run(self) -> None:
        """启动 GUI 主循环"""
        self.window.mainloop()


def _sanitize_name(name: str) -> str:
    """清理卷名，确保可用作目录名"""
    # 替换不可用于路径的字符
    cleaned = re.sub(r'[/:?<>|*]', '_', name)
    return cleaned.strip()


# ═══════════════════════════════════════════════════════════════
# 6. 主入口
# ═══════════════════════════════════════════════════════════════

def main() -> None:
    """程序入口"""
    ntfs3g_path, macfuse_ok = check_dependencies()
    deps_ok = ntfs3g_path is not None and macfuse_ok

    if not deps_ok:
        # 显示依赖警告
        root = tk.Tk()
        root.withdraw()

        missing = []
        if ntfs3g_path is None:
            missing.append('ntfs-3g')
        if not macfuse_ok:
            missing.append('macFUSE')

        msg = (
            f'缺少必要依赖: {", ".join(missing)}\n\n'
            '请在终端中运行以下命令安装依赖:\n'
            '  bash setup.sh\n\n'
            '工具将以受限模式启动（无法挂载磁盘）。'
        )
        messagebox.showwarning('缺少依赖', msg)
        root.destroy()

    app = NTFSMounter(ntfs3g_path, macfuse_ok)
    app.run()


if __name__ == '__main__':
    main()
