# macOS NTFS 读写挂载工具

一个基于 **macFUSE + ntfs-3g** 的图形界面工具，让 macOS 原生只读的 NTFS 外部硬盘支持**读写**操作，替代 Paragon NTFS / Tuxera 等商业软件。
# 测试时发现在macOS26无法正常使用很麻烦且与Nigate高度重合so选择弃置这个仓库，但仍然open，按需自己看着用
---

## 功能

- 自动扫描并列出所有外部 NTFS 磁盘
- 一键挂载 NTFS 磁盘为读写模式
- 图形界面操作，无需记忆命令
- 自动调用 Finder 打开挂载目录
- 双击磁盘即可快速挂载

## 系统要求

- macOS 11 Big Sur 或更高版本
- 建议 Python 3.9+

## 快速开始

### 1. 安装依赖

在终端中运行：

```bash
bash setup.sh
```

脚本会自动完成以下操作：

1. 检查系统架构（Intel / Apple Silicon）
2. 安装 Homebrew（如未安装）
3. 安装 macFUSE（内核扩展）
4. 安装 ntfs-3g（NTFS 驱动）

### 2. 允许 macFUSE

安装 macFUSE 后，打开 **系统设置 > 隐私与安全性**，在页面下方找到 **允许来自以下开发者的系统软件**，点击 **允许**。

> 部分 macOS 版本可能需要**重启**才能生效。

### 3. 启动工具

```bash
python3 ntfs_mounter.py
```

### 4. 使用

1. 连接 NTFS 格式的外部硬盘
2. 点击 **刷新列表** 扫描磁盘
3. 在列表中选择要挂载的磁盘
4. 点击 **挂载选中磁盘**（或双击磁盘）
5. 在弹出的密码框中输入 Mac 管理员密码
6. 磁盘将被挂载到 `/Volumes/卷宗名称`，并自动打开 Finder

### 5. 完成操作

在 Finder 中右键点击磁盘，选择 **弹出** 即可安全卸载。

---

## 工作原理

| 步骤 | 操作 | 说明 |
|------|------|------|
| 1 | `diskutil list external` | 扫描外部磁盘 |
| 2 | `diskutil info` | 识别 NTFS 分区 |
| 3 | `diskutil unmount` | 解除 macOS 只读挂载 |
| 4 | `ntfs-3g -o allow_other` | 使用 ntfs-3g 挂载为读写模式 |

### 为什么不用系统自带的 `mount -t ntfs`？

macOS 原生支持读写 NTFS，但该功能已被 Apple 标记为不稳定，**极易导致文件系统损坏或数据丢失**。本工具使用成熟的 **ntfs-3g** 驱动（开源、稳定、跨平台）。

### 权限处理

本工具使用 `osascript` 配合 `do shell script with administrator privileges` 弹出 macOS 原生密码对话框执行需要管理员权限的操作。利用 `sudo` 的 5 分钟凭证缓存，短时间内的多次操作无需重复输入密码。

不需要关闭 SIP（系统完整性保护）。

---

## 常见问题 (FAQ)

### Q: 提示 "缺少依赖" 怎么办？

运行以下命令安装依赖：

```bash
bash setup.sh
```

安装完成后重新启动工具。

### Q: 为什么 ntfs-3g 安装后工具仍提示未找到？

Apple Silicon Mac 的 Homebrew 安装在 `/opt/homebrew`，终端可能需要重新加载环境变量：

```bash
eval "$(/opt/homebrew/bin/brew shellenv)"
```

然后重新启动工具。

或者直接在终端检查：

```bash
which ntfs-3g
ls -l /opt/homebrew/bin/ntfs-3g
```

### Q: macFUSE 安装后需要做什么？

macFUSE 安装后，必须前往 **系统设置 > 隐私与安全性** 中**允许**其加载内核扩展。如果没有看到提示：

1. 重新启动 Mac
2. 再次检查系统设置
3. 如果仍不显示，尝试重新安装 macFUSE：
   ```bash
   brew reinstall --cask macfuse
   ```

### Q: 挂载失败，提示 "Resource busy" 怎么办？

有程序正在访问该磁盘。请检查：

- 是否有 Finder 窗口打开了该磁盘
- 终端是否正在该磁盘目录中
- 是否有应用（如 Time Machine、Spotlight）正在访问

关闭相关程序后重试。

### Q: 挂载后没有自动打开 Finder？

可以手动打开 Finder，或在工具中选中磁盘后点击 **在 Finder 中打开**。

### Q: 写入速度如何？

ntfs-3g 的读写速度通常接近 USB 3.0 的上限。如果速度明显偏低，尝试：

- 使用高质量的 USB 数据线
- 直接连接 Mac 而非通过 USB Hub
- 避免同时进行其他磁盘密集型操作

### Q: 卸载磁盘的正确方法？

在完成文件操作后：

1. 关闭所有正在访问该磁盘的文件和程序
2. 在 Finder 中右键点击磁盘 → **弹出**
3. 或运行：`diskutil unmount /Volumes/卷宗名称`

> **请不要直接拔掉硬盘！** 请先弹出磁盘以确保数据写入完成。

### Q: 卸载后 macOS 又自动挂载为只读了？

这是 macOS 的正常行为。系统会自动挂载可识别的文件系统。如需再次写入，在工具中重新挂载即可。

### Q: 此工具会影响系统稳定性吗？

不会。ntfs-3g 是一个成熟的用户空间文件系统驱动，不会修改系统内核文件。macFUSE 是广泛使用的 FUSE 实现，被许多应用依赖。

---

## 文件说明

```
ntfs_tool/
├── ntfs_mounter.py    # 主程序（Python GUI）
├── setup.sh           # 依赖安装脚本
└── README.md          # 使用文档
```

## 技术栈

- Python 3 + tkinter（GUI）
- macOS diskutil（磁盘管理）
- osascript（管理员权限）
- macFUSE + ntfs-3g（NTFS 驱动）

## 许可证

MIT License
