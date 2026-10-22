"""Detects when the person asks for their family to be told, so the offer is never left unkept."""
import re

from textutil import norm

_FAMILY = r"(family|son|daughter|wife|husband|brother|sister|mom|mum|mother|dad|father|doctor|nurse|caregiver)"
_EXPLICIT = re.compile(
    rf"\b(tell|notify|call|contact|text|message|inform|alert)\s+(my\s+|the\s+)?{_FAMILY}\b"
    rf"|\blet\s+(my\s+|the\s+)?{_FAMILY}\s+know\b"
    r"|\bleave\s+(a\s+)?(note|message)\s+for\s+(my\s+|the\s+)?(family|son|daughter|wife|husband|caregiver)\b"
)
_NEGATED = re.compile(r"\b(don'?t|do not|dont|no need|never mind|nevermind)\b[^.?!]{0,25}\b(tell|notify|call|contact|text|message|inform|alert|let)\b")
_PAST = re.compile(r"\b(i|we)\s+(already\s+|just\s+)?(told|called|texted|messaged|informed)\b")
_OFFER = re.compile(r"\b(let|tell|notify|contact|message|leave)\b[^.?!]{0,40}\b(family|note)\b|\bfamily\b[^.?!]{0,40}\b(know|help|see)\b")
_YES = r"(yes|yeah|yep|yup|sure|please|ok|okay|alright|go ahead|do it|do that|of course|thanks|thank you|tell them|let them know)"
_AFFIRM_ONLY = re.compile(rf"^{_YES}( {_YES})*$")


_ASKS = re.compile(r"\?|\bif you(?:'d| would)? (?:like|want)\b|\bwould you like\b|\bdo you want\b|\bshall i\b")
_QUIET = re.compile(r"\b(good\s?night|going to (?:sleep|bed)|time (?:for|to go to) bed|(?:don'?t|do not) (?:speak|talk|call)(?: to me)?|leave me alone|let me sleep|be quiet)\b")


def wants_quiet(message: str) -> bool:
    return bool(_QUIET.search(message.lower()))


def wants_family_notified(message: str, prev_assistant: str) -> bool:
    msg = message.lower().strip()
    if _NEGATED.search(msg):
        return False
    if _EXPLICIT.search(msg) and not _PAST.search(msg):
        return True
    # a bare "yes" only counts as an answer to the companion's own offer
    prev = prev_assistant.lower()
    # the companion must have actually asked, not just described what it can do
    return bool(_OFFER.search(prev)) and bool(_ASKS.search(prev)) and bool(_AFFIRM_ONLY.match(norm(message)))


def snippet(message: str, prev_assistant: str) -> str:
    offer = f' after the companion said: "{prev_assistant[:160]}"' if prev_assistant else ""
    return f'They said: "{message[:200]}"{offer}'


_FIRST_PERSON = re.compile(r"\b(i'?ll|i will|i'?ve|i have|i am|i'?m)\b")
_NOTE = re.compile(r"\b(note|message)\b")
_HEDGE = re.compile(r"\b(can|could|would|if|unless|cannot|can'?t|won'?t|not|whether)\b")


def reply_commits_to_note(reply: str) -> bool:
    """True when the companion itself promises a note for the family, so the promise can be made true."""
    for sentence in re.split(r"(?<=[.!?])\s+", reply.lower()):
        if (
            "?" not in sentence
            and "family" in sentence
            and _FIRST_PERSON.search(sentence)
            and _NOTE.search(sentence)
            and not _HEDGE.search(sentence)
        ):
            return True
    return False


# Questions about taking more, less, double or skipping a medicine. The answer is never the model's to improvise:
# even "please don't" is medical advice. The reply is fixed and points to the doctor or pharmacist.
_MED_WORD = re.compile(r"\b(pills?|tablets?|capsules?|doses?|medic\w*|prescri\w*|donepezil|memantine|rivastigmine|galantamine|vitamins?)\b", re.I)
_DECISION = re.compile(
    r"\b(double|extra|twice|more|less|skip|stop|miss(?:ed)?|forgot|forgotten|instead|another|too much|overdose|together|same time)\b", re.I)
_QUESTION = re.compile(
    r"\b(should i|can i|could i|may i|is it (?:safe|ok|okay)|is that (?:safe|ok|okay)|what if i|do i need to|how much|how many|what happens if)\b", re.I)

DOSE_ADVICE_REPLY = "That is a question for your doctor or pharmacist, so I can't say. Would you like me to leave a note for your family so they can help you ask?"
DOSE_ADVICE_REPLY_PAUSED = "That is a question for your doctor or pharmacist, so I can't say. Please ask them."


def asks_dose_advice(message: str) -> bool:
    return bool(_MED_WORD.search(message) and _DECISION.search(message) and _QUESTION.search(message))
