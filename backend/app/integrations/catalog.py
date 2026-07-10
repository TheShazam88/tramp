from __future__ import annotations

from app.integrations.types import (
    IntegrationCatalogEntry,
    IntegrationCredentialField,
    IntegrationFeatureFlagDefinition,
)

CATALOG: tuple[IntegrationCatalogEntry, ...] = (
    IntegrationCatalogEntry(
        key="flights_amadeus",
        label="Flights · Amadeus",
        description="Amadeus flight shopping connector used during multi-provider watch search.",
        category="flights",
        provider_key="amadeus",
        supports_shared_profile=True,
        compatible_profile_provider_keys=("amadeus",),
        credential_fields=(
            IntegrationCredentialField(
                key="client_id",
                label="API key / Client ID",
                placeholder="Amadeus API key",
                help_text="Create an app in the Amadeus Self-Service Workspace to get this value.",
            ),
            IntegrationCredentialField(
                key="client_secret",
                label="API secret / Client secret",
                placeholder="Amadeus API secret",
                help_text="Stored encrypted and used only when the live connector is implemented.",
            ),
            IntegrationCredentialField(
                key="provider",
                label="Provider label",
                placeholder="amadeus",
                help_text="Used in diagnostics and deal-source labeling.",
                sensitive=False,
            ),
        ),
        feature_flag_definitions=(
            IntegrationFeatureFlagDefinition(
                key="enable_live_search_shape",
                label="Live search shape",
                default_enabled=False,
                description="Allow the live-shaped connector path while remaining localhost safe.",
            ),
        ),
        validation_help="Get these from developers.amadeus.com: create a Self-Service app to receive an API Key (client_id) and API Secret (client_secret).",
    ),
    IntegrationCatalogEntry(
        key="flights_duffel",
        label="Flights · Duffel",
        description="Duffel flight shopping connector used during multi-provider watch search.",
        category="flights",
        provider_key="duffel",
        supports_shared_profile=True,
        compatible_profile_provider_keys=("duffel",),
        credential_fields=(
            IntegrationCredentialField(
                key="access_token",
                label="Access token",
                placeholder="duffel_test_...",
                help_text="Create this in Duffel Dashboard -> Developers -> Access tokens.",
            ),
            IntegrationCredentialField(
                key="provider",
                label="Provider label",
                placeholder="duffel",
                help_text="Used in diagnostics and deal-source labeling.",
                sensitive=False,
            ),
        ),
        feature_flag_definitions=(
            IntegrationFeatureFlagDefinition(
                key="enable_live_search_shape",
                label="Live search shape",
                default_enabled=False,
                description="Allow the live-shaped connector path while remaining localhost safe.",
            ),
        ),
        validation_help="Get this from duffel.com/docs: create a test or live access token in the Duffel dashboard under Developers -> Access tokens.",
    ),
    IntegrationCatalogEntry(
        key="flights_kiwi",
        label="Flights · Kiwi",
        description="Kiwi Tequila flight shopping connector used during multi-provider watch search.",
        category="flights",
        provider_key="kiwi",
        supports_shared_profile=True,
        compatible_profile_provider_keys=("kiwi",),
        credential_fields=(
            IntegrationCredentialField(
                key="api_key",
                label="Tequila API key",
                placeholder="Kiwi / Tequila partner key",
                help_text="Enter the Tequila key or token issued to your Kiwi partner account.",
            ),
            IntegrationCredentialField(
                key="provider",
                label="Provider label",
                placeholder="kiwi",
                help_text="Used in diagnostics and deal-source labeling.",
                sensitive=False,
            ),
        ),
        feature_flag_definitions=(
            IntegrationFeatureFlagDefinition(
                key="enable_live_search_shape",
                label="Live search shape",
                default_enabled=False,
                description="Allow the live-shaped connector path while remaining localhost safe.",
            ),
        ),
        validation_help="Start at tequila.kiwi.com. Kiwi partner access is more approval-driven, so production credentials may require affiliate/partner onboarding.",
    ),
    IntegrationCatalogEntry(
        key="hotels",
        label="Hotels",
        description="Controls hotel and car shopping connectors used by watch search.",
        category="hotels",
        credential_fields=(
            IntegrationCredentialField(
                key="api_key",
                label="API key",
                placeholder="Optional sandbox key",
                help_text="Optional for localhost; used only to mirror live-capable configuration.",
            ),
            IntegrationCredentialField(
                key="provider",
                label="Provider label",
                placeholder="booking, expedia, hotelbeds",
                help_text="Human-readable provider label used in diagnostics.",
                sensitive=False,
            ),
        ),
    ),
    IntegrationCatalogEntry(
        key="booking",
        label="Booking",
        description="Controls booking and cancellation connectors used during checkout.",
        category="booking",
        supports_shared_profile=True,
        compatible_profile_provider_keys=("duffel", "amadeus", "kiwi"),
        credential_fields=(
            IntegrationCredentialField(
                key="provider",
                label="Provider",
                placeholder="duffel",
                help_text="Choose the provider family this booking connector should use when linked to a shared credential profile.",
                sensitive=False,
            ),
            IntegrationCredentialField(
                key="access_token",
                label="Access token / API key",
                placeholder="Provider booking token",
                help_text="Used when the booking connector is not linked to a shared profile.",
            ),
            IntegrationCredentialField(
                key="api_secret",
                label="API secret",
                placeholder="Optional provider secret",
                help_text="Required for providers that use key/secret authentication, such as Amadeus-style setups.",
            ),
            IntegrationCredentialField(
                key="account_id",
                label="Account ID",
                placeholder="Optional account identifier",
                help_text="Optional account or organization identifier for the selected provider.",
                sensitive=False,
            ),
        ),
        validation_help="Booking connectors can link to a shared flight-provider profile. If not linked, store booking credentials here and keep sensitive values write-only.",
    ),
    IntegrationCatalogEntry(
        key="notifications",
        label="Notifications",
        description="Controls outbound notification connectors used for local/test delivery.",
        category="messaging",
        credential_fields=(
            IntegrationCredentialField(
                key="delivery_mode",
                label="Delivery mode",
                placeholder="log_only, smtp_dev, telegram_bot",
                help_text="Use log_only for localhost-safe dry runs.",
                sensitive=False,
            ),
            IntegrationCredentialField(
                key="smtp_host",
                label="SMTP host",
                placeholder="localhost",
                help_text="Required for smtp_dev mode.",
                sensitive=False,
            ),
            IntegrationCredentialField(
                key="smtp_port",
                label="SMTP port",
                placeholder="1025",
                help_text="Optional, defaults to 1025.",
                sensitive=False,
            ),
            IntegrationCredentialField(
                key="smtp_username",
                label="SMTP username",
                placeholder="Optional",
                help_text="Optional auth for smtp_dev.",
            ),
            IntegrationCredentialField(
                key="smtp_password",
                label="SMTP password",
                placeholder="Optional",
                help_text="Optional auth for smtp_dev.",
            ),
            IntegrationCredentialField(
                key="smtp_from_address",
                label="From address",
                placeholder="alerts@tramp.local",
                help_text="Required for smtp_dev mode.",
                sensitive=False,
            ),
            IntegrationCredentialField(
                key="telegram_bot_token",
                label="Telegram bot token",
                placeholder="123456:ABCDEF",
                help_text="Required for telegram_bot mode.",
            ),
        ),
        feature_flag_definitions=(
            IntegrationFeatureFlagDefinition(
                key="send_booking_updates",
                label="Booking updates",
                default_enabled=True,
                description="Send booking and cancellation notifications.",
            ),
            IntegrationFeatureFlagDefinition(
                key="send_disruption_updates",
                label="Disruption updates",
                default_enabled=True,
                description="Send disruption notifications.",
            ),
        ),
        validation_help="log_only needs no credentials, smtp_dev needs smtp_host and smtp_from_address, telegram_bot needs telegram_bot_token.",
    ),
    IntegrationCatalogEntry(
        key="calendar",
        label="Calendar",
        description="Controls booking calendar push and cancellation unwind behavior.",
        category="calendar",
        credential_fields=(
            IntegrationCredentialField(
                key="delivery_mode",
                label="Delivery mode",
                placeholder="log_only or google_calendar",
                help_text="Use log_only for localhost-safe dry runs.",
                sensitive=False,
            ),
            IntegrationCredentialField(
                key="calendar_id",
                label="Calendar ID",
                placeholder="primary",
                help_text="Required for google_calendar mode.",
                sensitive=False,
            ),
            IntegrationCredentialField(
                key="access_token",
                label="Access token",
                placeholder="OAuth access token",
                help_text="Required for google_calendar mode.",
            ),
        ),
        feature_flag_definitions=(
            IntegrationFeatureFlagDefinition(
                key="enable_conflict_check",
                label="Conflict check",
                default_enabled=False,
                description="Run calendar conflict advisories during validation.",
            ),
        ),
        validation_help="log_only needs no credentials, google_calendar needs calendar_id and access_token.",
    ),
)

CATALOG_BY_KEY = {entry.key: entry for entry in CATALOG}


def list_catalog_entries() -> list[IntegrationCatalogEntry]:
    return list(CATALOG)


def get_catalog_entry(key: str) -> IntegrationCatalogEntry:
    normalized = key.strip().lower()
    try:
        return CATALOG_BY_KEY[normalized]
    except KeyError as exc:
        raise LookupError(f"Unknown integration '{key}'.") from exc
