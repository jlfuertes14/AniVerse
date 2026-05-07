"use client";

import { useEffect, useMemo, useState } from "react";

import { getAiringSchedule } from "@/lib/api";
import type { AiringShow, WeeklySchedule } from "@/lib/types";

interface ScheduleDay {
    date: Date;
    label: string;
    monthLabel: string;
    dayNumber: string;
    shortWeekday: string;
    weekdayKey: keyof WeeklySchedule;
}

const DAY_KEYS: Array<keyof WeeklySchedule> = [
    "sunday",
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
];

function addDays(base: Date, offset: number) {
    const next = new Date(base);
    next.setDate(base.getDate() + offset);
    return next;
}

function buildVisibleDays(offsetDays: number): ScheduleDay[] {
    const today = new Date();
    const start = addDays(today, offsetDays - 2);

    return Array.from({ length: 6 }, (_, index) => {
        const date = addDays(start, index);
        return {
            date,
            label: date.toLocaleDateString(undefined, {
                weekday: "short",
                month: "short",
                day: "numeric",
                year: "numeric",
            }),
            monthLabel: date.toLocaleDateString(undefined, { month: "short" }).toUpperCase(),
            dayNumber: String(date.getDate()),
            shortWeekday: date.toLocaleDateString(undefined, { weekday: "short" }).toUpperCase(),
            weekdayKey: DAY_KEYS[date.getDay()],
        };
    });
}

function formatTime(dateValue: string) {
    const parsed = new Date(dateValue);
    if (Number.isNaN(parsed.getTime())) return "";
    return parsed.toLocaleTimeString(undefined, {
        hour: "numeric",
        minute: "2-digit",
    });
}

function formatFullDate(dateValue: string) {
    const parsed = new Date(dateValue);
    if (Number.isNaN(parsed.getTime())) return dateValue;
    return parsed.toLocaleString(undefined, {
        weekday: "short",
        month: "short",
        day: "numeric",
        year: "numeric",
        hour: "numeric",
        minute: "2-digit",
    });
}

function redateShow(show: AiringShow, targetDate: Date): AiringShow {
    const baseDate = new Date(show.airing_at);
    if (Number.isNaN(baseDate.getTime())) {
        return show;
    }

    const shifted = new Date(targetDate);
    shifted.setHours(
        baseDate.getHours(),
        baseDate.getMinutes(),
        baseDate.getSeconds(),
        baseDate.getMilliseconds()
    );

    const now = new Date();
    let nextStatus = show.status;
    if (show.status !== "delayed" && show.status !== "delayed-air") {
        const diff = shifted.getTime() - now.getTime();
        if (diff > 0) {
            nextStatus = "unaired";
        } else if (diff >= -30 * 60 * 1000) {
            nextStatus = "airing";
        } else {
            nextStatus = "aired";
        }
    }

    return {
        ...show,
        airing_at: shifted.toISOString(),
        status: nextStatus,
    };
}

export default function EstimatedSchedule() {
    const [offsetDays, setOffsetDays] = useState(0);
    const [selectedIndex, setSelectedIndex] = useState(2);
    const [nowLabel, setNowLabel] = useState<string>("");
    const [visibleDays, setVisibleDays] = useState<ScheduleDay[]>([]);
    const [mounted, setMounted] = useState(false);
    const [schedule, setSchedule] = useState<WeeklySchedule | null>(null);
    const [loadingSchedule, setLoadingSchedule] = useState(true);
    const [scheduleError, setScheduleError] = useState<string>("");
    const [visibleCount, setVisibleCount] = useState(5);

    useEffect(() => {
        setMounted(true);
        const updateNow = () => {
            setNowLabel(
                new Date().toLocaleString(undefined, {
                    month: "numeric",
                    day: "numeric",
                    year: "numeric",
                    hour: "numeric",
                    minute: "2-digit",
                    second: "2-digit",
                })
            );
        };
        updateNow();
        const timer = setInterval(updateNow, 1000);
        return () => clearInterval(timer);
    }, []);

    useEffect(() => {
        if (mounted) {
            setVisibleDays(buildVisibleDays(offsetDays));
            setVisibleCount(5); // Reset count when day changes
        }
    }, [offsetDays, mounted]);

    useEffect(() => {
        let cancelled = false;

        async function loadSchedule() {
            setLoadingSchedule(true);
            setScheduleError("");
            try {
                const data = await getAiringSchedule();
                if (!cancelled) {
                    setSchedule(data);
                }
            } catch (error) {
                if (!cancelled) {
                    setScheduleError(error instanceof Error ? error.message : "Failed to load schedule");
                }
            } finally {
                if (!cancelled) {
                    setLoadingSchedule(false);
                }
            }
        }

        loadSchedule();
        return () => {
            cancelled = true;
        };
    }, []);

    const selectedDay = visibleDays[selectedIndex] ?? visibleDays[2];

    const showsForSelectedDay = useMemo(() => {
        if (!schedule || !selectedDay) return [];
        const weekdayShows = schedule[selectedDay.weekdayKey] || [];
        return weekdayShows
            .map((show) => redateShow(show, selectedDay.date))
            .sort((a, b) => new Date(a.airing_at).getTime() - new Date(b.airing_at).getTime());
    }, [schedule, selectedDay]);

    if (!mounted || visibleDays.length === 0) {
        return (
            <section className="schedule-section container-wide">
                <div className="schedule-shell">
                    <div className="schedule-header">
                        <h2 className="schedule-title">Estimated Schedule</h2>
                        <div className="skeleton" style={{ width: "200px", height: "20px" }} />
                    </div>
                    <div className="schedule-rail">
                        <div className="schedule-days">
                            {Array.from({ length: 6 }).map((_, i) => (
                                <div key={i} className="schedule-day skeleton" style={{ width: "60px", height: "80px" }} />
                            ))}
                        </div>
                    </div>
                </div>
            </section>
        );
    }

    return (
        <section className="schedule-section container-wide">
            <div className="schedule-shell">
                <div className="schedule-header">
                    <h2 className="schedule-title">Estimated Schedule</h2>
                    <p className="schedule-now">Now: {nowLabel}</p>
                </div>

                <div className="schedule-rail">
                    <button
                        type="button"
                        className="schedule-arrow"
                        aria-label="Show previous days"
                        onClick={() => setOffsetDays((current) => current - 1)}
                    >
                        &#8249;
                    </button>

                    <div className="schedule-days">
                        {visibleDays.map((day, index) => {
                            const isActive = index === selectedIndex;
                            return (
                                <button
                                    type="button"
                                    key={`${day.date.toISOString()}-${index}`}
                                    className={`schedule-day ${isActive ? "active" : ""}`}
                                    onClick={() => setSelectedIndex(index)}
                                >
                                    <span className="schedule-month">{day.monthLabel}</span>
                                    <span className="schedule-number">{day.dayNumber}</span>
                                    <span className="schedule-weekday">{day.shortWeekday}</span>
                                </button>
                            );
                        })}
                    </div>

                    <button
                        type="button"
                        className="schedule-arrow"
                        aria-label="Show next days"
                        onClick={() => setOffsetDays((current) => current + 1)}
                    >
                        &#8250;
                    </button>
                </div>

                {loadingSchedule ? (
                    <p className="schedule-status">Loading schedule for {selectedDay?.label}...</p>
                ) : scheduleError ? (
                    <p className="schedule-status">Schedule unavailable right now: {scheduleError}</p>
                ) : showsForSelectedDay.length === 0 ? (
                    <p className="schedule-status">No tracked drops for {selectedDay?.label}.</p>
                ) : (
                    <>
                        <p className="schedule-status">
                            {showsForSelectedDay.length} release{showsForSelectedDay.length === 1 ? "" : "s"} on {selectedDay?.label}
                        </p>

                        <div className="schedule-list">
                            {showsForSelectedDay.slice(0, visibleCount).map((show) => (
                                <a
                                    key={`${show.route}-${show.air_type || "unknown"}-${show.episode}`}
                                    className="schedule-row"
                                    href={show.anime_url || "#"}
                                    target={show.anime_url ? "_blank" : undefined}
                                    rel={show.anime_url ? "noreferrer" : undefined}
                                >
                                    <div className="schedule-row-time">
                                        {formatTime(show.airing_at)}
                                    </div>
                                    <div className="schedule-row-main">
                                        <h3 className="schedule-row-title">{show.title}</h3>
                                        <p className="schedule-row-subtitle">
                                            <span>{show.air_type || "Scheduled"}</span>
                                            <span>{formatFullDate(show.airing_at)}</span>
                                        </p>
                                    </div>
                                    <div className="schedule-row-actions">
                                        <span className={`schedule-chip ${show.status || "unknown"}`}>
                                            {(show.status || "scheduled").toUpperCase()}
                                        </span>
                                        <span className="schedule-row-episode">{show.episode}</span>
                                    </div>
                                </a>
                            ))}
                        </div>

                        {visibleCount < showsForSelectedDay.length && (
                            <button 
                                className="watch-community-load-more"
                                onClick={() => setVisibleCount(prev => prev + 5)}
                                style={{ 
                                    marginTop: '1.5rem',
                                    width: '100%',
                                    display: 'flex',
                                    justifyContent: 'center',
                                    gap: '0.75rem',
                                    padding: '0.85rem',
                                    background: 'rgba(255, 255, 255, 0.03)',
                                    border: '1px solid rgba(255, 255, 255, 0.06)',
                                    borderRadius: 'var(--radius-md)',
                                    color: 'var(--text-primary)',
                                    fontSize: '0.85rem',
                                    fontWeight: '600',
                                    cursor: 'pointer',
                                    transition: 'all 0.2s ease'
                                }}
                            >
                                <span>Load More</span>
                                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                                    <path d="M7 13l5 5 5-5M7 6l5 5 5-5" />
                                </svg>
                            </button>
                        )}
                    </>
                )}
            </div>
        </section>
    );
}
