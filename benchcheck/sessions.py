"""Bounded local analysis sessions. Only server-observed evidence can enter a report."""
from __future__ import annotations
import copy
import hashlib
import json
import secrets
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from fastapi import HTTPException
from .models import EvidenceContext, ExperimentMetadata

LOCK = threading.RLock()
SESSIONS = {}
BUDGETS = {}
LIVE_CALLS = deque()
TTL = 3600

@dataclass
class Session:
    analysis: dict
    fingerprint: str
    created: float = field(default_factory=time.monotonic)
    sources: dict = field(default_factory=dict)
    logs: list = field(default_factory=list)

    def context(self):
        return EvidenceContext(metadata=ExperimentMetadata(**self.analysis['metadata']),
            hypothesis_ids=[h['id'] for h in self.analysis['hypotheses'] if h['triggered']],
            measured_scan_rate_v_s=self.analysis.get('scan_rate_measured'))


def create(analysis, config):
    fingerprint = hashlib.sha256((analysis['provenance']['sha256'] + json.dumps(config, sort_keys=True)).encode()).hexdigest()
    with LOCK:
        now = time.monotonic()
        for key in list(SESSIONS):
            if now - SESSIONS[key].created > TTL or len(SESSIONS) >= 64:
                del SESSIONS[key]
        for key, value in list(BUDGETS.items()):
            if now - value['created'] > TTL:
                del BUDGETS[key]
        identifier = secrets.token_urlsafe(24)
        analysis['analysis_id'] = identifier
        # Plot arrays are not needed to generate reports; keep session memory bounded.
        SESSIONS[identifier] = Session(copy.deepcopy({k:v for k,v in analysis.items() if k != 'data'}), fingerprint)
        BUDGETS.setdefault(fingerprint, {'created': now, 'queries': 0, 'extracts': 0})
        return identifier


def get(identifier):
    with LOCK:
        session = SESSIONS.get(identifier)
        if not session or time.monotonic() - session.created > TTL:
            raise HTTPException(422, 'analysis_id is missing or expired; analyze the file again.')
        return session


def consume(session, kind, maximum, live):
    with LOCK:
        budget = BUDGETS[session.fingerprint]
        if budget[kind] >= maximum:
            raise HTTPException(429, f'The {kind} budget for this analysis has been reached.')
        if live:
            now = time.monotonic()
            while LIVE_CALLS and now - LIVE_CALLS[0] > 60:
                LIVE_CALLS.popleft()
            if len(LIVE_CALLS) >= 30:
                raise HTTPException(429, 'Evidence rate limit reached; try again in a minute.')
            LIVE_CALLS.append(now)
        budget[kind] += 1


def source(session, identifier):
    value = session.sources.get(identifier)
    if value is None:
        raise HTTPException(422, 'source_id was not returned by this analysis session.')
    return copy.deepcopy(value)
