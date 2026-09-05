import { useEffect, useMemo, useState } from "react";
import API from "../api/api";
import { steamIdForPlayer } from "../utils/playerAppearance.js";

export const STEAM_AVATAR_REQUEST_TIMEOUT_MS = 8_000;

function requestAvatars(requestKey, signal) {
  return API.get("/steam/player-avatars", {
    params: { steam_ids: requestKey },
    timeout: STEAM_AVATAR_REQUEST_TIMEOUT_MS,
    signal,
  })
    .then((response) => ({
      avatars: response?.data?.avatars || {},
      onlineAssetsEnabled: response?.data?.enabled === true,
    }))
    .catch(() => ({ avatars: {}, onlineAssetsEnabled: false }));
}

export function useSteamPlayerAvatars(players) {
  const requestKey = useMemo(() => [...new Set(
    (Array.isArray(players) ? players : [])
      .map(steamIdForPlayer)
      .filter(Boolean),
  )].slice(0, 10).join(","), [players]);
  const [result, setResult] = useState({ avatars: {}, onlineAssetsEnabled: false });

  useEffect(() => {
    if (!requestKey) {
      setResult({ avatars: {}, onlineAssetsEnabled: false });
      return undefined;
    }
    let cancelled = false;
    const controller = new AbortController();
    requestAvatars(requestKey, controller.signal).then((next) => {
      if (!cancelled) setResult(next);
    });
    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [requestKey]);

  return result;
}
