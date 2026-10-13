"use client";

import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "@/lib/api";
import type { Settings } from "@/lib/types";

const PROVIDERS = ["yfinance", "nse"];

export default function SettingsPage() {
  const queryClient = useQueryClient();
  const settingsQuery = useQuery({
    queryKey: ["settings"],
    queryFn: () => api<Settings>("GET", "/settings"),
  });

  const [telegramChatId, setTelegramChatId] = useState("");
  const [telegramBotToken, setTelegramBotToken] = useState("");
  const [activeProvider, setActiveProvider] = useState("yfinance");
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (settingsQuery.data) {
      setTelegramChatId(settingsQuery.data.telegram_chat_id ?? "");
      setActiveProvider(settingsQuery.data.active_provider ?? "yfinance");
    }
  }, [settingsQuery.data]);

  const saveMutation = useMutation({
    mutationFn: (body: { telegram_chat_id?: string; telegram_bot_token?: string; active_provider?: string }) =>
      api("PUT", "/settings", body),
    onSuccess: () => {
      setError(null);
      setSaved(true);
      setTelegramBotToken("");
      queryClient.invalidateQueries({ queryKey: ["settings"] });
    },
    onError: (err: unknown) => {
      setSaved(false);
      setError(err instanceof ApiError ? err.message : "Failed to save settings.");
    },
  });

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSaved(false);
    const body: { telegram_chat_id?: string; telegram_bot_token?: string; active_provider?: string } = {
      telegram_chat_id: telegramChatId,
      active_provider: activeProvider,
    };
    if (telegramBotToken.trim() !== "") {
      body.telegram_bot_token = telegramBotToken;
    }
    saveMutation.mutate(body);
  }

  const isLoading = settingsQuery.isLoading;
  const isError = settingsQuery.isError;

  return (
    <section>
      <h2>Settings</h2>
      {isLoading && <p>Loading...</p>}
      {isError && <p>Failed to load settings.</p>}
      {!isLoading && !isError && (
        <form onSubmit={handleSubmit}>
          <div className="row">
            <label>
              Telegram chat ID
              <input
                value={telegramChatId}
                onChange={(e) => setTelegramChatId(e.target.value)}
                placeholder="e.g. 123456789"
              />
            </label>
          </div>

          <div className="row">
            <label>
              Telegram bot token
              <input
                type="password"
                value={telegramBotToken}
                onChange={(e) => setTelegramBotToken(e.target.value)}
                placeholder={
                  settingsQuery.data?.telegram_bot_token_configured
                    ? "configured ✓ (enter a new value to replace)"
                    : "not configured"
                }
              />
            </label>
          </div>

          <div className="row">
            <label>
              Active provider
              <select value={activeProvider} onChange={(e) => setActiveProvider(e.target.value)}>
                {PROVIDERS.map((p) => (
                  <option key={p} value={p}>
                    {p}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <p className="muted">
            Note: this setting is informational for now — the scanner does not yet read it; each
            strategy still uses its own per-strategy provider field.
          </p>

          <div className="row">
            <button type="submit" className="btn" disabled={saveMutation.isPending}>
              {saveMutation.isPending ? "Saving..." : "Save"}
            </button>
          </div>

          {saved && <p className="g">Settings saved.</p>}
          {error && <p className="r">{error}</p>}
        </form>
      )}
    </section>
  );
}
