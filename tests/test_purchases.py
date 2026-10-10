import json
import re
from pathlib import Path

import pytest

from receiver_design import verify

PURCHASES = Path(__file__).parents[1] / "amazon_purchases.json"


def test_amazon_purchases_have_links_prices_and_fit_the_budget():
    purchases = json.loads(PURCHASES.read_text())
    totals = {}
    for key in ("items", "recommended_extras"):
        totals[key] = 0.0
        for item in purchases[key]:
            assert re.fullmatch(r"B0[A-Z0-9]{8}", item["asin"])
            assert item["url"] == f"https://www.amazon.com/dp/{item['asin']}"
            assert item["unit_price_usd"] > 0 and item["quantity"] >= 1
            assert item["role"] and item["listing_title"]
            totals[key] += item["quantity"] * item["unit_price_usd"]
    assert all(item["references"] for item in purchases["items"])
    assert purchases["total_usd"] == pytest.approx(totals["items"], abs=0.005)
    assert purchases["total_with_extras_usd"] == pytest.approx(
        totals["items"] + totals["recommended_extras"], abs=0.005)
    assert totals["items"] <= purchases["budget_usd"]


def test_bom_uses_every_purchase_and_only_allowed_parts():
    verify.allowed_components_check()


def test_purchase_check_rejects_an_over_budget_order(tmp_path, monkeypatch):
    purchases = json.loads(PURCHASES.read_text())
    purchases["items"][0]["quantity"] = 3
    purchases["total_usd"] = sum(item["quantity"] * item["unit_price_usd"]
                                 for item in purchases["items"])
    purchases["total_with_extras_usd"] = purchases["total_usd"] + sum(
        item["quantity"] * item["unit_price_usd"]
        for item in purchases["recommended_extras"])
    path = tmp_path / "amazon_purchases.json"
    path.write_text(json.dumps(purchases))
    monkeypatch.setattr(verify, "PURCHASES", path)

    with pytest.raises(SystemExit, match="over the 50.00 USD budget"):
        verify.purchases_check()
