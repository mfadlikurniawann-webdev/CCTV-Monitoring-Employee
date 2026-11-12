import tempfile
import unittest
from pathlib import Path

from app.events import EventGate, associate
from app.store import Store


class GateTests(unittest.TestCase):
    def test_minimum_duration_and_end(self):
        gate = EventGate(3, 2)
        self.assertEqual(gate.step(0, {1:'A'}), [])
        self.assertEqual(gate.step(1, {1:'A'}), [])
        self.assertEqual(gate.step(2, {1:'A'}), [])
        action, track, state = gate.step(3, {1:'A'})[0]
        self.assertEqual((action, track), ('start',1))
        state.event_id = 42
        self.assertEqual(gate.step(4, {1:'A'})[0][0], 'update')
        self.assertEqual(gate.step(5, {}), [])
        ended = gate.step(7, {})[0]
        self.assertEqual(ended[0], 'end')
        self.assertEqual(ended[2].last, 4)

    def test_discontinuous_observations_do_not_accumulate(self):
        gate = EventGate(3, 1)
        gate.step(0, {1:'A'})
        self.assertEqual(gate.step(5, {1:'A'}), [])
        self.assertEqual(gate.states[1].start, 5)

    def test_short_candidate_never_logged(self):
        gate = EventGate(10, 2)
        gate.step(0, {1:'A'})
        self.assertEqual(gate.step(3, {}), [])
        self.assertEqual(gate.close(), [])

    def test_zone_change_resets_candidate(self):
        gate = EventGate(1, 2)
        gate.step(0, {1:'A'})
        gate.step(1, {1:'A'})[0][2].event_id = 7
        actions = gate.step(2, {1:'B'})
        self.assertEqual(actions[0][0], 'end')
        self.assertEqual(gate.states[1].zone, 'B')
        self.assertIsNone(gate.states[1].event_id)

    def test_close_clears_state(self):
        gate = EventGate(1, 2)
        gate.step(0, {1:'A'})
        gate.step(1, {1:'A'})[0][2].event_id = 1
        self.assertEqual(len(gate.close()), 1)
        self.assertEqual(gate.close(), [])

    def test_phone_association_is_unique(self):
        people = {1:[0,0,100,100], 2:[50,0,150,100]}
        matches = associate(people, [[70,40,80,50]])
        self.assertEqual(len(matches), 1)

    def test_phone_outside_person_ignored(self):
        self.assertEqual(associate({1:[0,0,10,10]}, [[20,20,25,25]]), set())


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / 'test.sqlite3')

    def tearDown(self):
        self.temp.cleanup()

    def test_create_update_review(self):
        gate = EventGate(1, 2)
        gate.step(0, {3:'A'})
        state = gate.step(1, {3:'A'})[0][2]
        event_id = self.store.start('camera', 3, state)
        state.last = 4
        self.store.update(event_id, state, 'ended')
        self.assertTrue(self.store.review(event_id, 'false_positive'))
        event = self.store.list()[0]
        self.assertEqual(event['duration'], 4)
        self.assertEqual(event['review'], 'false_positive')
        self.assertFalse(self.store.review(999, 'pending'))

    def test_restart_marks_interrupted(self):
        from app.events import Candidate
        self.store.start('camera', 1, Candidate(0, 10, 'A'))
        Store(self.store.path)
        self.assertEqual(self.store.list()[0]['status'], 'interrupted')

    def test_retention_deletes_old_snapshots(self):
        from app.events import Candidate
        folder = Path(self.temp.name)
        snapshot = folder / 'old.jpg'
        snapshot.write_bytes(b'test')
        self.store.start('camera', 1, Candidate(0,10,'A'), 'old.jpg')
        with self.store.connect() as con:
            con.execute("UPDATE events SET recorded_at='2000-01-01T00:00:00+00:00'")
        self.store.purge(7, folder)
        self.assertEqual(self.store.list(), [])
        self.assertFalse(snapshot.exists())


if __name__ == '__main__':
    unittest.main()
