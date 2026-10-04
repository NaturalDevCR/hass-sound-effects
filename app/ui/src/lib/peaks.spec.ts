import { describe, expect, it } from "vitest";
import { computePeaks } from "./peaks";

describe("computePeaks", () => {
  it("partitions every sample, including uneven final buckets", () => {
    expect(computePeaks([new Float32Array([0.1, -0.8, 0.2, -0.4, 0.9])], 2)).toEqual([
      expect.closeTo(0.8),
      expect.closeTo(0.9),
    ]);
  });
  it("takes the absolute maximum across channels and clamps to one", () => {
    expect(computePeaks([new Float32Array([0.2, 2]), new Float32Array([-0.7, 0.1])], 2)).toEqual([
      expect.closeTo(0.7),
      1,
    ]);
  });
  it("returns zeros for silence, empty channels and undersized buffers", () => {
    expect(computePeaks([new Float32Array(6)], 3)).toEqual([0, 0, 0]);
    expect(computePeaks([], 2)).toEqual([0, 0]);
    expect(computePeaks([new Float32Array([1])], 3)).toEqual([0, 0, 1]);
    expect(computePeaks([], 0)).toEqual([]);
  });
});
