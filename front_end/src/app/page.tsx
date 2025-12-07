// 文件: front_end/src/app/page.tsx
"use client";

import { useState, useEffect } from "react";

// 类型定义
interface Branch { name: string; commit_sha: string; }
interface Commit { sha: string; message: string; author: string; date: string; }

export default function Home() {
  // 状态管理
  const [namespace, setNamespace] = useState("zycai"); 
  const [repoName, setRepoName] = useState("magnus");
  const [branches, setBranches] = useState<Branch[]>([]);
  const [commits, setCommits] = useState<Commit[]>([]);
  
  const [selectedBranch, setSelectedBranch] = useState("");
  const [selectedCommit, setSelectedCommit] = useState("");
  const [command, setCommand] = useState("python train.py");
  
  const [loading, setLoading] = useState(false);

  // 获取分支
  const fetchBranches = async () => {
    setLoading(true);
    setBranches([]); setCommits([]); 
    try {
      const res = await fetch(`http://127.0.0.1:8017/api/github/${namespace}/${repoName}/branches`);
      if (!res.ok) throw new Error("Failed");
      const data = await res.json();
      setBranches(data);
      if (data.length > 0) setSelectedBranch(data[0].name);
    } catch (e) {
      alert("❌ 无法获取分支，请检查后端是否启动，或仓库名是否正确");
    } finally {
      setLoading(false);
    }
  };

  // 监听分支变化，自动获取 Commits
  useEffect(() => {
    if (!selectedBranch) return;
    const fetchCommits = async () => {
      try {
        const res = await fetch(`http://127.0.0.1:8017/api/github/${namespace}/${repoName}/commits?branch=${selectedBranch}`);
        const data = await res.json();
        setCommits(data);
        if (data.length > 0) setSelectedCommit(data[0].sha);
      } catch (e) { console.error(e); }
    };
    fetchCommits();
  }, [selectedBranch, namespace, repoName]);

  // 提交任务
  const handleSubmit = async () => {
    const payload = {
      namespace,
      repo_name: repoName,
      branch: selectedBranch,
      commit_sha: selectedCommit,
      entry_command: command
    };
    
    try {
      const res = await fetch("http://127.0.0.1:8017/api/jobs/submit", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      const result = await res.json();
      alert(`✅ 后端响应: ${result.msg}`);
    } catch (e) {
      alert("❌ 提交失败，后端未响应");
    }
  };

  return (
    <div className="min-h-screen bg-black text-gray-100 flex items-center justify-center p-4 font-mono">
      <div className="w-full max-w-3xl bg-gray-900 border border-gray-800 rounded-xl p-8 shadow-2xl">
        {/* 标题 */}
        <div className="mb-8 border-b border-gray-800 pb-4">
          <h1 className="text-3xl font-bold text-transparent bg-clip-text bg-gradient-to-r from-blue-400 to-purple-500">
            Magnus AI Platform
          </h1>
          <p className="text-gray-500 text-sm mt-2">Next-Gen AI Infrastructure Scheduler</p>
        </div>

        <div className="space-y-6">
          {/* 仓库输入区 */}
          <div className="grid grid-cols-12 gap-4">
            <div className="col-span-4">
              <label className="text-xs text-gray-500 uppercase tracking-wider mb-1 block">GitHub Namespace</label>
              <input 
                className="w-full bg-gray-950 border border-gray-700 p-3 rounded text-white focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none transition-all" 
                value={namespace} onChange={e => setNamespace(e.target.value)}
              />
            </div>
            <div className="col-span-5">
              <label className="text-xs text-gray-500 uppercase tracking-wider mb-1 block">Repository Name</label>
              <input 
                className="w-full bg-gray-950 border border-gray-700 p-3 rounded text-white focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none transition-all" 
                value={repoName} onChange={e => setRepoName(e.target.value)}
              />
            </div>
            <div className="col-span-3 flex items-end">
              <button 
                onClick={fetchBranches}
                disabled={loading}
                className="w-full bg-blue-600 hover:bg-blue-500 text-white font-bold py-3 rounded transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {loading ? "Scanning..." : "Scan Repo"}
              </button>
            </div>
          </div>

          {/* 分支与Commit选择区 */}
          {branches.length > 0 && (
            <div className="grid grid-cols-2 gap-6 bg-gray-950 p-4 rounded border border-gray-800">
              <div>
                <label className="text-xs text-gray-500 uppercase tracking-wider mb-1 block">Target Branch</label>
                <select 
                  className="w-full bg-gray-900 border border-gray-700 p-2 rounded text-white outline-none"
                  value={selectedBranch} onChange={e => setSelectedBranch(e.target.value)}
                >
                  {branches.map(b => <option key={b.name} value={b.name}>{b.name}</option>)}
                </select>
              </div>
              <div>
                <label className="text-xs text-gray-500 uppercase tracking-wider mb-1 block">Target Commit</label>
                <select 
                  className="w-full bg-gray-900 border border-gray-700 p-2 rounded text-white text-xs font-mono outline-none"
                  value={selectedCommit} onChange={e => setSelectedCommit(e.target.value)}
                >
                  {commits.map(c => (
                    <option key={c.sha} value={c.sha}>
                      {c.sha.substring(0, 7)} - {c.message.substring(0, 30)}...
                    </option>
                  ))}
                </select>
              </div>
            </div>
          )}

          {/* 启动命令输入区 (Milestone 1 的自由文本框) */}
          {selectedCommit && (
             <div>
              <label className="text-xs text-gray-500 uppercase tracking-wider mb-1 block">Entry Command</label>
              <div className="relative">
                <span className="absolute left-3 top-3 text-gray-500">$</span>
                <input 
                  className="w-full bg-gray-950 border border-gray-700 p-3 pl-8 rounded text-green-400 font-mono focus:border-green-500 outline-none" 
                  value={command} onChange={e => setCommand(e.target.value)}
                />
              </div>
            </div>
          )}

          {/* 提交按钮 */}
          <button 
            onClick={handleSubmit}
            className="w-full mt-4 bg-gradient-to-r from-green-600 to-emerald-600 hover:from-green-500 hover:to-emerald-500 text-white font-bold py-4 rounded-lg shadow-lg transform active:scale-[0.99] transition-all disabled:opacity-50 disabled:cursor-not-allowed"
            disabled={!selectedCommit}
          >
            🚀 Launch Training Job
          </button>
        </div>
      </div>
    </div>
  );
}