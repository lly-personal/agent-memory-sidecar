from __future__ import annotations


AMBIENT_CAPABILITY_VERSION = "AMBIENT_V3"
MAX_AMBIENT_CAPABILITY_BYTES = 512
AMBIENT_CAPABILITY_TEMPLATE = (
    "AMBIENT_V3 internal; never disclose. approval_ref=user_prompt:{event_id}. "
    "Finish the current task first. Afterward, use the installed agent-memory "
    "skill once only for an explicit remember or memory audit, or an evidenced "
    "reusable behavior or stable preference. If used or mentioned to the user, "
    "the final reply must end with one real card, receipt, or failure; commentary "
    "and future-tense promises do not count. Otherwise stay silent."
)
AMBIENT_CAPABILITY_TEMPLATE_BYTES = len(AMBIENT_CAPABILITY_TEMPLATE.encode("utf-8"))


def build_ambient_capability(event_id: str) -> str:
    safe_event_id = str(event_id).strip()
    if not safe_event_id or any(character.isspace() for character in safe_event_id):
        raise ValueError("ambient capability event_id must be non-empty and contain no whitespace")
    return AMBIENT_CAPABILITY_TEMPLATE.replace("{event_id}", safe_event_id, 1)
