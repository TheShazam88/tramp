from __future__ import annotations

from app.integrations.types import (
    IntegrationAcquisitionGuide,
    IntegrationAcquisitionLink,
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
            "Test connection checks local credential presence and shape only. It does not "
            "call Amadeus."
        ),
        guide=IntegrationAcquisitionGuide(
            links=(
                IntegrationAcquisitionLink(
                    label="Amadeus quick start",
                    url=(
                        "https://developers.amadeus.com/self-service/apis-docs/guides/"
                        "developer-guides/quick-start/"
                    ),
                ),
                IntegrationAcquisitionLink(
                    label="Amadeus production access guide",
                    url=(
                        "https://developers.amadeus.com/self-service/apis-docs/guides/"
                        "developer-guides/API-Keys/moving-to-production/"
                    ),
                ),
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
                "Local credential presence and configuration shape checks.",
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
            "Test connection checks local token presence and shape only. It does not call Duffel."
        ),
        guide=IntegrationAcquisitionGuide(
            links=(
                IntegrationAcquisitionLink(
                    label="Duffel API authentication guide",
                    url="https://duffel.com/docs/api/overview/making-requests",
                ),
                IntegrationAcquisitionLink(
                    label="Duffel flights getting started",
                    url="https://duffel.com/docs/guides/getting-started-with-flights",
                ),
            ),
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
                "Local token presence and configuration shape checks.",
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
            "New Kiwi Tequila partnerships are invitation only. Test connection checks "
            "local key presence and shape and does not call Kiwi."
        ),
        guide=IntegrationAcquisitionGuide(
            links=(
                IntegrationAcquisitionLink(
                    label="Kiwi invitation-only partnership announcement",
                    url=(
                        "https://media.kiwi.com/articles-and-interviews/"
                        "better-for-business-kiwi-com-takes-a-new-approach-to-partnerships/"
                    ),
                ),
                IntegrationAcquisitionLink(
                    label="Kiwi Tequila portal",
                    url="https://tequila.kiwi.com/",
                ),
            ),
            account_requirements=(
                "An existing Kiwi partnership or a direct invitation from Kiwi.",
                "Credentials issued by Kiwi for the approved use case.",
            ),
            steps=(
                "Read Kiwi's official partnership announcement before planning this integration.",
                (
                    "New Tequila partnerships are invitation only. There is no public "
                    "credential application flow."
                ),
                "If Kiwi invites your organization, complete the onboarding it provides.",
                "Paste the issued key into Tequila API key, save it, and run Test connection.",
            ),
            environment_notes=(
                (
                    "Invitation only means the Tequila portal does not guarantee access "
                    "or instant credentials."
                ),
                (
                    "Test and production terms depend on the access Kiwi grants to your "
                    "partner account."
                ),
                "TRAMP currently keeps this connector simulated, even when live mode is selected.",
            ),
            enables=(
                "Kiwi credential storage after an invitation and onboarding.",
                "Local key presence and configuration shape checks.",
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
                key="provider",
                label="Provider label",
                placeholder="hotelbeds or booking",
                help_text="Choose a provider before entering provider-specific credentials.",
                sensitive=False,
            ),
            IntegrationCredentialField(
                key="api_key",
                label="Hotelbeds API key",
                placeholder="Hotelbeds API key",
                help_text="Required with the Hotelbeds API secret for Hotelbeds requests.",
            ),
            IntegrationCredentialField(
                key="api_secret",
                label="Hotelbeds API secret",
                placeholder="Hotelbeds API secret",
                help_text=(
                    "Hotelbeds requires this secret to generate the X-Signature "
                    "authentication header."
                ),
            ),
        ),
        validation_help=(
            "Test connection checks local credential presence and shape only and makes no "
            "hotel provider request. Hotelbeds requires an API key and API secret."
        ),
        guide=IntegrationAcquisitionGuide(
            links=(
                IntegrationAcquisitionLink(
                    label="Hotelbeds getting started",
                    url="https://developer.hotelbeds.com/documentation/getting-started/",
                ),
                IntegrationAcquisitionLink(
                    label="Booking.com Demand API",
                    url="https://developers.booking.com/demand",
                ),
            ),
            account_requirements=(
                "An account approved by the hotel inventory provider you select.",
                (
                    "Hotelbeds requires both an API Key and Secret. Booking.com Demand "
                    "uses its own separate access process."
                ),
            ),
            steps=(
                "Choose one hotel provider before entering credentials.",
                (
                    "For Hotelbeds, obtain both the API Key and Secret and generate the "
                    "required X-Signature on each future provider request."
                ),
                (
                    "For Booking.com, use its labeled Demand API link. This generic TRAMP "
                    "card does not yet define a Booking.com credential shape."
                ),
                "Enter only the fields shown for the selected provider.",
                "Save the connector and run Test connection.",
            ),
            environment_notes=(
                (
                    "Sandbox, test, and production access are defined separately by each "
                    "hotel provider."
                ),
                "Do not reuse Hotelbeds credentials for Booking.com or another provider.",
                (
                    "TRAMP currently uses local-safe hotel behavior and does not perform "
                    "live hotel searches."
                ),
            ),
            enables=(
                "Provider selection and complete Hotelbeds credential storage.",
                "Local credential presence and configuration shape checks.",
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
                    "Choose the direct credential shape. A linked shared profile supplies "
                    "its own provider family."
                ),
                sensitive=False,
            ),
            IntegrationCredentialField(
                key="access_token",
                label="Duffel access token",
                placeholder="duffel_test_...",
                help_text="Required for direct Duffel configuration.",
            ),
            IntegrationCredentialField(
                key="client_id",
                label="Amadeus Client ID",
                placeholder="Amadeus API key",
                help_text="Required with Client secret for direct Amadeus configuration.",
            ),
            IntegrationCredentialField(
                key="client_secret",
                label="Amadeus Client secret",
                placeholder="Amadeus API secret",
                help_text="Required with Client ID for direct Amadeus configuration.",
            ),
            IntegrationCredentialField(
                key="api_key",
                label="Kiwi Tequila API key",
                placeholder="Kiwi key issued by invitation",
                help_text="Required for direct Kiwi configuration after invitation-only access.",
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
            "Choose Duffel, Amadeus, or Kiwi and use its exact credential shape, or link "
            "a matching shared profile. Test connection is local and makes no provider request."
        ),
        guide=IntegrationAcquisitionGuide(
            links=(
                IntegrationAcquisitionLink(
                    label="Duffel flights getting started",
                    url="https://duffel.com/docs/guides/getting-started-with-flights",
                ),
                IntegrationAcquisitionLink(
                    label="Amadeus quick start",
                    url=(
                        "https://developers.amadeus.com/self-service/apis-docs/guides/"
                        "developer-guides/quick-start/"
                    ),
                ),
                IntegrationAcquisitionLink(
                    label="Kiwi invitation-only partnership announcement",
                    url=(
                        "https://media.kiwi.com/articles-and-interviews/"
                        "better-for-business-kiwi-com-takes-a-new-approach-to-partnerships/"
                    ),
                ),
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
                "Duffel direct mode requires access_token.",
                "Amadeus direct mode requires client_id and client_secret.",
                "Kiwi direct mode requires api_key after invitation-only access.",
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
                "Local credential presence and configuration shape checks.",
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
            "Test connection checks local presence and shape and does not send a message. "
            "Actual SMTP and Telegram deliveries can send externally."
        ),
        guide=IntegrationAcquisitionGuide(
            links=(
                IntegrationAcquisitionLink(
                    label="Telegram BotFather tutorial",
                    url="https://core.telegram.org/bots/tutorial",
                ),
            ),
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
                    "Mailpit is suitable for local capture. A hosted SMTP server sends "
                    "email outside TRAMP."
                ),
                (
                    "SMTP and Telegram can send externally when their delivery mode is "
                    "selected and a notification is delivered."
                ),
            ),
            enables=(
                "Local notification diagnostics without credentials.",
                "Real SMTP delivery through Mailpit or the user's SMTP provider.",
                "Real Telegram Bot API delivery using an official BotFather token.",
                "Local configuration checks without sending a test message.",
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
            "log_only checks local configuration. google_calendar Test connection calls "
            "Google Calendar, and configured workflows can create and delete live events."
        ),
        guide=IntegrationAcquisitionGuide(
            links=(
                IntegrationAcquisitionLink(
                    label="Google Calendar create events guide",
                    url=(
                        "https://developers.google.com/workspace/calendar/api/guides/"
                        "create-events"
                    ),
                ),
            ),
            account_requirements=(
                "A Google account and a Google Cloud project.",
                "The Google Calendar API enabled for that project.",
                (
                    "An OAuth consent screen and client authorized for "
                    "https://www.googleapis.com/auth/calendar."
                ),
            ),
            steps=(
                "Open the official Google Calendar create events guide linked here.",
                "Create or select a Google Cloud project and enable the Google Calendar API.",
                "Configure the OAuth consent screen and create the required OAuth client.",
                (
                    "Authorize the target account with "
                    "https://www.googleapis.com/auth/calendar, not a readonly scope."
                ),
                (
                    "Enter the calendar ID and access token, save the connector, and run "
                    "Test connection."
                ),
            ),
            environment_notes=(
                (
                    "log_only stays local. google_calendar can create and delete live events "
                    "as soon as a booking workflow uses it."
                ),
                (
                    "OAuth access tokens can expire. A production integration normally "
                    "needs a secure refresh flow."
                ),
            ),
            enables=(
                "Google Calendar credential and calendar ID configuration.",
                "A network reachability check when google_calendar mode is selected.",
                "Live Google Calendar event creation and deletion.",
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
