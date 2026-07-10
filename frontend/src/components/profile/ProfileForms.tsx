import { useEffect, useState } from "react";

import { Badge, Button, Surface } from "@/components/ui/primitives";
import { MultiSelectDropdown } from "@/components/ui/MultiSelectDropdown";
import { AIRLINE_OPTIONS, ALLIANCE_OPTIONS } from "@/data/aviationOptions";
import type {
  IntegrationProvider,
  LoyaltyProgramProfile,
  PaymentMethodProfile,
  TravelerProfile,
  TripTemplateProfile,
  UserPreferencesProfile,
} from "@/api/types";

function listToText(values: string[]) {
  return values.join(", ");
}

function textToList(value: string) {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function linesToList(value: string) {
  return value
    .split("\n")
    .map((item) => item.trim())
    .filter(Boolean);
}

function normalizeLoyaltyPrograms(programs: LoyaltyProgramProfile[]) {
  if (programs.length === 0) {
    return [];
  }
  const hasFavorite = programs.some((program) => program.isFavorite);
  return programs.map((program, index) => ({
    ...program,
    alliance: program.alliance || "none",
    programType: program.programType || "airline",
    isFavorite: hasFavorite ? program.isFavorite : index === 0,
  }));
}

function getInitialLoyaltyPrograms(initialValue?: TravelerProfile): LoyaltyProgramProfile[] {
  if (initialValue?.loyaltyPrograms?.length) {
    return normalizeLoyaltyPrograms(initialValue.loyaltyPrograms);
  }
  if (initialValue?.loyaltyProgramCode && initialValue?.loyaltyAccountNumber) {
    return [
      {
        programType: "airline",
        programCode: initialValue.loyaltyProgramCode,
        accountNumber: initialValue.loyaltyAccountNumber,
        alliance: initialValue.loyaltyAlliance || "none",
        statusTier: initialValue.loyaltyStatusTier || "",
        isFavorite: true,
      },
    ];
  }
  return [];
}

function getAirlineLabel(code: string) {
  return AIRLINE_OPTIONS.find((option) => option.value === code)?.label ?? code;
}

function titleizeStatus(value: string) {
  return value
    .split(/[_\s-]+/)
    .filter(Boolean)
    .map((part) => part[0].toUpperCase() + part.slice(1))
    .join(" ");
}

const HOTEL_RATING_OPTIONS = [
  { value: "", label: "No default minimum" },
  { value: "3.5", label: "3.5+" },
  { value: "4.0", label: "4.0+" },
  { value: "4.5", label: "4.5+" },
  { value: "5.0", label: "5.0 only" },
] as const;

const MAX_LAYOVER_OPTIONS = [
  { value: "", label: "Let TRAMP decide" },
  { value: "120", label: "Up to 2 hours" },
  { value: "180", label: "Up to 3 hours" },
  { value: "240", label: "Up to 4 hours" },
  { value: "360", label: "Up to 6 hours" },
] as const;

const MIN_CONNECTION_OPTIONS = [
  { value: "", label: "Algorithm decides" },
  { value: "45", label: "At least 45 minutes" },
  { value: "60", label: "At least 60 minutes" },
  { value: "75", label: "At least 75 minutes" },
  { value: "90", label: "At least 90 minutes" },
] as const;

const CARD_BRAND_OPTIONS = [
  { value: "", label: "Choose brand" },
  { value: "visa", label: "Visa" },
  { value: "mastercard", label: "Mastercard" },
  { value: "amex", label: "American Express" },
  { value: "discover", label: "Discover" },
  { value: "jcb", label: "JCB" },
  { value: "diners", label: "Diners Club" },
  { value: "unionpay", label: "UnionPay" },
] as const;

type SupportedCardBrand =
  | ""
  | "visa"
  | "mastercard"
  | "amex"
  | "discover"
  | "jcb"
  | "diners"
  | "unionpay";

const CARD_PATTERNS: Record<Exclude<SupportedCardBrand, "">, RegExp> = {
  visa: /^4\d{12}(?:\d{3})?(?:\d{3})?$/,
  mastercard: /^(?:5[1-5]\d{14}|2(?:2[2-9]\d|[3-6]\d{2}|7(?:0\d|1\d|20))\d{12})$/,
  amex: /^3[47]\d{13}$/,
  discover: /^(?:6011\d{12}|65\d{14}|64[4-9]\d{13})$/,
  jcb: /^(?:2131|1800|35\d{3})\d{11}$/,
  diners: /^3(?:0[0-5]|[68]\d)\d{11}$/,
  unionpay: /^62\d{14,17}$/,
};

function normalizeCardBrand(value: string): SupportedCardBrand {
  const normalized = value.trim().toLowerCase();
  return CARD_BRAND_OPTIONS.some((option) => option.value === normalized)
    ? (normalized as SupportedCardBrand)
    : "";
}

function digitsOnly(value: string) {
  return value.replace(/\D/g, "");
}

function formatCardNumberForBrand(value: string, brand: SupportedCardBrand) {
  const digits = digitsOnly(value).slice(0, brand === "amex" ? 15 : 19);
  if (brand === "amex") {
    const parts = [digits.slice(0, 4), digits.slice(4, 10), digits.slice(10, 15)].filter(Boolean);
    return parts.join(" ");
  }
  return digits.replace(/(.{4})/g, "$1 ").trim();
}

function getCardPlaceholder(brand: SupportedCardBrand) {
  switch (brand) {
    case "amex":
      return "3782 822463 10005";
    case "mastercard":
      return "5555 5555 5555 4444";
    case "discover":
      return "6011 1111 1111 1117";
    case "jcb":
      return "3530 1113 3330 0000";
    case "diners":
      return "3056 9309 0259 04";
    case "unionpay":
      return "6200 0000 0000 0000";
    case "visa":
    default:
      return "4111 1111 1111 1111";
  }
}

function getCardValidationMessage(brand: SupportedCardBrand, cardNumber: string) {
  const digits = digitsOnly(cardNumber);
  if (!digits) {
    return "";
  }
  if (!brand) {
    return "Choose a card brand before entering the number.";
  }
  const pattern = CARD_PATTERNS[brand];
  if (!pattern.test(digits)) {
    return `Card number does not match the expected ${CARD_BRAND_OPTIONS.find((option) => option.value === brand)?.label} format.`;
  }
  return "";
}

export function LoyaltyProgramsEditor({
  value,
  onChange,
  disabled = false,
}: {
  value: LoyaltyProgramProfile[];
  onChange: (programs: LoyaltyProgramProfile[]) => void;
  disabled?: boolean;
}) {
  const programs = normalizeLoyaltyPrograms(value);

  const updateProgram = (
    index: number,
    patch: Partial<LoyaltyProgramProfile>,
    options?: { makeFavorite?: boolean },
  ) => {
    const nextPrograms = programs.map((program, programIndex) => {
      if (programIndex !== index) {
        return options?.makeFavorite ? { ...program, isFavorite: false } : program;
      }
      return {
        ...program,
        ...patch,
        isFavorite: options?.makeFavorite ? true : (patch.isFavorite ?? program.isFavorite),
      };
    });
    onChange(normalizeLoyaltyPrograms(nextPrograms));
  };

  const removeProgram = (index: number) => {
    const nextPrograms = programs.filter((_, programIndex) => programIndex !== index);
    onChange(normalizeLoyaltyPrograms(nextPrograms));
  };

  return (
    <div className="stack-tight">
      <div className="toolbar-row">
        <div>
          <p className="field-label">Loyalty programs</p>
          <p className="helper-copy">
            Add as many airline programs as you want, then mark one favorite for default earning.
          </p>
        </div>
        <Button
          type="button"
          variant="secondary"
          disabled={disabled}
          onClick={() =>
            onChange(
              normalizeLoyaltyPrograms([
                ...programs,
                {
                  programType: "airline",
                  programCode: "",
                  accountNumber: "",
                  alliance: "none",
                  statusTier: "",
                  isFavorite: programs.length === 0,
                },
              ]),
            )
          }
        >
          Add loyalty program
        </Button>
      </div>

      {programs.length === 0 ? (
        <div className="muted-card">
          <p className="item-title">No loyalty programs yet</p>
          <p className="item-copy">
            Add Flying Blue, MileagePlus, KrisFlyer, or any other airline program you want TRAMP to
            consider.
          </p>
        </div>
      ) : null}

      {programs.map((program, index) => (
        <Surface key={`${program.programCode || "program"}-${index}`} className="list-card inset-card">
          <div className="watch-topline">
            <div>
              <div className="badge-row">
                <h3>{program.programCode ? getAirlineLabel(program.programCode) : `Program ${index + 1}`}</h3>
                {program.isFavorite ? <Badge tone="value">Favorite</Badge> : null}
              </div>
              <p className="item-copy">
                {program.accountNumber ? `Account ${program.accountNumber}` : "Program details not complete yet."}
              </p>
            </div>
            <Button type="button" variant="ghost" disabled={disabled} onClick={() => removeProgram(index)}>
              Remove
            </Button>
          </div>

          <div className="form-grid">
            <div className="field-stack">
              <label htmlFor={`loyalty-program-code-${index}`}>Program code</label>
              <input
                id={`loyalty-program-code-${index}`}
                className="text-input"
                list="loyalty-program-options"
                value={program.programCode}
                onChange={(event) =>
                  updateProgram(index, { programCode: event.target.value.trim().toUpperCase() })
                }
                placeholder="AF"
                disabled={disabled}
              />
            </div>

            <div className="field-stack">
              <label htmlFor={`loyalty-account-number-${index}`}>Account number</label>
              <input
                id={`loyalty-account-number-${index}`}
                className="text-input"
                value={program.accountNumber}
                onChange={(event) => updateProgram(index, { accountNumber: event.target.value })}
                placeholder="FB-2048"
                disabled={disabled}
              />
            </div>

            <div className="field-stack">
              <label htmlFor={`loyalty-alliance-${index}`}>Alliance</label>
              <select
                id={`loyalty-alliance-${index}`}
                className="text-input"
                value={program.alliance}
                onChange={(event) => updateProgram(index, { alliance: event.target.value })}
                disabled={disabled}
              >
                <option value="none">None</option>
                <option value="star">Star Alliance</option>
                <option value="oneworld">oneworld</option>
                <option value="skyteam">SkyTeam</option>
              </select>
            </div>

            <div className="field-stack">
              <label htmlFor={`loyalty-status-tier-${index}`}>Status tier</label>
              <input
                id={`loyalty-status-tier-${index}`}
                className="text-input"
                value={program.statusTier}
                onChange={(event) => updateProgram(index, { statusTier: event.target.value })}
                placeholder="Gold"
                disabled={disabled}
              />
            </div>
          </div>

          <label className="checkbox-row">
            <input
              type="radio"
              name="favorite-loyalty-program"
              checked={program.isFavorite}
              onChange={() => updateProgram(index, {}, { makeFavorite: true })}
              disabled={disabled}
            />
            <span>Use this as the favorite loyalty program for default crediting.</span>
          </label>
        </Surface>
      ))}
      <datalist id="loyalty-program-options">
        {AIRLINE_OPTIONS.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </datalist>
    </div>
  );
}

export function TravelerForm({
  initialValue,
  submitLabel,
  onSubmit,
  onCancel,
  disabled = false,
}: {
  initialValue?: TravelerProfile;
  submitLabel: string;
  onSubmit: (value: Omit<TravelerProfile, "id"> & { id?: string }) => void;
  onCancel?: () => void;
  disabled?: boolean;
}) {
  const [form, setForm] = useState(() => ({
    displayName: initialValue?.displayName ?? "",
    relationship: initialValue?.relationship ?? "self",
    legalFirstName: initialValue?.legalFirstName ?? "",
    legalLastName: initialValue?.legalLastName ?? "",
    dob: initialValue?.dob ?? "",
    nationality: initialValue?.nationality ?? "",
    residencyCountry: initialValue?.residencyCountry ?? "",
    passportNumber: initialValue?.passportNumber ?? "",
    passportCountry: initialValue?.passportCountry ?? "",
    passportExpiry: initialValue?.passportExpiry ?? "",
    knownTravelerNumber: initialValue?.knownTravelerNumber ?? "",
    redressNumber: initialValue?.redressNumber ?? "",
    seatPreference: initialValue?.seatPreference ?? "no_pref",
    mealPreference: initialValue?.mealPreference ?? "",
    loyaltyPrograms: getInitialLoyaltyPrograms(initialValue),
    accessibilityNeeds: initialValue?.accessibilityNeeds ?? "",
    infantOnLap: initialValue?.infantOnLap ?? false,
  }));

  useEffect(() => {
    setForm({
      displayName: initialValue?.displayName ?? "",
      relationship: initialValue?.relationship ?? "self",
      legalFirstName: initialValue?.legalFirstName ?? "",
      legalLastName: initialValue?.legalLastName ?? "",
      dob: initialValue?.dob ?? "",
      nationality: initialValue?.nationality ?? "",
      residencyCountry: initialValue?.residencyCountry ?? "",
      passportNumber: initialValue?.passportNumber ?? "",
      passportCountry: initialValue?.passportCountry ?? "",
      passportExpiry: initialValue?.passportExpiry ?? "",
      knownTravelerNumber: initialValue?.knownTravelerNumber ?? "",
      redressNumber: initialValue?.redressNumber ?? "",
      seatPreference: initialValue?.seatPreference ?? "no_pref",
      mealPreference: initialValue?.mealPreference ?? "",
      loyaltyPrograms: getInitialLoyaltyPrograms(initialValue),
      accessibilityNeeds: initialValue?.accessibilityNeeds ?? "",
      infantOnLap: initialValue?.infantOnLap ?? false,
    });
  }, [initialValue]);

  return (
    <form
      className="form-shell"
      onSubmit={(event) => {
        event.preventDefault();
        const normalizedLoyaltyPrograms = normalizeLoyaltyPrograms(
          form.loyaltyPrograms.filter(
            (program) => program.programCode.trim() && program.accountNumber.trim(),
          ),
        );
        const favoriteLoyaltyProgram =
          normalizedLoyaltyPrograms.find((program) => program.isFavorite) ??
          normalizedLoyaltyPrograms[0];
        onSubmit({
          id: initialValue?.id,
          displayName: form.displayName.trim(),
          relationship: form.relationship,
          legalFirstName: form.legalFirstName.trim(),
          legalLastName: form.legalLastName.trim(),
          dob: form.dob,
          nationality: form.nationality.trim().toUpperCase(),
          residencyCountry: form.residencyCountry.trim().toUpperCase(),
          passportNumber: form.passportNumber.trim(),
          passportCountry: form.passportCountry.trim().toUpperCase(),
          passportExpiry: form.passportExpiry,
          knownTravelerNumber: form.knownTravelerNumber.trim(),
          redressNumber: form.redressNumber.trim(),
          seatPreference: form.seatPreference,
          mealPreference: form.mealPreference.trim(),
          loyaltyProgramCode: favoriteLoyaltyProgram?.programCode ?? "",
          loyaltyAccountNumber: favoriteLoyaltyProgram?.accountNumber ?? "",
          loyaltyAlliance: favoriteLoyaltyProgram?.alliance ?? "none",
          loyaltyStatusTier: favoriteLoyaltyProgram?.statusTier ?? "",
          preferredEarningForAlliance: favoriteLoyaltyProgram?.isFavorite ?? false,
          loyaltyPrograms: normalizedLoyaltyPrograms,
          accessibilityNeeds: form.accessibilityNeeds.trim(),
          infantOnLap: form.infantOnLap,
        });
      }}
    >
      <div className="toolbar-row">
        <div>
          <p className="field-label">Traveler editor</p>
          <p className="helper-copy">Capture enough legal and comfort data to seed future watches.</p>
        </div>
      </div>

      <div className="form-grid">
        <div className="field-stack">
          <label htmlFor="traveler-display-name">Display name</label>
          <input
            id="traveler-display-name"
            className="text-input"
            value={form.displayName}
            onChange={(event) => setForm((current) => ({ ...current, displayName: event.target.value }))}
            placeholder="Matt"
            required
            disabled={disabled}
          />
        </div>

        <div className="field-stack">
          <label htmlFor="traveler-relationship">Relationship</label>
          <select
            id="traveler-relationship"
            className="text-input"
            value={form.relationship}
            onChange={(event) => setForm((current) => ({ ...current, relationship: event.target.value }))}
            disabled={disabled}
          >
            <option value="self">Self</option>
            <option value="partner">Partner</option>
            <option value="child">Child</option>
            <option value="other">Other</option>
          </select>
        </div>

        <div className="field-stack">
          <label htmlFor="traveler-first-name">Legal first name</label>
          <input
            id="traveler-first-name"
            className="text-input"
            value={form.legalFirstName}
            onChange={(event) =>
              setForm((current) => ({ ...current, legalFirstName: event.target.value }))
            }
            required
            disabled={disabled}
          />
        </div>

        <div className="field-stack">
          <label htmlFor="traveler-last-name">Legal last name</label>
          <input
            id="traveler-last-name"
            className="text-input"
            value={form.legalLastName}
            onChange={(event) =>
              setForm((current) => ({ ...current, legalLastName: event.target.value }))
            }
            required
            disabled={disabled}
          />
        </div>

        <div className="field-stack">
          <label htmlFor="traveler-dob">Date of birth</label>
          <input
            id="traveler-dob"
            className="text-input"
            type="date"
            value={form.dob}
            onChange={(event) => setForm((current) => ({ ...current, dob: event.target.value }))}
            required
            disabled={disabled}
          />
        </div>

        <div className="field-stack">
          <label htmlFor="traveler-nationality">Nationality</label>
          <input
            id="traveler-nationality"
            className="text-input"
            value={form.nationality}
            onChange={(event) =>
              setForm((current) => ({ ...current, nationality: event.target.value }))
            }
            placeholder="JP"
            required
            disabled={disabled}
          />
        </div>

        <div className="field-stack">
          <label htmlFor="traveler-residency">Residency country</label>
          <input
            id="traveler-residency"
            className="text-input"
            value={form.residencyCountry}
            onChange={(event) =>
              setForm((current) => ({ ...current, residencyCountry: event.target.value }))
            }
            placeholder="JP"
            disabled={disabled}
          />
        </div>

        <div className="field-stack">
          <label htmlFor="traveler-passport-number">Passport number</label>
          <input
            id="traveler-passport-number"
            className="text-input"
            value={form.passportNumber}
            onChange={(event) =>
              setForm((current) => ({ ...current, passportNumber: event.target.value }))
            }
            disabled={disabled}
          />
        </div>

        <div className="field-stack">
          <label htmlFor="traveler-passport-country">Passport country</label>
          <input
            id="traveler-passport-country"
            className="text-input"
            value={form.passportCountry}
            onChange={(event) =>
              setForm((current) => ({ ...current, passportCountry: event.target.value }))
            }
            placeholder="US"
            disabled={disabled}
          />
        </div>

        <div className="field-stack">
          <label htmlFor="traveler-passport-expiry">Passport expiry</label>
          <input
            id="traveler-passport-expiry"
            className="text-input"
            type="date"
            value={form.passportExpiry}
            onChange={(event) =>
              setForm((current) => ({ ...current, passportExpiry: event.target.value }))
            }
            disabled={disabled}
          />
        </div>

        <div className="field-stack">
          <label htmlFor="traveler-known-number">Known traveler number</label>
          <input
            id="traveler-known-number"
            className="text-input"
            value={form.knownTravelerNumber}
            onChange={(event) =>
              setForm((current) => ({ ...current, knownTravelerNumber: event.target.value }))
            }
            disabled={disabled}
          />
        </div>

        <div className="field-stack">
          <label htmlFor="traveler-redress-number">Redress number</label>
          <input
            id="traveler-redress-number"
            className="text-input"
            value={form.redressNumber}
            onChange={(event) =>
              setForm((current) => ({ ...current, redressNumber: event.target.value }))
            }
            disabled={disabled}
          />
        </div>

        <div className="field-stack">
          <label htmlFor="traveler-seat-pref">Seat preference</label>
          <select
            id="traveler-seat-pref"
            className="text-input"
            value={form.seatPreference}
            onChange={(event) =>
              setForm((current) => ({ ...current, seatPreference: event.target.value }))
            }
            disabled={disabled}
          >
            <option value="window">Window</option>
            <option value="aisle">Aisle</option>
            <option value="extra_legroom">Extra legroom</option>
            <option value="no_pref">No preference</option>
          </select>
        </div>

        <div className="field-stack">
          <label htmlFor="traveler-meal-pref">Meal preference</label>
          <input
            id="traveler-meal-pref"
            className="text-input"
            value={form.mealPreference}
            onChange={(event) =>
              setForm((current) => ({ ...current, mealPreference: event.target.value }))
            }
            placeholder="Vegetarian"
            disabled={disabled}
          />
        </div>

        <div className="field-stack field-span-full">
          <label htmlFor="traveler-accessibility">Accessibility needs</label>
          <textarea
            id="traveler-accessibility"
            className="text-area"
            value={form.accessibilityNeeds}
            onChange={(event) =>
              setForm((current) => ({ ...current, accessibilityNeeds: event.target.value }))
            }
            placeholder="Wheelchair assistance, mobility note, or leave blank."
            disabled={disabled}
          />
        </div>

        <label className="checkbox-row">
          <input
            type="checkbox"
            checked={form.infantOnLap}
            onChange={(event) =>
              setForm((current) => ({ ...current, infantOnLap: event.target.checked }))
            }
            disabled={disabled}
          />
          <span>Infant travels on lap for this traveler profile.</span>
        </label>
      </div>

      <LoyaltyProgramsEditor
        value={form.loyaltyPrograms}
        onChange={(loyaltyPrograms) => setForm((current) => ({ ...current, loyaltyPrograms }))}
        disabled={disabled}
      />

      <div className="panel-actions">
        <Button type="submit" disabled={disabled}>
          {submitLabel}
        </Button>
        {onCancel ? (
          <Button type="button" variant="ghost" onClick={onCancel} disabled={disabled}>
            Cancel
          </Button>
        ) : null}
      </div>
    </form>
  );
}

export function PreferencesForm({
  initialValue,
  submitLabel,
  onSubmit,
  disabled = false,
  notificationContext,
  includeNotificationControls = true,
}: {
  initialValue: UserPreferencesProfile;
  submitLabel: string;
  onSubmit: (value: UserPreferencesProfile) => void;
  disabled?: boolean;
  notificationContext?: {
    currentUserEmail?: string;
    telegramChatId?: string | null;
    messagingIntegration?: IntegrationProvider;
  };
  includeNotificationControls?: boolean;
}) {
  const [form, setForm] = useState(() => ({
    homeAirports: listToText(initialValue.homeAirports),
    defaultCabin: initialValue.defaultCabin,
    defaultLuxuryVsSavings: initialValue.defaultLuxuryVsSavings,
    preferredAlliances: initialValue.preferredAlliances,
    preferredAirlines: initialValue.preferredAirlines,
    avoidedAirlines: listToText(initialValue.avoidedAirlines),
    preferredHotelBrands: listToText(initialValue.preferredHotelBrands),
    avoidedHotelBrands: listToText(initialValue.avoidedHotelBrands),
    quietHoursStart: initialValue.quietHoursStart,
    quietHoursEnd: initialValue.quietHoursEnd,
    defaultNotifyChannel: initialValue.defaultNotifyChannel,
    avoidRedeye: initialValue.avoidRedeye,
    preferRefundable: initialValue.preferRefundable,
    seatAutoSelect: initialValue.seatAutoSelect,
    defaultHotelMinRating: initialValue.defaultHotelMinRating,
    maxLayoverMinutes: initialValue.maxLayoverMinutes,
    minConnectionMinutes: initialValue.minConnectionMinutes,
  }));

  useEffect(() => {
    setForm({
      homeAirports: listToText(initialValue.homeAirports),
      defaultCabin: initialValue.defaultCabin,
      defaultLuxuryVsSavings: initialValue.defaultLuxuryVsSavings,
      preferredAlliances: initialValue.preferredAlliances,
      preferredAirlines: initialValue.preferredAirlines,
      avoidedAirlines: listToText(initialValue.avoidedAirlines),
      preferredHotelBrands: listToText(initialValue.preferredHotelBrands),
      avoidedHotelBrands: listToText(initialValue.avoidedHotelBrands),
      quietHoursStart: initialValue.quietHoursStart,
      quietHoursEnd: initialValue.quietHoursEnd,
      defaultNotifyChannel: initialValue.defaultNotifyChannel,
      avoidRedeye: initialValue.avoidRedeye,
      preferRefundable: initialValue.preferRefundable,
      seatAutoSelect: initialValue.seatAutoSelect,
      defaultHotelMinRating: initialValue.defaultHotelMinRating,
      maxLayoverMinutes: initialValue.maxLayoverMinutes,
      minConnectionMinutes: initialValue.minConnectionMinutes,
    });
  }, [initialValue]);

  const defaultNotifyChannelLabel =
    form.defaultNotifyChannel === "email"
      ? "Email"
      : form.defaultNotifyChannel === "telegram"
        ? "Telegram"
        : form.defaultNotifyChannel === "both"
          ? "Both"
          : "Inherit";

  const notificationInstructions =
    form.defaultNotifyChannel === "email"
      ? [
          `Make sure the account email is correct${notificationContext?.currentUserEmail ? ` (${notificationContext.currentUserEmail})` : ""}.`,
          "Go to Admin -> Integrations -> Messaging and select `smtp_dev` when you want real email delivery.",
          "Enter `SMTP host` and `From address`, then test the connector before relying on alerts.",
        ]
      : form.defaultNotifyChannel === "telegram"
        ? [
            "Go to Admin -> Integrations -> Messaging and select `telegram_bot`.",
            "Paste the Telegram bot token and test the connector.",
            notificationContext?.telegramChatId
              ? `Telegram chat is already linked (${notificationContext.telegramChatId}).`
              : "Link a Telegram chat ID to this account before expecting Telegram alerts.",
          ]
        : form.defaultNotifyChannel === "both"
          ? [
              "Set up both Email and Telegram delivery before using the combined channel.",
              "In Messaging integrations, choose the provider path you want to operationalize first and test it.",
              "Use connector tests after each change so alerts do not silently fail.",
            ]
          : [
              "Inherit follows the account-level or watch-level notification choice.",
              "Set up your preferred delivery channel in Messaging integrations before switching away from inherit.",
            ];

  const preferenceIntentText =
    form.preferredAirlines.length === 0 && form.preferredAlliances.length === 0
      ? "All airlines remain eligible by default, including carriers not listed here."
      : "These are soft preferences only. TRAMP can still consider other airlines and non-aligned carriers when they provide better value or availability.";

  return (
    <form
      className="form-shell"
      onSubmit={(event) => {
        event.preventDefault();
        onSubmit({
          homeAirports: textToList(form.homeAirports).map((item) => item.toUpperCase()),
          defaultCabin: form.defaultCabin,
          defaultLuxuryVsSavings: form.defaultLuxuryVsSavings,
          preferredAlliances: form.preferredAlliances,
          preferredAirlines: form.preferredAirlines,
          avoidedAirlines: textToList(form.avoidedAirlines),
          preferredHotelBrands: textToList(form.preferredHotelBrands),
          avoidedHotelBrands: textToList(form.avoidedHotelBrands),
          quietHoursStart: form.quietHoursStart,
          quietHoursEnd: form.quietHoursEnd,
          defaultNotifyChannel: form.defaultNotifyChannel,
          avoidRedeye: form.avoidRedeye,
          preferRefundable: form.preferRefundable,
          seatAutoSelect: form.seatAutoSelect,
          defaultHotelMinRating: form.defaultHotelMinRating,
          maxLayoverMinutes: form.maxLayoverMinutes,
          minConnectionMinutes: form.minConnectionMinutes,
        });
      }}
    >
      <div className="toolbar-row">
        <div>
          <p className="field-label">Preference defaults</p>
          <p className="helper-copy">
            These defaults prefill the watch editor{includeNotificationControls ? " and alerting behavior" : ""}.
          </p>
        </div>
      </div>

      <Surface className="inset-card">
        <p className="field-label">Preference behavior</p>
        <p className="helper-copy">{preferenceIntentText}</p>
      </Surface>

      <div className="form-grid">
        {includeNotificationControls ? (
          <>
            <div className="field-stack">
              <label htmlFor="pref-notify-channel">Default notify channel</label>
              <select
                id="pref-notify-channel"
                className="text-input"
                value={form.defaultNotifyChannel}
                onChange={(event) =>
                  setForm((current) => ({ ...current, defaultNotifyChannel: event.target.value }))
                }
                disabled={disabled}
              >
                <option value="inherit">Inherit</option>
                <option value="email">Email</option>
                <option value="telegram">Telegram</option>
                <option value="both">Both</option>
              </select>
              <p className="helper-copy">Current selection: {defaultNotifyChannelLabel}.</p>
            </div>

            <Surface className="inset-card field-span-full">
              <p className="field-label">How to enable {defaultNotifyChannelLabel.toLowerCase()}</p>
              <div className="stack-tight">
                {notificationInstructions.map((line) => (
                  <p key={line} className="helper-copy">
                    {line}
                  </p>
                ))}
                {notificationContext?.messagingIntegration ? (
                  <p className="helper-copy">
                    Messaging integration status: {notificationContext.messagingIntegration.environment} /{" "}
                    {notificationContext.messagingIntegration.enabled ? "enabled" : "disabled"}.
                  </p>
                ) : null}
              </div>
            </Surface>
          </>
        ) : null}

        <div className="field-stack">
          <label htmlFor="pref-home-airports">Home airports</label>
          <input
            id="pref-home-airports"
            className="text-input"
            value={form.homeAirports}
            onChange={(event) => setForm((current) => ({ ...current, homeAirports: event.target.value }))}
            placeholder="HND, NRT"
            disabled={disabled}
          />
        </div>

        <div className="field-stack">
          <label htmlFor="pref-cabin">Default cabin</label>
          <select
            id="pref-cabin"
            className="text-input"
            value={form.defaultCabin}
            onChange={(event) => setForm((current) => ({ ...current, defaultCabin: event.target.value }))}
            disabled={disabled}
          >
            <option value="economy">Economy</option>
            <option value="premium economy">Premium economy</option>
            <option value="business">Business</option>
            <option value="first">First</option>
          </select>
        </div>

        <div className="field-stack field-span-full">
          <label htmlFor="pref-luxury-slider">Luxury to savings</label>
          <div className="range-row">
            <input
              id="pref-luxury-slider"
              className="range-input"
              type="range"
              min="0"
              max="100"
              value={Math.round(form.defaultLuxuryVsSavings * 100)}
              onChange={(event) =>
                setForm((current) => ({
                  ...current,
                  defaultLuxuryVsSavings: Number(event.target.value) / 100,
                }))
              }
              disabled={disabled}
            />
            <strong>{Math.round(form.defaultLuxuryVsSavings * 100)}%</strong>
          </div>
          <p className="helper-copy">0 favors luxury, 100 favors savings.</p>
        </div>

        <MultiSelectDropdown
          id="pref-alliances"
          label="Preferred alliances"
          options={ALLIANCE_OPTIONS}
          selectedValues={form.preferredAlliances}
          onChange={(preferredAlliances) => setForm((current) => ({ ...current, preferredAlliances }))}
          disabled={disabled}
          helperText="Leave this blank to include every alliance and non-aligned carrier by default."
          otherPlaceholder="Add other alliance"
        />

        <MultiSelectDropdown
          id="pref-airlines"
          label="Preferred airlines"
          options={AIRLINE_OPTIONS}
          selectedValues={form.preferredAirlines}
          onChange={(preferredAirlines) => setForm((current) => ({ ...current, preferredAirlines }))}
          disabled={disabled}
          helperText="Leave this blank to include all airlines by default, including carriers not listed here."
          otherPlaceholder="Add IATA or ICAO code"
        />

        <MultiSelectDropdown
          id="pref-avoided-airlines"
          label="Avoided airlines"
          options={AIRLINE_OPTIONS}
          selectedValues={textToList(form.avoidedAirlines)}
          onChange={(avoidedAirlines) =>
            setForm((current) => ({ ...current, avoidedAirlines: listToText(avoidedAirlines) }))
          }
          disabled={disabled}
          helperText="Use this only for true exclusions. Preferred airlines above remain non-exclusive."
          otherPlaceholder="Add IATA or ICAO code"
        />

        <div className="field-stack">
          <label htmlFor="pref-hotels">Preferred hotel brands</label>
          <input
            id="pref-hotels"
            className="text-input"
            value={form.preferredHotelBrands}
            onChange={(event) =>
              setForm((current) => ({ ...current, preferredHotelBrands: event.target.value }))
            }
            placeholder="Hyatt, Aman"
            disabled={disabled}
          />
        </div>

        <div className="field-stack">
          <label htmlFor="pref-avoided-hotels">Avoided hotel brands</label>
          <input
            id="pref-avoided-hotels"
            className="text-input"
            value={form.avoidedHotelBrands}
            onChange={(event) =>
              setForm((current) => ({ ...current, avoidedHotelBrands: event.target.value }))
            }
            placeholder="Brand to avoid"
            disabled={disabled}
          />
        </div>

        <div className="field-stack">
          <label htmlFor="pref-quiet-start">Quiet hours start</label>
          <input
            id="pref-quiet-start"
            className="text-input"
            type="time"
            value={form.quietHoursStart}
            onChange={(event) =>
              setForm((current) => ({ ...current, quietHoursStart: event.target.value }))
            }
            disabled={disabled}
          />
        </div>

        <div className="field-stack">
          <label htmlFor="pref-quiet-end">Quiet hours end</label>
          <input
            id="pref-quiet-end"
            className="text-input"
            type="time"
            value={form.quietHoursEnd}
            onChange={(event) =>
              setForm((current) => ({ ...current, quietHoursEnd: event.target.value }))
            }
            disabled={disabled}
          />
        </div>

        <div className="field-stack">
          <label htmlFor="pref-hotel-rating">Minimum hotel rating</label>
          <select
            id="pref-hotel-rating"
            className="text-input"
            value={form.defaultHotelMinRating}
            onChange={(event) =>
              setForm((current) => ({ ...current, defaultHotelMinRating: event.target.value }))
            }
            disabled={disabled}
          >
            {HOTEL_RATING_OPTIONS.map((option) => (
              <option key={option.value || "none"} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>

        <div className="field-stack">
          <label htmlFor="pref-max-layover">Max layover minutes</label>
          <select
            id="pref-max-layover"
            className="text-input"
            value={form.maxLayoverMinutes}
            onChange={(event) =>
              setForm((current) => ({ ...current, maxLayoverMinutes: event.target.value }))
            }
            disabled={disabled}
          >
            {MAX_LAYOVER_OPTIONS.map((option) => (
              <option key={option.value || "auto"} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>

        <div className="field-stack">
          <label htmlFor="pref-min-connection">Min connection minutes</label>
          <select
            id="pref-min-connection"
            className="text-input"
            value={form.minConnectionMinutes}
            onChange={(event) =>
              setForm((current) => ({ ...current, minConnectionMinutes: event.target.value }))
            }
            disabled={disabled}
          >
            {MIN_CONNECTION_OPTIONS.map((option) => (
              <option key={option.value || "auto"} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>

        <label className="checkbox-row">
          <input
            type="checkbox"
            checked={form.avoidRedeye}
            onChange={(event) => setForm((current) => ({ ...current, avoidRedeye: event.target.checked }))}
            disabled={disabled}
          />
          <span>Avoid red-eye flights by default.</span>
        </label>

        <label className="checkbox-row">
          <input
            type="checkbox"
            checked={form.preferRefundable}
            onChange={(event) =>
              setForm((current) => ({ ...current, preferRefundable: event.target.checked }))
            }
            disabled={disabled}
          />
          <span>Prefer refundable inventory when quality is similar.</span>
        </label>

        <label className="checkbox-row">
          <input
            type="checkbox"
            checked={form.seatAutoSelect}
            onChange={(event) =>
              setForm((current) => ({ ...current, seatAutoSelect: event.target.checked }))
            }
            disabled={disabled}
          />
          <span>Auto-select seats that match traveler preferences.</span>
        </label>
      </div>

      <div className="panel-actions">
        <Button type="submit" disabled={disabled}>
          {submitLabel}
        </Button>
      </div>
    </form>
  );
}

export function TravelerGroupForm({
  initialValue,
  travelers,
  submitLabel,
  onSubmit,
  onCancel,
  disabled = false,
}: {
  initialValue?: { id?: string; name: string; travelerIds: string[] } | null;
  travelers: TravelerProfile[];
  submitLabel: string;
  onSubmit: (value: { id?: string; name: string; travelerIds: string[] }) => void;
  onCancel: () => void;
  disabled?: boolean;
}) {
  const [form, setForm] = useState(() => ({
    id: initialValue?.id,
    name: initialValue?.name ?? "",
    travelerIds: initialValue?.travelerIds ?? [],
  }));

  useEffect(() => {
    setForm({
      id: initialValue?.id,
      name: initialValue?.name ?? "",
      travelerIds: initialValue?.travelerIds ?? [],
    });
  }, [initialValue]);

  const toggleTraveler = (travelerId: string) => {
    setForm((current) => ({
      ...current,
      travelerIds: current.travelerIds.includes(travelerId)
        ? current.travelerIds.filter((value) => value !== travelerId)
        : [...current.travelerIds, travelerId],
    }));
  };

  return (
    <Surface className="inset-card">
      <form
        className="stack-tight"
        onSubmit={(event) => {
          event.preventDefault();
          onSubmit({
            id: form.id,
            name: form.name.trim(),
            travelerIds: form.travelerIds,
          });
        }}
      >
        <div>
          <p className="field-label">Traveler group</p>
          <p className="helper-copy">
            Create reusable household sets so new watches can start with the right people already selected.
          </p>
        </div>

        <label className="field-stack">
          <span>Group name</span>
          <input
            className="text-input"
            value={form.name}
            onChange={(event) => setForm((current) => ({ ...current, name: event.target.value }))}
            placeholder="Family spring trip"
            disabled={disabled}
          />
        </label>

        <div className="field-stack">
          <span>Travelers in this group</span>
          <div className="stack-tight">
            {travelers.map((traveler) => (
              <label key={traveler.id} className="checkbox-row">
                <input
                  type="checkbox"
                  checked={form.travelerIds.includes(traveler.id)}
                  onChange={() => toggleTraveler(traveler.id)}
                  disabled={disabled}
                />
                <span>
                  {traveler.displayName} · {titleizeStatus(traveler.relationship)}
                </span>
              </label>
            ))}
          </div>
        </div>

        <div className="button-row">
          <Button type="submit" disabled={disabled || !form.name.trim() || form.travelerIds.length === 0}>
            {submitLabel}
          </Button>
          <Button type="button" variant="secondary" onClick={onCancel} disabled={disabled}>
            Cancel
          </Button>
        </div>
      </form>
    </Surface>
  );
}

export function PaymentMethodForm({
  initialValue,
  submitLabel,
  onSubmit,
  onCancel,
  disabled = false,
}: {
  initialValue?: PaymentMethodProfile;
  submitLabel: string;
  onSubmit: (value: Omit<PaymentMethodProfile, "id"> & { id?: string }) => void;
  onCancel?: () => void;
  disabled?: boolean;
}) {
  const currentYear = new Date().getFullYear();
  const expiryYearOptions = Array.from({ length: 15 }, (_, index) => String(currentYear + index));
  const [cardValidationMessage, setCardValidationMessage] = useState("");
  const [form, setForm] = useState(() => ({
    label: initialValue?.label ?? "",
    brand: normalizeCardBrand(initialValue?.brand ?? ""),
    cardholderName: initialValue?.cardholderName ?? "",
    cardNumber: "",
    billingCountry: initialValue?.billingCountry ?? "",
    expMonth: initialValue?.expMonth ?? "",
    expYear: initialValue?.expYear ?? "",
    providerToken: initialValue?.providerToken ?? "",
    billingAddressLine1: initialValue?.billingAddressLine1 ?? "",
    billingAddressCity: initialValue?.billingAddressCity ?? "",
    billingAddressPostalCode: initialValue?.billingAddressPostalCode ?? "",
  }));

  useEffect(() => {
    setForm({
      label: initialValue?.label ?? "",
      brand: normalizeCardBrand(initialValue?.brand ?? ""),
      cardholderName: initialValue?.cardholderName ?? "",
      cardNumber: "",
      billingCountry: initialValue?.billingCountry ?? "",
      expMonth: initialValue?.expMonth ?? "",
      expYear: initialValue?.expYear ?? "",
      providerToken: initialValue?.providerToken ?? "",
      billingAddressLine1: initialValue?.billingAddressLine1 ?? "",
      billingAddressCity: initialValue?.billingAddressCity ?? "",
      billingAddressPostalCode: initialValue?.billingAddressPostalCode ?? "",
    });
    setCardValidationMessage("");
  }, [initialValue]);

  const normalizedCardNumber = digitsOnly(form.cardNumber);
  const cardNumberPlaceholder = getCardPlaceholder(form.brand);
  const canKeepStoredCard = Boolean(initialValue?.last4) && normalizedCardNumber.length === 0;
  const submitDisabled = disabled || Boolean(cardValidationMessage);

  return (
    <form
      className="form-shell"
      onSubmit={(event) => {
        event.preventDefault();
        const validationMessage = getCardValidationMessage(form.brand, form.cardNumber);
        setCardValidationMessage(validationMessage);
        if (validationMessage) {
          return;
        }
        onSubmit({
          id: initialValue?.id,
          label: form.label.trim(),
          brand: form.brand,
          cardholderName: form.cardholderName.trim(),
          cardNumber: normalizedCardNumber,
          last4: canKeepStoredCard ? initialValue?.last4 ?? "" : normalizedCardNumber.slice(-4),
          expMonth: form.expMonth,
          expYear: form.expYear,
          providerToken: form.providerToken.trim(),
          billingAddressLine1: form.billingAddressLine1.trim(),
          billingAddressCity: form.billingAddressCity.trim(),
          billingAddressPostalCode: form.billingAddressPostalCode.trim(),
          billingCountry: form.billingCountry.trim().toUpperCase(),
        });
      }}
    >
      <div className="toolbar-row">
        <div>
          <p className="field-label">Payment method</p>
          <p className="helper-copy">Sensitive billing data stays summarized and masked in the UI.</p>
        </div>
      </div>

      <Surface className="inset-card">
        <p className="field-label">Card quality checks</p>
        <p className="helper-copy">
          Card brand and expiry now use guided selections to reduce typos. The card number is checked against the selected brand before saving.
        </p>
      </Surface>

      <div className="form-grid">
        <div className="field-stack">
          <label htmlFor="payment-label">Label</label>
          <input
            id="payment-label"
            className="text-input"
            value={form.label}
            onChange={(event) => setForm((current) => ({ ...current, label: event.target.value }))}
            placeholder="Household Visa"
            required
            disabled={disabled}
          />
        </div>

        <div className="field-stack">
          <label htmlFor="payment-brand">Brand</label>
          <select
            id="payment-brand"
            className="text-input"
            value={form.brand}
            onChange={(event) => {
              const nextBrand = normalizeCardBrand(event.target.value);
              const nextCardNumber = form.cardNumber
                ? formatCardNumberForBrand(form.cardNumber, nextBrand)
                : "";
              setForm((current) => ({
                ...current,
                brand: nextBrand,
                cardNumber: nextCardNumber,
              }));
              setCardValidationMessage(getCardValidationMessage(nextBrand, nextCardNumber));
            }}
            disabled={disabled}
          >
            {CARD_BRAND_OPTIONS.map((option) => (
              <option key={option.value || "none"} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>

        <div className="field-stack">
          <label htmlFor="payment-cardholder">Cardholder name</label>
          <input
            id="payment-cardholder"
            className="text-input"
            value={form.cardholderName}
            onChange={(event) =>
              setForm((current) => ({ ...current, cardholderName: event.target.value }))
            }
            placeholder="Matt DM"
            required
            disabled={disabled}
          />
        </div>

        <div className="field-stack">
          <label htmlFor="payment-card-number">
            Card number {initialValue?.last4 ? `(current ends ${initialValue.last4})` : ""}
          </label>
          <input
            id="payment-card-number"
            className="text-input"
            value={form.cardNumber}
            inputMode="numeric"
            onChange={(event) => {
              const formatted = formatCardNumberForBrand(event.target.value, form.brand);
              setForm((current) => ({ ...current, cardNumber: formatted }));
              setCardValidationMessage(getCardValidationMessage(form.brand, formatted));
            }}
            placeholder={initialValue?.last4 ? `Leave blank to keep current card · ${cardNumberPlaceholder}` : cardNumberPlaceholder}
            disabled={disabled}
          />
          <p className="helper-copy">
            {form.brand
              ? `Expected format for ${CARD_BRAND_OPTIONS.find((option) => option.value === form.brand)?.label}.`
              : "Choose a brand first so TRAMP can validate the number format."}
          </p>
          {cardValidationMessage ? <div className="notice notice-alert">{cardValidationMessage}</div> : null}
        </div>

        <div className="field-stack">
          <label htmlFor="payment-exp-month">Expiry month</label>
          <select
            id="payment-exp-month"
            className="text-input"
            value={form.expMonth}
            onChange={(event) => setForm((current) => ({ ...current, expMonth: event.target.value }))}
            disabled={disabled}
          >
            <option value="">Choose month</option>
            {Array.from({ length: 12 }, (_, index) => String(index + 1).padStart(2, "0")).map((month) => (
              <option key={month} value={month}>
                {month}
              </option>
            ))}
          </select>
        </div>

        <div className="field-stack">
          <label htmlFor="payment-exp-year">Expiry year</label>
          <select
            id="payment-exp-year"
            className="text-input"
            value={form.expYear}
            onChange={(event) => setForm((current) => ({ ...current, expYear: event.target.value }))}
            disabled={disabled}
          >
            <option value="">Choose year</option>
            {expiryYearOptions.map((year) => (
              <option key={year} value={year}>
                {year}
              </option>
            ))}
          </select>
        </div>

        <div className="field-stack">
          <label htmlFor="payment-country">Billing country</label>
          <input
            id="payment-country"
            className="text-input"
            value={form.billingCountry}
            onChange={(event) =>
              setForm((current) => ({ ...current, billingCountry: event.target.value }))
            }
            placeholder="JP"
            disabled={disabled}
          />
        </div>

        <div className="field-stack">
          <label htmlFor="payment-provider-token">Provider token</label>
          <input
            id="payment-provider-token"
            className="text-input"
            value={form.providerToken}
            onChange={(event) =>
              setForm((current) => ({ ...current, providerToken: event.target.value }))
            }
            placeholder="Optional tokenized reference"
            disabled={disabled}
          />
        </div>

        <div className="field-stack field-span-full">
          <label htmlFor="payment-address-line1">Billing address line 1</label>
          <input
            id="payment-address-line1"
            className="text-input"
            value={form.billingAddressLine1}
            onChange={(event) =>
              setForm((current) => ({ ...current, billingAddressLine1: event.target.value }))
            }
            disabled={disabled}
          />
        </div>

        <div className="field-stack">
          <label htmlFor="payment-address-city">Billing city</label>
          <input
            id="payment-address-city"
            className="text-input"
            value={form.billingAddressCity}
            onChange={(event) =>
              setForm((current) => ({ ...current, billingAddressCity: event.target.value }))
            }
            disabled={disabled}
          />
        </div>

        <div className="field-stack">
          <label htmlFor="payment-address-postal">Postal code</label>
          <input
            id="payment-address-postal"
            className="text-input"
            value={form.billingAddressPostalCode}
            onChange={(event) =>
              setForm((current) => ({ ...current, billingAddressPostalCode: event.target.value }))
            }
            disabled={disabled}
          />
        </div>
      </div>

      <div className="panel-actions">
        <Button type="submit" disabled={submitDisabled}>
          {submitLabel}
        </Button>
        {onCancel ? (
          <Button type="button" variant="ghost" onClick={onCancel} disabled={disabled}>
            Cancel
          </Button>
        ) : null}
      </div>
    </form>
  );
}

export function TemplateForm({
  initialValue,
  travelerGroups,
  submitLabel,
  onSubmit,
  onCancel,
  disabled = false,
}: {
  initialValue?: TripTemplateProfile;
  travelerGroups: string[];
  submitLabel: string;
  onSubmit: (value: Omit<TripTemplateProfile, "id"> & { id?: string }) => void;
  onCancel?: () => void;
  disabled?: boolean;
}) {
  const [form, setForm] = useState(() => ({
    name: initialValue?.name ?? "",
    travelerGroup: initialValue?.travelerGroup ?? travelerGroups[0] ?? "All travelers",
    origin: initialValue?.origin ?? "",
    destination: initialValue?.destination ?? "",
    flightBudgetMax: initialValue?.flightBudgetMax ?? "",
    hotelBudgetPerNightMax: initialValue?.hotelBudgetPerNightMax ?? "",
    notes: initialValue?.notes ?? "",
  }));

  useEffect(() => {
    setForm({
      name: initialValue?.name ?? "",
      travelerGroup: initialValue?.travelerGroup ?? travelerGroups[0] ?? "All travelers",
      origin: initialValue?.origin ?? "",
      destination: initialValue?.destination ?? "",
      flightBudgetMax: initialValue?.flightBudgetMax ?? "",
      hotelBudgetPerNightMax: initialValue?.hotelBudgetPerNightMax ?? "",
      notes: initialValue?.notes ?? "",
    });
  }, [initialValue, travelerGroups]);

  const groupOptions = travelerGroups.includes(form.travelerGroup)
    ? travelerGroups
    : [form.travelerGroup, ...travelerGroups];

  return (
    <form
      className="form-shell"
      onSubmit={(event) => {
        event.preventDefault();
        onSubmit({
          id: initialValue?.id,
          name: form.name.trim(),
          travelerGroup: form.travelerGroup,
          origin: form.origin.trim(),
          destination: form.destination.trim(),
          flightBudgetMax: form.flightBudgetMax.trim(),
          hotelBudgetPerNightMax: form.hotelBudgetPerNightMax.trim(),
          notes: form.notes.trim(),
        });
      }}
    >
      <div className="toolbar-row">
        <div>
          <p className="field-label">Trip template</p>
          <p className="helper-copy">Turn repeat trips into one-tap watch starting points.</p>
        </div>
      </div>

      <div className="form-grid">
        <div className="field-stack">
          <label htmlFor="template-name">Template name</label>
          <input
            id="template-name"
            className="text-input"
            value={form.name}
            onChange={(event) => setForm((current) => ({ ...current, name: event.target.value }))}
            placeholder="Singapore spring week"
            required
            disabled={disabled}
          />
        </div>

        <div className="field-stack">
          <label htmlFor="template-group">Traveler group</label>
          <select
            id="template-group"
            className="text-input"
            value={form.travelerGroup}
            onChange={(event) =>
              setForm((current) => ({ ...current, travelerGroup: event.target.value }))
            }
            disabled={disabled}
          >
            {groupOptions.map((group) => (
              <option key={group} value={group}>
                {group}
              </option>
            ))}
          </select>
        </div>

        <div className="field-stack">
          <label htmlFor="template-origin">Origins</label>
          <input
            id="template-origin"
            className="text-input"
            value={form.origin}
            onChange={(event) => setForm((current) => ({ ...current, origin: event.target.value }))}
            placeholder="HND, NRT"
            disabled={disabled}
          />
        </div>

        <div className="field-stack">
          <label htmlFor="template-destination">Destination</label>
          <input
            id="template-destination"
            className="text-input"
            value={form.destination}
            onChange={(event) =>
              setForm((current) => ({ ...current, destination: event.target.value }))
            }
            placeholder="Singapore"
            disabled={disabled}
          />
        </div>

        <div className="field-stack">
          <label htmlFor="template-flight-budget">Flight budget max</label>
          <input
            id="template-flight-budget"
            className="text-input"
            value={form.flightBudgetMax}
            onChange={(event) =>
              setForm((current) => ({ ...current, flightBudgetMax: event.target.value }))
            }
            placeholder="JPY 160,000"
            disabled={disabled}
          />
        </div>

        <div className="field-stack">
          <label htmlFor="template-hotel-budget">Hotel / night max</label>
          <input
            id="template-hotel-budget"
            className="text-input"
            value={form.hotelBudgetPerNightMax}
            onChange={(event) =>
              setForm((current) => ({ ...current, hotelBudgetPerNightMax: event.target.value }))
            }
            placeholder="JPY 45,000"
            disabled={disabled}
          />
        </div>

        <div className="field-stack field-span-full">
          <label htmlFor="template-notes">Notes</label>
          <textarea
            id="template-notes"
            className="text-area"
            value={form.notes}
            onChange={(event) => setForm((current) => ({ ...current, notes: event.target.value }))}
            placeholder="Business cabin, one stop max, Telegram + email."
            disabled={disabled}
          />
        </div>
      </div>

      <div className="panel-actions">
        <Button type="submit" disabled={disabled}>
          {submitLabel}
        </Button>
        {onCancel ? (
          <Button type="button" variant="ghost" onClick={onCancel} disabled={disabled}>
            Cancel
          </Button>
        ) : null}
      </div>
    </form>
  );
}
