/* ============================================
   Anime Discovery Engine — Auth Library
   JWT token management and auth state.
   ============================================ */

export interface User {
    id: string;
    username: string;
    email: string;
    avatar_url: string | null;
    created_at?: string;
    stats?: {
        watchlist: number;
        favorites: number;
        comments: number;
    };
}

const TOKEN_KEY = "ade_token";
const USER_KEY = "ade_user";

export function getToken(): string | null {
    if (typeof window === "undefined") return null;
    return localStorage.getItem(TOKEN_KEY);
}

export function getStoredUser(): User | null {
    if (typeof window === "undefined") return null;
    const raw = localStorage.getItem(USER_KEY);
    if (!raw) return null;
    try {
        return JSON.parse(raw);
    } catch {
        return null;
    }
}

export function setAuth(token: string, user: User): void {
    localStorage.setItem(TOKEN_KEY, token);
    localStorage.setItem(USER_KEY, JSON.stringify(user));
}

export function clearAuth(): void {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
}

export function isLoggedIn(): boolean {
    return !!getToken();
}
