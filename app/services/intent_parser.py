"""ML intent parser.

A TF-IDF + Logistic Regression pipeline trained on the labelled utterances in
data/intents.csv. The model is trained once at startup (dataset is small, this
takes well under a second) and cached with joblib so restarts are instant.

Alongside intent classification, a rule-based entity extractor pulls out
destination, number of days, month, budget, group type and interests from the
text so the planner can act on the parsed query.
"""

import csv
import os
import re

import joblib
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(BASE_DIR, "data")
MODEL_PATH = os.path.join(DATA_DIR, "intent_model.joblib")

_model = None

# ---------------------------------------------------------------- training

def _train():
    texts, labels = [], []
    with open(os.path.join(DATA_DIR, "intents.csv"), newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            texts.append(row["text"])
            labels.append(row["intent"])
    pipeline = Pipeline([
        ("tfidf", TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True,
                                  analyzer="word", min_df=1)),
        ("clf", LogisticRegression(max_iter=1000, C=8.0)),
    ])
    pipeline.fit(texts, labels)
    joblib.dump(pipeline, MODEL_PATH)
    return pipeline


def load_model():
    global _model
    if _model is None:
        if os.path.exists(MODEL_PATH):
            try:
                import warnings
                with warnings.catch_warnings():
                    warnings.simplefilter("error")  # treat version-mismatch warnings as errors
                    _model = joblib.load(MODEL_PATH)
                _model.predict(["health check"])  # sanity check the unpickled pipeline
            except Exception:
                _model = _train()  # retrain fresh (takes < 1 second)
        else:
            _model = _train()
    return _model


# ---------------------------------------------------------------- entities

PLACES = [
    "kedarnath", "badrinath", "gangotri", "yamunotri", "haridwar", "rishikesh",
    "dehradun", "mussoorie", "dhanaulti", "tehri", "nainital", "bhimtal",
    "mukteshwar", "ramnagar", "corbett", "jim corbett", "ranikhet", "almora",
    "kausani", "auli", "joshimath", "chopta", "tungnath", "chandrashila",
    "valley of flowers", "hemkund", "munsiyari", "chaukori", "chakrata",
    "harsil", "uttarkashi", "lansdowne", "sonprayag", "govindghat",
    "patal bhuvaneshwar", "jageshwar", "kasar devi", "naukuchiatal",
]

MONTHS = {
    "january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3, "mar": 3,
    "april": 4, "apr": 4, "may": 5, "june": 6, "jun": 6, "july": 7, "jul": 7,
    "august": 8, "aug": 8, "september": 9, "sep": 9, "sept": 9,
    "october": 10, "oct": 10, "november": 11, "nov": 11,
    "december": 12, "dec": 12,
}

GROUPS = {
    "family": ["family", "parents", "kids", "children", "mummy", "papa"],
    "friends": ["friends", "group", "college", "dosto", "yaar", "gang"],
    "couple": ["couple", "honeymoon", "wife", "husband", "partner"],
    "solo": ["solo", "alone", "akela", "myself"],
}

INTERESTS = {
    "adventure": ["adventure", "rafting", "bungee", "trek", "trekking", "ski",
                  "skiing", "paragliding", "camping", "zipline", "kayak"],
    "pilgrimage": ["temple", "yatra", "dham", "darshan", "aarti", "mandir",
                   "spiritual", "gurudwara", "pilgrimage"],
    "nature": ["nature", "waterfall", "lake", "valley", "flowers", "forest",
               "snow", "mountain", "scenic", "offbeat", "peaceful"],
    "wildlife": ["wildlife", "safari", "tiger", "elephant", "bird", "jungle"],
    "heritage": ["heritage", "museum", "history", "colonial", "ancient"],
    "hill_station": ["hill station", "mall road", "hills", "hillstation"],
}


def extract_entities(text: str) -> dict:
    low = text.lower()
    ent = {
        "destination": None, "days": None, "month": None,
        "budget": None, "group_type": None, "interests": [],
    }

    for p in sorted(PLACES, key=len, reverse=True):
        if p in low:
            ent["destination"] = "Jim Corbett" if p in ("corbett", "jim corbett") else p.title()
            break

    m = re.search(r"(\d+)\s*(?:din|day|days|nights?|raat)", low)
    if m:
        ent["days"] = max(1, min(10, int(m.group(1))))
    elif "weekend" in low:
        ent["days"] = 2
    elif "week" in low:
        ent["days"] = 7

    for name, num in MONTHS.items():
        if re.search(rf"\b{name}\b", low):
            ent["month"] = num
            break

    m = re.search(r"(?:under|budget|within|me|in)\s*(?:rs\.?|inr|₹)?\s*(\d{4,6})", low)
    if not m:
        m = re.search(r"(\d{4,6})\s*(?:rs|rupees|budget|ke andar|tak)", low)
    if m:
        ent["budget"] = int(m.group(1))

    for gtype, words in GROUPS.items():
        if any(w in low for w in words):
            ent["group_type"] = gtype
            break

    for interest, words in INTERESTS.items():
        if any(w in low for w in words):
            ent["interests"].append(interest)

    return ent


def parse(text: str) -> dict:
    model = load_model()
    proba = model.predict_proba([text])[0]
    classes = model.classes_
    best = int(proba.argmax())
    intent = classes[best]
    confidence = float(proba[best])
    if confidence < 0.18:
        intent = "sightseeing_info"
    return {
        "intent": str(intent),
        "confidence": round(confidence, 3),
        "entities": extract_entities(text),
    }
