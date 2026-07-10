from __future__ import annotations

from app.integrations.types import (
    IntegrationAcquisitionGuide,
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
        validation_help=(
            "Get these from developers.amadeus.com: create a Self-Service app to receive "
            "an API Key (client_id) and API Secret (client_secret)."
        ),
        guide=IntegrationAcquisitionGuide(
            signup_url=(
                "https://developers.amadeus.com/self-service/apis-docs/guides/"
                "developer-guides/quick-start/"
            ),
            application_url=(
                "https://developers.amadeus.com/self-service/apis-docs/guides/"
                "developer-guides/API-Keys/moving-to-production/"
            ),
            account_requirements=(
                "An Amadeus for Developers account with access to the Self-Service workspace.",
                "A separate application in the workspace for the credentials you plan to use.",
            ),
            steps=(
                "Open the official quick start and create or sign in to your developer account.",
                "Create a Self-Service application in the Amadeus workspace.",
                "Copy the test API key into Client ID and the test API secret into Client secret.",
                "Save the credential profile, link it to this connector, and run Test connection.",
                "Use the official production guide before requesting production access.",
            ),
            environment_notes=(
                "New Self-Service applications start with test credentials and test endpoints.",
                (
                    "Production access is a separate process with eligibility and "
                    "commercial requirements."
                ),
                "TRAMP currently keeps this connector simulated, even when live mode is selected.",
            ),
            enables=(
                "Reusable Amadeus credentials for compatible TRAMP connectors.",
                "Saved credential validation and local connection diagnostics.",
                "Configuration needed for future live Amadeus flight search wiring.",
            ),
        ),
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
        validation_help=(
            "Get this from duffel.com/docs: create a test or live access token in the "
            "Duffel dashboard under Developers -> Access tokens."
        ),
        guide=IntegrationAcquisitionGuide(
            signup_url="https://duffel.com/docs/api/overview/making-requests",
            application_url="https://duffel.com/docs/guides/getting-started-with-flights",
            account_requirements=(
                "A Duffel account with access to the dashboard and developer tools.",
                "Live selling access and any required business checks before using a live token.",
            ),
            steps=(
                "Open the official authentication guide and sign in to the Duffel dashboard.",
                "Create a test access token under Developers and Access tokens.",
                "Paste the token into Access token, then save or create a reusable Duffel profile.",
                "Link the profile to this connector and run Test connection.",
                "Complete Duffel live access requirements before creating or using a live token.",
            ),
            environment_notes=(
                (
                    "Duffel test and live tokens are separate. Keep each token in the "
                    "matching TRAMP environment."
                ),
                "Live access can require activation and compliance steps in your Duffel account.",
                "TRAMP currently keeps this connector simulated, even when live mode is selected.",
            ),
            enables=(
                "Reusable Duffel credentials for Flights and Booking configuration.",
                "Saved token validation and local connection diagnostics.",
                "Configuration needed for future live Duffel flight and order wiring.",
            ),
        ),
    ),
    IntegrationCatalogEntry(
        key="flights_kiwi",
        label="Flights · Kiwi",
        description=(
            "Kiwi Tequila flight shopping connector used during multi-provider watch search."
        ),
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
        validation_help=(
            "Start at tequila.kiwi.com. Kiwi partner access is more approval-driven, so "
            "production credentials may require affiliate/partner onboarding."
        ),
        guide=IntegrationAcquisitionGuide(
            signup_url="https://tequila.kiwi.com/",
            account_requirements=(
                "A Kiwi partner or affiliate relationship that is eligible for Tequila access.",
                "Approval from Kiwi for the requested API use case when required.",
            ),
            steps=(
                "Open the official Kiwi Tequila portal and review the current partner access path.",
                "Submit the requested partner or affiliate information for your use case.",
                (
                    "Wait for Kiwi approval and credential issuance. Access is not "
                    "guaranteed or instant."
                ),
                "Paste the issued key into Tequila API key, save it, and run Test connection.",
            ),
            environment_notes=(
                (
                    "Kiwi controls access and may restrict new API credentials or "
                    "available capabilities."
                ),
                (
                    "Test and production terms depend on the access Kiwi grants to your "
                    "partner account."
                ),
                "TRAMP currently keeps this connector simulated, even when live mode is selected.",
            ),
            enables=(
                "Kiwi credential storage after partner approval.",
                "Saved key validation and local connection diagnostics.",
                "Configuration needed for future Kiwi flight search wiring.",
            ),
        ),
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
        guide=IntegrationAcquisitionGuide(
            signup_url="https://developer.hotelbeds.com/documentation/getting-started/",
            application_url="https://developers.booking.com/demand",
            account_requirements=(
                "An account approved by the hotel inventory provider you select.",
                (
                    "Provider-specific commercial, billing, or partner details when that "
                    "provider asks for them."
                ),
            ),
            steps=(
                "Choose one hotel provider before entering credentials.",
                "For Hotelbeds, follow the official getting started guide linked here.",
                "For Booking.com, review the official Demand API portal linked here.",
                "Complete the selected provider's access process and obtain its own credentials.",
                (
                    "Enter that provider label and key in TRAMP. One credential does not "
                    "cover other providers."
                ),
                "Save the connector and run Test connection.",
            ),
            environment_notes=(
                (
                    "Sandbox, test, and production access are defined separately by each "
                    "hotel provider."
                ),
                "Do not reuse a Hotelbeds key for Booking.com or any other provider.",
                (
                    "TRAMP currently uses local-safe hotel behavior and does not perform "
                    "live hotel searches."
                ),
            ),
            enables=(
                "Provider-specific hotel credential configuration.",
                "Masked storage and local diagnostics for the selected provider.",
                "Configuration needed for future live hotel inventory wiring.",
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
                help_text=(
                    "Choose the provider family this booking connector should use when "
                    "linked to a shared credential profile."
                ),
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
                help_text=(
                    "Required for providers that use key/secret authentication, such as "
                    "Amadeus-style setups."
                ),
            ),
            IntegrationCredentialField(
                key="account_id",
                label="Account ID",
                placeholder="Optional account identifier",
                help_text="Optional account or organization identifier for the selected provider.",
                sensitive=False,
            ),
        ),
        validation_help=(
            "Booking connectors can link to a shared flight-provider profile. If not "
            "linked, store booking credentials here and keep sensitive values write-only."
        ),
        guide=IntegrationAcquisitionGuide(
            signup_url="https://duffel.com/docs/guides/getting-started-with-flights",
            application_url=(
                "https://developers.amadeus.com/self-service/apis-docs/guides/"
                "developer-guides/quick-start/"
            ),
            account_requirements=(
                "An account with the provider that will execute the booking.",
                (
                    "Booking, order, or ticketing permission from that provider, not only "
                    "search access."
                ),
            ),
            steps=(
                "Choose the booking provider first. Credentials are provider-specific.",
                "Use the linked official Duffel or Amadeus guide for those provider families.",
                (
                    "For Kiwi, start at https://tequila.kiwi.com/ and wait for any required "
                    "partner approval."
                ),
                (
                    "For Booking.com Demand API, start at "
                    "https://developers.booking.com/demand and use a separate approved account."
                ),
                (
                    "Confirm that the issued credentials include the booking capability "
                    "your workflow needs."
                ),
                (
                    "Create or select the matching shared profile, save the connector, "
                    "and run Test connection."
                ),
            ),
            environment_notes=(
                "Search access does not automatically grant booking, order, or ticketing access.",
                (
                    "Keep test credentials separate from production credentials for the "
                    "selected provider."
                ),
                (
                    "TRAMP currently uses a local-safe booking connector and does not "
                    "place live bookings."
                ),
            ),
            enables=(
                "Provider-specific booking credential configuration.",
                "Shared credential reuse between compatible Flights and Booking connectors.",
                "Configuration needed for future live booking and cancellation wiring.",
            ),
        ),
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
        validation_help=(
            "log_only needs no credentials, smtp_dev needs smtp_host and smtp_from_address, "
            "telegram_bot needs telegram_bot_token."
        ),
        guide=IntegrationAcquisitionGuide(
            signup_url="https://core.telegram.org/bots/tutorial",
            account_requirements=(
                "No external account or API key for log_only or a local Mailpit setup.",
                (
                    "Credentials from your chosen SMTP provider only when that SMTP server "
                    "requires authentication."
                ),
                "A Telegram account and a bot created through BotFather for telegram_bot mode.",
            ),
            steps=(
                "Choose log_only for local diagnostics with no external credentials.",
                "For local email testing, run Mailpit and use its local SMTP host and port.",
                (
                    "For hosted SMTP, enter credentials issued by your own SMTP provider. "
                    "There is no universal SMTP API key."
                ),
                (
                    "For Telegram, follow the official BotFather tutorial linked here and "
                    "copy the bot token."
                ),
                "Select the matching delivery mode, save the settings, and run Test connection.",
            ),
            environment_notes=(
                "log_only stays inside TRAMP and is the safest default.",
                (
                    "Mailpit is suitable for local capture. Hosted SMTP and Telegram "
                    "contact external services."
                ),
                (
                    "TRAMP local-safe connectors may record simulated delivery instead "
                    "of sending externally."
                ),
            ),
            enables=(
                "Local notification diagnostics without credentials.",
                "SMTP configuration using Mailpit or the user's SMTP provider.",
                "Telegram bot configuration using an official BotFather token.",
            ),
        ),
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
        validation_help=(
            "log_only needs no credentials, google_calendar needs calendar_id and "
            "access_token."
        ),
        guide=IntegrationAcquisitionGuide(
            signup_url="https://developers.google.com/workspace/calendar/api/quickstart/python",
            account_requirements=(
                "A Google account and a Google Cloud project.",
                "The Google Calendar API enabled for that project.",
                "An OAuth client and user consent for the calendar account you want to access.",
            ),
            steps=(
                "Follow the official Google Calendar quickstart linked here.",
                "Create or select a Google Cloud project and enable the Google Calendar API.",
                "Configure the OAuth consent screen and create the required OAuth client.",
                "Authorize the target Google account and obtain an access token for testing.",
                (
                    "Enter the calendar ID and access token, save the connector, and run "
                    "Test connection."
                ),
            ),
            environment_notes=(
                (
                    "Use log_only until Google OAuth is configured and approved for the "
                    "intended users."
                ),
                (
                    "OAuth access tokens can expire. A production integration normally "
                    "needs a secure refresh flow."
                ),
                (
                    "TRAMP currently uses local-safe calendar behavior and does not create "
                    "live Google events."
                ),
            ),
            enables=(
                "Google Calendar credential and calendar ID configuration.",
                "Saved OAuth token validation and local connection diagnostics.",
                "Configuration needed for future live event creation and cancellation wiring.",
            ),
        ),
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
