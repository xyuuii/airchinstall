# Airchinstall

[![CI](https://github.com/xyuuii/airchinstall/actions/workflows/ci.yml/badge.svg)](https://github.com/xyuuii/airchinstall/actions/workflows/ci.yml)

Airchinstall 是运行在 Arch Linux Live TTY 中的动态安装助手。用户始终在真实 Bash 中亲手执行命令；Airchinstall 观察命令与结果、验证系统事实、解释风险、关联 ArchWiki，并通过云端 AI 提供基于可信操作目录的建议。

它不是 WebUI、自动安装器或固定顺序课程。

当前 `0.1` 是框架垂直切片：它验证 UEFI、网络和磁盘观察链路，但不会分区、格式化或安装 Arch Linux。

## 首个框架切片

- `tmux` 左栏是真实 Bash/PTY；右上是中文导师；右下是 ArchWiki 上下文。
- UEFI、网络和磁盘检查可以任意顺序完成，事实图独立更新。
- AI 只能引用可信操作目录中的命令，不能执行命令或决定目标磁盘。
- 默认只允许在 QEMU/KVM 的官方 Arch ISO 中运行。
- API Key 只保存在 `/run/airchinstall`，关机即消失。

## 在官方 Arch ISO 中运行

把完整仓库复制到 QEMU 中的官方 Arch Live 环境，然后运行：

```bash
cd /root/airchinstall
./scripts/bootstrap.sh
```

仓库公开后，也可以直接在 Live Shell 中下载完整源码：

```bash
curl -fL https://github.com/xyuuii/airchinstall/archive/refs/heads/main.tar.gz -o /tmp/airchinstall.tar.gz
bsdtar -xf /tmp/airchinstall.tar.gz -C /root
cd /root/airchinstall-main
./scripts/bootstrap.sh
```

bootstrap 使用 Live 环境的可写内存层安装官方依赖，不会修改 ISO，也不会把 Airchinstall 自动装进目标系统。首阶段会拒绝物理机。

启动后：

- 在左栏真实 Bash 中自行输入命令。
- 在右上输入自然语言目标；云端 AI 只能选择可信 Operation。
- 右上给出风险与需要亲手输入的可信命令；按 `Ctrl+D` 展开成功条件等详情。
- 右下自动显示当前 Operation 对应的 ArchWiki 页面与章节。
- 使用 `airchinstall export-transcript PATH` 主动导出脱敏记录。

## 开发

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e '.[test]'
pytest
airchinstall doctor
```

QEMU 流程见 [QEMU 验证指南](docs/qemu-bootstrap.md)，架构和安全约束分别见 [architecture](docs/architecture.md) 与 [security](docs/security.md)。

研究背景见 [GitHub 与一手资料竞品研究](docs/research/arch-ai-installer-landscape.md)。

> 自定义 ISO 不属于第一阶段；核心框架稳定前始终使用官方 Arch ISO + bootstrap。

## 许可证

Copyright © 2026 xyuuii。项目按 [GPL-3.0-or-later](LICENSE) 发布。
