// THE CLOSE-OUT CARD READS GITHUB BEFORE IT OFFERS ANYTHING (the owner, 2026-09-28: "the close out should use api to get
// the state of the pr and have the correct buttons"). One reading - server ghcloseout.assess, the same one that guards the
// merge - says whether Close out may merge now, why not, and which other buttons fit: Update branch, Re-run checks,
// Close out anyway. Nothing here decides; the card only draws what the reading says.
import { useCallback, useEffect, useState } from "react";
import api from "./api";

export const OFFER_LABEL = { update: "Update branch", rerun: "Re-run checks", anyway: "Close out anyway" };
export const OFFER_HINT = {
  update: "GitHub merges the base into the pull request, so its checks run again against today's base",
  rerun: "Re-runs the failed checks on the pull request's head commit",
  anyway: "Merges although the card says why it should not - only where this repository and your settings allow it",
};

export function useCloseoutState(rid) {
  const [gh, setGh] = useState(null);
  const load = useCallback(() => {
    if (!rid) { setGh(null); return; }
    api.get(`/api/reviews/${rid}/closeout`).then(({ data }) => setGh(data)).catch(() => setGh(null));
  }, [rid]);
  useEffect(() => { load(); }, [load]);
  // Update branch / Re-run checks: run on GitHub, then read the card again - neither closes anything
  const act = async (what) => {
    const { data } = await api.post(`/api/reviews/${rid}/closeout/${what}`);
    load();
    return data?.said || "";
  };
  return { gh, reload: load, act };
}
