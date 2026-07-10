import { useEffect, useState, type KeyboardEvent, type ReactNode } from "react";

import type { TravelerProfile } from "@/api/types";
import { Button, Dial, Surface } from "@/components/ui/primitives";
import { TravelerForm } from "@/components/profile/ProfileForms";
import { MultiSelectDropdown } from "@/components/ui/MultiSelectDropdown";
import { AIRLINE_OPTIONS, ALLIANCE_OPTIONS } from "@/data/aviationOptions";
import type { WatchDraft } from "@/api/types";

function textToList(value: string) {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function listToText(values: string[]) {
  return values.join(", ");
}

function toggleDisclosureFromKeyboard(event: KeyboardEvent<HTMLElement>) {
  if (event.key !== "Enter" && event.key !== " ") {
    return;
  }

  event.preventDefault();
  const disclosure = event.currentTarget.parentElement;
  if (disclosure instanceof HTMLDetailsElement) {
    disclosure.open = !disclosure.open;
  }
}

export function WatchForm({
  initialValue,
  submitLabel,
  onSubmit,
  onCreateTraveler,
  secondaryAction,
  onCancel,
  disabled = false,
}: {
  initialValue: WatchDraft;
  submitLabel: string;
  onSubmit: (value: WatchDraft) => void;
  onCreateTraveler?: (
    value: Omit<TravelerProfile, "id"> & { id?: string },
  ) => Promise<TravelerProfile>;
  secondaryAction?: ReactNode;
  onCancel?: () => void;
  disabled?: boolean;
}) {
  const [form, setForm] = useState(initialValue);
  const [isAddingTraveler, setIsAddingTraveler] = useState(false);
  const [isCreatingTraveler, setIsCreatingTraveler] = useState(false);
  const [travelerCreateError, setTravelerCreateError] = useState<string | null>(null);

  useEffect(() => {
    setForm(initialValue);
  }, [initialValue]);

  const selectedGroup =
    form.travelerGroups.find((group) => group.id === form.selectedGroupId) ??
    form.travelerGroups.find((group) => group.name === form.selectedGroup);
  const selectedTravelers = form.travelerOptions.filter((traveler) =>
    form.selectedTravelerIds.includes(traveler.id),
  );

  function toggleTraveler(travelerId: string) {
    setForm((current) => {
      const selectedTravelerIds = current.selectedTravelerIds.includes(travelerId)
        ? current.selectedTravelerIds.filter((id) => id !== travelerId)
        : [...current.selectedTravelerIds, travelerId];
      return {
        ...current,
        selectedTravelerIds,
        selectedGroupId: "",
        selectedGroup: selectedTravelerIds.length === 0 ? "" : `${selectedTravelerIds.length} selected`,
      };
    });
  }

  async function handleCreateTraveler(
    traveler: Omit<TravelerProfile, "id"> & { id?: string },
  ) {
    if (!onCreateTraveler) {
      return;
    }

    setIsCreatingTraveler(true);
    setTravelerCreateError(null);
    try {
      const createdTraveler = await onCreateTraveler(traveler);
      setForm((current) => ({
        ...current,
        travelerOptions: [
          ...current.travelerOptions,
          {
            id: createdTraveler.id,
            displayName: createdTraveler.displayName,
            relationship: createdTraveler.relationship,
          },
        ],
        selectedTravelerIds: [...current.selectedTravelerIds, createdTraveler.id],
        selectedGroupId: "",
        selectedGroup: `${current.selectedTravelerIds.length + 1} selected`,
      }));
      setIsAddingTraveler(false);
    } catch (error) {
      setTravelerCreateError(error instanceof Error ? error.message : "Unable to add traveler inline.");
    } finally {
      setIsCreatingTraveler(false);
    }
  }

  return (
    <form
      className="stack"
      onSubmit={(event) => {
        event.preventDefault();
        onSubmit({
          ...form,
          selectedGroup: selectedGroup?.name ?? form.selectedGroup,
          selectedGroupId: selectedGroup?.id ?? form.selectedGroupId,
          origins: form.origins.trim(),
          destination: form.destination.trim(),
          flexibleRegion: form.flexibleRegion.trim(),
          flexibleTheme: form.flexibleTheme.trim(),
          cabinClass: form.cabinClass.trim(),
          preferredAirlines: form.preferredAirlines.trim(),
          preferredAlliances: form.preferredAlliances.trim(),
          budgetCurrency: form.budgetCurrency.trim().toUpperCase() || "JPY",
          flightBudget: form.flightBudget.trim(),
          hotelBudget: form.hotelBudget.trim(),
          hotelMinRating: form.hotelMinRating.trim(),
          idealPrice: form.idealPrice.trim(),
          glideStartDays: form.glideStartDays.trim(),
          glideEndDays: form.glideEndDays.trim(),
          maxStops: form.maxStops.trim(),
          maxLayoverMinutes: form.maxLayoverMinutes.trim(),
          minConnectionMinutes: form.minConnectionMinutes.trim(),
          tripMinNights: form.tripMinNights.trim(),
          tripMaxNights: form.tripMaxNights.trim(),
        });
      }}
    >
      <div>
        <p className="field-label">Who's traveling</p>
        <Surface className="inset-card">
          <div className="toolbar-row">
            <div>
              <p className="item-title">Saved travelers</p>
              <p className="helper-copy">
                Select the exact travelers for this watch, or use a saved family preset.
              </p>
            </div>
            <div className="button-row">
              {onCreateTraveler ? (
                <Button
                  type="button"
                  variant="secondary"
                  onClick={() => {
                    setTravelerCreateError(null);
                    setIsAddingTraveler((current) => !current);
                  }}
                >
                  {isAddingTraveler ? "Close traveler form" : "Add traveler here"}
                </Button>
              ) : null}
              <Button type="button" variant="ghost" to="/profile">
                Manage saved travelers
              </Button>
            </div>
          </div>

          {form.travelerOptions.length > 0 ? (
            <div className="traveler-selector-grid">
              {form.travelerOptions.map((traveler) => (
                <button
                  key={traveler.id}
                  type="button"
                  className={`traveler-selector-card ${form.selectedTravelerIds.includes(traveler.id) ? "traveler-selector-card-active" : ""}`}
                  onClick={() => toggleTraveler(traveler.id)}
                  disabled={disabled}
                >
                  <strong>{traveler.displayName}</strong>
                  <span>{traveler.relationship.replace(/_/g, " ")}</span>
                </button>
              ))}
            </div>
          ) : (
            <div className="muted-card">
              <p className="item-title">No saved travelers yet</p>
              <p className="item-copy">
                Add travelers first so this watch can be attached to the right people.
              </p>
            </div>
          )}

          {form.travelerGroups.length > 0 ? (
            <div className="stack-tight">
              <p className="field-label">Quick family presets</p>
              <div className="pill-row" role="list" aria-label="Traveler groups">
                {form.travelerGroups.map((group) => (
                  <button
                    key={group.id || group.name}
                    type="button"
                    className={`pill pill-button ${group.id === form.selectedGroupId ? "pill-selected" : ""}`}
                    onClick={() =>
                      setForm((current) => ({
                        ...current,
                        selectedGroupId: group.id,
                        selectedGroup: group.name,
                        selectedTravelerIds: group.travelerIds,
                      }))
                    }
                    disabled={disabled}
                  >
                    {group.name}
                  </button>
                ))}
              </div>
            </div>
          ) : null}

          {isAddingTraveler && onCreateTraveler ? (
            <Surface className="inset-card">
              <TravelerForm
                submitLabel="Save traveler"
                onSubmit={handleCreateTraveler}
                onCancel={() => {
                  setIsAddingTraveler(false);
                  setTravelerCreateError(null);
                }}
                disabled={disabled || isCreatingTraveler}
              />
              {travelerCreateError ? (
                <div className="notice notice-alert">{travelerCreateError}</div>
              ) : null}
            </Surface>
          ) : null}
        </Surface>
      </div>

      <div className="preview-grid">
        <div className="field-stack">
          <label htmlFor="watch-origins">From</label>
          <input
            id="watch-origins"
            className="text-input"
            value={form.origins}
            onChange={(event) => setForm((current) => ({ ...current, origins: event.target.value }))}
            placeholder="HND, NRT"
            disabled={disabled}
          />
          <p className="helper-copy">Comma-separated IATA codes. Prefilled from profile defaults when available.</p>
        </div>

        <div className="field-stack">
          <label htmlFor="watch-trip-mode">Trip mode</label>
          <select
            id="watch-trip-mode"
            className="text-input"
            value={form.tripMode}
            onChange={(event) => setForm((current) => ({ ...current, tripMode: event.target.value }))}
            disabled={disabled}
          >
            <option value="flights_then_hotels">Flights then hotels</option>
            <option value="flights_only">Flights only</option>
            <option value="hotels_only">Hotels only</option>
          </select>
        </div>

        <div className="field-stack">
          <label htmlFor="watch-destination-mode">Destination mode</label>
          <select
            id="watch-destination-mode"
            className="text-input"
            value={form.destinationMode}
            onChange={(event) =>
              setForm((current) => ({
                ...current,
                destinationMode: event.target.value as WatchDraft["destinationMode"],
              }))
            }
            disabled={disabled}
          >
            <option value="fixed">Fixed destination</option>
            <option value="flexible">Flexible inspiration</option>
          </select>
        </div>

        {form.destinationMode === "fixed" ? (
          <div className="field-stack">
            <label htmlFor="watch-destination">To</label>
            <input
              id="watch-destination"
              className="text-input"
              value={form.destination}
              onChange={(event) => setForm((current) => ({ ...current, destination: event.target.value }))}
              placeholder="SIN, CDG"
              disabled={disabled}
            />
          </div>
        ) : (
          <>
            <div className="field-stack">
              <label htmlFor="watch-flex-region">Flexible region</label>
              <input
                id="watch-flex-region"
                className="text-input"
                value={form.flexibleRegion}
                onChange={(event) => setForm((current) => ({ ...current, flexibleRegion: event.target.value }))}
                placeholder="Southeast Asia"
                disabled={disabled}
              />
            </div>

            <div className="field-stack">
              <label htmlFor="watch-flex-theme">Flexible theme</label>
              <input
                id="watch-flex-theme"
                className="text-input"
                value={form.flexibleTheme}
                onChange={(event) => setForm((current) => ({ ...current, flexibleTheme: event.target.value }))}
                placeholder="Anywhere warm"
                disabled={disabled}
              />
            </div>
          </>
        )}

        <div className="field-stack">
          <label htmlFor="watch-depart-from">Depart from</label>
          <input
            id="watch-depart-from"
            className="text-input"
            type="date"
            value={form.departDateFrom}
            onChange={(event) => setForm((current) => ({ ...current, departDateFrom: event.target.value }))}
            disabled={disabled}
          />
        </div>

        <div className="field-stack">
          <label htmlFor="watch-depart-to">Depart to</label>
          <input
            id="watch-depart-to"
            className="text-input"
            type="date"
            value={form.departDateTo}
            onChange={(event) => setForm((current) => ({ ...current, departDateTo: event.target.value }))}
            disabled={disabled}
          />
        </div>

        <div className="field-stack">
          <label htmlFor="watch-return-from">Return from</label>
          <input
            id="watch-return-from"
            className="text-input"
            type="date"
            value={form.returnDateFrom}
            onChange={(event) => setForm((current) => ({ ...current, returnDateFrom: event.target.value }))}
            disabled={disabled}
          />
        </div>

        <div className="field-stack">
          <label htmlFor="watch-return-to">Return to</label>
          <input
            id="watch-return-to"
            className="text-input"
            type="date"
            value={form.returnDateTo}
            onChange={(event) => setForm((current) => ({ ...current, returnDateTo: event.target.value }))}
            disabled={disabled}
          />
        </div>

        <div className="field-stack">
          <label htmlFor="watch-min-nights">Min nights</label>
          <input
            id="watch-min-nights"
            className="text-input"
            value={form.tripMinNights}
            onChange={(event) => setForm((current) => ({ ...current, tripMinNights: event.target.value }))}
            placeholder="5"
            inputMode="numeric"
            disabled={disabled}
          />
        </div>

        <div className="field-stack">
          <label htmlFor="watch-max-nights">Max nights</label>
          <input
            id="watch-max-nights"
            className="text-input"
            value={form.tripMaxNights}
            onChange={(event) => setForm((current) => ({ ...current, tripMaxNights: event.target.value }))}
            placeholder="9"
            inputMode="numeric"
            disabled={disabled}
          />
        </div>

        <div className="field-stack">
          <label htmlFor="watch-budget-currency">Currency</label>
          <input
            id="watch-budget-currency"
            className="text-input"
            value={form.budgetCurrency}
            onChange={(event) => setForm((current) => ({ ...current, budgetCurrency: event.target.value }))}
            placeholder="JPY"
            disabled={disabled}
          />
        </div>

        <div className="field-stack">
          <label htmlFor="watch-flight-budget">Flight budget max</label>
          <input
            id="watch-flight-budget"
            className="text-input"
            value={form.flightBudget}
            onChange={(event) => setForm((current) => ({ ...current, flightBudget: event.target.value }))}
            placeholder="160000"
            disabled={disabled}
          />
        </div>

        <div className="field-stack">
          <label htmlFor="watch-hotel-budget">Hotel / night max</label>
          <input
            id="watch-hotel-budget"
            className="text-input"
            value={form.hotelBudget}
            onChange={(event) => setForm((current) => ({ ...current, hotelBudget: event.target.value }))}
            placeholder="45000"
            disabled={disabled}
          />
        </div>
      </div>

      <Surface className="inset-card">
        <p className="field-label">Luxury to savings dial</p>
        <div className="stack-tight">
          <Dial value={form.luxuryVsSavings} />
          <div className="range-row">
            <span>Luxury</span>
            <input
              className="range-input"
              type="range"
              min="0"
              max="100"
              value={Math.round(form.luxuryVsSavings * 100)}
              onChange={(event) =>
                setForm((current) => ({
                  ...current,
                  luxuryVsSavings: Number(event.target.value) / 100,
                }))
              }
              disabled={disabled}
            />
            <strong>{Math.round(form.luxuryVsSavings * 100)}%</strong>
          </div>
          <p className="helper-copy">
            Leave the advanced comfort filters blank and TRAMP will prefer fewer stops, cleaner timings,
            and the highest realistic cabin quality it can justify for the value.
          </p>
        </div>
      </Surface>

      <details className="form-disclosure">
        <summary onKeyDown={toggleDisclosureFromKeyboard}>Advanced flight preferences</summary>
        <div className="form-grid form-grid-gap-top">
          <div className="field-stack">
            <label htmlFor="watch-cabin">Cabin</label>
            <select
              id="watch-cabin"
              className="text-input"
              value={form.cabinClass}
              onChange={(event) => setForm((current) => ({ ...current, cabinClass: event.target.value }))}
              disabled={disabled}
            >
              <option value="">Any cabin</option>
              <option value="economy">Economy</option>
              <option value="premium_economy">Premium economy</option>
              <option value="business">Business</option>
              <option value="first">First</option>
            </select>
            <p className="helper-copy">Leave blank to let TRAMP optimize cabin quality automatically.</p>
          </div>

          <div className="field-stack">
            <label htmlFor="watch-max-stops">Max stops</label>
            <input
              id="watch-max-stops"
              className="text-input"
              value={form.maxStops}
              onChange={(event) => setForm((current) => ({ ...current, maxStops: event.target.value }))}
              placeholder="1"
              inputMode="numeric"
              disabled={disabled}
            />
            <p className="helper-copy">Optional. Leave blank to let the algorithm prefer fewer stops without hard-limiting them.</p>
          </div>

          <div className="field-stack">
            <label htmlFor="watch-max-layover">Max layover minutes</label>
            <input
              id="watch-max-layover"
              className="text-input"
              value={form.maxLayoverMinutes}
              onChange={(event) => setForm((current) => ({ ...current, maxLayoverMinutes: event.target.value }))}
              placeholder="180"
              inputMode="numeric"
              disabled={disabled}
            />
            <p className="helper-copy">Optional. Leave blank and TRAMP will prefer shorter layovers on its own.</p>
          </div>

          <div className="field-stack">
            <label htmlFor="watch-min-connection">Min connection minutes</label>
            <input
              id="watch-min-connection"
              className="text-input"
              value={form.minConnectionMinutes}
              onChange={(event) =>
                setForm((current) => ({ ...current, minConnectionMinutes: event.target.value }))
              }
              placeholder="75"
              inputMode="numeric"
              disabled={disabled}
            />
            <p className="helper-copy">Optional safety preference for tight transfers.</p>
          </div>

          <MultiSelectDropdown
            id="watch-airlines"
            label="Preferred airlines"
            options={AIRLINE_OPTIONS}
            selectedValues={textToList(form.preferredAirlines)}
            onChange={(preferredAirlines) =>
              setForm((current) => ({ ...current, preferredAirlines: listToText(preferredAirlines) }))
            }
            disabled={disabled}
            helperText="Leave blank to include all airlines by default, including carriers not listed here."
            otherPlaceholder="Add IATA or ICAO code"
          />

          <MultiSelectDropdown
            id="watch-alliances"
            label="Preferred alliances"
            options={ALLIANCE_OPTIONS}
            selectedValues={textToList(form.preferredAlliances)}
            onChange={(preferredAlliances) =>
              setForm((current) => ({ ...current, preferredAlliances: listToText(preferredAlliances) }))
            }
            disabled={disabled}
            helperText="Leave blank to include all alliances and non-aligned carriers by default."
            otherPlaceholder="Add other alliance"
          />

          <label className="checkbox-row">
            <input
              type="checkbox"
              checked={form.avoidRedeye}
              onChange={(event) => setForm((current) => ({ ...current, avoidRedeye: event.target.checked }))}
              disabled={disabled}
            />
            <span>Avoid red-eye flights.</span>
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
            <span>Prefer refundable inventory when possible.</span>
          </label>
        </div>
      </details>

      <details className="form-disclosure">
        <summary onKeyDown={toggleDisclosureFromKeyboard}>Pricing and monitoring controls</summary>
        <div className="form-grid form-grid-gap-top">
          <div className="field-stack">
            <label htmlFor="watch-status">Status</label>
            <select
              id="watch-status"
              className="text-input"
              value={form.status}
              onChange={(event) =>
                setForm((current) => ({ ...current, status: event.target.value as WatchDraft["status"] }))
              }
              disabled={disabled}
            >
              <option value="active">Active</option>
              <option value="paused">Paused</option>
              <option value="fulfilled">Fulfilled</option>
            </select>
          </div>

          <div className="field-stack">
            <label htmlFor="watch-hotel-rating">Hotel min rating</label>
            <input
              id="watch-hotel-rating"
              className="text-input"
              value={form.hotelMinRating}
              onChange={(event) => setForm((current) => ({ ...current, hotelMinRating: event.target.value }))}
              placeholder="4.5"
              disabled={disabled}
            />
          </div>

          <div className="field-stack">
            <label htmlFor="watch-notify">Notify via</label>
            <select
              id="watch-notify"
              className="text-input"
              value={form.notifyChannel}
              onChange={(event) => setForm((current) => ({ ...current, notifyChannel: event.target.value }))}
              disabled={disabled}
            >
              <option value="inherit">Inherit</option>
              <option value="email">Email</option>
              <option value="telegram">Telegram</option>
              <option value="both">Both</option>
            </select>
          </div>

          <div className="field-stack">
            <label htmlFor="watch-refresh">Check cadence</label>
            <select
              id="watch-refresh"
              className="text-input"
              value={form.refreshInterval}
              onChange={(event) => setForm((current) => ({ ...current, refreshInterval: event.target.value }))}
              disabled={disabled}
            >
              <option value="daily">Daily</option>
              <option value="6h">6h</option>
              <option value="hourly">Hourly</option>
            </select>
          </div>

          <div className="field-stack">
            <label htmlFor="watch-ideal-price">Ideal price</label>
            <input
              id="watch-ideal-price"
              className="text-input"
              value={form.idealPrice}
              onChange={(event) => setForm((current) => ({ ...current, idealPrice: event.target.value }))}
              placeholder="118400"
              disabled={disabled}
            />
          </div>

          <div className="field-stack">
            <label htmlFor="watch-glide-start">Booking urgency starts at</label>
            <input
              id="watch-glide-start"
              className="text-input"
              value={form.glideStartDays}
              onChange={(event) => setForm((current) => ({ ...current, glideStartDays: event.target.value }))}
              placeholder="42"
              inputMode="numeric"
              disabled={disabled}
            />
            <p className="helper-copy">
              Days before departure when TRAMP starts getting more price-sensitive and urgency-aware.
            </p>
          </div>

          <div className="field-stack">
            <label htmlFor="watch-glide-end">Late-booking urgency at</label>
            <input
              id="watch-glide-end"
              className="text-input"
              value={form.glideEndDays}
              onChange={(event) => setForm((current) => ({ ...current, glideEndDays: event.target.value }))}
              placeholder="3"
              inputMode="numeric"
              disabled={disabled}
            />
            <p className="helper-copy">
              Days before departure when TRAMP treats booking as late-stage and favors acting sooner.
            </p>
          </div>

          <label className="checkbox-row">
            <input
              type="checkbox"
              checked={form.wantCar}
              onChange={(event) => setForm((current) => ({ ...current, wantCar: event.target.checked }))}
              disabled={disabled}
            />
            <span>Include car search context when it is available.</span>
          </label>

          <label className="checkbox-row">
            <input
              type="checkbox"
              checked={form.includeAirbnb}
              onChange={(event) => setForm((current) => ({ ...current, includeAirbnb: event.target.checked }))}
              disabled={disabled}
            />
            <span>Include Airbnb discovery if this backend supports it.</span>
          </label>
        </div>
      </details>

      <div className="panel-actions">
        <Button type="submit" disabled={disabled}>
          {submitLabel}
        </Button>
        {secondaryAction}
        {onCancel ? (
          <Button type="button" variant="ghost" onClick={onCancel} disabled={disabled}>
            Cancel
          </Button>
        ) : null}
      </div>

      {selectedTravelers.length > 0 ? (
        <p className="helper-copy">
          Selected travelers: {selectedTravelers.map((traveler) => traveler.displayName).join(", ")}
        </p>
      ) : form.travelerOptions.length > 0 ? (
        <p className="helper-copy">No travelers selected yet. Pick at least one saved traveler for this watch.</p>
      ) : (
        <p className="helper-copy">
          This form can still save a draft, but adding saved travelers makes who-travels selection much clearer.
        </p>
      )}
    </form>
  );
}
