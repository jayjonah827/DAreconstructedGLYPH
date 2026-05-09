"""
glyph_spine.py
Spine = the convergence layer. Links Heart (top-down) with Spark (bottom-up)
over a memory substrate (a source file — your Cursor code, or any text).

Architecture:
  Heart  (from glyph_heart.py)
    - starts at tick 1
    - reads the substrate from the TOP downward, one line per tick
    - emits event-records

  Spark  (new, this file)
    - starts at stamp 0
    - reads the substrate from the BOTTOM upward, one line per tick
    - emits event-records in negative-decimal space (-0.1, -0.2, -1.0, ...)

  Spine  (new, this file)
    - holds the substrate (memory)
    - drives Heart and Spark in alternation
    - detects convergence (when their read positions cross)
    - after convergence, flips each scanner to read the OTHER's output log
      -> events of events
    - keeps oscillating: Heart and Spark reverse direction and repeat
    - never stuck: always moving up or down, but not in the same direction
      as the last pass

Stamp schema:
    Heart events :  +N.M   (positive, up from 1)
    Spark events :  -N.M   (negative, down from 0)
    Meta events  :  M.N    (issued by Spine at convergence, prefixed "meta")
"""

from dataclasses import dataclass, asdict
from decimal import Decimal, getcontext
from enum import Enum
from typing import List, Dict, Any, Optional, Callable
import time
import json
from collections import Counter

getcontext().prec = 12

SCHEMA_VERSION = "spine.v1"


# ---------------------------------------------------------------------------
# Shared event type (compatible with Heart records)
# ---------------------------------------------------------------------------
@dataclass
class SpineEvent:
    stamp: Decimal
    actor: str              # "heart" | "spark" | "meta"
    position: int           # line index read from substrate
    direction: str          # "down" | "up" | "meta"
    pass_number: int        # which sweep we're on
    kind: str               # "read" | "convergence" | "reflection" | "spark_seed" | "nothing"
    payload: Optional[Dict[str, Any]]
    wall_time: float
    schema_version: str = SCHEMA_VERSION

    def to_record(self) -> Dict[str, Any]:
        d = asdict(self)
        d["stamp"] = str(self.stamp)
        return d


# ---------------------------------------------------------------------------
# Spark — bottom-up counterpart to Heart
# ---------------------------------------------------------------------------
class Spark:
    """
    Starts at stamp 0. Reads upward from the bottom of the substrate.
    Emits events in negative-decimal space.
    """
    def __init__(self):
        self._tick = 0          # LOCK: Spark starts at 0 (Heart starts at 1)
        self._tock = 0

    def seed(self, substrate_len: int) -> SpineEvent:
        """The 'spark' — the bottom-up origin event. Nothing read yet."""
        stamp = Decimal("0.0")
        return SpineEvent(
            stamp=stamp, actor="spark", position=substrate_len,
            direction="up", pass_number=1, kind="spark_seed",
            payload=None, wall_time=time.time(),
        )

    def advance(self, substrate_len: int, pass_number: int) -> SpineEvent:
        self._tick += 1
        self._tock = 0
        stamp = Decimal(f"-{self._tick}.0")
        position = substrate_len - self._tick   # walking UP
        return SpineEvent(
            stamp=stamp, actor="spark", position=position,
            direction="up", pass_number=pass_number, kind="read",
            payload=None, wall_time=time.time(),
        )

    def sub(self, pass_number: int, payload: Dict[str, Any]) -> SpineEvent:
        self._tock += 1
        stamp = Decimal(f"-{self._tick}.{self._tock}")
        return SpineEvent(
            stamp=stamp, actor="spark", position=-1,
            direction="up", pass_number=pass_number, kind="read",
            payload=payload, wall_time=time.time(),
        )

    def position(self) -> int:
        return self._tick


# ---------------------------------------------------------------------------
# Heart (simplified, spine-aware version — counts lines instead of wall time)
# ---------------------------------------------------------------------------
class HeartReader:
    def __init__(self):
        self._tick = 1          # LOCK: starts at 1
        self._tock = 0

    def first(self) -> SpineEvent:
        """First tick. The 'nothing' event. No line read yet."""
        return SpineEvent(
            stamp=Decimal("1.0"), actor="heart", position=0,
            direction="down", pass_number=1, kind="nothing",
            payload=None, wall_time=time.time(),
        )

    def advance(self, pass_number: int) -> SpineEvent:
        self._tick += 1
        self._tock = 0
        stamp = Decimal(f"{self._tick}.0")
        position = self._tick - 1   # walking DOWN (0-indexed)
        return SpineEvent(
            stamp=stamp, actor="heart", position=position,
            direction="down", pass_number=pass_number, kind="read",
            payload=None, wall_time=time.time(),
        )

    def sub(self, pass_number: int, payload: Dict[str, Any]) -> SpineEvent:
        self._tock += 1
        stamp = Decimal(f"{self._tick}.{self._tock}")
        return SpineEvent(
            stamp=stamp, actor="heart", position=-1,
            direction="down", pass_number=pass_number, kind="read",
            payload=payload, wall_time=time.time(),
        )

    def position(self) -> int:
        return self._tick - 1   # 0-indexed line just read


# ---------------------------------------------------------------------------
# Spine — the coordinator
# ---------------------------------------------------------------------------
class Spine:
    def __init__(self, substrate: List[str],
                 on_event: Optional[Callable[[SpineEvent], None]] = None):
        self.substrate = substrate
        self.on_event = on_event or (lambda e: None)
        self.log: List[SpineEvent] = []
        self.heart = HeartReader()
        self.spark = Spark()
        self._pass = 1

    def _emit(self, evt: SpineEvent) -> SpineEvent:
        self.log.append(evt)
        self.on_event(evt)
        return evt

    def run_convergent_pass(self) -> SpineEvent:
        """
        One full pass: Heart descends from top, Spark ascends from bottom,
        each step alternating. Stops when their positions cross.
        Emits a 'convergence' meta-event at the meeting point.
        """
        n = len(self.substrate)

        # origin events
        self._emit(self.heart.first())
        self._emit(self.spark.seed(n))

        # alternate steps until they meet
        while True:
            # heart step
            h_evt = self.heart.advance(self._pass)
            if h_evt.position < n:
                line = self.substrate[h_evt.position]
                h_evt = self.heart.sub(self._pass, {"line": line, "idx": h_evt.position})
            self._emit(h_evt)

            # spark step
            s_evt = self.spark.advance(n, self._pass)
            if 0 <= s_evt.position < n:
                line = self.substrate[s_evt.position]
                s_evt = self.spark.sub(self._pass, {"line": line, "idx": s_evt.position})
            self._emit(s_evt)

            # convergence check — have their reading fronts crossed?
            heart_front = self.heart.position()
            spark_front = n - 1 - self.spark.position()
            if heart_front >= spark_front:
                # they met (or crossed)
                meta = SpineEvent(
                    stamp=Decimal(f"{self._pass}.5"),
                    actor="meta",
                    position=(heart_front + spark_front) // 2,
                    direction="meta",
                    pass_number=self._pass,
                    kind="convergence",
                    payload={
                        "heart_front": heart_front,
                        "spark_front": spark_front,
                        "midpoint": (heart_front + spark_front) // 2,
                        "events_this_pass": len([e for e in self.log
                                                 if e.pass_number == self._pass]),
                    },
                    wall_time=time.time(),
                )
                self._emit(meta)
                return meta

    def run_reflection_pass(self) -> SpineEvent:
        """
        Events of events. Each scanner now reads the OTHER scanner's output
        from the prior pass instead of the substrate. Patterns about patterns.
        """
        prior_heart = [e for e in self.log
                       if e.actor == "heart" and e.pass_number == self._pass]
        prior_spark = [e for e in self.log
                       if e.actor == "spark" and e.pass_number == self._pass]

        self._pass += 1
        kinds_h = Counter(e.kind for e in prior_heart)
        kinds_s = Counter(e.kind for e in prior_spark)

        reflection = SpineEvent(
            stamp=Decimal(f"{self._pass}.0"),
            actor="meta", position=-1, direction="meta",
            pass_number=self._pass, kind="reflection",
            payload={
                "heart_reads": sum(kinds_h.values()),
                "spark_reads": sum(kinds_s.values()),
                "heart_kinds": dict(kinds_h),
                "spark_kinds": dict(kinds_s),
                "comment": "heart looked at spark's log; spark looked at heart's log",
            },
            wall_time=time.time(),
        )
        return self._emit(reflection)

    def oscillate(self, passes: int = 2) -> None:
        """
        Run alternating convergent passes and reflection passes.
        Always moving. Never stuck up or down.
        """
        for _ in range(passes):
            self.run_convergent_pass()
            self.run_reflection_pass()


# ---------------------------------------------------------------------------
# Wire to your Cursor code — load a file as the memory substrate
# ---------------------------------------------------------------------------
def load_substrate(path: str) -> List[str]:
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return [line.rstrip("\n") for line in f.readlines()]


# ---------------------------------------------------------------------------
# Demo — point it at glyph_heart.py itself as the memory substrate
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import os, sys

    # Use glyph_heart.py as the memory (the "ugly but mine" substrate)
    here = os.path.dirname(os.path.abspath(__file__))
    target = os.path.join(here, "glyph_heart.py")
    if not os.path.exists(target):
        print(f"substrate not found: {target}")
        sys.exit(1)

    substrate = load_substrate(target)
    print(f"substrate loaded: {len(substrate)} lines")

    sample_log: List[SpineEvent] = []
    def cap(e: SpineEvent) -> None:
        sample_log.append(e)

    spine = Spine(substrate, on_event=cap)
    spine.oscillate(passes=2)

    # Summarize
    convergences = [e for e in spine.log if e.kind == "convergence"]
    reflections = [e for e in spine.log if e.kind == "reflection"]

    print(f"total events: {len(spine.log)}")
    print(f"passes run  : {spine._pass}")
    print(f"convergences: {len(convergences)}")
    print(f"reflections : {len(reflections)}")

    for c in convergences:
        p = c.payload
        print(f"  pass {c.pass_number} convergence @ line {p['midpoint']} "
              f"(heart={p['heart_front']}, spark={p['spark_front']}, "
              f"events={p['events_this_pass']})")

    for r in reflections:
        p = r.payload
        print(f"  pass {r.pass_number} reflection: "
              f"heart_reads={p['heart_reads']}, spark_reads={p['spark_reads']}")

    # show the first nothing, the spark seed, and the first convergence
    print("\nsample events:")
    for e in spine.log[:3]:
        print(" ", json.dumps(e.to_record())[:160])
    print("  ...")
    if convergences:
        print(" ", json.dumps(convergences[0].to_record())[:200])
