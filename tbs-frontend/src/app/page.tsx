"use client";

import React, { useState } from 'react';
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
    fetchAnalystRetrieval,
    AuditConfig,
    SizingConfig
} from '../services/api';

export default function MasterDashboard() {
    const [currentStep, setCurrentStep] = useState<number>(0);
    const [config, setConfig] = useState<AuditConfig | null>(null);
    const [isETF, setIsETF] = useState<boolean>(false);
    const [eventAware, setEventAware] = useState<boolean>(false);

    // --- Position Monitor State ---
    const [isMonitorMode, setIsMonitorMode] = useState<boolean>(false);
    const [threats, setThreats] = useState<string[]>([]);
    const [noAdds, setNoAdds] = useState<boolean>(false);
    const [monitorRecommendation, setMonitorRecommendation] = useState<{status: string, rationale: string} | null>(null);

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

        // Reset Monitor State
        const monitorActive = !!(preFlightData.entry_price && preFlightData.shares);
        setIsMonitorMode(monitorActive);
        setThreats([]);
        setNoAdds(false);
        setMonitorRecommendation(null);

        let currentThreats: string[] = [];
        let currentNoAdds = false;

        setCurrentStep(1);

        try {
            // 1. Pre-Flight: Auto ID
            const idRes = await fetchAutoID(preFlightData.ticker, preFlightData.mode);
            setIsETF(idRes.is_etf);
            preFlightData.is_etf = idRes.is_etf;

            // 2. Layer 0: Sentinel
            const sentinelRes = await fetchSentinel(preFlightData);
            setSentinelResult(sentinelRes);
            if (sentinelRes.verdict === 'HALT' || sentinelRes.verdict === 'FORCE HARVEST') {
                if (monitorActive) {
                    currentThreats.push(`Layer 0 (Sentinel): ${sentinelRes.reason}`);
                    currentNoAdds = true;
                } else {
                    setErrorMsg(`PIPELINE ABORTED AT LAYER 0 (SENTINEL): ${sentinelRes.reason}`);
                    setLoading(false);
                    return;
                }
            }

            if (sentinelRes.details && sentinelRes.details.tnx_close_daily) {
                preFlightData.tnx = sentinelRes.details.tnx_close_daily / 10;
            }

            setCurrentStep(2);

            // 3. Layer 1.5a: Sympathy Audit
            const sympRes = await fetchSympathyAudit(preFlightData);
            setSympathyResult(sympRes);
            if (sympRes.status === 'HALT' || sympRes.status === 'ERROR') {
                if (monitorActive) {
                    currentThreats.push(`Layer 1.5a (Sympathy): ${sympRes.diagnostic}`);
                    currentNoAdds = true;
                } else {
                    setErrorMsg(`PIPELINE ABORTED AT LAYER 1.5a (SYMPATHY): ${sympRes.diagnostic}`);
                    setLoading(false);
                    return;
                }
            }
            setCurrentStep(3);

            // 4. Layer 1.5b: Asset Gates
            const gatesRes = await fetchAssetGates(preFlightData);
            setAssetGatesResult(gatesRes);
            if (gatesRes.status === 'BLOCKED') {
                if (monitorActive) {
                    currentThreats.push(`Layer 1.5b (Asset Gates): ${gatesRes.diagnostic}`);
                    currentNoAdds = true;
                } else {
                    setErrorMsg(`PIPELINE ABORTED AT LAYER 1.5b (ASSET GATES): ${gatesRes.diagnostic}`);
                    setLoading(false);
                    return;
                }
            }
            if (gatesRes.status === 'LIMIT_ONLY') {
                setEventAware(true);
            }
            setCurrentStep(4);

            // 5. Layer 1: Fundamental DNA, Pulse, and Health
            let fundRes = await fetchFundamentals(preFlightData);
            let retryCount = 0;
            const maxRetries = 5;

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
                    metricToFetch = 'Moat Rating'; payloadKey = 'moat';
                } else if (diagLower.includes('wacc')) {
                    metricToFetch = 'WACC'; payloadKey = 'wacc';
                } else if (diagLower.includes('roic')) {
                    metricToFetch = 'ROIC'; payloadKey = 'roic_override';
                } else if (diagLower.includes('fcf')) {
                    metricToFetch = 'FCF Yield'; payloadKey = 'fcf_yield_override';
                } else if (diagLower.includes('debt') || diagLower.includes('d/e')) {
                    metricToFetch = 'Debt-to-Equity'; payloadKey = 'de_override';
                }

                if (metricToFetch && payloadKey) {
                    setErrorMsg(`⚠️ AUTOMATIC OVERRIDE: AI Analyst hunting for missing ${metricToFetch}... (Attempt ${retryCount}/5)`);

                    try {
                        const aiRes = await fetchAnalystRetrieval(preFlightData.ticker, metricToFetch);

                        if (aiRes && aiRes.data && aiRes.data.value !== null && aiRes.data.value !== "NOT FOUND") {
                            let aiValue = aiRes.data.value;

                            if (payloadKey === 'moat') {
                                const rawVal = String(aiValue).toUpperCase();
                                if (rawVal.includes('WIDE')) aiValue = 'WIDE';
                                else if (rawVal.includes('NARROW')) aiValue = 'NARROW';
                                else if (rawVal.includes('NONE') || rawVal.includes('NO MOAT')) aiValue = 'NONE';
                                else throw new Error(`AI returned an invalid Moat: "${rawVal}".`);
                            }

                            if (payloadKey === 'moat' && aiValue === 'NONE' && preFlightData.profile === 'WEALTH') {
                                if (monitorActive) {
                                    currentThreats.push(`AI verified Moat is NONE. WEALTH profile mandates WIDE/NARROW.`);
                                    currentNoAdds = true;
                                } else {
                                    setErrorMsg(`❌ AI verified Moat is NONE. WEALTH profile mandates WIDE or NARROW.`);
                                    setLoading(false);
                                    return;
                                }
                            }

                            preFlightData[payloadKey] = aiValue;
                            setErrorMsg(`✅ AI retrieved ${metricToFetch}: ${aiValue}. Resuming Audit...`);
                            await new Promise(resolve => setTimeout(resolve, 2000));
                            fundRes = await fetchFundamentals({ ...preFlightData });
                        } else {
                            if (monitorActive) {
                                currentThreats.push(`AI Analyst could not verify ${metricToFetch} online.`);
                                currentNoAdds = true;
                                break;
                            } else {
                                setErrorMsg(`❌ AI Analyst could not verify ${metricToFetch} online.`);
                                setLoading(false);
                                return;
                            }
                        }
                    } catch (aiError) {
                        if (monitorActive) {
                            currentThreats.push(`AI Analyst network failure fetching ${metricToFetch}.`);
                            currentNoAdds = true;
                            break;
                        } else {
                            setErrorMsg(`❌ AI Analyst network failure while fetching ${metricToFetch}.`);
                            setLoading(false);
                            return;
                        }
                    }
                } else {
                    break;
                }
            }

            setFundamentalResult(fundRes);

            // Cleaned abort logic with Position Monitor bypass
            if (
                fundRes.status === 'HALT' ||
                fundRes.status === 'FAIL' ||
                fundRes.status === 'REJECTED' ||
                fundRes.status === 'WEAKENED' ||
                (fundRes.diagnostic && fundRes.diagnostic.includes('Missing'))
            ) {
                if (monitorActive) {
                    currentThreats.push(`Layer 1 (Fundamentals): ${fundRes.diagnostic}`);
                    currentNoAdds = true;
                } else {
                    setErrorMsg(`PIPELINE ABORTED AT LAYER 1 (FUNDAMENTALS): ${fundRes.diagnostic}`);
                    setLoading(false);
                    return;
                }
            }
            setCurrentStep(5);

            // 6. Layer 2: Technical Engine
            const techRes = await fetchTechnical(preFlightData);
            setTechnicalResult(techRes);
            setCurrentStep(6);

            // Handle Position Monitor Evaluation Post-Step 6
            if (monitorActive) {
                setThreats(currentThreats);
                setNoAdds(currentNoAdds);

                const exitSig = techRes.metrics?.Exit_Signal;
                const hasExitSignal = exitSig === 'WARNING' || exitSig === 'EXIT';

                if (hasExitSignal) currentThreats.push(`Engine Exit Signal Active: ${exitSig}`);
                if (techRes.metrics?.DI_Minus > techRes.metrics?.DI_Plus) currentThreats.push(`Bearish DI Dominance`);
                if (techRes.status === 'HALT') currentThreats.push(`Engine HALT: ${techRes.diagnostic}`);

                setThreats([...currentThreats]);

                let recommendation = '';
                let rationale = '';

                if (hasExitSignal) {
                    recommendation = 'EXIT';
                    rationale = `Exit_Signal = ${exitSig}. Position structural health deteriorating. Evaluate immediate exit.`;
                } else if (currentNoAdds || techRes.status === 'HALT') {
                    recommendation = 'NO ACTION';
                    rationale = 'Position structure intact but environment blocks new capital. Hold current position, do not add.';
                } else {
                    recommendation = 'FIT FOR ADD';
                    rationale = 'All pipeline steps clear and no exit signals active. Position eligible for add sizing.';
                }

                setMonitorRecommendation({ status: recommendation, rationale });
            } else if (techRes.status === 'HALT' || techRes.status === 'ERROR') {
                // If NOT in monitor mode, a Technical Engine HALT stops the flow before sizing
                setErrorMsg(`PIPELINE ABORTED AT LAYER 2 (TECHNICAL): ${techRes.diagnostic}`);
                setLoading(false);
                return;
            }

            setErrorMsg(null); // Clear loading/info messages if we made it here successfully

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
            setCurrentStep(8);
        } catch (err: any) {
            setErrorMsg(err.message || "Failed to calculate sizing.");
        }
        setLoading(false);
    };

    // --- Smart Formatter for Step 6 Metrics Payload ---
    const formatMetricValue = (key: string, val: any) => {
        if (val === null || val === undefined) return 'N/A';
        if (key === 'Exit_Signal') return val === false ? 'CLEAR' : String(val).toUpperCase();
        if (typeof val === 'boolean') return val ? 'TRUE' : 'FALSE';
        if (Array.isArray(val)) return val.length > 0 ? val.join(', ') : 'None';
        if (key === 'Reward_Risk' && val === 9999) return 'FLOOR_EXACT';
        if (typeof val === 'number') {
            if (key.toLowerCase().includes('window') || key.toLowerCase().includes('counter')) return val.toString();
            return val.toLocaleString(undefined, { maximumFractionDigits: 2 });
        }
        return String(val);
    };

    return (
        <div className="min-h-screen bg-black text-gray-300 font-sans flex flex-col">
            <PreFlight onStartAudit={handleStartAudit} isLoading={loading} />

            <main className="flex-grow p-6">
                {errorMsg && (
                    <div className={`p-4 rounded mb-6 font-mono whitespace-pre-wrap shadow-lg border ${errorMsg.includes('✅') || errorMsg.includes('⚠️') ? 'bg-blue-900/30 border-blue-500 text-blue-200' : 'bg-red-900/50 border-red-500 text-white'}`}>
                        <span className={`font-bold block mb-1 ${errorMsg.includes('✅') || errorMsg.includes('⚠️') ? 'text-blue-400' : 'text-red-400'}`}>
                            {errorMsg.includes('✅') || errorMsg.includes('⚠️') ? 'SYSTEM STATUS:' : 'SYSTEM HALT:'}
                        </span>
                        {errorMsg}
                    </div>
                )}

                {currentStep > 0 && currentStep < 8 && (
                    <div className="space-y-4">
                        {/* Layer 0: Sentinel */}
                        {sentinelResult && (
                            <div className={`p-4 rounded border ${sentinelResult.verdict === 'PASS' ? 'border-green-800 bg-green-900/20' : 'border-red-800 bg-red-900/20'}`}>
                                <h3 className="font-bold text-lg mb-2 text-white">1. Systemic Macro Weather (Layer 0)</h3>
                                <div className="grid grid-cols-3 gap-4 font-mono text-sm">
                                    <div><span className="text-gray-500">Regime:</span> <span className={sentinelResult.regime === 'BULLISH' ? 'text-green-400' : 'text-yellow-400'}>{sentinelResult.regime}</span></div>
                                    <div><span className="text-gray-500">Storm Watch:</span> <span className={sentinelResult.storm_watch ? 'text-red-400 font-bold' : 'text-green-400'}>{sentinelResult.storm_watch ? "ACTIVE" : "CLEAR"}</span></div>
                                    <div className="col-span-3 text-gray-400 mt-2">{sentinelResult.reason}</div>
                                </div>
                            </div>
                        )}

                        {/* Layer 1.5a & 1.5b: Sympathy & Asset Gates */}
                        <div className="grid grid-cols-2 gap-4">
                            {sympathyResult && (
                                <div className={`p-4 rounded border ${sympathyResult.status === 'PASS' ? 'border-green-800 bg-green-900/20' : 'border-red-800 bg-red-900/20'}`}>
                                    <h3 className="font-bold text-lg mb-2 text-white">2. Sympathy Audit (Layer 1.5a)</h3>
                                    <div className="font-mono text-sm space-y-1">
                                        <div><span className="text-gray-500">Status:</span> <span className={sympathyResult.status === 'PASS' ? 'text-green-400' : 'text-red-400'}>{sympathyResult.status}</span></div>
                                        <div><span className="text-gray-500">Sector ETF:</span> <span className="text-blue-400">{sympathyResult.metrics?.Sector_ETF || 'N/A'}</span></div>
                                        <div className="text-gray-400 mt-2">{sympathyResult.diagnostic}</div>
                                    </div>
                                </div>
                            )}

                            {assetGatesResult && (
                                <div className={`p-4 rounded border ${assetGatesResult.status === 'PASS' ? 'border-green-800 bg-green-900/20' : (assetGatesResult.status === 'LIMIT_ONLY' ? 'border-yellow-800 bg-yellow-900/20' : 'border-red-800 bg-red-900/20')}`}>
                                    <h3 className="font-bold text-lg mb-2 text-white">3. Asset Gates (Layer 1.5b)</h3>
                                    <div className="font-mono text-sm space-y-1">
                                        <div><span className="text-gray-500">Status:</span> <span className={assetGatesResult.status === 'PASS' ? 'text-green-400' : (assetGatesResult.status === 'LIMIT_ONLY' ? 'text-yellow-400' : 'text-red-400')}>{assetGatesResult.status}</span></div>
                                        <div><span className="text-gray-500">IV Guard:</span> <span>{assetGatesResult.metrics?.IV_Guard?.Implied_Vol > assetGatesResult.metrics?.IV_Guard?.Historical_Vol ? 'IV > HV (LIMIT ORDERS ONLY)' : 'CLEAR'}</span></div>
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
                                    <div>
                                        <span className="text-gray-500">Status:</span>{' '}
                                        <span className={fundamentalResult.status === 'CLEAN' ? 'text-green-400' : 'text-yellow-400'}>
                                            {fundamentalResult.status}
                                        </span>
                                    </div>
                                    <div className="text-gray-400 mt-2 whitespace-pre-wrap">{fundamentalResult.diagnostic}</div>
                                </div>
                            </div>
                        )}

                        {technicalResult && (
                            <div className="space-y-6 mt-6">
                                <div className="p-6 rounded-xl border border-gray-900 bg-black shadow-2xl">
                                    <h3 className="font-bold text-lg mb-6 text-white tracking-widest uppercase border-b border-gray-900 pb-4">
                                        5. Technical Engine (Layer 2)
                                    </h3>

                                    {/* COMPACT TERMINAL TELEMETRY (BORDERLESS & SPACED) */}
                                    <div className="mb-8 bg-black border border-gray-900 rounded-lg p-6">
                                        <div className="grid grid-cols-1 md:grid-cols-2 gap-x-8 md:gap-x-16 lg:gap-x-32 gap-y-3">
                                            {Object.entries(technicalResult.metrics || {})
                                                .filter(([key]) => !['charts', 'Notes', 'ATR_Dist_Note'].includes(key))
                                                .map(([key, value]) => (
                                                    <div key={key} className="flex justify-between items-center group md:pr-8">
                                                        <span className="text-xs text-gray-500 font-bold uppercase tracking-widest whitespace-nowrap">
                                                            {key.replace(/_/g, ' ')}
                                                        </span>

                                                        {/* Terminal Dotted Leader Line */}
                                                        <div className="flex-grow border-b border-dotted border-gray-800 opacity-40 mx-4 group-hover:border-blue-900/50 transition-colors"></div>

                                                        <span className={`text-sm font-mono font-bold whitespace-nowrap ${
                                                            value === null || value === undefined ? 'text-gray-700' :
                                                                key === 'Exit_Signal' && value !== false ? 'text-red-400' :
                                                                    'text-gray-200'
                                                        }`}>
                                                            {formatMetricValue(key, value)}
                                                        </span>
                                                    </div>
                                                ))}
                                        </div>
                                    </div>

                                    {/* --- POSITION MONITOR DASHBOARD --- */}
                                    {isMonitorMode && monitorRecommendation && (
                                        <div className={`mt-8 p-6 rounded-xl border-2 shadow-lg ${
                                            monitorRecommendation.status === 'EXIT' ? 'border-red-600 bg-red-950/40 text-red-100' :
                                                monitorRecommendation.status === 'NO ACTION' ? 'border-yellow-600 bg-yellow-950/40 text-yellow-100' :
                                                    'border-green-600 bg-green-950/40 text-green-100'
                                        }`}>
                                            <h4 className="font-black text-xl tracking-widest uppercase mb-2">
                                                RECOMMENDATION: {monitorRecommendation.status}
                                            </h4>
                                            <p className="font-mono text-sm opacity-90 mb-4">{monitorRecommendation.rationale}</p>

                                            {threats.length > 0 && (
                                                <div className="border-t border-white/20 pt-4 mt-2">
                                                    <span className="text-xs font-bold uppercase tracking-widest opacity-70 block mb-2">Accumulated Threats:</span>
                                                    <ul className="list-disc pl-5 font-mono text-sm space-y-1">
                                                        {threats.map((t, idx) => <li key={idx} className="text-red-300">{t}</li>)}
                                                    </ul>
                                                </div>
                                            )}
                                        </div>
                                    )}

                                    {/* Human-in-the-loop progression */}
                                    {!errorMsg && (
                                        <div className="mt-8 flex justify-end">
                                            {isMonitorMode ? (
                                                // Only show Sizing button in monitor mode if Fit For Add
                                                monitorRecommendation?.status === 'FIT FOR ADD' && (
                                                    <button
                                                        onClick={calculateFinalSizing}
                                                        className="bg-blue-600 hover:bg-blue-500 text-white font-bold py-3 px-8 rounded uppercase tracking-widest transition-colors"
                                                    >
                                                        Position Cleared - Proceed to Add Sizing
                                                    </button>
                                                )
                                            ) : (
                                                // Standard Entry Mode
                                                technicalResult.status !== 'HALT' && (
                                                    <button
                                                        onClick={calculateFinalSizing}
                                                        className="bg-blue-600 hover:bg-blue-500 text-white font-bold py-3 px-8 rounded uppercase tracking-widest transition-colors"
                                                    >
                                                        Charts Verified - Proceed to Sizing
                                                    </button>
                                                )
                                            )}
                                        </div>
                                    )}
                                </div>

                                {/* VISUAL AUDIT */}
                                <div className="bg-black border border-gray-800 rounded-xl p-6">
                                    <h3 className="font-bold text-white uppercase tracking-widest mb-6 text-sm flex items-center justify-between">
                                        <span>Visual Audit Perspectives [Doc 4]</span>
                                        <div className="flex gap-2">
                                            <div className="w-2 h-2 rounded-full bg-green-500" />
                                            <div className="w-2 h-2 rounded-full bg-yellow-500" />
                                            <div className="w-2 h-2 rounded-full bg-red-500" />
                                        </div>
                                    </h3>
                                    <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                                        {['primary', 'context', 'focus'].map((view) => (
                                            <div key={view} className="border border-gray-800 rounded-lg bg-gray-950 overflow-hidden flex flex-col group hover:border-blue-500/50 transition-all">
                                                <div className="bg-gray-900 p-2 text-center border-b border-gray-800">
                                                    <span className="text-[10px] font-black text-gray-500 uppercase tracking-widest">{view} View</span>
                                                </div>
                                                <div className="relative aspect-video flex items-center justify-center p-2 bg-[radial-gradient(#1e293b_1px,transparent_1px)] [background-size:16px_16px]">
                                                    <img
                                                        src={`${technicalResult.charts[view]}?t=${Date.now()}`}
                                                        alt={view}
                                                        className="w-full h-full object-contain"
                                                        onError={(e) => { e.currentTarget.style.display = 'none'; }}
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