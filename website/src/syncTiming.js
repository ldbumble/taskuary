// The server's scheduler wakes every 30 seconds. Far from the next scheduled sync the Timeline
// can check quietly; near (and just after) the due time it must watch closely or a short refresh
// can start and finish between UI checks and the sync glyph never moves.
export const syncStatusDelay = ({ running = false, nextAt = null, now = Date.now() } = {}) => {
  if (running) return 2000;
  if (!nextAt) return 30000;
  const untilDue = nextAt - now;
  return untilDue > 35000 ? Math.min(30000, untilDue - 30000) : 500;
};
