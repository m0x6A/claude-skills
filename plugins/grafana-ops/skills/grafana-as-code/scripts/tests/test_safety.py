#!/usr/bin/env python3
"""Tests for the guards that stop a publish from destroying live resources (no network).

    python3 -m unittest discover -s scripts/tests
"""

from __future__ import annotations

import unittest

import support
from support import grafana_config

import publish_alerts


class PruneRefusalTests(unittest.TestCase):
    def refusal(self, pushed: int, live: int, delete: int, allow: bool = False) -> str | None:
        return grafana_config.prune_refusal("dashboards", pushed, live, delete, allow)

    def test_nothing_to_delete_is_always_fine(self) -> None:
        self.assertIsNone(self.refusal(pushed=0, live=0, delete=0))

    def test_an_empty_repository_never_prunes_even_with_the_override(self) -> None:
        self.assertIn("no dashboards were published", self.refusal(pushed=0, live=12, delete=12))
        self.assertIsNotNone(self.refusal(pushed=0, live=12, delete=12, allow=True))

    def test_removing_one_or_two_items_is_routine(self) -> None:
        self.assertIsNone(self.refusal(pushed=1, live=3, delete=2))

    def test_deleting_more_than_half_needs_the_override(self) -> None:
        message = self.refusal(pushed=4, live=10, delete=6)
        self.assertIn(grafana_config.MASS_PRUNE_FLAG, message)
        self.assertIsNone(self.refusal(pushed=4, live=10, delete=6, allow=True))

    def test_deleting_exactly_half_is_allowed(self) -> None:
        self.assertIsNone(self.refusal(pushed=5, live=10, delete=5))


class ContactPointRefusalTests(unittest.TestCase):
    def test_creating_a_new_contact_point_is_fine(self) -> None:
        self.assertIsNone(publish_alerts.contact_point_refusal([], "acme-email", adopt=False))

    def test_one_this_tool_provisioned_is_updated(self) -> None:
        existing = [{"uid": "c1", "name": "acme-email", "provenance": "api"}]
        self.assertIsNone(publish_alerts.contact_point_refusal(existing, "acme-email", adopt=False))

    def test_one_made_in_the_ui_is_not_overwritten(self) -> None:
        existing = [{"uid": "c1", "name": "acme-email", "provenance": ""}]
        message = publish_alerts.contact_point_refusal(existing, "acme-email", adopt=False)
        self.assertIn("--adopt-contact-point", message)

    def test_a_missing_provenance_counts_as_foreign(self) -> None:
        existing = [{"uid": "c1", "name": "acme-email"}]
        self.assertIsNotNone(publish_alerts.contact_point_refusal(existing, "acme-email", adopt=False))

    def test_adopting_is_an_explicit_choice(self) -> None:
        existing = [{"uid": "c1", "name": "acme-email", "provenance": ""}]
        self.assertIsNone(publish_alerts.contact_point_refusal(existing, "acme-email", adopt=True))


if __name__ == "__main__":
    unittest.main()
