"""Tests for AirlinePolicy — airline filtering logic."""

from aventure_tracker.models.flight import AirlinePolicy, AirlineRule

ROUTE_THRESHOLD = 300_000  # COP


class TestAirlinePolicyPriorityRule:
    """Rule 1: Priority airlines included if price ≤ route threshold."""

    def test_latam_below_threshold_included(self) -> None:
        policy = AirlinePolicy.default()
        ok, reason = policy.should_track("LATAM", 250_000, ROUTE_THRESHOLD)
        assert ok
        assert "priority" in reason

    def test_latam_above_threshold_excluded(self) -> None:
        policy = AirlinePolicy.default()
        ok, _ = policy.should_track("LATAM", 400_000, ROUTE_THRESHOLD)
        assert not ok

    def test_latam_exact_threshold_included(self) -> None:
        policy = AirlinePolicy.default()
        ok, _ = policy.should_track("LATAM", ROUTE_THRESHOLD, ROUTE_THRESHOLD)
        assert ok

    def test_latam_case_insensitive(self) -> None:
        policy = AirlinePolicy.default()
        ok, _ = policy.should_track("Latam Airlines Colombia", 200_000, ROUTE_THRESHOLD)
        assert ok

    def test_multiple_priority_airlines(self) -> None:
        policy = AirlinePolicy(
            priority_airlines=["LATAM", "Avianca"], bargain_threshold=110_000
        )
        ok, _ = policy.should_track("Avianca", 250_000, ROUTE_THRESHOLD)
        assert ok


class TestAirlinePolicyBargainRule:
    """Rule 2: Any airline included if price ≤ bargain_threshold."""

    def test_wingo_below_bargain_included(self) -> None:
        policy = AirlinePolicy.default()
        ok, reason = policy.should_track("Wingo", 90_000, ROUTE_THRESHOLD)
        assert ok
        assert "bargain" in reason

    def test_wingo_at_bargain_threshold_included(self) -> None:
        policy = AirlinePolicy.default()
        ok, _ = policy.should_track("Wingo", 110_000, ROUTE_THRESHOLD)
        assert ok

    def test_wingo_above_bargain_excluded(self) -> None:
        policy = AirlinePolicy.default()
        ok, _ = policy.should_track("Wingo", 111_000, ROUTE_THRESHOLD)
        assert not ok

    def test_jetsmart_below_bargain_included(self) -> None:
        policy = AirlinePolicy.default()
        ok, _ = policy.should_track("JetSMART", 80_000, ROUTE_THRESHOLD)
        assert ok

    def test_unknown_airline_below_bargain_included(self) -> None:
        policy = AirlinePolicy.default()
        ok, _ = policy.should_track("Unknown Carrier", 50_000, ROUTE_THRESHOLD)
        assert ok

    def test_custom_bargain_threshold(self) -> None:
        policy = AirlinePolicy(priority_airlines=["LATAM"], bargain_threshold=150_000)
        ok, _ = policy.should_track("Wingo", 140_000, ROUTE_THRESHOLD)
        assert ok
        ok2, _ = policy.should_track("Wingo", 160_000, ROUTE_THRESHOLD)
        assert not ok2


class TestAirlinePolicyExtraRules:
    """Rule 3: Extra per-airline rules with custom thresholds."""

    def test_extra_airline_below_max_price_included(self) -> None:
        policy = AirlinePolicy(
            priority_airlines=["LATAM"],
            bargain_threshold=110_000,
            extra_airlines=[AirlineRule(name="Wingo", max_price=200_000)],
        )
        ok, reason = policy.should_track("Wingo", 180_000, ROUTE_THRESHOLD)
        assert ok
        assert "extra rule" in reason

    def test_extra_airline_above_max_price_excluded(self) -> None:
        policy = AirlinePolicy(
            priority_airlines=["LATAM"],
            bargain_threshold=110_000,
            extra_airlines=[AirlineRule(name="Wingo", max_price=200_000)],
        )
        ok, _ = policy.should_track("Wingo", 250_000, ROUTE_THRESHOLD)
        assert not ok

    def test_extra_airline_no_max_price_always_included(self) -> None:
        policy = AirlinePolicy(
            priority_airlines=["LATAM"],
            bargain_threshold=110_000,
            extra_airlines=[AirlineRule(name="Avianca", max_price=None)],
        )
        ok, _ = policy.should_track("Avianca", 900_000, ROUTE_THRESHOLD)
        assert ok

    def test_extra_rule_case_insensitive(self) -> None:
        policy = AirlinePolicy(
            priority_airlines=["LATAM"],
            bargain_threshold=110_000,
            extra_airlines=[AirlineRule(name="wingo", max_price=200_000)],
        )
        ok, _ = policy.should_track("WINGO", 150_000, ROUTE_THRESHOLD)
        assert ok


class TestAirlinePolicySkipRule:
    """Rule 4: Skip if none of the above rules match."""

    def test_non_priority_above_bargain_skipped(self) -> None:
        policy = AirlinePolicy.default()
        ok, reason = policy.should_track("Avianca", 250_000, ROUTE_THRESHOLD)
        assert not ok
        assert "not priority" in reason

    def test_jetsmart_above_bargain_skipped(self) -> None:
        policy = AirlinePolicy.default()
        ok, _ = policy.should_track("JetSMART", 200_000, ROUTE_THRESHOLD)
        assert not ok


class TestAddAirlineRuntime:
    """add_airline() modifies policy at runtime without config reload."""

    def test_add_airline_runtime(self) -> None:
        policy = AirlinePolicy.default()
        # Wingo above bargain → excluded
        ok, _ = policy.should_track("Wingo", 180_000, ROUTE_THRESHOLD)
        assert not ok

        # Add Wingo at runtime
        policy.add_airline("Wingo", max_price=200_000)
        ok, _ = policy.should_track("Wingo", 180_000, ROUTE_THRESHOLD)
        assert ok

    def test_add_airline_updates_existing_rule(self) -> None:
        policy = AirlinePolicy(
            priority_airlines=["LATAM"],
            bargain_threshold=110_000,
            extra_airlines=[AirlineRule(name="Wingo", max_price=150_000)],
        )
        # Update threshold
        policy.add_airline("Wingo", max_price=250_000)
        assert len(policy.extra_airlines) == 1  # No duplicate
        ok, _ = policy.should_track("Wingo", 200_000, ROUTE_THRESHOLD)
        assert ok

    def test_add_airline_no_max_price(self) -> None:
        policy = AirlinePolicy.default()
        policy.add_airline("Avianca")
        ok, _ = policy.should_track("Avianca", 500_000, ROUTE_THRESHOLD)
        assert ok


class TestAirlinePolicyFromYaml:
    """AirlinePolicy loads correctly from YAML via RoutesConfig."""

    def test_loads_from_routes_yaml(self, tmp_path) -> None:
        from aventure_tracker.models.flight import RoutesConfig

        yaml_content = """
airline_policy:
  priority_airlines: [LATAM]
  bargain_threshold: 110000
  extra_airlines:
    - name: Wingo
      max_price: 180000
routes:
  - origin: BAQ
    destination: MDE
    price_threshold: 300000
    drop_percentage: 15
    search_days: [thursday, friday]
"""
        path = tmp_path / "routes.yaml"
        path.write_text(yaml_content)
        config = RoutesConfig.from_yaml(path)

        policy = config.airline_policy
        assert "LATAM" in policy.priority_airlines
        assert policy.bargain_threshold == 110_000
        assert len(policy.extra_airlines) == 1
        assert policy.extra_airlines[0].name == "Wingo"
        assert policy.extra_airlines[0].max_price == 180_000

    def test_default_policy_when_not_in_yaml(self, tmp_path) -> None:
        from aventure_tracker.models.flight import RoutesConfig

        yaml_content = """
routes:
  - origin: BAQ
    destination: MDE
    price_threshold: 300000
    drop_percentage: 15
    search_days: [friday]
"""
        path = tmp_path / "routes.yaml"
        path.write_text(yaml_content)
        config = RoutesConfig.from_yaml(path)

        policy = config.airline_policy
        assert policy.bargain_threshold == 110_000  # default
        assert "LATAM" in policy.priority_airlines  # default
