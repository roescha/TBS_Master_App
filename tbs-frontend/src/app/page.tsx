"use client";

import React, {useState} from 'react';
import PreFlight from '../components/PreFlight';
import Execution from '../components/Execution';
import {
    fetchAutoID,
    fetchSentinel,
    fetchSympathyAudit,
    fetchAssetGates,
    fetchFundamentals,
    fetchTechnical,
    fetchSizing,
    fetchAnalystRetrieval, // <-- FIXED
    AuditConfig,
    SizingConfig
} from '../services/api';

export default function MasterDashboard() {
    const [currentStep, setCurrentStep] = useState<number>(0);
    const [config, setConfig] = useState<AuditConfig | null>(null);
    const [isETF, setIsETF] = useState<boolean>(false);
    const [eventAware, setEventAware] = useState<boolean>(false);

    // --- Pipeline State ---
    const [sentinelResult, setSentinelResult] = useState<any>(null);
    const [sympathyResult, setSympathyResult] = useState<any>(null);
    const [assetGatesResult, setAssetGatesResult] = useState<any>(null);
    const [fundamentalResult, setFundamentalResult] = useState<any>(null);
    const [technicalResult, setTechnicalResult] = useState<any>(null);
    const [sizingResult, setSizingResult] = useState<any>(null);

    const [loading, setLoading] = useState<boolean>(false);
    const [errorMsg, setErrorMsg] = useState<string | null>(null);

    const handleStartAudit = async (preFlightData: any) => {
        setLoading(true);
        setErrorMsg(null);
        setConfig(preFlightData);

        // Reset previous run data
        setSentinelResult(null);
        setSympathyResult(null);
        setAssetGatesResult(null);
        setFundamentalResult(null);
        setTechnicalResult(null);
        setSizingResult(null);
        setCurrentStep(1);

        try {
            // 1. Pre-Flight: Auto ID
            const idRes = await fetchAutoID(preFlightData.ticker, preFlightData.mode);
            setIsETF(idRes.is_etf);
            preFlightData.is_etf = idRes.is_etf;

            // 2. Layer 0: Sentinel
            const sentinelRes = await fetchSentinel(preFlightData);
            setSentinelResult(sentinelRes);
            if (sentinelRes.verdict === 'HALT') {
                setErrorMsg(`PIPELINE ABORTED AT LAYER 0 (SENTINEL): ${sentinelRes.reason}`);
                setLoading(false);
                return;
            }

            // ====================================================================
            // [MACRO-TO-MICRO BRIDGE] Extract TNX for the WEALTH FCF Yield Gate
            // ====================================================================
            if (sentinelRes.details && sentinelRes.details.tnx_close_daily) {
                // The CBOE TNX index is 10x the true yield. Divide by 10!
                preFlightData.tnx = sentinelRes.details.tnx_close_daily / 10;
                console.log(`[TBS] Macro Data Extracted: TNX = ${preFlightData.tnx}%`);
            }
            // ====================================================================

            setCurrentStep(2);

            // 3. Layer 1.5a: Sympathy Audit (v8.3)
            const sympRes = await fetchSympathyAudit(preFlightData);
            setSympathyResult(sympRes);
            if (sympRes.status === 'HALT') {
                setErrorMsg(`PIPELINE ABORTED AT LAYER 1.5a (SYMPATHY): ${sympRes.diagnostic}`);
                setLoading(false);
                return;
            }
            setCurrentStep(3);

            // 4. Layer 1.5b: Asset Gates (v8.3)
            const gatesRes = await fetchAssetGates(preFlightData);
            setAssetGatesResult(gatesRes);
            if (gatesRes.status === 'BLOCKED') {
                setErrorMsg(`PIPELINE ABORTED AT LAYER 1.5b (ASSET GATES): ${gatesRes.diagnostic}`);
                setLoading(false);
                return;
            }
            if (gatesRes.status === 'LIMIT_ONLY') {
                setEventAware(true);
            }
            setCurrentStep(4);

            // 5. Layer 1: Fundamental DNA, Pulse, and Health
            let fundRes = await fetchFundamentals(preFlightData);

            // [NEW] Safety counter to prevent infinite loops
            let retryCount = 0;
            const maxRetries = 5;

            // ====================================================================
            // [v8.3 FALLBACK TRACK] AI Analyst Auto-Retrieval Interception
            // ====================================================================
            // [FIX] Upgraded to a WHILE loop to catch sequential missing data!
            while (
                fundRes &&
                fundRes.diagnostic &&
                fundRes.diagnostic.includes('Missing') &&
                retryCount < maxRetries
                ) {
                retryCount++;
                const diagLower = fundRes.diagnostic.toLowerCase();
                let metricToFetch = null;
                let payloadKey = null;

                if (diagLower.includes('moat')) {
                    metricToFetch = 'Moat Rating';
                    payloadKey = 'moat';
                } else if (diagLower.includes('wacc')) {
                    metricToFetch = 'WACC';
                    payloadKey = 'wacc';
                } else if (diagLower.includes('roic')) {
                    metricToFetch = 'ROIC';
                    payloadKey = 'roic_override';
                } else if (diagLower.includes('fcf')) {
                    metricToFetch = 'FCF Yield';
                    payloadKey = 'fcf_yield_override';
                } else if (diagLower.includes('debt') || diagLower.includes('d/e')) {
                    metricToFetch = 'Debt-to-Equity';
                    payloadKey = 'de_override';
                }

                if (metricToFetch && payloadKey) {
                    setErrorMsg(`⚠️ AUTOMATIC OVERRIDE: AI Analyst hunting for missing ${metricToFetch}... (Attempt ${retryCount}/5)`);

                    try {
                        const aiRes = await fetchAnalystRetrieval(preFlightData.ticker, metricToFetch);

                        if (aiRes && aiRes.data && aiRes.data.value !== null && aiRes.data.value !== "NOT FOUND") {
                            let aiValue = aiRes.data.value;

                            if (payloadKey === 'moat') {
                                const rawVal = String(aiValue).toUpperCase();

                                // Check if the valid keywords exist ANYWHERE in the response
                                if (rawVal.includes('WIDE')) {
                                    aiValue = 'WIDE';
                                } else if (rawVal.includes('NARROW')) {
                                    aiValue = 'NARROW';
                                } else if (rawVal.includes('NONE') || rawVal.includes('NO MOAT')) {
                                    aiValue = 'NONE';
                                } else {
                                    // [STRICT HALT] If it's a number like "9" or random text, don't guess.
                                    throw new Error(`AI returned an invalid Moat category: "${rawVal}". Manual verification required.`);
                                }
                            }

                            // SMART FRONTEND GATE FOR WEALTH MOAT
                            if (payloadKey === 'moat' && aiValue === 'NONE' && preFlightData.profile === 'WEALTH') {
                                setErrorMsg(`❌ AI verified Moat is NONE. The WEALTH profile strictly mandates a WIDE or NARROW moat. Trade Rejected.`);
                                setLoading(false);
                                return;
                            }

                            // Inject data, clone payload, display success, and pause
                            preFlightData[payloadKey] = aiValue;
                            setErrorMsg(`✅ AI retrieved and sanitized ${metricToFetch}: ${aiValue}. Resuming Audit...`);
                            await new Promise(resolve => setTimeout(resolve, 2000));

                            // Re-run the engine! If it fails on something else, the loop repeats!
                            fundRes = await fetchFundamentals({...preFlightData});

                        } else {
                            setErrorMsg(`❌ AI Analyst could not verify ${metricToFetch} online. Operator manual override required.`);
                            setLoading(false);
                            return;
                        }
                    } catch (aiError) {
                        console.error("AI Retrieval Failed:", aiError);
                        setErrorMsg(`❌ AI Analyst network failure while fetching ${metricToFetch}.`);
                        setLoading(false);
                        return;
                    }
                } else {
                    // Failsafe: If it says 'Missing' but we don't recognize the metric, break the loop.
                    break;
                }
            }
            // ====================================================================

            setFundamentalResult(fundRes);

            // ABORT FIX: Catch ALL failure states and unresolved "Missing" data!
            if (
                fundRes.status === 'HALT' ||
                fundRes.status === 'FAIL' ||
                fundRes.status === 'REJECTED' ||
                (fundRes.diagnostic && fundRes.diagnostic.includes('Missing'))
            ) {
                setErrorMsg(`PIPELINE ABORTED AT LAYER 1 (FUNDAMENTALS): ${fundRes.diagnostic}`);
                setLoading(false);
                return;
            }
            setCurrentStep(5);
            // ====================================================================

            setFundamentalResult(fundRes);

            // ==========================================
            // ABORT FIX: Catch ALL failure states and unresolved "Missing" data!
            // ==========================================
            if (
                fundRes.status === 'HALT' ||
                fundRes.status === 'FAIL' ||
                fundRes.status === 'REJECTED' ||
                (fundRes.diagnostic && fundRes.diagnostic.includes('Missing'))
            ) {
                setErrorMsg(`PIPELINE ABORTED AT LAYER 1 (FUNDAMENTALS): ${fundRes.diagnostic}`);
                setLoading(false);
                return;
            }
            setCurrentStep(5);

            // ====================================================================

            // ==========================================
            // ABORT FIX: Catch HALT, FAIL, and REJECTED!
            // ==========================================
            if (fundRes.status === 'HALT' || fundRes.status === 'FAIL' || fundRes.status === 'REJECTED') {
                setErrorMsg(`PIPELINE ABORTED AT LAYER 1 (FUNDAMENTALS): ${fundRes.diagnostic}`);
                setLoading(false);
                return;
            }
            setCurrentStep(5);
            // ====================================================================

            setFundamentalResult(fundRes);

            if (fundRes.status === 'HALT') {
                setErrorMsg(`PIPELINE ABORTED AT LAYER 1 (FUNDAMENTALS): ${fundRes.diagnostic}`);
                setLoading(false);
                return;
            }
            setCurrentStep(5);

            // 6. Layer 2: Technical Engine
            const techRes = await fetchTechnical(preFlightData);
            setTechnicalResult(techRes);
            setCurrentStep(6); // Pipeline pauses here for Human-in-the-Loop Visual Verification

        } catch (err: any) {
            setErrorMsg(err.message || "An unexpected error occurred during the pipeline execution.");
        }
        setLoading(false);
    };

    const calculateFinalSizing = async () => {
        if (!config || !sentinelResult || !technicalResult) return;
        setLoading(true);
        try {
            const sizingConfig: SizingConfig = {
                profile: config.profile,
                mode: config.mode,
                regime: sentinelResult.regime,
                event_aware: eventAware,
                vix_storm: sentinelResult.storm_watch,
                audit_status: fundamentalResult?.status || "CLEAN",
                engine_metrics: technicalResult.metrics,
                total_capital: config.total_capital
            };

            const sizingRes = await fetchSizing(sizingConfig);
            setSizingResult(sizingRes);
            setCurrentStep(8); // Move to Final Execution View
        } catch (err: any) {
            setErrorMsg(err.message || "Failed to calculate sizing.");
        }
        setLoading(false);
    };

    return (
        <div className="min-h-screen bg-black text-gray-300 font-sans flex flex-col">
            <PreFlight onStartAudit={handleStartAudit} isLoading={loading}/>

            <main className="flex-grow p-6">
                {errorMsg && (
                    <div
                        className="bg-red-900/50 border border-red-500 text-white p-4 rounded mb-6 font-mono whitespace-pre-wrap shadow-lg">
                        <span className="font-bold text-red-400 block mb-1">SYSTEM HALT:</span>
                        {errorMsg}
                    </div>
                )}

                {/* --- DASHBOARD VIEW --- */}
                {currentStep > 0 && currentStep < 8 && (
                    <div className="space-y-4">

                        {/* Layer 0: Sentinel */}
                        {sentinelResult && (
                            <div
                                className={`p-4 rounded border ${sentinelResult.verdict === 'PASS' ? 'border-green-800 bg-green-900/20' : 'border-red-800 bg-red-900/20'}`}>
                                <h3 className="font-bold text-lg mb-2 text-white">1. Systemic Macro Weather (Layer
                                    0)</h3>
                                <div className="grid grid-cols-3 gap-4 font-mono text-sm">
                                    <div><span className="text-gray-500">Regime:</span> <span
                                        className={sentinelResult.regime === 'BULLISH' ? 'text-green-400' : 'text-yellow-400'}>{sentinelResult.regime}</span>
                                    </div>
                                    <div><span className="text-gray-500">Storm Watch:</span> <span
                                        className={sentinelResult.storm_watch ? 'text-red-400 font-bold' : 'text-green-400'}>{sentinelResult.storm_watch ? "ACTIVE" : "CLEAR"}</span>
                                    </div>
                                    <div className="col-span-3 text-gray-400 mt-2">{sentinelResult.reason}</div>
                                </div>
                            </div>
                        )}

                        {/* Layer 1.5a & 1.5b: Sympathy & Asset Gates (v8.3) */}
                        <div className="grid grid-cols-2 gap-4">
                            {sympathyResult && (
                                <div
                                    className={`p-4 rounded border ${sympathyResult.status === 'PASS' ? 'border-green-800 bg-green-900/20' : 'border-red-800 bg-red-900/20'}`}>
                                    <h3 className="font-bold text-lg mb-2 text-white">2. Sympathy Audit (Layer
                                        1.5a)</h3>
                                    <div className="font-mono text-sm space-y-1">
                                        <div><span className="text-gray-500">Status:</span> <span
                                            className={sympathyResult.status === 'PASS' ? 'text-green-400' : 'text-red-400'}>{sympathyResult.status}</span>
                                        </div>
                                        <div><span className="text-gray-500">Sector ETF:</span> <span
                                            className="text-blue-400">{sympathyResult.metrics?.Sector_ETF || 'N/A'}</span>
                                        </div>
                                        <div className="text-gray-400 mt-2">{sympathyResult.diagnostic}</div>
                                    </div>
                                </div>
                            )}

                            {assetGatesResult && (
                                <div
                                    className={`p-4 rounded border ${assetGatesResult.status === 'PASS' ? 'border-green-800 bg-green-900/20' : (assetGatesResult.status === 'LIMIT_ONLY' ? 'border-yellow-800 bg-yellow-900/20' : 'border-red-800 bg-red-900/20')}`}>
                                    <h3 className="font-bold text-lg mb-2 text-white">3. Asset Gates (Layer 1.5b)</h3>
                                    <div className="font-mono text-sm space-y-1">
                                        <div><span className="text-gray-500">Status:</span> <span
                                            className={assetGatesResult.status === 'PASS' ? 'text-green-400' : (assetGatesResult.status === 'LIMIT_ONLY' ? 'text-yellow-400' : 'text-red-400')}>{assetGatesResult.status}</span>
                                        </div>
                                        <div><span className="text-gray-500">IV Guard:</span>
                                            <span>{assetGatesResult.metrics?.IV_Guard?.Implied_Vol > assetGatesResult.metrics?.IV_Guard?.Historical_Vol ? 'IV > HV (LIMIT ORDERS ONLY)' : 'CLEAR'}</span>
                                        </div>
                                        <div className="text-gray-400 mt-2">{assetGatesResult.diagnostic}</div>
                                    </div>
                                </div>
                            )}
                        </div>

                        {/* Layer 1: Fundamentals */}
                        {fundamentalResult && (
                            <div className={`p-4 rounded border ${
                                fundamentalResult.status === 'CLEAN' && !fundamentalResult.diagnostic.includes('WARNING')
                                    ? 'border-green-800 bg-green-900/20'
                                    : 'border-yellow-800 bg-yellow-900/20'
                            }`}>
                                <h3 className="font-bold text-lg mb-2 text-white">4. Clean Trade Audit (Layer 1)</h3>
                                <div className="font-mono text-sm space-y-1">
                                    {/* [NEW] Explicit Status Badge */}
                                    <div>
                                        <span className="text-gray-500">Status:</span>{' '}
                                        <span
                                            className={fundamentalResult.status === 'CLEAN' ? 'text-green-400' : 'text-yellow-400'}>
                    {fundamentalResult.status}
                </span>
                                    </div>

                                    {/* The Diagnostic Message */}
                                    <div
                                        className="text-gray-400 mt-2 whitespace-pre-wrap">{fundamentalResult.diagnostic}</div>
                                </div>
                            </div>
                        )}

                        {technicalResult && (
                            <div className="space-y-6 mt-6">
                                <div className="p-6 rounded-xl border border-gray-900 bg-black shadow-2xl">
                                    <h3 className="font-bold text-lg mb-8 text-white tracking-widest uppercase border-b border-gray-900 pb-4">
                                        5. Technical Engine (Layer 2)
                                    </h3>

                                    {/* TIER 1: PRIMARY CORE INDICATORS (Pinned) */}
                                    <div className="grid grid-cols-2 lg:grid-cols-4 gap-6 mb-10">
                                        {[
                                            {label: 'Price', val: technicalResult.metrics?.Price, color: 'text-white'},
                                            {label: 'ATR', val: technicalResult.metrics?.ATR, color: 'text-blue-400'},
                                            {
                                                label: 'SMA 50',
                                                val: technicalResult.metrics?.SMA_50,
                                                color: 'text-purple-400'
                                            },
                                            {
                                                label: 'Hard Stop',
                                                val: technicalResult.metrics?.Hard_Stop,
                                                color: 'text-red-400'
                                            }
                                        ].map((item) => (
                                            <div key={item.label}
                                                 className="bg-gray-950 p-5 rounded-lg border border-gray-800 shadow-lg ring-1 ring-inset ring-white/5">
                                                <span
                                                    className="text-[10px] text-gray-500 uppercase font-black block mb-2 tracking-widest">{item.label}</span>
                                                <span className={`text-2xl font-mono font-bold ${item.color}`}>
                            {typeof item.val === 'number' ? `$${item.val.toFixed(2)}` : item.val || 'N/A'}
                        </span>
                                            </div>
                                        ))}
                                    </div>

                                    {/* TIER 2: SECONDARY TELEMETRY (Matching Core "Pill" Style) */}
                                    <div>
                                        <h4 className="text-[10px] text-blue-500 font-bold uppercase mb-6 tracking-widest flex items-center gap-2">
                                            <span className="w-2 h-2 bg-blue-500 rounded-full animate-pulse"/>
                                            Full Engine Telemetry
                                        </h4>

                                        {/* 4-Column Grid that mirrors the style of Tier 1 */}
                                        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                                            {Object.entries(technicalResult.metrics || {})
                                                .filter(([key]) => !['Price', 'ATR', 'SMA_50', 'Hard_Stop', 'Notes', 'ATR_Dist_Note', 'charts'].includes(key))
                                                .map(([key, value]) => (
                                                    <div key={key}
                                                         className="bg-gray-950/40 p-3 rounded border border-gray-800/60 flex flex-col justify-between min-h-[70px] hover:border-blue-500/50 transition-colors group">
                                <span
                                    className="text-[9px] text-gray-600 uppercase font-bold group-hover:text-blue-400/80 transition-colors tracking-tight">
                                    {key.replace(/_/g, ' ')}
                                </span>
                                                        <span
                                                            className="text-sm font-mono font-bold text-gray-200 truncate mt-1">
                                    {typeof value === 'number' && !key.includes('window')
                                        ? value.toLocaleString(undefined, {maximumFractionDigits: 2})
                                        : String(value)}
                                </span>
                                                    </div>
                                                ))}
                                        </div>
                                    </div>
                                </div>

                                {/* VISUAL AUDIT: Independent Chart Container */}
                                <div className="bg-black border border-gray-800 rounded-xl p-6">
                                    <h3 className="font-bold text-white uppercase tracking-widest mb-6 text-sm flex items-center justify-between">
                                        <span>Visual Audit Perspectives [Doc 4]</span>
                                        <div className="flex gap-2">
                                            <div className="w-2 h-2 rounded-full bg-green-500"/>
                                            <div className="w-2 h-2 rounded-full bg-yellow-500"/>
                                            <div className="w-2 h-2 rounded-full bg-red-500"/>
                                        </div>
                                    </h3>
                                    <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                                        {['primary', 'context', 'focus'].map((view) => (
                                            <div key={view}
                                                 className="border border-gray-800 rounded-lg bg-gray-950 overflow-hidden flex flex-col group hover:border-blue-500/50 transition-all">
                                                <div className="bg-gray-900 p-2 text-center border-b border-gray-800">
                                                    <span
                                                        className="text-[10px] font-black text-gray-500 uppercase tracking-widest">{view} View</span>
                                                </div>
                                                <div
                                                    className="relative aspect-video flex items-center justify-center p-2 bg-[radial-gradient(#1e293b_1px,transparent_1px)] [background-size:16px_16px]">
                                                    <img
                                                        src={`${technicalResult.charts[view]}?t=${Date.now()}`}
                                                        alt={view}
                                                        className="w-full h-full object-contain"
                                                        onError={(e) => {
                                                            e.currentTarget.style.display = 'none';
                                                        }}
                                                    />
                                                </div>
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            </div>
                        )}
                    </div>
                )}
            </main>

            {/* SYNCED HANDSHAKE: Final Execution Step 8 */}
            {currentStep === 8 && sizingResult && fundamentalResult && (
                <Execution
                    sizingData={sizingResult}
                    fundamentalResult={fundamentalResult}
                    eventAware={eventAware}
                />
            )}
        </div>
    );
}