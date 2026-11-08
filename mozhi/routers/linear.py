"""M1: TF-IDF + logistic regression on MASSIVE intents. Intent only; arguments come from the
regexes in R0. Trained on demand (a few seconds), nothing is persisted."""

import numpy as np
from scipy.sparse import hstack
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression

from jarvis.bench import data
from jarvis.bench.metrics import macro_f1, rates
from jarvis.routers.rules import CITY, STOP_CITY, WHEN
from jarvis.schema import ACTION_TOOLS, Route, action_view

_CACHE = {}


class LinearRouter:
    name = "M1"

    @classmethod
    def load(cls):
        if "m" not in _CACHE:
            _CACHE["m"] = cls()
        return _CACHE["m"]

    def __init__(self):
        tr, dev = data.load("train"), data.load("dev")
        self.w = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, min_df=1)
        self.c = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), sublinear_tf=True, min_df=2)
        X = hstack([self.w.fit_transform([i.text for i in tr]), self.c.fit_transform([i.text for i in tr])])
        self.clf = LogisticRegression(C=20, max_iter=2000).fit(X, [i.intent for i in tr])
        self.tool_of = {c: data.TOOL_OF_INTENT.get(c, "UNSUPPORTED") for c in self.clf.classes_}
        self.tools = sorted(set(self.tool_of.values()))
        self.M = np.zeros((len(self.clf.classes_), len(self.tools)))
        for i, c in enumerate(self.clf.classes_):
            self.M[i, self.tools.index(self.tool_of[c])] = 1
        self.threshold = self._tune(dev)

    def _tp(self, texts):
        X = hstack([self.w.transform(texts), self.c.transform(texts)])
        return self.clf.predict_proba(X) @ self.M

    def _tune(self, dev):
        tp = self._tp([i.text for i in dev])
        gold = [i.tool for i in dev]
        best, bf = 0.5, -1.0
        for th in np.arange(0.3, 0.99, 0.01):
            pred = []
            for row in tp:
                k = int(row.argmax())
                t = self.tools[k]
                pred.append("UNSUPPORTED" if t in ACTION_TOOLS and row[k] < th else t)
            f = macro_f1([action_view(g) for g in gold], [action_view(p) for p in pred])
            if rates(gold, pred)["far"] <= 0.015 and f > bf:
                best, bf = float(th), f
        return best

    def route(self, text: str) -> Route:
        row = self._tp([text])[0]
        k = int(row.argmax())
        tool, conf = self.tools[k], float(row[k])
        if tool in ACTION_TOOLS and conf < self.threshold:
            return Route("UNSUPPORTED", confidence=conf, path="abstain")
        t = text.lower()
        args = {}
        if tool == "WEATHER":
            m = CITY.search(t)
            args["city"] = m.group(1).strip() if m and m.group(1).split()[0] not in STOP_CITY else ""
        elif tool == "SET_REMINDER":
            args["when"] = " ".join(WHEN.findall(t))
        return Route(tool, args, conf, path="fast")
