from pathlib import Path
import unittest


ROOT = (Path(__file__).resolve().parents[1] / "src")


class ExistingPageHierarchyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.index = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
        cls.script = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        cls.styles = (ROOT / "web" / "app.css").read_text(encoding="utf-8")

    def test_training_page_is_grouped_under_team_facilities(self):
        facilities = self.index.split('id="facilities-subnav"', 1)[1].split("</div>", 1)[0]
        self.assertIn('data-page="training"', facilities)
        self.assertIn('id="page-training"', self.index)

    def test_world_pages_are_grouped_under_world_navigation(self):
        world = self.index.split('id="world-subnav"', 1)[1].split("</div>", 1)[0]
        self.assertIn('id="world-toggle"', self.index)
        self.assertIn('<span>世界</span>', self.index)
        self.assertIn('data-page="world-clubs"', world)
        self.assertIn('<span>世界俱乐部</span>', world)
        self.assertIn('data-page="world-nations"', world)
        self.assertIn('<span>世界国家</span>', world)
        self.assertIn('<h1 id="world-clubs-page-title">世界俱乐部</h1>', self.index)
        self.assertIn('<h1 id="world-players-page-title">世界球员</h1>', self.index)
        self.assertIn('<h1 id="world-nations-page-title">世界国家</h1>', self.index)
        self.assertIn(
            'const worldPage = ["world-clubs", "world-players", "world-nations"].includes(page)',
            self.script,
        )
        self.assertIn('$("#world-toggle").addEventListener("click"', self.script)

    def test_training_uses_public_bank_balance(self):
        self.assertIn("economy?.bank_balance", self.script)
        self.assertNotIn("economy?.general_balance", self.script)


    def test_result_actions_are_text_only_and_outdoor_maps_are_retired(self):
        self.assertIn(
            '<button class="results-button" id="results-button"><span>赛果</span></button>',
            self.index,
        )
        self.assertIn(
            '<button class="results-button" id="manual-refund-button"><span>手动退款</span></button>',
            self.index,
        )
        self.assertNotIn("data-training-scene=", self.index)
        self.assertNotIn("data-training-scene", self.script)



    def test_training_page_uses_module_workspace_without_legacy_equipment(self):
        self.assertIn('id="page-training"', self.index)
        self.assertIn('id="training-module-tabs"', self.index)
        self.assertIn('id="training-roster"', self.index)
        self.assertNotIn('id="training-dock-tabs"', self.index)
        self.assertNotIn("data-training-scene=", self.index)
        self.assertNotIn("器材仓库", self.index)
        self.assertIn("function renderTrainingRoster()", self.script)
        self.assertIn("function renderTrainingPersonDetail()", self.script)
        self.assertIn("function setTrainingModule(module)", self.script)


    def test_car_lottery_page_is_removed(self):
        self.assertNotIn('data-page="lottery"', self.index)
        self.assertNotIn('id="page-lottery"', self.index)
        self.assertNotIn("renderLottery", self.script)
        self.assertNotIn(".lottery-", self.styles)
        self.assertFalse((ROOT / "web" / "assets" / "lottery").exists())

    def test_item_and_player_operations_do_not_open_blocking_progress_ui(self):
        self.assertNotIn('id="operation-progress-dialog"', self.index)
        self.assertNotIn('id="attribute-busy-overlay"', self.index)
        self.assertNotIn("operation-progress-dialog", self.styles)
        self.assertNotIn("attribute-busy-overlay", self.styles)
        self.assertNotIn("正在确认当前存档", self.script)
        self.assertIn("if (app.operationBusy)", self.script)
        self.assertIn("app.operationBusy = false;", self.script)

    def test_state_training_and_inventory_requests_have_recovery_timeouts(self):
        request = self.script.split("async function request", 1)[1].split(
            "function localizeServerError", 1,
        )[0]
        self.assertIn('path === "/api/state"', self.script)
        self.assertIn('path === "/api/training/run"', self.script)
        self.assertIn('path.startsWith("/api/inventory/")', self.script)
        self.assertNotIn('/api/world-clubs/finance-transfer', request)
        self.assertIn("payload = await response.json();", self.script)
        self.assertIn("结果可能已在后台生效，请先刷新确认，不要连续重复提交", self.script)


if __name__ == "__main__":
    unittest.main()
