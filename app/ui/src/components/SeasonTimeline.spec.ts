import { mount, flushPromises } from "@vue/test-utils";
import { describe, it, expect, vi } from "vitest";
import SeasonTimeline from "./SeasonTimeline.vue";
import { makeSeason } from "@/test/factories";
import { ui } from "@/api/client";
describe("SeasonTimeline", () => {
  it("draws wrap-around ranges as two segments and October as one; regular is excluded", () => {
    const w = mount(SeasonTimeline, {
      props: {
        seasons: [
          makeSeason({ id: "winter", start: "12-01", end: "01-06" }),
          makeSeason({ id: "oct", start: "10-01", end: "10-31" }),
          makeSeason({ id: "regular" }),
        ],
      },
    });
    expect(w.findAll('[data-season="winter"]')).toHaveLength(2);
    expect(w.findAll('[data-season="oct"]')).toHaveLength(1);
    expect(w.findAll('[data-season="regular"]')).toHaveLength(0);
    expect(w.get('[data-season="winter"]').attributes("aria-label")).toContain("12-01");
    expect(w.findAll('[data-test="month"]')).toHaveLength(12);
    expect(w.find('[data-test="today"]').exists()).toBe(true);
  });
  it("resolves a date using the API and shows the returned season", async () => {
    const resolve = vi.spyOn(ui.seasons, "resolve").mockResolvedValue({ date: "2026-10-31", season_id: "oct" });
    const w = mount(SeasonTimeline, {
      props: {
        seasons: [
          makeSeason({
            id: "oct",
            name: "Halloween",
            start: "10-01",
            end: "10-31",
          }),
        ],
      },
    });
    await w.get('input[type="date"]').setValue("2026-10-31");
    await flushPromises();
    expect(resolve).toHaveBeenCalledWith("2026-10-31");
    expect(w.text()).toContain("Halloween");
    resolve.mockRestore();
  });
});
it("ignores stale date results and presents resolve errors inline", async () => {
  let finish!: (value: { date: string; season_id: string }) => void;
  const resolve = vi
    .spyOn(ui.seasons, "resolve")
    .mockImplementationOnce(
      () =>
        new Promise((r) => {
          finish = r;
        }),
    )
    .mockRejectedValueOnce(new Error("date unavailable"));
  const w = mount(SeasonTimeline, {
    props: { seasons: [makeSeason({ id: "old", name: "Old result" })] },
  });
  await w.get('input[type="date"]').setValue("2026-01-01");
  await w.get('input[type="date"]').setValue("2026-02-01");
  await flushPromises();
  finish({ date: "2026-01-01", season_id: "old" });
  await flushPromises();
  expect(w.get('[role="alert"]').text()).toBe("date unavailable");
  expect(w.text()).not.toContain("Old result");
  resolve.mockRestore();
});
