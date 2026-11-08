"""Synthetic training data for what MASSIVE does not cover.

MASSIVE has no "save a note" intent (its closest, lists_createoradd, is mostly "create a list"),
so a model trained only on it cannot take a note. These templates add a `note_save` intent for
training and dev only. The benchmark test set is untouched, so reported test numbers stay
comparable. Contents are hand-written and split by content between train and dev.
"""

import random

TRIGGERS = [
    "save a note", "take a note", "make a note", "add a note", "create a note", "note down",
    "jot down", "write down", "write this down", "keep a note", "note to self", "save this",
    "remember that", "make a note to self", "put in a note", "please save a note", "can you note down",
]
LINKS = ["", "", "that", "saying", "to", "about", "for me"]
CONTENT = [
    "buy oat milk", "the meeting moved to friday", "my locker code is 4412", "call the plumber",
    "ideas for the new app", "pick up the dry cleaning", "wifi password is on the fridge",
    "book dentist for march", "try the new ramen place", "birthday gift ideas for dad",
    "the parcel is with the neighbour", "check tyre pressure", "email priya the slides",
    "mum likes the blue scarf", "renew the passport", "the parking spot is level three",
    "read about reinforcement learning", "water the plants on sunday", "ask sam about the invoice",
    "gym bag by the door", "the code for the gate is 9081", "look into solar panels",
    "recipe needs two lemons and basil", "return the drill to rahul", "flight lands at nine",
    "the landlord prefers calls after six", "buy batteries", "chapter four is due next week",
    "paint colour is warm white", "tell anna the keys are under the mat", "grandma's phone number",
    "the vet said once a day", "update the budget sheet", "order more coffee beans",
    "think about the talk title", "the shop closes at eight", "bring the charger", "fix the squeaky door",
    "idea for a podcast on sleep", "what the doctor said about vitamin d", "lunch with maya on thursday",
    "the printer needs new ink", "sell the old monitor", "tickets are in the blue folder",
    "look up trains to leeds", "milk eggs and bread", "weekly review goes in the doc",
    "the plumber is called ravi", "new password hint is first pet", "buy a birthday card",
]
GREETINGS = ["hello jarvis", "hi jarvis", "hey jarvis", "good morning jarvis", "good evening jarvis",
             "hey there jarvis", "hello there", "yo jarvis", "jarvis hello", "thanks jarvis",
             "thank you jarvis", "hi there"]


def notes(seed: int = 0, per_content: int = 4):
    """Returns (train_rows, dev_rows) of (words, tags, intent); content split 80/20."""
    rng = random.Random(seed)
    contents = CONTENT[:]
    rng.shuffle(contents)
    cut = int(len(contents) * 0.8)
    out = []
    for part in (contents[:cut], contents[cut:]):
        rows = []
        for c in part:
            for _ in range(per_content):
                text = " ".join(x for x in (rng.choice(TRIGGERS), rng.choice(LINKS), c) if x)
                if rng.random() < 0.15:
                    text = "mozhi " + text
                w = text.split()
                rows.append((w, ["O"] * len(w), "note_save"))
        out.append(rows)
    return out


def greetings():
    return [(g.split(), ["O"] * len(g.split()), "general_greet") for g in GREETINGS]


def wake_word(rows, rng, p: float = 0.12):
    """Product augmentation: users address the assistant by name, MASSIVE never does."""
    out = []
    for w, t, i in rows:
        r = rng.random()
        if r < p / 2:
            out.append((["mozhi"] + w, ["O"] + t, i))
        elif r < p:
            out.append((["hey", "mozhi"] + w, ["O", "O"] + t, i))
        elif r < p * 1.5:
            out.append((w + ["mozhi"], t + ["O"], i))
        else:
            out.append((w, t, i))
    return out
