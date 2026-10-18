# 我的集团 UI、出售确认与货币缩写交接

日期：2026-10-18（Asia/Shanghai）。

## 当前状态

**本轮源码实现与定向回归已完成。** 主 Agent 最终复跑 **136 项通过**；另有一项已知基线问题排除。功能分支为 `codex/feature-20261018`，用户要求修复后直接推送，进一步审核由用户另行安排。实际页面视觉和真实游戏行为尚未验收，详见下文。

用户批准的第一版布局、出售二次确认和后续追加的货币缩写均已实现。此前发现的出售旧请求问题与金额舍入边界问题已修复；上传前补修了出售成功与列表并行刷新的同步竞态，并加入回归。本文件由主 Agent 维护，可用于继续验收或集成。

## 工作位置与保护范围

- 仓库工作区：`F:/codex-ys/home/worktrees/feature-20261018/FM-ODD`。
- 功能分支：`codex/feature-20261018`。
- 基准：`origin/codex/backend-refactor-20261018`，提交 `d09d10894be494b80ecdb52059bf0436213ffbe5`。
- 原主目录 `F:/codex/FM-ODD`、原工作区 `33f4`、另一个工作区 `94c5` 中的既有工作均保留；本次产品修改仅在上述功能工作区进行。
- 用户指定 Qoder 搜索 UI 参考、Grok 编写产品代码；主 Agent 负责验收及本交接文档。

## 已确认需求

1. “我的集团”上方集中五个现有功能入口，下方逐个展示已收购俱乐部明细卡片。
2. 每张卡片始终展开，取消折叠按钮、点击标题折叠及默认隐藏的指标。
3. 以用户选定的第一版预览为准；卡片保留足够空间呈现全部指标，窄窗口允许换列和内容撑高。
4. 展示现有 12 项指标及其真实数据：联赛排名、转会预算、财政结余、预计分红、估值、收购成本及涨跌、持有天数、债务、声望排名、声望比较、球迷或社媒比较、本赛季营收，以及最近五场赛果。
5. 底部“查看详情”和红色描边的“出售俱乐部”为并排、等高按钮，保留还债与排序入口。
6. 点击出售后显示二次确认，明确目标名称、预计金额与现有不可撤销说明；取消或关闭不提交，确认后只提交一次。
7. 保持深色主题、11 种界面语言和至少 13px 的用户可见字号。
8. 后续 UI 设计变更继续遵守“先预览图、用户确认、再编写代码”。本轮布局已确认，无需再次请求同一份设计的批准。
9. 游戏货币显示统一缩写，单位可延伸至 T 以上，沿用现有 K、M、B、T、P、E、Z、Y、R、Q。保留币种换算、本地化格式、小额精度及原始输入/计算数值。

## 设计参考与预览

- Qoder 搜索后由主 Agent 核对的参考：[PatternFly Dashboard](https://www.patternfly.org/patterns/dashboard/design-guidelines/)、[Telerik Dashboard Card](https://www.telerik.com/design-system/docs/ui-templates/building-blocks/dashboard/dashboard-card/)。
- 用户确认的是第一版加出售按钮的预览；本机文件：`C:/Users/SAS/.codex/generated_images/01a14d66-61fc-7f63-a7ba-2a6db8c77dc1/exec-5348bd69-7f67-4573-b9bd-9a36d98b791b.png`。
- 图片只用于设计参考，球队、金额、徽章均为示例，不能写入产品作为真实数据。

## 已完成的源码与行为

| 文件 | 作用 |
| --- | --- |
| `src/web/app.js` | 五个顶部功能入口、常驻展开卡片、共享俱乐部显示名、出售确认与重复点击/旧请求保护；统一货币格式，移除旧缩写开关、折叠状态及事件，保留排序和缓存签名 |
| `src/web/app.css`、`src/web/dark-theme.css` | 三/二/一卡片列、三列指标、并排等高操作按钮、红色描边出售；清理旧横条与折叠规则，保留深色主题 |
| `src/web/index.html` | 移除已无作用的“缩写数字”关闭开关，金额固定使用统一格式 |
| `src/web/i18n.world.js`、`i18n.tw.js`、`i18n.de.js`、`i18n.es.js`、`i18n.fr.js`、`i18n.ru.js`、`i18n.ja.js`、`i18n.pt-BR.js`、`i18n.pt-PT.js` | 新增查看详情、出售俱乐部按钮文案，覆盖全部 11 种语言 |
| `tests/test_owned_club_sell_confirm_frontend.py` | 执行真实出售与按钮忙碌函数，隔离网络与游戏，验证取消、重复点击、错误恢复、所有权/作用域变化及出售成功后的并行刷新同步 |
| `tests/test_player_card_frontend.py`、`tests/test_world_clubs.py`、`tests/test_dark_mode_frontend.py` | 更新已过时的折叠、按钮及确认代码结构断言，保留指标与原有行为检查 |
| `tests/test_money_abbreviations_frontend.py` | 执行真实格式化、换算和输入解析函数，覆盖 K 到 Q、币种、小额、负数、舍入晋级、历史精度与图表轴共用单位 |
| `tests/test_settings_frontend_optimization.py`、`tests/test_frontend_refresh_recovery.py`、`tests/test_global_statistics.py` | 更新移除旧开关、共用金额函数后的相关契约断言 |
| `docs/FEATURE_INDEX.md` | 记录常驻卡片、出售保护及统一货币显示行为 |

出售复用现有 `fmoddConfirm`，正文使用与卡片相同的俱乐部名称及现有估价规则。取消/关闭不发起出售；确认框和请求等待期间按账户与俱乐部锁定重复操作。提交前核对账户范围、世界俱乐部列表请求编号及原收购记录对象，旧错误也不污染当前界面；`finally` 恢复按钮和操作锁。

**并行刷新处理：** 提交前列表或所有权变化会取消旧出售意图。出售 POST 已成功时，若存在旧列表读取或请求编号/所有权对象变化，则等待这些读取结束，再通过全新状态和列表请求同步卡片、余额与汇总；此路径不直接套用旧响应中的金额或重复提交出售。账户范围变化时停止后续界面写入。指标与后端出售事务规则未扩展，未增加后端写入 API。

货币展示入口 `formatFullMoney`、`formatMoney`、`formatPounds`、`formatGlobalStatisticMoney`、`formatCompactMoney`、`formatChartAxisMoney` 共用单位选择规则。K 到 Q 每档相差 1000；普通大额一位小数，历史列表保留两位，千以下按当前币种的小数位显示。金额舍入达到下一档时晋级，零位小数的 `999.99` 也会显示为 `1.0K`；图表轴按共用规模选单位。球员工资、转会费及世界榜也使用所选币种及一次汇率换算，负数未读取标记保持。旧 `fm-odds-compact-money=false` 不再影响展示。

投注限额输入仍使用原有 `formatBettingLimitInput` / `parseBettingLimitInput`，原始数据、计算、请求数值和精度没有改动。例如该输入框原来可将 `1500000` 显示为 `1500.0K`，本轮保留此输入行为；不要误把展示格式需求扩展为交易数值变更。

## 最终验证结果与复跑

以下结果来自最后一轮源码上的主 Agent 独立执行，不代表真实游戏验证。使用现有 Python 环境，没有安装依赖。

| 检查 | 最终结果 |
| --- | --- |
| 卡片、集团工具、详情、出售行为、货币、设置、图表、投注历史/分析、深色、本地化、字号、设置分组的定向组合 | **125 passed，1 deselected** |
| 世界俱乐部、全局统计中的相关前端、货币、忙碌状态与改名焦点检查 | **11 passed，125 deselected** |
| `node --check src/web/app.js` | 通过 |
| `git diff --check` | 通过；仅提示 `app.css` 的 CRLF 将规范化为 LF |
| 世界球员纯前端索引断言 | 单独提取并隔离执行通过；不等于整份模块 pytest 通过 |
| 上传前修复回归 | 出售成功与列表并行刷新竞态已复现并修复，新增隔离测试通过；进一步审核由用户安排 |

从功能工作区根目录执行：

```powershell
Set-Location -LiteralPath 'F:/codex-ys/home/worktrees/feature-20261018/FM-ODD'
$testPython = 'F:/codex/FM-ODD/.venv/Scripts/python.exe'

& $testPython -m pytest `
  tests/test_owned_club_sell_confirm_frontend.py `
  tests/test_player_card_frontend.py tests/test_portfolio_tool_frontend.py `
  tests/test_owned_club_detail_frontend.py tests/test_group_performance_frontend.py `
  tests/test_money_abbreviations_frontend.py tests/test_settings_frontend_optimization.py `
  tests/test_profit_analysis_colors.py tests/test_bet_history_frontend.py tests/test_bet_analysis_page.py `
  tests/test_dark_mode_frontend.py tests/test_i18n_catalog_contract.py `
  tests/test_i18n_locale_packs.py tests/test_frontend_font_sizes.py `
  tests/test_frontend_refresh_recovery.py::FrontendRefreshRecoveryTests::test_settings_are_grouped_into_horizontal_top_tabs `
  -q --tb=no -k 'not test_shop_item_metadata_is_complete_in_every_locale'

& $testPython -m pytest tests/test_world_clubs.py tests/test_global_statistics.py `
  -q --tb=no -k 'frontend or configured_currency_formatter or extended_compact_money_units or busy_states_are_accessible or group_rename_focus'

node --check src/web/app.js
git diff --check
```

默认 `E:/python/python.exe` 没有 `pytest`，请使用上述现有虚拟环境或配置正确的等效环境。

## 未完成与验收限制

- 当前 CUA 浏览器清单只有 Codex MCP Apps；创建 in-app browser 返回 `Browser is not available: iab`。未能在本地隔离示例页执行视觉验收，临时示例服务已停止。
- 未提供实现后的实际页面截图，也未验证真实浏览器下的焦点、Escape、滚动和较长翻译布局；已批准的设计预览图不能替代运行截图。共享确认函数的取消/关闭返回值曾做隔离执行检查。
- 一项已知基线失败未修：`tests/test_i18n_locale_packs.py::test_shop_item_metadata_is_complete_in_every_locale` 读取不存在的 `src/docs/I18N_ARCHITECTURE.md`，实际文档在根目录 `docs/`。修改前已是 **25 passed，1 failed**；最终定向组合显式排除此项，没有把它算作通过。
- 扩展尝试 `tests/test_world_players.py` 时，pytest 收集因缺少 `fmodd_native_core.dll` 失败，提示按源码运行说明构建 Rust 原生核心。本轮未自动构建、复制 DLL 或修改加载逻辑；仅隔离执行了不依赖该原生模块的现有前端索引断言。
- 未启动产品服务、连接或操作 Football Manager，未修改存档、账户或 Hook。静态和隔离测试不证明真实游戏行为。
- 未运行全量测试、构建发布或创建 PR；本次交付范围是提交并推送功能分支。

## 后续接手顺序

1. 在可用浏览器中，以隔离示例数据检查宽、中、窄窗口、长俱乐部名称、深色模式和较长翻译；比对获批第一版预览，核对 12 项指标、比较信息与操作按钮完整可见。
2. 验证真实浏览器的取消、关闭、Escape、焦点恢复、确认仅提交一次，以及刷新时的成功结果同步、切账户时的中断和失败恢复。示例验收使用模拟出售接口，不操作真实俱乐部。
3. 如需扩展世界球员回归，先按项目源码运行说明准备兼容的 Rust 原生核心，再正常收集对应测试；既有商店测试路径问题单独决定是否修复。
4. 若需要真实游戏/桌面验证，取得对应明确授权后，按原有 `GameLayout`、身份校验、预期旧值、回读及回滚规则执行。
5. 由用户安排的审核人员检查已推送功能分支，完成上述验收后再决定是否创建 PR 或集成；无需移动或撤销其它工作区的既有修改。
