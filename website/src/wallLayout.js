// Pure wall-layout operations live here so drag behavior can be verified without a browser.
export const movePane = (order, from, target) => {
  if (!from || !target || from === target) return order;
  const next = [...order], fromAt = next.indexOf(from), targetAt = next.indexOf(target);
  if (fromAt < 0 || targetAt < 0) return order;
  next.splice(targetAt, 0, next.splice(fromAt, 1)[0]);
  return next;
};

export const resizedPaneHeight = (startHeight, startY, clientY, minimum) =>
  Math.max(minimum, Math.round(startHeight + clientY - startY));
