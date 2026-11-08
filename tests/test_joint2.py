import pytest

from mozhi.routers.joint2 import MODEL_DIR, JointRouter2, clean, language

pytestmark = pytest.mark.skipif(not (MODEL_DIR / "model.int8.onnx").exists(), reason="J2 model is not shipped")


def test_script_aware_clean_keeps_native_text():
    assert clean("நாளை மழை", "ta") == ["நாளை", "மழை"]
    assert clean("നാളെ മഴ", "ml") == ["നാളെ", "മഴ"]
    assert language("சென்னையில் மழை") == "ta"
    assert language("കൊച്ചിയിൽ മഴ") == "ml"


def test_native_digits_and_english_small_numbers():
    assert clean("௫ மணிக்கு", "ta") == ["5", "மணிக்கு"]
    assert clean("൭ മണിക്ക്", "ml") == ["7", "മണിക്ക്"]
    assert clean("at 5:30 pm", "en") == ["at", "five", "thirty", "pm"]


@pytest.mark.parametrize("text, expected", [
    ("bring me the newest headlines", "NEWS"),
    ("tell me a clever village story", "STORY"),
    ("say a poem from Bharathiyar", "VERSE"),
    ("இன்று காலையில் நடந்த செய்திகளைச் சொல்", "NEWS"),
    ("குழந்தைகளுக்காக ஒரு கதை சொல்லுங்கள்", "STORY"),
    ("குறளும் பொருளும் சொல்லுங்க", "VERSE"),
    ("ഇന്ന് രാവിലെ നടന്ന വാർത്ത പറയൂ", "NEWS"),
    ("മുത്തശ്ശി പറയാറുള്ള പോലെ ഒരു കഥ പറയണം", "STORY"),
    ("എഴുത്തച്ഛന്റെ ഒരു ശ്ലോകം ചൊല്ലൂ", "VERSE"),
])
def test_sample_routes(text, expected):
    assert JointRouter2.load().route(text).tool == expected

