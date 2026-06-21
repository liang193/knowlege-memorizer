# -*- coding: utf-8 -*-
"""SM-2 间隔重复算法"""
import datetime
from datetime import date


def calculate_sm2(quality: int, repetitions: int, ease_factor: float, interval: int):
    """SM-2 算法核心。quality: 0-5"""
    if quality < 3:
        return 0, ease_factor, 1
    new_ef = ease_factor + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
    if new_ef < 1.3:
        new_ef = 1.3
    new_repetitions = repetitions + 1
    if new_repetitions == 1:
        new_interval = 1
    elif new_repetitions == 2:
        new_interval = 6
    else:
        new_interval = round(interval * new_ef)
    return new_repetitions, round(new_ef, 2), new_interval


def get_next_review_date(last_review: str, interval: int) -> str:
    if not last_review:
        last_date = date.today()
    else:
        try:
            last_date = datetime.datetime.strptime(last_review, "%Y-%m-%d").date()
        except ValueError:
            last_date = date.today()
    next_date = last_date + datetime.timedelta(days=interval)
    return next_date.strftime("%Y-%m-%d")


def get_due_cards(knowledge_base: list) -> list:
    today = date.today().strftime("%Y-%m-%d")
    return [kp for kp in knowledge_base
            if not kp.get("next_review") or kp["next_review"] <= today]


def get_stats(knowledge_base: list) -> dict:
    total = len(knowledge_base)
    new_cards = sum(1 for kp in knowledge_base if kp.get("status") == "new")
    due = len(get_due_cards(knowledge_base))
    mastered = sum(1 for kp in knowledge_base if kp.get("status") == "mastered")
    learning = sum(1 for kp in knowledge_base if kp.get("status") == "learning")
    reviewing = sum(1 for kp in knowledge_base if kp.get("status") == "reviewing")
    return {"total": total, "new": new_cards, "due": due,
            "mastered": mastered, "learning": learning, "reviewing": reviewing}


def init_card(question: str, answer: str, tags=None, outline_ref=None, notes="", source_text=""):
    import uuid
    return {
        "id": str(uuid.uuid4()),
        "question": question,
        "answer": answer,
        "source_text": source_text,
        "tags": tags or [],
        "outline_ref": outline_ref or [],
        "notes": notes,
        "status": "new",
        "interval": 0,
        "ease_factor": 2.5,
        "repetitions": 0,
        "next_review": "",
        "last_review": "",
        "created": date.today().strftime("%Y-%m-%d"),
        "quiz_count": 0,
    "correct_count": 0,
}


def get_status_by_sm2(repetitions, ease_factor, interval):
    """根据 SM-2 参数判断卡片学习状态"""
    if repetitions == 0:
        return "new"
    if repetitions < 3 and interval < 7:
        return "learning"
    if interval >= 21 and repetitions >= 5:
        return "mastered"
    return "reviewing"
