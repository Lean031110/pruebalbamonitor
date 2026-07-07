import axios, { AxiosError, AxiosRequestConfig } from "axios";

// ---------------------------------------------------------------------------
// API client con JWT auth + refresh automático
// ---------------------------------------------------------------------------

export const api = axios.create({
  baseURL: "/api",
  timeout: 10_000,
  headers: { "Content-Type": "application/json" },
});

// Tokens en localStorage (con clave única)
const ACCESS_TOKEN_KEY = "lbamonitor_access_token";
const REFRESH_TOKEN_KEY = "lbamonitor_refresh_token";

export function getAccessToken(): string | null {
  return localStorage.getItem(ACCESS_TOKEN_KEY);
}
export function getRefreshToken(): string | null {
  return localStorage.getItem(REFRESH_TOKEN_KEY);
}
export function setTokens(access: string, refresh: string): void {
  localStorage.setItem(ACCESS_TOKEN_KEY, access);
  localStorage.setItem(REFRESH_TOKEN_KEY, refresh);
}
export function clearTokens(): void {
  localStorage.removeItem(ACCESS_TOKEN_KEY);
  localStorage.removeItem(REFRESH_TOKEN_KEY);
}

// Interceptor de request: añade Authorization header
api.interceptors.request.use((config) => {
  const token = getAccessToken();
  if (token) {
    config.headers = config.headers || {};
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Interceptor de response: maneja 401 con refresh automático
let isRefreshing = false;
let refreshSubscribers: Array<(token: string | null) => void> = [];

function subscribeTokenRefresh(cb: (token: string | null) => void) {
  refreshSubscribers.push(cb);
}

function onRefreshed(token: string | null) {
  refreshSubscribers.forEach((cb) => cb(token));
  refreshSubscribers = [];
}

api.interceptors.response.use(
  (r) => r,
  async (err: AxiosError) => {
    const originalRequest = err.config as AxiosRequestConfig & { _retry?: boolean };
    console.error("[API]", originalRequest.method?.toUpperCase(), originalRequest.url, err.message);

    // Si es 401 y no es el endpoint de login/refresh, intentar refresh
    if (
      err.response?.status === 401 &&
      !originalRequest._retry &&
      !(originalRequest.url || "").includes("/auth/login") &&
      !(originalRequest.url || "").includes("/auth/refresh")
    ) {
      if (isRefreshing) {
        // Ya hay un refresh en curso, esperar
        return new Promise((resolve, reject) => {
          subscribeTokenRefresh((token) => {
            if (!token) {
              reject(err);
              return;
            }
            originalRequest.headers = originalRequest.headers || {};
            (originalRequest.headers as Record<string, string>).Authorization = `Bearer ${token}`;
            resolve(api(originalRequest));
          });
        });
      }

      originalRequest._retry = true;
      isRefreshing = true;

      try {
        const refreshToken = getRefreshToken();
        if (!refreshToken) {
          clearTokens();
          window.location.href = "/login";
          return Promise.reject(err);
        }

        const { data } = await axios.post("/api/auth/refresh", { refresh_token: refreshToken });
        const newAccess = data.access_token;
        const newRefresh = data.refresh_token;
        setTokens(newAccess, newRefresh);

        onRefreshed(newAccess);
        isRefreshing = false;

        originalRequest.headers = originalRequest.headers || {};
        (originalRequest.headers as Record<string, string>).Authorization = `Bearer ${newAccess}`;
        return api(originalRequest);
      } catch (refreshErr) {
        onRefreshed(null);
        isRefreshing = false;
        clearTokens();
        window.location.href = "/login";
        return Promise.reject(refreshErr);
      }
    }

    return Promise.reject(err);
  }
);

// ---------------------------------------------------------------------------
// Auth
// ---------------------------------------------------------------------------

export interface LoginResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
  username: string;
  role: string;
  user_id?: number;
}

export async function login(username: string, password: string): Promise<LoginResponse> {
  const { data } = await api.post<LoginResponse>("/auth/login", { username, password });
  setTokens(data.access_token, data.refresh_token);
  return data;
}

export async function logout(): Promise<void> {
  const token = getAccessToken();
  if (token) {
    try {
      await api.post("/auth/logout", { token });
    } catch {
      // ignore
    }
  }
  clearTokens();
}

export function isAuthenticated(): boolean {
  return !!getAccessToken();
}

// ---------------------------------------------------------------------------
// Tipos
// ---------------------------------------------------------------------------

export interface HealthResponse {
  status: string;
  name: string;
  version: string;
  timestamp: string;
  platform: { system: string; machine: string; processor: string | null };
  python: string;
  config: {
    database_engine: string;
    host: string;
    port: number;
    docs_enabled: boolean;
  };
  service_session: {
    id: number;
    start: string;
    end: string | null;
    alive: string | null;
    is_running: boolean;
  } | null;
  counts: Record<string, number>;
}

export interface PaginationInfo {
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
  has_next: boolean;
  has_prev: boolean;
}

export interface PaginatedResponse<T> {
  items: T[];
  pagination: PaginationInfo;
}

export interface User {
  id: number;
  username: string;
  full_name: string | null;
  email: string | null;
  role: string;
  active: boolean;
  created: string;
  last_login: string | null;
}

export interface InsertedDrive {
  id: number;
  insertion_date_time: string;
  name: string | null;
  root_directory: string | null;
  volume_label: string | null;
  serial_number: string | null;
  model: string | null;
  is_mobile: boolean;
  space_bytes: number | null;
  available_space_bytes: number | null;
  payment: number | null;
  comment: string | null;
  comment_fixed: string | null;
  previous_insertions_counter: number;
  previous_payments_sum: number;
  removed_drive_id: number | null;
  user_id: number | null;
}

export interface Copy {
  id: number;
  copy_date_time: string;
  full_path: string;
  extension: string | null;
  file_name: string | null;
  size_bytes: number | null;
  category: string | null;
  inserted_drive_id: number | null;
}

export interface KPIs {
  range_start: string;
  range_end: string;
  transactions: number;
  revenue: number;
  discounts: number;
  usb_count: number;
  sessions: number;
  gb_copied: number;
  files_copied: number;
  avg_per_session: number;
  avg_per_gb: number;
}

export interface SeriesPoint {
  label: string;
  value: number;
  count: number;
}

export interface BusinessInsights {
  busiest_day_of_week: string | null;
  peak_hour: number | null;
  top_usb: { device_id: number; alias: string | null; visit_count: number } | null;
  top_client: { device_id: number; visit_count: number; total_spent: number; tier: string } | null;
  new_clients_30d: number;
  inactive_clients_60d: number;
  avg_per_session: number;
  avg_per_gb: number;
}

export interface Statistics {
  today_kpis: KPIs;
  month_kpis: KPIs;
  year_kpis: KPIs;
  revenue_by_day: SeriesPoint[];
  revenue_by_month: SeriesPoint[];
  top_clients: { device_id: number; alias: string | null; visit_count: number; total_spent: number; tier: string }[];
  top_usb: { device_id: number; alias: string | null; serial: string | null; visit_count: number }[];
  insights: BusinessInsights;
}

export interface CatalogEntry {
  id: number;
  title: string;
  category: string;
  year: number | null;
  genre: string | null;
  director: string | null;
  artist: string | null;
  size_gb: number | null;
  rating: number | null;
  times_copied: number;
  active: boolean;
}

export interface BusinessInfo {
  name: string;
  marketing_text: string;
  address: string;
}

export interface ServiceSession {
  id: number;
  start_date_time: string;
  end_date_time: string | null;
  alive_date_time: string | null;
  session_time: number | null;
}

export interface BackupRecord {
  id: number;
  file_path: string;
  size_bytes: number | null;
  auto: boolean;
  notes: string | null;
  created_at: string;
}

export interface LicenseStatus {
  valid: boolean;
  tier: string;
  expires: string | null;
  issued_at: string | null;
  reason: string;
  machine_id: string;
}

// ---------------------------------------------------------------------------
// Endpoints
// ---------------------------------------------------------------------------

export async function getHealth(): Promise<HealthResponse> {
  const { data } = await api.get<HealthResponse>("/health");
  return data;
}

// Users
export async function listUsers(page = 1, pageSize = 50): Promise<PaginatedResponse<User>> {
  const { data } = await api.get<PaginatedResponse<User>>("/users", { params: { page, page_size: pageSize } });
  return data;
}
export async function createUser(payload: { username: string; password: string; role: string; full_name?: string; email?: string }): Promise<User> {
  const { data } = await api.post<User>("/users", payload);
  return data;
}
export async function updateUser(id: number, payload: Partial<User> & { password?: string }): Promise<User> {
  const { data } = await api.patch<User>(`/users/${id}`, payload);
  return data;
}
export async function deleteUser(id: number): Promise<void> {
  await api.delete(`/users/${id}`);
}

// Inserted drives
export async function listInsertedDrives(params: Record<string, unknown> = {}): Promise<PaginatedResponse<InsertedDrive>> {
  const { data } = await api.get<PaginatedResponse<InsertedDrive>>("/inserted-drives", { params });
  return data;
}
export async function getActiveDrives(): Promise<InsertedDrive[]> {
  const { data } = await api.get<InsertedDrive[]>("/inserted-drives/active");
  return data;
}
export async function updateDrivePayment(id: number, payment: number, userId?: number): Promise<InsertedDrive> {
  const { data } = await api.patch<InsertedDrive>(`/inserted-drives/${id}/payment`, { payment, user_id: userId });
  return data;
}
export async function getDriveCopies(id: number): Promise<Copy[]> {
  const { data } = await api.get<Copy[]>(`/inserted-drives/${id}/copies`);
  return data;
}

// Statistics
export async function getStatistics(): Promise<Statistics> {
  const { data } = await api.get<Statistics>("/statistics");
  return data;
}

// Catalog
export async function listCatalog(params: Record<string, unknown> = {}): Promise<PaginatedResponse<CatalogEntry>> {
  const { data } = await api.get<PaginatedResponse<CatalogEntry>>("/catalog", { params });
  return data;
}
export async function createCatalogEntry(payload: Partial<CatalogEntry>): Promise<CatalogEntry> {
  const { data } = await api.post<CatalogEntry>("/catalog", payload);
  return data;
}
export async function updateCatalogEntry(id: number, payload: Partial<CatalogEntry>): Promise<CatalogEntry> {
  const { data } = await api.patch<CatalogEntry>(`/catalog/${id}`, payload);
  return data;
}
export async function deleteCatalogEntry(id: number): Promise<void> {
  await api.delete(`/catalog/${id}`);
}

// Settings
export async function getBusinessInfo(): Promise<BusinessInfo> {
  const { data } = await api.get<BusinessInfo>("/settings/business-info");
  return data;
}
export async function setBusinessInfo(payload: BusinessInfo): Promise<BusinessInfo> {
  const { data } = await api.put<BusinessInfo>("/settings/business-info", payload);
  return data;
}

// Sessions
export async function listSessions(page = 1, pageSize = 50): Promise<PaginatedResponse<ServiceSession>> {
  const { data } = await api.get<PaginatedResponse<ServiceSession>>("/sessions", { params: { page, page_size: pageSize } });
  return data;
}

// Backups
export async function listBackups(): Promise<BackupRecord[]> {
  const { data } = await api.get<BackupRecord[]>("/backups");
  return data;
}
export async function triggerBackup(notes?: string): Promise<{ success: boolean; message: string }> {
  const { data } = await api.post(`/backups/trigger`, null, { params: { notes } });
  return data;
}

// License
export async function getLicenseStatus(): Promise<LicenseStatus> {
  const { data } = await api.get<LicenseStatus>("/license");
  return data;
}
export async function getMachineId(): Promise<{ machine_id: string; components: Record<string, string> }> {
  const { data } = await api.get("/license/machine-id");
  return data;
}
export async function activateLicense(licenseKey: string): Promise<{ success: boolean; message: string }> {
  const { data } = await api.post("/license/activate", { license_key: licenseKey });
  return data;
}

// Admin
export async function getAdminStatus(): Promise<Record<string, unknown>> {
  const { data } = await api.get("/admin/status");
  return data;
}
