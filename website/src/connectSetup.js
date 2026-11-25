// The connection a card's Connect opens (outbound.connect_fix's `#connector=<type>`) - '' for a link that is not one connection's own card
// (Email's section, the images section): those still open where they point.
export const setupType = (href) => (/^#connector=([a-z0-9_-]+)$/i.exec(String(href || "")) || [])[1]?.toLowerCase() || "";
