"use client";

import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type FormEvent,
} from "react";
import { getQueries, getQuery, startDesignQuery } from "./api";
import { isActive } from "./progress";
import type { ArchitectureMode, DesignQuery, QuerySummary } from "./types";

function address(queryId?: string, replace = false) {
  const url = queryId ? "/?query=" + encodeURIComponent(queryId) : "/";
  if (window.location.pathname + window.location.search !== url) {
    window.history[replace ? "replaceState" : "pushState"](null, "", url);
  }
}

export function useDesignWorkspace() {
  const [problem, setProblem] = useState("");
  const [mode, setMode] = useState<ArchitectureMode>("balanced");
  const [clarifications, setClarifications] = useState<Record<string, string>>(
    {},
  );
  const [query, setQuery] = useState<DesignQuery | null>(null);
  const [queries, setQueries] = useState<QuerySummary[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [connected, setConnected] = useState<boolean | null>(null);
  const [historyError, setHistoryError] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [opening, setOpening] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pollError, setPollError] = useState(false);
  const viewVersion = useRef(0);
  const latest = query?.runs.at(-1);
  const loading = isActive(latest);
  const busy = submitting || opening || loading;
  const selected =
    query?.runs.find((run) => run.run_id === selectedRunId) ?? latest;

  const refreshHistory = useCallback(async (signal?: AbortSignal) => {
    try {
      const data = await getQueries(signal);
      if (!signal?.aborted) {
        setQueries(data);
        setHistoryError(false);
      }
    } catch {
      if (!signal?.aborted) setHistoryError(true);
    }
  }, []);

  const openQuery = useCallback(
    async (queryId: string, updateAddress = true) => {
      const version = ++viewVersion.current;
      setOpening(true);
      setError(null);
      setPollError(false);
      try {
        const saved = await getQuery(queryId);
        if (version !== viewVersion.current) return;
        const last = saved.runs.at(-1);
        setQuery(saved);
        setSelectedRunId(last?.run_id ?? null);
        setProblem(saved.problem);
        setMode(last?.request.mode ?? "balanced");
        setClarifications(last?.request.clarifications ?? {});
        if (updateAddress || saved.query_id !== queryId) address(saved.query_id, !updateAddress);
      } catch (err) {
        if (version === viewVersion.current)
          setError(err instanceof Error ? err.message : "Could not open query");
      } finally {
        if (version === viewVersion.current) setOpening(false);
      }
    },
    [],
  );

  const clearQuery = useCallback(() => {
    ++viewVersion.current;
    setQuery(null);
    setSelectedRunId(null);
    setClarifications({});
    setError(null);
    setPollError(false);
    setOpening(false);
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    void refreshHistory(controller.signal);
    function restore() {
      const queryId = new URLSearchParams(window.location.search).get("query");
      if (queryId) void openQuery(queryId, false);
      else {
        clearQuery();
        setProblem("");
        setMode("balanced");
      }
    }
    restore();
    window.addEventListener("popstate", restore);
    async function health() {
      try {
        const response = await fetch("/api/health", {
          cache: "no-store",
          signal: controller.signal,
        });
        if (!controller.signal.aborted) setConnected(response.ok);
      } catch {
        if (!controller.signal.aborted) setConnected(false);
      }
    }
    void health();
    const healthTimer = setInterval(() => void health(), 30000);
    const historyTimer = setInterval(
      () => void refreshHistory(controller.signal),
      10000,
    );
    return () => {
      ++viewVersion.current;
      controller.abort();
      clearInterval(healthTimer);
      clearInterval(historyTimer);
      window.removeEventListener("popstate", restore);
    };
  }, [refreshHistory, openQuery, clearQuery]);

  const queryId = query?.query_id;
  useEffect(() => {
    if (!queryId || !loading || opening) return;
    const controller = new AbortController();
    const version = viewVersion.current;
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const saved = await getQuery(queryId!, controller.signal);
        if (controller.signal.aborted || version !== viewVersion.current)
          return;
        setQuery(saved);
        setPollError(false);
        if (!isActive(saved.runs.at(-1))) {
          void refreshHistory();
          return;
        }
      } catch {
        if (!controller.signal.aborted && version === viewVersion.current)
          setPollError(true);
      }
      if (!controller.signal.aborted && version === viewVersion.current)
        timer = setTimeout(poll, 2000);
    }
    void poll();
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [queryId, loading, opening, refreshHistory]);

  function newDesign() {
    clearQuery();
    setProblem("");
    setMode("balanced");
    address();
  }
  function changeProblem(value: string) {
    if (query && value !== query.problem) {
      clearQuery();
      address();
    }
    setProblem(value);
  }
  function useDemo(brief: string) {
    clearQuery();
    setProblem(brief);
    setMode("cost_effective");
    address();
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    setSubmitting(true);
    setError(null);
    const version = ++viewVersion.current;
    try {
      const saved = await startDesignQuery(
        { problem, mode, clarifications },
        query?.query_id,
      );
      if (version !== viewVersion.current) return;
      setQuery(saved);
      setSelectedRunId(saved.runs.at(-1)?.run_id ?? null);
      setConnected(true);
      setPollError(false);
      address(saved.query_id);
      void refreshHistory();
    } catch (err) {
      if (version === viewVersion.current)
        setError(err instanceof Error ? err.message : "Could not start design");
    } finally {
      setSubmitting(false);
    }
  }

  return {
    problem,
    changeProblem,
    mode,
    setMode,
    clarifications,
    setClarifications,
    query,
    queries,
    latest,
    selected,
    setSelectedRunId,
    connected,
    historyError,
    loading,
    submitting,
    opening,
    busy,
    error,
    pollError,
    refreshHistory,
    openQuery,
    newDesign,
    useDemo,
    submit,
  };
}
