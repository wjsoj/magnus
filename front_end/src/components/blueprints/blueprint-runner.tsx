// front_end/src/components/blueprints/blueprint-runner.tsx
"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { Terminal, Loader2, Play } from "lucide-react";
import { client } from "@/lib/api";
import { Drawer } from "@/components/ui/drawer";
import { DynamicForm } from "@/components/ui/dynamic-form";
import { FieldSchema } from "@/components/ui/dynamic-form/types";

interface BlueprintRunnerProps {
  blueprint: { id: string; title: string } | null;
  onClose: () => void;
}

export function BlueprintRunner({ blueprint, onClose }: BlueprintRunnerProps) {
  const router = useRouter();
  
  const [paramsSchema, setParamsSchema] = useState<FieldSchema[]>([]);
  const [formValues, setFormValues] = useState<Record<string, any>>({});
  
  const [isLoadingSchema, setIsLoadingSchema] = useState(false);
  const [isRunning, setIsRunning] = useState(false);

  const [errorField, setErrorField] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    if (blueprint?.id) {
      let isMounted = true; 

      const fetchSchema = async () => {
        setIsLoadingSchema(true);
        setParamsSchema([]);
        setErrorField(null);
        setErrorMessage(null);

        try {
          const schema = await client(`/api/blueprints/${blueprint.id}/schema`);

          if (isMounted) {
            setParamsSchema(schema);
            const initial: Record<string, any> = {};
            schema.forEach((p: FieldSchema) => {
              initial[p.key] = p.default ?? "";
            });
            setFormValues(initial);
          }
        } catch (e) {
          if (isMounted) {
            alert("Failed to parse blueprint schema.");
            onClose();
          }
        } finally {
          if (isMounted) setIsLoadingSchema(false);
        }
      };

      fetchSchema();

      return () => { isMounted = false; };
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [blueprint?.id]);

  const scrollToError = (key: string) => {
    // 给予微小的延时，确保 DynamicForm 内部的 useEffect 已经处理完 Scope 的展开渲染
    setTimeout(() => {
      const el = document.getElementById(`field-${key}`);
      if (el) {
        el.scrollIntoView({ behavior: 'smooth', block: 'center' });
      }
    }, 100);
  };

  const handleRun = async () => {
    if (!blueprint) return;

    setErrorField(null);
    setErrorMessage(null);

    for (const param of paramsSchema) {
      // 仅检查 text 类型且明确标记 allow_empty 为 false 的字段
      if (param.type === 'text' && param.allow_empty === false) {
        const val = formValues[param.key];
        if (!val || (typeof val === 'string' && !val.trim())) {
          const label = param.label || param.key;
          setErrorField(param.key);
          setErrorMessage(`⚠️ ${label} is required`);
          scrollToError(param.key);
          return;
        }
      }
    }

    setIsRunning(true);
    try {
      await client(`/api/blueprints/${blueprint.id}/run`, { method: "POST", json: formValues });
      router.push('/jobs');
    } catch (e: any) {
      setErrorMessage(`Error: ${e.message}`);
      setIsRunning(false);
    }
  };

  const handleFieldChange = (key: string, val: any) => {
    setFormValues(prev => ({ ...prev, [key]: val }));
    if (errorField === key) {
      setErrorField(null);
      setErrorMessage(null);
    }
  };

  return (
    <Drawer
      isOpen={!!blueprint}
      onClose={onClose}
      title={blueprint?.title}
      description="Configure parameters to launch this task"
      icon={<Terminal className="w-5 h-5 text-blue-500" />}
      width="w-[600px]"
    >
      <div className="flex flex-col min-h-full">
        <div className="flex-1 pb-4">
          <DynamicForm
            schema={paramsSchema}
            values={formValues}
            onChange={handleFieldChange}
            isLoading={isLoadingSchema}
            errorField={errorField}
          />
        </div>

        <div className="mt-auto pt-6 border-t border-zinc-800 flex flex-col-reverse sm:flex-row sm:justify-between sm:items-center gap-4 pb-1">
          {errorMessage ? (
            <span className="text-red-500 text-xs font-bold animate-pulse text-center sm:text-left transition-all">
              {errorMessage}
            </span>
          ) : (
            <span className="text-zinc-500 text-xs text-center sm:text-left hidden sm:block transition-all">
              Waiting for launch
            </span>
          )}
          
          <div className="flex gap-3 w-full sm:w-auto">
            <button
              onClick={onClose}
              disabled={isRunning}
              className="flex-1 sm:flex-none px-4 py-2.5 rounded-lg text-sm font-medium text-zinc-400 hover:text-white hover:bg-zinc-800 transition-colors"
            >
              Cancel
            </button>
            <button
              onClick={handleRun}
              disabled={isRunning || isLoadingSchema}
              className="flex-1 sm:flex-none px-6 py-2.5 rounded-lg text-sm font-medium bg-blue-600 hover:bg-blue-500 text-white shadow-lg shadow-blue-900/20 active:scale-95 transition-all flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isRunning ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" /> 
                  Launching...
                </>
              ) : (
                <>
                  <Play className="w-4 h-4 fill-current" /> 
                  Launch
                </>
              )}
            </button>
          </div>
        </div>
      </div>
    </Drawer>
  );
}