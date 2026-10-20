# FMODD 项目改动总览

记录时间：2026-10-18，北京时间。当前按用户要求暂停后续开发。

本文汇总当前项目工作树内的全部未提交改动、已完成验证、测试包、界面预览及待办事项。包括从原工作目录继承的修改，以及在隔离工作树内继续完成的修改；不把仓库原有的全部功能算成本次新增功能。DeepSeek / Qoder 的本机接入另列为环境记录。

## 1. 当前交付状态

| 项目 | 当前状态 |
| --- | --- |
| 已有业务调整 | 已接入：钱包 +100B、固定结果心理辅导、移除免费购买、情报固定定价 |
| 后端结构 | 比赛情报、心理辅导、医疗、食堂海参奖励共四个应用服务已提取 |
| 离线定向回归 | 最后一轮记录为 **166 passed in 16.62s** |
| 原生依赖及 HTTP 定向回归 | 测试包阶段编译匹配源码的原生依赖后，**192 passed in 11.93s** |
| Windows 测试包 | 已生成 ZIP，文件完整性及冻结路径导入检查通过 |
| 产品 EXE 运行 / 真实 FM 验证 | 尚未执行；测试通过不等于实机验收通过 |
| 盘口刷新区域优化 | 仅完成代码检查和建议，没有实施 |
| Git 提交 / 推送 / 合并 | 均未执行，改动保留在本地 |

以上测试数字属于不同阶段、范围有重叠，不能相加当作独立测试总数。汇总本文时只做文件、差异、日志和产物核对，没有重新运行业务测试或重新打包。

## 2. 工作位置、基线与隔离

| 内容 | 位置 / 标识 |
| --- | --- |
| 原工作目录 | `F:/codex/FM-ODD` |
| 原目录分支（建立隔离时） | `refactor/match-intelligence-service` |
| 当前隔离工作树 | `F:/codex-ys/home/worktrees/94c5/FM-ODD` |
| 当前分支 | `codex/current-baseline-backend-refactor` |
| 起始及当前 HEAD | `cd5900858a08cb9333b1d3a750fabb220cd5ca79` |
| 基线哈希及初始 Git 状态 | `output/refactor-baseline-2026-10-17.json` |
| 基线源码副本 | `output/refactor-baseline-source/` |

重构以原目录当时的实际工作树为基线，包含其未提交和未跟踪源码；仅对比 Git HEAD 会把之前已有的改动一并显示出来。

建立工作树时逐文件核对了 **512 个源码、测试、文档及开发配置文件**。本次汇总再次核对：原目录这 512 个文件与保存的基线哈希全部一致，当前工作树没有覆盖原目录的这些文件。

相对该实际基线，本轮在原有文件中修改了 `src/fm_odds_web.py`、`docs/ARCHITECTURE.md`、`docs/FEATURE_INDEX.md` 和当前后端重构计划，另新增三个应用服务、三个测试文件、执行报告及本文。

工作树用于隔离源码修改；它不是一次 Git 提交，也不会自动保存成可切换的历史版本。以后是否提交、合并仍由用户在测试后决定。

## 3. 已接入并保留的产品行为调整

本节内容在本轮三个服务提取之前已经存在于实际基线中。历史设计记录显示，之前核对了三份改动导出，仅应用一次一致的业务补丁；随后又完成比赛情报提取、钱包 +100B 和语言契约调整。当前工作树完整继承这些结果。

### 3.1 钱包 +100B

- 设置中的按钮调整为“钱包 +100B”，位于“关闭足协”复选项右侧。
- 每次成功点击，在原钱包余额上增加并持久化 `100_000_000_000`，不修改银行余额。
- `/api/cheat-balance` 保持接受旧的 `100`、`500`、`5000`，并增加 `100_000_000_000`。
- 标签、成功和失败反馈覆盖项目支持的 11 种语言。
- 新增 `tests/test_cheat_balance_add_100.py`；文件名保留早期命名，当前断言包含后续 +100B 行为。

主要文件：`src/tools/betting_account.py`、`src/web/app.js`、`src/web/index.html` 及相关语言包。

### 3.2 心理辅导改为固定结果、钱包付费

- 固定获得“彻底释怀”，不再由前端转盘随机决定结果。
- 每次基础价为 `100_000`，通过既有 `local_purchase_price` 换算后从钱包支付；不从银行支付。
- 钱包不足时阻止执行，不施加辅导效果。
- 保留既有同层两天冷却、关系归档、失败恢复和退款语义。
- 界面改为直接辅导卡片，移除概率图例和转盘操作；批量按人依次执行，失败即停。
- 补充钱包余额提示、批量费用说明、处理中防重复操作和备份提示。

主要文件：`src/tools/club_economy.py`、`src/web/app.js`、`src/web/index.html`、样式和语言包；后续编排已提取到 `counseling_application.py`。

### 3.3 移除免费购买 / 免费服务

- 移除设置中的免费购买入口、前端同步逻辑和 `/api/cheat/free-services` API。
- 移除账户应用层对应方法，以及购买路径中的免费分支和前端 `free_purchase` 提交。
- 旧账户中的 `free_services` 标记不再生效；加载经济数据时清除该字段。
- 商店、批量购买、训练购买、活动楼层和房间、语言提升、医疗等按各自实际价格计费，界面同步显示实际费用。
- 食堂费用、医院预计日费等展示不再受已移除的免费开关影响。
- 相关测试及文档同步移除过时的免费服务契约。

主要文件：`account_application.py`、`club_economy.py`、`fm_odds_web.py` 和前端代码。

### 3.4 比赛情报改为固定价格

| 情报类型 | 指定比赛基础价 | 随机购买基础价 |
| --- | --- | --- |
| 胜负 | 40M | 20M |
| 总进球数 | 60M | 30M |
| 比分 | 80M | 60M |

- 基础价格继续通过 `local_purchase_price` 换算，不能把基础价和换算后金额混用。
- 扣款顺序继续为先银行、后钱包。
- `pricing_basis` 为 `fixed_price`，不再依据余额、投注上限或每日锁价计算报价。
- 旧存档中的锁价记录不参与当前定价；比分情报继续包含前两项信息。
- 保留候选有效期、已购买信息展示及随机购买请求去重规则。

主要文件：`src/tools/club_economy.py`、比赛情报应用服务、前端报价展示与对应测试。

### 3.5 多语言和显示调整

支持范围保持为 `en-GB`、`zh-CN`、`zh-TW`、`ko-KR`、`de-DE`、`es-ES`、`fr-FR`、`ru-RU`、`ja-JP`、`pt-BR`、`pt-PT`。

- 对齐固定辅导、固定情报价格、移除免费购买和钱包 +100B 的相关文案。
- 语言目录契约调整为：领域目录必须包含基础英、中、韩，可内嵌其他受支持语言；所有已声明语言仍检查键、空值和占位参数。
- HTML 语义键在 11 种语言下检查解析，保留已有英文后备规则。
- 调整设置中作弊选项的布局，以及辅导卡片、深色模式相关样式。

这些改动不表示新增了全部 11 种语言，也不代表全站每个字符串都已完成完整翻译验收。

## 4. 后端应用服务提取

共同原则：`LocalOddsState` 继续唯一持有运行时状态、锁、账户、会话和调度。应用服务只接管对应用例的编排，通过窄 Runtime Protocol 和冻结的 I/O 数据类调用现有领域能力；没有增加另一套账户状态、缓存、调度器或通用依赖注入框架。

旧门面保持签名，每次调用重新绑定当前依赖，保留既有函数替换点。领域持久化仍由 `club_economy.py` 等模块负责，原生读取、旧值校验、写后回读和回滚仍由原有读取/事务层负责。

| 服务 | 来源 | 提取内容 | 关键保留边界 |
| --- | --- | --- | --- |
| `match_intelligence_application.py` | 本轮开始前已完成，继承 | 单次探测、公共状态、购买编排 | 非阻塞内存锁、节流、账户作用域、缓存副本、随机请求幂等；监控循环仍在运行时 |
| `counseling_application.py` | 本轮新增 | 单次心理辅导编排 | 钱包付费、效果与关系写入、失败恢复、退款及归档顺序 |
| `medical_application.py` | 本轮新增 | 手动治疗、默认策略更新、到期推进、默认治疗应用四条路径 | 游戏日调度、当前名单、资金不足停止、未解析球员等待、默认治疗替换点 |
| `canteen_application.py` | 本轮新增 | 单人奖励、批量奖励、上下文和逐人处理四条路径 | 60K 基础价换算、银行/钱包分账、单人事务、批量去重和最多 200 人、单写会话、部分完成响应 |

三个新增服务对应 **9 个旧方法**。核对显示：旧签名保持；对显式依赖引用做对应替换后，迁移前后控制流 AST 一致。`fm_odds_web.py` 相对实际基线的 AST 改动限定在这九个方法体、三个工厂和三个新服务导入。

独立审查指出的恢复失败测试缺口已补齐：

- 心理辅导：刻画恢复失败后仍尝试退款的既有顺序；归档失败仍位于原补偿边界之外。
- 食堂：真实 `commit_player_effect` 抛出的 `PlayerEffectRollbackError` 同时保留原操作和恢复异常，按原银行/钱包分账退款，且不更新球员公共状态。

以上是对既有行为的保留和验证，没有借重构改写跨原生内存、账户与归档的事务规则。

## 5. 分工与验证记录

本轮采用用户确定的方式：Codex 拆分任务、控制范围并集成；DeepSeek Harness 通过 CLI 顺序实现；Qoder 通过 CLI 独立只读审查。共享入口文件没有交给两个 Agent 同时写入。

| 阶段 | 已有证据 | 限制 |
| --- | --- | --- |
| 本轮开始时的实际基线 | 相关定向集 102 passed | 当时完整入口受原生依赖缺失影响 |
| 心理辅导应用边界 | 15 项通过；当批相关集 117 passed | 阶段性结果，不与后续数字累加 |
| 医疗应用边界 | 新测试 14 项通过；当批相关集 39 passed | 保留原四条路径和替换点 |
| 食堂应用边界 | 最终 19 项通过 | 包括恢复失败和分账退款刻画 |
| 三批离线最终回归 | **166 passed in 16.62s** | 16 个测试文件的定向集，不是全库测试 |
| 测试包阶段原生依赖可用后 | **192 passed in 11.93s** | 12 个测试文件的定向集，含完整入口、HTTP 分派和来源上下文；没有真实 FM 操作 |

测试包阶段的定向集包含三个新增应用服务、活动后端、比赛情报、HTTP 分派、HTTP 修改来源上下文、食堂方案、医疗默认/不可用状态及批量读取与金额规范化等检查。

其他已记录检查：Python 编译、三个新服务独立导入、依赖方向、旧门面签名、迁移范围、`git diff --check` 以及 Qoder 独立审查。Qoder 未发现三批提取引入的生产行为回归；测试缺口由 Codex 补齐并验证。

日志保留在 Git 忽略的本地目录：

- `output/codex-refactor-final-regression.log`
- `output/test-build-20261017/native-enabled-tests.log`
- `output/refactor-scope-audit.json`
- `output/refactor-verification-2026-10-17.md`
- `output/` 中各批 Agent 输出、审查报告和控制流对比记录。

## 6. 原生依赖与 Windows 测试包

### 6.1 已解除的历史阻断

最初因缺少 `fmodd_native_core.dll`，完整运行时导入和部分 HTTP / 门面测试无法收集。用户当时选择先完成离线草稿，因此医疗和食堂早期记录标为“离线草稿”。

之后用户明确要求打包测试版，才在隔离构建目录准备工具链、从当前源码编译原生依赖并补跑相关入口测试。**当前不能再把 DLL 缺失描述为仍存在的阻断**；旧计划和执行报告中的早期阻断属于阶段历史，后续补充记录说明了其解除过程。

### 6.2 构建内容

- Rust GNU 1.99.1 使用官方清单核对下载包哈希；Zig 0.16.0 仅安装到本次构建目录。
- 从项目现有源码编译 `fmodd_native_core.dll` 和 `fmodd_hook_core.dll`，两者 ABI 均为 1；没有修改原生源码。
- 使用系统 .NET 编译器构建 WebView2 桌面宿主，通过既有脚本恢复固定版本及哈希的 WebView2 SDK。
- 使用既有生成器构建内嵌 Web 资源，没有手改生成资源包。
- 使用 PyInstaller 6.20.0 生成 Windows x64 目录式测试版，补齐 `fm_collector` 运行模块。
- 包内保留真实文件哈希与原生库完整性检查，没有用假模块或绕过校验的方式生成“通过”结果。
- 工具链、构建脚本、日志和中间产物位于 `output/test-build-20261017/`，未修改系统 PATH，未加入 Git。

### 6.3 交付产物

| 产物 | 路径 |
| --- | --- |
| 测试包 ZIP | [FMODD-Test-20261017.zip](../../../dist/FMODD-Test-20261017.zip) |
| ZIP 校验文件 | [FMODD-Test-20261017.zip.sha256](../../../dist/FMODD-Test-20261017.zip.sha256) |
| 解压后的主程序 | `dist/FMODD-Test-20261017/FMODD-Test-20261017.exe` |
| 包内说明 | `dist/FMODD-Test-20261017/测试说明.md` |
| 包内构建清单 | `dist/FMODD-Test-20261017/BUILD-MANIFEST.json` |

ZIP 大小：**68,937,488 字节，约 69 MB**。

SHA-256：

```text
5f3de22fee3028433037262631ae92031777cbd7e58d425baef0944f43badf14
```

汇总时重新计算的 ZIP 大小和哈希与交付记录一致。测试包仍使用产品版本 V2.7.0beta，通过文件名区分内部测试构建。

完整解压后运行，必须保留 `_internal` 等随包目录；无需安装 Python，运行环境为 Windows x64、.NET Framework 4.8 和 WebView2 Runtime。

测试入口在导入应用前把 FMODD 数据目录固定为 EXE 旁的 `test-data`，与正式版账户和设置分开。该目录隔离的是 FMODD 本地数据，**不构成游戏存档沙箱**。

### 6.4 产物验证边界

已检查包内九个关键模块、原生 / 宿主 / 资源哈希、ZIP 完整性、冻结路径下源码导入和内嵌首页读取。冻结路径检查通过，读取到首页内容 101,352 字节。

尚未启动打包后的产品 EXE，没有连接 Football Manager，没有安装运行中的 Hook，也没有操作真实账户或存档。包内容验证不能替代桌面启动、真实游戏及真实事务验收。

## 7. 已有 UI 预览

当前三批后端服务提取和测试包构建没有额外修改 UI。此前业务 / 钱包调整已经留下使用真实前端和隔离示例数据渲染的预览，存于原目录，未复制到当前工作树：

| 预览 | 原目录文件 |
| --- | --- |
| 心理辅导 | `F:/codex/FM-ODD/output/ui-preview/01-counseling.png` |
| 辅导确认 | `F:/codex/FM-ODD/output/ui-preview/02-counseling-confirm.png` |
| 钱包不足 | `F:/codex/FM-ODD/output/ui-preview/03-wallet-insufficient.png` |
| 设置 | `F:/codex/FM-ODD/output/ui-preview/04-settings.png` |
| 随机情报报价 | `F:/codex/FM-ODD/output/ui-preview/05-intelligence-random.png` |
| 指定情报报价 | `F:/codex/FM-ODD/output/ui-preview/06-intelligence-specific.png` |
| 商店 | `F:/codex/FM-ODD/output/ui-preview/07-shop.png` |
| 钱包 +100B 后续调整 | `F:/codex/FM-ODD/output/ui-preview/08-wallet-100b.png` |

前七张记录较早阶段；第八张记录后续钱包入口调整，不能把较早的设置图当作最终钱包布局。汇总时核对八个文件均存在，没有重新渲染预览。后续如涉及可见界面变化，继续遵守“测试后提供实际预览图”的要求。

## 8. 盘口刷新检查：仅建议，尚未实施

用户询问盘口刷新区域是否需要优化，本轮仅做只读源码检查，得到四项建议：

1. 快速 / 全量刷新入口检查后台返回的 `started`，区分已启动、已有任务占用和其他未启动情况，避免统一显示“刷新中”。
2. 刷新结束时优先判断错误，保留失败原因和重试入口，避免旧快照存在时被显示为“最新状态”。
3. 将刷新按钮、真实阶段、处理数量和最后成功刷新时间放在同一区域，说明快速与全量刷新的用途。
4. 状态轮询连接异常时采用退避并合并提示，减少反复弹错和无效请求。

后端已有缓存复用、轻量状态接口、阶段耗时和内存锁等待 / 持有时间记录。是否需要进一步提速，应先结合实际记录定位耗时；当前没有进行真实 FM 性能测量，也没有承诺具体提速比例。

用户随后要求暂停，因此四项建议都未修改、未测试、未纳入测试包。

## 9. DeepSeek / Qoder 本机环境记录

本节用于说明此前协作环境处理，不属于 FMODD 仓库差异。本次汇总没有重新连接或更改这些配置。

- 用户所称 DeepSeek Hermes，实际接入的是安装在 `E:/deepseek` 的 DeepSeek Harness。
- 之前连接失败涉及 Kaspersky HTTPS 拦截下的证书链校验和后续连接超时。曾按用户要求撤回 CLI 证书信任修改；后来经单独同意，仅为桌面端启用系统证书信任插件。
- 桌面端插件位置：`C:/Users/SAS/.dsh/profiles/desktop/local-plugins/system-ca.mjs`；桌面配置由其 profile 下的 `cordis.patch.yml` 加载。没有因此修改 Windows 根证书库或全局环境变量。
- CLI 的证书信任回退保持，不因桌面修复重新启用 CLI 全局信任覆盖。用户后来关闭 Kaspersky HTTPS 扫描，并确认语音模型下载问题已解决；该下载问题不再作为待办。
- 之后 DeepSeek 实际完成了三批代码任务，Qoder 实际完成了对应独立审查；这是历史任务成功记录，不保证未来网络始终可用。
- Qoder 当前按 CLI 调用，并非通过 Codex MCP 调用；包装脚本为 `F:/codex/agent-connections/qoder.ps1`。
- DeepSeek CLI 包装脚本为 `F:/codex/agent-connections/deepseek.ps1`；本轮任务运行记录在工作树 `output/` 下。
- 此前核对的默认模型：DeepSeek CLI 为 `deepseek-flash`；桌面 profile 为 `deepseek-flash`、reasoning high；Qoder 包装脚本默认指定 `Qwen3.8-Flash`。这些是当时读取的配置，本次未再次核实实时值。
- 协作方式保持为 Codex 总协调、DeepSeek 优先实现、Qoder 独立审核。没有实现新的 Worktree / Agent 产品侧边栏。

## 10. 暂停点和后续顺序

1. 由用户完整解压测试包并进行桌面启动和真实游戏测试，记录所用 FM 版本、具体操作、异常文字及必要截图。
2. 如发现问题，先按上述基线和构建清单定位，再做有范围的修复；保持原账户、对象身份、旧值校验、回读和回滚保护。
3. 如果决定继续盘口刷新优化，再单独实施第 8 节的建议，并完成相关测试及真实预览。
4. 刷新主循环、训练和经济存储的进一步拆分仍属于后续路线，不在已经完成的三批重构范围内。
5. 用户验收后再决定 Git 提交、合并或发布。当前没有自动提交、推送或合并，未跟踪的新服务 / 测试 / 文档也尚未进入提交历史。

继续工作时先读本文，再读[当前重构执行报告](2026-10-17-backend-refactor-progress.md)、[当前计划](../plans/2026-10-17-current-baseline-backend-refactor.md)和[设计基线](../specs/2026-10-17-current-baseline-backend-refactor-design.md)。早期比赛情报记录见[计划](../plans/2026-10-17-backend-intelligence-refactor.md)和[设计](../specs/2026-10-17-backend-intelligence-refactor-design.md)。

## 附录：当前完整文件改动清单

汇总前，`git status --porcelain --untracked-files=all` 列出 **55 个文件**：41 个已跟踪文件被修改，14 个未跟踪文件新增。本文另新增 1 个文档，因此清单包含 **56 个文件**。`M` 表示已跟踪文件有修改，`??` 表示新增但尚未跟踪；没有暂存改动。

清单包含继承修改和本轮修改，不等于全部由本轮新增。`output/`、`dist/`、构建工具链、DLL、测试数据、生成资源及本机 Agent 配置不纳入该清单，保持在 Git 之外。

| Git 状态 | 文件 | 与本轮开始时的实际基线关系 |
| --- | --- | --- |
| `M` | [docs/ARCHITECTURE.md](../../../docs/ARCHITECTURE.md) | 本轮继续修改 |
| `M` | [docs/FEATURE_INDEX.md](../../../docs/FEATURE_INDEX.md) | 本轮继续修改 |
| `M` | [docs/I18N_ARCHITECTURE.md](../../../docs/I18N_ARCHITECTURE.md) | 继承，内容保持 |
| `M` | [docs/RUNTIME_CONTRACTS.md](../../../docs/RUNTIME_CONTRACTS.md) | 继承，内容保持 |
| `M` | [src/fm_odds_web.py](../../../src/fm_odds_web.py) | 本轮继续修改 |
| `M` | [src/tools/account_application.py](../../../src/tools/account_application.py) | 继承，内容保持 |
| `M` | [src/tools/betting_account.py](../../../src/tools/betting_account.py) | 继承，内容保持 |
| `M` | [src/tools/club_economy.py](../../../src/tools/club_economy.py) | 继承，内容保持 |
| `M` | [src/web/app.css](../../../src/web/app.css) | 继承，内容保持 |
| `M` | [src/web/app.js](../../../src/web/app.js) | 继承，内容保持 |
| `M` | [src/web/dark-theme.css](../../../src/web/dark-theme.css) | 继承，内容保持 |
| `M` | [src/web/i18n.de.js](../../../src/web/i18n.de.js) | 继承，内容保持 |
| `M` | [src/web/i18n.es.js](../../../src/web/i18n.es.js) | 继承，内容保持 |
| `M` | [src/web/i18n.facilities.js](../../../src/web/i18n.facilities.js) | 继承，内容保持 |
| `M` | [src/web/i18n.fr.js](../../../src/web/i18n.fr.js) | 继承，内容保持 |
| `M` | [src/web/i18n.ja.js](../../../src/web/i18n.ja.js) | 继承，内容保持 |
| `M` | [src/web/i18n.js](../../../src/web/i18n.js) | 继承，内容保持 |
| `M` | [src/web/i18n.ko.js](../../../src/web/i18n.ko.js) | 继承，内容保持 |
| `M` | [src/web/i18n.pt-BR.js](../../../src/web/i18n.pt-BR.js) | 继承，内容保持 |
| `M` | [src/web/i18n.pt-PT.js](../../../src/web/i18n.pt-PT.js) | 继承，内容保持 |
| `M` | [src/web/i18n.ru.js](../../../src/web/i18n.ru.js) | 继承，内容保持 |
| `M` | [src/web/i18n.settings.js](../../../src/web/i18n.settings.js) | 继承，内容保持 |
| `M` | [src/web/i18n.shell.js](../../../src/web/i18n.shell.js) | 继承，内容保持 |
| `M` | [src/web/i18n.static.js](../../../src/web/i18n.static.js) | 继承，内容保持 |
| `M` | [src/web/i18n.tw.js](../../../src/web/i18n.tw.js) | 继承，内容保持 |
| `M` | [src/web/index.html](../../../src/web/index.html) | 继承，内容保持 |
| `M` | [tests/test_account_application.py](../../../tests/test_account_application.py) | 继承，内容保持 |
| `M` | [tests/test_activity_centre_backend.py](../../../tests/test_activity_centre_backend.py) | 继承，内容保持 |
| `M` | [tests/test_activity_centre_frontend.py](../../../tests/test_activity_centre_frontend.py) | 继承，内容保持 |
| `M` | [tests/test_frontend_refresh_recovery.py](../../../tests/test_frontend_refresh_recovery.py) | 继承，内容保持 |
| `M` | [tests/test_frontend_state_sync.py](../../../tests/test_frontend_state_sync.py) | 继承，内容保持 |
| `M` | [tests/test_i18n_catalog_contract.py](../../../tests/test_i18n_catalog_contract.py) | 继承，内容保持 |
| `M` | [tests/test_i18n_facilities.py](../../../tests/test_i18n_facilities.py) | 继承，内容保持 |
| `M` | [tests/test_language_learning.py](../../../tests/test_language_learning.py) | 继承，内容保持 |
| `M` | [tests/test_match_intelligence.py](../../../tests/test_match_intelligence.py) | 继承，内容保持 |
| `M` | [tests/test_match_intelligence_frontend.py](../../../tests/test_match_intelligence_frontend.py) | 继承，内容保持 |
| `M` | [tests/test_psychological_counseling.py](../../../tests/test_psychological_counseling.py) | 继承，内容保持 |
| `M` | [tests/test_relationship_api.py](../../../tests/test_relationship_api.py) | 继承，内容保持 |
| `M` | [tests/test_settings_frontend_optimization.py](../../../tests/test_settings_frontend_optimization.py) | 继承，内容保持 |
| `M` | [tests/test_training_ground.py](../../../tests/test_training_ground.py) | 继承，内容保持 |
| `M` | [tests/test_wallet_transfer.py](../../../tests/test_wallet_transfer.py) | 继承，内容保持 |
| `??` | [docs/superpowers/plans/2026-10-17-backend-intelligence-refactor.md](../../../docs/superpowers/plans/2026-10-17-backend-intelligence-refactor.md) | 继承，内容保持 |
| `??` | [docs/superpowers/plans/2026-10-17-current-baseline-backend-refactor.md](../../../docs/superpowers/plans/2026-10-17-current-baseline-backend-refactor.md) | 本轮继续修改 |
| `??` | [docs/superpowers/reports/2026-10-17-backend-refactor-progress.md](../../../docs/superpowers/reports/2026-10-17-backend-refactor-progress.md) | 本轮新增 |
| `??` | [docs/superpowers/reports/2026-10-18-project-change-summary.md](../../../docs/superpowers/reports/2026-10-18-project-change-summary.md) | 本轮新增 |
| `??` | [docs/superpowers/specs/2026-10-17-backend-intelligence-refactor-design.md](../../../docs/superpowers/specs/2026-10-17-backend-intelligence-refactor-design.md) | 继承，内容保持 |
| `??` | [docs/superpowers/specs/2026-10-17-current-baseline-backend-refactor-design.md](../../../docs/superpowers/specs/2026-10-17-current-baseline-backend-refactor-design.md) | 继承，内容保持 |
| `??` | [src/tools/canteen_application.py](../../../src/tools/canteen_application.py) | 本轮新增 |
| `??` | [src/tools/counseling_application.py](../../../src/tools/counseling_application.py) | 本轮新增 |
| `??` | [src/tools/match_intelligence_application.py](../../../src/tools/match_intelligence_application.py) | 继承，内容保持 |
| `??` | [src/tools/medical_application.py](../../../src/tools/medical_application.py) | 本轮新增 |
| `??` | [tests/test_canteen_application.py](../../../tests/test_canteen_application.py) | 本轮新增 |
| `??` | [tests/test_cheat_balance_add_100.py](../../../tests/test_cheat_balance_add_100.py) | 继承，内容保持 |
| `??` | [tests/test_match_intelligence_application.py](../../../tests/test_match_intelligence_application.py) | 继承，内容保持 |
| `??` | [tests/test_medical_application.py](../../../tests/test_medical_application.py) | 本轮新增 |
| `??` | [tests/test_psychological_counseling_application.py](../../../tests/test_psychological_counseling_application.py) | 本轮新增 |
