# ruff: noqa: B008,E501
from __future__ import annotations

import json
from dataclasses import asdict
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.schemas.profile import (
    BillingAddressModel,
    HouseholdWorkspaceSummaryResponse,
    LoyaltyProgramModel,
    LoyaltyProgramResponse,
    OnboardingCompletionResponse,
    PaymentMethodCreateRequest,
    PaymentMethodResponse,
    PaymentMethodUpdateRequest,
    ProfileSummaryResponse,
    TravelerCreateRequest,
    TravelerGroupCreateRequest,
    TravelerGroupResponse,
    TravelerGroupUpdateRequest,
    TravelerResponse,
    TravelerUpdateRequest,
    TripTemplateCreateRequest,
    TripTemplateResponse,
    TripTemplateUpdateRequest,
    UserPreferenceResponse,
    UserPreferenceUpsertRequest,
    UserSettingsResponse,
    UserSettingsUpdateRequest,
)
from app.db.models import (
    Alliance,
    LoyaltyAccount,
    NotificationChannel,
    PaymentMethod,
    ProgramType,
    Traveler,
    TravelerGroup,
    TripTemplate,
    User,
    UserPreference,
)
from app.db.session import get_db_session
from app.security.crypto import decrypt_with_app_secret, encrypt_with_app_secret
from app.travel_readiness import build_household_workspace_summary

router = APIRouter()


def _require_value(value: object, *, field_name: str) -> object:
    if value is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"{field_name} may not be null.",
        )
    return value


def _passport_aad(*, user_id: UUID, traveler_id: UUID) -> str:
    return f"user:{user_id}:traveler:{traveler_id}:passport"


def _payment_aad(*, user_id: UUID, payment_method_id: UUID) -> str:
    return f"user:{user_id}:payment-method:{payment_method_id}"


def _payment_address_aad(*, user_id: UUID, payment_method_id: UUID) -> str:
    return f"user:{user_id}:payment-method:{payment_method_id}:billing-address"


def _parse_uuid_list(*, values: list[str], field_name: str) -> list[UUID]:
    parsed: list[UUID] = []
    for value in values:
        try:
            parsed.append(UUID(value))
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"{field_name} must contain valid UUID values.",
            ) from exc
    return parsed


def _validate_traveler_ids_owned(
    *, db: Session, user: User, traveler_ids: list[UUID]
) -> list[UUID]:
    if not traveler_ids:
        return []

    unique_traveler_ids = list(dict.fromkeys(traveler_ids))
    owned_traveler_ids = set(
        db.scalars(
            select(Traveler.id).where(
                Traveler.user_id == user.id,
                Traveler.id.in_(unique_traveler_ids),
            )
        )
    )
    if len(owned_traveler_ids) != len(unique_traveler_ids):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Traveler groups may only reference the current user's travelers.",
        )
    return unique_traveler_ids


def _get_traveler_or_404(*, db: Session, user: User, traveler_id: UUID) -> Traveler:
    traveler = db.scalar(
        select(Traveler).where(Traveler.id == traveler_id, Traveler.user_id == user.id)
    )
    if traveler is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Traveler not found.")
    return traveler


def _get_traveler_group_or_404(
    *, db: Session, user: User, traveler_group_id: UUID
) -> TravelerGroup:
    traveler_group = db.scalar(
        select(TravelerGroup).where(
            TravelerGroup.id == traveler_group_id, TravelerGroup.user_id == user.id
        )
    )
    if traveler_group is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Traveler group not found."
        )
    return traveler_group


def _get_payment_method_or_404(
    *, db: Session, user: User, payment_method_id: UUID
) -> PaymentMethod:
    payment_method = db.scalar(
        select(PaymentMethod).where(
            PaymentMethod.id == payment_method_id, PaymentMethod.user_id == user.id
        )
    )
    if payment_method is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Payment method not found."
        )
    return payment_method


def _get_trip_template_or_404(*, db: Session, user: User, template_id: UUID) -> TripTemplate:
    template = db.scalar(
        select(TripTemplate).where(TripTemplate.id == template_id, TripTemplate.user_id == user.id)
    )
    if template is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Trip template not found."
        )
    return template


def _get_user_preference(*, db: Session, user: User) -> UserPreference | None:
    return db.scalar(select(UserPreference).where(UserPreference.user_id == user.id))


def _get_or_create_user_preference(*, db: Session, user: User) -> UserPreference:
    preference = _get_user_preference(db=db, user=user)
    if preference is not None:
        return preference

    preference = UserPreference(user_id=user.id)
    db.add(preference)
    db.flush()
    return preference


def _serialize_settings(user: User) -> UserSettingsResponse:
    return UserSettingsResponse(
        id=str(user.id),
        email=user.email,
        role=user.role.value,
        onboarding_completed=user.onboarding_completed,
        default_notify_channel=user.default_notify_channel,
        telegram_chat_id=user.telegram_chat_id,
        totp_enabled=bool(user.totp_secret),
        global_max_auto_book_amount=user.global_max_auto_book_amount,
        weekly_max_spend=user.weekly_max_spend,
        weekly_max_bookings=user.weekly_max_bookings,
        annual_travel_budget=user.annual_travel_budget,
        annual_budget_currency=user.annual_budget_currency,
    )


def _serialize_user_preference(preference: UserPreference | None) -> UserPreferenceResponse:
    if preference is None:
        return UserPreferenceResponse(
            home_airports=[],
            default_cabin=None,
            default_luxury_vs_savings=0.6,
            preferred_airlines=[],
            avoided_airlines=[],
            preferred_alliances=[],
            preferred_hotel_brands=[],
            avoided_hotel_brands=[],
            default_hotel_min_rating=None,
            avoid_redeye=False,
            default_max_layover_minutes=None,
            default_min_connection_minutes=None,
            default_outbound_window=None,
            default_return_window=None,
            prefer_refundable=False,
            seat_auto_select=False,
            default_notify_channel=NotificationChannel.INHERIT,
            quiet_hours_start=None,
            quiet_hours_end=None,
        )

    return UserPreferenceResponse(
        home_airports=list(preference.home_airports or []),
        default_cabin=preference.default_cabin,
        default_luxury_vs_savings=preference.default_luxury_vs_savings,
        preferred_airlines=list(preference.preferred_airlines or []),
        avoided_airlines=list(preference.avoided_airlines or []),
        preferred_alliances=list(preference.preferred_alliances or []),
        preferred_hotel_brands=list(preference.preferred_hotel_brands or []),
        avoided_hotel_brands=list(preference.avoided_hotel_brands or []),
        default_hotel_min_rating=preference.default_hotel_min_rating,
        avoid_redeye=preference.avoid_redeye,
        default_max_layover_minutes=preference.default_max_layover_minutes,
        default_min_connection_minutes=preference.default_min_connection_minutes,
        default_outbound_window=preference.default_outbound_window_json,
        default_return_window=preference.default_return_window_json,
        prefer_refundable=preference.prefer_refundable,
        seat_auto_select=preference.seat_auto_select,
        default_notify_channel=preference.default_notify_channel,
        quiet_hours_start=preference.quiet_hours_start,
        quiet_hours_end=preference.quiet_hours_end,
    )


def _decrypt_passport_number(*, traveler: Traveler, user: User) -> str | None:
    if not traveler.passport_number_enc:
        return None
    return decrypt_with_app_secret(
        ciphertext=traveler.passport_number_enc,
        aad=_passport_aad(user_id=user.id, traveler_id=traveler.id),
    )


def _list_loyalty_accounts(*, db: Session, traveler: Traveler) -> list[LoyaltyAccount]:
    return list(
        db.scalars(
            select(LoyaltyAccount)
            .where(
                LoyaltyAccount.traveler_id == traveler.id,
                LoyaltyAccount.program_type == ProgramType.AIRLINE,
            )
            .order_by(
                LoyaltyAccount.preferred_earning_for_alliance.desc(),
                LoyaltyAccount.program_code.asc(),
                LoyaltyAccount.id.asc(),
            )
        )
    )


def _get_primary_loyalty_account(*, db: Session, traveler: Traveler) -> LoyaltyAccount | None:
    loyalty_accounts = _list_loyalty_accounts(db=db, traveler=traveler)
    return loyalty_accounts[0] if loyalty_accounts else None


def _sync_loyalty_accounts(
    *,
    db: Session,
    traveler: Traveler,
    loyalty_programs: list[LoyaltyProgramModel],
) -> None:
    existing_accounts = {
        (account.program_type, account.program_code): account
        for account in _list_loyalty_accounts(db=db, traveler=traveler)
    }
    incoming_keys = {(program.program_type, program.program_code) for program in loyalty_programs}

    for existing_key, existing_account in existing_accounts.items():
        if existing_key not in incoming_keys:
            db.delete(existing_account)

    for program in loyalty_programs:
        account = existing_accounts.get((program.program_type, program.program_code))
        if account is None:
            account = LoyaltyAccount(
                traveler_id=traveler.id,
                program_type=program.program_type,
                program_code=program.program_code,
            )
        account.account_number = program.account_number
        account.alliance = program.alliance or Alliance.NONE
        account.status_tier = program.status_tier
        account.preferred_earning_for_alliance = program.is_favorite
        db.add(account)


def _upsert_primary_loyalty_account(
    *,
    db: Session,
    traveler: Traveler,
    program_code: str | None,
    account_number: str | None,
    alliance,
    status_tier: str | None,
    preferred_earning_for_alliance: bool,
) -> None:
    loyalty_account = _get_primary_loyalty_account(db=db, traveler=traveler)

    if not program_code and not account_number:
        if loyalty_account is not None:
            db.delete(loyalty_account)
        return

    if not program_code or not account_number:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="loyalty_program_code and loyalty_account_number must be set together.",
        )

    if loyalty_account is None:
        loyalty_account = LoyaltyAccount(
            traveler_id=traveler.id,
            program_type=ProgramType.AIRLINE,
            program_code=program_code,
            alliance=alliance or Alliance.NONE,
            account_number=account_number,
            status_tier=status_tier,
            preferred_earning_for_alliance=preferred_earning_for_alliance,
        )
    else:
        loyalty_account.program_code = program_code
        loyalty_account.account_number = account_number
        loyalty_account.alliance = alliance or Alliance.NONE
        loyalty_account.status_tier = status_tier
        loyalty_account.preferred_earning_for_alliance = preferred_earning_for_alliance

    db.add(loyalty_account)


def _serialize_traveler(*, db: Session, traveler: Traveler, user: User) -> TravelerResponse:
    loyalty_accounts = _list_loyalty_accounts(db=db, traveler=traveler)
    loyalty_account = loyalty_accounts[0] if loyalty_accounts else None
    return TravelerResponse(
        id=str(traveler.id),
        traveler_relationship=traveler.traveler_relationship,
        display_name=traveler.display_name,
        legal_first_name=traveler.legal_first_name,
        legal_last_name=traveler.legal_last_name,
        dob=traveler.dob,
        gender=traveler.gender,
        nationality=traveler.nationality,
        residency_country=traveler.residency_country,
        passport_number=_decrypt_passport_number(traveler=traveler, user=user),
        passport_country=traveler.passport_country,
        passport_expiry=traveler.passport_expiry,
        known_traveler_number=traveler.known_traveler_number,
        redress_number=traveler.redress_number,
        seat_pref=traveler.seat_pref,
        meal_pref=traveler.meal_pref,
        accessibility_needs=traveler.accessibility_needs,
        infant_on_lap=traveler.infant_on_lap,
        loyalty_program_code=loyalty_account.program_code if loyalty_account else None,
        loyalty_account_number=loyalty_account.account_number if loyalty_account else None,
        loyalty_alliance=loyalty_account.alliance if loyalty_account else None,
        loyalty_status_tier=loyalty_account.status_tier if loyalty_account else None,
        preferred_earning_for_alliance=(
            loyalty_account.preferred_earning_for_alliance if loyalty_account else False
        ),
        loyalty_programs=[
            LoyaltyProgramResponse(
                program_type=account.program_type,
                program_code=account.program_code,
                account_number=account.account_number,
                alliance=account.alliance,
                status_tier=account.status_tier,
                is_favorite=account.preferred_earning_for_alliance,
            )
            for account in loyalty_accounts
        ],
        created_at=traveler.created_at,
    )


def _serialize_traveler_group(traveler_group: TravelerGroup) -> TravelerGroupResponse:
    return TravelerGroupResponse(
        id=str(traveler_group.id),
        name=traveler_group.name,
        traveler_ids=[str(traveler_id) for traveler_id in traveler_group.traveler_ids],
    )


def _decrypt_payment_secret(*, payment_method: PaymentMethod, user: User) -> dict[str, object]:
    return json.loads(
        decrypt_with_app_secret(
            ciphertext=payment_method.encrypted_blob,
            aad=_payment_aad(user_id=user.id, payment_method_id=payment_method.id),
        )
    )


def _decrypt_billing_address(
    *,
    payment_method: PaymentMethod,
    user: User,
) -> BillingAddressModel | None:
    if not payment_method.billing_address_enc:
        return None

    raw_billing_address = json.loads(
        decrypt_with_app_secret(
            ciphertext=payment_method.billing_address_enc,
            aad=_payment_address_aad(user_id=user.id, payment_method_id=payment_method.id),
        )
    )
    return BillingAddressModel.model_validate(raw_billing_address)


def _serialize_payment_method(
    *, payment_method: PaymentMethod, user: User
) -> PaymentMethodResponse:
    secret = _decrypt_payment_secret(payment_method=payment_method, user=user)
    return PaymentMethodResponse(
        id=str(payment_method.id),
        label=payment_method.label,
        brand=payment_method.brand,
        last4=payment_method.last4,
        cardholder_name=secret.get("cardholder_name"),
        exp_month=secret.get("exp_month"),
        exp_year=secret.get("exp_year"),
        provider_token=payment_method.provider_token,
        billing_address=_decrypt_billing_address(payment_method=payment_method, user=user),
    )


def _serialize_trip_template(template: TripTemplate) -> TripTemplateResponse:
    return TripTemplateResponse(
        id=str(template.id),
        name=template.name,
        watch_payload=template.watch_payload_json,
    )


def _build_profile_summary(*, db: Session, user: User) -> ProfileSummaryResponse:
    preference = _get_user_preference(db=db, user=user)
    travelers = list(
        db.scalars(
            select(Traveler).where(Traveler.user_id == user.id).order_by(Traveler.created_at)
        )
    )
    traveler_groups = list(
        db.scalars(
            select(TravelerGroup)
            .where(TravelerGroup.user_id == user.id)
            .order_by(TravelerGroup.name)
        )
    )
    payment_methods = list(
        db.scalars(
            select(PaymentMethod)
            .where(PaymentMethod.user_id == user.id)
            .order_by(PaymentMethod.label)
        )
    )
    trip_templates = list(
        db.scalars(
            select(TripTemplate).where(TripTemplate.user_id == user.id).order_by(TripTemplate.name)
        )
    )
    household_summary = build_household_workspace_summary(
        user=user,
        travelers=travelers,
        traveler_group_count=len(traveler_groups),
        payment_methods=payment_methods,
        template_count=len(trip_templates),
    )

    return ProfileSummaryResponse(
        settings=_serialize_settings(user),
        preferences=_serialize_user_preference(preference),
        travelers=[
            _serialize_traveler(db=db, traveler=traveler, user=user) for traveler in travelers
        ],
        traveler_groups=[_serialize_traveler_group(group) for group in traveler_groups],
        payment_methods=[
            _serialize_payment_method(payment_method=payment_method, user=user)
            for payment_method in payment_methods
        ],
        trip_templates=[_serialize_trip_template(template) for template in trip_templates],
        household_summary=HouseholdWorkspaceSummaryResponse.model_validate(
            asdict(household_summary)
        ),
    )


def _apply_user_settings_update(*, user: User, payload: UserSettingsUpdateRequest) -> None:
    for field_name in (
        "default_notify_channel",
        "telegram_chat_id",
        "global_max_auto_book_amount",
        "weekly_max_spend",
        "weekly_max_bookings",
        "annual_travel_budget",
        "annual_budget_currency",
    ):
        if field_name in payload.model_fields_set:
            value = getattr(payload, field_name)
            if field_name == "default_notify_channel":
                value = _require_value(value, field_name=field_name)
            setattr(user, field_name, value)


def _apply_user_preference_update(
    *,
    preference: UserPreference,
    payload: UserPreferenceUpsertRequest,
) -> None:
    non_nullable_fields = {
        "default_luxury_vs_savings",
        "avoid_redeye",
        "prefer_refundable",
        "seat_auto_select",
        "default_notify_channel",
    }
    field_mapping = {
        "home_airports": "home_airports",
        "default_cabin": "default_cabin",
        "default_luxury_vs_savings": "default_luxury_vs_savings",
        "preferred_airlines": "preferred_airlines",
        "avoided_airlines": "avoided_airlines",
        "preferred_alliances": "preferred_alliances",
        "preferred_hotel_brands": "preferred_hotel_brands",
        "avoided_hotel_brands": "avoided_hotel_brands",
        "default_hotel_min_rating": "default_hotel_min_rating",
        "avoid_redeye": "avoid_redeye",
        "default_max_layover_minutes": "default_max_layover_minutes",
        "default_min_connection_minutes": "default_min_connection_minutes",
        "prefer_refundable": "prefer_refundable",
        "seat_auto_select": "seat_auto_select",
        "default_notify_channel": "default_notify_channel",
        "quiet_hours_start": "quiet_hours_start",
        "quiet_hours_end": "quiet_hours_end",
    }
    for request_field, model_field in field_mapping.items():
        if request_field in payload.model_fields_set:
            value = getattr(payload, request_field)
            if request_field in non_nullable_fields:
                value = _require_value(value, field_name=request_field)
            setattr(preference, model_field, value)

    if "default_outbound_window" in payload.model_fields_set:
        preference.default_outbound_window_json = (
            payload.default_outbound_window.model_dump(exclude_none=True)
            if hasattr(payload.default_outbound_window, "model_dump")
            else payload.default_outbound_window
        )
    if "default_return_window" in payload.model_fields_set:
        preference.default_return_window_json = (
            payload.default_return_window.model_dump(exclude_none=True)
            if hasattr(payload.default_return_window, "model_dump")
            else payload.default_return_window
        )


@router.get("", response_model=ProfileSummaryResponse)
async def get_profile(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> ProfileSummaryResponse:
    return _build_profile_summary(db=db, user=current_user)


@router.get("/settings", response_model=UserSettingsResponse)
async def get_settings(current_user: User = Depends(get_current_user)) -> UserSettingsResponse:
    return _serialize_settings(current_user)


@router.patch("/settings", response_model=UserSettingsResponse)
async def update_settings(
    payload: UserSettingsUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> UserSettingsResponse:
    _apply_user_settings_update(user=current_user, payload=payload)
    db.add(current_user)
    db.commit()
    db.refresh(current_user)
    return _serialize_settings(current_user)


@router.post("/onboarding/complete", response_model=OnboardingCompletionResponse)
async def complete_onboarding(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> OnboardingCompletionResponse:
    current_user.onboarding_completed = True
    db.add(current_user)
    db.commit()
    db.refresh(current_user)
    return OnboardingCompletionResponse(onboarding_completed=current_user.onboarding_completed)


@router.get("/preferences", response_model=UserPreferenceResponse)
async def get_preferences(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> UserPreferenceResponse:
    preference = _get_user_preference(db=db, user=current_user)
    return _serialize_user_preference(preference)


@router.put("/preferences", response_model=UserPreferenceResponse)
async def upsert_preferences(
    payload: UserPreferenceUpsertRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> UserPreferenceResponse:
    preference = _get_or_create_user_preference(db=db, user=current_user)
    _apply_user_preference_update(preference=preference, payload=payload)
    db.add(preference)
    db.commit()
    db.refresh(preference)
    return _serialize_user_preference(preference)


@router.get("/travelers", response_model=list[TravelerResponse])
async def list_travelers(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> list[TravelerResponse]:
    travelers = list(
        db.scalars(
            select(Traveler)
            .where(Traveler.user_id == current_user.id)
            .order_by(Traveler.created_at)
        )
    )
    return [
        _serialize_traveler(db=db, traveler=traveler, user=current_user) for traveler in travelers
    ]


@router.post("/travelers", response_model=TravelerResponse, status_code=status.HTTP_201_CREATED)
async def create_traveler(
    payload: TravelerCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> TravelerResponse:
    traveler = Traveler(
        id=uuid4(),
        user_id=current_user.id,
        traveler_relationship=payload.traveler_relationship,
        display_name=payload.display_name,
        legal_first_name=payload.legal_first_name,
        legal_last_name=payload.legal_last_name,
        dob=payload.dob,
        gender=payload.gender,
        nationality=payload.nationality,
        residency_country=payload.residency_country,
        passport_country=payload.passport_country,
        passport_expiry=payload.passport_expiry,
        known_traveler_number=payload.known_traveler_number,
        redress_number=payload.redress_number,
        seat_pref=payload.seat_pref,
        meal_pref=payload.meal_pref,
        accessibility_needs=payload.accessibility_needs,
        infant_on_lap=payload.infant_on_lap,
    )
    if payload.passport_number:
        traveler.passport_number_enc = encrypt_with_app_secret(
            plaintext=payload.passport_number,
            aad=_passport_aad(user_id=current_user.id, traveler_id=traveler.id),
        )

    db.add(traveler)
    _sync_loyalty_accounts(db=db, traveler=traveler, loyalty_programs=payload.loyalty_programs)
    db.commit()
    db.refresh(traveler)
    return _serialize_traveler(db=db, traveler=traveler, user=current_user)


@router.patch("/travelers/{traveler_id}", response_model=TravelerResponse)
async def update_traveler(
    traveler_id: UUID,
    payload: TravelerUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> TravelerResponse:
    traveler = _get_traveler_or_404(db=db, user=current_user, traveler_id=traveler_id)

    non_nullable_fields = {
        "traveler_relationship",
        "display_name",
        "legal_first_name",
        "legal_last_name",
        "dob",
        "nationality",
        "seat_pref",
        "infant_on_lap",
    }
    for field_name in (
        "traveler_relationship",
        "display_name",
        "legal_first_name",
        "legal_last_name",
        "dob",
        "gender",
        "nationality",
        "residency_country",
        "known_traveler_number",
        "redress_number",
        "seat_pref",
        "meal_pref",
        "accessibility_needs",
        "infant_on_lap",
    ):
        if field_name in payload.model_fields_set:
            value = getattr(payload, field_name)
            if field_name in non_nullable_fields:
                value = _require_value(value, field_name=field_name)
            setattr(traveler, field_name, value)

    passport_fields = {"passport_number", "passport_country", "passport_expiry"}
    if payload.model_fields_set & passport_fields:
        passport_number = (
            payload.passport_number
            if "passport_number" in payload.model_fields_set
            else _decrypt_passport_number(traveler=traveler, user=current_user)
        )
        passport_country = (
            payload.passport_country
            if "passport_country" in payload.model_fields_set
            else traveler.passport_country
        )
        passport_expiry = (
            payload.passport_expiry
            if "passport_expiry" in payload.model_fields_set
            else traveler.passport_expiry
        )

        if passport_number is None and passport_country is None and passport_expiry is None:
            traveler.passport_number_enc = None
            traveler.passport_country = None
            traveler.passport_expiry = None
        elif passport_number and passport_country and passport_expiry:
            traveler.passport_number_enc = encrypt_with_app_secret(
                plaintext=passport_number,
                aad=_passport_aad(user_id=current_user.id, traveler_id=traveler.id),
            )
            traveler.passport_country = passport_country
            traveler.passport_expiry = passport_expiry
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="passport_number, passport_country, and passport_expiry must be set together.",
            )

    loyalty_fields = {
        "loyalty_program_code",
        "loyalty_account_number",
        "loyalty_alliance",
        "loyalty_status_tier",
        "preferred_earning_for_alliance",
    }
    if "loyalty_programs" in payload.model_fields_set:
        _sync_loyalty_accounts(
            db=db,
            traveler=traveler,
            loyalty_programs=payload.loyalty_programs or [],
        )
    elif payload.model_fields_set & loyalty_fields:
        current_loyalty = _get_primary_loyalty_account(db=db, traveler=traveler)
        program_code = (
            payload.loyalty_program_code
            if "loyalty_program_code" in payload.model_fields_set
            else (current_loyalty.program_code if current_loyalty else None)
        )
        account_number = (
            payload.loyalty_account_number
            if "loyalty_account_number" in payload.model_fields_set
            else (current_loyalty.account_number if current_loyalty else None)
        )
        alliance = (
            payload.loyalty_alliance
            if "loyalty_alliance" in payload.model_fields_set
            else (current_loyalty.alliance if current_loyalty else None)
        )
        status_tier = (
            payload.loyalty_status_tier
            if "loyalty_status_tier" in payload.model_fields_set
            else (current_loyalty.status_tier if current_loyalty else None)
        )
        preferred_earning = (
            payload.preferred_earning_for_alliance
            if "preferred_earning_for_alliance" in payload.model_fields_set
            else (current_loyalty.preferred_earning_for_alliance if current_loyalty else False)
        )
        _upsert_primary_loyalty_account(
            db=db,
            traveler=traveler,
            program_code=program_code,
            account_number=account_number,
            alliance=alliance,
            status_tier=status_tier,
            preferred_earning_for_alliance=preferred_earning,
        )

    db.add(traveler)
    db.commit()
    db.refresh(traveler)
    return _serialize_traveler(db=db, traveler=traveler, user=current_user)


@router.delete("/travelers/{traveler_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_traveler(
    traveler_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> None:
    traveler = _get_traveler_or_404(db=db, user=current_user, traveler_id=traveler_id)
    db.delete(traveler)
    db.commit()


@router.get("/traveler-groups", response_model=list[TravelerGroupResponse])
async def list_traveler_groups(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> list[TravelerGroupResponse]:
    traveler_groups = list(
        db.scalars(
            select(TravelerGroup)
            .where(TravelerGroup.user_id == current_user.id)
            .order_by(TravelerGroup.name)
        )
    )
    return [_serialize_traveler_group(group) for group in traveler_groups]


@router.post(
    "/traveler-groups",
    response_model=TravelerGroupResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_traveler_group(
    payload: TravelerGroupCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> TravelerGroupResponse:
    traveler_ids = _validate_traveler_ids_owned(
        db=db,
        user=current_user,
        traveler_ids=_parse_uuid_list(values=payload.traveler_ids, field_name="traveler_ids"),
    )
    traveler_group = TravelerGroup(
        user_id=current_user.id,
        name=payload.name,
        traveler_ids=traveler_ids,
    )
    db.add(traveler_group)
    db.commit()
    db.refresh(traveler_group)
    return _serialize_traveler_group(traveler_group)


@router.patch("/traveler-groups/{traveler_group_id}", response_model=TravelerGroupResponse)
async def update_traveler_group(
    traveler_group_id: UUID,
    payload: TravelerGroupUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> TravelerGroupResponse:
    traveler_group = _get_traveler_group_or_404(
        db=db,
        user=current_user,
        traveler_group_id=traveler_group_id,
    )
    if "name" in payload.model_fields_set:
        traveler_group.name = _require_value(payload.name, field_name="name")
    if "traveler_ids" in payload.model_fields_set:
        traveler_group.traveler_ids = _validate_traveler_ids_owned(
            db=db,
            user=current_user,
            traveler_ids=_parse_uuid_list(
                values=payload.traveler_ids or [], field_name="traveler_ids"
            ),
        )

    db.add(traveler_group)
    db.commit()
    db.refresh(traveler_group)
    return _serialize_traveler_group(traveler_group)


@router.delete("/traveler-groups/{traveler_group_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_traveler_group(
    traveler_group_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> None:
    traveler_group = _get_traveler_group_or_404(
        db=db,
        user=current_user,
        traveler_group_id=traveler_group_id,
    )
    db.delete(traveler_group)
    db.commit()


@router.get("/payment-methods", response_model=list[PaymentMethodResponse])
async def list_payment_methods(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> list[PaymentMethodResponse]:
    payment_methods = list(
        db.scalars(
            select(PaymentMethod)
            .where(PaymentMethod.user_id == current_user.id)
            .order_by(PaymentMethod.label)
        )
    )
    return [
        _serialize_payment_method(payment_method=payment_method, user=current_user)
        for payment_method in payment_methods
    ]


@router.post(
    "/payment-methods",
    response_model=PaymentMethodResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_payment_method(
    payload: PaymentMethodCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> PaymentMethodResponse:
    payment_method = PaymentMethod(
        id=uuid4(),
        user_id=current_user.id,
        label=payload.label,
        brand=payload.brand,
        last4=payload.card_number[-4:],
        provider_token=payload.provider_token,
    )
    payment_method.encrypted_blob = encrypt_with_app_secret(
        plaintext=json.dumps(
            {
                "cardholder_name": payload.cardholder_name,
                "card_number": payload.card_number,
                "exp_month": payload.exp_month,
                "exp_year": payload.exp_year,
            }
        ),
        aad=_payment_aad(user_id=current_user.id, payment_method_id=payment_method.id),
    )
    if payload.billing_address is not None:
        payment_method.billing_address_enc = encrypt_with_app_secret(
            plaintext=json.dumps(payload.billing_address.model_dump(exclude_none=True)),
            aad=_payment_address_aad(user_id=current_user.id, payment_method_id=payment_method.id),
        )

    db.add(payment_method)
    db.commit()
    db.refresh(payment_method)
    return _serialize_payment_method(payment_method=payment_method, user=current_user)


@router.patch("/payment-methods/{payment_method_id}", response_model=PaymentMethodResponse)
async def update_payment_method(
    payment_method_id: UUID,
    payload: PaymentMethodUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> PaymentMethodResponse:
    payment_method = _get_payment_method_or_404(
        db=db,
        user=current_user,
        payment_method_id=payment_method_id,
    )

    if "label" in payload.model_fields_set:
        payment_method.label = _require_value(payload.label, field_name="label")
    if "brand" in payload.model_fields_set:
        payment_method.brand = payload.brand
    if "provider_token" in payload.model_fields_set:
        payment_method.provider_token = payload.provider_token

    secret = _decrypt_payment_secret(payment_method=payment_method, user=current_user)
    if "cardholder_name" in payload.model_fields_set:
        secret["cardholder_name"] = payload.cardholder_name
    if "card_number" in payload.model_fields_set:
        secret["card_number"] = payload.card_number
        payment_method.last4 = payload.card_number[-4:] if payload.card_number else None
    if "exp_month" in payload.model_fields_set:
        secret["exp_month"] = payload.exp_month
    if "exp_year" in payload.model_fields_set:
        secret["exp_year"] = payload.exp_year

    payment_method.encrypted_blob = encrypt_with_app_secret(
        plaintext=json.dumps(secret),
        aad=_payment_aad(user_id=current_user.id, payment_method_id=payment_method.id),
    )

    if "billing_address" in payload.model_fields_set:
        if payload.billing_address is None:
            payment_method.billing_address_enc = None
        else:
            payment_method.billing_address_enc = encrypt_with_app_secret(
                plaintext=json.dumps(payload.billing_address.model_dump(exclude_none=True)),
                aad=_payment_address_aad(
                    user_id=current_user.id, payment_method_id=payment_method.id
                ),
            )

    db.add(payment_method)
    db.commit()
    db.refresh(payment_method)
    return _serialize_payment_method(payment_method=payment_method, user=current_user)


@router.delete("/payment-methods/{payment_method_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_payment_method(
    payment_method_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> None:
    payment_method = _get_payment_method_or_404(
        db=db,
        user=current_user,
        payment_method_id=payment_method_id,
    )
    db.delete(payment_method)
    db.commit()


@router.get("/trip-templates", response_model=list[TripTemplateResponse])
async def list_trip_templates(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> list[TripTemplateResponse]:
    templates = list(
        db.scalars(
            select(TripTemplate)
            .where(TripTemplate.user_id == current_user.id)
            .order_by(TripTemplate.name)
        )
    )
    return [_serialize_trip_template(template) for template in templates]


@router.post(
    "/trip-templates", response_model=TripTemplateResponse, status_code=status.HTTP_201_CREATED
)
async def create_trip_template(
    payload: TripTemplateCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> TripTemplateResponse:
    template = TripTemplate(
        user_id=current_user.id,
        name=payload.name,
        watch_payload_json=payload.watch_payload,
    )
    db.add(template)
    db.commit()
    db.refresh(template)
    return _serialize_trip_template(template)


@router.patch("/trip-templates/{template_id}", response_model=TripTemplateResponse)
async def update_trip_template(
    template_id: UUID,
    payload: TripTemplateUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> TripTemplateResponse:
    template = _get_trip_template_or_404(db=db, user=current_user, template_id=template_id)
    if "name" in payload.model_fields_set:
        template.name = _require_value(payload.name, field_name="name")
    if "watch_payload" in payload.model_fields_set:
        template.watch_payload_json = payload.watch_payload

    db.add(template)
    db.commit()
    db.refresh(template)
    return _serialize_trip_template(template)


@router.delete("/trip-templates/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_trip_template(
    template_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> None:
    template = _get_trip_template_or_404(db=db, user=current_user, template_id=template_id)
    db.delete(template)
    db.commit()
