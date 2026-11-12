from dataclasses import dataclass


@dataclass
class Candidate:
    start: float
    last: float
    zone: str
    event_id: int | None = None


class EventGate:
    """Positive-observation spans; brief gaps tolerated, not proof of continuous use."""

    def __init__(self, minimum=10.0, gap=2.0):
        self.minimum = minimum
        self.gap = gap
        self.states = {}

    def step(self, now, observations):
        # observations maps temporary track ID to zone name.
        actions = []
        for track, state in list(self.states.items()):
            changed_zone = track in observations and observations[track] != state.zone
            if now - state.last > self.gap or changed_zone:
                if state.event_id is not None:
                    actions.append(('end', track, state))
                del self.states[track]
        for track, zone in observations.items():
            if track not in self.states:
                self.states[track] = Candidate(now, now, zone)
            state = self.states[track]
            state.last = now
            if now - state.start >= self.minimum:
                actions.append(('start' if state.event_id is None else 'update', track, state))
        return actions

    def close(self):
        actions = [('end', track, state) for track, state in self.states.items()
                   if state.event_id is not None]
        self.states.clear()
        return actions


def associate(people, phones):
    """Assign phone center to the nearest containing person, never an employee ID.

    Boxes are (x1,y1,x2,y2). Purely spatial heuristic, not hand-use detection.
    """
    matches = set()
    for phone in phones:
        px, py = (phone[0] + phone[2]) / 2, (phone[1] + phone[3]) / 2
        choices = []
        for track, box in people.items():
            x1, y1, x2, y2 = box
            if x1 <= px <= x2 and y1 <= py <= y2:
                w, h = max(x2 - x1, 1), max(y2 - y1, 1)
                distance = ((px - (x1 + x2) / 2) / w) ** 2 + ((py - (y1 + .45 * h)) / h) ** 2
                choices.append((distance, track))
        if choices:
            matches.add(min(choices)[1])
    return matches
