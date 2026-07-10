from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    Booking,
    Deal,
    Disruption,
    NotificationChannel,
    NotificationDelivery,
    NotificationDeliveryStatus,
    NotificationTransport,
    User,
    UserPreference,
)
from app.integrations.service import get_integration, get_notification_connector
from app.integrations.types import ResolvedIntegrationConfig


def queue_notification(
    *,
    db: Session,
    user: User,
    message_type: str,
    subject: str,
    body: str,
    booking: Booking | None = None,
    deal: Deal | None = None,
    disruption: Disruption | None = None,
    channel: NotificationChannel = NotificationChannel.INHERIT,
    force: bool = False,
    integration: ResolvedIntegrationConfig | None = None,
) -> list[NotificationDelivery]:
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
    created: list[NotificationDelivery] = []
    for destination_channel, destination_value in destinations:
        transport = _resolve_transport(
            destination_channel=destination_channel,
            integration_mode=integration_mode,
        )
        delivery = NotificationDelivery(
            user_id=user.id,
            booking_id=booking.id if booking else None,
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
            },
        )
        db.add(delivery)
        db.flush()
        created.append(delivery)
    return created


def send_notification_delivery(*, db: Session, delivery_id: UUID) -> NotificationDelivery:
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
        delivery.error_text = "Deferred by quiet hours."
        db.add(delivery)
        db.commit()
        db.refresh(delivery)
        return delivery

    subject = str((delivery.payload_json or {}).get("subject") or "TRAMP update")
    body = str((delivery.payload_json or {}).get("body") or "")

    try:
        connector = get_notification_connector(db=db, allow_disabled=True)
        response = connector.send(
            destination=delivery.destination or "",
            subject=subject,
            body=body,
            metadata={
                "message_type": delivery.message_type,
                "booking_id": str(delivery.booking_id) if delivery.booking_id else None,
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


def _in_quiet_hours(*, db: Session, user: User) -> bool:
    preference = db.scalar(select(UserPreference).where(UserPreference.user_id == user.id))
    if (
        preference is None
        or preference.quiet_hours_start is None
        or preference.quiet_hours_end is None
    ):
        return False
    current = datetime.now(UTC).time()
    start = preference.quiet_hours_start
    end = preference.quiet_hours_end
    if start == end:
        return False
    if start < end:
        return start <= current <= end
    return current >= start or current <= end
