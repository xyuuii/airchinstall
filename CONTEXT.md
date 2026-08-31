# Airchinstall

Airchinstall 在真实 Arch 安装过程中理解系统事实与用户目标，并为用户亲手执行的操作提供解释、风险提示和可追溯建议。

## Language

**Observation**:
真实 Shell 中已经发生的命令、输出或退出结果；它本身不证明系统状态。
_Avoid_: Step, lesson event

**Fact**:
由确定性只读检查确认的当前系统属性，例如 UEFI 可用、网络在线或磁盘清单。
_Avoid_: AI conclusion, assumed state

**Goal**:
用户希望系统达到的结果，可以随时提出、修改或放弃，并不规定唯一顺序。
_Avoid_: Course, fixed plan

**Operation**:
可信目录中一个可由用户亲手完成的系统动作，包含前置事实、风险、预期影响和知识来源。
_Avoid_: Step, task

**Advice**:
基于 Facts、Goals 和可信 Operations 生成的解释与可选方向，不拥有执行权。
_Avoid_: Instruction authority, command executor

**Assistant Session**:
一次 Live 环境中的协作过程，拥有当前 Facts、Goals、Advice 与易失 transcript。
_Avoid_: Course run, installer run
