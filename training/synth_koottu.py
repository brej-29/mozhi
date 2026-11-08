"""Held-out synthetic utterances for STORY, VERSE, and multilingual note_save.

The template groups are deliberately disjoint.  The training group is used by the
model, while the dev and test groups are used only for tuning and evidence.
Every returned row carries a synthetic marker for reports.
"""

from __future__ import annotations

import random

TOOLS = {"story": "STORY", "verse": "VERSE", "note": "SAVE_NOTE"}

_TEMPLATES = {
    "en": {
        "train": {
            "news": [
                "what are the main headlines today",
                "read me the world news",
                "tell me the latest news",
                "what happened in the news this morning",
                "give me a news briefing",
                "catch me up on current events",
                "read the day's reports",
                "what is making the headlines",
            ],
            "story": [
                "tell me a folk tale",
                "please tell a story for children",
                "share a village tale with me",
                "tell me a story before bed",
                "narrate an old village legend",
                "share a short tale with a lesson",
                "tell a gentle story tonight",
                "read a traditional story aloud",
            ],
            "verse": [
                "recite a thirukkural",
                "say an aathichoodi line",
                "read me a poem by bharathiyar",
                "give me a kural and its meaning",
                "share a classical couplet",
                "read a verse from Tamil literature",
                "say a meaningful poem",
                "recite a line of poetry",
            ],
            "note": [
                "save a note that I need to buy milk",
                "write this down for me the meeting moved to Friday",
                "take a note to call the plumber",
                "remember that the parcel is with the neighbour",
                "add to my notes that rent is due",
                "save this shopping reminder",
                "write down my idea for later",
                "keep a note about the school event",
            ],
        },
        "dev": {
            "news": [
                "could you give me today's top headlines",
                "what is new around the world",
                "please read the current news",
                "would you summarize the morning reports",
                "tell me the latest developments",
            ],
            "story": [
                "could you tell a Tenali Raman tale",
                "tell a gentle story like grandmother used to",
                "I would like a short folk story",
                "can you narrate a village legend",
                "share a traditional bedtime tale",
            ],
            "verse": [
                "please quote a Bharathiyar verse",
                "would you share a Thirukkural couplet",
                "read an Aathichoodi saying aloud",
                "could you recite a literary verse",
                "share a short Tamil poem",
            ],
            "note": [
                "jot down that the dentist is on Monday",
                "keep a note saying buy batteries",
                "put this in my notes the gate code is 4412",
                "please save that the train leaves at six",
                "record a reminder about the library book",
            ],
        },
        "test": {
            "news": [
                "tell me the big stories from today",
                "what are people reporting worldwide",
                "bring me the newest headlines",
                "read the evening news to me",
                "what important events were reported",
            ],
            "story": [
                "tell me a clever village story",
                "share a tale for the little ones",
                "narrate a short bedtime folk story",
                "tell me an adventure from a village",
                "share a wise old tale",
            ],
            "verse": [
                "recite one couplet from the Kural",
                "say a poem from Bharathiyar",
                "give me a line of Aathichoodi",
                "read a devotional verse",
                "recite a famous Tamil couplet",
            ],
            "note": [
                "make a note to renew the passport",
                "save this reminder in my notes buy coffee beans",
                "note down that lunch is on Thursday",
                "write a reminder to water the plants",
                "save a note about tomorrow's appointment",
            ],
        },
    },
    "ta": {
        "train": {
            "news": [
                "இன்றைய முக்கியச் செய்திகளைச் சொல்லு",
                "உலகச் செய்திகளை வாசித்துச் சொல்லுங்கள்",
                "சமீபத்திய செய்தி என்ன",
                "இன்று காலையில் நடந்த செய்திகளைச் சொல்",
            ],
            "story": [
                "ஒரு நாட்டுப்புறக் கதை சொல்லு",
                "குழந்தைகளுக்காக ஒரு கதை சொல்லுங்கள்",
                "பாட்டி சொல்வது போல ஒரு கதை சொல்",
                "ஒரு சின்ன கிராமக் கதை சொல்லுங்க",
            ],
            "verse": [
                "ஒரு திருக்குறள் சொல்லு",
                "ஆத்திச்சூடி வரி சொல்லுங்கள்",
                "பாரதியார் பாடல் ஒன்றைப் பாடு",
                "குறளும் பொருளும் சொல்லுங்க",
            ],
            "note": [
                "ஒரு குறிப்பு எழுதிக்கொள் பால் வாங்க வேண்டும்",
                "இதை நினைவில் வை நாளை கூட்டம் உள்ளது",
                "குறிப்பாக சேமி மருந்து வாங்க வேண்டும்",
                "இதை குறித்துக்கொள் கதவு கடவுச்சொல் மேசையில் உள்ளது",
            ],
        },
        "dev": {
            "news": [
                "இன்றைய தலைப்புச் செய்திகளைச் சொல்லுங்க",
                "உலகத்தில் புதிதாக என்ன நடக்கிறது",
                "தற்போதைய செய்திகளை வாசியுங்கள்",
            ],
            "story": [
                "தெனாலிராமன் கதை ஒன்று சொல்லு",
                "பரவாயில்லை மெதுவாக ஒரு நாட்டுக் கதை சொல்லுங்கள்",
                "தூங்குவதற்கு முன் ஒரு கதை சொல்லுங்க",
            ],
            "verse": [
                "ஒரு குறள் பாடலைச் சொல்லு",
                "பாரதியாரின் கவிதை ஒன்றை வாசியுங்கள்",
                "ஆத்திச்சூடி வரி ஒன்றைச் சொல்லுங்க",
            ],
            "note": [
                "திங்கட்கிழமை மருத்துவரை பார்க்க வேண்டும் என்று குறிப்பு எடு",
                "மின்கலம் வாங்க வேண்டும் என்பதை சேமித்து வை",
                "நாளை பத்து மணிக்கு கூட்டம் என்று எழுதிக்கொள்",
            ],
        },
        "test": {
            "news": [
                "இன்றைய பெரிய செய்திகளைப் படி",
                "உலகம் முழுவதும் பேசப்படும் செய்தி என்ன",
                "புதிய தலைப்புச் செய்திகளைச் சொல்லு",
            ],
            "story": [
                "ஒரு நகைச்சுவையான கிராமக் கதை சொல்",
                "சிறுவர்களுக்காக ஒரு பழைய கதை சொல்லுங்கள்",
                "ஒரு சுருக்கமான படுக்கைக் கதை சொல்லுங்க",
            ],
            "verse": [
                "திருக்குறளில் இருந்து ஒரு குறள் சொல்லு",
                "பாரதியார் கவிதை ஒன்று பாடுங்கள்",
                "ஆத்திச்சூடியில் இருந்து ஒரு வரி சொல்",
            ],
            "note": [
                "கடவுச்சீட்டை புதுப்பிக்க வேண்டும் என்று குறித்துக்கொள்",
                "காபி விதைகள் வாங்க வேண்டும் என்பதை நோட்டில் சேமி",
                "வியாழன் மதிய உணவு என்று ஒரு குறிப்பு எழுது",
            ],
        },
    },
    "ml": {
        "train": {
            "news": [
                "ഇന്നത്തെ പ്രധാന വാർത്തകൾ പറയൂ",
                "ലോക വാർത്തകൾ വായിച്ചു തരൂ",
                "ഏറ്റവും പുതിയ വാർത്ത എന്താണ്",
                "ഇന്ന് രാവിലെ നടന്ന വാർത്ത പറയൂ",
                "ഇന്നത്തെ വാർത്താ ബുള്ളറ്റിൻ തരൂ",
                "ലോകത്ത് ഇപ്പോൾ നടക്കുന്ന കാര്യങ്ങൾ പറയൂ",
                "പുതിയ റിപ്പോർട്ടുകൾ ഒന്ന് വായിക്കൂ",
                "തലക്കെട്ടുകളിൽ എന്താണ് പ്രധാനപ്പെട്ടത്",
            ],
            "story": [
                "ഒരു നാടോടിക്കഥ പറയൂ",
                "കുട്ടികൾക്കായി ഒരു കഥ പറയൂ",
                "മുത്തശ്ശി പറയാറുള്ള പോലെ ഒരു കഥ പറയണം",
                "ഒരു ചെറിയ ഗ്രാമക്കഥ പറയൂ",
                "ഒരു പഴയ നാട്ടുകഥ വിവരിക്കൂ",
                "പാഠമുള്ള ഒരു ചെറുകഥ പറയൂ",
                "ഇന്ന് രാത്രി ശാന്തമായൊരു കഥ പറയൂ",
                "ഒരു പരമ്പരാഗത കഥ വായിച്ചു തരൂ",
            ],
            "verse": [
                "ഒരു തിരുക്കുറൾ ചൊല്ലൂ",
                "ആശാന്റെ ഒരു വരി പറയൂ",
                "എഴുത്തച്ഛന്റെ ഒരു ശ്ലോകം ചൊല്ലൂ",
                "ഒരു കവിതയും അർത്ഥവും പറയൂ",
                "ഒരു പ്രശസ്ത മലയാള പദ്യവരി പറയൂ",
                "സാഹിത്യത്തിലെ ഒരു ചെറിയ വരി ചൊല്ലൂ",
                "അർത്ഥമുള്ള ഒരു കവിത പറയൂ",
                "ഒരു ക്ലാസിക് ശ്ലോകം വായിക്കൂ",
            ],
            "note": [
                "ഒരു കുറിപ്പ് എഴുതി വെക്കൂ പാൽ വാങ്ങണം",
                "ഇത് ഓർമ്മയിൽ വെക്കൂ നാളെ യോഗമുണ്ട്",
                "മരുന്ന് വാങ്ങണം എന്ന് കുറിച്ചിടൂ",
                "വാതിൽക്കോഡ് മേശപ്പുറത്തുണ്ട് എന്ന് സൂക്ഷിക്കൂ",
                "വാടക അടയ്ക്കണം എന്ന് കുറിപ്പാക്കൂ",
                "ഈ വാങ്ങൽപ്പട്ടിക നോട്ട് ചെയ്യൂ",
                "പിന്നീട് ഓർക്കാൻ ഇത് എഴുതി വെക്കൂ",
                "സ്കൂൾ പരിപാടിയുടെ വിവരം സൂക്ഷിക്കൂ",
            ],
        },
        "dev": {
            "news": [
                "ഇന്നത്തെ പ്രധാന തലക്കെട്ടുകൾ പറയൂ",
                "ലോകത്ത് പുതുതായി എന്താണ് സംഭവിച്ചത്",
                "ഇപ്പോഴത്തെ വാർത്തകൾ വായിക്കൂ",
                "രാവിലെ വന്ന റിപ്പോർട്ടുകൾ ചുരുക്കി പറയൂ",
                "ഏറ്റവും പുതിയ സംഭവവികാസങ്ങൾ എന്താണ്",
            ],
            "story": [
                "തച്ചോളി ഒതേനന്റെ ഒരു കഥ പറയൂ",
                "പരവായില്ല പതുക്കെ ഒരു നാട്ടുകഥ പറയൂ",
                "ഉറങ്ങുന്നതിന് മുമ്പ് ഒരു കഥ പറയണം",
                "ഒരു ഗ്രാമത്തിലെ പഴയ ഇതിഹാസം പറയൂ",
                "കുട്ടികൾക്കായി ഒരു bedtime കഥ പറയൂ",
            ],
            "verse": [
                "കുമാരനാശാന്റെ ഒരു വരി ചൊല്ലൂ",
                "ജ്ഞാനപ്പാനയിലെ ഒരു വരി പറയൂ",
                "എഴുത്തച്ഛന്റെ കവിത ചൊല്ലൂ",
                "ഒരു മലയാള സാഹിത്യവരി ചൊല്ലൂ",
                "ചെറിയൊരു കവിത വായിച്ചു തരൂ",
            ],
            "note": [
                "വെള്ളിയാഴ്ച ഡോക്ടറെ കാണണം എന്ന് കുറിച്ചിടൂ",
                "ബാറ്ററി വാങ്ങണം എന്ന് കുറിപ്പിൽ സൂക്ഷിക്കൂ",
                "നാളെ പത്ത് മണിക്ക് യോഗം എന്ന് എഴുതിവെക്കൂ",
                "ട്രെയിൻ ആറിന് പുറപ്പെടും എന്ന് സേവ് ചെയ്യൂ",
                "ലൈബ്രറി പുസ്തകം തിരികെ നൽകണം എന്ന് ഓർക്കൂ",
            ],
        },
        "test": {
            "news": [
                "ഇന്നത്തെ വലിയ വാർത്തകൾ പറയൂ",
                "ലോകമെമ്പാടും റിപ്പോർട്ട് ചെയ്യുന്ന വാർത്ത എന്താണ്",
                "പുതിയ തലക്കെട്ടുകൾ വായിച്ചു തരൂ",
                "വൈകുന്നേരത്തെ വാർത്തകൾ ഒന്ന് പറയൂ",
                "പ്രധാനപ്പെട്ട ഇന്നത്തെ സംഭവങ്ങൾ എന്താണ്",
            ],
            "story": [
                "ഒരു രസകരമായ ഗ്രാമകഥ പറയൂ",
                "കുട്ടികൾക്ക് ഒരു പഴയ കഥ പറഞ്ഞുതരൂ",
                "ചെറിയൊരു ഉറക്കക്കഥ പറയൂ",
                "ഒരു ഗ്രാമത്തിലെ സാഹസികകഥ പറയൂ",
                "ബുദ്ധിയുള്ള ഒരു പഴയ കഥ പങ്കിടൂ",
            ],
            "verse": [
                "തിരുക്കുറളിൽ നിന്ന് ഒരു വരി പറയൂ",
                "ഭാരതീയ കവിതയിലെ ഒരു വരി ചൊല്ലൂ",
                "ആശാന്റെ ഒരു കവിത പറയൂ",
                "ഒരു ഭക്തിഗാനം പോലെയുള്ള പദ്യവരി പറയൂ",
                "പ്രശസ്തമായ ഒരു മലയാള കവിത ചൊല്ലൂ",
            ],
            "note": [
                "പാസ്പോർട്ട് പുതുക്കണം എന്ന് കുറിപ്പാക്കൂ",
                "കാപ്പിക്കുരു വാങ്ങണം എന്ന് നോട്ട് ചെയ്യൂ",
                "വ്യാഴാഴ്ച ഉച്ചഭക്ഷണം എന്ന് എഴുതി വെക്കൂ",
                "ചെടികൾക്ക് വെള്ളം നൽകണം എന്ന് കുറിക്കൂ",
                "നാളത്തെ കൂടിക്കാഴ്ചയെക്കുറിച്ച് ഓർമ്മക്കുറിപ്പ് ഇടൂ",
            ],
        },
    },
}


def rows(split: str, seed: int = 0) -> list[tuple[list[str], list[str], str, str, bool]]:
    """Return synthetic rows as words, tags, intent, language, synthetic."""
    if split not in {"train", "dev", "test"}:
        raise ValueError(split)
    rng = random.Random(seed + {"train": 11, "dev": 17, "test": 23}[split])
    out = []
    for lang, groups in _TEMPLATES.items():
        for kind, texts in groups[split].items():
            for text in texts:
                repeats = 40 if split == "train" else 2
                for _ in range(repeats):
                    words = text.split()
                    rng.shuffle(words) if False else None
                    out.append((words, ["O"] * len(words), f"synthetic_{kind}_{lang}", lang, True))
    rng.shuffle(out)
    return out

