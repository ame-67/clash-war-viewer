# 部落冲突(国际服) 部落战成员战斗情况查看器

一个基于 **Clash of Clans 官方 API** 的 Windows 桌面小工具：用来看清部落战里每个成员到底打了几次、打得怎么样，以及联赛（CWL）每一轮的表现。

> ⚠️ 本项目是非官方粉丝作品，与 Supercell 无关，未获得 Supercell 认可。
> This material is unofficial and is not endorsed by Supercell. For more information see Supercell's Fan Content Policy: <https://www.supercell.com/fan-content-policy>

## 功能

- **当前部落战成员明细**：进攻次数、总星数、总摧毁率、场均星、最佳进攻、被攻星数、被摧毁率、未进攻次数
- **双击任意成员**：查看其每一次进攻与防守的明细（对手、几星、摧毁率、用时）
- **我方 / 敌方** 一键切换视角
- **部落联赛 CWL**：查看第 1~7 轮每轮数据，以及"汇总(全部轮次)"的全赛季统计
- **战争日志**：最近 30 场胜负汇总（绿=胜、红=负、橙=平）
- **自动刷新**：当前部落战视图每 30 秒自动刷新，可随时**暂停 / 继续**
- **导出 CSV**：一键保存为 Excel 可直接打开的表格
- 行颜色标记：绿 = 打出过 3 星，橙 = 最高 1~2 星，红 = 只打出 0 星，灰 = 未进攻

## 快速开始

### 1. 下载运行

打开 [Releases](../../releases) 下载 `CoC_War_Viewer.exe`，双击即可运行（单文件、免安装）。也可以从源码运行（见下文）。

### 2. 获取 API 令牌

本工具使用官方 API，需要一枚免费令牌：

1. 打开 <https://developer.clashofclans.com> 并登录（谷歌账号 / Supercell ID 等均可）
2. 点 **Create Key**（创建令牌）
   - 名称、描述随意填写
   - **IP 地址**：填写你当前电脑的公网 IP（必填，创建时会校验）
   - 勾选 **Clash of Clans**，创建后复制令牌
3. 把令牌粘贴到程序顶部的"API令牌"框，填入部落标签（如 `#2LJQ2YVY`），点击"查询当前部落战"

> 令牌与公网 IP 绑定，换网络（WiFi / 热点 / 代理）后需要重新创建令牌。

### 3. 查看数据

- 行内数字即每位成员的战斗情况；**双击某一行**查看每一次进攻与防守的明细
- 联赛期间点"部落联赛CWL"，可切换每一轮或查看全部轮次汇总
- 点"导出CSV"把当前表格保存到本地

## 从源码运行 / 构建

```bash
# 直接运行(需要 Python 3.9+，仅标准库 + tkinter)
python clash_war_viewer.py

# 打包为单文件 exe
pip install pyinstaller
pyinstaller --onefile --windowed --name CoC_War_Viewer --icon icon.ico clash_war_viewer.py
```

## 测试

```bash
python test_logic.py     # 离线统计逻辑测试(无需令牌)
python test_ui_smoke.py  # 端到端冒烟测试(需本机已保存令牌)
python test_pause.py     # 暂停/恢复自动刷新测试(需本机已保存令牌)
```

## 项目结构

```
clash_war_viewer.py   # 主程序(tkinter GUI + 官方 API 调用, 无第三方运行时依赖)
gen_icon.py           # 用 Pillow 生成程序图标
icon.ico              # 程序图标
test_logic.py         # 统计逻辑离线测试
test_ui_smoke.py      # UI 端到端冒烟测试
test_pause.py         # 暂停功能测试
README.txt            # 纯文本使用说明(离线版)
```

## 说明与限制

- **数据来源**：全部来自 Supercell 官方 Clash of Clans API；本程序不收集、不上传任何个人数据。
- 令牌仅保存在本机 `%APPDATA%\CoCWarViewer\config.json`，不会出现在仓库中。
- 官方 API **不提供常规部落战历史的成员明细**（战争日志只有胜负汇总）；成员明细仅在战争进行中 / 刚结束时可用，联赛明细仅联赛期间可用。
- 联赛每月 1~8 日进行，其余时间查询联赛会提示"未参加 / 不在联赛期"。

## License

本项目未设置开源许可证（默认保留所有权利）。如需转载或分发，请先联系作者或自行补充合适的 LICENSE 文件。
