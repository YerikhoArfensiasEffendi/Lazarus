#!/usr/bin/env python3
"""Republik Konoha Autopilot — Scheduled auto-claim, mission completion & ROI-optimal upgrade engine.

Pure Python standard library (zero external dependencies) for fast, reliable GitHub Actions execution.
Never prints credentials, session tokens, citizen IDs, usernames, or KTP codes.
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import json
import math
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

DEFAULT_SUPABASE_URL = "https://axgljtpjmcnzmwftheaq.supabase.co"
DEFAULT_SUPABASE_ANON_KEY = "sb_publishable_YRAQTiosnVp5QN2tthLgaQ_YKNduUZ9"
DEFAULT_WORLD_ID = "republik-konoha"

# Core economy constants matching the live Republik Konoha frontend bundle.
SALARY_BASE_REWARD = 50
SALARY_COOLDOWN_SECONDS = 24 * 3600
QUICK_WORK_REWARD = 25
QUICK_WORK_COOLDOWN_SECONDS = 2 * 3600
QUICK_WORK_DAILY_LIMIT = 3
FIRST_DONATION_MIN_COINS = 10
WIB_TZ = dt.timezone(dt.timedelta(hours=7))

FALLBACK_PROPERTY_CATALOG = [
    {"id": "gerobak_lapak", "name": "Gerobak / Lapak RT", "emoji": "🛒", "price": 80, "daily_bonus": 5, "sort": 1},
    {"id": "warung_madura", "name": "Warung Madura Mini", "emoji": "🏪", "price": 150, "daily_bonus": 12, "sort": 2},
    {"id": "rumah_kavling", "name": "Rumah Kavling RT", "emoji": "🏠", "price": 350, "daily_bonus": 30, "sort": 3},
    {"id": "ruko_distrik", "name": "Ruko Distrik Kota", "emoji": "🏬", "price": 800, "daily_bonus": 75, "sort": 4},
    {"id": "mansion_konglo", "name": "Mansion Konglomerat", "emoji": "🏰", "price": 2000, "daily_bonus": 200, "sort": 5},
]


class GameAPIError(RuntimeError):
    """Raised when the game backend rejects an RPC or table request."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclasses.dataclass(frozen=True)
class AutopilotConfig:
    ktp_code: str
    pin: str
    supabase_url: str = DEFAULT_SUPABASE_URL
    supabase_anon_key: str = DEFAULT_SUPABASE_ANON_KEY
    world_id: str = DEFAULT_WORLD_ID
    dry_run: bool = False
    auto_upgrade: bool = True
    auto_mission_chat: bool = True
    max_wait_seconds: int = 180
    horizon_days: float = 90.0
    min_coin_reserve: int = 0
    expected_tier_work_runs_per_day: float = 11.0
    max_investments_per_run: int = 5
    # Claim plot income early if fractional rounding loss is tiny, or before 24h cap.
    plot_claim_cap_buffer_hours: float = 4.0
    plot_claim_max_frac_waste: float = 0.08


@dataclasses.dataclass(frozen=True)
class InvestmentCandidate:
    kind: str  # "catalog_property" | "upgrade_plot" | "build_empty_plot" | "buy_plot_and_build"
    key: str
    label: str
    cost: int
    delta_daily_income: float
    payback_days: float
    effective_payback_days: float
    plot_code: str | None = None
    building_type: str | None = None
    property_type: str | None = None


def parse_iso_utc(raw: str | None) -> dt.datetime | None:
    if not raw:
        return None
    normalized = raw.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    parsed = dt.datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def wib_date_str(now_utc: dt.datetime) -> str:
    return now_utc.astimezone(WIB_TZ).strftime("%Y-%m-%d")


def salary_rank_bonus(citizen_number: int) -> int:
    if citizen_number <= 2:
        return 40
    if citizen_number <= 30:
        return 25
    if citizen_number <= 100:
        return 15
    return 0


def is_citizen_verified(citizen: dict[str, Any], economy: dict[str, Any], world_id: str) -> bool:
    follow_status = citizen.get("follow_status")
    if follow_status == "impeached":
        return False
    if follow_status == "verified":
        return True
    if world_id == "republik-konoha":
        upto = int(economy.get("inauguratedUpto") or 0)
        num = int(citizen.get("citizen_number") or 0)
        return 1 <= num <= upto
    return False


def find_tier(world_config: dict[str, Any], tier_id: str | None) -> dict[str, Any]:
    impeached = world_config.get("impeachedTier") or {}
    if tier_id == impeached.get("id"):
        return impeached
    tiers = world_config.get("tiers") or []
    for tier in tiers:
        if tier.get("id") == tier_id:
            return tier
    return tiers[-1] if tiers else {"id": tier_id or "civil", "work": {"reward": 12}, "perks": {}}


def building_upgrade_cost(building: dict[str, Any], current_level: int) -> int:
    base_cost = float(building["baseCost"])
    mult = float(building.get("upgradeMultiplier", 1.6))
    return int(round(base_cost * (mult**current_level)))


def raw_plot_income(
    building: dict[str, Any],
    level: int,
    last_claim_at: str | None,
    income_bonus_pct: float,
    max_accrual_hours: float,
    now_utc: dt.datetime,
) -> tuple[float, int, float]:
    """Return (raw_coins, floored_coins, elapsed_hours) matching frontend Jo()."""
    if level <= 0 or not last_claim_at:
        return 0.0, 0, 0.0
    last_dt = parse_iso_utc(last_claim_at)
    if last_dt is None:
        return 0.0, 0, 0.0
    elapsed_hours = max(0.0, (now_utc - last_dt).total_seconds() / 3600.0)
    capped_hours = min(max_accrual_hours, elapsed_hours)
    rate_per_day = float(building["incomePerLevelPerDay"]) * level * (1.0 + income_bonus_pct / 100.0)
    raw = rate_per_day * capped_hours / 24.0
    return raw, math.floor(raw), elapsed_hours


def select_slot_optimal_building(
    buildings: list[dict[str, Any]],
    can_build_government: bool,
) -> dict[str, Any] | None:
    """Pick the best building for scarce irreversible land slots (max L5 ceiling, tie-broken by L1 ROI)."""
    eligible = []
    for b in buildings:
        req = b.get("requiresPerk")
        if req == "canBuildGovernment" and not can_build_government:
            continue
        if req and req != "canBuildGovernment":
            continue
        eligible.append(b)
    if not eligible:
        return None
    return max(
        eligible,
        key=lambda b: (
            float(b["incomePerLevelPerDay"]) * int(b.get("maxLevel", 5)),
            float(b["incomePerLevelPerDay"]) / max(1.0, float(b["baseCost"])),
        ),
    )


def estimate_daily_income(
    citizen: dict[str, Any],
    tier: dict[str, Any],
    catalog: list[dict[str, Any]],
    owned_property_ids: set[str],
    my_plots: list[dict[str, Any]],
    buildings_by_id: dict[str, dict[str, Any]],
    expected_tier_work_runs_per_day: float,
) -> dict[str, float]:
    prop_bonus = sum(float(p["daily_bonus"]) for p in catalog if p["id"] in owned_property_ids)
    rank_bonus = float(salary_rank_bonus(int(citizen.get("citizen_number") or 0)))
    daily_salary = float(SALARY_BASE_REWARD) + rank_bonus + prop_bonus
    quick_work = float(QUICK_WORK_REWARD * QUICK_WORK_DAILY_LIMIT)
    tier_work_reward = float((tier.get("work") or {}).get("reward") or 12)
    tier_work = tier_work_reward * expected_tier_work_runs_per_day

    income_bonus_pct = float((tier.get("perks") or {}).get("incomeBonusPct") or 0)
    plot_income = 0.0
    for plot in my_plots:
        lvl = int(plot.get("building_level") or 0)
        b_id = plot.get("building_type")
        if lvl > 0 and b_id in buildings_by_id:
            b = buildings_by_id[b_id]
            plot_income += float(b["incomePerLevelPerDay"]) * lvl * (1.0 + income_bonus_pct / 100.0)

    total = daily_salary + quick_work + tier_work + plot_income
    return {
        "daily_salary": daily_salary,
        "quick_work": quick_work,
        "tier_work": tier_work,
        "plot_income": plot_income,
        "total": total,
    }


def plan_investments(
    citizen: dict[str, Any],
    world_config: dict[str, Any],
    catalog: list[dict[str, Any]],
    owned_property_ids: set[str],
    my_plots: list[dict[str, Any]],
    cheapest_free_plot: dict[str, Any] | None,
    daily_income_rate: float,
    horizon_days: float,
    world_id: str,
) -> list[InvestmentCandidate]:
    """Rank all legal investments via the exact incremental-game payback + wait-time theorem.

    Metric: effective_payback_days = (cost / delta_daily_income) + (cost / daily_income_rate).
    Lower is strictly better (pairwise-optimal ordering under continuous reinvestment).
    """
    economy = world_config.get("economy") or {}
    req_verified = economy.get("requireVerified") or {}
    verified = is_citizen_verified(citizen, economy, world_id)
    tier = find_tier(world_config, citizen.get("tier_id"))
    perks = tier.get("perks") or {}
    income_bonus_pct = float(perks.get("incomeBonusPct") or 0)
    land_discount_pct = float(perks.get("landDiscountPct") or 0)
    can_build_gov = bool(perks.get("canBuildGovernment"))

    buildings = world_config.get("buildings") or []
    buildings_by_id = {b["id"]: b for b in buildings}
    slot_best_building = select_slot_optimal_building(buildings, can_build_gov)

    max_plots = int((economy.get("land") or {}).get("maxPlotsPerCitizen") or 5)
    safe_rate = max(1.0, daily_income_rate)
    candidates: list[InvestmentCandidate] = []

    def add_candidate(
        kind: str,
        key: str,
        label: str,
        cost: int,
        delta_r: float,
        plot_code: str | None = None,
        building_type: str | None = None,
        property_type: str | None = None,
    ) -> None:
        if cost <= 0 or delta_r <= 0:
            return
        payback = cost / delta_r
        if payback > horizon_days:
            return
        eff = payback + (cost / safe_rate)
        candidates.append(
            InvestmentCandidate(
                kind=kind,
                key=key,
                label=label,
                cost=cost,
                delta_daily_income=delta_r,
                payback_days=payback,
                effective_payback_days=eff,
                plot_code=plot_code,
                building_type=building_type,
                property_type=property_type,
            )
        )

    can_buy_land = verified or not bool(req_verified.get("buyLand", True))
    can_build = verified or not bool(req_verified.get("build", True))

    # 1. Catalog properties (permanent daily salary bonus, 0 plot slots consumed).
    if can_buy_land:
        for prop in catalog:
            pid = prop["id"]
            if pid in owned_property_ids:
                continue
            add_candidate(
                kind="catalog_property",
                key=f"prop:{pid}",
                label=f"{prop.get('emoji', '🏪')} {prop['name']} (Properti Katalog)",
                cost=int(prop["price"]),
                delta_r=float(prop["daily_bonus"]),
                property_type=pid,
            )

    # 2. Existing owned plots: upgrade existing buildings or build on empty plots.
    if can_build:
        for plot in my_plots:
            lvl = int(plot.get("building_level") or 0)
            pcode = plot["plot_code"]
            if lvl == 0:
                if slot_best_building:
                    delta_r = float(slot_best_building["incomePerLevelPerDay"]) * (1.0 + income_bonus_pct / 100.0)
                    ring_tag = pcode.split("-")[0]
                    add_candidate(
                        kind="build_empty_plot",
                        key=f"build:{pcode}:{slot_best_building['id']}",
                        label=f"{slot_best_building.get('emoji', '🏢')} Bangun {slot_best_building['name']} L1 ({ring_tag})",
                        cost=building_upgrade_cost(slot_best_building, 0),
                        delta_r=delta_r,
                        plot_code=pcode,
                        building_type=slot_best_building["id"],
                    )
            else:
                b = buildings_by_id.get(plot.get("building_type") or "")
                if b and lvl < int(b.get("maxLevel", 5)):
                    delta_r = float(b["incomePerLevelPerDay"]) * (1.0 + income_bonus_pct / 100.0)
                    ring_tag = pcode.split("-")[0]
                    add_candidate(
                        kind="upgrade_plot",
                        key=f"up:{pcode}:L{lvl + 1}",
                        label=f"⬆️ Upgrade {b['name']} ({ring_tag}) ke L{lvl + 1}",
                        cost=building_upgrade_cost(b, lvl),
                        delta_r=delta_r,
                        plot_code=pcode,
                        building_type=b["id"],
                    )

    # 3. Atomic Buy Cheapest Unlocked Plot + Build slot-optimal L1 (zero dead capital).
    if can_buy_land and can_build and len(my_plots) < max_plots and cheapest_free_plot and slot_best_building:
        raw_land_price = int(cheapest_free_plot["price"])
        land_price = math.floor(raw_land_price * (100.0 - land_discount_pct) / 100.0)
        build_cost = building_upgrade_cost(slot_best_building, 0)
        delta_r = float(slot_best_building["incomePerLevelPerDay"]) * (1.0 + income_bonus_pct / 100.0)
        add_candidate(
            kind="buy_plot_and_build",
            key=f"plot_build:{slot_best_building['id']}",
            label=f"🏗️ Beli Kavling R{cheapest_free_plot['ring_level']} ({land_price}) + {slot_best_building['name']} L1",
            cost=land_price + build_cost,
            delta_r=delta_r,
            plot_code=cheapest_free_plot["plot_code"],
            building_type=slot_best_building["id"],
        )

    candidates.sort(key=lambda c: (c.effective_payback_days, c.cost, c.key))
    return candidates


class KonohaClient:
    """Minimal stdlib Supabase PostgREST/RPC client for Republik Konoha."""

    def __init__(self, supabase_url: str, anon_key: str, world_id: str, timeout: int = 20) -> None:
        self.base_url = supabase_url.rstrip("/")
        self.anon_key = anon_key
        self.world_id = world_id
        self.timeout = timeout

    def _headers(self, content_type: str | None = None) -> dict[str, str]:
        hdrs = {
            "apikey": self.anon_key,
            "Authorization": f"Bearer {self.anon_key}",
            "Accept": "application/json",
            "User-Agent": "LazarusKonohaAutopilot/1.0",
        }
        if content_type:
            hdrs["Content-Type"] = content_type
        return hdrs

    def _request_json(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        retry_transient: bool = True,
    ) -> Any:
        url = f"{self.base_url}{path}"
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        attempts = 3 if retry_transient else 1

        for attempt in range(1, attempts + 1):
            req = urllib.request.Request(
                url,
                data=data,
                headers=self._headers("application/json" if data is not None else None),
                method=method,
            )
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    raw = resp.read().decode("utf-8")
                    body = json.loads(raw) if raw else None
                    if isinstance(body, dict) and body.get("ok") is False:
                        raise GameAPIError(str(body.get("error") or "Ditolak server."), resp.status)
                    return body
            except urllib.error.HTTPError as exc:
                err_body = exc.read().decode("utf-8", errors="replace")
                msg = err_body
                try:
                    parsed = json.loads(err_body)
                    if isinstance(parsed, dict):
                        msg = str(parsed.get("message") or parsed.get("error") or err_body)
                except json.JSONDecodeError:
                    pass
                # Retry only on 5xx transient gateway/database failures.
                if exc.code >= 500 and attempt < attempts:
                    time.sleep(2 * attempt)
                    continue
                raise GameAPIError(msg, exc.code) from exc
            except (urllib.error.URLError, TimeoutError) as exc:
                if attempt < attempts:
                    time.sleep(2 * attempt)
                    continue
                raise GameAPIError(f"Network error: {exc}") from exc

        raise GameAPIError("Request failed after retries.")

    def rpc(self, name: str, payload: dict[str, Any], retry_transient: bool = True) -> Any:
        return self._request_json("POST", f"/rest/v1/rpc/{name}", payload, retry_transient=retry_transient)

    def get_table(self, table: str, params: dict[str, str]) -> list[dict[str, Any]]:
        query = urllib.parse.urlencode(params, safe=".,()*")
        res = self._request_json("GET", f"/rest/v1/{table}?{query}")
        return res if isinstance(res, list) else []

    def recover_session(self, ktp_code: str, pin: str) -> tuple[str, str]:
        # Never retry auth calls automatically to protect against the 5-strike 1h PIN lock.
        data = self.rpc(
            "recover_session",
            {"p_world_id": self.world_id, "p_ktp_code": ktp_code.strip(), "p_pin": pin.strip()},
            retry_transient=False,
        )
        return str(data["citizen_id"]), str(data["secret_token"])

    def auth_payload(self, citizen_id: str, token: str, **extra: Any) -> dict[str, Any]:
        return {"p_world_id": self.world_id, "p_citizen_id": citizen_id, "p_token": token, **extra}

    def get_my_citizen(self, citizen_id: str, token: str) -> dict[str, Any]:
        return self.rpc("get_my_citizen", self.auth_payload(citizen_id, token))

    def get_world_state(self) -> dict[str, Any]:
        rows = self.get_table("world_states", {"world_id": f"eq.{self.world_id}", "select": "*"})
        if not rows:
            raise GameAPIError(f"World '{self.world_id}' not found.")
        return rows[0]

    def get_property_catalog(self) -> list[dict[str, Any]]:
        try:
            rows = self.get_table(
                "property_types",
                {"world_id": f"eq.{self.world_id}", "select": "id,name,emoji,price,daily_bonus,sort", "order": "sort"},
            )
            return rows or list(FALLBACK_PROPERTY_CATALOG)
        except GameAPIError:
            return list(FALLBACK_PROPERTY_CATALOG)

    def get_my_property_ids(self, citizen_id: str) -> set[str]:
        try:
            rows = self.get_table(
                "citizen_properties",
                {"world_id": f"eq.{self.world_id}", "citizen_id": f"eq.{citizen_id}", "select": "property_type"},
            )
            return {str(r["property_type"]) for r in rows if r.get("property_type")}
        except GameAPIError:
            return set()

    def get_my_plots(self, citizen_id: str) -> list[dict[str, Any]]:
        return self.get_table(
            "land_plots",
            {
                "world_id": f"eq.{self.world_id}",
                "owner_citizen_id": f"eq.{citizen_id}",
                "select": "id,plot_code,ring_level,grid_x,grid_y,price,building_type,building_name,building_level,last_income_claim_at,purchased_at",
                "order": "purchased_at.asc",
            },
        )

    def get_cheapest_free_plots(self, max_ring: int, limit: int = 8) -> list[dict[str, Any]]:
        return self.get_table(
            "land_plots",
            {
                "world_id": f"eq.{self.world_id}",
                "owner_citizen_id": "is.null",
                "ring_level": f"lte.{max_ring}",
                "select": "plot_code,ring_level,grid_x,grid_y,price",
                "order": "price.asc",
                "limit": str(limit),
            },
        )

    def claim_daily_salary(self, citizen_id: str, token: str) -> dict[str, Any]:
        return self.rpc("claim_daily_salary", self.auth_payload(citizen_id, token), retry_transient=False)

    def do_quick_work(self, citizen_id: str, token: str) -> dict[str, Any]:
        return self.rpc("do_quick_work", self.auth_payload(citizen_id, token), retry_transient=False)

    def claim_work_reward(self, citizen_id: str, token: str) -> dict[str, Any]:
        return self.rpc("claim_work_reward", self.auth_payload(citizen_id, token), retry_transient=False)

    def claim_property_income(self, citizen_id: str, token: str, plot_code: str | None = None) -> dict[str, Any]:
        return self.rpc(
            "claim_property_income",
            self.auth_payload(citizen_id, token, p_plot_code=plot_code),
            retry_transient=False,
        )

    def claim_mission(self, citizen_id: str, token: str, mission_key: str) -> dict[str, Any]:
        return self.rpc(
            "claim_mission",
            self.auth_payload(citizen_id, token, p_mission=mission_key),
            retry_transient=False,
        )

    def donate_to_project(self, citizen_id: str, token: str, amount: int) -> dict[str, Any]:
        return self.rpc(
            "donate_to_project",
            self.auth_payload(citizen_id, token, p_amount=amount),
            retry_transient=False,
        )

    def send_global_chat(self, citizen_id: str, token: str, message: str) -> dict[str, Any]:
        return self.rpc(
            "send_global_chat",
            self.auth_payload(citizen_id, token, p_message=message, p_emote_key=None),
            retry_transient=False,
        )

    def buy_property(self, citizen_id: str, token: str, property_type: str) -> dict[str, Any]:
        return self.rpc(
            "buy_property",
            self.auth_payload(citizen_id, token, p_property_type=property_type),
            retry_transient=False,
        )

    def buy_land_plot(self, citizen_id: str, token: str, plot_code: str) -> dict[str, Any]:
        return self.rpc(
            "buy_land_plot",
            self.auth_payload(citizen_id, token, p_plot_code=plot_code),
            retry_transient=False,
        )

    def build_or_upgrade_property(
        self,
        citizen_id: str,
        token: str,
        plot_code: str,
        building_type: str | None = None,
        building_name: str | None = None,
    ) -> dict[str, Any]:
        return self.rpc(
            "build_or_upgrade_property",
            self.auth_payload(
                citizen_id,
                token,
                p_plot_code=plot_code,
                p_building_type=building_type,
                p_building_name=building_name,
            ),
            retry_transient=False,
        )


def format_duration(seconds: float) -> str:
    secs = max(0, int(round(seconds)))
    hours, rem = divmod(secs, 3600)
    minutes, s = divmod(rem, 60)
    if hours > 0:
        return f"{hours}j {minutes}m"
    if minutes > 0:
        return f"{minutes}m {s}d"
    return f"{s}d"


def compute_cooldowns(
    citizen: dict[str, Any],
    economy: dict[str, Any],
    now_utc: dt.datetime,
) -> dict[str, Any]:
    last_salary = parse_iso_utc(citizen.get("last_salary_at"))
    salary_wait = (
        max(0.0, (last_salary + dt.timedelta(seconds=SALARY_COOLDOWN_SECONDS) - now_utc).total_seconds())
        if last_salary
        else 0.0
    )

    today_wib = wib_date_str(now_utc)
    quick_used = int(citizen.get("quick_work_count") or 0) if citizen.get("quick_work_date") == today_wib else 0
    quick_left = max(0, QUICK_WORK_DAILY_LIMIT - quick_used)
    last_quick = parse_iso_utc(citizen.get("quick_work_at"))
    quick_wait = (
        max(0.0, (last_quick + dt.timedelta(seconds=QUICK_WORK_COOLDOWN_SECONDS) - now_utc).total_seconds())
        if last_quick
        else 0.0
    )

    work_cd_secs = float(economy.get("workCooldownMinutes") or 120) * 60.0
    last_work = parse_iso_utc(citizen.get("last_work_at"))
    work_wait = (
        max(0.0, (last_work + dt.timedelta(seconds=work_cd_secs) - now_utc).total_seconds())
        if last_work
        else 0.0
    )

    return {
        "salary_wait": salary_wait,
        "salary_ready": salary_wait <= 0,
        "quick_used": quick_used,
        "quick_left": quick_left,
        "quick_wait": quick_wait,
        "quick_ready": quick_left > 0 and quick_wait <= 0,
        "work_wait": work_wait,
        "work_ready": work_wait <= 0,
    }


def decide_plot_harvest(
    my_plots: list[dict[str, Any]],
    buildings_by_id: dict[str, dict[str, Any]],
    income_bonus_pct: float,
    max_accrual_hours: float,
    now_utc: dt.datetime,
    cap_buffer_hours: float,
    max_frac_waste: float,
    force_all: bool = False,
) -> tuple[list[tuple[str, int, str]], int]:
    """Select plots worth claiming without losing coins to Math.floor truncation."""
    to_claim: list[tuple[str, int, str]] = []
    total_claimable = 0
    for plot in my_plots:
        lvl = int(plot.get("building_level") or 0)
        b_id = plot.get("building_type")
        if lvl <= 0 or b_id not in buildings_by_id:
            continue
        raw, floored, elapsed = raw_plot_income(
            buildings_by_id[b_id],
            lvl,
            plot.get("last_income_claim_at"),
            income_bonus_pct,
            max_accrual_hours,
            now_utc,
        )
        total_claimable += floored
        if floored < 1:
            continue
        frac_waste = raw - floored
        if force_all:
            to_claim.append((plot["plot_code"], floored, "unlock_upgrade"))
        elif elapsed >= max(1.0, max_accrual_hours - cap_buffer_hours):
            to_claim.append((plot["plot_code"], floored, f"near_cap_{elapsed:.1f}h"))
        elif frac_waste <= max_frac_waste:
            to_claim.append((plot["plot_code"], floored, f"low_waste_{frac_waste:.2f}"))
    return to_claim, total_claimable


def run_autopilot(
    config: AutopilotConfig,
    client: KonohaClient | None = None,
    now_fn: Any = None,
    sleep_fn: Any = time.sleep,
) -> dict[str, Any]:
    api = client or KonohaClient(config.supabase_url, config.supabase_anon_key, config.world_id)
    get_now = now_fn or (lambda: dt.datetime.now(dt.timezone.utc))

    actions: list[str] = []
    warnings: list[str] = []
    coins_earned = 0
    coins_spent = 0

    citizen_id, token = api.recover_session(config.ktp_code, config.pin)
    citizen = api.get_my_citizen(citizen_id, token)
    world = api.get_world_state()
    world_config = world.get("config") or {}
    economy = world_config.get("economy") or {}
    catalog = api.get_property_catalog()
    owned_props = api.get_my_property_ids(citizen_id)
    my_plots = api.get_my_plots(citizen_id)

    starting_coins = int(citizen.get("coins") or 0)
    tier = find_tier(world_config, citizen.get("tier_id"))
    perks = tier.get("perks") or {}
    income_bonus_pct = float(perks.get("incomeBonusPct") or 0)
    max_accrual_hours = float((economy.get("income") or {}).get("maxAccrualHours") or 24)
    buildings_by_id = {b["id"]: b for b in (world_config.get("buildings") or [])}

    # --- Step 1: Near-ready wait (handles GitHub Actions cron jitter cleanly) ---
    now = get_now()
    cd = compute_cooldowns(citizen, economy, now)
    if not config.dry_run and config.max_wait_seconds > 0:
        near_waits = []
        if 0 < cd["salary_wait"] <= config.max_wait_seconds:
            near_waits.append(cd["salary_wait"])
        if cd["quick_left"] > 0 and 0 < cd["quick_wait"] <= config.max_wait_seconds:
            near_waits.append(cd["quick_wait"])
        if 0 < cd["work_wait"] <= config.max_wait_seconds:
            near_waits.append(cd["work_wait"])
        if near_waits:
            wait_secs = min(config.max_wait_seconds + 2, math.ceil(max(near_waits)) + 2)
            actions.append(f"⏳ Menunggu {wait_secs}d agar cooldown tepat selesai")
            sleep_fn(wait_secs)
            now = get_now()
            cd = compute_cooldowns(citizen, economy, now)

    # --- Step 2: Scheduled income claims (Gaji Harian, Kerja Cepat, Kerja Jabatan) ---
    if cd["salary_ready"]:
        if config.dry_run:
            actions.append("[DRY-RUN] Akan klaim Gaji Harian (claim_daily_salary)")
        else:
            try:
                res = api.claim_daily_salary(citizen_id, token)
                reward = int(res.get("reward") or 0)
                coins_earned += reward
                if isinstance(res.get("citizen"), dict):
                    citizen = res["citizen"]
                actions.append(f"💰 Gaji Harian diklaim: +{reward} RpK")
            except GameAPIError as exc:
                warnings.append(f"Gaji Harian dilewati: {exc}")

    if cd["quick_ready"]:
        if config.dry_run:
            actions.append(f"[DRY-RUN] Akan jalankan Kerja Cepat (+{QUICK_WORK_REWARD} RpK)")
        else:
            try:
                res = api.do_quick_work(citizen_id, token)
                reward = int(res.get("reward") or 0)
                rem = int(res.get("remaining") or 0)
                coins_earned += reward
                if isinstance(res.get("citizen"), dict):
                    citizen = res["citizen"]
                actions.append(f"⚡ Kerja Cepat diklaim: +{reward} RpK (sisa {rem}/{QUICK_WORK_DAILY_LIMIT} hari ini)")
            except GameAPIError as exc:
                warnings.append(f"Kerja Cepat dilewati: {exc}")

    if cd["work_ready"]:
        if config.dry_run:
            tier_reward = int((tier.get("work") or {}).get("reward") or 0)
            actions.append(f"[DRY-RUN] Akan jalankan Kerja Jabatan (+{tier_reward} RpK)")
        else:
            try:
                res = api.claim_work_reward(citizen_id, token)
                reward = int(res.get("reward") or 0)
                coins_earned += reward
                citizen["coins"] = int(res.get("coins") or citizen.get("coins") or 0)
                if res.get("last_work_at"):
                    citizen["last_work_at"] = res["last_work_at"]
                actions.append(f"💼 Kerja Jabatan diklaim: +{reward} RpK")
            except GameAPIError as exc:
                warnings.append(f"Kerja Jabatan dilewati: {exc}")

    # --- Step 3: Smart property income harvest (anti-truncation + anti-24h-cap) ---
    now = get_now()
    harvest_list, _ = decide_plot_harvest(
        my_plots,
        buildings_by_id,
        income_bonus_pct,
        max_accrual_hours,
        now,
        config.plot_claim_cap_buffer_hours,
        config.plot_claim_max_frac_waste,
        force_all=False,
    )
    for pcode, est_amount, reason in harvest_list:
        ring_tag = pcode.split("-")[0]
        if config.dry_run:
            actions.append(f"[DRY-RUN] Akan panen properti ({ring_tag}) (~+{est_amount} RpK, {reason})")
        else:
            try:
                res = api.claim_property_income(citizen_id, token, pcode)
                got = int(res.get("total") or 0)
                coins_earned += got
                citizen["coins"] = int(res.get("coins") or citizen.get("coins") or 0)
                for p in my_plots:
                    if p["plot_code"] == pcode:
                        p["last_income_claim_at"] = now.isoformat()
                actions.append(f"🏘️ Panen kavling ({ring_tag}): +{got} RpK ({reason})")
            except GameAPIError as exc:
                warnings.append(f"Panen kavling ({ring_tag}) dilewati: {exc}")

    # --- Step 4: Mission completion & claims ---
    claimed_missions = dict(citizen.get("claimed_missions") or {})
    verified = is_citizen_verified(citizen, economy, config.world_id)
    req_verified = economy.get("requireVerified") or {}

    def try_claim_mission(mkey: str) -> None:
        nonlocal citizen, coins_earned, claimed_missions
        if mkey in claimed_missions:
            return
        if config.dry_run:
            actions.append(f"[DRY-RUN] Akan klaim misi '{mkey}'")
            return
        try:
            res = api.claim_mission(citizen_id, token, mkey)
            reward = int(res.get("reward") or 0)
            coins_earned += reward
            if isinstance(res.get("citizen"), dict):
                citizen = res["citizen"]
                claimed_missions = dict(citizen.get("claimed_missions") or {})
            else:
                claimed_missions[mkey] = get_now().isoformat()
            actions.append(f"🎯 Misi '{mkey}' selesai: +{reward} RpK")
        except GameAPIError as exc:
            warnings.append(f"Misi '{mkey}' dilewati: {exc}")

    if "first_salary" not in claimed_missions and citizen.get("last_salary_at"):
        try_claim_mission("first_salary")

    if "first_emote" not in claimed_missions:
        try_claim_mission("first_emote")

    if "first_chat" not in claimed_missions:
        if citizen.get("last_chat_at"):
            try_claim_mission("first_chat")
        elif config.auto_mission_chat:
            if config.dry_run:
                actions.append("[DRY-RUN] Akan kirim 1 sapaan chat untuk misi 'first_chat'")
            else:
                try:
                    api.send_global_chat(citizen_id, token, "Halo warga Konoha! Salam sukses semua.")
                    citizen["last_chat_at"] = get_now().isoformat()
                    try_claim_mission("first_chat")
                except GameAPIError as exc:
                    warnings.append(f"Chat misi dilewati: {exc}")

    if "first_donation" not in claimed_missions:
        donated = int(citizen.get("total_donated") or 0)
        if donated >= FIRST_DONATION_MIN_COINS:
            try_claim_mission("first_donation")
        else:
            needed = FIRST_DONATION_MIN_COINS - donated
            can_donate = (verified or not bool(req_verified.get("donate", True))) and bool(
                world.get("active_project_id")
            ) and not bool(world.get("active_project_completed"))
            if can_donate and int(citizen.get("coins") or 0) >= needed:
                if config.dry_run:
                    actions.append(f"[DRY-RUN] Akan donasi {needed} RpK untuk misi 'first_donation' (+40 RpK)")
                else:
                    try:
                        dres = api.donate_to_project(citizen_id, token, needed)
                        coins_spent += needed
                        citizen["coins"] = int(dres.get("coins") or (int(citizen.get("coins") or 0) - needed))
                        citizen["total_donated"] = donated + needed
                        actions.append(f"🚇 Donasi proyek {needed} RpK untuk misi 'first_donation'")
                        try_claim_mission("first_donation")
                    except GameAPIError as exc:
                        warnings.append(f"Donasi misi dilewati: {exc}")

    # --- Step 5: AI Economic Upgrade Optimizer loop ---
    unlocked_ring = int(world.get("current_ring_unlocked") or 1)
    max_plots = int((economy.get("land") or {}).get("maxPlotsPerCitizen") or 5)
    free_plots_cache: list[dict[str, Any]] = []
    if len(my_plots) < max_plots:
        free_plots_cache = api.get_cheapest_free_plots(unlocked_ring, limit=8)

    ranked: list[InvestmentCandidate] = []
    investments_done = 0
    while True:
        income_breakdown = estimate_daily_income(
            citizen,
            tier,
            catalog,
            owned_props,
            my_plots,
            buildings_by_id,
            config.expected_tier_work_runs_per_day,
        )
        cheapest_free = free_plots_cache[0] if free_plots_cache else None
        ranked = plan_investments(
            citizen=citizen,
            world_config=world_config,
            catalog=catalog,
            owned_property_ids=owned_props,
            my_plots=my_plots,
            cheapest_free_plot=cheapest_free,
            daily_income_rate=income_breakdown["total"],
            horizon_days=config.horizon_days,
            world_id=config.world_id,
        )
        if not config.auto_upgrade or not ranked or investments_done >= config.max_investments_per_run:
            break

        best = ranked[0]
        liquid_coins = int(citizen.get("coins") or 0) - config.min_coin_reserve
        now = get_now()
        force_list, total_claimable = decide_plot_harvest(
            my_plots,
            buildings_by_id,
            income_bonus_pct,
            max_accrual_hours,
            now,
            config.plot_claim_cap_buffer_hours,
            config.plot_claim_max_frac_waste,
            force_all=True,
        )

        if liquid_coins + total_claimable < best.cost:
            break

        if config.dry_run:
            actions.append(
                f"[DRY-RUN] Akan eksekusi investasi optimal: {best.label} "
                f"(biaya {best.cost} RpK, +{best.delta_daily_income:.0f} RpK/hari, "
                f"payback {best.payback_days:.1f} hari)"
            )
            break

        # If we need uncollected plot income to afford best, harvest plots first.
        if liquid_coins < best.cost and force_list:
            for pcode, _, _ in force_list:
                # Server auto-claims accrued income on the upgraded plot itself.
                if best.kind == "upgrade_plot" and pcode == best.plot_code:
                    continue
                try:
                    hres = api.claim_property_income(citizen_id, token, pcode)
                    got = int(hres.get("total") or 0)
                    coins_earned += got
                    citizen["coins"] = int(hres.get("coins") or citizen.get("coins") or 0)
                    for p in my_plots:
                        if p["plot_code"] == pcode:
                            p["last_income_claim_at"] = now.isoformat()
                    actions.append(f"🏘️ Panen kavling ({pcode.split('-')[0]}) untuk upgrade: +{got} RpK")
                except GameAPIError as exc:
                    warnings.append(f"Panen kavling dilewati: {exc}")

        try:
            if best.kind == "catalog_property" and best.property_type:
                bres = api.buy_property(citizen_id, token, best.property_type)
                coins_spent += best.cost
                owned_props.add(best.property_type)
                if isinstance(bres.get("citizen"), dict):
                    citizen = bres["citizen"]
                actions.append(
                    f"🏪 Beli properti optimal: {best.label} (-{best.cost} RpK, +{best.delta_daily_income:.0f} RpK/hari)"
                )
            elif best.kind == "upgrade_plot" and best.plot_code:
                ures = api.build_or_upgrade_property(citizen_id, token, best.plot_code, None, None)
                actual_cost = int(ures.get("cost") or best.cost)
                coins_spent += actual_cost
                citizen["coins"] = int(ures.get("coins") or citizen.get("coins") or 0)
                if isinstance(ures.get("plot"), dict):
                    my_plots = [ures["plot"] if p["plot_code"] == best.plot_code else p for p in my_plots]
                actions.append(
                    f"⬆️ Upgrade optimal: {best.label} (-{actual_cost} RpK, +{best.delta_daily_income:.0f} RpK/hari)"
                )
            elif best.kind == "build_empty_plot" and best.plot_code and best.building_type:
                bres = api.build_or_upgrade_property(citizen_id, token, best.plot_code, best.building_type, None)
                actual_cost = int(bres.get("cost") or best.cost)
                coins_spent += actual_cost
                citizen["coins"] = int(bres.get("coins") or citizen.get("coins") or 0)
                if isinstance(bres.get("plot"), dict):
                    my_plots = [bres["plot"] if p["plot_code"] == best.plot_code else p for p in my_plots]
                actions.append(
                    f"🏗️ Bangun optimal: {best.label} (-{actual_cost} RpK, +{best.delta_daily_income:.0f} RpK/hari)"
                )
            elif best.kind == "buy_plot_and_build" and best.building_type:
                bought_plot = None
                last_err: Exception | None = None
                coins_before_buy = int(citizen.get("coins") or 0)
                while free_plots_cache:
                    cand_plot = free_plots_cache.pop(0)
                    try:
                        pres = api.buy_land_plot(citizen_id, token, cand_plot["plot_code"])
                        bought_plot = pres.get("plot") or cand_plot
                        citizen["coins"] = int(pres.get("coins") or citizen.get("coins") or 0)
                        coins_spent += max(0, coins_before_buy - int(citizen["coins"]))
                        my_plots.append(bought_plot)
                        break
                    except GameAPIError as exc:
                        last_err = exc
                        # Retry next free plot if someone else bought this plot first.
                        if "sudah dimiliki" in str(exc).lower():
                            continue
                        raise
                if not bought_plot:
                    raise GameAPIError(f"Gagal beli kavling kosong: {last_err}")
                pcode = bought_plot["plot_code"]
                bres = api.build_or_upgrade_property(citizen_id, token, pcode, best.building_type, None)
                actual_build_cost = int(bres.get("cost") or 0)
                coins_spent += actual_build_cost
                final_plot = bres.get("plot") or bought_plot
                my_plots = [final_plot if p["plot_code"] == pcode else p for p in my_plots]
                citizen["coins"] = int(bres.get("coins") or citizen.get("coins") or 0)
                actions.append(
                    f"🏗️ Beli kavling {pcode.split('-')[0]} + bangun {best.building_type} L1 "
                    f"(-{best.cost} RpK, +{best.delta_daily_income:.0f} RpK/hari)"
                )
            else:
                break
            investments_done += 1
        except GameAPIError as exc:
            warnings.append(f"Eksekusi investasi '{best.key}' gagal: {exc}")
            break

    # Final snapshot for reporting (strictly PII-redacted).
    now_end = get_now()
    final_cd = compute_cooldowns(citizen, economy, now_end)
    final_income = estimate_daily_income(
        citizen,
        tier,
        catalog,
        owned_props,
        my_plots,
        buildings_by_id,
        config.expected_tier_work_runs_per_day,
    )
    final_coins = int(citizen.get("coins") or 0)
    next_target = ranked[0] if ranked else None
    eta_hours = (
        max(0.0, (next_target.cost + config.min_coin_reserve - final_coins) / max(1.0, final_income["total"]) * 24.0)
        if next_target
        else None
    )

    return {
        "timestamp_utc": now_end.strftime("%Y-%m-%d %H:%M:%S UTC"),
        "timestamp_wib": now_end.astimezone(WIB_TZ).strftime("%Y-%m-%d %H:%M:%S WIB"),
        "dry_run": config.dry_run,
        "tier_id": citizen.get("tier_id"),
        "verified": verified,
        "starting_coins": starting_coins,
        "final_coins": final_coins,
        "coins_earned": coins_earned,
        "coins_spent": coins_spent,
        "owned_catalog_count": len(owned_props),
        "owned_catalog_total": len(catalog),
        "owned_plots_count": len(my_plots),
        "max_plots": max_plots,
        "missions_claimed": len(claimed_missions),
        "missions_total": 4,
        "income": final_income,
        "cooldowns": final_cd,
        "actions": actions,
        "warnings": warnings,
        "next_target": dataclasses.asdict(next_target) if next_target else None,
        "next_target_eta_hours": eta_hours,
        "top_candidates": [dataclasses.asdict(c) for c in ranked[:5]],
    }


def render_markdown_report(summary: dict[str, Any]) -> str:
    mode = "DRY-RUN" if summary["dry_run"] else "LIVE"
    inc = summary["income"]
    cd = summary["cooldowns"]
    lines = [
        f"## 🤖 Republik Konoha Autopilot ({mode})",
        f"- **Waktu:** `{summary['timestamp_wib']}` (`{summary['timestamp_utc']}`)",
        f"- **Tier:** `{summary['tier_id']}` • **Terverifikasi:** `{'Ya' if summary['verified'] else 'Belum'}`",
        f"- **Saldo:** `{summary['starting_coins']}` → **`{summary['final_coins']} RpK`** "
        f"(+{summary['coins_earned']} / -{summary['coins_spent']})",
        f"- **Aset:** Properti Katalog `{summary['owned_catalog_count']}/{summary['owned_catalog_total']}` • "
        f"Kavling Peta `{summary['owned_plots_count']}/{summary['max_plots']}` • "
        f"Misi `{summary['missions_claimed']}/{summary['missions_total']}`",
        f"- **Estimasi Penghasilan:** **`{inc['total']:.0f} RpK/hari`** "
        f"(Gaji `{inc['daily_salary']:.0f}` + Kerja Cepat `{inc['quick_work']:.0f}` + "
        f"Kerja Jabatan `{inc['tier_work']:.0f}` + Kavling `{inc['plot_income']:.0f}`)",
        "",
        "### 📋 Aksi Run Ini",
    ]
    if summary["actions"]:
        lines.extend(f"- {a}" for a in summary["actions"])
    else:
        lines.append("- Tidak ada klaim/upgrade jatuh tempo pada run ini (semua dalam cooldown atau menabung target optimal).")

    if summary["warnings"]:
        lines.append("")
        lines.append("### ⚠️ Catatan")
        lines.extend(f"- {w}" for w in summary["warnings"])

    lines.extend(
        [
            "",
            "### ⏱️ Jadwal Klaim Berikutnya",
            f"- **Gaji Harian:** `{'SIAP' if cd['salary_ready'] else format_duration(cd['salary_wait'])}`",
            f"- **Kerja Cepat:** `{'SIAP' if cd['quick_ready'] else ('Habis hari ini (reset 00:00 WIB)' if cd['quick_left'] == 0 else format_duration(cd['quick_wait']))}` "
            f"(`{cd['quick_used']}/{QUICK_WORK_DAILY_LIMIT}` shift WIB)",
            f"- **Kerja Jabatan:** `{'SIAP' if cd['work_ready'] else format_duration(cd['work_wait'])}`",
        ]
    )

    target = summary.get("next_target")
    if target:
        eta_h = summary.get("next_target_eta_hours") or 0.0
        eta_str = "SIAP BELI" if eta_h <= 0 else f"~{eta_h:.1f} jam ({eta_h / 24.0:.2f} hari)"
        lines.extend(
            [
                "",
                "### 🧠 Keputusan AI Optimizer (Exact Payback + Wait-Time)",
                f"- **Target #1 (HOLD & SAVE):** **{target['label']}**",
                f"- **Progress:** `{summary['final_coins']} / {target['cost']} RpK` • "
                f"**Gain:** `+{target['delta_daily_income']:.0f} RpK/hari` • **ETA:** `{eta_str}`",
                "",
                "| Rank | Opsi Investasi | Biaya | +RpK/hari | Payback | Skor Efektif |",
                "|---:|---|---:|---:|---:|---:|",
            ]
        )
        for idx, cand in enumerate(summary.get("top_candidates") or [], start=1):
            lines.append(
                f"| {idx} | {cand['label']} | {cand['cost']} | +{cand['delta_daily_income']:.0f} | "
                f"{cand['payback_days']:.1f} hari | {cand['effective_payback_days']:.2f} |"
            )

    return "\n".join(lines) + "\n"


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Republik Konoha scheduled autopilot & AI upgrade optimizer.")
    parser.add_argument("--dry-run", action="store_true", help="Inspect and plan without executing any write RPCs.")
    parser.add_argument("--no-upgrade", action="store_true", help="Run claims & missions only, skip auto-upgrades.")
    args = parser.parse_args(argv)

    ktp_code = os.environ.get("RK_KTP_CODE", "").strip()
    pin = os.environ.get("RK_PIN", "").strip()
    if not ktp_code or not pin:
        print("ERROR: RK_KTP_CODE and RK_PIN environment variables are required.", file=sys.stderr)
        return 2

    cfg = AutopilotConfig(
        ktp_code=ktp_code,
        pin=pin,
        supabase_url=os.environ.get("RK_SUPABASE_URL", DEFAULT_SUPABASE_URL).strip() or DEFAULT_SUPABASE_URL,
        supabase_anon_key=os.environ.get("RK_SUPABASE_ANON_KEY", DEFAULT_SUPABASE_ANON_KEY).strip()
        or DEFAULT_SUPABASE_ANON_KEY,
        world_id=os.environ.get("RK_WORLD_ID", DEFAULT_WORLD_ID).strip() or DEFAULT_WORLD_ID,
        dry_run=args.dry_run or _env_bool("RK_DRY_RUN", False),
        auto_upgrade=(not args.no_upgrade) and _env_bool("RK_AUTO_UPGRADE", True),
        auto_mission_chat=_env_bool("RK_AUTO_MISSION_CHAT", True),
        max_wait_seconds=int(os.environ.get("RK_MAX_WAIT_SECONDS", "180")),
        horizon_days=float(os.environ.get("RK_HORIZON_DAYS", "90")),
        min_coin_reserve=int(os.environ.get("RK_MIN_COIN_RESERVE", "0")),
    )

    try:
        summary = run_autopilot(cfg)
    except GameAPIError as exc:
        print(f"ERROR: Game API failure: {exc}", file=sys.stderr)
        return 1

    report = render_markdown_report(summary)
    print(report)

    step_summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if step_summary_path:
        with open(step_summary_path, "a", encoding="utf-8") as fh:
            fh.write(report)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
