// front_end/src/components/ui/searchable-select.tsx
"use client";

import { useState, useEffect, useRef, useMemo } from "react";
import { X, Search, ChevronDown, ChevronUp } from "lucide-react";

interface SearchableSelectProps {
  label?: string;
  value: string;
  options: { label: string; value: string; meta?: string }[];
  onChange: (val: string) => void;
  placeholder?: string;
  disabled?: boolean;
  hasError?: boolean;
  id?: string;
  className?: string;
  // ✅ 新增：控制弹出方向 'top' | 'bottom'
  placement?: "top" | "bottom"; 
  // ✅ 新增：极简模式 (隐藏搜索图标，适合窄选择器)
  minimal?: boolean; 
}

export function SearchableSelect({ 
  label, value, options, onChange, placeholder, disabled, hasError, id, className = "",
  placement = "bottom", 
  minimal = false 
}: SearchableSelectProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [query, setQuery] = useState("");
  const containerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // 初始化和外部更新
  useEffect(() => {
    const selectedOption = options.find(o => o.value === value);
    if (selectedOption) {
        setQuery(selectedOption.label);
    } else if (value) {
        setQuery(value);
    } else {
        setQuery("");
    }
  }, [value, options]);

  // 点击外部关闭
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setIsOpen(false);
        // 恢复显示
        const selectedOption = options.find(o => o.value === value);
        if (selectedOption) setQuery(selectedOption.label);
        else if (value) setQuery(value);
        else setQuery("");
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
    // 如果 Query 等于当前选中的 Label，说明用户没在搜，展示所有
    const selectedOption = options.find(o => o.value === value);
    if (selectedOption && query === selectedOption.label) return options;
    
    return options.filter((opt) => {
      const searchStr = (opt.label + (opt.meta || "")).toLowerCase();
      return searchStr.includes(query.toLowerCase());
    });
  }, [query, options, value]);

  return (
    <div className={`relative ${className}`} ref={containerRef} id={id}>
      {label && (
        <label className={`text-xs uppercase tracking-wider mb-1.5 block font-medium transition-colors ${hasError ? 'text-red-500' : 'text-zinc-500'}`}>
          {label} {hasError && "*"}
        </label>
      )}
      
      {/* Input Container */}
      <div className="relative group">
        <input
          ref={inputRef}
          type="text"
          disabled={disabled}
          // ✅ 样式逻辑：如果是 minimal 模式，padding 改小，且隐藏右侧的大 padding
          className={`w-full bg-zinc-950 border px-3 py-2.5 rounded-lg text-sm text-white outline-none transition-all placeholder-zinc-600 
            disabled:cursor-not-allowed disabled:text-zinc-500 disabled:bg-zinc-900/50
            ${minimal ? 'pr-6 text-center' : 'pr-10'} 
            ${hasError ? 'animate-shake border-red-500' : isOpen ? 'border-blue-500 ring-1 ring-blue-500/20' : 'border-zinc-800 hover:border-zinc-700'}
          `}
          placeholder={disabled ? "Waiting..." : (placeholder || "Search...")}
          value={query}
          onChange={(e) => { setQuery(e.target.value); setIsOpen(true); }}
          onFocus={() => !disabled && !minimal && setIsOpen(true)}
          // 如果是 minimal 模式，点击整个输入框都应该 toggle
          onClick={() => minimal && !disabled && setIsOpen(!isOpen)}
        />
        
        {/* Right Icons (Standard Mode) */}
        {!minimal && (
          <div className="absolute right-3 top-0 h-full flex items-center gap-2">
            {!disabled && query && (
              <button onClick={handleClear} className="p-0.5 text-zinc-500 hover:text-white rounded-full transition-colors">
                <X className="w-3.5 h-3.5" />
              </button>
            )}
            <div className="pointer-events-none text-zinc-600">
              <Search className="w-3.5 h-3.5" />
            </div>
          </div>
        )}

        {/* Minimal Mode Indicator (Optional, e.g., small chevron) */}
        {minimal && !disabled && (
           <div className="absolute right-2 top-0 h-full flex items-center pointer-events-none text-zinc-600">
              {placement === 'top' ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
           </div>
        )}
      </div>
      
      {/* Dropdown Menu */}
      {isOpen && !disabled && (
        <div className={`absolute z-[100] left-0 w-full bg-[#0F0F11] border border-zinc-800 rounded-lg shadow-2xl overflow-hidden max-h-60 overflow-y-auto custom-scrollbar
            ${placement === 'top' ? 'bottom-full mb-1' : 'top-full mt-1'} 
        `}>
          {filteredOptions.map((opt) => (
            <div 
              key={opt.value} 
              onClick={() => { onChange(opt.value); setQuery(opt.label); setIsOpen(false); }} 
              className={`px-3 py-2 cursor-pointer border-b border-zinc-800/50 last:border-0 hover:bg-blue-500/10 transition-colors flex items-center justify-between
                ${opt.value === value ? 'bg-blue-500/20 text-blue-400' : 'text-zinc-300'}
              `}
            >
              <div className="text-sm font-medium">{opt.label}</div>
              {opt.meta && <div className="text-[10px] text-zinc-600 font-mono ml-2">{opt.meta}</div>}
            </div>
          ))}
          {filteredOptions.length === 0 && <div className="p-3 text-center text-zinc-500 text-xs">No results</div>}
        </div>
      )}
    </div>
  );
}