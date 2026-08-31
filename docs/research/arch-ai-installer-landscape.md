# AI 引导式 Arch Linux 安装工具：GitHub 与一手资料竞品研究

> 调研日期：2026-08-31
> 证据范围：Arch Linux 官方包页、ArchWiki、`archlinux/archinstall` 官方仓库与文档，以及各项目自己的 GitHub 仓库、README 和源码。活跃度以调研日看到的默认分支提交、Release 与归档状态为准；star 数不作为质量判断。GitHub 私有、未索引或刚创建的项目不在本报告可见范围内。

## 结论先行

这个项目**值得做，但不值得再造一个安装器**。

最合理的产品定义不是“AI 帮你安装 Arch”，而是：

> 以官方 `archinstall` 作为确定性的安装执行引擎，在它上面增加一个可观察、可解释、可追溯的“Arch 安装导师层”。

调研得到的关键判断如下：

1. 安装自动化已经非常拥挤。官方 `archinstall`、ALIS、archfi、Rust TUI、GUI/离线安装器都覆盖了分区、桌面环境、bootloader、网络与配置保存。若重写这些能力，重复造轮子和误删磁盘的风险都很高。
2. 用户设想的视觉布局本身不是壁垒：`archinstall 4.4` 已迁移到 Textual，并已有“左侧选项、右侧预览”。真正仍为空白的是**安装执行期间的实时命令/操作流、按知识水平切换的解释、精确 ArchWiki 锚点与错误诊断**。[当前 TUI 的左右预览实现](https://github.com/archlinux/archinstall/blob/master/archinstall/tui/components.py#L294-L327)
3. “AI 辅助安装”并非无人提出。`archinstall` 官方 issue #4549 在 2026-05-20 提议了状态感知解释、安全默认值、日志诊断、文档链接和明确确认，几乎覆盖本想法的 AI 核心；它当天被以 `NOT_PLANNED` 关闭。[提案正文](https://github.com/archlinux/archinstall/issues/4549)；[维护者关闭说明](https://github.com/archlinux/archinstall/issues/4549#issuecomment-4501515778)
4. GitHub 上找到一个明确使用 AI 的近邻项目 `ArchScriptGen`，但它是 PyQt6 + Groq 的 Bash 脚本生成/导出器，不直接安装，也没有运行时三栏解释、确定性安全引擎或 Wiki 同步。[项目 README](https://github.com/ChitranshSingh-ind/ArchScriptGen)
5. 右下 Wiki 不必从网页抓取开始做。Arch 官方 Extra 仓库已有 `arch-wiki-lite`：约 20.6 MiB、可在 console 搜索和阅读，包页称其约为 HTML 版的 1/9，并明确标注 GFDL 许可。[Arch 官方包页](https://archlinux.org/packages/extra/any/arch-wiki-lite/)
6. 如果首发要求中文，stock Arch ISO 的 Linux console 字体是实际阻碍。`archinstall` 官方 README 明确说非 Latin 字符可能无法正确显示；中文 MVP 应使用自定义 ISO 内置 `kmscon` 与 CJK 字体，或采用 SSH/图形终端 companion 模式。[archinstall 字体说明](https://github.com/archlinux/archinstall/blob/master/README.md#fonts)；[Arch 官方 kmscon 包](https://archlinux.org/packages/extra/x86_64/kmscon/)

因此，重复造轮子风险可以这样概括：

- 重写分区、格式化、pacstrap、bootloader 和 profile：**高风险、高重复**。
- 给 `archinstall` 加事件流、教学解释、Wiki 映射和安全诊断：**仍有明显差异化**。
- 让 LLM 自由生成并以 root 执行安装命令：**不应做**。

## 1. 官方 `archinstall` 到底已经做了什么

### 1.1 当前状态与定位

Arch 官方 Extra 仓库在调研日提供 `archinstall 4.4-1`，正式依赖包含 `python-textual`；包在 2026-06-28 更新。[Arch 官方包页](https://archlinux.org/packages/extra/any/archinstall/) 4.4 release 同日发布，包含安装摘要、错误/警告/ready 分色和日志分享等改进。[4.4 release](https://github.com/archlinux/archinstall/releases/tag/4.4) 默认分支在 2026-08-30 仍有提交，说明它是高活跃的官方基座，而不是一个可以忽略的旧脚本。[2026-08-30 提交](https://github.com/archlinux/archinstall/commit/9bae29d6ed83401f8c995d0240efce21fd7a224b)

官方同时把它定义为 guided installer 和 Python 安装库，支持从 live medium 或已有系统执行安装与系统管理。[官方 README](https://github.com/archlinux/archinstall#arch-installer) 这意味着本项目可以复用安装模型和执行逻辑，而不必维护另一套硬件、磁盘和 profile 矩阵。

### 1.2 UI 已经接近“两栏”，但还不是教学界面

4.0 release 明确记录了从 curses 到 Textual 的迁移。[4.0 release](https://github.com/archlinux/archinstall/releases/tag/4.0) 当前 `OptionListScreen` 可把预览放在右侧或底部，并用滚动区域展示内容。[components.py](https://github.com/archlinux/archinstall/blob/master/archinstall/tui/components.py#L239-L327)

不过，这个 preview 的用途是展示选中的网络、认证、磁盘、swap、kernel 等配置，以及配置是否缺失、警告或 ready；它不是逐命令解释器。[global_menu.py 配置预览](https://github.com/archlinux/archinstall/blob/master/archinstall/lib/global_menu.py#L291-L445) [安装项状态摘要](https://github.com/archlinux/archinstall/blob/master/archinstall/lib/global_menu.py#L497-L537) `--advanced` 也只是暴露更多配置项，不是“小白/熟练/高级”三档教学内容。[README Advanced](https://github.com/archlinux/archinstall/blob/master/README.md#advanced)

更关键的是，当前交互顺序是“Textual 收集配置 → 保存/验证 → 最终确认 → 倒计时 → 离开主 TUI 执行安装 → 完成后再弹出 post-install 菜单”，并非安装期间一直保留三栏布局。[guided.py](https://github.com/archlinux/archinstall/blob/master/archinstall/scripts/guided.py#L204-L255) 因此，用户提出的“左侧实时 TTY，右上解释，右下 Wiki”仍然是实质性差异，不只是换皮。

截至调研日，正式依赖中也没有 LLM/AI 客户端；当前 preview 只接收确定性的字符串或 `PreviewResult`。因此 #4549 是尚未实现的提案，不是藏在实验开关中的现有功能。[pyproject.toml 依赖](https://github.com/archlinux/archinstall/blob/master/pyproject.toml#L20-L27) [preview 渲染](https://github.com/archlinux/archinstall/blob/master/archinstall/tui/components.py#L30-L43)

### 1.3 配置、库和扩展点

官方 guided 模式支持：

- 普通配置与敏感 credentials 分文件保存和加载；
- 本地或 URL 配置；
- `--dry-run` 生成/验证配置但不做永久修改；
- `--silent` 无人值守；
- `--advanced`、`--offline`、`--plugin` 等选项。
  [Guided installation 文档](https://github.com/archlinux/archinstall/blob/master/docs/installing/guided.rst) [README 配置说明](https://github.com/archlinux/archinstall/blob/master/README.md#running-from-a-declarative-configuration-file-or-url)

它也提供 `Installer`、`FilesystemHandler` 等 Python API 与自动化范例。[Installer API](https://archinstall.archlinux.page/archinstall/Installer.html) [自动安装范例](https://github.com/archlinux/archinstall/blob/master/examples/full_automated_installation.py)

插件可以通过 `--plugin` 或 Python entry point `archinstall.plugin` 加载，钩子如 `on_pacstrap` 可改变部分流程；但官方文档自己也说插件文档仍很稀疏，并建议直接搜索源码中的 `plugin.on_`。[插件文档](https://github.com/archlinux/archinstall/blob/master/docs/archinstall/plugins.rst#L1-L44) 当前 loader 会直接 import 并实例化插件代码，所以远程插件并不是天然安全边界。[plugins.py](https://github.com/archlinux/archinstall/blob/master/archinstall/lib/plugins.py#L13-L25)

**判断：**插件适合早期原型，但不是完整的 `before operation / stdout / after operation / rollback` 教学事件 API。若要稳定解释每一步，最好给执行层加结构化事件适配器；长期可以向上游贡献一个与 AI 无关的 observability hook，而不是把 LLM 塞进官方核心。

### 1.4 命令透明度与安全模型

`SysCommandWorker` 使用 PTY 执行命令，可读取实时输出，并在执行前记录命令历史。[command.py 执行与捕获](https://github.com/archlinux/archinstall/blob/master/archinstall/lib/command.py#L149-L220) 官方手册列出 `install.log`、`cmd_history.txt`、配置、credentials 和磁盘布局等日志文件。[archinstall(1) Log files](https://man.archlinux.org/man/archinstall.1#Log_files)

这提供了很好的拦截点，但“完全透明”不能只等同于 shell command：`archinstall` 也通过 Python 库、libparted 模型和直接文件写入完成工作。因此 UI 应展示统一的**操作事件**（将修改哪个设备/分区/文件、可否回滚、如何验证），有命令时再展示精确 argv，而不是为所有动作伪造一条 shell 命令。[guided.py 的高层安装步骤](https://github.com/archlinux/archinstall/blob/master/archinstall/scripts/guided.py#L45-L201)

安全上还有四条硬约束：

- live ISO 默认以 root 运行，AI 生成并执行任意命令就等同于给模型 root 权限。[官方 README](https://github.com/archlinux/archinstall/blob/master/README.md#installation--usage)
- 不可逆磁盘操作前，官方流程会做最终确认和倒计时；新产品不能让 AI 绕过这些 gate。[guided.py](https://github.com/archlinux/archinstall/blob/master/archinstall/scripts/guided.py#L219-L248)
- 用户/root 密码保存为 yescrypt hash，但磁盘加密口令在未加密 credentials 中必须以明文存在；credentials 可再选择加密。[credentials 说明](https://github.com/archlinux/archinstall/blob/master/README.md#credentials-configuration-file-encryption)
- `--debug` 会警告某些凭据可能进入日志；原始终端历史、debug log、Wi-Fi 配置和 credentials 默认都不应发往云模型。[args.py debug 警告](https://github.com/archlinux/archinstall/blob/master/archinstall/lib/args.py#L655-L666)

### 1.5 官方已经讨论并拒绝了 AI 提案

Issue #4549 的提案不是一句模糊的“加 AI”，而是一个相当完整的方案：让安装器给 AI 结构化磁盘、boot mode、profile、日志和网络状态；AI 只解释和提出建议；`archinstall` 仍是执行权威；破坏性操作要求明确确认；云模型 opt-in；MVP 先做安装计划解释、磁盘/bootloader 风险摘要、日志诊断和文档链接。[Issue #4549](https://github.com/archlinux/archinstall/issues/4549)

它没有形成代码或 PR，并在 2026-05-20 当天被关闭为 `NOT_PLANNED`。维护者说明同时提到提案者在多个仓库重复发相同 issue，以及该想法被认为不太可行、也不符合 Arch Linux philosophy。[关闭评论](https://github.com/archlinux/archinstall/issues/4549#issuecomment-4501515778)

这条证据应准确解读：

- 它证明需求和安全模型已经有人想到，不能把“AI 解释安装”宣传为前所未有。
- 它是该 issue 的维护决定，不等于一份禁止第三方项目的正式 Arch 政策。
- 它强烈暗示“直接把 AI 合入官方 archinstall”的上游路径阻力很大。
- 独立项目要更贴合 Arch 的透明、用户控制与可审计性：**AI 是可关闭的解释器，不是做决定或执行命令的权威。**

## 2. 代表性直接与近邻项目

| 项目 | 调研日活跃度证据 | 已覆盖能力 | 与本创意重叠 | 仍然缺少的部分 |
|---|---|---|---|---|
| [ArchScriptGen](https://github.com/ChitranshSingh-ind/ArchScriptGen) | 2026-03 创建；默认分支最后提交 2026-04-14，[提交](https://github.com/ChitranshSingh-ind/ArchScriptGen/commit/f08894d66ec7cbbccc8483be136f581954cd7340) | PyQt6 GUI，选择 DE、kernel、bootloader、packages，用 Groq/Llama 生成 Bash 并导出 `.sh` | 唯一检索到明确把 AI 与 Arch 安装脚本生成结合的项目 | README 明说“不直接安装”；没有实时执行状态、三栏 TUI、分层解释、Wiki 同步和确定性磁盘安全模型 |
| [ALIS](https://github.com/picodotdev/alis) | 默认分支最后提交 2025-12-29，[提交](https://github.com/picodotdev/alis/commit/5011076dc725ba73e1645ddb05a5bfb084ef0c0a) | Bash 无人值守安装；自称“executable installation guide and wiki”；覆盖 LUKS/LVM、多个文件系统、bootloader、桌面、Secure Boot、恢复与完整命令日志 | “展示真实命令、跟 Wiki 学习”理念重叠最大 | 以编辑配置后全自动执行为主；无运行时教学面板、知识层级和 AI 诊断 |
| [archinstall-zfs](https://github.com/okhsunrog/archinstall_zfs) | 默认分支 2026-08-17 仍有提交，[提交](https://github.com/okhsunrog/archinstall_zfs/commit/3fec6626e082c1db11ebdf81bb84ee61e58a5e52) | Rust；ratatui TUI + Linux KMS GUI；ZFS wizard、safe demo、取消与清理、trace log；另有逐命令教学文档 | wizard、安全 demo、命令级解释文档非常接近“边装边学” | 专注 ZFS；说明在独立文档而非随当前事件同步；无解释层级和 AI；不基于官方 archinstall |
| [archinstall-rs](https://github.com/Firstp1ck/archinstall-rs) | v0.2.3/最后提交 2026-03-23，[提交](https://github.com/Firstp1ck/archinstall-rs/commit/fca92ef7bfac70d11bfcd5243437d2cf732a1e08) | Rust/ratatui，guided steps、TOML 保存加载、分区、bootloader、明确 install plan 和 dry-run | TUI、安装计划预览和 dry-run 重叠 | 仍是另一个安装器；无实时教学、AI、Wiki 联动和知识层级 |
| [Arch Linux Install Assistant](https://github.com/rgeorgen10/Arch-Linux-Install-Assistant) | 2026-04 创建，最后提交 2026-06-26，[提交](https://github.com/rgeorgen10/Arch-Linux-Install-Assistant/commit/7108e0f9ed3ab405e83d89d65db723f75f6c0171) | C 语言终端向导；UEFI/BIOS、自动/手动分区、pacstrap、GRUB、用户和 DE | “assistant”命名和逐步交互直接重叠 | 非 AI；ext4/GRUB 等选择较窄；无命令解释、Wiki 与成熟安全验证 |
| [archfi](https://github.com/MatMoul/archfi) | GitHub 已归档；默认分支最后提交 2022-11-21，[提交](https://github.com/MatMoul/archfi/commit/c592f54854982bf03990bf8a1ed5bfad993926a1) | 官方 ISO 上运行的 Bash wizard，定位为 tutorial installer，最小 base/bootloader 后可接 archdi | 新手向终端 wizard | 已归档；教学主要依靠屏幕提示/视频；无 AI、分层解释和 Wiki 联动 |

其他历史参照也说明“再做一个菜单安装器”的供给已经很多：AUI 的 README 明说只接受 patches、不再主动开发；Anarchy 的 GitHub 仓库已归档并迁移 GitLab；AL Installer 提供离线、逐步、GNOME 导向安装。[AUI](https://github.com/helmuthdu/aui) [Anarchy](https://github.com/AnarchyLinux/installer) [AL Installer](https://github.com/alinstaller/alinstaller)

### ArchScriptGen 源码边界

ArchScriptGen 值得单独核实，因为只读 README 容易把它误判为“已有 AI 安装器”：

- 系统提示明确要求模型**只输出原始 Bash 脚本，不要解释或 Markdown**。[main.py#L72-L78](https://github.com/ChitranshSingh-ind/ArchScriptGen/blob/main/main.py#L72-L78)
- 它直接调用 Groq `llama-3.3-70b-versatile`，把系统提示和用户需求发给模型。[main.py#L256-L276](https://github.com/ChitranshSingh-ind/ArchScriptGen/blob/main/main.py#L256-L276)
- 最终动作是把文本保存为 `.sh`。[main.py#L564-L572](https://github.com/ChitranshSingh-ind/ArchScriptGen/blob/main/main.py#L564-L572)
- README 明确要求用户审查生成脚本，并声明它不直接安装 Arch。[README Disclaimer](https://github.com/ChitranshSingh-ind/ArchScriptGen#%EF%B8%8F-disclaimer)

所以它验证了“用户愿意用 AI 降低 Arch 配置门槛”的方向，但其核心是**生成器**；本创意可以明确定位为**确定性执行过程的解释器与导师**，二者不是同一产品。

## 3. 是否已经有完整的 “AI-guided Arch installer”

截至调研日，使用下列同义词做了 GitHub repository、README 与 code 搜索：`Arch Linux AI installer`、`archinstall AI guidance`、`archinstall OpenAI`、`archinstall GPT`、`archinstall LLM`、`Arch Linux installation assistant`、`ArchScriptGen`。可复查的搜索入口包括：[Arch Linux + AI + installer](https://github.com/search?q=%22Arch+Linux%22+AI+installer+in%3Areadme&type=repositories)、[archinstall + OpenAI](https://github.com/search?q=archinstall+OpenAI+in%3Areadme&type=repositories)、[archinstall + GPT](https://github.com/search?q=archinstall+GPT+in%3Areadme&type=repositories)。

有两个真正相关的结果：

1. `archinstall` issue #4549：是提案，已 `NOT_PLANNED`，没有实现。
2. `ArchScriptGen`：是 AI Bash 生成器，不是运行时安装器。

**没有发现一个成熟公开项目同时具备**：真实安装执行、每条命令/操作可见、按用户能力分层解释、当前输出诊断、ArchWiki 精确同步、AI 只读建议与破坏性操作确定性确认。

这是一个有范围的负面检索结论，不能证明 GitHub 上绝对不存在同类仓库；但足以说明该组合还没有明显的成熟占位者。

## 4. 相邻 AI 终端工具会不会替代它

| 工具 | 官方仓库显示的能力 | 能替代什么 | 不能替代什么 |
|---|---|---|---|
| [ShellGPT](https://github.com/TheR1D/shell_gpt) | 生成 shell command；执行前提供 Execute/Describe/Abort；stdin 可分析日志；支持 chat/REPL | 临时解释一条命令或一段安装错误 | 不知道 installer 的结构化磁盘状态、预期下一步和安全不变量；没有固定 Wiki 锚点；在 root live ISO 上让模型生成命令风险过高 |
| [AIChat](https://github.com/sigoden/aichat) | Shell Assistant、会话、角色、RAG、tools/agents，多模型和本地模型 | 可做通用解释 UI、RAG 与模型接入层原型 | 没有 Arch 安装状态机、磁盘确认、操作审计与步骤映射 |
| [GitHub Copilot CLI](https://github.com/github/copilot-cli) | 终端 agent、可预览动作并要求批准、支持 MCP | 可解释错误并执行通用诊断 | 偏代码工作流、需账户/订阅与网络；不是 live ISO 安装器，也没有 Arch 专用安全规则 |
| [Arch Linux MCP Server](https://github.com/nihalxkumar/arch-mcp) | 非官方 MCP；提供 `archwiki://` 资源、Wiki/AUR/官方仓库搜索、系统日志和包管理工具 | 已把“AI 助手接入 ArchWiki/Arch 状态”做成可复用邻近能力 | README 的工具面向已运行系统和包管理，不包含 archinstall、pacstrap 或分区安装流程；没有三栏安装 UI |

这些工具可以拼出一个“让 AI 陪你手工安装”的临时方案，却无法给新手提供可靠的、可恢复的安装状态机。它们更适合作为模型/检索层参考，而不是产品的执行核心。

## 5. ArchWiki 同步与离线方案

Arch 官方 Installation Guide 本身建议在 live environment 中切换虚拟控制台，用 Lynx 一边看文档一边安装；这正是用户所说“终端旁放文档”的现有基线。[Installation Guide](https://wiki.archlinux.org/title/Installation_guide)

右下 Wiki 面板建议采用以下策略：

1. **离线内容源：**在自定义 ISO 中预装 `arch-wiki-lite`。官方包页给出的描述是无 HTML、约为 HTML 版 1/9、易于 console 搜索和阅读，安装大小约 20.6 MiB。[arch-wiki-lite](https://archlinux.org/packages/extra/any/arch-wiki-lite/)
2. **需要完整 HTML 时：**`arch-wiki-docs` 提供离线 HTML，但安装大小约 224.9 MiB。[arch-wiki-docs](https://archlinux.org/packages/extra/any/arch-wiki-docs/)
3. **固定步骤映射：**不要每次让 LLM 猜 Wiki 页面。维护 `step_id -> page title -> section anchor -> tested wiki revision` 清单；模型只对选中的证据做分层改写。
4. **在线更新可选：**联网后检查页面版本并提示“本地快照/在线最新版”，但安装指导不能依赖网络一直可用。
5. **许可：**两个官方包都标注 Wiki 内容为 `GFDL-1.3-or-later`。若复制、修改或再分发内容，需要保留相应许可与归属；简单打开原始离线页面比把全文复制进自己的私有格式更省维护成本。[包页许可字段](https://archlinux.org/packages/extra/any/arch-wiki-lite/)

## 6. 中文终端是首发范围决策，不是小细节

`archinstall` 虽有社区翻译，但官方 README 明说 Arch ISO 没有为所有语言附带所需字体，非 Latin 字符集可能无法正确显示，需要手动选择合适 console font。[官方 Fonts 说明](https://github.com/archlinux/archinstall/blob/master/README.md#fonts)

对本项目的含义是：

- **英文 MVP：**可以直接在 stock TTY/Textual 上验证核心交互。
- **中文本机三栏 UI：**更稳妥的做法是提供自定义 ArchISO，加入 `kmscon`、Freetype/Pango 和明确的 CJK 字体。Arch 官方已有 `kmscon` 包；其上游支持 Unifont、Freetype 和 Pango 字体后端。[Arch kmscon 包](https://archlinux.org/packages/extra/x86_64/kmscon/) [kmscon 字体后端](https://github.com/kmscon/kmscon#fonts)
- **不想先维护 ISO：**让安装目标机通过 SSH 暴露 PTY，在另一台电脑/平板的 Unicode 终端或 Web companion 中显示中文解释和 Wiki。ArchWiki 有官方的 SSH 安装流程参考。[Install Arch Linux via SSH](https://wiki.archlinux.org/title/Install_Arch_Linux_via_SSH)

因此不建议同时把“安装引擎、AI、三栏 TUI、自定义 ISO、中文字体”都塞进第一个版本；中文支持会把一个应用原型升级为 ISO/字体/输入链路项目。

## 7. 建议的差异化与 MVP

### 产品护城河

建议把差异化写成以下六点，而不是“我们也有 AI”：

1. **确定性执行，生成式解释。**安装计划只能来自受测试的 archinstall API/配置；LLM 不得新增或改写将执行的命令。
2. **操作级可见性。**统一显示命令、Python/库操作和文件变更；每个事件带目的、输入、影响范围、危险等级、验证方法和回滚说明。
3. **三档解释来自同一事实模型。**小白版解释概念和后果；熟练版给关键参数与取舍；高级版给完整 argv、设备、文件、退出码与替代方案。不要让三档分别自由生成事实。
4. **Wiki 是证据，不是装饰。**右下栏定位到精确页面/section，并标记本地快照日期；AI 回答附来源。
5. **可重放安装课件。**安装 transcript 可以脱敏后 replay，让用户事后理解、分享和复盘；这比“一次性 chatbot”更独特。
6. **AI 可完全关闭。**无模型时仍能靠人工编写的解释 catalog 和 Wiki 完成安装；AI 只做问答、个性化措辞与错误摘要。

### 推荐 MVP 顺序

**MVP 0：QEMU 只读教学原型**

- 英文；不碰真实磁盘。
- 读取 `archinstall --dry-run` 配置与模拟事件。
- 实现左侧操作流、右上三级解释、右下 `arch-wiki-lite`。
- 先覆盖 UEFI + 单盘 + ext4/Btrfs + systemd-boot/GRUB 的 20–30 个核心事件。

**MVP 1：受控真实执行**

- 复用 `ArchConfig`、`Installer`、`FilesystemHandler` 和 `SysCommandWorker`。
- 加入结构化 event adapter、redaction、设备影响预览、显式确认与 transcript。
- AI 默认关闭；可选远程模型只接收脱敏后的结构化事件，不接收完整 TTY、credentials 或 debug log。

**MVP 2：诊断与中文 companion**

- 从退出码、已知错误规则和 Wiki 先做确定性诊断，LLM 再把结果改写为用户级别合适的语言。
- 先做 SSH/Web Unicode companion；只有证明用户确实需要本机中文 TUI 后，再维护自定义 ISO + kmscon/CJK 字体。

### 明确不做

- 不让 AI 选择要擦除的磁盘。
- 不让 AI 绕过确认、自动开启 `--silent` 或执行自由生成的 root 命令。
- 不把 credentials、磁盘加密口令、Wi-Fi 密码、完整 debug 日志上传到云端。
- 不在 MVP 重写分区器、包安装器、bootloader 配置和 desktop profile。
- 不把“官方 issue 已拒绝”包装成“官方支持”或“即将合并”。

## 最终判断

这个想法的项目价值在“**安装 Arch 的过程中真正学会 Arch**”，而不是让安装再快两分钟。

从 GitHub 版图看，自动化安装器很多、通用 AI 终端助手也很多，甚至已有 AI 脚本生成器；但截至调研日，尚未发现成熟项目把**确定性官方安装引擎 + 实时操作透明度 + 分层教学 + 离线 ArchWiki 证据 + 只读 AI 诊断**组合起来。

因此建议继续，但项目边界应是：

> `archinstall` 的 explainability/education companion，而不是 `archinstall` 的替代品。

这样既避开最高风险的重复造轮子，也能把官方项目尚未覆盖、且官方 core 不愿承担的 AI/教学体验做成清晰的第三方产品。
