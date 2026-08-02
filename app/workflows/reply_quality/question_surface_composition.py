"""Structured customer-visible question composition for deterministic fallback."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class QuestionComposeStrategy(str, Enum):
    SEND_REQUEST = "send_request"
    STANDALONE = "standalone"
    FULL_QUESTION = "full_question"


@dataclass(frozen=True)
class QuestionComposeSpec:
    strategy: QuestionComposeStrategy
  # (language, register) -> full customer sentence
    forms: dict[tuple[str, str], str]


def _sv(du: str, ni: str | None = None) -> dict[tuple[str, str], str]:
    return {("sv", "du"): du, ("sv", "ni"): ni or du.replace("du ", "ni ").replace("dig ", "er ")}


def _en(text: str) -> dict[tuple[str, str], str]:
    return {("en", "you"): text}


_QUESTION_COMPOSE_SPECS: dict[str, QuestionComposeSpec] = {
    "original_case": QuestionComposeSpec(
        strategy=QuestionComposeStrategy.SEND_REQUEST,
        forms={
            **_sv(
                "Kan du skicka orderreferens eller ursprungligt ärende?",
                "Kan ni skicka orderreferens eller ursprungligt ärende?",
            ),
            **_en("Could you send the original order or case reference?"),
        },
    ),
    "evidence": QuestionComposeSpec(
        strategy=QuestionComposeStrategy.SEND_REQUEST,
        forms={
            **_sv(
                "Skicka gärna bilder eller dokument som stödjer ärendet.",
                "Skicka gärna bilder eller dokument som stödjer ärendet.",
            ),
            **_en("Please send photos or documents that support the case."),
        },
    ),
    "discovery_time": QuestionComposeSpec(
        strategy=QuestionComposeStrategy.STANDALONE,
        forms={
            **_sv("När upptäckte du problemet?", "När upptäckte ni problemet?"),
            **_en("When did you discover the problem?"),
        },
    ),
    "safety_relevance": QuestionComposeSpec(
        strategy=QuestionComposeStrategy.STANDALONE,
        forms={
            **_sv(
                "Meddela också om felet kan påverka säkerheten.",
                "Meddela också om felet kan påverka säkerheten.",
            ),
            **_en("Please also let us know whether the fault may affect safety."),
        },
    ),
    "main_fuse": QuestionComposeSpec(
        strategy=QuestionComposeStrategy.FULL_QUESTION,
        forms={
            **_sv("Vilken storlek har huvudsäkringen?", "Vilken storlek har huvudsäkringen?"),
            **_en("What size is your main fuse or available capacity?"),
        },
    ),
    "load_balancing_need": QuestionComposeSpec(
        strategy=QuestionComposeStrategy.FULL_QUESTION,
        forms={
            **_sv(
                "Behöver ni även lastbalansering till laddboxen?",
                "Behöver ni även lastbalansering till laddboxen?",
            ),
            **_en("Do you also need load balancing for the charger?"),
        },
    ),
}


def _lookup_form(spec: QuestionComposeSpec, *, language: str, register: str) -> str:
    lang = "en" if language.lower().startswith("en") else "sv"
    reg = register if lang == "sv" else "you"
    return spec.forms.get((lang, reg)) or next(iter(spec.forms.values()))


def compose_semantic_question_sentence(
    field: str,
    *,
    language: str,
    register: str,
    label_fallback: str,
) -> tuple[str, QuestionComposeStrategy]:
    spec = _QUESTION_COMPOSE_SPECS.get(field)
    if spec is not None:
        return _lookup_form(spec, language=language, register=register), spec.strategy
    lowered = label_fallback.strip().lower()
    if lowered.startswith(("vilken ", "vilket ", "vad ", "när ", "hur ", "behöver ", "which ", "what ", "when ", "how ", "do ")):
        return label_fallback.rstrip(".?") + ("?" if not label_fallback.endswith("?") else ""), QuestionComposeStrategy.FULL_QUESTION
    if lowered.startswith("om "):
        if language == "en":
            return f"Please also let us know {label_fallback.rstrip('.?')}?", QuestionComposeStrategy.STANDALONE
        if register == "du":
            return f"Meddela också {label_fallback.rstrip('.?')}?", QuestionComposeStrategy.STANDALONE
        return f"Meddela också {label_fallback.rstrip('.?')}?", QuestionComposeStrategy.STANDALONE
    if language == "en":
        return f"Could you please send {label_fallback.rstrip('.?')}?", QuestionComposeStrategy.SEND_REQUEST
    if register == "du":
        return f"Kan du skicka {label_fallback.rstrip('.?')}?", QuestionComposeStrategy.SEND_REQUEST
    return f"Kan ni skicka {label_fallback.rstrip('.?')}?", QuestionComposeStrategy.SEND_REQUEST


def _combine_send_requests(sentences: list[str], *, language: str, register: str) -> str:
    if not sentences:
        return ""
    if len(sentences) == 1:
        return sentences[0]
    if language == "en":
        if len(sentences) == 2:
            first = sentences[0].rstrip(".?")
            second = sentences[1].rstrip(".?")
            if first.lower().startswith("could you send"):
                payload = first[len("Could you send ") :].rstrip(".?")
                return f"Could you send {payload} and {second.lower()}?"
            return f"{first}? {second}"
        return " ".join(s.rstrip(".?") + ("?" if not s.endswith("?") else "") for s in sentences)
    if len(sentences) == 2:
        a, b = sentences[0].rstrip(".?"), sentences[1].rstrip(".?")
        if b.lower().startswith("skicka gärna "):
            b = b[len("Skicka gärna ") :].rstrip(".?")
        if b.lower().startswith("please send "):
            b = b[len("Please send ") :].rstrip(".?")
        if a.lower().startswith("kan du skicka "):
            payload = a[len("Kan du skicka ") :].rstrip(".?")
            return f"Kan du skicka {payload} samt {b.lower()}?"
        if a.lower().startswith("kan ni skicka "):
            payload = a[len("Kan ni skicka ") :].rstrip(".?")
            return f"Kan ni skicka {payload} samt {b.lower()}?"
        if a.lower().startswith("could you send "):
            payload = a[len("Could you send ") :].rstrip(".?")
            return f"Could you send {payload} and {b.lower()}?"
        if a.lower().startswith("skicka gärna"):
            return f"{a}? {b}"
    return " ".join(s.rstrip(".?") + ("?" if not s.endswith("?") else "") for s in sentences)


def compose_customer_question_block(
    fields: tuple[str, ...],
    labels: tuple[str, ...],
    *,
    language: str,
    register: str,
) -> str:
    if not fields:
        return ""
    pairs: list[tuple[str, QuestionComposeStrategy]] = []
    for field, label in zip(fields, labels):
        sentence, strategy = compose_semantic_question_sentence(
            field, language=language, register=register, label_fallback=label
        )
        pairs.append((sentence, strategy))

    send_requests = [s for s, st in pairs if st == QuestionComposeStrategy.SEND_REQUEST]
    standalone = [s for s, st in pairs if st == QuestionComposeStrategy.STANDALONE]
    full_questions = [s for s, st in pairs if st == QuestionComposeStrategy.FULL_QUESTION]

    parts: list[str] = []
    if send_requests:
        parts.append(_combine_send_requests(send_requests, language=language, register=register))
    parts.extend(full_questions)
    parts.extend(standalone)
    return " ".join(p for p in parts if p)
