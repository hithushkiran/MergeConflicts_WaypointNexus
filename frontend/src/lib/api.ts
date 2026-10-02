const configuredApiUrl = import.meta.env.VITE_API_URL

/** Base URL for future backend API clients. */
export const API_BASE_URL = configuredApiUrl?.replace(/\/$/, '') ?? 'http://localhost:8000'
