from mozhi.bench import data, metrics
from mozhi.schema import Route


def test_mapping_and_slots():
    items = data.load("test")
    assert {i.tool for i in items} == {
        "WEATHER", "SET_REMINDER", "SAVE_NOTE", "GENERAL_QA", "UNSUPPORTED"}
    assert all(i.intent != "general_quirky" for i in items)
    assert any(i.city for i in items if i.tool == "WEATHER")
    assert all(not i.city for i in items if i.tool != "WEATHER")


def test_subset_is_deterministic():
    items = data.load("test")
    assert [i.id for i in data.llm_subset(items)] == [i.id for i in data.llm_subset(items)]


def test_when_match_number_words():
    assert metrics.when_match("5 am", "five am")
    assert not metrics.when_match("", "five am")
    assert metrics.when_match("", "")


def test_rates_and_f1():
    gold = ["WEATHER", "UNSUPPORTED", "GENERAL_QA", "SET_REMINDER"]
    pred = ["WEATHER", "SET_REMINDER", "GENERAL_QA", "SET_REMINDER"]
    r = metrics.rates(gold, pred)
    assert r["far"] == 0.5 and r["miss"] == 0.0 and r["honesty"] == 0.0
    items = [data.Item(str(i), "", "", g, "test") for i, g in enumerate(gold)]
    routes = [Route(p) for p in pred]
    assert 0 < metrics.score(items, routes)["action_macro_f1"] < 1
