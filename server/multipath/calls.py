"""Fail-closed call policy and state machine, independent of carrier AKA.

This module controls calls, not SIP signalling or RTP. Asterisk owns SIP/media.
Evidence is supplied by a trusted provisioning operator, never an app request.
"""
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_CEILING
from enum import Enum
import re
import threading
import time
import uuid


class Route(str, Enum):
    INTERNAL = "sip_internal"
    CELLULAR = "cellular_voice"
    USB_USIM = "external_usim"
    CARRIER = "carrier_wifi"


class State(str, Enum):
    DIALING = "dialing"
    RINGING = "ringing"
    ACTIVE = "active"
    ENDED = "ended"
    FAILED = "failed"


@dataclass(frozen=True)
class VoiceEvidence:
    gateway_id: str
    online: bool = False
    sim_present: bool = False
    registered: bool = False
    voice_commands: bool = False
    audio_interface: bool = False
    inbound_verified: bool = False
    outbound_verified: bool = False
    two_way_audio_verified: bool = False
    firmware: str = ""
    modem_model: str = ""
    verified_at: float = 0

    def available(self, now: float) -> bool:
        return (self.online and self.sim_present and self.registered
                and self.voice_commands and self.audio_interface
                and self.inbound_verified and self.outbound_verified
                and self.two_way_audio_verified and 0 <= now-self.verified_at <= 300)


@dataclass(frozen=True)
class Policy:
    extensions: frozenset[str]
    cellular_allowed: bool = False
    destinations: frozenset[str] = frozenset()
    max_seconds: int = 300
    daily_budget: Decimal = Decimal("0")
    rate_per_minute: Decimal = Decimal("0")
    max_concurrent: int = 1

    def __post_init__(self):
        if (not 1 <= self.max_seconds <= 3600 or not 1 <= self.max_concurrent <= 4
                or not self.daily_budget.is_finite() or self.daily_budget < 0
                or not self.rate_per_minute.is_finite() or self.rate_per_minute < 0):
            raise ValueError("Invalid call limits")
        if any(not re.fullmatch(r"[1-9][0-9]{3,5}", e) for e in self.extensions):
            raise ValueError("Invalid internal extension")
        if any(not re.fullmatch(r"\+[1-9][0-9]{7,14}", d) for d in self.destinations):
            raise ValueError("Destinations must be explicit E.164 allowlist entries")


@dataclass
class Call:
    id: str
    owner: str
    target: str
    route: Route
    gateway: str | None
    started: float
    deadline: float
    reservation: Decimal
    budget_day: int
    rate: Decimal
    state: State = State.DIALING
    answered: float | None = None
    ended: float | None = None
    cost: Decimal = Decimal("0")
    failure: str | None = None


class Calls:
    def __init__(self, clock=time.time):
        self.clock = clock
        self.lock = threading.RLock()
        self.policies: dict[str, Policy] = {}
        self.gateways: dict[str, VoiceEvidence] = {}
        self.calls: dict[str, Call] = {}
        self.spent: dict[tuple[str, int], Decimal] = {}

    def start(self, owner: str, target: str, route: Route, gateway: str | None = None) -> Call:
        with self.lock:
            now = self.clock()
            policy = self.policies.get(owner)
            if policy is None:
                raise PermissionError("User has no call permission")
            if route not in (Route.INTERNAL, Route.CELLULAR):
                raise PermissionError("Carrier routes require independent verified authorization")
            active = [c for c in self.calls.values() if c.state not in (State.ENDED, State.FAILED)]
            if sum(c.owner == owner for c in active) >= policy.max_concurrent:
                raise PermissionError("Concurrent call limit")
            reservation = Decimal("0")
            if route == Route.INTERNAL:
                if target not in policy.extensions:
                    raise PermissionError("Internal destination not allowed")
                gateway = None
            else:
                evidence = self.gateways.get(gateway)
                if not policy.cellular_allowed or target not in policy.destinations:
                    raise PermissionError("Cellular destination not allowed")
                if evidence is None or not evidence.available(now):
                    raise PermissionError("Cellular voice and audio evidence missing or stale")
                if any(c.gateway == gateway for c in active):
                    raise PermissionError("Modem busy")
                # Reserve worst-case rounded-up minutes, before opening a channel.
                reservation = (Decimal(policy.max_seconds)/60).to_integral_value(rounding=ROUND_CEILING) * policy.rate_per_minute
                if reservation <= 0:
                    raise PermissionError("Explicit positive cost estimate required")
                held = sum((c.reservation for c in active if c.owner == owner and c.budget_day == int(now // 86400)), Decimal("0"))
                if self.spent.get((owner, int(now//86400)), Decimal("0")) + held + reservation > policy.daily_budget:
                    raise PermissionError("Daily cost limit")
            call = Call(uuid.uuid4().hex, owner, target, route, gateway, now,
                        now+policy.max_seconds, reservation, int(now//86400), policy.rate_per_minute)
            self.calls[call.id] = call
            return call

    def transition(self, call_id: str, state: State, failure: str | None = None) -> Call:
        with self.lock:
            call = self.calls[call_id]
            allowed = {
                State.DIALING: {State.RINGING, State.ACTIVE, State.ENDED, State.FAILED},
                State.RINGING: {State.ACTIVE, State.ENDED, State.FAILED},
                State.ACTIVE: {State.ENDED, State.FAILED},
                State.ENDED: set(), State.FAILED: set(),
            }
            if state == call.state:
                return call
            if state not in allowed[call.state]:
                raise ValueError("Invalid call transition")
            now = self.clock()
            if state == State.ACTIVE:
                call.answered = now
            if state in (State.ENDED, State.FAILED):
                call.ended = now
                call.failure = failure
                if call.answered is not None and call.route == Route.CELLULAR:
                    minutes = (Decimal(str(max(0, min(now, call.deadline)-call.answered)))/60).to_integral_value(rounding=ROUND_CEILING)
                    call.cost = min(call.reservation, minutes*call.rate)
                    key = (call.owner, call.budget_day)
                    self.spent[key] = self.spent.get(key, Decimal("0"))+call.cost
                call.reservation = Decimal("0")
            call.state = state
            return call

    def terminate_due(self) -> list[str]:
        """Caller must hang up returned PBX channels; state change is not audio teardown."""
        with self.lock:
            ids = []
            now = self.clock()
            for c in list(self.calls.values()):
                if c.state in (State.ENDED, State.FAILED):
                    continue
                evidence = self.gateways.get(c.gateway)
                reason = ("duration_limit" if now >= c.deadline else
                          "gateway_unavailable" if c.route == Route.CELLULAR and
                          (evidence is None or not evidence.available(now)) else None)
                if reason:
                    self.transition(c.id, State.FAILED, reason)
                    ids.append(c.id)
            return ids
