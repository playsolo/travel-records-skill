import copy
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location("resolve_stays", Path(__file__).resolve().parents[1] / "scripts/resolve_stays.py")
resolver = importlib.util.module_from_spec(spec)
spec.loader.exec_module(resolver)


def stay(key, start="2015-04-25", end="2015-04-26", kind="reservation", booked="2015-04-01T12:00:00Z", traveler="person-a", **extra):
    return dict(id=key, start=start, end=end, evidence_kind=kind, booked_at=booked, traveler_scope=traveler, **extra)


def decide(*rows):
    result = resolver.resolve({"policy": resolver.POLICY, "stays": list(rows)})
    return {x["id"]: x for x in result["decisions"]}


class AcceptanceTests(unittest.TestCase):
    def test_isolated_reservation_accepted_without_photos(self):
        self.assertEqual(decide(stay("a", booked=None))["a"]["acceptance"], "accepted")

    def test_actual_evidence_beats_even_a_newer_booking(self):
        r = decide(stay("bill", kind="stay_evidence"), stay("new", booked="2015-04-24T12:00:00Z"))
        self.assertEqual(r["bill"]["acceptance"], "accepted")
        self.assertEqual(r["new"]["reason"], "conflicts_with_stay_evidence")

    def test_later_original_booking_wins_regardless_of_input_order(self):
        old, new = stay("old"), stay("new", booked="2015-04-02T13:00:00+01:00")
        for rows in [(old, new), (new, old)]:
            r = decide(*rows)
            self.assertEqual(r["old"]["acceptance"], "not_accepted")
            self.assertEqual(r["new"]["acceptance"], "accepted")

    def test_checkout_and_next_checkin_do_not_overlap(self):
        r = decide(stay("a"), stay("b", start="2015-04-26", end="2015-04-27"))
        self.assertTrue(all(x["acceptance"] == "accepted" for x in r.values()))

    def test_different_travelers_do_not_conflict(self):
        r = decide(stay("a"), stay("b", traveler="person-b"))
        self.assertTrue(all(x["acceptance"] == "accepted" for x in r.values()))

    def test_missing_or_tied_order_is_not_guessed(self):
        for stamp in [None, "2015-04-01T12:00:00Z"]:
            r = decide(stay("a"), stay("b", booked=stamp))
            self.assertTrue(all(x["acceptance"] == "needs_review" for x in r.values()))

    def test_conflicting_bills_remain_for_review(self):
        r = decide(stay("a", kind="stay_evidence"), stay("b", kind="stay_evidence"))
        self.assertTrue(all(x["acceptance"] == "needs_review" for x in r.values()))

    def test_superseded_booking_does_not_reappear_transitively(self):
        r = decide(stay("a", start="2015-04-25", end="2015-04-27"),
                   stay("b", start="2015-04-26", end="2015-04-28", booked="2015-04-02T12:00:00Z"),
                   stay("c", start="2015-04-27", end="2015-04-29", booked="2015-04-03T12:00:00Z"))
        self.assertEqual([r[k]["acceptance"] for k in ["a", "b", "c"]], ["not_accepted", "not_accepted", "accepted"])

    def test_cancellation_and_partial_dates_not_auto_accepted(self):
        self.assertEqual(decide(stay("a", cancelled=True))["a"]["reason"], "explicitly_cancelled")
        self.assertEqual(decide(stay("a", start="2015-04"))["a"]["acceptance"], "needs_review")

    def test_unknown_checkout_cannot_prove_no_conflict(self):
        r = decide(stay("e", kind="stay_evidence", end=None), stay("r"))
        self.assertEqual(r["r"]["acceptance"], "needs_review")
        self.assertEqual(r["r"]["related_ids"], ["e"])

    def test_unknown_traveler_evidence_can_block_unjustified_acceptance(self):
        r = decide(stay("e", kind="stay_evidence", traveler=None), stay("r"))
        self.assertEqual(r["r"]["reason"], "potential_conflict_with_unresolved_record")

    def test_unknown_start_with_known_prior_checkout_does_not_block_future(self):
        r = decide(stay("e", kind="stay_evidence", start=None, end="2015-04-24"), stay("r"))
        self.assertEqual(r["r"]["acceptance"], "accepted")

    def test_blank_or_nonstring_scope_is_consistently_unknown(self):
        for scope in [" ", "\t", 12, {"unexpected": "shape"}]:
            r = decide(stay("e", kind="stay_evidence", traveler=scope), stay("r"))
            self.assertEqual(r["r"]["acceptance"], "needs_review")
        r = decide(stay("a", traveler=" person-a "), stay("b", booked="2015-04-02T12:00:00Z"))
        self.assertEqual(r["a"]["acceptance"], "not_accepted")

    def test_input_not_mutated_and_policy_is_explicit(self):
        r = stay("a")
        original = copy.deepcopy(r)
        decide(r)
        self.assertEqual(r, original)
        with self.assertRaises(ValueError):
            resolver.resolve({"stays": [r]})


class RetainedOrdersTests(unittest.TestCase):
    def resolve(self, *rows):
        return resolver.resolve({"policy": resolver.RETAIN_ORDERS_POLICY, "stays": list(rows)})

    def row(self, key, **kwargs):
        return stay(key, property_key=kwargs.pop("property_key", "hotel-a"), **kwargs)

    def test_same_hotel_orders_retained_without_booking_order(self):
        r = self.resolve(self.row("a", booked=None), self.row("b", booked=None))
        self.assertTrue(all(x["acceptance"] == "accepted" for x in r["decisions"]))
        self.assertEqual(r["nights"]["by_property"][0]["nights"], 1)

    def test_two_rooms_do_not_double_stay_nights(self):
        r = self.resolve(self.row("a", end="2015-04-27", room_count=2),
                         self.row("b", end="2015-04-27", room_count=1))
        self.assertEqual(r["nights"]["by_property"][0]["nights"], 2)
        self.assertEqual(r["nights"]["by_traveler_scope"][0]["nights"], 2)

    def test_overlapping_independent_bills_for_same_hotel_are_compatible(self):
        r = self.resolve(self.row("a", kind="stay_evidence", end="2015-04-27"),
                         self.row("b", kind="stay_evidence", start="2015-04-26", end="2015-04-28"))
        self.assertTrue(all(x["acceptance"] == "accepted" for x in r["decisions"]))
        self.assertEqual(r["nights"]["by_property"][0]["nights"], 3)

    def test_same_hotel_reservation_and_bill_do_not_conflict(self):
        r = self.resolve(self.row("r"), self.row("b", kind="stay_evidence"))
        self.assertTrue(all(x["acceptance"] == "accepted" for x in r["decisions"]))
        self.assertEqual(r["nights"]["by_property"][0]["nights"], 1)

    def test_linked_bill_dates_win_before_other_hotel_conflict_check(self):
        planned = self.row("r", start="2015-04-24", end="2015-04-28", stay_key="same")
        original = copy.deepcopy(planned)
        r = self.resolve(planned, self.row("b", kind="stay_evidence", stay_key="same"),
                         self.row("other", kind="stay_evidence", property_key="hotel-b",
                                  start="2015-04-24", end="2015-04-25"))
        decisions = {x["id"]: x for x in r["decisions"]}
        self.assertEqual(decisions["r"]["acceptance"], "accepted")
        self.assertEqual(decisions["r"]["effective_dates"], dict(start="2015-04-25", end="2015-04-26"))
        self.assertEqual(planned, original)
        self.assertEqual(r["nights"]["by_traveler_scope"][0]["nights"], 2)

    def test_unresolved_dates_are_not_positive_conflict_evidence(self):
        r = self.resolve(self.row("partial", kind="stay_evidence", end=None), self.row("r", property_key="hotel-b"))
        self.assertTrue(all(x["acceptance"] == "accepted" for x in r["decisions"]))
        self.assertEqual(r["nights"]["pending_date_record_ids"], ["partial"])

    def test_unknown_traveler_does_not_block_other_orders(self):
        r = self.resolve(self.row("a", traveler=None), self.row("b", property_key="hotel-b"))
        self.assertTrue(all(x["acceptance"] == "accepted" for x in r["decisions"]))

    def test_other_hotel_actual_evidence_still_beats_reservation(self):
        r = self.resolve(self.row("r"), self.row("b", kind="stay_evidence", property_key="hotel-b"))
        decisions = {x["id"]: x for x in r["decisions"]}
        self.assertEqual(decisions["r"]["reason"], "conflicts_with_stay_evidence")

    def test_later_other_hotel_booking_and_explicit_cancellation(self):
        r = self.resolve(self.row("old"), self.row("new", property_key="hotel-b", booked="2015-04-02T12:00:00Z"),
                         self.row("cancelled", cancelled=True, property_key="hotel-c"))
        decisions = {x["id"]: x for x in r["decisions"]}
        self.assertEqual(decisions["old"]["reason"], "superseded_by_later_booking")
        self.assertEqual(decisions["new"]["acceptance"], "accepted")
        self.assertEqual(decisions["cancelled"]["reason"], "explicitly_cancelled")

    def test_long_intervals_count_without_materializing_each_date(self):
        r = self.resolve(self.row("a", start="1800-01-01", end="9999-12-31"))
        self.assertGreater(r["nights"]["by_property"][0]["nights"], 2000000)

    def test_invalid_complete_dates_are_not_treated_as_merely_missing(self):
        r = self.resolve(self.row("a", end="2015-04-24"))
        self.assertEqual(r["decisions"][0]["reason"], "invalid_stay_dates")
        self.assertEqual(r["nights"]["by_property"], [])


if __name__ == "__main__":
    unittest.main()
