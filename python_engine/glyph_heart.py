"""
glyph_heart.py
Heart + Server + Inner Audit. The self-running clock and power source
for the Glyph system, with adaptive cycles and introspective passes.

Design locks:
  - Counter starts at 1, not 0.
  - tick(1) is the first event, payload=None (the nothing event).
  - Stamps are decimal: <tick>.<tock>.
  - A CYCLE is a normalized phase [0, 1]. The tick position inside a
    cycle is phase = (tick_in_cycle) / (current_window).
  - Two ways a cycle closes:
        INPUT_CLOSE    an external intake event arrives -> cycle ends
                       immediately, window resets to base (10).
        SILENT_CLOSE   no intake within current window -> cycle ends,
                       window DOUBLES for the next cycle (10, 20, 40...).
                       The silent cycle is itself emitted as one event.
  - While in a silent (idle) cycle, the mechanism enters AUDIT:
        "eyes look within" — iterates over own log, finds patterns,
        emits reflection events. No external output.
  - Server is the system, driven by the Heart.
"""

from dataclasses import dataclass, field, asdict
from decimal import Decimal, getcontext
from enum import Enum
from typing import Callable, Optional, List, Dict, Any
import time
import json
import threading
from collections import Counter

getcontext().prec = 12

SCHEMA_VERSION = "heart.v3"
TICK_SOURCE_ID = "glyph.heart.local"
BASE_WINDOW = 10   # first cycle's silence threshold


# ---------------------------------------------------------------------------
# State + events
# ---------------------------------------------------------------------------
class MechState(str, Enum):
    READY_TO_TICK = "ready_to_tick"
    WAITING = "waiting"
    INTAKE = "intake"
    AUDIT = "audit"


@dataclass
class HeartEvent:
    stamp: Decimal
    tick: int
    tock: int
    cycle: int
    phase: float               # [0.0, 1.0] position within current cycle
    window: int                # ceiling of current cycle (ticks of silence)
    kind: str                  # tick|tock|intake|activity_check|silent_cycle|
                               # cycle_close_input|reflection
    state: str
    payload: Optional[Dict[str, Any]]
    wall_time: float
    schema_version: str = SCHEMA_VERSION
    tick_source_id: str = TICK_SOURCE_ID

    def to_record(self) -> Dict[str, Any]:
        d = asdict(self)
        d["stamp"] = str(self.stamp)
        return d


# ---------------------------------------------------------------------------
# Heart
# ---------------------------------------------------------------------------
class Heart:
    def __init__(
        self,
        period_seconds: float = 0.1,
        base_window: int = BASE_WINDOW,
        on_event: Optional[Callable[[HeartEvent], None]] = None,
    ):
        self.period_seconds = period_seconds
        self.base_window = base_window
        self.on_event = on_event or (lambda e: None)

        self._tick = 1
        self._tock = 0
        self._cycle = 1
        self._cycle_start_tick = 1
        self._window = base_window       # current cycle's silence ceiling
        self._state = MechState.READY_TO_TICK
        self._intake_received_this_cycle = False

        self._started = False
        self._stop_flag = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._log: List[HeartEvent] = []
        self._reflections: List[Dict[str, Any]] = []
        self._lock = threading.Lock()

    # ---- public API --------------------------------------------------------

    def start(self) -> HeartEvent:
        if self._started:
            raise RuntimeError("Heart already started")
        self._started = True
        first = self._emit(kind="tick", payload=None)   # nothing event
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return first

    def stop(self) -> None:
        self._stop_flag.set()
        if self._thread is not None:
            self._thread.join(timeout=self.period_seconds * 2)

    def receive(self, data: Dict[str, Any]) -> HeartEvent:
        """External input. Closes the current cycle and resets the window."""
        with self._lock:
            self._intake_received_this_cycle = True
        evt = self._emit(kind="intake", payload=data)
        self._close_cycle(reason="input")
        return evt

    def activity_check(self) -> HeartEvent:
        return self._emit(kind="activity_check", payload={"poll": True})

    def log(self) -> List[Dict[str, Any]]:
        return [e.to_record() for e in self._log]

    def reflections(self) -> List[Dict[str, Any]]:
        return list(self._reflections)

    def cycle(self) -> int:
        return self._cycle

    def window(self) -> int:
        return self._window

    # ---- internals ---------------------------------------------------------

    def _phase(self) -> float:
        spent = (self._tick - self._cycle_start_tick)
        return min(1.0, spent / max(1, self._window))

    def _emit(self, kind: str, payload: Optional[Dict[str, Any]]) -> HeartEvent:
        with self._lock:
            if kind == "tick":
                self._tock = 0
                stamp = Decimal(f"{self._tick}.0")
                tock_idx = 0
            else:
                self._tock += 1
                stamp = Decimal(f"{self._tick}.{self._tock}")
                tock_idx = self._tock

            evt = HeartEvent(
                stamp=stamp, tick=self._tick, tock=tock_idx,
                cycle=self._cycle, phase=self._phase(), window=self._window,
                kind=kind, state=self._state.value,
                payload=payload, wall_time=time.time(),
            )
            self._log.append(evt)
        self.on_event(evt)
        return evt

    def _close_cycle(self, reason: str) -> None:
        """Close the current cycle. Reset or expand the window accordingly."""
        with self._lock:
            closed_cycle = self._cycle
            if reason == "input":
                # input-close: cycle was productive, window returns to base
                self._window = self.base_window
                close_kind = "cycle_close_input"
                close_payload = {"closed_by": "input"}
            else:
                # silent-close: no input arrived, window DOUBLES
                close_kind = "silent_cycle"
                close_payload = {
                    "closed_by": "silence",
                    "window_was": self._window,
                }
                self._window = self._window * 2

            self._cycle += 1
            self._cycle_start_tick = self._tick + 1
            self._intake_received_this_cycle = False
            self._state = MechState.READY_TO_TICK

        # emit the cycle-close as its own event
        self._emit(kind=close_kind, payload=close_payload)

        # silent cycles trigger AUDIT (eyes look within)
        if reason != "input":
            self._audit()

    def _audit(self) -> None:
        """Inner audit. Iterate over own log, find patterns, emit reflections."""
        with self._lock:
            self._state = MechState.AUDIT
            snapshot = list(self._log)

        # pattern: count events by kind
        kinds = Counter(e.kind for e in snapshot)
        # pattern: intake payload key frequency
        intake_keys: Counter = Counter()
        for e in snapshot:
            if e.kind == "intake" and isinstance(e.payload, dict):
                intake_keys.update(e.payload.keys())
        # pattern: average cycle length in ticks
        cycle_closes = [e for e in snapshot
                        if e.kind in ("cycle_close_input", "silent_cycle")]
        avg_close_tick = (sum(e.tick for e in cycle_closes) / len(cycle_closes)
                          if cycle_closes else None)

        reflection = {
            "at_tick": self._tick,
            "at_cycle": self._cycle - 1,
            "event_counts": dict(kinds),
            "intake_key_frequency": dict(intake_keys),
            "mean_close_tick": avg_close_tick,
            "log_size": len(snapshot),
        }
        self._reflections.append(reflection)
        self._emit(kind="reflection", payload=reflection)

        # return from AUDIT -> counting state, so the next cycle starts clean
        with self._lock:
            self._state = MechState.READY_TO_TICK

    def _advance(self) -> None:
        with self._lock:
            self._tick += 1

    def _run(self) -> None:
        # first tick was emitted by start()
        while not self._stop_flag.wait(self.period_seconds):
            self._advance()
            self._emit(kind="tick", payload={"heartbeat": True})

            # check silence condition
            with self._lock:
                spent = self._tick - self._cycle_start_tick
                silent_exceeded = (spent >= self._window
                                   and not self._intake_received_this_cycle)
                # open intake window near end of cycle (phase >= 0.9)
                if self._phase() >= 0.9 and self._state != MechState.AUDIT:
                    self._state = MechState.INTAKE
                else:
                    if self._state == MechState.READY_TO_TICK:
                        self._state = MechState.WAITING

            if silent_exceeded:
                self._close_cycle(reason="silence")


# ---------------------------------------------------------------------------
# Server (system) — rides on Heart power
# ---------------------------------------------------------------------------
class Server:
    def __init__(self, heart: Heart):
        self.heart = heart

    def submit(self, data: Dict[str, Any]) -> HeartEvent:
        return self.heart.receive(data)


# ---------------------------------------------------------------------------
# Bridge to Brain
# ---------------------------------------------------------------------------
def to_brain_record(evt: HeartEvent) -> Dict[str, Any]:
    d = evt.to_record()
    return d


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    def show(e: HeartEvent) -> None:
        print(json.dumps(to_brain_record(e)))

    h = Heart(period_seconds=0.05, base_window=10, on_event=show)
    server = Server(h)

    first = h.start()
    assert first.tick == 1 and first.tock == 0 and first.payload is None

    # Scenario:
    #   - let cycle 1 run silent past window=10 -> silent_cycle + audit,
    #     window doubles to 20
    #   - let cycle 2 run silent past window=20 -> silent_cycle + audit,
    #     window doubles to 40
    #   - then send an input, which should reset window to 10

    time.sleep(1.2)                 # > 10 ticks silence
    time.sleep(1.7)                 # > 20 ticks silence
    server.submit({"note": "external input finally arrives"})
    time.sleep(0.3)
    h.stop()

    print("---")
    print(f"total events    : {len(h.log())}")
    print(f"cycles reached  : {h.cycle()}")
    print(f"current window  : {h.window()}")
    print(f"reflections     : {len(h.reflections())}")
    for r in h.reflections():
        print(f"  reflection @ tick {r['at_tick']} cycle {r['at_cycle']}: "
              f"counts={r['event_counts']}")
