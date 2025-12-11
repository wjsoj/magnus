// front_end/src/components/ui/copyable-text.tsx
"use client";

import { useState } from "react";
import { Copy, Check } from "lucide-react";

interface CopyableTextProps {
  text: string;
  copyValue?: string;
  label?: string;
  className?: string;
  variant?: "id" | "text"; 
}

export function CopyableText({ 
  text, 
  copyValue, 
  label, 
  className = "", 
  variant = "id" 
}: CopyableTextProps) {
  const [copied, setCopied] = useState(false);
  const valueToCopy = copyValue || text;

  const handleCopy = (e: React.MouseEvent) => {
    e.stopPropagation();
    navigator.clipboard.writeText(valueToCopy);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };


  const baseStyles = variant === "id" 
    ? "text-xs text-zinc-500 font-mono" 
    : "w-full";
  return (
    <button 
      onClick={handleCopy}
      className={`flex items-start text-left gap-1.5 transition-colors group/copy ${baseStyles} hover:text-blue-400 ${className}`}
      title="Click to copy"
    >
      {label && <span className="text-zinc-600 flex-shrink-0">{label}</span>}
      <span className={`min-w-0 ${variant === "text" ? "whitespace-normal break-all" : "truncate"}`}>
        {text}
      </span>
      <div className="flex-shrink-0 mt-[0.15em]">
        {copied ? (
          <Check className="w-3.5 h-3.5 text-green-500" />
        ) : (
          <Copy className="w-3.5 h-3.5 opacity-0 group-hover/copy:opacity-100 transition-opacity" />
        )}
      </div>
    </button>
  );
}