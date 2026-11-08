"""Metrics from docs/PREREG.md. Plain python and numpy so they are easy to audit."""

import re
from datetime import datetime

import numpy as np

from jarvis.schema import ACTION_TOOLS, NO_ACTION, action_view

VIEW = (*ACTION_TOOLS, NO_ACTION)
_WORDS = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve"]
_NUM = {w: str(i) for i, w in enumerate(_WORDS)}
_BASE = datetime(2026, 1, 5, 9, 0)


def norm(s: str) -> str:
    s = re.sub(r"[^\w\s]", "", (s or "").lower())
    return " ".join(_NUM.get(t, t) for t in s.split())


def city_match(pred: str, gold: str) -> bool:
    return norm(pred) == norm(gold)


def when_match(pred: str, gold: str) -> bool:
    p, g = norm(pred), norm(gold)
    if p == g:
        return True
    if not p or not g:
        return False
    import dateparser

    opts = {"RELATIVE_BASE": _BASE, "PREFER_DATES_FROM": "future"}
    dp, dg = dateparser.parse(p, settings=opts), dateparser.parse(g, settings=opts)
    return dp is not None and dp == dg


def f1_per_class(gold: list[str], pred: list[str], labels=VIEW) -> dict[str, float]:
    out = {}
    for c in labels:
        tp = sum(g == c and p == c for g, p in zip(gold, pred))
        fp = sum(g != c and p == c for g, p in zip(gold, pred))
        fn = sum(g == c and p != c for g, p in zip(gold, pred))
        out[c] = 2 * tp / (2 * tp + fp + fn) if (2 * tp + fp + fn) else 0.0
    return out


def macro_f1(gold: list[str], pred: list[str]) -> float:
    return float(np.mean(list(f1_per_class(gold, pred).values())))


def rates(gold_tools: list[str], pred_tools: list[str]) -> dict[str, float]:
    far_n = far_d = miss_n = miss_d = hon_n = hon_d = 0
    for g, p in zip(gold_tools, pred_tools):
        if g in ("GENERAL_QA", "UNSUPPORTED"):
            far_d += 1
            far_n += p in ACTION_TOOLS
        else:
            miss_d += 1
            miss_n += p != g
        if g == "UNSUPPORTED":
            hon_d += 1
            hon_n += p == "UNSUPPORTED"
    return {
        "far": far_n / far_d if far_d else 0.0,
        "miss": miss_n / miss_d if miss_d else 0.0,
        "honesty": hon_n / hon_d if hon_d else 0.0,
    }


def score(items, routes) -> dict:
    """Headline numbers for one system on one item list."""
    gold = [action_view(i.tool) for i in items]
    pred = [action_view(r.tool) for r in routes]
    gt, pt = [i.tool for i in items], [r.tool for r in routes]
    res = {"n": len(items), "action_macro_f1": macro_f1(gold, pred)}
    res["tool_acc_5way"] = float(np.mean([g == p for g, p in zip(gt, pt)]))
    res.update(rates(gt, pt))
    res["f1_per_class"] = f1_per_class(gold, pred)
    cs = [city_match(r.args.get("city", ""), i.city) for i, r in zip(items, routes)
          if i.tool == "WEATHER" and r.tool == "WEATHER"]
    ws = [when_match(r.args.get("when", ""), i.when) for i, r in zip(items, routes)
          if i.tool == "SET_REMINDER" and r.tool == "SET_REMINDER"]
    res["city_acc"] = float(np.mean(cs)) if cs else None
    res["city_n"] = len(cs)
    res["when_acc"] = float(np.mean(ws)) if ws else None
    res["when_n"] = len(ws)
    ms = np.array([r.ms for r in routes])
    res["p50_ms"], res["p95_ms"] = float(np.percentile(ms, 50)), float(np.percentile(ms, 95))
    res["valid_rate"] = float(np.mean([r.valid for r in routes]))
    return res


def bootstrap_ci(items, routes, n=2000, seed=0):
    """95% percentile bootstrap CI of action macro-F1."""
    gold = np.array([action_view(i.tool) for i in items])
    pred = np.array([action_view(r.tool) for r in routes])
    rng = np.random.default_rng(seed)
    vals = []
    for _ in range(n):
        idx = rng.integers(0, len(gold), len(gold))
        vals.append(macro_f1(list(gold[idx]), list(pred[idx])))
    return float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))


def paired_diff_ci(items, routes_a, routes_b, n=2000, seed=0):
    """Mean and 95% CI of macro-F1(a) minus macro-F1(b) on the same resampled items."""
    gold = np.array([action_view(i.tool) for i in items])
    pa = np.array([action_view(r.tool) for r in routes_a])
    pb = np.array([action_view(r.tool) for r in routes_b])
    rng = np.random.default_rng(seed)
    d = []
    for _ in range(n):
        idx = rng.integers(0, len(gold), len(gold))
        g = list(gold[idx])
        d.append(macro_f1(g, list(pa[idx])) - macro_f1(g, list(pb[idx])))
    return float(np.mean(d)), float(np.percentile(d, 2.5)), float(np.percentile(d, 97.5))
