import json
import os
import re
import time
import shutil
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path


# ============================================================
# GAUKHANE QUESTIONS JSON BUILDER v2.1
#
# Features:
# - Riddle 30% / GK 70%
# - Validation
# - Duplicate protection
# - Bad question auto retry
# - GK fact verification
# - Safe atomic questions.json save
# - Backup + old backup cleanup
# - JSON health check
# - Statistics
# - Daily API usage counter
# - Daily usage history
# - Quota safe stop
# ============================================================


# ============================================================
# PATHS
# ============================================================

BASE_DIR = Path(r"E:\Streamer bot\Pabi GK bot")
DATA_DIR = BASE_DIR / "Data"

QUESTIONS_FILE = DATA_DIR / "questions.json"
API_KEY_FILE = DATA_DIR / "gemini_api_key.txt"

BACKUP_DIR = DATA_DIR / "Backups"

USAGE_FILE = DATA_DIR / "builder_usage.json"


# ============================================================
# GEMINI CONFIG
# ============================================================

MODEL = "gemini-3.6-flash"

API_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    f"{MODEL}:generateContent"
)


# ============================================================
# BUILDER CONFIG
# ============================================================

TARGET_RIDDLE_RATIO = 0.30
TARGET_GK_RATIO = 0.70

MAX_HTTP_RETRIES = 3

MAX_QUESTION_RETRIES = 4

VERIFY_GK_FACTS = True

REQUEST_DELAY_SECONDS = 2

PROMPT_EXISTING_LIMIT = 80

MAX_BACKUPS = 20

MAX_BATCH_SIZE = 100

MAX_USAGE_HISTORY_DAYS = 90


# ============================================================
# CUSTOM ERRORS
# ============================================================

class QuotaExhaustedError(Exception):
    pass


# ============================================================
# BASIC HELPERS
# ============================================================

def ensure_directories():

    DATA_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    BACKUP_DIR.mkdir(
        parents=True,
        exist_ok=True
    )


def pause():

    input(
        "\nEnter थिचेर Menu मा फर्कनुहोस्..."
    )


def today_string():

    return datetime.now().strftime(
        "%Y-%m-%d"
    )


# ============================================================
# API KEY
# ============================================================

def load_api_key():

    if not API_KEY_FILE.exists():

        print()
        print(
            "❌ gemini_api_key.txt भेटिएन।"
        )

        print(
            f"File: {API_KEY_FILE}"
        )

        return None

    api_key = API_KEY_FILE.read_text(
        encoding="utf-8"
    ).strip()

    if not api_key:

        print()
        print(
            "❌ gemini_api_key.txt खाली छ।"
        )

        return None

    return api_key


# ============================================================
# DAILY USAGE
# ============================================================

def empty_daily_usage(date_value=None):

    if date_value is None:
        date_value = today_string()

    return {
        "date": date_value,

        "apiCalls": 0,

        "generated": 0,
        "gkGenerated": 0,
        "riddleGenerated": 0,

        "factChecks": 0,

        "failed": 0,

        "generationRetries": 0,

        "duplicates": 0,

        "validationRejects": 0,

        "quotaStops": 0
    }


def create_empty_usage_database():

    return {
        "version": 1,

        "current": empty_daily_usage(),

        "history": []
    }


def load_usage():

    if not USAGE_FILE.exists():

        usage = create_empty_usage_database()

        save_usage(
            usage
        )

        return usage

    try:

        text = USAGE_FILE.read_text(
            encoding="utf-8-sig"
        )

        if not text.strip():

            usage = create_empty_usage_database()

            save_usage(
                usage
            )

            return usage

        usage = json.loads(
            text
        )

        if not isinstance(
            usage,
            dict
        ):

            raise ValueError(
                "Usage root invalid"
            )

        if "current" not in usage:

            usage["current"] = (
                empty_daily_usage()
            )

        if "history" not in usage:

            usage["history"] = []

        rollover_usage_day(
            usage
        )

        return usage

    except Exception:

        usage = create_empty_usage_database()

        save_usage(
            usage
        )

        return usage


def save_usage(usage):

    temp_file = (
        USAGE_FILE.with_suffix(
            ".json.tmp"
        )
    )

    text = json.dumps(
        usage,
        ensure_ascii=False,
        indent=2
    )

    temp_file.write_text(
        text,
        encoding="utf-8"
    )

    os.replace(
        temp_file,
        USAGE_FILE
    )


def rollover_usage_day(usage):

    today = today_string()

    current = usage.get(
        "current",
        {}
    )

    current_date = current.get(
        "date"
    )

    if current_date == today:

        return

    # पुरानो दिन history मा राख्ने
    if current_date:

        usage.setdefault(
            "history",
            []
        )

        usage["history"].append(
            current
        )

    # Latest history मात्र राख्ने
    history = usage.get(
        "history",
        []
    )

    if len(history) > MAX_USAGE_HISTORY_DAYS:

        history = history[
            -MAX_USAGE_HISTORY_DAYS:
        ]

    usage["history"] = history

    # नयाँ दिन reset
    usage["current"] = (
        empty_daily_usage(
            today
        )
    )

    save_usage(
        usage
    )


def increment_usage(
    usage,
    field,
    amount=1
):

    rollover_usage_day(
        usage
    )

    current = usage[
        "current"
    ]

    current[field] = (
        int(
            current.get(
                field,
                0
            )
        )
        +
        amount
    )

    save_usage(
        usage
    )


# ============================================================
# DAILY USAGE DISPLAY
# ============================================================

def show_daily_usage(usage):

    rollover_usage_day(
        usage
    )

    current = usage[
        "current"
    ]

    print()
    print(
        "📡 GEMINI DAILY USAGE"
    )

    print(
        "=========================================="
    )

    print(
        f"Date          : "
        f"{current['date']}"
    )

    print(
        f"API Calls     : "
        f"{current['apiCalls']}"
    )

    print()

    print(
        f"🧩 Riddles    : "
        f"{current['riddleGenerated']}"
    )

    print(
        f"🧠 GK         : "
        f"{current['gkGenerated']}"
    )

    print(
        f"🔎 Fact Checks: "
        f"{current['factChecks']}"
    )

    print()

    print(
        f"✅ Generated  : "
        f"{current['generated']}"
    )

    print(
        f"❌ Failed     : "
        f"{current['failed']}"
    )

    print(
        f"🔁 Gen Retry  : "
        f"{current['generationRetries']}"
    )

    print(
        f"♻️ Duplicates : "
        f"{current['duplicates']}"
    )

    print(
        f"⚠️ Validation : "
        f"{current['validationRejects']}"
    )

    print(
        f"🛑 Quota Stops: "
        f"{current['quotaStops']}"
    )

    print(
        "=========================================="
    )


# ============================================================
# DAILY HISTORY
# ============================================================

def show_usage_history(usage):

    rollover_usage_day(
        usage
    )

    history = usage.get(
        "history",
        []
    )

    print()
    print(
        "📅 GEMINI USAGE HISTORY"
    )

    print(
        "=========================================="
    )

    if not history:

        print(
            "अहिलेसम्म पुरानो दिनको history छैन।"
        )

        print(
            "=========================================="
        )

        return

    latest = history[-30:]

    for item in reversed(
        latest
    ):

        print(
            f"{item.get('date', '-')}"
            f" | Calls: "
            f"{item.get('apiCalls', 0)}"
            f" | Generated: "
            f"{item.get('generated', 0)}"
            f" | GK: "
            f"{item.get('gkGenerated', 0)}"
            f" | Riddle: "
            f"{item.get('riddleGenerated', 0)}"
            f" | Failed: "
            f"{item.get('failed', 0)}"
            f" | Quota: "
            f"{item.get('quotaStops', 0)}"
        )

    print(
        "=========================================="
    )


# ============================================================
# QUESTIONS DATABASE
# ============================================================

def create_empty_database():

    return {
        "version": 1,
        "questions": []
    }


def load_questions():

    if not QUESTIONS_FILE.exists():

        return create_empty_database()

    text = QUESTIONS_FILE.read_text(
        encoding="utf-8-sig"
    )

    if not text.strip():

        return create_empty_database()

    root = json.loads(
        text
    )

    if not isinstance(
        root,
        dict
    ):

        raise ValueError(
            "questions.json root object हुनुपर्छ।"
        )

    if "questions" not in root:

        root["questions"] = []

    if not isinstance(
        root["questions"],
        list
    ):

        raise ValueError(
            "'questions' array हुनुपर्छ।"
        )

    if "version" not in root:

        root["version"] = 1

    return root


# ============================================================
# SAFE QUESTIONS SAVE
# ============================================================

def save_questions(root):

    temp_file = (
        QUESTIONS_FILE.with_suffix(
            ".json.tmp"
        )
    )

    text = json.dumps(
        root,
        ensure_ascii=False,
        indent=2
    )

    temp_file.write_text(
        text,
        encoding="utf-8"
    )

    os.replace(
        temp_file,
        QUESTIONS_FILE
    )


# ============================================================
# BACKUP
# ============================================================

def backup_questions_file():

    if not QUESTIONS_FILE.exists():

        return None

    timestamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )

    backup_file = (
        BACKUP_DIR
        /
        f"questions_{timestamp}.json"
    )

    shutil.copy2(
        QUESTIONS_FILE,
        backup_file
    )

    cleanup_old_backups()

    return backup_file


def cleanup_old_backups():

    backups = sorted(
        BACKUP_DIR.glob(
            "questions_*.json"
        ),
        key=lambda p: p.stat().st_mtime,
        reverse=True
    )

    for old_file in backups[
        MAX_BACKUPS:
    ]:

        try:

            old_file.unlink()

        except Exception:

            pass


# ============================================================
# COUNTS
# ============================================================

def get_counts(questions):

    riddles = 0
    gk = 0
    approved = 0
    pending = 0

    for q in questions:

        q_type = str(
            q.get(
                "type",
                ""
            )
        ).lower()

        if q_type == "riddle":

            riddles += 1

        elif q_type == "gk":

            gk += 1

        if q.get(
            "approved"
        ) is True:

            approved += 1

        else:

            pending += 1

    return (
        riddles,
        gk,
        approved,
        pending
    )


# ============================================================
# STATISTICS
# ============================================================

def show_statistics(root):

    questions = root[
        "questions"
    ]

    (
        riddles,
        gk,
        approved,
        pending
    ) = get_counts(
        questions
    )

    total = (
        riddles + gk
    )

    if total > 0:

        riddle_percent = (
            riddles
            /
            total
            *
            100
        )

        gk_percent = (
            gk
            /
            total
            *
            100
        )

    else:

        riddle_percent = 0
        gk_percent = 0

    print()
    print(
        "📊 QUESTIONS STATISTICS"
    )

    print(
        "=========================================="
    )

    print(
        f"📚 Total Questions : "
        f"{len(questions)}"
    )

    print(
        f"🧩 Riddles         : "
        f"{riddles} "
        f"({riddle_percent:.1f}%)"
    )

    print(
        f"🧠 GK              : "
        f"{gk} "
        f"({gk_percent:.1f}%)"
    )

    print(
        f"✅ Approved        : "
        f"{approved}"
    )

    print(
        f"⏳ Pending         : "
        f"{pending}"
    )

    print()

    print(
        "🎯 Target"
    )

    print(
        "   Riddle : 30%"
    )

    print(
        "   GK     : 70%"
    )

    print(
        "=========================================="
    )


# ============================================================
# NORMALIZE
# ============================================================

def normalize_text(text):

    if not text:

        return ""

    text = str(
        text
    ).lower().strip()

    return "".join(
        ch
        for ch in text
        if ch.isalnum()
    )


# ============================================================
# DUPLICATE
# ============================================================

def is_duplicate(
    questions,
    new_question
):

    normalized_new = (
        normalize_text(
            new_question
        )
    )

    if not normalized_new:

        return True

    for item in questions:

        existing = (
            normalize_text(
                item.get(
                    "question",
                    ""
                )
            )
        )

        if (
            existing
            ==
            normalized_new
        ):

            return True

    return False


# ============================================================
# UNIQUE ID
# ============================================================

def next_question_id(
    questions,
    q_type
):

    prefix = (
        "r-"
        if q_type == "riddle"
        else "gk-"
    )

    highest = 0

    for item in questions:

        qid = str(
            item.get(
                "id",
                ""
            )
        )

        if not qid.lower().startswith(
            prefix.lower()
        ):

            continue

        number_part = (
            qid[
                len(prefix):
            ]
        )

        try:

            number = int(
                number_part
            )

            if number > highest:

                highest = number

        except ValueError:

            pass

    return (
        f"{prefix}"
        f"{highest + 1:06d}"
    )


# ============================================================
# 30 / 70 TYPE SELECTION
# ============================================================

def determine_next_type(
    questions
):

    riddles, gk, _, _ = (
        get_counts(
            questions
        )
    )

    total = (
        riddles + gk
    )

    if total == 0:

        return "gk"

    current_riddle_ratio = (
        riddles
        /
        total
    )

    if (
        current_riddle_ratio
        <
        TARGET_RIDDLE_RATIO
    ):

        return "riddle"

    return "gk"


# ============================================================
# EXISTING QUESTIONS FOR PROMPT
# ============================================================

def existing_questions_for_prompt(
    questions
):

    recent = questions[
        -PROMPT_EXISTING_LIMIT:
    ]

    lines = []

    for item in recent:

        question = str(
            item.get(
                "question",
                ""
            )
        ).strip()

        if question:

            lines.append(
                "- " + question
            )

    if not lines:

        return "(कुनै प्रश्न छैन)"

    return "\n".join(
        lines
    )


# ============================================================
# RIDDLE PROMPT
# ============================================================

def build_riddle_prompt(
    questions
):

    existing = (
        existing_questions_for_prompt(
            questions
        )
    )

    return f"""
तपाईं नेपाली गाउँखाने कथा तयार गर्ने विशेषज्ञ हुनुहुन्छ।

एउटा मात्र नयाँ, रमाइलो, स्पष्ट र राम्रो नेपाली गाउँखाने कथा तयार गर्नुहोस्।

नियम:
- एउटै स्पष्ट मुख्य उत्तर हुनुपर्छ।
- अत्यन्त अस्पष्ट प्रश्न नबनाउनुहोस्।
- पहिले भएका प्रश्नसँग duplicate नहोस्।
- प्रश्न नेपाली देवनागरीमा लेख्नुहोस्।
- answerText नेपाली देवनागरीमा दिनुहोस्।
- answers array मा मुख्य उत्तर राख्नुहोस्।
- कम्तीमा एउटा Romanized accepted answer राख्नुहोस्।
- गलत synonym नथप्नुहोस्।
- explanation नदिनुहोस्।
- Markdown नदिनुहोस्।
- JSON बाहेक अरू text नदिनुहोस्।
- difficulty easy, medium वा hard मात्र।

JSON:

{{
  "category": "गाउँखाने कथा",
  "question": "...",
  "answers": [
    "मुख्य उत्तर",
    "romanized answer"
  ],
  "answerText": "मुख्य उत्तर",
  "difficulty": "easy"
}}

पहिले भएका प्रश्नहरू:

{existing}
""".strip()


# ============================================================
# GK PROMPT
# ============================================================

def build_gk_prompt(
    questions
):

    existing = (
        existing_questions_for_prompt(
            questions
        )
    )

    return f"""
तपाईं नेपाली सामान्य ज्ञान प्रश्न तयार गर्ने विशेषज्ञ हुनुहुन्छ।

एउटा मात्र नयाँ, तथ्यात्मक र स्पष्ट GK प्रश्न तयार गर्नुहोस्।

नियम:
- नेपालसम्बन्धी GK लाई प्राथमिकता दिनुहोस्।
- विश्व, विज्ञान, भूगोल, इतिहास, खेलकुद आदि पनि हुन सक्छ।
- एउटै मात्र सही उत्तर हुनुपर्छ।
- ठीक 4 विकल्प A, B, C, D हुनुपर्छ।
- गलत विकल्प सम्भाव्य देखिनुपर्छ।
- पहिले भएका प्रश्नसँग duplicate नहोस्।
- प्रश्न नेपाली देवनागरीमा लेख्नुहोस्।
- correctOption मा A, B, C वा D मात्र।
- answerText सही option सँग ठ्याक्कै मिल्नुपर्छ।
- answers मा correctOption, सही उत्तर र Romanized answer राख्नुहोस्।
- तथ्य गलत वा विवादास्पद प्रश्न नबनाउनुहोस्।
- explanation नदिनुहोस्।
- Markdown नदिनुहोस्।
- JSON बाहेक अरू text नदिनुहोस्।
- difficulty easy, medium वा hard मात्र।

JSON:

{{
  "category": "नेपाल",
  "question": "...",
  "options": {{
    "A": "...",
    "B": "...",
    "C": "...",
    "D": "..."
  }},
  "answers": [
    "C",
    "सही उत्तर",
    "romanized answer"
  ],
  "correctOption": "C",
  "answerText": "सही उत्तर",
  "difficulty": "easy"
}}

पहिले भएका प्रश्नहरू:

{existing}
""".strip()


def build_prompt(
    q_type,
    questions
):

    if q_type == "riddle":

        return build_riddle_prompt(
            questions
        )

    return build_gk_prompt(
        questions
    )


# ============================================================
# QUOTA DETECTION
# ============================================================

def looks_like_quota_error(
    status_code,
    error_text
):

    text = str(
        error_text
    ).lower()

    quota_words = [
        "quota",
        "resource_exhausted",
        "resource exhausted",
        "requests per day",
        "perday",
        "daily limit",
        "daily quota",
        "exceeded your current quota"
    ]

    if status_code != 429:

        return False

    for word in quota_words:

        if word in text:

            return True

    return False


# ============================================================
# GEMINI API
# ============================================================

def call_gemini(
    api_key,
    prompt,
    usage,
    temperature=0.8
):

    body = {

        "contents": [
            {
                "role": "user",
                "parts": [
                    {
                        "text": prompt
                    }
                ]
            }
        ],

        "generationConfig": {

            "temperature":
                temperature,

            "responseMimeType":
                "application/json"
        }
    }

    payload = json.dumps(
        body,
        ensure_ascii=False
    ).encode(
        "utf-8"
    )

    last_error = None

    for attempt in range(
        1,
        MAX_HTTP_RETRIES + 1
    ):

        print(
            f"      Gemini HTTP "
            f"{attempt}/"
            f"{MAX_HTTP_RETRIES}..."
        )

        # वास्तविक API request count
        increment_usage(
            usage,
            "apiCalls"
        )

        request = (
            urllib.request.Request(
                API_URL,
                data=payload,
                method="POST",

                headers={
                    "Content-Type":
                        "application/json",

                    "Accept":
                        "application/json",

                    "x-goog-api-key":
                        api_key
                }
            )
        )

        try:

            with urllib.request.urlopen(
                request,
                timeout=90
            ) as response:

                response_text = (
                    response
                    .read()
                    .decode(
                        "utf-8"
                    )
                )

            response_json = (
                json.loads(
                    response_text
                )
            )

            candidates = (
                response_json.get(
                    "candidates",
                    []
                )
            )

            if not candidates:

                raise RuntimeError(
                    "Gemini candidate छैन।"
                )

            parts = (
                candidates[0]
                .get(
                    "content",
                    {}
                )
                .get(
                    "parts",
                    []
                )
            )

            if not parts:

                raise RuntimeError(
                    "Gemini parts छैन।"
                )

            text = parts[0].get(
                "text",
                ""
            )

            if not text.strip():

                raise RuntimeError(
                    "Gemini response खाली छ।"
                )

            return text

        except urllib.error.HTTPError as exc:

            try:

                error_body = (
                    exc.read()
                    .decode(
                        "utf-8",
                        errors="replace"
                    )
                )

            except Exception:

                error_body = ""

            last_error = (
                f"HTTP {exc.code}: "
                f"{error_body}"
            )

            # स्पष्ट quota error
            if looks_like_quota_error(
                exc.code,
                error_body
            ):

                raise QuotaExhaustedError(
                    last_error
                )

            # Temporary server/rate errors
            if (
                exc.code
                in (
                    429,
                    500,
                    502,
                    503,
                    504
                )
                and
                attempt
                <
                MAX_HTTP_RETRIES
            ):

                wait_seconds = (
                    attempt * 5
                )

                print(
                    f"      ⚠️ HTTP "
                    f"{exc.code}. "
                    f"{wait_seconds}s पछि retry..."
                )

                time.sleep(
                    wait_seconds
                )

                continue

            # लगातार 429 आयो भने safe quota stop
            if exc.code == 429:

                raise QuotaExhaustedError(
                    last_error
                )

            raise RuntimeError(
                last_error
            )

        except (
            urllib.error.URLError,
            TimeoutError
        ) as exc:

            last_error = str(
                exc
            )

            if (
                attempt
                <
                MAX_HTTP_RETRIES
            ):

                wait_seconds = (
                    attempt * 5
                )

                print(
                    "      ⚠️ Network error. "
                    f"{wait_seconds}s retry..."
                )

                time.sleep(
                    wait_seconds
                )

                continue

            raise RuntimeError(
                last_error
            )

    raise RuntimeError(
        last_error
        or
        "Gemini request failed."
    )


# ============================================================
# CLEAN GEMINI JSON
# ============================================================

def clean_json_text(text):

    text = text.strip()

    text = re.sub(
        r"^```(?:json)?",
        "",
        text,
        flags=re.IGNORECASE
    )

    text = re.sub(
        r"```$",
        "",
        text
    )

    text = text.strip()

    first = text.find(
        "{"
    )

    last = text.rfind(
        "}"
    )

    if (
        first >= 0
        and
        last > first
    ):

        text = text[
            first:
            last + 1
        ]

    return text.strip()


# ============================================================
# COMMON VALIDATION
# ============================================================

def validate_common(item):

    if not isinstance(
        item,
        dict
    ):

        return (
            False,
            "JSON object होइन।"
        )

    question = str(
        item.get(
            "question",
            ""
        )
    ).strip()

    answer_text = str(
        item.get(
            "answerText",
            ""
        )
    ).strip()

    answers = item.get(
        "answers"
    )

    if not question:

        return (
            False,
            "question खाली छ।"
        )

    if len(question) < 5:

        return (
            False,
            "question धेरै छोटो छ।"
        )

    if not answer_text:

        return (
            False,
            "answerText खाली छ।"
        )

    if (
        not isinstance(
            answers,
            list
        )
        or
        len(answers) == 0
    ):

        return (
            False,
            "answers invalid छ।"
        )

    clean_answers = []

    seen = set()

    for answer in answers:

        answer = str(
            answer
        ).strip()

        if not answer:

            continue

        key = (
            answer.lower()
        )

        if key in seen:

            continue

        seen.add(
            key
        )

        clean_answers.append(
            answer
        )

    if not clean_answers:

        return (
            False,
            "accepted answers खाली छन्।"
        )

    item["answers"] = (
        clean_answers
    )

    difficulty = str(
        item.get(
            "difficulty",
            "easy"
        )
    ).lower().strip()

    if difficulty not in (
        "easy",
        "medium",
        "hard"
    ):

        difficulty = "easy"

    item["difficulty"] = (
        difficulty
    )

    return True, ""


# ============================================================
# RIDDLE VALIDATION
# ============================================================

def validate_riddle(item):

    return validate_common(
        item
    )


# ============================================================
# GK VALIDATION
# ============================================================

def validate_gk(item):

    ok, error = (
        validate_common(
            item
        )
    )

    if not ok:

        return (
            False,
            error
        )

    options = item.get(
        "options"
    )

    if not isinstance(
        options,
        dict
    ):

        return (
            False,
            "options object छैन।"
        )

    for key in (
        "A",
        "B",
        "C",
        "D"
    ):

        value = str(
            options.get(
                key,
                ""
            )
        ).strip()

        if not value:

            return (
                False,
                f"Option {key} खाली छ।"
            )

        options[key] = (
            value
        )

    normalized_options = [

        normalize_text(
            options[key]
        )

        for key in (
            "A",
            "B",
            "C",
            "D"
        )
    ]

    if len(
        set(
            normalized_options
        )
    ) != 4:

        return (
            False,
            "Duplicate options छन्।"
        )

    correct = str(
        item.get(
            "correctOption",
            ""
        )
    ).upper().strip()

    if correct not in (
        "A",
        "B",
        "C",
        "D"
    ):

        return (
            False,
            "correctOption invalid छ।"
        )

    answer_text = str(
        item.get(
            "answerText",
            ""
        )
    ).strip()

    correct_text = (
        options[
            correct
        ]
    )

    if (
        normalize_text(
            answer_text
        )
        !=
        normalize_text(
            correct_text
        )
    ):

        return (
            False,
            "answerText र correct option मिलेन।"
        )

    answers = item[
        "answers"
    ]

    upper_answers = [

        str(a).upper().strip()

        for a in answers
    ]

    if correct not in upper_answers:

        answers.insert(
            0,
            correct
        )

    normalized_answers = [

        normalize_text(
            a
        )

        for a in answers
    ]

    if (
        normalize_text(
            answer_text
        )
        not in normalized_answers
    ):

        answers.append(
            answer_text
        )

    item["options"] = options

    item["correctOption"] = (
        correct
    )

    return True, ""


# ============================================================
# GK FACT CHECK
# ============================================================

def verify_gk_fact(
    api_key,
    item,
    usage
):

    if not VERIFY_GK_FACTS:

        return (
            True,
            "Skipped"
        )

    increment_usage(
        usage,
        "factChecks"
    )

    prompt = f"""
तपाईं तथ्य जाँच गर्ने reviewer हुनुहुन्छ।

तलको GK प्रश्न र उत्तर जाँच गर्नुहोस्।

Question:
{item['question']}

Options:
A: {item['options']['A']}
B: {item['options']['B']}
C: {item['options']['C']}
D: {item['options']['D']}

Claimed correct option:
{item['correctOption']}

Claimed answer:
{item['answerText']}

जाँच:
- प्रश्न तथ्यात्मक रूपमा सही छ?
- एउटै स्पष्ट सही उत्तर छ?
- claimed answer सही छ?
- विवादास्पद वा छिटो बदलिने तथ्य हो?

JSON मात्र दिनुहोस्:

{{
  "valid": true,
  "reason": "छोटो कारण"
}}
""".strip()

    raw = call_gemini(
        api_key,
        prompt,
        usage,
        temperature=0.1
    )

    cleaned = (
        clean_json_text(
            raw
        )
    )

    result = json.loads(
        cleaned
    )

    valid = (
        result.get(
            "valid"
        )
        is True
    )

    reason = str(
        result.get(
            "reason",
            ""
        )
    ).strip()

    return (
        valid,
        reason
    )


# ============================================================
# BUILD FINAL QUESTION
# ============================================================

def build_final_question(
    generated,
    qid,
    q_type
):

    category = str(
        generated.get(
            "category",
            ""
        )
    ).strip()

    if not category:

        category = (
            "गाउँखाने कथा"
            if q_type == "riddle"
            else "सामान्य ज्ञान"
        )

    final = {

        "id":
            qid,

        "type":
            q_type,

        "category":
            category,

        "question":
            str(
                generated[
                    "question"
                ]
            ).strip(),

        "options":
            None,

        "answers":
            generated[
                "answers"
            ],

        "correctOption":
            None,

        "answerText":
            str(
                generated[
                    "answerText"
                ]
            ).strip(),

        "difficulty":
            generated[
                "difficulty"
            ],

        "source": {

            "provider":
                "gemini",

            "api":
                "Gemini API",

            "model":
                MODEL
        },

        "approved":
            True,

        "usedCount":
            0,

        "lastUsed":
            None
    }

    if q_type == "gk":

        final["options"] = (
            generated[
                "options"
            ]
        )

        final["correctOption"] = (
            generated[
                "correctOption"
            ]
        )

    return final


# ============================================================
# GENERATE ONE QUESTION
# ============================================================

def generate_one(
    root,
    api_key,
    q_type,
    usage
):

    questions = root[
        "questions"
    ]

    last_error = None

    for generation_attempt in range(
        1,
        MAX_QUESTION_RETRIES + 1
    ):

        print(
            f"      Generate try "
            f"{generation_attempt}/"
            f"{MAX_QUESTION_RETRIES}"
        )

        try:

            prompt = build_prompt(
                q_type,
                questions
            )

            raw = call_gemini(
                api_key,
                prompt,
                usage
            )

            cleaned = (
                clean_json_text(
                    raw
                )
            )

            generated = (
                json.loads(
                    cleaned
                )
            )

            if q_type == "riddle":

                valid, error = (
                    validate_riddle(
                        generated
                    )
                )

            else:

                valid, error = (
                    validate_gk(
                        generated
                    )
                )

            if not valid:

                increment_usage(
                    usage,
                    "validationRejects"
                )

                raise RuntimeError(
                    "Validation: "
                    +
                    error
                )

            question_text = str(
                generated[
                    "question"
                ]
            ).strip()

            if is_duplicate(
                questions,
                question_text
            ):

                increment_usage(
                    usage,
                    "duplicates"
                )

                raise RuntimeError(
                    "Duplicate question"
                )

            if (
                q_type == "gk"
                and
                VERIFY_GK_FACTS
            ):

                print(
                    "      🔎 GK fact check..."
                )

                fact_ok, reason = (
                    verify_gk_fact(
                        api_key,
                        generated,
                        usage
                    )
                )

                if not fact_ok:

                    raise RuntimeError(
                        "Fact check rejected: "
                        +
                        reason
                    )

                print(
                    "      ✅ Fact check passed"
                )

            qid = (
                next_question_id(
                    questions,
                    q_type
                )
            )

            final_question = (
                build_final_question(
                    generated,
                    qid,
                    q_type
                )
            )

            # यहाँ पुगेपछि मात्र append
            questions.append(
                final_question
            )

            # तुरुन्त सुरक्षित save
            save_questions(
                root
            )

            # Save सफल भएपछि मात्र generated count
            increment_usage(
                usage,
                "generated"
            )

            if q_type == "gk":

                increment_usage(
                    usage,
                    "gkGenerated"
                )

            else:

                increment_usage(
                    usage,
                    "riddleGenerated"
                )

            return final_question

        except QuotaExhaustedError:

            # Quota error लाई retry नगर्ने
            raise

        except Exception as exc:

            last_error = str(
                exc
            )

            print(
                f"      ⚠️ "
                f"{last_error}"
            )

            if (
                generation_attempt
                <
                MAX_QUESTION_RETRIES
            ):

                increment_usage(
                    usage,
                    "generationRetries"
                )

                print(
                    "      🔁 नयाँ question "
                    "फेरि generate गर्दै..."
                )

                time.sleep(
                    REQUEST_DELAY_SECONDS
                )

    raise RuntimeError(
        last_error
        or
        "Generation failed."
    )


# ============================================================
# JSON HEALTH CHECK
# ============================================================

def health_check(root):

    questions = root[
        "questions"
    ]

    errors = []
    warnings = []

    seen_ids = set()
    seen_questions = set()

    for index, item in enumerate(
        questions,
        start=1
    ):

        label = (
            f"Item #{index}"
        )

        if not isinstance(
            item,
            dict
        ):

            errors.append(
                f"{label}: object होइन।"
            )

            continue

        qid = str(
            item.get(
                "id",
                ""
            )
        ).strip()

        q_type = str(
            item.get(
                "type",
                ""
            )
        ).lower().strip()

        question = str(
            item.get(
                "question",
                ""
            )
        ).strip()

        if not qid:

            errors.append(
                f"{label}: ID खाली।"
            )

        elif qid in seen_ids:

            errors.append(
                f"Duplicate ID: {qid}"
            )

        else:

            seen_ids.add(
                qid
            )

        normalized_q = (
            normalize_text(
                question
            )
        )

        if not question:

            errors.append(
                f"{qid or label}: "
                "question खाली।"
            )

        elif normalized_q:

            if (
                normalized_q
                in seen_questions
            ):

                errors.append(
                    f"Duplicate question: "
                    f"{question}"
                )

            else:

                seen_questions.add(
                    normalized_q
                )

        if q_type not in (
            "riddle",
            "gk"
        ):

            errors.append(
                f"{qid or label}: "
                f"invalid type '{q_type}'"
            )

        if q_type == "riddle":

            valid, error = (
                validate_riddle(
                    dict(
                        item
                    )
                )
            )

            if not valid:

                errors.append(
                    f"{qid}: "
                    f"{error}"
                )

        elif q_type == "gk":

            valid, error = (
                validate_gk(
                    dict(
                        item
                    )
                )
            )

            if not valid:

                errors.append(
                    f"{qid}: "
                    f"{error}"
                )

        if (
            item.get(
                "approved"
            )
            is not True
        ):

            warnings.append(
                f"{qid}: "
                "approved != true"
            )

    print()
    print(
        "🩺 JSON HEALTH CHECK"
    )

    print(
        "=========================================="
    )

    print(
        f"Checked: "
        f"{len(questions)} questions"
    )

    if not errors:

        print(
            "✅ Critical error भेटिएन।"
        )

    else:

        print(
            f"❌ Errors: "
            f"{len(errors)}"
        )

        for error in errors:

            print(
                "   - "
                +
                error
            )

    if warnings:

        print(
            f"⚠️ Warnings: "
            f"{len(warnings)}"
        )

        for warning in warnings:

            print(
                "   - "
                +
                warning
            )

    print(
        "=========================================="
    )


# ============================================================
# REPAIR DUPLICATE IDS
# ============================================================

def repair_duplicate_ids(root):

    questions = root[
        "questions"
    ]

    seen = set()

    repaired = 0

    for item in questions:

        qid = str(
            item.get(
                "id",
                ""
            )
        ).strip()

        if (
            qid
            and
            qid not in seen
        ):

            seen.add(
                qid
            )

            continue

        q_type = str(
            item.get(
                "type",
                ""
            )
        ).lower()

        if q_type not in (
            "riddle",
            "gk"
        ):

            continue

        new_id = (
            next_question_id(
                questions,
                q_type
            )
        )

        while new_id in seen:

            prefix = (
                "r-"
                if q_type == "riddle"
                else "gk-"
            )

            number = int(
                new_id[
                    len(prefix):
                ]
            )

            new_id = (
                f"{prefix}"
                f"{number + 1:06d}"
            )

        item["id"] = (
            new_id
        )

        seen.add(
            new_id
        )

        repaired += 1

    if repaired > 0:

        backup_questions_file()

        save_questions(
            root
        )

    print()
    print(
        f"🔧 Repaired IDs: "
        f"{repaired}"
    )


# ============================================================
# ASK GENERATION COUNT
# ============================================================

def ask_number():

    while True:

        print()

        value = input(
            "कति नयाँ प्रश्न बनाउने? "
        ).strip()

        try:

            number = int(
                value
            )

            if number < 1:

                print(
                    "कम्तीमा 1 लेख्नुहोस्।"
                )

                continue

            if number > MAX_BATCH_SIZE:

                print(
                    f"एकपटकमा अधिकतम "
                    f"{MAX_BATCH_SIZE}।"
                )

                continue

            return number

        except ValueError:

            print(
                "संख्या मात्र लेख्नुहोस्।"
            )


# ============================================================
# GENERATION MENU
# ============================================================

def generate_questions_menu(
    root,
    api_key,
    usage
):

    count = ask_number()

    backup_file = (
        backup_questions_file()
    )

    if backup_file:

        print()
        print(
            "💾 Backup:"
        )

        print(
            f"   {backup_file}"
        )

    print()
    print(
        "🚀 Generation सुरु..."
    )

    print()

    successful = 0
    failed = 0

    quota_stopped = False

    for index in range(
        1,
        count + 1
    ):

        q_type = (
            determine_next_type(
                root[
                    "questions"
                ]
            )
        )

        type_label = (
            "🧩 Riddle"
            if q_type == "riddle"
            else "🧠 GK"
        )

        print(
            f"[{index}/{count}] "
            f"{type_label}"
        )

        try:

            result = (
                generate_one(
                    root,
                    api_key,
                    q_type,
                    usage
                )
            )

            successful += 1

            print(
                f"      ✅ "
                f"{result['id']}"
            )

            print(
                f"      Q: "
                f"{result['question']}"
            )

            print(
                f"      A: "
                f"{result['answerText']}"
            )

        except QuotaExhaustedError as exc:

            quota_stopped = True

            increment_usage(
                usage,
                "quotaStops"
            )

            print()
            print(
                "🛑 GEMINI API QUOTA / RATE LIMIT"
            )

            print(
                "=========================================="
            )

            print(
                "Generation सुरक्षित रूपमा रोकियो।"
            )

            print()

            print(
                f"यस session मा बनेका प्रश्न: "
                f"{successful}"
            )

            print(
                "✅ बनेका सबै प्रश्न questions.json "
                "मा सुरक्षित छन्।"
            )

            print(
                "❌ अधुरो question save गरिएको छैन।"
            )

            print()
            print(
                "API message:"
            )

            print(
                str(exc)[:500]
            )

            print(
                "=========================================="
            )

            break

        except Exception as exc:

            failed += 1

            increment_usage(
                usage,
                "failed"
            )

            print(
                f"      ❌ Final Failed: "
                f"{exc}"
            )

        print()

        if index < count:

            time.sleep(
                REQUEST_DELAY_SECONDS
            )

    (
        riddles,
        gk,
        approved,
        pending
    ) = get_counts(
        root[
            "questions"
        ]
    )

    print()
    print(
        "=========================================="
    )

    if quota_stopped:

        print(
            "🛑 Generation stopped safely"
        )

    else:

        print(
            "✅ Generation finished"
        )

    print(
        f"Requested  : "
        f"{count}"
    )

    print(
        f"Successful : "
        f"{successful}"
    )

    print(
        f"Failed     : "
        f"{failed}"
    )

    remaining = (
        count
        -
        successful
        -
        failed
    )

    if remaining > 0:

        print(
            f"Remaining  : "
            f"{remaining}"
        )

    print()

    print(
        f"Total      : "
        f"{len(root['questions'])}"
    )

    print(
        f"Riddles    : "
        f"{riddles}"
    )

    print(
        f"GK         : "
        f"{gk}"
    )

    print(
        f"Approved   : "
        f"{approved}"
    )

    if pending:

        print(
            f"Pending    : "
            f"{pending}"
        )

    print()

    print(
        "Saved:"
    )

    print(
        QUESTIONS_FILE
    )

    print(
        "=========================================="
    )


# ============================================================
# MENU
# ============================================================

def print_menu():

    print()
    print(
        "🇳🇵 Gaukhane Questions JSON Builder v2.1"
    )

    print(
        "=========================================="
    )

    print(
        "1. Generate Questions"
    )

    print(
        "2. Show Statistics"
    )

    print(
        "3. JSON Health Check"
    )

    print(
        "4. Daily API Usage"
    )

    print(
        "5. Daily Usage History"
    )

    print(
        "6. Create Backup"
    )

    print(
        "7. Repair Duplicate IDs"
    )

    print(
        "8. Exit"
    )

    print(
        "=========================================="
    )


# ============================================================
# MAIN
# ============================================================

def main():

    ensure_directories()

    try:

        root = load_questions()

    except Exception as exc:

        print()
        print(
            "❌ questions.json पढ्न सकिएन।"
        )

        print(
            f"Error: {exc}"
        )

        pause()

        return

    usage = load_usage()

    api_key = load_api_key()

    while True:

        print_menu()

        choice = input(
            "Select: "
        ).strip()

        if choice == "1":

            if not api_key:

                api_key = (
                    load_api_key()
                )

                if not api_key:

                    pause()

                    continue

            try:

                generate_questions_menu(
                    root,
                    api_key,
                    usage
                )

            except Exception as exc:

                print()
                print(
                    f"❌ Error: {exc}"
                )

            pause()

        elif choice == "2":

            show_statistics(
                root
            )

            pause()

        elif choice == "3":

            health_check(
                root
            )

            pause()

        elif choice == "4":

            show_daily_usage(
                usage
            )

            pause()

        elif choice == "5":

            show_usage_history(
                usage
            )

            pause()

        elif choice == "6":

            backup_file = (
                backup_questions_file()
            )

            if backup_file:

                print()
                print(
                    "✅ Backup created:"
                )

                print(
                    backup_file
                )

            else:

                print()
                print(
                    "⚠️ questions.json छैन।"
                )

            pause()

        elif choice == "7":

            print()
            print(
                "Duplicate ID मात्र repair हुन्छ।"
            )

            answer = input(
                "Proceed? (y/n): "
            ).strip().lower()

            if answer == "y":

                repair_duplicate_ids(
                    root
                )

            pause()

        elif choice == "8":

            print()
            print(
                "👋 Builder बन्द भयो।"
            )

            break

        else:

            print()
            print(
                "❌ 1 देखि 8 मध्ये छान्नुहोस्।"
            )

            time.sleep(
                1
            )


# ============================================================
# START
# ============================================================

if __name__ == "__main__":

    try:

        main()

    except Exception as exc:

        print()
        print(
            "=========================================="
        )

        print(
            "❌ BUILDER STARTUP ERROR"
        )

        print(
            "=========================================="
        )

        print(
            exc
        )

        print(
            "=========================================="
        )

        import traceback

        traceback.print_exc()

        input(
            "\nEnter थिचेर बन्द गर्नुहोस्..."
        )