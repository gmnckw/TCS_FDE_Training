"""Offline tests for the deterministic layer (no API key, no model calls).

    python -m unittest discover -s tests -v
"""
from __future__ import annotations

import asyncio
import json
import os
import tempfile
import unittest
from decimal import Decimal

# Point the workspace at a temp folder BEFORE importing the app.
_TMP = tempfile.mkdtemp(prefix="expense_test_")
os.environ["EXPENSE_WORKSPACE"] = _TMP

from expense_app import claims_mcp, config, policy, store, tools  # noqa: E402

SAMPLES = {c["id"]: c for c in json.loads(config.SAMPLE_CLAIMS_FILE.read_text(encoding="utf-8"))}


def run(coro):
    return asyncio.run(coro)


def text_of(result) -> str:
    return result["content"][0]["text"]


def good_reply(first: str, body: str = "We have recommended this amount; a finance reviewer will make the "
               "final decision.") -> str:
    return f"Hi {first},\n\n{body}\n\nFinance Operations"


class Arithmetic(unittest.TestCase):
    def test_fx_rounding(self):
        self.assertEqual(policy.to_usd(795, "GBP"), Decimal("1033.50"))
        self.assertEqual(policy.to_usd(1450, "INR"), Decimal("17.40"))
        self.assertEqual(policy.to_usd(45, "eur"), Decimal("49.50"))
        self.assertEqual(policy.to_usd("0.005", "USD"), Decimal("0.01"))        # half-up

    def test_unknown_currency(self):
        with self.assertRaises(policy.PolicyDataError):
            policy.to_usd(10, "JPY")

    def test_meal_alcohol_then_per_person(self):
        r = policy.calculate_reimbursable(SAMPLES["CLM-3002"], "meal", excluded_amount=96, attendees=4)
        self.assertEqual(r["reimbursable_usd"], 300.00)
        self.assertTrue(r["over_limit"])

    def test_meal_under_limit(self):
        r = policy.calculate_reimbursable(SAMPLES["CLM-3001"], "meal", attendees=3)
        self.assertEqual(r["reimbursable_usd"], 198.00)
        self.assertFalse(r["over_limit"])

    def test_hotel_high_cost_city(self):
        r = policy.calculate_reimbursable(SAMPLES["CLM-3003"], "hotel", nights=3, city="London")
        self.assertEqual(r["reimbursable_usd"], 960.00)

    def test_per_diem_excludes_covered_meal(self):
        r = policy.calculate_reimbursable(SAMPLES["CLM-3010"], "per_diem", days=5, excluded_amount=49.50)
        self.assertEqual(r["reimbursable_usd"], 300.00)

    def test_bad_inputs_raise_cleanly(self):
        with self.assertRaises(policy.PolicyDataError):
            policy.calculate_reimbursable(SAMPLES["CLM-3001"], "meal")              # no attendees
        with self.assertRaises(policy.PolicyDataError):
            policy.calculate_reimbursable(SAMPLES["CLM-3001"], "spa")
        with self.assertRaises(policy.PolicyDataError):
            policy.calculate_reimbursable(SAMPLES["CLM-3001"], "actual_cost", excluded_amount=999)


class Facts(unittest.TestCase):
    def test_duplicate(self):
        self.assertEqual(policy.claim_facts(SAMPLES["CLM-3007"])["duplicate_of"], ["C-9004"])
        self.assertEqual(policy.claim_facts(SAMPLES["CLM-3001"])["duplicate_of"], [])

    def test_late(self):
        f = policy.claim_facts(SAMPLES["CLM-3009"])
        self.assertTrue(f["late"])
        self.assertEqual(f["filing_gap_days"], 102)

    def test_split(self):
        f = policy.claim_facts(SAMPLES["CLM-3005"])
        self.assertTrue(f["split"]["is_split"])
        self.assertEqual(f["split"]["total_usd"], 423.0)

    def test_preapproval_of_someone_else_is_invalid(self):
        r = policy.check_preapproval(SAMPLES["CLM-3004"], "equipment", Decimal("249"))
        self.assertFalse(r["valid"])
        self.assertNotIn("Asha", json.dumps(r))      # never reveals whose it is

    def test_preapproval_own_record(self):
        claim = {**SAMPLES["CLM-3004"], "employee": "Mei Tan", "pre_approval": "PA-5001"}
        self.assertTrue(policy.check_preapproval(claim, "equipment", Decimal("600"))["valid"])
        self.assertFalse(policy.check_preapproval(claim, "equipment", Decimal("900"))["valid"])

    def test_monthly_cap(self):
        self.assertTrue(policy.monthly_cap_check("Asha Verma", Decimal("960"))["exceeds_cap"])
        self.assertFalse(policy.monthly_cap_check("Mei Tan", Decimal("300"))["exceeds_cap"])

    def test_injection_detected(self):
        self.assertTrue(policy.claim_facts(SAMPLES["CLM-3008"])["injection_signals"])
        self.assertFalse(policy.claim_facts(SAMPLES["CLM-3001"])["injection_signals"])


def decision(**kw):
    base = {"claim_id": "CLM-3001", "decision": "approve", "approved_amount_usd": 198.00,
            "policy_refs": ["EX-201"], "flags": [], "escalate_to": "none",
            "reply_to_employee": good_reply("Daniel"), "reviewer_notes": "ok"}
    base.update(kw)
    return base


class Guard(unittest.TestCase):
    def test_clean_decision_passes(self):
        self.assertEqual(policy.decision_problems(decision(), SAMPLES["CLM-3001"]), [])

    def test_more_than_claimed_blocked(self):
        p = policy.decision_problems(decision(approved_amount_usd=250), SAMPLES["CLM-3001"])
        self.assertTrue(any("more than the claimed" in x for x in p))

    def test_duplicate_must_be_rejected(self):
        d = decision(claim_id="CLM-3007", reply_to_employee=good_reply("Ravi"), approved_amount_usd=17.40)
        self.assertTrue(any("duplicates earlier claim C-9004" in x for x in
                            policy.decision_problems(d, SAMPLES["CLM-3007"])))

    def test_late_must_escalate_to_finance_controller(self):
        d = decision(claim_id="CLM-3009", approved_amount_usd=96)
        self.assertTrue(any("finance-controller" in x for x in policy.decision_problems(d, SAMPLES["CLM-3009"])))

    def test_monthly_cap_enforced(self):
        d = decision(claim_id="CLM-3003", approved_amount_usd=960, reply_to_employee=good_reply("Asha"))
        self.assertTrue(any("Monthly cap" in x for x in policy.decision_problems(d, SAMPLES["CLM-3003"])))
        ok = decision(claim_id="CLM-3003", decision="escalate", approved_amount_usd=0, escalate_to="manager",
                      escalation_reason="Over monthly cap", reimbursable_before_cap_usd=960,
                      flags=["over_limit", "monthly_cap_exceeded"], reply_to_employee=good_reply(
                          "Asha", "Your manager will review this because it would take you over your monthly "
                          "limit. A finance reviewer will make the final decision."))
        self.assertEqual(policy.decision_problems(ok, SAMPLES["CLM-3003"]), [])

    def test_injection_flag_required(self):
        d = decision(claim_id="CLM-3008", decision="reject", approved_amount_usd=0, flags=["prohibited_item"],
                     reply_to_employee=good_reply("Chloe", "Gym memberships are not reimbursable."))
        self.assertTrue(any("injection_attempt" in x for x in policy.decision_problems(d, SAMPLES["CLM-3008"])))


class ReplyRules(unittest.TestCase):
    claim = SAMPLES["CLM-3004"]

    def check(self, body):
        return policy.reply_problems(good_reply("Lucas", body), self.claim)

    def test_payment_statements_blocked(self):
        for body in ["Your claim has been paid.", "You will be reimbursed in the next payroll.",
                     "The amount will be paid within 5 business days.", "Your claim has been approved."]:
            self.assertTrue(self.check(body), body)

    def test_policy_description_is_not_a_payment_statement(self):
        # Regression: the guard once blocked this sentence during the CLM-3002 review.
        self.assertEqual(self.check("Team meals are reimbursed up to $75 per person. A finance reviewer "
                                    "will make the final decision."), [])
        self.assertTrue(self.check("Your claim was paid yesterday."))

    def test_neutral_wording_passes(self):
        self.assertEqual(self.check("PA-5002 is not on your record as an equipment pre-approval. Please ask "
                                    "your manager for one covering $249.00 and send us its number. Claims must "
                                    "be submitted within 60 days. A finance reviewer will make the final decision."), [])

    def test_other_employee_blocked(self):
        self.assertTrue(self.check("PA-5002 belongs to Asha Verma."))
        self.assertTrue(self.check("That number belongs to another employee."))

    def test_accusation_blocked(self):
        self.assertTrue(self.check("This looks like fraud."))
        self.assertTrue(self.check("You deliberately split the purchase."))

    def test_name_and_signoff(self):
        self.assertTrue(policy.reply_problems("Hello,\n\nSome reason here for the decision.\n\nThanks", self.claim))


class IntakeAndTools(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        store.seed_samples()

    def test_intake_roundtrip_and_restart(self):
        path = store.save_claim({"employee": "Omar Haddad", "expense_date": "2026-11-20", "category": "travel",
                                 "vendor": "Lyft", "amount": "18.5", "currency": "usd", "receipt": "no",
                                 "description": "Taxi to the client."})
        claim = json.loads(path.read_text(encoding="utf-8"))
        self.assertTrue(store.valid_claim_id(claim["id"]))
        self.assertEqual(claim["receipt"], "missing")
        self.assertEqual(store.load_claim(claim["id"])["amount"], 18.5)       # re-read from disk
        self.assertNotEqual(store.next_claim_id(), claim["id"])               # ids are unique

    def test_empty_claim_rejected(self):
        with self.assertRaises(ValueError):
            store.save_claim({})

    def test_path_traversal_rejected(self):
        self.assertIsNone(store.load_claim("../../data/employees"))
        self.assertIn("not a valid claim id", claims_mcp.read_claim("../x"))

    def test_read_claim_fences_untrusted_text(self):
        store.seed_samples(["CLM-3008"])
        out = claims_mcp.read_claim("CLM-3008")
        self.assertIn("UNTRUSTED", out)
        self.assertTrue(json.loads(out.split("\n", 1)[1])["instruction_like_text"])

    def test_duplicate_check_survives_unknown_currency(self):
        # Regression: an unsupported currency used to make the whole tool fail, skipping check 2.
        path = store.save_claim({"employee": "Omar Haddad", "expense_date": "2026-11-18", "category": "travel",
                                 "vendor": "Tokyo Metro", "amount": 4200, "currency": "JPY", "receipt": "yes",
                                 "description": "Train fares."})
        cid = json.loads(path.read_text(encoding="utf-8"))["id"]
        r = run(tools.find_related_claims.handler({"claim_id": cid}))
        self.assertFalse(r.get("is_error"))
        body = json.loads(text_of(r))
        self.assertFalse(body["is_duplicate"])
        self.assertIn("JPY", body["usd_checks_unavailable"])

    def test_tools_return_errors_not_exceptions(self):
        r = run(tools.lookup_employee.handler({"employee_name": "Nobody Here"}))
        self.assertTrue(r.get("is_error"))
        r = run(tools.convert_to_usd.handler({"amount": 10, "currency": "XYZ"}))
        self.assertTrue(r.get("is_error"))
        r = run(tools.find_related_claims.handler({"claim_id": "CLM-9999"}))
        self.assertTrue(r.get("is_error"))
        r = run(tools.calculate_reimbursable.handler({"claim_id": "CLM-3008", "rule": "meal"}))
        self.assertTrue(r.get("is_error"))


class ApprovalGate(unittest.TestCase):
    """Stretch goal: the reply is held until a person approves the current revision."""

    @classmethod
    def setUpClass(cls):
        store.seed_samples(["CLM-3001"])

    def save(self, **kw):
        store.write_decision({**decision(**kw), "escalation_reason": "", "employee": "Daniel Okafor"})
        return store.load_decision("CLM-3001")

    def test_new_revision_is_pending_and_not_released(self):
        d = self.save()
        self.assertEqual(d["approval"]["status"], "pending_review")
        self.assertFalse(store.released_path("CLM-3001").exists())

    def test_approve_releases_and_new_revision_withdraws(self):
        self.save()
        store.set_approval("CLM-3001", "approved", "Ana Ruiz")
        self.assertTrue(store.released_path("CLM-3001").exists())
        self.assertEqual(store.load_decision("CLM-3001")["approval"]["by"], "Ana Ruiz")
        d = self.save()                                       # agent saves a new revision
        self.assertEqual(d["approval"]["status"], "pending_review")
        self.assertFalse(store.released_path("CLM-3001").exists())

    def test_cannot_approve_a_reply_that_breaks_a_hard_stop(self):
        self.save()
        d = store.load_decision("CLM-3001")
        d["reply_to_employee"] = good_reply("Daniel", "Your claim has been paid.")   # edited on disk
        store._atomic_write(store.decision_path("CLM-3001"), json.dumps(d))
        with self.assertRaises(ValueError):
            store.set_approval("CLM-3001", "approved", "Ana Ruiz")
        self.assertFalse(store.released_path("CLM-3001").exists())

    def test_name_and_note_required(self):
        self.save()
        with self.assertRaises(ValueError):
            store.set_approval("CLM-3001", "approved", "  ")
        with self.assertRaises(ValueError):
            store.set_approval("CLM-3001", "changes_requested", "Ana Ruiz", "")


class Scoring(unittest.TestCase):
    def test_perfect_and_partial(self):
        from expense_app import scoring
        want = scoring.load_expected()["CLM-3002"]
        got = {**want, "reply_to_employee": good_reply("Mei")}
        self.assertEqual(scoring.score_one(got, want, SAMPLES["CLM-3002"])["total"], 1.0)
        worse = {**got, "approved_amount_usd": 300.01, "flags": ["alcohol_excluded"]}
        r = scoring.score_one(worse, want, SAMPLES["CLM-3002"])
        self.assertEqual(r["fields"]["amount"], 0.0)
        self.assertEqual(r["fields"]["flags"], 0.5)


if __name__ == "__main__":
    unittest.main()
