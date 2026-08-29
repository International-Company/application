"""كتابة سجل التدقيق."""
from apps.common.enums import ActorType

from .models import AuditLog


def record(
    *,
    action: str,
    entity: str,
    entity_id=None,
    actor_type: str = ActorType.SYSTEM,
    actor_id=None,
    actor_label: str = "",
    before: dict | None = None,
    after: dict | None = None,
    ip: str | None = None,
) -> AuditLog:
    """تسجيل حدث تدقيق واحد."""
    return AuditLog.objects.create(
        actor_type=actor_type,
        actor_id=actor_id,
        actor_label=actor_label,
        action=action,
        entity=entity,
        entity_id=entity_id,
        before_json=before,
        after_json=after,
        ip=ip,
    )
