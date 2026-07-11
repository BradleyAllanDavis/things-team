"""SpokeCore tests over in-memory fakes: outbound scan discipline (exact
trigger match, refusals, sent-cache), crash-then-rejournal, lost-ack
redelivery, terminal apply, retag-only-after-applied."""

import os
import tempfile
import unittest

from hub.direct import DirectHubClient
from hub.ledger import Ledger
from spoke.core import DELEGATED_TAG, SpokeCore, SpokeState
from tests.fakes import CrashAfterFire, FakeReader, FakeThings, FakeWriter, FlakyHub


class SpokeCoreTestBase(unittest.TestCase):
    """A real ledger + hub (Direct clients) with fake Things on both ends —
    bradley's spoke and jill's spoke share the hub, like production."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ledger = Ledger(os.path.join(self.tmp.name, "ledger.sqlite"))
        tenant = self.ledger.create_tenant("davis")["id"]
        b = self.ledger.create_member(tenant, "bradley", "B")
        j = self.ledger.create_member(tenant, "jill", "J")
        pb = self.ledger.principal_for_member(
            b["id"], self.ledger.ensure_gateway_device(b["id"]))
        pj = self.ledger.principal_for_member(
            j["id"], self.ledger.ensure_gateway_device(j["id"], "air"))

        self.b_things = FakeThings("b")
        self.j_things = FakeThings("j")
        for things in (self.b_things, self.j_things):
            things.tags.update({"jill", "bradley", DELEGATED_TAG,
                                "from-bradley 👨", "from-jill 👩🏻‍🦰"})

        self.b_hub = FlakyHub(DirectHubClient(self.ledger, pb, lease_seconds=0.2))
        self.j_hub = FlakyHub(DirectHubClient(self.ledger, pj, lease_seconds=0.2))
        self.b_writer = FakeWriter(self.b_things)
        self.j_writer = FakeWriter(self.j_things)
        self.b_spoke = self._spoke(self.b_things, self.b_writer, self.b_hub,
                                   {"jill": ["jill"]}, "b-state")
        self.j_spoke = self._spoke(self.j_things, self.j_writer, self.j_hub,
                                   {"bradley": ["bradley"]}, "j-state")

    def _spoke(self, things, writer, hub, triggers, name):
        return SpokeCore(
            reader=FakeReader(things), writer=writer, hub=hub,
            state=SpokeState(os.path.join(self.tmp.name, f"{name}.sqlite")),
            trigger_tags=triggers,
            correlate_timeout=1.0, correlate_interval=0.01)

    def tearDown(self):
        self.ledger.close()
        self.tmp.cleanup()

    def settle(self, rounds=4):
        import time
        for _ in range(rounds):
            time.sleep(0.25)  # let expired leases requeue between rounds
            self.b_spoke.tick()
            self.j_spoke.tick()


class TestOutbound(SpokeCoreTestBase):
    def test_exact_tag_match_only(self):
        # `Jillian 👩🏻‍🦰` must NOT trigger — the 2026-07-11 review amendment
        self.b_things.add("about jill", tags=["Jillian 👩🏻‍🦰"])
        tagged = self.b_things.add("for jill", tags=["jill"])
        self.settle(1)
        self.assertEqual(self.j_things.count_titled("for jill"), 1)
        self.assertEqual(self.j_things.count_titled("about jill"), 0)
        self.assertTrue(self.b_spoke.state.known_sent(tagged))

    def test_case_insensitive_exact_match(self):
        self.b_things.add("shout", tags=["JILL"])
        self.settle(1)
        self.assertEqual(self.j_things.count_titled("shout"), 1)

    def test_repeating_todo_refused_loudly_and_left_tagged(self):
        u = self.b_things.add("water plants", tags=["jill"], is_repeating=True)
        self.settle(1)
        self.assertEqual(self.j_things.count_titled("water plants"), 0)
        self.assertFalse(self.b_spoke.state.known_sent(u))
        self.assertIn("jill", self.b_things.todos[u]["tags"])  # visible, not silent

    def test_oversized_checklist_refused(self):
        self.b_things.add("mega", tags=["jill"], checklist=[str(i) for i in range(101)])
        self.settle(1)
        self.assertEqual(self.j_things.count_titled("mega"), 0)

    def test_sent_cache_suppresses_repush_but_hub_dedupes_anyway(self):
        self.b_things.add("once", tags=["jill"])
        self.settle(2)
        self.assertEqual(self.j_things.count_titled("once"), 1)

    def test_no_control_tags_cross_the_wire(self):
        self.b_things.add("clean", tags=["jill", "home 🏠"])
        self.settle(1)
        [todo] = [t for t in self.j_things.todos.values() if t["title"] == "clean"]
        # only the provenance tag arrives; trigger + payload tags dropped (v1)
        self.assertEqual(todo["tags"], ["from-bradley 👨"])


class TestInboundCrashSafety(SpokeCoreTestBase):
    def test_create_lands_in_inbox_with_provenance(self):
        self.b_things.add("errand", tags=["jill"], notes="details",
                          checklist=["x", "y"])
        self.settle(1)
        [todo] = [t for t in self.j_things.todos.values() if t["title"] == "errand"]
        self.assertEqual(todo["notes"], "details")
        self.assertEqual(todo["checklist"], ["x", "y"])
        self.assertIsNone(todo["when"])  # D3: real Inbox, no forced 'today'

    def test_crash_after_fire_rejournals_no_duplicate(self):
        self.b_things.add("fragile", tags=["jill"])
        self.b_spoke.tick()          # push
        self.j_writer.crash_next_create = True
        self.j_spoke.tick()          # fires, "crashes" before ack
        self.settle(3)               # restart-equivalent: re-correlate, re-ack
        self.assertEqual(self.j_things.count_titled("fragile"), 1)  # NOT 2
        self.assertEqual(self.j_writer.creates, 1)  # never re-fired

    def test_lost_ack_redelivery_reacks_same_uuid(self):
        self.b_things.add("flaky", tags=["jill"])
        self.b_spoke.tick()
        self.j_hub.drop_next.add("ack")  # ack succeeds hub-side, response lost
        self.j_spoke.tick()
        self.settle(3)
        self.assertEqual(self.j_things.count_titled("flaky"), 1)
        self.assertEqual(self.j_writer.creates, 1)


class TestRoundTrip(SpokeCoreTestBase):
    def test_sender_completes_at_send_not_at_recipient_completion(self):
        # D2 (2026-07-11): delegating IS the action — sender's copy is done
        # the moment delivery is confirmed, not when the recipient finishes.
        src = self.b_things.add("deliver", tags=["jill"])
        self.settle(2)
        self.assertIn(DELEGATED_TAG, self.b_things.todos[src]["tags"])
        self.assertNotIn("jill", self.b_things.todos[src]["tags"])
        self.assertEqual(self.b_things.todos[src]["status"], "completed")
        # jill's copy is still open — completing sender's copy does NOT
        # cascade to the recipient
        [dst] = [u for u, t in self.j_things.todos.items() if t["title"] == "deliver"]
        self.assertEqual(self.j_things.todos[dst]["status"], "open")
        # jill completes her copy for real; transfer resolves, watchlist clears
        self.j_things.complete(dst)
        self.settle(3)
        self.assertEqual(self.b_things.todos[src]["status"], "completed")  # unchanged
        self.assertEqual(self.ledger.watchlist(
            self.b_hub.inner.principal), [])

    def test_recipient_trash_does_not_uncomplete_sender_copy(self):
        src = self.b_things.add("unwanted", tags=["jill"])
        self.settle(2)
        self.assertEqual(self.b_things.todos[src]["status"], "completed")  # D2
        [dst] = [u for u, t in self.j_things.todos.items() if t["title"] == "unwanted"]
        self.j_things.trash(dst)
        self.settle(3)
        self.assertTrue(self.j_things.todos[dst]["trashed"])  # recipient's own action stands
        self.assertEqual(self.b_things.todos[src]["status"], "completed")  # sender NOT downgraded

    def test_sender_cancel_after_auto_complete_does_not_cascade(self):
        # Old "sender revocation" behavior (cancel your still-open delegated
        # copy to pull it back) has no window anymore under D2 — the sender's
        # copy is already completed by the time this could happen. Manually
        # canceling it afterward is a no-op from the sync system's view: the
        # retagged sender-role watch entry is permanently skipped, so it must
        # never propagate to the recipient's copy.
        src = self.b_things.add("nvm", tags=["jill"])
        self.settle(2)
        self.assertEqual(self.b_things.todos[src]["status"], "completed")
        self.b_things.cancel(src)
        self.settle(3)
        [dst] = [u for u, t in self.j_things.todos.items() if t["title"] == "nvm"]
        self.assertEqual(self.j_things.todos[dst]["status"], "open")

    def test_reverse_direction_jill_to_bradley(self):
        src = self.j_things.add("pick up kids", tags=["bradley"], when="2026-07-12")
        self.settle(2)
        [dst] = [u for u, t in self.b_things.todos.items()
                 if t["title"] == "pick up kids"]
        self.assertEqual(self.b_things.todos[dst]["tags"], ["from-jill 👩🏻‍🦰"])
        self.assertEqual(self.b_things.todos[dst]["when"], "2026-07-12")  # honored
        # D2 symmetric ("either side"): jill's sender copy already completed
        self.assertEqual(self.j_things.todos[src]["status"], "completed")
        self.b_things.complete(dst)
        self.settle(3)
        self.assertEqual(self.j_things.todos[src]["status"], "completed")  # unchanged


if __name__ == "__main__":
    unittest.main()
