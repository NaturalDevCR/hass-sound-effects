/** Max absolute amplitude across channels; integer partitions include every sample once. */
export function computePeaks(channels: Float32Array[], buckets: number): number[] {
  const count = Math.max(0, Math.floor(buckets));
  const length = Math.max(0, ...channels.map((channel) => channel.length));
  return Array.from({ length: count }, (_, bucket) => {
    const start = Math.floor((bucket * length) / count);
    const end = Math.floor(((bucket + 1) * length) / count);
    let max = 0;
    for (const channel of channels) {
      for (let i = start; i < Math.min(end, channel.length); i++)
        max = Math.max(max, Math.abs(channel[i] ?? 0));
    }
    return Math.min(1, max);
  });
}
