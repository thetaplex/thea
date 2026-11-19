import type { AppSettings } from "./ipc";

const keyOf = (s: AppSettings | null | undefined, id: string) =>
  (s?.provider_configs?.[id]?.api_key ?? "").trim();

/** True when `form` holds an API key that differs from the saved `settings`. */
export const hasUnsavedKey = (form: AppSettings, saved: AppSettings | null): boolean =>
  Object.keys(form.provider_configs ?? {}).some((id) => keyOf(form, id) !== keyOf(saved, id));
