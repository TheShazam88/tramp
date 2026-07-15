import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { newWatchDraft } from "@/api/mockData";
import type { WatchDraft } from "@/api/types";
import { WatchForm } from "@/components/watch/WatchForm";

function renderWatchForm(initialValue: WatchDraft = structuredClone(newWatchDraft)) {
  const onSubmit = vi.fn<(value: WatchDraft) => void>();
  const user = userEvent.setup();

  render(
    <MemoryRouter>
      <WatchForm
        initialValue={initialValue}
        submitLabel="Save watch"
        onSubmit={onSubmit}
      />
    </MemoryRouter>,
  );

  return { onSubmit, user };
}

describe("WatchForm progressive disclosure", () => {
  it("starts advanced groups collapsed and opens them from the keyboard", async () => {
    const { user } = renderWatchForm();
    const flightDetails = screen.getByRole("group", {
      name: "Advanced flight preferences",
    });
    const flightSummary = within(flightDetails).getByLabelText(
      "Advanced flight preferences toggle",
    );
    const pricingDetails = screen.getByRole("group", {
      name: "Pricing and monitoring controls",
    });
    const pricingSummary = within(pricingDetails).getByLabelText(
      "Pricing and monitoring controls toggle",
    );

    expect(flightDetails).not.toHaveAttribute("open");
    expect(pricingDetails).not.toHaveAttribute("open");

    flightSummary.focus();
    expect(flightSummary).toHaveFocus();
    await user.keyboard("{Enter}");
    expect(flightDetails).toHaveAttribute("open");

    for (const label of [
      "Cabin",
      "Max stops",
      "Max layover minutes",
      "Min connection minutes",
      "Avoid red-eye flights.",
      "Prefer refundable inventory when possible.",
    ]) {
      expect(within(flightDetails).getByLabelText(label)).toBeVisible();
    }
    expect(
      within(flightDetails).getByText("Preferred airlines"),
    ).toBeVisible();
    expect(
      within(flightDetails).getByText("Preferred alliances"),
    ).toBeVisible();

    pricingSummary.focus();
    expect(pricingSummary).toHaveFocus();
    await user.keyboard("{Enter}");
    expect(pricingDetails).toHaveAttribute("open");

    for (const label of [
      "Status",
      "Hotel min rating",
      "Notify via",
      "Check cadence",
      "Ideal price",
      "Booking urgency starts at",
      "Late-booking urgency at",
      "Include car search context when it is available.",
      "Include Airbnb discovery if this backend supports it.",
    ]) {
      expect(within(pricingDetails).getByLabelText(label)).toBeVisible();
    }
  });

  it("submits every field value while advanced groups begin collapsed", async () => {
    const initialValue: WatchDraft = {
      ...structuredClone(newWatchDraft),
      status: "paused",
      origins: "  HND, NRT  ",
      destination: "  SIN  ",
      flexibleRegion: "  Southeast Asia  ",
      flexibleTheme: "  Warm beach  ",
      cabinClass: "business",
      maxStops: " 2 ",
      maxLayoverMinutes: " 240 ",
      minConnectionMinutes: " 90 ",
      preferredAirlines: " ANA, JAL ",
      preferredAlliances: " Star Alliance ",
      budgetCurrency: " usd ",
      flightBudget: " 160000 ",
      hotelBudget: " 45000 ",
      hotelMinRating: " 4.7 ",
      preferRefundable: false,
      avoidRedeye: false,
      includeAirbnb: true,
      wantCar: true,
      notifyChannel: "telegram",
      refreshInterval: "hourly",
      idealPrice: " 118400 ",
      glideStartDays: " 35 ",
      glideEndDays: " 5 ",
      tripMinNights: " 4 ",
      tripMaxNights: " 8 ",
    };
    const { onSubmit, user } = renderWatchForm(initialValue);

    await user.click(screen.getByRole("button", { name: "Save watch" }));

    expect(onSubmit).toHaveBeenCalledWith({
      ...initialValue,
      origins: "HND, NRT",
      destination: "SIN",
      flexibleRegion: "Southeast Asia",
      flexibleTheme: "Warm beach",
      cabinClass: "business",
      preferredAirlines: "ANA, JAL",
      preferredAlliances: "Star Alliance",
      budgetCurrency: "USD",
      flightBudget: "160000",
      hotelBudget: "45000",
      hotelMinRating: "4.7",
      idealPrice: "118400",
      glideStartDays: "35",
      glideEndDays: "5",
      maxStops: "2",
      maxLayoverMinutes: "240",
      minConnectionMinutes: "90",
      tripMinNights: "4",
      tripMaxNights: "8",
    });
  });
});
