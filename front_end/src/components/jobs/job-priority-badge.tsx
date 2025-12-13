// front_end/src/components/jobs/job-priority-badge.tsx
import React from 'react';

export function JobPriorityBadge({ type }: { type: string }) {
  const isNoble = type && type.startsWith('A');
  return (
    <span className={`inline-flex items-center px-2.5 py-1 rounded-md text-[11px] md:text-xs font-mono font-bold tracking-tight border shadow-sm select-none
      ${isNoble 
        ? 'bg-purple-500/10 text-purple-400 border-purple-500/30' 
        : 'bg-zinc-800/80 text-zinc-400 border-zinc-700/50'
      }`}>
      {type || 'A2'}
    </span>
  );
}