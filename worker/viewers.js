/* worker/viewers.js — how many receivers are tuned in.
 *
 * Once segments come from the CDN (docs/scaling.tex, tier 1) the tower never
 * sees a viewer again and Owncast's viewerCount reads nothing. Every player
 * re-fetches the variant playlist every few seconds though, so the CDN's
 * analytics know exactly who is pulling it. This asks the GraphQL API for the
 * distinct client IPs that fetched the playlist in the last few minutes and
 * calls that the receiver count.
 *
 *   env.CF_ANALYTICS_TOKEN   secret; Analytics Read on the zone, nothing else
 *   env.ANALYTICS_ZONE_TAG   the zone id (wrangler.jsonc vars)
 *   env.HLS_HOST             the CDN host players pull from (wrangler.jsonc vars)
 */

const GRAPHQL_URL = "https://api.cloudflare.com/client/v4/graphql";
const VARIANT_PLAYLIST = "/hls/0/stream.m3u8";

/* A receiver is anyone who pulled the playlist this recently. Analytics lag
 * the edge by about a minute, so a short window would flicker. */
export const RECEIVER_WINDOW_S = 300;

/* One row per client IP. Past this the answer is a floor, not a count. */
const MAX_GROUPS = 5000;

const GRAPHQL_TIMEOUT_MS = 8000;

export function configured(env) {
  return Boolean(env.CF_ANALYTICS_TOKEN && env.ANALYTICS_ZONE_TAG && env.HLS_HOST);
}

/* Returns the number of distinct client IPs, or null when the answer is not
 * to be trusted (unconfigured, API error, timeout). Never throws. */
export async function countReceivers(env, now = new Date()) {
  if (!configured(env)) return null;

  const until = new Date(now.getTime());
  const since = new Date(until.getTime() - RECEIVER_WINDOW_S * 1000);
  const query = `{
    viewer {
      zones(filter: {zoneTag: "${env.ANALYTICS_ZONE_TAG}"}) {
        httpRequestsAdaptiveGroups(limit: ${MAX_GROUPS}, filter: {
          datetime_geq: "${since.toISOString()}",
          datetime_lt: "${until.toISOString()}",
          clientRequestHTTPHost: "${env.HLS_HOST}",
          clientRequestPath: "${VARIANT_PLAYLIST}"
        }) { dimensions { clientIP } }
      }
    }
  }`;

  try {
    const r = await fetch(GRAPHQL_URL, {
      method: "POST",
      headers: { "Authorization": `Bearer ${env.CF_ANALYTICS_TOKEN}`, "Content-Type": "application/json" },
      body: JSON.stringify({ query }),
      signal: AbortSignal.timeout(GRAPHQL_TIMEOUT_MS),
    });
    if (!r.ok) return null;

    const body = await r.json();
    const zones = body?.data?.viewer?.zones;
    if (!Array.isArray(zones) || !zones.length) return null;

    const groups = zones[0].httpRequestsAdaptiveGroups;
    return Array.isArray(groups) ? groups.length : null;
  } catch (e) {
    return null;
  }
}
