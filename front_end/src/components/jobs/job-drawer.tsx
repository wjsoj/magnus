// front_end/src/components/jobs/job-drawer.tsx
import { useEffect, useState } from "react";
import { Rocket, RefreshCw } from "lucide-react";
import JobForm, { JobFormData } from "@/components/jobs/job-form";

interface JobDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: () => void;
  mode: "create" | "clone";
  initialData: JobFormData | null;
  // 用于强制重置 Form 的 key，通常用 mode + id 组合
  formKey?: string; 
}

export function JobDrawer({ 
  isOpen, 
  onClose, 
  onSuccess, 
  mode, 
  initialData, 
  formKey 
}: JobDrawerProps) {
  
  // 处理 ESC 键关闭
  useEffect(() => {
    const handleEsc = (e: KeyboardEvent) => {
      if (e.key === "Escape" && isOpen) onClose();
    };
    window.addEventListener("keydown", handleEsc);
    return () => window.removeEventListener("keydown", handleEsc);
  }, [isOpen, onClose]);

  return (
    <>
      {/* Backdrop */}
      {isOpen && (
        <div 
          onClick={onClose} 
          className="fixed inset-0 bg-black/60 backdrop-blur-sm z-[90] transition-opacity" 
        />
      )}

      {/* Drawer Panel */}
      <div className={`fixed top-0 right-0 h-full w-[600px] bg-[#09090b] border-l border-zinc-800 shadow-2xl z-[100] transform transition-transform duration-300 ease-in-out ${isOpen ? 'translate-x-0' : 'translate-x-full'}`}>
        <div className="h-full flex flex-col relative">
          
          {/* Header */}
          <div className="px-6 py-5 border-b border-zinc-800 flex items-center justify-between bg-zinc-900/50 backdrop-blur-sm">
            <div>
                <h2 className="text-lg font-bold text-white flex items-center gap-2">
                    {mode === 'create' ? <Rocket className="w-5 h-5 text-blue-500"/> : <RefreshCw className="w-5 h-5 text-purple-500"/>}
                    {mode === 'create' ? "Submit New Job" : `Clone Job`}
                </h2>
                {mode === 'clone' && <p className="text-xs text-zinc-500 mt-1">Configurations pre-filled from previous task</p>}
            </div>
            <button 
              onClick={onClose} 
              className="text-zinc-500 hover:text-white transition-colors bg-zinc-800/50 hover:bg-zinc-700 p-1.5 rounded-md"
            >
              ✕
            </button>
          </div>

          {/* Body */}
          <div className="flex-1 overflow-y-auto p-6 custom-scrollbar relative">
            <JobForm 
                key={formKey || mode} 
                mode={mode}
                initialData={initialData}
                onCancel={onClose}
                onSuccess={onSuccess}
            />
          </div>
        </div>
      </div>
    </>
  );
}