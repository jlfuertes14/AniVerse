"use client";

import { useState, useEffect } from "react";
import { getComments, addComment, deleteComment } from "@/lib/api";
import type { Comment } from "@/lib/api";
import type { User } from "@/lib/auth";

interface CommentSectionProps {
    animeId: number;
    episode?: number;
    currentUser: User | null;
    onLoginClick: () => void;
}

export default function CommentSection({ animeId, episode = 0, currentUser, onLoginClick }: CommentSectionProps) {
    const [comments, setComments] = useState<Comment[]>([]);
    const [newComment, setNewComment] = useState("");
    const [loading, setLoading] = useState(true);
    const [submitting, setSubmitting] = useState(false);

    useEffect(() => {
        loadComments();
    }, [animeId, episode]);

    const loadComments = async () => {
        try {
            const data = await getComments(animeId, episode);
            setComments(data);
        } catch (err) {
            console.error("Failed to load comments:", err);
        } finally {
            setLoading(false);
        }
    };

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!newComment.trim() || submitting) return;
        setSubmitting(true);

        try {
            const comment = await addComment(animeId, newComment.trim(), episode);
            // Add username from current user since backend may not return it immediately
            comment.user = comment.user || {
                id: currentUser!.id,
                username: currentUser!.username,
                avatar_url: currentUser!.avatar_url,
            };
            comment.created_at = comment.created_at || new Date().toISOString();
            setComments([comment, ...comments]);
            setNewComment("");
        } catch (err) {
            console.error("Failed to add comment:", err);
        } finally {
            setSubmitting(false);
        }
    };

    const handleDelete = async (commentId: string) => {
        try {
            await deleteComment(commentId);
            setComments(comments.filter((c) => c.id !== commentId));
        } catch (err) {
            console.error("Failed to delete comment:", err);
        }
    };

    const [now, setNow] = useState<number | null>(null);

    useEffect(() => {
        setNow(Date.now());
        const interval = setInterval(() => {
            setNow(Date.now());
        }, 60000); // Update every minute
        return () => clearInterval(interval);
    }, []);

    const parseCommentDate = (dateStr: string) => {
        if (!dateStr) return null;
        const hasTimezone = /[zZ]|[+-]\d{2}:\d{2}$/.test(dateStr);
        const normalized = hasTimezone ? dateStr : `${dateStr}Z`;
        const parsed = new Date(normalized);
        return Number.isNaN(parsed.getTime()) ? null : parsed;
    };

    const getYearInPH = (date: Date) => Number(
        new Intl.DateTimeFormat("en-PH", { timeZone: "Asia/Manila", year: "numeric" }).format(date)
    );

    const timeAgo = (dateStr: string) => {
        if (!dateStr || now === null) return "just now";
        const date = parseCommentDate(dateStr);
        if (!date) return "just now";
        const seconds = Math.floor((now - date.getTime()) / 1000);

        if (seconds < 60) return "just now";
        if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
        if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
        if (seconds < 604800) return `${Math.floor(seconds / 86400)}d ago`;
        
        // Return actual date if older than a week
        const nowDate = new Date(now);
        const currentYear = getYearInPH(nowDate);
        const parsedYear = getYearInPH(date);

        return date.toLocaleDateString("en-PH", {
            timeZone: "Asia/Manila",
            month: "short",
            day: "numeric",
            year: parsedYear !== currentYear ? "numeric" : undefined
        });
    };

    return (
        <div className="comment-section">
            <div className="comment-header">
                <h3 className="comment-title">
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z" />
                    </svg>
                    Discussion
                </h3>
                <span className="comment-count">{comments.length} {comments.length === 1 ? "comment" : "comments"}</span>
            </div>

            {/* Comment Input */}
            {currentUser ? (
                <form onSubmit={handleSubmit} className="comment-form">
                    <div className="comment-input-wrapper">
                        <div className="comment-avatar">
                            {currentUser.avatar_url ? (
                                <img src={currentUser.avatar_url} alt={currentUser.username} className="comment-avatar-img" />
                            ) : (
                                currentUser.username[0].toUpperCase()
                            )}
                        </div>
                        <textarea
                            className="comment-input"
                            placeholder="Share your thoughts about this anime..."
                            value={newComment}
                            onChange={(e) => setNewComment(e.target.value)}
                            maxLength={2000}
                            rows={2}
                        />
                    </div>
                    <div className="comment-form-actions">
                        <span className="comment-char-count">{newComment.length}/2000</span>
                        <button
                            type="submit"
                            className="comment-submit"
                            disabled={!newComment.trim() || submitting}
                        >
                            {submitting ? "Posting..." : "Post"}
                        </button>
                    </div>
                </form>
            ) : (
                <div className="comment-login-prompt" onClick={onLoginClick}>
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <path d="M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2" /><circle cx="12" cy="7" r="4" />
                    </svg>
                    Login to join the discussion
                </div>
            )}

            {/* Comments List */}
            {loading ? (
                <div className="comment-loading">
                    <div className="spinner" style={{ width: 24, height: 24 }} />
                </div>
            ) : comments.length === 0 ? (
                <div className="comment-empty">
                    <div className="comment-empty-icon">✦</div>
                    <p>No comments yet. Be the first to share your thoughts.</p>
                </div>
            ) : (
                <div className="comment-list">
                    {comments.map((comment) => (
                        <div key={comment.id} className="comment-item">
                            <div className="comment-avatar">
                                {comment.user.avatar_url ? (
                                    <img
                                        src={comment.user.avatar_url}
                                        alt={comment.user.username}
                                        className="comment-avatar-img"
                                    />
                                ) : (
                                    comment.user.username[0].toUpperCase()
                                )}
                            </div>
                            <div className="comment-body">
                                <div className="comment-meta">
                                    <span className="comment-author">{comment.user.username}</span>
                                    <span className="comment-time">{timeAgo(comment.created_at)}</span>
                                    {currentUser && currentUser.id === comment.user.id && (
                                        <button
                                            className="comment-delete"
                                            onClick={() => handleDelete(comment.id)}
                                            title="Delete comment"
                                        >
                                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                                <path d="M3 6h18M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2" />
                                            </svg>
                                        </button>
                                    )}
                                </div>
                                <p className="comment-content">{comment.content}</p>
                            </div>
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
}
