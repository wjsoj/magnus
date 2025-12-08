// 文件: front_end/src/app/page.tsx
"use client";

import { useState, useEffect, useRef, useMemo } from "react";

// --- 常量配置 ---
const API_PORT = process.env.SERVER_PORT
const API_BASE = `http://127.0.0.1:${API_PORT}`;
const MAX_GPU_COUNT = 2;

const GPU_TYPES = [
  { label: "NVIDIA GeForce RTX 5090", value: "RTX_5090", meta: "32GB • Blackwell Architecture" },
];

interface Branch { name: string; commit_sha: string; }
interface Commit { sha: string; message: string; author: string; date: string; }

// --- 样式注入：Shake 动画 ---
const SHAKE_STYLE = `
  @keyframes shake {
    0%, 100% { transform: translateX(0); }
    10%, 30%, 50%, 70%, 90% { transform: translateX(-4px); }
    20%, 40%, 60%, 80% { transform: translateX(4px); }
  }
  .animate-shake {
    animation: shake 0.4s cubic-bezier(.36,.07,.19,.97) both;
    border-color: #ef4444 !important; /* Red-500 */
    box-shadow: 0 0 0 1px #ef4444 !important;
  }
  .text-error { color: #ef4444 !important; }

  /* 移除数字输入框的默认箭头 */
  .hide-arrows::-webkit-outer-spin-button,
  .hide-arrows::-webkit-inner-spin-button {
    -webkit-appearance: none;
    margin: 0;
  }
  .hide-arrows {
    -moz-appearance: textfield;
  }
`;

// --- 组件：SearchableSelect (保持不变) ---
interface SearchableSelectProps {
  label: string;
  value: string;
  options: { label: string; value: string; meta?: string }[];
  onChange: (val: string) => void;
  placeholder?: string;
  disabled?: boolean;
  hasError?: boolean;
  id?: string;
}

function SearchableSelect({ label, value, options, onChange, placeholder, disabled, hasError, id }: SearchableSelectProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [query, setQuery] = useState("");
  const containerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const selectedOption = options.find(o => o.value === value);
    if (selectedOption) setQuery(selectedOption.label);
    else if (!value) setQuery("");
  }, [value, options]);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setIsOpen(false);
        const selectedOption = options.find(o => o.value === value);
        setQuery(selectedOption ? selectedOption.label : "");
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [value, options]);

  const handleClear = (e: React.MouseEvent) => {
    e.stopPropagation(); setQuery(""); onChange(""); inputRef.current?.focus(); 
  };

  const filteredOptions = useMemo(() => {
    if (query === "") return options;
    const selectedOption = options.find(o => o.value === value);
    if (selectedOption && query === selectedOption.label) return options;
    return options.filter((opt) => {
      const searchStr = (opt.label + (opt.meta || "")).toLowerCase();
      return searchStr.includes(query.toLowerCase());
    });
  }, [query, options, value]);

  return (
    <div className="relative" ref={containerRef} id={id}>
      <label className={`text-xs uppercase tracking-wider mb-1 block transition-colors ${hasError ? 'text-red-500 font-bold' : 'text-gray-500'}`}>
        {label} {hasError && "*"}
      </label>
      <div className="relative group">
        <input
          ref={inputRef}
          type="text"
          disabled={disabled}
          className={`w-full bg-gray-950 border p-3 pr-16 rounded text-white outline-none transition-all placeholder-gray-600 
            disabled:cursor-not-allowed disabled:text-gray-500 disabled:bg-[#0A0A0C]
            ${hasError ? 'animate-shake' : isOpen ? 'border-blue-500 ring-1 ring-blue-500' : 'border-gray-700'}
          `}
          placeholder={disabled ? "Waiting for scan..." : (placeholder || "Search...")}
          value={query}
          onChange={(e) => { setQuery(e.target.value); setIsOpen(true); }}
          onFocus={() => !disabled && setIsOpen(true)}
        />
        <div className="absolute right-3 top-0 h-full flex items-center gap-2">
          {!disabled && query && (
            <button onClick={handleClear} className="p-1 text-gray-500 hover:text-white hover:bg-gray-800 rounded-full transition-colors">
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
            </button>
          )}
          <div className="pointer-events-none text-gray-600">
            <svg className={`w-4 h-4 transition-transform ${isOpen ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" /></svg>
          </div>
        </div>
      </div>
      {isOpen && !disabled && (
        <div className="absolute z-50 w-full mt-1 bg-gray-900 border border-gray-700 rounded-lg shadow-xl overflow-hidden animate-in fade-in zoom-in-95 duration-100">
          <div className="max-h-64 overflow-y-auto custom-scrollbar">
            {filteredOptions.map((opt) => (
              <div key={opt.value} onClick={() => { onChange(opt.value); setQuery(opt.label); setIsOpen(false); }} className={`p-3 cursor-pointer hover:bg-blue-900/30 transition-colors border-b border-gray-800 last:border-0 ${opt.value === value ? 'bg-blue-900/20 border-l-2 border-l-blue-500' : ''}`}>
                <div className="text-sm font-medium text-gray-200 truncate">{opt.label}</div>
                {opt.meta && <div className="text-xs text-gray-500 mt-0.5 font-mono">{opt.meta}</div>}
              </div>
            ))}
            {filteredOptions.length === 0 && <div className="p-4 text-center text-gray-500 text-sm">No results found</div>}
          </div>
        </div>
      )}
    </div>
  );
}

// --- 组件：GPU Count Stepper (数量步进器) ---
function GpuCountInput({ value, onChange }: { value: number, onChange: (v: number) => void }) {
  const handleIncrement = () => {
    if (value < MAX_GPU_COUNT) onChange(value + 1);
  };
  const handleDecrement = () => {
    if (value > 1) onChange(value - 1);
  };
  
  return (
    <div>
      <label className="text-xs text-gray-500 uppercase tracking-wider mb-1 block">GPU Count</label>
      {/* 整体容器：包含输入框和按钮组 */}
      <div className="flex bg-gray-950 border border-gray-700 rounded transition-all focus-within:border-blue-500 focus-within:ring-1 focus-within:ring-blue-500">
        
        {/* 输入框 (靠左，占据大部分空间) */}
        <input 
          type="number" 
          min={1} 
          max={MAX_GPU_COUNT} 
          value={value}
          onChange={(e) => {
            let val = parseInt(e.target.value);
            if (isNaN(val)) val = 1;
            if (val > MAX_GPU_COUNT) val = MAX_GPU_COUNT;
            if (val < 1) val = 1;
            onChange(val);
          }}
          // ✅ 关键修改点：left-align, 移除 width calculation, flex-grow
          className={`py-3 pl-4 text-white font-mono outline-none bg-transparent hide-arrows flex-grow text-left`}
        />

        {/* 步进按钮组 (固定宽度，垂直堆叠) */}
        <div className="flex flex-col border-l border-gray-700 w-12">
          {/* 按钮区域统一使用 flex items-center justify-center 确保图标垂直居中 */}
          <button 
            onClick={handleIncrement} 
            disabled={value >= MAX_GPU_COUNT}
            className="flex-1 text-white hover:bg-gray-800 transition-colors border-b border-gray-700 disabled:text-gray-600 disabled:cursor-not-allowed flex items-center justify-center py-0"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" /></svg>
          </button>
          <button 
            onClick={handleDecrement} 
            disabled={value <= 1}
            className="flex-1 text-white hover:bg-gray-800 transition-colors disabled:text-gray-600 disabled:cursor-not-allowed flex items-center justify-center py-0"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20 12H4" /></svg>
          </button>
        </div>
      </div>
    </div>
  );
}


// --- 主页面 (保持不变) ---
export default function Home() {
  const [namespace, setNamespace] = useState("PKU-Plasma"); 
  const [repoName, setRepoName] = useState("magnus");
  const [branches, setBranches] = useState<Branch[]>([]);
  const [commits, setCommits] = useState<Commit[]>([]);
  
  const [selectedBranch, setSelectedBranch] = useState("");
  const [selectedCommit, setSelectedCommit] = useState("");
  const [command, setCommand] = useState("python train.py");
  
  const [gpuCount, setGpuCount] = useState(1);
  const [gpuType, setGpuType] = useState("RTX_5090"); 

  const [loading, setLoading] = useState(false);
  const [hasScanned, setHasScanned] = useState(false);
  
  const [errorField, setErrorField] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const textareaRef = useRef<HTMLTextAreaElement>(null);
  useEffect(() => {
    const textarea = textareaRef.current;
    if (textarea) {
      textarea.style.height = 'auto';
      textarea.style.height = `${textarea.scrollHeight}px`;
    }
  }, [command]);

  const clearError = (field: string) => {
    if (errorField === field) {
      setErrorField(null);
      setErrorMessage(null);
    }
  };

  const fetchBranches = async () => {
    if (!namespace.trim()) { setErrorField("namespace"); setErrorMessage("⚠️ Namespace is required"); return; }
    if (!repoName.trim()) { setErrorField("repo"); setErrorMessage("⚠️ Repo Name is required"); return; }
    
    setLoading(true);
    setBranches([]); setCommits([]); setSelectedBranch(""); setSelectedCommit(""); setHasScanned(false); 
    setErrorField(null); setErrorMessage(null);
    try {
      const res = await fetch(`${API_BASE}/api/github/${namespace}/${repoName}/branches`);
      if (!res.ok) throw new Error("Failed");
      const data = await res.json();
      setBranches(data);
      if (data.length > 0) setSelectedBranch(data[0].name);
      setHasScanned(true);
    } catch (e) {
      alert(`❌ 无法连接后端 (${API_BASE})`); 
    } finally { setLoading(false); }
  };

  useEffect(() => {
    if (!selectedBranch) return;
    const fetchCommits = async () => {
      try {
        const res = await fetch(`${API_BASE}/api/github/${namespace}/${repoName}/commits?branch=${selectedBranch}`);
        const data = await res.json();
        setCommits(data);
        if (data.length > 0) setSelectedCommit(data[0].sha);
      } catch (e) { console.error(e); }
    };
    fetchCommits();
  }, [selectedBranch, namespace, repoName]);

  const scrollToError = (id: string) => {
    const el = document.getElementById(id);
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center' });
  };

  const handleLaunch = async () => {
    setErrorField(null);
    setErrorMessage(null);

    if (!namespace.trim()) { setErrorField("namespace"); setErrorMessage("⚠️ Namespace cannot be empty"); scrollToError("field-namespace"); return; }
    if (!repoName.trim()) { setErrorField("repo"); setErrorMessage("⚠️ Repository Name cannot be empty"); scrollToError("field-repo"); return; }
    if (!hasScanned) { setErrorField("repo"); setErrorMessage("⚠️ Please click 'Scan Repo' to fetch code first"); scrollToError("field-repo"); return; }
    if (!selectedBranch) { setErrorField("branch"); setErrorMessage("⚠️ Please select a Target Branch"); scrollToError("field-branch"); return; }
    if (!selectedCommit) { setErrorField("commit"); setErrorMessage("⚠️ Please select a Target Commit"); scrollToError("field-commit"); return; }
    if (!command.trim()) { setErrorField("command"); setErrorMessage("⚠️ Entry Command cannot be empty"); scrollToError("field-command"); return; }

    const payload = {
      namespace, repo_name: repoName, branch: selectedBranch, commit_sha: selectedCommit, 
      entry_command: command, gpu_count: gpuCount, gpu_type: gpuType
    };
    try {
      const res = await fetch(`${API_BASE}/api/jobs/submit`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload)
      });
      const result = await res.json();
      alert(`✅ ${result.msg}`);
    } catch (e) { alert("❌ Submit Failed"); }
  };

  return (
    <div className="fixed inset-0 w-full h-full bg-[#050505] text-gray-100 overflow-y-auto custom-scrollbar">
      <style dangerouslySetInnerHTML={{ __html: SHAKE_STYLE }} />
      
      <div className="min-h-full flex items-center justify-center p-4 font-mono">
        <div className="w-full max-w-4xl bg-[#0F0F11] border border-gray-800 rounded-xl p-8 shadow-2xl relative">
          
          <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-blue-600 via-purple-600 to-blue-600 opacity-70 rounded-t-xl"></div>

          <div className="mb-8 border-b border-gray-800 pb-4">
            <h1 className="text-3xl font-bold text-white tracking-tight">
              Magnus <span className="text-blue-500">Platform</span>
            </h1>
            <p className="text-gray-500 text-sm mt-2 flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-green-500 animate-pulse"></span>
              Milestone 1: End-to-End Connectivity
            </p>
          </div>

          <div className="space-y-8">
            {/* 1. Namespace & Repo */}
            <div className="grid grid-cols-12 gap-4">
              <div className="col-span-4" id="field-namespace">
                <label className={`text-xs uppercase tracking-wider mb-1 block transition-colors ${errorField === 'namespace' ? 'text-red-500 font-bold' : 'text-gray-500'}`}>Namespace</label>
                <input 
                  className={`w-full bg-gray-950 border p-3 rounded text-white focus:border-blue-500 outline-none transition-all 
                    ${errorField === 'namespace' ? 'animate-shake' : 'border-gray-700'}`} 
                  value={namespace} 
                  onChange={e => { setNamespace(e.target.value); clearError('namespace'); }} 
                />
              </div>
              <div className="col-span-6" id="field-repo">
                <label className={`text-xs uppercase tracking-wider mb-1 block transition-colors ${errorField === 'repo' ? 'text-red-500 font-bold' : 'text-gray-500'}`}>Repo Name</label>
                <input 
                  className={`w-full bg-gray-950 border p-3 rounded text-white focus:border-blue-500 outline-none transition-all 
                    ${errorField === 'repo' ? 'animate-shake' : 'border-gray-700'}`} 
                  value={repoName} 
                  onChange={e => { setRepoName(e.target.value); clearError('repo'); }} 
                />
              </div>
              <div className="col-span-2 flex items-end">
                <button onClick={fetchBranches} disabled={loading} className="w-full bg-blue-600 hover:bg-blue-500 text-white font-bold py-3 rounded transition-all active:scale-95 disabled:opacity-50 disabled:cursor-not-allowed shadow-lg shadow-blue-900/20">
                  {loading ? "Scanning..." : "Scan"}
                </button>
              </div>
            </div>

            {/* 2. Branch & Commit */}
            <div className="grid grid-cols-2 gap-6 bg-white/5 p-6 rounded-lg border border-gray-800/50">
              <SearchableSelect 
                id="field-branch"
                label="Target Branch" 
                disabled={!hasScanned} 
                value={selectedBranch} 
                onChange={(v) => { setSelectedBranch(v); clearError('branch'); }} 
                options={branches.map(b => ({ label: b.name, value: b.name }))} 
                placeholder="Select branch..." 
                hasError={errorField === 'branch'}
              />
              <SearchableSelect 
                id="field-commit"
                label="Target Commit" 
                disabled={!hasScanned} 
                value={selectedCommit} 
                onChange={(v) => { setSelectedCommit(v); clearError('commit'); }} 
                options={commits.map(c => ({ label: c.message, value: c.sha, meta: `${c.sha.substring(0, 7)} • ${c.author}` }))} 
                placeholder="Select commit..." 
                hasError={errorField === 'commit'}
              />
            </div>

            {/* 3. Resources */}
            <div className="grid grid-cols-3 gap-6">
              <div className="col-span-2">
                <SearchableSelect 
                  label="GPU Accelerator"
                  value={gpuType}
                  onChange={setGpuType}
                  options={GPU_TYPES}
                  placeholder="Select GPU model..."
                />
              </div>
              <div className="col-span-1">
                <GpuCountInput value={gpuCount} onChange={setGpuCount} />
              </div>
            </div>

            {/* 4. Entry Command */}
            <div id="field-command">
              <label className={`text-xs uppercase tracking-wider mb-1 block transition-colors ${errorField === 'command' ? 'text-red-500 font-bold' : 'text-gray-500'}`}>Entry Command</label>
              <div className="relative group">
                <span className="absolute left-3 top-3 text-gray-500 select-none group-focus-within:text-green-500 transition-colors">$</span>
                <textarea 
                  ref={textareaRef}
                  className={`w-full bg-gray-950 border p-3 pl-8 rounded text-green-400 font-mono focus:border-green-500 outline-none shadow-inner min-h-[120px] max-h-[400px] overflow-y-auto custom-scrollbar leading-relaxed
                    ${errorField === 'command' ? 'animate-shake' : 'border-gray-700'}`}
                  value={command} 
                  onChange={e => { setCommand(e.target.value); clearError('command'); }}
                  spellCheck={false}
                />
              </div>
            </div>

            {/* Submit Button */}
            <div className="mt-8">
              <div className="flex items-center justify-end gap-4">
                {errorMessage && (
                  <div className="text-red-500 text-sm font-bold animate-pulse">
                    {errorMessage}
                  </div>
                )}
                
                <button 
                  onClick={handleLaunch} 
                  className="w-1/3 bg-gradient-to-r from-green-600 to-emerald-600 hover:from-green-500 hover:to-emerald-500 text-white font-bold py-4 rounded-lg shadow-lg shadow-green-900/20 transform active:scale-[0.99] transition-all"
                >
                  🚀 Launch Training Job
                </button>
              </div>
            </div>
            
          </div>
        </div>
      </div>
    </div>
  );
}