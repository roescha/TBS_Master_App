const API_BASE_URL = 'http://localhost:8000/api';

// --- Types & Interfaces ---
// [api.ts] - Update this interface to include the capital field
export interface AuditConfig {
    ticker: string;
    profile: string;
    mode: string;
    is_etf: boolean;
    wacc: number | null;
    total_capital: number; // [FIX: Add this line to resolve the red error in page.tsx]
}


export interface SizingConfig {
    profile: string;
    mode: string;
    regime: string;
    event_aware: boolean;
    vix_storm: boolean;
    audit_status: string;
    engine_metrics: any;
    total_capital: number; // [MANDATE: ADDED FOR DYNAMIC RISK CALC]
}

// --- Helper for API Calls ---
async function fetchFromAPI(endpoint: string, method: string = 'GET', body?: any) {
    const options: RequestInit = {
        method,
        headers: { 'Content-Type': 'application/json' },
    };
    if (body) options.body = JSON.stringify(body);

    const response = await fetch(`${API_BASE_URL}${endpoint}`, options);
    if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        throw new Error(errData.detail || `API Request Failed: ${response.statusText}`);
    }
    return response.json();
}

// ==========================================
// TBS ENDPOINT FUNCTIONS
// ==========================================

export async function fetchAutoID(ticker: string, mode: string) {
    // Step 0: Deterministic Asset Classification [cite: 457]
    return fetchFromAPI('/preflight/autoid', 'POST', { ticker, mode });
}

export async function fetchSentinel() {
    // Step 1: Systemic Macro Weather calculation [cite: 444]
    return fetchFromAPI('/layer0/sentinel', 'GET');
}

// ... update the fetchFundamentals call to ensure it sends the whole object
export async function fetchFundamentals(config: AuditConfig) {
    return fetchFromAPI('/layer1/fundamentals', 'POST', config);
}


export async function fetchTechnical(config: AuditConfig) {
    // Step 6: Structural Verification & Visual Render [cite: 455]
    return fetchFromAPI('/layer2/technical', 'POST', {
        ticker: config.ticker,
        profile: config.profile,
        is_etf: config.is_etf,
        mode: config.mode
    });
}

export async function fetchSizing(config: SizingConfig) {
    // Step 7: Posture Multipliers & Expectancy Math [cite: 460, 461]
    return fetchFromAPI('/governor/sizing', 'POST', config);
}

export async function fetchAnalystWACC(ticker: string) {
    return fetchFromAPI(`/analyst/wacc/${ticker}`, 'GET');
}

export async function fetchVisionAudit(config: AuditConfig) {
    // Step 6.5: AI-Assisted Visual Audit (v8.2 Protocol)
    return fetchFromAPI('/analyst/vision', 'POST', config);
}

export async function fetchAnalystRadar(ticker: string) {
    // Step 4: AI Risk Radar (Integrity Shocks & Event Gates)
    return fetchFromAPI(`/analyst/radar/${ticker}`, 'GET');
}