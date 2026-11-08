"""C1: fast joint router first, LLM only when the fast path is unsure."""

import time

import numpy as np

from jarvis.schema import Route


class Cascade:
    name = "C1"

    def __init__(self, fast, slow, tau: float):
        self.fast, self.slow, self.tau = fast, slow, tau

    @staticmethod
    def tau_for_rate(fast, dev_items, rate: float) -> float:
        """Confidence below which `rate` of dev requests fall (so ~rate of traffic reaches the LLM)."""
        conf = [fast.route(i.text).confidence for i in dev_items]
        return float(np.quantile(conf, rate))

    def route(self, text: str) -> Route:
        t0 = time.perf_counter()
        r = self.fast.route(text)
        if r.confidence >= self.tau and r.path != "abstain":
            return r
        s = self.slow.route(text)
        s.path = "llm"
        s.ms = (time.perf_counter() - t0) * 1000
        return s
