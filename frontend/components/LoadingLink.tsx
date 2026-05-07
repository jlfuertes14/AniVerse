"use client";

import Link, { type LinkProps } from "next/link";
import type { AnchorHTMLAttributes, MouseEvent, ReactNode } from "react";
import { useLoadingToast } from "@/components/LoadingToastProvider";

type LoadingLinkProps = LinkProps &
  Omit<AnchorHTMLAttributes<HTMLAnchorElement>, "href"> & {
    children: ReactNode;
    loadingMessage?: string;
  };

export default function LoadingLink({
  children,
  loadingMessage,
  onClick,
  ...props
}: LoadingLinkProps) {
  const { showLoading } = useLoadingToast();

  const handleClick = (event: MouseEvent<HTMLAnchorElement>) => {
    onClick?.(event);
    if (!event.defaultPrevented) {
      showLoading(loadingMessage);
    }
  };

  return (
    <Link {...props} onClick={handleClick}>
      {children}
    </Link>
  );
}
