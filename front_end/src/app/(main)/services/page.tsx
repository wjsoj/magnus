// front_end/src/app/(main)/services/page.tsx
"use client";

import { useState, useEffect, useCallback, useMemo } from "react";
import { Search, Plus } from "lucide-react";
import { client } from "@/lib/api";
import { POLL_INTERVAL } from "@/lib/config";
import { Service } from "@/types/service";
import { User } from "@/types/job";
import { SearchableSelect } from "@/components/ui/searchable-select";
import { PaginationControls } from "@/components/ui/pagination-controls";
import { ServiceTable } from "@/components/services/service-table";
import { ServiceDrawer } from "@/components/services/service-drawer";

export default function ServicesPage() {
  const [services, setServices] = useState<Service[]>([]);
  const [allUsers, setAllUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(true);

  const [searchQuery, setSearchQuery] = useState("");
  const [debouncedQuery, setDebouncedQuery] = useState("");
  const [selectedUserId, setSelectedUserId] = useState("");

  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [totalItems, setTotalItems] = useState(0);

  // Drawer State
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);
  const [editingService, setEditingService] = useState<Service | null>(null);

  const skip = (currentPage - 1) * pageSize;

  // 1. Fetch Services
  const fetchServices = useCallback(async (isBackground = false) => {
    if (!isBackground) setLoading(true);
    try {
      const params = new URLSearchParams({
        skip: skip.toString(),
        limit: pageSize.toString(),
      });
      if (debouncedQuery.trim()) params.append("search", debouncedQuery.trim());
      if (selectedUserId) params.append("owner_id", selectedUserId);

      const data = await client(`/api/services?${params.toString()}`);
      setServices(data.items);
      setTotalItems(data.total);
    } catch (e) {
      console.error("Backend offline?", e);
    } finally {
      if (!isBackground) setLoading(false);
    }
  }, [skip, pageSize, debouncedQuery, selectedUserId]);

  // 2. Fetch Users
  useEffect(() => {
    const fetchUsers = async () => {
      try {
        const users = await client("/api/users");
        setAllUsers(users);
      } catch (e) {
        console.error("Failed to load users list", e);
      }
    };
    fetchUsers();
  }, []);

  const userFilterOptions = useMemo(() => {
    return [
      { label: "All Users", value: "", icon: "/api/logo" },
      ...allUsers.map((u) => ({
        label: u.name,
        value: u.id,
        meta: u.email || "",
        icon: u.avatar_url,
      })),
    ];
  }, [allUsers]);

  // 3. Debounce & Polling
  useEffect(() => {
    const timer = setTimeout(() => setDebouncedQuery(searchQuery), 300);
    return () => clearTimeout(timer);
  }, [searchQuery]);

  useEffect(() => {
    setCurrentPage(1);
  }, [debouncedQuery, selectedUserId]);

  useEffect(() => {
    fetchServices();
    const intervalId = setInterval(() => fetchServices(true), POLL_INTERVAL);
    return () => clearInterval(intervalId);
  }, [fetchServices]);

  // Handlers
  const handleCreate = () => {
    setEditingService(null);
    setIsDrawerOpen(true);
  };

  const handleEdit = (svc: Service) => {
    setEditingService(svc);
    setIsDrawerOpen(true);
  };

  const handleSuccess = () => {
    setIsDrawerOpen(false);
    fetchServices();
  };

  return (
    <div className="relative min-h-[calc(100vh-8rem)] pb-20">
      <style jsx global>{`
        ::-webkit-scrollbar {
          display: none;
        }
        html {
          -ms-overflow-style: none;
          scrollbar-width: none;
        }
      `}</style>

      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-bold text-white tracking-tight flex items-center gap-2">
            Service Registry
          </h1>
          <p className="text-zinc-500 text-sm mt-1">
            Manage persistent endpoints and elastic drivers.
          </p>
        </div>
        <button
          onClick={handleCreate}
          className="bg-blue-600 hover:bg-blue-500 text-white px-4 py-2 rounded-lg text-sm font-medium flex items-center gap-2 transition-colors shadow-lg shadow-blue-900/20 active:scale-95 border border-blue-500/50"
        >
          <Plus className="w-4 h-4" /> New Service
        </button>
      </div>

      {/* Filters & Search */}
      <div className="bg-zinc-900/40 border border-zinc-800 rounded-xl p-1.5 mb-6 flex items-center gap-2 backdrop-blur-sm relative z-20">
        <div className="relative flex-1 group">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-500 group-focus-within:text-blue-500 transition-colors" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search by Service Name or ID..."
            className="w-full bg-transparent border-none py-2.5 pl-9 pr-4 text-sm text-zinc-200 focus:outline-none focus:ring-0 placeholder-zinc-600"
          />
        </div>
        <div className="h-6 w-px bg-zinc-800"></div>
        <div className="w-56">
          <SearchableSelect
            value={selectedUserId}
            onChange={setSelectedUserId}
            options={userFilterOptions}
            placeholder="Filter by Owner"
            className="mb-0 border-none bg-transparent"
          />
        </div>
      </div>

      <div className="bg-zinc-900/40 border border-zinc-800 rounded-xl overflow-hidden backdrop-blur-sm">
        <ServiceTable
          services={services}
          loading={loading}
          onEdit={handleEdit}
        />
        {services.length > 0 && (
          <div className="px-6 py-2 border-zinc-900/30">
            <PaginationControls
              currentPage={currentPage}
              totalPages={Math.ceil(totalItems / pageSize)}
              pageSize={pageSize}
              totalItems={totalItems}
              onPageChange={setCurrentPage}
              onPageSizeChange={(newSize) => {
                setPageSize(newSize);
                setCurrentPage(1);
              }}
            />
          </div>
        )}
      </div>

      <ServiceDrawer
        isOpen={isDrawerOpen}
        onClose={() => setIsDrawerOpen(false)}
        initialData={editingService}
        onSuccess={handleSuccess}
      />
    </div>
  );
}