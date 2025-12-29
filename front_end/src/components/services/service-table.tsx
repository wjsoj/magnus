// front_end/src/components/services/service-table.tsx
"use client";

import { Loader2, Power, Activity, ExternalLink, Settings, Box } from "lucide-react";
import { Service } from "@/types/service";
import { CopyableText } from "@/components/ui/copyable-text";
import { UserAvatar } from "@/components/ui/user-avatar";
import { JobStatusBadge } from "@/components/jobs/job-status-badge";

interface ServiceTableProps {
  services: Service[];
  loading: boolean;
  onEdit: (service: Service) => void;
  className?: string;
}

export function ServiceTable({
  services,
  loading,
  onEdit,
  className = "min-h-[400px]",
}: ServiceTableProps) {
  if (loading) {
    return (
      <div className={`border border-zinc-800 rounded-xl bg-zinc-900/30 shadow-sm flex flex-col items-center justify-center text-zinc-500 gap-3 ${className}`}>
        <Loader2 className="w-8 h-8 animate-spin text-teal-500" />
        <p className="text-sm font-medium">Fetching services...</p>
      </div>
    );
  }

  if (services.length === 0) {
    return (
      <div className={`border border-zinc-800 rounded-xl bg-zinc-900/30 shadow-sm flex flex-col items-center justify-center text-zinc-500 ${className}`}>
        <Box className="w-10 h-10 opacity-20 mb-3" />
        <p className="text-base font-medium text-zinc-400">No services found</p>
      </div>
    );
  }

  return (
    <div className={`border border-zinc-800 rounded-xl bg-zinc-900/30 shadow-sm flex flex-col overflow-hidden ${className ? className.replace(/min-h-\[.*?\]/g, "") : ""}`}>
      <div className="overflow-x-auto w-full">
        <table className="w-full text-left text-sm whitespace-nowrap table-fixed">
          <thead className="bg-zinc-900/90 text-zinc-500 border-b border-zinc-800 backdrop-blur-md">
            <tr>
              <th className="px-6 py-4 font-medium w-[25%]">Service Identity</th>
              <th className="px-6 py-4 font-medium w-[15%] text-center">Status</th>
              <th className="px-6 py-4 font-medium w-[25%] text-center">Proxy Endpoint</th>
              <th className="px-6 py-4 font-medium w-[20%] text-center">Config / Resources</th>
              <th className="px-6 py-4 font-medium text-right w-[15%]"></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-800/50">
            {services.map((svc) => {
              const proxyUrl = typeof window !== "undefined"
                ? `${window.location.protocol}//${window.location.hostname}:${window.location.port || ""}/api/services/${svc.id}/`
                : `/api/services/${svc.id}/`;

              return (
                <tr
                  key={svc.id}
                  className="hover:bg-zinc-800/40 transition-colors group border-b border-zinc-800/50 last:border-0"
                >
                  <td className="px-6 py-4 align-top">
                    <div className="flex flex-col gap-1.5">
                      <span className="font-semibold text-zinc-200 text-base">{svc.name}</span>
                      <span className="text-xs text-zinc-500 font-mono tracking-wider">{svc.id}</span>
                      <div className="flex items-center gap-2 mt-0.5">
                        <UserAvatar user={svc.owner} subText={null} />
                      </div>
                    </div>
                  </td>

                  <td className="px-6 py-4 align-top text-center">
                    <div className="flex flex-col items-center gap-2">
                      {svc.is_active ? (
                        <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-teal-500/10 text-teal-400 text-xs font-medium border border-teal-500/20">
                          <Activity className="w-3 h-3" /> Active
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-zinc-800 text-zinc-500 text-xs font-medium border border-zinc-700">
                          <Power className="w-3 h-3" /> Inactive
                        </span>
                      )}
                      {svc.current_job ? (
                        <div className="scale-90 opacity-90">
                          <JobStatusBadge status={svc.current_job.status} />
                        </div>
                      ) : (
                        <span className="text-[10px] text-zinc-600 uppercase tracking-wider font-medium">
                          Idle (Scale 0)
                        </span>
                      )}
                    </div>
                  </td>

                  <td className="px-6 py-4 align-middle text-center">
                    <div className="flex flex-col items-center gap-1.5">
                      <div className="bg-zinc-950/50 border border-zinc-800/50 rounded px-2 py-1 max-w-full">
                        <CopyableText
                          text={proxyUrl}
                          variant="id"
                          className="max-w-[180px] truncate !text-zinc-400"
                        />
                      </div>
                      <a
                        href={proxyUrl}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-[10px] text-blue-400 hover:text-blue-300 flex items-center justify-center gap-1 transition-colors"
                      >
                        Open in new tab <ExternalLink className="w-2.5 h-2.5" />
                      </a>
                    </div>
                  </td>

                  <td className="px-6 py-4 align-top text-center">
                    <div className="flex flex-col gap-1.5 text-xs text-zinc-400">
                      <span className="font-mono bg-zinc-800/50 px-2 py-0.5 rounded border border-zinc-800 inline-block">
                        {svc.gpu_type} × {svc.gpu_count}
                      </span>
                      <span className="text-zinc-500">Idle Timeout: {svc.idle_timeout}m</span>
                    </div>
                  </td>

                  <td className="px-6 py-4 align-middle text-right">
                    <button
                      onClick={() => onEdit(svc)}
                      className="p-2 bg-zinc-800 hover:bg-zinc-700 hover:text-white rounded-lg text-zinc-400 transition-colors border border-zinc-700/50 shadow-sm opacity-0 group-hover:opacity-100 transform translate-x-2 group-hover:translate-x-0 transition-all"
                    >
                      <Settings className="w-4 h-4" />
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}