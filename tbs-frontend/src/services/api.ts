const API_BASE_URL = 'http://localhost:8000/api';

// --- Types & Interfaces ---
export interface AuditConfig {
    ticker: string;
    profile: string;
    mode: string;
    is_etf: boolean;
    total_capital: number;

    // [v8.3] The Fallback Track: Analyst Override Mandate fields
    wacc?: number | null;
    moat?: string | null;
    tnx?: number | null;
    roic_override?: number | null;
    de_override?: number | null;
    fcf_yield_override?: number | null;
    rev_override?: number | null;
    eps_override?: number | null;
    sector_etf_override?: string | null;
    pivot_confirmed?: boolean;
}

export interface SizingConfig {
    profile: string;
    mode: string;
    regime: string;
    event_aware: boolean;
    vix_storm: boolean;
    audit_status: string;
    engine_metrics: any;
    total_capital: number;
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

        // [FIX] Safely parse FastAPI 422 Pydantic Validation Arrays
        let errorMessage = errData.detail || `API Request Failed: ${response.statusText}`;
        if (typeof errorMessage === 'object') {
            errorMessage = JSON.stringify(errorMessage, null, 2);
        }

        throw new Error(errorMessage);
    }
    return response.json();
}

// ==============================================================================
// PIPELINE EXECUTION FUNCTIONS
// ==============================================================================

export async function fetchAutoID(ticker: string, mode: string) {
    return fetchFromAPI('/preflight/autoid', 'POST', { ticker, mode });
}

export async function fetchSentinel(config: Partial<AuditConfig>) {
    return fetchFromAPI('/layer0/sentinel', 'POST', config);
}

// [v8.3] Layer 1.5a: Sympathy Audit
export async function fetchSympathyAudit(config: AuditConfig) {
    return fetchFromAPI('/layer15/sympathy', 'POST', config);
}

// [v8.3] Layer 1.5b: Asset Gates
export async function fetchAssetGates(config: AuditConfig) {
    return fetchFromAPI('/layer15/asset-gates', 'POST', config);
}

export const fetchFundamentals = async (data: any) => {
    // Pass the ENTIRE data object so all AI overrides (moat, roic, wacc) survive the trip!
    return await fetchFromAPI('/layer1/fundamentals', 'POST', data);
};

export async function fetchTechnical(config: AuditConfig) {
    return fetchFromAPI('/layer2/technical', 'POST', {
        ticker: config.ticker,
        profile: config.profile,
        is_etf: config.is_etf,
        mode: config.mode
    });
}

export async function fetchSizing(config: SizingConfig) {
    return fetchFromAPI('/governor/sizing', 'POST', config);
}

// ==============================================================================
// AI ANALYST RETRIEVAL FUNCTIONS (Human-in-the-Loop)
// ==============================================================================

export async function fetchAnalystRetrieval(ticker: string, metric: string = "WACC") {
    return fetchFromAPI(`/analyst/retrieve/${ticker}?metric=${metric}`, 'GET');
}

export async function fetchAnalystRadar(ticker: string) {
    return fetchFromAPI(`/analyst/radar/${ticker}`, 'GET');
}

export async function fetchVisionAudit(config: AuditConfig) {
    return fetchFromAPI('/analyst/vision', 'POST', config);
}