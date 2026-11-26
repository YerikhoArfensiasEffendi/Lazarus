#!/usr/bin/env python3
"""Unit tests for Republik Konoha Autopilot."""

from __future__ import annotations

import datetime as dt
import unittest

import autopilot as ap


SAMPLE_WORLD_CONFIG = {
    "economy": {
        "inauguratedUpto": 5535,
        "workCooldownMinutes": 120,
        "income": {"maxAccrualHours": 24},
        "land": {"minPrice": 50, "basePrice": 200, "maxPlotsPerCitizen": 5},
        "requireVerified": {"buyLand": True, "build": True, "donate": True},
    },
    "tiers": [
        {
            "id": "street",
            "work": {"label": "Narik Orderan", "reward": 18},
            "perks": {"incomeBonusPct": 0, "landDiscountPct": 0, "canBuildGovernment": False},
        },
        {
            "id": "elite",
            "work": {"label": "Cairin Dividen", "reward": 45},
            "perks": {"incomeBonusPct": 10, "landDiscountPct": 20, "canBuildGovernment": False},
        },
    ],
    "buildings": [
        {
            "id": "gerobak_kopi",
            "name": "Gerobak Kopi / Angkringan",
            "emoji": "☕",
            "baseCost": 80,
            "incomePerLevelPerDay": 10,
            "upgradeMultiplier": 1.6,
            "maxLevel": 5,
        },
        {
            "id": "kafe_scbd",
            "name": "Kafe SCBD",
            "emoji": "🧋",
            "baseCost": 800,
            "incomePerLevelPerDay": 75,
            "upgradeMultiplier": 1.6,
            "maxLevel": 5,
        },
        {
            "id": "gedung_kantor",
            "name": "Gedung Pencakar Langit / Kantor PT",
            "emoji": "🏢",
            "baseCost": 1800,
            "incomePerLevelPerDay": 160,
            "upgradeMultiplier": 1.6,
            "maxLevel": 5,
        },
        {
            "id": "mansion_helipad",
            "name": "Mansion Helipad",
            "emoji": "🚁",
            "baseCost": 2000,
            "incomePerLevelPerDay": 140,
            "upgradeMultiplier": 1.6,
            "maxLevel": 5,
        },
        {
            "id": "kantor_kementerian",
            "name": "Kantor Kementerian Cabang",
            "emoji": "🏤",
            "baseCost": 900,
            "incomePerLevelPerDay": 80,
            "upgradeMultiplier": 1.6,
            "maxLevel": 5,
            "requiresPerk": "canBuildGovernment",
        },
    ],
}


class FakeKonohaClient:
    """In-memory mock of KonohaClient for end-to-end autopilot verification."""

    def __init__(self, citizen: dict, owned_props: set[str], plots: list[dict], free_plots: list[dict]) -> None:
        self.citizen = dict(citizen)
        self.owned_props = set(owned_props)
        self.plots = [dict(p) for p in plots]
        self.free_plots = [dict(p) for p in free_plots]
        self.calls: list[tuple[str, object]] = []
        self.fail_first_plot_buy = False

    def recover_session(self, ktp_code: str, pin: str) -> tuple[str, str]:
        self.calls.append(("recover_session", (ktp_code, pin)))
        return self.citizen["id"], "super-secret-token-xyz"

    def get_my_citizen(self, citizen_id: str, token: str) -> dict:
        return dict(self.citizen)

    def get_world_state(self) -> dict:
        return {
            "world_id": "republik-konoha",
            "current_ring_unlocked": 6,
            "active_project_id": "mrt_konoha",
            "active_project_completed": False,
            "config": SAMPLE_WORLD_CONFIG,
        }

    def get_property_catalog(self) -> list[dict]:
        return list(ap.FALLBACK_PROPERTY_CATALOG)

    def get_my_property_ids(self, citizen_id: str) -> set[str]:
        return set(self.owned_props)

    def get_my_plots(self, citizen_id: str) -> list[dict]:
        return [dict(p) for p in self.plots]

    def get_cheapest_free_plots(self, max_ring: int, limit: int = 8) -> list[dict]:
        return [dict(p) for p in self.free_plots[:limit]]

    def claim_daily_salary(self, citizen_id: str, token: str) -> dict:
        self.calls.append(("claim_daily_salary", None))
        prop_bonus = sum(p["daily_bonus"] for p in ap.FALLBACK_PROPERTY_CATALOG if p["id"] in self.owned_props)
        reward = 50 + prop_bonus
        self.citizen["coins"] += reward
        self.citizen["last_salary_at"] = "2026-11-26T06:00:00+00:00"
        return {"reward": reward, "citizen": dict(self.citizen)}

    def do_quick_work(self, citizen_id: str, token: str) -> dict:
        self.calls.append(("do_quick_work", None))
        self.citizen["coins"] += 25
        self.citizen["quick_work_date"] = "2026-11-26"
        self.citizen["quick_work_count"] = int(self.citizen.get("quick_work_count") or 0) + 1
        self.citizen["quick_work_at"] = "2026-11-26T06:00:00+00:00"
        rem = max(0, 3 - self.citizen["quick_work_count"])
        return {"reward": 25, "remaining": rem, "citizen": dict(self.citizen)}

    def claim_work_reward(self, citizen_id: str, token: str) -> dict:
        self.calls.append(("claim_work_reward", None))
        self.citizen["coins"] += 18
        self.citizen["last_work_at"] = "2026-11-26T06:00:00+00:00"
        return {"reward": 18, "coins": self.citizen["coins"], "last_work_at": self.citizen["last_work_at"]}

    def claim_property_income(self, citizen_id: str, token: str, plot_code: str | None = None) -> dict:
        self.calls.append(("claim_property_income", plot_code))
        self.citizen["coins"] += 40
        for p in self.plots:
            if plot_code is None or p["plot_code"] == plot_code:
                p["last_income_claim_at"] = "2026-11-26T06:00:00+00:00"
        return {"total": 40, "coins": self.citizen["coins"]}

    def claim_mission(self, citizen_id: str, token: str, mission_key: str) -> dict:
        self.calls.append(("claim_mission", mission_key))
        rewards = {"first_salary": 30, "first_chat": 30, "first_emote": 20, "first_donation": 40}
        reward = rewards[mission_key]
        self.citizen["coins"] += reward
        cm = dict(self.citizen.get("claimed_missions") or {})
        cm[mission_key] = "2026-11-26T06:00:00+00:00"
        self.citizen["claimed_missions"] = cm
        return {"reward": reward, "citizen": dict(self.citizen)}

    def donate_to_project(self, citizen_id: str, token: str, amount: int) -> dict:
        self.calls.append(("donate_to_project", amount))
        self.citizen["coins"] -= amount
        self.citizen["total_donated"] = int(self.citizen.get("total_donated") or 0) + amount
        return {"coins": self.citizen["coins"]}

    def send_global_chat(self, citizen_id: str, token: str, message: str) -> dict:
        self.calls.append(("send_global_chat", message))
        self.citizen["last_chat_at"] = "2026-11-26T06:00:00+00:00"
        return {"ok": True}

    def buy_property(self, citizen_id: str, token: str, property_type: str) -> dict:
        self.calls.append(("buy_property", property_type))
        item = next(p for p in ap.FALLBACK_PROPERTY_CATALOG if p["id"] == property_type)
        self.citizen["coins"] -= item["price"]
        self.owned_props.add(property_type)
        return {"citizen": dict(self.citizen)}

    def buy_land_plot(self, citizen_id: str, token: str, plot_code: str) -> dict:
        self.calls.append(("buy_land_plot", plot_code))
        if self.fail_first_plot_buy:
            self.fail_first_plot_buy = False
            raise ap.GameAPIError(f"Kavling {plot_code} sudah dimiliki Warga Lain.")
        plot = next(p for p in self.free_plots if p["plot_code"] == plot_code)
        self.free_plots = [p for p in self.free_plots if p["plot_code"] != plot_code]
        self.citizen["coins"] -= plot["price"]
        owned = {**plot, "building_type": None, "building_level": 0, "last_income_claim_at": None}
        self.plots.append(owned)
        return {"plot": dict(owned), "coins": self.citizen["coins"]}

    def build_or_upgrade_property(
        self,
        citizen_id: str,
        token: str,
        plot_code: str,
        building_type: str | None = None,
        building_name: str | None = None,
    ) -> dict:
        self.calls.append(("build_or_upgrade_property", (plot_code, building_type)))
        plot = next(p for p in self.plots if p["plot_code"] == plot_code)
        b_id = building_type or plot["building_type"]
        b = next(x for x in SAMPLE_WORLD_CONFIG["buildings"] if x["id"] == b_id)
        cost = ap.building_upgrade_cost(b, plot["building_level"])
        self.citizen["coins"] -= cost
        plot["building_type"] = b_id
        plot["building_level"] += 1
        plot["last_income_claim_at"] = "2026-11-26T06:00:00+00:00"
        return {"plot": dict(plot), "coins": self.citizen["coins"], "cost": cost}


class AutopilotTests(unittest.TestCase):
    def test_wib_date_midnight_boundary(self) -> None:
        self.assertEqual(ap.wib_date_str(dt.datetime(2026, 11, 26, 16, 59, tzinfo=dt.timezone.utc)), "2026-11-26")
        self.assertEqual(ap.wib_date_str(dt.datetime(2026, 11, 26, 17, 0, tzinfo=dt.timezone.utc)), "2026-11-27")

    def test_is_citizen_verified(self) -> None:
        econ = SAMPLE_WORLD_CONFIG["economy"]
        self.assertTrue(ap.is_citizen_verified({"follow_status": "verified", "citizen_number": 9999}, econ, "republik-konoha"))
        self.assertTrue(ap.is_citizen_verified({"follow_status": "pending", "citizen_number": 543}, econ, "republik-konoha"))
        self.assertFalse(ap.is_citizen_verified({"follow_status": "pending", "citizen_number": 6000}, econ, "republik-konoha"))
        self.assertFalse(ap.is_citizen_verified({"follow_status": "impeached", "citizen_number": 5}, econ, "republik-konoha"))

    def test_building_cost_and_plot_income_formulas(self) -> None:
        gedung = next(b for b in SAMPLE_WORLD_CONFIG["buildings"] if b["id"] == "gedung_kantor")
        self.assertEqual(ap.building_upgrade_cost(gedung, 0), 1800)
        self.assertEqual(ap.building_upgrade_cost(gedung, 1), 2880)
        self.assertEqual(ap.building_upgrade_cost(gedung, 2), 4608)

        now = dt.datetime(2026, 11, 26, 12, 0, tzinfo=dt.timezone.utc)
        # 6 hours at 160/day = 40.0 exact; 30 hours capped at 24h = 160.
        raw6, fl6, hrs6 = ap.raw_plot_income(gedung, 1, "2026-11-26T06:00:00+00:00", 0, 24, now)
        self.assertAlmostEqual(raw6, 40.0)
        self.assertEqual(fl6, 40)
        self.assertAlmostEqual(hrs6, 6.0)

        raw30, fl30, hrs30 = ap.raw_plot_income(gedung, 1, "2026-11-25T06:00:00+00:00", 0, 24, now)
        self.assertAlmostEqual(raw30, 160.0)
        self.assertEqual(fl30, 160)
        self.assertAlmostEqual(hrs30, 30.0)

    def test_smart_plot_harvest_avoids_truncation_waste_and_prevents_cap(self) -> None:
        b_map = {b["id"]: b for b in SAMPLE_WORLD_CONFIG["buildings"]}
        now = dt.datetime(2026, 11, 26, 12, 0, tzinfo=dt.timezone.utc)
        # gerobak_kopi = 10/day -> after 3h = 1.25 (waste 0.25 > 0.08 -> SKIP!)
        plot_wasteful = {
            "plot_code": "R6-B001",
            "building_type": "gerobak_kopi",
            "building_level": 1,
            "last_income_claim_at": "2026-11-26T09:00:00+00:00",
        }
        chosen, total = ap.decide_plot_harvest([plot_wasteful], b_map, 0, 24, now, 4.0, 0.08, force_all=False)
        self.assertEqual(chosen, [])
        self.assertEqual(total, 1)

        # After 21h -> near 24h cap (>= 20h) -> MUST claim regardless of fraction!
        plot_near_cap = {**plot_wasteful, "last_income_claim_at": "2026-11-25T15:00:00+00:00"}
        chosen_cap, _ = ap.decide_plot_harvest([plot_near_cap], b_map, 0, 24, now, 4.0, 0.08, force_all=False)
        self.assertEqual(len(chosen_cap), 1)
        self.assertTrue(chosen_cap[0][2].startswith("near_cap_"))

    def test_optimizer_ranks_exact_optimal_sequence_and_reserves_plots_for_gedung_kantor(self) -> None:
        citizen = {"tier_id": "street", "follow_status": "verified", "citizen_number": 543, "coins": 73}
        ranked = ap.plan_investments(
            citizen=citizen,
            world_config=SAMPLE_WORLD_CONFIG,
            catalog=ap.FALLBACK_PROPERTY_CATALOG,
            owned_property_ids={"warung_madura"},
            my_plots=[],
            cheapest_free_plot={"plot_code": "R6-B008", "ring_level": 6, "price": 50},
            daily_income_rate=335.0,
            horizon_days=90.0,
            world_id="republik-konoha",
        )
        # Must rank rumah_kavling #1, NOT gerobak_lapak (6.25% ROI) or gerobak_kopi (wastes finite plot slot)!
        self.assertEqual(ranked[0].property_type, "rumah_kavling")
        self.assertEqual(ranked[1].property_type, "ruko_distrik")
        self.assertEqual(ranked[2].property_type, "mansion_konglo")
        plot_cands = [c for c in ranked if c.kind == "buy_plot_and_build"]
        self.assertEqual(len(plot_cands), 1)
        self.assertEqual(plot_cands[0].building_type, "gedung_kantor")
        self.assertEqual(plot_cands[0].cost, 1850)

    def test_end_to_end_claims_missions_atomic_plot_retry_and_pii_redaction(self) -> None:
        now = dt.datetime(2026, 11, 26, 6, 0, tzinfo=dt.timezone.utc)
        citizen = {
            "id": "secret-uuid-9999",
            "ktp_code": "RK-9999",
            "username": "TopSecretUser",
            "ig_username": "secret_ig_handle",
            "tier_id": "street",
            "follow_status": "verified",
            "citizen_number": 543,
            "coins": 1800,
            "total_donated": 0,
            "last_salary_at": None,
            "last_work_at": None,
            "quick_work_at": None,
            "quick_work_date": None,
            "quick_work_count": 0,
            "last_chat_at": None,
            "claimed_missions": {},
        }
        # Own all catalog properties except gerobak_lapak so buy_plot_and_build (gedung_kantor, 1850) beats gerobak_lapak!
        owned = {"warung_madura", "rumah_kavling", "ruko_distrik", "mansion_konglo"}
        free = [
            {"plot_code": "R6-B001", "ring_level": 6, "price": 50},
            {"plot_code": "R6-B002", "ring_level": 6, "price": 50},
        ]
        fake = FakeKonohaClient(citizen, owned, [], free)
        fake.fail_first_plot_buy = True  # Simulates race condition on R6-B001!

        cfg = ap.AutopilotConfig(ktp_code="RK-9999", pin="123456", max_wait_seconds=0)
        summary = ap.run_autopilot(cfg, client=fake, now_fn=lambda: now, sleep_fn=lambda _: None)

        call_names = [c[0] for c in fake.calls]
        self.assertIn("claim_daily_salary", call_names)
        self.assertIn("do_quick_work", call_names)
        self.assertIn("claim_work_reward", call_names)
        self.assertIn("donate_to_project", call_names)
        self.assertIn("send_global_chat", call_names)
        # All 4 missions claimed!
        self.assertEqual(summary["missions_claimed"], 4)
        # Plot race condition retried R6-B001 -> R6-B002 and built gedung_kantor L1!
        self.assertEqual(summary["owned_plots_count"], 1)
        self.assertEqual(fake.plots[0]["plot_code"], "R6-B002")
        self.assertEqual(fake.plots[0]["building_type"], "gedung_kantor")
        self.assertEqual(fake.plots[0]["building_level"], 1)

        # Verify strict PII & secret redaction in rendered public report!
        report = ap.render_markdown_report(summary)
        for sensitive in ["RK-9999", "123456", "super-secret-token-xyz", "secret-uuid-9999", "TopSecretUser", "secret_ig_handle", "R6-B002"]:
            self.assertNotIn(sensitive, report)

    def test_env_bool_handles_empty_and_explicit_values(self) -> None:
        import os
        os.environ["RK_TEST_FLAG"] = ""
        self.assertTrue(ap._env_bool("RK_TEST_FLAG", True))
        self.assertFalse(ap._env_bool("RK_TEST_FLAG", False))
        os.environ["RK_TEST_FLAG"] = "false"
        self.assertFalse(ap._env_bool("RK_TEST_FLAG", True))
        os.environ["RK_TEST_FLAG"] = "true"
        self.assertTrue(ap._env_bool("RK_TEST_FLAG", False))
        del os.environ["RK_TEST_FLAG"]


if __name__ == "__main__":
    unittest.main()
