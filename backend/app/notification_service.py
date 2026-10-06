from __future__ import annotations

import logging
from datetime import UTC, datetime, time, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.activity_maintenance import acquire_activity_writer_lock
from app.db.models import (
    Booking,
    Cancellation,
    Deal,
    Disruption,
    NotificationChannel,
    NotificationDelivery,
    NotificationDeliveryStatus,
    NotificationTransport,
    User,
    UserPreference,
)
from app.integrations.service import (
    get_integration,
    get_notification_connector,
    provider_is_simulated,
    source_is_simulated,
)
from app.integrations.types import ResolvedIntegrationConfig

logger = logging.getLogger(__name__)


def queue_notification(
    *,
    db: Session,
    user: User,
    message_type: str,
    subject: str,
    body: str,
    booking: Booking | None = None,
    cancellation: Cancellation | None = None,
    deal: Deal | None = None,
    disruption: Disruption | None = None,
    channel: NotificationChannel = NotificationChannel.INHERIT,
    force: bool = False,
    integration: ResolvedIntegrationConfig | None = None,
    simulated: bool = False,
) -> list[NotificationDelivery]:
    acquire_activity_writer_lock(db)
    resolved_integration = integration or get_integration(
        db=db,
        key="notifications",
    )
    destinations = _resolve_destinations(
        user=user,
        requested_channel=channel,
        integration=resolved_integration,
    )
    integration_mode = _notification_mode(integration=resolved_integration)
    simulated_activity = (
        simulated
        or (deal is not None and source_is_simulated(deal.source))
        or (booking is not None and provider_is_simulated(booking.provider))
    )
    created: list[NotificationDelivery] = []
    for destination_channel, destination_value in destinations:
        transport = (
            NotificationTransport.LOG_ONLY
            if simulated_activity
            else _resolve_transport(
                destination_channel=destination_channel,
                integration_mode=integration_mode,
            )
        )
        delivery = NotificationDelivery(
            user_id=user.id,
            booking_id=booking.id if booking else None,
            cancellation_id=cancellation.id if cancellation else None,
            disruption_id=disruption.id if disruption else None,
            deal_id=deal.id if deal else None,
            channel=destination_channel.value,
            transport=transport.value,
            destination=destination_value,
            message_type=message_type,
            status=NotificationDeliveryStatus.PENDING.value,
            attempted_at=datetime.now(UTC),
            payload_json={
                "subject": subject,
                "body": body,
                "force": force,
                "simulated": simulated_activity,
                "external_side_effect_suppressed": simulated_activity,
            },
        )
        db.add(delivery)
        db.flush()
        created.append(delivery)
    return created


def send_notification_delivery(*, db: Session, delivery_id: UUID) -> NotificationDelivery:
    acquire_activity_writer_lock(db)
    delivery = db.scalar(select(NotificationDelivery).where(NotificationDelivery.id == delivery_id))
    if delivery is None:
        raise LookupError("Notification delivery not found.")

    if str(delivery.status) in {
        NotificationDeliveryStatus.SENT.value,
        NotificationDeliveryStatus.SENT.name,
    }:
        return delivery

    user = db.scalar(select(User).where(User.id == delivery.user_id)) if delivery.user_id else None
    force = bool((delivery.payload_json or {}).get("force"))
    if user and not force and _in_quiet_hours(db=db, user=user):
        preference = db.scalar(select(UserPreference).where(UserPreference.user_id == user.id))
        send_after = (
            next_quiet_hours_end(
                start=preference.quiet_hours_start,
                end=preference.quiet_hours_end,
                now=datetime.now(UTC),
                timezone_name=getattr(preference, "quiet_hours_timezone", None),
            )
            if preference and preference.quiet_hours_start and preference.quiet_hours_end
            else datetime.now(UTC) + timedelta(minutes=15)
        )
        _defer_for_quiet_hours(delivery, send_after=send_after)
        db.add(delivery)
        db.commit()
        db.refresh(delivery)
        return delivery

    subject = str((delivery.payload_json or {}).get("subject") or "TRAMP update")
    body = str((delivery.payload_json or {}).get("body") or "")

    if _delivery_transport(delivery) == NotificationTransport.LOG_ONLY.value:
        delivery.status = NotificationDeliveryStatus.SENT.value
        delivery.delivered_at = datetime.now(UTC)
        delivery.payload_json = {
            **(delivery.payload_json or {}),
            "response": {
                "transport": NotificationTransport.LOG_ONLY.value,
                "simulated": bool((delivery.payload_json or {}).get("simulated")),
                "external_side_effect_suppressed": bool(
                    (delivery.payload_json or {}).get("external_side_effect_suppressed")
                ),
            },
        }
        delivery.error_text = None
        db.add(delivery)
        db.commit()
        db.refresh(delivery)
        return delivery

    try:
        connector = get_notification_connector(db=db, allow_disabled=True)
        response = connector.send(
            destination=delivery.destination or "",
            subject=subject,
            body=body,
            metadata={
                "message_type": delivery.message_type,
                "booking_id": str(delivery.booking_id) if delivery.booking_id else None,
                "cancellation_id": (
                    str(delivery.cancellation_id) if delivery.cancellation_id else None
                ),
                "deal_id": str(delivery.deal_id) if delivery.deal_id else None,
                "disruption_id": str(delivery.disruption_id) if delivery.disruption_id else None,
            },
        )
        delivery.status = NotificationDeliveryStatus.SENT.value
        delivery.delivered_at = datetime.now(UTC)
        delivery.payload_json = {**(delivery.payload_json or {}), "response": response}
        delivery.error_text = None
    except Exception as exc:  # noqa: BLE001
        delivery.status = NotificationDeliveryStatus.FAILED.value
        delivery.error_text = str(exc)

    db.add(delivery)
    db.commit()
    db.refresh(delivery)
    return delivery


def deliver_due_notifications(*, db: Session, now: datetime | None = None) -> int:
    current = now or datetime.now(UTC)
    deliveries = list(
        db.scalars(
            select(NotificationDelivery).where(
                NotificationDelivery.status == NotificationDeliveryStatus.PENDING
            )
        )
    )
    due_ids = [
        delivery.id
        for delivery in deliveries
        if (send_after := _send_after(delivery)) is not None and send_after <= current
    ]
    processed = 0
    for delivery_id in due_ids:
        try:
            send_notification_delivery(db=db, delivery_id=delivery_id)
            processed += 1
        except Exception:  # noqa: BLE001
            logger.exception("Deferred notification %s could not be sent.", delivery_id)
            db.rollback()
    return processed


def _quiet_hours_zone(timezone_name: str | None) -> ZoneInfo:
    name = (timezone_name or "").strip() or "UTC"
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError:
        return ZoneInfo("UTC")


def next_quiet_hours_end(
    *,
    start: time,
    end: time,
    now: datetime,
    timezone_name: str | None = None,
) -> datetime:
    zone = _quiet_hours_zone(timezone_name)
    current = now.astimezone(zone)
    end_at = datetime.combine(current.date(), end, tzinfo=zone)
    if start < end:
        result = end_at + timedelta(days=1) if end_at <= current else end_at
    elif current.time() >= start or end_at <= current:
        result = end_at + timedelta(days=1)
    else:
        result = end_at
    return result.astimezone(UTC)


def _defer_for_quiet_hours(delivery: NotificationDelivery, *, send_after: datetime) -> None:
    delivery.payload_json = {
        **(delivery.payload_json or {}),
        "send_after": send_after.isoformat(),
        "deferred_reason": "quiet_hours",
    }
    delivery.error_text = "Deferred by quiet hours."


def _send_after(delivery: NotificationDelivery) -> datetime | None:
    raw = (delivery.payload_json or {}).get("send_after")
    if not isinstance(raw, str) or not raw.strip():
        return None
    parsed = datetime.fromisoformat(raw)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def list_notification_deliveries_for_booking(
    *,
    db: Session,
    booking_id: UUID,
) -> list[NotificationDelivery]:
    return list(
        db.scalars(
            select(NotificationDelivery)
            .where(NotificationDelivery.booking_id == booking_id)
            .order_by(NotificationDelivery.attempted_at.desc(), NotificationDelivery.id.desc())
        )
    )


def _resolve_destinations(
    *,
    user: User,
    requested_channel: NotificationChannel,
    integration: ResolvedIntegrationConfig,
) -> list[tuple[NotificationChannel, str]]:
    effective_channel = (
        user.default_notify_channel
        if requested_channel == NotificationChannel.INHERIT
        else requested_channel
    )
    destinations: list[tuple[NotificationChannel, str]] = []
    if effective_channel in {NotificationChannel.EMAIL, NotificationChannel.BOTH}:
        destinations.append((NotificationChannel.EMAIL, user.email))
    if effective_channel in {NotificationChannel.TELEGRAM, NotificationChannel.BOTH}:
        telegram_destination = (
            user.telegram_chat_id
            or str(integration.credentials.get("telegram_default_chat_id") or "").strip()
        )
        if telegram_destination:
            destinations.append((NotificationChannel.TELEGRAM, telegram_destination))
    return destinations


def _resolve_transport(
    *,
    destination_channel: NotificationChannel,
    integration_mode: str,
) -> NotificationTransport:
    if destination_channel == NotificationChannel.EMAIL and integration_mode == "smtp_dev":
        return NotificationTransport.SMTP_DEV
    if destination_channel == NotificationChannel.TELEGRAM and integration_mode == "telegram_bot":
        return NotificationTransport.TELEGRAM_BOT
    return NotificationTransport.LOG_ONLY


def _notification_mode(*, integration: ResolvedIntegrationConfig) -> str:
    return str(integration.credentials.get("delivery_mode") or "log_only").strip().lower()


def _delivery_transport(delivery: NotificationDelivery) -> str:
    transport = delivery.transport
    value = transport.value if hasattr(transport, "value") else str(transport)
    return value.strip().lower()


def _in_quiet_hours(*, db: Session, user: User) -> bool:
    preference = db.scalar(select(UserPreference).where(UserPreference.user_id == user.id))
    if (
        preference is None
        or preference.quiet_hours_start is None
        or preference.quiet_hours_end is None
    ):
        return False
    zone = _quiet_hours_zone(getattr(preference, "quiet_hours_timezone", None))
    current = datetime.now(UTC).astimezone(zone).time()
    start = preference.quiet_hours_start
    end = preference.quiet_hours_end
    if start == end:
        return False
    if start < end:
        return start <= current < end
    return current >= start or current < end
