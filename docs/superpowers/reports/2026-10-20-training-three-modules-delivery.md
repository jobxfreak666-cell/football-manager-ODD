# 训练场三模块改版交付报告

日期：2026-10-20（Asia/Shanghai）
分支：`codex/training-three-modules`
基线：`f58bf0a`（`football-manager-odd-dev` 合并 PR #1 / #2 后的提交）
状态：**已实现并完成定向验证；未合并、未部署、未操作真实 FM/存档/账户**。
交付入口：PR #3 `https://github.com/jobxfreak666-cell/football-manager-ODD/pull/3`（head `codex/training-three-modules` → base `football-manager-odd-dev`，未合并）。

## 1. 提交链与改动范围

| 提交 | 内容 |
| --- | --- |
| `8778fd7` | T1 项目目录、三模块归属、50% 单次固定费用 |
| `945e101` | T2 新任务身份（`project_sku`/`module`/规则版本）与一次性旧任务迁移 |
| `943f990` | T3 服务端统一安排、单账户事务扣费、`client_submission_id` 幂等、作用域复验 |
| `0837cba` | T4 达标结束、取消不退款与迟到快照防护、旧器械路由停用、档案兼容 |
| `79770c0` | T5 前端三模块、一线队/职员名单→详情、位置工作区保留、旧入口移除 |
| `ad63985` | T5b 英文任务摘要补空格（`training.active_summary` 模板） |
| `5a7e977` | T4b 训练错误服务端本地化（49 个 `training.error.*`，en-GB/zh-CN） |
| `fbe041d` | T6 三模块 UI 文案键、清理失效器械/楼层键、契约文档改写 |
| `549c386` | T5c 关系训练前端旧断言更新（8F 入口移除、代码保留） |
| `64c4cf3` | T6 收尾：`i18n.static.js` 残余旧键清理、错误契约文档补充、本报告 |
| `af3f360` | 交付报告补充 PR #3 链接 |
| `dd6d701` | 修复前端 CI 触发的两个重写后旧断言（owned-club 区块提取、训练枚举 token） |

相对基线 `f58bf0a`：21 个文件、+5363/−2547（不含本报告等收尾文件）。

- 后端：`src/fm_odds_web.py`、`src/tools/training_catalog.py`（新增）、`src/tools/training_ground.py`、`src/tools/relationship_training.py`、`src/tools/i18n_runtime.py`
- 前端：`src/web/index.html`、`src/web/app.js`、`src/web/app.css`、`src/web/i18n.facilities.js`、`src/web/i18n.static.js`
- 文档：`docs/ARCHITECTURE.md`、`docs/FEATURE_INDEX.md`、`docs/RUNTIME_CONTRACTS.md`
- 测试：`test_training_task_rules.py`、`test_training_task_application.py`、`test_training_task_frontend.py`（均新增），以及训练/档案/关系训练/页面层级/i18n/刷新相关既有文件

## 2. 需求 R1—R14 对照

| 需求 | 实现位置与证据 |
| --- | --- |
| R1 仅三个模块 | `src/web/index.html`、`app.js::renderTraining`/`renderTrainingModuleTabs`；目录模块键 `player_training`/`position_training`/`staff_training`（`training_catalog.py`） |
| R2 合并室内/室外/实验室及办公室球员项目 | `training_catalog.training_module_for_product()`；29 个保留 SKU 归属测试（27 球员 / 1 位置 / 1 职员） |
| R3 一线队名单→球员详情 | `app.js::trainingFirstTeamPlayers`、`renderTrainingPersonDetail`、`loadTrainingRoster`；服务端 `_assert_training_first_team_player` 复验 |
| R4 位置训练保留 | `app.js` 位置阵型工作区（预设、自定义命名、拖拽、自动添加）+ `training_ground.build_position_training_focus`；位置项目免费、沿用原熟练度规则 |
| R5 职员名单→办公室项目 | `app.js::trainingCurrentStaff`、`trainingStaffEligible`；服务端 `_cached_staff_profile`、`COACHING_STAFF_JOB_TYPES`，保留玩家经理考证路径 |
| R6 取消购买/房间/楼层/摆放门槛 | UI 入口移除（`79770c0`）；旧 `purchase`/`floor_purchase`/`place`/`store`/`sell` 路由改为停用提示且无副作用（`0837cba`） |
| R7 一次任务一次付费、完成结束 | `training_run` 单事务建任务；`advance_training_focuses`/`_sync_training_focuses` 达标结算释放，不续费不建下一轮 |
| R8 单次费=原价 50% | `training_catalog.training_task_fee_minor()`：原 GBP 基准价 ×0.5 → `local_purchase_price` → `to_minor`，只换算一次；免费项为 0 且不造扣费流水 |
| R9 时长沿用原规则 | 原 `duration_mode`、训练点、目标阶段、习惯 7 日、考证原天数保留；仅计费与生命周期改变 |
| R10 单人单任务 | `_assert_player_available`/`_assert_staff_available` 与提交时内存锁；同一球员跨模块仅一个 active；职员考证单人单任务 |
| R11 多人可同项目、不限器械容量 | 移除实例容量/库存/摆放校验；`test_two_players_can_use_one_project`、`test_multiple_players_can_use_same_project` |
| R12 取消二次确认且不退款 | `app.js::fmoddConfirm(..., cancelLabel)` + `cancelTrainingTask`；`training_cancel` 释放人物、无返款，返回权威状态 |
| R13 旧任务统一取消、旧购买不退款 | `migrate_training_tasks()`/`task_rules_version=1`；`migrate_relationship_training_rooms()`；旧购买/楼层记录只读历史 |
| R14 其余内容/效果/资格沿用 | 原属性、隐藏/反向、习惯、位置、考证结算与原生校验保留；旧训练/档案回归 133 passed |

## 3. 收费、事务与幂等

- 报价与扣费只来自服务端：`training_task_fee_minor(FACILITIES[sku], load_settings())` 返回整数最小单位；前端只展示 `catalog.task_price_minor`，提交的价格/目录字段一律忽略。
- 扣款沿用银行→钱包顺序：`club_economy._collect_combined_funds()` 生成 payment 与钱包腿（只改内存）；`commit_documents_with_wallet_adjustments()` 一次写入 `training_ground` + 可选 `economy`/`wallet`/`relationship_training_rooms`，失败零写入、可安全重试。
- 任务与付款凭证同事务：focus/session 保存 `payment`、`project_sku`、`module`、`task_rules_version=1`；付费任务必须携带 `client_submission_id`，免费项目可为空且无钱包流水。
- 幂等：同编号且人物/队伍/项目/操作/目标语义一致时返回原 focus+session+payment（`duplicate=true`）；异意图复用编号拒绝；仅匹配规则版本 1；并发请求由内存锁串行，同一球员只成功一个。
- 迁移接线：`training_run` 在账户绑定后把“迁移取消 + 关系房间释放 + 新任务 + 扣款”合并进同一次提交；`_sync_training_focuses` 在推进前做一次性独立单写迁移。

## 4. 完成、取消与旧接口

- 达标结束：属性到目标、习惯满 7 日、考证到原天数照旧结算；满级存量位置任务到期直接完成且不写原生、不无限占用；无二次扣费、无自动下一轮。
- 取消：普通/位置/职员统一释放人物、不退款；取消后旧后台快照即使拿到 due 列表也会在 persist 校验处失败回滚，不产生 completed 记录；成长 Hook 同步失败不影响取消权威状态（返回可重试提示）。
- 旧接口：`/api/training/purchase|floor/purchase|place|store|sell` 在任何账户/文件读写前返回本地化停用提示，无扣款、加款、库存或返款；位置阵型拖拽相关代码保留。
- 错误本地化：训练接口错误携带 `message_key`（`training.error.*`）与 `message_params`，服务端按 `X-FMODD-Locale` 渲染 en-GB/zh-CN `message`；中文 legacy `error` 保留仅作诊断，前端优先显示 `message`。

## 5. 迁移与旧数据

- 文档级标记 `task_rules_version = 1`；标记前所有 active 且任务版本 <1 的普通训练统一置 `cancelled`，写 `cancelled_at/cancelled_on/cancel_reason=training_task_model_migration` 并追加历史；不退款、不补发效果、不回滚已生效原生变化；已完成/历史/档案与旧设施购买记录保留。
- 纯函数 `migrate_training_tasks(payload, *, game_date="")` 只修改传入文档并返回是否变化，调用方原子保存；保存失败重试安全；焦点级版本检查保证新任务不会被再次取消。
- 8F 关系训练：旧 `occupied`/`settling` 房间停止并释放占用，原活动保留为 `cancelled_session`（`status=cancelled`、原因、参与者、属性），无效果结算；房间库存与门禁不变，训练场导航不再显示 8F 入口。

## 6. 验证命令与真实结果

环境：Windows、Python 3.14.4、pytest 9.1.1（用户级安装，未写入仓库）、Node.js v26.1.0。
原生 mock 依赖使用 0bf53f9 官方测试包内同源 `fmodd_native_core.dll` / `fmodd_hook_core.dll`，放入被 gitignore 的 `src/build/`（未提交）。

| 命令 | 结果 |
| --- | --- |
| `python -m pytest tests/test_training_task_rules.py -q` | 11 passed |
| `python -m pytest tests/test_training_task_application.py tests/test_training_task_frontend.py -q` | 44 passed |
| `python -m pytest tests/test_training_ground.py tests/test_training_archive.py -q` | 133 passed, 2 subtests |
| `python -m pytest tests/test_i18n_facilities.py tests/test_i18n_locale_packs.py -q` | 10 passed |
| `python -m pytest tests/test_i18n_catalog_contract.py tests/test_i18n_static.py tests/test_i18n_api_contract.py -q` | 28 passed |
| `python -m pytest tests/test_relationship_training.py tests/test_relationship_training_frontend.py tests/test_existing_page_hierarchy.py -q` | 44 passed |
| `python -m pytest tests/test_api_http_dispatch.py tests/test_refresh_optimization.py -q` | 233 passed, 11 subtests, **1 failed（基线既有）** |
| `node --check src/web/app.js` / `i18n.facilities.js` / `i18n.static.js` / `i18n.js` | 通过 |
| `git diff --check` | 通过 |

已知基线失败：`test_refresh_optimization.py::test_disabled_championship_skips_extra_team_profiles_and_market_work`。已在基线 `f58bf0a` 的独立工作树复跑确认同样失败（该文件 1 failed / 218 passed），与本次改版无关，未在本分支修复。

未运行整个仓库测试；未启动 Football Manager、未安装 Hook、未读取/修改真实存档或账户、未运行正式产品 EXE、未构建发布包。

## 7. 界面证据

离线 mock 预览（临时键与假 API，仅预览、未入库）：

- 全量 56 张：`F:\dsh\preview\T5\shots\`，清单 `MANIFEST.txt`
- 矩阵：`en-GB`/`zh-CN` × 浅色/深色 × 1280/720 × 7 状态（球员名单、球员详情、进行中、已安排、职员详情、位置训练、取消确认）
- mock 工具：`F:\dsh\preview\T5\mock\`（`serve.py`、假 API、自动驱动脚本、临时 i18n 键）
- 位置训练预览保留阵型预设、命名自定义阵型、拖拽与自动添加；取消确认明确“不退款”。

## 8. 计划 Review Focus 对照

1. 收费/重试/并发：`test_paid_attribute_task_charges_server_fee_once`、`test_duplicate_submission_returns_original_payment`、`test_two_concurrent_requests_for_one_player_allow_one_task`、`test_commit_failure_leaves_no_task_or_charge`。
2. 作用域：`test_requested_team_must_be_current_club`、`test_non_first_team_player_is_rejected`、`test_staff_from_other_team_is_rejected`、旧编号过期作用域用例。
3. 迁移：`test_legacy_active_task_is_migrated_before_new_task`、迁移只取消一次、无退款/无效果、保存失败可重试。
4. 推进/完成：满级位置拒绝与到期完成、习惯/考证原天数、取消后迟到快照不结算。
5. 多人同项目与身份：同 SKU 多人、`player_id` 兼容字段不误判职员身份、位置/普通共用单人占用。

## 9. 未验证与限制

- 未在真实 FM24/FM26 上验证原生写入、过日、保存/重载与 Hook 同步。
- “CA 超 PA 确认”后的真实属性重分配、成长 Hook 提交后失败的重试体验仅为单元/mock 结论。
- 旧客户端若仍调用旧器械路由会收到本地化停用错误（预期行为）。
- 8F 关系训练前端入口已移除但底层实现保留（未再实机验证其入口可达性）；历史档案与惰性记录保留。
- 全仓测试、构建、打包与实机验收均未执行；本分支未合并、未部署。

## 10. 交付清单

- 分支：`codex/training-three-modules`（基线 `f58bf0a`），提交链见第 1 节；最终 HEAD 以分支最新提交为准。
- PR：#3 `https://github.com/jobxfreak666-cell/football-manager-ODD/pull/3`（目标 `football-manager-odd-dev`，未合并）。
- 建议审核顺序：资金一致性/事务与幂等 → 迁移幂等 → 作用域与单人占用 → 原生保护与取消竞态 → UI/文案。
- 本报告与收尾清理同属最后一个 docs/i18n 提交；PR 由 Lead 创建后以上述提交为 head。
