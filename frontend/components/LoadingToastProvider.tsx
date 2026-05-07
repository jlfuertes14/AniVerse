"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import { usePathname, useSearchParams } from "next/navigation";
import Toast from "@/components/Toast";

type LoadingToastContextValue = {
  showLoading: (message?: string) => void;
  hideLoading: () => void;
};

const LoadingToastContext = createContext<LoadingToastContextValue | null>(null);

export function LoadingToastProvider({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [message, setMessage] = useState<string | null>(null);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastRouteRef = useRef<string>("");

  const clearHideTimer = useCallback(() => {
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current);
      timeoutRef.current = null;
    }
  }, []);

  const hideLoading = useCallback(() => {
    clearHideTimer();
    setMessage(null);
  }, [clearHideTimer]);

  const showLoading = useCallback((nextMessage = "Loading page...") => {
    clearHideTimer();
    setMessage(nextMessage);

    timeoutRef.current = setTimeout(() => {
      setMessage(null);
    }, 20000);
  }, [clearHideTimer]);

  useEffect(() => {
    const routeKey = `${pathname}?${searchParams.toString()}`;
    if (!lastRouteRef.current) {
      lastRouteRef.current = routeKey;
      return;
    }

    if (lastRouteRef.current !== routeKey) {
      lastRouteRef.current = routeKey;
      hideLoading();
    }
  }, [hideLoading, pathname, searchParams]);

  useEffect(() => () => clearHideTimer(), [clearHideTimer]);

  const value = useMemo(() => ({ showLoading, hideLoading }), [showLoading, hideLoading]);

  return (
    <LoadingToastContext.Provider value={value}>
      {children}
      {message && (
        <Toast
          message={message}
          type="loading"
          onClose={hideLoading}
        />
      )}
    </LoadingToastContext.Provider>
  );
}

export function useLoadingToast() {
  const context = useContext(LoadingToastContext);
  if (!context) {
    throw new Error("useLoadingToast must be used within LoadingToastProvider");
  }
  return context;
}
