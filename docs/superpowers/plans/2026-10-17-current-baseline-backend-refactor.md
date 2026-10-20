# 当前修改版后端重构实施计划

> **历史基线（2026-10-17）：** 本计划记录当时工作树（包括既有未提交改动）上的实施与验证；下文测试数字和语言范围均为历史记录。自提交 `eaf59ad`（2026-10-20）起，当前 UI 仅支持 `en-GB` 和 `zh-CN`；见 [`AGENTS.md`](../../../AGENTS.md) 与 [`I18N_ARCHITECTURE.md`](../../I18N_ARCHITECTURE.md)。

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans task-by-task; delegated implementation may use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax for tracking. Honor the user's DeepSeek-first code-task preference and preserve existing work.

**Goal:** 在当前修改版上，依次拆出心理辅导、医疗、食堂海参奖励的应用编排，保持用户已确认的业务行为。

**Architecture:** `LocalOddsState` 保留兼容门面、唯一运行时状态与调度；三个领域各有一个显式注入 I/O 的应用服务。复用现有账户、情报、领域事务、路由和状态发布模块，逐批迁移，不同时重写领域与持久化层。

**Tech Stack:** Windows、Python 3.10+、标准库、pytest；原生集成仍使用现有 Rust/C++ 核心；界面继续直接读取 `src/web/`。

**Spec:** [当前修改版的后端重构设计](../specs/2026-10-17-current-baseline-backend-refactor-design.md)。

**状态：** 三批结构提取已在独立 Worktree 完成并经审查；离线相关集 166 passed。用户随后明确要求测试包，已构建真实原生依赖并跑通完整入口/HTTP 等定向集 192 passed，生成 Windows x64 测试 ZIP。真实 FM 仍未验收，未自动启动产品、提交、推送或发布。详见 [执行与验收记录](../reports/2026-10-17-backend-refactor-progress.md)。

## Global Constraints

- 起点为 `F:/codex/FM-ODD` 当前工作树；现有分支 `refactor/match-intelligence-service`，HEAD `cd5900858a08cb9333b1d3a750fabb220cd5ca79` 不包含未提交改动，不能单独用作重构基线。
- 保持现有 API、响应字段、错误语义、存储格式、价格、冷却及 FM24/FM26 支持范围。
- 保持锁顺序、锁覆盖范围、账户绑定、预期旧值校验、写后回读和恢复调用顺序。
- 保留钱包 +100B 的金额、位置、入账及银行隔离；保留辅导固定结果/钱包付费、固定情报价及免费功能移除。
- 不操作真实 FM、不安装 Hook、不修改真实账户/存档、不启动产品 EXE；不自动构建发布包、提交或推送。
- 本轮默认不改 UI；必要的可见调整须单独说明并提供真实前端渲染的预览图。字号不小于 13px，相关文案覆盖 11 种语言。
- 不伪造原生依赖，不删除行为断言；既有缺陷的修复另列任务，不混入本轮迁移。

## Review Focus

- 辅导余额不足、效果失败、关系提交失败、恢复失败与归档失败：保持当前调用及补偿顺序，区分“尝试恢复”和“恢复成功”。归属 Task 1。
- 存档/经理切换及依赖在首次调用后被替换：不复用旧账户、地址、函数引用或响应缓存。归属各批兼容门面测试。
- 医疗名单部分不可读、时钟缺失或跨游戏日推进：保留等待、取消、完成及扣费的原始条件，不能把未解析球员当作康复。归属 Task 2。
- 海参批量含重复、无效或超过 200 个 ID，以及中途失败：保留去重/拒绝、单会话及部分完成语义。归属 Task 3。
- HTTP 来源上下文及旧门面函数替换点：完整导入、响应字段和错误分派不因隔离测试通过而免检。归属 Task 0、各批集成验收。

## 现状与不重复建设的部分

本次检查 `src/fm_odds_web.py` 为 23,225 行，`club_economy.py` 为 4,994 行；行数只描述当前体量。以下边界已存在：

| 已有模块 | 后续安排 |
| --- | --- |
| `account_application.py`、`AccountOperation` | 复用；不再设计第二套钱包/账户服务 |
| `match_intelligence_application.py` | 已完成的首批成果，仅做兼容回归，不重新提取 |
| `player_departure_application.py` | 已有球员离队服务，暂不改写其内部结构 |
| `api_routing.py`、`state_patches.py`、`state_publication.py` | 保留现有路由、响应来源与状态发布协议 |
| `player_effects.py`、`club_reader.py` | 复用效果事务及原生安全边界，不另建通用事务框架 |

近期定向记录为 102 passed；完整 HTTP/原生入口仍受原生库缺失限制。本次只编写计划，没有重跑全套测试。

## 批次与文件责任

| 顺序 | 新增模块 / 责任 | 迁移的现有入口 | 明确保留 |
| --- | --- | --- | --- |
| 0 | 当前源码基线清单与验证记录 | 无产品迁移 | 当前未提交源码、已导入补丁及 UI |
| 1 | `src/tools/counseling_application.py`：单次辅导用例 | `LocalOddsState.psychological_counseling` | 领域规则、原生效果、关系归档所有者和前端逐人批量 |
| 2 | `src/tools/medical_application.py`：手动/默认治疗及推进回调 | `update_medical_treatment`、`update_default_medical_treatment`、`_process_due_medical_treatments`、`_apply_default_medical_treatments` | 游戏日调度、名单真值及 `club_economy` 治疗状态 |
| 3 | `src/tools/canteen_application.py`：单人及批量海参奖励 | `_canteen_sea_cucumber_one`、`_canteen_sea_cucumber_context`、`canteen_sea_cucumber`、`canteen_sea_cucumbers` | `canteen_plan_update`、CA Hook 方案同步及底层写会话实现 |

三个应用服务分别可独立审核、退回和验收。虽然领域边界独立，共享入口文件的修改必须串行；后续批次从上一批验收后的工作树开始。

### Task 0：固定当前行为基线与验证边界

**Files:** Create `output/refactor-baseline-2026-10-17.json`、`output/refactor-verification-2026-10-17.md`（本地忽略产物）；只读当前源码、已有测试与 `output/AGENT-DELEGATION-REPORT.md`。

**Interfaces:** 清单记录当前分支、HEAD、源码/测试路径及 SHA-256、未提交与未跟踪源码清单；验证记录把隔离通过、集成受阻和未运行分别列出。不纳入账户、存档、凭证、日志或产品构建输出。

- [x] **Step 1:** 核对 `git status --short` 与当前 diff，记录本工作树的源码清单；若以后使用新工作区，先迁移并校验全部必要的未提交/未跟踪源码，不从远端旧版本重新开始。
- [x] **Step 2:** 重跑已有可用定向集，记录实际用例数量和输出；不能只引用历史 102 项结果：

```powershell
./.venv/Scripts/python.exe -m pytest tests/test_match_intelligence_application.py tests/test_match_intelligence_frontend.py tests/test_cheat_balance_add_100.py tests/test_psychological_counseling.py tests/test_activity_centre_frontend.py tests/test_i18n_facilities.py tests/test_i18n_settings.py tests/test_settings_frontend_optimization.py tests/test_i18n_catalog_contract.py -q
```

- [x] **Step 3:** 对 `tests/test_match_intelligence.py`、`tests/test_api_http_dispatch.py`、`tests/test_http_mutation_context.py` 做定向收集检查；若仍缺原生库，记录具体导入阻断，不自动构建、改 ACL 或以假模块替代。
- [x] **Step 4:** 明确本批允许做离线提取草稿、哪些集成检查尚不能验收；只选当前任务需要的开发依赖。医疗和食堂的整体验收不得跳过相应完整入口回归。

**退出条件：** 当前行为有可定位的源码基线，既有失败与环境阻断可区分，未改动任何真实运行数据。

### Task 1：提取心理辅导应用服务（下一批优先执行）

**Files:** Create `src/tools/counseling_application.py`、`tests/test_psychological_counseling_application.py`；Modify `src/fm_odds_web.py` 的 `psychological_counseling` 及对应依赖工厂；同步 `docs/ARCHITECTURE.md`、`docs/FEATURE_INDEX.md`。既有领域回归为 `tests/test_psychological_counseling.py`。

**Interfaces:**

- `CounselingApplicationService(runtime: CounselingRuntime, io: CounselingIO).counsel(payload: dict[str, Any]) -> dict[str, Any]`。
- `CounselingRuntime` 只声明当前用例使用的 `lock`、`memory_lock`、`output`、账户绑定、实时球员查询和关系归档能力；不持有复制状态。
- `CounselingIO` 为冻结数据类，显式提供游戏时钟、价格换算及基础价、钱包余额/调整、是否不满、效果/关系写入、恢复、领域辅导结算、经济/福利投影；回调沿用现有函数签名。
- `LocalOddsState._counseling_application()` 每次绑定当前模块依赖；原 `psychological_counseling(payload)` 委托 `counsel(payload)`，外部签名不变。

- [x] **Step 1:** 在新测试文件执行真实旧门面方法的隔离片段，刻画：固定 `unlocked` 结果、`local_purchase_price(100_000)` 钱包扣款及银行为零、余额不足无效果、锁顺序/释放、关系失败时恢复/退款，以及归档失败位于当前补偿边界之外的行为。
- [x] **Step 2:** 运行 `./.venv/Scripts/python.exe -m pytest tests/test_psychological_counseling_application.py -q`，确认这些刻画在迁移前通过；新增直接服务调用测试，确认因新模块不存在而失败。
- [x] **Step 3:** 按当前控制流提取服务并接上门面；保留共享两天冷却、关系归档、原始异常与恢复/退款尝试顺序，不顺手重写成新的事务模型。
- [x] **Step 4:** 用相同测试复核迁移结果；新增跨两次调用替换依赖、跨账户重新绑定、直接导入服务无需原生 DLL 的断言。恢复失败仍退款等现状明确标记，不误报为恢复成功。
- [x] **Step 5:** 运行新测试、既有辅导领域及活动前端检查；环境可用时运行 `tests/test_activity_centre_backend.py` 中辅导相关用例和 HTTP 来源上下文回归。检查 `git diff --check`，确认前端无额外变化。
- [x] **Step 6:** 审核新增服务的依赖方向、门面签名、补偿边界与响应 `counseling/economy/welfare`；更新所有权文档和验收记录。未授权时不提交或推送。

**执行记录（2026-10-17）：** 已完成结构提取、迁移前 5 项刻画、缺模块失败验证及迁移后隔离回归。Codex 最终相关集 117 passed，其中新应用边界 15 项；Qoder 未发现产品行为回归，指出的恢复失败测试缺口已补齐。完整活动后端/HTTP 导入仍因缺少 Rust 原生库受阻，真实 FM 未验证；勾选记录不代表这些集成层已通过。证据见本地 `output/refactor-verification-2026-10-17.md`。

- [x] **完整入口定向验收：** 后续明确授权打包后已构建原生依赖，活动后端及 HTTP 入口进入 192 项通过集。
- [ ] **实机验收：** 真实 FM 行为尚未验证。

**退出条件：** 用例主体离开入口文件，独立服务及旧门面行为一致；不足余额、异常与账户切换有行为测试；完整集成未验证时单独列明。

### Task 2：提取医疗应用编排

**前置条件：** Task 1 已审核；医疗现有完整入口测试具备可执行环境，或明确本批只产出离线草稿。此批不得同时迁移治疗存储和游戏日调度器。

**Files:** Create `src/tools/medical_application.py`、`tests/test_medical_application.py`；Modify `src/fm_odds_web.py` 中批次表列出的四个入口与工厂；同步架构/功能索引。保留 `club_economy.py`、`club_reader.py` 的领域与原生职责。

**Interfaces:** `MedicalApplicationService(runtime: MedicalRuntime, io: MedicalIO)` 提供 `update_treatment(payload) -> dict[str, Any]`、`update_default(payload) -> dict[str, Any]`、`process_due(game_date: str, profiles: list[dict[str, Any]]) -> dict[str, Any]`、`apply_default(game_date: str, profiles: list[dict[str, Any]], *, status: dict[str, Any] | None = None) -> dict[str, Any]`。原四个方法保留原签名。`MedicalIO` 显式提供时钟、设置/推进治疗、伤病变换/完成及投影；`MedicalRuntime` 只提供当前用例所需状态和保护操作。

- [x] **Step 1:** 在迁移前刻画手动方案切换、默认策略快照传递、缺失时钟、空/部分名单、资金不足停止、未解析球员等待，以及取消/完成的调用顺序。
- [x] **Step 2:** 运行刻画确认旧行为通过，再新增直接服务入口测试并观察缺模块失败；不把当前领域测试复制成实现细节断言。
- [x] **Step 3:** 提取四个用例；保留当前锁范围、球员 `availability` 更新、`club_medical_auto_result` 发布、单次医疗快照复用；推进仍由现有游戏日流程调用。
- [x] **Step 4:** 验证服务不重建活动/语言/情报福利投影来做默认识别，不缓存伤病真值或旧地址；复核原门面的逐次依赖绑定。
- [x] **Step 5:** 运行 `tests/test_medical_application.py`、`tests/test_medical_default_treatment.py`、`tests/test_medical_treatment_prices.py`、`tests/test_medical_unavailability_sync.py`。其中完整导入受阻时如实登记，不整组跳过后标绿。
- [x] **Step 6:** 审核 API 返回值、取消/完成/等待分支、未解析球员处理及文档；单独验收本批，不捎带改工资、语言课程或治疗算法。

**执行记录（2026-10-17，离线草稿）：** 已提取四条医疗路径；迁移前 9 项刻画、缺模块失败验证、迁移后 14 项新测试均有日志。Codex 独立相关集 39 passed；Qoder 未发现生产回归；四个用例在依赖重命名后控制流 AST 等价。完整入口/HTTP 与实机验收受原生依赖缺失限制，勾选仅记录离线执行和审查，不表示正式集成验收完成。

- [x] **完整入口定向验收：** 后续测试包阶段已加载真实原生 DLL，完整门面/HTTP 相关定向集通过；不等同于真实 FM 写入验证。
- [ ] **实机验收：** 真实 FM 治疗行为尚未验证。

**退出条件：** 手动、默认及推进路径共同使用一个医疗应用所有者，领域状态与调度真值未迁移；对应隔离和完整入口回归分别有结果。

### Task 3：提取食堂单人/批量海参奖励

**执行范围补充（2026-10-17）：** 用户确认暂无已知匹配原生 DLL，选择先完成离线草稿。因此允许顺序产出本批可审阅的服务/门面草稿及隔离测试；以下原定完整门面测试环境要求保留为正式验收门禁，不能用离线通过代替。

**前置条件：** Task 2 审核完成；具备执行海参既有门面测试的环境。CA Hook 供餐方案与 `canteen_plan_update` 不在迁移范围。

**Files:** Create `src/tools/canteen_application.py`、`tests/test_canteen_application.py`；Modify `src/fm_odds_web.py` 中四个海参方法及工厂；同步架构/功能索引；保留底层 `canteen_sea_cucumber_memory_session` 与 `commit_player_effect`。

**Interfaces:** `CanteenApplicationService(runtime: CanteenRuntime, io: CanteenIO)` 提供 `reward_one(payload: dict[str, Any]) -> dict[str, Any]`、`reward_batch(payload: dict[str, Any]) -> dict[str, Any]`；为保留旧辅助门面，提供 `context() -> tuple[dict[str, Any], int, str]` 及 `reward_player(player_id: int, requested_team_id: int, *, manager: dict[str, Any], manager_id: int, game_date: str, memory_session: Any = None) -> dict[str, Any]`。显式 I/O 传入金额换算、合并扣费/退款、原生效果/关系/恢复、效果提交、写会话工厂、错误描述和经济投影；Runtime 仍只暴露原状态/锁及实时目标解析。

- [x] **Step 1:** 刻画换算后 60K 基础价、银行/钱包原分账、国家队拒绝、单人效果及好感更新、失败恢复/退款；批量覆盖重复 ID、非法 ID、空列表、超过 200 人、第二人失败不再执行后续人员。
- [x] **Step 2:** 确认旧门面刻画通过；新增服务独立调用测试，观察缺模块失败。
- [x] **Step 3:** 提取四个方法并委托；保留一个批量写会话、逐人独立事务与遇错停止。不得把批量包装成跨全队原子事务，也不新增长期会话缓存。
- [x] **Step 4:** 验证 `requested/completed/results/failure/economy` 响应与错误分类相同；保留已有事务工具在关系提交失败后的恢复语义，不合并辅导与海参的不同补偿路径。
- [x] **Step 5:** 运行 `tests/test_canteen_application.py`、`tests/test_canteen_sea_cucumber.py`、`tests/test_canteen_page.py`；对 `tests/test_canteen_plan.py` 做相关兼容回归，确认 CA Hook 方案未改变。
- [x] **Step 6:** 审核单会话生命周期、锁范围、原分账退款及部分完成结果；更新本批验收记录并给出剩余原生/实机限制。

**执行记录（2026-10-17，离线草稿）：** 已提取四条食堂海参路径，迁移前 9 项刻画、缺模块失败验证、迁移后 DeepSeek 18 项应用测试有日志，Codex 补齐恢复失败分类/退款回归后为 19 项。最终三批相关回归 166 passed；食堂四条路径控制流 AST 等价，Qoder 未发现生产行为回归，指出的测试缺口已补齐。Step 5 中两个完整门面测试因原生库缺失无法收集，保留未完成，不将整批标为正式验收通过。

- [x] **完整入口定向验收：** 后续测试包阶段已构建依赖，原有海参门面、供餐方案兼容及 HTTP 相关定向集通过。
- [ ] **实机验收：** 真实 FM 海参奖励及原生写入行为尚未验证。

**退出条件：** 单人及批量奖励有独立应用入口，旧辅助及外部门面继续可用，前端交互和 Hook 供餐方案保持不变。

## 三批之后的路线（另写子计划，不在本轮实现）

1. **经济模块的纯价格/只读投影：** 先画出 `club_economy.py` 的账户锁与持久化调用图，只提取无副作用计算；已有报价模块不重复建设。账户读写、贷款、工资和统一账本不一起迁移。
2. **训练与关系结算：** 先审计 `relationship_training_room_preview`、`relationship_training_room_settle` 与 `training_run` 的共享事务，再单独规划；不能因为方法长就机械切分。当前前两者分别约 400/518 行。
3. **刷新与游戏日生命周期：** 最后评估 `_refresh_worker`（约 712 行）和 `watch_game_date`（约 369 行）；先建立连接、切档、取消、重入、关闭及线程竞态的专项测试，再决定提取边界。
4. **前端组件拆分：** 本次后端计划不包含 UI 重设计。若后续单独拆 `app.js`，先固定状态同步与交互契约，再单独计划和提供前后预览。

## 分派、验收与交付

| 角色 | 每批责任 | 接受条件 |
| --- | --- | --- |
| DeepSeek | 优先实现本批新服务和对应测试 | 返回实际 diff、测试记录、未完成项；传输错误或空回答不算交付 |
| Qoder | 只读审查本批行为保持、依赖方向与文档 | 给出可定位的发现；不得未经审核改其他 Agent 负责的文件 |
| Codex | 固定当前基线、控制共享文件、核对 Agent 部分修改、运行验证并整合 | 对照当前需求及行为证据逐项接受，不直接相信“已完成”自述 |

外部 Agent 每批重新验证实际任务能力；近期修复后的短问答不等于长任务验收。失败最多做一次针对性调整，仍失败则核对部分修改后由 Codex 接手，不让重试无限阻塞主任务。

每批交付：可审阅差异、边界行为测试、相关回归结果、更新的架构/功能索引及未验证项。仅在该批全部必需验收满足后勾选完成；缺少完整导入验证时标注其具体状态。必要 UI 变动另附预览，默认不生成与后端改动无关的新设计图。

本次交付仅为这份新计划和配套设计文档；后续执行沿用已确定的 DeepSeek 优先、Qoder 审查、Codex 验收方式，不自动提交、推送或发布。


## 测试包阶段补充

2026-10-17 用户明确请求打包测试版后，已准备本地独立构建工具并编译当前源码原生核心。上文各批执行记录中的缺库阻断是离线阶段的历史状态；本次后续完整入口/HTTP 等定向集 192 passed，门禁状态以本补充及最新勾选为准。测试包在 `dist/FMODD-Test-20261017.zip`，未启动产品或操作真实 FM，真实游戏验收仍待进行。
